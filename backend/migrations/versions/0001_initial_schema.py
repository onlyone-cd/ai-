"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "upload_batch",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "candidate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("upload_batch_id", sa.String(length=64), nullable=False),
        sa.Column("name_masked", sa.String(length=64), nullable=False),
        sa.Column("email_masked", sa.String(length=128), nullable=True),
        sa.Column("phone_masked", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("resume_json", sa.JSON(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=24), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "candidate_tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("department", sa.String(length=64), nullable=True),
        sa.Column("job_code", sa.String(length=64), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("jd_structured", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "match",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "pipeline_stage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "interview_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("interviewer_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("round", sa.String(length=40), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ai_plan", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "interview_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("interview_assignment.id"), nullable=False),
        sa.Column("interviewer_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("risks", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "offer_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("salary_min_k", sa.Float(), nullable=True),
        sa.Column("salary_max_k", sa.Float(), nullable=True),
        sa.Column("salary_months", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "boss_draft",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "boss_account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("account", sa.String(length=128), nullable=False),
        sa.Column("cookie_hash", sa.String(length=64), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_name", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("audit_log")
    op.drop_table("boss_account")
    op.drop_table("boss_draft")
    op.drop_table("offer_record")
    op.drop_table("interview_feedback")
    op.drop_table("interview_assignment")
    op.drop_table("pipeline_stage")
    op.drop_table("match")
    op.drop_table("job")
    op.drop_table("candidate_tag")
    op.drop_table("candidate")
    op.drop_table("upload_batch")
    op.drop_table("user")
