"""Local Git client for repository metadata and commit provenance."""

import re
import subprocess
from pathlib import Path


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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_repo_info(path: Path) -> tuple[Path | None, str | None, str | None]:
    """Return (repo_root, repo_name, repo_url) for a local path inside a Git repository."""
    dir_path = path if path.is_dir() else path.parent
    try:
        # Get repository root
        root_res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(dir_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if root_res.returncode != 0:
            return None, None, None

        repo_root = Path(root_res.stdout.strip())

        # Get remote URL
        url_res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
    except Exception:
        return None, None, None


def get_file_provenance(repo_root: Path, file_rel_path: str) -> tuple[str | None, str | None]:
    """Retrieve the introductory commit hash and author ISO date for a file."""
    try:
        # Primary lookup: introductory commit where file was added
        res = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--follow",
                "--format=%H %aI",
                "-1",
                "--",
                file_rel_path,
            ],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        output = res.stdout.strip()

        # Fallback if diff-filter=A didn't match (e.g. initial root commit or renamed without record)
        if not output:
            res_fallback = subprocess.run(
                ["git", "log", "--follow", "--format=%H %aI", "-1", "--", file_rel_path],
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            output = res_fallback.stdout.strip()

        if output:
            parts = output.split(" ", 1)
            commit_hash = parts[0]
            commit_date = parts[1] if len(parts) > 1 else None
            return commit_hash, commit_date

        return None, None
    except Exception:
        return None, None
