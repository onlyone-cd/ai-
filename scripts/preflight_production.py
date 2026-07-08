import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def app_context():
    from app import create_app

    app = create_app()
    return app, app.app_context()


def check_database_connection():
    from app import db

    db.session.execute(text("SELECT 1"))


def migration_status():
    from alembic.config import Config as AlembicConfig
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from app import db

    config = AlembicConfig(str(BACKEND / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = set(script.get_heads())
    with db.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current = set(context.get_current_heads())
    return {"current": sorted(current), "heads": sorted(heads), "at_head": current == heads}


def main():
    parser = argparse.ArgumentParser(description="Production preflight checks for HireInsight.")
    parser.add_argument("--require-migration-head", action="store_true", help="Fail unless the database alembic revision is at the latest head.")
    args = parser.parse_args()

    try:
        app, context = app_context()
        with context:
            check_database_connection()
            status = migration_status()
            from app.ops_service import build_deploy_gate_report

            deploy_gates = build_deploy_gate_report(status)
            payload = {
                "ok": True,
                "environment": app.config.get("ENVIRONMENT"),
                "database": app.config.get("SQLALCHEMY_DATABASE_URI", "").split("@")[-1],
                "migration": status,
                "deploy_gates": deploy_gates["summary"],
            }
            if args.require_migration_head and not status["at_head"]:
                payload["ok"] = False
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 2
            if str(app.config.get("ENVIRONMENT") or "").lower() == "production" and deploy_gates["summary"]["errors"] > 0:
                payload["ok"] = False
                payload["failed_gates"] = [gate for gate in deploy_gates["gates"] if not gate["ok"] and gate["severity"] == "error"]
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 2
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
