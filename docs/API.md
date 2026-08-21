# HireInsight — API 接口文档

> 基础路径：`/api`  
> 认证方式：`Authorization: Bearer <JWT>`  
> 响应格式：`{"data": {...}, "error": "...", "code": "...", "details": {...}, "request_id": "..."}`

---

## 目录

1. [认证与系统](#1-认证与系统)
2. [候选人管理](#2-候选人管理)
3. [岗位管理](#3-岗位管理)
4. [流程看板](#4-流程看板)
5. [面试管理](#5-面试管理)
6. [Offer 管理](#6-offer-管理)
7. [组织架构与员工](#7-组织架构与员工)
8. [BOSS 直聘集成](#8-boss-直聘集成)
9. [AI Agent](#9-ai-agent)
10. [后台任务](#10-后台任务)
11. [BI 与导出](#11-bi-与导出)
12. [通知与审计](#12-通知与审计)
13. [标签质量](#13-标签质量)
14. [运维与管理](#14-运维与管理)

---

## 1. 认证与系统

### POST /api/auth/login
登录获取 JWT Token。
```json
{"username": "admin", "password": "password"}
→ {"data": {"token": "eyJ...", "user": {...}}}
```

### GET /api/auth/me
获取当前用户信息。

### GET /api/system/llm/status
LLM 状态（是否可用、Provider、型号、超时配置）。

### GET /api/settings
获取系统设置（AI 配置 + 匹配权重）。

### PATCH /api/settings/ai
更新 AI 配置。

### PATCH /api/settings/matching-weights
更新匹配权重。

### POST /api/settings/matching-weights/auto
自动配置匹配权重（strict/balanced/growth）。

### POST /api/settings/ai/test
测试 AI 连接。

---

## 2. 候选人管理

### GET /api/candidates
候选人列表，支持 `experience_level` 筛选。返回候选人基本信息和经验统计。

### GET /api/candidates/:id
候选人详情（含 `resume_json`、`raw_text`、附件、`resume_quality` 状态）。

### PATCH /api/candidates/:id
更新候选人基本信息（姓名、手机、邮箱、城市、性别、简介）。

### DELETE /api/candidates/:id
删除候选人（级联删除标签、匹配、流程、面试、Offer、BOSS 草稿）。

### PUT /api/candidates/:id/tags
替换候选人标签。清除旧标签和匹配结果。

### DELETE /api/candidates/:id/tags/:tag_name
删除指定标签，自动清除匹配结果。

### POST /api/candidates/:id/tags/:tag_name/confirm
人工确认标签（保留该标签不再被 AI 误判标记）。

### GET /api/candidates/:id/resume.txt
导出候选人简历原文。

### POST /api/resume/upload
上传简历文件（支持 TXT/MD/DOCX/PDF/ZIP）。返回候选人和标签。

### POST /api/resume/:id/retry-parse
重新解析简历，更新标签和匹配。支持 `?async=1` 异步执行。

### GET /api/resume/attachments
附件列表，支持按 `candidate_id`/`scan_status`/`source` 筛选。

### GET /api/candidates/:id/attachments
候选人附件列表。

### GET /api/resume/attachments/:id
附件详情。

### POST /api/resume/attachments/:id/scan
附件安全扫描。

### POST /api/boss/resume-files/import
BOSS 附件文件批量导入（FormData 上传）。

---

## 3. 岗位管理

### GET /api/jobs
岗位列表，支持 `scope`（recruiting/internal/all）筛选。

### GET /api/jobs/:id
岗位详情。

### POST /api/jobs
创建岗位（含 `skill_tags_raw` 和 `jd_text`）。

### PATCH /api/jobs/:id
更新岗位（含 JD 结构化）。

### DELETE /api/jobs/:id
删除岗位（级联清理流程、匹配、面试）。

### POST /api/jobs/:id/close
关闭岗位。

### POST /api/jobs/:id/restore
恢复岗位。

### POST /api/jobs/ai-generate
AI 生成 JD（基于技能标签）。

### POST /api/jobs/ai-calibrate
AI 校准 JD。

### GET /api/jobs/:id/match-preview
匹配预览（前 N 名候选人）。

### GET /api/jobs/:id/matches
持久化匹配结果列表。

### POST /api/jobs/:id/match
执行岗位匹配（规则 + AI 复核）。支持 `?async=1`。

### POST /api/jobs/:id/batch-pipeline
批量将候选人加入岗位流程。

---

## 4. 流程看板

### GET /api/pipeline/board
全局流程看板（所有岗位）。

### GET /api/pipeline/:job_id/board
指定岗位流程看板。

### GET /api/pipeline/:job_id/history/:candidate_id
流程阶段变更历史。

### POST /api/pipeline/move
移动候选人流程阶段。
```json
{"candidate_id": 1, "job_id": 1, "stage": "interview_first", "note": "进入一面"}
```

### GET /api/pipeline/overview
流程概览（各阶段人数统计）。

---

## 5. 面试管理

### GET /api/interview/assignments
面试安排列表。

### GET /api/interview/assignments/:id
面试安排详情。

### POST /api/interview/assignments
创建面试安排。

### PATCH /api/interview/assignments/:id
更新面试安排。

### POST /api/interview/assignments/:id/cancel
取消面试安排。

### DELETE /api/interview/assignments/:id
删除面试安排。

### POST /api/interview/assignments/:id/ai-plan
AI 生成面试计划（问题、评分标准、开场白）。

### POST /api/interview/assignments/:id/room-link
生成面试间链接（Token 有效期 72 小时）。

### POST /api/interview/feedback
提交面试反馈（评分、决定、优势、风险）。

### GET /api/interview/feedback
面试反馈列表（按面试安排筛选）。

### GET /api/interview/assignments/:id/report.txt
面试报告导出。

### GET /api/interview/speech/logs
语音交互日志。

### 公开面试间（无需认证）

| 端点 | 说明 |
|------|------|
| `GET /public/interview-room/:token` | 获取面试间信息 |
| `POST /public/interview-room/:token/turn` | 提交回答/追问 |
| `POST /public/interview-room/:token/complete` | 完成面试 |
| `POST /public/interview-room/:token/speech/asr` | 语音转文字 |
| `POST /public/interview-room/:token/speech/tts` | 文字转语音 |
| `GET /public/interview-room/:token/speech/status` | 语音状态 |

---

## 6. Offer 管理

| 端点 | 说明 |
|------|------|
| `GET /api/offers` | Offer 列表 |
| `GET /api/offers/:id` | Offer 详情 |
| `POST /api/offers` | 创建 Offer |
| `PATCH /api/offers/:id` | 更新 Offer |
| `DELETE /api/offers/:id` | 删除 Offer |
| `GET /api/offers/:id/letter.txt` | 导出 Offer 确认函 |

Offer 状态流转：`draft → sent → accepted/declined/cancelled`

---

## 7. 组织架构与员工

### 组织架构

| 端点 | 说明 |
|------|------|
| `GET /api/organization/tree` | 组织架构树 |
| `POST /api/organization/units` | 创建组织单元 |
| `PATCH /api/organization/units/:id` | 更新组织单元 |
| `DELETE /api/organization/units/:id` | 删除组织单元 |
| `POST /api/organization/import-excel` | Excel 导入组织架构 |
| `GET /api/organization/units/:id/employees` | 组织单元下员工列表 |
| `GET /api/organization/units/:id/overview` | 组织单元概览 |
| `POST /api/organization/units/:id/employee-resumes` | 批量上传员工简历 |

### 员工管理

| 端点 | 说明 |
|------|------|
| `GET /api/employees` | 员工列表 |
| `GET /api/employees/:id` | 员工详情 |
| `POST /api/employees/import-excel` | Excel 导入员工信息 |
| `POST /api/employees/:id/resume` | 上传员工简历（解析并更新标签） |
| `POST /api/employees/from-candidate` | 候选人转内部员工 |
| `PATCH /api/employees/:id` | 更新员工信息 |
| `DELETE /api/employees/:id` | 删除员工 |
| `POST /api/employees/compensation-import` | 批量导入薪资 |
| `GET /api/employees/:id/report.txt` | 导出员工报告 |

### 员工 AI 分析

| 端点 | 说明 |
|------|------|
| `POST /api/employees/:id/analyze-current-job` | 分析当前岗位匹配度 |
| `POST /api/employees/:id/recommend-transfer` | 推荐调岗 |
| `POST /api/employees/:id/recommend-replacement` | 推荐离职替补 |
| `POST /api/employees/batch-analyze` | 批量分析 |

所有分析端点支持 `?async=1` 异步执行。

---

## 8. BOSS 直聘集成

### 账号与状态

| 端点 | 说明 |
|------|------|
| `GET /api/boss/status` | BOSS 集成状态 |
| `GET /api/boss/extension.zip` | 下载浏览器插件 |
| `POST /api/boss/login/browser-cookie` | Cookie 绑定登录 |
| `POST /api/boss/accounts/:id/verify` | 验证登录态 |

### 候选人同步

| 端点 | 说明 |
|------|------|
| `GET /api/boss/candidates/inbox` | BOSS 收件箱候选人 |
| `POST /api/boss/candidates/batch-import` | 批量导入候选人（含同步任务追踪） |
| `POST /api/boss/screen-resume/import` | 导入单页简历（插件端采集） |
| `POST /api/boss/obtained-resumes/import` | 已获取简历批量导入（服务端） |
| `POST /api/boss/candidates/ai-screen` | AI 初筛并写入流程 |

### 岗位同步

| 端点 | 说明 |
|------|------|
| `GET /api/boss/jobs` | BOSS 岗位列表 |
| `POST /api/boss/jobs/batch-import` | 批量导入岗位 |
| `GET /api/boss/jobs/:id/recommendations` | 岗位匹配推荐 |

### 同步任务追踪

| 端点 | 说明 |
|------|------|
| `GET /api/boss/sync/jobs` | 同步任务列表 |
| `GET /api/boss/sync/jobs/:id` | 同步任务详情（含失败明细） |
| `POST /api/boss/sync/jobs/:id/retry` | 重试失败同步任务 |

### 话术草稿

| 端点 | 说明 |
|------|------|
| `POST /api/boss/messages/draft` | 创建话术草稿 |
| `GET /api/boss/messages/drafts` | 草稿列表 |
| `PATCH /api/boss/messages/drafts/:id` | 更新草稿 |
| `DELETE /api/boss/messages/drafts/:id` | 删除草稿 |
| `POST /api/boss/messages/drafts/:id/approve` | 审批草稿 |
| `POST /api/boss/messages/drafts/:id/mark-sent` | 标记已发送 |
| `POST /api/boss/messages/drafts/:id/cancel` | 取消草稿 |

注入的同步任务明细（BossSyncItem）会包含 `error_info` 字段：
```json
{
  "category": "boss_1092 | auth | download | not_resume | parse | network | unknown",
  "label": "BOSS 接口拒绝",
  "next_action": "改用页面采集在线简历或附件简历；如仍失败，重新登录 BOSS 后再试。"
}
```

候选人列表会返回 `resume_quality` 字段：
```json
{
  "status": "complete | partial | empty | parse_failed",
  "label": "BOSS 半截简历",
  "next_action": "需要重新打开在线简历或附件简历补全"
}
```

---

## 9. AI Agent

### 对话管理

| 端点 | 说明 |
|------|------|
| `GET /api/agent/conversations` | 对话列表 |
| `POST /api/agent/conversations` | 创建新对话 |
| `GET /api/agent/conversations/:id` | 对话历史 |
| `PATCH /api/agent/conversations/:id` | 更新对话（标题/状态） |

### 聊天

| 端点 | 说明 |
|------|------|
| `POST /api/agent/chat` | 发送消息（支持多工具链） |
| `GET /api/agent/tools` | Agent 可用工具列表 |

Agent 支持的能力：
- 查询人才库人数/分类统计
- 创建岗位
- 推荐候选人并解释匹配原因
- 查询面试/流程/Offer/BOSS 状态
- 分析员工简历、推荐调岗/替补
- 比较候选人
- 联网搜索
- 后台任务执行

---

## 10. 后台任务

| 端点 | 说明 |
|------|------|
| `GET /api/tasks` | 任务列表（支持状态/类型筛选） |
| `GET /api/tasks/:id` | 任务详情 |
| `POST /api/tasks/:id/retry` | 重试失败任务 |
| `POST /api/tasks/retry-batch` | 批量重试 |
| `POST /api/tasks/:id/run` | 立即执行排队任务 |
| `POST /api/matching/recalibrate` | 重新校准全量匹配 |

任务类型：`resume_retry_parse`、`job_match`、`matching_recalibration`、`backup_export`、`employee_analyze`、`employee_transfer`、`employee_replacement`

---

## 11. BI 与导出

### GET /api/bi/overview
BI 看板概览数据（候选人/岗位/员工/流程/面试/Offer 统计）。

### 导出 CSV

| 端点 | 说明 |
|------|------|
| `GET /api/exports/candidates.csv` | 候选人导出 |
| `GET /api/exports/jobs.csv` | 岗位导出 |
| `GET /api/exports/offers.csv` | Offer 导出 |
| `GET /api/exports/interviews.csv` | 面试导出 |
| `GET /api/exports/pipeline.csv` | 流程导出 |
| `GET /api/exports/employees.csv` | 员工导出 |
| `GET /api/exports/boss-drafts.csv` | BOSS 草稿导出 |

---

## 12. 通知与审计

| 端点 | 说明 |
|------|------|
| `GET /api/notifications/channels` | 通知渠道（邮件/Webhook） |
| `POST /api/notifications/channels` | 创建渠道 |
| `PATCH /api/notifications/channels/:id` | 更新渠道 |
| `DELETE /api/notifications/channels/:id` | 删除渠道 |
| `GET /api/notifications/events` | 通知事件配置 |
| `POST /api/notifications/events` | 创建事件 |
| `PATCH /api/notifications/events/:id` | 更新事件 |
| `GET /api/notifications/logs` | 通知发送日志 |
| `POST /api/notifications/send-test` | 发送测试通知 |
| `GET /api/audit/logs` | 审计日志 |

---

## 13. 标签质量

| 端点 | 说明 |
|------|------|
| `GET /api/tags` | 标签库列表 |
| `GET /api/tags/quality` | 标签质量报告（缺失证据/低置信度/疑似误判） |
| `POST /api/tags/quality/reparse-batch` | 批量重新解析问题标签 |
| `POST /api/tags/quality/delete-batch` | 批量删除问题标签 |
| `POST /api/tags/quality/confirm-batch` | 批量确认标签 |

---

## 14. 运维与管理

| 端点 | 说明 |
|------|------|
| `GET /api/system/readiness` | 上线检查（环境/数据库/密钥/限流等） |
| `GET /api/system/data-integrity` | 数据完整性巡检 |
| `GET /api/system/llm/usage` | LLM 用量统计 |
| `GET /api/ops/backup/status` | 备份状态 |
| `POST /api/ops/backup/export` | 创建备份包 |
| `GET /api/ops/data-quality` | 数据质量报告 |
| `GET /api/ops/deploy-gates` | 部署门禁检查 |
| `GET /api/users` | 用户列表 |
| `POST /api/users` | 创建用户 |
| `PATCH /api/users/:id` | 更新用户 |
| `GET /api/users/interviewers` | 面试官列表 |

---

## 公开端点（无需认证）

| 端点 | 说明 |
|------|------|
| `GET /healthz` | 健康检查（`{"status":"ok","service":"hireinsight"}`） |
| `GET /health` | 健康检查别名 |
| `GET /public/interview-room/*` | 公开面试间 |
| `POST /public/interview-room/*` | 公开面试间操作 |
