"""teacher student links

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
    )
    op.create_index("ix_teacher_groups_teacher_id", "teacher_groups", ["teacher_id"], unique=False)
    op.create_index("uq_teacher_groups_name", "teacher_groups", ["teacher_id", sa.text("lower(name)")], unique=True)
    op.create_table(
        "teacher_students",
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("teacher_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_teacher_students_student_id", "teacher_students", ["student_id"], unique=False)
    op.create_table(
        "link_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("teacher_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_link_requests_teacher_id", "link_requests", ["teacher_id"], unique=False)
    op.create_index("ix_link_requests_student_id", "link_requests", ["student_id"], unique=False)
    op.create_index(
        "uq_link_requests_pending", "link_requests", ["teacher_id", "student_id"], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "link_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_link_attempts_sender_id", "link_attempts", ["sender_id"], unique=False)
    op.create_index("ix_link_attempts_created_at", "link_attempts", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("link_attempts")
    op.drop_table("link_requests")
    op.drop_table("teacher_students")
    op.drop_table("teacher_groups")
