"""add background tasks

Revision ID: 0003_add_background_tasks
Revises: 0002_add_query_indexes
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_background_tasks"
down_revision = "0002_add_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_task_status_created", "background_task", ["status", "created_at"])
    op.create_index("ix_background_task_type_status", "background_task", ["task_type", "status"])
    op.create_index("ix_background_task_creator_created", "background_task", ["created_by", "created_at"])


def downgrade():
    op.drop_index("ix_background_task_creator_created", table_name="background_task")
    op.drop_index("ix_background_task_type_status", table_name="background_task")
    op.drop_index("ix_background_task_status_created", table_name="background_task")
    op.drop_table("background_task")
