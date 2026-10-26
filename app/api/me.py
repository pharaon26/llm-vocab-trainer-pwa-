from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.student import HistoryOut, ProgressOut
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
