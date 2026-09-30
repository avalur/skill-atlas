"""Opt-in integration tests calling the real GitHub API (marked with network)."""

import pytest
from typer.testing import CliRunner

from skill_atlas.cli import app


@pytest.mark.network
def test_real_github_scan_kotlin_repo(cli_runner: CliRunner):
    """Scan JetBrains/kotlin via real GitHub API (requires network or GITHUB_TOKEN)."""
    res = cli_runner.invoke(app, ["scan", "https://github.com/JetBrains/kotlin"])
    assert res.exit_code == 0
    assert "Found 6 skills" in res.stdout or "Scanned Skills: 6" in res.stdout
    assert "Status: SUCCESS" in res.stdout
