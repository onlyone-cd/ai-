FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5001
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt gunicorn psycopg[binary]
COPY backend/ /app/backend/
COPY base_agent/ /app/base_agent/
COPY browser_extension/ /app/browser_extension/
COPY scripts/ /app/scripts/
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN mkdir -p /data/uploads
WORKDIR /app/backend
EXPOSE 5001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://127.0.0.1:${PORT}/healthz || exit 1
CMD ["sh", "-c", "python /app/scripts/preflight_production.py && flask --app run db upgrade && python /app/scripts/preflight_production.py --require-migration-head && gunicorn -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-5001} run:app"]
