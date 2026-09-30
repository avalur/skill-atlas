"""Tests for shared memory integrity and shared-memory skill compliance."""

import subprocess
import sys
from pathlib import Path

from skill_atlas.discovery.local import discover_local_skills
from skill_atlas.models import Severity, SkillOrigin
from skill_atlas.scanner import Scanner


def test_shared_memory_files_exist():
    repo_root = Path(__file__).resolve().parent.parent.parent
    memory_dir = repo_root / "memory"
    assert memory_dir.is_dir()

    expected_files = [
        "README.md",
        "architecture.md",
        "workflows.md",
        "gotchas.md",
        "rules-and-skills.md",
        "known-issues.md",
    ]
    for filename in expected_files:
        f = memory_dir / filename
        assert f.is_file(), f"Expected {filename} in memory/"
        assert f.stat().st_size > 0, f"Memory file {filename} is empty"


def test_shared_memory_verification_script():
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = (
        repo_root / ".claude" / "skills" / "shared-memory" / "scripts" / "verify_memory.py"
    )
    assert script_path.is_file()

    res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    assert res.returncode == 0, f"Script failed: {res.stdout}\n{res.stderr}"
    assert "SUCCESS: Shared memory verified" in res.stdout


def test_shared_memory_skill_valid_and_passing():
    repo_root = Path(__file__).resolve().parent.parent.parent
    skill_dir = repo_root / ".claude" / "skills" / "shared-memory"
    assert (skill_dir / "SKILL.md").is_file()

    skills = discover_local_skills(skill_dir)
    assert len(skills) == 1
    skill = skills[0]

    assert skill.name == "shared-memory"
    assert skill.origin == SkillOrigin.AGENT_CONFIG
    assert skill.description != ""
    assert "memory" in skill.tags

    scanner = Scanner()
    result = scanner.scan(skill_dir)
    assert result.summary.total_skills == 1
    assert result.summary.passed == 1
    assert result.summary.failed == 0
    errors = [f for s in result.skills for f in s.findings if f.severity == Severity.ERROR]
    assert len(errors) == 0


def test_agents_md_contains_shared_memory_directives():
    repo_root = Path(__file__).resolve().parent.parent.parent
    agents_md = (repo_root / "AGENTS.md").read_text(encoding="utf-8")

    assert "ALWAYS read `memory/` before a task" in agents_md
    assert "ALWAYS update shared memory with the `shared-memory` skill" in agents_md
    assert "Shared Memory Policy" in agents_md
