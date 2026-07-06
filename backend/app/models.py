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
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    tag = db.Column(db.String(64), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(32), nullable=False, default="其他")

    def to_dict(self):
        return {"tag": self.tag, "score": self.score, "category": self.category}


class Job(db.Model):
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


class AuditLog(db.Model):
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
