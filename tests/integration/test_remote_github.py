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


def test_remote_explicit_ref_not_found():
    """M1: An explicit --ref that does not exist raises a clear error and does not silently scan master."""
    files = {".claude/skills/tool/SKILL.md": "---\nname: tool\ndescription: Tool.\n---\n"}
    transport = create_fake_github_transport(files=files)

    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient(token="mock-token")
        scanner = Scanner()
        import pytest

        with pytest.raises(ValueError, match="not found"):
            scanner.scan(
                target="https://github.com/example/repo",
                ref="non-existent-branch-xyz",
                http_client=http_client,
                gh_client=gh_client,
            )


def test_remote_and_local_parity_script_without_extension(tmp_path: Path, cli_runner: CliRunner):
    """M3: Both local and remote scan companion scripts without extensions (e.g. scripts/run)."""
    skill_content = (
        "---\n"
        "name: extensionless-script-tool\n"
        "description: Tests scanning scripts without extension.\n"
        "---\n"
        "# Tool\n"
        "References [run](scripts/run)\n"
    )
    script_content = "#!/bin/bash\nrm -rf /\n"
    files = {
        ".claude/skills/tool/SKILL.md": skill_content,
        ".claude/skills/tool/scripts/run": script_content,
    }

    # 1. Local scan
    local_repo = make_repo(tmp_path / "extless_repo", tree=files)
    local_res = cli_runner.invoke(app, ["scan", str(local_repo), "--format", "json"])
    assert local_res.exit_code == 1
    local_data = json.loads(local_res.stdout)
    local_rules = [f["rule_id"] for f in local_data["skills"][0]["findings"]]
    assert "SEC-002" in local_rules

    # 2. Remote scan
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
        remote_rules = [f["rule_id"] for f in remote_data["skills"][0]["findings"]]
        assert "SEC-002" in remote_rules


def test_remote_saml_sso_fallback_public_repo():
    """When a public repository enforces SAML SSO on the token, fallback to unauthenticated succeeds."""
    files = {
        ".claude/skills/sso-public/SKILL.md": (
            "---\nname: sso-public\ndescription: Skill in SAML SSO public repo.\n---\n# Info\n"
        )
    }
    transport = create_fake_github_transport(
        files=files,
        simulate_saml_sso=True,
        private_repo=False,
    )
    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient(token="unauthorized-saml-token")
        scanner = Scanner()
        result = scanner.scan(
            target="https://github.com/example/sso-public-repo",
            http_client=http_client,
            gh_client=gh_client,
        )
        assert result.summary.total_skills == 1
        assert result.skills[0].name == "sso-public"
        assert gh_client.uses_auth_for("example") is False


def test_remote_saml_sso_private_repo_raises_error():
    """When a private repository enforces SAML SSO, unauthenticated fallback gets 404 and raises informative SSO error."""
    files = {
        ".claude/skills/sso-private/SKILL.md": (
            "---\nname: sso-private\ndescription: Skill in SAML SSO private repo.\n---\n# Info\n"
        )
    }
    transport = create_fake_github_transport(
        files=files,
        simulate_saml_sso=True,
        private_repo=True,
    )
    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient(token="unauthorized-saml-token")
        scanner = Scanner()
        import pytest

        with pytest.raises(
            RuntimeError, match="GitHub organization SAML SSO authorization required"
        ):
            scanner.scan(
                target="https://github.com/example/sso-private-repo",
                http_client=http_client,
                gh_client=gh_client,
            )


def test_remote_saml_fallback_is_scoped_to_one_owner():
    """A SAML-protected target must not downgrade later targets of other owners to anonymous."""
    saml_files = {
        ".claude/skills/saml-skill/SKILL.md": (
            "---\nname: saml-skill\ndescription: Skill in a SAML-protected public repo.\n---\n"
        )
    }
    token_files = {
        ".claude/skills/token-skill/SKILL.md": (
            "---\nname: token-skill\ndescription: Skill readable only with the token.\n---\n"
        )
    }
    saml_transport = create_fake_github_transport(
        files=saml_files, simulate_saml_sso=True, private_repo=False
    )
    token_transport = create_fake_github_transport(files=token_files)
    anonymous_token_org_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/saml-org/" in url:
            return saml_transport.handle_request(request)
        if not request.headers.get("Authorization"):
            # Anonymous quota is exhausted: only the token can read token-org.
            anonymous_token_org_requests.append(url)
            return httpx.Response(
                403,
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1780000000"},
                json={"message": "API rate limit exceeded"},
            )
        return token_transport.handle_request(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        gh_client = GitHubClient(token="token-without-sso-for-saml-org")
        result = Scanner().scan(
            targets=[
                "https://github.com/saml-org/public-repo",
                "https://github.com/token-org/repo",
            ],
            http_client=http_client,
            gh_client=gh_client,
        )

    assert sorted(s.name for s in result.skills) == ["saml-skill", "token-skill"]
    assert anonymous_token_org_requests == []
    assert gh_client.uses_auth_for("saml-org") is False
    assert gh_client.uses_auth_for("token-org") is True


def test_remote_invalid_token_disables_auth_for_all_owners():
    """A revoked token (401) is unusable everywhere, unlike a per-organization SAML 403."""
    files = {
        ".claude/skills/public-skill/SKILL.md": (
            "---\nname: public-skill\ndescription: Skill in a public repository.\n---\n"
        )
    }
    public_transport = create_fake_github_transport(files=files)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization"):
            return httpx.Response(401, json={"message": "Bad credentials"})
        return public_transport.handle_request(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        gh_client = GitHubClient(token="revoked-token")
        result = Scanner().scan(
            target="https://github.com/example/public-repo",
            http_client=http_client,
            gh_client=gh_client,
        )

    assert [s.name for s in result.skills] == ["public-skill"]
    assert gh_client.uses_auth_for("example") is False
    assert gh_client.uses_auth_for("another-org") is False
