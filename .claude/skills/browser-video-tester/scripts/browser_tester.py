"""Browser testing automation harness with video recording and human-like interaction.

Inspired by video-use (https://github.com/browser-use/video-use).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Response, sync_playwright

logger = logging.getLogger("browser_video_tester")

# Visual mouse cursor and action banner injected into the page DOM
CURSOR_INJECTION_JS = """
(() => {
  if (window.__qa_cursor_injected) return;
  window.__qa_cursor_injected = true;

  // Visual mouse cursor
  const cursor = document.createElement('div');
  cursor.id = '__qa_mouse_pointer';
  cursor.style.position = 'fixed';
  cursor.style.top = '0';
  cursor.style.left = '0';
  cursor.style.width = '24px';
  cursor.style.height = '24px';
  cursor.style.borderRadius = '50%';
  cursor.style.backgroundColor = 'rgba(239, 68, 68, 0.85)';
  cursor.style.border = '2px solid #ffffff';
  cursor.style.boxShadow = '0 0 12px rgba(0, 0, 0, 0.6)';
  cursor.style.pointerEvents = 'none';
  cursor.style.zIndex = '2147483647';
  cursor.style.transition = 'transform 0.08s ease-out, background-color 0.15s ease, width 0.15s, height 0.15s';
  cursor.style.transform = 'translate(-50px, -50px)';
  document.body.appendChild(cursor);

  // Ripple effect container
  const ripple = document.createElement('div');
  ripple.id = '__qa_click_ripple';
  ripple.style.position = 'fixed';
  ripple.style.top = '0';
  ripple.style.left = '0';
  ripple.style.width = '10px';
  ripple.style.height = '10px';
  ripple.style.borderRadius = '50%';
  ripple.style.border = '2px solid rgba(16, 185, 129, 0.9)';
  ripple.style.pointerEvents = 'none';
  ripple.style.zIndex = '2147483646';
  ripple.style.opacity = '0';
  ripple.style.transition = 'all 0.4s ease-out';
  document.body.appendChild(ripple);

  window.addEventListener('mousemove', (e) => {
    cursor.style.transform = `translate(${e.clientX - 12}px, ${e.clientY - 12}px)`;
  });

  window.addEventListener('mousedown', (e) => {
    cursor.style.backgroundColor = 'rgba(16, 185, 129, 0.95)';
    cursor.style.transform = `translate(${e.clientX - 12}px, ${e.clientY - 12}px) scale(0.85)`;

    ripple.style.transition = 'none';
    ripple.style.opacity = '1';
    ripple.style.width = '10px';
    ripple.style.height = '10px';
    ripple.style.transform = `translate(${e.clientX - 5}px, ${e.clientY - 5}px)`;

    requestAnimationFrame(() => {
      ripple.style.transition = 'all 0.35s ease-out';
      ripple.style.opacity = '0';
      ripple.style.width = '44px';
      ripple.style.height = '44px';
      ripple.style.transform = `translate(${e.clientX - 22}px, ${e.clientY - 22}px)`;
    });
  });

  window.addEventListener('mouseup', (e) => {
    cursor.style.backgroundColor = 'rgba(239, 68, 68, 0.85)';
    cursor.style.transform = `translate(${e.clientX - 12}px, ${e.clientY - 12}px) scale(1)`;
  });

  // Action banner overlay
  const banner = document.createElement('div');
  banner.id = '__qa_action_banner';
  banner.style.position = 'fixed';
  banner.style.bottom = '20px';
  banner.style.right = '20px';
  banner.style.padding = '8px 16px';
  banner.style.borderRadius = '8px';
  banner.style.backgroundColor = 'rgba(15, 23, 42, 0.9)';
  banner.style.color = '#f8fafc';
  banner.style.border = '1px solid rgba(255, 255, 255, 0.2)';
  banner.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.4)';
  banner.style.fontFamily = 'system-ui, -apple-system, sans-serif';
  banner.style.fontSize = '13px';
  banner.style.fontWeight = '500';
  banner.style.zIndex = '2147483645';
  banner.style.display = 'flex';
  banner.style.alignItems = 'center';
  banner.style.gap = '8px';
  banner.style.backdropFilter = 'blur(8px)';
  banner.style.transition = 'all 0.2s ease';
  banner.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#10b981;"></span><span id="__qa_banner_text">QA Live Tester Active</span>';
  document.body.appendChild(banner);
})();
"""


class BrowserTester:
    """Automated human-like QA browser tester with live video recording."""

    def __init__(
        self,
        url: str | None = None,
        output_dir: str | Path | None = None,
        width: int = 1280,
        height: int = 720,
        headless: bool = True,
    ) -> None:
        self.url = url
        self.width = width
        self.height = height
        self.headless = headless

        ts = time.strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(output_dir or f"artifacts/browser_tests/run_{ts}").resolve()
        self.screenshots_dir = self.output_dir / "screenshots"
        self.video_raw_dir = self.output_dir / "raw_video"

        self.playwright: Any = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

        self.step_counter = 0
        self.current_mouse_x = width // 2
        self.current_mouse_y = height // 2

        self.timeline: list[dict[str, Any]] = []
        self.console_errors: list[str] = []
        self.network_errors: list[str] = []
        self.start_time = 0.0

    def __enter__(self) -> BrowserTester:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.finish()

    def start(self) -> None:
        """Initialize browser and start video recording."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.video_raw_dir.mkdir(parents=True, exist_ok=True)
        self.start_time = time.time()

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-gpu"],
        )
        self.context = self.browser.new_context(
            viewport={"width": self.width, "height": self.height},
            record_video_dir=str(self.video_raw_dir),
            record_video_size={"width": self.width, "height": self.height},
        )
        self.page = self.context.new_page()

        # Capture console errors and uncaught exceptions
        def _on_console(msg: Any) -> None:
            if msg.type == "error":
                text = msg.text
                if not any(
                    ign in text
                    for ign in ["favicon.ico", "DevTools failed", "Download the Vue Devtools"]
                ):
                    self.console_errors.append(text)

        def _on_response(res: Response) -> None:
            if res.status >= 400:
                url = res.url
                if "favicon.ico" not in url:
                    self.network_errors.append(f"{res.status} {res.request.method} {url}")

        self.page.on("console", _on_console)
        self.page.on("response", _on_response)

        if self.url:
            self.navigate(self.url)

    def _inject_helpers(self) -> None:
        """Inject visual cursor and banner overlay into the current page."""
        if not self.page:
            return
        with contextlib.suppress(Exception):
            self.page.evaluate(CURSOR_INJECTION_JS)

    def navigate(self, url: str) -> None:
        """Navigate to URL and inject visual overlay."""
        if not self.page:
            raise RuntimeError("Browser not started")
        self.page.goto(url, wait_until="networkidle")
        time.sleep(0.3)
        self._inject_helpers()
        self.human_move(self.width // 2, self.height // 2)

    def step(self, title: str, pause: float = 0.4) -> None:
        """Record a test step, update on-screen subtitle banner, and capture screenshot."""
        if not self.page:
            raise RuntimeError("Browser not started")
        self.step_counter += 1
        elapsed = round(time.time() - self.start_time, 2)
        step_entry = {
            "step": self.step_counter,
            "title": title,
            "timestamp": elapsed,
        }
        self.timeline.append(step_entry)
        logger.info(f"[Step {self.step_counter}] ({elapsed}s) {title}")

        # Update visual banner on screen
        with contextlib.suppress(Exception):
            safe_title = json.dumps(f"Step {self.step_counter}: {title}")
            self.page.evaluate(f"""(() => {{
                const el = document.getElementById('__qa_banner_text');
                if (el) el.textContent = {safe_title};
            }})()""")

        time.sleep(pause)
        clean_title = re.sub(r"[^a-zA-Z0-9_\-]+", "_", title.lower())[:30]
        self.screenshot(f"step_{self.step_counter:02d}_{clean_title}")

    def human_move(self, target_x: int, target_y: int, steps: int = 8) -> None:
        """Move cursor smoothly with interpolation."""
        if not self.page:
            return
        start_x = self.current_mouse_x
        start_y = self.current_mouse_y

        for i in range(1, steps + 1):
            fraction = i / steps
            # Smooth quadratic easing
            eased = fraction * fraction * (3.0 - 2.0 * fraction)
            cx = int(start_x + (target_x - start_x) * eased)
            cy = int(start_y + (target_y - start_y) * eased)
            self.page.mouse.move(cx, cy)
            time.sleep(0.015)

        self.current_mouse_x = target_x
        self.current_mouse_y = target_y

    def human_click(self, selector: str, pause_after: float = 0.4) -> None:
        """Move cursor to element, click with visual ripple, and pause realistically."""
        if not self.page:
            raise RuntimeError("Browser not started")
        locator = self.page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=8000)
        time.sleep(0.1)

        box = locator.bounding_box()
        if not box:
            locator.click()
            time.sleep(pause_after)
            return

        target_x = int(box["x"] + box["width"] / 2)
        target_y = int(box["y"] + box["height"] / 2)

        self.human_move(target_x, target_y)
        time.sleep(0.1)
        self.page.mouse.down()
        time.sleep(0.08)
        self.page.mouse.up()
        time.sleep(pause_after)

    def human_type(
        self,
        selector: str,
        text: str,
        clear: bool = True,
        delay_per_char: float = 0.04,
        pause_after: float = 0.3,
    ) -> None:
        """Click input field and type characters with human cadence."""
        if not self.page:
            raise RuntimeError("Browser not started")
        self.human_click(selector, pause_after=0.1)
        if clear:
            self.page.keyboard.press("Meta+A")
            self.page.keyboard.press("Backspace")
            time.sleep(0.1)

        for char in text:
            self.page.keyboard.type(char)
            time.sleep(delay_per_char)

        time.sleep(pause_after)

    def human_select(self, selector: str, value: str, pause_after: float = 0.4) -> None:
        """Select an option from a dropdown with visual focus."""
        if not self.page:
            raise RuntimeError("Browser not started")
        self.human_click(selector, pause_after=0.2)
        self.page.select_option(selector, value)
        time.sleep(pause_after)

    def human_scroll(self, delta_y: int = 300, steps: int = 6) -> None:
        """Scroll the page smoothly."""
        if not self.page:
            return
        step_delta = delta_y / steps
        for _ in range(steps):
            self.page.mouse.wheel(0, step_delta)
            time.sleep(0.03)
        time.sleep(0.2)

    def screenshot(self, name: str) -> Path:
        """Capture a keyframe screenshot."""
        if not self.page:
            raise RuntimeError("Browser not started")
        path = self.screenshots_dir / f"{name}.png"
        self.page.screenshot(path=str(path))
        return path

    def finish(self) -> dict[str, Any]:
        """Close browser, encode video to MP4, and generate test reports."""
        raw_video_path: Path | None = None
        if self.page:
            with contextlib.suppress(Exception):
                v = self.page.video
                if v:
                    raw_video_path = Path(v.path())

        if self.context:
            with contextlib.suppress(Exception):
                self.context.close()
        if self.browser:
            with contextlib.suppress(Exception):
                self.browser.close()
        if self.playwright:
            with contextlib.suppress(Exception):
                self.playwright.stop()

        mp4_path = self.output_dir / "test_session.mp4"
        converted = False

        # Convert webm video to mp4 via ffmpeg
        ffmpeg_bin = shutil.which("ffmpeg") or "/Users/Aleksandr.Avdiushenko/.local/bin/ffmpeg"
        if raw_video_path and raw_video_path.exists() and os.path.exists(ffmpeg_bin):
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                str(raw_video_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "fast",
                "-crf",
                "22",
                str(mp4_path),
            ]
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if res.returncode == 0 and mp4_path.exists():
                    converted = True
            except (subprocess.SubprocessError, OSError) as err:
                logger.warning(f"FFmpeg conversion failed: {err}")

        final_video_path = mp4_path if converted else raw_video_path

        # Write timeline.json
        timeline_path = self.output_dir / "timeline.json"
        timeline_data = {
            "duration_seconds": round(time.time() - self.start_time, 2),
            "steps": self.timeline,
            "console_errors": self.console_errors,
            "network_errors": self.network_errors,
            "video_path": str(final_video_path) if final_video_path else None,
        }
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline_data, f, indent=2)

        # Write report.md
        report_path = self.output_dir / "report.md"
        self._write_report(report_path, timeline_data)

        return timeline_data

    def _write_report(self, report_path: Path, data: dict[str, Any]) -> None:
        """Write human-readable markdown test summary."""
        video_rel = (
            "test_session.mp4" if (self.output_dir / "test_session.mp4").exists() else "video"
        )
        status = "PASSED" if not data["console_errors"] and not data["network_errors"] else "FAILED"

        lines = [
            "# QA Browser Testing Session Report",
            "",
            f"**Status**: `{status}`  ",
            f"**Duration**: {data['duration_seconds']}s  ",
            f"**Video Recording**: `{video_rel}`  ",
            "",
            "## Executed Steps Timeline",
            "",
            "| Step | Timestamp | Action Description |",
            "|---|---|---|",
        ]
        for s in data["steps"]:
            lines.append(f"| {s['step']} | {s['timestamp']}s | {s['title']} |")

        lines.extend(
            [
                "",
                "## Quality & Error Audit",
                "",
                f"- **Console JavaScript Errors**: {len(data['console_errors'])}",
            ]
        )
        for err in data["console_errors"]:
            lines.append(f"  - `[JS Error]` {err}")

        lines.append(f"- **HTTP Network Errors (4xx/5xx)**: {len(data['network_errors'])}")
        for err in data["network_errors"]:
            lines.append(f"  - `[HTTP Error]` {err}")

        lines.extend(
            [
                "",
                "## Captured Keyframes",
                "",
            ]
        )
        for img in sorted(self.screenshots_dir.glob("*.png")):
            lines.append(f"- **{img.stem}**: `screenshots/{img.name}`")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
