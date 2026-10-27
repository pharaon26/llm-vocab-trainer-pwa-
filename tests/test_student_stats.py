from datetime import date, timedelta

import pytest

from sqlalchemy import select
from app.models import Card, ReviewHistory, User
from app.seed import load_cards
from app.services.student import streaks

TODAY = date(2026, 1, 10)


@pytest.fixture
async def card(db):
    await load_cards(db)
    return (await db.scalars(select(Card).filter_by(term="patch"))).one()


async def user_of(db, name="student"):
    return (await db.scalars(select(User).filter_by(name=name))).one()


async def add(db, user, card, day, correct=True, error=None, retry=False):
    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type="definition_match", answer="x",
            is_correct=correct, error_type=None if correct else error, is_retry=retry, answered_on=day,
        )
    )
    await db.commit()


def days(*offsets):
    return {TODAY - timedelta(days=offset) for offset in offsets}


@pytest.mark.parametrize(
    "active, expected",
    [
        (set(), (0, 0)),
        (days(0), (1, 1)),
        (days(0, 1, 2), (3, 3)),
        (days(1, 2), (2, 2)),
        (days(2, 3), (0, 2)),
        (days(0, 1, 3, 4, 5, 6), (2, 4)),
        (days(10, 11, 12, 13, 14), (0, 5)),
    ],
)
def test_streaks(active, expected):
    assert streaks(active, TODAY) == expected


async def test_stats_require_login(client):
    assert (await client.get("/me/stats")).status_code == 401


async def test_stats_window_length_is_validated(client, student_headers):
    assert (await client.get("/me/stats?days=6", headers=student_headers)).status_code == 422
    assert (await client.get("/me/stats?days=61", headers=student_headers)).status_code == 422
    assert len((await client.get("/me/stats?days=7", headers=student_headers)).json()["days"]) == 7


async def test_empty_stats(client, clock, student_headers):
    clock.today = TODAY
    data = (await client.get("/me/stats", headers=student_headers)).json()
    assert len(data["days"]) == 14
    assert data["days"][-1]["date"] == "2026-01-10" and data["days"][0]["date"] == "2025-12-28"
    assert all(d["answered"] == 0 and d["accuracy"] is None for d in data["days"])
    assert data["streak"] == {"current": 0, "best": 0}
    assert data["totals"] == {"answered": 0, "correct": 0, "accuracy": None}
    assert all(e["count"] == 0 and e["share"] == 0.0 for e in data["error_types"])


async def test_daily_accuracy_counts_first_answers_only(client, db, clock, student_headers, card):
    clock.today = TODAY
    user = await user_of(db)
    yesterday = TODAY - timedelta(days=1)
    for correct in (True, True, False):
        await add(db, user, card, yesterday, correct, "meaning")
    await add(db, user, card, yesterday, False, "meaning", retry=True)
    await add(db, user, card, TODAY, True)

    data = (await client.get("/me/stats", headers=student_headers)).json()
    by_date = {d["date"]: d for d in data["days"]}
    assert by_date["2026-01-09"] == {"date": "2026-01-09", "answered": 3, "correct": 2, "accuracy": 0.667, "practice": 0}
    assert by_date["2026-01-10"]["accuracy"] == 1.0
    assert data["totals"] == {"answered": 4, "correct": 3, "accuracy": 0.75}


async def test_error_distribution_and_streak(client, db, clock, student_headers, card):
    clock.today = TODAY
    user = await user_of(db)
    for offset, error in ((0, "meaning"), (1, "meaning"), (2, "form"), (3, "usage")):
        await add(db, user, card, TODAY - timedelta(days=offset), False, error)
    await add(db, user, card, TODAY - timedelta(days=1), False, "collocation", retry=True)

    data = (await client.get("/me/stats", headers=student_headers)).json()
    types = {e["error_type"]: (e["count"], e["share"]) for e in data["error_types"]}
    assert types == {"form": (1, 0.25), "meaning": (2, 0.5), "usage": (1, 0.25), "collocation": (0, 0.0)}
    assert data["streak"] == {"current": 4, "best": 4}


async def test_retry_only_day_still_counts_for_streak(client, db, clock, student_headers, card):
    clock.today = TODAY
    await add(db, await user_of(db), card, TODAY, False, "meaning", retry=True)
    data = (await client.get("/me/stats", headers=student_headers)).json()
    assert data["streak"]["current"] == 1
    assert data["totals"]["answered"] == 0


async def test_stats_are_private(client, db, clock, student_headers, card):
    from tests.conftest import login

    clock.today = TODAY
    await add(db, await user_of(db), card, TODAY)
    other = await login(client, name="other")
    assert (await client.get("/me/stats", headers=other)).json()["totals"]["answered"] == 0
