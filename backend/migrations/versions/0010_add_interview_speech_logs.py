"""add interview speech logs

Revision ID: 0010_add_interview_speech_logs
Revises: 0009_add_boss_sync_logs
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_interview_speech_logs"
down_revision = "0009_add_boss_sync_logs"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "interview_speech_log" not in tables:
        op.create_table(
            "interview_speech_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("interview_assignment.id"), nullable=False),
            sa.Column("operation", sa.String(length=16), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("transcript", sa.Text(), nullable=True),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("audio_bytes", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("meta_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("interview_speech_log", "ix_interview_speech_assignment_created", ["assignment_id", "created_at"])
    create_index_if_missing("interview_speech_log", "ix_interview_speech_operation_status", ["operation", "status"])


def downgrade():
    drop_index_if_exists("interview_speech_log", "ix_interview_speech_operation_status")
    drop_index_if_exists("interview_speech_log", "ix_interview_speech_assignment_created")
    op.drop_table("interview_speech_log")


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
