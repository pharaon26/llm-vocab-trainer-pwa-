from datetime import date

import pytest

from sqlalchemy import func, select
from app.llm.fake import FakeProvider
from app.models import Card, ReviewHistory, TaskBank, User
from app.seed import load_cards
from app.services import bank
from app.services.task_source import get_task
from app.enums import TaskType


@pytest.fixture
async def cards(db):
    await load_cards(db)
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


@pytest.fixture
def admin(client, admin_headers):
    client.headers.update(admin_headers)
    return client


async def student(db, name):
    user = User(name=name, role="student")
    db.add(user)
    await db.commit()
    return user


async def answer_row(db, user, card, correct, error=None, retry=False, by="task"):
    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type="definition_match", answer="x",
            is_correct=correct, error_type=None if correct else error, is_retry=retry,
            answered_on=date(2026, 1, 1), classified_by=by,
        )
    )
    await db.commit()


async def add_bank(db, card, prompt="A ____ here.", rejected=False, source="fake"):
    entry = TaskBank(
        card_id=card.id, task_type="gap_fill", source=source, prompt=prompt,
        options=[card.term, "a", "b", "c"], correct_answer=card.term, rejected=rejected,
    )
    db.add(entry)
    await db.commit()
    return entry


@pytest.mark.parametrize("path", ["/admin/analytics", "/admin/bank"])
async def test_teacher_endpoints_require_teacher(client, student_headers, path):
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=student_headers)).status_code == 403


async def test_analytics_counts_first_attempts_of_students_only(db, admin, cards):
    anna, boris = await student(db, "anna"), await student(db, "boris")
    vuln, threat = cards["vulnerability"], cards["threat"]
    for _ in range(3):
        await answer_row(db, anna, vuln, True)
    await answer_row(db, boris, vuln, False, "meaning", by="llm")
    await answer_row(db, anna, vuln, False, "form", by="rule")
    await answer_row(db, anna, vuln, False, "meaning", retry=True)
    await answer_row(db, anna, threat, False, "usage")
    await answer_row(db, boris, threat, True)
    teacher_user = (await db.scalars(select(User).filter_by(role="admin"))).one()
    await answer_row(db, teacher_user, vuln, False, "meaning")

    data = (await admin.get("/admin/analytics?min_answers=2")).json()
    assert (data["students"], data["answers"], data["errors"], data["error_rate"]) == (2, 7, 3, 0.429)
    types = {t["error_type"]: (t["count"], t["share"]) for t in data["error_types"]}
    assert types == {"form": (1, 0.333), "meaning": (1, 0.333), "usage": (1, 0.333), "collocation": (0, 0.0)}
    assert [(t["term"], t["attempts"], t["errors"], t["error_rate"]) for t in data["hardest_terms"]] == [
        ("threat", 2, 1, 0.5),
        ("vulnerability", 5, 2, 0.4),
    ]
    assert {s["classified_by"]: s["count"] for s in data["classified_by"]} == {"llm": 1, "rule": 1, "task": 5}


async def test_analytics_min_answers_and_limit(db, admin, cards):
    anna = await student(db, "anna")
    await answer_row(db, anna, cards["threat"], False, "usage")
    assert (await admin.get("/admin/analytics")).json()["hardest_terms"] == []
    assert len((await admin.get("/admin/analytics?min_answers=1")).json()["hardest_terms"]) == 1
    assert (await admin.get("/admin/analytics?min_answers=0")).status_code == 422


async def test_analytics_is_empty_without_answers(admin):
    data = (await admin.get("/admin/analytics")).json()
    assert (data["students"], data["answers"], data["error_rate"], data["hardest_terms"]) == (0, 0, 0.0, [])
    assert all(t["count"] == 0 for t in data["error_types"])


async def test_analytics_has_no_personal_data(db, admin, cards):
    await answer_row(db, await student(db, "SecretName"), cards["threat"], False, "usage")
    assert "SecretName" not in (await admin.get("/admin/analytics?min_answers=1")).text


async def test_bank_list_and_filters(db, admin, cards):
    await add_bank(db, cards["threat"], "One ____.")
    await add_bank(db, cards["vulnerability"], "Two ____.", rejected=True)
    await add_bank(db, cards["vulnerability"], "Three ____.")
    everything = (await admin.get("/admin/bank")).json()
    assert [(e["term"], e["prompt"]) for e in everything] == [
        ("threat", "One ____."), ("vulnerability", "Two ____."), ("vulnerability", "Three ____."),
    ]
    assert len((await admin.get("/admin/bank?rejected=true")).json()) == 1
    assert len((await admin.get("/admin/bank?rejected=false")).json()) == 2
    assert len((await admin.get(f"/admin/bank?card_id={cards['threat'].id}")).json()) == 1
    assert len((await admin.get("/admin/bank?task_type=gap_fill")).json()) == 3
    assert (await admin.get("/admin/bank?task_type=nonsense")).status_code == 422


async def test_reject_and_restore_bank_entry(db, admin, cards):
    entry = await add_bank(db, cards["threat"])
    assert (await admin.patch(f"/admin/bank/{entry.id}", json={"rejected": True})).json()["rejected"] is True
    assert await bank.count(db, cards["threat"].id, TaskType.GAP_FILL, "fake") == 0
    assert (await admin.patch(f"/admin/bank/{entry.id}", json={"rejected": False})).json()["rejected"] is False
    assert await bank.count(db, cards["threat"].id, TaskType.GAP_FILL, "fake") == 1
    assert (await admin.patch("/admin/bank/999", json={"rejected": True})).status_code == 404


async def test_rejected_entries_are_never_shown(db, cards):
    card = cards["threat"]
    rejected = await add_bank(db, card, "Bad ____.", rejected=True)
    good = await add_bank(db, card, "Good ____.")
    assert (await bank.pick(db, card.id, TaskType.GAP_FILL, "fake")).id == good.id
    good.rejected = True
    await db.commit()
    assert await bank.pick(db, card.id, TaskType.GAP_FILL, "fake") is None
    assert rejected.rejected


async def test_regenerated_rejected_task_is_not_saved_again(db, cards):
    card = cards["vulnerability"]
    rejected_json = (
        '{"prompt": "We fixed the ____ today.", "options": ["vulnerability", "threat", "attack", "exploit"],'
        ' "correct_answer": "vulnerability"}'
    )
    review = '{"fitting_options": ["vulnerability"], "term_meaning_matches": true}'
    first = await get_task(db, FakeProvider([rejected_json, review]), card, TaskType.GAP_FILL, [])
    (await db.get(TaskBank, first.task_id)).rejected = True
    await db.commit()

    again = await get_task(db, FakeProvider([rejected_json, review]), card, TaskType.GAP_FILL, list(cards.values()))
    assert again.task_id is None
    assert (await db.scalar(select(func.count()).select_from(select(TaskBank).subquery()))) == 1

