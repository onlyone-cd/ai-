# HireInsight AI 招聘管理系统

HireInsight 是一个面向招聘与组织人才盘点的 AI 管理系统，覆盖外部招聘、BOSS 半自动同步、AI 面试、Offer、BI、AI Agent，以及公司内部人才分析。

技术栈：

- 后端：Flask、SQLAlchemy、Flask-Migrate/Alembic、JWT、RBAC
- 前端：React、TypeScript、Vite、Tailwind CSS、Ant Design
- AI：DeepSeek 兼容接口，支持简历解析、JD 生成、面试追问、Agent 工具调用
- 部署：Docker、Docker Compose、PostgreSQL、Nginx

## 当前状态

项目已进入上线准备阶段。主流程功能基本完整，但正式上线前仍建议继续完善 BOSS 真实同步链路、薪资权限脱敏、AI 面试语音能力、E2E 自动化测试和生产监控告警。

最近已补齐：

- 生产环境预检脚本：`scripts/preflight_production.py`
- Docker 启动前配置检查、数据库连通检查、迁移 head 检查
- 内部人才组织架构、员工台账导入、薪资导入、岗位匹配、分析报告导出
- 多文件/ZIP 简历上传
- GitHub Actions：密钥扫描、后端测试、前端构建、预检脚本语法检查

## 核心功能

- 用户与权限：JWT 登录、RBAC、管理员用户管理、登录失败锁定
- 人才库：多文件/ZIP 简历上传、解析、标签库、经验档位、候选人详情、重解析、导出
- 岗位管理：岗位 CRUD、AI 生成 JD、AI 校准 JD、技能权重、关闭/恢复岗位
- 人岗匹配：匹配预览、正式匹配、低于 50 分过滤、命中/缺失标签解释、加入流程
- 流程看板：阶段推进、历史记录、批量加入、流程导出
- 面试管理：面试安排、AI 面试题、候选人网页面试间、动态追问、AI 评分、报告导出
- Offer 管理：Offer 创建、状态流转、确认函导出、流程同步
- BOSS 闭环：插件下载、登录态绑定、岗位同步、候选人导入、BOSS 候选人推荐
- 内部人才：组织架构、员工台账导入、员工简历上传、薪资导入、岗位/薪资分析、调岗和替补推荐
- BI 看板：招聘漏斗、来源质量、经验分布、流程概览
- AI Agent：自然语言查询人才、岗位、匹配、流程、面试、Offer、BOSS、BI、用户和内部人才数据
- 运维能力：健康检查、结构化访问日志、审计日志、后台任务、数据清理、备份/恢复脚本

## 本地开发

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

前端：

```powershell
cd frontend
pnpm install
pnpm run dev
```

默认地址：

- 前端开发服务：http://localhost:5173
- 后端 API / 同源生产预览：http://localhost:5001

开发默认账号：

- 用户名：`admin`
- 密码：`admin123`

如果先执行前端构建，Flask 可以直接托管前端产物：

```powershell
cd frontend
pnpm run build
cd ..\backend
.\.venv\Scripts\python run.py
```

然后访问：http://localhost:5001

## 生产部署

推荐使用 Docker Compose + PostgreSQL + Nginx + HTTPS。

完整部署说明见：

- [DEPLOYMENT.md](DEPLOYMENT.md)
- [docs/production-preflight.md](docs/production-preflight.md)

基础步骤：

```bash
cp .env.example .env
# 修改 JWT_SECRET、POSTGRES_PASSWORD、DATABASE_URL、CORS_ORIGINS、DEEPSEEK_API_KEY
docker compose -f docker-compose.production.yml --env-file .env up -d --build
```

生产环境必须满足：

- `ENVIRONMENT=production`
- `JWT_SECRET` 替换为至少 32 位随机字符串
- `CORS_ORIGINS` 不能使用 `*`
- `DATABASE_URL` 使用 PostgreSQL/MySQL，不能使用 SQLite
- `SEED_DEMO_DATA=false`
- `AUTO_CREATE_DB=false`
- `DEEPSEEK_API_KEY` 不得提交到 Git 仓库

容器启动时会自动执行：

```bash
python /app/scripts/preflight_production.py
flask --app run db upgrade
python /app/scripts/preflight_production.py --require-migration-head
```

只有配置、数据库连接和 Alembic 迁移状态都通过后，才会启动应用。

## 常用命令

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

前端构建：

```powershell
cd frontend
pnpm run build
```

密钥扫描：

```powershell
python scripts\check_secrets.py
```

生产预检：

```powershell
.\backend\.venv\Scripts\python.exe scripts\preflight_production.py
```

创建生产管理员：

```bash
docker compose -f docker-compose.production.yml --env-file .env exec app \
  flask --app run create-admin --username admin --name 系统管理员
```

备份：

```powershell
.\scripts\backup-production.ps1
```

恢复：

```powershell
.\scripts\restore-production.ps1 -DatabaseBackup .\backups\hireinsight-db.sql -UploadsBackup .\backups\hireinsight-uploads.tar
```

## 目录结构

```text
backend/                    Flask API、模型、迁移、解析与匹配逻辑
backend/migrations/          Alembic 数据库迁移
frontend/                   React + TypeScript 前端
base_agent/                 技能标签库与分类数据
browser_extension/          BOSS 浏览器插件
docs/                       业务与生产说明文档
scripts/                    密钥扫描、预检、备份、恢复、Smoke 测试脚本
deploy/                     Nginx 示例配置
.github/workflows/ci.yml    CI 流水线
```

## 重要接口概览

- `POST /api/auth/login`
- `GET /api/system/readiness`
- `GET /api/system/llm/status`
- `GET /api/system/llm/usage`：AI 调用、成本、失败率与阈值告警
- `GET /api/candidates`
- `POST /api/resume/upload`
- `POST /api/resume/<id>/retry-parse`
- `GET /api/jobs`
- `POST /api/jobs/ai-generate`
- `POST /api/jobs/<id>/match`
- `POST /api/jobs/<id>/batch-pipeline`
- `GET /api/pipeline/<job_id>/board`
- `POST /api/interview/assignments`
- `POST /api/interview/assignments/<id>/room-link`
- `POST /api/public/interview-room/<token>/complete`
- `GET /api/offers`
- `GET /api/boss/status`
- `POST /api/boss/candidates/batch-import`
- `POST /api/boss/jobs/batch-import`
- `GET /api/organization/tree`
- `POST /api/employees/import-excel`
- `POST /api/employees/batch-analyze`
- `GET /api/employees/<id>/report.txt`
- `POST /api/agent/chat`

## 上线前仍建议补齐

- BOSS 插件真实页面采集的稳定性、重试和导入日志
- AI 面试正式 ASR/TTS 接入、设备检测、异常恢复
- Redis/Celery 或更稳定的后台任务队列
- 对象存储或专用文件服务
- 前端 Playwright/E2E 自动化测试
- 集中日志、错误告警与告警通知渠道

## 已具备的上线保护

- 内部员工薪资按角色脱敏，员工薪资导出仅管理员/经理可用
- AI 调用量、成本、失败率阈值告警，生产环境建议配置 `LLM_DAILY_CALL_LIMIT`、`LLM_DAILY_COST_LIMIT_USD`、`LLM_FAILURE_RATE_WARN_PERCENT`
