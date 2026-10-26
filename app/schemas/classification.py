from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator

from app.enums import ErrorType


class ClassificationResult(BaseModel):
    is_correct: bool
    error_type: ErrorType | None = None
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]

    @model_validator(mode="after")
    def check_consistency(self):
        if self.is_correct and self.error_type is not None:
            raise ValueError("A correct answer must not have an error type")
        if not self.is_correct and self.error_type is None:
            raise ValueError("An incorrect answer must have an error type")
        return self
