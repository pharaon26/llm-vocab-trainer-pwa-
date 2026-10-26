from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    transcription: Mapped[str] = mapped_column(String(100))
    part_of_speech: Mapped[str] = mapped_column(String(30))
    definition_en: Mapped[str] = mapped_column(Text)
    translation_ru: Mapped[str] = mapped_column(String(200))
    collocations: Mapped[list[str]] = mapped_column(JSON)
    examples: Mapped[list[str]] = mapped_column(JSON)
    common_mistakes: Mapped[list[str]] = mapped_column(JSON)
    contrast_term: Mapped[str] = mapped_column(String(100))
    domain: Mapped[str] = mapped_column(String(50))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
