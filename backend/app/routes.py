from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
from io import BytesIO, StringIO
from pathlib import Path
import re
from time import time
from xml.etree import ElementTree
import zipfile

import jwt
from flask import Blueprint, Response, current_app, request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from . import db, production_config_checks
from .auth import hash_password, issue_token, login_required, roles_required, validate_password_strength, verify_password
from .job_service import build_jd_structured, ensure_jd_structured, persist_matches, preview_matches
from .llm_client import LLMError, chat_json, llm_available, llm_status
from .matching import match_candidate
from .models import AuditLog, BackgroundTask, BossAccount, BossDraft, Candidate, CandidateTag, EmployeeAnalysis, EmployeeCompensation, EmployeeProfile, EmployeeRecommendation, InterviewAssignment, InterviewFeedback, Job, LLMUsage, Match, OfferRecord, OrganizationUnit, PipelineStage, User, years_between
from .rbac import ROLES, role_permissions
from .resume_service import ARCHIVE_EXTENSIONS, parse_and_save_archive, parse_and_save_resume, parse_and_save_text, reparse_candidate
from .responses import error, ok
from .tag_library import label_map, load_labels
from .task_service import enqueue_task, retry_task

api = Blueprint("api", __name__)

STAGES = ["pending", "ai_screen", "business_review", "interview_first", "interview_second", "offer", "onboarded", "rejected"]
OFFER_STATUSES = {"draft", "sent", "accepted", "declined", "cancelled"}
LOGIN_FAILURES = {}
PUBLIC_INTERVIEW_REQUESTS = {}


@api.post("/auth/login")
def login():
    payload = request.get_json(force=True)
    username = str(payload.get("username") or "").strip()
    lock_key = login_failure_key(username)
    retry_after = login_retry_after(lock_key)
    if retry_after > 0:
        return error("登录失败次数过多，请稍后再试", "LOGIN_LOCKED", 429, {"retry_after_seconds": retry_after})
    user = User.query.filter_by(username=username, active=True).first()
    if not user or not verify_password(payload.get("password", ""), user.password_hash):
        retry_after = record_login_failure(lock_key)
        if retry_after > 0:
            return error("登录失败次数过多，请稍后再试", "LOGIN_LOCKED", 429, {"retry_after_seconds": retry_after})
        return error("用户名或密码错误", "INVALID_CREDENTIALS", 401)
    LOGIN_FAILURES.pop(lock_key, None)
    return ok({"token": issue_token(user), "user": with_permissions(user)})


@api.get("/auth/me")
@login_required
def me(user):
    return ok(with_permissions(user))


@api.get("/auth/permissions")
@login_required
def permissions(user):
    return ok({"role": user.role, "roles": list(ROLES), "permissions": role_permissions(user.role)})


@api.get("/system/llm/status")
@login_required
@roles_required("admin", "manager")
def system_llm_status(user):
    return ok(llm_status())


@api.get("/system/readiness")
@login_required
@roles_required("admin", "manager")
def system_readiness(user):
    checks = production_config_checks(current_app)
    error_count = sum(1 for item in checks if not item["ok"] and item["severity"] == "error")
    warning_count = sum(1 for item in checks if not item["ok"] and item["severity"] == "warning")
    return ok(
        {
            "ready": error_count == 0,
            "environment": current_app.config["ENVIRONMENT"],
            "database": db.engine.dialect.name,
            "checks": checks,
            "summary": {"errors": error_count, "warnings": warning_count, "total": len(checks)},
        }
    )


@api.get("/system/llm/usage")
@login_required
@roles_required("admin", "manager")
def system_llm_usage(user):
    days = max(1, min(request.args.get("days", 30, type=int) or 30, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base_query = LLMUsage.query.filter(LLMUsage.created_at >= since)
    rows = base_query.all()
    total_calls = len(rows)
    failed_calls = len([item for item in rows if not item.success])
    prompt_tokens = sum(item.prompt_tokens or 0 for item in rows)
    completion_tokens = sum(item.completion_tokens or 0 for item in rows)
    total_tokens = prompt_tokens + completion_tokens
    total_cost_usd = sum(float(item.cost_usd or 0) for item in rows)
    query = base_query.order_by(LLMUsage.created_at.desc())
    items, meta = paginate_query(query, default_limit=50, max_limit=200)
    return ok(
        {
            "period_days": days,
            "summary": {
                "total_calls": total_calls,
                "failed_calls": failed_calls,
                "success_rate": round(((total_calls - failed_calls) / total_calls * 100), 2) if total_calls else 100,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost_usd": round(total_cost_usd, 6),
            },
            "items": [item.to_dict() for item in items],
            **meta,
        }
    )


@api.get("/tasks")
@login_required
@roles_required("admin", "manager", "recruiter")
def list_tasks(user):
    query = BackgroundTask.query.order_by(BackgroundTask.created_at.desc())
    status = request.args.get("status")
    task_type = request.args.get("task_type")
    if status and status != "all":
        query = query.filter_by(status=status)
    if task_type:
        query = query.filter_by(task_type=task_type)
    if user.role == "recruiter":
        query = query.filter_by(created_by=user.id)
    tasks, meta = paginate_query(query)
    count_base = BackgroundTask.query
    if task_type:
        count_base = count_base.filter_by(task_type=task_type)
    if user.role == "recruiter":
        count_base = count_base.filter_by(created_by=user.id)
    status_counts = {status_name: count_base.filter_by(status=status_name).count() for status_name in ["queued", "running", "succeeded", "failed"]}
    return ok({"items": [task.to_dict() for task in tasks], "status_counts": status_counts, **meta})


@api.get("/tasks/<int:task_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def get_task(user, task_id):
    task = db.session.get(BackgroundTask, task_id)
    if not task:
        return error("后台任务不存在", "NOT_FOUND", 404)
    if user.role == "recruiter" and task.created_by != user.id:
        return error("无权查看该后台任务", "FORBIDDEN", 403)
    return ok(task.to_dict())


@api.post("/tasks/<int:task_id>/retry")
@login_required
@roles_required("admin", "manager", "recruiter")
def retry_background_task(user, task_id):
    task = db.session.get(BackgroundTask, task_id)
    if not task:
        return error("后台任务不存在", "NOT_FOUND", 404)
    if user.role == "recruiter" and task.created_by != user.id:
        return error("无权重试该后台任务", "FORBIDDEN", 403)
    try:
        task = retry_task(task)
    except ValueError as exc:
        return error(str(exc), "TASK_NOT_RETRYABLE", 409)
    audit_log(user, "retry", "background_task", task.id, task.task_type)
    db.session.commit()
    return ok(task.to_dict(), "后台任务已重新排队")


def pagination_params(default_limit=50, max_limit=200):
    limit = request.args.get("limit", default_limit, type=int)
    offset = request.args.get("offset", 0, type=int)
    if limit is None or limit <= 0:
        limit = default_limit
    if offset is None or offset < 0:
        offset = 0
    limit = min(limit, max_limit)
    return limit, offset


def pagination_meta(total, limit, offset):
    return {"total": total, "limit": limit, "offset": offset, "has_more": offset + limit < total}


def paginate_query(query, default_limit=50, max_limit=200):
    limit, offset = pagination_params(default_limit, max_limit)
    total = query.count()
    items = query.limit(limit).offset(offset).all()
    return items, pagination_meta(total, limit, offset)


def paginate_items(items, default_limit=50, max_limit=200):
    limit, offset = pagination_params(default_limit, max_limit)
    total = len(items)
    return items[offset : offset + limit], pagination_meta(total, limit, offset)


@api.get("/users")
@login_required
@roles_required("admin")
def list_users(user):
    users, meta = paginate_query(User.query.order_by(User.id.asc()))
    return ok({"items": [with_permissions(item) for item in users], **meta})


@api.get("/users/interviewers")
@login_required
def list_interviewers(user):
    users = User.query.filter(User.active.is_(True), User.role.in_(["admin", "manager", "interviewer"])).order_by(User.id.asc()).all()
    return ok({"items": [item.to_dict() for item in users]})


@api.get("/audit/logs")
@login_required
@roles_required("admin", "manager")
def list_audit_logs(user):
    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    target_type = request.args.get("target_type")
    if target_type:
        query = query.filter_by(target_type=target_type)
    logs, meta = paginate_query(query, default_limit=100, max_limit=500)
    return ok({"items": [item.to_dict() for item in logs], **meta})


@api.post("/users")
@login_required
@roles_required("admin")
def create_user(user):
    payload = request.get_json(force=True)
    username = (payload.get("username") or "").strip()
    name = (payload.get("name") or "").strip()
    role = payload.get("role") or "recruiter"
    password = payload.get("password") or ""

    if not username or not name or not password:
        return error("用户名、姓名和密码必填")
    if role not in ROLES:
        return error("角色不合法", details={"roles": ROLES})
    password_error = validate_password_strength(password)
    if password_error:
        return error(password_error, "WEAK_PASSWORD")

    new_user = User(username=username, name=name, role=role, password_hash=hash_password(password), active=True)
    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("用户名已存在", "CONFLICT", 409)
    return ok(with_permissions(new_user), "用户已创建")


@api.patch("/users/<int:user_id>")
@login_required
@roles_required("admin")
def update_user(user, user_id):
    target = db.session.get(User, user_id)
    if not target:
        return error("用户不存在", "NOT_FOUND", 404)

    payload = request.get_json(force=True)
    if "name" in payload:
        target.name = (payload.get("name") or target.name).strip()
    if "role" in payload:
        if payload["role"] not in ROLES:
            return error("角色不合法", details={"roles": ROLES})
        target.role = payload["role"]
    if "active" in payload:
        if target.id == user.id and payload["active"] is False:
            return error("不能禁用当前登录账号", "CONFLICT", 409)
        target.active = bool(payload["active"])
    if payload.get("password"):
        password_error = validate_password_strength(payload["password"])
        if password_error:
            return error(password_error, "WEAK_PASSWORD")
        target.password_hash = hash_password(payload["password"])
    audit_log(user, "update", "user", target.id, target.name, {"role": target.role, "active": target.active})
    db.session.commit()
    return ok(with_permissions(target), "用户已更新")


@api.get("/organization/tree")
@login_required
@roles_required("admin", "manager", "recruiter")
def organization_tree(user):
    ensure_default_organization(user)
    units = OrganizationUnit.query.order_by(OrganizationUnit.parent_id.asc().nullsfirst(), OrganizationUnit.sort_order.asc(), OrganizationUnit.id.asc()).all()
    return ok({"items": build_organization_tree(units)})


@api.post("/organization/units")
@login_required
@roles_required("admin", "manager")
def create_organization_unit(user):
    payload = request.get_json(force=True)
    name = str(payload.get("name") or "").strip()
    if not name:
        return error("组织名称必填")
    unit = OrganizationUnit(
        parent_id=payload.get("parent_id"),
        name=name,
        unit_type=payload.get("unit_type") or "department",
        city=payload.get("city"),
        headcount_plan=parse_optional_int(payload.get("headcount_plan"), 0) or None,
        hrbp_user_id=payload.get("hrbp_user_id"),
        sort_order=parse_optional_int(payload.get("sort_order"), 0),
    )
    db.session.add(unit)
    db.session.flush()
    audit_log(user, "create", "organization_unit", unit.id, unit.name)
    db.session.commit()
    return ok(unit.to_dict(include_counts=True), "组织节点已创建")


@api.patch("/organization/units/<int:unit_id>")
@login_required
@roles_required("admin", "manager")
def update_organization_unit(user, unit_id):
    unit = db.session.get(OrganizationUnit, unit_id)
    if not unit:
        return error("组织节点不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    for field in ["name", "unit_type", "city", "status"]:
        if field in payload:
            setattr(unit, field, str(payload.get(field) or "").strip())
    for field in ["parent_id", "manager_employee_id", "hrbp_user_id"]:
        if field in payload:
            setattr(unit, field, payload.get(field) or None)
    if "headcount_plan" in payload:
        unit.headcount_plan = parse_optional_int(payload.get("headcount_plan"), 0) or None
    if "sort_order" in payload:
        unit.sort_order = parse_optional_int(payload.get("sort_order"), 0)
    audit_log(user, "update", "organization_unit", unit.id, unit.name)
    db.session.commit()
    return ok(unit.to_dict(include_counts=True), "组织节点已更新")


@api.delete("/organization/units/<int:unit_id>")
@login_required
@roles_required("admin", "manager")
def delete_organization_unit(user, unit_id):
    unit = db.session.get(OrganizationUnit, unit_id)
    if not unit:
        return error("组织节点不存在", "NOT_FOUND", 404)
    if OrganizationUnit.query.filter_by(parent_id=unit.id).first():
        return error("请先删除或调整下级组织", "ORG_HAS_CHILDREN", 409)
    if EmployeeProfile.query.filter_by(organization_unit_id=unit.id).first():
        return error("该组织下仍有员工，不能删除", "ORG_HAS_EMPLOYEES", 409)
    audit_log(user, "delete", "organization_unit", unit.id, unit.name)
    db.session.delete(unit)
    db.session.commit()
    return ok({"deleted": unit_id}, "组织节点已删除")


@api.post("/organization/import-excel")
@login_required
@roles_required("admin", "manager")
def import_organization_excel(user):
    file = request.files.get("file")
    if not file:
        return error("请上传组织架构 Excel")
    if Path(file.filename or "").suffix.lower() != ".xlsx":
        return error("仅支持 .xlsx 组织架构文件")
    root = ensure_default_organization(user)
    try:
        rows = parse_organization_xlsx(file.stream)
    except ValueError as exc:
        return error(str(exc))
    created = []
    current = {"level1": "", "level2": ""}
    for row in rows:
        row_level1 = row.get("一级部门")
        row_level2 = row.get("二级部门")
        if row_level1 and row_level1 != current["level1"]:
            current["level2"] = ""
        level1 = row_level1 or current["level1"]
        level2 = row_level2 or current["level2"]
        level3 = row.get("三级部门")
        if level1:
            current["level1"] = level1
            unit1 = get_or_create_org_unit(level1, root.id, "business_unit", len(created))
            if unit1["created"]:
                created.append(unit1["unit"])
        else:
            unit1 = {"unit": root, "created": False}
        if level2:
            current["level2"] = level2
            unit2 = get_or_create_org_unit(level2, unit1["unit"].id, "department", len(created))
            if unit2["created"]:
                created.append(unit2["unit"])
        else:
            unit2 = unit1
        if level3:
            unit3 = get_or_create_org_unit(level3, unit2["unit"].id, "team", len(created))
            if unit3["created"]:
                created.append(unit3["unit"])
    audit_log(user, "import", "organization_unit", root.id, root.name, {"created": len(created), "rows": len(rows), "filename": file.filename})
    db.session.commit()
    units = OrganizationUnit.query.order_by(OrganizationUnit.parent_id.asc().nullsfirst(), OrganizationUnit.sort_order.asc(), OrganizationUnit.id.asc()).all()
    return ok({"created": [unit.to_dict(include_counts=True) for unit in created], "tree": build_organization_tree(units)}, "组织架构已导入")


@api.post("/organization/units/<int:unit_id>/employee-resumes")
@login_required
@roles_required("admin", "manager", "recruiter")
def upload_employee_resumes_to_unit(user, unit_id):
    unit = db.session.get(OrganizationUnit, unit_id)
    if not unit:
        return error("组织节点不存在", "NOT_FOUND", 404)
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    if not files:
        return error("请上传员工简历文件")
    employees = []
    candidates = []
    errors = []
    for file in files:
        try:
            if Path(file.filename or "").suffix.lower() in ARCHIVE_EXTENSIONS:
                _, archive_candidates, archive_errors = parse_and_save_archive(file, user)
                errors.extend(archive_errors)
                parsed_candidates = archive_candidates
            else:
                _, candidate = parse_and_save_resume(file, user)
                parsed_candidates = [candidate]
            for candidate in parsed_candidates:
                candidates.append(candidate)
                employee, created = employee_from_candidate_record(candidate, user, unit)
                employees.append(employee)
        except Exception as exc:
            errors.append({"filename": file.filename, "error": str(exc)})
    db.session.commit()
    audit_log(user, "upload", "organization_unit", unit.id, unit.name, {"employees": len(employees), "errors": len(errors)})
    db.session.commit()
    return ok(
        {
            "unit": unit.to_dict(include_counts=True),
            "employees": [employee_payload(employee, user, detail=True) for employee in employees],
            "candidates": [candidate.to_dict(detail=True) for candidate in candidates],
            "errors": errors,
            "success_count": len(employees),
            "failed_count": len(errors),
        },
        "员工简历已上传并归入组织",
    )


@api.get("/organization/units/<int:unit_id>/employees")
@login_required
@roles_required("admin", "manager", "recruiter")
def organization_unit_employees(user, unit_id):
    unit = db.session.get(OrganizationUnit, unit_id)
    if not unit:
        return error("组织节点不存在", "NOT_FOUND", 404)
    unit_ids = organization_descendant_ids(unit_id)
    query = apply_employee_search(EmployeeProfile.query.filter(EmployeeProfile.organization_unit_id.in_(unit_ids)))
    query = query.order_by(EmployeeProfile.updated_at.desc())
    employees, meta = paginate_query(query, default_limit=20, max_limit=200)
    audit_log(user, "view", "organization_unit", unit.id, unit.name, {"scope": "employees"})
    db.session.commit()
    return ok({"unit": unit.to_dict(include_counts=True), "items": [employee_payload(employee, user) for employee in employees], **meta})


@api.get("/organization/units/<int:unit_id>/overview")
@login_required
@roles_required("admin", "manager", "recruiter")
def organization_unit_overview(user, unit_id):
    unit = db.session.get(OrganizationUnit, unit_id)
    if not unit:
        return error("组织节点不存在", "NOT_FOUND", 404)
    employees = EmployeeProfile.query.filter(EmployeeProfile.organization_unit_id.in_(organization_descendant_ids(unit_id))).all()
    overview = employee_group_overview(employees)
    overview["unit"] = unit.to_dict(include_counts=True)
    return ok(overview)


@api.get("/employees")
@login_required
@roles_required("admin", "manager", "recruiter")
def list_employees(user):
    ensure_default_organization(user)
    query = EmployeeProfile.query.order_by(EmployeeProfile.updated_at.desc())
    unit_id = request.args.get("organization_unit_id", type=int)
    if unit_id:
        query = query.filter(EmployeeProfile.organization_unit_id.in_(organization_descendant_ids(unit_id)))
    status = request.args.get("status")
    if status and status != "all":
        query = query.filter_by(employment_status=status)
    query = apply_employee_search(query)
    overview = employee_group_overview(query.all())
    employees, meta = paginate_query(query, default_limit=20, max_limit=200)
    return ok({"items": [employee_payload(employee, user) for employee in employees], "overview": overview, **meta})


@api.post("/employees/import-excel")
@login_required
@roles_required("admin", "manager")
def import_employees_excel(user):
    file = request.files.get("file")
    if not file:
        return error("请上传员工基础信息表")
    suffix = Path(file.filename or "").suffix.lower()
    try:
        if suffix == ".csv":
            rows = parse_csv_table(file.stream)
        elif suffix == ".xlsx":
            rows = parse_xlsx_table(file.stream)
        elif suffix == ".xls":
            rows = parse_xls_table(file.stream)
        else:
            return error("仅支持 .csv、.xlsx 或 .xls 员工基础信息表")
    except ValueError as exc:
        return error(str(exc))

    replace_all = str(request.args.get("replace") or "").lower() in {"1", "true", "yes"}
    if replace_all:
        reset_internal_talent_data()

    created = []
    updated = []
    skipped = []
    errors = []
    for index, row in enumerate(rows, start=2):
        try:
            employee, was_created = upsert_employee_from_import_row(row, user)
            if not employee:
                skipped.append({"row": index, "reason": "缺少姓名/岗位等必要字段", "data": row})
                continue
            compensation = build_employee_compensation(employee.id, compensation_payload_from_row(row))
            if compensation:
                db.session.add(compensation)
            employee.updated_at = datetime.now(timezone.utc)
            item = employee_payload(employee, user, detail=True)
            if was_created:
                created.append({"row": index, "employee": item})
            else:
                updated.append({"row": index, "employee": item})
        except ValueError as exc:
            errors.append({"row": index, "error": str(exc), "data": row})
    audit_log(user, "import", "employee", None, file.filename, {"created": len(created), "updated": len(updated), "skipped": len(skipped), "errors": len(errors), "replace": replace_all})
    db.session.commit()
    return ok(
        {
            "created_count": len(created),
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "failed_count": len(errors),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        },
        "员工基础信息已导入",
    )


@api.get("/employees/<int:employee_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def get_employee(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    audit_log(user, "view", "employee", employee.id, employee.name, {"detail": True})
    db.session.commit()
    return ok(employee_payload(employee, user, detail=True))


@api.post("/employees/from-candidate")
@login_required
@roles_required("admin", "manager", "recruiter")
def create_employee_from_candidate(user):
    payload = request.get_json(force=True)
    candidate = db.session.get(Candidate, payload.get("candidate_id"))
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    existing = EmployeeProfile.query.filter_by(candidate_id=candidate.id).first()
    if existing:
        return ok(employee_payload(existing, user, detail=True), "候选人已转为内部员工，无需重复创建")
    unit = db.session.get(OrganizationUnit, payload.get("organization_unit_id")) if payload.get("organization_unit_id") else ensure_default_organization(user)
    job = db.session.get(Job, payload.get("current_job_id")) if payload.get("current_job_id") else None
    employee, _ = employee_from_candidate_record(candidate, user, unit, job=job, payload=payload)
    compensation = build_employee_compensation(employee.id, payload) if can_view_employee_salary(user) else None
    if compensation:
        db.session.add(compensation)
    audit_log(user, "create", "employee", employee.id, employee.name, {"candidate_id": candidate.id})
    db.session.commit()
    return ok(employee_payload(employee, user, detail=True), "候选人已转为内部员工")


@api.patch("/employees/<int:employee_id>")
@login_required
@roles_required("admin", "manager")
def update_employee(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    for field in ["employee_no", "name", "phone", "email", "department", "current_title", "level", "city", "employment_status", "manager_name", "education", "graduation_school"]:
        if field in payload:
            setattr(employee, field, str(payload.get(field) or "").strip())
    for field in ["organization_unit_id", "current_job_id"]:
        if field in payload:
            setattr(employee, field, payload.get(field) or None)
    if "hire_date" in payload:
        employee.hire_date = parse_date(payload.get("hire_date"))
    if "birth_date" in payload:
        employee.birth_date = parse_date(payload.get("birth_date"))
    if "graduation_date" in payload:
        employee.graduation_date = parse_date(payload.get("graduation_date"))
    compensation = build_employee_compensation(employee.id, payload)
    if compensation:
        db.session.add(compensation)
    audit_log(user, "update", "employee", employee.id, employee.name)
    db.session.commit()
    return ok(employee_payload(employee, user, detail=True), "员工档案已更新")


@api.delete("/employees/<int:employee_id>")
@login_required
@roles_required("admin", "manager")
def delete_employee(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    audit_log(user, "delete", "employee", employee.id, employee.name, {"candidate_id": employee.candidate_id})
    db.session.delete(employee)
    db.session.commit()
    return ok({"deleted": employee_id}, "内部员工档案已删除，原候选人档案已保留")


@api.post("/employees/compensation-import")
@login_required
@roles_required("admin", "manager")
def import_employee_compensations(user):
    file = request.files.get("file")
    if not file:
        return error("请上传员工薪资表")
    suffix = Path(file.filename or "").suffix.lower()
    try:
        if suffix == ".csv":
            rows = parse_csv_table(file.stream)
        elif suffix == ".xlsx":
            rows = parse_xlsx_table(file.stream)
        elif suffix == ".xls":
            rows = parse_xls_table(file.stream)
        else:
            return error("仅支持 .csv、.xlsx 或 .xls 薪资表")
    except ValueError as exc:
        return error(str(exc))

    updated = []
    skipped = []
    errors = []
    for index, row in enumerate(rows, start=2):
        try:
            employee = find_employee_for_compensation_row(row)
            if not employee:
                skipped.append({"row": index, "reason": "未匹配到员工", "data": row})
                continue
            payload = compensation_payload_from_row(row)
            compensation = build_employee_compensation(employee.id, payload)
            if not compensation:
                skipped.append({"row": index, "reason": "薪资字段为空", "employee": employee.name})
                continue
            db.session.add(compensation)
            employee.updated_at = datetime.now(timezone.utc)
            updated.append({"row": index, "employee": employee.to_dict(), "compensation": compensation.to_dict()})
        except ValueError as exc:
            errors.append({"row": index, "error": str(exc), "data": row})
    audit_log(user, "import", "employee_compensation", None, file.filename, {"updated": len(updated), "skipped": len(skipped), "errors": len(errors)})
    db.session.commit()
    return ok(
        {
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "failed_count": len(errors),
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        },
        "员工薪资已导入",
    )


@api.post("/employees/<int:employee_id>/analyze-current-job")
@login_required
@roles_required("admin", "manager", "recruiter")
def analyze_employee_current_job(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    analysis = analyze_employee_against_job(employee, employee.current_job)
    db.session.add(analysis)
    audit_log(user, "analyze", "employee", employee.id, employee.name, {"job_id": employee.current_job_id})
    db.session.commit()
    return ok(analysis.to_dict(include_salary=can_view_employee_salary(user)), "员工岗位与薪资分析已完成")


@api.post("/employees/<int:employee_id>/recommend-transfer")
@login_required
@roles_required("admin", "manager", "recruiter")
def recommend_employee_transfer(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    EmployeeRecommendation.query.filter_by(employee_id=employee.id, recommendation_type="transfer").delete()
    items = []
    for job in Job.query.filter_by(status="active").order_by(Job.created_at.desc()).all():
        if job.id == employee.current_job_id:
            continue
        reason = match_employee_to_job(employee, job)
        if reason["score"] < 50:
            continue
        recommendation = EmployeeRecommendation(employee_id=employee.id, recommendation_type="transfer", target_job_id=job.id, score=reason["score"], reason_json=reason)
        db.session.add(recommendation)
        db.session.flush()
        items.append(recommendation.to_dict())
    items.sort(key=lambda item: item["score"], reverse=True)
    audit_log(user, "recommend", "employee", employee.id, employee.name, {"type": "transfer", "count": len(items)})
    db.session.commit()
    return ok({"items": items}, "调岗推荐已生成")


@api.post("/employees/<int:employee_id>/recommend-replacement")
@login_required
@roles_required("admin", "manager", "recruiter")
def recommend_employee_replacement(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    if not employee.current_job:
        return error("员工未绑定当前岗位，无法推荐替补")
    EmployeeRecommendation.query.filter_by(employee_id=employee.id, recommendation_type="replacement").delete()
    items = []
    for item in preview_matches(employee.current_job, limit=20):
        if item["candidate_id"] == employee.candidate_id:
            continue
        candidate = db.session.get(Candidate, item["candidate_id"])
        if not candidate or EmployeeProfile.query.filter_by(candidate_id=item["candidate_id"]).first():
            continue
        reason = item["reason"]
        reason["summary"] = "候选人与员工当前岗位 JD 匹配，可作为离职替补候选。"
        recommendation = EmployeeRecommendation(employee_id=employee.id, recommendation_type="replacement", candidate_id=candidate.id, score=item["score"], reason_json=reason)
        db.session.add(recommendation)
        db.session.flush()
        items.append(recommendation.to_dict())
    items.sort(key=lambda item: item["score"], reverse=True)
    audit_log(user, "recommend", "employee", employee.id, employee.name, {"type": "replacement", "count": len(items)})
    db.session.commit()
    return ok({"items": items}, "离职替补推荐已生成")


@api.post("/employees/batch-analyze")
@login_required
@roles_required("admin", "manager")
def batch_analyze_employees(user):
    payload = request.get_json(silent=True) or {}
    query = EmployeeProfile.query.order_by(EmployeeProfile.updated_at.desc())
    unit_id = payload.get("organization_unit_id") or request.args.get("organization_unit_id", type=int)
    if unit_id:
        query = query.filter(EmployeeProfile.organization_unit_id.in_(organization_descendant_ids(int(unit_id))))
    employee_ids = payload.get("employee_ids") or []
    if employee_ids:
        query = query.filter(EmployeeProfile.id.in_([int(employee_id) for employee_id in employee_ids]))
    limit = min(parse_optional_int(payload.get("limit"), 100) or 100, 300)
    employees = query.limit(limit).all()
    analyzed = []
    skipped = []
    for employee in employees:
        if not employee.current_job:
            skipped.append({"employee_id": employee.id, "name": employee.name, "reason": "未绑定当前岗位"})
            continue
        analysis = analyze_employee_against_job(employee, employee.current_job)
        db.session.add(analysis)
        db.session.flush()
        analyzed.append(analysis.to_dict())
    audit_log(user, "batch_analyze", "employee", None, "内部员工批量分析", {"count": len(analyzed), "skipped": len(skipped), "organization_unit_id": unit_id})
    db.session.commit()
    return ok({"items": analyzed, "skipped": skipped, "analyzed_count": len(analyzed), "skipped_count": len(skipped)}, "内部员工批量分析已完成")


@api.get("/employees/<int:employee_id>/report.txt")
@login_required
@roles_required("admin", "manager", "recruiter")
def employee_report(user, employee_id):
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        return error("员工不存在", "NOT_FOUND", 404)
    audit_log(user, "export", "employee", employee.id, employee.name, {"kind": "report"})
    db.session.commit()
    body = employee_report_text(employee, include_salary=can_view_employee_salary(user))
    return Response(body, mimetype="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=employee-{employee.id}-report.txt"})


@api.get("/candidates")
@login_required
@roles_required("admin", "manager", "recruiter")
def list_candidates(user):
    query = Candidate.query.order_by(Candidate.created_at.desc())
    experience_level = request.args.get("experience_level")
    if experience_level and experience_level != "all":
        filtered = [
            candidate
            for candidate in query.all()
            if candidate.resume_json.get("experience_analysis", {}).get("level") == experience_level
        ]
        candidates, meta = paginate_items(filtered)
    else:
        candidates, meta = paginate_query(query)
    return ok(
        {
            "items": [candidate.to_dict() for candidate in candidates],
            "experience_stats": experience_stats(candidates),
            "visible_scope": user.role,
            **meta,
        }
    )


@api.get("/candidates/<int:candidate_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def get_candidate(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    audit_log(user, "view", "candidate", candidate.id, candidate.name_masked, {"scope": "detail"})
    db.session.commit()
    return ok(candidate.to_dict(detail=True))


@api.get("/candidates/<int:candidate_id>/resume.txt")
@login_required
@roles_required("admin", "manager", "recruiter")
def export_candidate_resume(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    audit_log(user, "export", "candidate", candidate.id, candidate.name_masked, {"kind": "resume_txt", "filename": f"candidate-{candidate.id}-resume.txt"})
    db.session.commit()
    return Response(
        "\ufeff" + build_candidate_resume_text(candidate),
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=candidate-{candidate.id}-resume.txt"},
    )


@api.patch("/candidates/<int:candidate_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def update_candidate(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    for field in ["name_masked", "email_masked", "phone_masked", "title", "city"]:
        if field in payload:
            setattr(candidate, field, str(payload.get(field) or "").strip())
    resume_json = dict(candidate.resume_json or {})
    for source, target in {"gender": "gender", "summary": "summary", "name_masked": "name", "email_masked": "email", "phone_masked": "phone", "title": "title", "city": "city"}.items():
        if source in payload:
            resume_json[target] = str(payload.get(source) or "").strip()
    candidate.resume_json = resume_json
    audit_log(user, "update", "candidate", candidate.id, candidate.name_masked)
    db.session.commit()
    return ok(candidate.to_dict(detail=True), "候选人基础信息已更新")


@api.put("/candidates/<int:candidate_id>/tags")
@login_required
@roles_required("admin", "manager", "recruiter")
def replace_candidate_tags(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    labels = label_map()
    items = request.get_json(force=True).get("tags") or []
    cleaned_by_tag = {}
    for item in items:
        tag = str(item.get("tag") or "").strip()
        if tag not in labels:
            return error(f"标签不在标签库：{tag}", "VALIDATION_ERROR")
        try:
            score = int(item.get("score", 3))
        except (TypeError, ValueError):
            return error("标签分数必须是 1-5", "VALIDATION_ERROR")
        if score < 1 or score > 5:
            return error("标签分数必须是 1-5", "VALIDATION_ERROR")
        current = cleaned_by_tag.get(tag)
        if current is None or score > current["score"]:
            cleaned_by_tag[tag] = {"tag": tag, "score": score, "category": labels[tag].category}
    CandidateTag.query.filter_by(candidate_id=candidate.id).delete()
    for item in cleaned_by_tag.values():
        db.session.add(CandidateTag(candidate_id=candidate.id, **item))
    Match.query.filter_by(candidate_id=candidate.id).delete()
    audit_log(user, "update_tags", "candidate", candidate.id, candidate.name_masked, {"tag_count": len(cleaned_by_tag)})
    db.session.commit()
    return ok(candidate.to_dict(detail=True), "候选人技能标签已更新")


@api.delete("/candidates/<int:candidate_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def delete_candidate(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    Match.query.filter_by(candidate_id=candidate_id).delete()
    PipelineStage.query.filter_by(candidate_id=candidate_id).delete()
    BossDraft.query.filter_by(candidate_id=candidate_id).delete()
    OfferRecord.query.filter_by(candidate_id=candidate_id).delete()
    assignment_ids = [item.id for item in InterviewAssignment.query.filter_by(candidate_id=candidate_id).all()]
    if assignment_ids:
        InterviewFeedback.query.filter(InterviewFeedback.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
        InterviewAssignment.query.filter(InterviewAssignment.id.in_(assignment_ids)).delete(synchronize_session=False)
    audit_log(user, "delete", "candidate", candidate.id, candidate.name_masked)
    db.session.delete(candidate)
    db.session.commit()
    return ok({"deleted": candidate_id}, "候选人及关联流程已删除")


def delete_job_relations(job_id):
    Match.query.filter_by(job_id=job_id).delete()
    PipelineStage.query.filter_by(job_id=job_id).delete()
    BossDraft.query.filter_by(job_id=job_id).delete()
    OfferRecord.query.filter_by(job_id=job_id).delete()
    assignment_ids = [item.id for item in InterviewAssignment.query.filter_by(job_id=job_id).all()]
    if assignment_ids:
        InterviewFeedback.query.filter(InterviewFeedback.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
        InterviewAssignment.query.filter(InterviewAssignment.id.in_(assignment_ids)).delete(synchronize_session=False)


def normalize_job_title(title):
    text = re.sub(r"\s+", "", str(title or "").lower())
    text = re.sub(r"[（(].*?[）)]", "", text)
    return text.strip()


def job_relation_counts(job):
    latest_items = latest_pipeline_items(job.id)
    recruiting_count = sum(1 for item in latest_items if item.stage not in {"onboarded", "rejected"})
    onboarded_pipeline_count = sum(1 for item in latest_items if item.stage == "onboarded")
    employee_count = EmployeeProfile.query.filter_by(current_job_id=job.id).count()
    active_employee_count = EmployeeProfile.query.filter_by(current_job_id=job.id, employment_status="active").count()
    return {
        "match_count": Match.query.filter_by(job_id=job.id).count(),
        "pipeline_count": len(latest_items),
        "recruiting_count": recruiting_count,
        "onboarded_pipeline_count": onboarded_pipeline_count,
        "employee_count": employee_count,
        "active_employee_count": active_employee_count,
        "interview_count": InterviewAssignment.query.filter_by(job_id=job.id).count(),
        "offer_count": OfferRecord.query.filter_by(job_id=job.id).count(),
        "boss_draft_count": BossDraft.query.filter_by(job_id=job.id).count(),
    }


def job_with_relation_counts(job):
    data = job.to_dict()
    data.update(job_relation_counts(job))
    return data


def dedupe_target_matches(job_id):
    matches = Match.query.filter_by(job_id=job_id).order_by(Match.candidate_id.asc(), Match.score.desc(), Match.id.asc()).all()
    seen = set()
    removed = 0
    for item in matches:
        if item.candidate_id in seen:
            db.session.delete(item)
            removed += 1
        else:
            seen.add(item.candidate_id)
    return removed


@api.post("/resume/upload")
@login_required
@roles_required("admin", "manager", "recruiter")
def upload_resume(user):
    files = request.files.getlist("files") or request.files.getlist("file")
    files = [file for file in files if file and file.filename]
    if not files:
        return error("请上传简历文件")
    max_files = int(current_app.config.get("MAX_UPLOAD_FILES", 20))
    if len(files) > max_files:
        return error(f"单次最多上传 {max_files} 个文件", "TOO_MANY_FILES", 413)

    batches = []
    candidates = []
    errors = []
    for file in files:
        try:
            if Path(file.filename).suffix.lower() in ARCHIVE_EXTENSIONS:
                archive_batches, archive_candidates, archive_errors = parse_and_save_archive(file, user)
                batches.extend(archive_batches)
                candidates.extend(archive_candidates)
                errors.extend(archive_errors)
            else:
                batch, candidate = parse_and_save_resume(file, user)
                batches.append(batch)
                candidates.append(candidate)
        except ValueError as exc:
            errors.append({"filename": file.filename, "error": str(exc)})
        except Exception as exc:
            errors.append({"filename": file.filename, "error": str(exc)})

    if not candidates:
        return error("简历解析失败", "PARSE_FAILED", 400, {"errors": errors})

    message = f"已解析 {len(candidates)} 份简历"
    if errors:
        message += f"，失败 {len(errors)} 份"
    return ok(
        {
            "batch": batches[0].to_dict() if batches else None,
            "candidate": candidates[0].to_dict(detail=True),
            "batches": [batch.to_dict() for batch in batches],
            "candidates": [candidate.to_dict(detail=True) for candidate in candidates],
            "errors": errors,
            "success_count": len(candidates),
            "failed_count": len(errors),
        },
        message,
    )


@api.post("/resume/<int:candidate_id>/retry-parse")
@login_required
@roles_required("admin", "manager", "recruiter")
def retry_parse_resume(user, candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return error("候选人不存在", "NOT_FOUND", 404)
    if request.args.get("async") in {"1", "true", "yes"}:
        task = enqueue_task("resume_retry_parse", {"candidate_id": candidate.id}, created_by=user.id)
        audit_log(user, "enqueue", "background_task", task.id, task.task_type, {"candidate_id": candidate.id})
        db.session.commit()
        return ok({"task": task.to_dict()}, "简历重解析任务已加入后台队列")
    try:
        candidate = reparse_candidate(candidate)
        db.session.commit()
    except Exception as exc:
        candidate.parse_status = "failed"
        candidate.parse_error = str(exc)
        db.session.commit()
        return error("简历重解析失败", "PARSE_FAILED", 500, {"reason": str(exc)})
    return ok({"candidate": candidate.to_dict(detail=True)}, "简历已重新解析")


@api.get("/jobs")
@login_required
def list_jobs(user):
    jobs, meta = paginate_query(Job.query.order_by(Job.created_at.desc()))
    for job in jobs:
        job.jd_structured = ensure_jd_structured(job)
    db.session.commit()
    return ok({"items": [job.to_dict() for job in jobs], **meta})


@api.get("/jobs/duplicates")
@login_required
@roles_required("admin", "manager", "recruiter")
def job_duplicates(user):
    groups = defaultdict(list)
    for job in Job.query.order_by(Job.title.asc(), Job.created_at.asc()).all():
        key = normalize_job_title(job.title)
        if key:
            job.jd_structured = ensure_jd_structured(job)
            groups[key].append(job)
    db.session.commit()
    items = []
    for key, jobs in groups.items():
        if len(jobs) < 2:
            continue
        items.append(
            {
                "key": key,
                "title": jobs[0].title,
                "count": len(jobs),
                "jobs": [job_with_relation_counts(job) for job in sorted(jobs, key=lambda item: (item.status != "active", item.created_at or datetime.min, item.id))],
            }
        )
    items.sort(key=lambda item: item["count"], reverse=True)
    return ok({"items": items, "total_groups": len(items), "duplicate_job_count": sum(item["count"] - 1 for item in items)})


@api.post("/jobs/merge")
@login_required
@roles_required("admin", "manager")
def merge_jobs(user):
    payload = request.get_json(force=True)
    target_id = int(payload.get("target_job_id") or 0)
    duplicate_ids = [int(item) for item in payload.get("duplicate_job_ids") or [] if int(item) != target_id]
    if not target_id or not duplicate_ids:
        return error("请选择保留岗位和需要合并的重复岗位")
    target = db.session.get(Job, target_id)
    duplicates = Job.query.filter(Job.id.in_(duplicate_ids)).all()
    if not target or len(duplicates) != len(set(duplicate_ids)):
        return error("岗位不存在", "NOT_FOUND", 404)

    before_counts = {job.id: job_relation_counts(job) for job in [target, *duplicates]}
    if not target.city:
        target.city = next((job.city for job in duplicates if job.city), target.city)
    if not target.department:
        target.department = next((job.department for job in duplicates if job.department), target.department)
    if not target.job_code:
        target.job_code = next((job.job_code for job in duplicates if job.job_code), target.job_code)
    if not target.jd_text:
        target.jd_text = next((job.jd_text for job in duplicates if job.jd_text), target.jd_text)

    for duplicate_id in duplicate_ids:
        Match.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        PipelineStage.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        InterviewAssignment.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        OfferRecord.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        BossDraft.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        EmployeeProfile.query.filter_by(current_job_id=duplicate_id).update({"current_job_id": target_id}, synchronize_session=False)
        EmployeeAnalysis.query.filter_by(job_id=duplicate_id).update({"job_id": target_id}, synchronize_session=False)
        EmployeeRecommendation.query.filter_by(target_job_id=duplicate_id).update({"target_job_id": target_id}, synchronize_session=False)

    removed_matches = dedupe_target_matches(target_id)
    deleted_titles = [job.title for job in duplicates]
    for job in duplicates:
        db.session.delete(job)
    audit_log(
        user,
        "merge",
        "job",
        target.id,
        target.title,
        {"merged_job_ids": duplicate_ids, "merged_titles": deleted_titles, "before_counts": before_counts, "removed_duplicate_matches": removed_matches},
    )
    db.session.commit()
    return ok(
        {
            "target": job_with_relation_counts(target),
            "merged_job_ids": duplicate_ids,
            "removed_duplicate_matches": removed_matches,
        },
        f"已合并 {len(duplicate_ids)} 个重复岗位，关联数据已迁移到「{target.title}」",
    )


@api.get("/jobs/<int:job_id>")
@login_required
def get_job(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    job.jd_structured = ensure_jd_structured(job)
    db.session.commit()
    data = job.to_dict()
    data["match_count"] = Match.query.filter_by(job_id=job.id).count()
    data["pipeline_count"] = PipelineStage.query.filter_by(job_id=job.id).count()
    return ok(data)


@api.post("/jobs")
@login_required
@roles_required("admin", "manager", "recruiter")
def create_job(user):
    payload = request.get_json(force=True)
    title = str(payload.get("title") or "").strip()
    jd_text = str(payload.get("jd_text") or "").strip()
    if not title or not jd_text:
        return error("岗位名称和 JD 必填")
    skill_tags_raw = payload.get("skill_tags_raw")
    job = Job(
        owner_hr_id=user.id,
        title=title,
        city=payload.get("city"),
        department=payload.get("department"),
        job_code=payload.get("job_code"),
        jd_text=jd_text,
        jd_structured=build_jd_structured(jd_text, skill_tags_raw),
    )
    db.session.add(job)
    db.session.flush()
    audit_log(user, "create", "job", job.id, job.title)
    db.session.commit()
    return ok(job.to_dict(), "岗位已创建")


@api.post("/jobs/ai-generate")
@login_required
@roles_required("admin", "manager", "recruiter")
def ai_generate_job(user):
    payload = request.get_json(force=True)
    title = str(payload.get("title") or "").strip()
    if not title:
        return error("岗位名称必填")
    return ok(ai_job_payload(payload, generate=True), "JD 已生成")


@api.post("/jobs/ai-calibrate")
@login_required
@roles_required("admin", "manager", "recruiter")
def ai_calibrate_job(user):
    payload = request.get_json(force=True)
    jd_text = str(payload.get("jd_text") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not title and not jd_text:
        return error("岗位名称或 JD 必填")
    return ok(ai_job_payload(payload, generate=False), "JD 已校准")


@api.patch("/jobs/<int:job_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def update_job(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    for field in ["title", "jd_text"]:
        if field in payload:
            value = str(payload.get(field) or "").strip()
            if not value:
                return error("岗位名称和 JD 不能为空")
            setattr(job, field, value)
    for field in ["city", "department", "job_code"]:
        if field in payload:
            setattr(job, field, str(payload.get(field) or "").strip())
    if "skill_tags_raw" in payload or "jd_text" in payload:
        job.jd_structured = build_jd_structured(job.jd_text, payload.get("skill_tags_raw", job.jd_structured.get("skill_tags_raw")))
        Match.query.filter_by(job_id=job.id).delete()
    audit_log(user, "update", "job", job.id, job.title)
    db.session.commit()
    return ok(job.to_dict(), "岗位已更新")


@api.post("/jobs/<int:job_id>/close")
@login_required
@roles_required("admin", "manager", "recruiter")
def close_job(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    job.status = "closed"
    audit_log(user, "close", "job", job.id, job.title)
    db.session.commit()
    return ok(job.to_dict(), "岗位已关闭")


@api.post("/jobs/<int:job_id>/restore")
@login_required
@roles_required("admin", "manager", "recruiter")
def restore_job(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    job.status = "active"
    audit_log(user, "restore", "job", job.id, job.title)
    db.session.commit()
    return ok(job.to_dict(), "岗位已恢复")


@api.delete("/jobs/<int:job_id>")
@login_required
@roles_required("admin", "manager")
def delete_job(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    delete_job_relations(job_id)
    audit_log(user, "delete", "job", job.id, job.title)
    db.session.delete(job)
    db.session.commit()
    return ok({"deleted": job_id}, "岗位及关联流程已删除")


@api.get("/jobs/<int:job_id>/match-preview")
@login_required
def match_preview(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    job.jd_structured = ensure_jd_structured(job)
    db.session.commit()
    limit = request.args.get("limit", type=int)
    return ok({"job": job.to_dict(), "items": preview_matches(job, limit=limit)})


@api.post("/jobs/<int:job_id>/match")
@login_required
def run_job_match(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    job.jd_structured = ensure_jd_structured(job)
    db.session.commit()
    if job.status != "active":
        return error("关闭岗位不能执行匹配，请先恢复岗位", "JOB_CLOSED", 409)
    results = persist_matches(db, job)
    return ok({"job": job.to_dict(), "items": results}, "岗位匹配已完成")


@api.post("/jobs/<int:job_id>/batch-pipeline")
@login_required
@roles_required("admin", "manager", "recruiter")
def batch_pipeline(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    candidate_ids = payload.get("candidate_ids") or []
    if payload.get("candidate_id"):
        candidate_ids.append(payload["candidate_id"])
    candidate_ids = list(dict.fromkeys(int(candidate_id) for candidate_id in candidate_ids if candidate_id))
    if not candidate_ids:
        return error("请选择候选人")

    stage = payload.get("stage") or "pending"
    if stage not in STAGES:
        return error("流程阶段不合法")

    created = []
    skipped = []
    missing = []
    for candidate_id in candidate_ids:
        candidate = db.session.get(Candidate, candidate_id)
        if not candidate:
            missing.append(candidate_id)
            continue
        latest = latest_pipeline_item(job_id, candidate_id)
        if latest and latest.stage != "rejected":
            skipped.append({"candidate_id": candidate_id, "stage": latest.stage})
            continue
        item = PipelineStage(
            candidate_id=candidate_id,
            job_id=job_id,
            stage=stage,
            updated_by=user.id,
            note=payload.get("note", "由匹配结果加入流程"),
        )
        db.session.add(item)
        db.session.flush()
        created.append(item.to_dict())
    db.session.commit()
    return ok({"created": created, "skipped": skipped, "missing": missing}, "候选人流程已更新")


@api.get("/pipeline/<int:job_id>/board")
@login_required
def pipeline_board(user, job_id):
    latest = latest_pipeline_items(job_id)
    columns = {stage: [] for stage in STAGES}
    for item in latest:
        columns.setdefault(item.stage, []).append(item.to_dict())
    return ok({"stages": STAGES, "columns": columns})


@api.get("/pipeline/<int:job_id>/history/<int:candidate_id>")
@login_required
def pipeline_history(user, job_id, candidate_id):
    items = (
        PipelineStage.query.filter_by(job_id=job_id, candidate_id=candidate_id)
        .order_by(PipelineStage.ts.asc())
        .all()
    )
    return ok({"items": [item.to_dict() for item in items]})


@api.post("/pipeline/move")
@login_required
@roles_required("admin", "manager", "recruiter")
def move_pipeline(user):
    payload = request.get_json(force=True)
    stage = payload.get("stage")
    if stage not in STAGES:
        return error("流程阶段不合法")
    if not db.session.get(Candidate, payload.get("candidate_id")) or not db.session.get(Job, payload.get("job_id")):
        return error("候选人或岗位不存在", "NOT_FOUND", 404)
    latest = latest_pipeline_item(payload.get("job_id"), payload.get("candidate_id"))
    if latest and latest.stage == stage:
        return ok(latest.to_dict(), "候选人已在该流程阶段")
    item = PipelineStage(
        candidate_id=payload.get("candidate_id"),
        job_id=payload.get("job_id"),
        stage=stage,
        updated_by=user.id,
        note=payload.get("note", "阶段推进"),
    )
    db.session.add(item)
    db.session.commit()
    return ok(item.to_dict(), "流程已推进")


@api.get("/interview/assignments")
@login_required
def list_interview_assignments(user):
    query = InterviewAssignment.query.order_by(InterviewAssignment.scheduled_at.desc())
    job_id = request.args.get("job_id", type=int)
    candidate_id = request.args.get("candidate_id", type=int)
    if job_id:
        query = query.filter_by(job_id=job_id)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    if user.role == "interviewer":
        query = query.filter_by(interviewer_id=user.id)
    assignments, meta = paginate_query(query)
    return ok({"items": [item.to_dict() for item in assignments], **meta})


@api.get("/interview/assignments/<int:assignment_id>")
@login_required
def get_interview_assignment(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if user.role == "interviewer" and assignment.interviewer_id != user.id:
        return error("无权查看该面试安排", "FORBIDDEN", 403)
    return ok(assignment.to_dict())


@api.post("/interview/assignments/<int:assignment_id>/ai-plan")
@login_required
def interview_ai_plan(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if user.role == "interviewer" and assignment.interviewer_id != user.id:
        return error("无权查看该面试安排", "FORBIDDEN", 403)
    return ok(build_interview_ai_plan(assignment), "AI 面试方案已生成")


@api.post("/interview/assignments/<int:assignment_id>/room-link")
@login_required
@roles_required("admin", "manager", "recruiter")
def interview_room_link(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if assignment.status != "scheduled":
        return error("该面试已结束或取消，不能生成候选人面试间", "INTERVIEW_CLOSED", 409)
    token = issue_interview_room_token(assignment.id)
    path = f"/interview-room/{token}"
    return ok({"token": token, "path": path, "url": request.host_url.rstrip("/") + path}, "候选人面试间链接已生成")


@api.get("/public/interview-room/<token>")
def public_interview_room(token):
    limited = public_interview_rate_limit(token)
    if limited:
        return limited
    assignment = assignment_from_room_token(token, allow_completed=True)
    if not assignment:
        return error("面试间链接无效或已过期", "INVALID_INTERVIEW_ROOM", 404)
    return ok({"assignment": assignment.to_dict(), "plan": build_interview_ai_plan(assignment)})


@api.post("/public/interview-room/<token>/turn")
def public_interview_turn(token):
    limited = public_interview_rate_limit(token)
    if limited:
        return limited
    assignment = assignment_from_room_token(token)
    if not assignment:
        return error("面试间链接无效或已过期", "INVALID_INTERVIEW_ROOM", 404)
    payload = request.get_json(force=True)
    payload_error = validate_public_interview_payload(payload, complete=False)
    if payload_error:
        return payload_error
    return ok(build_interview_turn_reply(assignment, payload))


@api.post("/public/interview-room/<token>/complete")
def public_interview_complete(token):
    limited = public_interview_rate_limit(token)
    if limited:
        return limited
    assignment = assignment_from_room_token(token)
    if not assignment:
        return error("面试间链接无效或已过期", "INVALID_INTERVIEW_ROOM", 404)
    payload = request.get_json(force=True)
    payload_error = validate_public_interview_payload(payload, complete=True)
    if payload_error:
        return payload_error
    feedback = save_public_interview_feedback(assignment, payload)
    closing = "本次 AI 面试已结束，感谢你的参与。面试结果已同步给招聘团队，请等待后续通知。"
    return ok({"assignment": assignment.to_dict(), "feedback": feedback.to_dict(), "closing": closing}, "AI 面试已同步到面试管理")


@api.post("/interview/assignments")
@login_required
@roles_required("admin", "manager", "recruiter")
def create_interview_assignment(user):
    payload = request.get_json(force=True)
    candidate = db.session.get(Candidate, payload.get("candidate_id"))
    job = db.session.get(Job, payload.get("job_id"))
    interviewer = db.session.get(User, payload.get("interviewer_id"))
    if not candidate or not job or not interviewer:
        return error("候选人、岗位或面试官不存在", "NOT_FOUND", 404)
    if interviewer.role not in {"admin", "manager", "interviewer"}:
        return error("所选用户不能作为面试官", "VALIDATION_ERROR")
    scheduled_at = parse_datetime(payload.get("scheduled_at"))
    if not scheduled_at:
        return error("面试时间不合法")
    round_name = payload.get("round") or "interview_first"
    if round_name not in {"interview_first", "interview_second", "interview_final"}:
        return error("面试轮次不合法")
    assignment = InterviewAssignment(
        candidate_id=candidate.id,
        job_id=job.id,
        interviewer_id=interviewer.id,
        round=round_name,
        scheduled_at=scheduled_at,
        location=payload.get("location"),
        note=payload.get("note"),
        created_by=user.id,
    )
    db.session.add(assignment)
    db.session.flush()
    assignment.ai_plan = build_interview_ai_plan(assignment, prefer_deepseek=True)
    db.session.add(
        PipelineStage(
            candidate_id=candidate.id,
            job_id=job.id,
            stage=round_name,
            updated_by=user.id,
            note=f"已安排{stageLabels_backend(round_name)}：{interviewer.name}",
        )
    )
    audit_log(user, "create", "interview", assignment.id, candidate.name_masked, {"round": round_name, "interviewer": interviewer.name})
    db.session.commit()
    return ok(assignment.to_dict(), "面试已安排")


@api.patch("/interview/assignments/<int:assignment_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def update_interview_assignment(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if assignment.status != "scheduled":
        return error("该面试已结束或取消，不能编辑安排", "INTERVIEW_CLOSED", 409)
    payload = request.get_json(force=True)
    if "interviewer_id" in payload:
        interviewer = db.session.get(User, payload.get("interviewer_id"))
        if not interviewer or interviewer.role not in {"admin", "manager", "interviewer"}:
            return error("所选用户不能作为面试官", "VALIDATION_ERROR")
        assignment.interviewer_id = interviewer.id
    if "scheduled_at" in payload:
        scheduled_at = parse_datetime(payload.get("scheduled_at"))
        if not scheduled_at:
            return error("面试时间不合法")
        assignment.scheduled_at = scheduled_at
    if "round" in payload:
        if payload["round"] not in {"interview_first", "interview_second", "interview_final"}:
            return error("面试轮次不合法")
        assignment.round = payload["round"]
    for field in ["location", "note"]:
        if field in payload:
            setattr(assignment, field, payload.get(field))
    audit_log(user, "update", "interview", assignment.id, assignment.candidate.name_masked, {"round": assignment.round})
    db.session.commit()
    return ok(assignment.to_dict(), "面试安排已更新")


@api.post("/interview/assignments/<int:assignment_id>/cancel")
@login_required
@roles_required("admin", "manager", "recruiter")
def cancel_interview_assignment(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if assignment.status != "scheduled":
        return error("该面试已结束或取消，不能重复取消", "INTERVIEW_CLOSED", 409)
    assignment.status = "cancelled"
    db.session.add(PipelineStage(candidate_id=assignment.candidate_id, job_id=assignment.job_id, stage=assignment.round, updated_by=user.id, note="面试已取消"))
    audit_log(user, "cancel", "interview", assignment.id, assignment.candidate.name_masked, {"round": assignment.round})
    db.session.commit()
    return ok(assignment.to_dict(), "面试已取消")


@api.delete("/interview/assignments/<int:assignment_id>")
@login_required
@roles_required("admin", "manager")
def delete_interview_assignment(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    InterviewFeedback.query.filter_by(assignment_id=assignment.id).delete()
    audit_log(user, "delete", "interview", assignment.id, assignment.candidate.name_masked, {"round": assignment.round})
    db.session.delete(assignment)
    db.session.commit()
    return ok({"deleted": assignment_id}, "面试安排已删除")


@api.post("/interview/feedback")
@login_required
def submit_interview_feedback(user):
    payload = request.get_json(force=True)
    assignment = db.session.get(InterviewAssignment, payload.get("assignment_id"))
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if assignment.status != "scheduled":
        return error("该面试已结束或取消，不能重复提交反馈", "INTERVIEW_CLOSED", 409)
    if user.role == "interviewer" and assignment.interviewer_id != user.id:
        return error("只能提交分配给自己的面试反馈", "FORBIDDEN", 403)
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        return error("评分必须是 1-5")
    if rating < 1 or rating > 5:
        return error("评分必须是 1-5")
    decision = payload.get("decision") or "hold"
    if decision not in {"pass", "hold", "reject"}:
        return error("面试结论不合法")
    feedback = InterviewFeedback(
        assignment_id=assignment.id,
        interviewer_id=user.id,
        rating=rating,
        decision=decision,
        strengths=payload.get("strengths"),
        risks=payload.get("risks"),
        comment=payload.get("comment"),
    )
    assignment.status = "completed"
    db.session.add(feedback)
    if decision == "reject":
        next_stage = "rejected"
    elif assignment.round == "interview_first":
        next_stage = "interview_second"
    elif assignment.round == "interview_second":
        next_stage = "offer"
    else:
        next_stage = "offer"
    db.session.add(
        PipelineStage(
            candidate_id=assignment.candidate_id,
            job_id=assignment.job_id,
            stage=next_stage,
            updated_by=user.id,
            note=f"面试反馈：{decision}，评分 {rating}/5",
        )
    )
    audit_log(user, "feedback", "interview", assignment.id, assignment.candidate.name_masked, {"decision": decision, "rating": rating})
    db.session.commit()
    return ok(feedback.to_dict(), "面试反馈已提交")


@api.get("/interview/feedback")
@login_required
def list_interview_feedback(user):
    assignment_id = request.args.get("assignment_id", type=int)
    query = InterviewFeedback.query.order_by(InterviewFeedback.created_at.desc())
    if assignment_id:
        query = query.filter_by(assignment_id=assignment_id)
    feedback, meta = paginate_query(query)
    return ok({"items": [item.to_dict() for item in feedback], **meta})


@api.get("/interview/assignments/<int:assignment_id>/report.txt")
@login_required
def export_interview_report(user, assignment_id):
    assignment = db.session.get(InterviewAssignment, assignment_id)
    if not assignment:
        return error("面试安排不存在", "NOT_FOUND", 404)
    if user.role == "interviewer" and assignment.interviewer_id != user.id:
        return error("无权查看该面试报告", "FORBIDDEN", 403)
    feedback = InterviewFeedback.query.filter_by(assignment_id=assignment.id).order_by(InterviewFeedback.created_at.desc()).first()
    if not feedback:
        return error("面试结果不存在", "NOT_FOUND", 404)
    body = build_interview_report_text(assignment, feedback)
    audit_log(user, "export", "interview", assignment.id, assignment.candidate.name_masked, {"kind": "interview_report", "filename": f"interview-report-{assignment.id}.txt"})
    db.session.commit()
    return Response(
        "\ufeff" + body,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=interview-report-{assignment.id}.txt"},
    )


@api.get("/offers")
@login_required
@roles_required("admin", "manager", "recruiter")
def list_offers(user):
    query = OfferRecord.query.order_by(OfferRecord.updated_at.desc(), OfferRecord.created_at.desc())
    status = request.args.get("status")
    job_id = request.args.get("job_id", type=int)
    candidate_id = request.args.get("candidate_id", type=int)
    if status and status != "all":
        query = query.filter_by(status=status)
    if job_id:
        query = query.filter_by(job_id=job_id)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    offers, meta = paginate_query(query)
    return ok({"items": [item.to_dict() for item in offers], "statuses": sorted(OFFER_STATUSES), **meta})


@api.get("/offers/<int:offer_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def get_offer(user, offer_id):
    offer = db.session.get(OfferRecord, offer_id)
    if not offer:
        return error("Offer 不存在", "NOT_FOUND", 404)
    return ok(offer.to_dict())


@api.get("/offers/<int:offer_id>/letter.txt")
@login_required
@roles_required("admin", "manager", "recruiter")
def export_offer_letter(user, offer_id):
    offer = db.session.get(OfferRecord, offer_id)
    if not offer:
        return error("Offer 不存在", "NOT_FOUND", 404)
    audit_log(user, "export", "offer", offer.id, offer.candidate.name_masked if offer.candidate else "", {"kind": "offer_letter", "filename": f"offer-{offer.id}.txt"})
    db.session.commit()
    return Response(
        "\ufeff" + build_offer_letter_text(offer),
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=offer-{offer.id}.txt"},
    )


@api.post("/offers")
@login_required
@roles_required("admin", "manager", "recruiter")
def create_offer(user):
    payload = request.get_json(force=True)
    candidate = db.session.get(Candidate, payload.get("candidate_id"))
    job = db.session.get(Job, payload.get("job_id"))
    if not candidate or not job:
        return error("候选人或岗位不存在", "NOT_FOUND", 404)
    status = payload.get("status") or "draft"
    if status not in OFFER_STATUSES:
        return error("Offer 状态不合法", details={"statuses": sorted(OFFER_STATUSES)})
    salary_min_k = parse_optional_float(payload.get("salary_min_k"))
    salary_max_k = parse_optional_float(payload.get("salary_max_k"))
    salary_months = parse_optional_int(payload.get("salary_months"), 12)
    validation_error = validate_offer_terms(salary_min_k, salary_max_k, salary_months)
    if validation_error:
        return validation_error
    offer = OfferRecord(
        candidate_id=candidate.id,
        job_id=job.id,
        salary_min_k=salary_min_k,
        salary_max_k=salary_max_k,
        salary_months=salary_months,
        city=payload.get("city") or job.city,
        start_date=parse_date(payload.get("start_date")),
        status=status,
        note=payload.get("note"),
        created_by=user.id,
    )
    db.session.add(offer)
    db.session.flush()
    push_offer_pipeline(offer, user.id, f"Offer 已创建：{offer_status_label(status)}")
    audit_log(user, "create", "offer", offer.id, offer.candidate.name_masked, {"status": status})
    db.session.commit()
    return ok(offer.to_dict(), "Offer 已创建")


@api.patch("/offers/<int:offer_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def update_offer(user, offer_id):
    offer = db.session.get(OfferRecord, offer_id)
    if not offer:
        return error("Offer 不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    previous_status = offer.status
    for field in ["city", "note"]:
        if field in payload:
            setattr(offer, field, payload.get(field))
    if "salary_min_k" in payload:
        offer.salary_min_k = parse_optional_float(payload.get("salary_min_k"))
    if "salary_max_k" in payload:
        offer.salary_max_k = parse_optional_float(payload.get("salary_max_k"))
    if "salary_months" in payload:
        offer.salary_months = parse_optional_int(payload.get("salary_months"), offer.salary_months)
    if "start_date" in payload:
        offer.start_date = parse_date(payload.get("start_date"))
    if "status" in payload:
        if payload["status"] not in OFFER_STATUSES:
            return error("Offer 状态不合法", details={"statuses": sorted(OFFER_STATUSES)})
        offer.status = payload["status"]
    validation_error = validate_offer_terms(offer.salary_min_k, offer.salary_max_k, offer.salary_months)
    if validation_error:
        return validation_error
    if offer.status != previous_status:
        push_offer_pipeline(offer, user.id, f"Offer 状态更新：{offer_status_label(offer.status)}")
    audit_log(user, "update", "offer", offer.id, offer.candidate.name_masked, {"status": offer.status})
    db.session.commit()
    return ok(offer.to_dict(), "Offer 已更新")


@api.delete("/offers/<int:offer_id>")
@login_required
@roles_required("admin", "manager")
def delete_offer(user, offer_id):
    offer = db.session.get(OfferRecord, offer_id)
    if not offer:
        return error("Offer 不存在", "NOT_FOUND", 404)
    audit_log(user, "delete", "offer", offer.id, offer.candidate.name_masked, {"status": offer.status})
    db.session.delete(offer)
    db.session.commit()
    return ok({"deleted": offer_id}, "Offer 已删除")


@api.get("/bi/overview")
@login_required
@roles_required("admin", "manager", "recruiter")
def bi_overview(user):
    days = max(1, min(parse_optional_int(request.args.get("days"), 30), 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    candidates = Candidate.query.filter(Candidate.created_at >= since).all()
    sources = Counter(candidate.source for candidate in candidates)
    pipeline = Counter(item.stage for item in latest_pipeline_items(since=since))
    top_tags = Counter()
    candidate_ids = {candidate.id for candidate in candidates}
    for tag in CandidateTag.query.filter(CandidateTag.candidate_id.in_(candidate_ids)).all() if candidate_ids else []:
        top_tags[tag.tag] += tag.score
    return ok(
        {
            "period_days": days,
            "total_candidates": len(candidates),
            "active_jobs": Job.query.filter_by(status="active").count(),
            "source_quality": dict(sources),
            "pipeline_funnel": {stage: pipeline.get(stage, 0) for stage in STAGES},
            "experience_stats": experience_stats(candidates),
            "top_tags": top_tags.most_common(8),
        }
    )


@api.get("/pipeline/overview")
@login_required
@roles_required("admin", "manager", "recruiter")
def pipeline_overview(user):
    items = latest_pipeline_items()
    by_stage = Counter(item.stage for item in items)
    by_job = Counter(item.job.title if item.job else str(item.job_id) for item in items)
    return ok(
        {
            "total": len(items),
            "stages": {stage: by_stage.get(stage, 0) for stage in STAGES},
            "jobs": dict(by_job),
            "items": [item.to_dict() for item in items[:50]],
        }
    )


@api.get("/exports/candidates.csv")
@login_required
@roles_required("admin", "manager")
def export_candidates(user):
    rows = [
        [
            item.id,
            item.name_masked,
            item.title,
            item.city or "",
            item.resume_json.get("gender", ""),
            item.phone_masked or "",
            item.email_masked or "",
            item.source,
            item.resume_json.get("experience_analysis", {}).get("label", ""),
            "、".join(tag.tag for tag in item.tags),
            item.created_at.isoformat(),
        ]
        for item in Candidate.query.order_by(Candidate.created_at.desc()).all()
    ]
    return csv_response("candidates.csv", ["ID", "姓名", "岗位", "城市", "性别", "手机号", "邮箱", "来源", "经验", "技能标签", "创建时间"], rows, user=user, audit_target="candidates")


@api.get("/exports/jobs.csv")
@login_required
@roles_required("admin", "manager")
def export_jobs(user):
    rows = []
    for item in Job.query.order_by(Job.created_at.desc()).all():
        structured = ensure_jd_structured(item)
        rows.append([item.id, item.title, item.city or "", item.department or "", item.job_code or "", item.status, structured.get("skill_tags_raw", ""), item.created_at.isoformat()])
    return csv_response("jobs.csv", ["ID", "岗位名称", "城市", "部门", "岗位编号", "状态", "技能权重", "创建时间"], rows, user=user, audit_target="jobs")


@api.get("/exports/offers.csv")
@login_required
@roles_required("admin", "manager")
def export_offers(user):
    rows = [
        [
            item.id,
            item.candidate.name_masked if item.candidate else "",
            item.job.title if item.job else "",
            item.city or "",
            item.salary_min_k or "",
            item.salary_max_k or "",
            item.salary_months,
            item.start_date.isoformat() if item.start_date else "",
            item.status,
            item.note or "",
            item.created_at.isoformat(),
        ]
        for item in OfferRecord.query.order_by(OfferRecord.created_at.desc()).all()
    ]
    return csv_response("offers.csv", ["ID", "候选人", "岗位", "城市", "最低月薪K", "最高月薪K", "薪资月数", "入职日期", "状态", "备注", "创建时间"], rows, user=user, audit_target="offers")


@api.get("/exports/interviews.csv")
@login_required
@roles_required("admin", "manager")
def export_interviews(user):
    rows = [
        [
            item.id,
            item.candidate.name_masked if item.candidate else "",
            item.job.title if item.job else "",
            item.interviewer.name if item.interviewer else "",
            stageLabels_backend(item.round),
            item.scheduled_at.isoformat(),
            item.location or "",
            item.status,
            item.note or "",
            item.created_at.isoformat(),
        ]
        for item in InterviewAssignment.query.order_by(InterviewAssignment.created_at.desc()).all()
    ]
    return csv_response("interviews.csv", ["ID", "候选人", "岗位", "面试官", "轮次", "时间", "地点", "状态", "备注", "创建时间"], rows, user=user, audit_target="interviews")


@api.get("/exports/pipeline.csv")
@login_required
@roles_required("admin", "manager")
def export_pipeline(user):
    rows = [
        [
            item.id,
            item.candidate.name_masked if item.candidate else "",
            item.job.title if item.job else "",
            stageLabels_backend(item.stage),
            item.user.name if item.user else "",
            item.note or "",
            item.ts.isoformat(),
        ]
        for item in latest_pipeline_items()
    ]
    return csv_response("pipeline.csv", ["ID", "候选人", "岗位", "当前阶段", "更新人", "备注", "更新时间"], rows, user=user, audit_target="pipeline")


@api.get("/exports/employees.csv")
@login_required
@roles_required("admin", "manager")
def export_employees(user):
    rows = []
    for item in EmployeeProfile.query.order_by(EmployeeProfile.updated_at.desc()).all():
        compensation = item.latest_compensation()
        analysis = item.analyses[0] if item.analyses else None
        rows.append(
            [
                item.id,
                item.employee_no or "",
                item.name,
                item.organization_unit.name if item.organization_unit else item.department or "",
                item.current_job.title if item.current_job else item.current_title or "",
                item.level or "",
                item.city or "",
                employment_status_label(item.employment_status),
                item.hire_date.isoformat() if item.hire_date else "",
                item.birth_date.isoformat() if item.birth_date else "",
                item.education or "",
                item.graduation_school or "",
                item.graduation_date.isoformat() if item.graduation_date else "",
                item.to_dict().get("seniority_years") or "",
                compensation.salary_monthly_k if compensation else "",
                compensation.salary_annual_k if compensation else "",
                analysis.match_score if analysis else "",
                salary_status_label(analysis.salary_status) if analysis else "",
                risk_label(analysis.risk_level) if analysis else "",
                "、".join(tag.tag for tag in item.tags()),
                item.updated_at.isoformat() if item.updated_at else "",
            ]
        )
    return csv_response(
        "employees.csv",
        ["ID", "员工编号", "姓名", "组织", "当前岗位", "职级", "城市", "状态", "入职日期", "出生日期", "学历", "毕业院校", "毕业时间", "司龄", "月薪K", "年包K", "岗位匹配分", "薪资状态", "风险等级", "技能标签", "更新时间"],
        rows,
        user=user,
        audit_target="employees",
    )


@api.get("/exports/boss-drafts.csv")
@login_required
@roles_required("admin", "manager")
def export_boss_drafts(user):
    rows = [
        [
            item.id,
            item.candidate.name_masked if item.candidate else "",
            item.job.title if item.job else "",
            boss_draft_status_label(item.status),
            item.content,
            item.created_at.isoformat(),
        ]
        for item in BossDraft.query.order_by(BossDraft.created_at.desc()).all()
    ]
    return csv_response("boss-drafts.csv", ["ID", "候选人", "岗位", "状态", "话术", "创建时间"], rows, user=user, audit_target="boss_drafts")


@api.get("/tags")
@login_required
def list_skill_tags(user):
    labels = [{"tag": item.tag, "category": item.category, "aliases": list(item.aliases)} for item in load_labels()]
    categories = sorted({item["category"] for item in labels})
    return ok({"items": labels, "categories": categories})


@api.get("/boss/status")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_status(user):
    account = latest_boss_account(user)
    candidates = valid_boss_candidates(limit=1000)
    jobs = Job.query.filter(Job.job_code.like("BOSS-%")).order_by(Job.created_at.desc()).all()
    return ok(
        {
            "cookie_bound": bool(account),
            "account": account.account if account else "未绑定",
            "mode": "半自动",
            "can_auto_send": False,
            "verified": bool(account and account.verified),
            "account_id": account.id if account else None,
            "candidate_count": len(candidates),
            "job_count": len(jobs),
            "last_candidate_at": candidates[0].created_at.isoformat() if candidates else None,
            "last_job_at": jobs[0].created_at.isoformat() if jobs else None,
        }
    )


@api.get("/boss/extension.zip")
@login_required
@roles_required("admin", "manager", "recruiter")
def download_boss_extension(user):
    extension_dir = Path(__file__).resolve().parents[2] / "browser_extension" / "boss-importer"
    if not extension_dir.exists():
        return error("BOSS 插件目录不存在", "NOT_FOUND", 404)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in extension_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(extension_dir).as_posix())
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=hireinsight-boss-importer.zip"},
    )


@api.post("/boss/login/browser-cookie")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_browser_cookie(user):
    payload = request.get_json(force=True)
    cookie = str(payload.get("cookie") or payload.get("cookies") or "").strip()
    if len(cookie) < 20:
        return error("Cookie 内容过短", "VALIDATION_ERROR")
    account_name = str(payload.get("account") or "BOSS 浏览器登录态").strip()[:128]
    digest = hashlib.sha256(cookie.encode("utf-8")).hexdigest()
    account = BossAccount.query.filter_by(owner_hr_id=user.id).order_by(BossAccount.updated_at.desc()).first()
    if not account:
        account = BossAccount(owner_hr_id=user.id, account=account_name, cookie_hash=digest)
        db.session.add(account)
    else:
        account.account = account_name
        account.cookie_hash = digest
        account.verified = False
    db.session.commit()
    return ok({"account": account.to_dict()}, "BOSS 登录态已绑定，未保存明文 Cookie")


@api.post("/boss/accounts/<int:account_id>/verify")
@login_required
@roles_required("admin", "manager", "recruiter")
def verify_boss_account(user, account_id):
    account = db.session.get(BossAccount, account_id)
    if not account:
        return error("BOSS 账号不存在", "NOT_FOUND", 404)
    if user.role != "admin" and account.owner_hr_id != user.id:
        return error("无权校验该 BOSS 账号", "FORBIDDEN", 403)
    account.verified = bool(account.cookie_hash)
    db.session.commit()
    return ok({"account": account.to_dict()}, "BOSS 登录态校验通过")


@api.get("/boss/candidates/inbox")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_inbox(user):
    limit, offset = pagination_params()
    candidates = valid_boss_candidates(limit=max(1000, offset + limit))
    total = len(candidates)
    page = candidates[offset : offset + limit]
    return ok({"items": [boss_inbox_item(candidate) for candidate in page], **pagination_meta(total, limit, offset)})


@api.get("/boss/jobs")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_jobs(user):
    jobs, meta = paginate_query(Job.query.filter(Job.job_code.like("BOSS-%")).order_by(Job.created_at.desc()))
    return ok({"items": [job.to_dict() for job in jobs], **meta})


@api.post("/boss/jobs/batch-import")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_jobs_batch_import(user):
    payload = request.get_json(force=True)
    imported = []
    errors = []
    for item in payload.get("items", []):
        title = str(item.get("title") or "").strip()[:128]
        if not title:
            errors.append({"title": "", "error": "岗位名称为空"})
            continue
        text = str(item.get("jd_text") or item.get("summary") or title).strip()
        city = str(item.get("city") or "").strip()[:64]
        external_id = str(item.get("external_id") or hashlib.sha1(f"{title}|{city}|{text}".encode("utf-8")).hexdigest()[:12])
        job_code = f"BOSS-{re.sub(r'[^A-Za-z0-9_-]+', '-', external_id)[:48]}"
        job = Job.query.filter_by(job_code=job_code).first()
        if not job:
            job = Job(owner_hr_id=user.id, title=title, job_code=job_code, jd_text=text, status="active")
            db.session.add(job)
        job.title = title
        job.city = city or job.city
        job.jd_text = text
        job.jd_structured = build_jd_structured(text)
        imported.append(job)
    db.session.commit()
    return ok({"items": [job.to_dict() for job in imported], "errors": errors}, "BOSS 岗位已同步")


@api.get("/boss/jobs/<int:job_id>/recommendations")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_job_recommendations(user, job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    limit = request.args.get("limit", default=8, type=int)
    items = []
    for candidate in Candidate.query.filter_by(source="boss").all():
        if not looks_like_boss_resume_text(candidate.raw_text):
            continue
        reason = preview_match_for_candidate(job, candidate)
        if reason["score"] >= 50:
            items.append({"job_id": job.id, "candidate_id": candidate.id, "candidate": candidate.to_dict(), "score": reason["score"], "reason": reason})
    items.sort(key=lambda item: item["score"], reverse=True)
    return ok({"job": job.to_dict(), "items": items[:limit]})


@api.post("/boss/candidates/batch-import")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_batch_import(user):
    payload = request.get_json(force=True)
    imported = []
    errors = []
    for item in payload.get("items", []):
        if item.get("candidate_id"):
            candidate = db.session.get(Candidate, item["candidate_id"])
            if candidate:
                imported.append(candidate.to_dict())
            continue
        raw_text = item.get("raw_text") or item.get("summary") or ""
        if not looks_like_boss_resume_text(raw_text):
            errors.append({"name": item.get("name") or "候选人", "error": "不是候选人简历内容，已跳过"})
            continue
        try:
            _, candidate = parse_and_save_text(raw_text, user, source="boss", filename=f"boss-batch-{item.get('external_id') or len(imported) + 1}.txt")
        except ValueError as exc:
            errors.append({"name": item.get("name") or "候选人", "error": str(exc)})
            continue
        imported.append(candidate.to_dict(detail=True))
    db.session.commit()
    return ok({"items": imported, "errors": errors}, "BOSS 候选人已导入人才库")


@api.post("/boss/candidates/ai-screen")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_ai_screen(user):
    payload = request.get_json(force=True)
    job = db.session.get(Job, payload.get("job_id"))
    if not job:
        return error("岗位不存在", "NOT_FOUND", 404)
    candidate_ids = payload.get("candidate_ids") or []
    if not candidate_ids:
        candidate_ids = [item["candidate_id"] for item in preview_matches(job, limit=int(payload.get("limit") or 5))]
    created = []
    skipped = []
    for candidate_id in candidate_ids:
        candidate = db.session.get(Candidate, candidate_id)
        if not candidate:
            continue
        latest = latest_pipeline_item(job.id, candidate.id)
        if latest and latest.stage != "rejected":
            skipped.append({"candidate_id": candidate.id, "stage": latest.stage})
            continue
        reason = preview_match_for_candidate(job, candidate)
        item = PipelineStage(
            candidate_id=candidate.id,
            job_id=job.id,
            stage="ai_screen",
            updated_by=user.id,
            note=f"BOSS AI 初筛：匹配分 {reason['score']}",
        )
        db.session.add(item)
        db.session.flush()
        created.append(item.to_dict())
    db.session.commit()
    return ok({"created": created, "skipped": skipped}, "BOSS AI 初筛已写入流程")


@api.post("/boss/screen-resume/import")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_screen_resume_import(user):
    payload = request.get_json(force=True)
    raw_text = payload.get("raw_text") or payload.get("text") or ""
    if not looks_like_boss_resume_text(raw_text):
        return error("不是候选人简历内容，已跳过", "PARSE_FAILED", 400)
    try:
        batch, candidate = parse_and_save_text(raw_text, user, source="boss", filename="boss-screen-resume.txt")
    except ValueError as exc:
        return error(str(exc), "PARSE_FAILED", 400)

    draft = None
    job_id = payload.get("job_id")
    if job_id:
        job = db.session.get(Job, job_id)
        if not job:
            return error("岗位不存在", "NOT_FOUND", 404)
        draft = create_boss_draft(candidate, job)
        db.session.add(draft)
        db.session.commit()

    return ok(
        {
            "batch": batch.to_dict(),
            "candidate": candidate.to_dict(detail=True),
            "draft": draft.to_dict() if draft else None,
            "chunk_count": int(payload.get("chunk_count") or 0),
            "text_length": len(raw_text),
        },
        "BOSS 页面简历已导入人才库",
    )


@api.post("/boss/messages/draft")
@login_required
@roles_required("admin", "manager", "recruiter")
def boss_message_draft(user):
    payload = request.get_json(force=True)
    candidate = db.session.get(Candidate, payload.get("candidate_id"))
    job = db.session.get(Job, payload.get("job_id"))
    if not candidate or not job:
        return error("候选人或岗位不存在", "NOT_FOUND", 404)
    draft = create_boss_draft(candidate, job)
    db.session.add(draft)
    db.session.commit()
    return ok(draft.to_dict(), "话术草稿已生成，需 HR 审核后手动发送")


@api.get("/boss/messages/drafts")
@login_required
def list_boss_drafts(user):
    drafts, meta = paginate_query(BossDraft.query.order_by(BossDraft.created_at.desc()))
    return ok({"items": [draft.to_dict() for draft in drafts], **meta})


@api.patch("/boss/messages/drafts/<int:draft_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def update_boss_draft(user, draft_id):
    draft = db.session.get(BossDraft, draft_id)
    if not draft:
        return error("话术草稿不存在", "NOT_FOUND", 404)
    payload = request.get_json(force=True)
    if "status" in payload:
        if payload["status"] not in {"draft", "reviewed", "approved", "sent", "archived"}:
            return error("草稿状态不合法")
        draft.status = payload["status"]
    if "content" in payload:
        content = str(payload.get("content") or "").strip()
        if not content:
            return error("话术内容不能为空")
        draft.content = content
    db.session.commit()
    return ok(draft.to_dict(), "话术草稿已更新")


@api.delete("/boss/messages/drafts/<int:draft_id>")
@login_required
@roles_required("admin", "manager", "recruiter")
def delete_boss_draft(user, draft_id):
    draft = db.session.get(BossDraft, draft_id)
    if not draft:
        return error("话术草稿不存在", "NOT_FOUND", 404)
    db.session.delete(draft)
    db.session.commit()
    return ok({"deleted": draft_id}, "话术草稿已删除")


@api.post("/boss/messages/drafts/<int:draft_id>/approve")
@login_required
@roles_required("admin", "manager", "recruiter")
def approve_boss_draft(user, draft_id):
    return set_boss_draft_status(draft_id, "approved", "话术草稿已审核通过")


@api.post("/boss/messages/drafts/<int:draft_id>/mark-sent")
@login_required
@roles_required("admin", "manager", "recruiter")
def mark_boss_draft_sent(user, draft_id):
    return set_boss_draft_status(draft_id, "sent", "话术已标记为已发送")


@api.post("/boss/messages/drafts/<int:draft_id>/cancel")
@login_required
@roles_required("admin", "manager", "recruiter")
def cancel_boss_draft(user, draft_id):
    return set_boss_draft_status(draft_id, "archived", "话术草稿已取消")


def set_boss_draft_status(draft_id, status, message):
    draft = db.session.get(BossDraft, draft_id)
    if not draft:
        return error("话术草稿不存在", "NOT_FOUND", 404)
    draft.status = status
    db.session.commit()
    return ok(draft.to_dict(), message)


def create_boss_draft(candidate, job):
    tags = "、".join(tag.tag for tag in candidate.tags[:5]) or candidate.title
    content = (
        f"您好，看到您有{candidate.title}相关经历，简历里体现了{tags}等能力，"
        f"和我们正在招聘的「{job.title}」比较匹配。方便的话想进一步沟通岗位职责、团队情况和薪资范围。"
    )
    return BossDraft(candidate_id=candidate.id, job_id=job.id, content=content)


def boss_inbox_item(candidate):
    summary = (candidate.resume_json or {}).get("summary") or candidate.raw_text
    return {
        "external_id": f"candidate-{candidate.id}",
        "candidate_id": candidate.id,
        "name": candidate.name_masked,
        "title": candidate.title,
        "summary": summarize_text(summary, 120),
        "imported": True,
        "created_at": candidate.created_at.isoformat(),
    }


def looks_like_boss_resume_text(text):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) < 30:
        return False
    noise_words = ["招聘规范", "账号权益", "续费VIP", "职位管理", "推荐牛人", "我的客服", "道具", "工具箱"]
    if sum(1 for word in noise_words if word in value) >= 2 and not re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+", value):
        return False
    evidence = [
        bool(re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+", value)),
        bool(re.search(r"\d+\s*年|应届|在校|本科|大专|硕士|博士|\d+\s*(years?|yrs?)|bachelor|master|phd|college|university|education", value, re.I)),
        bool(re.search(r"经验|项目|职责|教育|求职|简历|熟悉|负责|开发|会计|运营|销售|产品|设计|测试|人事|行政|experience|project|responsib|resume|profile|familiar|develop|engineer|accounting|operation|sales|product|design|test|hr|admin", value, re.I)),
    ]
    return sum(evidence) >= 2


def latest_boss_account(user):
    query = BossAccount.query
    if user.role != "admin":
        query = query.filter_by(owner_hr_id=user.id)
    return query.order_by(BossAccount.updated_at.desc()).first()


def valid_boss_candidates(limit=100):
    return [
        candidate
        for candidate in Candidate.query.filter_by(source="boss").order_by(Candidate.created_at.desc()).limit(limit).all()
        if looks_like_boss_resume_text(candidate.raw_text)
    ]


def preview_match_for_candidate(job, candidate):
    structured = ensure_jd_structured(job)
    return match_candidate(
        structured.get("skill_tags_raw"),
        [tag.to_dict() for tag in candidate.tags],
        years_required=structured.get("years_required"),
        candidate_years=(candidate.resume_json or {}).get("experience_analysis", {}).get("years"),
        candidate_context=" ".join([candidate.title or "", candidate.raw_text or ""]),
    )


def ai_job_payload(payload, generate=False):
    title = str(payload.get("title") or "待定岗位").strip()
    city = str(payload.get("city") or "").strip()
    department = str(payload.get("department") or "").strip()
    jd_text = str(payload.get("jd_text") or "").strip()
    skill_tags_raw = str(payload.get("skill_tags_raw") or "").strip()
    base = {
        "title": title,
        "city": city,
        "department": department,
        "jd_text": jd_text or fallback_jd_text(title, city, department),
        "skill_tags_raw": skill_tags_raw,
        "source": "local",
    }
    if request.args.get("deepseek") == "1" and llm_available():
        try:
            data = chat_json(
                [
                    {
                        "role": "system",
                        "content": "你是招聘 JD 助手。必须围绕用户给的岗位名称生成，不要套用数据分析师模板。输出 JSON：{\"jd_text\":\"完整JD\",\"skill_tags_raw\":\"标签 1-5|标签 1-5\"}。技能标签只写岗位硬要求，不要写空泛词。",
                    },
                    {
                        "role": "user",
                        "content": f"岗位={title} 城市={city} 部门={department} 当前JD={jd_text} 当前技能权重={skill_tags_raw} 任务={'生成JD' if generate else '校准JD'}",
                    },
                ],
                temperature=0.2,
                timeout=30,
                source="job",
                tool_name="ai_generate_jd" if generate else "ai_calibrate_jd",
            )
            base["jd_text"] = str(data.get("jd_text") or base["jd_text"]).strip()
            base["skill_tags_raw"] = str(data.get("skill_tags_raw") or base["skill_tags_raw"]).strip()
            base["source"] = "deepseek"
        except LLMError:
            pass
    structured = build_jd_structured(base["jd_text"], base["skill_tags_raw"] or None)
    base["skill_tags_raw"] = "|".join(f"{item['tag']} {item['weight']}" for item in structured.get("skills", []))
    base["structured"] = structured
    return base


def fallback_jd_text(title, city="", department=""):
    place = f"工作地点：{city}\n" if city else ""
    team = f"所属部门：{department}\n" if department else ""
    return f"{place}{team}岗位名称：{title}\n岗位职责：负责{title}相关工作，推动业务目标落地。\n任职要求：具备相关岗位经验，沟通清晰，执行力强。"


@api.post("/agent/chat")
@login_required
@roles_required("admin", "manager", "recruiter")
def agent_chat(user):
    payload = request.get_json(force=True)
    message = payload.get("message", "")
    result = run_agent_tool(user, message, payload.get("pending_action"))
    audit_log(
        user,
        "agent_tool",
        "agent",
        None,
        str(result.get("tool") or "chat"),
        {"tool": result.get("tool"), "readonly": bool(result.get("readonly", True)), "message_length": len(str(message or ""))},
    )
    db.session.commit()
    return ok(result)


@api.get("/agent/tools")
@login_required
@roles_required("admin", "manager", "recruiter")
def agent_tools(user):
    return ok(
        {
            "items": [
                {"name": "get_candidate_segment_stats", "description": "统计人才库总人数、软件开发、会计、HR、销售、数据等人才分布"},
                {"name": "get_candidate_experience_stats", "description": "查询人才库经验档位分布"},
                {"name": "search_candidates", "description": "按姓名、岗位、城市、技能标签检索候选人"},
                {"name": "get_job_summary", "description": "查询岗位数量、开放/关闭状态和最近岗位"},
                {"name": "create_job", "description": "根据自然语言创建岗位并结构化 JD"},
                {"name": "match_candidates_for_job", "description": "按岗位预览推荐候选人，不写入匹配结果"},
                {"name": "get_pipeline_funnel", "description": "查询招聘流程漏斗"},
                {"name": "get_interview_schedule", "description": "查询面试安排和待反馈数量"},
                {"name": "get_offer_status", "description": "查询 Offer 状态和最近 Offer"},
                {"name": "get_boss_status", "description": "查询 BOSS 闭环连接状态、候选人收件箱和同步岗位数量"},
                {"name": "get_bi_snapshot", "description": "查询招聘总览指标"},
                {"name": "get_user_summary", "description": "管理员查询账号角色和启用状态"},
                {"name": "chat", "description": "普通对话、能力说明和下一步引导"},
            ],
            "readonly": False,
        }
    )


def with_permissions(user):
    data = user.to_dict()
    data["permissions"] = role_permissions(user.role)
    return data


def can_view_employee_salary(user):
    return user.role in {"admin", "manager"}


def employee_payload(employee, user, detail=False):
    return employee.to_dict(detail=detail, include_salary=can_view_employee_salary(user))


def run_agent_tool(user, message, pending_action=None):
    text = (message or "").strip()
    lowered = text.lower()
    suggestions = [
        "现在人才库有多少人？软件开发和会计分别多少？",
        "创建岗位 数据分析师 城市上海 部门数据部 JD 要求 SQL、Python、报表分析，3 年以上经验",
        "推荐财务会计主管候选人",
        "现在面试和 Offer 状态怎么样？",
    ]

    if pending_action:
        return continue_pending_agent_action(user, text, pending_action, suggestions)

    if is_greeting_or_smalltalk(text):
        return {
            "answer": "你好，我是 AI 招聘 Agent。你可以直接让我查人才库人数、统计软件开发/会计人才、创建岗位、推荐候选人，或者查看流程、面试、Offer、BOSS 和 BI 数据。",
            "tool": "chat",
            "result": {"capabilities": [item for item in suggestions]},
            "suggestions": suggestions,
            "readonly": True,
        }

    if is_create_job_request(text):
        return create_job_from_agent(user, text, suggestions)

    if is_candidate_count_request(text):
        stats = candidate_segment_stats()
        requested = requested_segments(text)
        if requested:
            parts = [f"{stats['segments'][segment]['label']} {stats['segments'][segment]['count']} 人" for segment in requested]
            answer = f"当前人才库共 {stats['total']} 人，其中" + "，".join(parts) + "。"
        else:
            answer = (
                f"当前人才库共 {stats['total']} 人，软件开发 {stats['segments']['software']['count']} 人，"
                f"会计/财务 {stats['segments']['accounting']['count']} 人，HR {stats['segments']['hr']['count']} 人，"
                f"销售/商务 {stats['segments']['sales']['count']} 人。"
            )
        return {
            "answer": answer,
            "tool": "get_candidate_segment_stats",
            "result": stats,
            "suggestions": suggestions,
            "readonly": True,
        }

    if "offer" in lowered or "入职" in text:
        offers = OfferRecord.query.order_by(OfferRecord.updated_at.desc()).all()
        counts = Counter(offer.status for offer in offers)
        recent = [offer.to_dict() for offer in offers[:5]]
        return {
            "answer": f"当前共有 {len(offers)} 条 Offer，已接受 {counts.get('accepted', 0)} 条，已发放待确认 {counts.get('sent', 0)} 条。",
            "tool": "get_offer_status",
            "result": {"counts": {status: counts.get(status, 0) for status in sorted(OFFER_STATUSES)}, "recent": recent},
            "suggestions": suggestions,
            "readonly": True,
        }

    if "面试" in text:
        assignments = InterviewAssignment.query.order_by(InterviewAssignment.scheduled_at.desc()).all()
        counts = Counter(assignment.status for assignment in assignments)
        upcoming = [assignment.to_dict() for assignment in assignments[:8]]
        return {
            "answer": f"当前共有 {len(assignments)} 条面试安排，待反馈 {counts.get('scheduled', 0)} 条，已反馈 {counts.get('completed', 0)} 条。",
            "tool": "get_interview_schedule",
            "result": {"counts": dict(counts), "upcoming": upcoming},
            "suggestions": suggestions,
            "readonly": True,
        }

    if "漏斗" in text or "流程" in text or "阶段" in text:
        pipeline = Counter(item.stage for item in latest_pipeline_items())
        result = {stage: pipeline.get(stage, 0) for stage in STAGES}
        active_count = sum(value for stage, value in result.items() if stage not in {"onboarded", "rejected"})
        return {
            "answer": f"当前流程中活跃候选人 {active_count} 人，Offer 阶段 {result.get('offer', 0)} 人，已入职 {result.get('onboarded', 0)} 人。",
            "tool": "get_pipeline_funnel",
            "result": result,
            "suggestions": suggestions,
            "readonly": True,
        }

    if "岗位" in text and "推荐" not in text and "匹配" not in text:
        jobs = Job.query.order_by(Job.created_at.desc()).all()
        counts = Counter(job.status for job in jobs)
        detail = format_job_list(jobs)
        return {
            "answer": f"当前共有 {len(jobs)} 个岗位，开放 {counts.get('active', 0)} 个，关闭 {counts.get('closed', 0)} 个。\n{detail}",
            "tool": "get_job_summary",
            "result": {"counts": dict(counts), "recent": [job.to_dict() for job in jobs[:8]]},
            "suggestions": ["给所有开放岗位匹配最佳候选人", "推荐财务会计主管候选人", "创建一个 Java 后端岗位", "流程漏斗怎么样？"],
            "readonly": True,
        }

    if "经验" in text or "档位" in text or "年限" in text:
        data = experience_stats(Candidate.query.all())
        total = sum(item["count"] for item in data)
        return {
            "answer": f"当前人才库共 {total} 人，经验档位统计已按简历解析口径返回。",
            "tool": "get_candidate_experience_stats",
            "result": data,
            "suggestions": suggestions,
            "readonly": True,
        }

    if "推荐" in text or "匹配" in text or "最佳候选人" in text:
        jobs = jobs_for_match_request(text)
        if not jobs:
            return {
                "answer": "当前还没有岗位，无法执行候选人推荐。",
                "tool": "match_candidates_for_job",
                "result": {"items": []},
                "suggestions": suggestions,
                "readonly": True,
            }
        results = []
        for job in jobs:
            job.jd_structured = ensure_jd_structured(job)
            matches = preview_matches(job, limit=5)
            results.append({"job": job.to_dict(), "items": matches})
        db.session.commit()
        first = results[0]
        return {
            "answer": format_match_results(results),
            "tool": "match_candidates_for_job",
            "result": {"job": first["job"], "items": first["items"], "jobs": results},
            "suggestions": ["把第一名加入流程", "查看岗位明细", "继续匹配其他岗位", "查看 BOSS 同步状态"],
            "readonly": True,
        }

    if "候选人" in text or "人才" in text or "找" in text or "搜索" in text:
        items = search_candidates_for_agent(text)
        return {
            "answer": f"找到 {len(items)} 位相关候选人，已按关键词和标签命中排序。",
            "tool": "search_candidates",
            "result": {"items": items},
            "suggestions": suggestions,
            "readonly": True,
        }

    if "boss" in lowered:
        inbox = [boss_inbox_item(candidate) for candidate in Candidate.query.filter_by(source="boss").order_by(Candidate.created_at.desc()).limit(20).all() if looks_like_boss_resume_text(candidate.raw_text)]
        jobs = Job.query.filter(Job.job_code.like("BOSS-%")).order_by(Job.created_at.desc()).limit(20).all()
        account = latest_boss_account(user)
        return {
            "answer": f"BOSS 当前为半自动模式，已同步候选人 {len(inbox)} 位，BOSS 岗位 {len(jobs)} 个。",
            "tool": "get_boss_status",
            "result": {"status": {"cookie_bound": bool(account), "account": account.account if account else "未绑定", "mode": "半自动", "can_auto_send": False}, "inbox": inbox, "jobs": [job.to_dict() for job in jobs]},
            "suggestions": suggestions,
            "readonly": True,
        }

    if "用户" in text or "账号" in text or "权限" in text:
        if user.role != "admin":
            return {
                "answer": "账号和权限信息仅管理员可查询。你可以让我查询人才、岗位、流程、面试、Offer 和 BI。",
                "tool": "get_user_summary",
                "result": {"allowed": False},
                "suggestions": suggestions,
                "readonly": True,
            }
        users = User.query.order_by(User.id.asc()).all()
        roles = Counter(item.role for item in users)
        return {
            "answer": f"当前共有 {len(users)} 个账号，管理员 {roles.get('admin', 0)} 个，招聘经理 {roles.get('manager', 0)} 个，HR {roles.get('recruiter', 0)} 个，面试官 {roles.get('interviewer', 0)} 个。",
            "tool": "get_user_summary",
            "result": {"roles": dict(roles), "items": [with_permissions(item) for item in users]},
            "suggestions": suggestions,
            "readonly": True,
        }

    if is_bi_request(text):
        snapshot = bi_snapshot()
        return {
            "answer": f"当前人才库 {snapshot['total_candidates']} 人，开放岗位 {snapshot['active_jobs']} 个，Offer 已接受 {snapshot['offer_status'].get('accepted', 0)} 条。",
            "tool": "get_bi_snapshot",
            "result": snapshot,
            "suggestions": suggestions,
            "readonly": True,
        }

    return free_agent_chat(text, suggestions)


def free_agent_chat(text, suggestions):
    if not llm_available():
        return {
            "answer": "我可以继续自由对话，但当前 DeepSeek 未启用。你也可以直接让我查人才库、创建岗位、推荐候选人、看流程/面试/Offer/BOSS/BI。",
            "tool": "chat",
            "result": {"llm": "disabled"},
            "suggestions": suggestions,
            "readonly": True,
        }
    snapshot = bi_snapshot()
    jobs = Job.query.order_by(Job.created_at.desc()).limit(5).all()
    messages = [
        {
            "role": "system",
            "content": (
                "你是 HireInsight 招聘 AI Agent。你可以自由回答招聘系统相关问题，但不能编造系统数据。"
                "已有确定工具能力：查人才库统计、查候选人、创建岗位、推荐候选人、查流程、面试、Offer、BOSS、BI。"
                "涉及创建岗位、删除、发送消息等写操作时，提醒用户需要明确指令或人工确认。"
                "输出 JSON：{\"answer\":\"中文回答\",\"suggestions\":[\"下一步建议1\",\"下一步建议2\",\"下一步建议3\"]}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"系统快照={snapshot}\n"
                f"最近岗位={[job.to_dict() for job in jobs]}\n"
                f"用户问题={text}"
            ),
        },
    ]
    try:
        data = chat_json(messages, temperature=0.3, timeout=30, source="agent", tool_name="chat")
    except LLMError as exc:
        return {
            "answer": f"我理解你的问题，但 DeepSeek 暂时不可用：{str(exc)[:120]}。你可以先使用已接入的模块工具继续操作。",
            "tool": "chat",
            "result": {"llm_error": str(exc)},
            "suggestions": suggestions,
            "readonly": True,
        }
    return {
        "answer": str(data.get("answer") or "我可以继续帮你处理招聘相关问题。"),
        "tool": "chat",
        "result": {"llm": "deepseek"},
        "suggestions": data.get("suggestions") or suggestions,
        "readonly": True,
    }


def is_greeting_or_smalltalk(text):
    compact = re.sub(r"[\s，,。.!！?？～~]", "", text.lower())
    return compact in {"你好", "您好", "hi", "hello", "hey", "在吗", "开始", "测试"}


def is_bi_request(text):
    return any(keyword in text for keyword in ["总览", "概览", "BI", "bi", "看板", "数据情况", "整体情况"])


def is_create_job_request(text):
    return ("创建" in text or "新增" in text or "发布" in text or "生成" in text) and "岗位" in text


def continue_pending_agent_action(user, text, pending_action, suggestions):
    if not isinstance(pending_action, dict) or pending_action.get("type") != "create_job":
        return free_agent_chat(text, suggestions)
    if is_agent_cancel(text):
        return {
            "answer": "已取消当前岗位创建草案，没有写入系统。你可以重新描述一个岗位，或者继续让我查询人才库和推荐候选人。",
            "tool": "create_job",
            "result": {"created": False, "cancelled": True},
            "pending_action": None,
            "suggestions": suggestions,
            "readonly": False,
        }
    payload = dict(pending_action.get("payload") or {})
    if is_agent_confirm(text):
        return create_job_from_payload(user, payload)
    updates = parse_job_payload_from_message(text)
    for key, value in updates.items():
        if value:
            payload[key] = value
    return job_draft_response(payload, suggestions, prefix="我已根据你的补充更新岗位草案。")


def is_agent_confirm(text):
    compact = re.sub(r"\s+", "", text or "")
    return any(word in compact for word in ["确认创建", "确认发布", "确认保存", "可以创建", "就这样", "没问题", "确认"])


def is_agent_cancel(text):
    compact = re.sub(r"\s+", "", text or "")
    return any(word in compact for word in ["取消", "不用了", "先不创建", "停止"])


def create_job_from_agent(user, text, suggestions):
    if user.role not in {"admin", "manager", "recruiter"}:
        return {
            "answer": "当前账号没有创建岗位权限。可以让管理员、招聘经理或 HR 账号执行这个动作。",
            "tool": "create_job",
            "result": {"allowed": False},
            "suggestions": suggestions,
            "readonly": False,
        }
    payload = parse_job_payload_from_message(text)
    if not payload["title"]:
        return {
            "answer": "我还缺岗位名称。可以这样说：创建岗位 数据分析师 城市上海 部门数据部 JD 要求 SQL、Python、报表分析，3 年以上经验。",
            "tool": "create_job",
            "result": {"created": False, "missing": ["title"]},
            "suggestions": suggestions,
            "readonly": False,
        }
    return job_draft_response(payload, suggestions)


def job_draft_response(payload, suggestions, prefix="我先整理成岗位草案，确认后再创建。"):
    payload = enrich_agent_job_payload(payload)
    missing = missing_agent_job_fields(payload)
    answer = format_agent_job_draft(payload, prefix, missing)
    return {
        "answer": answer,
        "tool": "create_job",
        "result": {"created": False, "draft": payload, "missing": missing},
        "pending_action": {"type": "create_job", "payload": payload},
        "suggestions": ["确认创建", "补充薪资 20-30K", "补充要求 5 年以上经验，本科，熟悉 Spring Boot 和微服务", "取消"],
        "readonly": False,
    }


def create_job_from_payload(user, payload):
    payload = enrich_agent_job_payload(dict(payload or {}))
    missing = missing_agent_job_fields(payload)
    if missing:
        return job_draft_response(payload, [], prefix="还差一些关键信息，我先不创建。")
    job = Job(
        owner_hr_id=user.id,
        title=payload["title"],
        city=payload.get("city"),
        department=payload.get("department"),
        job_code=payload.get("job_code"),
        jd_text=payload["jd_text"],
        jd_structured=build_jd_structured(payload["jd_text"], payload.get("skill_tags_raw")),
    )
    db.session.add(job)
    db.session.commit()
    return {
        "answer": f"已创建岗位「{job.title}」，城市 {job.city or '未填写'}，部门 {job.department or '未填写'}。JD 已完成结构化，可到岗位匹配模块继续查看和执行匹配。",
        "tool": "create_job",
        "result": {"created": True, "job": job.to_dict()},
        "pending_action": None,
        "suggestions": ["推荐这个岗位的候选人", "现在岗位有多少个？", "现在人才库软件开发人员有多少？", "流程漏斗怎么样？"],
        "readonly": False,
    }


def enrich_agent_job_payload(payload):
    title = str(payload.get("title") or "").strip()
    city = payload.get("city")
    department = payload.get("department")
    jd_text = str(payload.get("jd_text") or "").strip()
    skill_tags_raw = str(payload.get("skill_tags_raw") or "").strip()
    if title and len(jd_text) < 80:
        jd_text = generate_agent_jd_text(title, city, department, jd_text)
    structured = build_jd_structured(jd_text or title, skill_tags_raw or None)
    payload.update(
        {
            "title": title[:128],
            "city": city,
            "department": department,
            "job_code": payload.get("job_code"),
            "skill_tags_raw": "|".join(f"{item['tag']} {item['weight']}" for item in structured.get("skills", [])),
            "jd_text": jd_text,
        }
    )
    return payload


def generate_agent_jd_text(title, city="", department="", base=""):
    context = f"用户补充：{base}" if base else ""
    if llm_available():
        try:
            data = chat_json(
                [
                    {"role": "system", "content": "你是招聘岗位顾问。根据岗位名称和用户补充，生成具体 JD。输出 JSON：{\"jd_text\":\"\"}。JD 必须包含岗位职责、任职要求、加分项，不能空泛。"},
                    {"role": "user", "content": f"岗位={title}\n城市={city or ''}\n部门={department or ''}\n{context}"},
                ],
                temperature=0.25,
                timeout=30,
                source="agent",
                tool_name="create_job_draft",
            )
            jd_text = str(data.get("jd_text") or "").strip()
            if jd_text:
                return jd_text
        except LLMError:
            pass
    return fallback_jd_text(title, city or "", department or "") + (f"\n补充要求：{base}" if base else "")


def missing_agent_job_fields(payload):
    missing = []
    if not payload.get("title"):
        missing.append("岗位名称")
    if not payload.get("city"):
        missing.append("工作城市")
    if len(str(payload.get("jd_text") or "")) < 80:
        missing.append("具体 JD 要求")
    if not payload.get("skill_tags_raw"):
        missing.append("技能权重")
    return missing


def format_agent_job_draft(payload, prefix, missing):
    structured = build_jd_structured(payload.get("jd_text") or "", payload.get("skill_tags_raw") or None)
    skills = "、".join(f"{item['tag']}({item['weight']}/5)" for item in structured.get("skills", [])[:8]) or "待补充"
    missing_text = "；还需要补充：" + "、".join(missing) if missing else ""
    return (
        f"{prefix}\n"
        f"岗位：{payload.get('title') or '待补充'}\n"
        f"城市：{payload.get('city') or '待补充'}\n"
        f"部门：{payload.get('department') or '未填写'}\n"
        f"技能权重：{skills}\n"
        f"JD 摘要：{summarize_text(payload.get('jd_text'), 260)}\n"
        f"{missing_text}\n"
        "如果没问题，请回复“确认创建”；如果要调整，直接补充城市、薪资、年限、学历、职责或技能要求。"
    ).strip()


def parse_job_payload_from_message(text):
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    rest_match = re.search(r"(?:创建|新增|发布|生成).{0,6}岗位\s*[:：]?\s*(.*)", normalized, flags=re.I)
    rest = rest_match.group(1).strip() if rest_match else normalized
    title = re.split(r"\s*(?:城市|地点|部门|JD|jd|要求|职责|薪资|技能)\s*[:：]?", rest, maxsplit=1)[0].strip(" ，,。；;")
    city = extract_agent_field(normalized, ["城市", "地点"])
    department = extract_agent_field(normalized, ["部门"])
    job_code = extract_agent_field(normalized, ["编号", "编码"])
    skill_tags_raw = extract_agent_field(normalized, ["技能"])
    jd = extract_agent_jd(normalized)
    if not jd:
        jd = f"{title}。{normalized}" if title else normalized
    return {"title": title[:128], "city": city, "department": department, "job_code": job_code, "skill_tags_raw": skill_tags_raw, "jd_text": jd}


def extract_agent_field(text, labels):
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{label_pattern})\s*[:：]?\s*([^，,。；;\s]+)", text, flags=re.I)
    return match.group(1).strip() if match else None


def extract_agent_jd(text):
    match = re.search(r"(?:JD|jd|要求|职责)\s*[:：]?\s*(.+)", text, flags=re.I)
    if not match:
        return ""
    jd = match.group(1).strip()
    return jd[:5000]


def is_candidate_count_request(text):
    return ("多少" in text or "几" in text or "统计" in text) and (
        "人才" in text
        or "候选人" in text
        or any(keyword in text for keyword in ["软件", "开发", "程序", "会计", "财务", "招聘", "人力", "销售", "数据"])
    )


def requested_segments(text):
    segments = []
    mapping = {
        "software": ["软件", "开发", "程序", "前端", "后端", "工程师", "Java", "Python", "React"],
        "accounting": ["会计", "财务", "税务", "总账", "出纳"],
        "hr": ["招聘", "人力", "HR", "薪酬", "绩效"],
        "sales": ["销售", "商务", "客户", "渠道"],
        "data": ["数据", "分析", "BI", "报表", "SQL"],
    }
    for segment, keywords in mapping.items():
        if any(keyword.lower() in text.lower() for keyword in keywords):
            segments.append(segment)
    return list(dict.fromkeys(segments))


def candidate_segment_stats():
    candidates = Candidate.query.order_by(Candidate.created_at.desc()).all()
    segment_meta = {
        "software": "软件开发",
        "accounting": "会计/财务",
        "hr": "人力资源",
        "sales": "销售/商务",
        "data": "数据/BI",
        "other": "其他",
    }
    buckets = {key: [] for key in segment_meta}
    for candidate in candidates:
        segments = classify_candidate_segments(candidate)
        for segment in segments or ["other"]:
            buckets[segment].append(candidate.to_dict())
    return {
        "total": len(candidates),
        "segments": {
            key: {"label": label, "count": len(buckets[key]), "items": buckets[key][:8]}
            for key, label in segment_meta.items()
        },
    }


def classify_candidate_segments(candidate):
    text = " ".join(
        [
            candidate.title or "",
            candidate.raw_text or "",
            " ".join(tag.tag for tag in candidate.tags),
            " ".join(tag.category for tag in candidate.tags),
        ]
    ).lower()
    rules = {
        "software": ["软件", "开发", "前端", "后端", "全栈", "java", "python", "react", "typescript", "javascript", "flask", "fastapi"],
        "accounting": ["会计", "财务", "税务", "纳税", "总账", "出纳", "金蝶", "用友"],
        "hr": ["招聘", "人力", "hr", "薪酬", "绩效", "员工关系", "面试安排"],
        "sales": ["销售", "商务", "客户成功", "渠道", "大客户", "bd"],
        "data": ["数据", "分析", "bi", "sql", "报表", "看板"],
    }
    return [segment for segment, keywords in rules.items() if any(keyword in text for keyword in keywords)]


def find_job_from_message(message):
    for job in Job.query.order_by(Job.created_at.desc()).all():
        if job.title and job.title in message:
            return job
    compact = re.sub(r"\s+", "", message).lower()
    scored = []
    for job in Job.query.order_by(Job.created_at.desc()).all():
        haystack = re.sub(r"\s+", "", " ".join([job.title or "", job.city or "", job.department or "", job.jd_text or ""])).lower()
        score = sum(1 for token in re.split(r"[，,。；;\s]+", message) if len(token) >= 2 and token.lower() in haystack)
        if not score and job.title and any(part and part in compact for part in re.split(r"[/+＋\s]+", job.title.lower())):
            score = 1
        if score:
            scored.append((score, job))
    if scored:
        return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]
    return None


def jobs_for_match_request(message):
    if any(word in message for word in ["所有岗位", "全部岗位", "每个岗位", "各岗位"]):
        return Job.query.filter_by(status="active").order_by(Job.created_at.desc()).limit(8).all()
    job = find_job_from_message(message)
    if job:
        return [job]
    if "岗位" in message and "最佳候选人" in message:
        return Job.query.filter_by(status="active").order_by(Job.created_at.desc()).limit(8).all()
    fallback = Job.query.filter_by(status="active").first() or Job.query.first()
    return [fallback] if fallback else []


def format_job_list(jobs):
    if not jobs:
        return "暂无岗位。"
    lines = []
    for index, job in enumerate(jobs[:10], 1):
        structured = ensure_jd_structured(job)
        skills = "、".join(skill["tag"] for skill in structured.get("skills", [])[:5]) or "未识别技能"
        lines.append(f"{index}. {job.title}（{job.status}）｜{job.city or '未填城市'}｜{job.department or '未填部门'}｜关键技能：{skills}")
    if len(jobs) > 10:
        lines.append(f"只显示前 10 个，剩余 {len(jobs) - 10} 个可按岗位名称继续查询。")
    return "\n".join(lines)


def format_match_results(results):
    lines = ["已从人才库按岗位匹配最佳候选人（预览不写入匹配结果）："]
    for result in results:
        job = result["job"]
        best = result["items"][0] if result["items"] else None
        if not best:
            lines.append(f"- {job['title']}：暂无候选人。")
            continue
        candidate = best["candidate"]
        hits = "、".join(hit["candidate_tag"] for hit in best["reason"].get("hits", [])[:5]) or "暂无命中标签"
        missing = "、".join(best["reason"].get("missing_tags", [])[:3]) or "无明显缺失"
        lines.append(f"- {job['title']}：最佳候选人 {candidate['name_masked']}，匹配分 {best['score']}。命中：{hits}；缺失：{missing}。")
    return "\n".join(lines)


def search_candidates_for_agent(message):
    keywords = [word.strip() for word in message.replace("，", " ").replace("？", " ").replace("?", " ").split() if len(word.strip()) >= 2]
    candidates = Candidate.query.order_by(Candidate.created_at.desc()).all()
    scored = []
    for candidate in candidates:
        haystack = " ".join(
            [
                candidate.name_masked or "",
                candidate.title or "",
                candidate.city or "",
                candidate.source or "",
                " ".join(tag.tag for tag in candidate.tags),
                " ".join(tag.category for tag in candidate.tags),
            ]
        )
        score = sum(1 for keyword in keywords if keyword.lower() in haystack.lower())
        if not keywords or score:
            data = candidate.to_dict()
            data["match_score"] = score
            scored.append(data)
    return sorted(scored, key=lambda item: (item["match_score"], len(item.get("tags", []))), reverse=True)[:8]


def bi_snapshot():
    candidates = Candidate.query.all()
    pipeline = Counter(item.stage for item in latest_pipeline_items())
    offers = Counter(offer.status for offer in OfferRecord.query.all())
    return {
        "total_candidates": len(candidates),
        "active_jobs": Job.query.filter_by(status="active").count(),
        "pipeline_funnel": {stage: pipeline.get(stage, 0) for stage in STAGES},
        "offer_status": {status: offers.get(status, 0) for status in sorted(OFFER_STATUSES)},
        "experience_stats": experience_stats(candidates),
    }


def experience_stats(candidates):
    stats = Counter("lt1" if candidate.resume_json.get("experience_analysis", {}).get("level") == "remote" else candidate.resume_json.get("experience_analysis", {}).get("level", "lt1") for candidate in candidates)
    labels = {"student": "在校生", "fresh": "应届毕业", "lt1": "1 年以下", "1-3": "1-3 年", "3-5": "3-5 年", "5-10": "5-10 年", "gt10": "10 年以上"}
    return [{"key": key, "label": labels[key], "count": stats.get(key, 0)} for key in labels]


def latest_pipeline_items(job_id=None, since=None):
    query = PipelineStage.query
    if job_id:
        query = query.filter_by(job_id=job_id)
    if since:
        query = query.filter(PipelineStage.ts >= since)
    items = query.order_by(PipelineStage.ts.desc()).all()
    seen = set()
    latest = []
    for item in items:
        key = (item.job_id, item.candidate_id)
        if key not in seen:
            latest.append(item)
            seen.add(key)
    return latest


def latest_pipeline_item(job_id, candidate_id):
    return (
        PipelineStage.query.filter_by(job_id=job_id, candidate_id=candidate_id)
        .order_by(PipelineStage.ts.desc())
        .first()
    )


def issue_interview_room_token(assignment_id):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=int(current_app.config.get("INTERVIEW_ROOM_TOKEN_HOURS", 72)))
    payload = {
        "scope": "interview_room",
        "assignment_id": assignment_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def assignment_from_room_token(token, allow_completed=False):
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("scope") != "interview_room":
        return None
    assignment = db.session.get(InterviewAssignment, int(payload.get("assignment_id") or 0))
    allowed = {"scheduled", "completed"} if allow_completed else {"scheduled"}
    if not assignment or assignment.status not in allowed:
        return None
    return assignment


def build_interview_ai_plan(assignment, prefer_deepseek=False):
    if assignment.ai_plan and not prefer_deepseek:
        return assignment.ai_plan
    candidate = assignment.candidate
    job = assignment.job
    tags = [tag.to_dict() for tag in candidate.tags]
    top_tags = "、".join(tag["tag"] for tag in sorted(tags, key=lambda item: item["score"], reverse=True)[:8]) or "暂无技能标签"
    resume = candidate.resume_json or {}
    payload = {
        "avatar": {"name": "AI 面试官", "role": stageLabels_backend(assignment.round), "voice": "zh-CN"},
        "meeting": {
            "provider": "腾讯会议",
            "location": assignment.location or "腾讯会议",
            "auto_join": False,
            "note": "站内模拟人可自动提问；腾讯会议自动入会需要企业开放平台授权。",
        },
        "opening": f"你好 {candidate.name_masked}，我是本轮 {stageLabels_backend(assignment.round)} 的 AI 面试官。接下来会围绕 {job.title} 和你的简历经历进行提问。",
        "questions": fallback_interview_questions(candidate, job, top_tags),
        "rubric": ["岗位关键技能是否匹配", "项目/经历证据是否真实具体", "表达是否结构化", "风险点是否可解释"],
        "closing": "本轮模拟面试结束，我会根据回答整理优势、风险和建议结论。",
        "source": "local",
    }
    if prefer_deepseek and llm_available():
        try:
            data = chat_json(
                [
                    {
                        "role": "system",
                        "content": "你是招聘 AI 面试官。根据岗位 JD 和简历生成结构化模拟面试方案。输出 JSON：{\"opening\":\"\",\"questions\":[{\"type\":\"\",\"question\":\"\",\"rubric\":\"\"}],\"rubric\":[],\"closing\":\"\"}。问题必须具体、可追问，不要泛泛而谈。",
                    },
                    {
                        "role": "user",
                        "content": f"岗位={job.title}\nJD={job.jd_text}\n岗位技能={ensure_jd_structured(job).get('skill_tags_raw')}\n候选人={candidate.name_masked} {candidate.title}\n简历摘要={resume.get('summary') or summarize_text(candidate.raw_text, 600)}\n技能={top_tags}\n轮次={stageLabels_backend(assignment.round)}",
                    },
                ],
                temperature=0.2,
                timeout=30,
                source="interview",
                tool_name="interview_ai_plan",
            )
            payload["opening"] = str(data.get("opening") or payload["opening"])
            payload["questions"] = normalize_interview_questions(data.get("questions")) or payload["questions"]
            payload["rubric"] = [str(item) for item in data.get("rubric") or payload["rubric"]][:6]
            payload["closing"] = str(data.get("closing") or payload["closing"])
            payload["source"] = "deepseek"
        except LLMError:
            pass
    assignment.ai_plan = payload
    return payload


def build_interview_turn_reply(assignment, payload):
    question = str(payload.get("question") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    intent = str(payload.get("intent") or "followup").strip()
    candidate_question = str(payload.get("candidate_question") or "").strip()
    if intent == "clarify":
        base = {
            "reply": f"这道题主要想了解：{question}。你可以按“背景、你做了什么、结果是什么”来回答，不需要一次说得很完美。",
            "source": "local",
        }
        if llm_available():
            try:
                data = chat_json(
                    [
                        {"role": "system", "content": "你是 AI 面试官。候选人没理解题目时，用自然口吻解释题意，并给出回答方向。输出 JSON：{\"reply\":\"\"}。不要超过 120 字。"},
                        {"role": "user", "content": f"岗位={assignment.job.title}\n原题={question}\n候选人疑问={candidate_question or '没理解题目'}"},
                    ],
                    temperature=0.3,
                    timeout=12,
                    source="interview",
                    tool_name="interview_clarify_question",
                )
                base["reply"] = str(data.get("reply") or base["reply"]).strip()
                base["source"] = "deepseek"
            except LLMError:
                pass
        return base
    base = {
        "reply": "谢谢你的回答。我会继续追问一个细节：请补充你在这个经历中的具体职责、关键动作和可量化结果。",
        "source": "local",
    }
    if not answer:
        base["reply"] = "我还没有听到完整回答。请你结合一个真实项目，按背景、行动、结果三步说明。"
        return base
    if llm_available():
        try:
            data = chat_json(
                [
                    {"role": "system", "content": "你是 AI 面试官。根据候选人回答生成一句自然追问或确认语。输出 JSON：{\"reply\":\"\"}。不要超过 80 字。"},
                    {"role": "user", "content": f"岗位={assignment.job.title}\n问题={question}\n候选人回答={answer}\n简历={summarize_text(assignment.candidate.raw_text, 600)}"},
                ],
                temperature=0.3,
                timeout=12,
                source="interview",
                tool_name="interview_followup",
            )
            base["reply"] = str(data.get("reply") or base["reply"]).strip()
            base["source"] = "deepseek"
        except LLMError:
            pass
    return base


def save_public_interview_feedback(assignment, payload):
    answers = payload.get("answers") or []
    messages = payload.get("messages") or []
    cheat_events = payload.get("cheat_events") or []
    score_result = score_public_interview(assignment, answers, messages, cheat_events)
    rating = max(1, min(5, round(score_result["score"] / 20)))
    transcript_lines = ["AI 网页面试记录"]
    transcript_lines.append(f"AI评分：{score_result['score']}/100")
    transcript_lines.append(f"评分摘要：{score_result['summary']}")
    transcript_lines.append("维度评分：")
    for label, value in score_result["dimensions"].items():
        transcript_lines.append(f"{label}：{value}/100")
    for index, item in enumerate(answers, 1):
        text = summarize_text(item, 500)
        if text:
            transcript_lines.append(f"{index}. {text}")
    if messages:
        transcript_lines.append("对话流：")
        for item in messages[-30:]:
            role = "AI" if item.get("role") == "ai" else "候选人"
            transcript_lines.append(f"{role}：{summarize_text(item.get('text'), 500)}")
    if cheat_events:
        transcript_lines.append("防作弊记录：")
        transcript_lines.extend(summarize_text(item, 200) for item in cheat_events[-20:])
    feedback = InterviewFeedback.query.filter_by(assignment_id=assignment.id).first()
    if not feedback:
        feedback = InterviewFeedback(assignment_id=assignment.id, interviewer_id=assignment.interviewer_id, rating=rating, decision="hold")
        db.session.add(feedback)
    feedback.rating = rating
    feedback.decision = "hold"
    feedback.strengths = score_result["strengths"]
    feedback.risks = score_result["risks"]
    feedback.comment = "\n".join(transcript_lines)
    assignment.status = "completed"
    db.session.add(PipelineStage(candidate_id=assignment.candidate_id, job_id=assignment.job_id, stage=assignment.round, updated_by=assignment.interviewer_id, note=f"AI 网页面试已完成，评分 {rating}/5"))
    db.session.commit()
    return feedback


def score_public_interview(assignment, answers, messages, cheat_events):
    answered = sum(1 for item in answers if str(item or "").strip())
    total = max(len(answers), 1)
    base_score = max(20, min(100, round(answered / total * 80 + 20)))
    if cheat_events:
        base_score = max(20, base_score - min(len(cheat_events) * 5, 25))
    result = {
        "score": base_score,
        "summary": f"完成 {answered}/{total} 道题，防作弊记录 {len(cheat_events)} 次。",
        "dimensions": {
            "岗位匹配": base_score,
            "专业能力": base_score,
            "表达结构": min(100, base_score + (10 if answered == total else 0)),
            "真实性": max(20, base_score - (15 if cheat_events else 0)),
            "风险控制": max(20, 100 - min(len(cheat_events) * 15, 60)),
        },
        "strengths": "候选人已完成 AI 网页面试，回答内容可供人工复核。",
        "risks": "需人工复核回答真实性和岗位匹配度。" + (" 存在防作弊提醒。" if cheat_events else ""),
    }
    if llm_available():
        try:
            data = chat_json(
                [
                    {"role": "system", "content": "你是招聘面试评分官。根据岗位、回答和对话记录给出客观评分。输出 JSON：{\"score\":0-100,\"summary\":\"\",\"dimensions\":{\"岗位匹配\":0-100,\"专业能力\":0-100,\"表达结构\":0-100,\"真实性\":0-100,\"风险控制\":0-100},\"strengths\":\"\",\"risks\":\"\"}。"},
                    {"role": "user", "content": f"岗位={assignment.job.title}\n候选人={assignment.candidate.name_masked} {assignment.candidate.title}\n回答={answers}\n对话={messages[-20:] if messages else []}\n防作弊记录={cheat_events}"},
                ],
                temperature=0.2,
                timeout=15,
                source="interview",
                tool_name="interview_ai_scoring",
            )
            score = int(data.get("score", result["score"]))
            result = {
                "score": max(0, min(100, score)),
                "summary": str(data.get("summary") or result["summary"]),
                "dimensions": normalize_score_dimensions(data.get("dimensions"), result["dimensions"]),
                "strengths": str(data.get("strengths") or result["strengths"]),
                "risks": str(data.get("risks") or result["risks"]),
            }
        except (LLMError, TypeError, ValueError):
            pass
    return result


def normalize_score_dimensions(value, fallback):
    if not isinstance(value, dict):
        return fallback
    result = {}
    for label in ["岗位匹配", "专业能力", "表达结构", "真实性", "风险控制"]:
        try:
            result[label] = max(0, min(100, int(value.get(label, fallback[label]))))
        except (TypeError, ValueError):
            result[label] = fallback[label]
    return result


def fallback_interview_questions(candidate, job, top_tags):
    return [
        {"type": "开场核验", "question": f"请用 2 分钟介绍你和「{job.title}」最相关的一段经历。", "rubric": "看表达结构、岗位相关性和真实性。"},
        {"type": "技能深挖", "question": f"你简历里较突出的技能是 {top_tags}。请选择一个讲清楚实际项目、你的职责和结果。", "rubric": "看技能熟练度是否有项目证据。"},
        {"type": "岗位匹配", "question": f"结合岗位 JD，你认为自己最能胜任 {job.title} 的哪三点？", "rubric": "看候选人对岗位要求的理解。"},
        {"type": "风险追问", "question": "如果入职后遇到陌生业务或技术栈，你会如何快速补齐并交付？", "rubric": "看学习能力、协作方式和落地思路。"},
        {"type": "反问", "question": "你对岗位职责、团队协作或发展空间有什么想了解的？", "rubric": "看动机和关注点。"},
    ]


def normalize_interview_questions(items):
    questions = []
    for item in items or []:
        if isinstance(item, dict):
            question = str(item.get("question") or "").strip()
            if question:
                questions.append({"type": str(item.get("type") or "AI提问"), "question": question, "rubric": str(item.get("rubric") or "结合回答质量评分。")})
        elif str(item).strip():
            questions.append({"type": "AI提问", "question": str(item).strip(), "rubric": "结合回答质量评分。"})
    return questions[:8]


def ensure_default_organization(user):
    root = OrganizationUnit.query.order_by(OrganizationUnit.id.asc()).first()
    if root:
        return root
    root = OrganizationUnit(name="总公司", unit_type="company", city="", headcount_plan=None, sort_order=0)
    db.session.add(root)
    db.session.flush()
    for name, unit_type, sort_order in [
        ("技术中心", "business_unit", 1),
        ("产品中心", "business_unit", 2),
        ("人力资源部", "department", 3),
        ("财务部", "department", 4),
    ]:
        db.session.add(OrganizationUnit(parent_id=root.id, name=name, unit_type=unit_type, sort_order=sort_order))
    audit_log(user, "create", "organization_unit", root.id, root.name, {"seed": True})
    db.session.commit()
    return root


def ensure_organization_root(user):
    root = OrganizationUnit.query.order_by(OrganizationUnit.id.asc()).first()
    if root:
        return root
    root = OrganizationUnit(name="总公司", unit_type="company", city="", headcount_plan=None, sort_order=0)
    db.session.add(root)
    db.session.flush()
    audit_log(user, "create", "organization_unit", root.id, root.name, {"seed": False})
    return root


def build_organization_tree(units):
    nodes = {unit.id: {**unit.to_dict(include_counts=True), "children": []} for unit in units}
    roots = []
    for unit in units:
        node = nodes[unit.id]
        if unit.parent_id and unit.parent_id in nodes:
            nodes[unit.parent_id]["children"].append(node)
        else:
            roots.append(node)
    apply_organization_aggregate_counts(roots)
    return roots


def apply_organization_aggregate_counts(nodes):
    for node in nodes:
        direct_count = int(node.get("employee_count") or 0)
        node["direct_employee_count"] = direct_count
        child_count = apply_organization_aggregate_counts(node.get("children") or [])
        node["employee_count"] = direct_count + child_count
        if node.get("headcount_plan"):
            node["vacancy_count"] = max(int(node.get("headcount_plan") or 0) - node["employee_count"], 0)
    return sum(int(node.get("employee_count") or 0) for node in nodes)


def organization_descendant_ids(unit_id):
    units = OrganizationUnit.query.all()
    children_by_parent = {}
    for unit in units:
        children_by_parent.setdefault(unit.parent_id, []).append(unit.id)
    result = []
    stack = [unit_id]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(children_by_parent.get(current, []))
    return result


def employee_group_overview(employees):
    total = len(employees)
    active = len([employee for employee in employees if employee.employment_status == "active"])
    with_compensation = len([employee for employee in employees if employee.latest_compensation()])
    latest_analyses = [employee.analyses[0] for employee in employees if employee.analyses]
    high_fit = len([analysis for analysis in latest_analyses if analysis.match_score >= 80])
    salary_risk = len([analysis for analysis in latest_analyses if analysis.salary_status in {"low", "high"}])
    avg_match = round(sum(analysis.match_score for analysis in latest_analyses) / len(latest_analyses), 1) if latest_analyses else 0
    today = date.today()
    seniority_values = [years_between(employee.hire_date, today) for employee in employees if employee.hire_date]
    avg_seniority = round(sum(seniority_values) / len(seniority_values), 1) if seniority_values else 0
    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "with_compensation": with_compensation,
        "analyzed": len(latest_analyses),
        "high_fit": high_fit,
        "salary_risk": salary_risk,
        "avg_match_score": avg_match,
        "avg_seniority_years": avg_seniority,
    }


def apply_employee_search(query):
    keyword = str(request.args.get("q") or "").strip().lower()
    if not keyword:
        return query
    like = f"%{keyword}%"
    return query.filter(
        or_(
            func.lower(EmployeeProfile.name).like(like),
            func.lower(EmployeeProfile.current_title).like(like),
            func.lower(EmployeeProfile.employee_no).like(like),
            func.lower(EmployeeProfile.department).like(like),
        )
    )


def reset_internal_talent_data():
    EmployeeRecommendation.query.delete()
    EmployeeAnalysis.query.delete()
    EmployeeCompensation.query.delete()
    EmployeeProfile.query.delete()
    OrganizationUnit.query.delete()
    Job.query.filter(Job.job_code.like("INTERNAL-%")).delete(synchronize_session=False)
    db.session.flush()


def build_employee_compensation(employee_id, payload):
    keys = {"salary_monthly_k", "salary_annual_k", "salary_months", "bonus_k"}
    if not any(key in payload and payload.get(key) not in (None, "") for key in keys):
        return None
    monthly = parse_optional_float(payload.get("salary_monthly_k"))
    annual = parse_optional_float(payload.get("salary_annual_k"))
    months = parse_optional_int(payload.get("salary_months"), 12)
    bonus = parse_optional_float(payload.get("bonus_k"))
    if annual is None and monthly is not None:
        annual = monthly * months + (bonus or 0)
    if monthly is None and annual is not None and months:
        monthly = annual / months
    return EmployeeCompensation(
        employee_id=employee_id,
        salary_monthly_k=monthly,
        salary_annual_k=annual,
        salary_months=months,
        bonus_k=bonus,
        currency=payload.get("currency") or "CNY",
        source=payload.get("salary_source") or "manual",
        effective_date=parse_date(payload.get("salary_effective_date")) or date.today(),
    )


def parse_csv_table(stream):
    raw = stream.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="ignore")
    else:
        text = raw
    reader = csv.DictReader(StringIO(text))
    rows = [{str(key or "").strip(): str(value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("导入文件没有可读取的数据")
    return rows


def parse_xlsx_table(stream):
    rows = read_xlsx_rows(stream)
    if not rows:
        raise ValueError("Excel 中没有可读取的数据")
    header_index = next((index for index, row in enumerate(rows) if any(cell for cell in row)), None)
    if header_index is None:
        raise ValueError("Excel 中没有表头")
    headers = [str(value or "").strip() for value in rows[header_index]]
    parsed = []
    for row in rows[header_index + 1 :]:
        item = {}
        for index, header in enumerate(headers):
            if header:
                item[header] = str(row[index] if index < len(row) else "").strip()
        if any(item.values()):
            parsed.append(item)
    if not parsed:
        raise ValueError("Excel 中没有可导入的数据")
    return parsed


def parse_xls_table(stream):
    try:
        import xlrd
    except ImportError as exc:
        raise ValueError("当前环境缺少 xlrd，无法读取 .xls 文件，请安装依赖后重试") from exc
    try:
        workbook = xlrd.open_workbook(file_contents=stream.read())
    except Exception as exc:
        raise ValueError("Excel .xls 文件格式无效") from exc
    sheet = next((item for item in workbook.sheets() if item.nrows > 1 and item.ncols > 0), None)
    if not sheet:
        raise ValueError("Excel 中没有可读取的数据")
    headers = [str(sheet.cell_value(0, col) or "").strip() for col in range(sheet.ncols)]
    parsed = []
    for row_index in range(1, sheet.nrows):
        item = {}
        for col_index, header in enumerate(headers):
            if header:
                item[header] = xls_cell_text(workbook, sheet.cell(row_index, col_index))
        if any(item.values()):
            parsed.append(item)
    if not parsed:
        raise ValueError("Excel 中没有可导入的数据")
    return parsed


def xls_cell_text(workbook, cell):
    try:
        import xlrd
    except ImportError:
        xlrd = None
    value = cell.value
    if value in (None, ""):
        return ""
    if xlrd and cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate.xldate_as_datetime(value, workbook.datemode).date().isoformat()
        except (ValueError, OverflowError):
            return str(value).strip()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_xlsx_rows(stream):
    try:
        with zipfile.ZipFile(stream) as archive:
            shared_strings = read_xlsx_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
            first_sheet = workbook.find("m:sheets/m:sheet", ns)
            if first_sheet is None:
                raise ValueError("Excel 中没有工作表")
            rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_target = None
            for rel in rels:
                if rel.attrib.get("Id") == rel_id:
                    rel_target = rel.attrib.get("Target")
                    break
            sheet_path = "xl/" + (rel_target or "worksheets/sheet1.xml").lstrip("/")
            sheet = ElementTree.fromstring(archive.read(sheet_path))
            rows = []
            for row in sheet.findall(".//m:sheetData/m:row", ns):
                values = {}
                for cell in row.findall("m:c", ns):
                    ref = cell.attrib.get("r", "")
                    col = re.sub(r"\d+", "", ref)
                    values[col] = read_xlsx_cell(cell, shared_strings, ns)
                rows.append([values.get(col, "") for col in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]])
            return rows
    except KeyError as exc:
        raise ValueError("Excel 文件结构不完整") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("Excel 文件格式无效") from exc


def row_value(row, aliases):
    normalized = {re.sub(r"[\s_：:（）()/-]+", "", str(key or "")).lower(): value for key, value in row.items()}
    for alias in aliases:
        key = re.sub(r"[\s_：:（）()/-]+", "", alias).lower()
        value = normalized.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def upsert_employee_from_import_row(row, user):
    employee_no = row_value(row, ["员工编号", "工号", "employee_no", "employee no", "emp_no"])
    phone = only_digits(row_value(row, ["手机号", "手机", "电话", "phone", "mobile"]))
    email_value = row_value(row, ["邮箱", "email", "mail"]).lower()
    name = row_value(row, ["姓名", "员工姓名", "name"])
    unit = resolve_organization_unit_from_import_row(row, user)
    current_title = row_value(row, ["当前岗位", "岗位", "职位", "current_title", "title", "job_title"])
    job = resolve_job_from_import_row(row, user, unit)
    if not employee_no and name:
        employee_no = stable_employee_no(row, name, unit, current_title)
    employee = find_employee_for_import_row(employee_no, phone, email_value)
    was_created = False
    if not employee:
        if not name:
            return None, False
        employee = EmployeeProfile(
            owner_hr_id=user.id,
            employee_no=employee_no or None,
            name=name,
            phone=phone or "",
            email=email_value or "",
            organization_unit_id=unit.id if unit else None,
            department=unit.name if unit else row_value(row, ["部门", "组织", "organization", "department"]),
            current_job_id=job.id if job else None,
            current_title=current_title or (job.title if job else "未设置岗位"),
            raw_text=employee_raw_text_from_row(row),
            resume_json={"summary": row_value(row, ["个人简介", "简介", "summary", "profile"])},
            parse_status="ok",
        )
        db.session.add(employee)
        db.session.flush()
        was_created = True
    if employee_no:
        employee.employee_no = employee_no
    if name:
        employee.name = name
    if phone:
        employee.phone = phone
    if email_value:
        employee.email = email_value
    if unit:
        employee.organization_unit_id = unit.id
        employee.department = unit.name
    if job:
        employee.current_job_id = job.id
        employee.current_title = job.title
    elif current_title:
        employee.current_title = current_title
    for field, aliases in {
        "level": ["职级", "级别", "level"],
        "city": ["城市", "city"],
        "employment_status": ["在职状态", "状态", "status", "employment_status"],
        "manager_name": ["直属上级", "上级", "manager", "manager_name"],
        "education": ["学历", "最高学历", "education"],
        "graduation_school": ["毕业院校", "学校", "院校", "school", "graduation_school"],
    }.items():
        value = row_value(row, aliases)
        if value:
            setattr(employee, field, normalize_employee_status(value) if field == "employment_status" else value)
    hire_date = row_value(row, ["入职日期", "入职时间", "hire_date", "hire date"])
    if hire_date:
        employee.hire_date = parse_date(hire_date)
    birth_date = row_value(row, ["出生日期", "出生年月", "生日", "birth_date", "birthday"])
    if birth_date:
        employee.birth_date = parse_date(birth_date)
    graduation_date = row_value(row, ["毕业时间", "毕业日期", "毕业年月", "graduation_date", "graduation date"])
    if graduation_date:
        employee.graduation_date = parse_date(graduation_date)
    summary = row_value(row, ["个人简介", "简介", "summary", "profile"])
    if summary:
        resume_json = dict(employee.resume_json or {})
        resume_json["summary"] = summary
        employee.resume_json = resume_json
    employee.resume_json = employee_resume_json_from_profile(employee, row)
    return employee, was_created


def find_employee_for_import_row(employee_no, phone, email_value):
    if employee_no:
        employee = EmployeeProfile.query.filter_by(employee_no=employee_no).first()
        if employee:
            return employee
    if phone:
        employee = EmployeeProfile.query.filter_by(phone=phone).first()
        if employee:
            return employee
    if email_value:
        employee = EmployeeProfile.query.filter(func.lower(EmployeeProfile.email) == email_value).first()
        if employee:
            return employee
    return None


def stable_employee_no(row, name, unit, current_title):
    identity = "|".join(
        [
            name or "",
            unit.name if unit else "",
            current_title or "",
            row_value(row, ["入职日期", "入职时间", "hire_date", "hire date"]),
            row_value(row, ["出生日期", "出生年月", "birth_date"]),
        ]
    )
    digest = hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:10].upper()
    return f"EMP-{digest}"


def employee_resume_json_from_profile(employee, row):
    resume_json = dict(employee.resume_json or {})
    education_item = {
        "school": employee.graduation_school or "",
        "degree": employee.education or "",
        "end": employee.graduation_date.isoformat() if employee.graduation_date else "",
    }
    if any(education_item.values()):
        resume_json["education"] = [education_item]
    resume_json["profile"] = {
        "birth_date": employee.birth_date.isoformat() if employee.birth_date else None,
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "education": employee.education,
        "graduation_school": employee.graduation_school,
        "graduation_date": employee.graduation_date.isoformat() if employee.graduation_date else None,
    }
    if not resume_json.get("summary"):
        resume_json["summary"] = "；".join(
            item
            for item in [
                f"当前职位：{employee.current_title}" if employee.current_title else "",
                f"学历：{employee.education}" if employee.education else "",
                f"毕业院校：{employee.graduation_school}" if employee.graduation_school else "",
            ]
            if item
        )
    return resume_json


def resolve_organization_unit_from_import_row(row, user):
    unit_id = parse_optional_int(row_value(row, ["organization_unit_id", "组织ID", "部门ID"]), None)
    if unit_id:
        unit = db.session.get(OrganizationUnit, unit_id)
        if unit:
            return unit
    levels = [
        row_value(row, ["1级部门", "一级部门", "一级组织", "level1_department"]),
        row_value(row, ["2级部门", "二级部门", "二级组织", "level2_department"]),
        row_value(row, ["3级部门", "三级部门", "三级组织", "level3_department"]),
    ]
    levels = [level for level in levels if level]
    if levels:
        parent = ensure_organization_root(user)
        unit = parent
        for index, name in enumerate(levels):
            unit_type = "business_unit" if index == 0 else ("department" if index == 1 else "team")
            unit = get_or_create_org_unit(name, parent.id, unit_type, index)["unit"]
            parent = unit
        return unit
    unit_name = row_value(row, ["组织", "组织名称", "部门", "部门名称", "organization", "department"])
    if unit_name:
        exact = OrganizationUnit.query.filter_by(name=unit_name).order_by(OrganizationUnit.id.asc()).first()
        if exact:
            return exact
        root = ensure_default_organization(user)
        return get_or_create_org_unit(unit_name, root.id, "department")["unit"]
    return ensure_default_organization(user)


def resolve_job_from_import_row(row, user=None, unit=None):
    job_id = parse_optional_int(row_value(row, ["current_job_id", "job_id", "岗位ID"]), None)
    if job_id:
        job = db.session.get(Job, job_id)
        if job:
            return job
    title = row_value(row, ["岗位", "职位", "当前岗位", "job_title", "title", "current_title"])
    if not title:
        return None
    department = unit.name if unit else row_value(row, ["部门", "组织", "department", "organization"])
    query = Job.query.filter(func.lower(Job.title) == title.lower())
    if department:
        scoped = query.filter(func.lower(Job.department) == department.lower()).order_by(Job.id.asc()).first()
        if scoped:
            return scoped
    existing = query.order_by(Job.id.asc()).first()
    if existing and not department:
        return existing
    if not user:
        return existing
    return create_internal_job_from_employee_row(title, department, user)


def create_internal_job_from_employee_row(title, department, user):
    code_seed = f"{title}|{department or ''}"
    job_code = f"INTERNAL-{hashlib.sha1(code_seed.encode('utf-8', errors='ignore')).hexdigest()[:12].upper()}"
    existing = Job.query.filter_by(job_code=job_code).first()
    if existing:
        return existing
    jd_text = f"内部在职岗位：{title}。所属组织：{department or '未维护'}。岗位职责与技能要求待通过 JD 校准补充。"
    job = Job(
        owner_hr_id=user.id,
        title=title,
        department=department or "",
        city="",
        job_code=job_code,
        jd_text=jd_text,
        jd_structured={
            "title": title,
            "department": department or "",
            "source": "internal_employee_import",
            "skill_tags_raw": "",
            "responsibilities": [f"承担{title}相关工作"],
            "requirements": ["待补充岗位 JD 和技能要求"],
        },
        status="active",
    )
    db.session.add(job)
    db.session.flush()
    return job


def normalize_employee_status(value):
    text = str(value or "").strip().lower()
    mapping = {
        "在职": "active",
        "active": "active",
        "离职": "departed",
        "departed": "departed",
        "待离职": "leaving",
        "leaving": "leaving",
        "调岗中": "transfer",
        "transfer": "transfer",
    }
    return mapping.get(text, text or "active")


def employee_raw_text_from_row(row):
    parts = []
    for key, value in row.items():
        if value not in (None, ""):
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def find_employee_for_compensation_row(row):
    employee_no = row_value(row, ["员工编号", "工号", "employee_no", "employee no"])
    if employee_no:
        employee = EmployeeProfile.query.filter_by(employee_no=employee_no).first()
        if employee:
            return employee
    phone = only_digits(row_value(row, ["手机号", "手机", "电话", "phone", "mobile"]))
    if phone:
        employee = EmployeeProfile.query.filter_by(phone=phone).first()
        if employee:
            return employee
    email_value = row_value(row, ["邮箱", "email", "mail"]).lower()
    if email_value:
        employee = EmployeeProfile.query.filter(func.lower(EmployeeProfile.email) == email_value).first()
        if employee:
            return employee
    name = row_value(row, ["姓名", "员工姓名", "name"])
    if name:
        employees = EmployeeProfile.query.filter_by(name=name).all()
        if len(employees) == 1:
            return employees[0]
        if len(employees) > 1:
            raise ValueError(f"姓名「{name}」匹配到多个员工，请补充员工编号/手机号/邮箱")
    return None


def compensation_payload_from_row(row):
    return {
        "salary_monthly_k": row_value(row, ["月薪K", "月薪", "monthly_k", "salary_monthly_k", "salary monthly k"]),
        "salary_annual_k": row_value(row, ["年包K", "年薪K", "年薪", "annual_k", "salary_annual_k", "salary annual k"]),
        "salary_months": row_value(row, ["薪资月数", "几薪", "months", "salary_months"]),
        "bonus_k": row_value(row, ["奖金K", "奖金", "bonus_k", "bonus"]),
        "currency": row_value(row, ["币种", "currency"]) or "CNY",
        "salary_source": "import",
        "salary_effective_date": row_value(row, ["生效日期", "effective_date", "effective date", "日期"]),
    }


def only_digits(value):
    return re.sub(r"\D+", "", str(value or ""))


def employee_from_candidate_record(candidate, user, unit, job=None, payload=None):
    payload = payload or {}
    existing = EmployeeProfile.query.filter_by(candidate_id=candidate.id).first()
    if existing:
        if unit and existing.organization_unit_id != unit.id:
            existing.organization_unit_id = unit.id
            existing.department = unit.name
        if job and existing.current_job_id != job.id:
            existing.current_job_id = job.id
            existing.current_title = job.title
        return existing, False
    employee = EmployeeProfile(
        candidate_id=candidate.id,
        organization_unit_id=unit.id if unit else None,
        current_job_id=job.id if job else None,
        owner_hr_id=user.id,
        employee_no=str(payload.get("employee_no") or f"EMP-{candidate.id:05d}").strip(),
        name=candidate.name_masked,
        phone=candidate.phone_masked,
        email=candidate.email_masked,
        department=unit.name if unit else candidate.city,
        current_title=job.title if job else candidate.title,
        level=str(payload.get("level") or "").strip(),
        city=payload.get("city") or candidate.city,
        employment_status=payload.get("employment_status") or "active",
        hire_date=parse_date(payload.get("hire_date")),
        birth_date=parse_date(payload.get("birth_date")),
        education=str(payload.get("education") or "").strip(),
        graduation_school=str(payload.get("graduation_school") or "").strip(),
        graduation_date=parse_date(payload.get("graduation_date")),
        manager_name=str(payload.get("manager_name") or "").strip(),
        raw_text=candidate.raw_text,
        resume_json=candidate.resume_json or {},
        parse_status=candidate.parse_status,
    )
    db.session.add(employee)
    db.session.flush()
    return employee, True


def parse_organization_xlsx(stream):
    rows = read_xlsx_rows(stream)
    header_index = next((index for index, row in enumerate(rows) if {"一级部门", "二级部门", "三级部门"} & set(row)), None)
    if header_index is None:
        raise ValueError("未找到一级部门/二级部门/三级部门表头")
    headers = rows[header_index]
    parsed = []
    for row in rows[header_index + 1 :]:
        item = {headers[index]: row[index].strip() for index in range(min(len(headers), len(row))) if headers[index]}
        if item.get("一级部门") or item.get("二级部门") or item.get("三级部门"):
            parsed.append(item)
    if not parsed:
        raise ValueError("组织架构 Excel 没有可导入的数据")
    return parsed


def read_xlsx_shared_strings(archive):
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall("m:si", ns):
        parts = [node.text or "" for node in item.findall(".//m:t", ns)]
        strings.append("".join(parts))
    return strings


def read_xlsx_cell(cell, shared_strings, ns):
    value = cell.find("m:v", ns)
    inline = cell.find("m:is/m:t", ns)
    if inline is not None:
        return (inline.text or "").strip()
    if value is None:
        return ""
    text = value.text or ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(text)].strip()
        except (ValueError, IndexError):
            return ""
    return str(text).strip()


def get_or_create_org_unit(name, parent_id, unit_type, sort_order=0):
    name = str(name or "").strip()
    unit = OrganizationUnit.query.filter_by(parent_id=parent_id, name=name).first()
    if unit:
        if unit.unit_type != unit_type:
            unit.unit_type = unit_type
        return {"unit": unit, "created": False}
    unit = OrganizationUnit(parent_id=parent_id, name=name, unit_type=unit_type, sort_order=sort_order)
    db.session.add(unit)
    db.session.flush()
    return {"unit": unit, "created": True}


def match_employee_to_job(employee, job):
    if not job:
        return {"score": 0, "hits": [], "missing_tags": [], "match_rate": 0, "capability_rate": 0, "summary": "员工未绑定岗位。"}
    structured = ensure_jd_structured(job)
    reason = match_candidate(
        structured.get("skill_tags_raw"),
        [tag.to_dict() for tag in employee.tags()],
        years_required=structured.get("years_required"),
        candidate_years=(employee.resume_json or {}).get("experience_analysis", {}).get("years"),
        candidate_context=" ".join([employee.current_title or "", employee.raw_text or ""]),
    )
    if reason["score"] >= 85:
        summary = "员工能力与岗位要求高度匹配，可作为核心人才关注。"
    elif reason["score"] >= 70:
        summary = "员工能力与岗位基本匹配，建议结合绩效继续观察。"
    elif reason["score"] >= 50:
        summary = "员工能力与岗位部分匹配，建议补齐缺失能力或评估调岗。"
    else:
        summary = "员工能力与岗位匹配度偏低，建议优先评估调岗或培训。"
    reason["summary"] = summary
    return reason


def analyze_employee_salary(employee, match_score):
    compensation = employee.latest_compensation()
    job = employee.current_job
    salary_range = (ensure_jd_structured(job).get("salary_range") if job else None) or None
    if not compensation or not compensation.salary_monthly_k:
        return {"score": 0, "status": "unknown", "label": "薪资数据不足", "summary": "员工未维护薪资，暂不能判断薪资合理性。"}
    if not salary_range:
        return {"score": 0, "status": "unknown", "label": "岗位薪资区间不足", "summary": "当前岗位未识别薪资范围，暂不能判断薪资是否合理。"}
    monthly = float(compensation.salary_monthly_k or 0)
    low = float(salary_range.get("min_k") or 0)
    high = float(salary_range.get("max_k") or 0)
    if low and monthly < low:
        status = "low"
        label = "薪资偏低"
        score = 70 if match_score >= 80 else 82
        summary = "员工薪资低于岗位区间下限。若岗位匹配分较高，存在保留风险。"
    elif high and monthly > high:
        status = "high"
        label = "薪资偏高"
        score = 70 if match_score < 60 else 85
        summary = "员工薪资高于岗位区间上限。若岗位匹配分偏低，建议复核岗位产出。"
    else:
        status = "reasonable"
        label = "薪资合理"
        score = 95 if match_score >= 70 else 82
        summary = "员工薪资处于岗位薪资区间内。"
    return {"score": score, "status": status, "label": label, "summary": summary, "monthly_k": monthly, "range": salary_range}


def analyze_employee_against_job(employee, job):
    fit = match_employee_to_job(employee, job)
    salary = analyze_employee_salary(employee, fit["score"])
    if fit["score"] >= 80 and salary["status"] == "low":
        risk = "retention"
    elif fit["score"] < 50:
        risk = "job_mismatch"
    elif fit["score"] < 60 and salary["status"] == "high":
        risk = "cost_mismatch"
    else:
        risk = "normal"
    payload = {
        "summary": f"{fit['summary']} {salary['summary']}",
        "job_fit": fit,
        "salary": salary,
        "actions": employee_analysis_actions(fit["score"], salary["status"], risk),
    }
    return EmployeeAnalysis(
        employee_id=employee.id,
        job_id=job.id if job else None,
        match_score=fit["score"],
        salary_score=salary["score"],
        salary_status=salary["status"],
        risk_level=risk,
        analysis_json=payload,
        source="rules",
    )


def employee_analysis_actions(match_score, salary_status, risk):
    actions = []
    if match_score >= 85:
        actions.append("列入高匹配人才池，可作为关键岗位继任或保留对象。")
    elif match_score < 50:
        actions.append("建议评估当前岗位适配，优先查看调岗推荐。")
    else:
        actions.append("建议结合绩效和项目产出继续观察，并补齐缺失能力。")
    if salary_status == "low":
        actions.append("建议结合绩效复核薪资，避免高匹配员工流失。")
    elif salary_status == "high":
        actions.append("建议复核薪资与岗位产出是否匹配。")
    if risk == "retention":
        actions.append("建议主管或 HRBP 主动沟通保留意愿。")
    return actions


def employee_report_text(employee, include_salary=True):
    actual_compensation = employee.latest_compensation()
    compensation = actual_compensation if include_salary else None
    analysis = employee.analyses[0] if employee.analyses else None
    resume = employee.resume_json or {}
    tags = "、".join(f"{tag.tag}({tag.score})" for tag in employee.tags()) or "暂无"
    salary = "薪资未维护"
    if not include_salary and actual_compensation:
        salary = "薪资已隐藏（仅管理员和经理可见）"
    if compensation:
        if compensation.salary_monthly_k:
            salary = f"{compensation.salary_monthly_k:.1f}K · {compensation.salary_months}薪"
        elif compensation.salary_annual_k:
            salary = f"年包 {compensation.salary_annual_k:.1f}K"
    lines = [
        "内部员工分析报告",
        "=" * 18,
        f"员工：{employee.name}",
        f"员工编号：{employee.employee_no or '-'}",
        f"组织：{employee.organization_unit.name if employee.organization_unit else employee.department or '-'}",
        f"当前岗位：{employee.current_job.title if employee.current_job else employee.current_title or '-'}",
        f"职级：{employee.level or '-'}",
        f"城市：{employee.city or '-'}",
        f"状态：{employment_status_label(employee.employment_status)}",
        f"薪资：{salary}",
        f"技能标签：{tags}",
        "",
        "个人简介",
        str(resume.get("summary") or employee.raw_text or "暂无简介")[:1200],
        "",
        "当前岗位与薪资分析",
    ]
    if analysis:
        actions = analysis.analysis_json.get("actions", []) if analysis.analysis_json else []
        lines.extend(
            [
                f"岗位匹配分：{analysis.match_score}/100",
                f"薪资评分：{analysis.salary_score}/100",
                f"薪资状态：{salary_status_label(analysis.salary_status)}",
                f"风险等级：{risk_label(analysis.risk_level)}",
                f"分析结论：{(analysis.analysis_json or {}).get('summary', '暂无分析摘要')}",
                "",
                "建议动作",
                *(actions or ["暂无建议动作"]),
            ]
        )
    else:
        lines.append("暂未分析，请先在系统中执行当前岗位/薪资分析。")
    return "\n".join(str(line) for line in lines)


def employment_status_label(status):
    return {"active": "在职", "departed": "离职", "leaving": "待离职", "transfer": "调岗中"}.get(status, status or "")


def salary_status_label(status):
    return {"low": "薪资偏低", "high": "薪资偏高", "reasonable": "薪资合理", "unknown": "数据不足"}.get(status, status or "")


def risk_label(risk):
    return {"normal": "正常", "retention": "保留风险", "job_mismatch": "岗位不匹配", "cost_mismatch": "成本不匹配", "unknown": "未分析"}.get(risk, risk or "")


def parse_datetime(value):
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return (date(1899, 12, 30) + timedelta(days=int(value)))
        except OverflowError:
            return None
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return parse_date(float(text))
    text = text.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{4}-\d{1,2}", text):
        text = f"{text}-01"
    if re.fullmatch(r"\d{4}", text):
        text = f"{text}-01-01"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_int(value, default):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_offer_terms(salary_min_k, salary_max_k, salary_months):
    if salary_min_k is not None and salary_min_k < 0:
        return error("最低月薪不能为负数")
    if salary_max_k is not None and salary_max_k < 0:
        return error("最高月薪不能为负数")
    if salary_min_k is not None and salary_max_k is not None and salary_min_k > salary_max_k:
        return error("最低月薪不能高于最高月薪")
    if salary_months <= 0:
        return error("薪资月数必须大于 0")
    return None


def push_offer_pipeline(offer, user_id, note):
    next_stage = "offer"
    if offer.status == "accepted":
        next_stage = "onboarded"
    elif offer.status in {"declined", "cancelled"}:
        next_stage = "rejected"
    db.session.add(
        PipelineStage(
            candidate_id=offer.candidate_id,
            job_id=offer.job_id,
            stage=next_stage,
            updated_by=user_id,
            note=note,
        )
    )


def offer_status_label(status):
    return {
        "draft": "草稿",
        "sent": "已发放",
        "accepted": "已接受",
        "declined": "已拒绝",
        "cancelled": "已取消",
    }.get(status, status)


def audit_log(user, action, target_type, target_id=None, target_name="", details=None):
    db.session.add(
        AuditLog(
            user_id=user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            details=details or {},
        )
    )


def stageLabels_backend(stage):
    return {
        "pending": "待处理",
        "ai_screen": "AI 初筛",
        "business_review": "业务复核",
        "interview_first": "一面",
        "interview_second": "二面",
        "interview_final": "终面",
        "offer": "Offer",
        "onboarded": "入职",
        "rejected": "淘汰",
    }.get(stage, stage)


def boss_draft_status_label(status):
    return {
        "draft": "待审核",
        "reviewed": "已审核",
        "approved": "已通过",
        "sent": "已发送",
        "archived": "已取消",
    }.get(status, status)


def login_failure_key(username):
    ip = request.remote_addr or "unknown"
    return f"{username.lower() or '-'}|{ip}"


def login_retry_after(key):
    entry = LOGIN_FAILURES.get(key)
    if not entry:
        return 0
    locked_until = float(entry.get("locked_until") or 0)
    remaining = int(max(0, locked_until - time()))
    if remaining <= 0 and locked_until:
        LOGIN_FAILURES.pop(key, None)
    return remaining


def record_login_failure(key):
    max_failures = max(1, int(current_app.config.get("LOGIN_MAX_FAILURES", 5)))
    lock_seconds = max(1, int(current_app.config.get("LOGIN_LOCKOUT_MINUTES", 15)) * 60)
    entry = LOGIN_FAILURES.setdefault(key, {"count": 0, "locked_until": 0})
    entry["count"] = int(entry.get("count") or 0) + 1
    if entry["count"] >= max_failures:
        entry["locked_until"] = time() + lock_seconds
        return lock_seconds
    return 0


def public_interview_rate_limit(token):
    limit = max(1, int(current_app.config.get("PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE", 60)))
    now = time()
    token_fingerprint = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]
    key = f"{token_fingerprint}|{request.remote_addr or 'unknown'}"
    bucket = PUBLIC_INTERVIEW_REQUESTS.setdefault(key, [])
    PUBLIC_INTERVIEW_REQUESTS[key] = [item for item in bucket if now - item < 60]
    bucket = PUBLIC_INTERVIEW_REQUESTS[key]
    if len(bucket) >= limit:
        return error("面试间请求过于频繁，请稍后再试", "PUBLIC_INTERVIEW_RATE_LIMITED", 429)
    bucket.append(now)
    return None


def validate_public_interview_payload(payload, complete=False):
    payload = payload or {}
    max_answer_chars = max(200, int(current_app.config.get("PUBLIC_INTERVIEW_MAX_ANSWER_CHARS", 4000)))
    max_messages = max(1, int(current_app.config.get("PUBLIC_INTERVIEW_MAX_MESSAGES", 80)))
    max_cheat_events = max(0, int(current_app.config.get("PUBLIC_INTERVIEW_MAX_CHEAT_EVENTS", 100)))
    text_values = [
        str(payload.get("question") or ""),
        str(payload.get("answer") or ""),
        str(payload.get("candidate_question") or ""),
    ]
    if any(len(value) > max_answer_chars for value in text_values):
        return error("面试回答内容过长，请精简后重试", "PUBLIC_INTERVIEW_PAYLOAD_TOO_LARGE", 413)
    if complete:
        answers = payload.get("answers") or []
        messages = payload.get("messages") or []
        cheat_events = payload.get("cheat_events") or []
        if len(answers) > max_messages or len(messages) > max_messages or len(cheat_events) > max_cheat_events:
            return error("面试提交内容超过限制", "PUBLIC_INTERVIEW_PAYLOAD_TOO_LARGE", 413)
        combined = " ".join(str(item) for item in answers[-max_messages:]) + " ".join(str(item) for item in messages[-max_messages:]) + " ".join(str(item) for item in cheat_events[-max_cheat_events:])
        if len(combined) > max_answer_chars * max(1, max_messages // 2):
            return error("面试提交内容超过限制", "PUBLIC_INTERVIEW_PAYLOAD_TOO_LARGE", 413)
    return None


def summarize_text(text, limit=120):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:limit] + ("..." if len(value) > limit else "")


def build_candidate_resume_text(candidate):
    resume = candidate.resume_json or {}
    lines = [
        "候选人简历",
        "",
        f"姓名：{candidate.name_masked}",
        f"手机号：{candidate.phone_masked or ''}",
        f"邮箱：{candidate.email_masked or ''}",
        f"性别：{resume.get('gender', '')}",
        f"城市：{candidate.city or ''}",
        f"当前岗位/意向：{candidate.title or ''}",
        f"经验：{resume.get('experience_analysis', {}).get('label', '')}",
        "",
        "个人简介",
        str(resume.get("summary") or "").strip() or "暂无",
        "",
        "技能标签",
        "、".join(f"{tag.tag}({tag.score}/5)" for tag in sorted(candidate.tags, key=lambda item: (-item.score, item.tag))) or "暂无",
        "",
        "简历原文",
        candidate.raw_text or "暂无",
    ]
    return "\n".join(lines)


def build_interview_report_text(assignment, feedback):
    ai_score_match = re.search(r"AI评分：(\d+)/100", feedback.comment or "")
    ai_score = ai_score_match.group(1) if ai_score_match else str(feedback.rating * 20)
    decision = {"pass": "通过", "hold": "待定", "reject": "淘汰"}.get(feedback.decision, feedback.decision)
    lines = [
        "AI 面试报告",
        "",
        f"候选人：{assignment.candidate.name_masked}",
        f"岗位：{assignment.job.title}",
        f"轮次：{stageLabels_backend(assignment.round)}",
        f"面试时间：{assignment.scheduled_at.isoformat()}",
        f"面试官：{assignment.interviewer.name if assignment.interviewer else ''}",
        f"AI评分：{ai_score}/100",
        f"面试官评分：{feedback.rating}/5",
        f"结论：{decision}",
        "",
        "优势",
        feedback.strengths or "暂无",
        "",
        "风险",
        feedback.risks or "暂无",
        "",
        "面试内容",
        feedback.comment or "暂无记录",
    ]
    return "\n".join(lines)


def build_offer_letter_text(offer):
    if offer.salary_min_k and offer.salary_max_k:
        salary = f"{offer.salary_min_k:g}-{offer.salary_max_k:g}K × {offer.salary_months} 薪"
    elif offer.salary_min_k or offer.salary_max_k:
        salary = f"{(offer.salary_min_k or offer.salary_max_k):g}K × {offer.salary_months} 薪"
    else:
        salary = "面议"
    lines = [
        "Offer 确认函",
        "",
        f"候选人：{offer.candidate.name_masked}",
        f"岗位：{offer.job.title}",
        f"工作城市：{offer.city or offer.job.city or '待定'}",
        f"薪资：{salary}",
        f"预计入职日期：{offer.start_date.isoformat() if offer.start_date else '待定'}",
        f"当前状态：{offer_status_label(offer.status)}",
        "",
        "备注",
        offer.note or "暂无",
    ]
    return "\n".join(lines)


def csv_response(filename, headers, rows, user=None, audit_target="export"):
    if user:
        audit_log(user, "export", audit_target, None, filename, {"kind": "csv", "filename": filename, "row_count": len(rows)})
        db.session.commit()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    body = "\ufeff" + output.getvalue()
    return Response(body, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})
