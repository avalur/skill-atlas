"""Live QA testing runner for Skill Atlas Web UI with video recording.

Executes a complete human-like walkthrough of the Web UI, testing buttons,
theme toggle, scan inputs, filters, and similar skills discovery.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

try:
    from .browser_tester import BrowserTester
except ImportError:
    from browser_tester import BrowserTester

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_web_audit")


def run_audit(
    url: str = "http://127.0.0.1:8765",
    target: str = "https://github.com/JetBrains/kotlin",
    headless: bool = True,
) -> int:
    """Run comprehensive browser audit on Skill Atlas web interface."""
    logger.info(
        f"Starting Live QA Browser Audit for {url} with target {target} (headless={headless})..."
    )

    with BrowserTester(url=url, headless=headless) as tester:
        # Step 1: Initial page load & health
        tester.step("Page Load & Initial State Verification", pause=0.6)
        tester.human_move(tester.width // 2, 220)

        # Step 2: Test Light Theme Toggle
        tester.step("Toggle Light Theme", pause=0.5)
        tester.human_click("#theme-toggle", pause_after=0.7)

        # Step 3: Test Dark Theme Toggle back
        tester.step("Toggle Dark Theme", pause=0.5)
        tester.human_click("#theme-toggle", pause_after=0.7)

        # Step 4: Enter Scan Target
        tester.step(f"Enter Scan Target: {target}", pause=0.4)
        tester.human_type("#target-input", target, clear=True)

        # Step 5: Click Scan Button
        tester.step("Trigger Scan Execution", pause=0.4)
        tester.human_click("#scan-btn", pause_after=0.8)

        # Wait for scan results to render
        logger.info("Waiting for scan summary to appear...")
        tester.page.locator("#summary-section").wait_for(state="visible", timeout=25000)
        tester.step("Scan Completed: Summary & Skills Rendered", pause=0.8)

        # Step 6: Filter by search keyword
        tester.step("Search Keyword Filter: gradle", pause=0.5)
        tester.human_type("#filter-input", "gradle", clear=True)
        tester.step("Keyword Filter Applied (Showing Gradle Skills)", pause=0.7)

        # Step 7: Clear search filter
        tester.step("Clear Search Filter", pause=0.4)
        tester.human_click("#filter-input")
        tester.page.keyboard.press("Meta+A")
        tester.page.keyboard.press("Backspace")
        time.sleep(0.4)
        tester.step("Search Filter Cleared (All Skills Shown)", pause=0.5)

        # Step 8: Test Status Filter (Passed / Failed / All)
        tester.step("Filter Status: Passed Only", pause=0.4)
        tester.human_select("#status-filter-select", "pass")
        tester.step("Filter Status: All", pause=0.4)
        tester.human_select("#status-filter-select", "all")

        # Step 9: Test Origin Chips Filters
        tester.step("Filter Origin Chip: Agent Config", pause=0.4)
        tester.human_click("#chip-agent-config", pause_after=0.6)
        tester.step("Filter Origin Chip: All", pause=0.4)
        tester.human_click("#chip-all", pause_after=0.6)

        # Step 10: Test Similar Skills Panel
        tester.step("Open Similar Skills Panel", pause=0.4)
        tester.human_click("#similar-btn", pause_after=0.8)
        tester.page.locator("#similar-section").wait_for(state="visible", timeout=5000)

        tester.step("Select Similarity Threshold: 0.3", pause=0.4)
        tester.human_select("#similar-threshold", "0.3")
        tester.step("Inspect Similar Skills Matches", pause=0.8)

        # Step 11: Scroll to inspect skills list cards
        tester.step("Smooth Scroll Down to Cards", pause=0.4)
        tester.human_scroll(delta_y=400, steps=8)
        tester.step("Smooth Scroll Up to Navigation", pause=0.4)
        tester.human_scroll(delta_y=-400, steps=8)

        # Step 12: Concluding session
        tester.step("Live QA Audit Completed Successfully", pause=0.8)

    logger.info(f"Audit completed. Artifacts generated in: {tester.output_dir}")
    print(f"\n[SUCCESS] Test report and video recording saved to:\n  {tester.output_dir}")
    print(f"  - Video: {tester.output_dir}/test_session.mp4")
    print(f"  - Report: {tester.output_dir}/report.md")

    if tester.console_errors or tester.network_errors:
        logger.warning(
            f"Audit finished with {len(tester.console_errors)} console errors "
            f"and {len(tester.network_errors)} network errors"
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live QA browser audit with video recording")
    parser.add_argument("--url", default="http://127.0.0.1:8765", help="Target Web UI URL")
    parser.add_argument(
        "--target",
        default="https://github.com/JetBrains/kotlin",
        help="Repository URL or folder path to scan",
    )
    parser.add_argument(
        "--headed", action="store_true", help="Run browser in headed (visible) mode"
    )
    args = parser.parse_args()

    sys.exit(run_audit(url=args.url, target=args.target, headless=not args.headed))


if __name__ == "__main__":
    main()
