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


def test_web_foreign_origin_rejected():
    """Verify that cross-origin requests from foreign websites are strictly forbidden."""
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/scans",
        json={"target": "https://github.com/example/repo"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403
    assert "cross-origin" in resp.text.lower()


def test_web_cancel_completed_job_conflict(tmp_path: Path):
    """Cancelling an already completed scan returns 409 Conflict."""
    repo = make_repo(
        tmp_path / "web_conflict",
        tree={
            ".claude/skills/simple/SKILL.md": (
                "---\nname: simple\ndescription: Simple skill for conflict test.\n---\n"
            )
        },
    )
    app = create_app(allow_local=True)
    client = TestClient(app)

    resp = client.post("/api/scans", json={"target": str(repo)})
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    # Wait for completion
    for _ in range(50):
        res_poll = client.get(f"/api/scans/{scan_id}")
        if res_poll.status_code == 200 and "skills" in res_poll.json():
            break
        time.sleep(0.05)

    # Now attempt to cancel completed scan
    del_resp = client.delete(f"/api/scans/{scan_id}")
    assert del_resp.status_code == 409


def test_web_per_request_scanner_options(tmp_path: Path):
    """Verify that rules, fail_on, and ignore options are passed to the per-request scanner."""
    repo = make_repo(
        tmp_path / "web_options",
        tree={
            ".claude/skills/bad/SKILL.md": ("---\nname: bad\ndescription: Short\n---\nrm -rf /\n")
        },
    )
    app = create_app(allow_local=True)
    client = TestClient(app)

    # Request only schema rules with ignore SCH-005
    resp = client.post(
        "/api/scans",
        json={
            "target": str(repo),
            "rules": "schema",
            "ignore": ["SCH-005"],
            "fail_on": "error",
        },
    )
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    for _ in range(50):
        res_poll = client.get(f"/api/scans/{scan_id}")
        if res_poll.status_code == 200 and "skills" in res_poll.json():
            data = res_poll.json()
            # SEC-002 should NOT be present because rules="schema"
            findings = data["skills"][0]["findings"]
            rule_ids = [f["rule_id"] for f in findings]
            assert "SEC-002" not in rule_ids
            # SCH-005 should NOT be present because it was ignored
            assert "SCH-005" not in rule_ids
            break
        time.sleep(0.05)


def test_web_similar_skills_endpoint(tmp_path: Path):
    """Verify that /api/scans/{scan_id}/similar computes and returns similar skills."""
    repo = make_repo(
        tmp_path / "web_similar",
        tree={
            ".claude/skills/docker-run/SKILL.md": (
                "---\nname: docker-run\ndescription: Run and manage Docker containers.\ntags:\n  - docker\n---\n"
            ),
            ".claude/skills/docker-runner/SKILL.md": (
                "---\nname: docker-runner\ndescription: Execute tasks inside Docker containers.\ntags:\n  - docker\n---\n"
            ),
        },
    )
    app = create_app(allow_local=True)
    client = TestClient(app)

    resp = client.post("/api/scans", json={"target": str(repo)})
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    for _ in range(50):
        res_poll = client.get(f"/api/scans/{scan_id}")
        if res_poll.status_code == 200 and "skills" in res_poll.json():
            break
        time.sleep(0.05)

    sim_resp = client.get(f"/api/scans/{scan_id}/similar?threshold=0.5")
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["total_skills"] == 2
    assert len(sim_data["matches"]) == 1
    assert sim_data["matches"][0]["score"] >= 0.6


def test_web_filter_ui_elements():
    """Verify that the web interface includes the search/filter input for skills list."""
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="filter-input"' in resp.text
    assert 'placeholder="Filter skills by words in name or description..."' in resp.text
    assert 'oninput="renderSkills()"' in resp.text
    assert "filterWords" in resp.text
    assert "setOriginFilter" in resp.text
