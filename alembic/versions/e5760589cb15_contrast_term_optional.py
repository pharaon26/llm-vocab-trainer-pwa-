"""contrast term optional

Revision ID: e5760589cb15
Revises: bb0953d3a86e
Create Date: 2026-10-26 23:59:42.016361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5760589cb15'
down_revision: Union[str, Sequence[str], None] = 'bb0953d3a86e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("cards", "contrast_term", existing_type=sa.String(length=100), nullable=True)


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE cards SET contrast_term = '' WHERE contrast_term IS NULL"))
    op.alter_column("cards", "contrast_term", existing_type=sa.String(length=100), nullable=False)
