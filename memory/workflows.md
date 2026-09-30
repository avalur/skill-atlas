# Development Workflows & Standards

This document formalizes the operational protocols, git conventions, and quality gates enforced in `Skill Atlas`.

## 1. Language & Communication Policy
- **Interactive User Communication**: **Russian**. All conversational replies, status updates, problem analyses, and design discussions with the user are in Russian.
- **Repository Artifacts**: **Strictly English**. Code, docstrings, inline comments, specifications, memory documents, READMEs, PR titles/descriptions, and git commit messages must be in English.

## 2. Git & Pull Request Protocol
Direct pushes to `main` are **strictly prohibited**. Every change follows the PR lifecycle:

1. **Dedicated Branch**:
   ```bash
   git checkout -b <prefix>/<short-description>
   # Prefixes: feat/, fix/, docs/, refactor/, test/
   ```
2. **Local Pre-Flight Checks**:
   Always run and verify:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```
3. **Commit with Junie Co-Author**:
   When committing changes, attach the Junie co-author trailer:
   ```bash
   git commit -m "feat: description" --trailer "Co-authored-by: Junie <junie@jetbrains.com>"
   ```
4. **Push & Open Pull Request**:
   Follow `.github/pull_request_template.md` when preparing the pull request description:
   ```bash
   git push -u origin <branch-name>
   gh pr create --title "type(scope): concise title" --body-file .github/pull_request_template.md
   # Or provide populated summary, changes, demo video, and verification:
   # gh pr create --title "type(scope): concise title" --body "..."
   ```
   **Mandatory Feature Demos**: Every feature PR must include a video demonstration (MP4 recording or animated GIF) illustrating the functionality (e.g., recorded with `browser-video-tester` or screen capture).

5. **CI Verification**:
   Monitor GitHub Actions CI checks (`ubuntu-latest` and `macos-latest` on Python 3.11 and 3.13):
   ```bash
   gh pr checks
   ```
   If red, inspect logs with `gh run view --log-failed`, resolve issues, and push again.
6. **Merge**:
   Merge only after green CI and explicit confirmation:
   ```bash
   gh pr merge <pr_number> --merge
   git checkout main && git pull origin main
   ```

## 3. Definition of Done (DoD)
A task is considered complete only when:
- [x] All unit and integration tests pass locally (`uv run pytest`).
- [x] Ruff linter and formatter checks are clean.
- [x] Spec (`SPEC.md`) and memory (`memory/`) are updated in the same change when applicable.
- [x] Feature demo video / recording attached in the Pull Request description (mandatory for all feature PRs).
- [x] Pull Request created following `.github/pull_request_template.md` via `gh pr create`.
- [x] CI checks pass on GitHub Actions across the full OS/Python matrix.
- [x] Pull Request is cleanly merged into `main`.

## 4. Multi-Agent Worktrees & Sandboxing
- `sbx-claude.sh <name>` and `sbx-junie.sh <name>` scripts provision isolated git worktrees at `../<name>` with centralized model proxy credentials.
- Worktrees like `filter` and `similar` allow concurrent agent development without working directory conflicts.
- Always check `git worktree list` when inspecting repository state across sessions.

## 5. Visual Regression Testing & Baseline Updates
Visual regression testing protects the Skill Atlas Web UI against CSS breakages, alignment regressions, and unintended visual distortions:
- **Test Suite**: Automated deterministic Playwright walkthrough (`tests/visual/test_walkthrough_screens.py`) capturing 5 key moments:
  1. `01_initial_dashboard` (clean landing state in dark theme)
  2. `02_light_theme` (toggled light mode styling across all controls)
  3. `03_scan_completed_results` (summary cards, skill list, origin badges, findings)
  4. `04_filtered_results` (keyword search filter 'memory' and origin chip active)
  5. `05_similar_skills_panel` (similarity drawer open with match breakdowns and threshold)
- **Local Run**:
  ```bash
  uv run pytest tests/visual
  ```
- **Updating Golden Baselines for Visual Features**:
  When developing intentional UI changes or new visual features, update baselines locally before pushing:
  ```bash
  UPDATE_BASELINES=1 uv run pytest tests/visual
  # or: uv run pytest tests/visual --update-baselines
  ```
  Commit the updated PNG files in `tests/visual/baselines/` in your PR branch. CI compares against the committed baselines and turns green.
- **Intentional Breakage Test**:
  `tests/visual/test_break_page.py` injects style distortions and verifies that regressions are caught, side-by-side diff highlight images are generated (`artifacts/visual/diffs/breakage_diff.png`), and diagnostic instructions are provided.
- **CI Pipeline**:
  Dedicated `visual-tests` job in `.github/workflows/ci.yml` runs on `ubuntu-latest`, caches Chromium (`~/.cache/ms-playwright`), and exports artifacts (`visual-artifacts-${{ github.sha }}`) containing captured screens, walkthrough video (`video_walkthrough.webm`), diffs, and interactive HTML summary report (`report.html`).
