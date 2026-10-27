import json
import logging

import pytest

from sqlalchemy import func, select
from app.config import GenerationConfig
from app.enums import TaskType
from app.llm.base import LLMError
from app.llm.fake import FakeProvider
from app.models import Card, TaskBank
from app.seed import load_cards
from app.services import bank
from app.services.task_source import generate_validated, get_task

GOOD = json.dumps(
    {"prompt": "A critical ____ was found in the server.",
     "options": ["vulnerability", "threat", "attack", "exploit"], "correct_answer": "vulnerability"}
)
GOOD_REVIEW = json.dumps({"fitting_options": ["vulnerability"], "term_meaning_matches": True})
BAD_RULES = json.dumps(
    {"prompt": "No blank here.", "options": ["vulnerability", "threat", "attack", "exploit"],
     "correct_answer": "vulnerability"}
)
AMBIGUOUS = json.dumps({"fitting_options": ["vulnerability", "exploit"], "term_meaning_matches": True})
GAP = TaskType.GAP_FILL


@pytest.fixture
async def cards(db):
    await load_cards(db)
    return (await db.scalars(select(Card).order_by(Card.id))).all()


@pytest.fixture
def vuln(cards):
    return next(c for c in cards if c.term == "vulnerability")


def others(cards, card):
    return [c for c in cards if c.id != card.id]


async def test_first_attempt_success(vuln):
    provider = FakeProvider([GOOD, GOOD_REVIEW])
    assert (await generate_validated(provider, vuln, GAP)).correct_answer == "vulnerability"
    assert len(provider.calls) == 2


async def test_retry_after_rule_failure_skips_review(vuln):
    provider = FakeProvider([BAD_RULES, GOOD, GOOD_REVIEW])
    assert await generate_validated(provider, vuln, GAP) is not None
    assert len(provider.calls) == 3


async def test_retry_after_ambiguous_review(vuln):
    provider = FakeProvider([GOOD, AMBIGUOUS, GOOD, GOOD_REVIEW])
    assert await generate_validated(provider, vuln, GAP) is not None
    assert len(provider.calls) == 4


async def test_invalid_json_counts_as_attempt(vuln):
    provider = FakeProvider(["garbage", GOOD, GOOD_REVIEW])
    assert await generate_validated(provider, vuln, GAP) is not None


async def test_gives_up_after_three_attempts(vuln):
    provider = FakeProvider(["garbage", BAD_RULES, BAD_RULES, GOOD, GOOD_REVIEW])
    assert await generate_validated(provider, vuln, GAP) is None
    assert len(provider.calls) == 3


async def test_max_retries_is_configurable(vuln):
    provider = FakeProvider([BAD_RULES, BAD_RULES])
    assert await generate_validated(provider, vuln, GAP, GenerationConfig(max_retries=0)) is None
    assert len(provider.calls) == 1


async def test_llm_error_propagates_without_retry(vuln):
    provider = FakeProvider([LLMError("down"), GOOD, GOOD_REVIEW])
    with pytest.raises(LLMError):
        await generate_validated(provider, vuln, GAP)
    assert len(provider.calls) == 1


async def test_get_task_saves_validated_task_to_bank(db, cards, vuln):
    provider = FakeProvider([GOOD, GOOD_REVIEW])
    task = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    entry = await db.get(TaskBank, task.task_id)
    assert entry.source == "fake"
    assert entry.correct_answer == "vulnerability"
    assert sorted(task.options) == sorted(entry.options)


async def test_rejected_task_is_not_saved(db, cards, vuln):
    provider = FakeProvider([BAD_RULES] * 3)
    task = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    assert (await db.scalar(select(func.count()).select_from(select(TaskBank).subquery()))) == 0
    assert task.task_id is None
    assert task.task_type == TaskType.GAP_FILL


async def test_falls_back_to_bank_when_generation_fails(db, cards, vuln):
    first = await get_task(db, FakeProvider([GOOD, GOOD_REVIEW]), vuln, GAP, others(cards, vuln))
    broken = FakeProvider([BAD_RULES] * 3)
    task = await get_task(db, broken, vuln, GAP, others(cards, vuln))
    assert task.task_id == first.task_id


async def test_falls_back_to_bank_on_llm_error(db, cards, vuln, caplog):
    first = await get_task(db, FakeProvider([GOOD, GOOD_REVIEW]), vuln, GAP, others(cards, vuln))
    with caplog.at_level(logging.WARNING):
        task = await get_task(db, FakeProvider([LLMError("down")]), vuln, GAP, others(cards, vuln))
    assert task.task_id == first.task_id
    assert "down" in caplog.text


async def test_empty_bank_and_llm_error_gives_algorithmic_task(db, cards, vuln):
    task = await get_task(db, FakeProvider([LLMError("down")]), vuln, GAP, others(cards, vuln))
    assert task.task_id is None
    assert task.options


async def test_no_provider_uses_algorithmic_task(db, cards, vuln):
    assert (await get_task(db, None, vuln, GAP, others(cards, vuln))).task_id is None


async def test_enough_bank_entries_skip_llm(db, cards, vuln):
    config = GenerationConfig(bank_min_size=1)
    provider = FakeProvider([GOOD, GOOD_REVIEW])
    first = await get_task(db, provider, vuln, GAP, others(cards, vuln), config=config)
    calls = len(provider.calls)
    again = await get_task(db, provider, vuln, GAP, others(cards, vuln), config=config)
    assert again.task_id == first.task_id
    assert len(provider.calls) == calls


@pytest.mark.parametrize("task_type", [TaskType.WRITE_TERM, TaskType.COLLOCATION_CHOICE])
async def test_non_generated_type_never_calls_llm(db, cards, vuln, task_type):
    provider = FakeProvider()
    task = await get_task(db, provider, vuln, task_type, others(cards, vuln))
    assert task.task_type == task_type
    assert task.task_id is None
    assert provider.calls == []


async def test_bank_deduplicates(db, cards, vuln):
    provider = FakeProvider([GOOD, GOOD_REVIEW, GOOD, GOOD_REVIEW])
    first = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    second = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    assert first.task_id == second.task_id
    assert (await db.scalar(select(func.count()).select_from(select(TaskBank).subquery()))) == 1


async def test_pick_prefers_least_used(db, cards, vuln):
    other_json = json.dumps(
        {"prompt": "We must fix the ____ before release.",
         "options": ["vulnerability", "threat", "attack", "exploit"], "correct_answer": "vulnerability"}
    )
    provider = FakeProvider([GOOD, GOOD_REVIEW, other_json, GOOD_REVIEW])
    a = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    b = await get_task(db, provider, vuln, GAP, others(cards, vuln))
    assert a.task_id != b.task_id
    (await db.get(TaskBank, a.task_id)).times_used = 5
    assert (await bank.pick(db, vuln.id, GAP, "fake")).id == b.task_id


async def test_bank_is_scoped_by_source(db, cards, vuln):
    await get_task(db, FakeProvider([GOOD, GOOD_REVIEW]), vuln, GAP, others(cards, vuln))
    assert await bank.count(db, vuln.id, GAP, "fake") == 1
    assert await bank.count(db, vuln.id, GAP, "gigachat:GigaChat-2") == 0
    assert await bank.count(db, vuln.id, GAP, None) == 0
    assert await bank.pick(db, vuln.id, GAP, None) is None
