"""passwords, sessions, login attempts

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f40a11
Create Date: 2026-10-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f40a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))

    # Прежние токены лежали в базе открытым текстом и передавались в заголовке. Их заменяют сессии в cookie, все входят заново.
    op.drop_table("auth_tokens")
    op.create_table(
        "sessions",
        sa.Column("session_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_name", "login_attempts", ["name"], unique=False)
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip"], unique=False)
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("sessions")
    op.create_table(
        "auth_tokens",
        sa.Column("token", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.drop_column("users", "password_hash")
