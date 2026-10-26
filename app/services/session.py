import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SchedulerConfig, scheduler_config
from app.enums import ErrorType, TaskType
from app.llm.base import LLMProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.schemas.card import CardRead
from app.schemas.session import AnswerOut, TaskOut
from app.services.scheduler import ReviewState, next_due_date, review
from app.services.task_source import get_task
from app.services.tasks import correct_answer, evaluate, is_available

STAGE_TASKS = (
    TaskType.DEFINITION_MATCH,
    TaskType.GAP_FILL,
    TaskType.COLLOCATION_CHOICE,
    TaskType.SPELLING_CHOICE,
    TaskType.WRITE_TERM,
)

TASK_BY_ERROR = {
    ErrorType.FORM: TaskType.WRITE_TERM,
    ErrorType.MEANING: TaskType.DEFINITION_MATCH,
    ErrorType.USAGE: TaskType.GAP_FILL,
    ErrorType.COLLOCATION: TaskType.COLLOCATION_CHOICE,
}


class CardNotInSession(Exception):
    pass


class TaskUnavailable(Exception):
    pass


@dataclass
class QueueItem:
    card: Card
    task_type: TaskType


def _stage_task(progress: CardProgress) -> TaskType:
    if progress.last_error_type:
        return TASK_BY_ERROR[ErrorType(progress.last_error_type)]
    return STAGE_TASKS[min(progress.repetitions, len(STAGE_TASKS) - 1)]


def _retry_items(db: Session, user: User, today: date) -> list[QueueItem]:
    rows = db.scalars(
        select(ReviewHistory)
        .where(ReviewHistory.user_id == user.id, ReviewHistory.answered_on == today)
        .order_by(ReviewHistory.id)
    ).all()
    last_by_card = {row.card_id: row for row in rows}
    items = []
    for row in sorted(last_by_card.values(), key=lambda r: r.id):
        card = db.get(Card, row.card_id)
        if not row.is_correct and card.verified:
            items.append(QueueItem(card, TASK_BY_ERROR[ErrorType(row.error_type)]))
    return items


def build_queue(
    db: Session, user: User, today: date, config: SchedulerConfig = scheduler_config
) -> list[QueueItem]:
    due = db.execute(
        select(CardProgress, Card)
        .join(Card, Card.id == CardProgress.card_id)
        .where(
            CardProgress.user_id == user.id,
            Card.verified.is_(True),
            CardProgress.due_date <= today,
        )
        .order_by(CardProgress.due_date, Card.id)
    ).all()
    items = [QueueItem(card, _stage_task(progress)) for progress, card in due]

    started_today = db.scalars(
        select(CardProgress.id).where(
            CardProgress.user_id == user.id, CardProgress.first_seen_on == today
        )
    ).all()
    slots = max(0, config.new_cards_per_day - len(started_today))
    known = select(CardProgress.card_id).where(CardProgress.user_id == user.id)
    new_cards = db.scalars(
        select(Card)
        .where(Card.verified.is_(True), Card.id.not_in(known))
        .order_by(Card.id)
        .limit(slots)
    ).all()
    items += [QueueItem(card, STAGE_TASKS[0]) for card in new_cards]

    return items + _retry_items(db, user, today)


def next_task(
    db: Session,
    user: User,
    today: date,
    provider: LLMProvider | None = None,
    rng: random.Random | None = None,
) -> tuple[TaskOut | None, int]:
    queue = build_queue(db, user, today)
    if not queue:
        return None, 0
    item = queue[0]
    others = list(db.scalars(select(Card).where(Card.id != item.card.id)))
    return get_task(db, provider, item.card, item.task_type, others, rng), len(queue)


def _update_progress(
    db: Session, user: User, card: Card, error: ErrorType | None, today: date, config: SchedulerConfig
) -> None:
    progress = db.scalar(
        select(CardProgress).where(CardProgress.user_id == user.id, CardProgress.card_id == card.id)
    )
    if progress is None:
        progress = CardProgress(
            user_id=user.id, card_id=card.id, interval=0, ease=config.ease_start,
            repetitions=0, first_seen_on=today, due_date=today,
        )
        db.add(progress)

    state = ReviewState(progress.interval, progress.ease, progress.repetitions, progress.pending_interval)
    new_state = review(state, error, config)
    progress.interval = new_state.interval
    progress.ease = new_state.ease
    progress.repetitions = new_state.repetitions
    progress.pending_interval = new_state.pending_interval
    progress.due_date = next_due_date(new_state, today)
    progress.last_error_type = error.value if error else None


def submit_answer(
    db: Session,
    user: User,
    card_id: int,
    task_type: TaskType,
    answer: str,
    today: date,
    task_id: int | None = None,
    config: SchedulerConfig = scheduler_config,
) -> AnswerOut:
    queue = build_queue(db, user, today, config)
    item = next((i for i in queue if i.card.id == card_id), None)
    if item is None:
        raise CardNotInSession
    card = item.card

    entry = None
    if task_id is not None:
        entry = db.get(TaskBank, task_id)
        if entry is None or entry.card_id != card.id or entry.task_type != task_type.value:
            raise TaskUnavailable
        error = evaluate(card, task_type, answer, correct=entry.correct_answer)
        correct_text = entry.correct_answer
        entry.times_used += 1
    else:
        if not is_available(card, task_type):
            raise TaskUnavailable
        error = evaluate(card, task_type, answer)
        correct_text = correct_answer(card, task_type)

    already_counted = db.scalar(
        select(ReviewHistory.id).where(
            ReviewHistory.user_id == user.id,
            ReviewHistory.card_id == card.id,
            ReviewHistory.answered_on == today,
            ReviewHistory.is_retry.is_(False),
        )
    )
    is_retry = already_counted is not None
    if not is_retry:
        _update_progress(db, user, card, error, today, config)

    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type=task_type.value, answer=answer,
            is_correct=error is None, error_type=error.value if error else None,
            is_retry=is_retry, answered_on=today, task_bank_id=task_id,
        )
    )
    db.commit()

    return AnswerOut(
        correct=error is None,
        error_type=error,
        correct_answer=correct_text,
        card=CardRead.model_validate(card),
        retry_in_session=error is not None,
        remaining=len(build_queue(db, user, today, config)),
    )
