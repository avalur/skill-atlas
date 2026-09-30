"""GitHub REST API and raw content client for remote repository scanning."""

import os

import httpx


class GitHubClient:
    """Client for scanning GitHub repositories via REST API and raw downloads."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.api_base = "https://api.github.com"
        self.raw_base = "https://raw.githubusercontent.com"

    def _get_headers(self, with_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SkillAtlas-Scanner/0.1.0",
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
        """Download raw file content without API rate limit consumption."""
        url = f"{self.raw_base}/{owner}/{repo}/{branch}/{file_path}"
        resp = client.get(url, headers={"User-Agent": "SkillAtlas-Scanner/0.1.0"})
        if resp.status_code == 200:
            return resp.text
        return None

    def fetch_file_provenance(
        self, client: httpx.Client, owner: str, repo: str, file_path: str
    ) -> tuple[str | None, str | None]:
        """Fetch introductory commit SHA and date using commits API."""
        url = f"{self.api_base}/repos/{owner}/{repo}/commits?path={file_path}"
        resp = self._request(client, url)
        if resp.status_code == 200:
            commits = resp.json()
            if isinstance(commits, list) and len(commits) > 0:
                oldest_commit = commits[-1]
                sha = oldest_commit.get("sha")
                commit_info = oldest_commit.get("commit", {})
                author_info = commit_info.get("author", {}) or commit_info.get("committer", {})
                date = author_info.get("date")
                return sha, date
        return None, None
