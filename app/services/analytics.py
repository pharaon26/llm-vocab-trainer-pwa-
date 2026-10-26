from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.enums import ErrorType, Role
from app.models import Card, ReviewHistory, User
from app.schemas.teacher import AnalyticsOut, ErrorTypeStat, SourceStat, TermStat


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def build_analytics(db: Session, min_answers: int = 3, limit: int = 10) -> AnalyticsOut:
    scope = (
        User.role == Role.STUDENT.value,
        ReviewHistory.is_retry.is_(False),
    )
    wrong = case((ReviewHistory.is_correct.is_(False), 1), else_=0)

    students, answers, errors = db.execute(
        select(func.count(func.distinct(ReviewHistory.user_id)), func.count(), func.coalesce(func.sum(wrong), 0))
        .join(User, User.id == ReviewHistory.user_id)
        .where(*scope)
    ).one()

    per_card = db.execute(
        select(Card.term, func.count(), func.sum(wrong))
        .join(Card, Card.id == ReviewHistory.card_id)
        .join(User, User.id == ReviewHistory.user_id)
        .where(*scope)
        .group_by(Card.id, Card.term)
    ).all()
    terms = [
        TermStat(term=term, attempts=attempts, errors=card_errors, error_rate=_ratio(card_errors, attempts))
        for term, attempts, card_errors in per_card
        if attempts >= min_answers and card_errors > 0
    ]
    terms.sort(key=lambda t: (-t.error_rate, -t.attempts, t.term))

    by_type = dict(
        db.execute(
            select(ReviewHistory.error_type, func.count())
            .join(User, User.id == ReviewHistory.user_id)
            .where(*scope, ReviewHistory.is_correct.is_(False))
            .group_by(ReviewHistory.error_type)
        ).all()
    )
    by_source = db.execute(
        select(ReviewHistory.classified_by, func.count())
        .join(User, User.id == ReviewHistory.user_id)
        .where(*scope)
        .group_by(ReviewHistory.classified_by)
        .order_by(ReviewHistory.classified_by)
    ).all()

    return AnalyticsOut(
        students=students,
        answers=answers,
        errors=errors,
        error_rate=_ratio(errors, answers),
        min_answers=min_answers,
        error_types=[
            ErrorTypeStat(error_type=t, count=by_type.get(t.value, 0), share=_ratio(by_type.get(t.value, 0), errors))
            for t in ErrorType
        ],
        hardest_terms=terms[:limit],
        classified_by=[SourceStat(classified_by=source, count=count) for source, count in by_source],
    )
