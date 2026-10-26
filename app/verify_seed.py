import json

from sqlalchemy import update

from app.db import SessionLocal
from app.models import Card
from app.seed import CARDS_FILE

if __name__ == "__main__":
    terms = [item["term"] for item in json.loads(CARDS_FILE.read_text(encoding="utf-8"))]
    with SessionLocal() as db:
        result = db.execute(update(Card).where(Card.term.in_(terms), Card.owner_id.is_(None)).values(verified=True))
        db.commit()
    print(f"Помечено проверенными: {result.rowcount}")
