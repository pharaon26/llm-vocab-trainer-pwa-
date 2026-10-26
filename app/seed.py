import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Card
from app.schemas.card import CardCreate
from app.services.cards import add_to_deck, card_values, ensure_default_deck

CARDS_FILE = Path(__file__).resolve().parent.parent / "data" / "cards.json"


def load_cards(db: Session, path: Path = CARDS_FILE) -> tuple[int, int]:
    added = skipped = 0
    deck = ensure_default_deck(db)
    for raw in json.loads(path.read_text(encoding="utf-8")):
        data = CardCreate(**raw)
        card = db.scalar(select(Card).where(Card.term == data.term, Card.owner_id.is_(None)))
        if card is not None:
            add_to_deck(db, deck, card)
            skipped += 1
            continue
        card = Card(**card_values(db, data.model_dump()), verified=False)
        db.add(card)
        db.flush()
        add_to_deck(db, deck, card)
        added += 1
    db.commit()
    return added, skipped


def update_cards(db: Session, path: Path = CARDS_FILE) -> int:
    updated = 0
    for raw in json.loads(path.read_text(encoding="utf-8")):
        data = CardCreate(**raw).model_dump()
        card = db.scalar(select(Card).where(Card.term == data["term"], Card.owner_id.is_(None)))
        if card is None or all(getattr(card, field) == value for field, value in data.items()):
            continue
        for field, value in card_values(db, data).items():
            setattr(card, field, value)
        card.verified = False
        updated += 1
    db.commit()
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="обновить уже загруженные карточки из файла")
    args = parser.parse_args()
    with SessionLocal() as db:
        added, skipped = load_cards(db)
        print(f"Добавлено: {added}, пропущено (уже есть): {skipped}")
        if args.update:
            print(f"Обновлено карточек (verified сброшен): {update_cards(db)}")
