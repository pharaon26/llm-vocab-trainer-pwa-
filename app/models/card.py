from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.catalog import Domain


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("owner_id", "term", name="uq_cards_owner_term"),
        Index(
            "uq_cards_term_shared", "term", unique=True,
            sqlite_where=text("owner_id IS NULL"), postgresql_where=text("owner_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), index=True)
    transcription: Mapped[str] = mapped_column(String(100))
    part_of_speech: Mapped[str] = mapped_column(String(30))
    definition_en: Mapped[str] = mapped_column(Text)
    translation_ru: Mapped[str] = mapped_column(String(200))
    collocations: Mapped[list[str]] = mapped_column(JSON)
    examples: Mapped[list[str]] = mapped_column(JSON)
    common_mistakes: Mapped[list[str]] = mapped_column(JSON)
    contrast_term: Mapped[str | None] = mapped_column(String(100))
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    confirmed_by_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    audio_url: Mapped[str | None] = mapped_column(Text)
    field_sources: Mapped[dict | None] = mapped_column(JSON)

    domain_ref: Mapped[Domain] = relationship(lazy="joined")

    @property
    def domain(self) -> str:
        return self.domain_ref.name

    @property
    def personal(self) -> bool:
        return self.owner_id is not None
