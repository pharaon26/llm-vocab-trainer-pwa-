from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.config import auth_config
from app.enums import Role

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class RegisterIn(BaseModel):
    name: Name
    password: str = Field(min_length=auth_config.password_min_length, max_length=auth_config.password_max_length)
    password_confirm: str = Field(max_length=auth_config.password_max_length)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class LoginIn(BaseModel):
    name: Name
    role: Role = Role.STUDENT
    password: str | None = Field(default=None, max_length=auth_config.password_max_length)


class LoginOut(BaseModel):
    name: str
    role: Role
