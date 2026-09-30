# Architecture & System Design

This document details the architectural choices, component boundaries, and design rationales for `Skill Atlas`.

## 1. Tech Stack
- **Language**: Python >= 3.11 (with strict typing).
- **Package Management & Toolchain**: `uv` exclusively.
- **CLI Framework**: `typer` with `rich` formatting.
- **Web Interface**: `fastapi` with `uvicorn` (supports `--reload` for dev, SSE for streaming updates).
- **Data Modeling**: `pydantic` v2 for all entities (`Skill`, `Finding`, `ScanResult`, etc.).
- **HTTP Client**: `httpx` for GitHub REST API calls and raw content retrieval.
- **Testing**: `pytest` with custom fixtures (`fake_github`, `make_repo`).

## 2. Core Scanning Engine
```text
                 ┌────────────────────────────────────────────────────────┐
                 │                 skill-atlas CLI / Web UI               │
                 └──────────────────────────┬─────────────────────────────┘
                                            │
                                            ▼
                 ┌────────────────────────────────────────────────────────┐
                 │                 Scanner Orchestrator                   │
                 └───────┬───────────────────────────────┬────────────────┘
                         │                               │
            Local Target │                  Remote Target│ (https://github.com/...)
                         ▼                               ▼
       ┌───────────────────────────┐           ┌───────────────────────────┐
       │  discovery/local.py       │           │  discovery/remote.py      │
       │  (FS Walk + git ls-files) │           │  (GitHub REST API Tree)   │
       └─────────────┬─────────────┘           └─────────────┬─────────────┘
                     │                                       │
                     └───────────────────┬───────────────────┘
                                         ▼
                       ┌───────────────────────────────────┐
                       │   Rule Engine (rules/runner.py)   │
                       │   - Schema: SCH-001..SCH-006      │
                       │   - Security: SEC-001..SEC-005    │
                       │   - Discovery: DSC-001            │
                       └─────────────────┬─────────────────┘
                                         ▼
                       ┌───────────────────────────────────┐
                       │   Reporters (Console / JSON / UI) │
                       └───────────────────────────────────┘
```

## 3. Remote Scanning Strategy (Zero-Clone)
Full repository cloning for massive repositories (e.g. `JetBrains/kotlin`) is prohibited because it wastes bandwidth, consumes gigabytes of local storage, and takes minutes.

Instead, Skill Atlas employs a lightweight API-driven approach:
1. **Repository Tree**: Fetch the complete repository file tree via `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`. A monorepo with 500,000 files transfers in a single ~2–3 MB compressed JSON response.
2. **Selective Manifest Fetching**: Filter paths ending with `SKILL.md` (e.g., `.claude/skills/*/SKILL.md`). Fetch only the contents of these files via raw content URLs or GitHub Contents API.
3. **Companion Script Fetching**: For discovered skill directories, fetch associated text companion files (scripts under 1MB).
4. **Provenance Tracking**: Determine the original introduction date and commit hash using `GET /repos/{owner}/{repo}/commits?path={path}` (or `git log --diff-filter=A --reverse` locally).

## 4. Web Interface & Security
- **Endpoints**:
  - `GET /`: Serves the single-page application with responsive dark/light theme.
  - `POST /api/scans`: Initiates an asynchronous scan and returns a `scan_id`.
  - `GET /api/scans/{scan_id}/progress`: Server-Sent Events (SSE) streaming real-time stage updates, progress percentage, and GitHub rate limit.
  - `GET /api/scans/{scan_id}`: Returns complete `ScanResult` JSON.
  - `DELETE /api/scans/{scan_id}`: Cancels an active scan (returns 409 if already completed).
  - `GET /api/scans/{scan_id}/similar`: Computes similarity matches between skills.
- **Security Protections**:
  - `TrustedHostMiddleware` restricting host header.
  - `Origin` validation rejecting foreign origins.
  - Session CSRF tokens required on state-modifying endpoints (`POST`, `DELETE`).
  - Target URL validation (GitHub URLs only by default; local paths require explicit `--allow-local`).
  - HTML escaping for untrusted manifest strings.

## 5. Similarity Engine (`similarity.py`)
Calculates composite similarity across skills:
- Name token Jaccard overlap (weight: 0.25).
- Description TF-IDF cosine similarity (weight: 0.35).
- Shared tags Jaccard overlap (weight: 0.15).
- Markdown body structure / prompt headings similarity (weight: 0.15).
- Companion script filenames overlap (weight: 0.10).
The composite score is between `0.0` and `1.0`. Thresholds default to `0.5`, with UI options ranging from `0.3` to `0.8`.

## 6. Live QA Browser Video Testing (`browser-video-tester`)
Inspired by `browser-use/video-use`, the project incorporates an autonomous browser testing skill:
- **Playwright Harness**: Drives real browser interactions (smooth mouse movements, ripple clicks, human typing delays).
- **In-DOM Visual Cursor & Subtitle Banners**: Renders a floating pointer and action step overlays directly in the browser viewport.
- **Universal MP4 Encoding**: Converts raw recordings to standard H.264/AAC `.mp4` using `ffmpeg`.
- **Self-Evaluation & Artifacts**: Collects console errors, network failures, keyframe screenshots, `timeline.json`, and structured `report.md`.

## 7. Visual Regression Testing Pipeline (`tests/visual/`)
- **Deterministic Fixture Server**: Spins up local FastAPI server pointing to a local Git fixture (`tests/fixtures/visual_repo/`) on an ephemeral port.
- **Headless Playwright Chromium**: Runs with fixed viewport (`1280x720`), `device_scale_factor=1`, `prefers-reduced-motion: reduce`, suppressed blinking cursors, and WebM video recording.
- **Pixel Comparison Engine (`image_diff.py`)**: Uses Pillow for fast (<5ms), pure-Python channel delta comparison with configurable pixel and color tolerances, highlight mask generation, and side-by-side composites.
- **HTML Visual Report (`report.py`)**: Builds an interactive summary report at `artifacts/visual/report.html` embedding statistics, embedded walkthrough video, and side-by-side screenshot comparisons.
