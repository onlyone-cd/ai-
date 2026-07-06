from datetime import datetime, timezone

from . import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="recruiter")
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "name": self.name, "role": self.role, "active": self.active}


class Candidate(db.Model):
    __table_args__ = (
        db.Index("ix_candidate_source_created_at", "source", "created_at"),
        db.Index("ix_candidate_phone_masked", "phone_masked"),
        db.Index("ix_candidate_email_masked", "email_masked"),
        db.Index("ix_candidate_owner_created_at", "owner_hr_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    upload_batch_id = db.Column(db.String(64), nullable=False, default="seed")
    name_masked = db.Column(db.String(64), nullable=False)
    email_masked = db.Column(db.String(128), nullable=True)
    phone_masked = db.Column(db.String(64), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    source = db.Column(db.String(32), nullable=False, default="upload")
    city = db.Column(db.String(64), nullable=True)
    resume_json = db.Column(db.JSON, nullable=False, default=dict)
    raw_text = db.Column(db.Text, nullable=False)
    parse_status = db.Column(db.String(24), nullable=False, default="ok")
    parse_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    owner = db.relationship("User")
    tags = db.relationship("CandidateTag", cascade="all, delete-orphan", backref="candidate")

    def to_dict(self, detail=False):
        data = {
            "id": self.id,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "upload_batch_id": self.upload_batch_id,
            "name_masked": self.name_masked,
            "email_masked": self.email_masked,
            "phone_masked": self.phone_masked,
            "gender": self.resume_json.get("gender", ""),
            "title": self.title,
            "source": self.source,
            "city": self.city,
            "parse_status": self.parse_status,
            "created_at": self.created_at.isoformat(),
            "tags": [tag.to_dict() for tag in self.tags],
            "experience_analysis": self.resume_json.get("experience_analysis", {}),
        }
        if detail:
            data["resume_json"] = self.resume_json
            data["raw_text"] = self.raw_text
        return data


class UploadBatch(db.Model):
    __table_args__ = (
        db.Index("ix_upload_batch_owner_created_at", "owner_hr_id", "created_at"),
        db.Index("ix_upload_batch_source_created_at", "source", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source = db.Column(db.String(32), nullable=False, default="upload")
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="ok")
    total = db.Column(db.Integer, nullable=False, default=1)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    owner = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "source": self.source,
            "filename": self.filename,
            "status": self.status,
            "total": self.total,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


class CandidateTag(db.Model):
    __table_args__ = (
        db.Index("ix_candidate_tag_candidate", "candidate_id"),
        db.Index("ix_candidate_tag_tag", "tag"),
        db.Index("ix_candidate_tag_category", "category"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    tag = db.Column(db.String(64), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(32), nullable=False, default="其他")

    def to_dict(self):
        return {"tag": self.tag, "score": self.score, "category": self.category}


class Job(db.Model):
    __table_args__ = (
        db.Index("ix_job_status_created_at", "status", "created_at"),
        db.Index("ix_job_job_code", "job_code"),
        db.Index("ix_job_owner_created_at", "owner_hr_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    city = db.Column(db.String(64), nullable=True)
    department = db.Column(db.String(64), nullable=True)
    job_code = db.Column(db.String(64), nullable=True)
    jd_text = db.Column(db.Text, nullable=False)
    jd_structured = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(24), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    owner = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "title": self.title,
            "city": self.city,
            "department": self.department,
            "job_code": self.job_code,
            "jd_text": self.jd_text,
            "jd_structured": self.jd_structured,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class Match(db.Model):
    __table_args__ = (
        db.Index("ix_match_job_score", "job_id", "score"),
        db.Index("ix_match_candidate", "candidate_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    job = db.relationship("Job")
    candidate = db.relationship("Candidate")

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict(),
            "score": self.score,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


class PipelineStage(db.Model):
    __table_args__ = (
        db.Index("ix_pipeline_stage_job_candidate_ts", "job_id", "candidate_id", "ts"),
        db.Index("ix_pipeline_stage_stage_ts", "stage", "ts"),
        db.Index("ix_pipeline_stage_candidate_ts", "candidate_id", "ts"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    stage = db.Column(db.String(40), nullable=False, default="pending")
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    note = db.Column(db.Text, nullable=True)
    ts = db.Column(db.DateTime(timezone=True), default=utcnow)

    candidate = db.relationship("Candidate")
    job = db.relationship("Job")
    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict(),
            "job_id": self.job_id,
            "stage": self.stage,
            "updated_by": self.user.name if self.user else "",
            "note": self.note,
            "ts": self.ts.isoformat(),
        }


class InterviewAssignment(db.Model):
    __table_args__ = (
        db.Index("ix_interview_assignment_status_time", "status", "scheduled_at"),
        db.Index("ix_interview_assignment_interviewer_time", "interviewer_id", "scheduled_at"),
        db.Index("ix_interview_assignment_candidate_job", "candidate_id", "job_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    interviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    round = db.Column(db.String(40), nullable=False, default="interview_first")
    scheduled_at = db.Column(db.DateTime(timezone=True), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    note = db.Column(db.Text, nullable=True)
    ai_plan = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(24), nullable=False, default="scheduled")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    candidate = db.relationship("Candidate")
    job = db.relationship("Job")
    interviewer = db.relationship("User", foreign_keys=[interviewer_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict(),
            "job_id": self.job_id,
            "job": self.job.to_dict(),
            "interviewer_id": self.interviewer_id,
            "interviewer": self.interviewer.to_dict() if self.interviewer else None,
            "round": self.round,
            "scheduled_at": self.scheduled_at.isoformat(),
            "location": self.location,
            "note": self.note,
            "ai_plan": self.ai_plan or {},
            "status": self.status,
            "created_by": self.creator.name if self.creator else "",
            "created_at": self.created_at.isoformat(),
        }


class InterviewFeedback(db.Model):
    __table_args__ = (
        db.Index("ix_interview_feedback_assignment_created", "assignment_id", "created_at"),
        db.Index("ix_interview_feedback_interviewer_created", "interviewer_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("interview_assignment.id"), nullable=False)
    interviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    decision = db.Column(db.String(32), nullable=False)
    strengths = db.Column(db.Text, nullable=True)
    risks = db.Column(db.Text, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    assignment = db.relationship("InterviewAssignment")
    interviewer = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "interviewer_id": self.interviewer_id,
            "interviewer": self.interviewer.to_dict() if self.interviewer else None,
            "rating": self.rating,
            "decision": self.decision,
            "strengths": self.strengths,
            "risks": self.risks,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }


class OfferRecord(db.Model):
    __table_args__ = (
        db.Index("ix_offer_status_updated", "status", "updated_at"),
        db.Index("ix_offer_candidate", "candidate_id"),
        db.Index("ix_offer_job", "job_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    salary_min_k = db.Column(db.Float, nullable=True)
    salary_max_k = db.Column(db.Float, nullable=True)
    salary_months = db.Column(db.Integer, nullable=False, default=12)
    city = db.Column(db.String(64), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="draft")
    note = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    candidate = db.relationship("Candidate")
    job = db.relationship("Job")
    creator = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "job_id": self.job_id,
            "job": self.job.to_dict() if self.job else None,
            "salary_min_k": self.salary_min_k,
            "salary_max_k": self.salary_max_k,
            "salary_months": self.salary_months,
            "city": self.city,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "status": self.status,
            "note": self.note,
            "created_by": self.creator.name if self.creator else "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BossDraft(db.Model):
    __table_args__ = (
        db.Index("ix_boss_draft_status_created", "status", "created_at"),
        db.Index("ix_boss_draft_candidate", "candidate_id"),
        db.Index("ix_boss_draft_job", "job_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="draft")
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    candidate = db.relationship("Candidate")
    job = db.relationship("Job")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "job_id": self.job_id,
            "job": self.job.to_dict() if self.job else None,
            "status": self.status,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class BossAccount(db.Model):
    __table_args__ = (
        db.Index("ix_boss_account_owner_updated", "owner_hr_id", "updated_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    account = db.Column(db.String(128), nullable=False, default="BOSS 账号")
    cookie_hash = db.Column(db.String(64), nullable=False)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "account": self.account,
            "verified": self.verified,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BackgroundTask(db.Model):
    __table_args__ = (
        db.Index("ix_background_task_status_created", "status", "created_at"),
        db.Index("ix_background_task_type_status", "task_type", "status"),
        db.Index("ix_background_task_creator_created", "created_by", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="queued")
    payload = db.Column(db.JSON, nullable=False, default=dict)
    result = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.Text, nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    creator = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status,
            "payload": self.payload or {},
            "result": self.result or {},
            "error": self.error,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_by": self.created_by,
            "creator_name": self.creator.name if self.creator else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class LLMUsage(db.Model):
    __table_args__ = (
        db.Index("ix_llm_usage_created_at", "created_at"),
        db.Index("ix_llm_usage_provider_model", "provider", "model"),
        db.Index("ix_llm_usage_success_created", "success", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(64), nullable=False)
    model = db.Column(db.String(128), nullable=False)
    endpoint = db.Column(db.String(255), nullable=True)
    source = db.Column(db.String(80), nullable=True)
    tool_name = db.Column(db.String(120), nullable=True)
    api_path = db.Column(db.String(255), nullable=True)
    request_id = db.Column(db.String(64), nullable=True)
    success = db.Column(db.Boolean, nullable=False, default=True)
    status_code = db.Column(db.Integer, nullable=True)
    error = db.Column(db.Text, nullable=True)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    estimated = db.Column(db.Boolean, nullable=False, default=True)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    duration_ms = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "source": self.source,
            "tool_name": self.tool_name,
            "api_path": self.api_path,
            "request_id": self.request_id,
            "success": self.success,
            "status_code": self.status_code,
            "error": self.error,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated": self.estimated,
            "cost_usd": round(float(self.cost_usd or 0), 8),
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    __table_args__ = (
        db.Index("ix_audit_log_created_at", "created_at"),
        db.Index("ix_audit_log_target_created", "target_type", "target_id", "created_at"),
        db.Index("ix_audit_log_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    target_type = db.Column(db.String(64), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    target_name = db.Column(db.String(255), nullable=True)
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else "",
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "details": self.details or {},
            "created_at": self.created_at.isoformat(),
        }
