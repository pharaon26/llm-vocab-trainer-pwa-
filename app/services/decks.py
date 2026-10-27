from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Card, Deck, DeckCard, User, UserDeck
from app.schemas.catalog import DeckOut, TeacherDeckOut
from app.services.cards import get_or_create_domain
from app.services.visibility import selected_deck_ids


class UnknownDecks(Exception):
    pass


def _counts(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    total = dict(db.execute(select(DeckCard.deck_id, func.count()).group_by(DeckCard.deck_id)).all())
    verified = dict(
        db.execute(
            select(DeckCard.deck_id, func.count())
            .join(Card, Card.id == DeckCard.card_id)
            .where(Card.verified.is_(True))
            .group_by(DeckCard.deck_id)
        ).all()
    )
    return total, verified


def list_decks(db: Session, user: User) -> list[DeckOut]:
    selected = set(selected_deck_ids(db, user))
    _, verified = _counts(db)
    decks = db.scalars(select(Deck).order_by(func.lower(Deck.name), Deck.name)).all()
    return [
        DeckOut(
            id=deck.id, name=deck.name, description=deck.description, domain=deck.domain,
            is_default=deck.is_default, cards=verified.get(deck.id, 0), selected=deck.id in selected,
        )
        for deck in decks
    ]


def select_decks(db: Session, user: User, deck_ids: list[int]) -> None:
    ids = set(deck_ids)
    known = set(db.scalars(select(Deck.id).where(Deck.id.in_(ids))))
    if known != ids:
        raise UnknownDecks
    db.execute(delete(UserDeck).where(UserDeck.user_id == user.id))
    for deck_id in sorted(ids):
        db.add(UserDeck(user_id=user.id, deck_id=deck_id))
    user.decks_customized = True
    db.commit()


def teacher_deck(db: Session, deck: Deck) -> TeacherDeckOut:
    total, verified = _counts(db)
    card_ids = list(db.scalars(select(DeckCard.card_id).where(DeckCard.deck_id == deck.id).order_by(DeckCard.card_id)))
    return TeacherDeckOut(
        id=deck.id, name=deck.name, description=deck.description, domain=deck.domain,
        is_default=deck.is_default, cards=verified.get(deck.id, 0), cards_total=total.get(deck.id, 0),
        card_ids=card_ids,
    )


def apply_deck(db: Session, deck: Deck, name: str, description: str, domain: str, is_default: bool) -> None:
    deck.name = name
    deck.description = description
    deck.domain_id = get_or_create_domain(db, domain).id
    deck.is_default = is_default


def set_deck_cards(db: Session, deck: Deck, card_ids: list[int]) -> None:
    ids = set(card_ids)
    known = set(db.scalars(select(Card.id).where(Card.id.in_(ids), Card.owner_id.is_(None))))
    if known != ids:
        raise UnknownDecks
    db.execute(delete(DeckCard).where(DeckCard.deck_id == deck.id))
    for card_id in sorted(ids):
        db.add(DeckCard(deck_id=deck.id, card_id=card_id))
    db.commit()


def delete_deck(db: Session, deck: Deck) -> None:
    db.execute(delete(DeckCard).where(DeckCard.deck_id == deck.id))
    db.execute(delete(UserDeck).where(UserDeck.deck_id == deck.id))
    db.delete(deck)
    db.commit()
