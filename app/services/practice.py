import random
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TaskType
from app.llm.base import LLMProvider
from app.models import Card, CardProgress, User
from app.schemas.session import TaskOut
from app.services.session import build_queue
from app.services.student import error_counts
from app.services.task_source import get_task
from app.services.tasks import OPEN_TYPES
from app.services.visibility import usable

CLOSED_TYPES = [t for t in TaskType if t not in OPEN_TYPES]


class SessionNotFinished(Exception):
    pass


def practice_next(
    db: Session,
    user: User,
    today: date,
    provider: LLMProvider | None,
    exclude: int | None = None,
    rng: random.Random | None = None,
) -> TaskOut | None:
    rng = rng or random.Random()
    if build_queue(db, user, today):
        raise SessionNotFinished

    opened = db.scalars(
        select(Card)
        .join(CardProgress, CardProgress.card_id == Card.id)
        .where(CardProgress.user_id == user.id, usable(user))
    ).all()
    if not opened:
        return None

    errors = error_counts(db, user)
    candidates = [card for card in opened if card.id != exclude] or opened
    weights = [1 + sum(errors.get(card.id, {}).values()) for card in candidates]
    card = rng.choices(candidates, weights)[0]

    task_type = rng.choice(list(TaskType) if provider is not None else CLOSED_TYPES)
    others = list(db.scalars(select(Card).where(Card.id != card.id, usable(user))))
    return get_task(db, provider, card, task_type, others, rng)
