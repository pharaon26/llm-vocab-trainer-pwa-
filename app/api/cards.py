from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_teacher
from app.db import get_db
from app.models import Card, CardProgress, DeckCard, ReviewHistory, TaskBank
from app.schemas.card import CardCreate, CardRead
from app.services.cards import card_values

router = APIRouter(prefix="/cards", tags=["cards"])


async def get_card_or_404(card_id: int, db: AsyncSession) -> Card:
    card = await db.get(Card, card_id)
    if card is None or card.owner_id is not None:
        raise HTTPException(404, "Card not found")
    return card


async def ensure_term_free(db: AsyncSession, term: str, exclude_id: int | None = None) -> None:
    existing = await db.scalar(select(Card).where(func.lower(Card.term) == term.lower(), Card.owner_id.is_(None)))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "Card with this term already exists")


@router.post("", response_model=CardRead, status_code=201, dependencies=[Depends(require_teacher)])
async def create_card(data: CardCreate, db: AsyncSession = Depends(get_db)):
    await ensure_term_free(db, data.term)
    card = Card(**await card_values(db, data.model_dump()), verified=False)
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.get("", response_model=list[CardRead], dependencies=[Depends(require_teacher)])
async def list_cards(verified: bool | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Card).where(Card.owner_id.is_(None)).order_by(func.lower(Card.term), Card.term)
    if verified is not None:
        query = query.where(Card.verified == verified)
    return (await db.scalars(query)).all()


@router.get("/{card_id}", response_model=CardRead, dependencies=[Depends(require_teacher)])
async def read_card(card_id: int, db: AsyncSession = Depends(get_db)):
    return await get_card_or_404(card_id, db)


@router.put("/{card_id}", response_model=CardRead, dependencies=[Depends(require_teacher)])
async def update_card(card_id: int, data: CardCreate, db: AsyncSession = Depends(get_db)):
    card = await get_card_or_404(card_id, db)
    await ensure_term_free(db, data.term, exclude_id=card_id)
    for field, value in (await card_values(db, data.model_dump())).items():
        setattr(card, field, value)
    card.verified = False
    await db.commit()
    await db.refresh(card)
    return card


@router.patch("/{card_id}/verify", response_model=CardRead, dependencies=[Depends(require_teacher)])
async def verify_card(card_id: int, db: AsyncSession = Depends(get_db)):
    card = await get_card_or_404(card_id, db)
    card.verified = True
    await db.commit()
    await db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=204, dependencies=[Depends(require_teacher)])
async def delete_card(card_id: int, db: AsyncSession = Depends(get_db)):
    card = await get_card_or_404(card_id, db)
    await db.execute(delete(ReviewHistory).where(ReviewHistory.card_id == card_id))
    await db.execute(delete(CardProgress).where(CardProgress.card_id == card_id))
    await db.execute(delete(TaskBank).where(TaskBank.card_id == card_id))
    await db.execute(delete(DeckCard).where(DeckCard.card_id == card_id))
    await db.delete(card)
    await db.commit()
