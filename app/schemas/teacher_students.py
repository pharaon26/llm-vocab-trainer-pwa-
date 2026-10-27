from datetime import date

from pydantic import BaseModel


class StudentSummary(BaseModel):
    name: str
    learned: int
    answered: int
    accuracy: float | None
    last_active: date | None


class StudentGroup(BaseModel):
    id: int | None
    name: str | None
    students: list[StudentSummary]


class StudentsOut(BaseModel):
    groups: list[StudentGroup]
