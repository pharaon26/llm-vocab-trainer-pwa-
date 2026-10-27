import re

import pytest

from app.config import BASE_DIR, settings
from app.web_security import content_security_policy, origin_of, request_origin_allowed
from tests.conftest import STUDENT_PASSWORD

CREDENTIALS = {"name": "Anna", "password": STUDENT_PASSWORD, "password_confirm": STUDENT_PASSWORD}
STATIC = BASE_DIR / "static"


@pytest.fixture
def plain(client):
    client.headers.pop("Origin", None)
    return client


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_foreign_origin_is_forbidden_for_changing_requests(plain, method):
    response = await getattr(plain, method)("/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "origin" in response.json()["detail"].lower()


async def test_foreign_origin_cannot_log_in_or_register(plain):
    assert (await plain.post("/auth/register", json=CREDENTIALS, headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await plain.post("/auth/login", json=CREDENTIALS, headers={"Origin": "null"})).status_code == 403


async def test_foreign_origin_cannot_use_a_valid_session(client, student_headers):
    response = await client.post(
        "/me/drafts", headers={**student_headers, "Origin": "https://evil.example"}, json={"term": "x", "domain": "IT"}
    )
    assert response.status_code == 403
    response = await client.put(
        "/me/settings", headers={**student_headers, "Origin": "https://evil.example"}, json={"new_cards_per_day": 3}
    )
    assert response.status_code == 403
    assert (await client.get("/me/settings", headers=student_headers)).json()["new_cards_per_day"] == 5


async def test_allowed_origin_passes(plain):
    for index, origin in enumerate(("http://test", "HTTP://TEST", "https://test")):
        response = await plain.post("/auth/register", json={"name": f"origin_{index}", "password": STUDENT_PASSWORD, "password_confirm": STUDENT_PASSWORD}, headers={"Origin": origin})
        assert response.status_code == 201


async def test_referer_is_used_when_origin_is_missing(plain):
    good = await plain.post("/auth/register", json=CREDENTIALS, headers={"Referer": "http://test/teacher.html?x=1"})
    assert good.status_code == 201
    bad = await plain.post("/auth/logout", headers={"Referer": "https://evil.example/page"})
    assert bad.status_code == 403


async def test_origin_wins_over_referer(plain):
    response = await plain.post(
        "/auth/logout", headers={"Origin": "https://evil.example", "Referer": "http://test/"}
    )
    assert response.status_code == 403


async def test_changing_requests_without_origin_and_referer_are_forbidden(plain):
    assert (await plain.post("/auth/logout")).status_code == 403
    assert (await plain.post("/auth/logout", headers={"Referer": "garbage"})).status_code == 403


async def test_reading_requests_are_not_checked(plain):
    assert (await plain.get("/health", headers={"Origin": "https://evil.example"})).status_code == 200


async def test_allowed_origins_come_from_settings(plain, monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", ["https://app.example"])
    assert (await plain.post("/auth/logout", headers={"Origin": "http://test"})).status_code == 403
    assert (await plain.post("/auth/logout", headers={"Origin": "https://app.example"})).status_code == 204


def test_origin_helpers():
    assert origin_of("https://App.Example:8443/path?q=1") == "https://app.example:8443"
    assert origin_of("null") is None and origin_of("") is None and origin_of(None) is None
    assert request_origin_allowed("https://a.example", None, ["https://a.example/"])
    assert not request_origin_allowed("https://a.example:444", None, ["https://a.example"])
    assert not request_origin_allowed(None, None, ["", "null"])


async def test_csp_header_is_on_api_and_static_responses(client):
    for path in ("/health", "/", "/teacher.html", "/js/app.js", "/css/app.css", "/auth/me"):
        policy = (await client.get(path)).headers["content-security-policy"]
        assert "script-src 'self'" in policy and "style-src 'self'" in policy
        assert "default-src 'self'" in policy and "object-src 'none'" in policy
        assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
        assert "frame-ancestors 'none'" in policy


async def test_csp_is_on_error_responses_too(client):
    assert "content-security-policy" in (await client.get("/auth/me")).headers
    assert "content-security-policy" in (await client.post("/auth/logout", headers={"Origin": "https://evil.example"})).headers


def test_csp_allows_audio_only_from_dictionary_domains(monkeypatch):
    monkeypatch.setattr(settings, "dictionary_audio_domains", ["api.dictionaryapi.dev", "ssl.gstatic.com"])
    policy = content_security_policy()
    assert "media-src 'self' https://api.dictionaryapi.dev https://ssl.gstatic.com;" in policy
    assert "https:" not in policy.replace("https://api", "").replace("https://ssl", "")


def test_pages_have_no_inline_scripts_styles_or_handlers():
    for page in ("index.html", "teacher.html"):
        html = (STATIC / page).read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)", html)
        assert "<style" not in html
        assert not re.search(r"\sstyle\s*=", html)
        assert not re.search(r"\son[a-z]+\s*=", html)


def test_scripts_do_not_use_eval_or_inline_style_attributes():
    for path in (STATIC / "js").rglob("*.js"):
        code = path.read_text(encoding="utf-8")
        assert not re.search(r"\beval\s*\(|new\s+Function\s*\(|setTimeout\(\s*[\"'`]|setInterval\(\s*[\"'`]", code), path
        assert not re.search(r"setAttribute\(\s*[\"']style[\"']|\bstyle\s*:\s|cssText|insertAdjacentHTML", code), path


def test_frontend_has_no_leftovers_of_token_handling():
    for path in [*(STATIC / "js").rglob("*.js"), STATIC / "sw.js"]:
        code = path.read_text(encoding="utf-8")
        assert not re.search(r"getToken|clearSession|Authorization|Bearer|vt_token|_token", code), path
