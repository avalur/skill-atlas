"""Unit tests for multi-repository scanning, target normalization, query filtering, and data models."""

from pathlib import Path

import pytest

from skill_atlas.models import (
    Finding,
    ProgressEvent,
    ScanResult,
    ScanSummary,
    Severity,
    Skill,
    SkillOrigin,
    Stage,
    matches_query,
)
from skill_atlas.scanner import Scanner, normalize_targets, parse_targets_file


def test_normalize_targets_basic():
    """Test normalizing single and multiple targets."""
    # Empty inputs default to ["."]
    assert normalize_targets() == ["."]
    assert normalize_targets(None) == ["."]
    assert normalize_targets([]) == ["."]
    assert normalize_targets("") == ["."]
    assert normalize_targets("   ") == ["."]

    # Single string target
    assert normalize_targets("tests/fixtures/valid_skill") == ["tests/fixtures/valid_skill"]
    assert normalize_targets("tests/fixtures/valid_skill/") == ["tests/fixtures/valid_skill"]

    # Multiple targets
    targets = ["tests/fixtures/valid_skill", "tests/fixtures/vulnerable_skills"]
    assert normalize_targets(targets) == targets

    # Target keyword parameter
    assert normalize_targets(target="repo1") == ["repo1"]
    assert normalize_targets(target="repo1", targets=["repo2"]) == ["repo1", "repo2"]


def test_normalize_targets_deduplication_and_ordering():
    """Test deduplication preserves declaration order and normalizes equivalent paths."""
    targets = [
        "skills/alpha",
        "skills/beta",
        "skills/alpha/",
        "skills/gamma",
        "skills/beta",
    ]
    assert normalize_targets(targets) == ["skills/alpha", "skills/beta", "skills/gamma"]

    # Remote URLs
    remote_targets = [
        "https://github.com/org/repo-a.git/",
        "https://github.com/org/repo-b.git",
        "https://github.com/org/repo-a.git",
    ]
    assert normalize_targets(remote_targets) == [
        "https://github.com/org/repo-a.git",
        "https://github.com/org/repo-b.git",
    ]


def test_matches_query_fields():
    """Test matches_query matches across name, description, path, repo_name, and tags."""
    skill = Skill(
        name="git-workflow-helper",
        description="Automates git branch creation and pr creation",
        path="skills/vcs/git-helper",
        repo_name="acme-corp/agent-skills",
        tags=["Git", "Automation", "Workflow"],
        origin=SkillOrigin.STANDALONE,
    )

    # Empty query matches everything
    assert matches_query(skill, "") is True
    assert matches_query(skill, "   ") is True

    # Case-insensitive matching across fields
    assert matches_query(skill, "WORKFLOW") is True
    assert matches_query(skill, "automates") is True
    assert matches_query(skill, "vcs") is True
    assert matches_query(skill, "acme-corp") is True
    assert matches_query(skill, "automation") is True
    assert matches_query(skill, "git") is True

    # Non-matching queries
    assert matches_query(skill, "kubernetes") is False
    assert matches_query(skill, "docker") is False


def test_matches_query_optional_none_fields():
    """Test matches_query gracefully handles None or empty fields."""
    skill = Skill(
        name="simple-skill",
        description="",
        path="simple-skill",
        repo_name=None,
        tags=[],
        origin=SkillOrigin.STANDALONE,
    )

    assert matches_query(skill, "simple") is True
    assert matches_query(skill, "nonexistent") is False


def test_scan_result_data_contract_backward_compatibility():
    """Test ScanResult maintains backward compatibility between target and targets."""
    summary = ScanSummary(total_skills=1, passed=1, failed=0)
    skill = Skill(name="test", path="test", origin=SkillOrigin.STANDALONE)

    # Initialized with single target: targets is populated
    r1 = ScanResult(target="repo1", summary=summary, skills=[skill])
    assert r1.target == "repo1"
    assert r1.targets == ["repo1"]
    assert r1.query is None

    # Initialized with targets: target is populated with first element
    r2 = ScanResult(targets=["repo1", "repo2"], query="test-q", summary=summary, skills=[skill])
    assert r2.target == "repo1"
    assert r2.targets == ["repo1", "repo2"]
    assert r2.query == "test-q"

    # Serialization and deserialization
    data = r2.model_dump()
    assert data["target"] == "repo1"
    assert data["targets"] == ["repo1", "repo2"]
    assert data["query"] == "test-q"

    # Deserializing legacy format without targets
    legacy_data = {
        "version": "0.2.0",
        "target": "legacy-repo",
        "summary": summary.model_dump(),
        "skills": [skill.model_dump()],
    }
    r3 = ScanResult.model_validate(legacy_data)
    assert r3.target == "legacy-repo"
    assert r3.targets == ["legacy-repo"]


def test_progress_event_target_context():
    """Test ProgressEvent supports target indexing and naming."""
    event = ProgressEvent(
        stage=Stage.DISCOVER,
        message="[1/2] Searching for skills in repo1...",
        target_index=1,
        target_total=2,
        target_name="repo1",
    )
    assert event.target_index == 1
    assert event.target_total == 2
    assert event.target_name == "repo1"


def test_scanner_multi_target_scan(tmp_path: Path):
    """Test Scanner.scan discovering and aggregating skills across multiple targets."""
    fixture_valid = Path("tests/fixtures/valid_skill").resolve()
    fixture_vuln = Path("tests/fixtures/vulnerable_skills").resolve()

    events: list[ProgressEvent] = []

    def on_progress(ev: ProgressEvent) -> None:
        events.append(ev)

    scanner = Scanner()
    result = scanner.scan(
        targets=[fixture_valid, fixture_vuln],
        on_progress=on_progress,
    )

    # Targets recorded in result
    assert result.targets == [str(fixture_valid), str(fixture_vuln)]
    assert result.target == str(fixture_valid)

    # Discovered skills from both targets
    skill_names = {s.name for s in result.skills}
    assert "sample-valid-skill" in skill_names
    assert "dangerous-command-skill" in skill_names

    # Check progress events received target context
    target_indices = {e.target_index for e in events if e.target_index is not None}
    assert target_indices == {1, 2}
    target_totals = {e.target_total for e in events if e.target_total is not None}
    assert target_totals == {2}


def test_scanner_query_filter_audit_scope():
    """Test Scanner.scan applies query filtering before rule evaluation."""
    fixture_valid = Path("tests/fixtures/valid_skill").resolve()
    fixture_vuln = Path("tests/fixtures/vulnerable_skills").resolve()

    scanner = Scanner()
    # Filter for sample-valid-skill specifically
    result = scanner.scan(
        targets=[fixture_valid, fixture_vuln],
        query="sample-valid-skill",
    )

    assert result.query == "sample-valid-skill"
    assert len(result.skills) == 1
    assert result.skills[0].name == "sample-valid-skill"
    assert result.summary.total_skills == 1
    # Only sample-valid-skill was audited, so zero errors
    assert result.summary.findings_count["error"] == 0
    assert result.exit_code() == 0


def test_scanner_query_zero_matches():
    """Test query matching zero skills results in clean exit code 0."""
    fixture_valid = Path("tests/fixtures/valid_skill").resolve()

    scanner = Scanner()
    result = scanner.scan(
        targets=[fixture_valid],
        query="nonexistent-skill-query-xyz",
    )

    assert result.query == "nonexistent-skill-query-xyz"
    assert len(result.skills) == 0
    assert result.summary.total_skills == 0
    assert result.exit_code() == 0
    assert result.has_failures() is False


def test_cross_repository_duplicate_isolation():
    """Test that skills with identical names in separate targets are not merged."""
    s1 = Skill(
        name="shared-skill",
        path="skills/shared-skill",
        repo_name="org-a/repo",
        repo_url="https://github.com/org-a/repo.git",
        origin=SkillOrigin.AGENT_CONFIG,
    )
    s2 = Skill(
        name="shared-skill",
        path="skills/shared-skill",
        repo_name="org-b/repo",
        repo_url="https://github.com/org-b/repo.git",
        origin=SkillOrigin.AGENT_CONFIG,
    )

    from skill_atlas.scanner import is_duplicate_candidate

    assert is_duplicate_candidate(s1, s2) is False


def test_deterministic_sorting():
    """Test skills are sorted primarily by repo_name, then by path."""
    skills = [
        Skill(name="s3", path="b/z", repo_name="repo-b", origin=SkillOrigin.STANDALONE),
        Skill(name="s1", path="a/b", repo_name="repo-a", origin=SkillOrigin.STANDALONE),
        Skill(name="s4", path="b/a", repo_name="repo-b", origin=SkillOrigin.STANDALONE),
        Skill(name="s2", path="a/a", repo_name="repo-a", origin=SkillOrigin.STANDALONE),
        Skill(name="s0", path="local/path", repo_name=None, origin=SkillOrigin.STANDALONE),
    ]

    skills.sort(key=lambda s: (s.repo_name or "", s.path))

    assert [s.name for s in skills] == ["s0", "s2", "s1", "s4", "s3"]


def test_scanner_scan_calling_conventions():
    """Test Scanner.scan supports various positional and keyword calling patterns."""
    fixture_valid = Path("tests/fixtures/valid_skill").resolve()
    scanner = Scanner()

    # 1. Positional string
    res1 = scanner.scan(str(fixture_valid))
    assert res1.target == str(fixture_valid)
    assert res1.targets == [str(fixture_valid)]

    # 2. Positional list
    res2 = scanner.scan([str(fixture_valid)])
    assert res2.target == str(fixture_valid)
    assert res2.targets == [str(fixture_valid)]

    # 3. Keyword target
    res3 = scanner.scan(target=str(fixture_valid))
    assert res3.target == str(fixture_valid)
    assert res3.targets == [str(fixture_valid)]

    # 4. Keyword targets
    res4 = scanner.scan(targets=[str(fixture_valid)])
    assert res4.target == str(fixture_valid)
    assert res4.targets == [str(fixture_valid)]


def test_parse_targets_file_comments_and_whitespace(tmp_path: Path):
    """Test parsing a targets file with comments, whitespace, and inline comments."""
    file = tmp_path / "targets.txt"
    file.write_text(
        "# Core repositories\n"
        "  /path/to/repo1  \n"
        "\n"
        "# Secondary with inline comment\n"
        "https://github.com/org/repo2.git # Main agent repo\n"
        "   \n"
        "https://github.com/org/repo3.git\n",
        encoding="utf-8",
    )

    targets = parse_targets_file(file)
    assert targets == [
        "/path/to/repo1",
        "https://github.com/org/repo2.git",
        "https://github.com/org/repo3.git",
    ]


def test_parse_targets_file_not_found(tmp_path: Path):
    """Test parsing a nonexistent targets file raises FileNotFoundError."""
    missing = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError, match="Targets file not found"):
        parse_targets_file(missing)


def test_parse_targets_file_empty_or_all_comments(tmp_path: Path):
    """Test parsing an empty or comment-only file raises ValueError."""
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no valid targets"):
        parse_targets_file(empty_file)

    comment_file = tmp_path / "comments.txt"
    comment_file.write_text("# Only comments\n# Another comment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no valid targets"):
        parse_targets_file(comment_file)


def test_scan_result_has_failures_and_exit_code():
    """Test ScanResult failure detection and exit codes with multi-target results."""
    summary_clean = ScanSummary(
        total_skills=2,
        passed=2,
        failed=0,
        findings_count={"error": 0, "warn": 0, "info": 0},
    )
    res_clean = ScanResult(
        target="target1",
        targets=["target1", "target2"],
        summary=summary_clean,
        skills=[],
    )
    assert res_clean.has_failures(fail_on="error") is False
    assert res_clean.has_failures(fail_on="warn") is False
    assert res_clean.exit_code(fail_on="error") == 0
    assert res_clean.exit_code(fail_on="warn") == 0

    # With warning finding
    warn_finding = Finding(
        rule_id="SEC-001",
        severity=Severity.WARN,
        message="Warning finding",
        file="SKILL.md",
        line=1,
    )
    skill_warn = Skill(
        name="warn-skill",
        path="skills/warn",
        origin=SkillOrigin.STANDALONE,
        findings=[warn_finding],
    )
    summary_warn = ScanSummary(
        total_skills=2,
        passed=1,
        failed=1,
        findings_count={"error": 0, "warn": 1, "info": 0},
    )
    res_warn = ScanResult(
        target="target1",
        targets=["target1", "target2"],
        summary=summary_warn,
        skills=[skill_warn],
    )
    assert res_warn.has_failures(fail_on="error") is False
    assert res_warn.has_failures(fail_on="warn") is True
    assert res_warn.exit_code(fail_on="error") == 0
    assert res_warn.exit_code(fail_on="warn") == 1
