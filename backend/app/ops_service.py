import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import make_url

from . import db
from .models import Candidate, CandidateTag, EmployeeProfile, Job, ResumeAttachment, UploadBatch
from .resume_service import resume_upload_dir


PACKAGE_FORMAT = "hireinsight-full-migration-v1"
PACKAGE_PREFIX = "hireinsight-full-migration"


def repo_root():
    return Path(__file__).resolve().parents[2]


def backup_dir():
    path = Path(current_app.config.get("BACKUP_FOLDER") or "backups")
    if not path.is_absolute():
        path = repo_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def redact_database_url(database_url):
    try:
        return str(make_url(database_url).render_as_string(hide_password=True))
    except Exception:
        return "<invalid database url>"


def encode_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def app_tables():
    return [table for table in db.metadata.sorted_tables if table.name != "alembic_version"]


def export_database_payload():
    payload = {}
    counts = {}
    with db.engine.connect() as connection:
        source_tables = set(inspect(connection).get_table_names())
        for table in app_tables():
            if table.name not in source_tables:
                payload[table.name] = []
                counts[table.name] = 0
                continue
            rows = []
            for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings():
                rows.append({column.name: encode_value(row[column.name]) for column in table.columns})
            payload[table.name] = rows
            counts[table.name] = len(rows)
    return payload, counts


def add_uploads_to_package(archive, upload_dir):
    count = 0
    total_bytes = 0
    if not upload_dir.exists():
        return count, total_bytes
    for path in upload_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(upload_dir).as_posix()
        archive.write(path, f"uploads/{relative}")
        count += 1
        total_bytes += path.stat().st_size
    return count, total_bytes


def create_backup_package():
    output_dir = backup_dir()
    upload_dir = resume_upload_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = output_dir / f"{PACKAGE_PREFIX}-{timestamp}.zip"
    data, counts = export_database_payload()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": PACKAGE_FORMAT,
        "source_database": redact_database_url(current_app.config["SQLALCHEMY_DATABASE_URI"]),
        "source_upload_dir": str(upload_dir),
        "tables": counts,
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        upload_count, upload_bytes = add_uploads_to_package(archive, upload_dir)
        manifest["uploads"] = {"files": upload_count, "bytes": upload_bytes}
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    stat = output.stat()
    return {
        "package": str(output),
        "filename": output.name,
        "size_bytes": stat.st_size,
        "tables": counts,
        "uploads": manifest["uploads"],
        "created_at": manifest["created_at"],
    }


def list_backup_packages(limit=8):
    candidates = []
    for pattern in ("*.zip", "*.json", "*.sql", "*.tar"):
        candidates.extend(backup_dir().glob(pattern))
    packages = []
    for path in sorted({item.resolve() for item in candidates}, key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        stat = path.stat()
        item = {
            "filename": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "kind": path.suffix.lstrip(".").lower() or "file",
        }
        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    if "manifest.json" in archive.namelist():
                        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                        item["format"] = manifest.get("format")
                        item["created_at"] = manifest.get("created_at")
                        item["tables"] = manifest.get("tables", {})
                        item["uploads"] = manifest.get("uploads", {})
            except Exception as exc:
                item["warning"] = str(exc)
        packages.append(item)
    return packages


def migration_status():
    migrations_dir = repo_root() / "backend" / "migrations"
    try:
        config = AlembicConfig(str(migrations_dir / "alembic.ini"))
        config.set_main_option("script_location", str(migrations_dir))
        script = ScriptDirectory.from_config(config)
        heads = set(script.get_heads())
        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current = set(context.get_current_heads())
        return {"current": sorted(current), "heads": sorted(heads), "at_head": current == heads, "available": True}
    except Exception as exc:
        return {"current": [], "heads": [], "at_head": False, "available": False, "error": str(exc)}


def storage_status():
    upload_dir = resume_upload_dir()
    return {
        "upload_dir": str(upload_dir),
        "upload_dir_exists": upload_dir.exists(),
        "backup_dir": str(backup_dir()),
        "backup_dir_exists": backup_dir().exists(),
    }


def table_counts():
    counts = {}
    for table in app_tables():
        try:
            counts[table.name] = int(db.session.query(func.count()).select_from(table).scalar() or 0)
        except Exception:
            counts[table.name] = 0
    return counts


def build_data_quality_report():
    issues = [
        candidate_parse_failed_issue(),
        candidate_without_tags_issue(),
        attachment_scan_issue(),
        employee_without_org_issue(),
        employee_without_job_issue(),
        employee_without_resume_issue(),
        recruiting_job_without_skills_issue(),
        upload_without_file_issue(),
    ]
    issues = [issue for issue in issues if issue["count"] > 0]
    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    total_items = sum(issue["count"] for issue in issues)
    return {
        "ready": errors == 0,
        "summary": {"errors": errors, "warnings": warnings, "issues": len(issues), "items": total_items},
        "issues": sorted(issues, key=lambda item: (0 if item["severity"] == "error" else 1, -item["count"], item["key"])),
    }


def candidate_parse_failed_issue():
    query = Candidate.query.filter(Candidate.parse_status != "ok").order_by(Candidate.created_at.desc())
    return issue(
        "candidate_parse_failed",
        "warning",
        "简历解析失败",
        query.count(),
        "解析失败会影响姓名、手机号、技能标签和岗位匹配评分。",
        "人才库",
        "进入人才详情执行后台重解析，或重新上传原始简历。",
        [candidate_sample(item, include_error=True) for item in query.limit(5).all()],
    )


def candidate_without_tags_issue():
    query = Candidate.query.outerjoin(CandidateTag).filter(CandidateTag.id.is_(None)).order_by(Candidate.created_at.desc())
    return issue(
        "candidate_without_tags",
        "warning",
        "候选人缺少技能标签",
        query.count(),
        "没有技能标签的候选人无法参与准确的岗位匹配和雷达评分。",
        "人才库",
        "进入详情页补标签，或执行后台重解析。",
        [candidate_sample(item) for item in query.limit(5).all()],
    )


def attachment_scan_issue():
    query = ResumeAttachment.query.filter(ResumeAttachment.scan_status.in_(["blocked", "warning"])).order_by(ResumeAttachment.created_at.desc())
    blocked = ResumeAttachment.query.filter_by(scan_status="blocked").count()
    return issue(
        "resume_attachment_scan_issue",
        "error" if blocked else "warning",
        "简历附件扫描异常",
        query.count(),
        "被拦截或告警的附件不应进入正式解析链路。",
        "人才库",
        "在附件列表中复核文件来源，必要时删除后重新上传可信文件。",
        [attachment_sample(item) for item in query.limit(5).all()],
    )


def employee_without_org_issue():
    query = EmployeeProfile.query.filter_by(employment_status="active").filter(EmployeeProfile.organization_unit_id.is_(None)).order_by(EmployeeProfile.updated_at.desc())
    return issue(
        "employee_without_org",
        "warning",
        "在职员工未关联组织",
        query.count(),
        "组织统计、部门人才盘点和调岗分析会不准确。",
        "组织与内部人才",
        "进入内部人才档案，补充组织架构归属。",
        [employee_sample(item) for item in query.limit(5).all()],
    )


def employee_without_job_issue():
    query = EmployeeProfile.query.filter_by(employment_status="active").filter(EmployeeProfile.current_job_id.is_(None)).order_by(EmployeeProfile.updated_at.desc())
    return issue(
        "employee_without_job",
        "warning",
        "在职员工未绑定岗位",
        query.count(),
        "员工能力与 JD 匹配、薪资合理性分析需要当前岗位作为基准。",
        "组织与内部人才",
        "进入员工档案，绑定公司内部岗位或补充当前职位。",
        [employee_sample(item) for item in query.limit(5).all()],
    )


def employee_without_resume_issue():
    query = EmployeeProfile.query.filter_by(employment_status="active").filter((EmployeeProfile.raw_text == "") | (EmployeeProfile.raw_text.is_(None))).order_by(EmployeeProfile.updated_at.desc())
    return issue(
        "employee_without_resume",
        "warning",
        "在职员工缺少简历文本",
        query.count(),
        "缺少简历会导致能力画像、调岗推荐和离职替补推荐依据不足。",
        "组织与内部人才",
        "通过组织架构上传员工简历，或在员工档案补充履历。",
        [employee_sample(item) for item in query.limit(5).all()],
    )


def recruiting_job_without_skills_issue():
    jobs = [
        job
        for job in Job.query.filter_by(status="active").order_by(Job.created_at.desc()).all()
        if not str(job.job_code or "").startswith("INTERNAL-") and not has_job_skills(job)
    ]
    return issue(
        "recruiting_job_without_skills",
        "warning",
        "招聘岗位缺少技能权重",
        len(jobs),
        "缺少结构化技能权重会降低岗位匹配分数的可信度。",
        "岗位匹配",
        "使用 AI 生成 JD 或 AI 校准 JD，确认技能权重后保存岗位。",
        [job_sample(item) for item in jobs[:5]],
    )


def upload_without_file_issue():
    upload_dir = resume_upload_dir()
    missing = []
    for batch in UploadBatch.query.filter_by(source="upload", status="ok").order_by(UploadBatch.created_at.desc()).limit(500).all():
        if not list(upload_dir.glob(f"{batch.id}_*")):
            missing.append(batch)
            if len(missing) >= 20:
                break
    return issue(
        "upload_without_file",
        "warning",
        "上传批次缺少原始文件",
        len(missing),
        "缺少原始文件会影响审计追溯、重新解析和生产迁移校验。",
        "人才库",
        "确认上传目录是否迁移完整，必要时重新上传原始简历。",
        [{"id": item.id, "name": item.filename, "status": item.status, "created_at": iso(item.created_at)} for item in missing[:5]],
    )


def issue(key, severity, title, count, impact, module, action, samples):
    return {
        "key": key,
        "severity": severity,
        "title": title,
        "count": int(count or 0),
        "impact": impact,
        "module": module,
        "action": action,
        "samples": samples,
    }


def has_job_skills(job):
    structured = job.jd_structured or {}
    return bool(structured.get("skills") or structured.get("skill_tags_raw"))


def candidate_sample(candidate, include_error=False):
    data = {
        "id": candidate.id,
        "name": candidate.name_masked,
        "subtitle": candidate.title,
        "status": candidate.parse_status,
        "created_at": iso(candidate.created_at),
    }
    if include_error:
        data["error"] = (candidate.parse_error or "")[:160]
    return data


def employee_sample(employee):
    return {
        "id": employee.id,
        "name": employee.name,
        "subtitle": employee.current_title,
        "status": employee.employment_status,
        "created_at": iso(employee.created_at),
    }


def job_sample(job):
    return {
        "id": job.id,
        "name": job.title,
        "subtitle": job.city or job.department or "",
        "status": job.status,
        "created_at": iso(job.created_at),
    }


def attachment_sample(attachment):
    return {
        "id": attachment.id,
        "name": attachment.original_filename,
        "subtitle": attachment.source,
        "status": attachment.scan_status,
        "created_at": iso(attachment.created_at),
        "error": attachment.scan_summary,
    }


def iso(value):
    return value.isoformat() if value else None
