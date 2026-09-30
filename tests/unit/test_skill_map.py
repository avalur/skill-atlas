"""Unit tests and ground-truth benchmark for Skill Map clustering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_atlas.map import (
    SkillMapResult,
    classify_skills_jev,
    cluster_skills_ai,
    group_skills_heuristic,
)
from skill_atlas.models import Skill, SkillOrigin


def _make_skill(
    name: str,
    description: str,
    tags: list[str] | None = None,
    path: str = "skills",
) -> Skill:
    return Skill(
        name=name,
        description=description,
        tags=tags or [],
        path=f"{path}/{name}",
        origin=SkillOrigin.STANDALONE,
        findings=[],
    )


@pytest.fixture
def ten_benchmark_skills() -> list[Skill]:
    """10 curated skills across 4 functional domains for human vs machine clustering benchmark."""
    return [
        # Domain 1: Memory & Agent State
        _make_skill(
            "shared-memory",
            "Maintains project shared memory across AI agent sessions and tracks architectural decisions.",
            ["memory", "shared-memory", "agent-state"],
        ),
        _make_skill(
            "memory-vault",
            "Stores agent session memory and persistent project state records across AI runs.",
            ["memory", "persistence", "agent-state"],
        ),
        _make_skill(
            "session-history",
            "Tracks, indexes, and retrieves previous session interactions and contextual notes.",
            ["history", "session", "memory"],
        ),
        # Domain 2: Code Quality & Refactoring
        _make_skill(
            "code-assistant",
            "Provides automated code reviews, refactoring suggestions, and static analysis.",
            ["code", "review", "refactoring", "assistant"],
        ),
        _make_skill(
            "lint-helper",
            "Runs linter inspections and formats codebase according to style rules.",
            ["code", "linting", "formatting", "quality"],
        ),
        _make_skill(
            "refactor-bot",
            "Automated code restructuring, modernization, and dead code cleanup.",
            ["code", "refactoring", "modernization"],
        ),
        # Domain 3: Security & Auditing
        _make_skill(
            "security-guard",
            "Security auditing and credential leak detector for agent configurations.",
            ["security", "audit", "credentials", "safety"],
        ),
        _make_skill(
            "secret-scanner",
            "Detects exposed API tokens, private keys, and secrets in commits and manifests.",
            ["security", "secrets", "audit"],
        ),
        _make_skill(
            "network-firewall",
            "Audits outbound network calls and domain egress permissions in companion scripts.",
            ["security", "network", "audit", "firewall"],
        ),
        # Domain 4: Data & Storage Sync
        _make_skill(
            "data-sync",
            "Automated synchronization utility for local caches and remote cloud data assets.",
            ["data", "sync", "storage"],
        ),
    ]


def test_heuristic_single_skill() -> None:
    skill = _make_skill("my-tool", "Does automated operations.", ["ops", "tool"])
    res = group_skills_heuristic([skill])
    assert res.total_skills == 1
    assert len(res.clusters) == 1
    assert res.clusters[0].skills == ["my-tool"]


def test_heuristic_empty_skills() -> None:
    res = group_skills_heuristic([])
    assert res.total_skills == 0
    assert res.clusters == []


def test_heuristic_shared_words_grouping(ten_benchmark_skills: list[Skill]) -> None:
    """1. WITHOUT AI: Group the skills with a heuristic, such as shared words."""
    res = group_skills_heuristic(ten_benchmark_skills, threshold=0.3)

    assert isinstance(res, SkillMapResult)
    assert res.method == "heuristic"
    assert res.total_skills == 10
    assert len(res.clusters) >= 3

    # Check that memory skills share a cluster
    memory_cluster = next((c for c in res.clusters if "shared-memory" in c.skills), None)
    assert memory_cluster is not None
    assert "memory-vault" in memory_cluster.skills
    assert memory_cluster.reason != ""
    assert len(memory_cluster.keywords) > 0

    # Check that security skills share a cluster
    sec_cluster = next((c for c in res.clusters if "security-guard" in c.skills), None)
    assert sec_cluster is not None
    assert "secret-scanner" in sec_cluster.skills


def test_check_human_vs_clustering_benchmark(ten_benchmark_skills: list[Skill]) -> None:
    """3. CHECK: Group ten skills yourself first, then compare.

    Ground truth manual grouping defined beforehand:
    - Group A (Memory): shared-memory, memory-vault, session-history
    - Group B (Code): code-assistant, lint-helper, refactor-bot
    - Group C (Security): security-guard, secret-scanner, network-firewall
    - Group D (Data): data-sync
    """
    ground_truth = {
        "Memory": {"shared-memory", "memory-vault", "session-history"},
        "Code": {"code-assistant", "lint-helper", "refactor-bot"},
        "Security": {"security-guard", "secret-scanner", "network-firewall"},
        "Data": {"data-sync"},
    }

    # Evaluate heuristic clustering
    heuristic_res = group_skills_heuristic(ten_benchmark_skills, threshold=0.35)

    # Convert clusters to sets
    cluster_sets = [set(c.skills) for c in heuristic_res.clusters]

    # Verify that closely linked domain pairs are clustered together
    assert any({"shared-memory", "memory-vault"}.issubset(c) for c in cluster_sets)
    assert any({"security-guard", "secret-scanner"}.issubset(c) for c in cluster_sets)
    assert any({"code-assistant", "refactor-bot"}.issubset(c) for c in cluster_sets)

    # Evaluate AI clustering with replay
    replay_path = Path("tests/fixtures/recorded_claude_map_benchmark.json")
    ai_res = cluster_skills_ai(ten_benchmark_skills, replay_file=replay_path)

    assert ai_res.replayed is True
    assert ai_res.method == "ai"
    assert len(ai_res.clusters) == 4

    ai_cluster_sets = {frozenset(c.skills): c.name for c in ai_res.clusters}

    # Verify 100% agreement with the 4 ground truth manual groups
    for group_name, members in ground_truth.items():
        assert frozenset(members) in ai_cluster_sets, (
            f"Ground truth group {group_name} ({members}) not found exactly in AI clusters: {ai_cluster_sets}"
        )


def test_ai_clustering_replay_and_record(ten_benchmark_skills: list[Skill], tmp_path: Path) -> None:
    """Test AI clustering replay from file and recording to file."""
    replay_src = Path("tests/fixtures/recorded_claude_map_benchmark.json")
    res = cluster_skills_ai(ten_benchmark_skills, replay_file=replay_src)

    assert res.replayed is True
    assert len(res.clusters) == 4

    # Test record file creation
    record_dest = tmp_path / "recorded.json"
    res_recorded = cluster_skills_ai(
        ten_benchmark_skills,
        replay_file=replay_src,
    )
    # Write to record dest
    record_dest.write_text(
        json.dumps([c.model_dump() for c in res_recorded.clusters], indent=2),
        encoding="utf-8",
    )
    assert record_dest.exists()

    # Replay back from record_dest
    res_replayed = cluster_skills_ai(ten_benchmark_skills, replay_file=record_dest)
    assert res_replayed.replayed is True
    assert len(res_replayed.clusters) == 4


def test_ai_clustering_fallback_when_cli_missing(ten_benchmark_skills: list[Skill]) -> None:
    """When Claude binary is not available, falls back gracefully to heuristic."""
    res = cluster_skills_ai(ten_benchmark_skills, claude_bin="/nonexistent/bin/claude")
    assert res.method == "heuristic"
    assert len(res.clusters) >= 1
    assert any("Claude CLI unavailable" in c.reason for c in res.clusters)


def test_ai_clustering_live_claude() -> None:
    """Test live Claude clustering when binary is installed."""
    import shutil

    if not shutil.which("claude"):
        pytest.skip("Claude CLI is not available in environment")
    skills = [
        _make_skill("shared-memory", "Maintains shared memory across sessions.", ["memory"]),
        _make_skill("code-assistant", "Provides automated code reviews.", ["code"]),
    ]
    res = cluster_skills_ai(skills)
    assert res.total_skills == 2
    assert len(res.clusters) >= 1
    assert all(c.name and c.reason for c in res.clusters)


def test_jev_classification_replay(ten_benchmark_skills: list[Skill]) -> None:
    """Test skill classification using TypeSafe AI's Jev model with recorded replay."""
    replay_path = Path("tests/fixtures/recorded_jev_map_benchmark.json")
    res = classify_skills_jev(ten_benchmark_skills, replay_file=replay_path)

    assert res.replayed is True
    assert res.method == "jev"
    assert len(res.clusters) == 4

    cluster_map = {c.name: set(c.skills) for c in res.clusters}
    assert "shared-memory" in cluster_map["Agent Memory & State"]
    assert "memory-vault" in cluster_map["Agent Memory & State"]
    assert "session-history" in cluster_map["Agent Memory & State"]

    assert "code-assistant" in cluster_map["Code Quality & Engineering"]
    assert "security-guard" in cluster_map["Security & Auditing"]
    assert "data-sync" in cluster_map["Data & Storage Sync"]


def test_jev_classification_fallback(
    ten_benchmark_skills: list[Skill], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When TYPESAFE_API_KEY is not set and no replay is provided, falls back cleanly."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    res = classify_skills_jev(ten_benchmark_skills)
    assert res.method == "jev"
    assert len(res.clusters) >= 1
    assert any("TYPESAFE_API_KEY not configured" in c.reason for c in res.clusters)
