---
name: browser-video-tester
version: 1.0.0
description: Autonomous browser testing skill with live video recording and human-like interaction. Use to verify web features, record video walkthroughs, and detect UI defects.
author: Skill Atlas Team
tags:
  - testing
  - browser
  - video
  - automation
  - qa
---

# Browser Video Tester

Autonomous browser testing skill inspired by [`video-use`](https://github.com/browser-use/video-use). It operates a real browser as a human QA tester would — moving the cursor with visual cues, typing with natural cadences, scrolling, clicking buttons, inspecting states, and recording high-definition video of the entire session.

## Core Principles

1. **Human-Like Interaction**: Actions are not instantaneous synthetic triggers. The tester moves a visible cursor across the screen, triggers visual ripple clicks, scrolls smoothly, and pauses realistically between actions (200–500ms).
2. **Video-First Evidence**: Every test run produces a clean, high-fps `.mp4` video recording showing exactly what happened on screen.
3. **On-Screen Action Subtitles**: An interactive banner overlay announces each testing step (e.g. "Switching to Light Theme", "Verifying Search Filter"), making the video self-explanatory and presentation-ready.
4. **Self-Evaluation Loop**: Every run inspects JavaScript console errors, HTTP network failures (4xx/5xx), DOM mutations, and visual regressions before declaring success.
5. **Structured Audit Artifacts**: Alongside the video, the skill generates a `report.md` with timestamps, an action `timeline.json`, and keyframe screenshots for each step.

## Hard Rules (Production Correctness)

1. **Never perform blind headless clicks**: Always scroll elements into view and move the cursor before clicking.
2. **Always capture console and network errors**: Listen to `console` and `response` events to fail fast on uncaught exceptions.
3. **Convert to web-friendly MP4**: Raw browser video recordings (`.webm`) must be converted to standard H.264/AAC `.mp4` using `ffmpeg` for universal playback.
4. **Isolate test artifacts**: All video recordings and screenshots must be stored in session-specific directories under `artifacts/browser_tests/`, never cluttering root or source code.
5. **Graceful cleanup**: Always ensure browser contexts and video streams are flushed and closed properly on both success and error.

## Companion Scripts

- [Browser Tester Engine](scripts/browser_tester.py): Core Playwright harness with visual cursor, action banners, video recording, and ffmpeg encoding.
- [Web UI Audit Runner](scripts/run_web_audit.py): End-to-end interactive test suite covering theme toggle, search, status and origin filters, scanning, and similar skills discovery.
- [Upbeat Music Generator](scripts/generate_music.py): Synthesizer for high-energy 128 BPM electronic background music with sidechain ducking and punchy drums.
- [Demo Video Recorder](scripts/record_demo.py): Automated pipeline recording a narrated walkthrough of the current Web UI (multi-repo scan of `cursor/plugins` and `avalur/skill-atlas`, time-lapsed scan wait, filters, Find Similar, Skill Map) and outputting MP4, GIF, and PNG assets into `docs/assets/`.
- [Narration](scripts/narration.py): Offline female voice-over via Piper (`en_US-lessac-medium`, override with `SKILL_ATLAS_PIPER_MODEL`) with a macOS `say -v Samantha` fallback, plus FFmpeg mixing with ducked background music and time-lapse support.

## Usage

### Run Pre-Configured Web UI Audit
```bash
uv run python .claude/skills/browser-video-tester/scripts/run_web_audit.py --url http://127.0.0.1:8765
```

### Record Narrated Demo Video & GIF Preview
Start the server first (`uv run skill-atlas serve`, with `GITHUB_TOKEN` set), then:
```bash
uv run python .claude/skills/browser-video-tester/scripts/record_demo.py
# Voice-over only, or render into a scratch folder for review:
uv run python .claude/skills/browser-video-tester/scripts/record_demo.py --no-music --assets-dir artifacts/demo_run/assets
```
Each narration line is synthesized before recording and every step waits for its line to finish, so speech stays in sync with on-screen actions. The scan wait is compressed to a ~6 s time-lapse in the final video.

### Custom Feature Test Script
```python
from scripts.browser_tester import BrowserTester

with BrowserTester(
    url="http://127.0.0.1:8765", output_dir="artifacts/browser_tests/my_feature"
) as tester:
    tester.step("Open application and verify header")
    tester.human_click("#theme-toggle")
    tester.step("Filter by keyword")
    tester.human_type("#search-input", "memory")
    tester.screenshot("filtered_state")
```
