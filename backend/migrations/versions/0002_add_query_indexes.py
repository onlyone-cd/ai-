"""add query indexes

Revision ID: 0002_add_query_indexes
Revises: 0001_initial_schema
Create Date: 2026-07-06
"""

from alembic import op


revision = "0002_add_query_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_candidate_source_created_at", "candidate", ["source", "created_at"]),
    ("ix_candidate_phone_masked", "candidate", ["phone_masked"]),
    ("ix_candidate_email_masked", "candidate", ["email_masked"]),
    ("ix_candidate_owner_created_at", "candidate", ["owner_hr_id", "created_at"]),
    ("ix_upload_batch_owner_created_at", "upload_batch", ["owner_hr_id", "created_at"]),
    ("ix_upload_batch_source_created_at", "upload_batch", ["source", "created_at"]),
    ("ix_candidate_tag_candidate", "candidate_tag", ["candidate_id"]),
    ("ix_candidate_tag_tag", "candidate_tag", ["tag"]),
    ("ix_candidate_tag_category", "candidate_tag", ["category"]),
    ("ix_job_status_created_at", "job", ["status", "created_at"]),
    ("ix_job_job_code", "job", ["job_code"]),
    ("ix_job_owner_created_at", "job", ["owner_hr_id", "created_at"]),
    ("ix_match_job_score", "match", ["job_id", "score"]),
    ("ix_match_candidate", "match", ["candidate_id"]),
    ("ix_pipeline_stage_job_candidate_ts", "pipeline_stage", ["job_id", "candidate_id", "ts"]),
    ("ix_pipeline_stage_stage_ts", "pipeline_stage", ["stage", "ts"]),
    ("ix_pipeline_stage_candidate_ts", "pipeline_stage", ["candidate_id", "ts"]),
    ("ix_interview_assignment_status_time", "interview_assignment", ["status", "scheduled_at"]),
    ("ix_interview_assignment_interviewer_time", "interview_assignment", ["interviewer_id", "scheduled_at"]),
    ("ix_interview_assignment_candidate_job", "interview_assignment", ["candidate_id", "job_id"]),
    ("ix_interview_feedback_assignment_created", "interview_feedback", ["assignment_id", "created_at"]),
    ("ix_interview_feedback_interviewer_created", "interview_feedback", ["interviewer_id", "created_at"]),
    ("ix_offer_status_updated", "offer_record", ["status", "updated_at"]),
    ("ix_offer_candidate", "offer_record", ["candidate_id"]),
    ("ix_offer_job", "offer_record", ["job_id"]),
    ("ix_boss_draft_status_created", "boss_draft", ["status", "created_at"]),
    ("ix_boss_draft_candidate", "boss_draft", ["candidate_id"]),
    ("ix_boss_draft_job", "boss_draft", ["job_id"]),
    ("ix_boss_account_owner_updated", "boss_account", ["owner_hr_id", "updated_at"]),
    ("ix_audit_log_created_at", "audit_log", ["created_at"]),
    ("ix_audit_log_target_created", "audit_log", ["target_type", "target_id", "created_at"]),
    ("ix_audit_log_user_created", "audit_log", ["user_id", "created_at"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
