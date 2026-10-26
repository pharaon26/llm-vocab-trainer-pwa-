from datetime import date

import pytest

from app.models import Card, CardProgress, User
from app.seed import load_cards
from tests.conftest import login


@pytest.fixture
def cards(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()
    return {c.term: c for c in db.query(Card).all()}


def open_card(db, name, card):
    user = db.query(User).filter_by(name=name).one()
    db.add(CardProgress(user_id=user.id, card_id=card.id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 2)))
    db.commit()


def test_dictionary_requires_login(client):
    assert client.get("/me/dictionary").status_code == 401


def test_dictionary_is_empty_until_terms_are_opened(client, student_headers, cards):
    assert client.get("/me/dictionary", headers=student_headers).json() == []


def test_only_opened_verified_cards_in_alphabetical_order(client, db, student_headers, cards):
    for term in ("threat", "authentication", "patch"):
        open_card(db, "student", cards[term])
    cards["patch"].verified = False
    db.commit()

    data = client.get("/me/dictionary", headers=student_headers).json()
    assert [e["term"] for e in data] == ["authentication", "threat"]


def test_entry_has_the_requested_fields_only(client, db, student_headers, cards):
    open_card(db, "student", cards["threat"])
    entry = client.get("/me/dictionary", headers=student_headers).json()[0]
    assert set(entry) == {
        "term", "transcription", "part_of_speech", "definition_en", "translation_ru", "collocations", "examples",
        "personal",
    }
    assert entry["translation_ru"] == "угроза"
    assert len(entry["collocations"]) >= 2 and len(entry["examples"]) >= 2


def test_dictionary_is_per_student(client, db, student_headers, cards):
    open_card(db, "student", cards["threat"])
    other = login(client, name="other")
    assert client.get("/me/dictionary", headers=other).json() == []
