from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Deck(Base):
    __tablename__ = "decks"
    __table_args__ = (
        Index("uq_decks_name_shared", text("lower(name)"), unique=True, postgresql_where=text("owner_id IS NULL")),
        Index("uq_decks_owner_name", "owner_id", text("lower(name)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    domain_ref: Mapped[Domain] = relationship(lazy="joined")

    @property
    def domain(self) -> str:
        return self.domain_ref.name


class DeckCard(Base):
    __tablename__ = "deck_cards"

    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True)


class GroupDeck(Base):
    __tablename__ = "group_decks"

    group_id: Mapped[int] = mapped_column(ForeignKey("teacher_groups.id", ondelete="CASCADE"), primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True, index=True)


class UserDeck(Base):
    __tablename__ = "user_decks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True)


class CardDraft(Base):
    __tablename__ = "card_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    term: Mapped[str] = mapped_column(String(100))
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    data: Mapped[dict] = mapped_column(JSON)
    sources: Mapped[dict] = mapped_column(JSON)
    general_definition: Mapped[str | None] = mapped_column(Text)
    notices: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    domain_ref: Mapped[Domain] = relationship(lazy="joined")


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(default=0)
