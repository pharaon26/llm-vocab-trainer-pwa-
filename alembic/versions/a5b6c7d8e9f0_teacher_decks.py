"""teacher decks

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-27 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("decks", sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_decks_owner_id", "decks", ["owner_id"], unique=False)
    op.drop_constraint("decks_name_key", "decks", type_="unique")
    op.create_index(
        "uq_decks_name_shared", "decks", [sa.text("lower(name)")], unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index("uq_decks_owner_name", "decks", ["owner_id", sa.text("lower(name)")], unique=True)
    op.create_table(
        "group_decks",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("teacher_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_group_decks_deck_id", "group_decks", ["deck_id"], unique=False)


def downgrade() -> None:
    op.drop_table("group_decks")
    op.execute("DELETE FROM decks WHERE owner_id IS NOT NULL")
    op.drop_index("uq_decks_owner_name", table_name="decks")
    op.drop_index("uq_decks_name_shared", table_name="decks")
    op.create_unique_constraint("decks_name_key", "decks", ["name"])
    op.drop_index("ix_decks_owner_id", table_name="decks")
    op.drop_column("decks", "owner_id")
