"""domains and decks

Revision ID: bb0953d3a86e
Revises: 85d3302c02ba
Create Date: 2026-10-26 23:55:47.064643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

DEFAULT_DOMAINS = ["IT", "Information security", "Medicine", "Law", "Economics", "Engineering"]
DECK_NAME = "IT & Security basics"
DECK_DESCRIPTION = "Базовая лексика по ИТ и информационной безопасности"


# revision identifiers, used by Alembic.
revision: str = 'bb0953d3a86e'
down_revision: Union[str, Sequence[str], None] = '85d3302c02ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False, unique=True),
    )
    op.create_table(
        "decks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "deck_cards",
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "user_decks",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decks_customized", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("domain_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    used = [row[0] for row in conn.execute(sa.text("SELECT DISTINCT domain FROM cards ORDER BY domain"))]
    for name in used + [d for d in DEFAULT_DOMAINS if d not in used]:
        conn.execute(sa.text("INSERT INTO domains (name) VALUES (:name)"), {"name": name})
    conn.execute(sa.text("UPDATE cards SET domain_id = (SELECT id FROM domains WHERE domains.name = cards.domain)"))

    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.alter_column("domain_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key("fk_cards_domain_id", "domains", ["domain_id"], ["id"])
        batch_op.drop_column("domain")

    if conn.execute(sa.text("SELECT COUNT(*) FROM cards")).scalar():
        conn.execute(
            sa.text(
                "INSERT INTO decks (name, description, domain_id, is_default) "
                "VALUES (:name, :description, (SELECT id FROM domains WHERE name = 'IT'), :default)"
            ),
            {"name": DECK_NAME, "description": DECK_DESCRIPTION, "default": True},
        )
        conn.execute(
            sa.text(
                "INSERT INTO deck_cards (deck_id, card_id) "
                "SELECT (SELECT id FROM decks WHERE name = :name), id FROM cards"
            ),
            {"name": DECK_NAME},
        )


def downgrade() -> None:
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("domain", sa.String(length=50), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE cards SET domain = (SELECT name FROM domains WHERE domains.id = cards.domain_id)"))
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.alter_column("domain", existing_type=sa.String(length=50), nullable=False)
        batch_op.drop_constraint("fk_cards_domain_id", type_="foreignkey")
        batch_op.drop_column("domain_id")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("decks_customized")
    op.drop_table("user_decks")
    op.drop_table("deck_cards")
    op.drop_table("decks")
    op.drop_table("domains")
