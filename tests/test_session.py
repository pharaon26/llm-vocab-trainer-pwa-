from datetime import timedelta

import pytest

from app.enums import TaskType
from app.models import Card, CardProgress, ReviewHistory
from app.seed import load_cards
from app.services.tasks import correct_answer


@pytest.fixture
def verified_cards(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()


def next_task(client, headers):
    return client.get("/session/next", headers=headers).json()


def answer(client, headers, db, task, correct=True):
    card = db.get(Card, task["card_id"])
    text = correct_answer(card, TaskType(task["task_type"])) if correct else "definitely wrong"
    response = client.post(
        "/session/answer",
        headers=headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "answer": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_session_requires_login(client):
    assert client.get("/session/next").status_code == 401


def test_unverified_cards_are_not_offered(client, db, student_headers):
    load_cards(db)
    assert next_task(client, student_headers) == {"task": None, "remaining": 0}


def test_five_new_cards_per_day(client, db, student_headers, verified_cards):
    assert next_task(client, student_headers)["remaining"] == 5
    for _ in range(5):
        answer(client, student_headers, db, next_task(client, student_headers)["task"])
    assert next_task(client, student_headers) == {"task": None, "remaining": 0}


def test_correct_answer_shows_reference_card(client, db, student_headers, verified_cards):
    result = answer(client, student_headers, db, next_task(client, student_headers)["task"])
    assert result["correct"] is True
    assert result["retry_in_session"] is False
    assert result["card"]["definition_en"]
    assert result["remaining"] == 4


def test_next_day_cards_are_due(client, db, clock, student_headers, verified_cards):
    for _ in range(5):
        answer(client, student_headers, db, next_task(client, student_headers)["task"])
    clock.today += timedelta(days=1)
    state = next_task(client, student_headers)
    assert state["remaining"] == 10
    assert state["task"] is not None
    assert state["task"]["task_type"] == TaskType.GAP_FILL.value


def test_wrong_answer_is_retried_at_end_without_touching_scheduler(
    client, db, student_headers, verified_cards
):
    first = next_task(client, student_headers)["task"]
    result = answer(client, student_headers, db, first, correct=False)
    assert result["correct"] is False
    assert result["error_type"] == "meaning"
    assert result["retry_in_session"] is True

    for _ in range(4):
        answer(client, student_headers, db, next_task(client, student_headers)["task"])

    retry = next_task(client, student_headers)
    assert retry["remaining"] == 1
    assert retry["task"]["card_id"] == first["card_id"]
    assert retry["task"]["task_type"] == TaskType.DEFINITION_MATCH.value

    progress = db.query(CardProgress).filter_by(card_id=first["card_id"]).one()
    before = (progress.ease, progress.pending_interval, progress.repetitions)
    assert before == (2.3, 1, 0)

    answer(client, student_headers, db, retry["task"])
    db.refresh(progress)
    assert (progress.ease, progress.pending_interval, progress.repetitions) == before
    assert next_task(client, student_headers)["task"] is None

    history = db.query(ReviewHistory).filter_by(card_id=first["card_id"]).order_by(ReviewHistory.id).all()
    assert [(h.is_correct, h.is_retry) for h in history] == [(False, False), (True, True)]


def test_pending_interval_applied_next_day(client, db, clock, student_headers, verified_cards):
    first = next_task(client, student_headers)["task"]
    answer(client, student_headers, db, first, correct=False)
    answer(client, student_headers, db, next_task(client, student_headers)["task"])
    clock.today += timedelta(days=1)

    task = next(
        t for t in iter_tasks(client, student_headers) if t["card_id"] == first["card_id"]
    )
    assert task["task_type"] == TaskType.DEFINITION_MATCH.value
    answer(client, student_headers, db, task)

    progress = db.query(CardProgress).filter_by(card_id=first["card_id"]).one()
    assert progress.pending_interval is None
    assert progress.interval == 1
    assert progress.repetitions == 1
    assert progress.due_date == clock.today + timedelta(days=1)


def iter_tasks(client, headers):
    seen = set()
    while True:
        task = next_task(client, headers)["task"]
        if task is None or task["card_id"] in seen:
            return
        seen.add(task["card_id"])
        yield task


def test_card_outside_session_rejected(client, db, student_headers, verified_cards):
    for _ in range(5):
        answer(client, student_headers, db, next_task(client, student_headers)["task"])
    response = client.post(
        "/session/answer",
        headers=student_headers,
        json={"card_id": 24, "task_type": "write_term", "answer": "x"},
    )
    assert response.status_code == 409


def test_progress_is_per_student(client, db, student_headers, verified_cards):
    from tests.conftest import login

    answer(client, student_headers, db, next_task(client, student_headers)["task"])
    other = login(client, name="other")
    assert next_task(client, other)["remaining"] == 5
