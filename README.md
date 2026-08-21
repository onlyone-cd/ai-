# HireInsight — AI 招聘与人才盘点系统

HireInsight 是一个面向招聘与组织人才盘点的 AI 管理系统，覆盖**外部招聘**（BOSS 直聘自动同步、简历解析、AI 匹配、AI 面试、Offer 管理）、**内部人才盘点**（组织架构、员工档案、调岗匹配、薪资分析、离职替补推荐）、以及 **AI Agent 智能助手**。

## 文档导航

| 文档 | 说明 |
|------|------|
| [系统架构](docs/ARCHITECTURE.md) | 项目结构、数据模型、核心流程、AI 体系、安全合规 |
| [接口文档](docs/API.md) | 全部 API 端点、请求/响应格式、认证方式 |
| [使用文档](docs/USAGE.md) | 日常操作指南（招聘/员工/Agent/BI） |
| [运维文档](docs/MAINTENANCE.md) | 部署、备份、迁移、监控、故障排查 |
| [部署指南](DEPLOYMENT.md) | 生产环境部署步骤 |
| [全量数据迁移](docs/full-data-migration.md) | 测试→生产数据迁移 |
| [生产预检](docs/production-preflight.md) | 上线前安全检查 |
| [内部人才智能计划](docs/internal-talent-intelligence-plan.md) | 内部人才盘点的整体规划 |
| [变更日志](CHANGELOG.md) | 版本历史 |

## 技术栈

| 层 | 技术 |
|-----|------|
| 后端框架 | Python 3.12, Flask, Gunicorn |
| 前端框架 | React 19, TypeScript, Vite, Tailwind CSS |
| 数据库 | SQLAlchemy, PostgreSQL (生产) / SQLite (开发) |
| AI 引擎 | DeepSeek API (简历解析/匹配/JD 生成/面试/Agent) |
| 浏览器插件 | Chrome Extension (Manifest V3) |
| 部署 | Docker / systemd + venv + Nginx |
| 语音 | 浏览器 Web Speech API (ASR/TTS) |

## 核心功能一览

### 外部招聘
- BOSS 直聘浏览器插件采集简历 → 后端导入/解析 → AI 标签提取 → 岗位匹配（规则+AI）→ 流程看板（初筛→面试→Offer→入职）→ 候选人转内部员工

### 内部人才盘点
- 组织架构导入 → 员工档案创建 → 简历上传/解析 → 当前岗位分析 → 调岗推荐 → 离职替补推荐 → 薪资合理性分析

### AI 招聘 Agent
- 用户对话 → 意图识别 → 多工具调用（查询/统计/创建/匹配）→ 上下文记忆 → 联网搜索 → 综合回答

## 快速开始

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

### 前端（开发模式）

```powershell
cd frontend
npm install
npm run dev
```

### 生产构建

```bash
cd frontend
npm run build
```

详细部署步骤见 [DEPLOYMENT.md](DEPLOYMENT.md) 和 [运维文档](docs/MAINTENANCE.md)。

## 安全

- 所有 API 端点（除登录/健康检查/面试间）均需 JWT 认证
- 三级角色权限：管理员 / 招聘官 / 面试官
- 登录失败锁定、请求限流、安全响应头
- 生产预检机制、审计日志、敏感数据脱敏
- 员工信息、简历数据为敏感数据，不提交到 Git 仓库

## 环境要求

- Python 3.12+
- Node.js 22+
- PostgreSQL 15+（生产环境）
- Chrome / Edge（BOSS 插件）

## 许可证

内部项目，仅供授权人员使用。
