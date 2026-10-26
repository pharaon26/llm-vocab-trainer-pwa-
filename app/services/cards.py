from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Card, Deck, DeckCard, Domain

DEFAULT_DOMAINS = ["IT", "Information security", "Medicine", "Law", "Economics", "Engineering"]
DEFAULT_DECK_NAME = "IT & Security basics"
DEFAULT_DECK_DESCRIPTION = "Базовая лексика по ИТ и информационной безопасности"


def get_or_create_domain(db: Session, name: str) -> Domain:
    name = name.strip()
    domain = db.scalar(select(Domain).where(func.lower(Domain.name) == name.lower()))
    if domain is None:
        domain = Domain(name=name)
        db.add(domain)
        db.flush()
    return domain


def ensure_default_domains(db: Session) -> None:
    for name in DEFAULT_DOMAINS:
        get_or_create_domain(db, name)
    db.flush()


def card_values(db: Session, data: dict) -> dict:
    values = dict(data)
    values["domain_id"] = get_or_create_domain(db, values.pop("domain")).id
    return values


def ensure_default_deck(db: Session) -> Deck:
    deck = db.scalar(select(Deck).where(Deck.name == DEFAULT_DECK_NAME))
    if deck is None:
        ensure_default_domains(db)
        deck = Deck(
            name=DEFAULT_DECK_NAME,
            description=DEFAULT_DECK_DESCRIPTION,
            domain_id=get_or_create_domain(db, "IT").id,
            is_default=True,
        )
        db.add(deck)
        db.flush()
    return deck


def add_to_deck(db: Session, deck: Deck, card: Card) -> None:
    if db.get(DeckCard, (deck.id, card.id)) is None:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id))
