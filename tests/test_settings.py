from datetime import timedelta

import pytest

from sqlalchemy import select, update
from app.models import Card, CardProgress, User
from app.seed import load_cards
from tests.conftest import login


@pytest.fixture
async def verified(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()


async def put(client, headers, value):
    return await client.put("/me/settings", headers=headers, json={"new_cards_per_day": value})


async def remaining(client, headers):
    return (await client.get("/session/next", headers=headers)).json()["remaining"]


async def test_settings_require_login(client):
    assert (await client.get("/me/settings")).status_code == 401
    assert (await client.put("/me/settings", json={"new_cards_per_day": 5})).status_code == 401


async def test_default_is_five_with_bounds(client, student_headers):
    assert (await client.get("/me/settings", headers=student_headers)).json() == {
        "new_cards_per_day": 5, "min_new_per_day": 1, "max_new_per_day": 20,
    }


@pytest.mark.parametrize("value", [1, 7, 20])
async def test_update_is_saved(client, db, student_headers, value):
    assert (await put(client, student_headers, value)).json()["new_cards_per_day"] == value
    assert (await client.get("/me/settings", headers=student_headers)).json()["new_cards_per_day"] == value
    assert (await db.scalars(select(User).filter_by(name="student"))).one().new_cards_per_day == value


@pytest.mark.parametrize("value", [0, -1, 21, 100, "five", None, 2.5])
async def test_values_outside_the_range_are_rejected(client, student_headers, value):
    assert (await put(client, student_headers, value)).status_code == 422
    assert (await client.get("/me/settings", headers=student_headers)).json()["new_cards_per_day"] == 5


async def test_setting_controls_how_many_new_terms_are_offered(client, student_headers, verified):
    assert await remaining(client, student_headers) == 5
    await put(client, student_headers, 2)
    assert await remaining(client, student_headers) == 2
    await put(client, student_headers, 20)
    assert await remaining(client, student_headers) == 20


async def test_maximum_does_not_exceed_available_terms(client, db, student_headers, verified):
    keep = [card.id for card in (await db.scalars(select(Card).order_by(Card.id).limit(8))).all()]
    (await db.execute(update(Card).where(Card.id.not_in(keep)).values({Card.verified: False})))
    await db.commit()
    await put(client, student_headers, 20)
    assert await remaining(client, student_headers) == 8


async def open_today(db, clock, count):
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    for card in (await db.scalars(select(Card).order_by(Card.id).limit(count))).all():
        db.add(CardProgress(user_id=user.id, card_id=card.id, interval=1, ease=2.5, repetitions=1,
                            first_seen_on=clock.today, due_date=clock.today + timedelta(days=1)))
    await db.commit()


async def test_limit_counts_terms_already_opened_today(client, db, clock, student_headers, verified):
    await put(client, student_headers, 3)
    await open_today(db, clock, 3)
    assert await remaining(client, student_headers) == 0
    await put(client, student_headers, 5)
    assert await remaining(client, student_headers) == 2


async def test_lowering_below_the_opened_count_gives_no_new_terms_today(client, db, clock, student_headers, verified):
    await open_today(db, clock, 4)
    await put(client, student_headers, 1)
    idle = (await client.get("/session/next", headers=student_headers)).json()
    assert (idle["task"], idle["remaining"], idle["new_cards_per_day"]) == (None, 0, 1)


async def test_idle_info_reports_the_students_own_limit(client, student_headers):
    await put(client, student_headers, 12)
    assert (await client.get("/session/next", headers=student_headers)).json()["new_cards_per_day"] == 12


async def test_settings_are_per_student(client, student_headers):
    await put(client, student_headers, 9)
    other = await login(client, name="other")
    assert (await client.get("/me/settings", headers=other)).json()["new_cards_per_day"] == 5
