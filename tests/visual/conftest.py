"""Pytest configuration and fixtures for visual regression testing."""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
import uvicorn
from playwright.sync_api import Browser, BrowserContext, Error, Page, sync_playwright

from skill_atlas.web import create_app
from tests.conftest import CommitDef, make_repo
from tests.visual.failures import clear_visual_failures, load_visual_failures

if TYPE_CHECKING:
    from collections.abc import Generator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINES_DIR = Path(__file__).resolve().parent / "baselines"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "visual"
RECORDINGS_DIR = ARTIFACTS_DIR / "recordings"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options for visual testing."""
    parser.addoption(
        "--update-baselines",
        action="store_true",
        default=False,
        help="Update golden visual baseline screenshots instead of comparing.",
    )


def get_git_commit_sha() -> str:
    """Resolve the current Git commit SHA or fallback to environment / local."""
    env_sha = os.environ.get("GITHUB_SHA")
    if env_sha:
        return env_sha[:8]
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = res.stdout.strip()
        if sha:
            return sha
    except (subprocess.SubprocessError, OSError):
        return "local"
    return "local"


@pytest.fixture(scope="session")
def commit_sha() -> str:
    return get_git_commit_sha()


@pytest.fixture(scope="session")
def visual_paths(commit_sha: str) -> dict[str, Path]:
    """Provide standard directories for visual testing artifacts and baselines."""
    actual_dir = ARTIFACTS_DIR / commit_sha
    diffs_dir = ARTIFACTS_DIR / "diffs"
    failures_file = ARTIFACTS_DIR / "failures.json"

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    actual_dir.mkdir(parents=True, exist_ok=True)
    diffs_dir.mkdir(parents=True, exist_ok=True)

    clear_visual_failures(failures_file)

    return {
        "baselines": BASELINES_DIR,
        "artifacts": ARTIFACTS_DIR,
        "recordings": RECORDINGS_DIR,
        "actual": actual_dir,
        "diffs": diffs_dir,
        "failures": failures_file,
    }


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, None, None]:
    """Record any unexpected visual test failure into failures.json for CI reporting."""
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        file_path = Path(item.location[0])
        if "visual" in file_path.parts:
            failures_file = ARTIFACTS_DIR / "failures.json"
            current = load_visual_failures(failures_file)
            title = item.name
            if not any(entry.get("title") == title for entry in current):
                err_msg = str(call.excinfo.value) if call.excinfo else rep.longreprtext
                current.append(
                    {
                        "file": file_path.as_posix(),
                        "line": item.location[1] + 1,
                        "title": title,
                        "errors": [err_msg],
                        "snapshots": [],
                    }
                )
                failures_file.parent.mkdir(parents=True, exist_ok=True)
                import json

                failures_file.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="session")
def deterministic_visual_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a fully deterministic Git repository with fixed commits from visual_repo fixture."""
    repo_dir = tmp_path_factory.mktemp("visual_repo_git")
    fixture_src = Path(__file__).resolve().parent.parent / "fixtures" / "visual_repo"

    tree: dict[str, str] = {}
    for p in fixture_src.rglob("*"):
        if p.is_file():
            rel = str(p.relative_to(fixture_src))
            tree[rel] = p.read_text(encoding="utf-8")

    commits = [
        CommitDef(
            message="feat: initial agent skills and security tools",
            files=tree,
            date="2026-09-01T10:00:00Z",
            author="Skill Atlas Agent <agent@example.com>",
        ),
    ]

    repo = make_repo(repo_dir, commits=commits)
    subprocess.run(
        ["git", "config", "remote.origin.url", "https://github.com/acme/core-skills.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture(scope="session")
def deterministic_visual_second_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a second deterministic Git repository for multi-repo visual testing."""
    repo_dir = tmp_path_factory.mktemp("visual_repo_secondary")
    tree = {
        ".claude/skills/deploy-helper/SKILL.md": (
            "---\nname: deploy-helper\ndescription: Multi-cloud automated deployment skill.\n---\n# Deploy\n"
        ),
        ".claude/skills/infra-monitor/SKILL.md": (
            "---\nname: infra-monitor\ndescription: Infrastructure telemetry and health checks.\n---\n# Telemetry\n"
        ),
    }
    commits = [
        CommitDef(
            message="feat: add cloud deployment and infrastructure skills",
            files=tree,
            date="2026-09-02T10:00:00Z",
            author="Skill Atlas Agent <agent@example.com>",
        ),
    ]
    repo = make_repo(repo_dir, commits=commits)
    subprocess.run(
        ["git", "config", "remote.origin.url", "https://github.com/acme/infra-skills.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def visual_server(deterministic_visual_repo: Path) -> Generator[str, None, None]:
    """Spin up local FastAPI server pointing to the deterministic repository fixture."""
    port = _find_free_port()
    app = create_app(allow_local=True, port=port)
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    start_time = time.time()
    healthy = False
    while time.time() - start_time < 5.0:
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=1.0)
            if resp.status_code == 200:
                healthy = True
                break
        except (httpx.HTTPError, OSError):
            time.sleep(0.05)

    if not healthy:
        server.should_exit = True
        thread.join(timeout=2.0)
        raise RuntimeError(f"Visual test server failed to start within 5s on {base_url}")

    yield base_url

    server.should_exit = True
    thread.join(timeout=2.0)


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    """Launch headless Chromium browser instance."""
    playwright_ctx = sync_playwright()
    try:
        p = playwright_ctx.start()
        b = p.chromium.launch(
            headless=True,
            args=[
                "--font-render-hinting=none",
                "--disable-skia-runtime-opts",
                "--disable-font-subpixel-positioning",
            ],
        )
    except (Error, OSError) as e:
        pytest.skip(f"Playwright Chromium browser not available: {e}")
        return

    yield b
    b.close()
    p.stop()


@pytest.fixture
def page(browser: Browser, visual_paths: dict[str, Path]) -> Generator[Page, None, None]:
    """Create deterministic browser page context with fixed viewport and video recording."""
    context: BrowserContext = browser.new_context(
        viewport={"width": 1280, "height": 720},
        device_scale_factor=1,
        color_scheme="dark",
        reduced_motion="reduce",
        record_video_dir=str(visual_paths["recordings"]),
        record_video_size={"width": 1280, "height": 720},
    )

    p: Page = context.new_page()

    # Suppress blinking cursors and dynamic scrollbars
    p.add_init_script(
        """
        const style = document.createElement('style');
        style.innerHTML = `
            *, *::before, *::after {
                animation-duration: 0s !important;
                animation-delay: 0s !important;
                transition-duration: 0s !important;
                transition-delay: 0s !important;
                caret-color: transparent !important;
            }
        `;
        document.head.appendChild(style);
        """
    )

    yield p

    # Ensure video is finalized on context close
    context.close()


def stabilize_page_for_screenshot(page: Page) -> None:
    """Ensure animations are settled and page is stationary before snapshotting."""
    page.wait_for_load_state("networkidle")
    page.evaluate(
        """() => {
            const el = document.activeElement;
            if (el && el.blur) el.blur();
        }"""
    )
    time.sleep(0.15)
