import os
from datetime import date
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from argon2 import PasswordHasher

from app import security
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


@pytest.fixture(autouse=True)
def audio_domains(monkeypatch):
    monkeypatch.setattr(settings, "dictionary_audio_domains", ["audio.test"])


@pytest.fixture(autouse=True)
def secure_cookies(monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)


@pytest.fixture(autouse=True)
def allowed_origins(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", ["http://test", "https://test"])


@pytest.fixture(autouse=True)
def cheap_password_hashing(monkeypatch):
    hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(security, "_hasher", hasher)
    monkeypatch.setattr(security, "_DUMMY_HASH", hasher.hash("dummy"))


class FreshSession(AsyncSession):
    """Сессия теста: всегда перечитывает объекты из базы, чтобы видеть изменения, сделанные запросами к API."""

    async def execute(self, statement, params=None, *, execution_options=None, **kwargs):
        options = {"populate_existing": True, **(execution_options or {})}
        return await super().execute(statement, params, execution_options=options, **kwargs)

    async def get(self, entity, ident, **kwargs):
        return await super().get(entity, ident, populate_existing=True, **kwargs)


@pytest.fixture
async def connection(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def db(connection):
    async with FreshSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
        yield session


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
async def client(connection, clock, llm, dictionary):
    request_session = async_sessionmaker(
        bind=connection, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async def override_db():
        async with request_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_today] = lambda: clock.today
    app.dependency_overrides[get_llm_provider] = lambda: llm.provider
    app.dependency_overrides[get_dictionary_provider] = lambda: dictionary.provider
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://test"}
    ) as http:
        yield http
    app.dependency_overrides.clear()


STUDENT_PASSWORD = "student-pass-1"


def session_cookie_of(response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        name, _, value = pair.partition("=")
        if name == settings.session_cookie_name and value:
            return value
    return None


async def login(client, **body):
    anonymous = {"Cookie": ""}
    if body.get("role") == "teacher":
        response = await client.post("/auth/login", json=body, headers=anonymous)
    else:
        body.setdefault("password", STUDENT_PASSWORD)
        response = await client.post(
            "/auth/register", json={"name": body["name"], "password": body["password"]}, headers=anonymous
        )
        if response.status_code == 409:
            response = await client.post("/auth/login", json=body, headers=anonymous)
    client.cookies.clear()
    return {"Cookie": f"{settings.session_cookie_name}={session_cookie_of(response)}"}


@pytest.fixture
async def teacher_headers(client):
    return await login(client, name="teacher", role="teacher", password="secret")


@pytest.fixture
async def student_headers(client):
    return await login(client, name="student")
