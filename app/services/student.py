from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import LearningConfig, learning_config
from app.enums import ErrorType
from app.models import Card, CardProgress, ReviewHistory, User
from app.schemas.student import ProgressItem, ProgressOut, ProgressSummary


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
