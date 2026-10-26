from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Card, Deck, DeckCard, User, UserDeck


def usable(user: User):
    shared = and_(Card.owner_id.is_(None), Card.verified.is_(True))
    personal = and_(Card.owner_id == user.id, Card.confirmed_by_owner.is_(True))
    return or_(shared, personal)


def selected_deck_ids(db: Session, user: User) -> list[int]:
    if user.decks_customized:
        return list(db.scalars(select(UserDeck.deck_id).where(UserDeck.user_id == user.id)))
    return list(db.scalars(select(Deck.id).where(Deck.is_default.is_(True))))


def in_selected_decks(db: Session, user: User):
    deck_ids = selected_deck_ids(db, user)
    return Card.id.in_(select(DeckCard.card_id).where(DeckCard.deck_id.in_(deck_ids)))


def new_term_pool(db: Session, user: User):
    return or_(in_selected_decks(db, user), Card.owner_id == user.id)
