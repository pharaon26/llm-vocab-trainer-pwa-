from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from types import SimpleNamespace

from app.api.session import get_llm_provider, get_today
from app.config import settings
from app.db import Base, get_db
from app.main import app


class Clock:
    today = date(2026, 1, 1)


@pytest.fixture(autouse=True)
def teacher_password(monkeypatch):
    monkeypatch.setattr(settings, "teacher_password", "secret")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def llm():
    return SimpleNamespace(provider=None)


@pytest.fixture
def client(db, clock, llm):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_today] = lambda: clock.today
    app.dependency_overrides[get_llm_provider] = lambda: llm.provider
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, **body):
    response = client.post("/auth/login", json=body)
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def teacher_headers(client):
    return login(client, name="teacher", role="teacher", password="secret")


@pytest.fixture
def student_headers(client):
    return login(client, name="student")
