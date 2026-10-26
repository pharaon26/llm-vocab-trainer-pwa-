from datetime import date

from pydantic import BaseModel, Field

from app.enums import ErrorType, TaskType
from app.schemas.card import CardRead


class TaskOut(BaseModel):
    task_id: int | None = None
    card_id: int
    task_type: TaskType
    instruction: str
    prompt: str
    options: list[str] | None = None
    context: str | None = None


class NextOut(BaseModel):
    task: TaskOut | None
    remaining: int
    next_review_date: date | None = None
    unseen_cards: int = 0
    new_cards_per_day: int | None = None


class AnswerIn(BaseModel):
    card_id: int
    task_type: TaskType
    answer: str = Field(max_length=500)
    task_id: int | None = None
    context: str | None = Field(default=None, max_length=300)


class AnswerOut(BaseModel):
    correct: bool
    error_type: ErrorType | None
    correct_answer: str
    card: CardRead
    retry_in_session: bool
    classified_by: str
    comment: str | None = None
    remaining: int
