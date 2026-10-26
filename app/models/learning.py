from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CardProgress(Base):
    __tablename__ = "card_progress"
    __table_args__ = (UniqueConstraint("user_id", "card_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"))
    interval: Mapped[float] = mapped_column(Float)
    ease: Mapped[float] = mapped_column(Float)
    repetitions: Mapped[int] = mapped_column(default=0)
    pending_interval: Mapped[float | None] = mapped_column(Float)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    first_seen_on: Mapped[date] = mapped_column(Date)
    last_error_type: Mapped[str | None] = mapped_column(String(20))


class ReviewHistory(Base):
    __tablename__ = "review_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(30))
    answer: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    error_type: Mapped[str | None] = mapped_column(String(20))
    is_retry: Mapped[bool] = mapped_column(Boolean)
    classified_by: Mapped[str] = mapped_column(String(10), server_default="task")
    comment: Mapped[str | None] = mapped_column(Text)
    task_bank_id: Mapped[int | None] = mapped_column(ForeignKey("task_bank.id", ondelete="SET NULL"))
    answered_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
