from datetime import date

import pytest

from sqlalchemy import select, update
from app.models import Card, CardProgress, User
from app.seed import load_cards
from tests.conftest import login


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


async def open_card(db, name, card):
    user = (await db.scalars(select(User).filter_by(name=name))).one()
    db.add(CardProgress(user_id=user.id, card_id=card.id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 2)))
    await db.commit()


async def test_dictionary_requires_login(client):
    assert (await client.get("/me/dictionary")).status_code == 401


async def test_dictionary_is_empty_until_terms_are_opened(client, student_headers, cards):
    assert (await client.get("/me/dictionary", headers=student_headers)).json() == []


async def test_only_opened_verified_cards_in_alphabetical_order(client, db, student_headers, cards):
    for term in ("threat", "authentication", "patch"):
        await open_card(db, "student", cards[term])
    cards["patch"].verified = False
    await db.commit()

    data = (await client.get("/me/dictionary", headers=student_headers)).json()
    assert [e["term"] for e in data] == ["authentication", "threat"]


async def test_entry_has_the_requested_fields_only(client, db, student_headers, cards):
    await open_card(db, "student", cards["threat"])
    entry = (await client.get("/me/dictionary", headers=student_headers)).json()[0]
    assert set(entry) == {
        "term", "transcription", "part_of_speech", "definition_en", "translation_ru", "collocations", "examples",
        "personal",
    }
    assert entry["translation_ru"] == "угроза"
    assert len(entry["collocations"]) >= 2 and len(entry["examples"]) >= 2


async def test_dictionary_is_per_student(client, db, student_headers, cards):
    await open_card(db, "student", cards["threat"])
    other = await login(client, name="other")
    assert (await client.get("/me/dictionary", headers=other)).json() == []
