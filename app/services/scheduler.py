from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.config import SchedulerConfig, scheduler_config
from app.enums import ErrorType


@dataclass(frozen=True)
class ReviewState:
    interval: float = 0
    ease: float = scheduler_config.ease_start
    repetitions: int = 0
    pending_interval: float | None = None


def review(
    state: ReviewState,
    error: ErrorType | None,
    config: SchedulerConfig = scheduler_config,
) -> ReviewState:
    if error is None:
        return _correct(state, config)
    return _incorrect(state, error, config)


def _correct(state: ReviewState, config: SchedulerConfig) -> ReviewState:
    if state.pending_interval is not None:
        interval = state.pending_interval
    elif state.repetitions == 0:
        interval = config.first_interval
    elif state.repetitions == 1:
        interval = config.second_interval
    else:
        interval = state.interval * state.ease

    ease = min(config.ease_max, round(state.ease + config.ease_step, 2))
    return ReviewState(interval, ease, state.repetitions + 1, None)


def _incorrect(state: ReviewState, error: ErrorType, config: SchedulerConfig) -> ReviewState:
    rule = config.error_rules[error]
    base = state.pending_interval if state.pending_interval is not None else state.interval
    ease = max(config.ease_min, round(state.ease - rule.delta, 2))
    return replace(state, ease=ease, pending_interval=max(1, base * rule.k))


def days_until_due(state: ReviewState) -> int:
    if state.pending_interval is not None:
        return 1
    return max(1, round(state.interval))


def next_due_date(state: ReviewState, reviewed_on: date) -> date:
    return reviewed_on + timedelta(days=days_until_due(state))
