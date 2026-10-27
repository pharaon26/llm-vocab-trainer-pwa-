from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class DomainOut(BaseModel):
    id: int
    name: str


class DomainIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class DeckOut(BaseModel):
    id: int
    name: str
    description: str
    domain: str
    is_default: bool
    cards: int
    selected: bool
    teacher: str | None = None
    assigned: bool = False


class DeckSelectionIn(BaseModel):
    deck_ids: list[int]


class TeacherDeckOut(BaseModel):
    id: int
    name: str
    description: str
    domain: str
    is_default: bool
    cards: int
    cards_total: int
    card_ids: list[int]
    group_ids: list[int] = []


class DeckIn(BaseModel):
    name: Name
    description: str = Field(default="", max_length=1000)
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    is_default: bool = False


class DeckCardsIn(BaseModel):
    card_ids: list[int]


class DeckGroupsIn(BaseModel):
    group_ids: list[int]
