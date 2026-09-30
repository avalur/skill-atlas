"""Integration tests for remote GitHub scanning using httpx.MockTransport."""

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from skill_atlas.cli import app
from skill_atlas.git.github import GitHubClient
from skill_atlas.scanner import Scanner
from tests.conftest import create_fake_github_transport, make_repo


def test_remote_discovery_with_fake_github():
    """Verify end-to-end remote scanning against simulated GitHub API responses."""
    files = {
        ".claude/skills/code-review/SKILL.md": (
            "---\n"
            "name: code-review\n"
            "description: Automated pull request code review assistant.\n"
            "---\n"
            "# Code Review\n"
            "References [helper.sh](scripts/helper.sh)\n"
        ),
        ".claude/skills/code-review/scripts/helper.sh": "#!/usr/bin/env bash\necho 'Reviewing code...'\n",
    }
    commits = {
        ".claude/skills/code-review": [
            {
                "sha": "9999999999999999999999999999999999999999",
                "commit": {
                    "author": {"date": "2026-09-10T15:00:00Z"},
                    "committer": {"date": "2026-09-10T15:00:00Z"},
                    "message": "Add code review skill",
                },
            }
        ]
    }

    transport = create_fake_github_transport(files=files, commits_by_path=commits)
    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient(token="mock-token")
        scanner = Scanner()
        result = scanner.scan(
            target="https://github.com/example/repo",
            http_client=http_client,
            gh_client=gh_client,
        )

        assert result.summary.total_skills == 1
        assert result.summary.passed == 1
        skill = result.skills[0]
        assert skill.name == "code-review"
        assert skill.commit == "9999999999999999999999999999999999999999"
        assert skill.commit_date == "2026-09-10T15:00:00Z"
        assert skill.origin == "agent-config"


def test_remote_rate_limit_handling():
    """Exhausted rate limit triggers a clean RateLimitError with reset timestamp."""
    files = {".claude/skills/tool/SKILL.md": "---\nname: tool\ndescription: A tool.\n---\n"}
    transport = create_fake_github_transport(files=files, simulate_rate_limit=True)

    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient(token=None)
        scanner = Scanner()
        import pytest

        from skill_atlas.git.github import RateLimitError

        with pytest.raises(RateLimitError) as exc_info:
            scanner.scan(
                target="https://github.com/example/repo",
                http_client=http_client,
                gh_client=gh_client,
            )
        assert "GitHub rate limit reached" in str(exc_info.value)
        assert "set GITHUB_TOKEN" in str(exc_info.value)


def test_remote_repository_not_found():
    """Non-existent GitHub repository triggers a clear error."""
    files = {}
    transport = create_fake_github_transport(files=files)

    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient()
        scanner = Scanner()
        import pytest

        with pytest.raises(ValueError, match="not found"):
            scanner.scan(
                target="https://github.com/example/not-found",
                http_client=http_client,
                gh_client=gh_client,
            )


def test_remote_and_local_parity(tmp_path: Path, cli_runner: CliRunner):
    """The local and remote scan paths must produce identical ScanResult JSON."""
    skill_content = (
        "---\n"
        "name: parity-skill\n"
        "description: Tests parity between local clone and remote API scanning.\n"
        "---\n"
        "# Parity\n"
    )
    files = {
        ".claude/skills/parity/SKILL.md": skill_content,
    }

    # 1. Local scan
    local_repo = make_repo(tmp_path / "parity_repo", tree=files)
    local_res = cli_runner.invoke(app, ["scan", str(local_repo), "--format", "json"])
    assert local_res.exit_code == 0
    local_data = json.loads(local_res.stdout)

    # 2. Remote scan with matching files
    transport = create_fake_github_transport(files=files)
    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient()
        scanner = Scanner()
        remote_result = scanner.scan(
            target="https://github.com/example/repo",
            http_client=http_client,
            gh_client=gh_client,
        )
        remote_data = json.loads(remote_result.model_dump_json())

    # Assert structural parity (ignoring target and repo metadata differences)
    assert local_data["summary"]["total_skills"] == remote_data["summary"]["total_skills"]
    assert local_data["summary"]["passed"] == remote_data["summary"]["passed"]
    assert local_data["summary"]["failed"] == remote_data["summary"]["failed"]

    local_skill = local_data["skills"][0]
    remote_skill = remote_data["skills"][0]
    assert local_skill["name"] == remote_skill["name"]
    assert local_skill["description"] == remote_skill["description"]
    assert local_skill["valid"] == remote_skill["valid"]
    assert local_skill["origin"] == remote_skill["origin"]
    assert len(local_skill["findings"]) == len(remote_skill["findings"])
