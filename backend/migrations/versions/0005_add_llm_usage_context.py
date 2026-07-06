"""add llm usage context

Revision ID: 0005_add_llm_usage_context
Revises: 0004_add_llm_usage
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_llm_usage_context"
down_revision = "0004_add_llm_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("llm_usage", sa.Column("source", sa.String(length=80), nullable=True))
    op.add_column("llm_usage", sa.Column("tool_name", sa.String(length=120), nullable=True))
    op.add_column("llm_usage", sa.Column("api_path", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("llm_usage", "api_path")
    op.drop_column("llm_usage", "tool_name")
    op.drop_column("llm_usage", "source")
