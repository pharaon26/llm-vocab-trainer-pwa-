import json

import pytest
from httpx import AsyncClient

from sqlalchemy import func, select, update
from app.models import Card
from app.seed import CARDS_FILE, load_cards, update_cards

@pytest.fixture
def client(client, admin_headers):
    client.headers.update(admin_headers)
    return client


VALID = {
    "term": "vulnerability",
    "transcription": "/ˌvʌlnərəˈbɪləti/",
    "part_of_speech": "noun",
    "definition_en": "A weakness that can be exploited.",
    "translation_ru": "уязвимость",
    "collocations": ["critical vulnerability", "patch a vulnerability"],
    "examples": ["The scan found a vulnerability.", "A vulnerability was fixed."],
    "common_mistakes": ["Confusing with threat."],
    "contrast_term": "threat",
    "domain": "Information security",
}


async def test_create_and_read(client):
    created = await client.post("/admin/cards", json=VALID)
    assert created.status_code == 201
    body = created.json()
    assert body["verified"] is False
    assert (await client.get(f"/admin/cards/{body['id']}")).json()["term"] == "vulnerability"


async def test_duplicate_term_conflict(client):
    await client.post("/admin/cards", json=VALID)
    assert (await client.post("/admin/cards", json=VALID)).status_code == 409


async def test_student_cannot_modify_cards(client, student_headers):
    client.headers.update(student_headers)
    assert (await client.post("/admin/cards", json=VALID)).status_code == 403


async def test_reading_cards_requires_teacher(client, student_headers):
    card_id = (await client.post("/admin/cards", json=VALID)).json()["id"]
    plain = AsyncClient(transport=client._transport, base_url="http://test")
    assert (await plain.get("/admin/cards")).status_code == 401
    assert (await plain.get(f"/admin/cards/{card_id}")).status_code == 401
    assert (await plain.get("/admin/cards", headers=student_headers)).status_code == 403


async def test_not_found(client):
    assert (await client.get("/admin/cards/999")).status_code == 404


@pytest.mark.parametrize(
    "field, value",
    [
        ("collocations", ["only one"]),
        ("collocations", ["a", "b", "c", "d", "e"]),
        ("examples", ["only one"]),
        ("examples", ["a", "b", "c", "d"]),
        ("term", "   "),
        ("common_mistakes", []),
    ],
)
async def test_validation(client, field, value):
    response = await client.post("/admin/cards", json={**VALID, field: value})
    assert response.status_code == 422


async def test_update_resets_verified(client):
    card_id = (await client.post("/admin/cards", json=VALID)).json()["id"]
    assert (await client.patch(f"/admin/cards/{card_id}/verify")).json()["verified"] is True
    updated = await client.put(f"/admin/cards/{card_id}", json={**VALID, "translation_ru": "брешь"})
    assert updated.json()["translation_ru"] == "брешь"
    assert updated.json()["verified"] is False


async def test_update_to_taken_term_conflict(client):
    await client.post("/admin/cards", json=VALID)
    other = (await client.post("/admin/cards", json={**VALID, "term": "threat"})).json()["id"]
    assert (await client.put(f"/admin/cards/{other}", json=VALID)).status_code == 409


async def test_filter_by_verified(client):
    first = (await client.post("/admin/cards", json=VALID)).json()["id"]
    await client.post("/admin/cards", json={**VALID, "term": "threat"})
    await client.patch(f"/admin/cards/{first}/verify")
    assert len((await client.get("/admin/cards")).json()) == 2
    assert [c["term"] for c in (await client.get("/admin/cards?verified=true")).json()] == ["vulnerability"]


async def test_delete(client):
    card_id = (await client.post("/admin/cards", json=VALID)).json()["id"]
    assert (await client.delete(f"/admin/cards/{card_id}")).status_code == 204
    assert (await client.get(f"/admin/cards/{card_id}")).status_code == 404


async def test_seed_is_idempotent(db):
    total = len(json.loads(CARDS_FILE.read_text(encoding="utf-8")))
    assert await load_cards(db) == (total, 0)
    assert await load_cards(db) == (0, total)
    assert (await db.scalar(select(func.count()).select_from(select(Card).subquery()))) == total
    assert 20 <= total <= 30


async def test_update_cards_restores_changed_cards_and_resets_verified(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    changed = (await db.scalars(select(Card).filter_by(term="encryption"))).one()
    changed.translation_ru = "что-то другое"
    await db.commit()

    assert await update_cards(db) == 1
    await db.refresh(changed)
    assert changed.translation_ru == "шифрование"
    assert changed.verified is False
    assert (await db.scalar(select(func.count()).select_from(select(Card).filter_by(verified=True).subquery()))) == (await db.scalar(select(func.count()).select_from(select(Card).subquery()))) - 1


async def test_update_cards_without_changes_does_nothing(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    assert await update_cards(db) == 0
    assert (await db.scalar(select(func.count()).select_from(select(Card).filter_by(verified=False).subquery()))) == 0
