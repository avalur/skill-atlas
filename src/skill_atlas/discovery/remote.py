"""Remote Git repository discovery for AI Agent Skills."""

from pathlib import Path

import httpx

from skill_atlas.git.client import parse_github_url
from skill_atlas.git.github import GitHubClient
from skill_atlas.models import Skill
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


def _discover_via_github_api(owner: str, repo: str, original_url: str) -> list[Skill]:
    """Fast discovery using GitHub REST API and raw file downloads."""
    gh_client = GitHubClient()
    skills: list[Skill] = []

    with httpx.Client(timeout=20.0, follow_redirects=True) as http_client:
        default_branch = gh_client.get_default_branch(http_client, owner, repo)
        active_branch, all_paths = gh_client.fetch_all_paths(
            http_client, owner, repo, default_branch
        )

        manifest_paths = [
            p
            for p in all_paths
            if p.endswith("/SKILL.md") or p == "SKILL.md" or p.endswith("/skill.md")
        ]

        if not manifest_paths:
            return []

        repo_full_name = f"{owner}/{repo}"
        canonical_repo_url = f"https://github.com/{owner}/{repo}"

        for manifest_path in manifest_paths:
            if "/" in manifest_path:
                skill_dir = str(Path(manifest_path).parent)
                fallback_name = Path(skill_dir).name
            else:
                skill_dir = "."
                fallback_name = repo

            # Collect companion files in the skill directory
            if skill_dir == ".":
                available_files = list(all_paths)
            else:
                prefix = f"{skill_dir}/"
                available_files = [p[len(prefix) :] for p in all_paths if p.startswith(prefix)]

            raw_content = gh_client.fetch_file_content(
                http_client, owner, repo, active_branch, manifest_path
            )

            commit_sha, commit_date = gh_client.fetch_file_provenance(
                http_client, owner, repo, manifest_path
            )

            # Fetch companion text files (e.g. scripts/run.sh) for security checks
            companion_contents: dict[str, str] = {}
            if raw_content is not None:
                companion_contents["SKILL.md"] = raw_content

            for rel_f in available_files:
                if rel_f != "SKILL.md" and Path(rel_f).suffix.lower() in TEXT_EXTENSIONS:
                    full_repo_path = f"{skill_dir}/{rel_f}" if skill_dir != "." else rel_f
                    f_content = gh_client.fetch_file_content(
                        http_client, owner, repo, active_branch, full_repo_path
                    )
                    if f_content is not None:
                        companion_contents[rel_f] = f_content

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

            skill = Skill(
                name=parse_info["name"],
                description=parse_info["description"],
                repo_name=repo_full_name,
                repo_url=canonical_repo_url,
                commit=commit_sha,
                commit_date=commit_date,
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
            )
            skills.append(skill)

    return skills


def discover_remote_skills(url: str) -> list[Skill]:
    """Discover skills in a remote Git repository using GitHub REST API and raw downloads."""
    gh_match = parse_github_url(url)
    if not gh_match:
        raise ValueError(f"Only GitHub repositories are supported for remote scans: '{url}'")
    owner, repo = gh_match
    return _discover_via_github_api(owner, repo, url)
