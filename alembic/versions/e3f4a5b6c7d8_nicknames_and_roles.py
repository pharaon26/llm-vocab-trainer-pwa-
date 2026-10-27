"""nicknames and roles

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ник: латиница, цифры, подчеркивание, 3-32 символа, уникален без учета регистра.
    # Старые имена, не подходящие под правило или повторяющиеся без учета регистра, заменяются на user<id>.
    op.execute("UPDATE users SET name = 'user' || id WHERE name !~ '^[A-Za-z0-9_]{3,32}$'")
    op.execute(
        "UPDATE users u SET name = 'user' || u.id "
        "WHERE EXISTS (SELECT 1 FROM users o WHERE lower(o.name) = lower(u.name) AND o.id < u.id)"
    )
    op.drop_index("ix_users_name", table_name="users")
    op.create_index("uq_users_name_lower", "users", [sa.text("lower(name)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_name_lower", table_name="users")
    op.create_index("ix_users_name", "users", ["name"], unique=True)
