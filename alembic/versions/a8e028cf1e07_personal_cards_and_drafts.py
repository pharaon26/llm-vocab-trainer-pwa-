"""personal cards and drafts

Revision ID: a8e028cf1e07
Revises: e5760589cb15
Create Date: 2026-10-27 00:03:10.763496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8e028cf1e07'
down_revision: Union[str, Sequence[str], None] = 'e5760589cb15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("cards", sa.Column("confirmed_by_owner", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cards", sa.Column("audio_url", sa.Text(), nullable=True))
    op.add_column("cards", sa.Column("field_sources", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_cards_owner_id", "cards", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_cards_owner_id", "cards", ["owner_id"], unique=False)
    op.drop_index("ix_cards_term", table_name="cards")
    op.create_index("ix_cards_term", "cards", ["term"], unique=False)
    op.create_unique_constraint("uq_cards_owner_term", "cards", ["owner_id", "term"])
    op.create_index(
        "uq_cards_term_shared", "cards", ["term"], unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_table(
        "card_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.String(length=100), nullable=False),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("general_definition", sa.Text(), nullable=True),
        sa.Column("notices", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_card_drafts_owner_id", "card_drafts", ["owner_id"], unique=False)
    op.create_table(
        "llm_usage",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_index("ix_card_drafts_owner_id", table_name="card_drafts")
    op.drop_table("card_drafts")
    op.drop_index("uq_cards_term_shared", table_name="cards")
    op.get_bind().execute(sa.text("DELETE FROM cards WHERE owner_id IS NOT NULL"))
    op.drop_constraint("uq_cards_owner_term", "cards", type_="unique")
    op.drop_index("ix_cards_term", table_name="cards")
    op.create_index("ix_cards_term", "cards", ["term"], unique=True)
    op.drop_index("ix_cards_owner_id", table_name="cards")
    op.drop_constraint("fk_cards_owner_id", "cards", type_="foreignkey")
    op.drop_column("cards", "field_sources")
    op.drop_column("cards", "audio_url")
    op.drop_column("cards", "confirmed_by_owner")
    op.drop_column("cards", "owner_id")
