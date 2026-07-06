# 生产部署清单

## 上线前必须修改

- 复制 `.env.example` 为 `.env`，替换 `JWT_SECRET`、`POSTGRES_PASSWORD`、`DEEPSEEK_API_KEY`、`CORS_ORIGINS` 和域名。
- DeepSeek Key 不要提交到 Git；如果曾经在聊天或代码中出现过，先到平台废弃旧 Key 并重新生成。
- `SEED_DEMO_DATA=false`，避免生产库写入演示数据。
- 使用 HTTPS，Nginx 前置代理后保留 `X-Forwarded-*` 请求头。

## Docker 启动

```powershell
docker compose -f docker-compose.production.yml --env-file .env up -d --build
```

容器启动时会先执行数据库迁移：

```powershell
flask --app run db upgrade
```

开发环境修改模型后生成迁移：

```powershell
cd backend
flask --app run db migrate -m "describe change"
flask --app run db upgrade
```

## 健康检查

```powershell
curl https://your-domain.example/healthz
```

返回 `status=ok` 才允许切流。

## 数据和文件

- 数据库使用 PostgreSQL，生产不要使用 SQLite。
- 生产环境设置 `AUTO_CREATE_DB=false`，只能通过迁移升级 schema。
- 上传文件保存在 `uploads` volume，需配置定期备份。
- 简历、面试报告、导出文件都属于敏感数据，下载和导出只能给授权角色。

## 当前仍需继续补齐

- 对象存储或专用文件服务。
- Redis/Celery 异步任务队列，用于批量简历解析、AI 评分和 BOSS 批量同步。
- 集中日志、错误告警、AI 调用费用统计。
- E2E 自动化测试和 CI/CD 发布流水线。
