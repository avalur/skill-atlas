"""GitHub REST API and raw content client for remote repository scanning."""

import contextlib
import datetime
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from collections.abc import Callable

import httpx

from skill_atlas import __version__
from skill_atlas.models import parse_utc_timestamp

# Upper bound (seconds) for honoring Retry-After / secondary rate-limit backoff.
MAX_RETRY_AFTER_SECONDS = 60
# Maximum number of automatic retries for secondary rate-limit responses.
MAX_SECONDARY_RATE_RETRIES = 3


class RateLimitError(RuntimeError):
    """Raised when GitHub API rate limit is exhausted."""

    def __init__(self, reset_epoch: int | None = None, token_configured: bool = False) -> None:
        self.reset_epoch = reset_epoch
        self.token_configured = token_configured
        if reset_epoch:
            reset_time = datetime.datetime.fromtimestamp(reset_epoch, tz=datetime.UTC).strftime(
                "%H:%M UTC"
            )
            if token_configured:
                msg = (
                    f"GitHub rate limit reached, resets at {reset_time}; "
                    "set GITHUB_TOKEN or check quota (configured token exhausted)"
                )
            else:
                msg = f"GitHub rate limit reached, resets at {reset_time}; set GITHUB_TOKEN"
        else:
            msg = (
                "GitHub rate limit reached; set GITHUB_TOKEN or check quota (configured token exhausted)"
                if token_configured
                else "GitHub rate limit reached; set GITHUB_TOKEN"
            )
        super().__init__(msg)


_cached_gh_token: str | None = None
_gh_token_checked: bool = False


def _resolve_gh_cli_token() -> str | None:
    """Resolve token from GitHub CLI once and cache result."""
    global _cached_gh_token, _gh_token_checked
    if _gh_token_checked:
        return _cached_gh_token
    _gh_token_checked = True
    if shutil.which("gh"):
        with contextlib.suppress(subprocess.SubprocessError, OSError):
            res = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                _cached_gh_token = res.stdout.strip()
    return _cached_gh_token


class GitHubClient:
    """Client for scanning GitHub repositories via REST API and raw downloads."""

    def __init__(self, token: str | None = None) -> None:
        self.token = (
            token
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
            or _resolve_gh_cli_token()
        )
        self.api_base = "https://api.github.com"
        self.raw_base = "https://raw.githubusercontent.com"
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None
        self._auth_disabled: bool = False

    def _get_headers(self, with_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SkillAtlas-Scanner/{__version__}",
        }
        if with_auth and self.token and not self._auth_disabled:
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
            raise RateLimitError(self.rate_limit_reset, token_configured=bool(self.token))

    def _is_repo_public(self, client: httpx.Client, owner: str, repo: str) -> bool:
        """Check if repository is publicly accessible without authentication."""
        try:
            r = client.get(
                f"{self.api_base}/repos/{owner}/{repo}",
                headers=self._get_headers(with_auth=False),
            )
            self._record_rate_limit(r)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _request(self, client: httpx.Client, url: str) -> httpx.Response:
        """Execute request with automatic fallback to unauthenticated request on 401/403."""
        resp = client.get(url, headers=self._get_headers(with_auth=True))
        self._record_rate_limit(resp)

        if resp.status_code in (401, 403) and self.token and not self._auth_disabled:
            if resp.status_code == 401:
                # Token is invalid or revoked: try unauthenticated request
                resp_unauth = client.get(url, headers=self._get_headers(with_auth=False))
                self._record_rate_limit(resp_unauth)
                if resp_unauth.status_code == 200:
                    self._auth_disabled = True
                    return resp_unauth
                raise ValueError(
                    "GitHub authentication failed: configured GITHUB_TOKEN is invalid or revoked"
                )

            sso_hdr = resp.headers.get("x-github-sso", "")
            is_sso = "organization saml enforcement" in resp.text.lower() or bool(sso_hdr)

            # Check if rate limit exhausted
            if self.rate_limit_remaining == 0 or "rate limit" in resp.text.lower():
                raise RateLimitError(self.rate_limit_reset, token_configured=True)

            # Fall back to unauthenticated request
            resp_unauth = client.get(url, headers=self._get_headers(with_auth=False))
            self._record_rate_limit(resp_unauth)

            if resp_unauth.status_code == 200:
                if is_sso:
                    self._auth_disabled = True
                return resp_unauth

            if is_sso:
                # If unauth was not 200, check if the repo itself is public
                # (e.g. 404 on a non-existent branch of a public repo)
                repo_match = re.search(r"https://api\.github\.com/repos/([^/]+)/([^/?]+)", url)
                if repo_match:
                    owner, repo = repo_match.group(1), repo_match.group(2)
                    repo_url = f"{self.api_base}/repos/{owner}/{repo}"
                    if url == repo_url:
                        # Already queried the repo root and it was not 200
                        is_public = False
                    else:
                        is_public = self._is_repo_public(client, owner, repo)

                    if is_public:
                        self._auth_disabled = True
                        return resp_unauth

                # Repository is private or requires SAML SSO
                sso_match = re.search(r"url=([^\s;]+)", sso_hdr)
                sso_url = sso_match.group(1) if sso_match else None
                msg = "GitHub organization SAML SSO authorization required for your token."
                if sso_url:
                    msg += f"\nPlease authorize your token at: {sso_url}"
                raise RuntimeError(msg)

            return resp_unauth

        return resp

    def get_rate_limit(self, client: httpx.Client | None = None) -> int | None:
        """Query current rate limit remaining from GitHub API."""
        url = f"{self.api_base}/rate_limit"
        close_client = False
        c = client
        if c is None:
            c = httpx.Client(timeout=10.0)
            close_client = True
        try:
            resp = c.get(url, headers=self._get_headers(with_auth=True))
            self._record_rate_limit(resp)
            return self.rate_limit_remaining
        except Exception:  # noqa: BLE001
            return self.rate_limit_remaining
        finally:
            if close_client:
                c.close()

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> int | None:
        """Parse the Retry-After header (seconds) if present, bounded to a sane cap."""
        retry_after = resp.headers.get("retry-after")
        if retry_after is None:
            return None
        try:
            seconds = int(retry_after.strip())
        except ValueError:
            return None
        if seconds < 0:
            return None
        return min(seconds, MAX_RETRY_AFTER_SECONDS)

    def _request_with_retry(
        self,
        client: httpx.Client,
        url: str,
        *,
        sleep_fn: "Callable[[float], None] | None" = None,
    ) -> httpx.Response:
        """Issue a request honoring secondary rate-limit Retry-After backoff.

        Primary rate-limit exhaustion is surfaced via RateLimitError by ``_request``.
        Secondary rate limits (HTTP 429, or 403 with a Retry-After header) are retried
        a bounded number of times after sleeping for the advertised interval.
        """
        sleeper = sleep_fn or time.sleep
        attempt = 0
        while True:
            resp = self._request(client, url)
            if resp.status_code in (403, 429):
                wait = self._parse_retry_after(resp)
                if wait is not None and attempt < MAX_SECONDARY_RATE_RETRIES:
                    attempt += 1
                    sleeper(float(wait))
                    continue
            return resp

    def fetch_org_repos(
        self,
        client: httpx.Client,
        org: str,
        *,
        include_forks: bool = False,
        include_archived: bool = False,
        max_repos: int | None = None,
        per_page: int = 100,
        sleep_fn: "Callable[[float], None] | None" = None,
    ) -> list[dict]:
        """Enumerate public repositories of a GitHub organization (or user).

        Uses the paginated ``GET /orgs/{org}/repos`` endpoint, falling back to
        ``GET /users/{org}/repos`` when the login refers to a user account.
        Archived repositories and forks are excluded by default.

        Returns a list of repository metadata dicts sorted by ``full_name``.
        """
        page_size = max(1, min(per_page, 100))
        endpoints = (
            f"{self.api_base}/orgs/{org}/repos",
            f"{self.api_base}/users/{org}/repos",
        )

        base_url: str | None = None
        for endpoint in endpoints:
            probe = self._request_with_retry(
                client,
                f"{endpoint}?per_page={page_size}&sort=full_name&page=1",
                sleep_fn=sleep_fn,
            )
            if probe.status_code == 404:
                continue
            if probe.status_code != 200:
                raise ValueError(
                    f"Failed to enumerate repositories for '{org}' (HTTP {probe.status_code})"
                )
            base_url = endpoint
            first_page = probe
            break
        else:
            raise ValueError(f"GitHub organization or user '{org}' not found")

        repos: list[dict] = []

        def consume(resp: httpx.Response) -> None:
            data = resp.json()
            if not isinstance(data, list):
                return
            for item in data:
                if not isinstance(item, dict):
                    continue
                if not include_forks and item.get("fork"):
                    continue
                if not include_archived and item.get("archived"):
                    continue
                repos.append(
                    {
                        "name": item.get("name"),
                        "full_name": item.get("full_name"),
                        "fork": bool(item.get("fork")),
                        "archived": bool(item.get("archived")),
                        "default_branch": item.get("default_branch"),
                        "html_url": item.get("html_url"),
                        "clone_url": item.get("clone_url"),
                        "size": item.get("size", 0),
                    }
                )

        consume(first_page)
        page = 2
        # Continue paginating while a full page was returned (more may remain).
        last_count = len(first_page.json()) if isinstance(first_page.json(), list) else 0
        while last_count >= page_size:
            if max_repos is not None and len(repos) >= max_repos:
                break
            resp = self._request_with_retry(
                client,
                f"{base_url}?per_page={page_size}&sort=full_name&page={page}",
                sleep_fn=sleep_fn,
            )
            if resp.status_code != 200:
                break
            payload = resp.json()
            last_count = len(payload) if isinstance(payload, list) else 0
            if last_count == 0:
                break
            consume(resp)
            page += 1

        repos.sort(key=lambda r: (r.get("full_name") or "").lower())
        if max_repos is not None:
            repos = repos[:max_repos]
        return repos

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
        self,
        client: httpx.Client,
        owner: str,
        repo: str,
        branch: str,
        is_explicit_ref: bool = False,
    ) -> tuple[str, list[dict], bool]:
        """Fetch full recursive tree of repository.

        Returns (branch_used, tree_items, is_truncated).
        """
        branches_to_try = (branch,) if is_explicit_ref else (branch, "master", "main")
        for target_branch in branches_to_try:
            url = f"{self.api_base}/repos/{owner}/{repo}/git/trees/{target_branch}?recursive=1"
            resp = self._request(client, url)
            if resp.status_code == 404:
                continue
            if resp.status_code == 200:
                data = resp.json()
                tree = data.get("tree", [])
                truncated = bool(data.get("truncated", False))
                return target_branch, tree, truncated
        if is_explicit_ref:
            raise ValueError(f"Git ref '{branch}' not found in GitHub repository '{owner}/{repo}'")
        return branch, [], False

    def fetch_file_content(
        self, client: httpx.Client, owner: str, repo: str, branch: str, file_path: str
    ) -> str | None:
        """Download raw file content with auth headers if token is present."""
        quoted_path = urllib.parse.quote(file_path.lstrip("/"))
        url = f"{self.raw_base}/{owner}/{repo}/{branch}/{quoted_path}"
        headers = {"User-Agent": f"SkillAtlas-Scanner/{__version__}"}
        if self.token and not self._auth_disabled:
            headers["Authorization"] = f"Bearer {self.token}"

        resp = client.get(url, headers=headers)
        self._record_rate_limit(resp)
        if resp.status_code == 200:
            return resp.text

        # If authenticated raw request failed (e.g. 404 due to token/SAML restrictions on public repos),
        # fall back to unauthenticated raw request
        if resp.status_code in (401, 403, 404) and self.token and not self._auth_disabled:
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

        if oldest_date:
            oldest_date = parse_utc_timestamp(oldest_date).strftime("%Y-%m-%dT%H:%M:%SZ")
        if newest_date:
            newest_date = parse_utc_timestamp(newest_date).strftime("%Y-%m-%dT%H:%M:%SZ")

        return oldest_sha, oldest_date, newest_sha, newest_date
