import os
from time import sleep

import click

from . import db
from .auth import hash_password, validate_password_strength, verify_password
from .models import User
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
