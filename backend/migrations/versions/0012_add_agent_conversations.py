"""add agent conversations

Revision ID: 0012_add_agent_conversations
Revises: 0011_add_resume_attachments
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_add_agent_conversations"
down_revision = "0011_add_resume_attachments"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "agent_conversation" not in tables:
        op.create_table(
            "agent_conversation",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("title", sa.String(length=128), nullable=False, server_default="新对话"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
            sa.Column("pending_action", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("agent_conversation", "ix_agent_conversation_owner_updated", ["owner_hr_id", "updated_at"])
    create_index_if_missing("agent_conversation", "ix_agent_conversation_status", ["status"])

    tables = set(sa.inspect(bind).get_table_names())
    if "agent_message" not in tables:
        op.create_table(
            "agent_message",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversation.id"), nullable=False),
            sa.Column("role", sa.String(length=24), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tool", sa.String(length=64), nullable=True),
            sa.Column("response", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("agent_message", "ix_agent_message_conversation_created", ["conversation_id", "created_at"])
    create_index_if_missing("agent_message", "ix_agent_message_role", ["role"])


def downgrade():
    drop_index_if_exists("agent_message", "ix_agent_message_role")
    drop_index_if_exists("agent_message", "ix_agent_message_conversation_created")
    op.drop_table("agent_message")
    drop_index_if_exists("agent_conversation", "ix_agent_conversation_status")
    drop_index_if_exists("agent_conversation", "ix_agent_conversation_owner_updated")
    op.drop_table("agent_conversation")


def create_index_if_missing(table_name, index_name, columns):
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def drop_index_if_exists(table_name, index_name):
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if table_name not in tables:
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
