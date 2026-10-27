from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, Deck, DeckCard, GroupDeck, TeacherGroup, User, UserDeck
from app.schemas.catalog import DeckOut, TeacherDeckOut
from app.services.cards import get_or_create_domain
from app.services.visibility import assigned_decks, selected_deck_ids


class UnknownDecks(Exception):
    pass


async def _counts(db: AsyncSession) -> tuple[dict[int, int], dict[int, int]]:
    total = dict((await db.execute(select(DeckCard.deck_id, func.count()).group_by(DeckCard.deck_id))).all())
    verified = dict(
        (
            await db.execute(
                select(DeckCard.deck_id, func.count())
                .join(Card, Card.id == DeckCard.card_id)
                .where(Card.verified.is_(True))
                .group_by(DeckCard.deck_id)
            )
        ).all()
    )
    return total, verified


async def list_decks(db: AsyncSession, user: User) -> list[DeckOut]:
    selected = set(await selected_deck_ids(db, user))
    _, verified = await _counts(db)
    assigned = {
        deck_id: teacher
        for deck_id, teacher in (
            await db.execute(select(Deck.id, User.name).join(User, User.id == Deck.owner_id).where(Deck.id.in_(assigned_decks(user))))
        ).all()
    }
    decks = (
        await db.scalars(
            select(Deck)
            .where(or_(Deck.owner_id.is_(None), Deck.id.in_(list(assigned))))
            .order_by(func.lower(Deck.name), Deck.name)
        )
    ).all()
    return [
        DeckOut(
            id=deck.id, name=deck.name, description=deck.description, domain=deck.domain,
            is_default=deck.is_default, cards=verified.get(deck.id, 0),
            selected=deck.id in selected or deck.id in assigned, teacher=assigned.get(deck.id), assigned=deck.id in assigned,
        )
        for deck in decks
    ]


async def select_decks(db: AsyncSession, user: User, deck_ids: list[int]) -> None:
    ids = set(deck_ids)
    shared = set(await db.scalars(select(Deck.id).where(Deck.id.in_(ids), Deck.owner_id.is_(None))))
    assigned = set(await db.scalars(select(Deck.id).where(Deck.id.in_(ids), Deck.id.in_(assigned_decks(user)))))
    if shared | assigned != ids:
        raise UnknownDecks
    ids = shared
    await db.execute(delete(UserDeck).where(UserDeck.user_id == user.id))
    for deck_id in sorted(ids):
        db.add(UserDeck(user_id=user.id, deck_id=deck_id))
    user.decks_customized = True
    await db.commit()


async def teacher_deck(db: AsyncSession, deck: Deck) -> TeacherDeckOut:
    total, verified = await _counts(db)
    card_ids = list(
        await db.scalars(select(DeckCard.card_id).where(DeckCard.deck_id == deck.id).order_by(DeckCard.card_id))
    )
    group_ids = list(await db.scalars(select(GroupDeck.group_id).where(GroupDeck.deck_id == deck.id).order_by(GroupDeck.group_id)))
    return TeacherDeckOut(
        group_ids=group_ids, id=deck.id, name=deck.name, description=deck.description, domain=deck.domain,
        is_default=deck.is_default, cards=verified.get(deck.id, 0), cards_total=total.get(deck.id, 0),
        card_ids=card_ids,
    )


async def apply_deck(db: AsyncSession, deck: Deck, name: str, description: str, domain: str, is_default: bool) -> None:
    deck.name = name
    deck.description = description
    deck.domain_ref = await get_or_create_domain(db, domain)
    deck.is_default = is_default


async def set_deck_cards(db: AsyncSession, deck: Deck, card_ids: list[int]) -> None:
    ids = set(card_ids)
    allowed = Card.owner_id.is_(None) if deck.owner_id is None else or_(Card.owner_id.is_(None), Card.owner_id == deck.owner_id)
    known = set(await db.scalars(select(Card.id).where(Card.id.in_(ids), allowed)))
    if known != ids:
        raise UnknownDecks
    await db.execute(delete(DeckCard).where(DeckCard.deck_id == deck.id))
    for card_id in sorted(ids):
        db.add(DeckCard(deck_id=deck.id, card_id=card_id))
    await db.commit()


class UnknownGroups(Exception):
    pass


async def set_deck_groups(db: AsyncSession, deck: Deck, group_ids: list[int]) -> None:
    ids = set(group_ids)
    known = set(
        await db.scalars(select(TeacherGroup.id).where(TeacherGroup.id.in_(ids), TeacherGroup.teacher_id == deck.owner_id))
    )
    if known != ids:
        raise UnknownGroups
    await db.execute(delete(GroupDeck).where(GroupDeck.deck_id == deck.id))
    for group_id in sorted(ids):
        db.add(GroupDeck(group_id=group_id, deck_id=deck.id))
    await db.commit()


async def delete_deck(db: AsyncSession, deck: Deck) -> None:
    await db.execute(delete(DeckCard).where(DeckCard.deck_id == deck.id))
    await db.execute(delete(UserDeck).where(UserDeck.deck_id == deck.id))
    await db.delete(deck)
    await db.commit()
