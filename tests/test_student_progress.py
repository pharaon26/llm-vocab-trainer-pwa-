from datetime import date

import pytest

from app.config import LearningConfig
from app.models import Card, CardProgress, ReviewHistory, User
from app.seed import load_cards
from app.services.student import card_status


@pytest.fixture
def cards(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()
    return {c.term: c for c in db.query(Card).all()}


def current_user(db, headers_name="student"):
    return db.query(User).filter_by(name=headers_name).one()


def progress_row(db, user, card, **kwargs):
    values = dict(interval=3, ease=2.5, repetitions=2, first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 4))
    values.update(kwargs)
    db.add(CardProgress(user_id=user.id, card_id=card.id, **values))
    db.commit()


def history_row(db, user, card, correct, error=None, retry=False):
    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type="definition_match", answer="x",
            is_correct=correct, error_type=None if correct else error, is_retry=retry,
            answered_on=date(2026, 1, 1),
        )
    )
    db.commit()


def test_progress_requires_login(client):
    assert client.get("/me/progress").status_code == 401


@pytest.mark.parametrize(
    "interval, pending, expected",
    [(0, None, "learning"), (20.9, None, "learning"), (21, None, "learned"), (50, None, "learned"), (50, 1.0, "learning")],
)
def test_status_criterion(interval, pending, expected):
    progress = CardProgress(interval=interval, pending_interval=pending)
    assert card_status(progress, LearningConfig(learned_interval_days=21)) == expected


def test_status_new_without_progress():
    assert card_status(None) == "new"


def test_all_verified_terms_are_listed_with_statuses(client, db, student_headers, cards):
    user = current_user(db)
    progress_row(db, user, cards["threat"], interval=30, repetitions=5, due_date=date(2026, 2, 1))
    progress_row(db, user, cards["patch"], interval=3, repetitions=2, due_date=date(2026, 1, 4))
    cards["backup"].verified = False
    db.commit()

    data = client.get("/me/progress", headers=student_headers).json()
    by_term = {i["term"]: i for i in data["items"]}
    assert len(data["items"]) == 23
    assert "backup" not in by_term
    assert by_term["threat"]["status"] == "learned" and by_term["threat"]["due_date"] == "2026-02-01"
    assert by_term["patch"]["status"] == "learning" and by_term["patch"]["repetitions"] == 2
    assert by_term["firewall"] == {
        "term": "firewall", "status": "new", "due_date": None, "repetitions": 0,
        "errors": {"form": 0, "meaning": 0, "usage": 0, "collocation": 0},
    }
    assert data["summary"] == {"total": 23, "new": 21, "learning": 1, "learned": 1}


def test_opened_terms_come_first_ordered_by_due_date(client, db, student_headers, cards):
    user = current_user(db)
    progress_row(db, user, cards["threat"], due_date=date(2026, 3, 1))
    progress_row(db, user, cards["patch"], due_date=date(2026, 1, 5))
    terms = [i["term"] for i in client.get("/me/progress", headers=student_headers).json()["items"]]
    assert terms[:2] == ["patch", "threat"]
    assert terms[2:] == sorted(terms[2:])


def test_error_history_counts_by_type_for_graded_answers_only(client, db, student_headers, cards):
    user = current_user(db)
    patch = cards["patch"]
    progress_row(db, user, patch)
    history_row(db, user, patch, False, "meaning")
    history_row(db, user, patch, False, "meaning")
    history_row(db, user, patch, False, "form")
    history_row(db, user, patch, True)
    history_row(db, user, patch, False, "usage", retry=True)

    item = next(i for i in client.get("/me/progress", headers=student_headers).json()["items"] if i["term"] == "patch")
    assert item["errors"] == {"form": 1, "meaning": 2, "usage": 0, "collocation": 0}


def test_progress_is_per_student(client, db, student_headers, cards):
    from tests.conftest import login

    progress_row(db, current_user(db), cards["patch"])
    other = login(client, name="other")
    data = client.get("/me/progress", headers=other).json()
    assert data["summary"]["learning"] == 0 and data["summary"]["new"] == 24
