import re

from app.config import GenerationConfig, generation_config
from app.enums import TaskType
from app.llm.base import LLMProvider
from app.llm.prompts import build_check_prompt
from app.models import Card
from app.schemas.generation import GeneratedTask, ReviewResult
from app.services.generation import InvalidResponse, parse_model
from app.services.tasks import BLANK, norm


def check_rules(
    card: Card, task_type: TaskType, task: GeneratedTask, config: GenerationConfig = generation_config
) -> list[str]:
    failures = []
    options = task.options or []
    normalized = [norm(o) for o in options]
    answer = norm(task.correct_answer)
    term = norm(card.term)

    if len(options) != config.options_count:
        failures.append("options_count")
    if len(set(normalized)) != len(normalized):
        failures.append("options_not_unique")
    if answer not in normalized:
        failures.append("answer_not_in_options")

    if task_type == TaskType.GAP_FILL:
        if answer != term:
            failures.append("answer_not_term")
        if task.prompt.count(BLANK) != 1:
            failures.append("blank_count")
        if re.search(rf"\b{re.escape(term)}", task.prompt, re.IGNORECASE):
            failures.append("term_in_prompt")

    elif task_type == TaskType.DEFINITION_MATCH:
        if norm(task.prompt) != term:
            failures.append("prompt_not_term")
        if answer != norm(card.definition_en):
            failures.append("wrong_definition")

    return failures


async def check_with_llm(
    provider: LLMProvider, card: Card, task_type: TaskType, task: GeneratedTask
) -> list[str]:
    system, user = build_check_prompt(card, task_type, task)
    try:
        review = parse_model(await provider.complete(system, user), ReviewResult)
    except InvalidResponse:
        return ["review_invalid"]

    failures = []
    fitting = {norm(o) for o in review.fitting_options}
    answer = norm(task.correct_answer)
    if answer not in fitting:
        failures.append("answer_rejected")
    if fitting - {answer}:
        failures.append("ambiguous")
    if not review.term_meaning_matches:
        failures.append("wrong_meaning")
    return failures


async def validate(
    provider: LLMProvider,
    card: Card,
    task_type: TaskType,
    task: GeneratedTask,
    config: GenerationConfig = generation_config,
) -> list[str]:
    failures = check_rules(card, task_type, task, config)
    if failures:
        return failures
    return await check_with_llm(provider, card, task_type, task)
