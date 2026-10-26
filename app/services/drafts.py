import logging
from datetime import date

from pydantic import ValidationError
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import DraftConfig, draft_config
from app.dictionary.base import DictionaryProvider, DictionaryUnavailable
from app.dictionary.dictionaryapi import contains_word
from app.llm.base import LLMError, LLMProvider
from app.llm.prompts import build_draft_prompt
from app.models import (
    Card,
    CardDraft,
    CardProgress,
    DeckCard,
    Domain,
    LlmUsage,
    ReviewHistory,
    TaskBank,
    User,
)
from app.schemas.card import CardCreate
from app.schemas.drafts import DraftFields, DraftOut
from app.schemas.generation import DraftSuggestion
from app.services.cards import card_values
from app.services.generation import InvalidResponse, parse_model

logger = logging.getLogger(__name__)

TEXT_FIELDS = ("transcription", "part_of_speech", "definition_en", "translation_ru", "contrast_term")
LIST_FIELDS = ("collocations", "examples", "common_mistakes")
FIELDS = TEXT_FIELDS + LIST_FIELDS
MIN_ITEMS = {"collocations": 2, "examples": 2, "common_mistakes": 1}
MAX_ITEMS = {"collocations": 4, "examples": 3, "common_mistakes": 3}
OPTIONAL = ("contrast_term",)

NOTICE_DICTIONARY_DOWN = "Внешний словарь недоступен: поля предложены моделью, проверьте их особенно внимательно."
NOTICE_NOT_FOUND = "В словаре слово не найдено: поля предложены моделью."
NOTICE_NO_LLM = "Модель не настроена: недостающие поля заполните вручную."
NOTICE_LIMIT = "Дневной лимит обращений к модели исчерпан: недостающие поля заполните вручную."
NOTICE_LLM_DOWN = "Модель сейчас недоступна: недостающие поля заполните вручную."
NOTICE_LLM_INVALID = "Модель не вернула корректный ответ: недостающие поля заполните вручную."


class DuplicateTerm(Exception):
    def __init__(self, card: Card):
        self.card = card


class UnknownDomain(Exception):
    pass


class TooManyDrafts(Exception):
    pass


class DraftIncomplete(Exception):
    def __init__(self, errors: list[dict]):
        self.errors = errors


def normalize_term(term: str) -> str:
    return " ".join(term.split())


def find_domain(db: Session, name: str) -> Domain:
    domain = db.scalar(select(Domain).where(func.lower(Domain.name) == name.strip().lower()))
    if domain is None:
        raise UnknownDomain
    return domain


def find_duplicate(db: Session, user: User, term: str) -> Card | None:
    visible = or_(and_(Card.owner_id.is_(None), Card.verified.is_(True)), Card.owner_id == user.id)
    return db.scalar(select(Card).where(func.lower(Card.term) == term.lower(), visible).order_by(Card.owner_id.is_(None).desc()))


def llm_calls_left(db: Session, user: User, today: date, config: DraftConfig = draft_config) -> int:
    used = db.scalar(select(LlmUsage.calls).where(LlmUsage.user_id == user.id, LlmUsage.day == today)) or 0
    return max(0, config.daily_llm_limit - used)


def register_llm_call(db: Session, user: User, today: date) -> None:
    usage = db.get(LlmUsage, (user.id, today))
    if usage is None:
        db.add(LlmUsage(user_id=user.id, day=today, calls=1))
    else:
        usage.calls += 1
    db.commit()


def _clean_list(items, term: str | None, limit: int, require_term: bool) -> list[str]:
    result: list[str] = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        item = " ".join(item.split())
        if not item or item in result or len(item) > 300:
            continue
        if require_term and term and not contains_word(item, term) and term.lower() not in item.lower():
            continue
        result.append(item)
    return result[:limit]


def _empty_fields() -> dict:
    return {field: ([] if field in LIST_FIELDS else None) for field in FIELDS}


def _suggest(
    db: Session, user: User, provider: LLMProvider, term: str, domain: str, known: dict,
    today: date, config: DraftConfig, notices: list[str],
) -> DraftSuggestion | None:
    system, prompt = build_draft_prompt(term, domain, known)
    for _ in range(config.max_retries + 1):
        if llm_calls_left(db, user, today, config) <= 0:
            notices.append(NOTICE_LIMIT)
            return None
        register_llm_call(db, user, today)
        try:
            return parse_model(provider.complete(system, prompt), DraftSuggestion)
        except InvalidResponse as exc:
            logger.info("draft suggestion for %s invalid: %s", term, exc)
        except LLMError as exc:
            logger.warning("draft suggestion failed: %s", exc)
            notices.append(NOTICE_LLM_DOWN)
            return None
    notices.append(NOTICE_LLM_INVALID)
    return None


def _merge(data: dict, sources: dict, suggestion: DraftSuggestion, term: str) -> str | None:
    def put(field, value):
        data[field] = value
        sources[field] = "llm"

    general_definition = None
    if suggestion.translation_ru and suggestion.translation_ru.strip():
        put("translation_ru", suggestion.translation_ru.strip()[:200])
    contrast = (suggestion.contrast_term or "").strip()
    if contrast and contrast.lower() != term.lower():
        put("contrast_term", contrast[:100])
    collocations = _clean_list(suggestion.collocations, term, MAX_ITEMS["collocations"], True)
    if collocations:
        put("collocations", collocations)
    mistakes = _clean_list(suggestion.common_mistakes, None, MAX_ITEMS["common_mistakes"], False)
    if mistakes:
        put("common_mistakes", mistakes)
    if not data["transcription"] and suggestion.transcription and suggestion.transcription.strip():
        put("transcription", suggestion.transcription.strip()[:100])
    if not data["part_of_speech"] and suggestion.part_of_speech and suggestion.part_of_speech.strip():
        put("part_of_speech", suggestion.part_of_speech.strip()[:30])
    proposed = (suggestion.definition_en or "").strip()
    if proposed:
        if not data["definition_en"]:
            put("definition_en", proposed)
        elif not suggestion.general_definition_fits:
            general_definition = data["definition_en"]
            put("definition_en", proposed)
    if len(data["examples"]) < MIN_ITEMS["examples"]:
        merged = _clean_list(data["examples"] + (suggestion.examples or []), term, MAX_ITEMS["examples"], True)
        if len(merged) > len(data["examples"]):
            put("examples", merged)
    return general_definition


def missing_fields(data: dict) -> list[str]:
    missing = []
    for field in FIELDS:
        if field in OPTIONAL:
            continue
        value = data.get(field)
        if field in LIST_FIELDS:
            if len(value or []) < MIN_ITEMS[field]:
                missing.append(field)
        elif not value:
            missing.append(field)
    return missing


def draft_out(db: Session, draft: CardDraft, user: User, today: date, config: DraftConfig = draft_config) -> DraftOut:
    data = {**_empty_fields(), **draft.data}
    return DraftOut(
        id=draft.id,
        term=draft.term,
        domain=draft.domain_ref.name,
        fields=DraftFields(**{field: data[field] for field in FIELDS}),
        audio_url=draft.data.get("audio_url"),
        sources=dict(draft.sources),
        general_definition=draft.general_definition,
        notices=list(draft.notices),
        missing=missing_fields(data),
        llm_calls_left=llm_calls_left(db, user, today, config),
    )


def create_draft(
    db: Session,
    user: User,
    term: str,
    domain_name: str,
    today: date,
    dictionary: DictionaryProvider | None,
    provider: LLMProvider | None,
    config: DraftConfig = draft_config,
) -> CardDraft:
    term = normalize_term(term)
    domain = find_domain(db, domain_name)
    duplicate = find_duplicate(db, user, term)
    if duplicate is not None:
        raise DuplicateTerm(duplicate)

    existing = db.scalar(
        select(CardDraft).where(CardDraft.owner_id == user.id, func.lower(CardDraft.term) == term.lower())
    )
    if existing is not None:
        return existing
    open_drafts = db.scalar(select(func.count()).select_from(CardDraft).where(CardDraft.owner_id == user.id))
    if open_drafts >= config.max_open_drafts:
        raise TooManyDrafts

    data, sources, notices = _empty_fields(), {}, []
    audio_url = None
    if dictionary is not None:
        try:
            entry = dictionary.lookup(term)
        except DictionaryUnavailable as exc:
            logger.info("dictionary unavailable for %s: %s", term, exc)
            entry = None
            notices.append(NOTICE_DICTIONARY_DOWN)
        else:
            if entry is None:
                notices.append(NOTICE_NOT_FOUND)
        if entry is not None:
            for field, value in (
                ("transcription", entry.transcription),
                ("part_of_speech", entry.part_of_speech),
                ("definition_en", entry.definition),
                ("examples", entry.examples),
            ):
                if value:
                    data[field] = value
                    sources[field] = "dictionary"
            audio_url = entry.audio_url

    general_definition = None
    if provider is None:
        notices.append(NOTICE_NO_LLM)
    else:
        known = {key: data[key] for key in ("transcription", "part_of_speech", "definition_en", "examples")}
        suggestion = _suggest(db, user, provider, term, domain.name, known, today, config, notices)
        if suggestion is not None:
            general_definition = _merge(data, sources, suggestion, term)

    data["audio_url"] = audio_url
    draft = CardDraft(
        owner_id=user.id, term=term, domain_id=domain.id, data=data, sources=sources,
        general_definition=general_definition, notices=notices,
    )
    db.add(draft)
    db.commit()
    return draft


def _clean_value(field: str, value):
    if field in LIST_FIELDS:
        return _clean_list(value, None, 10, False)
    value = (value or "").strip()
    return value or None


def update_draft(db: Session, draft: CardDraft, fields: DraftFields, domain_name: str | None) -> None:
    data = dict(draft.data)
    sources = dict(draft.sources)
    for field in FIELDS:
        incoming = getattr(fields, field)
        if incoming is None:
            continue
        value = _clean_value(field, incoming)
        if value != (data.get(field) or ([] if field in LIST_FIELDS else None)):
            data[field] = value if value is not None else ([] if field in LIST_FIELDS else None)
            sources[field] = "user"
    draft.data = data
    draft.sources = sources
    if domain_name:
        draft.domain_id = find_domain(db, domain_name).id
    db.commit()


def _validation_errors(error: ValidationError) -> list[dict]:
    return [{"loc": ["body", *[str(part) for part in item["loc"]]], "msg": item["msg"]} for item in error.errors()]


def confirm_draft(db: Session, user: User, draft: CardDraft) -> Card:
    data = {**_empty_fields(), **draft.data}
    payload = {field: data.get(field) for field in FIELDS}
    for field in TEXT_FIELDS:
        if payload[field] is None and field not in OPTIONAL:
            payload[field] = ""
    try:
        validated = CardCreate(term=draft.term, domain=draft.domain_ref.name, **payload)
    except ValidationError as exc:
        raise DraftIncomplete(_validation_errors(exc)) from exc

    duplicate = find_duplicate(db, user, draft.term)
    if duplicate is not None:
        raise DuplicateTerm(duplicate)
    card = Card(
        **card_values(db, validated.model_dump()),
        verified=False, owner_id=user.id, confirmed_by_owner=True,
        audio_url=data.get("audio_url"), field_sources=dict(draft.sources),
    )
    db.add(card)
    db.delete(draft)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateTerm(find_duplicate(db, user, draft.term)) from exc
    return card


def update_personal_card(db: Session, card: Card, data: CardCreate) -> None:
    sources = dict(card.field_sources or {})
    new_values = card_values(db, data.model_dump())
    for field in FIELDS:
        incoming = new_values.get(field)
        if incoming != getattr(card, field):
            sources[field] = "user"
    for field, value in new_values.items():
        setattr(card, field, value)
    card.field_sources = sources
    db.commit()


def delete_personal_card(db: Session, card: Card) -> None:
    db.execute(delete(ReviewHistory).where(ReviewHistory.card_id == card.id))
    db.execute(delete(CardProgress).where(CardProgress.card_id == card.id))
    db.execute(delete(TaskBank).where(TaskBank.card_id == card.id))
    db.execute(delete(DeckCard).where(DeckCard.card_id == card.id))
    db.delete(card)
    db.commit()
