from pathlib import Path
from time import time
from collections import defaultdict, deque
import json
import logging
import uuid

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from flask_migrate import Migrate
except ImportError:
    class Migrate:
        def init_app(self, *args, **kwargs):
            return None

db = SQLAlchemy()
migrate = Migrate()
_rate_buckets = defaultdict(deque)


def create_app(config_object=None):
    load_dotenv()
    from .config import Config

    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object or Config)
    configure_logging(app)
    validate_production_config(app)
    proxy_count = int(app.config.get("TRUST_PROXY_COUNT", 1))
    if proxy_count:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=proxy_count)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    db.init_app(app)
    migrate.init_app(app, db)

    from .routes import LOGIN_FAILURES, PUBLIC_INTERVIEW_REQUESTS, api
    from .cli import register_cli

    if app.config.get("TESTING"):
        LOGIN_FAILURES.clear()
        PUBLIC_INTERVIEW_REQUESTS.clear()

    app.register_blueprint(api, url_prefix="/api")
    register_cli(app)

    @app.before_request
    def attach_request_id():
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_id = request_id[:64]
        g.request_started_at = time()

    @app.before_request
    def apply_rate_limit():
        if not app.config.get("RATE_LIMIT_ENABLED", True) or app.config.get("TESTING"):
            return None
        if request.path in {"/health", "/healthz"}:
            return None
        limit = int(app.config.get("RATE_LIMIT_PER_MINUTE", 120))
        now = time()
        key = f"{request.remote_addr or 'unknown'}:{request.path}"
        bucket = _rate_buckets[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return jsonify({"error": "请求过于频繁，请稍后再试", "code": "RATE_LIMITED", "details": {}, "request_id": g.request_id}), 429
        bucket.append(now)
        return None

    @app.after_request
    def add_security_headers(response):
        if app.config.get("SECURITY_HEADERS_ENABLED", True):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
            if request.is_secure:
                response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
        write_access_log(app, response)
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_payload_too_large(exc):
        return jsonify({"error": "上传内容超过大小限制", "code": "PAYLOAD_TOO_LARGE", "details": {}, "request_id": getattr(g, "request_id", "")}), 413

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        return jsonify({"error": exc.description or "请求失败", "code": exc.name.upper().replace(" ", "_"), "details": {}, "request_id": getattr(g, "request_id", "")}), exc.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        app.logger.exception("Unhandled request error", extra={"request_id": getattr(g, "request_id", "")})
        return jsonify({"error": "服务器内部错误", "code": "INTERNAL_SERVER_ERROR", "details": {}, "request_id": getattr(g, "request_id", "")}), 500

    @app.get("/health")
    @app.get("/healthz")
    def health():
        db_status = "ok"
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            db_status = "error"
        status_code = 200 if db_status == "ok" else 503
        return jsonify({"status": db_status, "service": app.config["APP_NAME"], "environment": app.config["ENVIRONMENT"]}), status_code

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        if path and (dist / path).exists():
            return send_from_directory(dist, path)
        if (dist / "index.html").exists():
            return send_from_directory(dist, "index.html")
        return jsonify({"message": "Frontend is not built yet. Run npm run dev in frontend."})

    with app.app_context():
        if app.config["AUTO_CREATE_DB"]:
            db.create_all()
            ensure_sqlite_schema()
        if app.config["AUTO_CREATE_DB"] and app.config["SEED_DEMO_DATA"]:
            from .seed import seed_demo_data, sync_plain_profile_fields

            seed_demo_data()
            sync_plain_profile_fields()

    return app


def ensure_sqlite_schema():
    if db.engine.dialect.name != "sqlite":
        return
    columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(interview_assignment)")).fetchall()]
    if "ai_plan" not in columns:
        db.session.execute(text("ALTER TABLE interview_assignment ADD COLUMN ai_plan JSON NOT NULL DEFAULT '{}'"))
        db.session.commit()


def configure_logging(app):
    logging.basicConfig(level=getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO))


def write_access_log(app, response):
    if not app.config.get("ACCESS_LOG_ENABLED", True):
        return
    duration_ms = int((time() - getattr(g, "request_started_at", time())) * 1000)
    slow_ms = int(app.config.get("SLOW_REQUEST_MS", 1000))
    payload = {
        "event": "request.completed",
        "request_id": getattr(g, "request_id", ""),
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "slow": duration_ms >= slow_ms,
        "remote_addr": request.remote_addr or "",
        "user_agent": (request.user_agent.string or "")[:200],
    }
    app.logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def validate_production_config(app):
    if app.config.get("TESTING"):
        return
    if app.config["ENVIRONMENT"].lower() != "production":
        return
    problems = [item["message"] for item in production_config_checks(app) if not item["ok"] and item["severity"] == "error"]
    if problems:
        raise RuntimeError("生产配置不安全：" + "；".join(problems))


def production_config_checks(app):
    checks = []

    def add(key, ok, message, severity="error"):
        checks.append({"key": key, "ok": bool(ok), "message": message, "severity": severity})

    database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    add("environment", app.config["ENVIRONMENT"].lower() == "production", "ENVIRONMENT 应设置为 production", "warning")
    add("jwt_secret", app.config["JWT_SECRET"] not in {"demo-secret", "test-secret"} and len(app.config["JWT_SECRET"]) >= 32, "JWT_SECRET 必须替换为至少 32 位随机字符串")
    add("cors_origins", app.config["CORS_ORIGINS"] != ["*"], "生产环境 CORS_ORIGINS 不能使用 *")
    add("database", not database_uri.startswith("sqlite"), "生产环境必须使用 PostgreSQL/MySQL，不能使用 SQLite")
    add("seed_demo_data", not app.config["SEED_DEMO_DATA"], "生产环境必须设置 SEED_DEMO_DATA=false")
    add("auto_create_db", not app.config["AUTO_CREATE_DB"], "生产环境必须设置 AUTO_CREATE_DB=false，并使用数据库迁移")
    add("rate_limit", app.config.get("RATE_LIMIT_ENABLED", True), "公网环境需要开启 RATE_LIMIT_ENABLED")
    add("security_headers", app.config.get("SECURITY_HEADERS_ENABLED", True), "公网环境需要开启 SECURITY_HEADERS_ENABLED")
    add("llm_key", (not app.config.get("LLM_ENABLED")) or bool(app.config.get("DEEPSEEK_API_KEY")), "启用大模型时必须配置生产 API Key")
    add(
        "llm_budget_limits",
        (not app.config.get("LLM_ENABLED")) or app.config.get("LLM_DAILY_CALL_LIMIT", 0) > 0 or app.config.get("LLM_DAILY_COST_LIMIT_USD", 0) > 0,
        "建议配置 LLM_DAILY_CALL_LIMIT 或 LLM_DAILY_COST_LIMIT_USD，避免上线后 AI 调用失控",
        "warning",
    )
    add("upload_folder", bool(app.config.get("UPLOAD_FOLDER")), "必须配置 UPLOAD_FOLDER")
    add("backup_folder", bool(app.config.get("BACKUP_FOLDER")), "必须配置 BACKUP_FOLDER")
    return checks
