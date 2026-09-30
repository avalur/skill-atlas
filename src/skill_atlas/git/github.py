"""GitHub REST API and raw content client for remote repository scanning."""

import os
import re
import urllib.parse

import httpx

from skill_atlas import __version__


class GitHubClient:
    """Client for scanning GitHub repositories via REST API and raw downloads."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.api_base = "https://api.github.com"
        self.raw_base = "https://raw.githubusercontent.com"

    def _get_headers(self, with_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SkillAtlas-Scanner/{__version__}",
        }
        if with_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, client: httpx.Client, url: str) -> httpx.Response:
        """Execute request with automatic fallback to unauthenticated request on 401/403."""
        resp = client.get(url, headers=self._get_headers(with_auth=True))
        if resp.status_code in (401, 403) and self.token:
            # Fall back to unauthenticated request (e.g. for SAML-restricted public orgs)
            resp = client.get(url, headers=self._get_headers(with_auth=False))
        return resp

    def get_default_branch(self, client: httpx.Client, owner: str, repo: str) -> str:
        """Determine default branch of repository (main, master, etc.)."""
        url = f"{self.api_base}/repos/{owner}/{repo}"
        resp = self._request(client, url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("default_branch", "main")
        return "main"

    def fetch_all_paths(
        self, client: httpx.Client, owner: str, repo: str, branch: str
    ) -> tuple[str, list[str]]:
        """Fetch full recursive tree of repository. Falls back to master if branch fails."""
        for target_branch in (branch, "master", "main"):
            url = f"{self.api_base}/repos/{owner}/{repo}/git/trees/{target_branch}?recursive=1"
            resp = self._request(client, url)
            if resp.status_code == 200:
                data = resp.json()
                tree = data.get("tree", [])
                paths = [item["path"] for item in tree if item.get("type") == "blob"]
                return target_branch, paths
        return branch, []

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
        if resp.status_code == 200:
            return resp.text

        # Fallback to contents API with raw Accept header
        api_url = f"{self.api_base}/repos/{owner}/{repo}/contents/{quoted_path}?ref={branch}"
        api_headers = self._get_headers(with_auth=True)
        api_headers["Accept"] = "application/vnd.github.raw"
        resp_api = client.get(api_url, headers=api_headers)
        if resp_api.status_code == 200:
            return resp_api.text

        return None

    def fetch_file_provenance(
        self, client: httpx.Client, owner: str, repo: str, file_path: str
    ) -> tuple[str | None, str | None]:
        """Fetch introductory commit SHA and date using commits API (oldest first)."""
        quoted_path = urllib.parse.quote(file_path.lstrip("/"))
        url = f"{self.api_base}/repos/{owner}/{repo}/commits?path={quoted_path}&per_page=100"
        resp = self._request(client, url)
        if resp.status_code == 200:
            link_header = resp.headers.get("Link", "")
            # If multiple pages, jump to last page
            if 'rel="last"' in link_header:
                match = re.search(r'<([^>]+)>;\s*rel="last"', link_header)
                if match:
                    last_url = match.group(1)
                    resp_last = self._request(client, last_url)
                    if resp_last.status_code == 200:
                        resp = resp_last

            commits = resp.json()
            if isinstance(commits, list) and len(commits) > 0:
                oldest_commit = commits[-1]
                sha = oldest_commit.get("sha")
                commit_info = oldest_commit.get("commit", {})
                author_info = commit_info.get("author", {}) or commit_info.get("committer", {})
                date = author_info.get("date")
                return sha, date
        return None, None
