import json
import re
import ssl
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from gigachat import GigaChatException

from app.config import BASE_DIR, Settings
from app.enums import TaskType
from app.llm import gigachat as gigachat_module
from app.llm.base import LLMError
from app.llm.factory import get_provider
from app.llm.fake import FakeProvider
from app.llm.gigachat import GigaChatProvider
from app.llm.prompts import CARD_FIELDS, build_prompt
from app.models import Card
from app.schemas.generation import GeneratedTask
from app.seed import load_cards
from app.services.generation import GENERATED_TYPES, InvalidResponse, generate_task, parse_response

CA_FILE = "certs/russian_trusted_root_ca_pem.crt"


@pytest.fixture
def cards(db):
    load_cards(db)
    return db.query(Card).order_by(Card.id).all()


@pytest.fixture
def card(cards):
    return next(c for c in cards if c.term == "vulnerability")


class FakeSDKClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.payloads = []
        self.reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": 1}'))])
        self.error = None
        FakeSDKClient.instances.append(self)

    def chat(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def sdk(monkeypatch):
    FakeSDKClient.instances = []
    monkeypatch.setattr(gigachat_module, "GigaChat", FakeSDKClient)
    return FakeSDKClient


def make_provider(**overrides):
    params = dict(
        credentials="secret-key", scope="GIGACHAT_API_PERS", model="GigaChat-2",
        ca_bundle_file=CA_FILE, temperature=0.3, timeout=30.0,
    )
    return GigaChatProvider(**{**params, **overrides})


@pytest.mark.parametrize("task_type", GENERATED_TYPES)
def test_prompt_contains_card_and_task(card, task_type):
    system, user = build_prompt(card, task_type, "B2")
    assert "JSON" in system
    assert f"Task type: {task_type.value}" in user
    assert "Student level (CEFR): B2" in user
    assert "Domain: Information security" in user
    assert card.definition_en in user
    assert "strict JSON" in user


@pytest.mark.parametrize("task_type", GENERATED_TYPES)
def test_prompt_names_the_term_explicitly(card, task_type):
    _, user = build_prompt(card, task_type, "B1")
    assert "{term}" not in user
    if task_type != TaskType.DEFINITION_MATCH:
        assert '"vulnerability"' in user.split("<card>")[0]


def test_prompt_card_has_only_reference_fields(card):
    _, user = build_prompt(card, TaskType.GAP_FILL, "B1")
    payload = json.loads(re.search(r"<card>\s*(.*?)\s*</card>", user, re.DOTALL).group(1))
    assert set(payload) == set(CARD_FIELDS)
    assert "verified" not in payload and "id" not in payload


@pytest.mark.parametrize(
    "task_type", [TaskType.WRITE_TERM, TaskType.SPELLING_CHOICE, TaskType.COLLOCATION_CHOICE]
)
def test_non_generated_type_rejected(card, task_type):
    with pytest.raises(ValueError):
        generate_task(FakeProvider(), card, task_type)


@pytest.mark.parametrize("task_type", GENERATED_TYPES)
def test_fake_provider_output_is_valid_for_every_card(cards, task_type):
    provider = FakeProvider()
    for card in cards:
        task = generate_task(provider, card, task_type)
        assert task.correct_answer in task.options
        assert len(task.options) == len(set(task.options))
    assert len(provider.calls) == len(cards)


def test_fake_gap_fill_hides_term(card):
    task = generate_task(FakeProvider(), card, TaskType.GAP_FILL)
    assert "____" in task.prompt
    assert card.term not in task.prompt.lower()
    assert task.correct_answer == card.term


def test_fake_scripted_responses_and_errors(card):
    good = '{"prompt": "p", "options": ["a", "b"], "correct_answer": "a"}'
    provider = FakeProvider([good, LLMError("boom")])
    assert generate_task(provider, card, TaskType.GAP_FILL).correct_answer == "a"
    with pytest.raises(LLMError, match="boom"):
        generate_task(provider, card, TaskType.GAP_FILL)
    with pytest.raises(LLMError, match="No scripted"):
        generate_task(provider, card, TaskType.GAP_FILL)


def test_parse_accepts_fenced_json_with_noise():
    text = 'Here you go:\n```json\n{"prompt": "x ____", "options": ["a", "b"], "correct_answer": "a", "note": 1}\n```'
    assert parse_response(text) == GeneratedTask(prompt="x ____", options=["a", "b"], correct_answer="a")


@pytest.mark.parametrize(
    "text",
    [
        "no json at all",
        "{broken",
        '{"prompt": "x"}',
        '{"prompt": "", "options": ["a", "b"], "correct_answer": "a"}',
        '{"prompt": "x", "options": ["only"], "correct_answer": "only"}',
        '{"prompt": "x", "options": ["a", "b"], "correct_answer": "' + "z" * 301 + '"}',
        '["a", "b"]',
    ],
)
def test_parse_rejects_bad_responses(text):
    with pytest.raises(InvalidResponse):
        parse_response(text)


def test_factory_default_is_fake():
    assert isinstance(get_provider(Settings(_env_file=None)), FakeProvider)


def test_factory_gigachat_requires_credentials():
    with pytest.raises(LLMError, match="CREDENTIALS"):
        get_provider(Settings(_env_file=None, llm_provider="gigachat"))


def test_factory_builds_gigachat_from_settings(sdk):
    config = Settings(
        _env_file=None, llm_provider="gigachat", gigachat_credentials="key", gigachat_model="GigaChat-2"
    )
    assert isinstance(get_provider(config), GigaChatProvider)
    assert sdk.instances[0].kwargs["model"] == "GigaChat-2"


def test_gigachat_client_options(sdk):
    make_provider()
    kwargs = sdk.instances[0].kwargs
    assert kwargs["credentials"] == "secret-key"
    assert kwargs["scope"] == "GIGACHAT_API_PERS"
    assert kwargs["model"] == "GigaChat-2"
    assert kwargs["verify_ssl_certs"] is True
    assert Path(kwargs["ca_bundle_file"]) == BASE_DIR / CA_FILE


def test_gigachat_complete_sends_system_and_user(sdk):
    provider = make_provider()
    assert provider.complete("sys", "usr") == '{"ok": 1}'
    payload = sdk.instances[0].payloads[0]
    assert [(m.role, m.content) for m in payload.messages] == [("system", "sys"), ("user", "usr")]
    assert payload.temperature == 0.3


def test_gigachat_wraps_sdk_errors_without_leaking_key(sdk):
    provider = make_provider()
    sdk.instances[0].error = httpx.ConnectError("tls failure with secret-key")
    with pytest.raises(LLMError) as info:
        provider.complete("s", "u")
    assert "secret-key" not in str(info.value)
    sdk.instances[0].error = GigaChatException("bad")
    with pytest.raises(LLMError):
        provider.complete("s", "u")


def test_gigachat_empty_response(sdk):
    provider = make_provider()
    sdk.instances[0].reply = SimpleNamespace(choices=[])
    with pytest.raises(LLMError, match="empty"):
        provider.complete("s", "u")


def test_gigachat_missing_ca_bundle(sdk):
    with pytest.raises(LLMError, match="CA bundle"):
        make_provider(ca_bundle_file="certs/missing.crt")


def test_repository_certificate_is_valid_pem():
    pem = (BASE_DIR / CA_FILE).read_text()
    assert ssl.PEM_cert_to_DER_cert(pem)
