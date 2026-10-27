"""Во время вызова LLM или словаря соединение с базой должно быть возвращено в пул.

Тесты используют настоящий пул соединений и фиксируют данные в тестовой базе (а не откатываемую транзакцию), потому что
только так видно, сколько соединений занято. Все созданные данные удаляются после теста.
"""
from datetime import date

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_today
from app.db import get_db
from app.dictionary.base import DictionaryEntry
from app.dictionary.fake import FakeDictionary
from app.llm.fake import FakeProvider
from app.models import Card, CardDraft, CardProgress, ReviewHistory, TaskBank, TeacherGroup, TeacherStudent, User
from tests.conftest import login

TODAY = date(2026, 1, 1)
TERMS = ["firewall", "payload", "keylogger", "sandbox", "honeypot", "checksum"]


def card_body(term, definition=None):
    return {
        "term": term, "transcription": "/x/", "part_of_speech": "noun",
        "definition_en": definition or f"A thing that is called {term} in security work and is easy to describe.",
        "translation_ru": "т", "collocations": [f"strong {term}", f"{term} rule"],
        "examples": [f"The team reviewed the {term} yesterday.", f"A broken {term} is a risk."],
        "common_mistakes": ["m"], "contrast_term": None, "domain": "IT",
    }


class Spy:
    def __init__(self, engine):
        self.engine = engine
        self.checked_out = []
        self.on_first_call = None

    async def record(self):
        self.checked_out.append(self.engine.pool.checkedout())
        callback, self.on_first_call = self.on_first_call, None
        if callback is not None:
            await callback()


class SpyProvider(FakeProvider):
    def __init__(self, spy):
        super().__init__()
        self.spy = spy

    async def complete(self, system, user):
        await self.spy.record()
        return await super().complete(system, user)


class SpyDictionary(FakeDictionary):
    def __init__(self, spy, entries=None):
        super().__init__(entries)
        self.spy = spy

    async def lookup(self, word):
        await self.spy.record()
        return await super().lookup(word)


@pytest.fixture
async def world(client, database_url, clock, llm, dictionary):
    clock.today = TODAY
    engine = create_async_engine(database_url, pool_size=3, max_overflow=0)
    maker = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    async def real_db():
        async with maker() as session:
            yield session

    from app.main import app

    app.dependency_overrides[get_db] = real_db
    app.dependency_overrides[get_today] = lambda: TODAY
    spy = Spy(engine)
    llm.provider = SpyProvider(spy)
    dictionary.provider = SpyDictionary(spy)

    teacher = await login(client, name="rt_teacher", role="teacher")
    student = await login(client, name="rt_student")
    group = (await client.post("/teacher/groups", headers=teacher, json={"name": "G"})).json()["id"]
    card_ids = []
    for term in TERMS:
        response = await client.post("/teacher/cards", headers=teacher, json=card_body(term))
        assert response.status_code == 201, response.text
        card_ids.append(response.json()["id"])
    deck = (await client.post("/teacher/decks", headers=teacher, json={"name": "D", "domain": "IT"})).json()["id"]
    await client.put(f"/teacher/decks/{deck}/cards", headers=teacher, json={"card_ids": card_ids})
    await client.put(f"/teacher/decks/{deck}/groups", headers=teacher, json={"group_ids": [group]})
    async with maker() as session:
        teacher_id = await session.scalar(select(User.id).where(User.name == "rt_teacher"))
        student_id = await session.scalar(select(User.id).where(User.name == "rt_student"))
        session.add(TeacherStudent(teacher_id=teacher_id, student_id=student_id, group_id=group))
        await session.commit()

    class World:
        pass

    w = World()
    w.client, w.maker, w.spy, w.student, w.teacher = client, maker, spy, student, teacher
    w.student_id, w.card_ids, w.llm, w.dictionary = student_id, card_ids, llm, dictionary
    yield w

    async with maker() as session:
        await session.execute(delete(User).where(User.name.like("rt\\_%")))
        for table in ("login_attempts", "registration_attempts", "link_attempts"):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()
    await engine.dispose()


async def make_due(world, card_id, repetitions):
    async with world.maker() as session:
        session.add(CardProgress(
            user_id=world.student_id, card_id=card_id, interval=3, ease=2.5, repetitions=repetitions,
            due_date=TODAY, first_seen_on=TODAY,
        ))
        await session.commit()


async def count(world, model, *conditions):
    async with world.maker() as session:
        return await session.scalar(select(func.count()).select_from(model).where(*conditions))


async def delete_card(world, card_id):
    async with world.maker() as session:
        await session.execute(delete(Card).where(Card.id == card_id))
        await session.commit()


def explain_body(card_id, answer="A thing that is called something in security work and is easy to describe."):
    return {"card_id": card_id, "task_type": "explain_meaning", "answer": answer}


async def test_classifying_an_open_answer_does_not_hold_a_connection(world):
    await make_due(world, world.card_ids[0], repetitions=5)
    response = await world.client.post("/session/answer", headers=world.student, json=explain_body(world.card_ids[0]))
    assert response.status_code == 200, response.text
    assert world.spy.checked_out and set(world.spy.checked_out) == {0}


async def test_generating_a_task_does_not_hold_a_connection(world):
    response = await world.client.get("/session/next", headers=world.student)
    assert response.status_code == 200 and response.json()["task"] is not None
    assert len(world.spy.checked_out) >= 2
    assert set(world.spy.checked_out) == {0}


async def test_free_practice_generation_does_not_hold_a_connection(world):
    async with world.maker() as session:
        for card_id in world.card_ids:
            session.add(CardProgress(
                user_id=world.student_id, card_id=card_id, interval=3, ease=2.5, repetitions=1,
                due_date=date(2026, 2, 1), first_seen_on=TODAY,
            ))
        await session.commit()
    for _ in range(6):
        response = await world.client.get("/practice/next", headers=world.student)
        assert response.status_code == 200, response.text
    assert set(world.spy.checked_out) <= {0}


async def test_draft_creation_does_not_hold_a_connection(world):
    world.dictionary.provider.entries = {"latency": DictionaryEntry(definition="The delay before data begins.", part_of_speech="noun")}
    response = await world.client.post("/me/drafts", headers=world.student, json={"term": "latency", "domain": "IT"})
    assert response.status_code == 200, response.text
    assert len(world.spy.checked_out) >= 2
    assert set(world.spy.checked_out) == {0}


async def test_term_search_in_text_does_not_hold_a_connection(world):
    text_ = "The vulnerability scanner found a misconfiguration in the authentication service."
    response = await world.client.post("/me/extract", headers=world.student, json={"text": text_, "domain": "IT"})
    assert response.status_code == 200, response.text
    assert world.spy.checked_out and set(world.spy.checked_out) == {0}


async def test_answer_is_rejected_if_the_card_is_deleted_during_classification(world):
    card_id = world.card_ids[0]
    await make_due(world, card_id, repetitions=5)

    async def remove():
        await delete_card(world, card_id)

    world.spy.on_first_call = remove
    response = await world.client.post("/session/answer", headers=world.student, json=explain_body(card_id))
    assert response.status_code == 409
    assert await count(world, ReviewHistory, ReviewHistory.user_id == world.student_id) == 0


async def test_answer_recorded_by_a_parallel_request_is_not_recorded_twice(world):
    card_id = world.card_ids[0]
    await make_due(world, card_id, repetitions=5)
    nested = {}

    async def other_request():
        nested["response"] = await world.client.post("/session/answer", headers=world.student, json=explain_body(card_id))

    world.spy.on_first_call = other_request
    response = await world.client.post("/session/answer", headers=world.student, json=explain_body(card_id))
    assert nested["response"].status_code == 200
    assert response.status_code == 409
    assert await count(world, ReviewHistory, ReviewHistory.user_id == world.student_id) == 1
    async with world.maker() as session:
        progress = await session.scalar(select(CardProgress).where(CardProgress.user_id == world.student_id))
    assert progress.repetitions == 6


async def test_wrong_answer_while_a_parallel_wrong_answer_was_recorded_counts_as_a_retry(world):
    card_id = world.card_ids[0]
    await make_due(world, card_id, repetitions=5)
    nested = {}
    wrong = explain_body(card_id, answer="zzz")

    async def other_request():
        nested["response"] = await world.client.post("/session/answer", headers=world.student, json=wrong)

    world.spy.on_first_call = other_request
    response = await world.client.post("/session/answer", headers=world.student, json=wrong)
    assert response.status_code == 200 and nested["response"].status_code == 200
    async with world.maker() as session:
        rows = (await session.scalars(select(ReviewHistory).order_by(ReviewHistory.id))).all()
        progress = await session.scalar(select(CardProgress).where(CardProgress.user_id == world.student_id))
    assert [row.is_retry for row in rows] == [False, True]
    assert progress.repetitions == 5


async def test_card_deleted_while_a_task_is_generated_gives_another_task(world):
    first = world.card_ids[0]

    async def remove():
        await delete_card(world, first)

    world.spy.on_first_call = remove
    response = await world.client.get("/session/next", headers=world.student)
    assert response.status_code == 200
    task = response.json()["task"]
    assert task is not None and task["card_id"] != first
    assert await count(world, TaskBank, TaskBank.card_id == first) == 0


async def test_card_edited_while_a_task_is_generated_is_not_saved_to_the_bank(world):
    first = world.card_ids[0]

    async def edit():
        async with world.maker() as session:
            await session.execute(update(Card).where(Card.id == first).values(definition_en="Brand new definition."))
            await session.commit()

    world.spy.on_first_call = edit
    response = await world.client.get("/session/next", headers=world.student)
    assert response.status_code == 200
    assert await count(world, TaskBank, TaskBank.card_id == first) == 0
    task = response.json()["task"]
    assert task["card_id"] == first
    assert "Brand new definition." in task["options"]


async def test_duplicate_created_while_the_dictionary_is_queried_is_detected(world):
    async def add_card():
        async with world.maker() as session:
            card = Card(
                term="latency", transcription="/x/", part_of_speech="noun", definition_en="d", translation_ru="т",
                collocations=["a b", "c d"], examples=["latency one", "latency two"], common_mistakes=["m"],
                domain_id=await session.scalar(text("SELECT id FROM domains LIMIT 1")),
                owner_id=world.student_id, confirmed_by_owner=True,
            )
            session.add(card)
            await session.commit()

    world.spy.on_first_call = add_card
    response = await world.client.post("/me/drafts", headers=world.student, json={"term": "latency", "domain": "IT"})
    assert response.status_code == 200
    assert response.json()["draft"] is None and response.json()["duplicate"]["term"] == "latency"
    assert await count(world, CardDraft, CardDraft.owner_id == world.student_id) == 0


async def test_parallel_requests_for_the_same_word_give_one_draft(world):
    nested = {}

    async def other_request():
        nested["response"] = await world.client.post("/me/drafts", headers=world.student, json={"term": "latency", "domain": "IT"})

    world.spy.on_first_call = other_request
    response = await world.client.post("/me/drafts", headers=world.student, json={"term": "latency", "domain": "IT"})
    assert response.status_code == 200 and nested["response"].status_code == 200
    assert response.json()["draft"]["id"] == nested["response"].json()["draft"]["id"]
    assert await count(world, CardDraft, CardDraft.owner_id == world.student_id) == 1
