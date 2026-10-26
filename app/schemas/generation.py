from typing import Annotated

import re

from pydantic import BaseModel, Field, StringConstraints, field_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ReviewResult(BaseModel):
    fitting_options: list[str]
    term_meaning_matches: bool


class GeneratedTask(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    options: Annotated[list[Short], Field(min_length=2, max_length=6)] | None = None
    correct_answer: Short

    @field_validator("prompt")
    @classmethod
    def normalize_blank(cls, value: str) -> str:
        return re.sub(r"_{3,}", "____", value)
