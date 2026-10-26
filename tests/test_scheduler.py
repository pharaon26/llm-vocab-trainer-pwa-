from datetime import date

import pytest

from app.config import SchedulerConfig
from app.enums import ErrorType
from app.services.scheduler import ReviewState, days_until_due, next_due_date, review

ARTICLE_STATE = ReviewState(interval=8, ease=2.5, repetitions=3)


def test_article_example_correct():
    state = review(ARTICLE_STATE, None)
    assert state.interval == 20
    assert state.ease == 2.5


def test_article_example_form_error():
    state = review(ARTICLE_STATE, ErrorType.FORM)
    assert state.pending_interval == 4
    assert state.ease == 2.4
    assert days_until_due(state) == 1


def test_article_example_meaning_error():
    state = review(ARTICLE_STATE, ErrorType.MEANING)
    assert state.pending_interval == 1
    assert state.ease == 2.3


@pytest.mark.parametrize(
    "error, interval, ease",
    [
        (ErrorType.FORM, 4, 2.4),
        (ErrorType.MEANING, 1, 2.3),
        (ErrorType.USAGE, 4, 2.35),
        (ErrorType.COLLOCATION, 4.8, 2.4),
    ],
)
def test_error_table(error, interval, ease):
    state = review(ARTICLE_STATE, error)
    assert state.pending_interval == pytest.approx(interval)
    assert state.ease == pytest.approx(ease)


def test_first_and_second_intervals():
    first = review(ReviewState(), None)
    assert first.interval == 1
    second = review(first, None)
    assert second.interval == 3
    third = review(second, None)
    assert third.interval == pytest.approx(3 * 2.5)


def test_recovery_applies_pending_interval_without_multiplying():
    failed = review(ARTICLE_STATE, ErrorType.FORM)
    recovered = review(failed, None)
    assert recovered.interval == 4
    assert recovered.pending_interval is None
    assert days_until_due(recovered) == 4


def test_ease_recovers_after_form_error_and_two_correct():
    state = review(ARTICLE_STATE, ErrorType.FORM)
    assert state.ease == 2.4
    state = review(review(state, None), None)
    assert state.ease == 2.5


def test_ease_never_above_max():
    state = ReviewState(interval=5, ease=2.5, repetitions=4)
    for _ in range(5):
        state = review(state, None)
        assert state.ease == 2.5


def test_ease_never_below_min():
    state = ReviewState(interval=5, ease=1.4, repetitions=4)
    for _ in range(5):
        state = review(state, ErrorType.MEANING)
        assert state.ease == 1.3


def test_repetitions_not_reset_by_error():
    state = review(ARTICLE_STATE, ErrorType.MEANING)
    assert state.repetitions == 3


def test_error_on_new_term():
    state = review(ReviewState(), ErrorType.FORM)
    assert state.pending_interval == 1
    assert state.ease == 2.4
    recovered = review(state, None)
    assert recovered.interval == 1
    assert review(recovered, None).interval == 3


def test_repeated_error_compounds():
    state = review(review(ARTICLE_STATE, ErrorType.FORM), ErrorType.FORM)
    assert state.pending_interval == 2
    assert state.ease == 2.3


def test_interval_never_below_one_day():
    state = review(ReviewState(interval=1, repetitions=5), ErrorType.MEANING)
    assert state.pending_interval == 1
    assert days_until_due(ReviewState(interval=0.4, repetitions=5)) == 1


def test_next_due_date():
    state = ReviewState(interval=20, repetitions=4)
    assert next_due_date(state, date(2026, 1, 1)) == date(2026, 1, 21)


def test_custom_config_changes_result():
    config = SchedulerConfig(ease_step=0.1, first_interval=2)
    state = review(ReviewState(ease=2.0), None, config)
    assert state.interval == 2
    assert state.ease == 2.1
