from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
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


class UserDeck(Base):
    __tablename__ = "user_decks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True)
