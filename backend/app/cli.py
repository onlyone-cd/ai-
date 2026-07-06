import os

import click

from . import db
from .auth import hash_password, validate_password_strength, verify_password
from .models import User


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
