from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import TaskType
from app.models import Card, TaskBank
from app.schemas.generation import GeneratedTask


def _scope(card_id: int, task_type: TaskType, source: str | None):
    query = select(TaskBank).where(TaskBank.card_id == card_id, TaskBank.task_type == task_type.value)
    if source is None:
        return query.where(TaskBank.source != "fake")
    return query.where(TaskBank.source == source)


def count(db: Session, card_id: int, task_type: TaskType, source: str | None) -> int:
    subquery = _scope(card_id, task_type, source).subquery()
    return db.scalar(select(func.count()).select_from(subquery))


def pick(db: Session, card_id: int, task_type: TaskType, source: str | None) -> TaskBank | None:
    query = _scope(card_id, task_type, source).order_by(TaskBank.times_used, TaskBank.id).limit(1)
    return db.scalar(query)


def get_or_create(
    db: Session, card: Card, task_type: TaskType, task: GeneratedTask, source: str
) -> TaskBank:
    existing = db.scalar(
        _scope(card.id, task_type, source).where(
            TaskBank.prompt == task.prompt, TaskBank.correct_answer == task.correct_answer
        )
    )
    if existing:
        return existing
    entry = TaskBank(
        card_id=card.id, task_type=task_type.value, source=source, prompt=task.prompt,
        options=task.options, correct_answer=task.correct_answer,
    )
    db.add(entry)
    db.commit()
    return entry
