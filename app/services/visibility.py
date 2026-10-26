from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Card, Deck, DeckCard, User, UserDeck


def usable(user: User):
    return Card.verified.is_(True)


def selected_deck_ids(db: Session, user: User) -> list[int]:
    if user.decks_customized:
        return list(db.scalars(select(UserDeck.deck_id).where(UserDeck.user_id == user.id)))
    return list(db.scalars(select(Deck.id).where(Deck.is_default.is_(True))))


def in_selected_decks(db: Session, user: User):
    deck_ids = selected_deck_ids(db, user)
    return Card.id.in_(select(DeckCard.card_id).where(DeckCard.deck_id.in_(deck_ids)))
