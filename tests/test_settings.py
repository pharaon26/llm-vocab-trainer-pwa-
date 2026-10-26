from datetime import timedelta

import pytest

from app.models import Card, CardProgress, User
from app.seed import load_cards
from tests.conftest import login


@pytest.fixture
def verified(db):
    load_cards(db)
    db.query(Card).update({Card.verified: True})
    db.commit()


def put(client, headers, value):
    return client.put("/me/settings", headers=headers, json={"new_cards_per_day": value})


def remaining(client, headers):
    return client.get("/session/next", headers=headers).json()["remaining"]


def test_settings_require_login(client):
    assert client.get("/me/settings").status_code == 401
    assert client.put("/me/settings", json={"new_cards_per_day": 5}).status_code == 401


def test_default_is_five_with_bounds(client, student_headers):
    assert client.get("/me/settings", headers=student_headers).json() == {
        "new_cards_per_day": 5, "min_new_per_day": 1, "max_new_per_day": 20,
    }


@pytest.mark.parametrize("value", [1, 7, 20])
def test_update_is_saved(client, db, student_headers, value):
    assert put(client, student_headers, value).json()["new_cards_per_day"] == value
    assert client.get("/me/settings", headers=student_headers).json()["new_cards_per_day"] == value
    assert db.query(User).filter_by(name="student").one().new_cards_per_day == value


@pytest.mark.parametrize("value", [0, -1, 21, 100, "five", None, 2.5])
def test_values_outside_the_range_are_rejected(client, student_headers, value):
    assert put(client, student_headers, value).status_code == 422
    assert client.get("/me/settings", headers=student_headers).json()["new_cards_per_day"] == 5


def test_setting_controls_how_many_new_terms_are_offered(client, student_headers, verified):
    assert remaining(client, student_headers) == 5
    put(client, student_headers, 2)
    assert remaining(client, student_headers) == 2
    put(client, student_headers, 20)
    assert remaining(client, student_headers) == 20


def test_maximum_does_not_exceed_available_terms(client, db, student_headers, verified):
    db.query(Card).filter(Card.id > 8).update({Card.verified: False})
    db.commit()
    put(client, student_headers, 20)
    assert remaining(client, student_headers) == 8


def open_today(db, clock, count):
    user = db.query(User).filter_by(name="student").one()
    for card in db.query(Card).order_by(Card.id).limit(count):
        db.add(CardProgress(user_id=user.id, card_id=card.id, interval=1, ease=2.5, repetitions=1,
                            first_seen_on=clock.today, due_date=clock.today + timedelta(days=1)))
    db.commit()


def test_limit_counts_terms_already_opened_today(client, db, clock, student_headers, verified):
    put(client, student_headers, 3)
    open_today(db, clock, 3)
    assert remaining(client, student_headers) == 0
    put(client, student_headers, 5)
    assert remaining(client, student_headers) == 2


def test_lowering_below_the_opened_count_gives_no_new_terms_today(client, db, clock, student_headers, verified):
    open_today(db, clock, 4)
    put(client, student_headers, 1)
    idle = client.get("/session/next", headers=student_headers).json()
    assert (idle["task"], idle["remaining"], idle["new_cards_per_day"]) == (None, 0, 1)


def test_idle_info_reports_the_students_own_limit(client, student_headers):
    put(client, student_headers, 12)
    assert client.get("/session/next", headers=student_headers).json()["new_cards_per_day"] == 12


def test_settings_are_per_student(client, student_headers):
    put(client, student_headers, 9)
    other = login(client, name="other")
    assert client.get("/me/settings", headers=other).json()["new_cards_per_day"] == 5
