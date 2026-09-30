"""Integration tests for Skill Atlas FastAPI web server and UI."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from skill_atlas.models import Finding, ScanResult, ScanSummary, Severity, Skill
from skill_atlas.web import create_app
from tests.conftest import make_repo


def test_web_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_web_index_and_security_headers():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Content-Security-Policy" in resp.headers
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert "Skill Atlas" in resp.text
    assert "status-bar" in resp.text


def test_web_validation_rejects_non_github_by_default():
    app = create_app(allow_local=False)
    client = TestClient(app)
    resp = client.post("/api/scans", json={"target": "https://gitlab.com/user/project"})
    assert resp.status_code == 422
    assert "Only GitHub" in resp.json()["detail"]


def test_web_allow_local_flag(tmp_path: Path):
    repo = make_repo(
        tmp_path / "web_local",
        tree={
            ".claude/skills/my-skill/SKILL.md": (
                "---\nname: my-skill\ndescription: Web local test skill.\n---\n"
            )
        },
    )
    # Refused without allow_local
    app_no_local = create_app(allow_local=False)
    client_no_local = TestClient(app_no_local)
    resp_no = client_no_local.post("/api/scans", json={"target": str(repo)})
    assert resp_no.status_code == 422

    # Allowed with allow_local
    app_local = create_app(allow_local=True)
    client_local = TestClient(app_local)
    resp_ok = client_local.post("/api/scans", json={"target": str(repo)})
    assert resp_ok.status_code == 200
    scan_id = resp_ok.json()["scan_id"]
    assert scan_id is not None


def test_web_scan_lifecycle_and_events(tmp_path: Path):
    """Test full scan lifecycle: start -> check status -> get result."""
    repo = make_repo(
        tmp_path / "web_lifecycle",
        tree={
            ".claude/skills/web-demo/SKILL.md": (
                "---\nname: web-demo\ndescription: A demo skill for web testing.\n---\n# Demo\n"
            )
        },
    )
    app = create_app(allow_local=True)
    client = TestClient(app)

    # 1. Start scan
    resp = client.post("/api/scans", json={"target": str(repo)})
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    # 2. Wait briefly for worker thread to complete
    max_wait = 5.0
    start = time.time()
    completed = False
    while time.time() - start < max_wait:
        res_poll = client.get(f"/api/scans/{scan_id}")
        if res_poll.status_code == 200:
            data = res_poll.json()
            if "skills" in data:
                completed = True
                assert data["summary"]["total_skills"] == 1
                assert data["skills"][0]["name"] == "web-demo"
                break
        time.sleep(0.1)

    assert completed, "Scan did not complete within timeout"

    # 3. Read events endpoint
    events_resp = client.get(f"/api/scans/{scan_id}/events")
    assert events_resp.status_code == 200
    assert "data:" in events_resp.text


def test_web_cancellation(tmp_path: Path):
    """Cancelling a scan marks it cancelled and returns 400 on result."""
    app = create_app(allow_local=True)
    client = TestClient(app)

    resp = client.post("/api/scans", json={"target": "https://github.com/example/repo"})
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    # Cancel scan
    del_resp = client.delete(f"/api/scans/{scan_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "cancelled"

    # Get scan result should reflect cancelled state
    res_get = client.get(f"/api/scans/{scan_id}")
    assert res_get.status_code in (400, 500)


def test_web_xss_prevention():
    """Verify that malicious payload in skill description is preserved as raw string and not executed."""
    malicious_desc = "<img src=x onerror=alert(1)>"
    mock_skill = Skill(
        name="xss-test",
        description=malicious_desc,
        path=".claude/skills/xss",
        findings=[
            Finding(
                rule_id="SEC-005",
                severity=Severity.WARN,
                message=f"Suspicious payload: {malicious_desc}",
                file="SKILL.md",
            )
        ],
    )
    mock_result = ScanResult(
        target="https://github.com/example/xss-repo",
        summary=ScanSummary(total_skills=1, passed=1, failed=0),
        skills=[mock_skill],
    )

    class MockScanner:
        def __init__(self, *args, **kwargs):
            self.registry = None

        def scan(self, *args, **kwargs):
            return mock_result

    # Start app with mocked scanner
    app = create_app(allow_local=True, scanner=MockScanner())
    client = TestClient(app)

    resp = client.post("/api/scans", json={"target": "https://github.com/example/xss-repo"})
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    # Wait for completion
    time.sleep(0.2)
    res_poll = client.get(f"/api/scans/{scan_id}")
    assert res_poll.status_code == 200
    data = res_poll.json()

    # The raw string must be preserved in JSON payload exactly
    assert data["skills"][0]["description"] == malicious_desc
    assert data["skills"][0]["findings"][0]["message"] == f"Suspicious payload: {malicious_desc}"
