"""Intentional visual breakage validation test ('Break it').

Verifies that layout distortions, color shifts, and CSS regressions
are reliably detected with non-zero diff scores and visual diff highlight images.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.visual.conftest import stabilize_page_for_screenshot
from tests.visual.image_diff import compare_images

if TYPE_CHECKING:
    from playwright.sync_api import Page


def test_intentional_visual_breakage_detection(
    page: Page,
    visual_server: str,
    visual_paths: dict[str, Path],
    pytestconfig: pytest.Config,
) -> None:
    """Deliberately introduce CSS distortions and assert that diff engine catches them."""
    baseline_path = visual_paths["baselines"] / "01_initial_dashboard.png"
    assert baseline_path.exists(), (
        f"Baseline '{baseline_path}' must exist before running breakage test. "
        "Run `UPDATE_BASELINES=1 uv run pytest tests/visual/test_walkthrough_screens.py` first."
    )

    page.goto(visual_server)
    page.wait_for_selector("#target-input")
    stabilize_page_for_screenshot(page)

    # Inject deliberate visual anomalies: altered accent colors, giant heading, and distorted layout
    page.add_style_tag(
        content="""
        body {
            background: #2b0938 !important;
        }
        h1 {
            font-size: 3.5rem !important;
            color: #ff0055 !important;
            transform: rotate(-4deg) !important;
            margin-bottom: 2rem !important;
        }
        #target-input {
            background: #ffe066 !important;
            color: #000000 !important;
            border: 4px solid #ff0055 !important;
            height: 60px !important;
        }
        #scan-btn {
            background: #00ffaa !important;
            color: #000000 !important;
            font-size: 1.5rem !important;
            padding: 1rem 2.5rem !important;
        }
        """
    )
    stabilize_page_for_screenshot(page)

    broken_screenshot_path = visual_paths["actual"] / "broken_dashboard.png"
    page.screenshot(path=str(broken_screenshot_path))

    diff_output_path = visual_paths["diffs"] / "breakage_diff.png"
    if diff_output_path.exists():
        diff_output_path.unlink()

    # Compare distorted actual screen against golden baseline
    result = compare_images(
        baseline_path=baseline_path,
        actual_path=broken_screenshot_path,
        diff_output_path=diff_output_path,
        tolerance_percent=0.5,
        pytest_config=pytestconfig,
    )

    # 1. Assert regression was detected
    assert result.matched is False, "Visual diff engine must detect the intentional visual breakage"

    # 2. Assert significant mismatch percentage
    assert result.diff_percent > 3.0, (
        f"Expected significant visual regression (>3%), but got {result.diff_percent:.2f}%"
    )
    assert result.diff_pixels > 0

    # 3. Assert highlight diff image was created
    assert diff_output_path.exists(), "Diff highlight image must be generated on regression"
    assert diff_output_path.stat().st_size > 0

    # 4. Assert diagnostic guidance in message
    assert "Visual regression detected" in result.message
    assert "UPDATE_BASELINES=1" in result.message

    # 5. Verify that an assertion expecting a match would fail with actionable guidance
    with pytest.raises(AssertionError) as exc_info:
        assert result.matched, result.message
    assert "UPDATE_BASELINES=1" in str(exc_info.value)
