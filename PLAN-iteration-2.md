# Implementation Plan: Iteration 2 (Tests, CI, and a Web Interface)

**Date**: 2026-09-30
**Target release**: v0.2.0
**Inputs**: workshop hands-on task "Tests, CI, and a web interface", `SPEC.md` 0.1.0-draft, `claude-review-cli-v1.md`.

## 0. Goals and starting point

The iteration has three workstreams, in this order:

1. **CI and `AGENTS.md`**: set up CI and write the definition of done into `AGENTS.md`.
2. **Corner cases**: integration tests for real-world repository layouts, then handling them. Work continues until CI is green.
   - duplicates in `.claude` and `.agents` (MPS)
   - test data (koog)
   - a skill that is part of the product (MPS)
3. **Web interface**: a local web view over the same core. It has a repository URL input and a **status bar that tells the user what the tool is doing right now**. CI stays green.

**Decisions taken (2026-09-30)**:
- **No `git clone`, ever.** Remote repositories are read only through the GitHub REST API and raw file downloads. The clone fallback is removed from the code (§2.4).
- **Duplicates**: the report shows the **most recently updated** copy and marks the skill as duplicated (Case A).
- **Test data**: listed, but never affects the exit code unless `--include-test-data` is passed (Case B).
- **Web stack**: FastAPI.
- The "unusual folder" case is out of scope for this iteration.

**Baseline (commit `7628847` plus uncommitted work)**:
- 17 unit tests pass.
- Fixes for several v1 review findings are in the working tree but not committed: missing target, reading companion files, symlink policy, `Field(exclude=True)`, `ScanResult.exit_code()`, pagination of GitHub commits.
- There is no CI, no integration tests and no web UI.
- Origin is `github.com/avalur/skill-atlas`, so CI will be GitHub Actions.

**Rule for the whole iteration**: every step ends with the definition of done from §1.2. Nothing counts as finished while CI is red.

---

## 1. Workstream 1: CI and `AGENTS.md`

### 1.1. Land the in-flight work first
- Review and commit the uncommitted v1 fixes as they are. Keep the commits small, one per review finding if practical.
- Pin the linter configuration in `pyproject.toml`, so the result does not depend on a developer's global ruff config:
  ```toml
  [tool.ruff.lint]
  select = ["E", "F", "I", "UP", "B", "BLE", "S", "RUF"]
  [tool.ruff.lint.per-file-ignores]
  "tests/**" = ["S101"]
  ```
- `uv run ruff check . --fix && uv run ruff format .`, then fix whatever remains by hand.

### 1.2. `AGENTS.md` additions
Add these sections verbatim, then adapt the wording:

```markdown
## Specs
Read ./SPEC.md first. Update it in the same change as the code.

## Tests
Integration tests for every case in the spec (every rule, every CLI option,
every exit code, every corner-case layout in SPEC §3.3).

## Definition of done
- All tests pass locally: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`
- Pushed; CI is green for this commit
- Red CI: read the logs (`gh run view --log-failed`), fix, push again
```

Also add to the development commands:
- `uv run skill-atlas serve` starts the web UI.
- `uv run pytest -m network` runs the opt-in tests that call the real GitHub API.

### 1.3. CI workflow (`.github/workflows/ci.yml`)
- **Triggers**: `push` to any branch and `pull_request`.
- **Matrix**: `os: [ubuntu-latest, macos-latest]` × `python: ["3.11", "3.13"]`. macOS stays in the matrix on purpose: its filesystem is case-insensitive, which exposed the duplicate-manifest bug (review M7).
- **Steps**:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v6` with the cache enabled.
  3. `uv sync --locked`
  4. `uv run ruff check .`
  5. `uv run ruff format --check .`
  6. `uv run pytest -m "not network" --junitxml=report.xml`
  7. Upload `report.xml` as an artifact.
- Set `git config --global user.name/user.email` before pytest. Local fixture repos create commits.
- **Separate job `network`**: runs `pytest -m network` against the real GitHub API with `GITHUB_TOKEN` from the workflow, pinned to commit SHAs (§2.3). It runs on `workflow_dispatch` and a nightly `schedule`, and it is never required for merge. That keeps the required CI deterministic and free of rate limits.
- Add a CI badge to `README.md`.

**Exit criteria**: a push to a branch produces a green run, and a deliberately broken test turns it red.

---

## 2. Workstream 2: corner cases and integration tests

### 2.1. Test harness
New layout:

```text
tests/
├── conftest.py              # shared fixtures and helpers
├── unit/                    # existing test_scanner.py, split per module
├── integration/
│   ├── test_cli_contract.py     # exit codes 0/1/2, --format, --fail-on, --rules, --ignore, --verbose
│   ├── test_rules_e2e.py        # every SCH/SEC rule through the CLI, positive + negative
│   ├── test_provenance.py       # local git: add / delete / re-add / rename; remote: fake GitHub
│   ├── test_remote_github.py    # remote discovery against the fake GitHub API
│   ├── test_layouts.py          # the three corner cases (§2.2), local and remote
│   └── test_web.py              # API + progress events (§3)
└── fixtures/
    ├── skills/                  # single-skill fixtures (existing ones move here)
    └── layouts/                 # repository trees for §2.2, as plain files
```

Helpers in `conftest.py`:
- `make_repo(tmp_path, tree: dict[str, str], commits: list[Commit])`: builds a local git repo with deterministic `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`, so local provenance tests can assert exact SHAs and dates.
- `copy_layout(name) -> Path`: copies a `fixtures/layouts/<name>` tree into `tmp_path` and commits it.
- `fake_github(layout, history) -> httpx.MockTransport`: serves a layout directory as GitHub API responses. It covers the repo metadata, `git/trees?recursive=1` (including a `truncated: true` variant), `commits?path=` with `Link` pagination, raw downloads and 403 rate-limit responses. `GitHubClient` takes an injectable `httpx.Client`, so every remote test runs offline. The same layouts drive the local tests and the remote tests, and both paths must return the same JSON.
- `run_cli(*args) -> Result`: wraps `typer.testing.CliRunner` and parses the output when `--format json` is set.

Markers:
- `network`: real GitHub, opt-in.
- `slow`: optional.

### 2.2. Corner cases

Each case is described below by the layout, the expected behaviour and the tests. The behaviour proposed here is **new spec text**: add it to `SPEC.md` as §3.3 "Repository layouts" in the same change.

To support these cases, discovery classifies each skill with a new field.

```python
class SkillOrigin(str, Enum):
    AGENT_CONFIG = (
        "agent-config"  # .claude/skills, .agents/skills, .junie/skills, .cursor/..., .codex/...
    )
    PRODUCT = "product"  # shipped inside the product (resources, plugin bundles)
    TEST_DATA = "test-data"  # fixtures / test resources, intentionally broken
    STANDALONE = "standalone"  # anything else, e.g. top-level skills/ catalog
```

The classifier is a pure function `classify(path: str) -> SkillOrigin` that matches path segments in order:
1. test data: `test`, `tests`, `testData`, `testdata`, `fixtures`, `src/test/`, `src/*Test/`, `test-resources`
2. agent config: `.claude`, `.agents`, `.junie`, `.cursor`, `.codex`, `.github/skills`
3. product: `src/main/resources`, `resources/`, `plugins/*/`, `languages/*/`
4. standalone: everything else

Test-data skills are still **listed**, but their findings **never affect the exit code** unless the user passes `--include-test-data`.

Duplicate handling needs a second provenance point, so `Skill` gets two new fields next to `commit`/`commit_date` (which keep their meaning, the first introduction):
- `updated_commit` and `updated_date`: the last commit that touched the skill directory.
  - Local: `git log -1 --format="%H %aI" -- <skill_dir>`.
  - Remote: the first item of the same `commits?path=` response that already gives the oldest commit, so no extra request is needed.
  - Local skills with uncommitted changes, or outside git: use the newest file mtime in the skill directory, and mark it `updated_source: "mtime"`.

#### Case A: duplicates in `.claude` and `.agents` (MPS)
- **Layout**: a skill with the same `name` appears in more than one place, e.g. `.claude/skills/foo/SKILL.md` and `.agents/skills/foo/SKILL.md`. It can be a copy or a symlink, and either side may be a symlinked directory.
- **Current behaviour**: the skill is reported twice, with findings counted twice.
- **Target behaviour**:
  - Group skills by `name`. The report shows **one** entry per group, built from the copy with the newest `updated_date`. Ties (for example, both copies added in the same commit) are broken by path in lexicographic order, so the output stays deterministic.
  - The shown entry gets `duplicates: list[DuplicateRef]`, where each ref holds `path`, `updated_commit`, `updated_date` and `identical: bool` (sha256 of the normalised skill directory compared with the shown copy). The console marks it as `⧉ duplicated (2 copies)` and lists the other paths. The web UI shows a "duplicate" badge.
  - Rules run only on the shown copy, so findings are counted once.
  - A new rule `DSC-001 Stale Duplicate` (WARN) fires when at least one copy is **not identical**: "2 copies of 'foo' differ; showing .agents/skills/foo (updated 2026-09-12), .claude/skills/foo is older (2026-05-03)". The suggestion is to sync or remove the stale copy.
  - A symlink counts as one location resolved to its target, never as a second skill.
- **Tests** (local and fake-GitHub variants):
  - identical copies → 1 skill, 1 duplicate ref with `identical: true`, no DSC-001
  - divergent copies, `.claude` newer → `.claude` copy shown, `.agents` listed as a duplicate, DSC-001 present
  - the same, with `.agents` newer → the choice follows the date, not the folder name
  - same-commit tie → deterministic choice
  - symlinked dir, symlinked `SKILL.md` → 1 skill, no duplicate ref
  - findings are counted once in the summary

#### Case B: test data (koog)
- **Layout**: `SKILL.md` files under test resources, e.g. `src/test/resources/skills/broken/SKILL.md` or `testData/...`. They exist so the product's own tests can load broken or edge-case skills.
- **Current behaviour**: they are scanned as real skills and fail the run with false errors.
- **Target behaviour**:
  - `origin = test-data`, and a separate "Test data" section in the report.
  - They are excluded from pass/fail and from the exit code by default.
  - `--include-test-data` restores normal handling.
  - Test-data skills are never merged with non-test skills during duplicate grouping. A fixture called `foo` must not hide the real `foo`.
- **Tests**:
  - a repo with one real skill and one broken test-data skill → exit 0, both listed, test-data findings present but non-blocking
  - the same repo with `--include-test-data` → exit 1
  - a test-data skill with the same name as a real one → both shown, no DSC-001

#### Case C: part of the product (MPS)
- **Layout**: skills bundled as product resources, e.g. `plugins/<plugin>/resources/skills/<x>/SKILL.md` or `languages/.../skills/...`. They ship to end users and are not the repository's own agent configuration.
- **Target behaviour**:
  - `origin = product`, shown as a separate group in both reports.
  - All rules apply, because these reach users.
  - The console summary breaks results down by origin.
  - If a product skill is also mirrored into `.claude`/`.agents`, Case A applies unchanged: the newest copy is shown, and the other copies are listed as duplicates with their origin.
- **Tests**:
  - the classifier returns `product` for each known product path
  - a mixed repo (agent-config + product + test-data) → the JSON groups and counts are correct
  - a product skill mirrored into `.agents` with an older mirror → the product copy is shown and DSC-001 points at the stale mirror

### 2.3. Grounding in the real repositories
The layouts above come from the workshop slide. The exact paths still have to be **confirmed against the real repositories** (JetBrains MPS and koog) before the fixtures are frozen:
- Run `skill-atlas scan <url> -f json` once for each repo (API only) and record the real paths where skills live. Copy a **minimal** reproduction of each layout (a few files, no product code) into `tests/fixtures/layouts/{mps,koog}/`, including the commit dates needed for Case A.
- Add one `network` test per repository, pinned to a commit SHA (`git/trees/<sha>` and `commits?sha=<sha>&path=`), that asserts the skill count, origins and duplicate groups. This catches the case where the synthetic fixture stops matching reality.

### 2.4. Remote access: GitHub API only
Without a clone, the API path carries all remote scanning, so it has to be complete and robust:
- **Remove** `_discover_via_git_clone` and every fallback to it. A remote target that is not a GitHub URL fails with exit 2: "Only GitHub repositories are supported for remote scans". Review findings C4 (unchecked clone) and C6 (argument injection into `git clone`) go away together with the code.
- **Companion files for SEC rules** (review C1): take the file list from the tree, skip entries larger than 1 MB (the tree has a `size` field) and known binary extensions, then download the rest from `raw.githubusercontent.com`. Raw downloads do not count against the REST API limit.
- **Truncated trees**: when `truncated: true`, walk the tree non-recursively, but only into directories that can contain skills, and emit a warning on the scan result.
- **Pagination** (M4): for each skill, use one `commits?path=<dir>&per_page=100` request. The first item gives `updated_*`. For the oldest commit, follow `Link: rel="last"`. That makes 1–2 REST calls per skill.
- **Auth** (M5): use `GITHUB_TOKEN`/`GH_TOKEN` for API calls and for raw downloads, so private repositories work.
- **Rate limits**: read `X-RateLimit-Remaining`/`X-RateLimit-Reset` on every response. Without a token the limit is 60 requests per hour, which covers roughly 25–30 skills. When the limit runs out, fail with exit 2 and a clear message: "GitHub rate limit reached, resets at 14:32; set GITHUB_TOKEN". The remaining budget goes into progress events (§3.1).
- **Pin a ref**: `--ref <branch|tag|sha>`, defaulting to the default branch. Tests and network checks use it to get reproducible results.
- **Consistency**: the local and remote paths build `Skill` through one shared function, and the same layout must produce the same JSON either way. The parity test in §2.1 enforces this.

### 2.5. Other review findings folded into this workstream
These have to be fixed for the new integration tests to be meaningful. Each fix ships with its test:
- C2 regex for `rm -rf`
- C5 crash → exit 2
- M1 escape Rich markup
- M2 local provenance: the oldest add wins
- M6 `SCH-006` normalisation
- M7 case-insensitive manifest dedup, the same in local and remote discovery
- M8 `--verbose`

**Exit criteria**: all layout tests (local and fake-GitHub) plus the CLI contract tests pass on the Ubuntu and macOS matrix, and CI is green.

---

## 3. Workstream 3: local web interface

### 3.1. Core change first: progress events
The status bar should report what the tool is **actually** doing, not a generic spinner. So the core has to emit progress events. The CLI and the web UI then consume the **same** stream, which keeps them from drifting apart.

```python
class Stage(str, Enum):
    VALIDATE = "validate"  # "Checking the repository URL"
    FETCH = "fetch"  # "Fetching the file tree of JetBrains/MPS (default branch: master)…"
    DISCOVER = "discover"  # "Found 14 SKILL.md files"
    DOWNLOAD = "download"  # "Downloading skill files (37/52)"
    PROVENANCE = "provenance"  # "Reading commit history for .agents/skills/foo (5/14)"
    DEDUPE = "dedupe"  # "3 skills have duplicates; showing the newest copy"
    RULES = "rules"  # "Running 12 rules on .agents/skills/foo (5/14)"
    REPORT = "report"  # "Building the report"
    DONE = "done"  # "Done: 14 skills, 2 failed, 5 findings"
    ERROR = "error"  # "GitHub rate limit reached, resets at 14:32; set GITHUB_TOKEN"


class ProgressEvent(BaseModel):
    stage: Stage
    message: str  # human-readable text shown in the status bar
    current: int | None = None
    total: int | None = None
    skill_path: str | None = None
    rate_limit_remaining: int | None = None  # GitHub API budget, when known
    elapsed_ms: int


ProgressCallback = Callable[[ProgressEvent], None]
```

- `Scanner.scan(target, on_progress: ProgressCallback | None = None)`. The callback is optional and does nothing by default. Discovery, downloads, provenance and rule evaluation call it at every step that takes noticeable time. For remote scans, the unit of progress is an HTTP request, so the counters are real.
- **Cancellation**: the scanner checks a `threading.Event` between HTTP requests and between skills.
- **CLI consumer**: a `rich.status`/`Progress` line on **stderr**, so `--format json` on stdout stays clean. It is turned off when stderr is not a TTY.
- **Tests** (against the fake GitHub):
  - a scan emits the stages in order and ends with `done`
  - the `current`/`total` counters never decrease
  - a 404 repository ends with `error`
  - an exhausted rate limit ends with `error` and the reset time appears in the message

### 3.2. Server
- **Stack**: FastAPI + Uvicorn, added as the optional extra `skill-atlas[web]`. The CLI install stays light. The frontend is a single static `index.html` with vanilla JS and CSS, and no build step.
- **Command**: `skill-atlas serve [--host 127.0.0.1] [--port 8765] [--open]`. It binds to **localhost only** by default, and prints a warning if `--host 0.0.0.0` is used. The token is read from the server's environment and is never sent to the browser.
- **API**:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/scans` | Body `{target, ref, rules, fail_on, ignore, include_test_data}` → `{scan_id}` |
| `GET` | `/api/scans/{id}/events` | **Server-Sent Events** stream of `ProgressEvent`, replays history on reconnect |
| `GET` | `/api/scans/{id}` | Final `ScanResult` JSON, the same schema as `--format json` |
| `DELETE` | `/api/scans/{id}` | Cancel a running scan |
| `GET` | `/api/health` | Version, liveness, whether a GitHub token is configured, current rate-limit budget |

- **Jobs**: an in-memory registry with each scan running in a worker thread. One concurrent scan by default, and later requests wait in a queue. The status bar shows "Queued: position 1" for those. Finished results are kept for the session only.
- **Input validation**: the same `validate_target()` as the CLI. It accepts `https://github.com/<owner>/<repo>` (with an optional `.git`, `/tree/<ref>` or trailing slash) and `git@github.com:<owner>/<repo>.git`, and returns 422 for anything else. Local filesystem paths are refused unless the server was started with `--allow-local`.

### 3.3. UI
```text
┌──────────────────────────────────────────────────────────────────────┐
│ Skill Atlas                                                 v0.2.0   │
├──────────────────────────────────────────────────────────────────────┤
│ Repository URL                                                       │
│ [ https://github.com/owner/repo                          ] [ Scan ]  │
│ ▸ Options: ref [default]  rules [all▾]  fail on [error▾]             │
│            ☐ include test data                                       │
├──────────────────────────────────────────────────────────────────────┤
│ Summary: 14 skills · 12 passed · 2 failed · 1 error · 4 warnings     │
│ [All] [Agent config 6] [Product 5] [Standalone 1] [Test data 2]      │
│                                                                      │
│ ✖ my-broken-skill   skills/my-broken-skill    a1b2c3d  2024-03-15    │
│   Demonstrates broken frontmatter and unsafe shell script execution  │
│   ▾ ERROR SCH-003 Missing required field 'description'  SKILL.md:4   │
│     WARN  SEC-003 Unsafe pipe to shell   scripts/install.sh:12       │
│ ✔ git-helper  ⧉ duplicated   .agents/skills/git-helper               │
│   updated 8f9e0d1 2026-09-12 · also at .claude/skills/git-helper     │
│   (older, 2026-05-03, differs)                                       │
├──────────────────────────────────────────────────────────────────────┤
│ ⟳ Reading commit history for skills/foo (5/14) ▓▓▓▓▓░░░░ API 41/60 ✕ │  ← status bar
└──────────────────────────────────────────────────────────────────────┘
```

- **Status bar**: pinned to the bottom of the page and always visible.
  - It shows the current `ProgressEvent.message`, a progress bar when `total` is known, elapsed time, the remaining GitHub API budget and a cancel button.
  - Its states are idle ("Paste a GitHub repository URL to start"), queued, running, done (a green summary) and error (a red message with the reason and a "Retry" button).
  - The last 50 events can be expanded as a log, so the user can see what already happened.
  - It uses `aria-live="polite"` for screen readers.
  - When no token is configured, the idle state says so: "No GITHUB_TOKEN: limited to ~25 skills per hour".
- **Results**: grouped by origin, with filter chips. Each skill shows name, description, path, the first and last commit with dates, and the duplicate badge with the other copies. Findings can be expanded per skill. There is a "Download JSON" button.
- **Security**: all text from scanned repos goes in through `textContent` and never `innerHTML` (the same concern as review M1). A strict CSP header (`default-src 'self'`) is set, with no third-party scripts.
- **Light and dark themes** via `prefers-color-scheme`. It works at narrow widths.

### 3.4. Tests
- **API** with FastAPI `TestClient` and the fake GitHub transport:
  - `POST` → SSE events arrive in stage order → `GET` returns the same JSON as the CLI for the same target. This parity test keeps the web and CLI on one core.
  - A non-GitHub URL or garbage input → 422 with a clear message.
  - Cancel → the stream ends with `error`/`cancelled`.
  - A local path without `--allow-local` → 403.
  - A rate-limited fake → the `error` event carries the reset time.
- **XSS regression**: a fixture skill whose description contains `<img src=x onerror=alert(1)>` renders as text. This is checked at the API level (raw string preserved) and by a DOM assertion in the browser test below.
- **Optional browser smoke test** (`playwright`, marker `e2e`, not required in CI at first): type a URL, click Scan, see the status bar text change, see the results table.

**Exit criteria**: `skill-atlas serve` scans a public GitHub repository end to end with live status, the parity test is green, and CI is green.

---

## 4. Order of work and milestones

| # | Milestone | Main deliverables | Done when |
|---|---|---|---|
| 1 | CI baseline | Commit in-flight fixes, ruff config, `AGENTS.md` DoD, `ci.yml` | First green CI run on Ubuntu + macOS |
| 2 | Test harness | `conftest.py` helpers incl. `fake_github`, CLI contract tests, provenance tests | Tests expose the known review bugs and those bugs are fixed; CI green |
| 3 | API-only remote | Remove the clone path; add truncation, pagination, raw files with auth, rate limits, `--ref` | Remote tests on fake GitHub green; local and remote JSON parity; CI green |
| 4 | Layout recon | Scan MPS and koog once via the API; freeze minimal fixtures; `network` tests pinned to SHAs | Fixtures committed, network job green |
| 5 | Corner cases | `SkillOrigin`, classifier, `updated_*` provenance, newest-copy dedupe + `DSC-001`, test-data handling, `SPEC.md` §3.3 | All `test_layouts.py` green; CI green |
| 6 | Progress events | `ProgressEvent`, callbacks in the core, CLI status line on stderr | Event-order tests green; CI green |
| 7 | Web UI | `serve` command, API, SSE, `index.html` with status bar | API + parity + XSS tests green; CI green |
| 8 | Docs and release | README (web UI usage and screenshot), SPEC v0.2.0 (no cloning, GitHub-only remote, duplicates, origins), CHANGELOG, tag `v0.2.0` | Tagged commit has green CI |

Each milestone is one or more PRs. Per `AGENTS.md`, a PR is not done until its CI run is green.

---

## 5. Resolved questions (2026-09-30)

1. **Non-GitHub remotes** (GitLab, Bitbucket, self-hosted): out of scope for v0.2.0 and rejected with exit 2. Each would need its own API client.
2. **What "updated" means for duplicates**: the last commit touching the skill **directory**, not only `SKILL.md`, so changes to companion scripts count too.
3. **Paths of MPS and koog**: confirmed by one API scan of each real repository before the fixtures are frozen (milestone 4, §2.3).
