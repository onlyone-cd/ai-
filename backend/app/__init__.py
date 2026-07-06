from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()


def create_app(config_object=None):
    load_dotenv()
    from .config import Config

    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object or Config)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    db.init_app(app)

    from .routes import api

    app.register_blueprint(api, url_prefix="/api")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "hireinsight-demo"}

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
        db.create_all()
        ensure_sqlite_schema()
        if app.config["SEED_DEMO_DATA"]:
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
