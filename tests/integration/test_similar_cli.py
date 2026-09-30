"""Integration tests for the 'similar' CLI command."""

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from skill_atlas.cli import app

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def test_similar_cli_help(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["similar", "--help"])
    assert result.exit_code == 0
    clean_out = ANSI_RE.sub("", result.stdout)
    assert "similar" in clean_out
    assert "--threshold" in clean_out
    assert "--top-k" in clean_out
    assert "--skill" in clean_out


def test_similar_cli_invalid_options(cli_runner: CliRunner):
    # Invalid target starting with '-'
    res = cli_runner.invoke(app, ["similar", "--nonexistent-arg"])
    assert res.exit_code == 2

    # Invalid threshold < 0 or > 1
    res = cli_runner.invoke(app, ["similar", ".", "--threshold", "1.5"])
    assert res.exit_code == 2

    res = cli_runner.invoke(app, ["similar", ".", "--threshold", "-0.1"])
    assert res.exit_code == 2

    # Invalid format
    res = cli_runner.invoke(app, ["similar", ".", "--format", "yaml"])
    assert res.exit_code == 2

    # Invalid top-k
    res = cli_runner.invoke(app, ["similar", ".", "--top-k", "-5"])
    assert res.exit_code == 2


def test_similar_cli_on_local_skills_text_and_json(tmp_path: Path, cli_runner: CliRunner):
    # Setup two similar skills and one different skill
    skill_a = tmp_path / "docker-run"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text(
        "---\nname: docker-run\ndescription: Run Docker containers and execute tasks\ntags:\n  - docker\n  - containers\n---\n# Run Docker\nInstructions to run docker."
    )

    skill_b = tmp_path / "docker-runner"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text(
        "---\nname: docker-runner\ndescription: Execute and manage Docker containers\ntags:\n  - docker\n  - containers\n---\n# Docker Runner\nInstructions to execute docker."
    )

    skill_c = tmp_path / "code-formatter"
    skill_c.mkdir()
    (skill_c / "SKILL.md").write_text(
        "---\nname: code-formatter\ndescription: Format Python and JavaScript code style\ntags:\n  - linter\n  - formatting\n---\n# Code Formatter\nRun code formatter."
    )

    # Run CLI in text mode
    res_text = cli_runner.invoke(app, ["similar", str(tmp_path), "--threshold", "0.5"])
    assert res_text.exit_code == 0
    assert "Finding similar skills" in res_text.output
    assert "docker-run" in res_text.output
    assert "docker-runner" in res_text.output
    assert "code-formatter" not in res_text.output or "Summary:" in res_text.output

    # Run CLI in JSON mode
    res_json = cli_runner.invoke(
        app, ["similar", str(tmp_path), "--format", "json", "--threshold", "0.5"]
    )
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["total_skills"] == 3
    assert len(data["matches"]) == 1
    match = data["matches"][0]
    assert {match["skill_a"], match["skill_b"]} == {"docker-run", "docker-runner"}
    assert match["score"] >= 0.6
    assert len(match["reasons"]) > 0

    # Query specific skill
    res_query = cli_runner.invoke(
        app, ["similar", str(tmp_path), "--skill", "docker-run", "--format", "json"]
    )
    assert res_query.exit_code == 0
    query_data = json.loads(res_query.output)
    assert len(query_data["matches"]) == 1
    assert query_data["matches"][0]["skill_b"] == "docker-runner"

    # High threshold should return 0 matches
    res_high = cli_runner.invoke(
        app, ["similar", str(tmp_path), "--threshold", "0.99", "--format", "json"]
    )
    assert res_high.exit_code == 0
    high_data = json.loads(res_high.output)
    assert len(high_data["matches"]) == 0
