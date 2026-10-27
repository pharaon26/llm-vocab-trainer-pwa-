import argparse
import asyncio

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.enums import TaskType
from app.llm.factory import get_provider
from app.models import Card
from app.services.generation import GENERATED_TYPES, generate_task


async def main(term: str, task_type: str) -> None:
    async with SessionLocal() as db:
        card = await db.scalar(select(Card).where(Card.term == term))
        if card is None:
            raise SystemExit(f"Card not found: {term}")
        task = await generate_task(get_provider(), card, TaskType(task_type))
    await engine.dispose()
    print(task.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("term")
    parser.add_argument("task_type", choices=[t.value for t in GENERATED_TYPES])
    args = parser.parse_args()
    asyncio.run(main(args.term, args.task_type))
