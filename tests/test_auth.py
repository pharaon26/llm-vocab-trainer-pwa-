from app.config import settings
from tests.conftest import login


def test_student_login_and_me(client):
    response = client.post("/auth/login", json={"name": " Anna "})
    assert response.status_code == 200
    token = response.json()["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["name"] == "Anna"
    assert me.json()["role"] == "student"


def test_same_name_gives_same_user_but_new_token(client):
    first = client.post("/auth/login", json={"name": "Anna"}).json()
    second = client.post("/auth/login", json={"name": "Anna"}).json()
    assert first["token"] != second["token"]


def test_missing_and_fake_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer fake"}).status_code == 401


def test_teacher_requires_password(client):
    body = {"name": "teacher", "role": "teacher"}
    assert client.post("/auth/login", json=body).status_code == 403
    assert client.post("/auth/login", json={**body, "password": "wrong"}).status_code == 403
    assert client.post("/auth/login", json={**body, "password": "secret"}).status_code == 200


def test_teacher_login_disabled_without_configured_password(client, monkeypatch):
    monkeypatch.setattr(settings, "teacher_password", "")
    response = client.post("/auth/login", json={"name": "t", "role": "teacher", "password": ""})
    assert response.status_code == 403


def test_non_ascii_password_does_not_crash(client):
    response = client.post("/auth/login", json={"name": "t", "role": "teacher", "password": "пароль"})
    assert response.status_code == 403


def test_name_collision_between_roles(client):
    login(client, name="Ivan", role="teacher", password="secret")
    assert client.post("/auth/login", json={"name": "Ivan"}).status_code == 403
    login(client, name="Petr")
    response = client.post("/auth/login", json={"name": "Petr", "role": "teacher", "password": "secret"})
    assert response.status_code == 409
