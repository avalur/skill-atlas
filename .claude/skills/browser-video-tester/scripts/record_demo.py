"""Automated narrated demo video recording for Skill Atlas.

Walks through the current Web UI with a female voice-over:
1. Landing page and light/dark theme switch
2. Multi-repository targets (cursor/plugins and avalur/skill-atlas)
3. Live scan via the GitHub API with the status bar reporting each step (time-lapsed)
4. Results: repository chips, origin chips, status filter, keyword search
5. Heuristic similarity discovery and the Skill Map
Then mixes narration with quiet, ducked background music and renders MP4, GIF and a
poster thumbnail into docs/assets/ for the README.

Every narration line is synthesized before the browser starts, and each step waits for
its line to finish, so speech and on-screen actions stay in sync.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from .browser_tester import BrowserTester
    from .generate_music import generate_music_track
    from .narration import Narrator, VoiceClip, ffmpeg_bin, media_duration, render_with_voiceover
except ImportError:
    from browser_tester import BrowserTester
    from generate_music import generate_music_track
    from narration import Narrator, VoiceClip, ffmpeg_bin, media_duration, render_with_voiceover

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("record_demo")

DEMO_TARGETS = ("https://github.com/cursor/plugins", "https://github.com/avalur/skill-atlas")

SCRIPT: dict[str, str] = {
    "intro": (
        "This is Skill Atlas. It finds AI agent skills in your repositories, "
        "and checks them for broken structure and security risks."
    ),
    "theme": "It follows your system theme, and one click switches between light and dark.",
    "targets": (
        "You can scan several repositories at once. Let's take two public ones: "
        "Cursor's plugin collection, and the Skill Atlas repository itself."
    ),
    "scan": (
        "Press Scan. Nothing gets cloned. Skill Atlas reads each repository through the "
        "GitHub API, and the status bar at the bottom tells you what it is doing right now."
    ),
    # "results" is generated after the scan from the real summary numbers.
    "repo": (
        "Repository chips narrow the list down to one source, "
        "and the status filter keeps only the skills that failed the audit."
    ),
    "origin": (
        "Skills are also grouped by origin. Test data are fixtures broken on purpose, "
        "so they never fail your build."
    ),
    "search": "Search filters instantly. Type secret, and you get the fixture that leaks credentials.",
    "reset": "Clear the filters to bring the whole catalog back.",
    "similar": (
        "Find Similar compares skills with simple, transparent heuristics. "
        "No AI is involved, and every match comes with its reasons."
    ),
    "map": "The Skill Map groups related skills into themes, so a large catalog is easier to read.",
    "outro": "That's Skill Atlas: discovery, audit and provenance for agent skills, in one local tool.",
}


class NarratedSession:
    """Pairs on-screen steps with pre-synthesized voice-over clips."""

    def __init__(self, tester: BrowserTester, clips: dict[str, VoiceClip]) -> None:
        self.tester = tester
        self.clips = clips
        self.placed: list[VoiceClip] = []

    def say(
        self,
        key: str,
        banner: str,
        action: Callable[[], None] | None = None,
        tail: float = 0.5,
    ) -> None:
        """Show the banner, start the voice line, run the action, and wait for the line to end."""
        clip = self.clips[key]
        clip.start = time.time() - self.tester.start_time
        self.placed.append(clip)
        line_end = time.time() + clip.duration
        self.tester.step(banner, pause=0.0)
        if action:
            action()
        remaining = line_end - time.time()
        time.sleep(max(0.0, remaining) + tail)


def _scroll_to(tester: BrowserTester, selector: str) -> None:
    tester.page.evaluate(
        "sel => { const el = document.querySelector(sel);"
        " window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - 16,"
        " behavior: 'smooth'}); }",
        selector,
    )
    time.sleep(0.9)


def _clear_input(tester: BrowserTester, selector: str) -> None:
    tester.human_click(selector, pause_after=0.1)
    tester.page.keyboard.press("ControlOrMeta+A")
    tester.page.keyboard.press("Backspace")
    tester.page.dispatch_event(selector, "input")


def record_demo(
    url: str = "http://127.0.0.1:8765",
    output_dir: Path | str = "artifacts/demo_run",
    assets_dir: Path | str = "docs/assets",
    music: bool = True,
) -> int:
    out_dir = Path(output_dir).resolve()
    docs_assets_dir = Path(assets_dir).resolve()
    docs_assets_dir.mkdir(parents=True, exist_ok=True)

    narrator = Narrator(out_dir / "voice")
    logger.info(f"Synthesizing narration with {narrator.engine}...")
    clips = {key: narrator.synthesize(text) for key, text in SCRIPT.items()}

    with BrowserTester(
        url=url, output_dir=out_dir, width=1280, height=720, headless=True
    ) as tester:
        page = tester.page
        session = NarratedSession(tester, clips)

        session.say(
            "intro",
            "Skill Atlas: discovery and security audit for AI agent skills",
            action=lambda: tester.human_move(tester.width // 2, 200),
        )

        def switch_to_dark() -> None:
            time.sleep(1.2)
            tester.human_click("#theme-toggle", pause_after=0.4)

        session.say("theme", "Light and dark themes", action=switch_to_dark)

        def enter_targets() -> None:
            time.sleep(1.5)
            tester.human_type("#target-input", "\n".join(DEMO_TARGETS), clear=True)

        session.say("targets", "Scan several repositories at once", action=enter_targets)

        def start_scan() -> None:
            time.sleep(0.6)
            tester.human_click("#scan-btn", pause_after=0.2)
            tester.human_move(tester.width // 2, tester.height - 30)

        session.say(
            "scan", "Live scan through the GitHub API, no cloning", action=start_scan, tail=0
        )
        logger.info("Waiting for the scan to finish (time-lapsed in the final video)...")
        lapse_start = time.time() - tester.start_time
        tester.step("Time-lapse: scanning through the GitHub API", pause=0.0)
        page.locator("#summary-section").wait_for(state="visible", timeout=600000)
        lapse_end = time.time() - tester.start_time
        time.sleep(0.8)

        # Narrate the real numbers from the finished scan.
        total = page.evaluate("scanResult.summary.total_skills")
        repos = page.evaluate("new Set(scanResult.skills.map(s => s.repo_name)).size")
        findings = page.evaluate(
            "Object.values(scanResult.summary.findings_count).reduce((a, b) => a + b, 0)"
        )
        repo_word = "repository" if repos == 1 else "repositories"
        clips["results"] = narrator.synthesize(
            f"Done. {total} skills from {repos} {repo_word}, with {findings} findings. "
            "Every card shows where the skill lives, when it was first committed, "
            "and what the audit found."
        )
        session.say(
            "results",
            f"{total} skills audited",
            action=lambda: tester.human_move(tester.width // 2, 330),
        )

        def repo_and_status() -> None:
            tester.human_click('#repo-chips .chip:has-text("cursor/plugins")', pause_after=2.2)
            tester.human_select("#status-filter-select", "fail", pause_after=0.3)

        session.say("repo", "Repository and status filters", action=repo_and_status)

        def origin_filter() -> None:
            tester.human_select("#status-filter-select", "all", pause_after=0.3)
            tester.human_click("#chip-repo-all", pause_after=0.4)
            tester.human_click("#chip-test-data", pause_after=0.3)

        session.say("origin", "Origin filter: test data never blocks CI", action=origin_filter)

        def search_secret() -> None:
            time.sleep(1.2)
            tester.human_type("#filter-input", "secret", clear=True, delay_per_char=0.09)

        session.say("search", "Instant keyword search", action=search_secret)

        def reset_filters() -> None:
            _clear_input(tester, "#filter-input")
            tester.human_select("#status-filter-select", "all", pause_after=0.2)
            tester.human_click("#chip-all", pause_after=0.2)
            tester.human_click("#chip-repo-all", pause_after=0.2)

        session.say("reset", "Back to the full catalog", action=reset_filters)

        def open_similar() -> None:
            tester.human_click("#similar-btn", pause_after=0.6)
            page.locator("#similar-section").wait_for(state="visible", timeout=60000)
            tester.human_select("#similar-threshold", "0.4", pause_after=0.6)
            _scroll_to(tester, "#similar-section")

        session.say("similar", "Find Similar: heuristic, explainable matches", action=open_similar)

        def open_map() -> None:
            tester.human_click("#map-btn", pause_after=0.6)
            page.locator("#map-section").wait_for(state="visible", timeout=60000)
            _scroll_to(tester, "#map-section")

        session.say("map", "Skill Map: related skills grouped by theme", action=open_map)

        def back_to_top() -> None:
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

        session.say(
            "outro", "Skill Atlas: discovery, audit, provenance", action=back_to_top, tail=1.2
        )
        session_end = time.time() - tester.start_time
        placed = list(session.placed)

    raw_video_files = sorted(
        (out_dir / "raw_video").glob("*.webm"), key=lambda p: p.stat().st_mtime
    )
    if not raw_video_files:
        logger.error("No raw video found")
        return 1
    input_webm = raw_video_files[-1]

    # The recording starts when the page is created, slightly after tester.start_time.
    video_len = media_duration(input_webm)
    offset = max(0.0, session_end - video_len)
    for clip in placed:
        clip.start -= offset
    lapse = (lapse_start - offset, lapse_end - offset)
    trim_start = max(0.0, placed[0].start - 0.4)

    music_wav: Path | None = None
    if music:
        music_wav = out_dir / "background_music.wav"
        generate_music_track(music_wav, duration_sec=video_len + 2.0)

    demo_mp4 = docs_assets_dir / "demo.mp4"
    logger.info(f"Rendering narrated MP4 to {demo_mp4}...")
    saved = render_with_voiceover(
        input_webm, demo_mp4, placed, trim_start=trim_start, music_wav=music_wav, timelapse=lapse
    )

    demo_gif = docs_assets_dir / "demo.gif"
    logger.info(f"Rendering README GIF preview to {demo_gif}...")
    gif_filter = (
        "setpts=PTS/1.5,fps=10,scale=800:-1:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=max_colors=96:stats_mode=diff[p];"
        "[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    )
    res_gif = subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(demo_mp4),
            "-an",
            "-vf",
            gif_filter,
            "-loop",
            "0",
            str(demo_gif),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res_gif.returncode != 0:
        logger.error(f"FFmpeg GIF render failed: {res_gif.stderr[-2000:]}")
        return 1

    thumb_png = docs_assets_dir / "demo-thumbnail.png"
    results_clip = clips["results"]
    capture_time = max(0.0, results_clip.start - trim_start - saved + 1.5)
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{capture_time:.2f}",
            "-i",
            str(demo_mp4),
            "-vframes",
            "1",
            str(thumb_png),
        ],
        capture_output=True,
        check=False,
    )

    duration = media_duration(demo_mp4)
    print("\n" + "=" * 70)
    print("🎬 NARRATED DEMO GENERATED")
    print("=" * 70)
    print(f"  • Voice engine:  {narrator.engine}")
    print(
        f"  • Video (MP4):   {demo_mp4} ({demo_mp4.stat().st_size / 1048576:.2f} MB, {duration:.1f}s)"
    )
    print(f"  • README GIF:    {demo_gif} ({demo_gif.stat().st_size / 1048576:.2f} MB)")
    print(f"  • Thumbnail:     {thumb_png}")
    print("=" * 70 + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", default="artifacts/demo_run")
    parser.add_argument("--assets-dir", default="docs/assets")
    parser.add_argument("--no-music", action="store_true", help="Voice-over only")
    args = parser.parse_args()
    return record_demo(
        url=args.url,
        output_dir=args.output_dir,
        assets_dir=args.assets_dir,
        music=not args.no_music,
    )


if __name__ == "__main__":
    sys.exit(main())
