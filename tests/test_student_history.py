from datetime import date

import pytest

from app.enums import TaskType
from app.llm.fake import FakeProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.seed import load_cards
from app.services.tasks import correct_answer


@pytest.fixture
def cards(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()
    return {c.term: c for c in db.query(Card).all()}


def user_of(db, name="student"):
    return db.query(User).filter_by(name=name).one()


def add(db, user, card, correct=True, error=None, day=1, **extra):
    row = ReviewHistory(
        user_id=user.id, card_id=card.id, task_type="definition_match", answer="my answer",
        is_correct=correct, error_type=None if correct else error, is_retry=False,
        answered_on=date(2026, 1, day), **extra,
    )
    db.add(row)
    db.commit()
    return row


def get(client, headers, query=""):
    return client.get(f"/me/history{query}", headers=headers).json()


def test_history_requires_login(client):
    assert client.get("/me/history").status_code == 401


def test_history_is_newest_first_with_all_fields(client, db, student_headers, cards):
    user = user_of(db)
    add(db, user, cards["patch"], False, "meaning", day=1, prompt="p1", correct_answer="c1", comment="Неверно.", classified_by="llm")
    add(db, user, cards["threat"], True, day=2, prompt="p2", correct_answer="c2")
    data = get(client, student_headers)
    assert data["total"] == 2
    first, second = data["items"]
    assert (first["term"], first["prompt"], first["correct_answer"], first["is_correct"]) == ("threat", "p2", "c2", True)
    assert first["answered_on"] == "2026-01-02" and first["error_type"] is None
    assert (second["term"], second["error_type"], second["comment"], second["classified_by"]) == ("patch", "meaning", "Неверно.", "llm")
    assert second["answer"] == "my answer" and second["is_retry"] is False


def test_filter_by_term_and_terms_list(client, db, student_headers, cards):
    user = user_of(db)
    for term in ("patch", "threat", "patch"):
        add(db, user, cards[term])
    data = get(client, student_headers, "?term=patch")
    assert data["total"] == 2 and {i["term"] for i in data["items"]} == {"patch"}
    assert data["terms"] == ["patch", "threat"]
    assert get(client, student_headers, "?term=unknown")["items"] == []


def test_pagination(client, db, student_headers, cards):
    user = user_of(db)
    for _ in range(5):
        add(db, user, cards["patch"])
    page1 = get(client, student_headers, "?limit=2")
    page2 = get(client, student_headers, "?limit=2&offset=2")
    page3 = get(client, student_headers, "?limit=2&offset=4")
    assert page1["total"] == 5
    assert [len(p["items"]) for p in (page1, page2, page3)] == [2, 2, 1]
    ids = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 5
    assert client.get("/me/history?limit=0", headers=student_headers).status_code == 422
    assert client.get("/me/history?limit=101", headers=student_headers).status_code == 422


def test_history_is_private(client, db, student_headers, cards):
    from tests.conftest import login

    add(db, user_of(db), cards["patch"])
    other = login(client, name="other")
    assert get(client, other) == {"total": 0, "terms": [], "items": []}


def test_old_rows_without_prompt_are_reconstructed(client, db, student_headers, cards):
    add(db, user_of(db), cards["patch"], False, "meaning")
    item = get(client, student_headers)["items"][0]
    assert item["prompt"] == "patch"
    assert item["correct_answer"] == cards["patch"].definition_en


def test_old_bank_rows_use_the_bank_task(client, db, student_headers, cards):
    entry = TaskBank(
        card_id=cards["patch"].id, task_type="definition_match", source="fake",
        prompt="Bank prompt", options=["a", "b"], correct_answer="Bank answer",
    )
    db.add(entry)
    db.commit()
    add(db, user_of(db), cards["patch"], task_bank_id=entry.id)
    item = get(client, student_headers)["items"][0]
    assert (item["prompt"], item["correct_answer"]) == ("Bank prompt", "Bank answer")


def start(client, headers, task_type=None):
    return client.get("/session/next", headers=headers).json()["task"]


def reply(client, headers, task, text, context=None):
    return client.post(
        "/session/answer",
        headers=headers,
        json={"card_id": task["card_id"], "task_type": task["task_type"], "answer": text,
              "task_id": task["task_id"], "context": context or task.get("context")},
    )


@pytest.mark.parametrize("use_llm", [False, True])
def test_answers_store_the_shown_prompt_and_correct_answer(client, db, llm, student_headers, cards, use_llm):
    if use_llm:
        llm.provider = FakeProvider()
    task = start(client, student_headers)
    assert reply(client, student_headers, task, "wrong").status_code == 200
    item = get(client, student_headers)["items"][0]
    assert item["prompt"] == task["prompt"]
    card = db.get(Card, task["card_id"])
    expected = db.get(TaskBank, task["task_id"]).correct_answer if task["task_id"] else correct_answer(card, TaskType(task["task_type"]))
    assert item["correct_answer"] == expected
    row = db.query(ReviewHistory).one()
    assert row.prompt == task["prompt"] and row.correct_answer == expected


def test_compose_sentence_prompt_includes_the_situation(client, db, llm, student_headers, cards):
    from app.config import classification_config

    llm.provider = FakeProvider()
    situation = classification_config.situations[0]
    user = user_of(db)
    first = db.query(Card).order_by(Card.id).first()
    db.add(CardProgress(user_id=user.id, card_id=first.id, interval=10, ease=2.5, repetitions=6,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 1)))
    db.commit()
    task = start(client, student_headers)
    assert task["task_type"] == "compose_sentence"
    reply(client, student_headers, task, f"We found a {first.term} today in the code.", context=situation)
    item = get(client, student_headers)["items"][0]
    assert item["prompt"] == f"{first.term} - {situation}"
    assert item["correct_answer"] == first.examples[0]
