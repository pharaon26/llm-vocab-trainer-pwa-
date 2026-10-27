import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, engine
from app.models import Card, Deck
from app.schemas.card import CardCreate
from app.services.cards import add_to_deck, card_values, ensure_default_deck, get_or_create_domain

CARDS_FILE = Path(__file__).resolve().parent.parent / "data" / "cards.json"
DECKS_DIR = Path(__file__).resolve().parent.parent / "data" / "decks"


async def load_cards(db: AsyncSession, path: Path = CARDS_FILE) -> tuple[int, int]:
    added = skipped = 0
    deck = await ensure_default_deck(db)
    for raw in json.loads(path.read_text(encoding="utf-8")):
        data = CardCreate(**raw)
        card = await db.scalar(select(Card).where(Card.term == data.term, Card.owner_id.is_(None)))
        if card is not None:
            await add_to_deck(db, deck, card)
            skipped += 1
            continue
        card = Card(**await card_values(db, data.model_dump()), verified=False)
        db.add(card)
        await db.flush()
        await add_to_deck(db, deck, card)
        added += 1
    await db.commit()
    return added, skipped


async def load_decks(db: AsyncSession, directory: Path = DECKS_DIR) -> dict[str, tuple[int, int]]:
    """Наборы из data/decks/*.json: каждый файл - один общий набор. Новые карточки не проверены (verified=false)."""
    report = {}
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        info = raw["deck"]
        deck = await db.scalar(select(Deck).where(func.lower(Deck.name) == info["name"].lower(), Deck.owner_id.is_(None)))
        if deck is None:
            deck = Deck(
                name=info["name"], description=info["description"], is_default=False,
                domain_ref=await get_or_create_domain(db, info["domain"]),
            )
            db.add(deck)
            await db.flush()
        added = skipped = 0
        for item in raw["cards"]:
            data = CardCreate(**item)
            card = await db.scalar(select(Card).where(func.lower(Card.term) == data.term.lower(), Card.owner_id.is_(None)))
            if card is None:
                card = Card(**await card_values(db, data.model_dump()), verified=False)
                db.add(card)
                await db.flush()
                added += 1
            else:
                skipped += 1
            await add_to_deck(db, deck, card)
        report[deck.name] = (added, skipped)
    await db.commit()
    return report


async def update_cards(db: AsyncSession, path: Path = CARDS_FILE) -> int:
    updated = 0
    for raw in json.loads(path.read_text(encoding="utf-8")):
        data = CardCreate(**raw).model_dump()
        card = await db.scalar(select(Card).where(Card.term == data["term"], Card.owner_id.is_(None)))
        if card is None or all(getattr(card, field) == value for field, value in data.items()):
            continue
        for field, value in (await card_values(db, data)).items():
            setattr(card, field, value)
        card.verified = False
        updated += 1
    await db.commit()
    return updated


async def main(update: bool, decks: bool) -> None:
    async with SessionLocal() as db:
        added, skipped = await load_cards(db)
        print(f"Добавлено: {added}, пропущено (уже есть): {skipped}")
        if update:
            print(f"Обновлено карточек (verified сброшен): {await update_cards(db)}")
        if decks:
            for name, (new, old) in (await load_decks(db)).items():
                print(f"Набор «{name}»: добавлено {new}, уже было {old} (карточки не проверены)")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="обновить уже загруженные карточки из файла")
    parser.add_argument("--decks", action="store_true", help="загрузить тематические наборы из data/decks (карточки не проверены)")
    args = parser.parse_args()
    asyncio.run(main(args.update, args.decks))
