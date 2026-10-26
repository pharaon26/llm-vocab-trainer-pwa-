import logging
import re
from dataclasses import dataclass

from app.config import ClassificationConfig, classification_config
from app.enums import ErrorType, TaskType
from app.llm.base import LLMError, LLMProvider
from app.llm.prompts import build_classification_prompt
from app.models import Card
from app.schemas.classification import ClassificationResult
from app.services.generation import InvalidResponse, parse_model
from app.services.tasks import distance, norm

logger = logging.getLogger(__name__)

WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

EMPTY_ANSWER_ERROR = {
    TaskType.EXPLAIN_MEANING: ErrorType.MEANING,
    TaskType.COMPOSE_SENTENCE: ErrorType.USAGE,
}


INJECTION = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,40}\b(instruction|rule|prompt|above|previous|before)"
    r"|error_type|is_correct|system prompt",
    re.IGNORECASE | re.DOTALL,
)


class ClassifierUnavailable(Exception):
    pass


@dataclass
class Classification:
    error_type: ErrorType | None
    source: str
    comment: str | None


def has_misspelled_term(term: str, answer: str, config: ClassificationConfig) -> bool:
    target = norm(term)
    limit = min(config.typo_distance, max(1, len(target) // 4))
    words = [w.casefold() for w in WORD.findall(answer)]
    if any(w.startswith(target) for w in words):
        return False
    return any(abs(len(w) - len(target)) <= limit and distance(w, target) <= limit for w in words)


def classify_open_answer(
    provider: LLMProvider | None,
    card: Card,
    task_type: TaskType,
    answer: str,
    context: str | None,
    config: ClassificationConfig = classification_config,
) -> Classification:
    if not answer.strip():
        return Classification(EMPTY_ANSWER_ERROR[task_type], "rule", "Ответ пустой.")
    if INJECTION.search(answer):
        return Classification(
            EMPTY_ANSWER_ERROR[task_type], "rule",
            "Ответ содержит обращение к проверяющей системе, а не ответ на задание.",
        )
    if has_misspelled_term(card.term, answer, config):
        return Classification(
            ErrorType.FORM, "rule", f"Термин написан с ошибкой, правильно: {card.term}."
        )
    if provider is None:
        raise ClassifierUnavailable("No LLM provider configured")

    system, user = build_classification_prompt(card, task_type, answer, context)
    for attempt in range(1, config.max_retries + 2):
        try:
            result = parse_model(provider.complete(system, user), ClassificationResult)
        except InvalidResponse as exc:
            logger.info("%s/%s classification attempt %s invalid: %s", card.term, task_type.value, attempt, exc)
            continue
        except LLMError as exc:
            raise ClassifierUnavailable(str(exc)) from exc
        return Classification(result.error_type, "llm", result.comment)
    raise ClassifierUnavailable("Classifier returned no valid response")
