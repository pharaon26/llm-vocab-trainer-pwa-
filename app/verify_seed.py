import asyncio
import json

from sqlalchemy import update

from app.db import SessionLocal, engine
from app.models import Card
from app.seed import CARDS_FILE


async def main() -> None:
    terms = [item["term"] for item in json.loads(CARDS_FILE.read_text(encoding="utf-8"))]
    async with SessionLocal() as db:
        result = await db.execute(update(Card).where(Card.term.in_(terms), Card.owner_id.is_(None)).values(verified=True))
        await db.commit()
    await engine.dispose()
    print(f"Помечено проверенными: {result.rowcount}")


if __name__ == "__main__":
    asyncio.run(main())
