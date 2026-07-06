数据库迁移目录。

生产环境不要依赖 `db.create_all()` 自动建表，应执行：

```powershell
flask --app run db upgrade
```

新增或修改模型后，在开发环境生成迁移：

```powershell
flask --app run db migrate -m "describe change"
flask --app run db upgrade
```
