from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.config import learning_config
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
    is_practice: bool
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


class DayStat(BaseModel):
    date: date
    answered: int
    correct: int
    accuracy: float | None
    practice: int = 0


class StreakStat(BaseModel):
    current: int
    best: int


class TotalsStat(BaseModel):
    answered: int
    correct: int
    accuracy: float | None


class StudentErrorStat(BaseModel):
    error_type: ErrorType
    count: int
    share: float


class StatsOut(BaseModel):
    days: list[DayStat]
    error_types: list[StudentErrorStat]
    streak: StreakStat
    totals: TotalsStat


class SettingsIn(BaseModel):
    new_cards_per_day: int = Field(ge=learning_config.min_new_per_day, le=learning_config.max_new_per_day)


class SettingsOut(BaseModel):
    new_cards_per_day: int
    min_new_per_day: int
    max_new_per_day: int
