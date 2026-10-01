"""Unit and integration tests for GitHub organization-wide skill scanning.

All GitHub interactions are simulated via httpx.MockTransport so the suite runs
fully offline and deterministically.
"""

import re
import urllib.parse
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from skill_atlas.cli import app
from skill_atlas.discovery.org import discover_org_skills
from skill_atlas.git.client import is_org_target, parse_org_target
from skill_atlas.git.github import GitHubClient, RateLimitError
from skill_atlas.scanner import Scanner

# --------------------------------------------------------------------------- #
# Target resolution (unit)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("org:JetBrains", "JetBrains"),
        ("ORG:JetBrains", "JetBrains"),
        ("https://github.com/JetBrains", "JetBrains"),
        ("https://github.com/orgs/JetBrains", "JetBrains"),
        ("https://github.com/orgs/JetBrains/", "JetBrains"),
        ("http://github.com/JetBrains/", "JetBrains"),
    ],
)
def test_parse_org_target_positive(target: str, expected: str) -> None:
    assert parse_org_target(target) == expected
    assert is_org_target(target) is True


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/JetBrains/intellij-community",
        "https://github.com/JetBrains/intellij-community.git",
        "git@github.com:JetBrains/intellij-community.git",
        "./local/path",
        "https://github.com/settings",
        "https://github.com/orgs",
        "",
        "-oops",
    ],
)
def test_parse_org_target_negative(target: str) -> None:
    assert parse_org_target(target) is None
    assert is_org_target(target) is False


# --------------------------------------------------------------------------- #
# Mock transport helpers
# --------------------------------------------------------------------------- #


def _skill_md(name: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: A valid skill named {name} used for organization scan tests.\n"
        "---\n"
        f"# {name}\n"
    )


def build_org_transport(
    org: str,
    repos: list[dict[str, Any]],
    repo_files: dict[str, dict[str, str]],
    *,
    per_page_cap: int = 100,
    user_fallback: bool = False,
    retry_after_once: bool = False,
) -> tuple[httpx.MockTransport, dict[str, int]]:
    """Build a MockTransport emulating org repo enumeration and per-repo tree scans.

    Returns the transport plus a mutable call-counter dict for assertions.
    """
    counters = {"repos_requests": 0, "retry_served": 0}

    def paginate(request: httpx.Request) -> httpx.Response:
        qs = urllib.parse.parse_qs(request.url.query.decode())
        page = int(qs.get("page", ["1"])[0])
        per_page = min(int(qs.get("per_page", ["100"])[0]), per_page_cap)
        start = (page - 1) * per_page
        chunk = repos[start : start + per_page]
        return httpx.Response(200, json=chunk)

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        # Org repos enumeration
        m_org = re.search(r"/orgs/([^/]+)/repos", request.url.path)
        if m_org:
            counters["repos_requests"] += 1
            if user_fallback:
                return httpx.Response(404, json={"message": "Not Found"})
            if retry_after_once and counters["retry_served"] == 0:
                counters["retry_served"] += 1
                return httpx.Response(403, headers={"retry-after": "2"}, json={"message": "slow"})
            return paginate(request)

        m_user = re.search(r"/users/([^/]+)/repos", request.url.path)
        if m_user:
            if user_fallback:
                return paginate(request)
            return httpx.Response(404, json={"message": "Not Found"})

        # Repo metadata: /repos/{owner}/{repo}
        m_repo = re.match(r"^https://api\.github\.com/repos/([^/]+)/([^/]+)$", url_str)
        if m_repo:
            full = f"{m_repo.group(1)}/{m_repo.group(2)}"
            if full not in repo_files:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"default_branch": "main", "full_name": full})

        # Recursive tree
        if "/git/trees/" in url_str:
            m = re.match(r"^https://api\.github\.com/repos/([^/]+)/([^/]+)/git/trees/", url_str)
            full = f"{m.group(1)}/{m.group(2)}" if m else ""
            files = repo_files.get(full, {})
            tree_items = [
                {
                    "path": p,
                    "mode": "100644",
                    "type": "blob",
                    "size": len(c.encode()),
                    "sha": "sha_" + p.replace("/", "_"),
                }
                for p, c in files.items()
            ]
            return httpx.Response(200, json={"sha": "root", "tree": tree_items, "truncated": False})

        # Commits
        if "/commits" in url_str:
            return httpx.Response(200, json=[])

        # Raw content
        m_raw = re.match(
            r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/[^/]+/(.+)$", url_str
        )
        if m_raw:
            full = f"{m_raw.group(1)}/{m_raw.group(2)}"
            path = urllib.parse.unquote(m_raw.group(3))
            content = repo_files.get(full, {}).get(path)
            if content is None:
                return httpx.Response(404, text="Not Found")
            return httpx.Response(200, text=content)

        if "/rate_limit" in url_str:
            return httpx.Response(200, json={"resources": {"core": {"remaining": 5000}}})

        return httpx.Response(404, json={"message": "Not Found", "url": url_str})

    return httpx.MockTransport(handler), counters


def _repo(name: str, *, fork: bool = False, archived: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "full_name": f"TestOrg/{name}",
        "fork": fork,
        "archived": archived,
        "default_branch": "main",
        "html_url": f"https://github.com/TestOrg/{name}",
        "clone_url": f"https://github.com/TestOrg/{name}.git",
        "size": 10,
    }


# --------------------------------------------------------------------------- #
# Repo enumeration (unit)
# --------------------------------------------------------------------------- #


def test_fetch_org_repos_pagination() -> None:
    repos = [_repo(f"repo-{i:02d}") for i in range(250)]
    transport, counters = build_org_transport("TestOrg", repos, {}, per_page_cap=100)
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        result = gh.fetch_org_repos(client, "TestOrg")
    assert len(result) == 250
    # 3 pages (100, 100, 50) -> last page < per_page stops pagination.
    assert counters["repos_requests"] == 3


def test_fetch_org_repos_filters_forks_and_archived() -> None:
    repos = [
        _repo("active"),
        _repo("a-fork", fork=True),
        _repo("old", archived=True),
    ]
    transport, _ = build_org_transport("TestOrg", repos, {})
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        default = gh.fetch_org_repos(client, "TestOrg")
        assert [r["name"] for r in default] == ["active"]

        with_forks = gh.fetch_org_repos(client, "TestOrg", include_forks=True)
        assert {r["name"] for r in with_forks} == {"active", "a-fork"}

        with_archived = gh.fetch_org_repos(client, "TestOrg", include_archived=True)
        assert {r["name"] for r in with_archived} == {"active", "old"}


def test_fetch_org_repos_max_repos() -> None:
    repos = [_repo(f"repo-{i:02d}") for i in range(20)]
    transport, _ = build_org_transport("TestOrg", repos, {})
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        result = gh.fetch_org_repos(client, "TestOrg", max_repos=5)
    assert len(result) == 5


def test_fetch_org_repos_user_fallback() -> None:
    repos = [_repo("solo")]
    transport, _ = build_org_transport("TestOrg", repos, {}, user_fallback=True)
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        result = gh.fetch_org_repos(client, "TestOrg")
    assert [r["name"] for r in result] == ["solo"]


def test_fetch_org_repos_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gh = GitHubClient()
        with pytest.raises(ValueError, match="not found"):
            gh.fetch_org_repos(client, "ghost")


def test_fetch_org_repos_retry_after() -> None:
    repos = [_repo("r1")]
    transport, counters = build_org_transport("TestOrg", repos, {}, retry_after_once=True)
    slept: list[float] = []
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        result = gh.fetch_org_repos(client, "TestOrg", sleep_fn=slept.append)
    assert [r["name"] for r in result] == ["r1"]
    assert slept == [2.0]  # honored the Retry-After interval once
    assert counters["retry_served"] == 1


# --------------------------------------------------------------------------- #
# Concurrent org discovery + full scan (integration)
# --------------------------------------------------------------------------- #


def test_discover_org_skills_concurrent() -> None:
    repos = [_repo("alpha"), _repo("beta"), _repo("gamma")]
    repo_files = {
        "TestOrg/alpha": {".claude/skills/alpha/SKILL.md": _skill_md("alpha")},
        "TestOrg/beta": {"skills/beta/SKILL.md": _skill_md("beta")},
        "TestOrg/gamma": {},  # no skills
    }
    transport, _ = build_org_transport("TestOrg", repos, repo_files)
    events: list[str] = []
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        skills = discover_org_skills(
            "TestOrg",
            gh_client=gh,
            http_client=client,
            on_progress=lambda e: events.append(e.message),
            concurrency=4,
        )
    names = sorted(s.name for s in skills)
    assert names == ["alpha", "beta"]
    # Each skill is attributed to its originating repository.
    assert {s.repo_name for s in skills} == {"TestOrg/alpha", "TestOrg/beta"}
    assert any("Found 3 repository" in m for m in events)


def test_scan_org_end_to_end() -> None:
    repos = [_repo("one"), _repo("two")]
    repo_files = {
        "TestOrg/one": {".claude/skills/one/SKILL.md": _skill_md("one")},
        "TestOrg/two": {".claude/skills/two/SKILL.md": _skill_md("two")},
    }
    transport, _ = build_org_transport("TestOrg", repos, repo_files)
    with httpx.Client(transport=transport) as client:
        gh = GitHubClient()
        scanner = Scanner()
        result = scanner.scan(
            target="https://github.com/TestOrg",
            http_client=client,
            gh_client=gh,
        )
    assert result.summary.total_skills == 2
    assert {s.repo_name for s in result.skills} == {"TestOrg/one", "TestOrg/two"}


def test_scan_org_rate_limit_propagates() -> None:
    repos = [_repo("one")]

    def handler(request: httpx.Request) -> httpx.Response:
        if "/orgs/" in str(request.url):
            return httpx.Response(200, json=repos)
        # Any repo-level request reports exhausted primary rate limit.
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1780000000"},
            json={"message": "API rate limit exceeded"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gh = GitHubClient()
        scanner = Scanner()
        with pytest.raises(RateLimitError):
            scanner.scan(
                target="org:TestOrg",
                http_client=client,
                gh_client=gh,
            )


def test_cli_invalid_concurrency_exit_code() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["scan", "org:TestOrg", "--concurrency", "0"])
    assert result.exit_code == 2


def test_cli_invalid_max_repos_exit_code() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["scan", "org:TestOrg", "--max-repos", "0"])
    assert result.exit_code == 2
