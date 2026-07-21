from io import BytesIO
import json
import logging
import urllib.error
from datetime import datetime, timedelta, timezone
import zipfile

import jwt
import pytest
from sqlalchemy import inspect

from app import create_app, db
from app.config import Config
from app.auth import verify_password
from app.llm_client import LLMError, chat_json
from app.models import AgentConversation, AgentMessage, AuditLog, BackgroundTask, BossDraft, BossSyncJob, Candidate, CandidateTag, EmployeeCompensation, EmployeeProfile, EmployeeRecommendation, InterviewAssignment, InterviewFeedback, InterviewSpeechLog, Job, LLMUsage, Match, NotificationLog, OfferRecord, OrganizationUnit, PipelineStage, ResumeAttachment, User
from app.task_service import run_next_task


def minimal_organization_xlsx(rows):
    shared = []
    shared_index = {}

    def shared_id(value):
        text = str(value or "")
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    def col_name(index):
        return chr(ord("A") + index)

    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            sid = shared_id(value)
            cells.append(f'<c r="{col_name(col_index)}{row_index}" t="s"><v>{sid}</v></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{0}" uniqueCount="{0}">{1}</sst>'
    ).format(len(shared), "".join(f"<si><t>{text}</t></si>" for text in shared))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{}</sheetData></worksheet>'
    ).format("".join(sheet_rows))
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '</Types>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
    output.seek(0)
    return output


def test_login_returns_user_permissions(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["user"]["role"] == "admin"
    assert "users:manage" in data["user"]["permissions"]


def test_login_locks_after_repeated_failures(client, app):
    app.config["LOGIN_MAX_FAILURES"] = 2
    app.config["LOGIN_LOCKOUT_MINUTES"] = 1

    first = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    second = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-again"})
    locked = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})

    assert first.status_code == 401
    assert first.get_json()["code"] == "INVALID_CREDENTIALS"
    assert second.status_code == 429
    assert second.get_json()["code"] == "LOGIN_LOCKED"
    assert second.get_json()["details"]["retry_after_seconds"] > 0
    assert locked.status_code == 429


def test_auth_is_required_for_business_api(client):
    response = client.get("/api/candidates")

    assert response.status_code == 401
    assert response.get_json()["code"] == "UNAUTHORIZED"
    assert response.headers["X-Request-ID"]


def test_healthz_reports_database_and_security_headers(client):
    response = client.get("/healthz", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_access_log_records_request_metadata(client, caplog):
    caplog.set_level(logging.INFO)

    response = client.get("/healthz", headers={"X-Request-ID": "log-request-id", "User-Agent": "pytest-agent"})

    assert response.status_code == 200
    access_records = [record for record in caplog.records if '"event":"request.completed"' in record.getMessage()]
    assert access_records
    payload = json.loads(access_records[-1].getMessage())
    assert payload["request_id"] == "log-request-id"
    assert payload["method"] == "GET"
    assert payload["path"] == "/healthz"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert payload["user_agent"] == "pytest-agent"
    assert "?" not in payload["path"]


def test_llm_status_does_not_expose_api_key(client, admin_headers):
    response = client.get("/api/system/llm/status", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "DEEPSEEK_API_KEY" not in data
    assert "api_key" not in data
    assert {"enabled", "available", "provider", "model", "timeout_seconds", "max_retries"} <= set(data)


def test_system_settings_manage_ai_and_matching_weights(client, admin_headers):
    response = client.get("/api/settings", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["matching_weights"] == {
        "skill_match": 75,
        "capability": 25,
        "skill_overall": 85,
        "experience": 15,
        "rule": 35,
        "ai": 65,
        "pending_rule": 35,
    }
    assert "api_key" not in data["ai"]

    updated_ai = client.patch(
        "/api/settings/ai",
        headers=admin_headers,
        json={"mode": "ai", "provider": "deepseek", "base_url": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-chat", "api_key": "sk-test-secret", "temperature": 0.2},
    )
    assert updated_ai.status_code == 200
    assert updated_ai.get_json()["data"]["api_key_configured"] is True
    assert "sk-test-secret" not in json.dumps(updated_ai.get_json()["data"])

    weights = client.patch("/api/settings/matching-weights", headers=admin_headers, json={"skill_match": 60, "capability": 40, "rule": 50, "ai": 50})
    assert weights.status_code == 200
    payload = weights.get_json()["data"]
    assert payload["skill_match"] == 60
    assert payload["capability"] == 40
    assert payload["rule"] == 50
    assert payload["ai"] == 50

    auto = client.post("/api/settings/matching-weights/auto", headers=admin_headers, json={"profile": "strict"})
    assert auto.status_code == 200
    assert auto.get_json()["data"]["ai"] == 70


def test_system_readiness_reports_config_without_secrets(client, admin_headers):
    response = client.get("/api/system/readiness", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {"ready", "environment", "database", "checks", "summary"} <= set(data)
    assert any(item["key"] == "jwt_secret" for item in data["checks"])
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)
    assert "test-secret" not in json.dumps(data)


def test_system_data_integrity_reports_counts_and_checks(client, admin_headers):
    response = client.get("/api/system/data-integrity", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {"ready", "checked_at", "database", "summary", "counts", "checks", "details"} <= set(data)
    assert data["counts"]["candidates"] >= 1
    assert data["counts"]["jobs"] >= 1
    assert any(item["key"] == "orphan_relations" for item in data["checks"])
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)


def test_ops_backup_status_reports_safe_operational_state(client, admin_headers):
    response = client.get("/api/ops/backup/status", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {"environment", "database", "readiness", "migration", "storage", "recent_packages", "commands"} <= set(data)
    assert "backup_dir" in data["storage"]
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)
    assert "test-secret" not in json.dumps(data)


def test_ops_backup_export_runs_as_background_task(app, client, admin_headers, tmp_path):
    app.config["BACKUP_FOLDER"] = str(tmp_path)

    response = client.post("/api/ops/backup/export", headers=admin_headers)

    assert response.status_code == 200
    task = response.get_json()["data"]["task"]
    assert task["task_type"] == "backup_export"
    assert task["status"] == "queued"

    completed = run_next_task()
    assert completed.id == task["id"]
    assert completed.status == "succeeded"
    package_path = completed.result["package"]
    assert package_path.endswith(".zip")
    with zipfile.ZipFile(package_path, "r") as archive:
        assert "manifest.json" in archive.namelist()
        assert "data.json" in archive.namelist()


def test_ops_data_quality_reports_actionable_issues(client, admin_headers):
    response = client.get("/api/ops/data-quality", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {"ready", "summary", "issues"} <= set(data)
    assert {"errors", "warnings", "issues", "items"} <= set(data["summary"])
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)
    assert "test-secret" not in json.dumps(data)


def test_ops_data_quality_excludes_internal_jobs_from_recruiting_skill_issue(client, admin_headers):
    admin_id = client.get("/api/auth/me", headers=admin_headers).get_json()["data"]["id"]
    internal_job = Job(owner_hr_id=admin_id, title="内部架构师", city="长沙", department="内部", job_code="INTERNAL-QUALITY", jd_text="内部任职岗位", jd_structured={}, status="active")
    recruiting_job = Job(owner_hr_id=admin_id, title="外部招聘岗位", city="长沙", department="招聘", job_code="QUALITY-OPEN", jd_text="招聘岗位", jd_structured={}, status="active")
    db.session.add_all([internal_job, recruiting_job])
    db.session.commit()

    response = client.get("/api/ops/data-quality", headers=admin_headers)

    assert response.status_code == 200
    issues = response.get_json()["data"]["issues"]
    skill_issue = next(item for item in issues if item["key"] == "recruiting_job_without_skills")
    sample_names = [item["name"] for item in skill_issue["samples"]]
    assert "外部招聘岗位" in sample_names
    assert "内部架构师" not in sample_names


def test_bi_overview_counts_only_recruiting_active_jobs(client, admin_headers):
    admin_id = client.get("/api/auth/me", headers=admin_headers).get_json()["data"]["id"]
    recruiting_job = Job(owner_hr_id=admin_id, title="BI招聘岗位", city="长沙", department="招聘", job_code="BI-OPEN", jd_text="招聘岗位", jd_structured={"skills": [{"tag": "Java", "weight": 5}], "skill_tags_raw": "Java 5"}, status="active")
    internal_job = Job(owner_hr_id=admin_id, title="BI内部岗位", city="长沙", department="内部", job_code="INTERNAL-BI", jd_text="内部任职岗位", jd_structured={"source": "internal_employee_import"}, status="active")
    db.session.add_all([recruiting_job, internal_job])
    db.session.commit()

    response = client.get("/api/bi/overview", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    active_recruiting_jobs = [job for job in Job.query.filter_by(status="active").all() if not str(job.job_code or "").startswith("INTERNAL-")]
    assert data["active_jobs"] == len(active_recruiting_jobs)
    assert data["active_jobs"] < Job.query.filter_by(status="active").count()

def test_ops_deploy_gates_reports_release_blockers_without_secrets(client, admin_headers):
    response = client.get("/api/ops/deploy-gates", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {"ready", "summary", "gates"} <= set(data)
    assert data["summary"]["total"] >= 10
    assert any(item["key"] == "environment" for item in data["gates"])
    assert any(item["key"] == "backup_dir" for item in data["gates"])
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)
    assert "test-secret" not in json.dumps(data)


def test_notification_center_channel_event_and_logs(client, admin_headers):
    created = client.post(
        "/api/notifications/channels",
        headers=admin_headers,
        json={
            "name": "企业微信测试",
            "channel_type": "wecom",
            "config": {"webhook_url": "https://example.com/hook", "default_recipient": "hr@example.com"},
        },
    )
    assert created.status_code == 200
    channel = created.get_json()["data"]
    assert channel["config"]["webhook_url"] == "***"

    events = client.get("/api/notifications/events", headers=admin_headers)
    assert events.status_code == 200
    event_items = events.get_json()["data"]["items"]
    assert any(item["event_type"] == "interview_scheduled" for item in event_items)

    test_send = client.post(
        "/api/notifications/send-test",
        headers=admin_headers,
        json={"channel_id": channel["id"], "subject": "上线测试", "content": "通知中心测试"},
    )
    assert test_send.status_code == 200
    log = test_send.get_json()["data"]["log"]
    assert log["status"] == "sent"
    assert log["channel"]["config"]["webhook_url"] == "***"

    logs = client.get("/api/notifications/logs?event_type=manual_test", headers=admin_headers)
    assert logs.status_code == 200
    assert logs.get_json()["data"]["items"][0]["subject"] == "上线测试"

    updated = client.patch(f"/api/notifications/channels/{channel['id']}", headers=admin_headers, json={"enabled": False})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["enabled"] is False


def test_business_actions_emit_notification_logs(client, admin_headers):
    channel_response = client.post(
        "/api/notifications/channels",
        headers=admin_headers,
        json={"name": "Business Console", "channel_type": "console", "config": {"default_recipient": "hr@example.com"}},
    )
    assert channel_response.status_code == 200

    imported = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={
            "items": [
                {
                    "external_id": "notify-java",
                    "raw_text": "Name: Notify Candidate\nPhone: 13922223333 notify@example.com\n4 years Java backend development experience, familiar with Spring Boot, MySQL and Redis.",
                }
            ]
        },
    )
    assert imported.status_code == 200
    candidate_id = imported.get_json()["data"]["items"][0]["id"]

    assert client.post("/api/jobs/1/match", headers=admin_headers).status_code == 200
    assert client.post("/api/jobs/1/batch-pipeline", headers=admin_headers, json={"candidate_id": candidate_id, "stage": "pending"}).status_code == 200

    assignment_response = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": candidate_id, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    )
    assert assignment_response.status_code == 200
    assignment = assignment_response.get_json()["data"]
    feedback = client.post(
        "/api/interview/feedback",
        headers=admin_headers,
        json={"assignment_id": assignment["id"], "rating": 4, "decision": "pass", "strengths": "ok"},
    )
    assert feedback.status_code == 200

    offer_response = client.post("/api/offers", headers=admin_headers, json={"candidate_id": candidate_id, "job_id": 1, "status": "draft"})
    assert offer_response.status_code == 200
    offer = offer_response.get_json()["data"]
    assert client.patch(f"/api/offers/{offer['id']}", headers=admin_headers, json={"status": "sent"}).status_code == 200

    event_types = {item.event_type for item in NotificationLog.query.all()}
    assert {
        "candidate_imported",
        "boss_sync_completed",
        "job_matched",
        "pipeline_updated",
        "interview_scheduled",
        "interview_completed",
        "offer_created",
        "offer_status_changed",
    } <= event_types
    assert NotificationLog.query.filter_by(status="sent").count() >= 8


def test_llm_chat_json_retries_transient_failure(app, monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            body = {
                "choices": [{"message": {"content": json.dumps({"ok": True})}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            }
            return json.dumps(body).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("temporary outage")
        return FakeResponse()

    app.config["LLM_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    app.config["LLM_MAX_RETRIES"] = 1
    app.config["LLM_RETRY_BACKOFF_SECONDS"] = 0
    app.config["LLM_PROMPT_PRICE_PER_1M_TOKENS_USD"] = 1
    app.config["LLM_COMPLETION_PRICE_PER_1M_TOKENS_USD"] = 2
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with app.app_context():
        assert chat_json([{"role": "user", "content": "json"}], source="test_suite", tool_name="unit_test_tool") == {"ok": True}
        usage = LLMUsage.query.order_by(LLMUsage.id.desc()).first()
        assert usage is not None
        assert usage.success is True
        assert usage.source == "test_suite"
        assert usage.tool_name == "unit_test_tool"
        assert usage.api_path is None
        assert usage.prompt_tokens == 12
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 17
        assert usage.attempts == 2
        assert usage.cost_usd > 0
    assert calls["count"] == 2


def test_llm_usage_endpoint_summarizes_without_secrets(client, admin_headers, app):
    app.config["LLM_DAILY_CALL_LIMIT"] = 1
    app.config["LLM_DAILY_COST_LIMIT_USD"] = 0.001
    app.config["LLM_FAILURE_RATE_WARN_PERCENT"] = 10
    with app.app_context():
        db.session.add(
            LLMUsage(
                provider="deepseek",
                model="deepseek-chat",
                endpoint="https://api.deepseek.com/v1/chat/completions",
                request_id="usage-test",
                success=True,
                prompt_tokens=100,
                completion_tokens=40,
                total_tokens=140,
                estimated=False,
                cost_usd=0.01,
                duration_ms=300,
                attempts=1,
            )
        )
        db.session.add(
            LLMUsage(
                provider="deepseek",
                model="deepseek-chat",
                endpoint="https://api.deepseek.com/v1/chat/completions",
                request_id="usage-failed",
                success=False,
                error="timeout",
                prompt_tokens=20,
                completion_tokens=0,
                total_tokens=20,
                estimated=True,
                cost_usd=0,
                duration_ms=45000,
                attempts=2,
            )
        )
        db.session.commit()

    response = client.get("/api/system/llm/usage?days=1", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["summary"]["total_calls"] >= 2
    assert data["summary"]["failed_calls"] >= 1
    assert data["summary"]["failure_rate"] > 0
    assert data["summary"]["total_tokens"] >= 160
    assert data["summary"]["estimated_cost_usd"] >= 0.01
    assert data["summary"]["avg_daily_calls"] > 0
    assert data["limits"]["daily_call_limit"] == 1
    assert {item["key"] for item in data["alerts"]} >= {"daily_calls", "daily_cost"}
    assert {"source", "tool_name", "api_path"} <= set(data["items"][0])
    assert "DEEPSEEK_API_KEY" not in json.dumps(data)
    assert "test-key" not in json.dumps(data)


def test_production_config_rejects_demo_secret_and_sqlite():
    class UnsafeProductionConfig(Config):
        TESTING = False
        ENVIRONMENT = "production"
        JWT_SECRET = "demo-secret"
        CORS_ORIGINS = ["*"]
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SEED_DEMO_DATA = True

    with pytest.raises(RuntimeError, match="生产配置不安全"):
        create_app(UnsafeProductionConfig)


def test_common_query_indexes_exist(app):
    inspector = inspect(db.engine)

    candidate_indexes = {item["name"] for item in inspector.get_indexes("candidate")}
    pipeline_indexes = {item["name"] for item in inspector.get_indexes("pipeline_stage")}
    audit_indexes = {item["name"] for item in inspector.get_indexes("audit_log")}
    task_indexes = {item["name"] for item in inspector.get_indexes("background_task")}
    llm_usage_indexes = {item["name"] for item in inspector.get_indexes("llm_usage")}

    assert "ix_candidate_source_created_at" in candidate_indexes
    assert "ix_candidate_phone_masked" in candidate_indexes
    assert "ix_pipeline_stage_job_candidate_ts" in pipeline_indexes
    assert "ix_audit_log_target_created" in audit_indexes
    assert "ix_background_task_status_created" in task_indexes
    assert "ix_llm_usage_success_created" in llm_usage_indexes


def test_admin_can_manage_users(client, admin_headers, recruiter_headers):
    forbidden = client.get("/api/users", headers=recruiter_headers)
    assert forbidden.status_code == 403

    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "interviewer1", "name": "面试官一", "role": "interviewer", "password": "Pass1234"},
    )
    assert created.status_code == 200
    user = created.get_json()["data"]
    assert user["role"] == "interviewer"
    assert "interviews:feedback" in user["permissions"]

    updated = client.patch(f"/api/users/{user['id']}", headers=admin_headers, json={"active": False})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["active"] is False


def test_user_password_must_be_strong(client, admin_headers):
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "weak1", "name": "弱密码", "role": "recruiter", "password": "12345678"},
    )

    assert created.status_code == 400
    assert created.get_json()["code"] == "WEAK_PASSWORD"

    updated = client.patch("/api/users/1", headers=admin_headers, json={"password": "password123"})
    assert updated.status_code == 400
    assert updated.get_json()["code"] == "WEAK_PASSWORD"


def test_internal_talent_organization_employee_analysis_and_recommendations(client, admin_headers, app, monkeypatch):
    tree = client.get("/api/organization/tree", headers=admin_headers)
    assert tree.status_code == 200
    root = tree.get_json()["data"]["items"][0]
    assert root["name"] == "总公司"

    unit = client.post(
        "/api/organization/units",
        headers=admin_headers,
        json={"parent_id": root["id"], "name": "后端研发部", "unit_type": "department", "headcount_plan": 8},
    ).get_json()["data"]
    job = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={
            "title": "内部 Java 后端工程师",
            "city": "上海",
            "department": "后端研发部",
            "jd_text": "负责 Java 后端服务开发，薪资 20-30K，要求 Spring Boot、MySQL、Redis。",
            "skill_tags_raw": "Java 5\nSpring Boot 5\nMySQL 4\nRedis 4",
        },
    ).get_json()["data"]
    employee_csv = BytesIO(
        f"employee_no,name,phone,email,organization_unit_id,current_job_id,level,city,status,hire_date,salary_monthly_k,salary_months,summary\n"
        f"EMP-CSV-001,Imported Employee,13800001111,imported@example.com,{unit['id']},{job['id']},P5,Shanghai,active,2026-07-01,22,13,Imported internal profile\n".encode()
    )
    employee_import = client.post(
        "/api/employees/import-excel",
        headers=admin_headers,
        data={"file": (employee_csv, "employees.csv")},
        content_type="multipart/form-data",
    )
    assert employee_import.status_code == 200
    employee_import_data = employee_import.get_json()["data"]
    assert employee_import_data["created_count"] == 1
    imported_employee = employee_import_data["created"][0]["employee"]
    assert imported_employee["employee_no"] == "EMP-CSV-001"
    assert imported_employee["organization_unit"]["id"] == unit["id"]
    assert imported_employee["current_job"]["id"] == job["id"]
    assert imported_employee["compensation"]["salary_annual_k"] == 286

    employee_update_csv = BytesIO(
        f"employee_no,name,organization_unit_id,current_job_id,level,salary_monthly_k,salary_months\n"
        f"EMP-CSV-001,Imported Employee Updated,{unit['id']},{job['id']},P6,24,14\n".encode()
    )
    employee_update = client.post(
        "/api/employees/import-excel",
        headers=admin_headers,
        data={"file": (employee_update_csv, "employees-update.csv")},
        content_type="multipart/form-data",
    )
    assert employee_update.status_code == 200
    employee_update_data = employee_update.get_json()["data"]
    assert employee_update_data["updated_count"] == 1
    assert EmployeeProfile.query.filter_by(employee_no="EMP-CSV-001").count() == 1

    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "internal-java", "raw_text": "姓名：内部候选人\n男 13800009999 internal@example.com\n4 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis。"}]},
    ).get_json()["data"]["items"][0]

    created = client.post(
        "/api/employees/from-candidate",
        headers=admin_headers,
        json={
            "candidate_id": candidate["id"],
            "organization_unit_id": unit["id"],
            "current_job_id": job["id"],
            "employee_no": "EMP-T-001",
            "level": "P6",
            "salary_monthly_k": 18,
            "salary_months": 13,
            "hire_date": "2026-07-06",
        },
    )
    assert created.status_code == 200
    employee = created.get_json()["data"]
    assert employee["candidate_id"] == candidate["id"]
    assert employee["organization_unit"]["name"] == "后端研发部"
    assert employee["compensation"]["salary_annual_k"] == 234

    duplicate = client.post("/api/employees/from-candidate", headers=admin_headers, json={"candidate_id": candidate["id"]})
    assert duplicate.status_code == 200
    assert duplicate.get_json()["data"]["id"] == employee["id"]
    assert EmployeeProfile.query.filter_by(candidate_id=candidate["id"]).count() == 1

    department_employees = client.get(f"/api/organization/units/{unit['id']}/employees", headers=admin_headers)
    assert department_employees.status_code == 200
    assert department_employees.get_json()["data"]["items"][0]["id"] == employee["id"]

    app.config["LLM_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    ai_calls = []

    def fake_employee_chat_json(messages, **kwargs):
        ai_calls.append({"messages": messages, "kwargs": kwargs})
        assert "员工完整简历" in messages[-1]["content"]
        assert "规则薪资分析" in messages[-1]["content"]
        return {
            "score": 88,
            "recommendation": "匹配",
            "summary": "AI 阅读完整简历和 JD 后判断，员工与 Java 后端岗位匹配，薪资偏低需要复核。",
            "strengths": ["Java 后端经验与 JD 对齐"],
            "risks": ["薪资低于岗位区间下限"],
            "evidence": ["简历中出现 Spring Boot、MySQL、Redis 项目经验"],
            "rule_corrections": ["规则标签命中有效，未发现明显噪音"],
            "salary": {"score": 72, "status": "low", "summary": "当前 18K 低于 20-30K 岗位区间。"},
            "actions": ["建议 HRBP 复核薪资并制定保留方案"],
        }

    monkeypatch.setattr("app.routes.chat_json", fake_employee_chat_json)

    analysis = client.post(f"/api/employees/{employee['id']}/analyze-current-job", headers=admin_headers)
    assert analysis.status_code == 200
    analysis_data = analysis.get_json()["data"]
    assert analysis_data["match_score"] >= 88
    assert analysis_data["salary_status"] == "low"
    assert analysis_data["salary_score"] == 72
    assert analysis_data["source"] == "deepseek"
    assert analysis_data["analysis"]["ai_review"]["source"] == "deepseek"
    assert analysis_data["analysis"]["ai_review"]["score"] == 88
    assert analysis_data["analysis"]["ai_review"]["evidence"]

    batch_analysis = client.post("/api/employees/batch-analyze", headers=admin_headers, json={"organization_unit_id": unit["id"]})
    assert batch_analysis.status_code == 200
    batch_data = batch_analysis.get_json()["data"]
    assert batch_data["analyzed_count"] >= 1
    assert "skipped_count" in batch_data

    transfer = client.post(f"/api/employees/{employee['id']}/recommend-transfer", headers=admin_headers)
    assert transfer.status_code == 200
    assert "items" in transfer.get_json()["data"]
    assert ai_calls

    client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "replacement-java", "raw_text": "姓名：替补候选人\n电话：13800008888\n5 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis，负责核心业务系统稳定性。"}]},
    )
    replacement_ai_calls = []

    def fake_replacement_chat_json(messages, **kwargs):
        replacement_ai_calls.append({"messages": messages, "kwargs": kwargs})
        assert "候选人完整简历" in messages[-1]["content"]
        assert "岗位 JD" in messages[-1]["content"]
        return {
            "score": 86,
            "recommendation": "推荐",
            "summary": "候选人与离职员工当前岗位 JD 匹配，可作为替补重点沟通。",
            "strengths": ["Java 后端经验匹配"],
            "risks": ["需复核业务复杂度"],
            "interview_focus": ["核心系统稳定性职责"],
            "evidence": ["简历中有 Spring Boot、MySQL、Redis 项目经验"],
            "rule_corrections": ["规则命中与简历证据一致"],
        }

    monkeypatch.setattr("app.job_service.chat_json", fake_replacement_chat_json)

    replacement = client.post(f"/api/employees/{employee['id']}/recommend-replacement", headers=admin_headers)
    assert replacement.status_code == 200
    replacement_items = replacement.get_json()["data"]["items"]
    assert replacement_items
    assert replacement_ai_calls
    assert any(item["reason"]["ai_review"]["source"] == "deepseek" for item in replacement_items)
    assert "replacement_context" in replacement_items[0]["reason"]

    detail = client.get(f"/api/employees/{employee['id']}", headers=admin_headers)
    assert detail.status_code == 200
    detail_data = detail.get_json()["data"]
    assert detail_data["candidate"]["id"] == candidate["id"]
    assert any(item["recommendation_type"] == "replacement" for item in detail_data["recommendations"])
    assert detail_data["recommendations"][0]["score"] >= detail_data["recommendations"][-1]["score"]

    queued_analysis = client.post(f"/api/employees/{employee['id']}/analyze-current-job?async=1", headers=admin_headers)
    assert queued_analysis.status_code == 200
    analysis_task = queued_analysis.get_json()["data"]["task"]
    assert analysis_task["task_type"] == "employee_analyze_current_job"
    run_analysis_task = client.post(f"/api/tasks/{analysis_task['id']}/run", headers=admin_headers)
    assert run_analysis_task.status_code == 200
    assert run_analysis_task.get_json()["data"]["status"] == "succeeded"

    queued_transfer = client.post(f"/api/employees/{employee['id']}/recommend-transfer?async=1", headers=admin_headers)
    assert queued_transfer.status_code == 200
    assert queued_transfer.get_json()["data"]["task"]["task_type"] == "employee_recommend_transfer"

    queued_replacement = client.post(f"/api/employees/{employee['id']}/recommend-replacement?async=1", headers=admin_headers)
    assert queued_replacement.status_code == 200
    assert queued_replacement.get_json()["data"]["task"]["task_type"] == "employee_recommend_replacement"

    report = client.get(f"/api/employees/{employee['id']}/report.txt", headers=admin_headers)
    assert report.status_code == 200
    assert "内部员工分析报告" in report.get_data(as_text=True)
    assert "内部候选人" in report.get_data(as_text=True)

    exported = client.get("/api/exports/employees.csv", headers=admin_headers)
    assert exported.status_code == 200
    exported_text = exported.get_data(as_text=True)
    assert "员工编号" in exported_text
    assert "EMP-T-001" in exported_text

    salary_csv = BytesIO(b"employee_no,salary_monthly_k,salary_months,bonus_k,effective_date\nEMP-T-001,26,14,8,2026-07-07\n")
    salary_import = client.post(
        "/api/employees/compensation-import",
        headers=admin_headers,
        data={"file": (salary_csv, "salary.csv")},
        content_type="multipart/form-data",
    )
    assert salary_import.status_code == 200
    salary_data = salary_import.get_json()["data"]
    assert salary_data["updated_count"] == 1
    detail_after_salary = client.get(f"/api/employees/{employee['id']}", headers=admin_headers)
    compensation = detail_after_salary.get_json()["data"]["compensation"]
    assert compensation["salary_monthly_k"] == 26
    assert compensation["salary_annual_k"] == 372
    assert compensation["source"] == "import"

    transfer_unit = client.post(
        "/api/organization/units",
        headers=admin_headers,
        json={"parent_id": root["id"], "name": "平台架构部", "unit_type": "department"},
    ).get_json()["data"]
    transfer_job = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={
            "title": "内部平台架构师",
            "city": "长沙",
            "department": "平台架构部",
            "status": "active",
            "jd_text": "负责 Java 微服务平台架构，薪资 25-35K，要求 Spring Boot、MySQL、Redis、Kubernetes。",
            "skill_tags_raw": "Java 5\nSpring Boot 5\nMySQL 4\nRedis 4\nKubernetes 3",
        },
    ).get_json()["data"]
    patched = client.patch(
        f"/api/employees/{employee['id']}",
        headers=admin_headers,
        json={
            "organization_unit_id": transfer_unit["id"],
            "current_job_id": transfer_job["id"],
            "level": "P7",
            "salary_monthly_k": 28,
            "salary_months": 13,
        },
    )
    assert patched.status_code == 200
    patched_employee = patched.get_json()["data"]
    assert patched_employee["organization_unit"]["name"] == "平台架构部"
    assert patched_employee["department"] == "平台架构部"
    assert patched_employee["current_job"]["title"] == "内部平台架构师"
    assert patched_employee["current_title"] == "内部平台架构师"
    assert patched_employee["compensation"]["salary_monthly_k"] == 28

    resume_file = BytesIO("姓名：内部员工简历\n电话：13800007777\n邮箱：internal-resume@example.com\n6 年 Java 后端与平台架构经验，熟悉 Spring Boot、MySQL、Redis、Kubernetes。".encode("utf-8"))
    resume_upload = client.post(
        f"/api/employees/{employee['id']}/resume",
        headers=admin_headers,
        data={"file": (resume_file, "employee-resume.txt")},
        content_type="multipart/form-data",
    )
    assert resume_upload.status_code == 200
    resume_employee = resume_upload.get_json()["data"]
    assert resume_employee["candidate_id"]
    assert "Kubernetes" in resume_employee["raw_text"]
    assert resume_employee["parse_status"] == "ok"

    assert AuditLog.query.filter_by(target_type="employee", target_id=employee["id"]).count() >= 2


def test_recruiter_cannot_view_internal_salary_details(client, admin_headers, recruiter_headers):
    root = client.get("/api/organization/tree", headers=admin_headers).get_json()["data"]["items"][0]
    unit = client.post(
        "/api/organization/units",
        headers=admin_headers,
        json={"parent_id": root["id"], "name": "薪资隔离测试部", "unit_type": "department"},
    ).get_json()["data"]
    job = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={
            "title": "内部 Java 工程师",
            "city": "上海",
            "jd_text": "负责 Java 后端服务开发，薪资 20-30K，要求 Spring Boot、MySQL、Redis。",
            "skill_tags_raw": "Java 5\nSpring Boot 5\nMySQL 4\nRedis 4",
        },
    ).get_json()["data"]
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "salary-mask", "raw_text": "姓名：薪资隔离员工\n电话：13800001234\n5 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis。"}]},
    ).get_json()["data"]["items"][0]
    employee = client.post(
        "/api/employees/from-candidate",
        headers=admin_headers,
        json={
            "candidate_id": candidate["id"],
            "organization_unit_id": unit["id"],
            "current_job_id": job["id"],
            "employee_no": "EMP-SALARY-MASK",
            "salary_monthly_k": 18,
            "salary_months": 13,
        },
    ).get_json()["data"]
    assert employee["compensation"]["salary_annual_k"] == 234

    list_response = client.get("/api/employees", headers=recruiter_headers)
    assert list_response.status_code == 200
    listed = [item for item in list_response.get_json()["data"]["items"] if item["id"] == employee["id"]][0]
    assert listed["compensation"] is None
    assert listed["salary_hidden"] is True

    detail = client.get(f"/api/employees/{employee['id']}", headers=recruiter_headers)
    assert detail.status_code == 200
    detail_data = detail.get_json()["data"]
    assert detail_data["compensation"] is None
    assert detail_data["salary_hidden"] is True
    assert "salary_monthly_k" not in json.dumps(detail_data, ensure_ascii=False)
    assert "salary_annual_k" not in json.dumps(detail_data, ensure_ascii=False)

    analysis = client.post(f"/api/employees/{employee['id']}/analyze-current-job", headers=recruiter_headers)
    assert analysis.status_code == 200
    analysis_data = analysis.get_json()["data"]
    assert analysis_data["salary_status"] == "low"
    assert analysis_data["salary_score"] > 0
    assert "monthly_k" not in analysis_data["analysis"]["salary"]
    assert "range" not in analysis_data["analysis"]["salary"]

    report = client.get(f"/api/employees/{employee['id']}/report.txt", headers=recruiter_headers)
    assert report.status_code == 200
    report_text = report.get_data(as_text=True)
    assert "薪资已隐藏" in report_text
    assert "18.0K" not in report_text
    assert "234.0K" not in report_text


def test_employee_import_replaces_org_tree_and_tracks_demographics(client, admin_headers):
    client.get("/api/organization/tree", headers=admin_headers)
    employee_csv = (
        "姓名,1级部门,2级部门,3级部门,职位,入职时间,出生日期,学历,毕业院校,毕业时间\n"
        "组织员工A,产品中心,平台产品部,支付产品组,产品经理,2020-01-15,1995-05-20,本科,湖南大学,2017-06\n"
        "组织员工B,研发中心,后端研发部,Java组,Java工程师,2021/03/01,1996/08/09,硕士,中南大学,2020/06/30\n"
    ).encode("utf-8")

    imported = client.post(
        "/api/employees/import-excel?replace=1",
        headers=admin_headers,
        data={"file": (BytesIO(employee_csv), "employees.csv")},
        content_type="multipart/form-data",
    )

    assert imported.status_code == 200
    data = imported.get_json()["data"]
    assert data["created_count"] == 2
    assert data["updated_count"] == 0
    employee = data["created"][0]["employee"]
    assert employee["employee_no"].startswith("EMP-")
    assert employee["education"] == "本科"
    assert employee["graduation_school"] == "湖南大学"
    assert employee["graduation_date"] == "2017-06-01"
    assert employee["birth_date"] == "1995-05-20"
    assert employee["seniority_years"] >= 6
    assert employee["organization_unit"]["name"] == "支付产品组"
    assert employee["current_job"]["title"] == "产品经理"
    assert employee["current_job"]["job_code"].startswith("INTERNAL-")

    internal_job_id = employee["current_job"]["id"]
    recruiting_jobs = client.get("/api/jobs", headers=admin_headers).get_json()["data"]["items"]
    assert all(not str(item.get("job_code") or "").startswith("INTERNAL-") for item in recruiting_jobs)
    internal_jobs = client.get("/api/jobs?scope=internal", headers=admin_headers).get_json()["data"]["items"]
    assert any(item["id"] == internal_job_id for item in internal_jobs)
    match_preview = client.get(f"/api/jobs/{internal_job_id}/match-preview", headers=admin_headers)
    assert match_preview.status_code == 409
    assert match_preview.get_json()["code"] == "INTERNAL_JOB_NOT_RECRUITING"
    run_match = client.post(f"/api/jobs/{internal_job_id}/match", headers=admin_headers)
    assert run_match.status_code == 409
    pipeline = client.post(f"/api/jobs/{internal_job_id}/batch-pipeline", headers=admin_headers, json={"candidate_id": 1})
    assert pipeline.status_code == 409

    tree = client.get("/api/organization/tree", headers=admin_headers).get_json()["data"]["items"]
    root = tree[0]
    assert root["name"] == "总公司"
    assert {item["name"] for item in root["children"]} == {"产品中心", "研发中心"}
    assert root["employee_count"] == 2
    assert next(item for item in root["children"] if item["name"] == "产品中心")["employee_count"] == 1

    employees = client.get("/api/employees", headers=admin_headers).get_json()["data"]
    assert employees["total"] == 2
    assert employees["limit"] == 20
    assert employees["overview"]["avg_seniority_years"] >= 5

    paged = client.get("/api/employees?limit=1&offset=1", headers=admin_headers).get_json()["data"]
    assert paged["total"] == 2
    assert paged["limit"] == 1
    assert paged["offset"] == 1
    assert len(paged["items"]) == 1

    name_search = client.get("/api/employees?q=组织员工A", headers=admin_headers).get_json()["data"]
    assert name_search["total"] == 1
    assert name_search["items"][0]["name"] == "组织员工A"
    title_search = client.get("/api/employees?q=Java工程师", headers=admin_headers).get_json()["data"]
    assert title_search["total"] == 1
    assert title_search["items"][0]["current_job"]["title"] == "Java工程师"


def test_organization_excel_import_and_department_resume_upload(client, admin_headers):
    excel = minimal_organization_xlsx(
        [
            ["序号", "一级部门", "二级部门", "三级部门"],
            ["1", "SIM空间运营团队", "超级sim产品事业部", "SIM空间运营团队"],
            ["", "", "", "证券业务研发"],
            ["", "", "互金运营事业部", "金融运营部"],
            ["2", "产品开发团队", "缴费产品事业部", "客户业务研发部"],
            ["3", "CodexRoot", "", "DirectTeam"],
        ]
    )
    imported = client.post(
        "/api/organization/import-excel",
        headers=admin_headers,
        data={"file": (excel, "组织架构.xlsx")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    tree = imported.get_json()["data"]["tree"]
    assert any(item["name"] == "SIM空间运营团队" for item in tree[0]["children"])

    team = OrganizationUnit.query.filter_by(name="证券业务研发").first()
    assert team is not None
    direct_team = OrganizationUnit.query.filter_by(name="DirectTeam").first()
    assert direct_team is not None
    assert direct_team.parent.name == "CodexRoot"
    resume = BytesIO("姓名：组织员工\n男 13911112222 org@example.com\n3 年 Java 后端开发经验，熟悉 Spring Boot 和 MySQL。".encode("utf-8"))
    uploaded = client.post(
        f"/api/organization/units/{team.id}/employee-resumes",
        headers=admin_headers,
        data={"files": (resume, "org-employee.txt")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    data = uploaded.get_json()["data"]
    assert data["success_count"] == 1
    assert data["employees"][0]["name"] == "组织员工"
    assert data["employees"][0]["organization_unit"]["name"] == "证券业务研发"

    employees = client.get(f"/api/organization/units/{team.id}/employees", headers=admin_headers)
    assert employees.status_code == 200
    assert employees.get_json()["data"]["items"][0]["name"] == "组织员工"

    blocked_delete = client.delete(f"/api/organization/units/{team.id}", headers=admin_headers)
    assert blocked_delete.status_code == 409
    assert blocked_delete.get_json()["code"] == "ORG_HAS_EMPLOYEES"


def test_cli_can_create_admin_and_reset_password(app, client):
    runner = app.test_cli_runner()

    created = runner.invoke(args=["create-admin", "--username", "prod_admin", "--name", "生产管理员", "--password", "Strong123"])
    assert created.exit_code == 0
    user = User.query.filter_by(username="prod_admin").first()
    assert user is not None
    assert user.role == "admin"
    assert user.active is True

    login = client.post("/api/auth/login", json={"username": "prod_admin", "password": "Strong123"})
    assert login.status_code == 200

    reset = runner.invoke(args=["reset-password", "--username", "prod_admin", "--password", "NewStrong123"])
    assert reset.exit_code == 0
    db.session.refresh(user)
    assert verify_password("NewStrong123", user.password_hash)


def test_cli_prune_data_requires_confirm(app):
    runner = app.test_cli_runner()
    old = datetime.now(timezone.utc) - timedelta(days=400)
    recent = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add(AuditLog(user_id=1, action="old", target_type="candidate", target_id=1, target_name="old", created_at=old))
        db.session.add(AuditLog(user_id=1, action="recent", target_type="candidate", target_id=1, target_name="recent", created_at=recent))
        db.session.add(
            LLMUsage(
                provider="deepseek",
                model="deepseek-chat",
                success=True,
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated=True,
                cost_usd=0,
                duration_ms=100,
                attempts=1,
                created_at=old,
            )
        )
        db.session.add(
            BackgroundTask(
                task_type="resume_retry_parse",
                status="succeeded",
                payload={},
                result={},
                attempts=1,
                max_attempts=3,
                created_by=1,
                created_at=old,
                updated_at=old,
            )
        )
        db.session.commit()

        dry_run = runner.invoke(args=["prune-data", "--audit-days", "365", "--llm-days", "180", "--task-days", "90"])
        assert dry_run.exit_code == 0
        assert "dry_run=True" in dry_run.output
        assert "audit_logs=1" in dry_run.output
        assert "llm_usages=1" in dry_run.output
        assert "background_tasks=1" in dry_run.output
        assert AuditLog.query.filter_by(action="old").count() == 1

        confirmed = runner.invoke(args=["prune-data", "--audit-days", "365", "--llm-days", "180", "--task-days", "90", "--confirm"])
        assert confirmed.exit_code == 0
        assert "prune committed" in confirmed.output
        assert AuditLog.query.filter_by(action="old").count() == 0
        assert AuditLog.query.filter_by(action="recent").count() == 1
        assert LLMUsage.query.count() == 0
        assert BackgroundTask.query.count() == 0


def test_audit_logs_record_sensitive_actions(client, admin_headers):
    client.patch("/api/candidates/1", headers=admin_headers, json={"name_masked": "审计候选人"})
    job = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={"title": "审计岗位", "city": "上海", "jd_text": "需要 Java、MySQL。", "skill_tags_raw": "Java 4\nMySQL 4"},
    ).get_json()["data"]

    response = client.get("/api/audit/logs", headers=admin_headers)

    assert response.status_code == 200
    logs = response.get_json()["data"]["items"]
    assert any(item["action"] == "update" and item["target_type"] == "candidate" for item in logs)
    assert any(item["action"] == "create" and item["target_type"] == "job" and item["target_id"] == job["id"] for item in logs)
    assert AuditLog.query.count() >= 2


def test_list_endpoints_return_pagination_meta(client, admin_headers):
    client.patch("/api/candidates/1", headers=admin_headers, json={"name_masked": "分页审计候选人"})

    candidates = client.get("/api/candidates?limit=2&offset=1", headers=admin_headers)
    assert candidates.status_code == 200
    candidate_data = candidates.get_json()["data"]
    assert len(candidate_data["items"]) == 2
    assert candidate_data["total"] >= 4
    assert candidate_data["limit"] == 2
    assert candidate_data["offset"] == 1
    assert candidate_data["has_more"] is True
    assert sum(item["count"] for item in candidate_data["experience_stats"]) == candidate_data["total"]

    jobs = client.get("/api/jobs?limit=1", headers=admin_headers)
    assert jobs.status_code == 200
    job_data = jobs.get_json()["data"]
    assert len(job_data["items"]) == 1
    assert job_data["total"] >= 3
    assert job_data["limit"] == 1
    assert job_data["offset"] == 0

    users = client.get("/api/users?limit=1", headers=admin_headers)
    assert users.status_code == 200
    user_data = users.get_json()["data"]
    assert len(user_data["items"]) == 1
    assert user_data["total"] >= 3

    audits = client.get("/api/audit/logs?limit=1", headers=admin_headers)
    assert audits.status_code == 200
    audit_data = audits.get_json()["data"]
    assert len(audit_data["items"]) == 1
    assert audit_data["total"] >= 1


def test_candidate_resume_export(client, admin_headers):
    response = client.get("/api/candidates/1/resume.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    body = response.data.decode("utf-8-sig")
    assert "候选人简历" in body
    assert "技能标签" in body
    assert "简历原文" in body
    log = AuditLog.query.filter_by(action="export", target_type="candidate", target_id=1).order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.details["kind"] == "resume_txt"


def test_candidate_detail_view_and_csv_export_are_audited(client, admin_headers):
    detail = client.get("/api/candidates/1", headers=admin_headers)
    exported = client.get("/api/exports/candidates.csv", headers=admin_headers)

    assert detail.status_code == 200
    assert exported.status_code == 200
    view_log = AuditLog.query.filter_by(action="view", target_type="candidate", target_id=1).order_by(AuditLog.id.desc()).first()
    export_log = AuditLog.query.filter_by(action="export", target_type="candidates", target_name="candidates.csv").order_by(AuditLog.id.desc()).first()
    assert view_log is not None
    assert view_log.details["scope"] == "detail"
    assert export_log is not None
    assert export_log.details["kind"] == "csv"
    assert export_log.details["row_count"] >= 1


def test_sensitive_candidate_and_export_permissions(client, admin_headers, recruiter_headers):
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "interviewer_only", "name": "只面试", "role": "interviewer", "password": "Pass1234"},
    )
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": "interviewer_only", "password": "Pass1234"})
    interviewer_headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

    recruiter_candidates = client.get("/api/candidates", headers=recruiter_headers)
    assert recruiter_candidates.status_code == 200
    recruiter_candidate_ids = {item["id"] for item in recruiter_candidates.get_json()["data"]["items"]}
    assert 3 not in recruiter_candidate_ids
    assert client.get("/api/candidates/3", headers=recruiter_headers).status_code == 403
    assert client.patch("/api/candidates/3", headers=recruiter_headers, json={"city": "上海"}).status_code == 403
    assert client.put("/api/candidates/3/tags", headers=recruiter_headers, json={"tags": [{"tag": "Python", "score": 3}]}).status_code == 403
    assert client.delete("/api/candidates/3", headers=recruiter_headers).status_code == 403
    assert client.get("/api/candidates/3/resume.txt", headers=recruiter_headers).status_code == 403
    match_preview = client.get("/api/jobs/1/match-preview", headers=recruiter_headers).get_json()["data"]["items"]
    assert 3 not in {item["candidate_id"] for item in match_preview}
    assert client.get("/api/candidates/1", headers=interviewer_headers).status_code == 403
    assert client.get("/api/candidates/1/resume.txt", headers=interviewer_headers).status_code == 403

    recruiter_export = client.get("/api/exports/candidates.csv", headers=recruiter_headers)
    admin_export = client.get("/api/exports/candidates.csv", headers=admin_headers)
    assert recruiter_export.status_code == 403
    assert admin_export.status_code == 200

def test_employee_salary_is_masked_for_recruiter(client, admin_headers, recruiter_headers):
    created = client.post(
        "/api/employees/from-candidate",
        headers=admin_headers,
        json={"candidate_id": 1, "current_job_id": 1, "salary_monthly_k": 18, "salary_months": 13},
    )
    assert created.status_code == 200

    admin_list = client.get("/api/employees", headers=admin_headers).get_json()["data"]
    recruiter_list = client.get("/api/employees", headers=recruiter_headers).get_json()["data"]

    assert admin_list["overview"]["with_compensation"] == 1
    assert admin_list["items"][0]["compensation"]["salary_monthly_k"] == 18
    assert recruiter_list["overview"]["with_compensation"] == 1
    assert recruiter_list["items"][0]["compensation"] is None
    assert recruiter_list["items"][0]["salary_hidden"] is True
    assert client.get("/api/exports/employees.csv", headers=recruiter_headers).status_code == 403


def test_sensitive_module_permissions_for_interviewer(client, admin_headers, recruiter_headers):
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={"username": "module_interviewer", "name": "模块面试官", "role": "interviewer", "password": "Pass1234"},
    )
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"username": "module_interviewer", "password": "Pass1234"})
    interviewer_headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

    protected_gets = [
        "/api/jobs",
        "/api/jobs/1",
        "/api/jobs/1/match-preview",
        "/api/offers",
        "/api/offers/1",
        "/api/offers/1/letter.txt",
        "/api/bi/overview",
        "/api/system/llm/usage",
        "/api/pipeline/overview",
        "/api/boss/status",
        "/api/boss/extension.zip",
        "/api/boss/candidates/inbox",
        "/api/boss/jobs",
        "/api/boss/jobs/1/recommendations",
        "/api/agent/tools",
    ]
    for path in protected_gets:
        response = client.get(path, headers=interviewer_headers)
        assert response.status_code == 403, path

    match = client.post("/api/jobs/1/match", headers=interviewer_headers)
    assert match.status_code == 403

    chat = client.post("/api/agent/chat", headers=interviewer_headers, json={"message": "现在人才库有多少人"})
    assert chat.status_code == 403

    assert client.get("/api/bi/overview", headers=recruiter_headers).status_code == 200
    assert client.get("/api/boss/status", headers=recruiter_headers).status_code == 200
    assert client.get("/api/agent/tools", headers=recruiter_headers).status_code == 200

def test_accounting_job_matches_accounting_candidate_first(client, admin_headers):
    jobs = client.get("/api/jobs", headers=admin_headers).get_json()["data"]["items"]
    accounting_job = next(job for job in jobs if job["title"] == "财务会计主管")

    response = client.post(f"/api/jobs/{accounting_job['id']}/match", headers=admin_headers)

    assert response.status_code == 200
    matches = response.get_json()["data"]["items"]
    assert matches[0]["candidate"]["title"] == "总账会计"
    assert matches[0]["score"] >= 90
    assert len(matches) < Candidate.query.count()
    assert not any(item["candidate"]["title"] == "Python 后端工程师" for item in matches)
    assert all("rule_score" in item["reason"] for item in matches)
    assert all(item["reason"]["hits"] for item in matches)


def test_job_match_can_run_as_background_task_and_list_persisted_matches(client, admin_headers):
    jobs = client.get("/api/jobs", headers=admin_headers).get_json()["data"]["items"]
    accounting_job = next(job for job in jobs if job["title"] == "财务会计主管")

    queued = client.post(f"/api/jobs/{accounting_job['id']}/match?async=1", headers=admin_headers)

    assert queued.status_code == 200
    task = queued.get_json()["data"]["task"]
    assert task["task_type"] == "job_match"
    assert task["status"] == "queued"
    assert task["payload"]["job_id"] == accounting_job["id"]

    run_task = run_next_task()
    assert run_task.id == task["id"]
    assert run_task.status == "succeeded"
    assert run_task.result["job_id"] == accounting_job["id"]
    assert 0 < run_task.result["count"] < Candidate.query.count()

    listed = client.get(f"/api/jobs/{accounting_job['id']}/matches", headers=admin_headers)
    assert listed.status_code == 200
    data = listed.get_json()["data"]
    assert data["job"]["id"] == accounting_job["id"]
    assert data["items"][0]["candidate"]["title"] == "总账会计"
    assert data["items"][0]["score"] >= data["items"][-1]["score"]


def test_matching_recalibration_task_reparses_and_rematches(client, admin_headers):
    queued = client.post(
        "/api/matching/recalibrate",
        headers=admin_headers,
        json={"candidate_limit": 3, "job_limit": 2, "reparse_candidates": True, "rematch_jobs": True},
    )

    assert queued.status_code == 200
    task = queued.get_json()["data"]["task"]
    assert task["task_type"] == "matching_recalibration"
    assert task["payload"]["candidate_limit"] == 3

    run_task = run_next_task()
    assert run_task.id == task["id"]
    assert run_task.status == "succeeded"
    assert run_task.result["reparsed_count"] <= 3
    assert run_task.result["rematched_count"] <= 2
    assert Match.query.count() > 0


def test_job_match_combines_rule_score_and_ai_review(client, admin_headers, app, monkeypatch):
    jobs = client.get("/api/jobs", headers=admin_headers).get_json()["data"]["items"]
    accounting_job = next(job for job in jobs if job["title"] == "财务会计主管")

    app.config["LLM_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    calls = []

    def fake_chat_json(messages, **kwargs):
        calls.append(messages)
        assert "完整简历" in messages[-1]["content"]
        return {
            "score": 80,
            "recommendation": "推荐",
            "summary": "AI 已阅读 JD 和完整简历后给出综合判断。",
            "strengths": ["岗位经验接近"],
            "risks": ["需要复核业务深度"],
            "interview_focus": ["项目职责"],
            "evidence": ["简历中有相关经历"],
        }

    monkeypatch.setattr("app.job_service.chat_json", fake_chat_json)

    response = client.post(f"/api/jobs/{accounting_job['id']}/match", headers=admin_headers)

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["reason"]["hits"] for item in items)
    assert len(calls) == min(3, len(items))
    if len(items) > 8:
        pending = [item for item in items if item["reason"]["ai_review"]["source"] == "rule_pending"]
        assert pending
        assert pending[0]["score"] == round(pending[0]["reason"]["rule_score"] * 0.35)
    assert all(item["reason"]["ai_review"]["source"] == "deepseek" for item in items[: min(5, len(items))])
    first = items[0]
    reason = first["reason"]
    assert reason["ai_score"] == 80
    assert reason["ai_review"]["source"] == "deepseek"
    assert reason["ai_review"]["recommendation"] == "推荐"
    assert reason["score_formula"] == "final_score=round(rule_score*35% + ai_score*65%); no-hit candidates hidden before AI review"
    assert first["score"] == round(reason["rule_score"] * 0.35 + 80 * 0.65)
    assert reason["score_breakdown"]["rule_score"] == reason["rule_score"]
    assert reason["score_breakdown"]["ai_score"] == 80
    assert reason["score_breakdown"]["final_score"] == first["score"]
    assert any(item["type"] == "ai_summary" for item in reason["evidence_chain"])
    assert any(item["type"] == "rule_hit" and item["evidence"] for item in reason["evidence_chain"])


def test_job_match_reports_deepseek_balance_error_once(client, admin_headers, app, monkeypatch):
    jobs = client.get("/api/jobs", headers=admin_headers).get_json()["data"]["items"]
    accounting_job = next(job for job in jobs if job["title"] == "财务会计主管")

    app.config["LLM_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    calls = []

    def fake_chat_json(messages, **kwargs):
        calls.append(messages)
        raise LLMError('LLM HTTP 402: {"message":"Insufficient Balance"}')

    monkeypatch.setattr("app.job_service.chat_json", fake_chat_json)

    response = client.post(f"/api/jobs/{accounting_job['id']}/match", headers=admin_headers)

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert len(calls) == 1
    failed = [item for item in items if item["reason"]["ai_review"]["source"] == "failed"]
    unavailable = [item for item in items if item["reason"]["ai_review"]["source"] == "ai_unavailable"]
    assert len(failed) == 1
    assert "DeepSeek 余额不足" in failed[0]["reason"]["ai_review"]["summary"]
    if unavailable:
        assert "DeepSeek 余额不足" in unavailable[0]["reason"]["ai_review"]["summary"]
    assert failed[0]["score"] == failed[0]["reason"]["rule_score"]


def test_job_creation_structures_jd_without_manual_skill_tags(client, admin_headers):
    response = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={
            "title": "React 前端工程师",
            "city": "南京",
            "department": "研发部",
            "job_code": "FE-001",
            "jd_text": "要求 3 年以上经验，熟练 React、TypeScript、JavaScript，本科优先，薪资 15K-25K。",
        },
    )

    assert response.status_code == 200
    job = response.get_json()["data"]
    assert job["jd_structured"]["years_required"] == 3
    assert job["jd_structured"]["salary_range"] == {"min_k": 15.0, "max_k": 25.0}
    assert {"React", "TypeScript", "JavaScript"} <= {skill["tag"] for skill in job["jd_structured"]["skills"]}


def test_job_creation_rejects_missing_text_without_500(client, admin_headers):
    response = client.post("/api/jobs", headers=admin_headers, json={"title": 123, "jd_text": None})

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


def test_job_ai_generate_and_calibrate_fallback(client, admin_headers):
    generated = client.post("/api/jobs/ai-generate", headers=admin_headers, json={"title": "Java 后端工程师", "city": "上海"})
    assert generated.status_code == 200
    generated_data = generated.get_json()["data"]
    assert "Java 后端工程师" in generated_data["jd_text"]
    assert generated_data["structured"]["skill_tags_raw"]

    calibrated = client.post(
        "/api/jobs/ai-calibrate",
        headers=admin_headers,
        json={"title": "数据分析师", "jd_text": "需要 SQL、Python、数据分析、报表能力。", "skill_tags_raw": ""},
    )
    assert calibrated.status_code == 200
    calibrated_data = calibrated.get_json()["data"]
    assert {"SQL", "Python"} <= {skill["tag"] for skill in calibrated_data["structured"]["skills"]}


def test_job_ai_generate_records_llm_context(client, admin_headers, app, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            body = {
                "choices": [{"message": {"content": json.dumps({"jd_text": "岗位职责：负责 Java 开发。任职要求：Java、Spring Boot。", "skill_tags_raw": "Java 5|Spring Boot 4"})}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            }
            return json.dumps(body).encode("utf-8")

    app.config["LLM_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "test-key"
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())

    response = client.post("/api/jobs/ai-generate", headers=admin_headers, json={"title": "Java 后端工程师"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["source"] == "deepseek"
    assert "Spring Boot" in data["skill_tags_raw"]
    usage = LLMUsage.query.order_by(LLMUsage.id.desc()).first()
    assert usage is not None
    assert usage.source == "job"
    assert usage.tool_name == "ai_generate_jd"
    assert usage.api_path == "/api/jobs/ai-generate"


def test_job_update_rejects_blank_required_fields(client, admin_headers):
    response = client.patch("/api/jobs/1", headers=admin_headers, json={"title": "   "})

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


def test_skill_tags_endpoint_lists_label_library(client, admin_headers):
    response = client.get("/api/tags", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "财务/会计" in data["categories"]
    assert any(item["tag"] == "Python" for item in data["items"])


def test_match_preview_does_not_persist_matches(client, admin_headers):
    before = Match.query.filter_by(job_id=1).count()
    response = client.get("/api/jobs/1/match-preview?limit=2", headers=admin_headers)
    after = Match.query.filter_by(job_id=1).count()

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert len(items) <= 2
    assert all("rule_score" in item["reason"] for item in items)
    assert all(item["reason"]["final_score"] == item["reason"]["rule_score"] for item in items)
    assert after == before


def test_closed_job_cannot_run_persisted_match(client, admin_headers):
    close_response = client.post("/api/jobs/1/close", headers=admin_headers)
    assert close_response.status_code == 200
    assert close_response.get_json()["data"]["status"] == "closed"

    match_response = client.post("/api/jobs/1/match", headers=admin_headers)
    assert match_response.status_code == 409
    assert match_response.get_json()["code"] == "JOB_CLOSED"

    restore_response = client.post("/api/jobs/1/restore", headers=admin_headers)
    assert restore_response.status_code == 200
    assert restore_response.get_json()["data"]["status"] == "active"


def test_batch_pipeline_adds_candidates_and_skips_duplicates(client, admin_headers):
    response = client.post(
        "/api/jobs/1/batch-pipeline",
        headers=admin_headers,
        json={"candidate_ids": [1, 2], "stage": "pending", "note": "测试加入流程"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["created"]) == 1
    assert data["created"][0]["candidate_id"] == 2
    assert data["skipped"] == [{"candidate_id": 1, "stage": "business_review"}]

    duplicate = client.post(
        "/api/jobs/1/batch-pipeline",
        headers=admin_headers,
        json={"candidate_ids": [2], "stage": "pending"},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["data"]["created"] == []
    assert duplicate.get_json()["data"]["skipped"] == [{"candidate_id": 2, "stage": "pending"}]


def test_delete_employee_clears_recommendations_and_compensation(client, admin_headers):
    employee = EmployeeProfile(owner_hr_id=1, employee_no="DEL-EMP", name="删除员工测试", current_title="Java", raw_text="Java")
    db.session.add(employee)
    db.session.flush()
    db.session.add(EmployeeCompensation(employee_id=employee.id, salary_monthly_k=20, salary_months=13))
    db.session.add(EmployeeRecommendation(employee_id=employee.id, recommendation_type="transfer", score=80, reason_json={}))
    db.session.commit()

    response = client.delete(f"/api/employees/{employee.id}", headers=admin_headers)

    assert response.status_code == 200
    assert db.session.get(EmployeeProfile, employee.id) is None
    assert EmployeeRecommendation.query.filter_by(employee_id=employee.id).count() == 0
    assert EmployeeCompensation.query.filter_by(employee_id=employee.id).count() == 0


def test_delete_interview_clears_speech_logs(client, admin_headers):
    assignment = InterviewAssignment(
        candidate_id=1,
        job_id=1,
        interviewer_id=2,
        round="interview_first",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        location="站内",
        status="scheduled",
        created_by=1,
    )
    db.session.add(assignment)
    db.session.flush()
    db.session.add(InterviewSpeechLog(assignment_id=assignment.id, operation="asr", provider="e2e", status="succeeded", transcript="测试"))
    db.session.commit()

    response = client.delete(f"/api/interview/assignments/{assignment.id}", headers=admin_headers)

    assert response.status_code == 200
    assert db.session.get(InterviewAssignment, assignment.id) is None
    assert InterviewSpeechLog.query.filter_by(assignment_id=assignment.id).count() == 0


def test_delete_candidate_and_job_clear_new_references(client, admin_headers):
    target_candidate = Candidate(owner_hr_id=1, upload_batch_id="delete-candidate-ref", name_masked="删除候选人引用", title="Java", raw_text="Java", resume_json={}, source="upload")
    employee = EmployeeProfile(owner_hr_id=1, employee_no="DEL-REC", name="推荐来源员工", current_title="Java", raw_text="Java")
    job = Job(owner_hr_id=1, title="删除岗位引用", city="长沙", department="研发", job_code="DEL-JOB", jd_text="Java", jd_structured={}, status="active")
    db.session.add_all([target_candidate, employee, job])
    db.session.flush()
    db.session.add(EmployeeRecommendation(employee_id=employee.id, recommendation_type="replacement", candidate_id=target_candidate.id, score=88, reason_json={}))
    assignment = InterviewAssignment(candidate_id=1, job_id=job.id, interviewer_id=2, round="interview_first", scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), status="scheduled", created_by=1)
    db.session.add(assignment)
    db.session.flush()
    assignment_id = assignment.id
    db.session.add(InterviewSpeechLog(assignment_id=assignment.id, operation="tts", provider="e2e", status="succeeded", text="测试"))
    db.session.commit()

    candidate_response = client.delete(f"/api/candidates/{target_candidate.id}", headers=admin_headers)
    job_response = client.delete(f"/api/jobs/{job.id}", headers=admin_headers)

    assert candidate_response.status_code == 200
    assert job_response.status_code == 200
    assert db.session.get(Candidate, target_candidate.id) is None
    assert db.session.get(Job, job.id) is None
    assert EmployeeRecommendation.query.filter_by(candidate_id=target_candidate.id).count() == 0
    assert InterviewSpeechLog.query.filter_by(assignment_id=assignment_id).count() == 0


def test_pipeline_history_returns_append_only_events(client, admin_headers):
    client.post(
        "/api/jobs/1/batch-pipeline",
        headers=admin_headers,
        json={"candidate_ids": [2], "stage": "pending"},
    )
    client.post(
        "/api/pipeline/move",
        headers=admin_headers,
        json={"candidate_id": 2, "job_id": 1, "stage": "ai_screen", "note": "进入 AI 初筛"},
    )

    response = client.get("/api/pipeline/1/history/2", headers=admin_headers)

    assert response.status_code == 200
    stages = [item["stage"] for item in response.get_json()["data"]["items"]]
    assert stages == ["pending", "ai_screen"]

    overview = client.get("/api/pipeline/overview", headers=admin_headers)
    assert overview.status_code == 200
    assert overview.get_json()["data"]["total"] >= 1


def test_global_pipeline_board_can_show_all_jobs_and_filter_by_job(client, admin_headers):
    job = Job(owner_hr_id=1, title="全局看板测试岗位", city="长沙", department="研发部", job_code="PIPELINE-GLOBAL", jd_text="测试 JD", jd_structured={}, status="active")
    candidate = Candidate(owner_hr_id=1, upload_batch_id="pipeline-global", name_masked="全局看板候选人", title="Java", raw_text="Java 候选人", resume_json={}, source="upload")
    db.session.add_all([job, candidate])
    db.session.flush()
    db.session.add(PipelineStage(candidate_id=candidate.id, job_id=job.id, stage="interview_first", updated_by=1, note="全局看板测试"))
    db.session.commit()

    global_response = client.get("/api/pipeline/board", headers=admin_headers)

    assert global_response.status_code == 200
    global_data = global_response.get_json()["data"]
    assert global_data["scope"] == "all"
    assert global_data["total"] >= 1
    assert any(item["job"]["title"] == "全局看板测试岗位" for item in global_data["columns"]["interview_first"])

    filtered_response = client.get(f"/api/pipeline/board?job_id={job.id}", headers=admin_headers)

    assert filtered_response.status_code == 200
    filtered_data = filtered_response.get_json()["data"]
    assert filtered_data["scope"] == "job"
    assert filtered_data["job_id"] == job.id
    assert filtered_data["columns"]["interview_first"][0]["candidate"]["name_masked"] == "全局看板候选人"


def test_pipeline_move_skips_duplicate_latest_stage(client, admin_headers):
    first = client.post(
        "/api/pipeline/move",
        headers=admin_headers,
        json={"candidate_id": 2, "job_id": 1, "stage": "ai_screen", "note": "进入 AI 初筛"},
    )
    second = client.post(
        "/api/pipeline/move",
        headers=admin_headers,
        json={"candidate_id": 2, "job_id": 1, "stage": "ai_screen", "note": "重复点击"},
    )
    history = client.get("/api/pipeline/1/history/2", headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert [item["stage"] for item in history.get_json()["data"]["items"]].count("ai_screen") == 1


def test_interview_assignment_pushes_pipeline_stage(client, admin_headers):
    response = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={
            "candidate_id": 1,
            "job_id": 1,
            "interviewer_id": 2,
            "round": "interview_first",
            "scheduled_at": "2026-07-03T10:00:00",
            "location": "腾讯会议",
            "note": "技术一面",
        },
    )

    assert response.status_code == 200
    assignment = response.get_json()["data"]
    assert assignment["status"] == "scheduled"
    assert assignment["interviewer"]["id"] == 2
    assert len(assignment["ai_plan"]["questions"]) >= 3

    history = client.get("/api/pipeline/1/history/1", headers=admin_headers)
    stages = [item["stage"] for item in history.get_json()["data"]["items"]]
    assert "interview_first" in stages

    board = client.get("/api/pipeline/board?job_id=1", headers=admin_headers).get_json()["data"]
    assert board["source_counts"]["interview"] >= 1


def test_interview_round_update_cancel_and_delete_sync_pipeline(client, admin_headers):
    created = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={
            "candidate_id": 1,
            "job_id": 1,
            "interviewer_id": 2,
            "round": "interview_first",
            "scheduled_at": "2026-07-03T10:00:00",
        },
    ).get_json()["data"]

    updated = client.patch(
        f"/api/interview/assignments/{created['id']}",
        headers=admin_headers,
        json={"round": "interview_final"},
    )

    assert updated.status_code == 200
    history = client.get("/api/pipeline/1/history/1", headers=admin_headers).get_json()["data"]["items"]
    assert history[-1]["stage"] == "interview_final"

    cancelled = client.post(f"/api/interview/assignments/{created['id']}/cancel", headers=admin_headers)

    assert cancelled.status_code == 200
    board = client.get("/api/pipeline/board?job_id=1", headers=admin_headers).get_json()["data"]
    latest = [item for rows in board["columns"].values() for item in rows if item["candidate_id"] == 1 and item["job_id"] == 1][0]
    assert latest["stage"] == "interview_second"
    assert latest["source_label"] == "面试回退"

    another = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={
            "candidate_id": 2,
            "job_id": 1,
            "interviewer_id": 2,
            "round": "interview_second",
            "scheduled_at": "2026-07-05T10:00:00",
        },
    ).get_json()["data"]
    deleted = client.delete(f"/api/interview/assignments/{another['id']}", headers=admin_headers)

    assert deleted.status_code == 200
    latest_after_delete = PipelineStage.query.filter_by(job_id=1, candidate_id=2).order_by(PipelineStage.ts.desc()).first()
    assert latest_after_delete.stage == "interview_first"


def test_interview_ai_plan_generates_questions(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00", "location": "腾讯会议 123-456-789"},
    ).get_json()["data"]

    response = client.post(f"/api/interview/assignments/{assignment['id']}/ai-plan", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["avatar"]["name"] == "AI 面试官"
    assert data["meeting"]["provider"] == "腾讯会议"
    assert len(data["questions"]) >= 3


def test_public_interview_room_and_turn_work_without_login(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    link = client.post(f"/api/interview/assignments/{assignment['id']}/room-link", headers=admin_headers).get_json()["data"]

    room = client.get(f"/api/public/interview-room/{link['token']}")
    turn = client.post(f"/api/public/interview-room/{link['token']}/turn", json={"question": "请介绍项目", "answer": "我负责核心开发并上线"})
    complete = client.post(
        f"/api/public/interview-room/{link['token']}/complete",
        json={"answers": ["我负责核心开发并上线"], "messages": [{"role": "ai", "text": "请介绍项目"}, {"role": "candidate", "text": "我负责核心开发并上线"}]},
    )

    assert room.status_code == 200
    assert room.get_json()["data"]["assignment"]["id"] == assignment["id"]
    assert turn.status_code == 200
    assert turn.get_json()["data"]["reply"]
    assert complete.status_code == 200
    assert complete.get_json()["data"]["assignment"]["status"] == "completed"
    assert "维度评分：" in complete.get_json()["data"]["feedback"]["comment"]
    assert "岗位匹配：" in complete.get_json()["data"]["feedback"]["comment"]
    reopened = client.get(f"/api/public/interview-room/{link['token']}")
    blocked_turn = client.post(f"/api/public/interview-room/{link['token']}/turn", json={"question": "继续问"})
    assert reopened.status_code == 200
    assert reopened.get_json()["data"]["assignment"]["status"] == "completed"
    assert blocked_turn.status_code == 404
    assert InterviewFeedback.query.filter_by(assignment_id=assignment["id"]).count() == 1


def test_public_interview_speech_asr_tts_and_logs(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    link = client.post(f"/api/interview/assignments/{assignment['id']}/room-link", headers=admin_headers).get_json()["data"]

    status = client.get(f"/api/public/interview-room/{link['token']}/speech/status")
    assert status.status_code == 200
    speech = status.get_json()["data"]["speech"]
    assert speech["asr"]["enabled"] is True
    assert speech["tts"]["browser_fallback"] is True

    asr = client.post(
        f"/api/public/interview-room/{link['token']}/speech/asr",
        json={"transcript": "我负责 Java 后端服务开发", "source": "browser_recognition", "duration_ms": 1200},
    )
    assert asr.status_code == 200
    assert asr.get_json()["data"]["transcript"] == "我负责 Java 后端服务开发"

    tts = client.post(f"/api/public/interview-room/{link['token']}/speech/tts", json={"text": "请介绍一个项目", "voice": "zh-CN"})
    assert tts.status_code == 200
    assert tts.get_json()["data"]["browser_fallback"] is True

    logs = client.get(f"/api/interview/speech/logs?assignment_id={assignment['id']}", headers=admin_headers)
    assert logs.status_code == 200
    items = logs.get_json()["data"]["items"]
    assert {item["operation"] for item in items} == {"asr", "tts"}
    assert InterviewSpeechLog.query.filter_by(assignment_id=assignment["id"]).count() == 2


def test_public_interview_room_token_uses_configured_expiry(client, admin_headers, app):
    app.config["INTERVIEW_ROOM_TOKEN_HOURS"] = 2
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]

    link = client.post(f"/api/interview/assignments/{assignment['id']}/room-link", headers=admin_headers).get_json()["data"]
    payload = jwt.decode(link["token"], app.config["JWT_SECRET"], algorithms=["HS256"])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)

    assert 7100 <= (expires_at - issued_at).total_seconds() <= 7300


def test_public_interview_room_rate_limit_and_payload_limit(client, admin_headers, app):
    app.config["PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE"] = 2
    app.config["PUBLIC_INTERVIEW_MAX_ANSWER_CHARS"] = 200
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    link = client.post(f"/api/interview/assignments/{assignment['id']}/room-link", headers=admin_headers).get_json()["data"]

    assert client.get(f"/api/public/interview-room/{link['token']}").status_code == 200
    assert client.get(f"/api/public/interview-room/{link['token']}").status_code == 200
    limited = client.get(f"/api/public/interview-room/{link['token']}")
    assert limited.status_code == 429
    assert limited.get_json()["code"] == "PUBLIC_INTERVIEW_RATE_LIMITED"

    app.config["PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE"] = 100
    too_large = client.post(
        f"/api/public/interview-room/{link['token']}/turn",
        json={"question": "请介绍项目", "answer": "x" * 1000},
    )
    assert too_large.status_code == 413
    assert too_large.get_json()["code"] == "PUBLIC_INTERVIEW_PAYLOAD_TOO_LARGE"


def test_interview_report_export(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    client.post(
        "/api/interview/feedback",
        headers=admin_headers,
        json={"assignment_id": assignment["id"], "rating": 4, "decision": "pass", "strengths": "基础扎实", "risks": "需要复核", "comment": "AI评分：82/100\n面试记录"},
    )

    response = client.get(f"/api/interview/assignments/{assignment['id']}/report.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    body = response.data.decode("utf-8-sig")
    assert "AI 面试报告" in body
    assert assignment["candidate"]["name_masked"] in body
    assert assignment["job"]["title"] in body
    assert "AI评分：82/100" in body
    assert "基础扎实" in body
    log = AuditLog.query.filter_by(action="export", target_type="interview", target_id=assignment["id"]).order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.details["kind"] == "interview_report"


def test_interview_feedback_completes_assignment_and_moves_pipeline(client, admin_headers):
    assignment_response = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={
            "candidate_id": 1,
            "job_id": 1,
            "interviewer_id": 2,
            "round": "interview_first",
            "scheduled_at": "2026-07-03T10:00:00",
        },
    )
    assignment_id = assignment_response.get_json()["data"]["id"]

    response = client.post(
        "/api/interview/feedback",
        headers=admin_headers,
        json={
            "assignment_id": assignment_id,
            "rating": 4,
            "decision": "pass",
            "strengths": "基础扎实",
            "risks": "需要业务熟悉",
            "comment": "建议进入二面",
        },
    )

    assert response.status_code == 200
    feedback = response.get_json()["data"]
    assert feedback["rating"] == 4
    assert feedback["decision"] == "pass"

    assignment = db.session.get(InterviewAssignment, assignment_id)
    assert assignment.status == "completed"
    assert InterviewFeedback.query.filter_by(assignment_id=assignment_id).count() == 1
    history = client.get("/api/pipeline/1/history/1", headers=admin_headers)
    stages = [item["stage"] for item in history.get_json()["data"]["items"]]
    assert "interview_second" in stages


def test_interview_feedback_rejects_closed_assignment(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    client.post(f"/api/interview/assignments/{assignment['id']}/cancel", headers=admin_headers)

    cancelled = client.post("/api/interview/feedback", headers=admin_headers, json={"assignment_id": assignment["id"], "rating": 4, "decision": "pass"})
    assert cancelled.status_code == 409
    assert cancelled.get_json()["code"] == "INTERVIEW_CLOSED"

    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    first = client.post("/api/interview/feedback", headers=admin_headers, json={"assignment_id": assignment["id"], "rating": 4, "decision": "pass"})
    second = client.post("/api/interview/feedback", headers=admin_headers, json={"assignment_id": assignment["id"], "rating": 5, "decision": "pass"})
    assert first.status_code == 200
    assert second.status_code == 409
    assert InterviewFeedback.query.filter_by(assignment_id=assignment["id"]).count() == 1


def test_interview_assignment_can_be_updated_cancelled_and_deleted(client, admin_headers, app):
    created = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]

    updated = client.patch(
        f"/api/interview/assignments/{created['id']}",
        headers=admin_headers,
        json={"scheduled_at": "2026-07-04T11:30:00", "location": "现场"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["location"] == "现场"

    detail = client.get(f"/api/interview/assignments/{created['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["id"] == created["id"]

    cancelled = client.post(f"/api/interview/assignments/{created['id']}/cancel", headers=admin_headers)
    assert cancelled.status_code == 200
    assert cancelled.get_json()["data"]["status"] == "cancelled"
    repeated_cancel = client.post(f"/api/interview/assignments/{created['id']}/cancel", headers=admin_headers)
    assert repeated_cancel.status_code == 409
    closed_update = client.patch(f"/api/interview/assignments/{created['id']}", headers=admin_headers, json={"location": "新会议"})
    closed_link = client.post(f"/api/interview/assignments/{created['id']}/room-link", headers=admin_headers)
    assert closed_update.status_code == 409
    assert closed_link.status_code == 409

    deleted = client.delete(f"/api/interview/assignments/{created['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    with app.app_context():
        assert db.session.get(InterviewAssignment, created["id"]) is None


def test_completed_interview_cannot_be_cancelled(client, admin_headers):
    assignment = client.post(
        "/api/interview/assignments",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"},
    ).get_json()["data"]
    client.post("/api/interview/feedback", headers=admin_headers, json={"assignment_id": assignment["id"], "rating": 4, "decision": "pass"})

    response = client.post(f"/api/interview/assignments/{assignment['id']}/cancel", headers=admin_headers)
    update = client.patch(f"/api/interview/assignments/{assignment['id']}", headers=admin_headers, json={"location": "新会议"})
    link = client.post(f"/api/interview/assignments/{assignment['id']}/room-link", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "INTERVIEW_CLOSED"
    assert update.status_code == 409
    assert link.status_code == 409


def test_offer_create_and_status_updates_pipeline(client, admin_headers):
    response = client.post(
        "/api/offers",
        headers=admin_headers,
        json={
            "candidate_id": 1,
            "job_id": 1,
            "salary_min_k": 18,
            "salary_max_k": 25,
            "salary_months": 13,
            "city": "上海",
            "start_date": "2026-08-01",
            "status": "sent",
            "note": "测试 Offer",
        },
    )

    assert response.status_code == 200
    offer = response.get_json()["data"]
    assert offer["status"] == "sent"
    assert offer["salary_max_k"] == 25.0

    update = client.patch(f"/api/offers/{offer['id']}", headers=admin_headers, json={"status": "accepted"})
    assert update.status_code == 200
    assert update.get_json()["data"]["status"] == "accepted"

    detail = client.get(f"/api/offers/{offer['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["id"] == offer["id"]

    history = client.get("/api/pipeline/1/history/1", headers=admin_headers)
    stages = [item["stage"] for item in history.get_json()["data"]["items"]]
    assert "offer" in stages
    assert "onboarded" in stages


def test_offer_letter_export(client, admin_headers):
    offer = client.post(
        "/api/offers",
        headers=admin_headers,
        json={
            "candidate_id": 1,
            "job_id": 1,
            "salary_min_k": 18,
            "salary_max_k": 25,
            "salary_months": 13,
            "city": "上海",
            "start_date": "2026-08-01",
            "status": "sent",
            "note": "测试 Offer",
        },
    ).get_json()["data"]

    response = client.get(f"/api/offers/{offer['id']}/letter.txt", headers=admin_headers)

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    body = response.data.decode("utf-8-sig")
    assert "Offer 确认函" in body
    assert offer["candidate"]["name_masked"] in body
    assert offer["job"]["title"] in body
    assert "18-25K × 13 薪" in body


def test_offer_rejects_invalid_salary_terms(client, admin_headers):
    bad_range = client.post(
        "/api/offers",
        headers=admin_headers,
        json={"candidate_id": 1, "job_id": 1, "salary_min_k": 30, "salary_max_k": 20},
    )
    assert bad_range.status_code == 400
    assert "最低月薪" in bad_range.get_json()["error"]

    offer = client.post("/api/offers", headers=admin_headers, json={"candidate_id": 1, "job_id": 1}).get_json()["data"]
    bad_months = client.patch(f"/api/offers/{offer['id']}", headers=admin_headers, json={"salary_months": 0})
    assert bad_months.status_code == 400
    assert "薪资月数" in bad_months.get_json()["error"]


def test_offer_can_be_deleted(client, admin_headers, app):
    offer = client.post("/api/offers", headers=admin_headers, json={"candidate_id": 1, "job_id": 1}).get_json()["data"]

    response = client.delete(f"/api/offers/{offer['id']}", headers=admin_headers)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(OfferRecord, offer["id"]) is None


def test_delete_job_cascades_related_records(client, admin_headers, app):
    job = client.post(
        "/api/jobs",
        headers=admin_headers,
        json={"title": "临时岗位", "city": "上海", "department": "测试", "jd_text": "需要 Excel。", "skill_tags_raw": "Excel 3"},
    ).get_json()["data"]
    client.post(f"/api/jobs/{job['id']}/match", headers=admin_headers)
    client.post(f"/api/jobs/{job['id']}/batch-pipeline", headers=admin_headers, json={"candidate_id": 1})
    client.post("/api/interview/assignments", headers=admin_headers, json={"candidate_id": 1, "job_id": job["id"], "interviewer_id": 2, "round": "interview_first", "scheduled_at": "2026-07-03T10:00:00"})
    client.post("/api/offers", headers=admin_headers, json={"candidate_id": 1, "job_id": job["id"]})
    client.post("/api/boss/messages/draft", headers=admin_headers, json={"candidate_id": 1, "job_id": job["id"]})

    response = client.delete(f"/api/jobs/{job['id']}", headers=admin_headers)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Job, job["id"]) is None
        assert Match.query.filter_by(job_id=job["id"]).count() == 0
        assert PipelineStage.query.filter_by(job_id=job["id"]).count() == 0
        assert InterviewAssignment.query.filter_by(job_id=job["id"]).count() == 0
        assert OfferRecord.query.filter_by(job_id=job["id"]).count() == 0
        assert BossDraft.query.filter_by(job_id=job["id"]).count() == 0


def test_agent_uses_readonly_offer_and_match_tools(client, admin_headers):
    client.post("/api/offers", headers=admin_headers, json={"candidate_id": 1, "job_id": 1, "status": "sent"})

    offer_response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "Offer 状态怎么样？"})
    assert offer_response.status_code == 200
    offer_data = offer_response.get_json()["data"]
    assert offer_data["tool"] == "get_offer_status"
    assert offer_data["readonly"] is True
    assert offer_data["result"]["counts"]["sent"] == 1

    before = Match.query.filter_by(job_id=1).count()
    match_response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "推荐财务会计主管候选人"})
    after = Match.query.filter_by(job_id=1).count()
    match_data = match_response.get_json()["data"]
    assert match_data["tool"] == "match_candidates_for_job"
    assert match_data["result"]["job"]["title"] == "财务会计主管"
    assert len(match_data["result"]["items"]) > 0
    assert after == before


def test_csv_exports_return_business_data(client, admin_headers):
    for path, expected in [
        ("/api/exports/candidates.csv", "姓名"),
        ("/api/exports/jobs.csv", "岗位名称"),
        ("/api/exports/interviews.csv", "面试官"),
        ("/api/exports/offers.csv", "候选人"),
        ("/api/exports/pipeline.csv", "当前阶段"),
        ("/api/exports/boss-drafts.csv", "话术"),
    ]:
        response = client.get(path, headers=admin_headers)
        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert expected in response.data.decode("utf-8-sig")


def test_agent_counts_candidate_segments_and_can_create_job_after_confirmation(client, admin_headers):
    count_response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "现在人才库有多少人？现在人才库有多少是软件开发人员，有多少是会计人员？"},
    )
    assert count_response.status_code == 200
    count_data = count_response.get_json()["data"]
    assert count_data["tool"] == "get_candidate_segment_stats"
    assert count_data["result"]["total"] >= 4
    assert count_data["result"]["segments"]["software"]["count"] >= 2
    assert count_data["result"]["segments"]["accounting"]["count"] >= 1

    before_jobs = Job.query.count()
    draft_response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "创建岗位 数据分析师 城市上海 部门数据部 JD 要求 SQL、Python、报表分析，3 年以上经验"},
    )
    assert draft_response.status_code == 200
    draft_data = draft_response.get_json()["data"]
    assert draft_data["tool"] == "create_job"
    assert draft_data["readonly"] is False
    assert draft_data["result"]["created"] is False
    assert draft_data["pending_action"]["type"] == "create_job"
    assert Job.query.count() == before_jobs

    create_response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "确认创建", "pending_action": draft_data["pending_action"]},
    )
    create_data = create_response.get_json()["data"]
    assert create_data["result"]["created"] is True
    assert create_data["pending_action"] is None
    assert create_data["result"]["job"]["title"] == "数据分析师"
    assert {"SQL", "Python"} <= {skill["tag"] for skill in create_data["result"]["job"]["jd_structured"]["skills"]}


def test_agent_candidate_segment_stats_use_primary_occupation(client, admin_headers):
    before = client.post("/api/agent/chat", headers=admin_headers, json={"message": "现在人才库有多少人？软件开发和会计分别多少？"})
    assert before.status_code == 200
    before_stats = before.get_json()["data"]["result"]["segments"]
    candidate = Candidate(
        owner_hr_id=1,
        name_masked="Java财务系统开发候选人",
        title="Java 开发工程师",
        city="长沙",
        raw_text="Java 开发工程师，负责金蝶财务系统接口和报表系统开发，不负责会计核算、纳税申报或账务处理。",
        resume_json={},
    )
    db.session.add(candidate)
    db.session.flush()
    db.session.add(CandidateTag(candidate_id=candidate.id, tag="Java", score=5, category="软件开发"))
    db.session.add(CandidateTag(candidate_id=candidate.id, tag="金蝶", score=3, category="工具"))
    db.session.commit()

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "现在人才库有多少人？软件开发和会计分别多少？"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    stats = data["result"]
    assert stats["classification_mode"] == "primary_occupation_deduplicated"
    assert stats["segments"]["software"]["count"] == before_stats["software"]["count"] + 1
    assert stats["segments"]["accounting"]["count"] == before_stats["accounting"]["count"]
    assert "按主职业去重统计" in data["answer"]


def test_agent_tool_calls_are_audited_without_message_content(client, admin_headers):
    message = "现在人才库有多少人？"
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": message})

    assert response.status_code == 200
    data = response.get_json()["data"]
    log = AuditLog.query.filter_by(action="agent_tool", target_type="agent").order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.target_name == data["tool"]
    assert log.details["tool"] == data["tool"]
    assert log.details["message_length"] == len(message)
    assert message not in json.dumps(log.details, ensure_ascii=False)


def test_agent_smalltalk_does_not_trigger_bi_snapshot(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "你好"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "chat"
    assert "AI 招聘 Agent" in data["answer"]


def test_agent_conversations_persist_messages_and_context(client, admin_headers):
    first = client.post("/api/agent/chat", headers=admin_headers, json={"message": "创建岗位 Java后端工程师"})
    assert first.status_code == 200
    first_data = first.get_json()["data"]
    conversation = first_data["conversation"]
    assert conversation["title"].startswith("创建岗位 Java")
    assert first_data["pending_action"]["type"] == "create_job"

    second = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"conversation_id": conversation["id"], "message": "城市上海，岗位Java后端工程师"},
    )
    assert second.status_code == 200
    second_data = second.get_json()["data"]
    assert second_data["conversation"]["id"] == conversation["id"]

    conversations = client.get("/api/agent/conversations", headers=admin_headers).get_json()["data"]["items"]
    assert conversations[0]["id"] == conversation["id"]
    detail = client.get(f"/api/agent/conversations/{conversation['id']}", headers=admin_headers).get_json()["data"]
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert AgentConversation.query.count() == 1
    assert AgentMessage.query.count() == 4


def test_agent_analyzes_employee_resume_and_recommends_jobs(client, admin_headers):
    java_job = Job(
        owner_hr_id=1,
        title="内部 Java 后端工程师",
        city="上海",
        department="研发部",
        job_code="INTERNAL-AGENT-JAVA",
        jd_text="负责 Java 后端服务开发，要求 Spring Boot、MySQL、Redis，薪资 20-30K。",
        jd_structured={},
        status="active",
    )
    product_job = Job(
        owner_hr_id=1,
        title="内部产品经理",
        city="上海",
        department="产品部",
        job_code="INTERNAL-AGENT-PM",
        jd_text="负责产品规划、需求分析和跨部门沟通。",
        jd_structured={},
        status="active",
    )
    db.session.add_all([java_job, product_job])
    db.session.commit()

    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-employee-java", "raw_text": "姓名：员工Agent测试\n男 13800001234 agent-employee@example.com\n4 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis，负责绩效系统和接口服务开发。"}]},
    ).get_json()["data"]["items"][0]
    replacement_candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-replacement-java", "raw_text": "姓名：替补Agent候选人\n男 13900001234 replacement-agent@example.com\n5 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis 和接口性能优化。"}]},
    ).get_json()["data"]["items"][0]
    employee = client.post(
        "/api/employees/from-candidate",
        headers=admin_headers,
        json={"candidate_id": candidate["id"], "current_job_id": java_job.id, "employee_no": "EMP-AGENT-001", "salary_monthly_k": 18, "salary_months": 13},
    ).get_json()["data"]

    response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "分析员工 员工Agent测试 的简历，推荐适合岗位，并告诉我简历有哪些可以优化"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "analyze_employee_resume"
    assert data["result"]["matched"] is True
    assert data["result"]["employee"]["id"] == employee["id"]
    assert data["result"]["items"][0]["job"]["title"] == "内部 Java 后端工程师"
    assert data["result"]["items"][0]["score"] >= data["result"]["items"][-1]["score"]
    assert data["result"]["plan"]
    assert data["result"]["communication_advice"]
    assert any(item["candidate"]["id"] == replacement_candidate["id"] for item in data["result"]["replacement_candidates"])
    assert data["result"]["resume_optimizations"]
    assert "本次执行" in data["answer"]
    assert "离职替补候选人" in data["answer"]
    assert "沟通建议" in data["answer"]
    assert "简历优化建议" in data["answer"]


def test_agent_analyzes_candidate_resume_when_not_internal_employee(client, admin_headers):
    java_job = Job(
        owner_hr_id=1,
        title="Java 后端开发工程师",
        city="长沙",
        department="研发部",
        job_code="AGENT-CANDIDATE-JAVA",
        jd_text="负责 Java 后端系统开发，要求 Spring Boot、MySQL、Redis、接口性能优化。",
        jd_structured={},
        status="active",
    )
    ops_job = Job(
        owner_hr_id=1,
        title="运维工程师",
        city="长沙",
        department="运维部",
        job_code="AGENT-CANDIDATE-OPS",
        jd_text="负责 Linux、Docker、Kubernetes 和 CI/CD 运维。",
        jd_structured={},
        status="active",
    )
    db.session.add_all([java_job, ops_job])
    db.session.commit()
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-candidate-gui", "raw_text": "姓名：桂嘉豪\n男 13700001234 gui@example.com\n3 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis，做过接口性能优化和订单系统。"}]},
    ).get_json()["data"]["items"][0]

    response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "查看桂嘉豪的简历 并告诉我他适合什么岗位"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "analyze_employee_resume"
    assert data["result"]["matched"] is True
    assert data["result"]["profile_type"] == "candidate"
    assert data["result"]["candidate"]["id"] == candidate["id"]
    assert data["result"]["items"][0]["job"]["title"] == "Java 后端开发工程师"
    assert data["result"]["resume_optimizations"]
    assert "适合岗位" in data["answer"]
    assert "简历优化建议" in data["answer"]

    short_question = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "桂嘉豪适合什么岗位"},
    )
    assert short_question.status_code == 200
    short_data = short_question.get_json()["data"]
    assert short_data["tool"] == "analyze_employee_resume"
    assert short_data["result"]["profile_type"] == "candidate"
    assert short_data["result"]["candidate"]["id"] == candidate["id"]


def test_agent_uses_knowledge_lookup_for_profile_questions(client, admin_headers):
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-candidate-knowledge", "raw_text": "姓名：知识库候选人\n女 13600001234 knowledge@example.com\n2 年数据分析经验，熟悉 SQL、Python、报表分析。"}]},
    ).get_json()["data"]["items"][0]

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "知识库候选人怎么样"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "knowledge_lookup"
    assert data["result"]["profile_type"] == "candidate"
    assert data["result"]["candidate"]["id"] == candidate["id"]
    assert "人才库" in data["answer"]


def test_agent_ignores_boss_navigation_noise_profiles(client, admin_headers):
    noisy = Candidate(
        owner_hr_id=1,
        upload_batch_id="agent-noise",
        name_masked="职位管理",
        title="职位管理",
        source="boss",
        city="",
        raw_text="招聘规范 我的客服 面试 招聘数据 账号权益 续费VIP 王成都 推荐牛人 职位管理 候选人 工具箱 更多",
        resume_json={"summary": "职位管理 推荐牛人 搜索 沟通 新互动 人才管理 道具 首充礼 工具箱 更多"},
    )
    db.session.add(noisy)
    db.session.commit()

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "查看 职位管理 简历"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "chat"
    assert data["result"]["type"] == "module_name_guard"
    assert "推荐牛人" not in data["answer"]
    assert "工具箱" not in data["answer"]
    if data["tool"] == "knowledge_lookup":
        assert data["result"].get("candidate", {}).get("id") != noisy.id


def test_agent_global_lookup_finds_user_owned_jobs(client, admin_headers):
    owner = User(username="wangchengdu-agent", name="王成都", role="recruiter", password_hash="x", active=True)
    db.session.add(owner)
    db.session.flush()
    job = Job(
        owner_hr_id=owner.id,
        title="Java 平台工程师",
        city="长沙",
        department="研发部",
        job_code="AGENT-WANG-JAVA",
        jd_text="负责 Java 平台研发，要求 Spring Boot、MySQL、Redis。",
        jd_structured={},
        status="active",
    )
    db.session.add(job)
    db.session.commit()

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "现在查询王成都的职位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "global_lookup"
    assert data["agent_trace"]["plan"]
    assert data["agent_trace"]["tool_calls"][-1]["name"] == "global_lookup"
    assert data["agent_trace"]["tool_calls"][-1]["status"] == "succeeded"
    assert data["result"]["users"][0]["name"] == "王成都"
    assert data["result"]["users"][0]["owned_jobs"][0]["title"] == "Java 平台工程师"
    assert "王成都" in data["answer"]
    assert "Java 平台工程师" in data["answer"]
    assert [step["step"] for step in data["result"]["plan"]] == ["理解问题", "检索知识库", "组织回答"]


def test_agent_global_lookup_uses_candidate_resume_full_text(client, admin_headers):
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-candidate-ref-wang", "raw_text": "姓名：张伟\n男 13900001111 zhangwei@example.com\n5 年 Java 后端经验。沟通过的招聘负责人是王成都，期望继续了解平台研发岗位。"}]},
    ).get_json()["data"]["items"][0]

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "现在查询王成都的职位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "global_lookup"
    assert data["agent_trace"]["knowledge"]["query_terms"]
    assert data["result"]["candidates"][0]["id"] == candidate["id"]
    assert "简历全文" in data["answer"]
    assert "王成都" in data["result"]["candidates"][0]["matched_evidence"]


def test_agent_runs_multi_tool_chain_for_explicit_multi_step_requests(client, admin_headers):
    owner = User(username="multi-wangchengdu", name="王成都", role="recruiter", password_hash="x", active=True)
    db.session.add(owner)
    db.session.flush()
    job = Job(owner_hr_id=owner.id, title="Java 平台工程师", city="长沙", department="研发部", job_code="AGENT-CHAIN-JAVA", jd_text="负责 Java 平台研发。", jd_structured={}, status="active")
    candidate = Candidate(owner_hr_id=1, upload_batch_id="agent-chain", name_masked="链路候选人", title="Java", raw_text="姓名：链路候选人\nJava 后端开发", resume_json={}, source="upload")
    db.session.add_all([job, candidate])
    db.session.flush()
    db.session.add(PipelineStage(candidate_id=candidate.id, job_id=job.id, stage="pending", updated_by=1))
    db.session.add(InterviewAssignment(candidate_id=candidate.id, job_id=job.id, interviewer_id=1, round="interview_first", scheduled_at=datetime.now(timezone.utc), created_by=1))
    db.session.commit()

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "现在查询王成都的职位，同时查看流程和面试情况"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "agent_toolchain"
    tool_names = [item["name"] for item in data["agent_trace"]["tool_calls"]]
    assert "global_lookup" in tool_names
    assert "get_pipeline_funnel" in tool_names
    assert "get_interview_schedule" in tool_names
    assert all(item["status"] == "succeeded" for item in data["agent_trace"]["tool_calls"])
    assert len(data["result"]["chain"]) >= 3


def test_agent_remembers_clarification_and_continues_resume_analysis(client, admin_headers):
    job = Job(
        owner_hr_id=1,
        title="Java 后端工程师",
        city="长沙",
        department="研发部",
        job_code="AGENT-CLARIFY-JAVA",
        jd_text="负责 Java 后端开发，要求 Spring Boot、MySQL、Redis。",
        jd_structured={},
        status="active",
    )
    db.session.add(job)
    db.session.commit()
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-clarify-gui", "raw_text": "姓名：桂嘉豪\n男 13700001234 clarify-gui@example.com\n3 年 Java 后端经验，熟悉 Spring Boot、MySQL、Redis。"}]},
    ).get_json()["data"]["items"][0]

    first = client.post("/api/agent/chat", headers=admin_headers, json={"message": "分析他的简历并推荐岗位"})

    assert first.status_code == 200
    first_data = first.get_json()["data"]
    assert first_data["tool"] == "agent_clarification"
    assert first_data["pending_action"]["type"] == "agent_clarification"
    assert first_data["pending_action"]["missing"] == ["person"]

    second = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"conversation_id": first_data["conversation"]["id"], "message": "桂嘉豪"},
    )

    assert second.status_code == 200
    second_data = second.get_json()["data"]
    assert second_data["tool"] == "analyze_employee_resume"
    assert second_data["pending_action"] is None
    assert second_data["result"]["profile_type"] == "candidate"
    assert second_data["result"]["candidate"]["id"] == candidate["id"]
    assert second_data["result"]["continued_from"]["user_clarification"] == "桂嘉豪"
    assert "接上上一步任务" in second_data["answer"]


def test_agent_asks_for_job_before_open_ended_candidate_match(client, admin_headers):
    job = Job(owner_hr_id=1, title="会计", city="上海", department="财务部", job_code="AGENT-CLARIFY-ACCOUNTING", jd_text="负责总账会计、财务报表、纳税申报。", jd_structured={}, status="active")
    candidate = Candidate(owner_hr_id=1, upload_batch_id="agent-clarify-job", name_masked="会计候选人", title="总账会计", raw_text="5 年总账会计经验，熟悉财务报表和纳税申报。", resume_json={}, source="upload")
    db.session.add_all([job, candidate])
    db.session.commit()

    first = client.post("/api/agent/chat", headers=admin_headers, json={"message": "推荐候选人"})

    assert first.status_code == 200
    first_data = first.get_json()["data"]
    assert first_data["tool"] == "agent_clarification"
    assert first_data["pending_action"]["missing"] == ["job"]

    second = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"conversation_id": first_data["conversation"]["id"], "message": "会计"},
    )

    assert second.status_code == 200
    second_data = second.get_json()["data"]
    assert second_data["tool"] == "match_candidates_for_job"
    assert second_data["pending_action"] is None
    assert second_data["result"]["continued_from"]["user_clarification"] == "会计"
    assert "会计" in second_data["answer"]


def test_agent_does_not_create_job_from_ambiguous_create_and_recommend(client, admin_headers):
    candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "agent-ambiguous-gui", "raw_text": "姓名：桂嘉豪\n男 13700001234 gui-ambiguous@example.com\n3 年 Java 后端开发经验，熟悉 Spring Boot、MySQL。"}]},
    ).get_json()["data"]["items"][0]
    before = Job.query.count()

    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "创建新岗位并推荐桂嘉豪"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "agent_plan"
    assert data["result"]["candidate"]["id"] == candidate["id"]
    assert Job.query.count() == before
    assert "不会把" in data["answer"]


def test_agent_web_trend_question_is_not_treated_as_candidate_search(client, admin_headers):
    response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "联网查一下今年Java招聘趋势，再结合我们人才库说说"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "chat"
    assert data["tool"] != "search_candidates"


def test_agent_free_chat_falls_back_to_llm_chat(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "帮我规划一下下周招聘重点"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "chat"
    assert data["result"]["llm"] == "disabled"


def test_agent_generate_job_without_details_asks_for_title(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "给我生成一个岗位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "create_job"
    assert data["result"]["created"] is False
    assert "岗位名称" in data["answer"]


def test_agent_lists_job_details_and_matches_best_candidates(client, admin_headers):
    list_response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "列出所有岗位"})
    assert list_response.status_code == 200
    list_data = list_response.get_json()["data"]
    assert list_data["tool"] == "get_job_summary"
    assert "财务会计主管" in list_data["answer"]
    assert "关键技能" in list_data["answer"]

    match_response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "给所有岗位匹配最佳候选人"})
    assert match_response.status_code == 200
    match_data = match_response.get_json()["data"]
    assert match_data["tool"] == "match_candidates_for_job"
    assert "最佳候选人" in match_data["answer"]
    assert "匹配分" in match_data["answer"]
    assert len(match_data["result"]["jobs"]) >= 3


def test_agent_explains_candidate_job_match_with_evidence_chain(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "李华为什么适合财务会计主管岗位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "match_candidates_for_job"
    assert data["result"]["candidate"]["name_masked"] == "李华"
    assert data["result"]["job"]["title"] == "财务会计主管"
    assert "评分拆解" in data["answer"]
    assert "主要证据" in data["answer"]
    assert data["result"]["match"]["reason"]["score_breakdown"]
    assert data["result"]["match"]["reason"]["evidence_chain"]


def test_agent_compares_candidates_for_same_job(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "李华和王强谁更适合Python后端工程师岗位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "match_candidates_for_job"
    assert data["result"]["comparison"] is True
    assert data["result"]["job"]["title"] == "Python 后端工程师"
    assert data["result"]["items"][0]["candidate"]["name_masked"] == "王强"
    assert "当前更推荐 王强" in data["answer"]
    assert "排序" in data["answer"]
    assert "缺口" in data["answer"]


def test_agent_can_queue_job_match_background_task(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "后台匹配财务会计主管岗位"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "queue_background_task"
    assert data["readonly"] is False
    task = data["result"]["task"]
    assert task["task_type"] == "job_match"
    assert task["status"] == "queued"
    assert data["result"]["job"]["title"] == "财务会计主管"


def test_agent_can_queue_matching_recalibration_task(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "执行匹配数据校准"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "queue_background_task"
    task = data["result"]["task"]
    assert task["task_type"] == "matching_recalibration"
    assert task["payload"]["reparse_candidates"] is True
    assert "校准" in data["answer"]


def test_boss_draft_can_be_listed_and_reviewed(client, admin_headers):
    created = client.post("/api/boss/messages/draft", headers=admin_headers, json={"candidate_id": 1, "job_id": 1})
    assert created.status_code == 200
    draft = created.get_json()["data"]
    assert draft["status"] == "draft"
    assert draft["candidate"]["id"] == 1

    listed = client.get("/api/boss/messages/drafts", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.get_json()["data"]["items"][0]["id"] == draft["id"]

    reviewed = client.patch(f"/api/boss/messages/drafts/{draft['id']}", headers=admin_headers, json={"status": "reviewed"})
    assert reviewed.status_code == 200
    assert reviewed.get_json()["data"]["status"] == "reviewed"

    edited = client.patch(f"/api/boss/messages/drafts/{draft['id']}", headers=admin_headers, json={"content": "更新后的沟通话术"})
    assert edited.status_code == 200
    assert edited.get_json()["data"]["content"] == "更新后的沟通话术"

    deleted = client.delete(f"/api/boss/messages/drafts/{draft['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted"] == draft["id"]


def test_boss_extension_can_be_downloaded(client, admin_headers):
    response = client.get("/api/boss/extension.zip", headers=admin_headers)

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(BytesIO(response.data)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "popup.js" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert "http://120.24.172.139/*" in manifest["host_permissions"]
        assert manifest["version"] == "0.3.6"
        content = archive.read("content.js").decode("utf-8")
        assert "findResumeColumnBounds" in content
        assert "assertBossJobListPage" in content
        assert "inspectBossPage" in content
        assert "hasOnlineResumeModal" in content
        assert "collectObtainedResumeText" in content
        assert "autoCollectCommunicationResumes" in content
        assert "can_import_obtained_resume" in content
        assert "\\u4e0d\\u80fd\\u91c7\\u96c6\\u5019\\u9009\\u4eba\\u7684\\u671f\\u671b\\u804c\\u4f4d" in content
        popup = archive.read("popup.js").decode("utf-8")
        assert "refreshPageState" in popup
        assert "can_sync_jobs" in popup
        assert "obtainedImportBtn" in popup
        assert "autoListImportBtn" in popup


def test_boss_screen_resume_import_creates_candidate_and_draft(client, admin_headers):
    response = client.post(
        "/api/boss/screen-resume/import",
        headers=admin_headers,
        json={
            "raw_text": "姓名：周会计\n女 13812345678\n5 年总账会计经验，熟悉财务报表、纳税申报、Excel、金蝶。",
            "chunk_count": 2,
            "job_id": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["candidate"]["source"] == "boss"
    assert data["candidate"]["name_masked"] == "周会计"
    assert data["draft"]["candidate_id"] == data["candidate"]["id"]
    assert "财务会计主管" in data["draft"]["content"]
    assert {"总账会计", "财务报表", "纳税申报", "Excel"} <= {tag["tag"] for tag in data["candidate"]["tags"]}

    inbox = client.get("/api/boss/candidates/inbox", headers=admin_headers)
    assert inbox.status_code == 200
    assert any(item["candidate_id"] == data["candidate"]["id"] for item in inbox.get_json()["data"]["items"])


def test_boss_screen_resume_import_updates_duplicate_by_phone(client, admin_headers):
    for name in ["周一", "周二"]:
        response = client.post(
            "/api/boss/screen-resume/import",
            headers=admin_headers,
            json={"raw_text": f"姓名：{name}\n女 13899998888\n5 年总账会计经验，熟悉 Excel、财务报表。"},
        )
        assert response.status_code == 200

    matches = Candidate.query.filter_by(phone_masked="13899998888").all()
    assert len(matches) == 1
    assert matches[0].name_masked == "周二"
    assert matches[0].source == "boss"


def test_boss_batch_import_parses_real_resume_text(client, admin_headers):
    response = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={
            "items": [
                {
                    "external_id": "boss-a",
                    "name": "批量候选人",
                    "title": "Java 开发工程师",
                    "raw_text": "姓名：批量候选人\n男 13612345678 batch@example.com\n3 年 Java 开发经验，熟悉 Spring Boot、MySQL、Redis，做过绩效系统。",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"][0]["source"] == "boss"
    assert data["items"][0]["name_masked"] == "批量候选人"
    assert {"Java", "MySQL", "Redis"} <= {tag["tag"] for tag in data["items"][0]["tags"]}


def test_boss_batch_import_accepts_english_resume_text(client, admin_headers):
    response = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={
            "items": [
                {
                    "external_id": "boss-english",
                    "raw_text": "Name: English Candidate\nPhone: 13900001234 english@example.com\n4 years Java backend development experience, familiar with Spring Boot, MySQL and Redis.\nEducation: Bachelor, Computer Science",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"][0]["source"] == "boss"
    assert {"Java", "MySQL", "Redis"} <= {tag["tag"] for tag in data["items"][0]["tags"]}


def test_boss_batch_import_skips_navigation_noise(client, admin_headers):
    response = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "bad", "name": "招聘规范", "raw_text": "招聘规范 我的客服 职位管理 推荐牛人 账号权益 续费VIP 道具 工具箱"}]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"] == []
    assert data["errors"][0]["error"] == "不是候选人简历内容，已跳过"


def test_boss_jobs_can_be_synced_and_recommend_boss_candidates(client, admin_headers):
    imported_candidate = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "boss-java", "raw_text": "姓名：Boss候选人\n男 13600001111\n4 年 Java 后端开发经验，熟悉 Spring Boot、MySQL、Redis。"}]},
    ).get_json()["data"]["items"][0]
    job_response = client.post(
        "/api/boss/jobs/batch-import",
        headers=admin_headers,
        json={"items": [{"external_id": "job-java", "title": "Java 后端工程师", "city": "上海", "jd_text": "招聘 Java 后端工程师，要求 Spring Boot、MySQL、Redis，3 年以上经验。"}]},
    )

    assert job_response.status_code == 200
    job = job_response.get_json()["data"]["items"][0]
    assert job["job_code"].startswith("BOSS-")
    listed = client.get("/api/boss/jobs", headers=admin_headers)
    assert any(item["id"] == job["id"] for item in listed.get_json()["data"]["items"])

    recommendations = client.get(f"/api/boss/jobs/{job['id']}/recommendations", headers=admin_headers)
    assert recommendations.status_code == 200
    items = recommendations.get_json()["data"]["items"]
    assert items[0]["candidate_id"] == imported_candidate["id"]
    assert all(item["candidate"]["source"] == "boss" for item in items)


def test_boss_job_import_rejects_resume_expected_position(client, admin_headers):
    response = client.post(
        "/api/boss/jobs/batch-import",
        headers=admin_headers,
        json={
            "items": [
                {
                    "external_id": "resume-expected-job",
                    "title": "\u4f1a\u8ba1",
                    "jd_text": "\u671f\u671b\u804c\u4f4d\uff1a\u4f1a\u8ba1\n\u5de5\u4f5c\u7ecf\u5386\uff1a\u8d1f\u8d23\u8d22\u52a1\u62a5\u8868\u548c\u7eb3\u7a0e\u7533\u62a5\n\u6559\u80b2\u7ecf\u5386\uff1a\u672c\u79d1\n\u7535\u8bdd 13600002222",
                }
            ]
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"] == []
    assert data["errors"][0]["error"] == "\u7591\u4f3c\u5019\u9009\u4eba\u7b80\u5386/\u671f\u671b\u804c\u4f4d\u5185\u5bb9\uff0c\u4e0d\u80fd\u4f5c\u4e3a BOSS \u5c97\u4f4d\u5bfc\u5165"
    assert not Job.query.filter_by(job_code="BOSS-resume-expected-job").first()


def test_boss_sync_jobs_are_logged_and_failed_items_can_retry(client, admin_headers):
    response = client.post(
        "/api/boss/candidates/batch-import",
        headers=admin_headers,
        json={
            "items": [
                {
                    "external_id": "sync-ok",
                    "raw_text": "Name: Sync Candidate\nPhone: 13911112222\n5 years Java backend development experience, familiar with Spring Boot, MySQL and Redis.",
                },
                {"external_id": "sync-bad", "name": "navigation", "raw_text": "job menu vip account tools"},
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["sync_job"]["sync_type"] == "candidate_batch"
    assert data["sync_job"]["status"] == "partial"
    assert data["sync_job"]["success_count"] == 1
    assert data["sync_job"]["failed_count"] == 1
    assert BossSyncJob.query.filter_by(sync_type="candidate_batch").count() >= 1

    listed = client.get("/api/boss/sync/jobs?sync_type=candidate_batch", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.get_json()["data"]["items"][0]["id"] == data["sync_job"]["id"]

    detail = client.get(f"/api/boss/sync/jobs/{data['sync_job']['id']}", headers=admin_headers)
    assert detail.status_code == 200
    detail_data = detail.get_json()["data"]
    assert len(detail_data["items"]) == 2
    assert any(item["status"] == "failed" and item["external_id"] == "sync-bad" for item in detail_data["items"])

    retry = client.post(f"/api/boss/sync/jobs/{data['sync_job']['id']}/retry", headers=admin_headers)
    assert retry.status_code == 200
    retry_data = retry.get_json()["data"]
    assert retry_data["retried"] is True
    assert retry_data["retry_result"]["sync_job"]["parent_sync_job_id"] == data["sync_job"]["id"]
    assert retry_data["retry_result"]["sync_job"]["status"] == "failed"


def test_resume_retry_parse_refreshes_tags(client, admin_headers):
    candidate = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    response = client.post(f"/api/resume/{candidate['id']}/retry-parse", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]["candidate"]
    assert data["parse_status"] == "ok"
    assert data["tags"]


def test_resume_retry_parse_can_run_as_background_task(client, admin_headers):
    candidate = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    queued = client.post(f"/api/resume/{candidate['id']}/retry-parse?async=1", headers=admin_headers)

    assert queued.status_code == 200
    task = queued.get_json()["data"]["task"]
    assert task["task_type"] == "resume_retry_parse"
    assert task["status"] == "queued"
    assert "before_tags" in task["payload"]

    listed = client.get("/api/tasks?task_type=resume_retry_parse", headers=admin_headers)
    assert listed.status_code == 200
    listed_data = listed.get_json()["data"]
    assert listed_data["status_counts"]["queued"] >= 1
    assert any(item["id"] == task["id"] for item in listed_data["items"])

    run_task = run_next_task()
    assert run_task.id == task["id"]
    assert run_task.status == "succeeded"
    assert run_task.result["candidate_id"] == candidate["id"]
    assert run_task.result["tag_count"] > 0
    assert "after_tags" in run_task.result
    assert "tag_diff" in run_task.result

    detail = client.get(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["status"] == "succeeded"


def test_queued_background_task_can_run_now(client, admin_headers):
    candidate = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    queued = client.post(f"/api/resume/{candidate['id']}/retry-parse?async=1", headers=admin_headers)
    task = queued.get_json()["data"]["task"]

    response = client.post(f"/api/tasks/{task['id']}/run", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "succeeded"
    assert data["result"]["candidate_id"] == candidate["id"]
    assert data["result"]["tag_count"] > 0


def test_failed_background_task_can_be_retried(client, admin_headers):
    task = BackgroundTask(task_type="resume_retry_parse", status="failed", payload={"candidate_id": 999999}, attempts=1, max_attempts=3, created_by=1)
    db.session.add(task)
    db.session.commit()

    response = client.post(f"/api/tasks/{task.id}/retry", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "queued"
    assert data["error"] is None


def test_failed_background_tasks_can_be_retried_in_batch(client, admin_headers):
    first = BackgroundTask(task_type="resume_retry_parse", status="failed", payload={"candidate_id": 999999}, attempts=1, max_attempts=3, created_by=1, error="候选人不存在")
    second = BackgroundTask(task_type="backup_export", status="failed", payload={}, attempts=1, max_attempts=1, created_by=1, error="备份失败")
    db.session.add_all([first, second])
    db.session.commit()

    response = client.post("/api/tasks/retry-batch", headers=admin_headers, json={"task_ids": [first.id, second.id]})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["retried_count"] == 1
    assert data["skipped_count"] == 1
    assert data["retried"][0]["id"] == first.id
    assert data["skipped"][0]["id"] == second.id
    assert db.session.get(BackgroundTask, first.id).status == "queued"


def test_boss_cookie_verify_ai_screen_and_draft_actions(client, admin_headers):
    bind = client.post(
        "/api/boss/login/browser-cookie",
        headers=admin_headers,
        json={"account": "hr@boss", "cookie": "sid=abcdefghijklmnopqrstuvwxyz; token=1234567890"},
    )
    assert bind.status_code == 200
    account = bind.get_json()["data"]["account"]
    assert account["verified"] is False

    verify = client.post(f"/api/boss/accounts/{account['id']}/verify", headers=admin_headers)
    assert verify.status_code == 200
    assert verify.get_json()["data"]["account"]["verified"] is True

    screen = client.post("/api/boss/candidates/ai-screen", headers=admin_headers, json={"job_id": 1, "candidate_ids": [2]})
    assert screen.status_code == 200
    assert screen.get_json()["data"]["created"][0]["stage"] == "ai_screen"

    draft = client.post("/api/boss/messages/draft", headers=admin_headers, json={"candidate_id": 1, "job_id": 1}).get_json()["data"]
    approved = client.post(f"/api/boss/messages/drafts/{draft['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200
    assert approved.get_json()["data"]["status"] == "approved"
    sent = client.post(f"/api/boss/messages/drafts/{draft['id']}/mark-sent", headers=admin_headers)
    assert sent.get_json()["data"]["status"] == "sent"
    cancelled = client.post(f"/api/boss/messages/drafts/{draft['id']}/cancel", headers=admin_headers)
    assert cancelled.get_json()["data"]["status"] == "archived"


def test_pipeline_move_validates_candidate_and_job(client, admin_headers):
    response = client.post(
        "/api/pipeline/move",
        headers=admin_headers,
        json={"candidate_id": 999, "job_id": 1, "stage": "interview_first"},
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "NOT_FOUND"


def test_resume_upload_parses_candidate_and_tags(client, admin_headers):
    content = "姓名：刘会计\n性别：女\n城市：上海\n手机：13812345678\n邮箱：liucpa@example.com\n5 年总账会计经验，熟悉纳税申报、财务报表、Excel、金蝶。"
    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={"file": (BytesIO(content.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    candidate = response.get_json()["data"]["candidate"]
    assert candidate["name_masked"] == "刘会计"
    assert candidate["phone_masked"] == "13812345678"
    assert candidate["email_masked"] == "liucpa@example.com"
    assert candidate["gender"] == "女"
    assert candidate["resume_json"]["name"] == "刘会计"
    assert candidate["resume_json"]["phone"] == "13812345678"
    assert candidate["title"] == "总账会计"
    assert candidate["experience_analysis"]["level"] == "5-10"
    assert candidate["attachments"][0]["scan_status"] == "clean"

    attachment_id = candidate["attachments"][0]["id"]
    attachments = client.get("/api/resume/attachments?limit=5", headers=admin_headers)
    assert attachments.status_code == 200
    assert any(item["id"] == attachment_id for item in attachments.get_json()["data"]["items"])

    candidate_attachments = client.get(f"/api/candidates/{candidate['id']}/attachments", headers=admin_headers)
    assert candidate_attachments.status_code == 200
    assert candidate_attachments.get_json()["data"]["items"][0]["sha256"]

    detail = client.get(f"/api/resume/attachments/{attachment_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["original_filename"] == "resume.txt"

    rescan = client.post(f"/api/resume/attachments/{attachment_id}/scan", headers=admin_headers)
    assert rescan.status_code == 200
    assert rescan.get_json()["data"]["scan_status"] == "clean"
    assert ResumeAttachment.query.filter_by(candidate_id=candidate["id"]).count() == 1
    assert {tag["tag"] for tag in candidate["tags"]} >= {"总账会计", "纳税申报", "财务报表", "Excel"}


def test_resume_upload_accepts_multiple_files_and_zip(client, admin_headers):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("zip-resume.txt", "姓名：赵会计\n手机：13812345679\n6 年总账会计经验，熟悉 Excel、财务报表。")
    zip_buffer.seek(0)

    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={
            "files": [
                (BytesIO("姓名：王开发\n手机：13812345670\n3 年 Java、MySQL、Redis 开发经验。".encode("utf-8")), "dev.txt"),
                (zip_buffer, "resumes.zip"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["success_count"] == 2
    assert data["failed_count"] == 0
    assert {item["name_masked"] for item in data["candidates"]} >= {"王开发", "赵会计"}


def test_resume_upload_keeps_extension_for_non_ascii_filename(client, admin_headers):
    content = (
        "Name: Unicode Filename Candidate\n"
        "Phone: 13812349999\n"
        "Email: unicode-filename@example.com\n"
        "Target: Java Engineer\n"
        "Experience: 4 years Java, Spring Boot, MySQL and Redis.\n"
    )
    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={"file": (BytesIO(content.encode("utf-8")), "\u4e2a\u4eba\u7b80\u5386.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    candidate = response.get_json()["data"]["candidate"]
    attachment = candidate["attachments"][0]
    assert attachment["original_filename"] == "\u4e2a\u4eba\u7b80\u5386.txt"
    assert attachment["extension"] == ".txt"
    assert attachment["stored_filename"].endswith(".txt")
    assert attachment["scan_status"] == "clean"


def test_resume_upload_rejects_too_many_files(app, client, admin_headers):
    app.config["MAX_UPLOAD_FILES"] = 1

    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={
            "files": [
                (BytesIO("姓名：一号\n手机：13800000001\n3 年 Java 开发经验。".encode("utf-8")), "one.txt"),
                (BytesIO("姓名：二号\n手机：13800000002\n3 年 Python 开发经验。".encode("utf-8")), "two.txt"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert response.get_json()["code"] == "TOO_MANY_FILES"


def test_resume_upload_rejects_unsafe_zip_path(client, admin_headers):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("../evil.txt", "姓名：路径风险\n手机：13800000003\n3 年 Java 开发经验。")
    zip_buffer.seek(0)

    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={"file": (zip_buffer, "unsafe.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["code"] == "PARSE_FAILED"
    assert data["details"]["errors"][0]["error"] == "压缩包路径不安全，已跳过"


def test_resume_upload_updates_duplicate_by_phone(client, admin_headers):
    payloads = [
        ("姓名：重复一\n手机：13911112222\n3 年 Java、MySQL 开发经验。", "one.txt"),
        ("姓名：重复二\n手机：13911112222\n4 年 Python、Redis 开发经验。", "two.txt"),
    ]
    for text, filename in payloads:
        response = client.post(
            "/api/resume/upload",
            headers=admin_headers,
            data={"file": (BytesIO(text.encode("utf-8")), filename)},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200

    matches = Candidate.query.filter_by(phone_masked="13911112222").all()
    assert len(matches) == 1
    assert matches[0].name_masked == "重复二"
    assert CandidateTag.query.filter_by(candidate_id=matches[0].id, tag="Python").count() == 1
    detail = client.get(f"/api/candidates/{matches[0].id}", headers=admin_headers).get_json()["data"]
    python_tag = next(tag for tag in detail["tags"] if tag["tag"] == "Python")
    assert python_tag["evidence_status"] == "verified"
    assert python_tag["evidence"]


def test_candidate_basic_info_can_be_updated(client, admin_headers):
    response = client.patch(
        "/api/candidates/1",
        headers=admin_headers,
        json={"name_masked": "李华修正", "phone_masked": "13900001111", "gender": "女", "summary": "人工修正简介"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name_masked"] == "李华修正"
    assert data["phone_masked"] == "13900001111"
    assert data["gender"] == "女"
    assert data["resume_json"]["summary"] == "人工修正简介"


def test_candidate_tags_can_be_replaced_and_clear_matches(client, admin_headers, app):
    client.post("/api/jobs/1/match", headers=admin_headers)
    with app.app_context():
        assert Match.query.filter_by(candidate_id=1).count() > 0

    response = client.put(
        "/api/candidates/1/tags",
        headers=admin_headers,
        json={"tags": [{"tag": "Python", "score": 4}, {"tag": "MySQL", "score": 3}, {"tag": "Python", "score": 2}]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert [(tag["tag"], tag["score"], tag["category"]) for tag in data["tags"]] == [("Python", 4, "编程语言"), ("MySQL", 3, "数据库")]
    with app.app_context():
        assert Match.query.filter_by(candidate_id=1).count() == 0


def test_tag_quality_panel_can_confirm_and_delete_tags(client, admin_headers):
    response = client.put(
        "/api/candidates/1/tags",
        headers=admin_headers,
        json={"tags": [{"tag": "Python", "score": 2}, {"tag": "iOS", "score": 5}]},
    )
    assert response.status_code == 200

    quality = client.get("/api/tags/quality?issue=all", headers=admin_headers)
    assert quality.status_code == 200
    data = quality.get_json()["data"]
    assert data["overview"]["low_confidence"] >= 1
    assert any(item["candidate"]["id"] == 1 and item["tag"]["tag"] == "iOS" and "suspected_mismatch" in item["issue_types"] for item in data["items"])

    queued = client.post("/api/resume/1/retry-parse?async=1", headers=admin_headers)
    assert queued.status_code == 200
    quality_with_task = client.get("/api/tags/quality?issue=all", headers=admin_headers).get_json()["data"]
    ios_item = next(item for item in quality_with_task["items"] if item["candidate"]["id"] == 1 and item["tag"]["tag"] == "iOS")
    assert ios_item["latest_reparse_task"]["id"] == queued.get_json()["data"]["task"]["id"]
    assert ios_item["latest_reparse_task"]["payload"]["before_tags"]

    confirmed = client.post("/api/candidates/1/tags/iOS/confirm", headers=admin_headers, json={"note": "人工复核确认保留"})
    assert confirmed.status_code == 200
    ios_tag = next(tag for tag in confirmed.get_json()["data"]["tags"] if tag["tag"] == "iOS")
    assert ios_tag["evidence_status"] == "manual_confirmed"

    deleted = client.delete("/api/candidates/1/tags/iOS", headers=admin_headers)
    assert deleted.status_code == 200
    assert "iOS" not in {tag["tag"] for tag in deleted.get_json()["data"]["tags"]}


def test_tag_quality_panel_supports_batch_actions(client, admin_headers):
    response = client.put(
        "/api/candidates/1/tags",
        headers=admin_headers,
        json={"tags": [{"tag": "Python", "score": 2}, {"tag": "Java", "score": 5}]},
    )
    assert response.status_code == 200
    items = [{"candidate_id": 1, "tag": "Python"}, {"candidate_id": 1, "tag": "Java"}]

    reparse = client.post("/api/tags/quality/reparse-batch", headers=admin_headers, json={"items": items})
    assert reparse.status_code == 200
    reparse_data = reparse.get_json()["data"]
    assert reparse_data["queued_count"] == 1
    assert reparse_data["tasks"][0]["payload"]["before_tags"]

    confirm = client.post("/api/tags/quality/confirm-batch", headers=admin_headers, json={"items": items, "note": "批量确认"})
    assert confirm.status_code == 200
    assert confirm.get_json()["data"]["confirmed_count"] == 2
    detail = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    assert {tag["evidence_status"] for tag in detail["tags"]} == {"manual_confirmed"}

    deleted = client.post("/api/tags/quality/delete-batch", headers=admin_headers, json={"items": items})
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted_count"] == 2
    detail = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    assert detail["tags"] == []


def test_candidate_tags_reject_unknown_label(client, admin_headers):
    response = client.put("/api/candidates/1/tags", headers=admin_headers, json={"tags": [{"tag": "不存在标签", "score": 3}]})

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


def test_resume_upload_does_not_treat_job_intent_as_name(client, admin_headers):
    content = "求职意向：Java 开发工程师（全栈）\n男 26岁 16673326126\n邮箱：java@example.com\n3 年 Java 和 SQL 开发经验。"
    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={"file": (BytesIO(content.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    candidate = response.get_json()["data"]["candidate"]
    assert candidate["name_masked"] == "候选人"
    assert candidate["phone_masked"] == "16673326126"
    assert candidate["gender"] == "男"


def test_resume_upload_structures_sections_and_ignores_date_years(client, admin_headers):
    content = """姓名：李旺鑫
求职意向：Java开发 + AI应用开发
男 23岁 19066519221 19066519221@163.com
2 年 Java 开发经验，熟悉 Spring Boot、MySQL、Redis、大模型。

教育经历
湖南软件职业技术大学 本科 软件工程 2022-2026

工作经历
上海智答科技有限公司 全栈开发工程师 2024.07-至今
负责 Spring Boot 后端接口、MySQL 数据建模和 Redis 缓存。

项目经历
AI Agent SaaS
使用 Java、Spring Boot、大模型能力完成简历解析与匹配。"""
    response = client.post(
        "/api/resume/upload",
        headers=admin_headers,
        data={"file": (BytesIO(content.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    candidate = response.get_json()["data"]["candidate"]
    assert candidate["name_masked"] == "李旺鑫"
    assert candidate["title"] == "Java开发 + AI应用开发"
    assert candidate["experience_analysis"]["years"] == 2
    assert candidate["resume_json"]["education"]
    assert candidate["resume_json"]["experience"]
    assert candidate["resume_json"]["projects"]
    assert {"Java", "Spring Boot", "MySQL", "Redis", "大模型"} <= {tag["tag"] for tag in candidate["tags"]}


def test_delete_candidate_cascades_related_records(client, admin_headers, app):
    match_response = client.post("/api/jobs/1/match", headers=admin_headers)
    assert match_response.status_code == 200

    draft_response = client.post("/api/boss/messages/draft", headers=admin_headers, json={"candidate_id": 1, "job_id": 1})
    assert draft_response.status_code == 200

    offer_response = client.post("/api/offers", headers=admin_headers, json={"candidate_id": 1, "job_id": 1, "status": "sent"})
    assert offer_response.status_code == 200

    response = client.delete("/api/candidates/1", headers=admin_headers)
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(Candidate, 1) is None
        assert Match.query.filter_by(candidate_id=1).count() == 0
        assert PipelineStage.query.filter_by(candidate_id=1).count() == 0
        assert InterviewAssignment.query.filter_by(candidate_id=1).count() == 0
        assert OfferRecord.query.filter_by(candidate_id=1).count() == 0
        assert BossDraft.query.filter_by(candidate_id=1).count() == 0
