from datetime import date

import pytest

from app.llm.fake import FakeProvider
from app.models import Card, ReviewHistory, TaskBank, User
from app.seed import load_cards
from app.services import bank
from app.services.task_source import get_task
from app.enums import TaskType


@pytest.fixture
def cards(db):
    load_cards(db)
    return {c.term: c for c in db.query(Card).all()}


@pytest.fixture
def teacher(client, teacher_headers):
    client.headers.update(teacher_headers)
    return client


def student(db, name):
    user = User(name=name, role="student")
    db.add(user)
    db.commit()
    return user


def answer_row(db, user, card, correct, error=None, retry=False, by="task"):
    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type="definition_match", answer="x",
            is_correct=correct, error_type=None if correct else error, is_retry=retry,
            answered_on=date(2026, 1, 1), classified_by=by,
        )
    )
    db.commit()


def add_bank(db, card, prompt="A ____ here.", rejected=False, source="fake"):
    entry = TaskBank(
        card_id=card.id, task_type="gap_fill", source=source, prompt=prompt,
        options=[card.term, "a", "b", "c"], correct_answer=card.term, rejected=rejected,
    )
    db.add(entry)
    db.commit()
    return entry


@pytest.mark.parametrize("path", ["/teacher/analytics", "/teacher/bank"])
def test_teacher_endpoints_require_teacher(client, student_headers, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=student_headers).status_code == 403


def test_analytics_counts_first_attempts_of_students_only(db, teacher, cards):
    anna, boris = student(db, "anna"), student(db, "boris")
    vuln, threat = cards["vulnerability"], cards["threat"]
    for _ in range(3):
        answer_row(db, anna, vuln, True)
    answer_row(db, boris, vuln, False, "meaning", by="llm")
    answer_row(db, anna, vuln, False, "form", by="rule")
    answer_row(db, anna, vuln, False, "meaning", retry=True)
    answer_row(db, anna, threat, False, "usage")
    answer_row(db, boris, threat, True)
    teacher_user = db.query(User).filter_by(role="teacher").one()
    answer_row(db, teacher_user, vuln, False, "meaning")

    data = teacher.get("/teacher/analytics?min_answers=2").json()
    assert (data["students"], data["answers"], data["errors"], data["error_rate"]) == (2, 7, 3, 0.429)
    types = {t["error_type"]: (t["count"], t["share"]) for t in data["error_types"]}
    assert types == {"form": (1, 0.333), "meaning": (1, 0.333), "usage": (1, 0.333), "collocation": (0, 0.0)}
    assert [(t["term"], t["attempts"], t["errors"], t["error_rate"]) for t in data["hardest_terms"]] == [
        ("threat", 2, 1, 0.5),
        ("vulnerability", 5, 2, 0.4),
    ]
    assert {s["classified_by"]: s["count"] for s in data["classified_by"]} == {"llm": 1, "rule": 1, "task": 5}


def test_analytics_min_answers_and_limit(db, teacher, cards):
    anna = student(db, "anna")
    answer_row(db, anna, cards["threat"], False, "usage")
    assert teacher.get("/teacher/analytics").json()["hardest_terms"] == []
    assert len(teacher.get("/teacher/analytics?min_answers=1").json()["hardest_terms"]) == 1
    assert teacher.get("/teacher/analytics?min_answers=0").status_code == 422


def test_analytics_is_empty_without_answers(teacher):
    data = teacher.get("/teacher/analytics").json()
    assert (data["students"], data["answers"], data["error_rate"], data["hardest_terms"]) == (0, 0, 0.0, [])
    assert all(t["count"] == 0 for t in data["error_types"])


def test_analytics_has_no_personal_data(db, teacher, cards):
    answer_row(db, student(db, "SecretName"), cards["threat"], False, "usage")
    assert "SecretName" not in teacher.get("/teacher/analytics?min_answers=1").text


def test_bank_list_and_filters(db, teacher, cards):
    add_bank(db, cards["threat"], "One ____.")
    add_bank(db, cards["vulnerability"], "Two ____.", rejected=True)
    add_bank(db, cards["vulnerability"], "Three ____.")
    everything = teacher.get("/teacher/bank").json()
    assert [(e["term"], e["prompt"]) for e in everything] == [
        ("threat", "One ____."), ("vulnerability", "Two ____."), ("vulnerability", "Three ____."),
    ]
    assert len(teacher.get("/teacher/bank?rejected=true").json()) == 1
    assert len(teacher.get("/teacher/bank?rejected=false").json()) == 2
    assert len(teacher.get(f"/teacher/bank?card_id={cards['threat'].id}").json()) == 1
    assert len(teacher.get("/teacher/bank?task_type=gap_fill").json()) == 3
    assert teacher.get("/teacher/bank?task_type=nonsense").status_code == 422


def test_reject_and_restore_bank_entry(db, teacher, cards):
    entry = add_bank(db, cards["threat"])
    assert teacher.patch(f"/teacher/bank/{entry.id}", json={"rejected": True}).json()["rejected"] is True
    assert bank.count(db, cards["threat"].id, TaskType.GAP_FILL, "fake") == 0
    assert teacher.patch(f"/teacher/bank/{entry.id}", json={"rejected": False}).json()["rejected"] is False
    assert bank.count(db, cards["threat"].id, TaskType.GAP_FILL, "fake") == 1
    assert teacher.patch("/teacher/bank/999", json={"rejected": True}).status_code == 404


def test_rejected_entries_are_never_shown(db, cards):
    card = cards["threat"]
    rejected = add_bank(db, card, "Bad ____.", rejected=True)
    good = add_bank(db, card, "Good ____.")
    assert bank.pick(db, card.id, TaskType.GAP_FILL, "fake").id == good.id
    good.rejected = True
    db.commit()
    assert bank.pick(db, card.id, TaskType.GAP_FILL, "fake") is None
    assert rejected.rejected


def test_regenerated_rejected_task_is_not_saved_again(db, cards):
    card = cards["vulnerability"]
    rejected_json = (
        '{"prompt": "We fixed the ____ today.", "options": ["vulnerability", "threat", "attack", "exploit"],'
        ' "correct_answer": "vulnerability"}'
    )
    review = '{"fitting_options": ["vulnerability"], "term_meaning_matches": true}'
    first = get_task(db, FakeProvider([rejected_json, review]), card, TaskType.GAP_FILL, [])
    db.get(TaskBank, first.task_id).rejected = True
    db.commit()

    again = get_task(db, FakeProvider([rejected_json, review]), card, TaskType.GAP_FILL, list(cards.values()))
    assert again.task_id is None
    assert db.query(TaskBank).count() == 1

