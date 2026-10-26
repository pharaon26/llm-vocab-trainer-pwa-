from datetime import datetime

from pydantic import BaseModel

from app.enums import ErrorType, TaskType


class BankEntryOut(BaseModel):
    id: int
    card_id: int
    term: str
    task_type: TaskType
    source: str
    prompt: str
    options: list[str]
    correct_answer: str
    times_used: int
    rejected: bool
    created_at: datetime


class BankPatch(BaseModel):
    rejected: bool


class ErrorTypeStat(BaseModel):
    error_type: ErrorType
    count: int
    share: float


class TermStat(BaseModel):
    term: str
    attempts: int
    errors: int
    error_rate: float


class SourceStat(BaseModel):
    classified_by: str
    count: int


class AnalyticsOut(BaseModel):
    students: int
    answers: int
    errors: int
    error_rate: float
    min_answers: int
    error_types: list[ErrorTypeStat]
    hardest_terms: list[TermStat]
    classified_by: list[SourceStat]
