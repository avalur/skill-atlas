"""Shared fixtures, test helpers, and MockTransport for Skill Atlas tests."""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class CommitDef:
    message: str
    files: dict[str, str] = field(default_factory=dict)
    deleted_files: list[str] = field(default_factory=list)
    date: str = "2026-09-01T12:00:00Z"
    author: str = "Developer <dev@example.com>"


def make_repo(
    repo_dir: Path,
    tree: dict[str, str] | None = None,
    commits: list[CommitDef] | None = None,
) -> Path:
    """Create a local Git repository with deterministic commit history."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "committer@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    git_env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
    }

    if commits:
        for c in commits:
            for rel_path, content in c.files.items():
                dest = repo_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
                subprocess.run(
                    ["git", "add", rel_path], cwd=repo_dir, check=True, capture_output=True
                )

            for del_path in c.deleted_files:
                dest = repo_dir / del_path
                if dest.exists():
                    dest.unlink()
                subprocess.run(
                    ["git", "rm", "--ignore-unmatch", del_path],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

            commit_env = {
                **git_env,
                "GIT_AUTHOR_DATE": c.date,
                "GIT_COMMITTER_DATE": c.date,
            }
            subprocess.run(
                ["git", "commit", "-m", c.message],
                cwd=repo_dir,
                env=commit_env,
                check=True,
                capture_output=True,
            )
    elif tree:
        for rel_path, content in tree.items():
            dest = repo_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        commit_env = {
            **git_env,
            "GIT_AUTHOR_DATE": "2026-09-01T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-09-01T12:00:00Z",
        }
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_dir,
            env=commit_env,
            check=True,
            capture_output=True,
        )

    return repo_dir


def copy_layout(name: str, dest_dir: Path) -> Path:
    """Copy a fixture layout tree into dest_dir and initialize a git repository."""
    layout_src = FIXTURES_DIR / "layouts" / name
    if not layout_src.exists():
        raise FileNotFoundError(f"Layout '{name}' not found at {layout_src}")

    tree: dict[str, str] = {}
    for p in layout_src.rglob("*"):
        if p.is_file():
            rel_p = str(p.relative_to(layout_src))
            tree[rel_p] = p.read_text(encoding="utf-8")

    return make_repo(dest_dir, tree=tree)


def create_fake_github_transport(
    files: dict[str, str],
    commits_by_path: dict[str, list[dict[str, Any]]] | None = None,
    default_branch: str = "main",
    rate_limit_remaining: int = 60,
    simulate_rate_limit: bool = False,
    simulate_truncated_tree: bool = False,
) -> httpx.MockTransport:
    """Create an httpx.MockTransport that emulates the GitHub API and raw content endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        headers = {
            "x-ratelimit-remaining": str(0 if simulate_rate_limit else rate_limit_remaining),
            "x-ratelimit-reset": "1780000000",
        }

        if simulate_rate_limit:
            return httpx.Response(
                403,
                headers=headers,
                json={
                    "message": "API rate limit exceeded for user",
                    "documentation_url": "https://docs.github.com",
                },
            )

        # 1. Repository metadata endpoint: GET /repos/{owner}/{repo}
        if re.search(r"^https://api\.github\.com/repos/[^/]+/[^/]+$", url_str):
            if "not-found" in url_str:
                return httpx.Response(404, headers=headers, json={"message": "Not Found"})
            return httpx.Response(
                200,
                headers=headers,
                json={
                    "default_branch": default_branch,
                    "full_name": "example/repo",
                    "private": False,
                },
            )

        # 2. Recursive git tree: GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1
        if "/git/trees/" in url_str:
            match_tree = re.search(r"/git/trees/([^?]+)", request.url.path)
            if match_tree:
                branch_in_url = match_tree.group(1)
                if branch_in_url not in (default_branch, "master", "main", "HEAD"):
                    return httpx.Response(404, headers=headers, json={"message": "Not Found"})

            tree_items = []
            for path_str, content in files.items():
                tree_items.append(
                    {
                        "path": path_str,
                        "mode": "100644",
                        "type": "blob",
                        "size": len(content.encode("utf-8")),
                        "sha": "blob_sha_" + path_str.replace("/", "_"),
                    }
                )
            return httpx.Response(
                200,
                headers=headers,
                json={
                    "sha": "tree_root_sha",
                    "tree": tree_items,
                    "truncated": simulate_truncated_tree,
                },
            )

        # 2b. Rate limit endpoint: GET /rate_limit
        if "/rate_limit" in url_str:
            return httpx.Response(
                200,
                headers=headers,
                json={
                    "resources": {
                        "core": {
                            "limit": 5000,
                            "remaining": 0 if simulate_rate_limit else rate_limit_remaining,
                            "reset": 1780000000,
                        }
                    }
                },
            )

        # 3. Raw file downloads: raw.githubusercontent.com or /contents/
        if "raw.githubusercontent.com" in url_str:
            # Format: https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
            parts = request.url.path.strip("/").split("/", 3)
            if len(parts) >= 4:
                file_rel = parts[3]
                if file_rel in files:
                    return httpx.Response(200, headers=headers, text=files[file_rel])
            return httpx.Response(404, headers=headers, text="Not Found")

        if "/contents/" in url_str:
            # Format: /repos/{owner}/{repo}/contents/{path}?ref=...
            match = re.search(r"/contents/([^?]+)", request.url.path)
            if match:
                file_rel = match.group(1).lstrip("/")
                if file_rel in files:
                    return httpx.Response(200, headers=headers, text=files[file_rel])
            return httpx.Response(404, headers=headers, text="Not Found")

        # 4. Commits endpoint: GET /repos/{owner}/{repo}/commits?path=...
        if "/commits" in url_str:
            path_query = request.url.params.get("path", "")
            commits = []
            if commits_by_path and path_query in commits_by_path:
                commits = commits_by_path[path_query]
            else:
                # Default synthetic commit for path
                commits = [
                    {
                        "sha": "1111111111111111111111111111111111111111",
                        "commit": {
                            "author": {"date": "2026-09-01T12:00:00Z"},
                            "committer": {"date": "2026-09-01T12:00:00Z"},
                            "message": "Update " + path_query,
                        },
                    }
                ]
            return httpx.Response(200, headers=headers, json=commits)

        return httpx.Response(404, headers=headers, json={"message": "Not Found"})

    import re

    return httpx.MockTransport(handler)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
