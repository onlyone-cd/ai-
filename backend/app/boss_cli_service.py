from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from typing import Any


BOSS_INSTALL_TARGET = "git+https://github.com/jackwener/boss-cli.git"
BOSS_BIN_NAME = "boss"
REQUIRED_COOKIES = ("wt2", "wbg", "zp_at")


def parse_cookie_header(raw: Any) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            key = str(key or "").strip()
            if key:
                cookies[key] = str(value or "")
        return cookies
    for part in str(raw or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            cookies[key] = value.strip()
    return cookies


def cookie_header(cookies: dict[str, str]) -> str:
    preferred = [name for name in REQUIRED_COOKIES if cookies.get(name)]
    rest = sorted(name for name in cookies if name not in preferred and cookies.get(name))
    return "; ".join(f"{name}={cookies[name]}" for name in [*preferred, *rest])


def candidate_script_dirs() -> list[Path]:
    dirs = [Path(sys.executable).parent]
    try:
        paths = sysconfig.get_paths()
        scripts = paths.get("scripts")
        purelib = paths.get("purelib")
        if scripts:
            dirs.append(Path(scripts))
        if purelib:
            dirs.append(Path(purelib).parent.parent.parent / ("Scripts" if os.name == "nt" else "bin"))
    except Exception:  # noqa: BLE001
        pass
    seen: set[str] = set()
    unique: list[Path] = []
    for item in dirs:
        key = str(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def resolve_boss_bin() -> str | None:
    override = os.getenv("BOSS_CLI_BIN", "").strip()
    if override and os.path.exists(override):
        return override
    found = shutil.which(BOSS_BIN_NAME)
    if found:
        return found
    names = [BOSS_BIN_NAME, f"{BOSS_BIN_NAME}.exe"]
    for directory in candidate_script_dirs():
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return None


def ensure_boss_cli() -> tuple[bool, str]:
    found = resolve_boss_bin()
    if found:
        return True, found
    if os.getenv("BOSS_CLI_AUTO_INSTALL", "true").lower() != "true":
        return False, f"BOSS CLI 未安装，请执行 pip install {BOSS_INSTALL_TARGET} 或设置 BOSS_CLI_BIN"
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", BOSS_INSTALL_TARGET],
            timeout=300,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"BOSS CLI 自动安装失败：{exc}"
    found = resolve_boss_bin()
    if found:
        return True, found
    return False, "BOSS CLI 安装后仍未找到 boss 可执行文件"


def run_boss(args: list[str], cookies: str, timeout: int = 60, want_json: bool = True) -> dict[str, Any]:
    ok, binary_or_error = ensure_boss_cli()
    if not ok:
        return {"ok": False, "error": {"code": "boss_cli_not_installed", "message": binary_or_error}}
    command = [binary_or_error, *args]
    if want_json:
        command.append("--json")
    env = dict(os.environ, BOSS_COOKIES=cookies, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="ignore")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "timeout", "message": f"BOSS 命令执行超时 {timeout}s"}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"code": "exec_error", "message": str(exc)}}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        if out:
            try:
                parsed_error = json.loads(out)
                if isinstance(parsed_error, dict) and parsed_error.get("error"):
                    inner = parsed_error.get("error") or {}
                    inner_code = str(inner.get("code") or "boss_cli_error")
                    inner_message = str(inner.get("message") or out)
                    if inner_code == "api_error" and any(token in inner_message for token in ("未登录", "失效", "code=7", "not_authenticated")):
                        inner_code = "not_authenticated"
                    elif inner_code == "api_error" and any(token in inner_message for token in ("环境异常", "code=37", "stoken")):
                        inner_code = "needs_stoken"
                    return {"ok": False, "error": {"code": inner_code, "message": inner_message[:600]}}
            except Exception:  # noqa: BLE001
                pass
        message = err or out or f"BOSS 命令失败，退出码 {proc.returncode}"
        code = "not_authenticated" if any(token in message for token in ("未登录", "失效", "code=7", "not_authenticated")) else "boss_cli_error"
        code = "needs_stoken" if any(token in message for token in ("环境异常", "code=37", "stoken")) else code
        code = "rate_limited" if any(token in message for token in ("频控", "rate", "429")) else code
        return {"ok": False, "error": {"code": code, "message": message[:600]}}
    if not out:
        return {"ok": True, "data": None}
    if not want_json:
        return {"ok": True, "data": out}
    try:
        parsed = json.loads(out)
    except Exception:
        return {"ok": True, "data": out}
    if isinstance(parsed, dict) and "ok" in parsed:
        return {"ok": bool(parsed.get("ok")), "data": parsed.get("data"), "error": parsed.get("error")}
    return {"ok": True, "data": parsed}


def iter_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if find_first(value, GEEK_KEYS):
            records.append(value)
        for child in value.values():
            records.extend(iter_records(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(iter_records(child))
    return records


GEEK_KEYS = (
    "geek_id",
    "geekId",
    "encrypt_geek_id",
    "encryptGeekId",
    "encryptedGeekId",
    "encryptGeekIdStr",
    "encryptUid",
    "encrypt_uid",
    "encryptFriendId",
    "encrypt_friend_id",
)
SECURITY_KEYS = ("security_id", "securityId", "securityID", "lid", "encryptSecurityId")
JOB_KEYS = ("job", "job_id", "jobId", "encrypt_job_id", "encryptJobId", "encrypt_jobId", "encryptJobIdStr")
FRIEND_KEYS = ("friend_id", "friendId", "encryptFriendId")
NAME_KEYS = ("name", "geekName", "userName", "candidateName", "geek_name")


def find_first(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return str(value[key])
        for child in value.values():
            found = find_first(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first(child, keys)
            if found:
                return found
    return ""


def normalize_inbox_items(data: Any) -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for record in iter_records(data):
        geek_id = find_first(record, GEEK_KEYS)
        if not geek_id or geek_id in seen:
            continue
        seen.add(geek_id)
        items.append({
            "geek_id": geek_id,
            "security_id": find_first(record, SECURITY_KEYS),
            "job": find_first(record, JOB_KEYS),
            "friend_id": find_first(record, FRIEND_KEYS),
            "name": find_first(record, NAME_KEYS),
        })
    return items


def looks_like_resume_markdown(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) < 30:
        return False
    signals = [
        bool(re.search(r"简历|工作经历|项目经历|教育经历|求职|个人优势|专业技能", value)),
        bool(re.search(r"本科|大专|硕士|博士|应届|\d+\s*年", value)),
        bool(re.search(r"开发|工程师|会计|运营|销售|产品|设计|测试|Java|Python", value, re.I)),
    ]
    return sum(signals) >= 2


def import_obtained_resumes(raw_cookies: Any, limit: int = 20, labels: list[int] | None = None, interval_sec: float = 1.5) -> dict[str, Any]:
    cookies = parse_cookie_header(raw_cookies)
    missing = [name for name in REQUIRED_COOKIES if not cookies.get(name)]
    if missing:
        return {"ok": False, "error": {"code": "incomplete_cookie", "message": f"BOSS Cookie 不完整，缺少 {', '.join(missing)}"}}
    header = cookie_header(cookies)
    labels = labels or [0]
    limit = max(1, min(int(limit or 20), 50))
    interval_sec = max(0, float(interval_sec or 0))

    candidates: list[dict[str, str]] = []
    inbox_errors: list[dict[str, Any]] = []
    for label in labels:
        result = run_boss(["recruiter", "inbox", "--label", str(label), "-n", str(limit)], header, timeout=60)
        if result.get("ok"):
            candidates.extend(normalize_inbox_items(result.get("data")))
        else:
            inbox_errors.append({"label": label, "error": result.get("error")})
        if len(candidates) >= limit:
            break
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        if item["geek_id"] in seen:
            continue
        seen.add(item["geek_id"])
        deduped.append(item)
        if len(deduped) >= limit:
            break

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(deduped):
        if index > 0 and interval_sec:
            time.sleep(interval_sec)
        args = ["recruiter", "resume-download", item["geek_id"]]
        if item.get("job"):
            args += ["--job", item["job"]]
        if item.get("security_id"):
            args += ["--security-id", item["security_id"]]
        args += ["-o", "-"]
        downloaded = run_boss(args, header, timeout=90, want_json=False)
        if not downloaded.get("ok"):
            errors.append({"geek_id": item["geek_id"], "name": item.get("name"), "error": downloaded.get("error")})
            if (downloaded.get("error") or {}).get("code") == "rate_limited":
                break
            continue
        raw_text = str(downloaded.get("data") or "")
        if not looks_like_resume_markdown(raw_text):
            errors.append({"geek_id": item["geek_id"], "name": item.get("name"), "error": "下载内容不像完整简历"})
            continue
        items.append({
            "external_id": f"boss-cli-{item['geek_id']}",
            "name": item.get("name") or "",
            "title": "",
            "summary": raw_text[:260],
            "raw_text": raw_text,
            "page_url": "boss-cli://recruiter/resume-download",
            "boss": item,
            "source": "boss_cli_obtained_resume",
        })
    return {"ok": True, "data": {"items": items, "errors": [*inbox_errors, *errors], "discovered": len(deduped)}}
