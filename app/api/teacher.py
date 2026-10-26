from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db import get_db
from app.enums import TaskType
from app.models import Card, Deck, Domain, TaskBank
from app.schemas.catalog import DeckCardsIn, DeckIn, DomainIn, DomainOut, TeacherDeckOut
from app.schemas.teacher import AnalyticsOut, BankEntryOut, BankPatch
from app.services import decks as decks_service
from app.services.cards import get_or_create_domain
from app.services.analytics import build_analytics

router = APIRouter(prefix="/teacher", tags=["teacher"], dependencies=[Depends(require_teacher)])


def bank_out(entry: TaskBank, term: str) -> BankEntryOut:
    return BankEntryOut(
        id=entry.id, card_id=entry.card_id, term=term, task_type=TaskType(entry.task_type),
        source=entry.source, prompt=entry.prompt, options=entry.options,
        correct_answer=entry.correct_answer, times_used=entry.times_used,
        rejected=entry.rejected, created_at=entry.created_at,
    )


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    min_answers: int = Query(3, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return build_analytics(db, min_answers, limit)


@router.get("/bank", response_model=list[BankEntryOut])
def list_bank(
    card_id: int | None = None,
    task_type: TaskType | None = None,
    rejected: bool | None = None,
    db: Session = Depends(get_db),
):
    query = select(TaskBank, Card.term).join(Card, Card.id == TaskBank.card_id)
    if card_id is not None:
        query = query.where(TaskBank.card_id == card_id)
    if task_type is not None:
        query = query.where(TaskBank.task_type == task_type.value)
    if rejected is not None:
        query = query.where(TaskBank.rejected.is_(rejected))
    rows = db.execute(query.order_by(Card.term, TaskBank.id)).all()
    return [bank_out(entry, term) for entry, term in rows]


@router.patch("/bank/{entry_id}", response_model=BankEntryOut)
def update_bank_entry(entry_id: int, data: BankPatch, db: Session = Depends(get_db)):
    entry = db.get(TaskBank, entry_id)
    if entry is None:
        raise HTTPException(404, "Bank entry not found")
    entry.rejected = data.rejected
    db.commit()
    return bank_out(entry, db.get(Card, entry.card_id).term)


@router.post("/domains", response_model=DomainOut, status_code=201)
def create_domain(data: DomainIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Domain).where(func.lower(Domain.name) == data.name.lower()))
    if existing:
        raise HTTPException(409, "Domain already exists")
    domain = get_or_create_domain(db, data.name)
    db.commit()
    return domain


def get_deck_or_404(db: Session, deck_id: int) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(404, "Deck not found")
    return deck


def ensure_deck_name_free(db: Session, name: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Deck).where(func.lower(Deck.name) == name.lower()))
    if existing and existing.id != exclude_id:
        raise HTTPException(409, "Deck with this name already exists")


@router.get("/decks", response_model=list[TeacherDeckOut])
def list_decks(db: Session = Depends(get_db)):
    return [decks_service.teacher_deck(db, deck) for deck in db.scalars(select(Deck).order_by(Deck.name))]


@router.post("/decks", response_model=TeacherDeckOut, status_code=201)
def create_deck(data: DeckIn, db: Session = Depends(get_db)):
    ensure_deck_name_free(db, data.name)
    deck = Deck()
    decks_service.apply_deck(db, deck, data.name, data.description, data.domain, data.is_default)
    db.add(deck)
    db.commit()
    return decks_service.teacher_deck(db, deck)


@router.put("/decks/{deck_id}", response_model=TeacherDeckOut)
def update_deck(deck_id: int, data: DeckIn, db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id)
    ensure_deck_name_free(db, data.name, exclude_id=deck_id)
    decks_service.apply_deck(db, deck, data.name, data.description, data.domain, data.is_default)
    db.commit()
    return decks_service.teacher_deck(db, deck)


@router.put("/decks/{deck_id}/cards", response_model=TeacherDeckOut)
def set_cards(deck_id: int, data: DeckCardsIn, db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id)
    try:
        decks_service.set_deck_cards(db, deck, data.card_ids)
    except decks_service.UnknownDecks:
        raise HTTPException(422, "Unknown card id")
    return decks_service.teacher_deck(db, deck)


@router.delete("/decks/{deck_id}", status_code=204)
def delete_deck(deck_id: int, db: Session = Depends(get_db)):
    decks_service.delete_deck(db, get_deck_or_404(db, deck_id))
