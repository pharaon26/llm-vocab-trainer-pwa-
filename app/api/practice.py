from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_today
from app.api.session import get_llm_provider, submit_or_http
from app.db import get_db
from app.llm.base import LLMProvider
from app.models import User
from app.schemas.session import AnswerIn, AnswerOut, PracticeNextOut
from app.services.practice import SessionNotFinished, practice_next

router = APIRouter(prefix="/practice", tags=["practice"])


@router.get("/next", response_model=PracticeNextOut)
async def next_task(
    exclude: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    try:
        return PracticeNextOut(task=await practice_next(db, user, today, provider, exclude))
    except SessionNotFinished:
        raise HTTPException(409, "Finish today's session before free practice")


@router.post("/answer", response_model=AnswerOut)
async def answer(
    data: AnswerIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    today: date = Depends(get_today),
    provider: LLMProvider | None = Depends(get_llm_provider),
):
    return await submit_or_http(db, user, data, today, provider, practice=True)
