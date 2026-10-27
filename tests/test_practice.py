from datetime import date, timedelta

import pytest

from sqlalchemy import func, select, update
from app.llm.base import LLMError
from app.llm.fake import FakeProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.seed import load_cards
from app.services.tasks import correct_answer
from app.enums import TaskType
from tests.conftest import login

TODAY = date(2026, 1, 10)


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


async def user_of(db, name="student"):
    return (await db.scalars(select(User).filter_by(name=name))).one()


async def open_card(db, card, due=None, name="student", **extra):
    values = dict(interval=10, ease=2.5, repetitions=3, first_seen_on=TODAY - timedelta(days=5),
                  due_date=due or TODAY + timedelta(days=5))
    values.update(extra)
    db.add(CardProgress(user_id=(await user_of(db, name)).id, card_id=card.id, **values))
    await db.commit()


async def snapshot(db):
    return sorted(
        (p.card_id, p.interval, p.ease, p.repetitions, p.pending_interval, p.due_date, p.last_error_type)
        for p in (await db.scalars(select(CardProgress))).all()
    )


async def practice_next(client, headers, query=""):
    return await client.get(f"/practice/next{query}", headers=headers)


async def practice_answer(client, db, headers, task, correct=True, text=None):
    card = await db.get(Card, task["card_id"])
    if task["task_type"] in ("explain_meaning", "compose_sentence"):
        right = f"A weakness in a system that an attacker can exploit. We found a {card.term} today."
    elif task["task_id"]:
        right = (await db.get(TaskBank, task["task_id"])).correct_answer
    else:
        right = correct_answer(card, TaskType(task["task_type"]))
    return await client.post(
        "/practice/answer",
        headers=headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "task_id": task["task_id"],
              "context": task["context"], "answer": text if text is not None else (right if correct else "wrong")},
    )


@pytest.fixture(autouse=True)
def fixed_today(clock):
    clock.today = TODAY


async def test_practice_requires_login(client):
    assert (await client.get("/practice/next")).status_code == 401
    assert (await client.post("/practice/answer", json={})).status_code == 401


async def test_practice_is_locked_until_the_session_is_finished(client, db, student_headers, cards):
    await open_card(db, cards["patch"], due=TODAY)
    response = await practice_next(client, student_headers)
    assert response.status_code == 409


async def test_practice_with_new_cards_waiting_is_also_locked(client, db, student_headers, cards):
    await open_card(db, cards["patch"])
    assert (await practice_next(client, student_headers)).status_code == 409


async def finish_new_cards(db, cards, count=5):
    for term in list(cards)[:count]:
        await open_card(db, cards[term], first_seen_on=TODAY)


async def test_no_opened_cards_means_no_task(client, db, student_headers):
    (await db.execute(update(Card).values({Card.verified: False})))
    await db.commit()
    assert (await practice_next(client, student_headers)).json() == {"task": None}


async def test_practice_offers_only_opened_cards(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    opened = {cards[t].id for t in list(cards)[:5]}
    for _ in range(25):
        task = (await practice_next(client, student_headers)).json()["task"]
        assert task["card_id"] in opened


async def test_exclude_avoids_the_previous_card(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    first = (await practice_next(client, student_headers)).json()["task"]["card_id"]
    for _ in range(25):
        assert (await practice_next(client, student_headers, f"?exclude={first}")).json()["task"]["card_id"] != first


async def test_exclude_is_ignored_when_it_is_the_only_card(client, db, student_headers, cards):
    (await db.execute(update(Card).where(Card.term != "patch").values({Card.verified: False})))
    await db.commit()
    await open_card(db, cards["patch"])
    only = cards["patch"].id
    assert (await practice_next(client, student_headers, f"?exclude={only}")).json()["task"]["card_id"] == only


async def test_practice_answers_never_touch_the_schedule(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    before = await snapshot(db)
    for index in range(12):
        task = (await practice_next(client, student_headers)).json()["task"]
        result = (await practice_answer(client, db, student_headers, task, correct=index % 2 == 0)).json()
        assert result["retry_in_session"] is False and result["remaining"] == 0
    assert await snapshot(db) == before
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).subquery()))) == 12


async def test_practice_answers_are_marked_in_history(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    task = (await practice_next(client, student_headers)).json()["task"]
    await practice_answer(client, db, student_headers, task, correct=False)
    row = (await db.scalars(select(ReviewHistory))).one()
    assert (row.is_practice, row.is_retry, row.is_correct) == (True, False, False)
    assert row.prompt and row.correct_answer
    item = (await client.get("/me/history", headers=student_headers)).json()["items"][0]
    assert item["is_practice"] is True


async def test_wrong_practice_answer_does_not_create_a_session_retry(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    task = (await practice_next(client, student_headers)).json()["task"]
    await practice_answer(client, db, student_headers, task, correct=False)
    (await db.execute(update(Card).values({Card.verified: False})))
    await db.commit()
    (await db.execute(update(Card).where(Card.id == task["card_id"]).values({Card.verified: True})))
    await db.commit()
    queue = (await client.get("/session/next", headers=student_headers)).json()
    assert queue["task"] is None and queue["remaining"] == 0


async def test_practice_answer_does_not_turn_the_real_answer_into_a_retry(client, db, student_headers, cards):
    await open_card(db, cards["patch"], due=TODAY, repetitions=1, interval=3)
    db.add(
        ReviewHistory(
            user_id=(await user_of(db)).id, card_id=cards["patch"].id, task_type="write_term", answer="x",
            is_correct=False, error_type="form", is_retry=False, is_practice=True, answered_on=TODAY,
        )
    )
    await db.commit()
    task = (await client.get("/session/next", headers=student_headers)).json()["task"]
    assert task["card_id"] == cards["patch"].id
    result = await client.post(
        "/session/answer",
        headers=student_headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "task_id": task["task_id"],
              "answer": "wrong"},
    )
    assert result.status_code == 200
    progress = (await db.scalars(select(CardProgress).filter_by(card_id=cards["patch"].id))).one()
    assert progress.pending_interval is not None
    graded = (await db.scalars(select(ReviewHistory).filter_by(is_practice=False))).one()
    assert graded.is_retry is False


async def test_practice_answer_for_an_unopened_card_is_rejected(client, db, student_headers, cards):
    await open_card(db, cards["patch"])
    response = await client.post(
        "/practice/answer",
        headers=student_headers,
        json={"card_id": cards["threat"].id, "task_type": "write_term", "answer": "threat"},
    )
    assert response.status_code == 409


async def test_practice_includes_generated_and_open_tasks_with_a_provider(client, db, llm, student_headers, cards):
    llm.provider = FakeProvider()
    await finish_new_cards(db, cards)
    kinds = set()
    for _ in range(60):
        task = (await practice_next(client, student_headers)).json()["task"]
        kinds.add(task["task_type"])
    assert {"explain_meaning", "compose_sentence", "write_term"} <= kinds


async def test_open_task_in_practice_is_classified_and_never_scheduled(client, db, llm, student_headers, cards):
    llm.provider = FakeProvider()
    await finish_new_cards(db, cards)
    before = await snapshot(db)
    for _ in range(200):
        task = (await practice_next(client, student_headers)).json()["task"]
        if task["task_type"] == "explain_meaning":
            break
    result = (await practice_answer(client, db, student_headers, task)).json()
    assert result["classified_by"] == "llm"
    assert await snapshot(db) == before


async def test_classifier_failure_in_practice_returns_503_and_records_nothing(client, db, llm, student_headers, cards):
    await finish_new_cards(db, cards)
    llm.provider = FakeProvider()
    for _ in range(200):
        task = (await practice_next(client, student_headers)).json()["task"]
        if task["task_type"] == "explain_meaning":
            break
    llm.provider = FakeProvider([LLMError("down")])
    response = await practice_answer(client, db, student_headers, task, text="My long answer about the term")
    assert response.status_code == 503
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).subquery()))) == 0


async def test_practice_is_excluded_from_progress_and_stats(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    task = (await practice_next(client, student_headers)).json()["task"]
    await practice_answer(client, db, student_headers, task, correct=False)

    progress = (await client.get("/me/progress", headers=student_headers)).json()
    assert all(sum(item["errors"].values()) == 0 for item in progress["items"])

    stats = (await client.get("/me/stats", headers=student_headers)).json()
    assert stats["totals"] == {"answered": 0, "correct": 0, "accuracy": None}
    assert all(e["count"] == 0 for e in stats["error_types"])
    assert stats["days"][-1]["practice"] == 1
    assert stats["streak"] == {"current": 1, "best": 1}


async def test_teacher_analytics_excludes_practice_and_counts_it_separately(client, db, student_headers, teacher_headers, cards):
    await finish_new_cards(db, cards)
    for _ in range(3):
        task = (await practice_next(client, student_headers)).json()["task"]
        await practice_answer(client, db, student_headers, task, correct=False)
    data = (await client.get("/teacher/analytics", headers=teacher_headers)).json()
    assert (data["answers"], data["errors"], data["practice_answers"]) == (0, 0, 3)
    assert data["hardest_terms"] == [] and all(t["count"] == 0 for t in data["error_types"])


async def test_idle_info_reports_opened_cards(client, db, student_headers, cards):
    await finish_new_cards(db, cards)
    idle = (await client.get("/session/next", headers=student_headers)).json()
    assert idle["opened_cards"] == 5
