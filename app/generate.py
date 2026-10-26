import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.enums import TaskType
from app.llm.factory import get_provider
from app.models import Card
from app.services.generation import GENERATED_TYPES, generate_task

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("term")
    parser.add_argument("task_type", choices=[t.value for t in GENERATED_TYPES])
    args = parser.parse_args()

    with SessionLocal() as db:
        card = db.scalar(select(Card).where(Card.term == args.term))
        if card is None:
            raise SystemExit(f"Card not found: {args.term}")
        task = generate_task(get_provider(), card, TaskType(args.task_type))
    print(task.model_dump_json(indent=2))
