from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, Deck, DeckCard, Domain

DEFAULT_DOMAINS = ["IT", "Information security", "Medicine", "Law", "Economics", "Engineering"]
DEFAULT_DECK_NAME = "IT & Security basics"
DEFAULT_DECK_DESCRIPTION = "Базовая лексика по ИТ и информационной безопасности"


async def get_or_create_domain(db: AsyncSession, name: str) -> Domain:
    name = name.strip()
    domain = await db.scalar(select(Domain).where(func.lower(Domain.name) == name.lower()))
    if domain is None:
        domain = Domain(name=name)
        db.add(domain)
        await db.flush()
    return domain


async def ensure_default_domains(db: AsyncSession) -> None:
    for name in DEFAULT_DOMAINS:
        await get_or_create_domain(db, name)
    await db.flush()


async def card_values(db: AsyncSession, data: dict) -> dict:
    values = dict(data)
    values["domain_ref"] = await get_or_create_domain(db, values.pop("domain"))
    return values


async def ensure_default_deck(db: AsyncSession) -> Deck:
    deck = await db.scalar(select(Deck).where(Deck.name == DEFAULT_DECK_NAME))
    if deck is None:
        await ensure_default_domains(db)
        deck = Deck(
            name=DEFAULT_DECK_NAME,
            description=DEFAULT_DECK_DESCRIPTION,
            domain_ref=await get_or_create_domain(db, "IT"),
            is_default=True,
        )
        db.add(deck)
        await db.flush()
    return deck


async def add_to_deck(db: AsyncSession, deck: Deck, card: Card) -> None:
    if await db.get(DeckCard, (deck.id, card.id)) is None:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id))
