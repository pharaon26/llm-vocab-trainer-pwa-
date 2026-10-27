from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.config import auth_config
from app.enums import Role

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Nickname = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=rf"^[A-Za-z0-9_]{{{auth_config.nickname_min_length},{auth_config.nickname_max_length}}}$",
    ),
]


class RegisterIn(BaseModel):
    name: Nickname
    password: str = Field(min_length=auth_config.password_min_length, max_length=auth_config.password_max_length)
    password_confirm: str = Field(max_length=auth_config.password_max_length)
    role: Literal[Role.STUDENT, Role.TEACHER] = Role.STUDENT

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class LoginIn(BaseModel):
    name: Name
    password: str | None = Field(default=None, max_length=auth_config.password_max_length)


class LoginOut(BaseModel):
    name: str
    role: Role
