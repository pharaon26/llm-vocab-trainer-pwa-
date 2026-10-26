from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.student import ProgressOut
from app.services import student as student_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/progress", response_model=ProgressOut)
def progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return student_service.build_progress(db, user)
