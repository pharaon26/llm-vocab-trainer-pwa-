from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import LearningConfig, learning_config
from app.enums import ErrorType
from app.enums import TaskType
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.schemas.student import HistoryItem, HistoryOut, ProgressItem, ProgressOut, ProgressSummary
from app.services.tasks import correct_answer, task_prompt


def card_status(progress: CardProgress | None, config: LearningConfig = learning_config) -> str:
    if progress is None:
        return "new"
    if progress.pending_interval is None and progress.interval >= config.learned_interval_days:
        return "learned"
    return "learning"


def error_counts(db: Session, user: User) -> dict[int, dict[str, int]]:
    rows = db.execute(
        select(ReviewHistory.card_id, ReviewHistory.error_type, func.count())
        .where(
            ReviewHistory.user_id == user.id,
            ReviewHistory.is_correct.is_(False),
            ReviewHistory.is_retry.is_(False),
        )
        .group_by(ReviewHistory.card_id, ReviewHistory.error_type)
    ).all()
    result: dict[int, dict[str, int]] = {}
    for card_id, error_type, count in rows:
        result.setdefault(card_id, {t.value: 0 for t in ErrorType})[error_type] = count
    return result


def build_progress(db: Session, user: User, config: LearningConfig = learning_config) -> ProgressOut:
    cards = db.scalars(select(Card).where(Card.verified.is_(True)).order_by(Card.term)).all()
    progress = {
        p.card_id: p for p in db.scalars(select(CardProgress).where(CardProgress.user_id == user.id))
    }
    errors = error_counts(db, user)
    empty = {t.value: 0 for t in ErrorType}

    items = [
        ProgressItem(
            term=card.term,
            status=card_status(progress.get(card.id), config),
            due_date=progress[card.id].due_date if card.id in progress else None,
            repetitions=progress[card.id].repetitions if card.id in progress else 0,
            errors=errors.get(card.id, empty),
        )
        for card in cards
    ]
    items.sort(key=lambda i: (i.due_date is None, i.due_date or date.max, i.term))
    counts = {status: sum(1 for i in items if i.status == status) for status in ("new", "learning", "learned")}
    return ProgressOut(summary=ProgressSummary(total=len(items), **counts), items=items)


def build_history(db: Session, user: User, term: str | None, limit: int, offset: int) -> HistoryOut:
    query = (
        select(ReviewHistory, Card, TaskBank)
        .join(Card, Card.id == ReviewHistory.card_id)
        .outerjoin(TaskBank, TaskBank.id == ReviewHistory.task_bank_id)
        .where(ReviewHistory.user_id == user.id)
    )
    if term:
        query = query.where(Card.term == term)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(ReviewHistory.id.desc()).limit(limit).offset(offset)).all()
    terms = db.scalars(
        select(Card.term)
        .join(ReviewHistory, ReviewHistory.card_id == Card.id)
        .where(ReviewHistory.user_id == user.id)
        .distinct()
        .order_by(Card.term)
    ).all()

    items = []
    for row, card, entry in rows:
        task_type = TaskType(row.task_type)
        items.append(
            HistoryItem(
                id=row.id, answered_on=row.answered_on, created_at=row.created_at, term=card.term,
                task_type=task_type,
                prompt=row.prompt if row.prompt is not None else task_prompt(card, task_type, None, entry),
                answer=row.answer,
                correct_answer=row.correct_answer if row.correct_answer is not None else (
                    entry.correct_answer if entry else correct_answer(card, task_type)
                ),
                is_correct=row.is_correct, error_type=row.error_type, is_retry=row.is_retry,
                classified_by=row.classified_by, comment=row.comment,
            )
        )
    return HistoryOut(total=total, terms=list(terms), items=items)
