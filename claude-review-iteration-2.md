# Code Review: Skill Atlas Iteration 2

**Date**: 2026-09-30
**Scope**: commits `98d0eee..838f87a` on `main` (41 files, +4061/−506). Checked against `PLAN-iteration-2.md`, `SPEC.md` and `claude-review-cli-v1.md`.
**Method**: Read all changed source files and the test harness. Ran lint, the tests and the CLI. Reproduced behavioural claims with fixture repos (`tests/conftest.py::make_repo`), the fake GitHub transport and FastAPI `TestClient`. Findings marked **[verified]** were reproduced by a run. The others come from reading the code.

---

## 1. Summary

A lot of good work landed:
- **CI**: green on Ubuntu and macOS × Python 3.11/3.13; the logs confirm each leg really uses its Python version. Ruff config is pinned, lint and format are clean.
- **`AGENTS.md`**: has the Definition of Done.
- **Tests**: 74 offline tests pass.
- **Clone path**: gone.
- **v1 review items fixed**:
  - security rules now scan companion files
  - `rm -rf /`, `rm -fr /`, `curl … | sudo bash` and `bash <(curl …)` are detected, and `rm -rf /tmp/build` and `| shasum` are no longer flagged
  - Rich markup in the report is escaped
  - missing target and crashes exit 2
  - the oldest add wins in local provenance
  - `--verbose` works
  - pass/fail follows the `--fail-on` threshold

Blocking problems remain:
- **The web server can be driven by any website** the user visits, using the user's GitHub token.
- **Duplicate handling hides skills from the security audit.** Only the newest copy is scanned. Distinct skills that share a name are merged, so a secret in one of them never shows up.
- **"Newest" is decided by comparing date strings**, which is wrong across time zones.
- **Remote scanning differs from local scanning** on the same repository.
- **The web UI ignores most of its options.**

| Severity | Count |
|---|---|
| Critical | 4 |
| Major | 9 |
| Minor | 12 |

---

## 2. Critical

### C1. Any website can drive the local web server **[verified]**
`web.py:108-114` sets `CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`. A preflight from `Origin: https://evil.example` gets back `Access-Control-Allow-Origin: https://evil.example` and `Allow-Credentials: true`. So any page open in the user's browser can `POST /api/scans` to `http://127.0.0.1:8765` and read the result.
- The server scans with the user's `GITHUB_TOKEN` from its environment. A hostile page can therefore list **private** repositories' skill names, descriptions, paths, commits and findings, and use up the token's rate limit.
- With `--allow-local`, the same page can scan any local directory.
- There is no `Host` header check, so DNS rebinding works even without CORS.

*Fix*: remove `CORSMiddleware`, because the UI is same-origin and needs no CORS. Reject requests whose `Host` is not `127.0.0.1:<port>`/`localhost:<port>` (Starlette `TrustedHostMiddleware`). Require a per-process random token: embed it in the served HTML and send it as a header. Add a test with a foreign `Origin`.

### C2. Stale duplicate copies are never audited **[verified]**
`scanner.py:163-184`: rules run only on the shown ("newest") copy. The other copies become a `DuplicateRef` and are never scanned.

*Repro*: an older `.claude/skills/foo/SKILL.md` containing `rm -rf ~/` and `curl … | bash`, plus a newer clean `.agents/skills/foo/SKILL.md`. Result: one skill with `DSC-001` only, **exit 0**. The dangerous copy is still in the repository, and an agent that reads `.claude/` will load it.

The plan's "show the newest copy" is a *display* decision. It must not also be an *audit* decision.

*Fix*: run the rules on every copy. Group only for display: attach each copy's findings to its `DuplicateRef`, or report them as findings of the shown skill with `file` set to the copy's path. Pass/fail and the exit code must include the findings of every copy. Add the repro above as a test.

### C3. Distinct skills that share a name are merged and hidden **[verified]**
`scanner.py:35-38` groups by `(is_test_data, name)` across the **whole repository**. Two different product skills, `plugins/a/resources/skills/setup` and `plugins/b/resources/skills/setup`, become one entry. On a date tie, lexicographic path order picks `plugins/a`.

*Repro*: an AWS key in plugin B's `SKILL.md` produces **no SEC-001 and exit 0**. The only trace is a `DSC-001` saying the "copies differ". A monorepo with several plugins will hit this routinely.

The corner case in the plan is *mirrored agent-config copies*, not "any two skills with the same name".

*Fix*: treat skills as duplicates only when they share `name` **and** at least one side is under an agent-config root, or when their relative paths inside the known roots match (`.claude/skills/foo` ↔ `.agents/skills/foo`). Keep everything else separate. A same-name collision between separate skills could be its own INFO rule (`DSC-002 Name Collision`). C2's fix is needed anyway.

### C4. "Newest copy" compares ISO strings with different time-zone offsets **[verified]**
`scanner.py:51` sorts by the `updated_date` **string**. Local dates come from `git log --format=%aI` in the author's own offset, remote dates are in `Z`, and mtime fallbacks are in `+00:00`.

*Repro*: copy A committed at `2026-01-01T10:00:00+05:00` (05:00Z) and copy B at `2026-01-01T08:00:00+00:00` (08:00Z). A is chosen as "newest" although it is three hours older.

The decision "show the latest copy" (§2.2 Case A) is therefore unreliable in any team that spans time zones.

*Fix*: parse with `datetime.fromisoformat`, normalise to UTC and compare datetimes. Emit dates in UTC `Z` everywhere (`%aI` → convert, or use `--date=format-local:` with `TZ=UTC`). Consider committer date (`%cI`) instead of author date, since rebases and cherry-picks keep old author dates.

---

## 3. Major

### M1. A pinned `--ref` that does not exist silently scans `master` **[verified]**
`github.py:97-107` tries `(branch, "master", "main")` in turn. With `--ref no-such-ref`, the tree request gets 404 and the scan quietly uses `master`, reporting skills from a different revision. `get_default_branch` also returns `"main"` on any non-200, non-404 answer (401, 5xx).

*Fix*: when `ref` is set explicitly, a 404 means exit 2 ("ref not found"). The fallback list is only acceptable when the default-branch lookup failed, and even then it should be reported as a warning in the result.

### M2. Truncated trees are ignored **[verified by grep]**
`remote.py:120` discards `_is_truncated`. For large repositories, and JetBrains monorepos are exactly the target, GitHub truncates the recursive tree and skills are lost with no warning. Plan §2.4 requires a fallback walk and a warning. The fake transport has a `simulate_truncated_tree` flag, but no test uses it.

### M3. Local and remote scans give different results **[verified]**
The same layout, scanned locally and through the (fake) GitHub API:
- **Remote reads companion files only with a listed extension** (`remote.py:21-36`). Local reads every non-binary file up to 1 MB. `scripts/install` (no extension) containing `rm -rf /` → SEC-002 locally, **nothing remotely**. The list also misses `.zsh`, `.ps1`, `.rb`, `.kts`, `.kt`, `Makefile` and `Dockerfile`.
- The content hashes are built from different file sets, so `identical` in duplicate refs can disagree between modes.

The local/remote parity test promised in plan §2.1 does not exist yet.

*Fix*: use the same file selection in both modes: size from the tree, a NUL-byte check after download, and a shared deny-list of binary extensions. Add the parity test as a parametrised fixture over every layout.

### M4. A skill at the repository root pulls in the whole repository **[verified]**
For a root `SKILL.md`, `available_files` is **every file in the repo**:
- **Remote** (`remote.py:166-167`): every text file gets downloaded. That was 30 extra raw requests in the check; a monorepo would need thousands.
- **Local** (`local.py:37`): the whole tree is walked and read into memory.

Nested skills have the same problem at a smaller scale. A parent skill's file set includes its children's files, so every finding in a child is **reported twice**, once under the child and once under the parent **[verified]**.

*Fix*: when collecting a skill's files, stop at subdirectories that contain their own `SKILL.md`. For a root skill, consider limiting the set to files referenced from `SKILL.md` plus conventional folders (`scripts/`, `reference/`, `assets/`).

### M5. The web UI ignores `rules`, `ignore` and `fail_on` **[verified]**
`web.py:117` builds one shared `Scanner()` with default options. `start_scan` passes only `ref` and `include_test_data`. A request with `ignore: ["SEC-003"], rules: "schema"` still returns `SEC-003`. The UI sends `fail_on`, but the server drops it. The PASS/FAIL badge uses `sk.valid` (`web.py:332`), which ignores both `fail_on` and the test-data exemption: a broken test-data skill shows **FAIL** in the web UI but passes in the CLI.

*Fix*: build a `Scanner` per request from the request fields. Validate them with `Literal[...]` types, which give 422 for free. Return the per-skill pass state computed by `is_passing(fail_on, include_test_data)` in the JSON. The plan's parity test (same JSON from web and CLI) would have caught this.

### M6. Cancelling a finished scan discards its result **[verified]**
`ScanJob.cancel()` (`web.py:76-79`) sets `status = "cancelled"` unconditionally. A `DELETE` after completion turns a finished scan into "cancelled", and `GET` then returns 400. Worker-side status writes race with it too.

*Fix*: cancelling is valid only while the job is `queued`/`running`; otherwise return 409. Guard status transitions with a lock.

### M7. Web jobs have no concurrency limit, no queue and no eviction **[inferred from code]**
Every `POST` starts a new daemon thread. Plan §3.2 asked for one concurrent scan and a queue shown in the status bar. `JobManager.jobs` grows forever, and each entry holds full `ScanResult` objects, including companion file contents that `exclude=True` hides from JSON but not from memory.

*Fix*: a single worker with a `queue.Queue`, a "queued: position N" event, and a small LRU of finished jobs (e.g. 20). Drop `companion_contents` after the rules have run.

### M8. The SPEC still describes cloning **[verified by grep]**
`SPEC.md:89` ("The scanner clones/fetches the repository into a temporary workspace") and `SPEC.md:305` ("shallow/temporary clone") contradict the new §1 and the decision "no clone, ever". `AGENTS.md` requires the SPEC to change together with the code.

### M9. Layout fixtures are invented, and the network test checks a different repo **[verified]**
- The `tests/fixtures/layouts/{mps,koog}` trees are synthetic (`plugins/mps-core/resources/skills/editor-ops`, `src/test/resources/skills/broken-test-fixture`). Plan milestone 4 (one API scan of the real MPS and koog repos, then freeze minimal fixtures) was skipped.
- The only `network` test scans **JetBrains/kotlin** on the default branch, not pinned to a SHA. It asserts an exact count ("6 skills") that will drift, and it checks text output.
- Locally it failed with exit 2 on the unauthenticated rate limit. On CI it depends on `secrets.GITHUB_TOKEN`.

*Fix*: add one pinned test each for MPS and koog, asserting origins and duplicate groups rather than exact text. Rebuild the fixtures from what the real repos contain.

---

## 4. Minor

1. **`.junie` is still in `IGNORED_DIRS`** (`local.py:25`), so `.junie/skills/*` is never found locally **[verified]**. Meanwhile `classify_origin` lists `.junie` as agent config, and remote discovery does find those skills. Another local/remote difference.
2. **CLI progress line is not escaped** (`cli.py:150`: `f"[dim]⟳ {event.message}[/dim]"`). Messages contain repository paths, so a directory named `[/dim]` in a remote repo raises `MarkupError`, and an interactive scan exits 2. Use `rich.text.Text` or `escape()`.
3. **CSP allows `'unsafe-inline'` scripts** (header and `<meta>`, `web.py:30,122`). With several `innerHTML` sinks (`web.py:364,378,390`), escaping all goes through one hand-written `escapeHtml`. Move the script to `/static/app.js`, drop `'unsafe-inline'` for `script-src`, and switch the remaining sinks to `textContent`/`createElement`. The plan's XSS regression test is present at API level only. The DOM check needs the optional browser test.
4. **`/api/health` always reports `rate_limit_remaining: null`**, because it creates a fresh `GitHubClient` that has never made a request. Scanner-level events (`RULES`, `DONE`) also carry `null`, because `Scanner.scan` is not given the `gh_client` that discovery creates. The status bar's API budget therefore disappears after the download stage. Create the client once per scan and pass it down, or call `GET /rate_limit` for health.
5. **Status bar is missing parts of the plan**: elapsed time, the expandable event log, a Retry button, and the queued state. On `eventSource.onerror` the connection is closed and the UI stays "running" forever with the Scan button disabled. The first-introduced commit is not shown, only `updated_date`.
6. **Local path rejected with 422 instead of the planned 403**, and the only check is "is it a GitHub URL". With `--allow-local`, any string, such as `ssh://gitlab…`, is accepted and fails later in the worker.
7. **`get_directory_last_commit` ignores uncommitted changes.** A dirty working copy is newer than its last commit, but the plan's mtime fallback applies only when there is no commit at all.
8. **The `Link` pagination and rate-limit fallback paths are untested.** The fake transport never sends a `Link` header, and `_request` falls back to unauthenticated calls on any 401/403. With a revoked token, a private repo is then reported as "not found" and the real cause is hidden. The rate-limit message always says "set GITHUB_TOKEN", even when a token is set.
9. **Provenance semantics changed quietly.** Remote `commit` is now the oldest commit touching the skill **directory**, while local `commit` is still the add of `SKILL.md`. The two can differ when the directory existed before the manifest. Pick one meaning and state it in the SPEC.
10. **`serve` without the `web` extra** ends in an `ImportError` traceback. Catch it and print `pip install 'skill-atlas[web]'`. `fastapi`/`uvicorn` are listed both in `[project.optional-dependencies].web` and in the dev group. That works, but put a comment on it or use `uv sync --extra web` in CI instead.
11. **Duplicate code**: `_calculate_content_hash` exists in both `local.py` and `remote.py`, and the `emit()` helpers are copied between `scanner.py` and `remote.py`. The fallback `parse_info` dict appears three times. The plan asked for one shared `Skill` builder for both paths, which would also enforce M3.
12. **`pythonpath = ["src", "."]`** in `pyproject.toml` hides packaging mistakes, because tests import from the source tree instead of the installed package. `uv sync` already installs the package in editable mode, so `"."` looks unnecessary.

---

## 5. Plan conformance

| Plan item | Status |
|---|---|
| CI matrix, ruff pin, DoD in `AGENTS.md` | Done |
| Test harness (`make_repo`, fake GitHub, CLI runner) | Done |
| Clone path removed, GitHub-only remote, exit 2 for other hosts | Done |
| Pagination / auth for raw / rate-limit error / `--ref` | Partly done: truncation ignored (M2), bad ref falls back silently (M1) |
| Local ↔ remote parity test | Missing (M3) |
| Case A: duplicates, newest shown, `DSC-001` | Done, but with C2, C3, C4 |
| Case B: test data non-blocking | Done in the CLI; the web badge is wrong (M5) |
| Case C: product origin | Done |
| Layout recon against the real MPS/koog | Skipped (M9) |
| Progress events, CLI status line | Done (minor #2) |
| Web: API, SSE, status bar | Done, but with C1, M5–M7 and minor #3–#5 |
| SPEC updated with the code | Partly done (M8) |

---

## 6. Suggested fix order

1. **C1**: lock down the web server (remove CORS, host check, per-process token). It is small and closes the only remotely exploitable issue.
2. **C2, C3, C4**: audit every copy, narrow what counts as a duplicate, compare dates as UTC datetimes. Add the three repros from this review as tests.
3. **M5, M6**: a scanner built per request, and cancel semantics. Add the planned web↔CLI JSON parity test.
4. **M1, M2, M3, M4**: remote correctness and the local/remote parity test.
5. **M8, M9**: SPEC cleanup, real-repo recon, and pinned network tests for MPS and koog.
6. Then M7 and the minor items.
