import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = ""

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, expect_json: bool = True):
        body = None
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(urljoin(self.base_url, path.lstrip("/")), data=body, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=20) as response:
                content = response.read()
                if not expect_json:
                    return {"status": response.status, "bytes": len(content)}
                data = json.loads(content.decode("utf-8"))
                if response.status >= 400:
                    raise RuntimeError(data.get("error") or f"HTTP {response.status}")
                return data.get("data", data)
        except HTTPError as exc:
            content = exc.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(content)
                message = data.get("error") or content
            except json.JSONDecodeError:
                message = content or str(exc)
            raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc


def run_step(results: list[StepResult], name: str, fn):
    try:
        detail = fn()
        results.append(StepResult(name, True, str(detail or "ok")))
    except Exception as exc:
        results.append(StepResult(name, False, str(exc)))


def assert_items(payload: dict[str, Any], key: str = "items"):
    if key not in payload:
        raise RuntimeError(f"missing {key}")
    return len(payload.get(key) or [])


def main():
    parser = argparse.ArgumentParser(description="Smoke test a running HireInsight API.")
    parser.add_argument("--base-url", default="http://localhost:5001", help="Base URL, for example https://hire.example.com")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--mutating", action="store_true", help="Create and clean up temporary records to verify write flows.")
    args = parser.parse_args()

    client = ApiClient(args.base_url)
    results: list[StepResult] = []
    temp: dict[str, int] = {}

    run_step(results, "health", lambda: client.request("GET", "/healthz").get("status", "ok"))

    def login():
        data = client.request("POST", "/api/auth/login", {"username": args.username, "password": args.password})
        client.token = data["token"]
        return f"role={data['user']['role']}"

    run_step(results, "auth.login", login)
    run_step(results, "auth.me", lambda: client.request("GET", "/api/auth/me")["username"])
    run_step(results, "system.readiness", lambda: "ready" if "checks" in client.request("GET", "/api/system/readiness") else "missing checks")
    run_step(results, "system.data_integrity", lambda: client.request("GET", "/api/system/data-integrity")["summary"]["total"])
    run_step(results, "system.llm_usage", lambda: client.request("GET", "/api/system/llm/usage?days=7")["summary"]["total_calls"])
    run_step(results, "notifications.channels", lambda: assert_items(client.request("GET", "/api/notifications/channels")))
    run_step(results, "candidates.list", lambda: assert_items(client.request("GET", "/api/candidates?limit=5")))
    run_step(results, "jobs.list", lambda: assert_items(client.request("GET", "/api/jobs?limit=5")))
    run_step(results, "organization.tree", lambda: assert_items(client.request("GET", "/api/organization/tree")))
    run_step(results, "employees.list", lambda: assert_items(client.request("GET", "/api/employees?limit=5")))
    run_step(results, "pipeline.overview", lambda: client.request("GET", "/api/pipeline/overview")["total"])
    run_step(results, "interviews.list", lambda: assert_items(client.request("GET", "/api/interview/assignments")))
    run_step(results, "offers.list", lambda: assert_items(client.request("GET", "/api/offers")))
    run_step(results, "boss.status", lambda: client.request("GET", "/api/boss/status").get("mode", "ok"))
    run_step(results, "boss.sync_jobs", lambda: client.request("GET", "/api/boss/sync/jobs?limit=5").get("total", 0))
    run_step(results, "bi.overview", lambda: client.request("GET", "/api/bi/overview?days=30")["total_candidates"])
    run_step(results, "agent.tools", lambda: assert_items(client.request("GET", "/api/agent/tools")))
    run_step(results, "exports.jobs", lambda: client.request("GET", "/api/exports/jobs.csv", expect_json=False)["bytes"])

    if args.mutating:
        def create_candidate():
            text = (
                "Name: Smoke Candidate\n"
                "Phone: 13900001234\n"
                "Email: smoke@example.com\n"
                "Target: Java Backend Engineer\n"
                "Experience: 4 years Java, Spring Boot, MySQL, Redis.\n"
            )
            data = client.request("POST", "/api/boss/candidates/batch-import", {"items": [{"external_id": "smoke-api-py", "raw_text": text}]})
            item = data["items"][0]
            temp["candidate_id"] = item["id"]
            temp["boss_sync_job_id"] = data.get("sync_job", {}).get("id")
            return item["id"]

        def create_job():
            data = client.request(
                "POST",
                "/api/jobs",
                {
                    "title": "Smoke API Java Engineer",
                    "city": "Shanghai",
                    "jd_text": "Build Java backend services. Requires Spring Boot, MySQL and Redis.",
                    "skill_tags_raw": "Java 5\nSpring Boot 5\nMySQL 4\nRedis 4",
                },
            )
            temp["job_id"] = data["id"]
            return data["id"]

        def create_notification_channel():
            data = client.request(
                "POST",
                "/api/notifications/channels",
                {"name": "Smoke Notification Channel", "channel_type": "console", "config": {"default_recipient": "smoke@example.com"}},
            )
            temp["notification_channel_id"] = data["id"]
            return data["id"]

        run_step(results, "mutating.candidate_create", create_candidate)
        run_step(results, "mutating.boss_sync_detail", lambda: client.request("GET", f"/api/boss/sync/jobs/{temp['boss_sync_job_id']}")["status"])
        run_step(results, "mutating.job_create", create_job)
        run_step(results, "mutating.notification_channel_create", create_notification_channel)
        run_step(
            results,
            "mutating.notification_send_test",
            lambda: client.request(
                "POST",
                "/api/notifications/send-test",
                {"channel_id": temp["notification_channel_id"], "subject": "Smoke", "content": "Smoke notification"},
            )["log"]["status"],
        )
        run_step(results, "mutating.match_preview", lambda: assert_items(client.request("GET", f"/api/jobs/{temp['job_id']}/match-preview?limit=5")))
        run_step(
            results,
            "mutating.pipeline",
            lambda: len(client.request("POST", f"/api/jobs/{temp['job_id']}/batch-pipeline", {"candidate_id": temp["candidate_id"], "stage": "pending"})["created"]),
        )

    cleanup_errors: list[str] = []
    if args.mutating:
        for key, path in [
            ("notification_channel_id", "/api/notifications/channels/{id}"),
            ("job_id", "/api/jobs/{id}"),
            ("candidate_id", "/api/candidates/{id}"),
        ]:
            if key in temp:
                try:
                    client.request("DELETE", path.format(id=temp[key]))
                except Exception as exc:
                    cleanup_errors.append(f"{key}: {exc}")
        results.append(StepResult("cleanup", not cleanup_errors, "; ".join(cleanup_errors) or "removed temp records"))

    failed = [item for item in results if not item.ok]
    print(json.dumps({"ok": not failed, "base_url": args.base_url, "results": [item.__dict__ for item in results]}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
