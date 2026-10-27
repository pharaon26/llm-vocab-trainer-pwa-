from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.config import link_config
from app.schemas.auth import Name

GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=link_config.max_group_name)]


class SendIn(BaseModel):
    name: Name


class InviteIn(SendIn):
    group_id: int | None = None


class GroupIn(BaseModel):
    name: GroupName


class GroupOut(BaseModel):
    id: int
    name: str
    students: int


class AcceptIn(BaseModel):
    group_id: int | None = None


class MoveIn(BaseModel):
    group_id: int | None = None


class SentOut(BaseModel):
    detail: str = "If this user exists and can be linked, the request has been sent"


class PersonOut(BaseModel):
    name: str


class PendingOut(BaseModel):
    id: int
    name: str


class MyTeachersOut(BaseModel):
    teachers: list[PersonOut]
    invitations: list[PendingOut]
    requests: list[PendingOut]


class TeacherLinksOut(BaseModel):
    requests: list[PendingOut]
    invitations: list[PendingOut]
