from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, Deck, DeckCard, User, UserDeck


def usable(user: User):
    shared = and_(Card.owner_id.is_(None), Card.verified.is_(True))
    personal = and_(Card.owner_id == user.id, Card.confirmed_by_owner.is_(True))
    return or_(shared, personal)


async def selected_deck_ids(db: AsyncSession, user: User) -> list[int]:
    if user.decks_customized:
        return list(await db.scalars(select(UserDeck.deck_id).where(UserDeck.user_id == user.id)))
    return list(await db.scalars(select(Deck.id).where(Deck.is_default.is_(True))))


async def in_selected_decks(db: AsyncSession, user: User):
    deck_ids = await selected_deck_ids(db, user)
    return Card.id.in_(select(DeckCard.card_id).where(DeckCard.deck_id.in_(deck_ids)))


async def new_term_pool(db: AsyncSession, user: User):
    return or_(await in_selected_decks(db, user), Card.owner_id == user.id)
