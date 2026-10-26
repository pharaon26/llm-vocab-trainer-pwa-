from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.enums import ErrorType, TaskType


class ProgressItem(BaseModel):
    term: str
    status: Literal["new", "learning", "learned"]
    due_date: date | None
    repetitions: int
    errors: dict[str, int]


class ProgressSummary(BaseModel):
    total: int
    new: int
    learning: int
    learned: int


class ProgressOut(BaseModel):
    summary: ProgressSummary
    items: list[ProgressItem]


class HistoryItem(BaseModel):
    id: int
    answered_on: date
    created_at: datetime
    term: str
    task_type: TaskType
    prompt: str
    answer: str
    correct_answer: str
    is_correct: bool
    error_type: ErrorType | None
    is_retry: bool
    classified_by: str
    comment: str | None


class HistoryOut(BaseModel):
    total: int
    terms: list[str]
    items: list[HistoryItem]


class DictionaryEntry(BaseModel):
    term: str
    transcription: str
    part_of_speech: str
    definition_en: str
    translation_ru: str
    collocations: list[str]
    examples: list[str]
