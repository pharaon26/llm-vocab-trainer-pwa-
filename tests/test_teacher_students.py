from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Card, CardProgress, ReviewHistory, TeacherGroup, TeacherStudent, User
from app.seed import load_cards
from tests.conftest import login


@pytest.fixture
async def cards(db):
    await load_cards(db)
    return {c.term: c for c in (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).all()}


@pytest.fixture
async def people(client, db):
    headers = {
        "t1": await login(client, name="teach_one", role="teacher"),
        "t2": await login(client, name="teach_two", role="teacher"),
    }
    for name in ("anna", "boris", "clara", "denis"):
        headers[name] = await login(client, name=name)
    return headers


async def uid(db, name):
    return await db.scalar(select(User.id).where(User.name == name))


async def link(db, teacher, student, group=None):
    db.add(TeacherStudent(teacher_id=await uid(db, teacher), student_id=await uid(db, student), group_id=group))
    await db.commit()


async def new_group(db, teacher, name):
    group = TeacherGroup(teacher_id=await uid(db, teacher), name=name)
    db.add(group)
    await db.commit()
    return group.id


async def answer(db, student, card, correct=True, retry=False, practice=False, day=date(2026, 1, 5)):
    db.add(ReviewHistory(
        user_id=await uid(db, student), card_id=card.id, task_type="definition_match", answer="x",
        is_correct=correct, error_type=None if correct else "meaning", is_retry=retry, is_practice=practice,
        answered_on=day,
    ))
    await db.commit()


async def progress(db, student, card, interval, pending=None):
    db.add(CardProgress(
        user_id=await uid(db, student), card_id=card.id, interval=interval, ease=2.5, repetitions=3,
        pending_interval=pending, due_date=date(2026, 2, 1), first_seen_on=date(2026, 1, 1),
    ))
    await db.commit()


def flat(data):
    return {s["name"]: s for g in data["groups"] for s in g["students"]}


async def test_teacher_sees_his_students_by_group_with_summaries(client, db, people, cards):
    g1, g2 = await new_group(db, "teach_one", "Alpha"), await new_group(db, "teach_one", "Beta")
    await link(db, "teach_one", "anna", g1)
    await link(db, "teach_one", "boris", g2)
    await link(db, "teach_one", "clara")
    await link(db, "teach_two", "denis")
    vuln, threat, patch = cards["vulnerability"], cards["threat"], cards["patch"]
    await answer(db, "anna", vuln, True)
    await answer(db, "anna", threat, False)
    await answer(db, "anna", threat, True, retry=True, day=date(2026, 1, 9))
    await answer(db, "anna", patch, True, practice=True, day=date(2026, 1, 20))
    await progress(db, "anna", vuln, 30)
    await progress(db, "anna", threat, 30, pending=1)
    await progress(db, "anna", patch, 5)
    data = (await client.get("/teacher/students", headers=people["t1"])).json()
    assert [(g["id"], g["name"]) for g in data["groups"]] == [(g1, "Alpha"), (g2, "Beta"), (None, None)]
    students = flat(data)
    assert set(students) == {"anna", "boris", "clara"}
    assert students["anna"] == {"name": "anna", "learned": 1, "answered": 2, "accuracy": 0.5, "last_active": "2026-01-09"}
    assert students["boris"] == {"name": "boris", "learned": 0, "answered": 0, "accuracy": None, "last_active": None}
    assert [s["name"] for s in data["groups"][2]["students"]] == ["clara"]


async def test_summary_has_no_individual_answers(client, db, people, cards):
    await link(db, "teach_one", "anna")
    await answer(db, "anna", cards["threat"], False)
    student = flat((await client.get("/teacher/students", headers=people["t1"])).json())["anna"]
    assert set(student) == {"name", "learned", "answered", "accuracy", "last_active"}


async def test_personal_cards_and_practice_do_not_count(client, db, people, cards):
    await link(db, "teach_one", "anna")
    personal = Card(
        term="mine", transcription="/x/", part_of_speech="noun", definition_en="d", translation_ru="т",
        collocations=["a b", "c d"], examples=["e one", "e two"], common_mistakes=["m"], domain_id=cards["threat"].domain_id,
        owner_id=await uid(db, "anna"), confirmed_by_owner=True,
    )
    db.add(personal)
    await db.commit()
    await answer(db, "anna", personal, False)
    await progress(db, "anna", personal, 40)
    await answer(db, "anna", cards["threat"], False, practice=True)
    student = flat((await client.get("/teacher/students", headers=people["t1"])).json())["anna"]
    assert student["learned"] == 0 and student["answered"] == 0 and student["last_active"] is None
    analytics = (await client.get("/teacher/analytics", headers=people["t1"])).json()
    assert analytics["answers"] == 0 and analytics["hardest_terms"] == []
    assert analytics["practice_answers"] == 1


async def test_students_of_other_teachers_are_invisible(client, db, people, cards):
    await link(db, "teach_one", "anna")
    await link(db, "teach_two", "denis")
    await answer(db, "denis", cards["threat"], False)
    assert set(flat((await client.get("/teacher/students", headers=people["t1"])).json())) == {"anna"}
    assert set(flat((await client.get("/teacher/students", headers=people["t2"])).json())) == {"denis"}
    assert (await client.get("/teacher/students", headers=people["anna"])).status_code == 403


async def test_students_before_acceptance_are_invisible(client, db, people, cards):
    await client.post("/teacher/invitations", headers=people["t1"], json={"name": "anna"})
    await client.post("/me/teachers/requests", headers=people["boris"], json={"name": "teach_one"})
    await answer(db, "anna", cards["threat"], False)
    await answer(db, "boris", cards["threat"], False)
    assert (await client.get("/teacher/students", headers=people["t1"])).json() == {"groups": []}
    assert (await client.get("/teacher/analytics", headers=people["t1"])).json()["answers"] == 0


async def test_access_disappears_immediately_after_the_link_is_broken(client, db, people, cards):
    await link(db, "teach_one", "anna")
    await answer(db, "anna", cards["threat"], False)
    assert (await client.get("/teacher/analytics", headers=people["t1"])).json()["answers"] == 1
    assert (await client.delete("/me/teachers/teach_one", headers=people["anna"])).status_code == 204
    assert (await client.get("/teacher/students", headers=people["t1"])).json() == {"groups": []}
    assert (await client.get("/teacher/analytics", headers=people["t1"])).json()["answers"] == 0
    await link(db, "teach_one", "anna")
    assert (await client.delete("/teacher/students/anna", headers=people["t1"])).status_code == 204
    assert (await client.get("/teacher/analytics", headers=people["t1"])).json()["answers"] == 0


async def test_analytics_by_group(client, db, people, cards):
    g1, g2 = await new_group(db, "teach_one", "Alpha"), await new_group(db, "teach_one", "Beta")
    await link(db, "teach_one", "anna", g1)
    await link(db, "teach_one", "boris", g2)
    await link(db, "teach_one", "clara")
    for _ in range(3):
        await answer(db, "anna", cards["threat"], False)
    for _ in range(2):
        await answer(db, "boris", cards["patch"], True)
    await answer(db, "clara", cards["patch"], False)
    everyone = (await client.get("/teacher/analytics?min_answers=1", headers=people["t1"])).json()
    assert (everyone["students"], everyone["answers"], everyone["errors"]) == (3, 6, 4)
    first = (await client.get(f"/teacher/analytics?min_answers=1&group_id={g1}", headers=people["t1"])).json()
    assert (first["students"], first["answers"], first["errors"]) == (1, 3, 3)
    assert [t["term"] for t in first["hardest_terms"]] == ["threat"]
    assert {e["error_type"]: e["count"] for e in first["error_types"]}["meaning"] == 3
    second = (await client.get(f"/teacher/analytics?min_answers=1&group_id={g2}", headers=people["t1"])).json()
    assert (second["answers"], second["errors"], second["hardest_terms"]) == (2, 0, [])


async def test_analytics_group_must_be_own(client, db, people, cards):
    other = await new_group(db, "teach_two", "Theirs")
    await link(db, "teach_two", "denis", other)
    await answer(db, "denis", cards["threat"], False)
    assert (await client.get(f"/teacher/analytics?group_id={other}", headers=people["t1"])).status_code == 404
    assert (await client.get("/teacher/analytics?group_id=999999", headers=people["t1"])).status_code == 404
    assert (await client.get(f"/teacher/analytics?group_id={other}", headers=people["t2"])).json()["answers"] == 1


async def test_analytics_excludes_unlinked_students_even_with_many_answers(client, db, people, cards):
    await link(db, "teach_one", "anna")
    for _ in range(5):
        await answer(db, "boris", cards["threat"], False)
    data = (await client.get("/teacher/analytics?min_answers=1", headers=people["t1"])).json()
    assert data["students"] == 0 and data["hardest_terms"] == []


async def test_admin_analytics_still_covers_everyone(client, db, people, cards, admin_headers):
    await link(db, "teach_one", "anna")
    await answer(db, "anna", cards["threat"], False)
    await answer(db, "denis", cards["threat"], False)
    assert (await client.get("/admin/analytics", headers=admin_headers)).json()["answers"] == 2
    assert (await client.get("/admin/analytics", headers=people["t1"])).status_code == 403


async def test_teachers_do_not_count_as_students(client, db, people, cards):
    await link(db, "teach_one", "anna")
    await answer(db, "teach_one", cards["threat"], False)
    assert (await client.get("/teacher/analytics?min_answers=1", headers=people["t1"])).json()["answers"] == 0
