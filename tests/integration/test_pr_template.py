"""Tests for Pull Request template existence, structure, and guidelines compliance."""

from pathlib import Path


def test_pr_template_exists_and_contains_required_sections() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    template_path = repo_root / ".github" / "pull_request_template.md"

    assert template_path.is_file(), ".github/pull_request_template.md must exist"
    content = template_path.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "PR template must not be empty"

    required_sections = [
        "### Summary",
        "### Changes",
        "### Demo / Visual Evidence",
        "### Verification",
        "### Checklist",
    ]
    for section in required_sections:
        assert section in content, f"Missing section '{section}' in PR template"

    # Mandatory video requirement checks
    assert "MANDATORY" in content, "PR template must highlight mandatory requirements"
    assert "video" in content.lower(), "PR template must mention video demos"
    assert "mp4" in content.lower(), "PR template should reference MP4 video format"


def test_documentation_references_pr_template() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent

    agents_md = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert ".github/pull_request_template.md" in agents_md
    assert "demo video" in agents_md.lower()

    workflows_md = (repo_root / "memory" / "workflows.md").read_text(encoding="utf-8")
    assert ".github/pull_request_template.md" in workflows_md
    assert "video" in workflows_md.lower()
