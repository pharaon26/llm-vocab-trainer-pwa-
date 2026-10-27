from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Domain
from app.schemas.catalog import DomainOut

router = APIRouter(tags=["catalog"], dependencies=[Depends(current_user)])


@router.get("/domains", response_model=list[DomainOut])
def list_domains(db: Session = Depends(get_db)):
    return db.scalars(select(Domain).order_by(func.lower(Domain.name), Domain.name)).all()
