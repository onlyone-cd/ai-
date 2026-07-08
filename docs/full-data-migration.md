# Full Data Migration

This script moves a complete test environment into a production PostgreSQL
database. It exports application tables and uploaded resume files into a zip
package, then imports that package into PostgreSQL.

The generated package contains sensitive business data. It is written under
`backups/` by default, and that directory is ignored by Git.

## What It Migrates

- Users and RBAC data
- Candidates, resume text, tags, matches, pipeline history
- Jobs and JD structures
- Interviews, feedback, offers
- BOSS accounts, drafts, sync jobs and sync item logs
- Organization units, employees, compensation, employee analyses and recommendations
- Background tasks, LLM usage, audit logs
- Uploaded files from the source upload directory

## Safety Rules

Importing is destructive. The target application tables are truncated before
rows are inserted. The script will not modify the target unless both flags are
present:

```powershell
--apply --confirm-overwrite MIGRATE_ALL_DATA
```

Run `flask --app run db upgrade` on production before importing.

## Recommended Docker Compose Migration

This is the safest option for the current production compose setup because
PostgreSQL does not need to expose port `5432` to the host.

```powershell
.\backend\.venv\Scripts\python.exe scripts\full_data_migration.py migrate `
  --source-database-url "sqlite:///C:/Users/PC/Documents/AI-agent/backend/instance/hireinsight_demo.db" `
  --source-upload-dir "C:/Users/PC/Documents/AI-agent/backend/instance/uploads" `
  --target-compose-file docker-compose.production.yml `
  --target-env-file .env `
  --apply `
  --confirm-overwrite MIGRATE_ALL_DATA
```

The command exports the local test database into `backups/`, copies the package
into the production `app` container, imports into the container's `DATABASE_URL`,
and replaces `/data/uploads`.

## Direct PostgreSQL Migration

Use this when the target PostgreSQL database is reachable from the machine
running the script.

```powershell
.\backend\.venv\Scripts\python.exe scripts\full_data_migration.py migrate `
  --source-database-url "sqlite:///C:/Users/PC/Documents/AI-agent/backend/instance/hireinsight_demo.db" `
  --source-upload-dir "C:/Users/PC/Documents/AI-agent/backend/instance/uploads" `
  --target-database-url "postgresql+psycopg://hireinsight:password@host:5432/hireinsight" `
  --target-upload-dir "D:/hireinsight/uploads" `
  --apply `
  --confirm-overwrite MIGRATE_ALL_DATA
```

## Dry Run

Omit `--apply` to inspect the package and planned row counts without changing
production:

```powershell
.\backend\.venv\Scripts\python.exe scripts\full_data_migration.py migrate `
  --target-database-url "postgresql+psycopg://hireinsight:password@host:5432/hireinsight" `
  --target-upload-dir "D:/hireinsight/uploads"
```

## Two-Step Export And Import

```powershell
.\backend\.venv\Scripts\python.exe scripts\full_data_migration.py export `
  --output backups\migration-package.zip

.\backend\.venv\Scripts\python.exe scripts\full_data_migration.py import `
  --input backups\migration-package.zip `
  --target-database-url "postgresql+psycopg://hireinsight:password@host:5432/hireinsight" `
  --target-upload-dir "D:/hireinsight/uploads" `
  --apply `
  --confirm-overwrite MIGRATE_ALL_DATA
```

## Post-Migration Checks

```powershell
.\backend\.venv\Scripts\python.exe scripts\preflight_production.py --require-migration-head
python scripts\smoke_api.py --base-url https://your-domain.example --username admin --password your-password
```
