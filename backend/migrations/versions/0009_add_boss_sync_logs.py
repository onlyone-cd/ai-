"""add boss sync logs

Revision ID: 0009_add_boss_sync_logs
Revises: 0008_add_notification_center
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_boss_sync_logs"
down_revision = "0008_add_notification_center"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "boss_sync_job" not in tables:
        op.create_table(
            "boss_sync_job",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sync_type", sa.String(length=40), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("total_count", sa.Integer(), nullable=False),
            sa.Column("success_count", sa.Integer(), nullable=False),
            sa.Column("failed_count", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("parent_sync_job_id", sa.Integer(), sa.ForeignKey("boss_sync_job.id"), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("boss_sync_job", "ix_boss_sync_job_status_created", ["status", "created_at"])
    create_index_if_missing("boss_sync_job", "ix_boss_sync_job_type_created", ["sync_type", "created_at"])
    create_index_if_missing("boss_sync_job", "ix_boss_sync_job_parent", ["parent_sync_job_id"])

    tables = set(sa.inspect(bind).get_table_names())
    if "boss_sync_item" not in tables:
        op.create_table(
            "boss_sync_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sync_job_id", sa.Integer(), sa.ForeignKey("boss_sync_job.id"), nullable=False),
            sa.Column("item_type", sa.String(length=32), nullable=False),
            sa.Column("external_id", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("raw_summary", sa.String(length=512), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("boss_sync_item", "ix_boss_sync_item_job_status", ["sync_job_id", "status"])
    create_index_if_missing("boss_sync_item", "ix_boss_sync_item_external", ["external_id"])
    create_index_if_missing("boss_sync_item", "ix_boss_sync_item_target", ["target_type", "target_id"])


def downgrade():
    drop_index_if_exists("boss_sync_item", "ix_boss_sync_item_target")
    drop_index_if_exists("boss_sync_item", "ix_boss_sync_item_external")
    drop_index_if_exists("boss_sync_item", "ix_boss_sync_item_job_status")
    op.drop_table("boss_sync_item")
    drop_index_if_exists("boss_sync_job", "ix_boss_sync_job_parent")
    drop_index_if_exists("boss_sync_job", "ix_boss_sync_job_type_created")
    drop_index_if_exists("boss_sync_job", "ix_boss_sync_job_status_created")
    op.drop_table("boss_sync_job")


def create_index_if_missing(table_name, index_name, columns):
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def drop_index_if_exists(table_name, index_name):
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
