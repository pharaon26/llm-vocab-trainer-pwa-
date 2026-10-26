from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import LearningConfig, learning_config
from app.enums import ErrorType, TaskType
from app.models import Card, CardProgress, ReviewHistory, TaskBank, User
from app.schemas.student import (
    DayStat,
    DictionaryEntry,
    HistoryItem,
    HistoryOut,
    ProgressItem,
    ProgressOut,
    ProgressSummary,
    StatsOut,
    StreakStat,
    StudentErrorStat,
    TotalsStat,
)
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
            ReviewHistory.is_practice.is_(False),
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
                is_practice=row.is_practice,
                classified_by=row.classified_by, comment=row.comment,
            )
        )
    return HistoryOut(total=total, terms=list(terms), items=items)


def build_dictionary(db: Session, user: User) -> list[DictionaryEntry]:
    cards = db.scalars(
        select(Card)
        .join(CardProgress, CardProgress.card_id == Card.id)
        .where(CardProgress.user_id == user.id, Card.verified.is_(True))
        .order_by(Card.term)
    ).all()
    return [DictionaryEntry.model_validate(card, from_attributes=True) for card in cards]


def streaks(active_days: set[date], today: date) -> tuple[int, int]:
    best = run = 0
    previous = None
    for day in sorted(active_days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day

    cursor = today if today in active_days else today - timedelta(days=1)
    current = 0
    while cursor in active_days:
        current += 1
        cursor -= timedelta(days=1)
    return current, best


def _accuracy(correct: int, answered: int) -> float | None:
    return round(correct / answered, 3) if answered else None


def build_stats(db: Session, user: User, today: date, days: int) -> StatsOut:
    correct_flag = case((ReviewHistory.is_correct.is_(True), 1), else_=0)
    graded = db.execute(
        select(ReviewHistory.answered_on, func.count(), func.sum(correct_flag))
        .where(
            ReviewHistory.user_id == user.id,
            ReviewHistory.is_retry.is_(False),
            ReviewHistory.is_practice.is_(False),
        )
        .group_by(ReviewHistory.answered_on)
    ).all()
    practice_per_day = dict(
        db.execute(
            select(ReviewHistory.answered_on, func.count())
            .where(ReviewHistory.user_id == user.id, ReviewHistory.is_practice.is_(True))
            .group_by(ReviewHistory.answered_on)
        ).all()
    )
    per_day = {day: (answered, correct) for day, answered, correct in graded}
    active_days = set(
        db.scalars(select(ReviewHistory.answered_on).where(ReviewHistory.user_id == user.id).distinct())
    )

    window = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    day_stats = [
        DayStat(
            date=day,
            answered=per_day.get(day, (0, 0))[0],
            correct=per_day.get(day, (0, 0))[1],
            accuracy=_accuracy(per_day.get(day, (0, 0))[1], per_day.get(day, (0, 0))[0]),
            practice=practice_per_day.get(day, 0),
        )
        for day in window
    ]

    by_type = dict(
        db.execute(
            select(ReviewHistory.error_type, func.count())
            .where(
                ReviewHistory.user_id == user.id,
                ReviewHistory.is_correct.is_(False),
                ReviewHistory.is_retry.is_(False),
                ReviewHistory.is_practice.is_(False),
            )
            .group_by(ReviewHistory.error_type)
        ).all()
    )
    errors = sum(by_type.values())
    total_answered = sum(a for a, _ in per_day.values())
    total_correct = sum(c for _, c in per_day.values())
    current, best = streaks(active_days, today)

    return StatsOut(
        days=day_stats,
        error_types=[
            StudentErrorStat(
                error_type=t, count=by_type.get(t.value, 0),
                share=round(by_type.get(t.value, 0) / errors, 3) if errors else 0.0,
            )
            for t in ErrorType
        ],
        streak=StreakStat(current=current, best=best),
        totals=TotalsStat(answered=total_answered, correct=total_correct, accuracy=_accuracy(total_correct, total_answered)),
    )
