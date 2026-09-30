"""Unit tests for heuristic similarity calculations."""

import pytest

from skill_atlas.models import Skill
from skill_atlas.similarity import (
    calculate_body_similarity,
    calculate_description_similarity,
    calculate_files_similarity,
    calculate_name_similarity,
    calculate_tags_similarity,
    compare_skills,
    cosine_token_similarity,
    find_similar_skills,
    jaccard_similarity,
    string_ratio,
    tokenize_name,
    tokenize_text,
)


def test_tokenize_name():
    assert tokenize_name("docker-runner") == ["docker", "runner"]
    assert tokenize_name("gitCommitHelper") == ["git", "commit", "helper"]
    assert tokenize_name("run_docker_exec") == ["run", "docker", "exec"]
    assert tokenize_name("a-b-c") == []  # Single-character tokens filtered


def test_tokenize_text():
    text = "A simple tool that helps with git commit actions and automation"
    tokens = tokenize_text(text)
    assert "simple" in tokens
    assert "git" in tokens
    assert "commit" in tokens
    assert "automation" in tokens
    assert "that" not in tokens
    assert "helps" not in tokens
    assert "with" not in tokens


def test_jaccard_similarity():
    s1 = {"git", "automation", "ci"}
    s2 = {"git", "automation", "cd"}
    assert jaccard_similarity(s1, s2) == pytest.approx(2 / 4)
    assert jaccard_similarity(set(), set()) == 0.0


def test_cosine_token_similarity():
    t1 = ["git", "commit", "push"]
    t2 = ["git", "commit", "push"]
    assert cosine_token_similarity(t1, t2) == pytest.approx(1.0)

    t3 = ["docker", "container", "run"]
    assert cosine_token_similarity(t1, t3) == 0.0
    assert cosine_token_similarity([], []) == 0.0


def test_string_ratio():
    assert string_ratio("docker-run", "docker-run") == 1.0
    assert string_ratio("docker-run", "docker-runner") > 0.8
    assert string_ratio("", "abc") == 0.0


def test_calculate_name_similarity():
    score, reasons = calculate_name_similarity("docker-run", "docker-runner")
    assert score >= 0.7
    assert len(reasons) > 0

    score_identical, reasons_id = calculate_name_similarity("deploy-app", "deploy-app")
    assert score_identical == 1.0
    assert "Identical skill name" in reasons_id[0]

    score_diff, _ = calculate_name_similarity("kubernetes-deploy", "image-resizer")
    assert score_diff < 0.3


def test_calculate_description_similarity():
    d1 = "Run and manage Docker containers with ease."
    d2 = "Manage Docker containers and images in local development."
    score, reasons = calculate_description_similarity(d1, d2)
    assert score >= 0.5
    assert len(reasons) > 0

    score_id, reasons_id = calculate_description_similarity(d1, d1)
    assert score_id == 1.0
    assert "Identical description text" in reasons_id[0]

    score_empty, _ = calculate_description_similarity("", "some desc")
    assert score_empty == 0.0


def test_calculate_tags_similarity():
    t1 = ["docker", "devops", "containers"]
    t2 = ["docker", "containers", "cloud"]
    score, reasons = calculate_tags_similarity(t1, t2)
    assert score == pytest.approx(2 / 4)
    assert "Shared tags: containers, docker" in reasons[0]

    score_none, _ = calculate_tags_similarity([], ["git"])
    assert score_none is None


def test_calculate_body_similarity():
    b1 = "## Instructions\nExecute the docker run command to start container."
    b2 = "## Instructions\nExecute docker command to inspect container."
    score, _reasons = calculate_body_similarity(b1, b2)
    assert score is not None
    assert score >= 0.5

    score_none, _ = calculate_body_similarity("", "content")
    assert score_none is None


def test_calculate_files_similarity():
    f1 = ["scripts/run.sh", "reference/schema.json"]
    f2 = ["scripts/run.sh", "reference/guide.md"]
    score, reasons = calculate_files_similarity(f1, f2)
    assert score == pytest.approx(1 / 3)
    assert "Matching file names: run.sh" in reasons[0]

    score_none, _ = calculate_files_similarity([], ["scripts/a.sh"])
    assert score_none is None


def test_compare_skills_and_weights():
    s1 = Skill(
        name="docker-runner",
        description="Run Docker containers and execute tasks",
        tags=["docker", "containers"],
        path="skills/docker-runner",
        referenced_files=["scripts/run.sh"],
    )
    s2 = Skill(
        name="docker-run",
        description="Execute commands inside Docker containers",
        tags=["docker", "containers"],
        path="skills/docker-run",
        referenced_files=["scripts/run.sh"],
    )
    match = compare_skills(s1, s2)
    assert match.score >= 0.7
    assert match.skill_a == "docker-runner"
    assert match.skill_b == "docker-run"
    assert match.breakdown.name >= 0.5
    assert match.breakdown.tags == 1.0
    assert len(match.reasons) > 0


def test_find_similar_skills_pairwise_and_query():
    skills = [
        Skill(
            name="git-commit",
            description="Create git commits and format commit messages",
            tags=["git", "vcs"],
            path="skills/git-commit",
        ),
        Skill(
            name="git-committer",
            description="Automate git commits and stage changed files",
            tags=["git", "vcs"],
            path="skills/git-committer",
        ),
        Skill(
            name="image-optimizer",
            description="Compress PNG and JPEG images to reduce file size",
            tags=["image", "media"],
            path="skills/image-optimizer",
        ),
    ]

    # Pairwise find
    result = find_similar_skills(skills, threshold=0.5, target="skills")
    assert result.total_skills == 3
    assert len(result.matches) == 1
    m = result.matches[0]
    assert {m.skill_a, m.skill_b} == {"git-commit", "git-committer"}
    assert m.score >= 0.6

    # Query specific skill
    query_res = find_similar_skills(skills, query_skill="git-commit", threshold=0.5)
    assert len(query_res.matches) == 1
    assert query_res.matches[0].skill_b == "git-committer"

    # Query nonexistent skill
    empty_res = find_similar_skills(skills, query_skill="nonexistent")
    assert len(empty_res.matches) == 0

    # High threshold filters out
    high_res = find_similar_skills(skills, threshold=0.99)
    assert len(high_res.matches) == 0
