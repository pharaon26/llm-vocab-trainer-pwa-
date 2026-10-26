from typing import Annotated

from pydantic import BaseModel, StringConstraints


class DraftFields(BaseModel):
    transcription: str | None = None
    part_of_speech: str | None = None
    definition_en: str | None = None
    translation_ru: str | None = None
    collocations: list[str] | None = None
    examples: list[str] | None = None
    common_mistakes: list[str] | None = None
    contrast_term: str | None = None


class DraftCreateIn(BaseModel):
    term: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class DraftUpdateIn(BaseModel):
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None = None
    fields: DraftFields = DraftFields()


class DraftOut(BaseModel):
    id: int
    term: str
    domain: str
    fields: DraftFields
    audio_url: str | None
    sources: dict[str, str]
    general_definition: str | None
    notices: list[str]
    missing: list[str]
    llm_calls_left: int


class DuplicateDeck(BaseModel):
    id: int
    name: str
    selected: bool


class DuplicateOut(BaseModel):
    id: int
    term: str
    domain: str
    definition_en: str
    personal: bool
    decks: list[DuplicateDeck]


class CreateDraftOut(BaseModel):
    draft: DraftOut | None = None
    duplicate: DuplicateOut | None = None


class PersonalCardOut(BaseModel):
    id: int
    term: str
    domain: str
    transcription: str
    part_of_speech: str
    definition_en: str
    translation_ru: str
    collocations: list[str]
    examples: list[str]
    common_mistakes: list[str]
    contrast_term: str | None
    audio_url: str | None
    sources: dict[str, str]


class ExtractIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ExtractCandidate(BaseModel):
    term: str
    exists: bool
    personal: bool
    has_draft: bool


class ExtractOut(BaseModel):
    candidates: list[ExtractCandidate]
    llm_calls_left: int


class LimitsOut(BaseModel):
    extract_max_chars: int
    extract_max_terms: int
    daily_llm_limit: int
    llm_calls_left: int
