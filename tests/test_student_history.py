from datetime import date

import pytest

from sqlalchemy import select, update
from app.enums import TaskType
from app.llm.fake import FakeProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.seed import load_cards
from app.services.tasks import correct_answer


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


async def user_of(db, name="student"):
    return (await db.scalars(select(User).filter_by(name=name))).one()


async def add(db, user, card, correct=True, error=None, day=1, **extra):
    row = ReviewHistory(
        user_id=user.id, card_id=card.id, task_type="definition_match", answer="my answer",
        is_correct=correct, error_type=None if correct else error, is_retry=False,
        answered_on=date(2026, 1, day), **extra,
    )
    db.add(row)
    await db.commit()
    return row


async def get(client, headers, query=""):
    return (await client.get(f"/me/history{query}", headers=headers)).json()


async def test_history_requires_login(client):
    assert (await client.get("/me/history")).status_code == 401


async def test_history_is_newest_first_with_all_fields(client, db, student_headers, cards):
    user = await user_of(db)
    await add(db, user, cards["patch"], False, "meaning", day=1, prompt="p1", correct_answer="c1", comment="Неверно.", classified_by="llm")
    await add(db, user, cards["threat"], True, day=2, prompt="p2", correct_answer="c2")
    data = await get(client, student_headers)
    assert data["total"] == 2
    first, second = data["items"]
    assert (first["term"], first["prompt"], first["correct_answer"], first["is_correct"]) == ("threat", "p2", "c2", True)
    assert first["answered_on"] == "2026-01-02" and first["error_type"] is None
    assert (second["term"], second["error_type"], second["comment"], second["classified_by"]) == ("patch", "meaning", "Неверно.", "llm")
    assert second["answer"] == "my answer" and second["is_retry"] is False


async def test_filter_by_term_and_terms_list(client, db, student_headers, cards):
    user = await user_of(db)
    for term in ("patch", "threat", "patch"):
        await add(db, user, cards[term])
    data = await get(client, student_headers, "?term=patch")
    assert data["total"] == 2 and {i["term"] for i in data["items"]} == {"patch"}
    assert data["terms"] == ["patch", "threat"]
    assert (await get(client, student_headers, "?term=unknown"))["items"] == []


async def test_pagination(client, db, student_headers, cards):
    user = await user_of(db)
    for _ in range(5):
        await add(db, user, cards["patch"])
    page1 = await get(client, student_headers, "?limit=2")
    page2 = await get(client, student_headers, "?limit=2&offset=2")
    page3 = await get(client, student_headers, "?limit=2&offset=4")
    assert page1["total"] == 5
    assert [len(p["items"]) for p in (page1, page2, page3)] == [2, 2, 1]
    ids = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 5
    assert (await client.get("/me/history?limit=0", headers=student_headers)).status_code == 422
    assert (await client.get("/me/history?limit=101", headers=student_headers)).status_code == 422


async def test_history_is_private(client, db, student_headers, cards):
    from tests.conftest import login

    await add(db, await user_of(db), cards["patch"])
    other = await login(client, name="other")
    assert await get(client, other) == {"total": 0, "terms": [], "items": []}


async def test_old_rows_without_prompt_are_reconstructed(client, db, student_headers, cards):
    await add(db, await user_of(db), cards["patch"], False, "meaning")
    item = (await get(client, student_headers))["items"][0]
    assert item["prompt"] == "patch"
    assert item["correct_answer"] == cards["patch"].definition_en


async def test_old_bank_rows_use_the_bank_task(client, db, student_headers, cards):
    entry = TaskBank(
        card_id=cards["patch"].id, task_type="definition_match", source="fake",
        prompt="Bank prompt", options=["a", "b"], correct_answer="Bank answer",
    )
    db.add(entry)
    await db.commit()
    await add(db, await user_of(db), cards["patch"], task_bank_id=entry.id)
    item = (await get(client, student_headers))["items"][0]
    assert (item["prompt"], item["correct_answer"]) == ("Bank prompt", "Bank answer")


async def start(client, headers, task_type=None):
    return (await client.get("/session/next", headers=headers)).json()["task"]


async def reply(client, headers, task, text, context=None):
    return await client.post(
        "/session/answer",
        headers=headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "answer": text,
              "task_id": task["task_id"], "context": context or task.get("context")},
    )


@pytest.mark.parametrize("use_llm", [False, True])
async def test_answers_store_the_shown_prompt_and_correct_answer(client, db, llm, student_headers, cards, use_llm):
    if use_llm:
        llm.provider = FakeProvider()
    task = await start(client, student_headers)
    assert (await reply(client, student_headers, task, "wrong")).status_code == 200
    item = (await get(client, student_headers))["items"][0]
    assert item["prompt"] == task["prompt"]
    card = await db.get(Card, task["card_id"])
    expected = (await db.get(TaskBank, task["task_id"])).correct_answer if task["task_id"] else correct_answer(card, TaskType(task["task_type"]))
    assert item["correct_answer"] == expected
    row = (await db.scalars(select(ReviewHistory))).one()
    assert row.prompt == task["prompt"] and row.correct_answer == expected


async def test_compose_sentence_prompt_includes_the_situation(client, db, llm, student_headers, cards):
    from app.config import classification_config

    llm.provider = FakeProvider()
    situation = classification_config.situations[0]
    user = await user_of(db)
    first = (await db.scalars(select(Card).order_by(Card.id))).first()
    db.add(CardProgress(user_id=user.id, card_id=first.id, interval=10, ease=2.5, repetitions=6,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 1)))
    await db.commit()
    task = await start(client, student_headers)
    assert task["task_type"] == "compose_sentence"
    await reply(client, student_headers, task, f"We found a {first.term} today in the code.", context=situation)
    item = (await get(client, student_headers))["items"][0]
    assert item["prompt"] == f"{first.term} - {situation}"
    assert item["correct_answer"] == first.examples[0]
