from app.config import settings
from tests.conftest import login


async def test_student_login_and_me(client):
    response = await client.post("/auth/login", json={"name": " Anna "})
    assert response.status_code == 200
    token = response.json()["token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["name"] == "Anna"
    assert me.json()["role"] == "student"


async def test_same_name_gives_same_user_but_new_token(client):
    first = (await client.post("/auth/login", json={"name": "Anna"})).json()
    second = (await client.post("/auth/login", json={"name": "Anna"})).json()
    assert first["token"] != second["token"]


async def test_missing_and_fake_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/auth/me", headers={"Authorization": "Bearer fake"})).status_code == 401


async def test_teacher_requires_password(client):
    body = {"name": "teacher", "role": "teacher"}
    assert (await client.post("/auth/login", json=body)).status_code == 403
    assert (await client.post("/auth/login", json={**body, "password": "wrong"})).status_code == 403
    assert (await client.post("/auth/login", json={**body, "password": "secret"})).status_code == 200


async def test_teacher_login_disabled_without_configured_password(client, monkeypatch):
    monkeypatch.setattr(settings, "teacher_password", "")
    response = await client.post("/auth/login", json={"name": "t", "role": "teacher", "password": ""})
    assert response.status_code == 403


async def test_non_ascii_password_does_not_crash(client):
    response = await client.post("/auth/login", json={"name": "t", "role": "teacher", "password": "пароль"})
    assert response.status_code == 403


async def test_name_collision_between_roles(client):
    await login(client, name="Ivan", role="teacher", password="secret")
    assert (await client.post("/auth/login", json={"name": "Ivan"})).status_code == 403
    await login(client, name="Petr")
    response = await client.post("/auth/login", json={"name": "Petr", "role": "teacher", "password": "secret"})
    assert response.status_code == 409
