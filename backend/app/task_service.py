from . import db
from .models import BackgroundTask, Candidate, CandidateTag, EmployeeProfile, User, utcnow
from .ops_service import create_backup_package
from .resume_service import reparse_candidate


TASK_STATUSES = {"queued", "running", "succeeded", "failed"}
RETRYABLE_STATUSES = {"failed"}


def enqueue_task(task_type, payload=None, created_by=None, max_attempts=3):
    task = BackgroundTask(
        task_type=task_type,
        payload=payload or {},
        created_by=created_by,
        max_attempts=max(1, int(max_attempts or 1)),
    )
    db.session.add(task)
    db.session.commit()
    return task


def retry_task(task):
    if task.status not in RETRYABLE_STATUSES:
        raise ValueError("只有失败任务可以重新排队")
    if task.attempts >= task.max_attempts:
        raise ValueError("任务已达到最大重试次数")
    task.status = "queued"
    task.error = None
    task.started_at = None
    task.finished_at = None
    db.session.commit()
    return task


def run_next_task():
    task = (
        BackgroundTask.query.filter_by(status="queued")
        .order_by(BackgroundTask.created_at.asc(), BackgroundTask.id.asc())
        .first()
    )
    if not task:
        return None
    return run_task(task)


def run_task(task):
    task.status = "running"
    task.attempts += 1
    task.started_at = utcnow()
    task.error = None
    db.session.commit()
    try:
        result = execute_task(task)
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = utcnow()
        db.session.commit()
        raise
    task.status = "succeeded"
    task.result = result or {}
    task.finished_at = utcnow()
    db.session.commit()
    return task


def execute_task(task):
    if task.task_type == "resume_retry_parse":
        return run_resume_retry_parse(task)
    if task.task_type == "backup_export":
        return create_backup_package()
    if task.task_type == "employee_analyze_current_job":
        return run_employee_analyze_current_job(task)
    if task.task_type == "employee_recommend_transfer":
        return run_employee_recommend_transfer(task)
    if task.task_type == "employee_recommend_replacement":
        return run_employee_recommend_replacement(task)
    if task.task_type == "job_match":
        return run_job_match(task)
    raise ValueError(f"未知后台任务类型：{task.task_type}")


def run_resume_retry_parse(task):
    candidate_id = int((task.payload or {}).get("candidate_id") or 0)
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        raise ValueError("候选人不存在")
    candidate = reparse_candidate(candidate)
    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name_masked,
        "parse_status": candidate.parse_status,
        "tag_count": CandidateTag.query.filter_by(candidate_id=candidate.id).count(),
    }


def task_employee(task):
    employee_id = int((task.payload or {}).get("employee_id") or 0)
    employee = db.session.get(EmployeeProfile, employee_id)
    if not employee:
        raise ValueError("员工不存在")
    return employee


def run_employee_analyze_current_job(task):
    from .routes import run_employee_current_job_analysis

    employee = task_employee(task)
    analysis = run_employee_current_job_analysis(employee)
    db.session.add(analysis)
    db.session.flush()
    return {
        "employee_id": employee.id,
        "employee_name": employee.name,
        "analysis": analysis.to_dict(),
    }


def run_employee_recommend_transfer(task):
    from .routes import run_employee_transfer_recommendation

    employee = task_employee(task)
    items = run_employee_transfer_recommendation(employee)
    return {
        "employee_id": employee.id,
        "employee_name": employee.name,
        "items": items,
        "count": len(items),
    }


def run_employee_recommend_replacement(task):
    from .routes import run_employee_replacement_recommendation

    employee = task_employee(task)
    items = run_employee_replacement_recommendation(employee)
    return {
        "employee_id": employee.id,
        "employee_name": employee.name,
        "items": items,
        "count": len(items),
    }


def run_job_match(task):
    from .routes import run_job_match_for_user

    job_id = int((task.payload or {}).get("job_id") or 0)
    user = db.session.get(User, task.created_by) if task.created_by else None
    job, items = run_job_match_for_user(job_id, user=user)
    return {
        "job_id": job.id,
        "job_title": job.title,
        "count": len(items),
        "top_score": items[0]["score"] if items else 0,
        "top_candidates": [
            {
                "candidate_id": item["candidate_id"],
                "candidate_name": item["candidate"]["name_masked"],
                "score": item["score"],
                "ai_source": (item.get("reason") or {}).get("ai_review", {}).get("source"),
            }
            for item in items[:5]
        ],
    }
