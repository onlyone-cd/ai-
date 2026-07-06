"""add llm usage

Revision ID: 0004_add_llm_usage
Revises: 0003_add_background_tasks
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_llm_usage"
down_revision = "0003_add_background_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])
    op.create_index("ix_llm_usage_provider_model", "llm_usage", ["provider", "model"])
    op.create_index("ix_llm_usage_success_created", "llm_usage", ["success", "created_at"])


def downgrade():
    op.drop_index("ix_llm_usage_success_created", table_name="llm_usage")
    op.drop_index("ix_llm_usage_provider_model", table_name="llm_usage")
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_table("llm_usage")
