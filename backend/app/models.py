from datetime import datetime, timezone

from . import db


def utcnow():
    return datetime.now(timezone.utc)


def years_between(start, end):
    if not start or not end:
        return None
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return max(years, 0)


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
    attachments = db.relationship("ResumeAttachment", cascade="all, delete-orphan", backref="candidate")

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
            data["attachments"] = [attachment.to_dict() for attachment in self.attachments]
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


class ResumeAttachment(db.Model):
    __table_args__ = (
        db.Index("ix_resume_attachment_batch", "upload_batch_id"),
        db.Index("ix_resume_attachment_candidate", "candidate_id"),
        db.Index("ix_resume_attachment_owner_created", "owner_hr_id", "created_at"),
        db.Index("ix_resume_attachment_scan_status", "scan_status"),
        db.Index("ix_resume_attachment_sha256", "sha256"),
    )

    id = db.Column(db.Integer, primary_key=True)
    upload_batch_id = db.Column(db.String(64), db.ForeignKey("upload_batch.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source = db.Column(db.String(32), nullable=False, default="upload")
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(512), nullable=False)
    content_type = db.Column(db.String(128), nullable=True)
    extension = db.Column(db.String(24), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=False)
    scan_status = db.Column(db.String(24), nullable=False, default="clean")
    scan_summary = db.Column(db.String(255), nullable=False, default="")
    scan_flags = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    scanned_at = db.Column(db.DateTime(timezone=True), nullable=True)

    owner = db.relationship("User")
    upload_batch = db.relationship("UploadBatch")

    def to_dict(self):
        return {
            "id": self.id,
            "upload_batch_id": self.upload_batch_id,
            "candidate_id": self.candidate_id,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "source": self.source,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "content_type": self.content_type,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "scan_status": self.scan_status,
            "scan_summary": self.scan_summary,
            "scan_flags": self.scan_flags or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
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


class OrganizationUnit(db.Model):
    __table_args__ = (
        db.Index("ix_org_parent_sort", "parent_id", "sort_order"),
        db.Index("ix_org_status_type", "status", "unit_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("organization_unit.id"), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    unit_type = db.Column(db.String(32), nullable=False, default="department")
    manager_employee_id = db.Column(db.Integer, nullable=True)
    hrbp_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    city = db.Column(db.String(64), nullable=True)
    headcount_plan = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    parent = db.relationship("OrganizationUnit", remote_side=[id], backref="children", foreign_keys=[parent_id])
    hrbp = db.relationship("User", foreign_keys=[hrbp_user_id])

    def to_dict(self, include_counts=False):
        data = {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "unit_type": self.unit_type,
            "manager_employee_id": self.manager_employee_id,
            "manager_name": db.session.get(EmployeeProfile, self.manager_employee_id).name if self.manager_employee_id and db.session.get(EmployeeProfile, self.manager_employee_id) else "",
            "hrbp_user_id": self.hrbp_user_id,
            "hrbp_name": self.hrbp.name if self.hrbp else "",
            "city": self.city,
            "headcount_plan": self.headcount_plan,
            "status": self.status,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_counts:
            employee_count = EmployeeProfile.query.filter_by(organization_unit_id=self.id).count()
            data["employee_count"] = employee_count
            data["vacancy_count"] = max((self.headcount_plan or 0) - employee_count, 0) if self.headcount_plan else 0
        return data


class EmployeeProfile(db.Model):
    __table_args__ = (
        db.Index("ix_employee_org_status", "organization_unit_id", "employment_status"),
        db.Index("ix_employee_candidate", "candidate_id"),
        db.Index("ix_employee_job_status", "current_job_id", "employment_status"),
        db.UniqueConstraint("employee_no", name="uq_employee_no"),
    )

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=True)
    organization_unit_id = db.Column(db.Integer, db.ForeignKey("organization_unit.id"), nullable=True)
    current_job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=True)
    owner_hr_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    employee_no = db.Column(db.String(64), nullable=True)
    name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(128), nullable=True)
    department = db.Column(db.String(128), nullable=True)
    current_title = db.Column(db.String(128), nullable=False)
    level = db.Column(db.String(64), nullable=True)
    city = db.Column(db.String(64), nullable=True)
    employment_status = db.Column(db.String(24), nullable=False, default="active")
    hire_date = db.Column(db.Date, nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    education = db.Column(db.String(64), nullable=True)
    graduation_school = db.Column(db.String(128), nullable=True)
    graduation_date = db.Column(db.Date, nullable=True)
    manager_name = db.Column(db.String(64), nullable=True)
    raw_text = db.Column(db.Text, nullable=False, default="")
    resume_json = db.Column(db.JSON, nullable=False, default=dict)
    parse_status = db.Column(db.String(24), nullable=False, default="ok")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    candidate = db.relationship("Candidate")
    organization_unit = db.relationship("OrganizationUnit", foreign_keys=[organization_unit_id], backref="employees")
    current_job = db.relationship("Job")
    owner = db.relationship("User")
    compensations = db.relationship("EmployeeCompensation", cascade="all, delete-orphan", backref="employee", order_by="desc(EmployeeCompensation.effective_date)")
    analyses = db.relationship("EmployeeAnalysis", cascade="all, delete-orphan", backref="employee", order_by="desc(EmployeeAnalysis.created_at)")

    def latest_compensation(self):
        return self.compensations[0] if self.compensations else None

    def tags(self):
        return self.candidate.tags if self.candidate else []

    def to_dict(self, detail=False, include_salary=True):
        compensation = self.latest_compensation()
        data = {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "organization_unit_id": self.organization_unit_id,
            "organization_unit": self.organization_unit.to_dict() if self.organization_unit else None,
            "current_job_id": self.current_job_id,
            "current_job": self.current_job.to_dict() if self.current_job else None,
            "owner_hr_id": self.owner_hr_id,
            "owner_name": self.owner.name if self.owner else "",
            "employee_no": self.employee_no,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "department": self.department,
            "current_title": self.current_title,
            "level": self.level,
            "city": self.city,
            "employment_status": self.employment_status,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "age": years_between(self.birth_date, utcnow().date()) if self.birth_date else None,
            "seniority_years": years_between(self.hire_date, utcnow().date()) if self.hire_date else None,
            "education": self.education,
            "graduation_school": self.graduation_school,
            "graduation_date": self.graduation_date.isoformat() if self.graduation_date else None,
            "manager_name": self.manager_name,
            "parse_status": self.parse_status,
            "compensation": compensation.to_dict() if compensation and include_salary else None,
            "salary_hidden": bool(compensation and not include_salary),
            "tags": [tag.to_dict() for tag in self.tags()],
            "experience_analysis": (self.resume_json or {}).get("experience_analysis", {}),
            "analyses": [self.analyses[0].to_dict(include_salary=include_salary)] if self.analyses else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if detail:
            data["resume_json"] = self.resume_json or {}
            data["raw_text"] = self.raw_text or ""
            data["candidate"] = self.candidate.to_dict(detail=True) if self.candidate else None
            data["analyses"] = [analysis.to_dict(include_salary=include_salary) for analysis in self.analyses]
        return data


class EmployeeCompensation(db.Model):
    __table_args__ = (
        db.Index("ix_employee_comp_employee_effective", "employee_id", "effective_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee_profile.id"), nullable=False)
    salary_monthly_k = db.Column(db.Float, nullable=True)
    salary_annual_k = db.Column(db.Float, nullable=True)
    salary_months = db.Column(db.Integer, nullable=False, default=12)
    bonus_k = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(16), nullable=False, default="CNY")
    source = db.Column(db.String(32), nullable=False, default="manual")
    effective_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "salary_monthly_k": self.salary_monthly_k,
            "salary_annual_k": self.salary_annual_k,
            "salary_months": self.salary_months,
            "bonus_k": self.bonus_k,
            "currency": self.currency,
            "source": self.source,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmployeeAnalysis(db.Model):
    __table_args__ = (
        db.Index("ix_employee_analysis_employee_created", "employee_id", "created_at"),
        db.Index("ix_employee_analysis_job_score", "job_id", "match_score"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee_profile.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=True)
    match_score = db.Column(db.Integer, nullable=False, default=0)
    salary_score = db.Column(db.Integer, nullable=False, default=0)
    salary_status = db.Column(db.String(32), nullable=False, default="unknown")
    risk_level = db.Column(db.String(32), nullable=False, default="unknown")
    analysis_json = db.Column(db.JSON, nullable=False, default=dict)
    source = db.Column(db.String(32), nullable=False, default="rules")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    job = db.relationship("Job")

    def to_dict(self, include_salary=True):
        analysis = self.analysis_json or {}
        if not include_salary and isinstance(analysis, dict):
            analysis = dict(analysis)
            salary = dict(analysis.get("salary") or {})
            salary.pop("monthly_k", None)
            salary.pop("range", None)
            analysis["salary"] = salary
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "job_id": self.job_id,
            "job": self.job.to_dict() if self.job else None,
            "match_score": self.match_score,
            "salary_score": self.salary_score,
            "salary_status": self.salary_status,
            "risk_level": self.risk_level,
            "analysis": analysis,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmployeeRecommendation(db.Model):
    __table_args__ = (
        db.Index("ix_employee_recommendation_employee_type", "employee_id", "recommendation_type"),
        db.Index("ix_employee_recommendation_score", "score"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee_profile.id"), nullable=False)
    recommendation_type = db.Column(db.String(32), nullable=False)
    target_job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=True)
    score = db.Column(db.Integer, nullable=False, default=0)
    reason_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    employee = db.relationship("EmployeeProfile")
    target_job = db.relationship("Job")
    candidate = db.relationship("Candidate")

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "recommendation_type": self.recommendation_type,
            "target_job_id": self.target_job_id,
            "target_job": self.target_job.to_dict() if self.target_job else None,
            "candidate_id": self.candidate_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "score": self.score,
            "reason": self.reason_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
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


class InterviewSpeechLog(db.Model):
    __table_args__ = (
        db.Index("ix_interview_speech_assignment_created", "assignment_id", "created_at"),
        db.Index("ix_interview_speech_operation_status", "operation", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("interview_assignment.id"), nullable=False)
    operation = db.Column(db.String(16), nullable=False)
    provider = db.Column(db.String(64), nullable=False, default="browser")
    status = db.Column(db.String(24), nullable=False, default="succeeded")
    transcript = db.Column(db.Text, nullable=True)
    text = db.Column(db.Text, nullable=True)
    audio_bytes = db.Column(db.Integer, nullable=False, default=0)
    duration_ms = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.Text, nullable=True)
    meta_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    assignment = db.relationship("InterviewAssignment")

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "operation": self.operation,
            "provider": self.provider,
            "status": self.status,
            "transcript": self.transcript,
            "text": self.text,
            "audio_bytes": self.audio_bytes,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "meta": self.meta_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
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


class BossSyncJob(db.Model):
    __table_args__ = (
        db.Index("ix_boss_sync_job_status_created", "status", "created_at"),
        db.Index("ix_boss_sync_job_type_created", "sync_type", "created_at"),
        db.Index("ix_boss_sync_job_parent", "parent_sync_job_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(40), nullable=False)
    source = db.Column(db.String(32), nullable=False, default="api")
    status = db.Column(db.String(24), nullable=False, default="running")
    total_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    result_json = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.Text, nullable=True)
    parent_sync_job_id = db.Column(db.Integer, db.ForeignKey("boss_sync_job.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    creator = db.relationship("User")
    parent = db.relationship("BossSyncJob", remote_side=[id])
    items = db.relationship("BossSyncItem", cascade="all, delete-orphan", backref="sync_job", order_by="BossSyncItem.id.asc()")

    def to_dict(self, detail=False):
        data = {
            "id": self.id,
            "sync_type": self.sync_type,
            "source": self.source,
            "status": self.status,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "result": self.result_json or {},
            "error": self.error,
            "parent_sync_job_id": self.parent_sync_job_id,
            "created_by": self.created_by,
            "creator_name": self.creator.name if self.creator else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
        if detail:
            data["items"] = [item.to_dict() for item in self.items]
            data["payload"] = self.payload_json or {}
        return data


class BossSyncItem(db.Model):
    __table_args__ = (
        db.Index("ix_boss_sync_item_job_status", "sync_job_id", "status"),
        db.Index("ix_boss_sync_item_external", "external_id"),
        db.Index("ix_boss_sync_item_target", "target_type", "target_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sync_job_id = db.Column(db.Integer, db.ForeignKey("boss_sync_job.id"), nullable=False)
    item_type = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="pending")
    target_type = db.Column(db.String(32), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    error = db.Column(db.Text, nullable=True)
    raw_summary = db.Column(db.String(512), nullable=True)
    raw_payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "sync_job_id": self.sync_job_id,
            "item_type": self.item_type,
            "external_id": self.external_id,
            "status": self.status,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "error": self.error,
            "raw_summary": self.raw_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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


class NotificationChannel(db.Model):
    __table_args__ = (
        db.Index("ix_notification_channel_type_enabled", "channel_type", "enabled"),
        db.Index("ix_notification_channel_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    channel_type = db.Column(db.String(32), nullable=False, default="webhook")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    config_json = db.Column(db.JSON, nullable=False, default=dict)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    creator = db.relationship("User")

    def to_dict(self, include_secret=False):
        config = dict(self.config_json or {})
        if not include_secret:
            for key in list(config):
                if any(word in key.lower() for word in ["secret", "token", "key", "password", "webhook_url"]):
                    config[key] = "***" if config[key] else ""
        return {
            "id": self.id,
            "name": self.name,
            "channel_type": self.channel_type,
            "enabled": self.enabled,
            "config": config,
            "created_by": self.created_by,
            "creator_name": self.creator.name if self.creator else "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationEvent(db.Model):
    __table_args__ = (
        db.Index("ix_notification_event_type_enabled", "event_type", "enabled"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(128), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("notification_channel.id"), nullable=True)
    template_subject = db.Column(db.String(255), nullable=True)
    template_body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    channel = db.relationship("NotificationChannel")

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "name": self.name,
            "enabled": self.enabled,
            "channel_id": self.channel_id,
            "channel": self.channel.to_dict() if self.channel else None,
            "template_subject": self.template_subject,
            "template_body": self.template_body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationLog(db.Model):
    __table_args__ = (
        db.Index("ix_notification_log_status_created", "status", "created_at"),
        db.Index("ix_notification_log_event_created", "event_type", "created_at"),
        db.Index("ix_notification_log_channel_created", "channel_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("notification_channel.id"), nullable=True)
    event_type = db.Column(db.String(80), nullable=False, default="manual_test")
    recipient = db.Column(db.String(255), nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="queued")
    provider_response = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    channel = db.relationship("NotificationChannel")
    creator = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "channel": self.channel.to_dict() if self.channel else None,
            "event_type": self.event_type,
            "recipient": self.recipient,
            "subject": self.subject,
            "content": self.content,
            "status": self.status,
            "provider_response": self.provider_response or {},
            "error": self.error,
            "created_by": self.created_by,
            "creator_name": self.creator.name if self.creator else "",
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
