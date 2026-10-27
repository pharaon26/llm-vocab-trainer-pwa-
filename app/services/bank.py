from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TaskType
from app.models import Card, TaskBank
from app.schemas.generation import GeneratedTask


def _scope(card_id: int, task_type: TaskType, source: str | None):
    query = select(TaskBank).where(
        TaskBank.card_id == card_id, TaskBank.task_type == task_type.value, TaskBank.rejected.is_(False)
    )
    if source is None:
        return query.where(TaskBank.source != "fake")
    return query.where(TaskBank.source == source)


async def count(db: AsyncSession, card_id: int, task_type: TaskType, source: str | None) -> int:
    subquery = _scope(card_id, task_type, source).subquery()
    return await db.scalar(select(func.count()).select_from(subquery))


async def pick(db: AsyncSession, card_id: int, task_type: TaskType, source: str | None) -> TaskBank | None:
    query = _scope(card_id, task_type, source).order_by(TaskBank.times_used, TaskBank.id).limit(1)
    return await db.scalar(query)


async def get_or_create(
    db: AsyncSession, card: Card, task_type: TaskType, task: GeneratedTask, source: str
) -> TaskBank | None:
    existing = await db.scalar(
        select(TaskBank).where(
            TaskBank.card_id == card.id,
            TaskBank.task_type == task_type.value,
            TaskBank.source == source,
            TaskBank.prompt == task.prompt,
            TaskBank.correct_answer == task.correct_answer,
        )
    )
    if existing:
        return None if existing.rejected else existing
    entry = TaskBank(
        card_id=card.id, task_type=task_type.value, source=source, prompt=task.prompt,
        options=task.options, correct_answer=task.correct_answer,
    )
    db.add(entry)
    await db.commit()
    return entry
