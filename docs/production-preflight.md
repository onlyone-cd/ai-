# Production Preflight

This project now runs production preflight checks before serving traffic.

Container startup sequence:

```bash
python /app/scripts/preflight_production.py
flask --app run db upgrade
python /app/scripts/preflight_production.py --require-migration-head
gunicorn -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-5001} run:app
```

The first check validates production safety settings and database connectivity. The second check fails startup if the database Alembic revision is not at the latest migration head.

Run manually before switching traffic:

```bash
docker compose -f docker-compose.production.yml --env-file .env exec app \
  python /app/scripts/preflight_production.py --require-migration-head
```

The check fails when:

- production config still uses demo JWT secrets
- production CORS is `*`
- production database is SQLite
- demo seed data is enabled
- automatic schema creation is enabled in production
- the database is unreachable
- `--require-migration-head` is passed and Alembic is not at the latest head
