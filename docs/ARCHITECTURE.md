# HireInsight — 系统架构文档

## 1. 项目概述

HireInsight 是一个面向招聘与组织人才盘点的 AI 管理系统，覆盖外部招聘（BOSS 直聘自动同步/简历解析/AI 匹配/AI 面试/Offer 管理）、内部人才盘点（组织架构/员工档案/调岗匹配/薪资分析/离职替补推荐）、以及 AI Agent 智能助手。

**开发语言：** Python 3.12 (后端) + TypeScript/React 19 (前端) + JavaScript (浏览器插件)
**数据库：** 开发环境 SQLite / 生产环境 PostgreSQL
**AI 引擎：** DeepSeek API（简历解析、JD 生成、岗位匹配、AI 面试、Agent 对话）

---

## 2. 目录结构

```
AI-agent/
├── backend/                  # Flask 后端应用
│   └── app/
│       ├── __init__.py       # 应用工厂、路由注册、中间件
│       ├── config.py         # 配置管理（环境变量/默认值）
│       ├── models.py         # SQLAlchemy 数据模型（~30 个表）
│       ├── routes.py         # 核心业务 API 路由（候选人/岗位/流程/BOSS/Agent 等）
│       ├── insight_routes.py # AI 深度洞察独立 Blueprint
│       ├── insight_service.py # 漏斗/渠道/周期/面试官/Offer 洞察聚合
│       ├── auth.py           # JWT 认证、密码哈希、登录锁定
│       ├── resume_service.py # 简历上传/解析/存储/附件管理
│       ├── deepseek_resume_parser.py  # DeepSeek AI 简历解析
│       ├── tag_library.py    # 标签库（规则标签 + AI 标签合并）
│       ├── matching.py       # 岗位匹配规则引擎
│       ├── job_service.py    # 岗位管理、JD 结构化和 AI 复核
│       ├── boss_cli_service.py  # BOSS 直聘 CLI 集成
│       ├── experience_analysis.py  # 工作经验年限分析
│       ├── task_service.py   # 后台任务队列管理
│       ├── llm_client.py     # DeepSeek API 调用封装
│       ├── ops_service.py    # 运维/备份/数据完整性
│       ├── settings_service.py  # 系统设置（AI 配置/匹配权重）
│       ├── rbac.py           # 角色权限管理
│       ├── crypto_service.py # 加密工具
│       ├── responses.py      # 统一响应格式
│       ├── seed.py           # 演示数据种子
│       └── cli.py            # Flask CLI 命令
│
├── frontend/                 # React 19 + Vite + TypeScript
│   └── src/
│       ├── App.tsx           # 主应用外壳与尚未拆分的业务页面
│       ├── InsightPage.tsx   # AI 深度洞察页面与轻量 CSS 数据图形
│       ├── lib/api.ts        # API 客户端封装（~47KB）
│       ├── styles.css        # Tailwind 样式
│       └── main.tsx          # 入口
│
├── browser_extension/        # BOSS 直聘浏览器插件
│   └── boss-importer/
│       ├── content.js        # 页面内容采集脚本
│       ├── background.js     # 后台任务脚本
│       ├── popup.js/html     # 插件弹窗 UI
│       ├── manifest.json     # 插件清单
│       └── network_probe.js  # 网络请求拦截
│
├── scripts/                  # 部署/运维/迁移脚本
│   ├── full_data_migration.py   # 全量数据迁移
│   ├── preflight_production.py  # 生产预检
│   ├── check_secrets.py         # 密钥泄露检查
│   ├── backup-production.ps1    # 备份脚本
│   ├── restore-production.ps1   # 恢复脚本
│   └── smoke_api.py / smoke-api.ps1  # 烟雾测试
│
├── deploy/                   # Nginx 配置
├── docs/                     # 文档
├── base_agent/               # AI 标签库（all_labels.csv / tech_taxonomy.json）
├── Dockerfile                # 多阶段构建（前端 + 后端）
├── docker-compose.production.yml  # 生产 Docker Compose
└── .env.example              # 环境变量模板
```

> 根目录的 Word 文档《技术架构和开发流程-精细补充》是 2026-07-06 的历史重建蓝图，其中部分文件路径、React 版本、Agent 编排和任务队列方案已经被当前实现替代。维护和开发以本目录文档及实际代码为准，业务规则可继续参考该历史文档。

---

## 3. 数据模型（核心 30 张表）

| 模型 | 表名 | 说明 |
|------|------|------|
| `User` | user | 用户（管理员/招聘官/面试官） |
| `SystemSetting` | system_setting | 系统配置键值对 |
| `Candidate` | candidate | 候选人（人才库） |
| `CandidateTag` | candidate_tag | 候选人标签（技能/经验） |
| `ResumeAttachment` | resume_attachment | 简历附件文件 |
| `UploadBatch` | upload_batch | 上传批次 |
| `Job` | job | 岗位（招聘/内部） |
| `OrganizationUnit` | organization_unit | 组织架构节点 |
| `EmployeeProfile` | employee_profile | 员工档案 |
| `EmployeeCompensation` | employee_compensation | 员工薪资 |
| `EmployeeAnalysis` | employee_analysis | 员工 AI 分析 |
| `EmployeeRecommendation` | employee_recommendation | 员工调岗/替补推荐 |
| `Match` | match | 岗位匹配结果 |
| `PipelineStage` | pipeline_stage | 流程阶段记录 |
| `InterviewAssignment` | interview_assignment | 面试安排 |
| `InterviewFeedback` | interview_feedback | 面试反馈 |
| `InterviewSpeechLog` | interview_speech_log | 语音交互日志 |
| `OfferRecord` | offer_record | Offer 记录 |
| `BossDraft` | boss_draft | BOSS 话术草稿 |
| `BossAccount` | boss_account | BOSS 账号绑定 |
| `BossSyncJob` | boss_sync_job | BOSS 同步任务 |
| `BossSyncItem` | boss_sync_item | BOSS 同步明细项 |
| `AgentConversation` | agent_conversation | AI Agent 对话会话 |
| `AgentMessage` | agent_message | Agent 对话消息 |
| `BackgroundTask` | background_task | 后台任务队列 |
| `LLMUsage` | llm_usage | LLM 调用用量 |
| `NotificationChannel` | notification_channel | 通知渠道 |
| `NotificationEvent` | notification_event | 通知事件配置 |
| `NotificationLog` | notification_log | 通知发送日志 |
| `AuditLog` | audit_log | 审计日志 |

---

## 4. 核心业务流程

### 4.1 外部招聘流程
```
BOSS 插件采集简历 → 后端导入/解析 → AI 标签提取 → 岗位匹配（规则+AI）
  → 流程看板（初筛→一面→二面→终面→Offer→入职）→ 候选人转内部员工
```

### 4.2 内部人才盘点是
```
组织架构导入 → 员工档案创建 → 简历上传/解析 → 当前岗位分析
  → 调岗推荐（AI 匹配全公司岗位）→ 离职替补推荐（AI 匹配人才库候选人）
  → 薪资合理性分析
```

### 4.3 AI 招聘 Agent
```
用户对话 → 意图识别 → 多工具调用（查询人才库/统计/创建岗位/匹配）
  → 上下文记忆 → 联网搜索（可选）→ 综合回答
```

### 4.4 BOSS 直聘集成
```
浏览器插件采集（在线简历/附件简历/岗位列表）→ 后端批量导入
  → 同步任务追踪（BossSyncJob/Item）→ 话术草稿管理 → AI 初筛并写入流程
```

---

## 5. AI 分析体系

| 功能 | 规则引擎 | AI (DeepSeek) | 证据校验 |
|------|---------|---------------|---------|
| 简历标签提取 | 规则标签（关键字匹配） | DeepSeek 语义提取 | 原文证据链 |
| 岗位匹配 | 标签权重 + 相关度算法 | DeepSeek 复核 + 证据解释 | 误判检测 |
| JD 生成 | 标签推断 | DeepSeek 生成/校准 | - |
| 简历解析 | 基础信息提取 | DeepSeek 结构化 | 标签校验 |
| 员工调岗匹配 | 标签匹配 | DeepSeek 全局分析 | 证据链 |
| 薪资分析 | 市场对标规则 | DeepSeek 合理性判断 | - |
| AI 面试 | 预设问题模板 | DeepSeek 实时问答 ASR/TTS | 作弊检测 |
| Agent 对话 | 意图分类 | DeepSeek 多工具链 | 上下文记忆 |

---

## 6. 安全与合规

- **JWT 认证：** 所有 `/api/*` 端点（除 `/auth/login`、`/healthz`、`/public/*`）需 JWT Token
- **RBAC：** 管理员/招聘官/面试官 三级角色权限
- **登录锁定：** 连续失败 5 次锁定 15 分钟
- **限流：** 默认 120 次/分钟/路由/IP
- **安全响应头：** X-Content-Type-Options、X-Frame-Options、HSTS 等
- **生产预检：** 启动时检查 JWT 密钥强度、CORS 配置、数据库类型、LLM 预算
- **审计日志：** 敏感操作自动记录（查看/导出/删除）

---

## 7. 部署架构

```
客户端浏览器 (React SPA) ←→ Nginx (反向代理/SSL) ←→ Gunicorn (Flask API)
                                                        ├── PostgreSQL (生产)
                                                        ├── Worker (后台任务)
                                                        └── 文件存储 (上传目录)

BOSS 浏览器插件 ←→ 系统 API (Cookie 授权) ←→ BOSS 直聘 API
AI 引擎 ←→ DeepSeek API (HTTP)
```

---

## 8. 配置管理

所有配置通过环境变量注入，详见 `backend/app/config.py`。关键配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接 | `sqlite:///hireinsight_demo.db` |
| `JWT_SECRET` | JWT 签名密钥 | `demo-secret` |
| `LLM_ENABLED` | 是否启用 AI | `true` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `ENVIRONMENT` | 运行环境 | `development` |
| `CORS_ORIGINS` | 允许跨域来源 | `*` |
| `UPLOAD_FOLDER` | 上传文件目录 | `uploads` |
| `BACKUP_FOLDER` | 备份目录 | `backups` |

生产环境配置通过 `.env` 文件注入，`systemctl` 服务通过 `EnvironmentFile` 加载。
