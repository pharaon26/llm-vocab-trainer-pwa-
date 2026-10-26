from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_today
from app.db import get_db
from app.models import User
from app.schemas.student import DictionaryEntry, HistoryOut, ProgressOut, StatsOut
from app.services import student as student_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/progress", response_model=ProgressOut)
def progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return student_service.build_progress(db, user)


@router.get("/history", response_model=HistoryOut)
def history(
    term: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return student_service.build_history(db, user, term, limit, offset)


@router.get("/dictionary", response_model=list[DictionaryEntry])
def dictionary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return student_service.build_dictionary(db, user)


@router.get("/stats", response_model=StatsOut)
def stats(
    days: int = Query(14, ge=7, le=60),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    return student_service.build_stats(db, user, today, days)
