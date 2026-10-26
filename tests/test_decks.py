import random
from datetime import date, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

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
def cards(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()
    return {c.term: c for c in db.query(Card).all()}


@pytest.fixture
def teacher(client, teacher_headers):
    client.headers.update(teacher_headers)
    return client


def make_deck(db, name, card_terms, domain="Medicine", default=False):
    domain_row = db.query(Domain).filter_by(name=domain).first() or Domain(name=domain)
    db.add(domain_row)
    db.flush()
    deck = Deck(name=name, description="d", domain_id=domain_row.id, is_default=default)
    db.add(deck)
    db.flush()
    for term in card_terms:
        db.add(DeckCard(deck_id=deck.id, card_id=db.query(Card).filter_by(term=term).one().id))
    db.commit()
    return deck


def remaining(client, headers):
    return client.get("/session/next", headers=headers).json()["remaining"]


def test_seed_creates_default_deck_and_domains(db, cards):
    deck = db.query(Deck).filter_by(name=DEFAULT_DECK_NAME).one()
    assert deck.is_default and deck.domain == "IT"
    assert db.query(DeckCard).filter_by(deck_id=deck.id).count() == 24
    assert {d.name for d in db.query(Domain)} >= set(DEFAULT_DOMAINS)
    load_cards(db)
    assert db.query(DeckCard).count() == 24 and db.query(Deck).count() == 1


def test_card_domain_is_an_entity_shared_between_cards(db, cards):
    assert cards["patch"].domain == "IT"
    assert cards["threat"].domain == "Information security"
    assert cards["patch"].domain_ref.id == cards["deployment"].domain_ref.id
    assert cards["threat"].domain_ref.id == cards["firewall"].domain_ref.id


def test_cards_api_resolves_domain_case_insensitively(teacher, db):
    ensure_default_domains(db)
    db.commit()
    created = teacher.post("/cards", json={**CARD, "domain": "medicine"}).json()
    assert created["domain"] == "Medicine"
    assert db.query(Domain).filter(Domain.name.ilike("medicine")).count() == 1


def test_domains_list_requires_login_and_is_sorted(client, student_headers, db, cards):
    assert client.get("/domains").status_code == 401
    names = [d["name"] for d in client.get("/domains", headers=student_headers).json()]
    assert names == sorted(names) and "Medicine" in names


def test_default_deck_is_selected_until_the_student_chooses(client, student_headers, cards):
    decks = client.get("/me/decks", headers=student_headers).json()
    assert [(d["name"], d["selected"], d["cards"]) for d in decks] == [(DEFAULT_DECK_NAME, True, 24)]
    assert remaining(client, student_headers) == 5


def test_new_terms_come_only_from_selected_decks(client, db, student_headers, cards):
    medicine = make_deck(db, "Medicine basics", ["patch", "threat"])
    client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    queue = []
    while True:
        task = client.get("/session/next", headers=student_headers).json()
        if task["task"] is None:
            break
        queue.append(task["task"]["card_id"])
        client.post("/session/answer", headers=student_headers, json={
            "card_id": task["task"]["card_id"], "task_type": task["task"]["task_type"],
            "task_id": task["task"]["task_id"], "answer": "x"})
        if len(queue) > 10:
            break
    assert set(queue) == {cards["patch"].id, cards["threat"].id}


def test_choosing_decks_persists_and_flags_selection(client, db, student_headers, cards):
    medicine = make_deck(db, "Medicine basics", ["patch"])
    default = db.query(Deck).filter_by(name=DEFAULT_DECK_NAME).one()
    result = client.put("/me/decks", headers=student_headers, json={"deck_ids": [default.id, medicine.id]}).json()
    assert {d["name"]: d["selected"] for d in result} == {DEFAULT_DECK_NAME: True, "Medicine basics": True}
    assert db.query(User).filter_by(name="student").one().decks_customized is True
    client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    assert db.query(UserDeck).count() == 1


def test_empty_selection_means_no_new_terms(client, student_headers, cards):
    client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    assert remaining(client, student_headers) == 0


def test_unknown_deck_is_rejected_and_nothing_changes(client, student_headers, cards):
    assert client.put("/me/decks", headers=student_headers, json={"deck_ids": [999]}).status_code == 422
    assert client.get("/me/decks", headers=student_headers).json()[0]["selected"] is True


def test_deselecting_a_deck_keeps_reviews_of_opened_terms(client, db, clock, student_headers, cards):
    clock.today = date(2026, 1, 10)
    user = db.query(User).filter_by(name="student").one()
    db.add(CardProgress(user_id=user.id, card_id=cards["patch"].id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 9), due_date=date(2026, 1, 10)))
    db.commit()
    client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    queue = client.get("/session/next", headers=student_headers).json()
    assert queue["remaining"] == 1 and queue["task"]["card_id"] == cards["patch"].id


def test_deck_card_counts_use_verified_cards_only(client, db, student_headers, cards):
    cards["patch"].verified = False
    db.commit()
    assert client.get("/me/decks", headers=student_headers).json()[0]["cards"] == 23


def test_progress_lists_selected_decks_and_opened_terms_only(client, db, student_headers, cards):
    medicine = make_deck(db, "Medicine basics", ["patch"])
    client.put("/me/decks", headers=student_headers, json={"deck_ids": [medicine.id]})
    terms = [i["term"] for i in client.get("/me/progress", headers=student_headers).json()["items"]]
    assert terms == ["patch"]
    user = db.query(User).filter_by(name="student").one()
    db.add(CardProgress(user_id=user.id, card_id=cards["threat"].id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=date(2026, 1, 1), due_date=date(2026, 1, 2)))
    db.commit()
    terms = [i["term"] for i in client.get("/me/progress", headers=student_headers).json()["items"]]
    assert sorted(terms) == ["patch", "threat"]


def test_teacher_deck_endpoints_require_teacher(client, student_headers):
    assert client.get("/teacher/decks").status_code == 401
    assert client.get("/teacher/decks", headers=student_headers).status_code == 403
    assert client.post("/teacher/domains", headers=student_headers, json={"name": "X"}).status_code == 403


def test_teacher_deck_crud(teacher, db, cards):
    created = teacher.post("/teacher/decks", json={"name": "Law basics", "description": "d", "domain": "Law"}).json()
    assert created["domain"] == "Law" and created["is_default"] is False and created["cards_total"] == 0
    assert teacher.post("/teacher/decks", json={"name": "law BASICS", "domain": "Law"}).status_code == 409

    cards["patch"].verified = False
    db.commit()
    ids = [cards["patch"].id, cards["threat"].id]
    updated = teacher.put(f"/teacher/decks/{created['id']}/cards", json={"card_ids": ids}).json()
    assert updated["card_ids"] == sorted(ids) and updated["cards"] == 1 and updated["cards_total"] == 2
    assert teacher.put(f"/teacher/decks/{created['id']}/cards", json={"card_ids": ids[:1]}).json()["cards"] == 0
    assert teacher.put(f"/teacher/decks/{created['id']}/cards", json={"card_ids": [9999]}).status_code == 422

    renamed = teacher.put(f"/teacher/decks/{created['id']}", json={"name": "Law 101", "domain": "Law", "is_default": True}).json()
    assert renamed["name"] == "Law 101" and renamed["is_default"] is True
    assert len(teacher.get("/teacher/decks").json()) == 2
    assert teacher.delete(f"/teacher/decks/{created['id']}").status_code == 204
    assert teacher.delete(f"/teacher/decks/{created['id']}").status_code == 404
    assert db.query(DeckCard).filter_by(deck_id=created["id"]).count() == 0
    assert db.query(Card).count() == 24


def test_deleting_a_deck_removes_student_selections(teacher, client, db, student_headers, cards):
    deck = make_deck(db, "Temp", ["patch"])
    client.put("/me/decks", headers=student_headers, json={"deck_ids": [deck.id]})
    teacher.delete(f"/teacher/decks/{deck.id}")
    assert db.query(UserDeck).count() == 0


def test_teacher_domains(teacher):
    assert teacher.post("/teacher/domains", json={"name": "Aviation"}).status_code == 201
    assert teacher.post("/teacher/domains", json={"name": "aviation"}).status_code == 409
    assert teacher.post("/teacher/domains", json={"name": " "}).status_code == 422


def test_deleting_a_card_removes_it_from_decks(teacher, db, cards):
    teacher.delete(f"/cards/{cards['patch'].id}")
    assert db.query(DeckCard).filter_by(card_id=cards["patch"].id).count() == 0


def test_distractors_prefer_cards_of_the_same_domain(db, cards):
    medicine = db.query(Domain).filter_by(name="Medicine").one()
    extra = []
    for index, term in enumerate(["aspirin", "insulin", "vaccine", "antibiotic"]):
        card = Card(
            term=term, transcription="/x/", part_of_speech="noun", definition_en=f"Definition of {term}.",
            translation_ru="т", collocations=["a b", "c d"], examples=[f"We use {term} here.", "Second."],
            common_mistakes=["m"], contrast_term=None, verified=True, domain_id=medicine.id,
        )
        db.add(card)
        extra.append(card)
    db.commit()
    target = extra[0]
    for task_type in (TaskType.DEFINITION_MATCH, TaskType.GAP_FILL):
        for seed in range(10):
            others = [c for c in db.query(Card).all() if c.id != target.id]
            task = build_task(target, others, task_type, random.Random(seed))
            joined = " ".join(task.options)
            assert "weakness" not in joined and "process of" not in joined.lower()
            assert all(t in joined for t in [e.term if task_type == TaskType.GAP_FILL else e.definition_en for e in extra[1:]])


def test_prompts_are_not_tied_to_it(db, cards):
    medicine = db.query(Domain).filter_by(name="Medicine").one()
    card = Card(
        term="anticoagulant", transcription="/x/", part_of_speech="noun", definition_en="A substance.",
        translation_ru="т", collocations=["a b", "c d"], examples=["An anticoagulant helps.", "Second."],
        common_mistakes=["m"], contrast_term=None, verified=True, domain_id=medicine.id,
    )
    db.add(card)
    db.commit()
    for task_type in (TaskType.GAP_FILL, TaskType.DEFINITION_MATCH):
        system, user = build_prompt(card, task_type, "B1")
        assert "Domain: Medicine" in user
        assert "information security" not in (system + user).lower()
        assert "contrast term" not in user.split("<card>")[0]
    _, with_contrast = build_prompt(cards["vulnerability"], TaskType.DEFINITION_MATCH, "B1")
    assert "contrast term" in with_contrast.split("<card>")[0]


def test_migration_moves_domain_strings_into_domains_and_builds_the_default_deck(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(config, "85d3302c02ba")
    engine = create_engine(url)
    with engine.begin() as conn:
        for term, domain in (("alpha", "IT"), ("beta", "Law")):
            conn.execute(text(
                "INSERT INTO cards (term, transcription, part_of_speech, definition_en, translation_ru, collocations,"
                " examples, common_mistakes, contrast_term, domain, verified) VALUES (:t, 'x', 'noun', 'd', 'п', '[]', '[]',"
                " '[]', 'c', :d, 1)"), {"t": term, "d": domain})
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
