"""Integration tests for `skill-atlas map` CLI command."""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from skill_atlas.cli import app

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
runner = CliRunner()


def test_cli_map_help() -> None:
    res = runner.invoke(app, ["map", "--help"])
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Generate a Skill Map" in clean_out
    assert "--method" in clean_out
    assert "--ai" in clean_out
    assert "--jev" in clean_out
    assert "--threshold" in clean_out


def test_cli_map_heuristic_visual_repo() -> None:
    res = runner.invoke(
        app,
        ["map", "tests/fixtures/visual_repo/", "--include-test-data"],
    )
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "Skill Map for:" in clean_out
    assert "Heuristic" in clean_out
    assert "shared-memory" in clean_out
    assert "memory-vault" in clean_out


def test_cli_map_json_format() -> None:
    res = runner.invoke(
        app,
        ["map", "tests/fixtures/visual_repo/", "--include-test-data", "--format", "json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["method"] == "heuristic"
    assert data["total_skills"] == 5
    assert len(data["clusters"]) >= 1


def test_cli_map_ai_replay() -> None:
    replay_file = "tests/fixtures/recorded_claude_map_visual.json"
    res = runner.invoke(
        app,
        [
            "map",
            "tests/fixtures/visual_repo/",
            "--include-test-data",
            "--ai",
            "--replay",
            replay_file,
        ],
    )
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "AI (Claude)" in clean_out
    assert "Agent Memory Management" in clean_out


def test_cli_map_jev_replay() -> None:
    replay_file = "tests/fixtures/recorded_jev_map_visual.json"
    res = runner.invoke(
        app,
        [
            "map",
            "tests/fixtures/visual_repo/",
            "--include-test-data",
            "--jev",
            "--replay",
            replay_file,
        ],
    )
    assert res.exit_code == 0
    clean_out = ANSI_RE.sub("", res.stdout)
    assert "AI (TypeSafe Jev)" in clean_out
    assert "Agent Memory & State" in clean_out


def test_cli_map_invalid_method() -> None:
    res = runner.invoke(app, ["map", ".", "--method", "unknown"])
    assert res.exit_code == 2
    assert "Invalid method" in res.output


def test_cli_map_invalid_format() -> None:
    res = runner.invoke(app, ["map", ".", "--format", "xml"])
    assert res.exit_code == 2
    assert "Invalid format" in res.output


def test_cli_map_invalid_target() -> None:
    res = runner.invoke(app, ["map", "-invalid-flag"])
    assert res.exit_code == 2
