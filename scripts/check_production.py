"""Check production health over a verified OpenSSH connection.

Required environment variables:
    HIREINSIGHT_SSH_HOST
    HIREINSIGHT_SSH_USER

Authentication uses the local SSH agent or HIREINSIGHT_SSH_KEY_FILE. The
server must already be present in the user's known_hosts file. No shell is
used to construct the local command.
"""

from __future__ import annotations

import os
import json
import subprocess
import sys


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    host = required_env("HIREINSIGHT_SSH_HOST")
    username = required_env("HIREINSIGHT_SSH_USER")
    key_filename = os.getenv("HIREINSIGHT_SSH_KEY_FILE") or None
    port = int(os.getenv("HIREINSIGHT_SSH_PORT", "22"))
    require_business = os.getenv("HIREINSIGHT_REQUIRE_BUSINESS_PROBE", "false").strip().lower() in {"1", "true", "yes"}

    base_command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10",
        "-p", str(port),
    ]
    if key_filename:
        base_command.extend(["-i", key_filename])
    base_command.append(f"{username}@{host}")

    checks = {
        "app": "http://127.0.0.1:5001/",
        "healthz": "http://127.0.0.1:5001/healthz",
    }
    failed = False
    for name, url in checks.items():
        remote_command = f"curl -sS -o /dev/null -w '%{{http_code}}' {url}"
        result = subprocess.run(
            [*base_command, remote_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        status = result.stdout.strip()
        print(f"{name}: {status or 'no response'}")
        if result.returncode != 0 or not status.startswith("2"):
            failed = True
            if result.stderr.strip():
                print(f"{name} error: {result.stderr.strip()}", file=sys.stderr)

    credentials = {
        "username": os.getenv("HIREINSIGHT_PROBE_USERNAME", ""),
        "password": os.getenv("HIREINSIGHT_PROBE_PASSWORD", ""),
        "token": os.getenv("HIREINSIGHT_PROBE_TOKEN", ""),
    }
    has_credentials = bool(credentials["token"] or (credentials["username"] and credentials["password"]))
    if has_credentials:
        remote_command = "python3 /opt/hireinsight/scripts/probe_business_api.py --base-url http://127.0.0.1:5001 --credentials-stdin"
        result = subprocess.run(
            [*base_command, remote_command],
            input=json.dumps(credentials),
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        print(result.stdout.strip() or "business probe: no response")
        if result.returncode != 0:
            failed = True
            if result.stderr.strip():
                print(f"business probe error: {result.stderr.strip()}", file=sys.stderr)
    else:
        message = "business probe skipped: set HIREINSIGHT_PROBE_TOKEN or HIREINSIGHT_PROBE_USERNAME/HIREINSIGHT_PROBE_PASSWORD"
        print(message)
        if require_business:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Production check failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
