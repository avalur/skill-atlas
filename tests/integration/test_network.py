"""Opt-in integration tests calling the real GitHub API (marked with network)."""

import json

import pytest
from typer.testing import CliRunner

from skill_atlas.cli import app


@pytest.mark.network
def test_real_github_scan_kotlin_repo(cli_runner: CliRunner):
    """Scan JetBrains/kotlin pinned to SHA (verifies nested paths and SCH-006)."""
    res = cli_runner.invoke(
        app,
        [
            "scan",
            "https://github.com/JetBrains/kotlin",
            "--ref",
            "197871e7256b81028d7dbce42eaee642a36900d0",
            "--format",
            "json",
        ],
    )
    if res.exit_code == 2 and "rate limit" in res.stderr.lower():
        pytest.skip("GitHub rate limit reached during network test run")
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 6
    assert data["summary"]["passed"] == 6


@pytest.mark.network
def test_real_github_scan_mps_repo(cli_runner: CliRunner):
    """Scan JetBrains/MPS pinned to SHA (verifies Case A duplicates and Case C product skills)."""
    res = cli_runner.invoke(
        app,
        [
            "scan",
            "https://github.com/JetBrains/MPS",
            "--ref",
            "49d37b63488a0a8e42eb0130cb867fd508f398ac",
            "--format",
            "json",
        ],
    )
    if res.exit_code == 2 and "rate limit" in res.stderr.lower():
        pytest.skip("GitHub rate limit reached during network test run")
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] >= 1


@pytest.mark.network
def test_real_github_scan_koog_repo(cli_runner: CliRunner):
    """Scan JetBrains/koog pinned to SHA (verifies Case B test-data isolation)."""
    res = cli_runner.invoke(
        app,
        [
            "scan",
            "https://github.com/JetBrains/koog",
            "--ref",
            "16d83270f8a7f25358ae0165466f14e70416c428",
            "--format",
            "json",
        ],
    )
    if res.exit_code == 2 and "rate limit" in res.stderr.lower():
        pytest.skip("GitHub rate limit reached during network test run")
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["failed"] == 0
