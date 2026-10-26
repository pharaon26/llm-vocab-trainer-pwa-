from pydantic import BaseModel, Field

from app.enums import ErrorType, TaskType
from app.schemas.card import CardRead


class TaskOut(BaseModel):
    card_id: int
    task_type: TaskType
    instruction: str
    prompt: str
    options: list[str] | None = None


class NextOut(BaseModel):
    task: TaskOut | None
    remaining: int


class AnswerIn(BaseModel):
    card_id: int
    task_type: TaskType
    answer: str = Field(max_length=500)


class AnswerOut(BaseModel):
    correct: bool
    error_type: ErrorType | None
    correct_answer: str
    card: CardRead
    retry_in_session: bool
    remaining: int
