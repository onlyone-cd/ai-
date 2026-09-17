from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_business_api import ProbeClient, candidate_detail, run_probe


class FakeProbeClient(ProbeClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:5001", 1)

    def request(self, method, path, payload=None):
        responses = {
            "/healthz": {"status": "ok"},
            "/api/auth/login": {"data": {"token": "test-token", "user": {"role": "admin"}}},
            "/api/auth/me": {"data": {"username": "probe"}},
            "/api/candidates?limit=1": {
                "data": {
                    "items": [{"id": 1}],
                    "total": 2,
                    "experience_stats": [{"key": "1-3", "count": 2}],
                }
            },
            "/api/jobs?limit=1": {"data": {"items": [], "total": 0}},
            "/api/pipeline/overview": {"data": {"total": 0}},
            "/api/insight/report?days=30": {"data": {"generated_at": "2026-09-17T00:00:00+00:00"}},
        }
        return 200, responses[path], 12


def test_business_probe_covers_authenticated_core_endpoints():
    client = FakeProbeClient()

    results = run_probe(client, {"username": "probe", "password": "secret", "token": ""})

    assert all(result.ok for result in results)
    assert [result.name for result in results] == [
        "healthz",
        "auth.login",
        "auth.me",
        "candidates.list",
        "jobs.list",
        "pipeline.overview",
        "insight.report",
    ]
    assert client.token == "test-token"


def test_candidate_probe_rejects_inconsistent_experience_totals():
    payload = {"items": [], "total": 3, "experience_stats": [{"key": "1-3", "count": 2}]}

    try:
        candidate_detail(payload)
    except ValueError as exc:
        assert "experience total 2 != candidate total 3" in str(exc)
    else:
        raise AssertionError("candidate_detail should reject inconsistent totals")
