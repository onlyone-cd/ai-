# 更新日志

## 2026-07-06

### 已完成模块

- 系统地基：Flask API、SQLAlchemy 模型、React + Vite 前端、JWT 登录、RBAC 权限、统一响应、审计日志。
- 人才库：简历上传、批量文件/ZIP 上传、简历解析、DeepSeek 解析兜底、基础信息识别、技能标签、经验档位、候选人详情页、简历导出、重新解析、候选人删除级联。
- 技能标签库：接入 `base_agent/all_labels.csv` 和 `base_agent/tech_taxonomy.json`，支持标签类别、别名、规则识别和候选人标签维护。
- 岗位管理：岗位 CRUD、AI 生成 JD、AI 校准 JD、JD 结构化、技能权重、关闭/恢复、岗位导出。
- 人岗匹配：匹配预览、正式匹配持久化、低于 50 分过滤、命中/缺失标签解释、批量加入流程。
- 招聘流程：流程看板、阶段推进、重复阶段跳过、流程历史、流程导出、流程总览。
- 面试管理：面试安排、编辑、取消、删除、AI 面试题生成、候选人网页面试间、语音识别答题、动态追问/解释题目、完成同步、面试反馈、AI 评分、面试报告导出。
- Offer 管理：Offer 创建、状态流转、薪资校验、流程同步、删除、CSV 导出、单条确认函导出。
- BOSS 半自动闭环：插件下载、登录态绑定/校验、BOSS 岗位同步、BOSS 候选人导入、噪声内容过滤、BOSS 候选人推荐、BOSS 候选人完整简历查看、AI 初筛入流程。
- BOSS 体验增强：连接状态显示已同步候选人/岗位数量和最近同步时间，岗位列表支持一键切换到该岗位的推荐候选人。
- BI 看板：招聘概览、流程漏斗、来源质量、经验分布、周期筛选。
- AI Agent：人才统计、候选人检索、岗位查询、自然语言创建岗位、岗位匹配推荐、流程/面试/Offer/BOSS/BI/用户查询。
- 用户管理：管理员创建账号、更新角色、启用/禁用用户。
- 生产化基础：新增 `.env.example`、Dockerfile、生产 Docker Compose、Nginx 示例、部署清单、`/healthz` 健康检查、安全响应头、基础限流、上传数量限制和 ZIP 安全校验。

### 接口变更记录

#### 认证和权限

- `POST /api/auth/login`：账号登录，返回 JWT 和用户权限。
- `GET /api/auth/me`：获取当前用户。
- `GET /api/auth/permissions`：获取当前角色权限。
- `GET /healthz`：生产健康检查，校验服务和数据库连接状态。
- `GET /api/users`：用户列表。
- `GET /api/users/interviewers`：面试官列表。
- `POST /api/users`：创建用户。
- `PATCH /api/users/<id>`：更新用户角色、状态或密码。
- `GET /api/audit/logs`：审计日志列表。

#### 人才库和简历

- `GET /api/candidates`：候选人列表，支持经验档位过滤。
- `GET /api/candidates/<id>`：候选人详情。
- `GET /api/candidates/<id>/resume.txt`：导出候选人简历文本。
- `PATCH /api/candidates/<id>`：更新候选人基础信息。
- `PUT /api/candidates/<id>/tags`：替换候选人技能标签。
- `DELETE /api/candidates/<id>`：删除候选人并清理关联数据。
- `POST /api/resume/upload`：上传单个/多个简历文件或 ZIP。
- `POST /api/resume/<id>/retry-parse`：重新解析候选人简历。
- `GET /api/tags`：获取技能标签库。

#### 岗位和匹配

- `GET /api/jobs`：岗位列表。
- `GET /api/jobs/<id>`：岗位详情。
- `POST /api/jobs`：创建岗位。
- `POST /api/jobs/ai-generate`：AI 生成 JD 和技能权重。
- `POST /api/jobs/ai-calibrate`：AI 校准 JD 和技能权重。
- `PATCH /api/jobs/<id>`：更新岗位。
- `POST /api/jobs/<id>/close`：关闭岗位。
- `POST /api/jobs/<id>/restore`：恢复岗位。
- `DELETE /api/jobs/<id>`：删除岗位并清理关联数据。
- `GET /api/jobs/<id>/match-preview`：岗位匹配预览，不写库。
- `POST /api/jobs/<id>/match`：执行岗位匹配并持久化。
- `POST /api/jobs/<id>/batch-pipeline`：批量加入流程。

#### 招聘流程

- `GET /api/pipeline/<job_id>/board`：岗位流程看板。
- `GET /api/pipeline/<job_id>/history/<candidate_id>`：候选人流程历史。
- `POST /api/pipeline/move`：推进候选人阶段。
- `GET /api/pipeline/overview`：流程总览。

#### 面试

- `GET /api/interview/assignments`：面试安排列表。
- `GET /api/interview/assignments/<id>`：面试安排详情。
- `POST /api/interview/assignments`：创建面试安排。
- `PATCH /api/interview/assignments/<id>`：更新面试安排。
- `POST /api/interview/assignments/<id>/cancel`：取消面试。
- `DELETE /api/interview/assignments/<id>`：删除面试安排。
- `POST /api/interview/assignments/<id>/ai-plan`：生成 AI 面试方案。
- `POST /api/interview/assignments/<id>/room-link`：生成候选人面试间链接。
- `GET /api/interview/assignments/<id>/report.txt`：导出面试报告。
- `POST /api/interview/feedback`：提交面试反馈。
- `GET /api/interview/feedback`：查询面试反馈。
- `GET /api/public/interview-room/<token>`：候选人面试间详情。
- `POST /api/public/interview-room/<token>/turn`：AI 面试官追问/解释题目。
- `POST /api/public/interview-room/<token>/complete`：完成面试并同步结果。

#### Offer

- `GET /api/offers`：Offer 列表。
- `GET /api/offers/<id>`：Offer 详情。
- `GET /api/offers/<id>/letter.txt`：导出 Offer 确认函。
- `POST /api/offers`：创建 Offer。
- `PATCH /api/offers/<id>`：更新 Offer。
- `DELETE /api/offers/<id>`：删除 Offer。

#### BI 和导出

- `GET /api/bi/overview`：BI 概览。
- `GET /api/exports/candidates.csv`：导出候选人。
- `GET /api/exports/jobs.csv`：导出岗位。
- `GET /api/exports/offers.csv`：导出 Offer。
- `GET /api/exports/interviews.csv`：导出面试。
- `GET /api/exports/pipeline.csv`：导出流程。
- `GET /api/exports/boss-drafts.csv`：历史 BOSS 话术导出接口，当前前端已不再使用。

#### BOSS 半自动

- `GET /api/boss/status`：BOSS 连接状态，并返回 BOSS 候选人数量、岗位数量、最近候选人同步时间和最近岗位同步时间。
- `GET /api/boss/extension.zip`：下载 Chrome 扩展。
- `POST /api/boss/login/browser-cookie`：绑定当前浏览器登录态指纹。
- `POST /api/boss/accounts/<id>/verify`：校验 BOSS 登录态。
- `GET /api/boss/candidates/inbox`：BOSS 已同步候选人收件箱。
- `POST /api/boss/candidates/batch-import`：批量导入 BOSS 候选人。
- `POST /api/boss/candidates/ai-screen`：将 BOSS 候选人写入 AI 初筛流程。
- `POST /api/boss/screen-resume/import`：导入当前 BOSS 简历页。
- `GET /api/boss/jobs`：BOSS 同步岗位列表。
- `POST /api/boss/jobs/batch-import`：批量同步 BOSS 岗位。
- `GET /api/boss/jobs/<id>/recommendations`：按 BOSS 岗位推荐 BOSS 候选人。
- `POST /api/boss/messages/draft`、`GET/PATCH/DELETE /api/boss/messages/drafts...`：历史话术接口，当前前端已不再使用。

#### AI Agent

- `POST /api/agent/chat`：Agent 对话和工具调用入口。
- `GET /api/agent/tools`：Agent 工具清单。

### 已知剩余事项

- BOSS 同步仍基于浏览器插件采集当前账号可见页面，不是 BOSS 官方开放平台 API。
- 数据库迁移体系尚未接入，当前仍依赖 `db.create_all()` 和轻量 SQLite schema patch。
- BOSS 历史话术后端接口仍保留用于兼容旧数据，前端已不再展示。
- 面试间还缺正式上线级录音留存、转写失败重试、设备检测和异常恢复。
- 前端缺少 Playwright/E2E 自动化测试。
