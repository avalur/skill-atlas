"""Automated demo video recording for Skill Atlas.

Walks through key capabilities in the Web UI:
1. Health & Dual Themes (Light / Dark mode toggle)
2. Scanning GitHub repository (avalur/skill-atlas) with real-time SSE progress
3. Provenance & origin classification (Agent Config, Test Data)
4. Fast keyword filtering (typing 'memory' -> instant filter)
5. Heuristic similarity discovery (composite scores, token overlap, match reasons)
6. Merging upbeat background synthwave music via FFmpeg
7. Generating optimized inline GIF and poster thumbnail for GitHub README.md
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Ensure browser tester and music generator can be imported
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

try:
    from .browser_tester import BrowserTester
    from .generate_music import generate_music_track
except ImportError:
    from browser_tester import BrowserTester
    from generate_music import generate_music_track

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("record_demo")


def record_demo(
    url: str = "http://127.0.0.1:8765",
    target: str = "https://github.com/avalur/skill-atlas",
    output_dir: Path | str = "artifacts/demo_run",
) -> int:
    out_dir = Path(output_dir).resolve()
    docs_assets_dir = Path("docs/assets").resolve()
    docs_assets_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting Demo Video Walkthrough against {url} scanning {target}...")

    with BrowserTester(
        url=url, output_dir=out_dir, width=1280, height=720, headless=True
    ) as tester:
        # Step 1: Initial Page Load & Ready State
        tester.step("⚡ Skill Atlas: Intelligent Agent Skills Security & Discovery", pause=0.8)
        tester.human_move(tester.width // 2, 220)

        # Step 2: Showcase Light Theme
        tester.step("🌓 Dual Theme: Switching to Light Mode", pause=0.6)
        tester.human_click("#theme-toggle", pause_after=1.2)

        # Step 3: Switch back to Dark Theme
        tester.step("🌙 Sleek Dark Mode Interface", pause=0.6)
        tester.human_click("#theme-toggle", pause_after=1.0)

        # Step 4: Enter Scan Target
        tester.step(f"🔍 Scan Target: {target}", pause=0.5)
        tester.human_type("#target-input", target, clear=True)

        # Step 5: Start Scan with Real-Time Progress
        tester.step("🚀 Live Scan via GitHub API (Zero-Clone)", pause=0.5)
        tester.human_click("#scan-btn", pause_after=0.8)

        # Wait for scan to complete and summary to appear
        logger.info("Awaiting scan completion and summary rendering...")
        tester.page.locator("#summary-section").wait_for(state="visible", timeout=45000)
        tester.step("✅ Audit Complete: 19 Skills Discovered & Audited", pause=1.5)

        # Step 6: Filter by Origin (Agent Config)
        tester.step("🏷️ Origin Filter: Agent Config (Production Skills)", pause=0.5)
        tester.human_click("#chip-agent-config", pause_after=1.2)

        # Step 7: Filter by Origin (All)
        tester.step("🏷️ Origin Filter: View All Discovered Skills", pause=0.5)
        tester.human_click("#chip-all", pause_after=1.0)

        # Step 8: Multi-Token Search Filter
        tester.step("🔎 Instant Search Filter: 'memory'", pause=0.5)
        tester.human_type("#filter-input", "memory", clear=True)
        tester.step("🎯 Real-Time Match: shared-memory skill", pause=1.2)

        # Step 9: Clear Search Filter
        tester.step("🧹 Reset Search Filter", pause=0.4)
        tester.human_click("#filter-input")
        tester.page.keyboard.press("Meta+A")
        tester.page.keyboard.press("Backspace")
        time.sleep(0.4)
        tester.step("📋 Full Catalog Restored", pause=0.8)

        # Step 10: Open Similar Skills Panel
        tester.step("🤖 Heuristic Similarity Discovery (No AI)", pause=0.5)
        tester.human_click("#similar-btn", pause_after=1.0)
        tester.page.locator("#similar-section").wait_for(state="visible", timeout=5000)

        # Adjust threshold
        tester.step("🎚️ Set Similarity Threshold: 0.3", pause=0.5)
        tester.human_select("#similar-threshold", "0.3")
        tester.step("📊 Multi-Feature Breakdown & Token Overlap", pause=1.6)

        # Step 11: Scroll to inspect skill cards
        tester.step("📜 Exploring Skill Cards & Security Findings", pause=0.5)
        tester.human_scroll(delta_y=380, steps=8)
        time.sleep(0.8)
        tester.human_scroll(delta_y=-380, steps=8)

        # Step 12: Concluding showcase banner
        tester.step("✨ Skill Atlas: Auditing, Discovery & Provenance", pause=2.2)

    logger.info("Browser session finished. Processing video and audio assets...")

    raw_video = out_dir / "raw_video"
    raw_video_files = list(raw_video.glob("*.webm"))
    if not raw_video_files:
        logger.error(f"No raw video found in {raw_video}")
        return 1

    input_webm = raw_video_files[0]
    duration_sec = tester.timeline[-1]["timestamp"] if tester.timeline else 32.0
    total_audio_dur = duration_sec + 2.0

    # 1. Generate upbeat background music
    music_wav = out_dir / "upbeat_music.wav"
    logger.info(f"Generating upbeat background synthwave track ({total_audio_dur:.1f}s)...")
    generate_music_track(music_wav, duration_sec=total_audio_dur)

    # 2. Render MP4 with audio using FFmpeg
    ffmpeg_bin = shutil.which("ffmpeg") or "/Users/Aleksandr.Avdiushenko/.local/bin/ffmpeg"
    demo_mp4 = docs_assets_dir / "demo.mp4"
    logger.info(f"Rendering HD MP4 video with upbeat audio track to {demo_mp4}...")
    cmd_mp4 = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_webm),
        "-i",
        str(music_wav),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(demo_mp4),
    ]
    res_mp4 = subprocess.run(cmd_mp4, capture_output=True, text=True)
    if res_mp4.returncode != 0:
        logger.error(f"FFmpeg MP4 render failed: {res_mp4.stderr}")
        return 1

    logger.info(f"Successfully generated {demo_mp4} ({demo_mp4.stat().st_size} bytes)")

    # 3. Generate high-quality optimized animated GIF for README preview
    demo_gif = docs_assets_dir / "demo.gif"
    logger.info(f"Rendering optimized animated GIF preview to {demo_gif}...")
    cmd_gif = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(demo_mp4),
        "-vf",
        "fps=12,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
        "-loop",
        "0",
        str(demo_gif),
    ]
    res_gif = subprocess.run(cmd_gif, capture_output=True, text=True)
    if res_gif.returncode != 0:
        logger.error(f"FFmpeg GIF render failed: {res_gif.stderr}")
        return 1

    logger.info(f"Successfully generated {demo_gif} ({demo_gif.stat().st_size} bytes)")

    # 4. Generate poster thumbnail
    thumb_png = docs_assets_dir / "demo-thumbnail.png"
    logger.info(f"Generating thumbnail keyframe to {thumb_png}...")
    # Grab a frame when results are displayed (~18s)
    capture_time = min(18.0, duration_sec * 0.5)
    cmd_thumb = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{capture_time:.2f}",
        "-i",
        str(demo_mp4),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(thumb_png),
    ]
    subprocess.run(cmd_thumb, capture_output=True, text=True)

    print("\n" + "=" * 70)
    print("🎬 DEMO VIDEO & MEDIA ASSETS GENERATION COMPLETE")
    print("=" * 70)
    print(
        f"  • Video (MP4 + Upbeat Audio): {demo_mp4} ({demo_mp4.stat().st_size / (1024 * 1024):.2f} MB)"
    )
    print(
        f"  • Inline Animated GIF:        {demo_gif} ({demo_gif.stat().st_size / (1024 * 1024):.2f} MB)"
    )
    print(f"  • Poster Thumbnail:           {thumb_png}")
    print(f"  • Total Duration:             {duration_sec:.1f} seconds")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(record_demo())
