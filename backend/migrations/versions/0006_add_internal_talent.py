"""add internal talent organization and employee tables

Revision ID: 0006_add_internal_talent
Revises: 0005_add_llm_usage_context
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_internal_talent"
down_revision = "0005_add_llm_usage_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_unit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("organization_unit.id"), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("unit_type", sa.String(length=32), nullable=False),
        sa.Column("manager_employee_id", sa.Integer(), nullable=True),
        sa.Column("hrbp_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("headcount_plan", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_org_parent_sort", "organization_unit", ["parent_id", "sort_order"])
    op.create_index("ix_org_status_type", "organization_unit", ["status", "unit_type"])

    op.create_table(
        "employee_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=True),
        sa.Column("organization_unit_id", sa.Integer(), sa.ForeignKey("organization_unit.id"), nullable=True),
        sa.Column("current_job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=True),
        sa.Column("owner_hr_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("employee_no", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("current_title", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("employment_status", sa.String(length=24), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("manager_name", sa.String(length=64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("resume_json", sa.JSON(), nullable=False),
        sa.Column("parse_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("employee_no", name="uq_employee_no"),
    )
    op.create_index("ix_employee_org_status", "employee_profile", ["organization_unit_id", "employment_status"])
    op.create_index("ix_employee_candidate", "employee_profile", ["candidate_id"])
    op.create_index("ix_employee_job_status", "employee_profile", ["current_job_id", "employment_status"])

    op.create_table(
        "employee_compensation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee_profile.id"), nullable=False),
        sa.Column("salary_monthly_k", sa.Float(), nullable=True),
        sa.Column("salary_annual_k", sa.Float(), nullable=True),
        sa.Column("salary_months", sa.Integer(), nullable=False),
        sa.Column("bonus_k", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_employee_comp_employee_effective", "employee_compensation", ["employee_id", "effective_date"])

    op.create_table(
        "employee_analysis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee_profile.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=True),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("salary_score", sa.Integer(), nullable=False),
        sa.Column("salary_status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_employee_analysis_employee_created", "employee_analysis", ["employee_id", "created_at"])
    op.create_index("ix_employee_analysis_job_score", "employee_analysis", ["job_id", "match_score"])

    op.create_table(
        "employee_recommendation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee_profile.id"), nullable=False),
        sa.Column("recommendation_type", sa.String(length=32), nullable=False),
        sa.Column("target_job_id", sa.Integer(), sa.ForeignKey("job.id"), nullable=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidate.id"), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_employee_recommendation_employee_type", "employee_recommendation", ["employee_id", "recommendation_type"])
    op.create_index("ix_employee_recommendation_score", "employee_recommendation", ["score"])


def downgrade():
    op.drop_index("ix_employee_recommendation_score", table_name="employee_recommendation")
    op.drop_index("ix_employee_recommendation_employee_type", table_name="employee_recommendation")
    op.drop_table("employee_recommendation")
    op.drop_index("ix_employee_analysis_job_score", table_name="employee_analysis")
    op.drop_index("ix_employee_analysis_employee_created", table_name="employee_analysis")
    op.drop_table("employee_analysis")
    op.drop_index("ix_employee_comp_employee_effective", table_name="employee_compensation")
    op.drop_table("employee_compensation")
    op.drop_index("ix_employee_job_status", table_name="employee_profile")
    op.drop_index("ix_employee_candidate", table_name="employee_profile")
    op.drop_index("ix_employee_org_status", table_name="employee_profile")
    op.drop_table("employee_profile")
    op.drop_index("ix_org_status_type", table_name="organization_unit")
    op.drop_index("ix_org_parent_sort", table_name="organization_unit")
    op.drop_table("organization_unit")
