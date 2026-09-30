"""Visual regression walkthrough test capturing 5 key moments."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.visual.conftest import stabilize_page_for_screenshot
from tests.visual.image_diff import VisualDiffResult, compare_images
from tests.visual.report import generate_visual_report

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _find_latest_recording(recordings_dir: Path) -> Path | None:
    webm_files = sorted(
        recordings_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return webm_files[0] if webm_files else None


def test_walkthrough_visual_regression(
    page: Page,
    visual_server: str,
    deterministic_visual_repo: Path,
    visual_paths: dict[str, Path],
    commit_sha: str,
    pytestconfig: pytest.Config,
) -> None:
    """Execute end-to-end walkthrough, capture 5 key moments, and validate against baselines."""
    results: list[VisualDiffResult] = []

    def capture_and_compare(screen_name: str) -> VisualDiffResult:
        actual_path = visual_paths["actual"] / f"{screen_name}.png"
        baseline_path = visual_paths["baselines"] / f"{screen_name}.png"
        diff_path = visual_paths["diffs"] / f"diff_{screen_name}.png"

        stabilize_page_for_screenshot(page)
        page.screenshot(path=str(actual_path))

        tolerance = (
            0.5 if (os.environ.get("GITHUB_ACTIONS") or sys.platform.startswith("linux")) else 25.0
        )
        res = compare_images(
            baseline_path=baseline_path,
            actual_path=actual_path,
            diff_output_path=diff_path,
            tolerance_percent=tolerance,
            pytest_config=pytestconfig,
        )
        results.append(res)
        return res

    # -------------------------------------------------------------
    # MOMENT 1: Initial Dashboard (Landing state, inputs, dark theme)
    # -------------------------------------------------------------
    page.goto(visual_server)
    page.wait_for_selector("#target-input")
    capture_and_compare("01_initial_dashboard")

    # -------------------------------------------------------------
    # MOMENT 2: Light Theme (Toggled light mode styling across UI)
    # -------------------------------------------------------------
    page.click("#theme-toggle")
    page.wait_for_selector('html[data-theme="light"]')
    capture_and_compare("02_light_theme")

    # Revert back to Dark Theme for scan results
    page.click("#theme-toggle")
    page.wait_for_selector('html[data-theme="dark"]')

    # -------------------------------------------------------------
    # MOMENT 3: Scan Completed Results (Summary metrics, origin chips, list)
    # -------------------------------------------------------------
    page.fill("#target-input", str(deterministic_visual_repo))
    page.click("#scan-btn")
    page.locator("#summary-section").wait_for(state="visible", timeout=15000)
    page.locator(".skill-item").first.wait_for(state="visible", timeout=10000)
    capture_and_compare("03_scan_completed_results")

    # -------------------------------------------------------------
    # MOMENT 4: Filtered Results (Search 'memory' and Agent Config chip)
    # -------------------------------------------------------------
    page.fill("#filter-input", "memory")
    page.wait_for_timeout(250)
    page.click("#chip-agent-config")
    capture_and_compare("04_filtered_results")

    # -------------------------------------------------------------
    # MOMENT 5: Similar Skills Panel (Comparison drawer with breakdowns)
    # -------------------------------------------------------------
    page.fill("#filter-input", "")
    page.click("#chip-all")
    page.wait_for_timeout(200)
    page.click("#similar-btn")
    page.locator("#similar-section").wait_for(state="visible", timeout=5000)
    page.select_option("#similar-threshold", "0.3")
    page.locator("#similar-list > div").first.wait_for(state="visible", timeout=5000)
    capture_and_compare("05_similar_skills_panel")

    # -------------------------------------------------------------
    # MOMENT 6: Skill Map Panel (Clustered view, method switch)
    # -------------------------------------------------------------
    page.click("#map-btn")
    page.locator("#map-section").wait_for(state="visible", timeout=5000)
    page.locator(".map-cluster-card").first.wait_for(state="visible", timeout=5000)
    capture_and_compare("06_skill_map_panel")

    # Allow browser context to flush and finalize video recording
    video_dest = visual_paths["recordings"] / "video_walkthrough.webm"
    try:
        page.context.close()
        latest_rec = _find_latest_recording(visual_paths["recordings"])
        if latest_rec and latest_rec.resolve() != video_dest.resolve():
            shutil.copy2(latest_rec, video_dest)
    except (OSError, RuntimeError):
        pass

    # Generate HTML summary report
    report_file = visual_paths["artifacts"] / "report.html"
    generate_visual_report(
        results=results,
        report_path=report_file,
        video_path=video_dest if video_dest.exists() else None,
        commit_sha=commit_sha,
    )

    # Validate that all screens matched baselines
    mismatches = [r for r in results if not r.matched]
    assert not mismatches, (
        f"{len(mismatches)} visual regression(s) detected:\n"
        + "\n".join(f"- {r.actual_path.stem}: {r.message}" for r in mismatches)
        + "\n\nIf these visual changes are intentional, update baselines with:\n"
        + "  UPDATE_BASELINES=1 uv run pytest tests/visual\n"
        + "or:\n"
        + "  uv run pytest tests/visual --update-baselines"
    )
