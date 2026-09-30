"""Remote Git repository discovery for AI Agent Skills."""

import hashlib
import threading
import time
from pathlib import Path

import httpx

from skill_atlas.git.client import parse_github_url
from skill_atlas.git.github import GitHubClient
from skill_atlas.models import (
    ProgressCallback,
    ProgressEvent,
    Skill,
    Stage,
    classify_origin,
)
from skill_atlas.parsers.markdown import parse_skill_markdown

TEXT_EXTENSIONS = {
    ".sh",
    ".bash",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
    ".env",
    ".cfg",
    ".ini",
    ".toml",
}


def _calculate_content_hash(companion_contents: dict[str, str]) -> str:
    """Calculate a deterministic sha256 hash of all text contents in the skill."""
    hasher = hashlib.sha256()
    for rel_p in sorted(companion_contents.keys()):
        hasher.update(rel_p.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(companion_contents[rel_p].encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


def is_remote_target(target: str) -> bool:
    """Check if target string represents a remote Git URL."""
    cleaned = target.strip()
    if cleaned.startswith("-"):
        return False
    if cleaned.startswith(("http://", "https://", "git@", "ssh://")):
        return True
    if cleaned.endswith(".git"):
        if "://" in cleaned or "@" in cleaned or not Path(cleaned).exists():
            return True
    return False


def _discover_via_github_api(
    owner: str,
    repo: str,
    original_url: str,
    ref: str | None = None,
    gh_client: GitHubClient | None = None,
    http_client: httpx.Client | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    start_time: float | None = None,
) -> list[Skill]:
    """Fast discovery using GitHub REST API and raw file downloads."""
    gh = gh_client or GitHubClient()
    skills: list[Skill] = []
    t0 = start_time or time.time()

    def emit(
        stage: Stage,
        message: str,
        current: int | None = None,
        total: int | None = None,
        skill_path: str | None = None,
    ) -> None:
        if on_progress:
            event = ProgressEvent(
                stage=stage,
                message=message,
                current=current,
                total=total,
                skill_path=skill_path,
                rate_limit_remaining=gh.rate_limit_remaining,
                elapsed_ms=int((time.time() - t0) * 1000),
            )
            on_progress(event)

    def check_cancel() -> None:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Scan cancelled by user")

    check_cancel()
    emit(Stage.VALIDATE, f"Validating repository {owner}/{repo}...")

    close_client = False
    client = http_client
    if client is None:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
        close_client = True

    try:
        check_cancel()
        target_ref = ref
        if not target_ref:
            target_ref = gh.get_default_branch(client, owner, repo)

        emit(Stage.FETCH, f"Fetching tree for {owner}/{repo} (ref: {target_ref})...")
        check_cancel()

        active_branch, tree_items, _is_truncated = gh.fetch_all_paths(
            client, owner, repo, target_ref
        )

        all_paths = [item["path"] for item in tree_items if item.get("type") == "blob"]
        path_to_size = {
            item["path"]: item.get("size", 0) for item in tree_items if item.get("type") == "blob"
        }

        # Case-insensitive dedup for manifests
        seen_dirs: set[str] = set()
        manifest_paths: list[str] = []
        for p in all_paths:
            p_lower = p.lower()
            if p_lower.endswith("/skill.md") or p_lower == "skill.md":
                d = str(Path(p).parent) if "/" in p else "."
                d_lower = d.lower()
                if d_lower not in seen_dirs:
                    seen_dirs.add(d_lower)
                    manifest_paths.append(p)

        emit(Stage.DISCOVER, f"Found {len(manifest_paths)} SKILL.md file(s)")
        if not manifest_paths:
            return []

        repo_full_name = f"{owner}/{repo}"
        canonical_repo_url = f"https://github.com/{owner}/{repo}"

        for idx, manifest_path in enumerate(manifest_paths, start=1):
            check_cancel()
            if "/" in manifest_path:
                skill_dir = str(Path(manifest_path).parent)
                fallback_name = Path(skill_dir).name
            else:
                skill_dir = "."
                fallback_name = repo

            emit(
                Stage.DOWNLOAD,
                f"Downloading skill files for {skill_dir} ({idx}/{len(manifest_paths)})",
                current=idx,
                total=len(manifest_paths),
                skill_path=skill_dir,
            )

            # Collect companion files in the skill directory
            if skill_dir == ".":
                available_files = list(all_paths)
            else:
                prefix = f"{skill_dir}/"
                available_files = [p[len(prefix) :] for p in all_paths if p.startswith(prefix)]

            raw_content = gh.fetch_file_content(client, owner, repo, active_branch, manifest_path)

            # Fetch companion text files (e.g. scripts/run.sh) for security checks
            companion_contents: dict[str, str] = {}
            if raw_content is not None:
                companion_contents["SKILL.md"] = raw_content

            for rel_f in available_files:
                check_cancel()
                if rel_f != "SKILL.md" and Path(rel_f).suffix.lower() in TEXT_EXTENSIONS:
                    full_repo_path = f"{skill_dir}/{rel_f}" if skill_dir != "." else rel_f
                    file_size = path_to_size.get(full_repo_path, 0)
                    if file_size <= 1_048_576:  # 1 MB
                        f_content = gh.fetch_file_content(
                            client, owner, repo, active_branch, full_repo_path
                        )
                        if f_content is not None:
                            companion_contents[rel_f] = f_content

            check_cancel()
            emit(
                Stage.PROVENANCE,
                f"Reading commit history for {skill_dir} ({idx}/{len(manifest_paths)})",
                current=idx,
                total=len(manifest_paths),
                skill_path=skill_dir,
            )

            provenance_path = skill_dir if skill_dir != "." else manifest_path
            intro_sha, intro_date, updated_sha, updated_date = gh.fetch_provenance_and_updated(
                client, owner, repo, provenance_path, ref=active_branch
            )

            if raw_content is not None:
                parse_info = parse_skill_markdown(raw_content, fallback_name=fallback_name)
            else:
                parse_info = {
                    "name": fallback_name,
                    "description": "",
                    "version": None,
                    "author": None,
                    "tags": [],
                    "frontmatter": {},
                    "markdown_body": "",
                    "referenced_files": [],
                    "parse_error": "Failed to fetch remote SKILL.md content",
                }

            origin = classify_origin(skill_dir)
            content_hash = _calculate_content_hash(companion_contents)

            skill = Skill(
                name=parse_info["name"],
                description=parse_info["description"],
                repo_name=repo_full_name,
                repo_url=canonical_repo_url,
                commit=intro_sha,
                commit_date=intro_date,
                updated_commit=updated_sha,
                updated_date=updated_date,
                updated_source="git",
                origin=origin,
                path=skill_dir,
                version=parse_info.get("version"),
                author=parse_info.get("author"),
                tags=parse_info.get("tags", []),
                raw_content=raw_content,
                frontmatter=parse_info.get("frontmatter", {}),
                markdown_body=parse_info.get("markdown_body", ""),
                referenced_files=parse_info.get("referenced_files", []),
                available_files=available_files,
                companion_contents=companion_contents,
                repo_files=all_paths,
                parse_error=parse_info.get("parse_error"),
                content_hash=content_hash,
            )
            skills.append(skill)

    finally:
        if close_client:
            client.close()

    return skills


def discover_remote_skills(
    url: str,
    ref: str | None = None,
    gh_client: GitHubClient | None = None,
    http_client: httpx.Client | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Skill]:
    """Discover skills in a remote Git repository using GitHub REST API and raw downloads."""
    gh_match = parse_github_url(url)
    if not gh_match:
        raise ValueError(f"Only GitHub repositories are supported for remote scans: '{url}'")
    owner, repo = gh_match
    return _discover_via_github_api(
        owner=owner,
        repo=repo,
        original_url=url,
        ref=ref,
        gh_client=gh_client,
        http_client=http_client,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )
