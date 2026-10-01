"""Organization-wide skill discovery across all repositories of a GitHub org.

This module enumerates the public repositories of a GitHub organization (or user)
and scans their git trees concurrently (zero-clone) via the GitHub REST API,
bounding concurrency with a thread pool to maximize throughput while respecting
rate limits.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from skill_atlas.discovery.remote import _discover_via_github_api
from skill_atlas.git.github import GitHubClient, RateLimitError
from skill_atlas.models import (
    ProgressCallback,
    ProgressEvent,
    Skill,
    Stage,
)

# Default and maximum bounded concurrency for repository tree scanning.
DEFAULT_ORG_CONCURRENCY = 8
MAX_ORG_CONCURRENCY = 32


def discover_org_skills(
    org: str,
    ref: str | None = None,
    *,
    gh_client: GitHubClient | None = None,
    http_client: httpx.Client | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    discovery_only: bool = False,
    warnings: list[str] | None = None,
    concurrency: int = DEFAULT_ORG_CONCURRENCY,
    include_forks: bool = False,
    include_archived: bool = False,
    max_repos: int | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> list[Skill]:
    """Discover skills across every repository of a GitHub organization.

    Repositories are enumerated via the GitHub REST API (with pagination and
    archived/fork filtering) and scanned concurrently with bounded parallelism.
    """
    gh = gh_client or GitHubClient()
    t0 = time.time()
    concurrency = max(1, min(concurrency, MAX_ORG_CONCURRENCY))

    close_client = False
    client = http_client
    if client is None:
        limits = httpx.Limits(
            max_connections=concurrency * 2,
            max_keepalive_connections=concurrency * 2,
        )
        client = httpx.Client(timeout=20.0, follow_redirects=True, limits=limits)
        close_client = True

    def emit(
        stage: Stage,
        message: str,
        current: int | None = None,
        total: int | None = None,
        target_index: int | None = None,
        target_total: int | None = None,
        target_name: str | None = None,
    ) -> None:
        if on_progress:
            on_progress(
                ProgressEvent(
                    stage=stage,
                    message=message,
                    current=current,
                    total=total,
                    rate_limit_remaining=gh.rate_limit_remaining,
                    elapsed_ms=int((time.time() - t0) * 1000),
                    target_index=target_index,
                    target_total=target_total,
                    target_name=target_name,
                )
            )

    def check_cancel() -> None:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Scan cancelled by user")

    try:
        check_cancel()
        emit(Stage.DISCOVER, f"Enumerating repositories for organization '{org}'...")

        repos = gh.fetch_org_repos(
            client,
            org,
            include_forks=include_forks,
            include_archived=include_archived,
            max_repos=max_repos,
            sleep_fn=sleep_fn,
        )

        total_repos = len(repos)
        emit(
            Stage.DISCOVER,
            f"Found {total_repos} repository(ies) in '{org}'",
            total=total_repos,
        )
        if total_repos == 0:
            return []

        all_skills: list[Skill] = []
        results_lock = threading.Lock()
        completed = 0
        rate_limit_error: list[RateLimitError] = []

        def scan_repo(index: int, repo: dict) -> list[Skill]:
            check_cancel()
            full_name = repo.get("full_name") or f"{org}/{repo.get('name')}"
            repo_name = repo.get("name") or ""
            repo_url = repo.get("html_url") or f"https://github.com/{org}/{repo_name}"
            emit(
                Stage.FETCH,
                f"Scanning {full_name} ({index}/{total_repos})",
                current=index,
                total=total_repos,
                target_index=index,
                target_total=total_repos,
                target_name=full_name,
            )
            return _discover_via_github_api(
                owner=org,
                repo=repo_name,
                original_url=repo_url,
                ref=ref,
                gh_client=gh,
                http_client=client,
                on_progress=None,
                cancel_event=cancel_event,
                start_time=t0,
                discovery_only=discovery_only,
                warnings=warnings,
            )

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_repo = {
                executor.submit(scan_repo, idx, repo): repo
                for idx, repo in enumerate(repos, start=1)
            }
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                full_name = repo.get("full_name") or f"{org}/{repo.get('name')}"
                try:
                    repo_skills = future.result()
                    with results_lock:
                        all_skills.extend(repo_skills)
                except RateLimitError as err:
                    rate_limit_error.append(err)
                    if cancel_event:
                        cancel_event.set()
                except Exception as err:  # noqa: BLE001
                    msg = f"Failed to scan repository '{full_name}': {err}"
                    if warnings is not None:
                        with results_lock:
                            warnings.append(msg)
                finally:
                    with results_lock:
                        completed += 1
                        done = completed
                    emit(
                        Stage.DISCOVER,
                        f"Completed {done}/{total_repos} repositories",
                        current=done,
                        total=total_repos,
                    )

        if rate_limit_error:
            raise rate_limit_error[0]

        all_skills.sort(key=lambda s: (s.repo_name or "", s.path))
        return all_skills
    finally:
        if close_client:
            client.close()
