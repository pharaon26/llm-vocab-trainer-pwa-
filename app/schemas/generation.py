from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class GeneratedTask(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    options: Annotated[list[Short], Field(min_length=2, max_length=6)] | None = None
    correct_answer: Short
