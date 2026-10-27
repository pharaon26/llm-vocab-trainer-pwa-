from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, Deck, DeckCard, GroupDeck, TeacherStudent, User, UserDeck


def assigned_decks(user: User):
    """Наборы преподавателей, назначенные группам, в которых состоит студент (связь принята и действует)."""
    return (
        select(Deck.id)
        .join(GroupDeck, GroupDeck.deck_id == Deck.id)
        .join(TeacherStudent, TeacherStudent.group_id == GroupDeck.group_id)
        .where(TeacherStudent.student_id == user.id, Deck.owner_id == TeacherStudent.teacher_id)
    )


def assigned_cards(user: User):
    return select(DeckCard.card_id).where(DeckCard.deck_id.in_(assigned_decks(user)))


def usable(user: User):
    shared = and_(Card.owner_id.is_(None), Card.verified.is_(True))
    personal = and_(Card.owner_id == user.id, Card.confirmed_by_owner.is_(True))
    from_teacher = and_(Card.owner_id.is_not(None), Card.verified.is_(True), Card.id.in_(assigned_cards(user)))
    return or_(shared, personal, from_teacher)


async def selected_deck_ids(db: AsyncSession, user: User) -> list[int]:
    if user.decks_customized:
        return list(await db.scalars(select(UserDeck.deck_id).where(UserDeck.user_id == user.id)))
    return list(await db.scalars(select(Deck.id).where(Deck.is_default.is_(True), Deck.owner_id.is_(None))))


async def in_selected_decks(db: AsyncSession, user: User):
    deck_ids = await selected_deck_ids(db, user)
    chosen = select(DeckCard.card_id).where(DeckCard.deck_id.in_(deck_ids))
    return or_(Card.id.in_(chosen), Card.id.in_(assigned_cards(user)))


async def new_term_pool(db: AsyncSession, user: User):
    return or_(await in_selected_decks(db, user), Card.owner_id == user.id)
