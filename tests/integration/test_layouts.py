"""Integration tests for repository layouts and corner cases (Case A, Case B, Case C)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from skill_atlas.cli import app
from skill_atlas.models import SkillOrigin, classify_origin
from tests.conftest import CommitDef, make_repo


def test_classify_origin_rules():
    assert classify_origin(".claude/skills/my-tool") == SkillOrigin.AGENT_CONFIG
    assert classify_origin(".agents/skills/my-tool") == SkillOrigin.AGENT_CONFIG
    assert classify_origin(".junie/skills/helper") == SkillOrigin.AGENT_CONFIG
    assert classify_origin(".cursor/skills/refactor") == SkillOrigin.AGENT_CONFIG
    assert classify_origin(".codex/skills/runner") == SkillOrigin.AGENT_CONFIG
    assert classify_origin(".github/skills/ci") == SkillOrigin.AGENT_CONFIG

    assert classify_origin("tests/fixtures/skills/broken") == SkillOrigin.TEST_DATA
    assert classify_origin("src/test/resources/skills/broken") == SkillOrigin.TEST_DATA
    assert classify_origin("testData/skills/sample") == SkillOrigin.TEST_DATA
    assert classify_origin("test-resources/skills/sample") == SkillOrigin.TEST_DATA

    assert classify_origin("src/main/resources/skills/editor") == SkillOrigin.PRODUCT
    assert classify_origin("resources/skills/terminal") == SkillOrigin.PRODUCT
    assert classify_origin("plugins/kotlin-plugin/resources/skills/fmt") == SkillOrigin.PRODUCT
    assert classify_origin("languages/mps-lang/skills/dsl") == SkillOrigin.PRODUCT

    assert classify_origin("skills/general-assistant") == SkillOrigin.STANDALONE
    assert classify_origin("custom/tools/skill-one") == SkillOrigin.STANDALONE


def test_case_a_identical_duplicates(tmp_path: Path, cli_runner: CliRunner):
    """Identical copies in .claude and .agents are deduped, 1 skill reported, no DSC-001."""
    skill_content = (
        "---\n"
        "name: duplicate-helper\n"
        "description: A helper skill that exists in multiple agent directories.\n"
        "---\n"
        "# Helper\n"
    )
    repo = make_repo(
        tmp_path / "repo_a1",
        commits=[
            CommitDef(
                message="Add helper to .claude",
                files={".claude/skills/helper/SKILL.md": skill_content},
                date="2026-09-01T10:00:00Z",
            ),
            CommitDef(
                message="Add helper to .agents",
                files={".agents/skills/helper/SKILL.md": skill_content},
                date="2026-09-02T10:00:00Z",
            ),
        ],
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)

    assert data["summary"]["total_skills"] == 1
    assert data["summary"]["passed"] == 1
    assert data["summary"]["findings_count"]["warn"] == 0

    skill = data["skills"][0]
    assert skill["name"] == "duplicate-helper"
    # Newest copy (.agents, updated 2026-09-02) should be displayed
    assert skill["path"] == ".agents/skills/helper"
    assert len(skill["duplicates"]) == 1
    dup = skill["duplicates"][0]
    assert dup["path"] == ".claude/skills/helper"
    assert dup["identical"] is True


def test_case_a_divergent_duplicates_fires_dsc_001(tmp_path: Path, cli_runner: CliRunner):
    """Divergent copies fire DSC-001 Stale Duplicate pointing to older copy."""
    content_old = (
        "---\nname: sync-tool\ndescription: Older version of the sync tool skill.\n---\n# Old\n"
    )
    content_new = (
        "---\nname: sync-tool\ndescription: Brand new version of the sync tool skill.\n---\n# New\n"
    )

    repo = make_repo(
        tmp_path / "repo_a2",
        commits=[
            CommitDef(
                message="Add older version to .claude",
                files={".claude/skills/sync-tool/SKILL.md": content_old},
                date="2026-05-01T10:00:00Z",
            ),
            CommitDef(
                message="Add updated version to .agents",
                files={".agents/skills/sync-tool/SKILL.md": content_new},
                date="2026-09-15T12:00:00Z",
            ),
        ],
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)

    assert data["summary"]["total_skills"] == 1
    skill = data["skills"][0]
    assert skill["path"] == ".agents/skills/sync-tool"
    assert len(skill["duplicates"]) == 1
    assert skill["duplicates"][0]["identical"] is False

    # Check DSC-001 finding
    findings = skill["findings"]
    dsc_findings = [f for f in findings if f["rule_id"] == "DSC-001"]
    assert len(dsc_findings) == 1
    assert dsc_findings[0]["severity"] == "WARN"
    assert "sync-tool" in dsc_findings[0]["message"]
    assert ".claude/skills/sync-tool" in dsc_findings[0]["message"]


def test_case_a_tie_breaking_is_lexicographical(tmp_path: Path, cli_runner: CliRunner):
    """When update timestamps are identical, tie is broken by path lexicographically."""
    content = (
        "---\n"
        "name: tied-skill\n"
        "description: Skill added to both locations in the exact same commit.\n"
        "---\n"
        "# Tied\n"
    )
    repo = make_repo(
        tmp_path / "repo_a3",
        commits=[
            CommitDef(
                message="Add tied skill to two folders",
                files={
                    "b_folder/skills/tied/SKILL.md": content,
                    "a_folder/skills/tied/SKILL.md": content,
                },
                date="2026-09-01T10:00:00Z",
            ),
        ],
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["skills"][0]["path"] == "a_folder/skills/tied"


def test_case_b_test_data_isolation(tmp_path: Path, cli_runner: CliRunner):
    """Test-data skills are listed but do not trigger exit code 1 unless --include-test-data."""
    real_content = (
        "---\n"
        "name: real-workflow\n"
        "description: Production-grade workflow skill for agents.\n"
        "---\n"
        "# Real\n"
    )
    broken_test_content = (
        "---\n"
        "name: broken-fixture\n"
        "description: short\n"  # triggers SCH-005
        "---\n"
        "rm -rf /\n"  # triggers SEC-002
    )

    repo = make_repo(
        tmp_path / "repo_b",
        tree={
            ".claude/skills/real-workflow/SKILL.md": real_content,
            "src/test/resources/skills/broken/SKILL.md": broken_test_content,
        },
    )

    # 1. Default scan: test data is excluded from failing the exit code
    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 2
    assert data["summary"]["passed"] == 2
    assert data["summary"]["failed"] == 0

    # 2. Scan with --include-test-data: fails with exit code 1
    res_included = cli_runner.invoke(
        app, ["scan", str(repo), "--include-test-data", "--format", "json"]
    )
    assert res_included.exit_code == 1
    data_inc = json.loads(res_included.stdout)
    assert data_inc["summary"]["passed"] == 1
    assert data_inc["summary"]["failed"] == 1


def test_case_b_test_data_never_masks_real_skill(tmp_path: Path, cli_runner: CliRunner):
    """A test fixture named 'foo' must never merge with a real skill named 'foo'."""
    real_content = (
        "---\nname: common-name\ndescription: Real agent tool for operations.\n---\n# Real\n"
    )
    test_content = (
        "---\n"
        "name: common-name\n"
        "description: Test fixture mock for common name tool.\n"
        "---\n"
        "# Test\n"
    )

    repo = make_repo(
        tmp_path / "repo_b2",
        tree={
            ".claude/skills/tool/SKILL.md": real_content,
            "fixtures/skills/tool/SKILL.md": test_content,
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 2
    origins = {s["origin"] for s in data["skills"]}
    assert SkillOrigin.AGENT_CONFIG.value in origins
    assert SkillOrigin.TEST_DATA.value in origins


def test_case_c_product_skills_classified_and_reported(tmp_path: Path, cli_runner: CliRunner):
    """Skills inside product bundles are classified as product and validated."""
    prod_content = (
        "---\n"
        "name: product-extension\n"
        "description: Skill shipped as part of the IDE product plugin.\n"
        "---\n"
        "# Product\n"
    )
    repo = make_repo(
        tmp_path / "repo_c",
        tree={
            "plugins/my-plugin/resources/skills/ext/SKILL.md": prod_content,
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 1
    skill = data["skills"][0]
    assert skill["origin"] == SkillOrigin.PRODUCT.value
    assert data["summary"]["by_origin"]["product"] == 1


def test_copy_layout_mps(tmp_path: Path, cli_runner: CliRunner):
    """Test full scan on real-world MPS fixture layout (agent-config duplicates + product skill)."""
    from tests.conftest import copy_layout

    repo = copy_layout("mps", tmp_path / "mps_test_repo")
    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 2  # 1 git-helper (deduped) + 1 editor-ops
    names = {s["name"] for s in data["skills"]}
    assert names == {"git-helper", "editor-ops"}


def test_copy_layout_koog(tmp_path: Path, cli_runner: CliRunner):
    """Test full scan on real-world koog fixture layout (agent-config + test-data)."""
    from tests.conftest import copy_layout

    repo = copy_layout("koog", tmp_path / "koog_test_repo")
    # Without --include-test-data: exit code 0
    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 2
    assert data["summary"]["passed"] == 2

    # With --include-test-data: exit code 1
    res_inc = cli_runner.invoke(app, ["scan", str(repo), "--include-test-data", "--format", "json"])
    assert res_inc.exit_code == 1


def test_case_a_vulnerable_stale_copy_is_audited(tmp_path: Path, cli_runner: CliRunner):
    """C2: An older duplicate copy with security vulnerabilities must be audited and fail the scan."""
    old_dangerous = (
        "---\nname: my-tool\ndescription: Older copy with dangerous command.\n---\nrm -rf /\n"
    )
    new_clean = "---\nname: my-tool\ndescription: Newer clean copy without dangerous command.\n---\n# Safe\n"

    repo = make_repo(
        tmp_path / "repo_c2",
        commits=[
            CommitDef(
                message="Add dangerous older copy to .claude",
                files={".claude/skills/my-tool/SKILL.md": old_dangerous},
                date="2026-01-01T10:00:00Z",
            ),
            CommitDef(
                message="Add clean newer copy to .agents",
                files={".agents/skills/my-tool/SKILL.md": new_clean},
                date="2026-02-01T10:00:00Z",
            ),
        ],
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["summary"]["failed"] == 1
    skill = data["skills"][0]
    rule_ids = [f["rule_id"] for f in skill["findings"]]
    assert "SEC-002" in rule_ids


def test_case_c_distinct_product_skills_same_name_not_merged(tmp_path: Path, cli_runner: CliRunner):
    """C3: Two distinct product skills in different plugins sharing a name must NOT be merged."""
    clean_plugin = "---\nname: setup\ndescription: Setup tool for plugin A.\n---\n# Clean\n"
    vulnerable_plugin = (
        "---\nname: setup\ndescription: Setup tool for plugin B.\n---\nAKIAIOSFODNN7EXAMPLE\n"
    )

    repo = make_repo(
        tmp_path / "repo_c3",
        tree={
            "plugins/plugin-a/resources/skills/setup/SKILL.md": clean_plugin,
            "plugins/plugin-b/resources/skills/setup/SKILL.md": vulnerable_plugin,
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    # Both skills must be retained
    assert data["summary"]["total_skills"] == 2
    names = [s["name"] for s in data["skills"]]
    assert names == ["setup", "setup"]
    # Secret in plugin-b must be detected
    all_rule_ids = [f["rule_id"] for s in data["skills"] for f in s["findings"]]
    assert "SEC-001" in all_rule_ids


def test_case_a_timezone_aware_newest_selection(tmp_path: Path, cli_runner: CliRunner):
    """C4: Newest copy is selected by comparing timezone-aware UTC timestamps, not ISO strings."""
    # Copy A: 10:00:00+05:00 == 05:00:00 UTC (older)
    # Copy B: 08:00:00+00:00 == 08:00:00 UTC (newer)
    # Lexicographically, '2026-01-01T10:00:00+05:00' > '2026-01-01T08:00:00+00:00',
    # but Copy B is actually newer in real time!
    repo = make_repo(
        tmp_path / "repo_c4",
        commits=[
            CommitDef(
                message="Add Copy A",
                files={
                    ".claude/skills/tz-tool/SKILL.md": "---\nname: tz-tool\ndescription: Copy A\n---\n"
                },
                date="2026-01-01T10:00:00+05:00",
            ),
            CommitDef(
                message="Add Copy B",
                files={
                    ".agents/skills/tz-tool/SKILL.md": "---\nname: tz-tool\ndescription: Copy B\n---\n"
                },
                date="2026-01-01T08:00:00+00:00",
            ),
        ],
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    skill = data["skills"][0]
    # Copy B (.agents) must be chosen as newest
    assert skill["path"] == ".agents/skills/tz-tool"


def test_nested_skills_isolation_no_double_reporting(tmp_path: Path, cli_runner: CliRunner):
    """M4: Root skill does not collect child skills' companion files or double-report their findings."""
    root_skill = "---\nname: root-project\ndescription: Root skill for repository.\n---\n# Root\n"
    child_skill = "---\nname: child-skill\ndescription: Nested child skill.\n---\nrm -rf /\n"

    repo = make_repo(
        tmp_path / "repo_m4",
        tree={
            "SKILL.md": root_skill,
            ".claude/skills/child/SKILL.md": child_skill,
        },
    )

    res = cli_runner.invoke(app, ["scan", str(repo), "--format", "json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["summary"]["total_skills"] == 2
    root_s = next(s for s in data["skills"] if s["name"] == "root-project")
    child_s = next(s for s in data["skills"] if s["name"] == "child-skill")

    # Root skill must NOT contain SEC-002 from child skill
    root_rule_ids = [f["rule_id"] for f in root_s["findings"]]
    assert "SEC-002" not in root_rule_ids

    # Child skill has SEC-002
    child_rule_ids = [f["rule_id"] for f in child_s["findings"]]
    assert "SEC-002" in child_rule_ids
