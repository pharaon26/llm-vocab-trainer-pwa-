import os
from datetime import date
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_today
from app.api.personal import get_dictionary_provider
from app.api.session import get_llm_provider
from app.config import BASE_DIR, settings
from app.db import get_db
from app.dictionary.fake import FakeDictionary
from app.main import app


class Clock:
    today = date(2026, 1, 1)


def _test_url(suffix: str = "") -> URL:
    explicit = os.environ.get("TEST_DATABASE_URL")
    url = make_url(explicit or settings.database_url)
    if not explicit:
        url = url.set(database=f"{url.database}_test")
    assert url.database.endswith("_test"), "the test database name must end with _test"
    return url.set(database=url.database + suffix)


def _recreate_database(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def alembic_config(url: URL) -> Config:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def database_url():
    url = _test_url()
    _recreate_database(url)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def scratch_database():
    url = _test_url("_scratch")
    _recreate_database(url)
    yield url, alembic_config(url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
def teacher_password(monkeypatch):
    monkeypatch.setattr(settings, "teacher_password", "secret")


@pytest.fixture(scope="session")
def engine(database_url):
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def llm():
    return SimpleNamespace(provider=None)


@pytest.fixture
def dictionary():
    return SimpleNamespace(provider=FakeDictionary())


@pytest.fixture
def client(db, clock, llm, dictionary):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_today] = lambda: clock.today
    app.dependency_overrides[get_llm_provider] = lambda: llm.provider
    app.dependency_overrides[get_dictionary_provider] = lambda: dictionary.provider
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
