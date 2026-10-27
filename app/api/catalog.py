from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db import get_db
from app.models import Domain
from app.schemas.catalog import DomainOut

router = APIRouter(tags=["catalog"], dependencies=[Depends(current_user)])


@router.get("/domains", response_model=list[DomainOut])
async def list_domains(db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Domain).order_by(func.lower(Domain.name), Domain.name))).all()
