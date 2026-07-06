# 生产部署清单

## 阿里云 Ubuntu 24.04 64 位部署

推荐使用 Docker Compose 部署，应用、后台 worker 和 PostgreSQL 都由 `docker-compose.production.yml` 管理；Nginx 和 HTTPS 放在宿主机，方便接入阿里云安全组和证书续期。

### 服务器和安全组

- ECS 系统：Ubuntu 24.04 64 位。
- 建议规格：至少 2 vCPU / 4 GB 内存；简历批量解析或 AI 面试较多时建议 4 vCPU / 8 GB。
- 系统盘：至少 40 GB；上传简历较多时挂载独立数据盘并备份 `uploads` volume。
- 阿里云安全组放行：`22/tcp`、`80/tcp`、`443/tcp`。
- `5001/tcp` 只给本机 Nginx 反代使用，生产不要在安全组公网放行。

### 安装系统依赖

```bash
sudo apt update
sudo apt install -y git curl ca-certificates openssl nginx certbot python3-certbot-nginx docker.io docker-compose-v2
sudo systemctl enable --now docker nginx
sudo usermod -aG docker "$USER"
```

执行 `usermod` 后重新登录 SSH，让当前用户获得 Docker 权限。也可以继续在命令前加 `sudo`。

### 拉取代码

```bash
sudo mkdir -p /opt/hireinsight
sudo chown "$USER":"$USER" /opt/hireinsight
git clone git@github.com:onlyone-cd/ai-.git /opt/hireinsight
cd /opt/hireinsight
```

如果服务器未配置 GitHub SSH Key，也可以使用 HTTPS 地址克隆。

### 配置生产环境变量

```bash
cp .env.example .env
openssl rand -hex 32
openssl rand -base64 32
nano .env
```

上线前至少修改这些值：

- `JWT_SECRET`：使用 `openssl rand -hex 32` 生成。
- `POSTGRES_PASSWORD`：使用强密码，需和 `DATABASE_URL` 中的密码一致。
- `DATABASE_URL`：Docker Compose 内部地址保持 `postgres:5432`，只替换密码即可。
- `CORS_ORIGINS`：改成你的正式域名，例如 `https://hr.example.com`。
- `DEEPSEEK_API_KEY`：填新的生产 Key，不要把真实 Key 提交到 Git。
- `SEED_DEMO_DATA=false`、`AUTO_CREATE_DB=false`：生产保持关闭。

### 构建并启动

```bash
docker compose -f docker-compose.production.yml --env-file .env up -d --build
docker compose -f docker-compose.production.yml --env-file .env ps
docker compose -f docker-compose.production.yml --env-file .env logs -f app
```

首次启动后创建管理员：

```bash
docker compose -f docker-compose.production.yml --env-file .env exec app \
  flask --app run create-admin --username admin --name 系统管理员
```

### 配置 Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/hireinsight
sudo sed -i 's/your-domain.example/hr.example.com/g' /etc/nginx/sites-available/hireinsight
sudo ln -sf /etc/nginx/sites-available/hireinsight /etc/nginx/sites-enabled/hireinsight
sudo nginx -t
sudo systemctl reload nginx
```

把 `hr.example.com` 换成你的真实域名，并确保域名 A 记录已经指向 ECS 公网 IP。

### 开启 HTTPS

```bash
sudo certbot --nginx -d hr.example.com
sudo certbot renew --dry-run
```

HTTPS 生效后，把 `.env` 中的 `CORS_ORIGINS` 改成 `https://hr.example.com`，然后重启服务：

```bash
docker compose -f docker-compose.production.yml --env-file .env up -d
```

### 发布新版本

```bash
cd /opt/hireinsight
git pull --ff-only
python3 scripts/check_secrets.py
docker compose -f docker-compose.production.yml --env-file .env up -d --build
docker compose -f docker-compose.production.yml --env-file .env exec app flask --app run db upgrade
curl -fsS https://hr.example.com/healthz
```

`app` 和 `worker` 容器启动时也会执行迁移；手动执行 `db upgrade` 是为了发布时更容易看到迁移错误。

### 常用运维命令

```bash
docker compose -f docker-compose.production.yml --env-file .env logs -f app
docker compose -f docker-compose.production.yml --env-file .env logs -f worker
docker compose -f docker-compose.production.yml --env-file .env restart app worker
docker compose -f docker-compose.production.yml --env-file .env exec app flask --app run prune-data
docker compose -f docker-compose.production.yml --env-file .env exec app flask --app run prune-data --confirm
```

### 备份

```bash
mkdir -p backups
docker compose -f docker-compose.production.yml --env-file .env exec -T postgres \
  pg_dump -U hireinsight hireinsight > backups/hireinsight-db-$(date +%Y%m%d-%H%M%S).sql
docker run --rm -v hireinsight_uploads:/data -v "$PWD/backups:/backups" alpine \
  tar -cf /backups/hireinsight-uploads-$(date +%Y%m%d-%H%M%S).tar -C /data .
```

建议每天至少备份一次，并同步到阿里云 OSS 或另一台服务器。

## 上线前必须修改

- 复制 `.env.example` 为 `.env`，替换 `JWT_SECRET`、`POSTGRES_PASSWORD`、`DEEPSEEK_API_KEY`、`CORS_ORIGINS` 和域名。
- DeepSeek Key 不要提交到 Git；如果曾经在聊天或代码中出现过，先到平台废弃旧 Key 并重新生成。
- 提交前可执行 `python scripts/check_secrets.py` 检查仓库内是否误包含 API Key、GitHub Token 或私钥；CI 也会自动检查。
- `SEED_DEMO_DATA=false`，避免生产库写入演示数据。
- 登录失败锁定由 `LOGIN_MAX_FAILURES` 和 `LOGIN_LOCKOUT_MINUTES` 控制，公网环境不要关闭。
- LLM 调用超时和重试由 `LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`、`LLM_RETRY_BACKOFF_SECONDS` 控制，状态可通过 `/api/system/llm/status` 巡检。
- LLM 用量记录由 `LLM_USAGE_LOG_ENABLED` 控制，成本估算单价由 `LLM_PROMPT_PRICE_PER_1M_TOKENS_USD`、`LLM_COMPLETION_PRICE_PER_1M_TOKENS_USD` 控制，用量可通过 `/api/system/llm/usage` 巡检。
- 候选人面试间链接有效期和公开接口限制由 `INTERVIEW_ROOM_TOKEN_HOURS`、`PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE`、`PUBLIC_INTERVIEW_MAX_ANSWER_CHARS` 控制。
- 结构化访问日志由 `ACCESS_LOG_ENABLED` 控制，慢请求阈值由 `SLOW_REQUEST_MS` 控制；生产建议接入集中日志平台并按 `request_id` 检索。
- 后台任务 worker 由 Docker Compose 的 `worker` 服务运行，轮询参数由 `TASK_WORKER_LIMIT`、`TASK_WORKER_SLEEP_SECONDS` 控制。
- 数据留存由 `AUDIT_LOG_RETENTION_DAYS`、`LLM_USAGE_RETENTION_DAYS`、`TASK_RETENTION_DAYS` 控制；上线后建议每周执行一次 `prune-data --confirm`。
- 使用 HTTPS，Nginx 前置代理后保留 `X-Forwarded-*` 请求头。

## Docker 启动

```powershell
docker compose -f docker-compose.production.yml --env-file .env up -d --build
```

`app` 和 `worker` 容器启动时会先执行数据库迁移：

```powershell
flask --app run db upgrade
```

首次部署完成后创建管理员：

```powershell
docker compose -f docker-compose.production.yml --env-file .env exec app flask --app run create-admin --username admin --name 系统管理员 --password "StrongPassword123"
```

后续重置密码：

```powershell
docker compose -f docker-compose.production.yml --env-file .env exec app flask --app run reset-password --username admin --password "NewStrongPassword123"
```

开发环境修改模型后生成迁移：

```powershell
cd backend
flask --app run db migrate -m "describe change"
flask --app run db upgrade
```

本地手动执行后台任务：

```powershell
cd backend
flask --app run run-tasks --limit 10
```

预览和执行过期数据清理：

```powershell
cd backend
flask --app run prune-data
flask --app run prune-data --confirm
```

## 健康检查

```powershell
curl https://your-domain.example/healthz
```

返回 `status=ok` 才允许切流。

## 数据和文件

- 数据库使用 PostgreSQL，生产不要使用 SQLite。
- 生产环境设置 `AUTO_CREATE_DB=false`，只能通过迁移升级 schema。
- 新版本发布前先备份，再执行 `flask --app run db upgrade`，索引迁移可能在大数据量时耗时。
- 生产首个管理员使用 `flask --app run create-admin` 创建，不再依赖演示数据。
- 上传文件保存在 `uploads` volume，需配置定期备份。
- 简历、面试报告、导出文件都属于敏感数据，下载和导出只能给授权角色。
- 批量 CSV 导出仅允许 admin/manager；人才库详情和简历下载仅允许 admin/manager/recruiter。
- BOSS、AI Agent、BI、Offer、流程总览等业务接口限制为 admin/manager/recruiter，interviewer 只能处理分配给自己的面试相关能力。
- 列表接口已支持 `limit`/`offset` 分页；公网环境前端和第三方调用不要使用超大页大小，避免拖慢数据库。
- 候选人详情查看、简历/面试/Offer/CSV 导出会写入审计日志，上线后需定期巡检异常导出行为。
- 访问日志不记录请求体和完整查询参数，避免简历、手机号、Token 等敏感内容进入日志。
- LLM 用量记录不保存 Prompt 和模型响应正文，只保存 Token、耗时、状态、request_id、调用来源、工具名和 API 路径。

## 备份和恢复

备份 PostgreSQL 和上传文件：

```powershell
.\scripts\backup-production.ps1
```

恢复前请确认目标环境可以被覆盖：

```powershell
.\scripts\restore-production.ps1 -DatabaseBackup .\backups\hireinsight-db-YYYYMMDD-HHMMSS.sql -UploadsBackup .\backups\hireinsight-uploads-YYYYMMDD-HHMMSS.tar
```

建议至少每天备份一次，并把备份文件同步到独立存储。

## 当前仍需继续补齐

- 对象存储或专用文件服务。
- Redis/Celery 高吞吐任务队列，用于替换当前数据库轻量任务队列，承载更大规模的批量简历解析、AI 评分和 BOSS 批量同步。
- 集中日志、错误告警和 AI 费用阈值告警。
- E2E 自动化测试和正式发布流水线。
