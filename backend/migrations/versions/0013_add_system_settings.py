"""add system settings

Revision ID: 0013_add_system_settings
Revises: 0012_add_agent_conversations
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_add_system_settings"
down_revision = "0012_add_agent_conversations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "system_setting" not in tables:
        op.create_table(
            "system_setting",
            sa.Column("key", sa.String(length=80), primary_key=True),
            sa.Column("group", sa.String(length=40), nullable=False, server_default="system"),
            sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("system_setting", "ix_system_setting_group", ["group"])


def downgrade():
    drop_index_if_exists("system_setting", "ix_system_setting_group")
    op.drop_table("system_setting")


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
