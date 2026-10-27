import json

import pytest

from sqlalchemy import select
from app.config import GenerationConfig
from app.enums import TaskType
from app.llm.base import LLMError
from app.llm.fake import FakeProvider
from app.models import Card
from app.schemas.generation import GeneratedTask
from app.seed import load_cards
from app.services.generation import GENERATED_TYPES, generate_task
from app.services.validation import check_rules, check_with_llm, validate


@pytest.fixture
async def cards(db):
    await load_cards(db)
    return {c.term: c for c in (await db.scalars(select(Card))).all()}


@pytest.fixture
def vuln(cards):
    return cards["vulnerability"]


def task(prompt, options, answer):
    return GeneratedTask(prompt=prompt, options=options, correct_answer=answer)


GAP_OK = task("A critical ____ was found in the server.", ["vulnerability", "threat", "attack", "exploit"], "vulnerability")
DEF_OK = task(
    "vulnerability",
    [
        "A weakness in a system, application or process that can be exploited by an attacker.",
        "A potential event that can cause harm.",
        "A copy of data stored separately.",
        "A delay between request and response.",
    ],
    "A weakness in a system, application or process that can be exploited by an attacker.",
)


def test_valid_tasks_pass_rules(vuln):
    assert check_rules(vuln, TaskType.GAP_FILL, GAP_OK) == []
    assert check_rules(vuln, TaskType.DEFINITION_MATCH, DEF_OK) == []


@pytest.mark.parametrize(
    "task_type, bad, reason",
    [
        (TaskType.GAP_FILL, task("A ____ was found.", ["vulnerability", "threat", "attack"], "vulnerability"), "options_count"),
        (TaskType.GAP_FILL, task("A ____ was found.", ["vulnerability", "Threat", "threat", "attack"], "vulnerability"), "options_not_unique"),
        (TaskType.GAP_FILL, task("A ____ was found.", ["bug", "threat", "attack", "exploit"], "vulnerability"), "answer_not_in_options"),
        (TaskType.GAP_FILL, task("A ____ was found.", ["vulnerability", "threat", "attack", "exploit"], "threat"), "answer_not_term"),
        (TaskType.GAP_FILL, task("A found.", ["vulnerability", "threat", "attack", "exploit"], "vulnerability"), "blank_count"),
        (TaskType.GAP_FILL, task("A ____ is not a vulnerability.", ["vulnerability", "threat", "attack", "exploit"], "vulnerability"), "term_in_prompt"),
        (TaskType.DEFINITION_MATCH, task("threat", DEF_OK.options, DEF_OK.correct_answer), "prompt_not_term"),
        (TaskType.DEFINITION_MATCH, task("vulnerability", DEF_OK.options, DEF_OK.options[1]), "wrong_definition"),
    ],
)
def test_rule_failures(vuln, task_type, bad, reason):
    assert reason in check_rules(vuln, task_type, bad)


def test_missing_options_fail(vuln):
    failures = check_rules(vuln, TaskType.GAP_FILL, GeneratedTask(prompt="A ____", correct_answer="vulnerability"))
    assert "options_count" in failures


def review(fitting, meaning=True):
    return json.dumps({"fitting_options": fitting, "term_meaning_matches": meaning})


async def test_llm_check_accepts_single_fitting_option(vuln):
    provider = FakeProvider([review(["vulnerability"])])
    assert await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK) == []


async def test_llm_check_hides_correct_answer_from_reviewer(vuln):
    provider = FakeProvider([review(["vulnerability"])])
    await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK)
    _, user = provider.calls[0]
    assert "correct_answer" not in user


async def test_llm_check_detects_ambiguity(vuln):
    provider = FakeProvider([review(["vulnerability", "exploit"])])
    assert await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK) == ["ambiguous"]


async def test_llm_check_detects_rejected_answer(vuln):
    provider = FakeProvider([review(["exploit"])])
    failures = await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK)
    assert set(failures) == {"answer_rejected", "ambiguous"}


async def test_llm_check_detects_wrong_meaning(vuln):
    provider = FakeProvider([review(["vulnerability"], meaning=False)])
    assert await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK) == ["wrong_meaning"]


async def test_llm_check_invalid_review(vuln):
    provider = FakeProvider(["not json"])
    assert await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK) == ["review_invalid"]


async def test_llm_error_in_review_propagates(vuln):
    provider = FakeProvider([LLMError("down")])
    with pytest.raises(LLMError):
        await check_with_llm(provider, vuln, TaskType.GAP_FILL, GAP_OK)


async def test_llm_not_called_when_rules_fail(vuln):
    provider = FakeProvider()
    bad = task("A found.", ["vulnerability", "threat", "attack", "exploit"], "vulnerability")
    assert await validate(provider, vuln, TaskType.GAP_FILL, bad) == ["blank_count"]
    assert provider.calls == []


def test_custom_options_count(vuln):
    config = GenerationConfig(options_count=3)
    three = task("A ____ was found.", ["vulnerability", "threat", "attack"], "vulnerability")
    assert check_rules(vuln, TaskType.GAP_FILL, three, config) == []


@pytest.mark.parametrize("task_type", GENERATED_TYPES)
async def test_fake_provider_end_to_end_passes_validation(cards, task_type):
    provider = FakeProvider()
    for card in cards.values():
        generated = await generate_task(provider, card, task_type)
        assert await validate(provider, card, task_type, generated) == [], card.term


def test_blank_is_normalized():
    generated = task("The _____ was found, and the ______ fixed.", ["a", "b"], "a")
    assert generated.prompt == "The ____ was found, and the ____ fixed."
