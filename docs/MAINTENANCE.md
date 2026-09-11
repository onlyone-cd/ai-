# HireInsight — 运维与维护文档

> 本文档面向系统管理员和运维人员，涵盖部署、备份、迁移、监控、故障排查等。

---

## 1. 部署方式

### 1.1 生产环境（推荐：Docker Compose）

仓库内的 Dockerfile、PostgreSQL、应用、后台 worker、迁移和健康检查已经形成完整部署链路，生产环境优先使用：

```bash
docker compose -f docker-compose.production.yml --env-file .env up -d --build
```

详细步骤见项目根目录的 `DEPLOYMENT.md`。

### 1.2 可选部署：systemd + venv

```bash
# 首次部署
git clone git@github.com:onlyone-cd/ai-.git /opt/hireinsight
cd /opt/hireinsight
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt gunicorn
cp .env.example .env  # 修改配置
cd backend && flask --app run db upgrade

# systemd 服务配置
# /etc/systemd/system/hireinsight.service
# /etc/systemd/system/hireinsight-worker.service
systemctl daemon-reload
systemctl enable --now hireinsight.service hireinsight-worker.service
```

### 1.3 更新部署

```bash
cd /opt/hireinsight
git pull origin main
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
flask --app run db upgrade
systemctl restart hireinsight.service hireinsight-worker.service
```

systemd 更新命令只适用于自行维护了服务文件的部署；本仓库的默认生产发布流程以 Docker Compose 为准。

### 1.4 前端构建

```bash
cd frontend
npm install
npm run build
# 构建产物在 frontend/dist/，Flask 会自动 serve
```

---

## 2. 环境变量配置

### 2.1 必须配置

| 变量 | 说明 | 生产建议 |
|------|------|---------|
| `ENVIRONMENT` | 运行环境 | `production` |
| `JWT_SECRET` | JWT 密钥 | 至少 32 位随机字符串 |
| `DATABASE_URL` | 数据库连接 | `postgresql+psycopg://user:pass@host:5432/hireinsight` |
| `CORS_ORIGINS` | 跨域来源 | 限制为具体域名 |
| `DEEPSEEK_API_KEY` | AI API Key | 生产环境必填 |
| `SEED_DEMO_DATA` | 演示数据 | `false` |
| `AUTO_CREATE_DB` | 自动建表 | `false`（使用迁移） |

### 2.2 安全配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOGIN_MAX_FAILURES` | 5 | 登录锁定阈值 |
| `LOGIN_LOCKOUT_MINUTES` | 15 | 锁定时间 |
| `RATE_LIMIT_PER_MINUTE` | 120 | 限流次数 |
| `SECURITY_HEADERS_ENABLED` | true | 安全响应头 |

### 2.3 AI 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_ENABLED` | true | 启用 AI |
| `LLM_PROVIDER` | deepseek | AI 提供商 |
| `LLM_MODEL` | deepseek-chat | 模型名称 |
| `LLM_API_URL` | https://api.deepseek.com/... | API 地址 |
| `LLM_TIMEOUT_SECONDS` | 45 | 超时时间 |
| `LLM_DAILY_CALL_LIMIT` | 0 | 每日调用上限（0=不限） |
| `LLM_DAILY_COST_LIMIT_USD` | 0 | 每日成本上限（0=不限） |

### 2.4 数据保留

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AUDIT_LOG_RETENTION_DAYS` | 365 | 审计日志保留 |
| `LLM_USAGE_RETENTION_DAYS` | 180 | LLM 用量保留 |
| `TASK_RETENTION_DAYS` | 90 | 后台任务保留 |

---

## 3. 备份与恢复

### 3.1 手动备份（Docker 环境）

```bash
# 数据库备份
docker compose -f docker-compose.production.yml --env-file .env exec -T postgres \
  pg_dump -U hireinsight hireinsight > backups/hireinsight-db-$(date +%Y%m%d-%H%M%S).sql

# 上传文件备份
docker run --rm -v hireinsight_uploads:/data -v "$PWD/backups:/backups" alpine \
  tar -cf /backups/hireinsight-uploads-$(date +%Y%m%d-%H%M%S).tar -C /data .
```

### 3.2 手动备份（systemd 环境）

```bash
# 数据库备份
pg_dump -U hireinsight hireinsight > backups/hireinsight-db-$(date +%Y%m%d-%H%M%S).sql

# 上传文件备份
tar -czf backups/hireinsight-uploads-$(date +%Y%m%d-%H%M%S).tar.gz -C /opt/hireinsight/backend/uploads .
```

### 3.3 备份脚本

Windows 备份脚本（管理员使用）：
```powershell
.\scripts\backup-production.ps1
```

### 3.4 恢复

数据库恢复：
```bash
psql -U hireinsight -d hireinsight < backups/hireinsight-db-YYYYMMDD-HHMMSS.sql
```

上传文件恢复：
```bash
tar -xf backups/hireinsight-uploads-YYYYMMDD-HHMMSS.tar -C /opt/hireinsight/backend/uploads
```

全量迁移恢复（从测试环境到生产）：
```bash
python scripts/full_data_migration.py import \
  --source-package backups/hireinsight-full-migration-*.zip \
  --target-database-url "postgresql+psycopg://hireinsight:password@host:5432/hireinsight"
```

---

## 4. 数据库迁移

```bash
cd backend
flask --app run db upgrade    # 升级到最新版本
flask --app run db downgrade  # 回滚
flask --app run db history    # 查看迁移历史
flask --app run db current    # 查看当前版本
```

创建新迁移：
```bash
flask --app run db migrate -m "description"
```

全量数据迁移（从测试环境迁移到生产 PostgreSQL）：
```bash
python scripts/full_data_migration.py \
  --source-database-url "sqlite:///backend/instance/hireinsight_demo.db" \
  --target-database-url "postgresql+psycopg://hireinsight:password@host:5432/hireinsight"
```

迁移脚本支持分步执行：`export`（导出 json 包）→ `scp` → `import`（导入到目标库）。

---

## 5. 监控与健康检查

### 5.1 健康检查端点

```bash
curl -fsS http://localhost:5001/healthz
# → {"environment":"production","service":"hireinsight","status":"ok"}
```

### 5.2 生产预检

```bash
python scripts/preflight_production.py
```

检查项目包括：环境变量、JWT 密钥强度、CORS 配置、数据库类型、演示数据、限流、安全头、LLM 密钥和预算、上传目录、备份目录。

### 5.3 烟雾测试

```bash
python scripts/smoke_api.py --base-url http://localhost:5001
```

运行一系列 API 端点测试，确保核心功能正常。

### 5.4 部署门禁

```bash
curl -H "Authorization: Bearer <token>" http://localhost:5001/api/ops/deploy-gates
```

返回所有部署门禁检查结果，包括阻断项和警告项。

### 5.5 SSH 生产健康巡检

本地可使用 `scripts/check_production.py` 通过 SSH 检查生产应用和 `/healthz`。脚本不接受明文密码，也不会自动信任未知主机；运行前必须把服务器主机密钥写入当前用户的 `known_hosts`，并使用 SSH Agent 或专用私钥：

```powershell
$env:HIREINSIGHT_SSH_HOST = "your-production-host"
$env:HIREINSIGHT_SSH_USER = "deploy"
$env:HIREINSIGHT_SSH_KEY_FILE = "C:\secure\hireinsight_ed25519"
python scripts/check_production.py
```

`HIREINSIGHT_SSH_KEY_FILE` 可省略，此时系统 OpenSSH 使用本地 SSH Agent 或默认密钥。不要使用 `root` 密码登录，不要把服务器地址、私钥或密码写入脚本或提交到 Git。

---

## 6. 日常维护任务

### 6.1 数据清理

```bash
cd backend
flask --app run prune-data --confirm
```

清理过期的审计日志、LLM 用量记录、后台任务。

### 6.2 标签质量治理

通过系统 UI 的「后台任务」页面 → 标签质量面板：
- 定期检查缺失证据、低置信度、疑似误判标签
- 批量重新解析或删除有问题的标签
- 人工确认经核实正确的标签

### 6.3 重复候选人清理

```bash
python scripts/dedupe_candidates.py
```

基于手机号、邮箱、姓名去重，保留最新/最完整的简历。

### 6.4 Nginx 日志轮转

建议配置 `logrotate` 管理 Nginx 和 Flask 日志：
```
/var/log/nginx/hireinsight-*.log {
  daily
  rotate 30
  compress
  delaycompress
  missingok
  notifempty
  postrotate
    systemctl reload nginx
  endscript
}
```

---

## 7. 故障排查指南

### 7.1 服务无法启动

```bash
systemctl status hireinsight.service
journalctl -u hireinsight.service -n 50 --no-pager
```

常见原因：
- `JWT_SECRET` 无效或太短
- 数据库连接失败
- 生产环境用了 SQLite 而非 PostgreSQL
- `CORS_ORIGINS` 配置了 `*` 被预检拦截

### 7.2 Worker 任务不执行

```bash
systemctl status hireinsight-worker.service
journalctl -u hireinsight-worker.service -n 50 --no-pager
```

检查：
- Worker 是否 active
- 数据库连接是否正常
- 任务队列中是否有排队任务（`GET /api/tasks?status=queued`）

### 7.3 BOSS 插件无法采集

- 确认 BOSS 页面已登录
- 确认插件配置的系统地址和 Token 正确
- 检查插件控制台 Console 错误日志
- 确认系统侧的 BOSS 账号状态（`GET /api/boss/status`）
- 查看同步任务明细（`GET /api/boss/sync/jobs`）了解失败原因

常见 BOSS 同步失败原因：

| 错误分类 | 含义 | 处理方式 |
|----------|------|---------|
| `boss_1092` | BOSS 接口拒绝 | 使用页面采集在线简历 |
| `auth` | 登录态失效 | 重新登录 BOSS |
| `download` | 附件下载失败 | 优先使用在线简历 |
| `not_resume` | 采集到非简历内容 | 进入候选人详情页再采集 |
| `parse` | 解析失败 | 检查原文完整性 |
| `network` | 网络超时 | 稍后重试 |

### 7.4 AI 功能异常

- 检查 `GET /api/system/llm/status` 确认 LLM 可用
- 检查 `DEEPSEEK_API_KEY` 是否正确
- 检查 `LLM_DAILY_CALL_LIMIT` 和 `LLM_DAILY_COST_LIMIT_USD` 是否超限
- 查看 `GET /api/system/llm/usage` 了解用量情况

### 7.5 数据库连接问题

```bash
# 检查数据库连接
pg_isready -U hireinsight -d hireinsight

# 检查连接数
psql -U hireinsight -c "SELECT count(*) FROM pg_stat_activity;"
```

### 7.6 504 错误

- 检查 Gunicorn worker 是否过载（`WEB_CONCURRENCY` 默认 2）
- 检查 `LLM_TIMEOUT_SECONDS` 是否太短
- 查看 Nginx 错误日志

---

## 8. 安全注意事项

1. **JWT 密钥**：生产环境必须替换为至少 32 位的随机字符串，不要使用 `demo-secret` 或 `test-secret`
2. **API Key**：不要在代码、Git 提交、聊天记录中泄露 DeepSeek API Key；如果泄露过，到平台废弃旧 Key 并重新生成
3. **CORS**：生产环境不要使用 `*`，限制为具体域名
4. **HTTPS**：生产环境使用 Nginx 前置代理 + SSL，保留 `X-Forwarded-*` 请求头
5. **敏感数据**：员工信息、简历数据为敏感数据，不要提交到 Git 仓库
6. **备份**：建议每天备份一次，并同步到阿里云 OSS 或另一台服务器
7. **定期清理**：建议每周执行 `prune-data --confirm`，避免数据库膨胀
8. **密钥检查**：提交前可执行 `python scripts/check_secrets.py` 检查密钥泄露
9. **登录锁定**：公网环境不要关闭登录锁定功能
10. **审核日志**：建议接入集中日志平台，按 `request_id` 检索

---

## 9. 生产环境拓扑

```
用户 → CDN/Cloudflare → Nginx (443) → Gunicorn (5001) → PostgreSQL
                                                    → Worker (后台任务)
                                                    → 本地文件存储 (/data/uploads)
```

**生产入口：** 使用正式 HTTPS 域名，不在仓库文档中保存真实服务器 IP。
**服务目录：** 由部署环境决定，示例使用 `/opt/hireinsight`。
**服务管理：** 推荐 Docker Compose；systemd + venv 为可选兼容方案。
**数据库：** PostgreSQL
**运行环境：** Docker 镜像内 Python 3.12；systemd 部署使用独立 venv。

---

## 10. 相关文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 系统架构
- [API.md](./API.md) — 接口文档
- [USAGE.md](./USAGE.md) — 使用文档
- [DEPLOYMENT.md](../DEPLOYMENT.md) — 部署指南
- [full-data-migration.md](./full-data-migration.md) — 全量数据迁移
- [production-preflight.md](./production-preflight.md) — 生产预检
- [internal-talent-intelligence-plan.md](./internal-talent-intelligence-plan.md) — 内部人才智能计划
- [CHANGELOG.md](../CHANGELOG.md) — 变更日志
- `README.md` — 项目介绍
- `scripts/` — 运维脚本目录
- `deploy/nginx.conf` — Nginx 配置示例
- `docker-compose.production.yml` — 生产 Docker Compose
- `.env.example` — 环境变量模板
