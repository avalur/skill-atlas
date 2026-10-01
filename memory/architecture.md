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
                 │                 (TARGET..., -T file, -q query)         │
                 └──────────────────────────┬─────────────────────────────┘
                                            │
                                            ▼
                 ┌────────────────────────────────────────────────────────┐
                 │                 Scanner Orchestrator                   │
                 │                 - Target Normalization & Deduplication │
                 │                 - Target Discovery Loop                │
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
                       │   Query Filter (Audit-Scope)      │
                       │   - Case-insensitive substring    │
                       │   - Matches name, desc, path,     │
                       │     repo_name, and tags           │
                       └─────────────────┬─────────────────┘
                                         ▼
                       ┌───────────────────────────────────┐
                       │   Deduplication & Drift Check     │
                       │   (Isolated per repository)       │
                       └─────────────────┬─────────────────┘
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
                       │   - Aggregated ScanResult         │
                       │   - Target-indexed progress (SSE) │
                       └───────────────────────────────────┘
```

### Multi-Target & Audit-Scoped Search
- **Target Ingestion**: Accepts multiple positional targets on the CLI (`skill-atlas scan TARGET1 TARGET2`), a newline-delimited text file via `--targets-file / -T`, or newline/comma-separated targets in the Web UI textarea.
- **Audit-Scoped Search (`--query / -q`)**: Discovered skills are filtered *before* running static rule evaluations (`matches_query`). This eliminates expensive rule checks on irrelevant skills, drastically reducing computation and network traffic.
- **Repository Provenance & Isolation**: Cross-repository skill names are isolated (skills with identical names in separate repositories are not falsely merged as duplicate copies).
- **Data Contract Compatibility**: `ScanResult` carries `targets: list[str]` and `query: str | None`, while maintaining `target: str` populated with the first target for complete backward compatibility.

## 3. Remote Scanning Strategy (Zero-Clone)
Full repository cloning for massive repositories (e.g. `JetBrains/kotlin`) is prohibited because it wastes bandwidth, consumes gigabytes of local storage, and takes minutes.

Instead, Skill Atlas employs a lightweight API-driven approach:
1. **Repository Tree**: Fetch the complete repository file tree via `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`. A monorepo with 500,000 files transfers in a single ~2–3 MB compressed JSON response.
2. **Selective Manifest Fetching**: Filter paths ending with `SKILL.md` (e.g., `.claude/skills/*/SKILL.md`). Fetch only the contents of these files via raw content URLs or GitHub Contents API.
3. **Companion Script Fetching**: For discovered skill directories, fetch associated text companion files (scripts under 1MB).
4. **Provenance Tracking**: Determine the original introduction date and commit hash using `GET /repos/{owner}/{repo}/commits?path={path}` (or `git log --diff-filter=A --reverse` locally).

## 4. Web Interface & Security
- **Endpoints**:
  - `GET /`: Serves the single-page application with responsive dark/light theme, multi-repository textarea, dynamic repository chips, and instant filtering.
  - `POST /api/scans`: Initiates an asynchronous scan accepting `targets: list[str]`, legacy `target: str`, and optional `query: str | None`. Returns a `scan_id`.
  - `GET /api/scans/{scan_id}/events`: Server-Sent Events (SSE) streaming real-time stage updates, multi-repository progress context (`target_index`, `target_total`, `target_name`), progress percentage, and GitHub rate limit.
  - `GET /api/scans/{scan_id}`: Returns complete `ScanResult` JSON.
  - `DELETE /api/scans/{scan_id}`: Cancels an active scan (returns 409 if already completed).
  - `GET /api/scans/{scan_id}/similar`: Computes similarity matches between skills.
- **Multi-Repository & Filter Interactions**:
  - Adaptive multi-line textarea accepting newline- or comma-separated repository URLs and directory paths.
  - Quick sample target loader button (`Load Sample Repos`).
  - Dynamic repository filter chips (`All Repos (<count>)`, `<repo_name> (<count>)`) automatically populated from scan results.
  - Unified client-side filter engine combining repository filter chips, origin filter chips, pass/fail status filters, and instant keyword search without page reloads.
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

## 7. Visual Regression Testing & Failure Reporting (`tests/visual/`)
- **Deterministic Fixture Server**: Spins up local FastAPI server pointing to a local Git fixture (`tests/fixtures/visual_repo/`) on an ephemeral port.
- **Headless Playwright Chromium**: Runs with fixed viewport (`1280x720`), `device_scale_factor=1`, `prefers-reduced-motion: reduce`, suppressed blinking cursors, and WebM video recording.
- **Pixel Comparison Engine (`image_diff.py`)**: Uses Pillow for fast (<5ms), pure-Python channel delta comparison with configurable pixel and color tolerances, highlight mask generation, and side-by-side composites.
- **HTML Visual Report (`report.py`)**: Builds an interactive summary report at `artifacts/visual/report.html` embedding statistics, embedded walkthrough video, and side-by-side screenshot comparisons.
- **Failure Serialization (`failures.py`)**: Tracks snapshot regressions into `artifacts/visual/failures.json` (and `tests/visual/out/failures.json`).
- **Asset Publication (`scripts/publish-assets.sh`)**: Direct tree injection into `demo-assets` orphan branch without modifying local working tree.
- **Failure Explainer (`scripts/visual-report.sh` / `scripts/ui-report.sh`)**: Formats terminal logs, GitHub Actions `::error` annotations, and markdown table (`Expected | Actual | Diff`) into `$GITHUB_STEP_SUMMARY`.

## 8. The Skill Map Engine (`map.py`)
Provides thematic clustering, categorical discovery, and visual mapping:
- **Heuristic Grouping**: BFS connected components on pairwise similarity + shared keyword graph; automatically names clusters from dominant tags/words and generates rationale.
- **Claude AI Clustering**: Non-interactive `claude -p` execution asking for structured cluster JSON; supports deterministic recording (`--record`) and replaying (`--replay`).
- **TypeSafe Jev Classification**: Fast System One classification model via `typesafe-sdk` (`Choice` API) mapping skills into typed domain categories (`memory_and_state`, `code_and_review`, `security_and_audit`, `data_and_sync`, `general_automation`).
- **Ground-Truth Benchmark Check**: Validated against a 10-skill manual golden benchmark verifying grouping consistency.
- **Web UI & Endpoints**: `GET /api/scans/{scan_id}/map` powering interactive visual cluster cards with instant keyword filtering and deterministic replay support.
