from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.session import AnswerIn, AnswerOut, NextOut
from app.services import session as session_service

router = APIRouter(prefix="/session", tags=["session"])


def get_today() -> date:
    return date.today()


@router.get("/next", response_model=NextOut)
def next_task(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    task, remaining = session_service.next_task(db, user, today)
    return NextOut(task=task, remaining=remaining)


@router.post("/answer", response_model=AnswerOut)
def answer(
    data: AnswerIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    try:
        return session_service.submit_answer(db, user, data.card_id, data.task_type, data.answer, today)
    except session_service.CardNotInSession:
        raise HTTPException(409, "Card is not in today's session")
    except session_service.TaskUnavailable:
        raise HTTPException(422, "Task type is not available for this card")
