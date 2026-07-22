import base64
import hashlib

from cryptography.fernet import Fernet
from flask import current_app


def _fernet():
    secret = str(current_app.config.get("JWT_SECRET") or "demo-secret").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(str(value or "").encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    return _fernet().decrypt(str(value or "").encode("utf-8")).decode("utf-8")
