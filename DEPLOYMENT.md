# 生产部署清单

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
- LLM 用量记录不保存 Prompt 和模型响应正文，只保存 Token、耗时、状态和 request_id。

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
