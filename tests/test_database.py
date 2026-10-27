import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models import Card, Domain


def test_migrations_apply_from_scratch_and_roll_back_fully(scratch_database):
    url, config = scratch_database
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = create_engine(url)
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
    engine.dispose()
    assert tables == ["alembic_version"]
    command.upgrade(config, "head")


def card(domain_id, term, owner_id=None):
    return Card(
        term=term, transcription="/x/", part_of_speech="noun", definition_en="d", translation_ru="т",
        collocations=["a b", "c d"], examples=["e one", "e two"], common_mistakes=["m"],
        domain_id=domain_id, owner_id=owner_id,
    )


async def test_shared_card_terms_are_unique_ignoring_case(db):
    domain = Domain(name="Test domain")
    db.add(domain)
    await db.flush()
    db.add(card(domain.id, "Patch"))
    await db.flush()
    db.add(card(domain.id, "patch"))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_nul_character_in_input_is_rejected_with_422(client, admin_headers):
    response = await client.post("/admin/domains", headers=admin_headers, json={"name": "a\u0000b"})
    assert response.status_code == 422


def test_all_endpoints_and_dependencies_are_coroutines():
    import inspect

    from fastapi.routing import APIRoute

    from app.main import app

    def dependencies(dependant):
        for sub in dependant.dependencies:
            yield sub.call
            yield from dependencies(sub)

    for route in app.routes:
        if isinstance(route, APIRoute):
            assert inspect.iscoroutinefunction(route.endpoint), route.path
            for call in dependencies(route.dependant):
                if not hasattr(call, "__name__"):
                    continue
                assert (
                    inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call)
                    or call.__name__ in SYNC_DEPENDENCIES
                ), call.__name__


SYNC_DEPENDENCIES = {"get_today", "get_llm_provider", "get_dictionary_provider"}


def test_auth_migration_replaces_tokens_with_sessions_and_leaves_old_accounts_without_passwords(scratch_database):
    url, config = scratch_database
    command.upgrade(config, "c1d2e3f40a11")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (name, role) VALUES ('anna', 'student'), ('boss', 'teacher')"))
        conn.execute(text("INSERT INTO auth_tokens (token, user_id) SELECT 'plain-text-token', id FROM users WHERE name = 'anna'"))
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM sessions")).scalar() == 0
        assert conn.execute(text("SELECT name, password_hash FROM users ORDER BY name")).all() == [("anna", None), ("boss", None)]
        tables = set(conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
        assert "auth_tokens" not in tables and {"sessions", "login_attempts"} <= tables
    command.downgrade(config, "c1d2e3f40a11")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM auth_tokens")).scalar() == 0
    engine.dispose()


def test_nickname_migration_renames_unsuitable_and_duplicate_names(scratch_database):
    url, config = scratch_database
    command.upgrade(config, "d2e3f4a5b6c7")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, name, role) VALUES (1, 'Anna', 'student'), (2, 'anna', 'student'), "
            "(3, 'Анна', 'student'), (4, 'ok_name1', 'teacher'), (5, 'a b', 'student')"
        ))
    command.upgrade(config, "e3f4a5b6c7d8")
    with engine.connect() as conn:
        names = dict(conn.execute(text("SELECT id, name FROM users")).all())
    assert names == {1: "Anna", 2: "user2", 3: "user3", 4: "ok_name1", 5: "user5"}
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO users (name, role) VALUES ('ANNA', 'student')"))
    command.downgrade(config, "d2e3f4a5b6c7")
    engine.dispose()
