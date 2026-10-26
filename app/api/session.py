import logging
from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.llm.base import LLMError, LLMProvider
from app.llm.factory import get_provider
from app.models import User
from app.schemas.session import AnswerIn, AnswerOut, NextOut
from app.services import session as session_service
from app.services.classification import ClassifierUnavailable

router = APIRouter(prefix="/session", tags=["session"])


logger = logging.getLogger(__name__)


def get_today() -> date:
    return date.today()


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    try:
        return get_provider()
    except LLMError as exc:
        logger.error("LLM provider is not available, using algorithmic tasks only: %s", exc)
        return None


@router.get("/next", response_model=NextOut)
def next_task(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    task, remaining = session_service.next_task(db, user, today, provider)
    return NextOut(task=task, remaining=remaining)


@router.post("/answer", response_model=AnswerOut)
def answer(
    data: AnswerIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    try:
        return session_service.submit_answer(
            db, user, data.card_id, data.task_type, data.answer, today,
            task_id=data.task_id, provider=provider, context=data.context,
        )
    except session_service.CardNotInSession:
        raise HTTPException(409, "Card is not in today's session")
    except ClassifierUnavailable:
        raise HTTPException(
            503,
            "The answer could not be checked and was not recorded. Submit it again in a moment.",
            headers={"Retry-After": "5"},
        )
    except session_service.TaskUnavailable:
        raise HTTPException(422, "Task type is not available for this card")
