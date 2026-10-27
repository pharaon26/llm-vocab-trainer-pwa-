import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SchedulerConfig, classification_config, scheduler_config
from app.enums import ErrorType, TaskType
from app.llm.base import LLMProvider
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.schemas.card import CardRead
from app.schemas.session import AnswerOut, TaskOut
from app.services.classification import classify_open_answer
from app.services.scheduler import ReviewState, next_due_date, review
from app.services.task_source import CardGone, get_task
from app.services.visibility import new_term_pool, usable
from app.services.tasks import OPEN_TYPES, correct_answer, evaluate, is_available, task_prompt

STAGE_TASKS = (
    TaskType.DEFINITION_MATCH,
    TaskType.GAP_FILL,
    TaskType.COLLOCATION_CHOICE,
    TaskType.SPELLING_CHOICE,
)

ADVANCED_TASKS = (TaskType.WRITE_TERM, TaskType.EXPLAIN_MEANING, TaskType.COMPOSE_SENTENCE)

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
    if progress.repetitions < len(STAGE_TASKS):
        return STAGE_TASKS[progress.repetitions]
    return ADVANCED_TASKS[(progress.repetitions - len(STAGE_TASKS)) % len(ADVANCED_TASKS)]


async def _retry_items(db: AsyncSession, user: User, today: date) -> list[QueueItem]:
    rows = (
        await db.scalars(
            select(ReviewHistory)
            .where(
                ReviewHistory.user_id == user.id,
                ReviewHistory.answered_on == today,
                ReviewHistory.is_practice.is_(False),
            )
            .order_by(ReviewHistory.id)
        )
    ).all()
    last_by_card = {row.card_id: row for row in rows}
    items = []
    for row in sorted(last_by_card.values(), key=lambda r: r.id):
        card = await db.get(Card, row.card_id)
        if (
            not row.is_correct
            and not row.is_retry
            and await db.scalar(select(Card.id).where(Card.id == card.id, usable(user)))
        ):
            items.append(QueueItem(card, TASK_BY_ERROR[ErrorType(row.error_type)]))
    return items


async def build_queue(
    db: AsyncSession, user: User, today: date, config: SchedulerConfig = scheduler_config
) -> list[QueueItem]:
    due = (
        await db.execute(
            select(CardProgress, Card)
            .join(Card, Card.id == CardProgress.card_id)
            .where(
                CardProgress.user_id == user.id,
                usable(user),
                CardProgress.due_date <= today,
            )
            .order_by(CardProgress.due_date, Card.id)
        )
    ).all()
    items = [QueueItem(card, _stage_task(progress)) for progress, card in due]

    started_today = (
        await db.scalars(
            select(CardProgress.id).where(CardProgress.user_id == user.id, CardProgress.first_seen_on == today)
        )
    ).all()
    slots = max(0, user.new_cards_per_day - len(started_today))
    known = select(CardProgress.card_id).where(CardProgress.user_id == user.id)
    pool = await new_term_pool(db, user)
    new_cards = (
        await db.scalars(
            select(Card)
            .where(usable(user), pool, Card.id.not_in(known))
            .order_by(Card.owner_id.is_(None), Card.id)
            .limit(slots)
        )
    ).all()
    items += [QueueItem(card, STAGE_TASKS[0]) for card in new_cards]

    return items + await _retry_items(db, user, today)


async def next_task(
    db: AsyncSession,
    user: User,
    today: date,
    provider: LLMProvider | None = None,
    rng: random.Random | None = None,
) -> tuple[TaskOut | None, int]:
    for _ in range(2):
        queue = await build_queue(db, user, today)
        if not queue:
            return None, 0
        item = queue[0]
        task_type = item.task_type
        if task_type in OPEN_TYPES and provider is None:
            task_type = TaskType.WRITE_TERM
        others = list(await db.scalars(select(Card).where(Card.id != item.card.id, usable(user))))
        try:
            return await get_task(db, provider, item.card, task_type, others, rng), len(queue)
        except CardGone:
            continue
    return None, 0


async def _opened_card(db: AsyncSession, user: User, card_id: int) -> Card:
    card = await db.scalar(
        select(Card)
        .join(CardProgress, CardProgress.card_id == Card.id)
        .where(CardProgress.user_id == user.id, Card.id == card_id, usable(user))
    )
    if card is None:
        raise CardNotInSession
    return card


async def idle_info(db: AsyncSession, user: User, today: date) -> tuple[date | None, int, int]:
    next_review = await db.scalar(
        select(func.min(CardProgress.due_date))
        .join(Card, Card.id == CardProgress.card_id)
        .where(CardProgress.user_id == user.id, usable(user), CardProgress.due_date > today)
    )
    known = select(CardProgress.card_id).where(CardProgress.user_id == user.id)
    pool = await new_term_pool(db, user)
    unseen = await db.scalar(
        select(func.count()).select_from(Card).where(usable(user), pool, Card.id.not_in(known))
    )
    opened = await db.scalar(
        select(func.count())
        .select_from(CardProgress)
        .join(Card, Card.id == CardProgress.card_id)
        .where(CardProgress.user_id == user.id, usable(user))
    )
    return next_review, unseen, opened


async def _update_progress(
    db: AsyncSession, user: User, card: Card, error: ErrorType | None, today: date, config: SchedulerConfig
) -> None:
    progress = await db.scalar(
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


async def _session_card(
    db: AsyncSession, user: User, card_id: int, today: date, config: SchedulerConfig, practice: bool
) -> Card:
    if practice:
        return await _opened_card(db, user, card_id)
    queue = await build_queue(db, user, today, config)
    item = next((i for i in queue if i.card.id == card_id), None)
    if item is None:
        raise CardNotInSession
    return item.card


async def submit_answer(
    db: AsyncSession,
    user: User,
    card_id: int,
    task_type: TaskType,
    answer: str,
    today: date,
    task_id: int | None = None,
    config: SchedulerConfig = scheduler_config,
    provider: LLMProvider | None = None,
    context: str | None = None,
    practice: bool = False,
) -> AnswerOut:
    card = await _session_card(db, user, card_id, today, config, practice)

    classified_by = "task"
    comment = None
    entry = None
    if task_type in OPEN_TYPES:
        if task_type == TaskType.COMPOSE_SENTENCE and context not in classification_config.situations:
            raise TaskUnavailable
        await db.commit()  # соединение возвращается в пул на время вызова модели
        result = await classify_open_answer(provider, card, task_type, answer, context)
        card = await _session_card(db, user, card_id, today, config, practice)  # за это время карточку могли удалить или ответ уже записан
        error, classified_by, comment = result.error_type, result.source, result.comment
        correct_text = correct_answer(card, task_type)
    elif task_id is not None:
        entry = await db.get(TaskBank, task_id)
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
        if task_type == TaskType.WRITE_TERM:
            classified_by = "rule"

    await db.execute(select(func.pg_advisory_xact_lock(user.id, card.id)))
    already_counted = await db.scalar(
        select(ReviewHistory.id).where(
            ReviewHistory.user_id == user.id,
            ReviewHistory.card_id == card.id,
            ReviewHistory.answered_on == today,
            ReviewHistory.is_retry.is_(False),
            ReviewHistory.is_practice.is_(False),
        )
    )
    is_retry = already_counted is not None and not practice
    if not is_retry and not practice:
        await _update_progress(db, user, card, error, today, config)

    db.add(
        ReviewHistory(
            user_id=user.id, card_id=card.id, task_type=task_type.value, answer=answer,
            prompt=task_prompt(card, task_type, context, entry), correct_answer=correct_text,
            is_correct=error is None, error_type=error.value if error else None,
            is_retry=is_retry, is_practice=practice, answered_on=today, task_bank_id=task_id,
            classified_by=classified_by, comment=comment,
        )
    )
    await db.commit()

    return AnswerOut(
        correct=error is None,
        error_type=error,
        correct_answer=correct_text,
        card=CardRead.model_validate(card),
        retry_in_session=error is not None and not practice,
        classified_by=classified_by,
        comment=comment,
        remaining=0 if practice else len(await build_queue(db, user, today, config)),
    )
