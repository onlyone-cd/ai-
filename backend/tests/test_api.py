from io import BytesIO
import json
import logging
import urllib.error
from datetime import datetime, timezone
import zipfile

import jwt
import pytest
from sqlalchemy import inspect

from app import create_app, db
from app.config import Config
from app.auth import verify_password
from app.llm_client import chat_json
from app.models import AuditLog, BossDraft, Candidate, CandidateTag, InterviewAssignment, InterviewFeedback, Job, Match, OfferRecord, PipelineStage, User


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


def test_llm_chat_json_retries_transient_failure(app, monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            body = {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}
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
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with app.app_context():
        assert chat_json([{"role": "user", "content": "json"}]) == {"ok": True}
    assert calls["count"] == 2


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

    assert "ix_candidate_source_created_at" in candidate_indexes
    assert "ix_candidate_phone_masked" in candidate_indexes
    assert "ix_pipeline_stage_job_candidate_ts" in pipeline_indexes
    assert "ix_audit_log_target_created" in audit_indexes


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

    assert client.get("/api/candidates", headers=recruiter_headers).status_code == 200
    assert client.get("/api/candidates/1", headers=interviewer_headers).status_code == 403
    assert client.get("/api/candidates/1/resume.txt", headers=interviewer_headers).status_code == 403

    recruiter_export = client.get("/api/exports/candidates.csv", headers=recruiter_headers)
    admin_export = client.get("/api/exports/candidates.csv", headers=admin_headers)
    assert recruiter_export.status_code == 403
    assert admin_export.status_code == 200


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
        "/api/offers",
        "/api/offers/1",
        "/api/offers/1/letter.txt",
        "/api/bi/overview",
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
    assert all(item["score"] >= 50 for item in matches)
    assert all(item["candidate"]["title"] != "Python 后端工程师" for item in matches)


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
    assert all(item["score"] >= 50 for item in items)
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


def test_agent_counts_candidate_segments_and_can_create_job(client, admin_headers):
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

    create_response = client.post(
        "/api/agent/chat",
        headers=admin_headers,
        json={"message": "创建岗位 数据分析师 城市上海 部门数据部 JD 要求 SQL、Python、报表分析，3 年以上经验"},
    )
    assert create_response.status_code == 200
    create_data = create_response.get_json()["data"]
    assert create_data["tool"] == "create_job"
    assert create_data["readonly"] is False
    assert create_data["result"]["created"] is True
    assert create_data["result"]["job"]["title"] == "数据分析师"
    assert {"SQL", "Python"} <= {skill["tag"] for skill in create_data["result"]["job"]["jd_structured"]["skills"]}


def test_agent_smalltalk_does_not_trigger_bi_snapshot(client, admin_headers):
    response = client.post("/api/agent/chat", headers=admin_headers, json={"message": "你好"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tool"] == "chat"
    assert "AI 招聘 Agent" in data["answer"]


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


def test_resume_retry_parse_refreshes_tags(client, admin_headers):
    candidate = client.get("/api/candidates/1", headers=admin_headers).get_json()["data"]
    response = client.post(f"/api/resume/{candidate['id']}/retry-parse", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]["candidate"]
    assert data["parse_status"] == "ok"
    assert data["tags"]


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
