import logging
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DraftConfig, draft_config
from app.llm.base import LLMError, LLMProvider
from app.llm.prompts import build_extract_prompt
from app.models import CardDraft, User
from app.schemas.drafts import ExtractCandidate, ExtractOut
from app.schemas.generation import ExtractedTerms
from app.services.drafts import (
    find_domain,
    find_duplicate,
    llm_calls_left,
    normalize_term,
    register_llm_call,
)
from app.services.generation import InvalidResponse, parse_model

logger = logging.getLogger(__name__)

MAX_TERM_WORDS = 4
MAX_TERM_LENGTH = 100


class TextTooLong(Exception):
    pass


class ModelUnavailable(Exception):
    pass


class LimitReached(Exception):
    pass


def _stem(word: str) -> str:
    return word[: max(4, len(word) - 3)]


def appears_in(term: str, text: str) -> bool:
    lowered = text.lower()
    if term.lower() in lowered:
        return True
    return all(_stem(word) in lowered for word in term.lower().split())


def clean_terms(raw: list, text: str, max_terms: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        term = normalize_term(item).strip(" .,;:!?\"'()[]")
        key = term.lower()
        if (
            not term
            or key in seen
            or len(term) > MAX_TERM_LENGTH
            or len(term.split()) > MAX_TERM_WORDS
            or re.fullmatch(r"[\d\W_]+", term)
            or not appears_in(term, text)
        ):
            continue
        seen.add(key)
        result.append(term)
    return result[:max_terms]


def extract_terms(
    db: Session,
    user: User,
    text: str,
    domain_name: str,
    today: date,
    provider: LLMProvider | None,
    config: DraftConfig = draft_config,
) -> ExtractOut:
    if len(text) > config.extract_max_chars:
        raise TextTooLong
    domain = find_domain(db, domain_name)
    if provider is None:
        raise ModelUnavailable
    if llm_calls_left(db, user, today, config) <= 0:
        raise LimitReached

    system, prompt = build_extract_prompt(text, domain.name, config.extract_max_terms)
    terms: list | None = None
    for _ in range(config.max_retries + 1):
        if llm_calls_left(db, user, today, config) <= 0:
            raise LimitReached
        register_llm_call(db, user, today)
        try:
            terms = parse_model(provider.complete(system, prompt), ExtractedTerms).terms
            break
        except InvalidResponse as exc:
            logger.info("term extraction invalid: %s", exc)
        except LLMError as exc:
            logger.warning("term extraction failed: %s", exc)
            raise ModelUnavailable from exc
    if terms is None:
        raise ModelUnavailable

    drafts = {
        value.lower()
        for value in db.scalars(select(CardDraft.term).where(CardDraft.owner_id == user.id))
    }
    candidates = []
    for term in clean_terms(terms, text, config.extract_max_terms):
        existing = find_duplicate(db, user, term)
        candidates.append(
            ExtractCandidate(
                term=term,
                exists=existing is not None,
                personal=existing is not None and existing.owner_id is not None,
                has_draft=term.lower() in drafts,
            )
        )
    return ExtractOut(candidates=candidates, llm_calls_left=llm_calls_left(db, user, today, config))
