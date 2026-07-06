# AI 招聘管理系统

AI 招聘管理系统用于打通简历导入、人才库解析、岗位管理、人岗匹配、招聘流程、AI 面试、Offer、BOSS 半自动同步、BI 看板和 AI Agent 助手。技术栈为 Flask + SQLAlchemy + Alembic + React + TypeScript + Vite + Tailwind，支持 Docker 生产部署、权限控制、审计日志、后台任务和 DeepSeek 增强解析。

## 快速启动

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

开发默认账号：

- 用户名：`admin`
- 密码：`admin123`

默认地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:5001`

也可以先执行 `pnpm run build`，再只启动后端，Flask 会在 `http://localhost:5001` 同源托管前端和 `/api`。

## 生产部署

阿里云 ECS Ubuntu 24.04 64 位推荐使用 Docker Compose + PostgreSQL + 宿主机 Nginx 部署，完整步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 核心能力

- JWT 登录、RBAC 权限、管理员用户管理
- 人才库列表、批量简历/ZIP 上传、标签、经验档位、详情页、重解析和导出
- 岗位创建、AI 生成 JD、AI 校准 JD、JD 技能权重解析
- 人岗匹配、匹配预览、正式匹配持久化、低于 50 分过滤
- 命中标签、缺失标签、exact/related 解释
- 候选人流程看板、阶段推进、流程历史和导出
- AI 面试安排、候选人网页面试间、语音答题、动态追问、完成同步和 AI 评分
- Offer 创建、状态流转、确认函导出
- BOSS Cookie 状态、岗位同步、候选人收件箱导入、岗位推荐
- BI 招聘漏斗、来源质量、经验分布
- AI Agent 对话，可查询人才库、岗位、匹配、流程、面试、Offer、BOSS、BI 和用户模块
- 后台任务队列、结构化访问日志、审计日志、健康检查、生产迁移和备份脚本

## 开发进度

当前主链路已进入上线准备阶段，已完成：

- 后端已拆出 `config.py`、`auth.py`、`rbac.py`、`responses.py`
- JWT 登录、当前用户、角色权限清单已独立封装
- 已加入 admin 用户管理接口：列表、创建、更新、启用/禁用
- 前端已加入“用户管理”页面，仅 admin 可见
- 已加入后端 API smoke 测试，覆盖登录、鉴权、RBAC、匹配和流程校验
- 已加入简历上传接口 `POST /api/resume/upload`
- 上传简历支持 TXT、MD、DOCX、PDF，文件落盘后进入解析、经验识别和标签入库
- 人才库详情已接入后端详情接口，并支持候选人级联删除
- 简历解析基础信息改为明文展示：姓名、手机号、邮箱不再脱敏；性别从明确字段或顶部常见写法识别
- 岗位侧已加入 JD 结构化：技能权重、年限、学历、薪资、关键要求、加分项
- 已加入岗位详情、编辑基础接口、关闭/恢复接口、匹配预览接口
- 匹配预览不写库；执行匹配会持久化结果；关闭岗位不能执行正式匹配
- 已加入正式标签库文件：`base_agent/all_labels.csv` 和 `base_agent/tech_taxonomy.json`
- 简历解析已接入 DeepSeek，模型只能从标签库候选标签中选择，并且必须带原文证据
- DeepSeek 不可用或返回不合格时，会自动回退到规则标签识别
- 候选人详情已改为完整页面展示，不再使用右侧抽屉
- 候选人详情页已加入技能标签雷达图和按类别分组的标签明细
- 匹配结果已接入 ATS 流程：支持单个候选人加入流程、批量加入前 5 名、重复加入自动跳过
- 已加入流程历史接口，流程阶段继续保持 append-only
- 流程看板已正式化：按阶段展示候选人、支持备注推进、候选人流程历史侧栏查看
- 已加入面试管理模块：支持安排面试、提交面试反馈，并按反馈结果推进一面、二面、Offer 或淘汰阶段
- 已加入 Offer 管理模块：支持创建 Offer、维护薪资/入职信息、发放/接受/拒绝状态流转，并同步写入流程历史
- AI 助手已从占位问答升级为受控工具助手：支持经验分布、候选人检索、岗位推荐预览、流程漏斗、Offer 状态和 BI 快照查询；推荐预览不写入匹配结果
- AI 助手已升级为多轮 Agent 对话模式：可调用人才库、岗位、匹配、流程、面试、Offer、BOSS、BI、用户等模块工具，支持人才分类统计，例如软件开发/会计/HR/销售/数据人才数量，并支持通过自然语言创建岗位

## 目录

```text
backend/   Flask API、SQLAlchemy 模型、匹配规则、种子数据
frontend/  React + TypeScript + Vite 单页应用
```
