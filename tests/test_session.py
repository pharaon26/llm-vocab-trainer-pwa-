from datetime import timedelta

import pytest

from sqlalchemy import func, select, update
from app.enums import TaskType
from app.llm.base import LLMError
from app.llm.fake import FakeProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank
from app.seed import load_cards
from app.services.tasks import correct_answer


@pytest.fixture
async def verified_cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()


async def next_task(client, headers):
    return (await client.get("/session/next", headers=headers)).json()


async def answer(client, headers, db, task, correct=True):
    card = await db.get(Card, task["card_id"])
    if task["task_type"] in ("explain_meaning", "compose_sentence"):
        right = "A weakness in a system that an attacker can exploit. We found a " + card.term + " today."
    elif task.get("task_id"):
        right = (await db.get(TaskBank, task["task_id"])).correct_answer
    else:
        right = correct_answer(card, TaskType(task["task_type"]))
    text = right if correct else "definitely wrong"
    response = await client.post(
        "/session/answer",
        headers=headers,
        json={
            "card_id": task["card_id"],
            "task_type": task["task_type"],
            "answer": text,
            "task_id": task.get("task_id"),
            "context": task.get("context"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_session_requires_login(client):
    assert (await client.get("/session/next")).status_code == 401


async def test_unverified_cards_are_not_offered(client, db, student_headers):
    await load_cards(db)
    idle = await next_task(client, student_headers)
    assert (idle["task"], idle["remaining"]) == (None, 0)
    assert (idle["next_review_date"], idle["unseen_cards"]) == (None, 0)


async def test_five_new_cards_per_day(client, db, student_headers, verified_cards):
    assert (await next_task(client, student_headers))["remaining"] == 5
    for _ in range(5):
        await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    idle = await next_task(client, student_headers)
    assert idle["task"] is None and idle["remaining"] == 0
    assert idle["next_review_date"] == "2026-01-02"
    assert idle["unseen_cards"] == 19
    assert idle["new_cards_per_day"] == 5


async def test_correct_answer_shows_reference_card(client, db, student_headers, verified_cards):
    result = await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    assert result["correct"] is True
    assert result["retry_in_session"] is False
    assert result["card"]["definition_en"]
    assert result["remaining"] == 4


async def test_next_day_cards_are_due(client, db, clock, student_headers, verified_cards):
    for _ in range(5):
        await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    clock.today += timedelta(days=1)
    state = await next_task(client, student_headers)
    assert state["remaining"] == 10
    assert state["task"] is not None
    assert state["task"]["task_type"] == TaskType.GAP_FILL.value


async def test_wrong_answer_is_retried_at_end_without_touching_scheduler(
    client, db, student_headers, verified_cards
):
    first = (await next_task(client, student_headers))["task"]
    result = await answer(client, student_headers, db, first, correct=False)
    assert result["correct"] is False
    assert result["error_type"] == "meaning"
    assert result["retry_in_session"] is True

    for _ in range(4):
        await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])

    retry = await next_task(client, student_headers)
    assert retry["remaining"] == 1
    assert retry["task"]["card_id"] == first["card_id"]
    assert retry["task"]["task_type"] == TaskType.DEFINITION_MATCH.value

    progress = (await db.scalars(select(CardProgress).filter_by(card_id=first["card_id"]))).one()
    before = (progress.ease, progress.pending_interval, progress.repetitions)
    assert before == (2.3, 1, 0)

    await answer(client, student_headers, db, retry["task"])
    await db.refresh(progress)
    assert (progress.ease, progress.pending_interval, progress.repetitions) == before
    assert (await next_task(client, student_headers))["task"] is None

    history = (await db.scalars(select(ReviewHistory).filter_by(card_id=first["card_id"]).order_by(ReviewHistory.id))).all()
    assert [(h.is_correct, h.is_retry) for h in history] == [(False, False), (True, True)]


async def test_pending_interval_applied_next_day(client, db, clock, student_headers, verified_cards):
    first = (await next_task(client, student_headers))["task"]
    await answer(client, student_headers, db, first, correct=False)
    await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    clock.today += timedelta(days=1)

    task = [t async for t in iter_tasks(client, student_headers) if t["card_id"] == first["card_id"]][0]
    assert task["task_type"] == TaskType.DEFINITION_MATCH.value
    await answer(client, student_headers, db, task)

    progress = (await db.scalars(select(CardProgress).filter_by(card_id=first["card_id"]))).one()
    assert progress.pending_interval is None
    assert progress.interval == 1
    assert progress.repetitions == 1
    assert progress.due_date == clock.today + timedelta(days=1)


async def iter_tasks(client, headers):
    seen = set()
    while True:
        task = (await next_task(client, headers))["task"]
        if task is None or task["card_id"] in seen:
            return
        seen.add(task["card_id"])
        yield task


async def test_card_outside_session_rejected(client, db, student_headers, verified_cards):
    for _ in range(5):
        await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    response = await client.post(
        "/session/answer",
        headers=student_headers,
        json={"card_id": 24, "task_type": "write_term", "answer": "x"},
    )
    assert response.status_code == 409


async def test_progress_is_per_student(client, db, student_headers, verified_cards):
    from tests.conftest import login

    await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    other = await login(client, name="other")
    assert (await next_task(client, other))["remaining"] == 5


async def test_generated_task_flow(client, db, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = (await next_task(client, student_headers))["task"]
    assert task["task_id"] is not None
    assert task["task_type"] == TaskType.DEFINITION_MATCH.value

    result = await answer(client, student_headers, db, task)
    assert result["correct"] is True
    entry = await db.get(TaskBank, task["task_id"])
    assert entry.times_used == 1
    history = (await db.scalars(select(ReviewHistory).filter_by(card_id=task["card_id"]))).one()
    assert history.task_bank_id == task["task_id"]


async def test_generated_task_wrong_answer(client, db, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = (await next_task(client, student_headers))["task"]
    result = await answer(client, student_headers, db, task, correct=False)
    assert result["correct"] is False
    assert result["error_type"] == "meaning"
    assert result["correct_answer"] == (await db.get(TaskBank, task["task_id"])).correct_answer


async def test_task_id_of_another_card_rejected(client, db, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    first = (await next_task(client, student_headers))["task"]
    other = (await db.scalars(select(TaskBank).where(TaskBank.card_id != first["card_id"]))).first()
    if other is None:
        other = TaskBank(
            card_id=first["card_id"] + 1, task_type="definition_match", source="fake",
            prompt="p", options=["a", "b"], correct_answer="a",
        )
        db.add(other)
        await db.commit()
    response = await client.post(
        "/session/answer",
        headers=student_headers,
        json={"card_id": first["card_id"], "task_type": first["task_type"], "answer": "x", "task_id": other.id},
    )
    assert response.status_code == 422


async def test_session_survives_llm_failure(client, db, llm, student_headers, verified_cards):
    llm.provider = FakeProvider([LLMError("down")] * 10)
    task = (await next_task(client, student_headers))["task"]
    assert task["task_id"] is None
    assert (await answer(client, student_headers, db, task))["correct"] is True


async def test_deleting_card_removes_bank_entries(client, db, llm, student_headers, teacher_headers, verified_cards):
    llm.provider = FakeProvider()
    task = (await next_task(client, student_headers))["task"]
    await answer(client, student_headers, db, task)
    response = await client.delete(f"/cards/{task['card_id']}", headers=teacher_headers)
    assert response.status_code == 204
    assert (await db.scalar(select(func.count()).select_from(select(TaskBank).filter_by(card_id=task["card_id"]).subquery()))) == 0


async def set_progress(db, user_name, card_id, repetitions, today):
    from app.models import User

    user = (await db.scalars(select(User).filter_by(name=user_name))).one()
    progress = CardProgress(
        user_id=user.id, card_id=card_id, interval=10, ease=2.5, repetitions=repetitions,
        first_seen_on=today, due_date=today,
    )
    db.add(progress)
    await db.commit()


async def advanced_task(client, db, clock, headers, repetitions):
    first = (await db.scalars(select(Card).order_by(Card.id))).first()
    await set_progress(db, "student", first.id, repetitions, clock.today)
    task = (await next_task(client, headers))["task"]
    assert task["card_id"] == first.id
    return task


@pytest.mark.parametrize(
    "repetitions, task_type",
    [(4, "write_term"), (5, "explain_meaning"), (6, "compose_sentence"), (7, "write_term")],
)
async def test_advanced_stage_rotates_task_types(client, db, clock, llm, student_headers, verified_cards, repetitions, task_type):
    llm.provider = FakeProvider()
    assert (await advanced_task(client, db, clock, student_headers, repetitions))["task_type"] == task_type


async def test_open_task_falls_back_to_write_term_without_llm(client, db, clock, student_headers, verified_cards):
    assert (await advanced_task(client, db, clock, student_headers, 5))["task_type"] == "write_term"


async def test_compose_task_has_configured_situation(client, db, clock, llm, student_headers, verified_cards):
    from app.config import classification_config

    llm.provider = FakeProvider()
    task = await advanced_task(client, db, clock, student_headers, 6)
    assert task["context"] in classification_config.situations
    assert task["options"] is None


async def test_explain_answer_is_classified_and_recorded(client, db, clock, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = await advanced_task(client, db, clock, student_headers, 5)
    result = await answer(client, student_headers, db, task)
    assert result["correct"] is True
    assert result["classified_by"] == "llm"
    assert result["comment"]
    assert result["correct_answer"] == (await db.get(Card, task["card_id"])).definition_en
    history = (await db.scalars(select(ReviewHistory).filter_by(card_id=task["card_id"]))).one()
    assert (history.classified_by, history.is_correct) == ("llm", True)
    assert history.comment == result["comment"]


async def test_wrong_open_answer_updates_scheduler(client, db, clock, llm, student_headers, verified_cards):
    llm.provider = FakeProvider([
        '{"is_correct": false, "error_type": "meaning", "comment": "Неверно."}'
    ])
    task = await advanced_task(client, db, clock, student_headers, 5)
    result = await answer(client, student_headers, db, task, correct=False)
    assert result["error_type"] == "meaning"
    assert result["retry_in_session"] is True
    progress = (await db.scalars(select(CardProgress).filter_by(card_id=task["card_id"]))).one()
    assert progress.pending_interval == 1 and progress.ease == 2.3


async def test_classifier_down_returns_503_and_records_nothing(client, db, clock, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = await advanced_task(client, db, clock, student_headers, 5)
    llm.provider = FakeProvider([LLMError("down")])
    progress = (await db.scalars(select(CardProgress).filter_by(card_id=task["card_id"]))).one()
    before = (progress.interval, progress.ease, progress.repetitions, progress.due_date)

    response = await client.post(
        "/session/answer",
        headers=student_headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "answer": "My long answer"},
    )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).subquery()))) == 0
    await db.refresh(progress)
    assert before == (progress.interval, progress.ease, progress.repetitions, progress.due_date)

    llm.provider = FakeProvider()
    retry = await answer(client, student_headers, db, task)
    assert retry["classified_by"] == "llm"
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).subquery()))) == 1


async def test_compose_requires_a_configured_situation(client, db, clock, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = await advanced_task(client, db, clock, student_headers, 6)
    for context in (None, "Придуманная ситуация"):
        response = await client.post(
            "/session/answer",
            headers=student_headers,
            json={"card_id": task["card_id"], "task_type": "compose_sentence", "answer": "x", "context": context},
        )
        assert response.status_code == 422


async def test_spelling_error_in_open_answer_never_reaches_llm(client, db, clock, llm, student_headers, verified_cards):
    llm.provider = FakeProvider()
    task = await advanced_task(client, db, clock, student_headers, 6)
    term = (await db.get(Card, task["card_id"])).term
    typo = term[:3] + term[4:]
    response = await client.post(
        "/session/answer",
        headers=student_headers,
        json={
            "card_id": task["card_id"], "task_type": "compose_sentence",
            "answer": f"We found a {typo} today.", "context": task["context"],
        },
    )
    body = response.json()
    assert body["error_type"] == "form" and body["classified_by"] == "rule"
    assert llm.provider.calls == []


async def test_choice_answer_is_recorded_as_task_classified(client, db, student_headers, verified_cards):
    first = (await next_task(client, student_headers))["task"]
    assert (await answer(client, student_headers, db, first))["classified_by"] == "task"


async def test_write_term_answer_is_recorded_as_rule_classified(client, db, clock, student_headers, verified_cards):
    typed = await advanced_task(client, db, clock, student_headers, 4)
    assert typed["task_type"] == "write_term"
    assert (await answer(client, student_headers, db, typed))["classified_by"] == "rule"


async def test_failed_retry_is_not_repeated_again_in_session(client, db, student_headers, verified_cards):
    first = (await next_task(client, student_headers))["task"]
    await answer(client, student_headers, db, first, correct=False)
    for _ in range(4):
        await answer(client, student_headers, db, (await next_task(client, student_headers))["task"])
    retry = await next_task(client, student_headers)
    assert retry["task"]["card_id"] == first["card_id"]

    result = await answer(client, student_headers, db, retry["task"], correct=False)
    assert result["retry_in_session"] is True
    assert (await next_task(client, student_headers))["task"] is None
    progress = (await db.scalars(select(CardProgress).filter_by(card_id=first["card_id"]))).one()
    assert progress.pending_interval == 1
