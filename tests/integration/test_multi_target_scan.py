"""Integration tests for multi-target CLI scanning, targets file, and query filtering."""

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from skill_atlas.cli import app
from tests.conftest import make_repo

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def test_cli_multi_target_positional(tmp_path: Path, cli_runner: CliRunner):
    """Test scanning multiple repository directories via positional arguments."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-one/SKILL.md": (
                "---\nname: skill-one\ndescription: First repository skill.\n---\n"
            )
        },
    )
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/skill-two/SKILL.md": (
                "---\nname: skill-two\ndescription: Second repository skill.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo1), str(repo2)])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Scanning skills across 2 targets:" in clean_out
    assert "Scanned Targets: 2" in clean_out
    assert "Scanned Skills: 2" in clean_out
    assert "skill-one" in clean_out
    assert "skill-two" in clean_out


def test_cli_targets_file_parsing(tmp_path: Path, cli_runner: CliRunner):
    """Test loading target paths from a file with comments and whitespace."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-one/SKILL.md": (
                "---\nname: skill-one\ndescription: Skill one.\n---\n"
            )
        },
    )
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/skill-two/SKILL.md": (
                "---\nname: skill-two\ndescription: Skill two.\n---\n"
            )
        },
    )

    targets_file = tmp_path / "targets.txt"
    targets_file.write_text(
        f"# Core repositories\n{repo1}\n\n# Secondary team repos\n  {repo2}   # inline comment\n\n",
        encoding="utf-8",
    )

    res = cli_runner.invoke(app, ["scan", "-T", str(targets_file)])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Scanning skills across 2 targets:" in clean_out
    assert "Scanned Skills: 2" in clean_out
    assert "skill-one" in clean_out
    assert "skill-two" in clean_out


def test_cli_targets_file_missing(cli_runner: CliRunner):
    """Test exit code 2 when targets file does not exist."""
    res = cli_runner.invoke(app, ["scan", "-T", "nonexistent_targets_file.txt"])
    assert res.exit_code == 2
    clean_err = ANSI_RE.sub("", res.stderr or res.stdout)
    assert "Targets file not found" in clean_err


def test_cli_targets_file_empty(tmp_path: Path, cli_runner: CliRunner):
    """Test exit code 2 when targets file contains only whitespace or comments."""
    empty_file = tmp_path / "empty_targets.txt"
    empty_file.write_text("# Only comments\n\n   # and whitespace\n", encoding="utf-8")

    res = cli_runner.invoke(app, ["scan", "--targets-file", str(empty_file)])
    assert res.exit_code == 2
    clean_err = ANSI_RE.sub("", res.stderr or res.stdout)
    assert "contains no valid targets" in clean_err


def test_cli_combine_positional_and_targets_file(tmp_path: Path, cli_runner: CliRunner):
    """Test combining positional target arguments with --targets-file."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-one/SKILL.md": (
                "---\nname: skill-one\ndescription: Skill one.\n---\n"
            )
        },
    )
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/skill-two/SKILL.md": (
                "---\nname: skill-two\ndescription: Skill two.\n---\n"
            )
        },
    )

    targets_file = tmp_path / "extra_targets.txt"
    targets_file.write_text(f"{repo2}\n", encoding="utf-8")

    res = cli_runner.invoke(app, ["scan", str(repo1), "-T", str(targets_file)])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Scanning skills across 2 targets:" in clean_out
    assert "Scanned Targets: 2" in clean_out
    assert "Scanned Skills: 2" in clean_out


def test_cli_query_filter_audit_scope(tmp_path: Path, cli_runner: CliRunner):
    """Test query filtering scopes audit to only matching skills."""
    # repo1 has a valid skill matching query 'deploy'
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/deploy-tool/SKILL.md": (
                "---\nname: deploy-tool\ndescription: Deployment helper.\n---\n"
            )
        },
    )
    # repo2 has an invalid/vulnerable skill that does NOT match query 'deploy'
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/secret-tool/SKILL.md": (
                "---\nname: secret-tool\ndescription: Has secrets.\n---\nAKIA1234567890ABCDEF\n"
            )
        },
    )

    # Without query: audits both, repo2 triggers exit code 1
    res_no_q = cli_runner.invoke(app, ["scan", str(repo1), str(repo2)])
    assert res_no_q.exit_code == 1

    # With query 'deploy': only repo1 skill is audited, so exit code 0
    res_q = cli_runner.invoke(app, ["scan", str(repo1), str(repo2), "-q", "deploy"])
    assert res_q.exit_code == 0
    clean_out = ANSI_RE.sub("", res_q.stdout)
    assert "Filter query: 'deploy'" in clean_out
    assert "Found 1 matching skills" in clean_out
    assert "deploy-tool" in clean_out
    assert "secret-tool" not in clean_out
    assert "Status: SUCCESS" in clean_out


def test_cli_query_zero_matches(tmp_path: Path, cli_runner: CliRunner):
    """Test query matching zero skills results in exit code 0 and notice."""
    repo = make_repo(
        tmp_path / "repo",
        tree={
            ".claude/skills/test-skill/SKILL.md": (
                "---\nname: test-skill\ndescription: General skill.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--query", "nonexistent-query-string"])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "0 skills matched query 'nonexistent-query-string' across 1 target(s)" in clean_out
    assert "Scanned Skills: 0" in clean_out
    assert "Status: SUCCESS (Exit Code 0)" in clean_out


def test_cli_multi_target_json_output(tmp_path: Path, cli_runner: CliRunner):
    """Test JSON output formatting with multiple targets and query."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-alpha/SKILL.md": (
                "---\nname: skill-alpha\ndescription: Alpha automation.\n---\n"
            )
        },
    )
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/skill-beta/SKILL.md": (
                "---\nname: skill-beta\ndescription: Beta automation.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(
        app,
        ["scan", str(repo1), str(repo2), "-q", "alpha", "--format", "json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)

    assert data["target"] == str(repo1)
    assert data["targets"] == [str(repo1), str(repo2)]
    assert data["query"] == "alpha"
    assert data["summary"]["total_skills"] == 1
    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "skill-alpha"


def test_cli_single_target_backward_compatibility(tmp_path: Path, cli_runner: CliRunner):
    """Test backward-compatible single target console rendering."""
    repo = make_repo(
        tmp_path / "repo_single",
        tree={
            ".claude/skills/skill-single/SKILL.md": (
                "---\nname: skill-single\ndescription: Single target skill.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo)])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Scanning skills in:" in clean_out
    assert "repo_single" in clean_out
    assert "Scanned Targets:" not in clean_out  # Single target preserves Iteration 1 summary
    assert "Scanned Skills: 1" in clean_out


def test_cli_default_target_fallback(monkeypatch, tmp_path: Path, cli_runner: CliRunner):
    """Test running scan without positional arguments defaults to '.'."""
    repo = make_repo(
        tmp_path / "repo_cwd",
        tree={
            ".claude/skills/cwd-skill/SKILL.md": (
                "---\nname: cwd-skill\ndescription: Current directory skill.\n---\n"
            )
        },
    )
    monkeypatch.chdir(repo)

    res = cli_runner.invoke(app, ["scan"])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Scanning skills in:" in clean_out
    assert "cwd-skill" in clean_out


def test_cli_multi_target_fail_on_warn(tmp_path: Path, cli_runner: CliRunner):
    """Test exit code 1 with --fail-on warn across multiple targets."""
    # repo1 is clean
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/clean-skill/SKILL.md": (
                "---\nname: clean-skill\ndescription: A valid clean skill description.\n---\n# Body\n"
            )
        },
    )
    # repo2 triggers a warning (e.g. empty/short description or warning rule)
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/warn-skill/SKILL.md": (
                "---\nname: warn-skill\ndescription: Fix\n---\n# Body\n"
            )
        },
    )

    # Default fail_on='error': exit code 0
    res_err = cli_runner.invoke(app, ["scan", str(repo1), str(repo2), "--fail-on", "error"])
    assert res_err.exit_code == 0

    # With fail_on='warn': exit code 1
    res_warn = cli_runner.invoke(app, ["scan", str(repo1), str(repo2), "--fail-on", "warn"])
    assert res_warn.exit_code == 1


def test_cli_multi_target_rules_filter(tmp_path: Path, cli_runner: CliRunner):
    """Test --rules schema ignores security findings across targets."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/clean-skill/SKILL.md": (
                "---\nname: clean-skill\ndescription: Valid description.\n---\n"
            )
        },
    )
    # repo2 has an AWS secret (security finding), but schema is valid
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/sec-skill/SKILL.md": (
                "---\nname: sec-skill\ndescription: Valid description.\n---\nAKIAIOSFODNN7EXAMPLE\n"
            )
        },
    )

    # With --rules schema: security rule SEC-001 is not executed
    res = cli_runner.invoke(app, ["scan", str(repo1), str(repo2), "--rules", "schema"])
    assert res.exit_code == 0


def test_cli_multi_target_json_zero_matches(tmp_path: Path, cli_runner: CliRunner):
    """Test JSON output structure when query matches zero skills across multiple targets."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-one/SKILL.md": (
                "---\nname: skill-one\ndescription: Skill one.\n---\n"
            )
        },
    )
    repo2 = make_repo(
        tmp_path / "repo2",
        tree={
            ".claude/skills/skill-two/SKILL.md": (
                "---\nname: skill-two\ndescription: Skill two.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(
        app,
        ["scan", str(repo1), str(repo2), "-q", "unmatched-xyz", "--format", "json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["query"] == "unmatched-xyz"
    assert data["targets"] == [str(repo1), str(repo2)]
    assert data["summary"]["total_skills"] == 0
    assert data["skills"] == []


def test_cli_multi_target_deduplication(tmp_path: Path, cli_runner: CliRunner):
    """Test passing duplicate targets or trailing slashes on CLI deduplicates cleanly."""
    repo1 = make_repo(
        tmp_path / "repo1",
        tree={
            ".claude/skills/skill-one/SKILL.md": (
                "---\nname: skill-one\ndescription: Skill one.\n---\n"
            )
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo1), f"{repo1}/", str(repo1)])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    # Deduplicates to a single target
    assert "Scanning skills in:" in clean_out
    assert "Scanned Skills: 1" in clean_out
