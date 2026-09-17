"""Read-only authenticated production probe for HireInsight.

Credentials are read from environment variables or a JSON object on stdin so
they never need to appear in command-line arguments:

    HIREINSIGHT_PROBE_USERNAME=... HIREINSIGHT_PROBE_PASSWORD=... \
      python scripts/probe_business_api.py --base-url https://hire.example.com

    printf '{"token":"..."}' | \
      python scripts/probe_business_api.py --credentials-stdin
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass
class ProbeResult:
    name: str
    ok: bool
    status: int
    duration_ms: int
    detail: str


class ProbeClient:
    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds
        self.token = ""

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], int]:
        body = None
        headers = {"Accept": "application/json", "User-Agent": "HireInsight-Business-Probe/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(urljoin(self.base_url, path.lstrip("/")), data=body, headers=headers, method=method.upper())
        started = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
                duration_ms = round((perf_counter() - started) * 1000)
                return response.status, json.loads(content), duration_ms
        except HTTPError as exc:
            duration_ms = round((perf_counter() - started) * 1000)
            content = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {"error": content or str(exc)}
            return exc.code, data, duration_ms
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc


def credentials_from_environment() -> dict[str, str]:
    return {
        "username": os.getenv("HIREINSIGHT_PROBE_USERNAME", "").strip(),
        "password": os.getenv("HIREINSIGHT_PROBE_PASSWORD", ""),
        "token": os.getenv("HIREINSIGHT_PROBE_TOKEN", "").strip(),
    }


def validate_payload(name: str, status: int, payload: dict[str, Any], duration_ms: int, validator: Callable[[dict[str, Any]], str]) -> ProbeResult:
    if status < 200 or status >= 300:
        error = payload.get("error") or payload.get("message") or f"HTTP {status}"
        return ProbeResult(name, False, status, duration_ms, str(error))
    try:
        detail = validator(payload)
        return ProbeResult(name, True, status, duration_ms, detail)
    except (KeyError, TypeError, ValueError, AssertionError) as exc:
        return ProbeResult(name, False, status, duration_ms, f"invalid response: {exc}")


def data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data", payload)
    if not isinstance(value, dict):
        raise TypeError("data is not an object")
    return value


def run_probe(client: ProbeClient, credentials: dict[str, str]) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    status, payload, duration_ms = client.request("GET", "/healthz")
    results.append(validate_payload("healthz", status, payload, duration_ms, lambda body: f"status={body['status']}" if body["status"] == "ok" else (_ for _ in ()).throw(ValueError("status is not ok"))))

    token = credentials.get("token", "").strip()
    if not token:
        username = credentials.get("username", "").strip()
        password = credentials.get("password", "")
        if not username or not password:
            results.append(ProbeResult("auth.login", False, 0, 0, "missing probe token or username/password"))
            return results
        status, payload, duration_ms = client.request("POST", "/api/auth/login", {"username": username, "password": password})
        login_result = validate_payload("auth.login", status, payload, duration_ms, lambda body: f"role={data(body)['user']['role']}")
        results.append(login_result)
        if not login_result.ok:
            return results
        token = data(payload)["token"]
    client.token = token

    checks: list[tuple[str, str, Callable[[dict[str, Any]], str]]] = [
        ("auth.me", "/api/auth/me", lambda body: f"user={data(body)['username']}"),
        (
            "candidates.list",
            "/api/candidates?limit=1",
            lambda body: candidate_detail(data(body)),
        ),
        ("jobs.list", "/api/jobs?limit=1", lambda body: f"total={int(data(body)['total'])}"),
        ("pipeline.overview", "/api/pipeline/overview", lambda body: f"total={int(data(body)['total'])}"),
        ("insight.report", "/api/insight/report?days=30", lambda body: f"generated_at={data(body)['generated_at']}"),
    ]
    for name, path, validator in checks:
        try:
            status, payload, duration_ms = client.request("GET", path)
            results.append(validate_payload(name, status, payload, duration_ms, validator))
        except Exception as exc:
            results.append(ProbeResult(name, False, 0, 0, str(exc)))
    return results


def candidate_detail(payload: dict[str, Any]) -> str:
    total = int(payload["total"])
    items = payload["items"]
    stats = payload["experience_stats"]
    if not isinstance(items, list) or not isinstance(stats, list):
        raise TypeError("items or experience_stats is not a list")
    stats_total = sum(int(item["count"]) for item in stats)
    if stats_total != total:
        raise ValueError(f"experience total {stats_total} != candidate total {total}")
    return f"total={total}, experience_total={stats_total}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only authenticated HireInsight business checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--credentials-stdin", action="store_true", help="Read a JSON object containing token or username/password from stdin.")
    args = parser.parse_args()

    credentials = credentials_from_environment()
    if args.credentials_stdin:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("stdin credentials must be a JSON object")
        credentials.update({key: str(incoming.get(key) or "") for key in ("username", "password", "token")})

    results = run_probe(ProbeClient(args.base_url, args.timeout_seconds), credentials)
    payload = {"ok": all(result.ok for result in results), "base_url": args.base_url, "results": [asdict(result) for result in results]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
