from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TaskBank(Base):
    __tablename__ = "task_bank"
    __table_args__ = (UniqueConstraint("card_id", "task_type", "source", "prompt", "correct_answer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(60))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_answer: Mapped[str] = mapped_column(Text)
    times_used: Mapped[int] = mapped_column(default=0)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
