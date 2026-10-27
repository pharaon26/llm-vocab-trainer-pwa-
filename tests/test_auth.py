from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.config import settings
from app.main import app
from app.models import LoginAttempt, User, UserSession
from app.security import hash_password
from tests.conftest import STUDENT_PASSWORD, session_cookie_of

PASSWORD = STUDENT_PASSWORD
NAME = settings.session_cookie_name


def cookie(value):
    return {"Cookie": f"{NAME}={value}"}


async def register(client, name="Anna", password=PASSWORD, role=None, **kwargs):
    body = {"name": name, "password": password, "password_confirm": password}
    if role is not None:
        body["role"] = role
    return await client.post("/auth/register", json=body, **kwargs)


async def attempt(client, name="Anna", password="wrong-password", **extra):
    return await client.post("/auth/login", json={"name": name, "password": password, **extra})


async def registered(client, name="Anna"):
    response = await register(client, name)
    assert response.status_code == 201
    return session_cookie_of(response)


def set_cookie_header(response) -> str:
    return next(h for h in response.headers.get_list("set-cookie") if h.startswith(f"{NAME}="))


async def test_register_login_and_me(client):
    created = await register(client, " Anna ")
    assert created.status_code == 201
    assert created.json() == {"name": "Anna", "role": "student"}
    me = await client.get("/auth/me", headers=cookie(session_cookie_of(created)))
    assert me.json() == {"name": "Anna", "role": "student"}
    logged = await attempt(client, "Anna", PASSWORD)
    assert logged.status_code == 200
    assert session_cookie_of(logged) != session_cookie_of(created)


async def test_login_sets_a_session_cookie_with_safe_flags(client):
    await register(client)
    response = await attempt(client, "Anna", PASSWORD)
    header = set_cookie_header(response).lower()
    assert "httponly" in header and "secure" in header
    assert "samesite=lax" in header and "path=/" in header
    assert f"max-age={settings.session_ttl_days * 86400}" in header
    assert "session_id" not in response.text and session_cookie_of(response) not in response.text


async def test_secure_flag_can_be_switched_off_for_local_http(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    header = set_cookie_header(await register(client)).lower()
    assert "secure" not in header and "httponly" in header and "samesite=lax" in header


async def test_requests_without_cookie_are_rejected(client):
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/session/next")).status_code == 401
    assert (await client.get("/auth/me", headers=cookie("fake"))).status_code == 401
    assert (await client.get("/auth/me", headers={"Authorization": "Bearer anything"})).status_code == 401


async def test_authorization_header_is_not_a_way_to_log_in(client):
    value = await registered(client)
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {value}"})).status_code == 401


async def test_only_the_hash_of_the_session_id_is_stored(client, db):
    value = await registered(client)
    stored = list(await db.scalars(select(UserSession.session_hash)))
    assert value not in stored and len(stored) == 1 and len(stored[0]) == 64


async def test_expired_session_is_rejected(client, db):
    value = await registered(client)
    assert (await client.get("/auth/me", headers=cookie(value))).status_code == 200
    await db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()
    assert (await client.get("/auth/me", headers=cookie(value))).status_code == 401


async def test_session_lifetime_comes_from_settings(client, db, monkeypatch):
    monkeypatch.setattr(settings, "session_ttl_days", 2)
    await register(client)
    expires = await db.scalar(select(UserSession.expires_at))
    assert timedelta(days=1, hours=23) < expires - datetime.now(UTC) <= timedelta(days=2)


async def test_expired_sessions_are_swept_on_login(client, db):
    await register(client)
    await db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
    await db.commit()
    await attempt(client, "Anna", PASSWORD)
    assert await db.scalar(select(func.count()).select_from(UserSession)) == 1


async def test_logout_removes_the_session_and_clears_the_cookie(client, db):
    first = await registered(client)
    second = session_cookie_of(await attempt(client, "Anna", PASSWORD))
    response = await client.post("/auth/logout", headers=cookie(first))
    assert response.status_code == 204
    cleared = set_cookie_header(response).lower()
    assert "max-age=0" in cleared or "expires=" in cleared
    assert cleared.startswith(f"{NAME}=\"\"") or cleared.startswith(f"{NAME}=;")
    assert (await client.get("/auth/me", headers=cookie(first))).status_code == 401
    assert (await client.get("/auth/me", headers=cookie(second))).status_code == 200
    assert await db.scalar(select(func.count()).select_from(UserSession)) == 1
    assert (await client.post("/auth/logout", headers=cookie(first))).status_code == 204
    assert (await client.post("/auth/logout", headers={"Cookie": ""})).status_code == 204


async def test_login_replaces_the_session_of_this_browser(client, db):
    old = await registered(client)
    other = await registered(client, "Boris")
    response = await client.post(
        "/auth/login", json={"name": "Anna", "password": PASSWORD}, headers=cookie(old)
    )
    new = session_cookie_of(response)
    assert new and new != old
    assert (await client.get("/auth/me", headers=cookie(old))).status_code == 401
    assert (await client.get("/auth/me", headers=cookie(new))).json()["name"] == "Anna"
    assert (await client.get("/auth/me", headers=cookie(other))).status_code == 200


async def test_login_as_another_user_drops_the_previous_session(client):
    old = await registered(client)
    await registered(client, "Boris")
    response = await client.post(
        "/auth/login", json={"name": "Boris", "password": PASSWORD}, headers=cookie(old)
    )
    assert response.status_code == 200
    assert (await client.get("/auth/me", headers=cookie(old))).status_code == 401


async def test_a_session_id_chosen_by_the_attacker_is_never_adopted(client):
    response = await client.post(
        "/auth/register", json={"name": "Victim", "password": PASSWORD, "password_confirm": PASSWORD}, headers=cookie("attacker-known-value")
    )
    assert session_cookie_of(response) != "attacker-known-value"
    assert (await client.get("/auth/me", headers=cookie("attacker-known-value"))).status_code == 401


async def test_browser_flow_with_a_cookie_jar(client):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test", headers={"Origin": "https://test"}
    ) as browser:
        assert (await register(browser)).status_code == 201
        assert (await browser.get("/auth/me")).json()["name"] == "Anna"
        assert (await browser.post("/auth/logout")).status_code == 204
        assert (await browser.get("/auth/me")).status_code == 401
        assert (await attempt(browser, "Anna", PASSWORD)).status_code == 200
        assert (await browser.get("/auth/me")).status_code == 200


async def test_password_is_validated_and_stored_as_a_hash(client, db):
    assert (await register(client, "Short", "1234567")).status_code == 422
    assert (await register(client, "Long", "x" * 129)).status_code == 422
    assert (await register(client, "Anna", "пароль-на-русском")).status_code == 201
    stored = await db.scalar(select(User.password_hash).where(User.name == "Anna"))
    assert stored.startswith("$argon2") and "пароль" not in stored


async def test_password_must_be_repeated_identically(client):
    body = {"name": "Anna", "password": PASSWORD}
    assert (await client.post("/auth/register", json=body)).status_code == 422
    assert (await client.post("/auth/register", json={**body, "password_confirm": PASSWORD + "x"})).status_code == 422
    assert (await client.post("/auth/register", json={**body, "password_confirm": ""})).status_code == 422
    assert (await client.post("/auth/register", json={**body, "password_confirm": PASSWORD})).status_code == 201


async def test_nickname_is_taken_ignoring_case(client):
    await register(client)
    assert (await register(client)).status_code == 409
    assert (await register(client, "ANNA")).status_code == 409
    assert (await register(client, "anna")).status_code == 409


@pytest.mark.parametrize("nickname", ["ab", "a" * 33, "with space", "dash-name", "Анна", "dot.name", "a@b", "emoji😀x", ""])
async def test_nickname_rules(client, nickname):
    assert (await register(client, nickname)).status_code == 422


@pytest.mark.parametrize("nickname", ["abc", "Anna_1", "_x_", "A1b2C3", "a" * 32])
async def test_valid_nicknames(client, nickname):
    assert (await register(client, nickname)).status_code == 201


async def test_login_ignores_nickname_case(client):
    await register(client, "AnnaK")
    assert (await attempt(client, "annak", PASSWORD)).json()["name"] == "AnnaK"


async def test_role_is_chosen_at_registration_and_returned(client):
    student = await register(client, "stud")
    teacher = await register(client, "teach", role="teacher")
    assert student.json()["role"] == "student" and teacher.json()["role"] == "teacher"
    me = await client.get("/auth/me", headers=cookie(session_cookie_of(teacher)))
    assert me.json() == {"name": "teach", "role": "teacher"}


async def test_admin_role_cannot_be_chosen_at_registration(client):
    assert (await register(client, "sneaky", role="admin")).status_code == 422
    assert (await register(client, "sneaky", role="")).status_code == 422


async def test_unknown_role_defaults_are_not_accepted(client):
    body = {"name": "Anna", "password": PASSWORD, "password_confirm": PASSWORD, "role": "superuser"}
    assert (await client.post("/auth/register", json=body)).status_code == 422


async def test_login_has_no_role_parameter_and_roles_come_from_the_database(client, db):
    await register(client, "teach", role="teacher")
    response = await client.post("/auth/login", json={"name": "teach", "password": PASSWORD, "role": "admin"})
    assert response.json()["role"] == "teacher"


async def test_wrong_and_unknown_credentials_look_the_same(client):
    await register(client)
    wrong = await attempt(client, "Anna")
    unknown = await attempt(client, "Nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert not wrong.headers.get_list("set-cookie")
    assert (await client.post("/auth/login", json={"name": "Anna"})).status_code == 401


async def test_accounts_created_before_passwords_cannot_log_in(client, db):
    db.add(User(name="legacy", role="student"))
    await db.commit()
    assert (await attempt(client, "legacy", "")).status_code == 401
    assert (await attempt(client, "legacy", "dummy-password-for-timing")).status_code == 401
    user = await db.scalar(select(User).where(User.name == "legacy"))
    user.password_hash = hash_password("fresh-password")
    await db.commit()
    assert (await attempt(client, "legacy", "fresh-password")).status_code == 200


async def test_there_is_no_shared_teacher_password_anymore(client):
    assert not hasattr(settings, "teacher_password")
    response = await client.post("/auth/login", json={"name": "teach", "password": "secret"})
    assert response.status_code == 401


async def test_non_ascii_password_does_not_crash(client):
    response = await client.post("/auth/login", json={"name": "t", "password": "пароль"})
    assert response.status_code == 401


async def test_teacher_can_log_out(client):
    created = await register(client, "teach", role="teacher")
    headers = cookie(session_cookie_of(created))
    assert (await client.get("/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/auth/me", headers=headers)).status_code == 401


async def test_admin_logs_in_like_everyone(client, db):
    from tests.conftest import make_admin

    await make_admin(db, "boss")
    response = await attempt(client, "boss", PASSWORD)
    assert response.status_code == 200 and response.json()["role"] == "admin"


async def fail_times(client, count, name="Anna", **extra):
    for _ in range(count):
        assert (await attempt(client, name, **extra)).status_code in (401, 403)


async def test_sixth_failed_attempt_for_a_name_is_blocked_with_retry_after(client):
    await register(client)
    await fail_times(client, 5)
    blocked = await attempt(client)
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 15 * 60 + 1


async def test_correct_password_does_not_help_while_blocked(client):
    await register(client)
    await fail_times(client, 5)
    assert (await attempt(client, "Anna", PASSWORD)).status_code == 429


async def test_four_failures_and_a_success_do_not_block(client):
    await register(client)
    await fail_times(client, 4)
    assert (await attempt(client, "Anna", PASSWORD)).status_code == 200
    await fail_times(client, 4)
    assert (await attempt(client, "Anna", PASSWORD)).status_code == 200


async def test_name_limit_is_case_insensitive_and_covers_unknown_names(client):
    await fail_times(client, 3, name="Ghost")
    await fail_times(client, 2, name="ghost ")
    assert (await attempt(client, "GHOST")).status_code == 429


async def test_limit_per_ip_across_different_names(client):
    for index in range(5):
        await attempt(client, f"user{index}")
    assert (await attempt(client, "someone-else")).status_code == 429


async def test_block_expires_after_the_window(client, db):
    await register(client)
    await fail_times(client, 5)
    assert (await attempt(client, "Anna", PASSWORD)).status_code == 429
    await db.execute(update(LoginAttempt).values(created_at=datetime.now(UTC) - timedelta(minutes=16)))
    await db.commit()
    assert (await attempt(client, "Anna", PASSWORD)).status_code == 200


async def test_failures_only_older_than_window_do_not_count(client, db):
    await register(client)
    old = datetime.now(UTC) - timedelta(minutes=14)
    db.add_all([LoginAttempt(name="anna", ip="127.0.0.1", created_at=old) for _ in range(4)])
    await db.commit()
    assert (await attempt(client)).status_code == 401
    assert (await attempt(client)).status_code == 429


async def test_limit_covers_every_role(client):
    await register(client, "teach", role="teacher")
    await fail_times(client, 5, name="teach")
    assert (await attempt(client, "teach", PASSWORD)).status_code == 429


async def test_attempts_are_stored_in_the_database(client, db):
    await fail_times(client, 2)
    rows = (await db.execute(select(LoginAttempt.name, LoginAttempt.ip))).all()
    assert rows == [("anna", "127.0.0.1")] * 2


async def test_forwarded_for_is_ignored_from_untrusted_peers(client):
    for index in range(5):
        await client.post("/auth/login", headers={"X-Forwarded-For": f"203.0.113.{index}"}, json={"name": f"u{index}", "password": "x"})
    assert (await attempt(client, "other")).status_code == 429


async def test_forwarded_for_is_used_behind_a_trusted_proxy(client, monkeypatch, db):
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1"])
    for index in range(5):
        await client.post("/auth/login", headers={"X-Forwarded-For": f"203.0.113.{index}"}, json={"name": f"u{index}", "password": "x"})
    assert (await attempt(client, "other")).status_code == 401
    ips = set(await db.scalars(select(LoginAttempt.ip)))
    assert {f"203.0.113.{index}" for index in range(5)} <= ips


@pytest.mark.parametrize(
    "peer, header, trusted, expected",
    [
        ("10.0.0.5", "1.2.3.4", [], "10.0.0.5"),
        ("10.0.0.5", "1.2.3.4", ["10.0.0.0/8"], "1.2.3.4"),
        ("10.0.0.5", None, ["10.0.0.0/8"], "10.0.0.5"),
        ("8.8.8.8", "1.2.3.4", ["10.0.0.0/8"], "8.8.8.8"),
        ("10.0.0.5", "6.6.6.6, 1.2.3.4", ["10.0.0.0/8"], "1.2.3.4"),
        ("10.0.0.5", "1.2.3.4, 10.0.0.9", ["10.0.0.0/8"], "1.2.3.4"),
        ("10.0.0.5", "10.0.0.8, 10.0.0.9", ["10.0.0.0/8"], "10.0.0.8"),
        ("10.0.0.5", "1.2.3.4, garbage", ["10.0.0.0/8"], "10.0.0.5"),
        ("::1", "2001:db8::1", ["::1"], "2001:db8::1"),
        (None, "1.2.3.4", ["10.0.0.0/8"], "unknown"),
    ],
)
def test_client_ip_resolution(peer, header, trusted, expected):
    from app.security import resolve_client_ip

    assert resolve_client_ip(peer, header, trusted) == expected


def test_comma_separated_lists_in_settings():
    from app.config import Settings

    config = Settings(
        _env_file=None, database_url="postgresql+psycopg://x/y",
        trusted_proxies="10.0.0.0/8, 127.0.0.1", dictionary_audio_domains="a.example,b.example",
        allowed_origins="https://one.example, https://two.example",
    )
    assert config.trusted_proxies == ["10.0.0.0/8", "127.0.0.1"]
    assert config.dictionary_audio_domains == ["a.example", "b.example"]
    assert config.allowed_origins == ["https://one.example", "https://two.example"]


@pytest.mark.parametrize("path", ["/admin/analytics", "/admin/bank", "/admin/decks", "/admin/cards", "/admin/personal-cards"])
async def test_admin_endpoints_are_for_admins_only(client, teacher_headers, student_headers, admin_headers, path):
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=student_headers)).status_code == 403
    assert (await client.get(path, headers=teacher_headers)).status_code == 403
    assert (await client.get(path, headers=admin_headers)).status_code == 200
