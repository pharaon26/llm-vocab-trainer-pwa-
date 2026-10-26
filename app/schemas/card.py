from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CardCreate(BaseModel):
    term: Annotated[NonEmpty, Field(max_length=100)]
    transcription: Annotated[NonEmpty, Field(max_length=100)]
    part_of_speech: Annotated[NonEmpty, Field(max_length=30)]
    definition_en: NonEmpty
    translation_ru: Annotated[NonEmpty, Field(max_length=200)]
    collocations: Annotated[list[NonEmpty], Field(min_length=2, max_length=4)]
    examples: Annotated[list[NonEmpty], Field(min_length=2, max_length=3)]
    common_mistakes: Annotated[list[NonEmpty], Field(min_length=1)]
    contrast_term: Annotated[NonEmpty, Field(max_length=100)]
    domain: Annotated[NonEmpty, Field(max_length=50)]


class CardRead(CardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    verified: bool
