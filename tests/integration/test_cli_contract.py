"""Integration tests for CLI contract, options, and deterministic exit codes."""

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from skill_atlas.cli import app
from tests.conftest import make_repo

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def test_cli_help(cli_runner: CliRunner):
    res = cli_runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "scan" in clean_out
    assert "serve" in clean_out


def test_cli_version(cli_runner: CliRunner):
    res = cli_runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "skill-atlas version:" in res.stdout


def test_cli_invalid_target_starting_with_dash(cli_runner: CliRunner):
    res = cli_runner.invoke(app, ["scan", "-invalid-target"])
    assert res.exit_code == 2


def test_cli_non_existent_target(cli_runner: CliRunner):
    res = cli_runner.invoke(app, ["scan", "/non/existent/path/for/skills"])
    assert res.exit_code == 2


def test_cli_invalid_options(cli_runner: CliRunner):
    res_fmt = cli_runner.invoke(app, ["scan", ".", "--format", "xml"])
    assert res_fmt.exit_code == 2
    assert "Invalid format" in res_fmt.stderr or "Invalid format" in res_fmt.stdout

    res_fail = cli_runner.invoke(app, ["scan", ".", "--fail-on", "critical"])
    assert res_fail.exit_code == 2

    res_rules = cli_runner.invoke(app, ["scan", ".", "--rules", "unknown"])
    assert res_rules.exit_code == 2


def test_cli_exit_code_zero_on_clean_scan(tmp_path: Path, cli_runner: CliRunner):
    repo = make_repo(
        tmp_path / "clean_repo",
        tree={
            ".claude/skills/clean/SKILL.md": (
                "---\nname: clean-skill\ndescription: Perfectly valid skill manifest.\n---\n# Clean\n"
            )
        },
    )
    res = cli_runner.invoke(app, ["scan", str(repo)])
    assert res.exit_code == 0
    assert "Status: SUCCESS" in res.stdout


def test_cli_exit_code_one_on_blocking_error(tmp_path: Path, cli_runner: CliRunner):
    repo = make_repo(
        tmp_path / "err_repo",
        tree={
            ".claude/skills/err/SKILL.md": (
                "---\nname: err-skill\ndescription: Has a secret.\n---\nAKIA1234567890ABCDEF\n"
            )
        },
    )
    res = cli_runner.invoke(app, ["scan", str(repo)])
    assert res.exit_code == 1
    assert "Status: FAILED" in res.stdout
    assert "SEC-001" in res.stdout


def test_cli_ignore_flag(tmp_path: Path, cli_runner: CliRunner):
    repo = make_repo(
        tmp_path / "ignore_repo",
        tree={
            ".claude/skills/err/SKILL.md": (
                "---\nname: err-skill\ndescription: Has a secret.\n---\nAKIA1234567890ABCDEF\n"
            )
        },
    )
    res = cli_runner.invoke(app, ["scan", str(repo), "--ignore", "SEC-001"])
    assert res.exit_code == 0
    assert "Status: SUCCESS" in res.stdout


def test_cli_json_output_structure(tmp_path: Path, cli_runner: CliRunner):
    repo = make_repo(
        tmp_path / "json_repo",
        tree={
            ".claude/skills/my-tool/SKILL.md": (
                "---\nname: my-tool\ndescription: Useful automation skill.\n---\n"
            )
        },
    )
    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "version" in data
    assert "summary" in data
    assert "skills" in data
    assert data["summary"]["total_skills"] == 1
    assert data["summary"]["by_origin"]["agent-config"] == 1


def test_cli_serve_help(cli_runner: CliRunner):
    res = cli_runner.invoke(app, ["serve", "--help"])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "--host" in clean_out
    assert "--port" in clean_out
    assert "--open" in clean_out
    assert "--allow-local" in clean_out
