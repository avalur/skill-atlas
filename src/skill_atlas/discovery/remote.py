"""Remote Git repository discovery for AI Agent Skills."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from skill_atlas.discovery.local import discover_local_skills
from skill_atlas.git.client import parse_github_url
from skill_atlas.git.github import GitHubClient
from skill_atlas.models import Skill
from skill_atlas.parsers.markdown import parse_skill_markdown


def is_remote_target(target: str) -> bool:
    """Check if target string represents a remote Git URL."""
    cleaned = target.strip()
    return cleaned.startswith(("http://", "https://", "git@", "ssh://")) or cleaned.endswith(".git")


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
                repo_files=all_paths,
                parse_error=parse_info.get("parse_error"),
            )
            skills.append(skill)

    return skills


def _discover_via_git_clone(url: str) -> list[Skill]:
    """Lightweight discovery using blobless shallow clone with no checkout."""
    tmp_dir = tempfile.mkdtemp(prefix="skill_atlas_clone_")
    try:
        # 1. Shallow blobless clone without checking out files (downloads only ~5MB for Kotlin)
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--no-checkout",
            url,
            tmp_dir,
        ]
        clone_res = subprocess.run(
            clone_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if clone_res.returncode != 0:
            # Fallback if blob filter is not supported by Git server
            subprocess.run(
                ["git", "clone", "--depth", "1", "--no-checkout", url, tmp_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        # 2. Inspect tree directly without checking out files
        tree_res = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"],
            cwd=tmp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        all_tree_files = [line.strip() for line in tree_res.stdout.splitlines() if line.strip()]
        manifest_paths = [
            p
            for p in all_tree_files
            if p.endswith("/SKILL.md") or p == "SKILL.md" or p.endswith("/skill.md")
        ]

        if not manifest_paths:
            return []

        # 3. Checkout ONLY the detected skill directories
        skill_dirs = list(
            {str(Path(p).parent) for p in manifest_paths if "/" in p}
            | {p for p in manifest_paths if "/" not in p}
        )
        subprocess.run(
            ["git", "checkout", "HEAD", "--"] + skill_dirs,
            cwd=tmp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        # 4. Discover skills locally from the checked out directories
        skills = discover_local_skills(Path(tmp_dir))

        # 5. Normalize repo metadata
        gh_match = parse_github_url(url)
        orig_repo_name = f"{gh_match[0]}/{gh_match[1]}" if gh_match else Path(url.rstrip("/")).stem
        canonical_url = f"https://github.com/{gh_match[0]}/{gh_match[1]}" if gh_match else url

        # Attempt to enrich introductory commit provenance via GitHub API if available
        if gh_match:
            gh_client = GitHubClient()
            with httpx.Client(timeout=10.0) as http_client:
                for skill in skills:
                    skill.repo_name = orig_repo_name
                    skill.repo_url = canonical_url
                    skill.repo_files = all_tree_files
                    manifest_rel = f"{skill.path}/SKILL.md" if skill.path != "." else "SKILL.md"
                    try:
                        api_sha, api_date = gh_client.fetch_file_provenance(
                            http_client, gh_match[0], gh_match[1], manifest_rel
                        )
                        if api_sha:
                            skill.commit = api_sha
                            skill.commit_date = api_date
                    except Exception:
                        pass
        else:
            for skill in skills:
                skill.repo_name = orig_repo_name
                skill.repo_url = canonical_url
                skill.repo_files = all_tree_files

        return skills
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def discover_remote_skills(url: str) -> list[Skill]:
    """Discover skills in a remote Git repository using hybrid API + lightweight clone."""
    gh_match = parse_github_url(url)
    if gh_match:
        owner, repo = gh_match
        try:
            skills = _discover_via_github_api(owner, repo, url)
            if skills:
                return skills
        except Exception:
            pass

    return _discover_via_git_clone(url)
