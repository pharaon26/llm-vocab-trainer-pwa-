import random

import pytest

from app.config import classification_config
from app.enums import ErrorType, TaskType
from app.models import Card
from app.seed import load_cards
from app.services.tasks import BLANK, OPEN_TYPES, build_task, correct_answer, evaluate, gap_sentence


@pytest.fixture
def cards(db):
    load_cards(db)
    return {card.term: card for card in db.query(Card).all()}


def build(cards, term, task_type, seed=1):
    card = cards[term]
    others = [c for c in cards.values() if c.id != card.id]
    return build_task(card, others, task_type, random.Random(seed))


CHOICE_TYPES = [t for t in TaskType if t != TaskType.WRITE_TERM and t not in OPEN_TYPES]


@pytest.mark.parametrize("task_type", CHOICE_TYPES)
def test_choice_tasks_contain_correct_answer_once(cards, task_type):
    for term, card in cards.items():
        task = build(cards, term, task_type)
        if task.task_type != task_type:
            continue
        assert correct_answer(card, task_type) in task.options
        assert len(task.options) == len(set(task.options))
        assert len(task.options) >= 2


def test_gap_fill_hides_term(cards):
    task = build(cards, "vulnerability", TaskType.GAP_FILL)
    assert BLANK in task.prompt
    assert "vulnerability" not in task.prompt.lower()
    assert "threat" in task.options


def test_gap_sentence_covers_inflected_form(cards):
    assert gap_sentence(cards["credential"]) == f"Attackers tried stolen {BLANK} on many other websites."


def test_definition_match_includes_contrast_definition(cards):
    task = build(cards, "vulnerability", TaskType.DEFINITION_MATCH)
    assert cards["threat"].definition_en in task.options


def test_spelling_options_are_misspellings(cards):
    task = build(cards, "authentication", TaskType.SPELLING_CHOICE)
    assert "authentication" in task.options
    assert len(task.options) == 4


def test_collocation_choice_hides_other_word(cards):
    task = build(cards, "vulnerability", TaskType.COLLOCATION_CHOICE)
    assert task.prompt == f"{BLANK} vulnerability"
    assert "critical" in task.options


def test_write_term_has_no_options(cards):
    task = build(cards, "patch", TaskType.WRITE_TERM)
    assert task.options is None
    assert task.prompt == cards["patch"].definition_en


def test_unavailable_task_falls_back(cards):
    card = cards["patch"]
    card.examples = ["Nothing relevant here.", "Still nothing."]
    task = build(cards, "patch", TaskType.GAP_FILL)
    assert task.task_type == TaskType.DEFINITION_MATCH


@pytest.mark.parametrize(
    "task_type, answer, expected",
    [
        (TaskType.SPELLING_CHOICE, "patch", None),
        (TaskType.SPELLING_CHOICE, "pacth", ErrorType.FORM),
        (TaskType.DEFINITION_MATCH, "wrong", ErrorType.MEANING),
        (TaskType.GAP_FILL, "threat", ErrorType.USAGE),
        (TaskType.WRITE_TERM, "  Patch ", None),
        (TaskType.WRITE_TERM, "pach", ErrorType.FORM),
        (TaskType.WRITE_TERM, "update", ErrorType.MEANING),
        (TaskType.WRITE_TERM, "", ErrorType.MEANING),
    ],
)
def test_evaluate(cards, task_type, answer, expected):
    assert evaluate(cards["patch"], task_type, answer) == expected


def test_evaluate_collocation(cards):
    card = cards["vulnerability"]
    assert evaluate(card, TaskType.COLLOCATION_CHOICE, "critical") is None
    assert evaluate(card, TaskType.COLLOCATION_CHOICE, "high") == ErrorType.COLLOCATION


def test_open_tasks_have_no_options_and_compose_has_situation(cards):
    explain = build(cards, "patch", TaskType.EXPLAIN_MEANING)
    assert explain.options is None and explain.prompt == "patch" and explain.context is None
    compose = build(cards, "patch", TaskType.COMPOSE_SENTENCE)
    assert compose.options is None and compose.prompt == "patch"
    assert compose.context in classification_config.situations


def test_situation_is_chosen_randomly(cards):
    seen = {build(cards, "patch", TaskType.COMPOSE_SENTENCE, seed=i).context for i in range(40)}
    assert len(seen) == len(classification_config.situations)


def test_open_answers_are_not_compared(cards):
    with pytest.raises(ValueError):
        evaluate(cards["patch"], TaskType.EXPLAIN_MEANING, "anything")


def test_open_task_reference_is_shown(cards):
    assert correct_answer(cards["patch"], TaskType.EXPLAIN_MEANING) == cards["patch"].definition_en
    assert correct_answer(cards["patch"], TaskType.COMPOSE_SENTENCE) == cards["patch"].examples[0]
