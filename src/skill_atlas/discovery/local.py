"""Local filesystem discovery for AI Agent Skills."""

import os
import subprocess
from pathlib import Path

from skill_atlas.git.client import get_file_provenance, get_repo_info, is_git_repository
from skill_atlas.models import Skill
from skill_atlas.parsers.markdown import parse_skill_markdown

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".junie",
    ".idea",
    ".vscode",
}


def _collect_skill_files(skill_dir: Path) -> list[str]:
    """Collect all files inside skill directory relative to skill directory root."""
    files: list[str] = []
    for root, dirs, filenames in os.walk(skill_dir):
        # Prune ignored dirs
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in filenames:
            abs_f = Path(root) / f
            try:
                rel_path = abs_f.relative_to(skill_dir)
                files.append(str(rel_path))
            except ValueError:
                pass
    return files


def _collect_git_repo_files(repo_root: Path) -> list[str]:
    """Collect tracked and untracked repository files relative to repo root."""
    try:
        res = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def discover_local_skills(target_path: Path) -> list[Skill]:
    """Discover all skills in the given local directory or file path."""
    skills: list[Skill] = []
    target = target_path.resolve()

    if not target.exists():
        return []

    # Check git repo context
    in_git = is_git_repository(target)
    repo_root, repo_name, repo_url = get_repo_info(target) if in_git else (None, None, None)
    repo_files = _collect_git_repo_files(repo_root) if repo_root else []

    manifest_paths: list[Path] = []

    if target.is_file():
        if target.name.lower() == "skill.md":
            manifest_paths.append(target)
    else:
        # Check if target directory itself directly contains SKILL.md
        direct_manifest = target / "SKILL.md"
        if direct_manifest.is_file():
            manifest_paths.append(direct_manifest)

        # Recursively search for subdirectories containing SKILL.md
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for file in files:
                if file.lower() == "skill.md":
                    p = Path(root) / file
                    if p not in manifest_paths:
                        manifest_paths.append(p)

    # Process each discovered manifest
    for manifest in manifest_paths:
        skill_dir = manifest.parent
        fallback_name = skill_dir.name

        try:
            raw_content = manifest.read_text(encoding="utf-8")
        except Exception as err:
            raw_content = None
            parse_info = {
                "name": fallback_name,
                "description": "",
                "version": None,
                "author": None,
                "tags": [],
                "frontmatter": {},
                "markdown_body": "",
                "referenced_files": [],
                "parse_error": f"Failed to read SKILL.md: {err}",
            }

        if raw_content is not None:
            parse_info = parse_skill_markdown(raw_content, fallback_name=fallback_name)

        # Compute skill path relative to repo or scan target
        if repo_root:
            try:
                rel_skill_path = str(skill_dir.relative_to(repo_root))
                manifest_rel_path = str(manifest.relative_to(repo_root))
            except ValueError:
                rel_skill_path = str(skill_dir)
                manifest_rel_path = str(manifest)
        else:
            try:
                rel_skill_path = str(
                    skill_dir.relative_to(target.parent if target.is_file() else target)
                )
            except ValueError:
                rel_skill_path = str(skill_dir)
            manifest_rel_path = rel_skill_path

        # Resolve Git provenance
        commit_sha: str | None = None
        commit_date: str | None = None
        if repo_root:
            commit_sha, commit_date = get_file_provenance(repo_root, manifest_rel_path)

        available_files = _collect_skill_files(skill_dir)

        skill = Skill(
            name=parse_info["name"],
            description=parse_info["description"],
            repo_name=repo_name,
            repo_url=repo_url,
            commit=commit_sha,
            commit_date=commit_date,
            path=rel_skill_path,
            version=parse_info.get("version"),
            author=parse_info.get("author"),
            tags=parse_info.get("tags", []),
            raw_content=raw_content,
            frontmatter=parse_info.get("frontmatter", {}),
            markdown_body=parse_info.get("markdown_body", ""),
            referenced_files=parse_info.get("referenced_files", []),
            available_files=available_files,
            repo_files=repo_files,
            base_dir=str(skill_dir),
            repo_root_dir=str(repo_root) if repo_root else None,
            parse_error=parse_info.get("parse_error"),
        )

        skills.append(skill)

    return skills
