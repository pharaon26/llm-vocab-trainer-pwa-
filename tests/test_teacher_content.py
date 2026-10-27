import pytest
from sqlalchemy import func, select

from app.models import Card, Deck, GroupDeck, TeacherGroup, TeacherStudent, User
from app.seed import load_cards
from tests.conftest import login

CARD = {
    "term": "latency", "transcription": "/ˈleɪtənsi/", "part_of_speech": "noun",
    "definition_en": "The delay before a transfer of data begins.", "translation_ru": "задержка",
    "collocations": ["low latency", "network latency"],
    "examples": ["Low latency matters.", "We measured the latency."],
    "common_mistakes": ["Confusing latency with bandwidth."], "contrast_term": "bandwidth", "domain": "IT",
}


@pytest.fixture
async def cards(db):
    await load_cards(db)


@pytest.fixture
async def people(client, db, cards):
    headers = {
        "t1": await login(client, name="teach_one", role="teacher"),
        "t2": await login(client, name="teach_two", role="teacher"),
    }
    for name in ("anna", "boris", "clara"):
        headers[name] = await login(client, name=name)
    return headers


async def uid(db, name):
    return await db.scalar(select(User.id).where(User.name == name))


async def link(db, teacher, student, group_id=None):
    db.add(TeacherStudent(teacher_id=await uid(db, teacher), student_id=await uid(db, student), group_id=group_id))
    await db.commit()


async def group(client, headers, name):
    return (await client.post("/teacher/groups", headers=headers, json={"name": name})).json()["id"]


async def make_card(client, headers, term="latency"):
    response = await client.post("/teacher/cards", headers=headers, json={**CARD, "term": term})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def make_deck(client, headers, name="Networks", card_ids=(), group_ids=()):
    response = await client.post("/teacher/decks", headers=headers, json={"name": name, "domain": "IT"})
    assert response.status_code == 201, response.text
    deck_id = response.json()["id"]
    if card_ids:
        assert (await client.put(f"/teacher/decks/{deck_id}/cards", headers=headers, json={"card_ids": list(card_ids)})).status_code == 200
    if group_ids:
        assert (await client.put(f"/teacher/decks/{deck_id}/groups", headers=headers, json={"group_ids": list(group_ids)})).status_code == 200
    return deck_id


async def progress_terms(client, headers):
    return {item["term"] for item in (await client.get("/me/progress", headers=headers)).json()["items"]}


async def deck_names(client, headers):
    return {d["name"] for d in (await client.get("/me/decks", headers=headers)).json()}


async def test_teacher_card_crud(client, db, people):
    card_id = await make_card(client, people["t1"])
    created = (await client.get(f"/teacher/cards/{card_id}", headers=people["t1"])).json()
    assert created["term"] == "latency" and created["verified"] is True
    assert (await client.post("/teacher/cards", headers=people["t1"], json=CARD)).status_code == 409
    assert (await client.post("/teacher/cards", headers=people["t1"], json={**CARD, "term": "LATENCY"})).status_code == 409
    assert (await client.post("/teacher/cards", headers=people["t2"], json=CARD)).status_code == 201
    shared_term = await db.scalar(select(Card.term).where(Card.owner_id.is_(None)).limit(1))
    assert (await client.post("/teacher/cards", headers=people["t1"], json={**CARD, "term": shared_term})).status_code == 201
    updated = await client.put(f"/teacher/cards/{card_id}", headers=people["t1"], json={**CARD, "translation_ru": "лаг"})
    assert updated.json()["translation_ru"] == "лаг" and updated.json()["verified"] is True
    assert (await client.post("/teacher/cards", headers=people["t1"], json={**CARD, "term": ""})).status_code == 422
    listed = (await client.get("/teacher/cards", headers=people["t1"])).json()
    assert [c["term"] for c in listed] == sorted([shared_term, "latency"], key=str.lower)
    assert (await client.delete(f"/teacher/cards/{card_id}", headers=people["t1"])).status_code == 204
    assert (await client.get(f"/teacher/cards/{card_id}", headers=people["t1"])).status_code == 404


async def test_teacher_cards_are_invisible_to_other_teachers_and_admin(client, db, people, admin_headers):
    card_id = await make_card(client, people["t1"], "jitter")
    assert (await client.get(f"/teacher/cards/{card_id}", headers=people["t2"])).status_code == 404
    assert (await client.put(f"/teacher/cards/{card_id}", headers=people["t2"], json=CARD)).status_code == 404
    assert (await client.delete(f"/teacher/cards/{card_id}", headers=people["t2"])).status_code == 404
    assert (await client.get("/teacher/cards", headers=people["t2"])).json() == []
    assert "jitter" not in {c["term"] for c in (await client.get("/admin/cards", headers=admin_headers)).json()}
    assert (await client.get(f"/admin/cards/{card_id}", headers=admin_headers)).status_code == 404
    assert (await client.patch(f"/admin/cards/{card_id}/verify", headers=admin_headers)).status_code == 404
    assert (await client.delete(f"/admin/cards/{card_id}", headers=admin_headers)).status_code == 404
    assert await db.scalar(select(func.count()).select_from(Card).where(Card.id == card_id)) == 1


async def test_students_see_teacher_cards_only_through_assigned_decks_of_their_group(client, db, people):
    g1, g2 = await group(client, people["t1"], "Alpha"), await group(client, people["t1"], "Beta")
    card_id = await make_card(client, people["t1"])
    await make_deck(client, people["t1"], "Networks", [card_id], [g1])
    await link(db, "teach_one", "anna", g1)
    await link(db, "teach_one", "boris", g2)
    await link(db, "teach_one", "clara")
    assert "latency" in await progress_terms(client, people["anna"])
    assert "Networks" in await deck_names(client, people["anna"])
    for other in ("boris", "clara"):
        assert "latency" not in await progress_terms(client, people[other])
        assert "Networks" not in await deck_names(client, people[other])


async def test_assigned_deck_is_shown_with_its_teacher_and_cannot_be_deselected(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    card_id = await make_card(client, people["t1"])
    deck_id = await make_deck(client, people["t1"], "Networks", [card_id], [g1])
    await link(db, "teach_one", "anna", g1)
    decks = {d["name"]: d for d in (await client.get("/me/decks", headers=people["anna"])).json()}
    assert decks["Networks"]["teacher"] == "teach_one" and decks["Networks"]["assigned"] and decks["Networks"]["selected"]
    shared_ids = [d["id"] for d in decks.values() if d["teacher"] is None]
    saved = await client.put("/me/decks", headers=people["anna"], json={"deck_ids": shared_ids[:0] + [deck_id]})
    assert saved.status_code == 200
    after = {d["name"]: d for d in saved.json()}
    assert after["Networks"]["selected"] is True
    assert "latency" in await progress_terms(client, people["anna"])


async def test_students_cannot_select_decks_of_teachers_who_did_not_assign_them(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    deck_id = await make_deck(client, people["t1"], "Secret", [await make_card(client, people["t1"])], [])
    await link(db, "teach_one", "anna", g1)
    assert (await client.put("/me/decks", headers=people["anna"], json={"deck_ids": [deck_id]})).status_code == 422
    assert (await client.put("/me/decks", headers=people["boris"], json={"deck_ids": [deck_id]})).status_code == 422
    assert "Secret" not in await deck_names(client, people["anna"])


async def test_visibility_follows_group_changes_and_link_breaks_immediately(client, db, people):
    g1, g2 = await group(client, people["t1"], "Alpha"), await group(client, people["t1"], "Beta")
    await make_deck(client, people["t1"], "Networks", [await make_card(client, people["t1"])], [g1])
    await link(db, "teach_one", "anna", g1)
    assert "latency" in await progress_terms(client, people["anna"])
    await client.put("/teacher/students/anna/group", headers=people["t1"], json={"group_id": g2})
    assert "latency" not in await progress_terms(client, people["anna"])
    await client.put("/teacher/students/anna/group", headers=people["t1"], json={"group_id": g1})
    assert "latency" in await progress_terms(client, people["anna"])
    await client.put("/teacher/students/anna/group", headers=people["t1"], json={"group_id": None})
    assert "latency" not in await progress_terms(client, people["anna"])
    await client.put("/teacher/students/anna/group", headers=people["t1"], json={"group_id": g1})
    assert (await client.delete("/me/teachers/teach_one", headers=people["anna"])).status_code == 204
    assert "latency" not in await progress_terms(client, people["anna"])
    assert "Networks" not in await deck_names(client, people["anna"])


async def test_removing_the_deck_from_a_group_or_deleting_it_hides_it(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    deck_id = await make_deck(client, people["t1"], "Networks", [await make_card(client, people["t1"])], [g1])
    await link(db, "teach_one", "anna", g1)
    await client.put(f"/teacher/decks/{deck_id}/groups", headers=people["t1"], json={"group_ids": []})
    assert "latency" not in await progress_terms(client, people["anna"])
    await client.put(f"/teacher/decks/{deck_id}/groups", headers=people["t1"], json={"group_ids": [g1]})
    assert "latency" in await progress_terms(client, people["anna"])
    assert (await client.delete(f"/teacher/decks/{deck_id}", headers=people["t1"])).status_code == 204
    assert "latency" not in await progress_terms(client, people["anna"])
    assert await db.scalar(select(func.count()).select_from(GroupDeck)) == 0


async def test_a_card_of_another_teacher_is_not_shown_through_my_group(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    g2 = await group(client, people["t2"], "Other")
    other_card = await make_card(client, people["t2"], "jitter")
    await make_deck(client, people["t2"], "Their deck", [other_card], [g2])
    await link(db, "teach_one", "anna", g1)
    await link(db, "teach_two", "boris", g2)
    assert "jitter" not in await progress_terms(client, people["anna"])
    assert "jitter" in await progress_terms(client, people["boris"])


async def test_student_with_two_teachers_sees_both_assignments(client, db, people):
    g1, g2 = await group(client, people["t1"], "Alpha"), await group(client, people["t2"], "Other")
    await make_deck(client, people["t1"], "Deck one", [await make_card(client, people["t1"], "latency")], [g1])
    await make_deck(client, people["t2"], "Deck two", [await make_card(client, people["t2"], "jitter")], [g2])
    await link(db, "teach_one", "anna", g1)
    await link(db, "teach_two", "anna", g2)
    assert {"latency", "jitter"} <= await progress_terms(client, people["anna"])
    await client.delete("/me/teachers/teach_two", headers=people["anna"])
    terms = await progress_terms(client, people["anna"])
    assert "latency" in terms and "jitter" not in terms


async def test_deck_endpoints_are_owner_only(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    g2 = await group(client, people["t2"], "Other")
    card_id = await make_card(client, people["t1"])
    deck_id = await make_deck(client, people["t1"], "Networks", [card_id], [g1])
    body = {"name": "Hacked", "domain": "IT"}
    assert (await client.put(f"/teacher/decks/{deck_id}", headers=people["t2"], json=body)).status_code == 404
    assert (await client.put(f"/teacher/decks/{deck_id}/cards", headers=people["t2"], json={"card_ids": []})).status_code == 404
    assert (await client.put(f"/teacher/decks/{deck_id}/groups", headers=people["t2"], json={"group_ids": [g2]})).status_code == 404
    assert (await client.delete(f"/teacher/decks/{deck_id}", headers=people["t2"])).status_code == 404
    assert (await client.get("/teacher/decks", headers=people["t2"])).json() == []
    assert [d["name"] for d in (await client.get("/teacher/decks", headers=people["t1"])).json()] == ["Networks"]
    assert await db.scalar(select(Deck.name).where(Deck.id == deck_id)) == "Networks"


async def test_cannot_assign_to_foreign_groups_or_use_foreign_cards(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    g2 = await group(client, people["t2"], "Other")
    mine = await make_card(client, people["t1"], "latency")
    theirs = await make_card(client, people["t2"], "jitter")
    deck_id = await make_deck(client, people["t1"], "Networks")
    assert (await client.put(f"/teacher/decks/{deck_id}/groups", headers=people["t1"], json={"group_ids": [g1, g2]})).status_code == 422
    assert (await client.put(f"/teacher/decks/{deck_id}/groups", headers=people["t1"], json={"group_ids": [999999]})).status_code == 422
    assert (await client.put(f"/teacher/decks/{deck_id}/cards", headers=people["t1"], json={"card_ids": [mine, theirs]})).status_code == 422
    shared = await db.scalar(select(Card.id).where(Card.owner_id.is_(None)).limit(1))
    assert (await client.put(f"/teacher/decks/{deck_id}/cards", headers=people["t1"], json={"card_ids": [mine, shared]})).status_code == 200
    assert (await client.get(f"/teacher/decks", headers=people["t1"])).json()[0]["group_ids"] == []


async def test_deck_names_are_unique_per_teacher_only(client, db, people):
    await make_deck(client, people["t1"], "Networks")
    assert (await client.post("/teacher/decks", headers=people["t1"], json={"name": "networks", "domain": "IT"})).status_code == 409
    assert (await client.post("/teacher/decks", headers=people["t2"], json={"name": "Networks", "domain": "IT"})).status_code == 201
    shared_name = await db.scalar(select(Deck.name).where(Deck.owner_id.is_(None)))
    assert (await client.post("/teacher/decks", headers=people["t1"], json={"name": shared_name, "domain": "IT"})).status_code == 201


async def test_teacher_decks_never_leak_into_the_shared_catalog(client, db, people, admin_headers):
    deck_id = await make_deck(client, people["t1"], "Private")
    assert "Private" not in {d["name"] for d in (await client.get("/admin/decks", headers=admin_headers)).json()}
    assert (await client.put(f"/admin/decks/{deck_id}", headers=admin_headers, json={"name": "X", "domain": "IT"})).status_code == 404
    assert (await client.put(f"/admin/decks/{deck_id}/cards", headers=admin_headers, json={"card_ids": []})).status_code == 404
    assert (await client.delete(f"/admin/decks/{deck_id}", headers=admin_headers)).status_code == 404
    assert "Private" not in await deck_names(client, people["anna"])


async def test_shared_starter_set_stays_visible_to_everyone(client, db, people):
    await db.execute(__import__("sqlalchemy").update(Card).where(Card.owner_id.is_(None)).values(verified=True))
    await db.commit()
    assert "vulnerability" in await progress_terms(client, people["anna"])
    assert "IT & Security basics" in await deck_names(client, people["clara"])


async def test_roles_for_teacher_content(client, people, admin_headers):
    for path in ("/teacher/cards", "/teacher/decks", "/teacher/students", "/teacher/groups"):
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=people["anna"])).status_code == 403
        assert (await client.get(path, headers=admin_headers)).status_code == 403


async def test_students_cannot_read_teacher_cards_by_id_in_any_student_endpoint(client, db, people):
    g1 = await group(client, people["t1"], "Alpha")
    card_id = await make_card(client, people["t1"])
    await make_deck(client, people["t1"], "Networks", [card_id], [g1])
    for path in (f"/teacher/cards/{card_id}", f"/admin/cards/{card_id}"):
        assert (await client.get(path, headers=people["clara"])).status_code == 403
    assert (await client.get(f"/me/cards", headers=people["clara"])).json() == []
    dictionary = (await client.get("/me/dictionary", headers=people["clara"])).json()
    assert dictionary == []
