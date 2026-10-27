import json
import re

import pytest
from sqlalchemy import func, select

from app.config import BASE_DIR
from app.models import Card, Deck, DeckCard
from app.schemas.card import CardCreate
from app.seed import CARDS_FILE, DECKS_DIR, load_cards, load_decks

EXPECTED = {
    "web-security.json": "Web Security",
    "cryptography.json": "Cryptography",
    "networking.json": "Networking",
    "access-control-identity.json": "Access Control & Identity",
    "incident-response.json": "Incident Response",
    "devops-cloud.json": "DevOps & Cloud",
    "databases.json": "Databases",
    "software-development.json": "Software Development",
}
DOMAINS = {"IT", "Information security"}


def decks():
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(DECKS_DIR.glob("*.json"))}


def all_cards():
    return [(name, card) for name, data in decks().items() for card in data["cards"]]


def test_there_is_one_file_per_expected_deck():
    assert set(decks()) == set(EXPECTED)
    for name, data in decks().items():
        assert data["deck"]["name"] == EXPECTED[name]
        assert data["deck"]["domain"] in DOMAINS
        assert data["deck"]["description"].strip()


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_each_deck_has_twenty_five_cards(filename):
    assert len(decks()[filename]["cards"]) == 25


def test_two_hundred_cards_in_total():
    assert len(all_cards()) == 200


@pytest.mark.parametrize("filename, card", all_cards(), ids=lambda value: value if isinstance(value, str) else value["term"])
def test_every_card_matches_the_card_schema_and_quality_rules(filename, card):
    data = CardCreate(**card)
    term = data.term.lower()
    assert data.domain in DOMAINS
    assert re.fullmatch(r"/.+/", data.transcription), "transcription must be written between slashes"
    assert term not in data.definition_en.lower(), "the definition must not contain the term"
    assert data.definition_en.rstrip().endswith("."), "the definition is a full sentence"
    assert 2 <= len(data.collocations) <= 4 and 2 <= len(data.examples) <= 3
    assert all(term in collocation.lower() for collocation in data.collocations), "collocations must contain the term"
    stem = re.escape(term)
    assert any(re.search(rf"\b{stem}\w*", example, re.I) for example in data.examples), "an example must use the term"
    assert len(set(data.examples)) == len(data.examples) and len(set(data.collocations)) == len(data.collocations)
    assert len(data.common_mistakes) >= 1 and all(len(item) > 15 for item in data.common_mistakes)
    assert re.search(r"[а-яё]", data.translation_ru, re.I), "the translation is in Russian"
    assert data.contrast_term is None or (data.contrast_term.strip() and data.contrast_term.lower() != term)


def test_no_duplicate_terms_inside_the_decks_or_with_the_starter_cards():
    starter = {item["term"].lower() for item in json.loads(CARDS_FILE.read_text(encoding="utf-8"))}
    terms = [card["term"].lower() for _, card in all_cards()]
    assert len(terms) == len(set(terms)), sorted({t for t in terms if terms.count(t) > 1})
    assert not starter & set(terms), sorted(starter & set(terms))


def test_definitions_and_examples_are_not_repeated_between_cards():
    definitions = [card["definition_en"].lower() for _, card in all_cards()]
    examples = [example.lower() for _, card in all_cards() for example in card["examples"]]
    assert len(definitions) == len(set(definitions))
    assert len(examples) == len(set(examples))


def test_contrast_terms_that_name_a_card_name_an_existing_one():
    starter = {item["term"].lower() for item in json.loads(CARDS_FILE.read_text(encoding="utf-8"))}
    known = starter | {card["term"].lower() for _, card in all_cards()}
    for name, card in all_cards():
        contrast = card["contrast_term"]
        if contrast is not None:
            assert contrast.lower() in known, (card["term"], contrast)


async def test_loader_creates_eight_decks_of_unverified_cards(db):
    report = await load_decks(db)
    assert {name: counts for name, counts in report.items()} == {name: (25, 0) for name in EXPECTED.values()}
    names = set(await db.scalars(select(Deck.name).where(Deck.owner_id.is_(None))))
    assert names == set(EXPECTED.values())
    assert await db.scalar(select(func.count()).select_from(Card).where(Card.owner_id.is_(None))) == 200
    assert await db.scalar(select(func.count()).select_from(Card).where(Card.verified.is_(True))) == 0
    for deck in await db.scalars(select(Deck)):
        assert deck.is_default is False
        assert await db.scalar(select(func.count()).select_from(DeckCard).where(DeckCard.deck_id == deck.id)) == 25


async def test_loader_is_idempotent_and_does_not_touch_the_starter_set(db):
    await load_cards(db)
    first = await load_decks(db)
    second = await load_decks(db)
    assert all(added == 0 and skipped == 25 for added, skipped in second.values())
    assert sum(added for added, _ in first.values()) == 200
    assert await db.scalar(select(func.count()).select_from(Card).where(Card.owner_id.is_(None))) == 224
    starter = await db.scalar(select(Deck).where(Deck.is_default.is_(True)))
    assert await db.scalar(select(func.count()).select_from(DeckCard).where(DeckCard.deck_id == starter.id)) == 24


async def test_students_do_not_see_unverified_deck_cards(client, db, student_headers):
    await load_cards(db)
    await load_decks(db)
    items = (await client.get("/me/progress", headers=student_headers)).json()["items"]
    assert items == []
    decks = (await client.get("/me/decks", headers=student_headers)).json()
    assert {d["name"] for d in decks} >= set(EXPECTED.values())
    assert all(d["cards"] == 0 for d in decks)


def test_deck_files_are_valid_utf8_json_with_stable_formatting():
    for path in DECKS_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n") and json.loads(text)
        assert "\\u" not in text, "Cyrillic and IPA must be stored as readable characters"
        assert str(BASE_DIR) not in text
