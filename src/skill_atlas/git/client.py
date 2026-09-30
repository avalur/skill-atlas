"""Local Git client for repository metadata and commit provenance."""

import os
import re
import subprocess
from pathlib import Path

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", **os.environ}


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Parse owner and repo name from GitHub URL (https or ssh)."""
    # Matches https://github.com/owner/repo(.git)? or git@github.com:owner/repo(.git)?
    pattern = re.compile(
        r"^(?:https?://github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
    )
    match = pattern.match(url.strip())
    if match:
        return match.group("owner"), match.group("repo")
    return None


def is_git_repository(path: Path) -> bool:
    """Check if the given path is inside a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path if path.is_dir() else path.parent),
            capture_output=True,
            text=True,
            timeout=15,
            env=GIT_ENV,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:  # noqa: BLE001
        return False


def get_repo_info(path: Path) -> tuple[Path | None, str | None, str | None]:
    """Return (repo_root, repo_name, repo_url) for a local path inside a Git repository."""
    dir_path = path if path.is_dir() else path.parent
    try:
        # Get repository root
        root_res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(dir_path),
            capture_output=True,
            text=True,
            timeout=15,
            env=GIT_ENV,
            check=False,
        )
        if root_res.returncode != 0:
            return None, None, None

        repo_root = Path(root_res.stdout.strip())

        # Get remote URL
        url_res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
            env=GIT_ENV,
            check=False,
        )
        repo_url = (
            url_res.stdout.strip() if url_res.returncode == 0 and url_res.stdout.strip() else None
        )

        # Determine repo_name
        repo_name: str | None = None
        if repo_url:
            gh_match = parse_github_url(repo_url)
            if gh_match:
                repo_name = f"{gh_match[0]}/{gh_match[1]}"
            else:
                repo_name = Path(repo_url.rstrip("/")).stem
        else:
            repo_name = repo_root.name

        return repo_root, repo_name, repo_url
    except Exception:  # noqa: BLE001
        return None, None, None


def get_file_provenance(repo_root: Path, file_rel_path: str) -> tuple[str | None, str | None]:
    """Retrieve the introductory commit hash and author ISO date for a file."""
    try:
        # Primary lookup: introductory commit where file was first added (oldest first)
        res = subprocess.run(
            [
                "git",
                "log",
                "--reverse",
                "--diff-filter=A",
                "--format=%H %aI",
                "--",
                file_rel_path,
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
            env=GIT_ENV,
            check=False,
        )
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        output = lines[0] if lines else ""

        # Fallback if diff-filter=A didn't match (e.g. initial root commit)
        if not output:
            res_fallback = subprocess.run(
                [
                    "git",
                    "log",
                    "--reverse",
                    "--format=%H %aI",
                    "--",
                    file_rel_path,
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
                env=GIT_ENV,
                check=False,
            )
            fallback_lines = [
                line.strip() for line in res_fallback.stdout.splitlines() if line.strip()
            ]
            output = fallback_lines[0] if fallback_lines else ""

        if output:
            parts = output.split(" ", 1)
            commit_hash = parts[0]
            commit_date = parts[1] if len(parts) > 1 else None
            return commit_hash, commit_date

        return None, None
    except Exception:  # noqa: BLE001
        return None, None
