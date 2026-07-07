import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_SOURCE_DB = BACKEND / "instance" / "hireinsight_demo.db"
DEFAULT_SOURCE_UPLOADS = BACKEND / "instance" / "uploads"
DEFAULT_PACKAGE_DIR = ROOT / "backups"
CONFIRM_PHRASE = "MIGRATE_ALL_DATA"

sys.path.insert(0, str(BACKEND))
from app import db  # noqa: E402
import app.models  # noqa: F401,E402


def app_tables():
    return [table for table in db.metadata.sorted_tables if table.name != "alembic_version"]


def read_env_file(path: str | None):
    values = {}
    if not path:
        return values
    env_path = Path(path)
    if not env_path.exists():
        raise RuntimeError(f"env file not found: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, raw = value.split("=", 1)
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def default_source_database_url():
    return "sqlite:///" + DEFAULT_SOURCE_DB.resolve().as_posix()


def resolve_source_upload_dir(value: str | None):
    if not value:
        return DEFAULT_SOURCE_UPLOADS
    path = Path(value)
    if path.is_absolute():
        return path
    instance_path = BACKEND / "instance" / path
    return instance_path if instance_path.exists() else (ROOT / path)


def redact_database_url(database_url: str):
    try:
        return str(make_url(database_url).render_as_string(hide_password=True))
    except Exception:
        return "<invalid database url>"


def require_confirm(apply: bool, confirm: str | None):
    if not apply:
        return
    if confirm != CONFIRM_PHRASE:
        raise RuntimeError(f"destructive import requires --confirm-overwrite {CONFIRM_PHRASE}")


def ensure_postgres_url(database_url: str):
    backend = make_url(database_url).get_backend_name()
    if backend != "postgresql":
        raise RuntimeError("target database must be PostgreSQL")


def create_db_engine(database_url: str):
    return create_engine(database_url, future=True)


def encode_value(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def decode_value(column, value: Any):
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date) and not isinstance(column.type, DateTime) and isinstance(value, str):
        return date.fromisoformat(value)
    return value


def count_rows(connection, table):
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def export_database(source_database_url: str):
    engine = create_db_engine(source_database_url)
    tables = app_tables()
    payload = {}
    counts = {}
    with engine.connect() as connection:
        source_tables = set(inspect(connection).get_table_names())
        for table in tables:
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


def add_uploads_to_package(archive: zipfile.ZipFile, upload_dir: Path):
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


def export_package(args):
    source_database_url = args.source_database_url or os.getenv("DATABASE_URL") or default_source_database_url()
    source_upload_dir = resolve_source_upload_dir(args.source_upload_dir)
    output = Path(args.output) if args.output else default_package_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    data, counts = export_database(source_database_url)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_database": redact_database_url(source_database_url),
        "source_upload_dir": str(source_upload_dir),
        "tables": counts,
        "format": "hireinsight-full-migration-v1",
    }

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        upload_count, upload_bytes = add_uploads_to_package(archive, source_upload_dir)
        manifest["uploads"] = {"files": upload_count, "bytes": upload_bytes}
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(json.dumps({"ok": True, "package": str(output), "tables": counts, "uploads": manifest["uploads"]}, ensure_ascii=False, indent=2))
    return output


def default_package_path():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_PACKAGE_DIR / f"hireinsight-full-migration-{timestamp}.zip"


def load_package(package_path: Path):
    with zipfile.ZipFile(package_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        data = json.loads(archive.read("data.json").decode("utf-8"))
    if manifest.get("format") != "hireinsight-full-migration-v1":
        raise RuntimeError("unsupported migration package")
    return manifest, data


def validate_target_schema(connection):
    target_tables = set(inspect(connection).get_table_names())
    missing = [table.name for table in app_tables() if table.name not in target_tables]
    if missing:
        raise RuntimeError(f"target database is missing tables: {', '.join(missing)}. Run Alembic migrations first.")


def target_counts(connection):
    return {table.name: count_rows(connection, table) for table in app_tables()}


def truncate_app_tables(connection):
    preparer = connection.dialect.identifier_preparer
    names = ", ".join(preparer.quote(table.name) for table in app_tables())
    connection.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


def insert_rows(connection, table, rows):
    if not rows:
        return
    columns = {column.name: column for column in table.columns}
    decoded = [{key: decode_value(columns[key], value) for key, value in row.items() if key in columns} for row in rows]
    chunk_size = 500
    for start in range(0, len(decoded), chunk_size):
        connection.execute(table.insert(), decoded[start : start + chunk_size])


def reset_postgres_sequences(connection):
    for table in app_tables():
        for column in table.primary_key.columns:
            if not getattr(column, "autoincrement", False):
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar()
            if not sequence_name:
                continue
            max_value = connection.execute(select(func.max(column))).scalar() or 0
            next_value = int(max_value) + 1
            connection.execute(text("SELECT setval(:sequence_name, :next_value, false)"), {"sequence_name": sequence_name, "next_value": next_value})


def replace_uploads(package_path: Path, target_upload_dir: Path):
    target_upload_dir.mkdir(parents=True, exist_ok=True)
    for child in target_upload_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    with zipfile.ZipFile(package_path, "r") as archive:
        for item in archive.infolist():
            if not item.filename.startswith("uploads/") or item.is_dir():
                continue
            relative = Path(item.filename).relative_to("uploads")
            destination = target_upload_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def import_package(args):
    package_path = Path(args.input)
    if not package_path.exists():
        raise RuntimeError(f"migration package not found: {package_path}")
    target_database_url = args.target_database_url or os.getenv("DATABASE_URL")
    if not target_database_url:
        raise RuntimeError("target database url is required. Use --target-database-url or DATABASE_URL.")
    ensure_postgres_url(target_database_url)
    require_confirm(args.apply, args.confirm_overwrite)

    manifest, data = load_package(package_path)
    engine = create_db_engine(target_database_url)
    with engine.begin() as connection:
        validate_target_schema(connection)
        before = target_counts(connection)
        planned = {table: len(rows) for table, rows in data.items()}
        if args.apply:
            truncate_app_tables(connection)
            for table in app_tables():
                insert_rows(connection, table, data.get(table.name, []))
            reset_postgres_sequences(connection)
            after = target_counts(connection)
        else:
            after = None

    upload_summary = {"mode": "skipped"}
    if args.apply and not args.skip_uploads:
        if not args.target_upload_dir:
            raise RuntimeError("target upload dir is required unless --skip-uploads is used")
        replace_uploads(package_path, Path(args.target_upload_dir))
        upload_summary = manifest.get("uploads", {"mode": "replaced"})

    print(
        json.dumps(
            {
                "ok": True,
                "applied": bool(args.apply),
                "package": str(package_path),
                "target_database": redact_database_url(target_database_url),
                "before": before,
                "planned": planned,
                "after": after,
                "uploads": upload_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def docker_compose_command(compose_file: str, env_file: str | None, *parts: str):
    command = ["docker", "compose", "-f", compose_file]
    if env_file:
        command.extend(["--env-file", env_file])
    command.extend(parts)
    return command


def import_package_in_compose(package_path: Path, args):
    require_confirm(args.apply, args.confirm_overwrite)
    if not args.apply:
        raise RuntimeError("compose import is only used for --apply migrations")
    remote_package = "/tmp/hireinsight-full-migration.zip"
    service = args.target_compose_service
    compose_file = args.target_compose_file
    env_file = args.target_env_file

    subprocess.run(docker_compose_command(compose_file, env_file, "cp", str(package_path), f"{service}:{remote_package}"), check=True)
    import_command = [
        "exec",
        "-T",
        service,
        "python",
        "/app/scripts/full_data_migration.py",
        "import",
        "--input",
        remote_package,
        "--target-upload-dir",
        "/data/uploads",
        "--apply",
        "--confirm-overwrite",
        CONFIRM_PHRASE,
    ]
    if args.skip_uploads:
        import_command.append("--skip-uploads")
    try:
        subprocess.run(docker_compose_command(compose_file, env_file, *import_command), check=True)
    finally:
        subprocess.run(docker_compose_command(compose_file, env_file, "exec", "-T", service, "rm", "-f", remote_package), check=False)


def migrate(args):
    package_path = export_package(args)
    if args.target_compose_file:
        import_package_in_compose(package_path, args)
        return
    import_args = argparse.Namespace(
        input=str(package_path),
        target_database_url=args.target_database_url,
        target_upload_dir=args.target_upload_dir,
        apply=args.apply,
        confirm_overwrite=args.confirm_overwrite,
        skip_uploads=args.skip_uploads,
    )
    import_package(import_args)


def add_source_args(parser):
    parser.add_argument("--source-database-url", help="Source test database URL. Defaults to backend/instance/hireinsight_demo.db.")
    parser.add_argument("--source-upload-dir", help="Source upload directory. Defaults to backend/instance/uploads.")
    parser.add_argument("--source-env-file", help="Optional env file used to read source DATABASE_URL.")


def add_import_args(parser):
    parser.add_argument("--target-database-url", help="Target PostgreSQL URL. Defaults to DATABASE_URL.")
    parser.add_argument("--target-upload-dir", help="Target uploads directory. Required unless --skip-uploads is used.")
    parser.add_argument("--apply", action="store_true", help="Actually overwrite target data. Without this flag the command is dry-run.")
    parser.add_argument("--confirm-overwrite", help=f"Required for --apply. Must be {CONFIRM_PHRASE}.")
    parser.add_argument("--skip-uploads", action="store_true", help="Only migrate database rows; do not replace uploaded files.")


def build_parser():
    parser = argparse.ArgumentParser(description="Full test-to-production data migration for HireInsight.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export source database and uploads into a zip package.")
    add_source_args(export_parser)
    export_parser.add_argument("--output", help="Output zip path. Defaults to backups/hireinsight-full-migration-*.zip.")

    import_parser = subparsers.add_parser("import", help="Import a migration package into PostgreSQL.")
    import_parser.add_argument("--input", required=True, help="Migration package zip path.")
    import_parser.add_argument("--target-env-file", help="Optional env file used to read target DATABASE_URL.")
    add_import_args(import_parser)

    migrate_parser = subparsers.add_parser("migrate", help="Export source and import into target in one command.")
    add_source_args(migrate_parser)
    migrate_parser.add_argument("--output", help="Optional package path to keep after migration.")
    migrate_parser.add_argument("--target-env-file", help="Optional env file used to read target DATABASE_URL.")
    add_import_args(migrate_parser)
    migrate_parser.add_argument("--target-compose-file", help="Docker Compose file. If set, import runs inside the app container.")
    migrate_parser.add_argument("--target-compose-service", default="app", help="Compose service used for in-container import.")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    source_env = read_env_file(getattr(args, "source_env_file", None))
    target_env = read_env_file(getattr(args, "target_env_file", None))
    if hasattr(args, "source_database_url") and not args.source_database_url:
        args.source_database_url = source_env.get("DATABASE_URL")
    if hasattr(args, "source_upload_dir") and not args.source_upload_dir:
        args.source_upload_dir = source_env.get("UPLOAD_FOLDER")
    if hasattr(args, "target_database_url") and not args.target_database_url:
        args.target_database_url = target_env.get("DATABASE_URL")
    if hasattr(args, "target_upload_dir") and not args.target_upload_dir:
        args.target_upload_dir = target_env.get("UPLOAD_FOLDER")
    try:
        if args.command == "export":
            export_package(args)
        elif args.command == "import":
            import_package(args)
        elif args.command == "migrate":
            migrate(args)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
