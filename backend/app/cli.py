import os
from datetime import datetime, timedelta, timezone
from time import sleep

import click

from . import db
from .auth import hash_password, validate_password_strength, verify_password
from .models import AuditLog, BackgroundTask, LLMUsage, User
from .task_service import run_next_task


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--username", default=lambda: os.getenv("ADMIN_USERNAME", "admin"), show_default="admin")
    @click.option("--name", default=lambda: os.getenv("ADMIN_NAME", "系统管理员"), show_default="系统管理员")
    @click.option("--password", default=lambda: os.getenv("ADMIN_PASSWORD", ""), help="生产环境建议通过 ADMIN_PASSWORD 环境变量传入。")
    def create_admin(username, name, password):
        """Create or update the first administrator account."""
        username = (username or "").strip()
        name = (name or "").strip()
        password = password or click.prompt("Admin password", hide_input=True, confirmation_prompt=True)
        if not username or not name:
            raise click.ClickException("username 和 name 不能为空")
        password_error = validate_password_strength(password)
        if password_error:
            raise click.ClickException(password_error)

        user = User.query.filter_by(username=username).first()
        if user:
            user.name = name
            user.role = "admin"
            user.active = True
            user.password_hash = hash_password(password)
            action = "updated"
        else:
            user = User(username=username, name=name, role="admin", active=True, password_hash=hash_password(password))
            db.session.add(user)
            action = "created"
        db.session.commit()
        click.echo(f"admin user {action}: {username}")

    @app.cli.command("reset-password")
    @click.option("--username", required=True)
    @click.option("--password", default=lambda: os.getenv("NEW_PASSWORD", ""), help="也可通过 NEW_PASSWORD 环境变量传入。")
    def reset_password(username, password):
        """Reset a user's password."""
        username = (username or "").strip()
        password = password or click.prompt("New password", hide_input=True, confirmation_prompt=True)
        user = User.query.filter_by(username=username).first()
        if not user:
            raise click.ClickException("用户不存在")
        password_error = validate_password_strength(password)
        if password_error:
            raise click.ClickException(password_error)
        if verify_password(password, user.password_hash):
            raise click.ClickException("新密码不能与旧密码相同")
        user.password_hash = hash_password(password)
        db.session.commit()
        click.echo(f"password reset: {username}")

    @app.cli.command("run-tasks")
    @click.option("--limit", default=10, show_default=True, help="单轮最多执行多少个队列任务。")
    @click.option("--watch", is_flag=True, help="持续轮询队列，适合生产 worker 容器。")
    @click.option("--sleep-seconds", default=5, show_default=True, help="watch 模式空闲等待秒数。")
    def run_tasks(limit, watch, sleep_seconds):
        """Run queued background tasks."""
        while True:
            processed = 0
            for _ in range(max(1, int(limit or 1))):
                try:
                    task = run_next_task()
                except Exception as exc:
                    processed += 1
                    click.echo(f"task failed: {exc}")
                    continue
                if not task:
                    break
                processed += 1
                click.echo(f"task succeeded: {task.id} {task.task_type}")
            click.echo(f"processed tasks: {processed}")
            if not watch:
                break
            sleep(max(1, int(sleep_seconds or 1)))

    @app.cli.command("prune-data")
    @click.option("--confirm", is_flag=True, help="真正删除过期数据；不加时只做 dry-run 预览。")
    @click.option("--audit-days", type=int, default=None, help="审计日志保留天数。")
    @click.option("--llm-days", type=int, default=None, help="LLM 用量记录保留天数。")
    @click.option("--task-days", type=int, default=None, help="已完成/失败后台任务保留天数。")
    def prune_data(confirm, audit_days, llm_days, task_days):
        """Prune expired operational records."""
        audit_days = retention_days(audit_days, app.config.get("AUDIT_LOG_RETENTION_DAYS", 365))
        llm_days = retention_days(llm_days, app.config.get("LLM_USAGE_RETENTION_DAYS", 180))
        task_days = retention_days(task_days, app.config.get("TASK_RETENTION_DAYS", 90))
        now = datetime.now(timezone.utc)

        audit_query = AuditLog.query.filter(AuditLog.created_at < now - timedelta(days=audit_days))
        llm_query = LLMUsage.query.filter(LLMUsage.created_at < now - timedelta(days=llm_days))
        task_query = BackgroundTask.query.filter(
            BackgroundTask.status.in_(["succeeded", "failed"]),
            BackgroundTask.updated_at < now - timedelta(days=task_days),
        )

        counts = {
            "audit_logs": audit_query.count(),
            "llm_usages": llm_query.count(),
            "background_tasks": task_query.count(),
        }
        click.echo(
            "prune "
            f"dry_run={not confirm} "
            f"audit_logs={counts['audit_logs']} "
            f"llm_usages={counts['llm_usages']} "
            f"background_tasks={counts['background_tasks']}"
        )
        if not confirm:
            return
        audit_query.delete(synchronize_session=False)
        llm_query.delete(synchronize_session=False)
        task_query.delete(synchronize_session=False)
        db.session.commit()
        click.echo("prune committed")


def retention_days(value, default):
    days = int(default if value is None else value)
    if days <= 0:
        raise click.ClickException("保留天数必须大于 0")
    return days
