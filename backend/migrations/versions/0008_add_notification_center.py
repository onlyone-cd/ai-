"""add notification center

Revision ID: 0008_add_notification_center
Revises: 0007_add_employee_profile_demographics
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_notification_center"
down_revision = "0007_add_employee_profile_demographics"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "notification_channel" not in tables:
        op.create_table(
            "notification_channel",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("config_json", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("notification_channel", "ix_notification_channel_type_enabled", ["channel_type", "enabled"])
    create_index_if_missing("notification_channel", "ix_notification_channel_created", ["created_at"])

    tables = set(sa.inspect(bind).get_table_names())
    if "notification_event" not in tables:
        op.create_table(
            "notification_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("channel_id", sa.Integer(), sa.ForeignKey("notification_channel.id"), nullable=True),
            sa.Column("template_subject", sa.String(length=255), nullable=True),
            sa.Column("template_body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("event_type", name="uq_notification_event_type"),
        )
    create_index_if_missing("notification_event", "ix_notification_event_type_enabled", ["event_type", "enabled"])

    tables = set(sa.inspect(bind).get_table_names())
    if "notification_log" not in tables:
        op.create_table(
            "notification_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("channel_id", sa.Integer(), sa.ForeignKey("notification_channel.id"), nullable=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=True),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("provider_response", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("notification_log", "ix_notification_log_status_created", ["status", "created_at"])
    create_index_if_missing("notification_log", "ix_notification_log_event_created", ["event_type", "created_at"])
    create_index_if_missing("notification_log", "ix_notification_log_channel_created", ["channel_id", "created_at"])


def downgrade():
    op.drop_index("ix_notification_log_channel_created", table_name="notification_log")
    op.drop_index("ix_notification_log_event_created", table_name="notification_log")
    op.drop_index("ix_notification_log_status_created", table_name="notification_log")
    op.drop_table("notification_log")
    op.drop_index("ix_notification_event_type_enabled", table_name="notification_event")
    op.drop_table("notification_event")
    op.drop_index("ix_notification_channel_created", table_name="notification_channel")
    op.drop_index("ix_notification_channel_type_enabled", table_name="notification_channel")
    op.drop_table("notification_channel")


def create_index_if_missing(table_name, index_name, columns):
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)
