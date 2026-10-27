import random
from datetime import date, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from sqlalchemy import func, select, update
from app.config import BASE_DIR, settings
from app.enums import TaskType
from app.llm.prompts import build_prompt
from app.models import Card, CardProgress, Deck, DeckCard, Domain, User, UserDeck
from app.seed import load_cards
from app.services.cards import DEFAULT_DECK_NAME, DEFAULT_DOMAINS, ensure_default_domains
from app.services.tasks import build_task
from tests.conftest import login

CARD = {
    "term": "anticoagulant", "transcription": "/ˌæntikoʊˈæɡjələnt/", "part_of_speech": "noun",
    "definition_en": "A substance that prevents blood from clotting.", "translation_ru": "антикоагулянт",
    "collocations": ["prescribe an anticoagulant", "oral anticoagulant"],
    "examples": ["The patient takes an anticoagulant daily.", "An anticoagulant reduces the risk of stroke."],
    "common_mistakes": ["Confusing anticoagulant with antibiotic."], "contrast_term": "antiplatelet", "domain": "Medicine",
}


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


@pytest.fixture
def admin(client, admin_headers):
    client.headers.update(admin_headers)
    return client


async def make_deck(db, name, card_terms, domain="Medicine", default=False):
    domain_row = (await db.scalars(select(Domain).filter_by(name=domain))).first() or Domain(name=domain)
    db.add(domain_row)
    await db.flush()
    deck = Deck(name=name, description="d", domain_id=domain_row.id, is_default=default)
    db.add(deck)
    await db.flush()
    for term in card_terms:
        db.add(DeckCard(deck_id=deck.id, card_id=(await db.scalars(select(Card).filter_by(term=term))).one().id))
    await db.commit()
    return deck


async def remaining(client, headers):
    return (await client.get("/session/next", headers=headers)).json()["remaining"]


async def test_seed_creates_default_deck_and_domains(db, cards):
    deck = (await db.scalars(select(Deck).filter_by(name=DEFAULT_DECK_NAME))).one()
    assert deck.is_default and deck.domain == "IT"
    assert (await db.scalar(select(func.count()).select_from(select(DeckCard).filter_by(deck_id=deck.id).subquery()))) == 24
    assert {d.name for d in (await db.scalars(select(Domain))).all()} >= set(DEFAULT_DOMAINS)
    await load_cards(db)
    assert (await db.scalar(select(func.count()).select_from(select(DeckCard).subquery()))) == 24 and (await db.scalar(select(func.count()).select_from(select(Deck).subquery()))) == 1


def test_card_domain_is_an_entity_shared_between_cards(db, cards):
    assert cards["patch"].domain == "IT"
    assert cards["threat"].domain == "Information security"
    assert cards["patch"].domain_ref.id == cards["deployment"].domain_ref.id
    assert cards["threat"].domain_ref.id == cards["firewall"].domain_ref.id


async def test_cards_api_resolves_domain_case_insensitively(admin, db):
    await ensure_default_domains(db)
    await db.commit()
    created = (await admin.post("/admin/cards", json={**CARD, "domain": "medicine"})).json()
    assert created["domain"] == "Medicine"
    assert (await db.scalar(select(func.count()).select_from(select(Domain).where(Domain.name.ilike("medicine")).subquery()))) == 1


async def test_domains_list_requires_login_and_is_sorted(client, student_headers, db, cards):
    assert (await client.get("/domains")).status_code == 401
    names = [d["name"] for d in (await client.get("/domains", headers=student_headers)).json()]
    assert names == sorted(names, key=str.lower) and "Medicine" in names


async def test_default_deck_is_selected_until_the_student_chooses(client, student_headers, cards):
    decks = (await client.get("/me/decks", headers=student_headers)).json()
    assert [(d["name"], d["selected"], d["cards"]) for d in decks] == [(DEFAULT_DECK_NAME, True, 24)]
    assert await remaining(client, student_headers) == 5


async def test_new_terms_come_only_from_selected_decks(client, db, student_headers, cards):
    medicine = await make_deck(db, "Medicine basics", ["patch", "threat"])
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    queue = []
    while True:
        task = (await client.get("/session/next", headers=student_headers)).json()
        if task["task"] is None:
            break
        queue.append(task["task"]["card_id"])
        await client.post("/session/answer", headers=student_headers, json={
            "card_id": task["task"]["card_id"], "task_type": task["task"]["task_type"],
            "task_id": task["task"]["task_id"], "answer": "x"})
        if len(queue) > 10:
            break
    assert set(queue) == {cards["patch"].id, cards["threat"].id}


async def test_choosing_decks_persists_and_flags_selection(client, db, student_headers, cards):
    medicine = await make_deck(db, "Medicine basics", ["patch"])
    default = (await db.scalars(select(Deck).filter_by(name=DEFAULT_DECK_NAME))).one()
    result = (await client.put("/me/decks", headers=student_headers, json={"deck_ids": [default.id, medicine.id]})).json()
    assert {d["name"]: d["selected"] for d in result} == {DEFAULT_DECK_NAME: True, "Medicine basics": True}
    assert (await db.scalars(select(User).filter_by(name="student"))).one().decks_customized is True
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    assert (await db.scalar(select(func.count()).select_from(select(UserDeck).subquery()))) == 1


async def test_empty_selection_means_no_new_terms(client, student_headers, cards):
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    assert await remaining(client, student_headers) == 0


async def test_unknown_deck_is_rejected_and_nothing_changes(client, student_headers, cards):
    assert (await client.put("/me/decks", headers=student_headers, json={"deck_ids": [999]})).status_code == 422
    assert (await client.get("/me/decks", headers=student_headers)).json()[0]["selected"] is True


async def test_deselecting_a_deck_keeps_reviews_of_opened_terms(client, db, clock, student_headers, cards):
    clock.today = date(2026, 1, 10)
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    db.add(CardProgress(user_id=user.id, card_id=cards["patch"].id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 9), due_date=date(2026, 1, 10)))
    await db.commit()
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    queue = (await client.get("/session/next", headers=student_headers)).json()
    assert queue["remaining"] == 1 and queue["task"]["card_id"] == cards["patch"].id


async def test_deck_card_counts_use_verified_cards_only(client, db, student_headers, cards):
    cards["patch"].verified = False
    await db.commit()
    assert (await client.get("/me/decks", headers=student_headers)).json()[0]["cards"] == 23


async def test_progress_lists_selected_decks_and_opened_terms_only(client, db, student_headers, cards):
    medicine = await make_deck(db, "Medicine basics", ["patch"])
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    terms = [i["term"] for i in (await client.get("/me/progress", headers=student_headers)).json()["items"]]
    assert terms == ["patch"]
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    db.add(CardProgress(user_id=user.id, card_id=cards["threat"].id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 2)))
    await db.commit()
    terms = [i["term"] for i in (await client.get("/me/progress", headers=student_headers)).json()["items"]]
    assert sorted(terms) == ["patch", "threat"]


async def test_teacher_deck_endpoints_require_teacher(client, student_headers):
    assert (await client.get("/admin/decks")).status_code == 401
    assert (await client.get("/admin/decks", headers=student_headers)).status_code == 403
    assert (await client.post("/admin/domains", headers=student_headers, json={"name": "X"})).status_code == 403


async def test_teacher_deck_crud(admin, db, cards):
    created = (await admin.post("/admin/decks", json={"name": "Law basics", "description": "d", "domain": "Law"})).json()
    assert created["domain"] == "Law" and created["is_default"] is False and created["cards_total"] == 0
    assert (await admin.post("/admin/decks", json={"name": "law BASICS", "domain": "Law"})).status_code == 409

    cards["patch"].verified = False
    await db.commit()
    ids = [cards["patch"].id, cards["threat"].id]
    updated = (await admin.put(f"/admin/decks/{created['id']}/cards", json={"card_ids": ids})).json()
    assert updated["card_ids"] == sorted(ids) and updated["cards"] == 1 and updated["cards_total"] == 2
    assert (await admin.put(f"/admin/decks/{created['id']}/cards", json={"card_ids": ids[:1]})).json()["cards"] == 0
    assert (await admin.put(f"/admin/decks/{created['id']}/cards", json={"card_ids": [9999]})).status_code == 422

    renamed = (await admin.put(f"/admin/decks/{created['id']}", json={"name": "Law 101", "domain": "Law", "is_default": True})).json()
    assert renamed["name"] == "Law 101" and renamed["is_default"] is True
    assert len((await admin.get("/admin/decks")).json()) == 2
    assert (await admin.delete(f"/admin/decks/{created['id']}")).status_code == 204
    assert (await admin.delete(f"/admin/decks/{created['id']}")).status_code == 404
    assert (await db.scalar(select(func.count()).select_from(select(DeckCard).filter_by(deck_id=created["id"]).subquery()))) == 0
    assert (await db.scalar(select(func.count()).select_from(select(Card).subquery()))) == 24


async def test_deleting_a_deck_removes_student_selections(admin, client, db, student_headers, cards):
    deck = await make_deck(db, "Temp", ["patch"])
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": [deck.id]})
    await admin.delete(f"/admin/decks/{deck.id}")
    assert (await db.scalar(select(func.count()).select_from(select(UserDeck).subquery()))) == 0


async def test_teacher_domains(admin):
    assert (await admin.post("/admin/domains", json={"name": "Aviation"})).status_code == 201
    assert (await admin.post("/admin/domains", json={"name": "aviation"})).status_code == 409
    assert (await admin.post("/admin/domains", json={"name": " "})).status_code == 422


async def test_deleting_a_card_removes_it_from_decks(admin, db, cards):
    await admin.delete(f"/admin/cards/{cards['patch'].id}")
    assert (await db.scalar(select(func.count()).select_from(select(DeckCard).filter_by(card_id=cards["patch"].id).subquery()))) == 0


async def test_distractors_prefer_cards_of_the_same_domain(db, cards):
    medicine = (await db.scalars(select(Domain).filter_by(name="Medicine"))).one()
    extra = []
    for index, term in enumerate(["aspirin", "insulin", "vaccine", "antibiotic"]):
        card = Card(
            term=term, transcription="/x/", part_of_speech="noun", definition_en=f"Definition of {term}.",
            translation_ru="т", collocations=["a b", "c d"], examples=[f"We use {term} here.", "Second."],
            common_mistakes=["m"], contrast_term=None, verified=True, domain_id=medicine.id,
        )
        db.add(card)
        extra.append(card)
    await db.commit()
    target = extra[0]
    for task_type in (TaskType.DEFINITION_MATCH, TaskType.GAP_FILL):
        for seed in range(10):
            others = [c for c in (await db.scalars(select(Card))).all() if c.id != target.id]
            task = build_task(target, others, task_type, random.Random(seed))
            joined = " ".join(task.options)
            assert "weakness" not in joined and "process of" not in joined.lower()
            assert all(t in joined for t in [e.term if task_type == TaskType.GAP_FILL else e.definition_en for e in extra[1:]])


async def test_prompts_are_not_tied_to_it(db, cards):
    medicine = (await db.scalars(select(Domain).filter_by(name="Medicine"))).one()
    card = Card(
        term="anticoagulant", transcription="/x/", part_of_speech="noun", definition_en="A substance.",
        translation_ru="т", collocations=["a b", "c d"], examples=["An anticoagulant helps.", "Second."],
        common_mistakes=["m"], contrast_term=None, verified=True, domain_id=medicine.id,
    )
    db.add(card)
    await db.commit()
    for task_type in (TaskType.GAP_FILL, TaskType.DEFINITION_MATCH):
        system, user = build_prompt(card, task_type, "B1")
        assert "Domain: Medicine" in user
        assert "information security" not in (system + user).lower()
        assert "contrast term" not in user.split("<card>")[0]
    _, with_contrast = build_prompt(cards["vulnerability"], TaskType.DEFINITION_MATCH, "B1")
    assert "contrast term" in with_contrast.split("<card>")[0]


def test_migration_moves_domain_strings_into_domains_and_builds_the_default_deck(scratch_database):
    url, config = scratch_database
    command.upgrade(config, "85d3302c02ba")
    engine = create_engine(url)
    with engine.begin() as conn:
        for term, domain in (("alpha", "IT"), ("beta", "Law")):
            conn.execute(text(
                "INSERT INTO cards (term, transcription, part_of_speech, definition_en, translation_ru, collocations,"
                " examples, common_mistakes, contrast_term, domain, verified) VALUES (:t, 'x', 'noun', 'd', 'п', '[]', '[]',"
                " '[]', 'c', :d, true)"), {"t": term, "d": domain})
    command.upgrade(config, "head")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT c.term, d.name FROM cards c JOIN domains d ON d.id = c.domain_id ORDER BY c.term")).all()
        assert rows == [("alpha", "IT"), ("beta", "Law")]
        deck = conn.execute(text("SELECT name, is_default FROM decks")).one()
        assert (deck[0], bool(deck[1])) == (DEFAULT_DECK_NAME, True)
        assert conn.execute(text("SELECT COUNT(*) FROM deck_cards")).scalar() == 2
        assert {r[0] for r in conn.execute(text("SELECT name FROM domains"))} >= set(DEFAULT_DOMAINS)
    command.downgrade(config, "85d3302c02ba")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT domain FROM cards ORDER BY term")).all() == [("IT",), ("Law",)]
    engine.dispose()
