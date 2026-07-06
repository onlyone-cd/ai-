from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, request
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import User
from .responses import error


def validate_password_strength(password):
    value = password or ""
    if len(value) < 8:
        return "密码至少需要 8 位"
    if value.lower() in {"password", "password123", "admin123", "12345678"}:
        return "密码过于常见"
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        return "密码需要同时包含字母和数字"
    return ""


def issue_token(user):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=current_app.config["JWT_EXPIRY_HOURS"])
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def hash_password(password):
    return generate_password_hash(password)


def current_user():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

    user = db.session.get(User, int(payload["sub"]))
    return user if user and user.active else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return error("未登录或 token 已失效", "UNAUTHORIZED", 401)
        return view(user, *args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(user, *args, **kwargs):
            if user.role not in roles:
                return error("当前账号无权执行该操作", "FORBIDDEN", 403, {"required_roles": roles})
            return view(user, *args, **kwargs)

        return wrapped

    return decorator
