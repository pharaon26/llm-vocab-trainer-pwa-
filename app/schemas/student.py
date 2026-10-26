from datetime import date
from typing import Literal

from pydantic import BaseModel


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
