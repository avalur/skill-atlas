"""Local filesystem discovery for AI Agent Skills."""

import datetime
import hashlib
import os
import subprocess
from pathlib import Path

from skill_atlas.git.client import (
    get_directory_last_commit,
    get_file_provenance,
    get_repo_info,
    is_git_repository,
)
from skill_atlas.models import Skill, classify_origin
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


def _collect_skill_files(skill_dir: Path) -> tuple[list[str], dict[str, str]]:
    """Collect companion file paths and text contents inside skill directory."""
    files: list[str] = []
    contents: dict[str, str] = {}
    resolved_skill_dir = skill_dir.resolve()

    for root, dirs, filenames in os.walk(skill_dir):
        # Prune ignored dirs
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in filenames:
            abs_f = Path(root) / f
            # Check symlink destination
            if abs_f.is_symlink():
                try:
                    resolved_target = abs_f.resolve()
                    if not resolved_target.is_relative_to(resolved_skill_dir):
                        continue
                except (OSError, RuntimeError, ValueError):
                    continue

            try:
                rel_path = str(abs_f.relative_to(skill_dir))
                files.append(rel_path)
            except ValueError:
                continue

            # Read text files if under 1MB and non-binary
            try:
                st = abs_f.stat()
                if st.st_size <= 1_048_576:  # 1 MB
                    with open(abs_f, "rb") as bf:
                        chunk = bf.read(8192)
                        if b"\x00" not in chunk:
                            bf.seek(0)
                            contents[rel_path] = bf.read().decode("utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                pass

    return files, contents


def _collect_git_repo_files(repo_root: Path) -> list[str]:
    """Collect tracked and untracked repository files relative to repo root."""
    try:
        res = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            env={"GIT_TERMINAL_PROMPT": "0", **os.environ},
            check=False,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError):
        pass
    return []


def _calculate_content_hash(companion_contents: dict[str, str]) -> str:
    """Calculate a deterministic sha256 hash of all text contents in the skill."""
    hasher = hashlib.sha256()
    for rel_p in sorted(companion_contents.keys()):
        hasher.update(rel_p.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(companion_contents[rel_p].encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


def discover_local_skills(target_path: Path) -> list[Skill]:
    """Discover all skills in the given local directory or file path."""
    skills: list[Skill] = []
    target = target_path.resolve()

    if not target.exists():
        raise FileNotFoundError(f"Target path does not exist: {target_path}")

    # Check git repo context
    in_git = is_git_repository(target)
    repo_root, repo_name, repo_url = get_repo_info(target) if in_git else (None, None, None)
    repo_files = _collect_git_repo_files(repo_root) if repo_root else []

    manifest_paths: list[Path] = []
    seen_manifests: set[Path] = set()
    seen_skill_dirs: set[Path] = set()

    if target.is_file():
        if target.name.lower() == "skill.md":
            manifest_paths.append(target)
    else:
        # Recursively search for subdirectories containing SKILL.md
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for file in files:
                if file.lower() == "skill.md":
                    p = (Path(root) / file).resolve()
                    if p not in seen_manifests:
                        seen_manifests.add(p)
                        manifest_paths.append(p)

    # Process each discovered manifest
    for manifest in manifest_paths:
        skill_dir = manifest.parent
        resolved_skill_dir = skill_dir.resolve()
        if resolved_skill_dir in seen_skill_dirs:
            continue
        seen_skill_dirs.add(resolved_skill_dir)

        fallback_name = skill_dir.name

        try:
            raw_content = manifest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
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
        updated_sha: str | None = None
        updated_date: str | None = None
        updated_source = "git"

        if repo_root:
            commit_sha, commit_date = get_file_provenance(repo_root, manifest_rel_path)
            updated_sha, updated_date = get_directory_last_commit(repo_root, rel_skill_path)

        available_files, companion_contents = _collect_skill_files(skill_dir)
        if raw_content is not None:
            companion_contents["SKILL.md"] = raw_content

        if not updated_date:
            # Fallback to file mtime
            latest_mtime = 0.0
            for rel_f in available_files:
                try:
                    st = (skill_dir / rel_f).stat()
                    if st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                except OSError:
                    pass
            if latest_mtime > 0:
                dt = datetime.datetime.fromtimestamp(latest_mtime, tz=datetime.UTC)
                updated_date = dt.isoformat()
                updated_source = "mtime"
            elif commit_date:
                updated_date = commit_date
                updated_sha = commit_sha

        origin = classify_origin(rel_skill_path)
        content_hash = _calculate_content_hash(companion_contents)

        skill = Skill(
            name=parse_info["name"],
            description=parse_info["description"],
            repo_name=repo_name,
            repo_url=repo_url,
            commit=commit_sha,
            commit_date=commit_date,
            updated_commit=updated_sha,
            updated_date=updated_date,
            updated_source=updated_source,
            origin=origin,
            path=rel_skill_path,
            version=parse_info.get("version"),
            author=parse_info.get("author"),
            tags=parse_info.get("tags", []),
            raw_content=raw_content,
            frontmatter=parse_info.get("frontmatter", {}),
            markdown_body=parse_info.get("markdown_body", ""),
            referenced_files=parse_info.get("referenced_files", []),
            available_files=available_files,
            companion_contents=companion_contents,
            repo_files=repo_files,
            base_dir=str(skill_dir),
            repo_root_dir=str(repo_root) if repo_root else None,
            parse_error=parse_info.get("parse_error"),
            content_hash=content_hash,
        )

        skills.append(skill)

    return skills
