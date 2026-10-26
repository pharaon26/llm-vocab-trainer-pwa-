from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db import get_db
from app.models import Card, CardProgress, ReviewHistory, TaskBank
from app.schemas.card import CardCreate, CardRead

router = APIRouter(prefix="/cards", tags=["cards"])


def get_card_or_404(card_id: int, db: Session) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(404, "Card not found")
    return card


def ensure_term_free(db: Session, term: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Card).where(Card.term == term))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "Card with this term already exists")


@router.post("", response_model=CardRead, status_code=201, dependencies=[Depends(require_teacher)])
def create_card(data: CardCreate, db: Session = Depends(get_db)):
    ensure_term_free(db, data.term)
    card = Card(**data.model_dump(), verified=False)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.get("", response_model=list[CardRead])
def list_cards(verified: bool | None = None, db: Session = Depends(get_db)):
    query = select(Card).order_by(Card.term)
    if verified is not None:
        query = query.where(Card.verified == verified)
    return db.scalars(query).all()


@router.get("/{card_id}", response_model=CardRead)
def read_card(card_id: int, db: Session = Depends(get_db)):
    return get_card_or_404(card_id, db)


@router.put("/{card_id}", response_model=CardRead, dependencies=[Depends(require_teacher)])
def update_card(card_id: int, data: CardCreate, db: Session = Depends(get_db)):
    card = get_card_or_404(card_id, db)
    ensure_term_free(db, data.term, exclude_id=card_id)
    for field, value in data.model_dump().items():
        setattr(card, field, value)
    card.verified = False
    db.commit()
    db.refresh(card)
    return card


@router.patch("/{card_id}/verify", response_model=CardRead, dependencies=[Depends(require_teacher)])
def verify_card(card_id: int, db: Session = Depends(get_db)):
    card = get_card_or_404(card_id, db)
    card.verified = True
    db.commit()
    db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=204, dependencies=[Depends(require_teacher)])
def delete_card(card_id: int, db: Session = Depends(get_db)):
    card = get_card_or_404(card_id, db)
    db.execute(delete(ReviewHistory).where(ReviewHistory.card_id == card_id))
    db.execute(delete(CardProgress).where(CardProgress.card_id == card_id))
    db.execute(delete(TaskBank).where(TaskBank.card_id == card_id))
    db.delete(card)
    db.commit()
