import random
import re

from app.config import ClassificationConfig, classification_config
from app.enums import ErrorType, TaskType
from app.models import Card
from app.schemas.session import TaskOut

OPTIONS_COUNT = 4
BLANK = "____"
TYPO_DISTANCE = 2
FALLBACK = (TaskType.DEFINITION_MATCH, TaskType.WRITE_TERM)

INSTRUCTIONS = {
    TaskType.SPELLING_CHOICE: "Выберите правильное написание термина",
    TaskType.DEFINITION_MATCH: "Выберите определение, которое соответствует термину",
    TaskType.GAP_FILL: "Вставьте подходящий термин в пропуск",
    TaskType.COLLOCATION_CHOICE: "Выберите слово, которое сочетается с термином",
    TaskType.WRITE_TERM: "Запишите термин по определению",
    TaskType.EXPLAIN_MEANING: "Объясните значение термина своими словами на английском (1-2 предложения)",
    TaskType.COMPOSE_SENTENCE: "Составьте одно предложение на английском с этим термином для ситуации ниже",
}

OPEN_TYPES = (TaskType.EXPLAIN_MEANING, TaskType.COMPOSE_SENTENCE)

ERROR_BY_TASK = {
    TaskType.SPELLING_CHOICE: ErrorType.FORM,
    TaskType.DEFINITION_MATCH: ErrorType.MEANING,
    TaskType.GAP_FILL: ErrorType.USAGE,
    TaskType.COLLOCATION_CHOICE: ErrorType.COLLOCATION,
}


def norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def gap_sentence(card: Card) -> str | None:
    pattern = re.compile(rf"\b{re.escape(card.term)}\w*", re.IGNORECASE)
    for example in card.examples:
        if pattern.search(example):
            return pattern.sub(BLANK, example)
    return None


def collocation_gap(card: Card) -> tuple[str, str] | None:
    term = norm(card.term)
    for collocation in card.collocations:
        words = collocation.split()
        if len(words) != 2:
            continue
        for index, word in enumerate(words):
            if norm(word) == term:
                hidden = words[1 - index]
                prompt = f"{BLANK} {word}" if index == 1 else f"{word} {BLANK}"
                return prompt, hidden
    return None


def is_available(card: Card, task_type: TaskType) -> bool:
    if task_type == TaskType.GAP_FILL:
        return gap_sentence(card) is not None
    if task_type == TaskType.COLLOCATION_CHOICE:
        return collocation_gap(card) is not None
    if task_type == TaskType.SPELLING_CHOICE:
        return len(card.term) >= 4
    return True


def task_prompt(card: Card, task_type: TaskType, context: str | None = None, entry=None) -> str:
    if entry is not None:
        return entry.prompt
    if task_type == TaskType.GAP_FILL:
        return gap_sentence(card) or card.term
    if task_type == TaskType.COLLOCATION_CHOICE:
        gap = collocation_gap(card)
        return gap[0] if gap else card.term
    if task_type == TaskType.SPELLING_CHOICE:
        return card.translation_ru
    if task_type == TaskType.WRITE_TERM:
        return card.definition_en
    if task_type == TaskType.COMPOSE_SENTENCE and context:
        return f"{card.term} - {context}"
    return card.term


def correct_answer(card: Card, task_type: TaskType) -> str:
    if task_type == TaskType.EXPLAIN_MEANING:
        return card.definition_en
    if task_type == TaskType.COMPOSE_SENTENCE:
        return card.examples[0]
    if task_type == TaskType.DEFINITION_MATCH:
        return card.definition_en
    if task_type == TaskType.COLLOCATION_CHOICE:
        return collocation_gap(card)[1]
    return card.term


def evaluate(
    card: Card, task_type: TaskType, answer: str, correct: str | None = None
) -> ErrorType | None:
    if task_type in OPEN_TYPES:
        raise ValueError("Open tasks are classified, not compared")
    expected = norm(correct if correct is not None else correct_answer(card, task_type))
    given = norm(answer)
    if given == expected:
        return None
    if task_type == TaskType.WRITE_TERM:
        return ErrorType.FORM if distance(given, expected) <= TYPO_DISTANCE else ErrorType.MEANING
    return ERROR_BY_TASK[task_type]


def _task(card, task_type, instruction, prompt, correct=None, distractors=(), rng=random):
    options = None
    if correct is not None:
        options = [correct, *distractors]
        rng.shuffle(options)
    return TaskOut(
        card_id=card.id, task_type=task_type, instruction=instruction, prompt=prompt, options=options
    )


def _misspellings(term: str, rng: random.Random) -> list[str]:
    variants = set()
    for _ in range(40):
        i = rng.randrange(1, len(term) - 1)
        kind = rng.choice(("swap", "drop", "double"))
        if kind == "swap":
            variant = term[:i] + term[i + 1] + term[i] + term[i + 2 :]
        elif kind == "drop":
            variant = term[:i] + term[i + 1 :]
        else:
            variant = term[:i] + term[i] + term[i:]
        if norm(variant) != norm(term):
            variants.add(variant)
    return rng.sample(sorted(variants), min(len(variants), OPTIONS_COUNT - 1))


def _spelling_choice(card, others, rng):
    typos = _misspellings(card.term, rng)
    if not typos:
        return None
    return _task(
        card, TaskType.SPELLING_CHOICE,
        INSTRUCTIONS[TaskType.SPELLING_CHOICE],
        card.translation_ru, card.term, typos, rng=rng,
    )


def _definition_match(card, others, rng):
    pool = list(others)
    rng.shuffle(pool)
    pool.sort(key=lambda other: norm(other.term) != norm(card.contrast_term))
    definitions = []
    for other in pool:
        if other.definition_en != card.definition_en and other.definition_en not in definitions:
            definitions.append(other.definition_en)
    definitions = definitions[: OPTIONS_COUNT - 1]
    if not definitions:
        return None
    return _task(
        card, TaskType.DEFINITION_MATCH,
        INSTRUCTIONS[TaskType.DEFINITION_MATCH],
        card.term, card.definition_en, definitions, rng=rng,
    )


def _gap_fill(card, others, rng):
    terms = [card.contrast_term] + [other.term for other in rng.sample(others, len(others))]
    distractors = []
    for term in terms:
        if norm(term) != norm(card.term) and norm(term) not in map(norm, distractors):
            distractors.append(term)
    distractors = distractors[: OPTIONS_COUNT - 1]
    if not distractors:
        return None
    return _task(
        card, TaskType.GAP_FILL,
        INSTRUCTIONS[TaskType.GAP_FILL],
        gap_sentence(card), card.term, distractors, rng=rng,
    )


def _collocation_choice(card, others, rng):
    prompt, hidden = collocation_gap(card)
    own_words = {norm(word) for col in card.collocations for word in col.split()}
    pool = []
    for other in others:
        gap = collocation_gap(other)
        if gap and norm(gap[1]) not in own_words and gap[1] not in pool:
            pool.append(gap[1])
    distractors = rng.sample(pool, min(len(pool), OPTIONS_COUNT - 1))
    if not distractors:
        return None
    return _task(
        card, TaskType.COLLOCATION_CHOICE,
        INSTRUCTIONS[TaskType.COLLOCATION_CHOICE],
        prompt, hidden, distractors, rng=rng,
    )


def _write_term(card, others, rng):
    return _task(
        card, TaskType.WRITE_TERM,
        INSTRUCTIONS[TaskType.WRITE_TERM],
        card.definition_en,
    )


def _explain_meaning(card, others, rng):
    return _task(card, TaskType.EXPLAIN_MEANING, INSTRUCTIONS[TaskType.EXPLAIN_MEANING], card.term)


def _compose_sentence(card, others, rng, config: ClassificationConfig = classification_config):
    task = _task(card, TaskType.COMPOSE_SENTENCE, INSTRUCTIONS[TaskType.COMPOSE_SENTENCE], card.term)
    task.context = rng.choice(config.situations)
    return task


_BUILDERS = {
    TaskType.EXPLAIN_MEANING: _explain_meaning,
    TaskType.COMPOSE_SENTENCE: _compose_sentence,
    TaskType.SPELLING_CHOICE: _spelling_choice,
    TaskType.DEFINITION_MATCH: _definition_match,
    TaskType.GAP_FILL: _gap_fill,
    TaskType.COLLOCATION_CHOICE: _collocation_choice,
    TaskType.WRITE_TERM: _write_term,
}


def build_task(
    card: Card, others: list[Card], task_type: TaskType, rng: random.Random | None = None
) -> TaskOut:
    rng = rng or random.Random()
    for candidate in (task_type, *FALLBACK):
        if is_available(card, candidate):
            task = _BUILDERS[candidate](card, others, rng)
            if task is not None:
                return task
    return _write_term(card, others, rng)
