"""add resume attachments

Revision ID: 0011_add_resume_attachments
Revises: 0010_add_interview_speech_logs
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_resume_attachments"
down_revision = "0010_add_interview_speech_logs"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "resume_attachment" not in tables:
        op.create_table(
            "resume_attachment",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("upload_batch_id", sa.String(length=64), sa.ForeignKey("upload_batch.id"), nullable=False),
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=True),
            sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=True),
            sa.Column("extension", sa.String(length=24), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("scan_status", sa.String(length=24), nullable=False),
            sa.Column("scan_summary", sa.String(length=255), nullable=False),
            sa.Column("scan_flags", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        )
    create_index_if_missing("resume_attachment", "ix_resume_attachment_batch", ["upload_batch_id"])
    create_index_if_missing("resume_attachment", "ix_resume_attachment_candidate", ["candidate_id"])
    create_index_if_missing("resume_attachment", "ix_resume_attachment_owner_created", ["owner_hr_id", "created_at"])
    create_index_if_missing("resume_attachment", "ix_resume_attachment_scan_status", ["scan_status"])
    create_index_if_missing("resume_attachment", "ix_resume_attachment_sha256", ["sha256"])


def downgrade():
    drop_index_if_exists("resume_attachment", "ix_resume_attachment_sha256")
    drop_index_if_exists("resume_attachment", "ix_resume_attachment_scan_status")
    drop_index_if_exists("resume_attachment", "ix_resume_attachment_owner_created")
    drop_index_if_exists("resume_attachment", "ix_resume_attachment_candidate")
    drop_index_if_exists("resume_attachment", "ix_resume_attachment_batch")
    op.drop_table("resume_attachment")


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
