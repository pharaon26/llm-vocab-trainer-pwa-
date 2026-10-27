"""case insensitive card terms

Revision ID: c1d2e3f40a11
Revises: a8e028cf1e07
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f40a11'
down_revision: Union[str, Sequence[str], None] = 'a8e028cf1e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_cards_owner_term", "cards", type_="unique")
    op.drop_index("uq_cards_term_shared", table_name="cards")
    op.create_index("uq_cards_owner_term", "cards", ["owner_id", sa.text("lower(term)")], unique=True)
    op.create_index(
        "uq_cards_term_shared", "cards", [sa.text("lower(term)")], unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_cards_term_shared", table_name="cards")
    op.drop_index("uq_cards_owner_term", table_name="cards")
    op.create_index(
        "uq_cards_term_shared", "cards", ["term"], unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_unique_constraint("uq_cards_owner_term", "cards", ["owner_id", "term"])
