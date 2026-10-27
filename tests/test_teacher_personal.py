from datetime import date

import pytest

from sqlalchemy import func, select, update
from app.models import Card, CardProgress, Deck, DeckCard, ReviewHistory, TaskBank, User
from app.seed import load_cards
from tests.conftest import login

TODAY = date(2026, 1, 10)


@pytest.fixture(autouse=True)
def fixed_today(clock):
    clock.today = TODAY


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()


@pytest.fixture
def teacher(client, teacher_headers):
    client.headers.update(teacher_headers)
    return client


async def personal(db, owner_name, term="jitter", confirmed=True, sources=None, **extra):
    owner = (await db.scalars(select(User).filter_by(name=owner_name))).first()
    if owner is None:
        owner = User(name=owner_name, role="student")
        db.add(owner)
        await db.flush()
    values = dict(
        transcription="/x/", part_of_speech="noun", definition_en="Variation in delay.", translation_ru="джиттер",
        collocations=["network jitter", "low jitter"], examples=["Jitter hurts calls.", "Measure the jitter."],
        common_mistakes=["Confusing jitter with latency."], contrast_term="latency", domain_id=1,
    )
    values.update(extra)
    card = Card(term=term, owner_id=owner.id, confirmed_by_owner=confirmed, verified=False,
                field_sources=sources or {"translation_ru": "llm", "definition_en": "dictionary"}, **values)
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


def payload(card, **changes):
    data = {
        "term": card.term, "transcription": card.transcription, "part_of_speech": card.part_of_speech,
        "definition_en": card.definition_en, "translation_ru": card.translation_ru,
        "collocations": card.collocations, "examples": card.examples, "common_mistakes": card.common_mistakes,
        "contrast_term": card.contrast_term, "domain": card.domain,
    }
    data.update(changes)
    return data


async def deck_id(db):
    return (await db.scalars(select(Deck))).first().id


@pytest.mark.parametrize("method, path", [("get", "/teacher/personal-cards"), ("put", "/teacher/personal-cards/1"), ("post", "/teacher/personal-cards/1/promote")])
async def test_endpoints_require_teacher(client, student_headers, method, path):
    assert (await getattr(client, method)(path)).status_code == 401
    assert (await getattr(client, method)(path, headers=student_headers)).status_code == 403


async def test_teacher_sees_students_personal_cards_with_owner_and_sources(teacher, db, cards):
    await personal(db, "anna")
    await personal(db, "boris", term="packet loss")
    data = (await teacher.get("/teacher/personal-cards")).json()
    assert [(c["term"], c["owner"]) for c in data] == [("jitter", "anna"), ("packet loss", "boris")]
    assert data[0]["sources"] == {"translation_ru": "llm", "definition_en": "dictionary"}
    assert data[0]["shared_duplicate"] is False and data[0]["domain"] == "IT"
    assert [c["term"] for c in (await teacher.get("/teacher/personal-cards?owner=boris")).json()] == ["packet loss"]


async def test_unconfirmed_cards_are_not_shown_to_the_teacher(teacher, db, cards):
    await personal(db, "anna", confirmed=False)
    assert (await teacher.get("/teacher/personal-cards")).json() == []


async def test_shared_duplicate_is_flagged(teacher, db, cards):
    await personal(db, "anna", term="Patch")
    assert (await teacher.get("/teacher/personal-cards")).json()[0]["shared_duplicate"] is True


async def test_teacher_edit_keeps_ownership_and_confirmation_and_marks_changes(teacher, db, cards):
    card = await personal(db, "anna")
    result = (await teacher.put(f"/teacher/personal-cards/{card.id}", json=payload(card, translation_ru="дрожание", definition_en="Variation in packet delay."))).json()
    assert result["translation_ru"] == "дрожание" and result["owner"] == "anna"
    assert result["sources"]["translation_ru"] == "user" and result["sources"]["definition_en"] == "user"
    await db.refresh(card)
    assert card.owner_id is not None and card.confirmed_by_owner is True and card.verified is False


async def test_teacher_edit_validates_and_rejects_clashes(teacher, db, cards):
    first, second = await personal(db, "anna"), await personal(db, "anna", term="packet loss")
    assert (await teacher.put(f"/teacher/personal-cards/{first.id}", json=payload(first, collocations=["only one"]))).status_code == 422
    assert (await teacher.put(f"/teacher/personal-cards/{first.id}", json=payload(first, term="Packet Loss"))).status_code == 409
    assert second.term == "packet loss"


async def test_teacher_cannot_touch_shared_cards_through_personal_endpoints(teacher, db, cards):
    shared = (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).first()
    assert (await teacher.put(f"/teacher/personal-cards/{shared.id}", json=payload(shared))).status_code == 404
    assert (await teacher.post(f"/teacher/personal-cards/{shared.id}/promote", json={"deck_ids": [await deck_id(db)]})).status_code == 404


async def test_promote_makes_the_card_shared_verified_and_adds_it_to_decks(teacher, db, cards):
    card = await personal(db, "anna")
    result = await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": [await deck_id(db)]})
    assert result.status_code == 200
    await db.refresh(card)
    assert (card.owner_id, card.verified, card.confirmed_by_owner) == (None, True, False)
    assert await db.get(DeckCard, (await deck_id(db), card.id)) is not None
    assert (await teacher.get("/teacher/personal-cards")).json() == []
    assert "jitter" in {c["term"] for c in (await teacher.get("/cards")).json()}


async def test_promoted_card_is_offered_to_other_students_through_the_selected_deck(teacher, client, db, cards):
    card = await personal(db, "anna")
    other = await login(client, name="other")
    assert "jitter" not in (await client.get("/me/progress", headers=other)).text
    await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": [await deck_id(db)]})
    assert any(i["term"] == "jitter" for i in (await client.get("/me/progress", headers=other)).json()["items"])
    assert (await client.get("/session/next", headers=other)).json()["remaining"] == 5


async def test_owner_keeps_progress_and_history_after_promotion(teacher, client, db, cards):
    card = await personal(db, "anna")
    owner = (await db.scalars(select(User).filter_by(name="anna"))).one()
    db.add(CardProgress(user_id=owner.id, card_id=card.id, interval=3, ease=2.4, repetitions=2,
                        first_seen_on=TODAY, due_date=TODAY))
    db.add(ReviewHistory(user_id=owner.id, card_id=card.id, task_type="write_term", answer="x", is_correct=True,
                         is_retry=False, answered_on=TODAY))
    await db.commit()
    await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": [await deck_id(db)]})
    progress = (await db.scalars(select(CardProgress).filter_by(card_id=card.id))).one()
    assert (progress.interval, progress.ease, progress.repetitions) == (3, 2.4, 2)
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).filter_by(card_id=card.id).subquery()))) == 1


async def test_promotion_is_blocked_by_an_existing_shared_term(teacher, db, cards):
    card = await personal(db, "anna", term="PATCH")
    assert (await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": [await deck_id(db)]})).status_code == 409
    await db.refresh(card)
    assert card.owner_id is not None and card.verified is False


async def test_promotion_needs_existing_decks(teacher, db, cards):
    card = await personal(db, "anna")
    assert (await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": []})).status_code == 422
    assert (await teacher.post(f"/teacher/personal-cards/{card.id}/promote", json={"deck_ids": [999]})).status_code == 422
    await db.refresh(card)
    assert card.owner_id is not None


async def test_other_students_personal_card_with_same_term_survives_a_promotion(teacher, db, cards):
    first, second = await personal(db, "anna"), await personal(db, "boris")
    await teacher.post(f"/teacher/personal-cards/{first.id}/promote", json={"deck_ids": [await deck_id(db)]})
    await db.refresh(second)
    assert second.owner_id is not None
    assert (await teacher.get("/teacher/personal-cards")).json()[0]["shared_duplicate"] is True


async def test_group_analytics_ignore_personal_cards(teacher, client, db, cards):
    card = await personal(db, "anna")
    owner = (await db.scalars(select(User).filter_by(name="anna"))).one()
    for _ in range(5):
        db.add(ReviewHistory(user_id=owner.id, card_id=card.id, task_type="write_term", answer="x", is_correct=False,
                             error_type="form", is_retry=False, answered_on=TODAY))
    db.add(ReviewHistory(user_id=owner.id, card_id=card.id, task_type="write_term", answer="x", is_correct=True,
                         is_retry=False, is_practice=True, answered_on=TODAY))
    await db.commit()
    data = (await teacher.get("/teacher/analytics?min_answers=1")).json()
    assert (data["students"], data["answers"], data["errors"], data["practice_answers"]) == (0, 0, 0, 0)
    assert data["hardest_terms"] == []
    assert "jitter" not in (await teacher.get("/teacher/analytics?min_answers=1")).text


async def test_shared_answers_still_count_alongside_personal_ones(teacher, db, cards):
    shared = (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).first()
    personal_card = await personal(db, "anna")
    owner = (await db.scalars(select(User).filter_by(name="anna"))).one()
    for card, correct in ((shared, False), (personal_card, False), (personal_card, False)):
        db.add(ReviewHistory(user_id=owner.id, card_id=card.id, task_type="write_term", answer="x", is_correct=correct,
                             error_type=None if correct else "form", is_retry=False, answered_on=TODAY))
    await db.commit()
    data = (await teacher.get("/teacher/analytics")).json()
    assert (data["answers"], data["errors"]) == (1, 1)


async def test_teacher_bank_hides_entries_of_personal_cards(teacher, db, cards):
    shared = (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).first()
    mine = await personal(db, "anna")
    for card in (shared, mine):
        db.add(TaskBank(card_id=card.id, task_type="gap_fill", source="fake", prompt=f"{card.term} ____",
                        options=["a", "b"], correct_answer="a"))
    await db.commit()
    terms = {entry["term"] for entry in (await teacher.get("/teacher/bank")).json()}
    assert terms == {shared.term}


async def test_shared_deck_cannot_contain_personal_cards(teacher, db, cards):
    mine = await personal(db, "anna")
    deck = (await db.scalars(select(Deck))).first()
    assert (await teacher.put(f"/teacher/decks/{deck.id}/cards", json={"card_ids": [mine.id]})).status_code == 422
