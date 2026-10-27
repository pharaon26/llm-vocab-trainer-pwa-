import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, engine
from app.models import Card
from app.schemas.card import CardCreate
from app.services.cards import add_to_deck, card_values, ensure_default_deck

CARDS_FILE = Path(__file__).resolve().parent.parent / "data" / "cards.json"


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


async def main(update: bool) -> None:
    async with SessionLocal() as db:
        added, skipped = await load_cards(db)
        print(f"Добавлено: {added}, пропущено (уже есть): {skipped}")
        if update:
            print(f"Обновлено карточек (verified сброшен): {await update_cards(db)}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="обновить уже загруженные карточки из файла")
    asyncio.run(main(parser.parse_args().update))
