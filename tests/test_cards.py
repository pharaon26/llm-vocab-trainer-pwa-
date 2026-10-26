import json

import pytest

from app.models import Card
from app.seed import CARDS_FILE, load_cards

@pytest.fixture
def client(client, teacher_headers):
    client.headers.update(teacher_headers)
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


def test_create_and_read(client):
    created = client.post("/cards", json=VALID)
    assert created.status_code == 201
    body = created.json()
    assert body["verified"] is False
    assert client.get(f"/cards/{body['id']}").json()["term"] == "vulnerability"


def test_duplicate_term_conflict(client):
    client.post("/cards", json=VALID)
    assert client.post("/cards", json=VALID).status_code == 409


def test_student_cannot_modify_cards(client, student_headers):
    client.headers.update(student_headers)
    assert client.post("/cards", json=VALID).status_code == 403


def test_not_found(client):
    assert client.get("/cards/999").status_code == 404


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
def test_validation(client, field, value):
    response = client.post("/cards", json={**VALID, field: value})
    assert response.status_code == 422


def test_update_resets_verified(client):
    card_id = client.post("/cards", json=VALID).json()["id"]
    assert client.patch(f"/cards/{card_id}/verify").json()["verified"] is True
    updated = client.put(f"/cards/{card_id}", json={**VALID, "translation_ru": "брешь"})
    assert updated.json()["translation_ru"] == "брешь"
    assert updated.json()["verified"] is False


def test_update_to_taken_term_conflict(client):
    client.post("/cards", json=VALID)
    other = client.post("/cards", json={**VALID, "term": "threat"}).json()["id"]
    assert client.put(f"/cards/{other}", json=VALID).status_code == 409


def test_filter_by_verified(client):
    first = client.post("/cards", json=VALID).json()["id"]
    client.post("/cards", json={**VALID, "term": "threat"})
    client.patch(f"/cards/{first}/verify")
    assert len(client.get("/cards").json()) == 2
    assert [c["term"] for c in client.get("/cards?verified=true").json()] == ["vulnerability"]


def test_delete(client):
    card_id = client.post("/cards", json=VALID).json()["id"]
    assert client.delete(f"/cards/{card_id}").status_code == 204
    assert client.get(f"/cards/{card_id}").status_code == 404


def test_seed_is_idempotent(db):
    total = len(json.loads(CARDS_FILE.read_text(encoding="utf-8")))
    assert load_cards(db) == (total, 0)
    assert load_cards(db) == (0, total)
    assert db.query(Card).count() == total
    assert 20 <= total <= 30
