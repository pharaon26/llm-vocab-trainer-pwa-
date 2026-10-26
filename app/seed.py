import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Card
from app.schemas.card import CardCreate

CARDS_FILE = Path(__file__).resolve().parent.parent / "data" / "cards.json"


def load_cards(db: Session, path: Path = CARDS_FILE) -> tuple[int, int]:
    added = skipped = 0
    for raw in json.loads(path.read_text(encoding="utf-8")):
        data = CardCreate(**raw)
        if db.scalar(select(Card).where(Card.term == data.term)):
            skipped += 1
            continue
        db.add(Card(**data.model_dump(), verified=False))
        added += 1
    db.commit()
    return added, skipped


if __name__ == "__main__":
    with SessionLocal() as db:
        added, skipped = load_cards(db)
    print(f"Добавлено: {added}, пропущено (уже есть): {skipped}")
