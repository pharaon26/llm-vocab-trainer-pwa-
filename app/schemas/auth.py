from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.enums import Role


class LoginIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    role: Role = Role.STUDENT
    password: str | None = None


class LoginOut(BaseModel):
    token: str
    name: str
    role: Role
