from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db import get_db
from app.enums import TaskType
from app.models import Card, TaskBank
from app.schemas.teacher import AnalyticsOut, BankEntryOut, BankPatch
from app.services.analytics import build_analytics

router = APIRouter(prefix="/teacher", tags=["teacher"], dependencies=[Depends(require_teacher)])


def bank_out(entry: TaskBank, term: str) -> BankEntryOut:
    return BankEntryOut(
        id=entry.id, card_id=entry.card_id, term=term, task_type=TaskType(entry.task_type),
        source=entry.source, prompt=entry.prompt, options=entry.options,
        correct_answer=entry.correct_answer, times_used=entry.times_used,
        rejected=entry.rejected, created_at=entry.created_at,
    )


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    min_answers: int = Query(3, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return build_analytics(db, min_answers, limit)


@router.get("/bank", response_model=list[BankEntryOut])
def list_bank(
    card_id: int | None = None,
    task_type: TaskType | None = None,
    rejected: bool | None = None,
    db: Session = Depends(get_db),
):
    query = select(TaskBank, Card.term).join(Card, Card.id == TaskBank.card_id)
    if card_id is not None:
        query = query.where(TaskBank.card_id == card_id)
    if task_type is not None:
        query = query.where(TaskBank.task_type == task_type.value)
    if rejected is not None:
        query = query.where(TaskBank.rejected.is_(rejected))
    rows = db.execute(query.order_by(Card.term, TaskBank.id)).all()
    return [bank_out(entry, term) for entry, term in rows]


@router.patch("/bank/{entry_id}", response_model=BankEntryOut)
def update_bank_entry(entry_id: int, data: BankPatch, db: Session = Depends(get_db)):
    entry = db.get(TaskBank, entry_id)
    if entry is None:
        raise HTTPException(404, "Bank entry not found")
    entry.rejected = data.rejected
    db.commit()
    return bank_out(entry, db.get(Card, entry.card_id).term)
