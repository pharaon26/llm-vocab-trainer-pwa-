import logging
import random

from sqlalchemy.orm import Session

from app.config import GenerationConfig, generation_config
from app.enums import TaskType
from app.llm.base import LLMError, LLMProvider
from app.models import Card, TaskBank
from app.schemas.generation import GeneratedTask
from app.schemas.session import TaskOut
from app.services import bank
from app.services.generation import GENERATED_TYPES, InvalidResponse, generate_task
from app.services.tasks import INSTRUCTIONS, build_task
from app.services.validation import validate

logger = logging.getLogger(__name__)


def generate_validated(
    provider: LLMProvider,
    card: Card,
    task_type: TaskType,
    config: GenerationConfig = generation_config,
) -> GeneratedTask | None:
    for attempt in range(1, config.max_retries + 2):
        try:
            task = generate_task(provider, card, task_type)
        except InvalidResponse as exc:
            logger.info("%s/%s attempt %s: invalid response (%s)", card.term, task_type.value, attempt, exc)
            continue
        failures = validate(provider, card, task_type, task, config)
        if not failures:
            return task
        logger.info("%s/%s attempt %s rejected: %s", card.term, task_type.value, attempt, failures)
    return None


def _from_bank(entry: TaskBank, rng: random.Random) -> TaskOut:
    options = list(entry.options)
    rng.shuffle(options)
    task_type = TaskType(entry.task_type)
    return TaskOut(
        task_id=entry.id, card_id=entry.card_id, task_type=task_type,
        instruction=INSTRUCTIONS[task_type], prompt=entry.prompt, options=options,
    )


def get_task(
    db: Session,
    provider: LLMProvider | None,
    card: Card,
    task_type: TaskType,
    others: list[Card],
    rng: random.Random | None = None,
    config: GenerationConfig = generation_config,
) -> TaskOut:
    rng = rng or random.Random()
    if task_type in GENERATED_TYPES:
        source = provider.name if provider else None
        entry = None
        if bank.count(db, card.id, task_type, source) >= config.bank_min_size:
            entry = bank.pick(db, card.id, task_type, source)
        else:
            generated = None
            if provider is not None:
                try:
                    generated = generate_validated(provider, card, task_type, config)
                except LLMError as exc:
                    logger.warning("LLM unavailable, using bank: %s", exc)
            if generated is not None:
                entry = bank.get_or_create(db, card, task_type, generated, provider.name)
            else:
                entry = bank.pick(db, card.id, task_type, source)
        if entry is not None:
            return _from_bank(entry, rng)
    return build_task(card, others, task_type, rng)
