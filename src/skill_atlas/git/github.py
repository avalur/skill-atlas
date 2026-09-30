"""GitHub REST API and raw content client for remote repository scanning."""

import contextlib
import datetime
import os
import re
import shutil
import subprocess
import urllib.parse

import httpx

from skill_atlas import __version__


class RateLimitError(RuntimeError):
    """Raised when GitHub API rate limit is exhausted."""

    def __init__(self, reset_epoch: int | None = None) -> None:
        if reset_epoch:
            reset_time = datetime.datetime.fromtimestamp(reset_epoch, tz=datetime.UTC).strftime(
                "%H:%M UTC"
            )
            msg = f"GitHub rate limit reached, resets at {reset_time}; set GITHUB_TOKEN"
        else:
            msg = "GitHub rate limit reached; set GITHUB_TOKEN"
        super().__init__(msg)
        self.reset_epoch = reset_epoch


class GitHubClient:
    """Client for scanning GitHub repositories via REST API and raw downloads."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not self.token and shutil.which("gh"):
            with contextlib.suppress(subprocess.SubprocessError, OSError):
                res = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    self.token = res.stdout.strip()
        self.api_base = "https://api.github.com"
        self.raw_base = "https://raw.githubusercontent.com"
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None

    def _get_headers(self, with_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SkillAtlas-Scanner/{__version__}",
        }
        if with_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _record_rate_limit(self, resp: httpx.Response) -> None:
        rem = resp.headers.get("x-ratelimit-remaining")
        if rem is not None:
            try:
                self.rate_limit_remaining = int(rem)
            except ValueError:
                pass
        rst = resp.headers.get("x-ratelimit-reset")
        if rst is not None:
            try:
                self.rate_limit_reset = int(rst)
            except ValueError:
                pass

        if resp.status_code == 403 and (
            self.rate_limit_remaining == 0 or "rate limit" in resp.text.lower()
        ):
            raise RateLimitError(self.rate_limit_reset)

    def _request(self, client: httpx.Client, url: str) -> httpx.Response:
        """Execute request with automatic fallback to unauthenticated request on 401/403."""
        resp = client.get(url, headers=self._get_headers(with_auth=True))
        self._record_rate_limit(resp)

        if resp.status_code in (401, 403) and self.token:
            sso_hdr = resp.headers.get("x-github-sso", "")
            if "organization saml enforcement" in resp.text.lower() or sso_hdr:
                sso_match = re.search(r"url=([^\s;]+)", sso_hdr)
                sso_url = sso_match.group(1) if sso_match else None
                msg = "GitHub organization SAML SSO authorization required for your token."
                if sso_url:
                    msg += f"\nPlease authorize your token at: {sso_url}"
                raise RuntimeError(msg)

            # Fall back to unauthenticated request if it wasn't a rate limit issue
            if self.rate_limit_remaining != 0 and "rate limit" not in resp.text.lower():
                resp = client.get(url, headers=self._get_headers(with_auth=False))
                self._record_rate_limit(resp)

        return resp

    def get_default_branch(self, client: httpx.Client, owner: str, repo: str) -> str:
        """Determine default branch of repository (main, master, etc.)."""
        url = f"{self.api_base}/repos/{owner}/{repo}"
        resp = self._request(client, url)
        if resp.status_code == 404:
            raise ValueError(f"GitHub repository '{owner}/{repo}' not found")
        if resp.status_code == 200:
            data = resp.json()
            return data.get("default_branch", "main")
        return "main"

    def fetch_all_paths(
        self, client: httpx.Client, owner: str, repo: str, branch: str
    ) -> tuple[str, list[dict], bool]:
        """Fetch full recursive tree of repository.

        Returns (branch_used, tree_items, is_truncated).
        """
        for target_branch in (branch, "master", "main"):
            url = f"{self.api_base}/repos/{owner}/{repo}/git/trees/{target_branch}?recursive=1"
            resp = self._request(client, url)
            if resp.status_code == 404:
                continue
            if resp.status_code == 200:
                data = resp.json()
                tree = data.get("tree", [])
                truncated = bool(data.get("truncated", False))
                return target_branch, tree, truncated
        return branch, [], False

    def fetch_file_content(
        self, client: httpx.Client, owner: str, repo: str, branch: str, file_path: str
    ) -> str | None:
        """Download raw file content with auth headers if token is present."""
        quoted_path = urllib.parse.quote(file_path.lstrip("/"))
        url = f"{self.raw_base}/{owner}/{repo}/{branch}/{quoted_path}"
        headers = {"User-Agent": f"SkillAtlas-Scanner/{__version__}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        resp = client.get(url, headers=headers)
        self._record_rate_limit(resp)
        if resp.status_code == 200:
            return resp.text

        # If authenticated raw request failed (e.g. 404 due to token/SAML restrictions on public repos),
        # fall back to unauthenticated raw request
        if resp.status_code in (401, 403, 404) and self.token:
            unauth_headers = {"User-Agent": f"SkillAtlas-Scanner/{__version__}"}
            resp_unauth = client.get(url, headers=unauth_headers)
            self._record_rate_limit(resp_unauth)
            if resp_unauth.status_code == 200:
                return resp_unauth.text

        # Fallback to contents API with raw Accept header
        api_url = f"{self.api_base}/repos/{owner}/{repo}/contents/{quoted_path}?ref={branch}"
        api_headers = self._get_headers(with_auth=True)
        api_headers["Accept"] = "application/vnd.github.raw"
        resp_api = client.get(api_url, headers=api_headers)
        self._record_rate_limit(resp_api)
        if resp_api.status_code == 200:
            return resp_api.text

        if resp_api.status_code in (401, 403) and self.token:
            resp_api_unauth = client.get(
                api_url,
                headers={
                    "Accept": "application/vnd.github.raw",
                    "User-Agent": f"SkillAtlas-Scanner/{__version__}",
                },
            )
            self._record_rate_limit(resp_api_unauth)
            if resp_api_unauth.status_code == 200:
                return resp_api_unauth.text

        return None

    def fetch_provenance_and_updated(
        self, client: httpx.Client, owner: str, repo: str, path: str, ref: str | None = None
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Fetch oldest (introductory) and newest commit info for a path.

        Returns (introductory_sha, introductory_date, updated_sha, updated_date).
        """
        quoted_path = urllib.parse.quote(path.lstrip("/"))
        url = f"{self.api_base}/repos/{owner}/{repo}/commits?path={quoted_path}&per_page=100"
        if ref:
            url += f"&sha={urllib.parse.quote(ref)}"

        resp = self._request(client, url)
        if resp.status_code != 200:
            return None, None, None, None

        commits = resp.json()
        if not isinstance(commits, list) or len(commits) == 0:
            return None, None, None, None

        # First commit is the newest commit
        newest = commits[0]
        newest_sha = newest.get("sha")
        newest_commit = newest.get("commit", {})
        newest_author = newest_commit.get("author", {}) or newest_commit.get("committer", {})
        newest_date = newest_author.get("date")

        # Check for pagination to find oldest commit
        link_header = resp.headers.get("Link", "")
        oldest_sha = newest_sha
        oldest_date = newest_date

        if 'rel="last"' in link_header:
            match = re.search(r'<([^>]+)>;\s*rel="last"', link_header)
            if match:
                last_url = match.group(1)
                resp_last = self._request(client, last_url)
                if resp_last.status_code == 200:
                    last_commits = resp_last.json()
                    if isinstance(last_commits, list) and len(last_commits) > 0:
                        oldest = last_commits[-1]
                        oldest_sha = oldest.get("sha")
                        oldest_commit = oldest.get("commit", {})
                        oldest_author = oldest_commit.get("author", {}) or oldest_commit.get(
                            "committer", {}
                        )
                        oldest_date = oldest_author.get("date")
        else:
            oldest = commits[-1]
            oldest_sha = oldest.get("sha")
            oldest_commit = oldest.get("commit", {})
            oldest_author = oldest_commit.get("author", {}) or oldest_commit.get("committer", {})
            oldest_date = oldest_author.get("date")

        return oldest_sha, oldest_date, newest_sha, newest_date
