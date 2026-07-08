import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from sqlalchemy import Date, DateTime, func, inspect, select
from sqlalchemy.engine import make_url

from . import db
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
