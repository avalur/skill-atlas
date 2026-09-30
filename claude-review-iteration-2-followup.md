# Code Review: Skill Atlas at `e527a85` (follow-up to iteration 2)

**Date**: 2026-09-30
**Scope**: `main` at `e527a85`. That is PRs #2–#5 since the previous review (`838f87a`): fixes for `claude-review-iteration-2.md`, the new `similar` command with its web panel, and web UI filters and theming. 21 files, +2596/−172.
**Method**: Read the diffs and the new modules (`similarity.py`, the `web.py` server and JS, the `github.py` auth logic). Ran lint and the tests. Re-ran every repro from the previous review against the current code, and wrote new ones for the new code. Findings marked **[verified]** were reproduced by a run. The others come from reading the code.

---

## 1. Summary

The fix PR is solid:
- **Lint and tests**: `ruff check`/`format` are clean, and 104 offline tests pass.
- **CI**: green on every PR and on `main`.
- **Repro tests**: the scenarios from the last review are now regression tests (`test_case_a_vulnerable_stale_copy_is_audited`, `..._timezone_aware_newest_selection`, `..._distinct_product_skills_same_name_not_merged`, `test_remote_and_local_parity_script_without_extension`, `test_web_foreign_origin_rejected`, …).

Status of the previous findings, re-checked by hand:

| Previous finding | Status |
|---|---|
| C1 CORS / drive-by scans | **Fixed**: no CORS, `TrustedHostMiddleware`, `Origin` allow-list, per-process CSRF token. But see new C1 |
| C2 stale copies not audited | **Fixed** [verified]: the stale copy's SEC-001/SEC-003 are reported with its path, and the exit code is 1 |
| C3 distinct same-name skills merged | **Fixed** [verified]: two plugins stay separate, and SEC-001 is reported |
| C4 time-zone string comparison | **Fixed** [verified]: dates are compared in UTC |
| M1 bad `--ref` falls back to master | **Fixed** [verified]: `ValueError`, exit 2 |
| M2 truncated tree ignored | **Partly fixed**: a progress event only, see M3 |
| M3 local/remote file selection differs | **Fixed** [verified]: an extensionless script is flagged in both modes |
| M4 root skill pulls the whole repo | **Partly fixed**: nested children are excluded [verified], but a root skill still downloads every file, see M2 |
| M5 web ignores options | **Fixed**: a scanner per request, `Literal` validation |
| M6 cancel after completion | **Fixed**: 409 |
| M7 web queue / eviction | **Fixed**: one worker, LRU of 20 |
| M8 SPEC mentions cloning | **Fixed** |
| M9 invented layouts, unpinned network test | **Not addressed**, see M4 |
| minor #1 `.junie` ignored | **Fixed** [verified] |
| minor #2 CLI progress markup | **Fixed** (`escape()`) |
| minor #3 CSP `'unsafe-inline'` | **Not addressed**, and it now enables new C1 |

The new code brings one critical issue and several major ones:

| Severity | Count |
|---|---|
| Critical | 1 |
| Major | 5 |
| Minor | 8 |

---

## 2. Critical

### C1. Stored XSS in the Similar Skills panel **[verified]**
`web.py:717,719` builds inline handlers from skill names that come from the scanned repository's frontmatter:

```js
onclick="filterByKeyword('${escapeHtml(m.skill_a)}')"
```

`escapeHtml` turns `'` into `&#039;`, but the browser **decodes entities in attribute values before running the JS**. HTML escaping therefore does nothing inside a JS string in an attribute. A skill named

```yaml
name: "x');fetch('/api/scans',{method:'POST'});//"
```

produces this handler after HTML decoding (checked with `html.unescape`):

```js
filterByKeyword('x');fetch('/api/scans',{method:'POST'});//')
```

**Impact**: a user scans a hostile public repo and clicks a name in the Similar panel. Arbitrary script then runs in the `127.0.0.1:8765` origin. It can read the `CSRF_TOKEN` constant from the page and start scans that use the user's token, which now includes the implicit `gh auth token` (M1). That covers private repositories, and local paths when `--allow-local` is set. It can exfiltrate results by navigating to an attacker URL, which CSP does not block. This undoes the protection added for the previous C1.

*Fix*:
- Build these elements with `createElement`/`textContent`, and attach handlers with `addEventListener` and a closure over the value. Never put untrusted strings into inline JS.
- Remove `'unsafe-inline'` from `script-src`: move the script to `/static/app.js` and replace every `onclick=` attribute with a listener. That makes any remaining mistake of this kind non-exploitable.
- Add a regression test that asserts the served JS has no `onclick=` built from data, plus the optional browser test with a hostile skill name.

---

## 3. Major

### M1. The GitHub client silently uses the `gh` CLI token **[inferred from code]**
`GitHubClient.__init__` (`github.py`) runs `gh auth token` whenever `GITHUB_TOKEN`/`GH_TOKEN` is unset. Consequences:
- A `gh` token usually has broad `repo` scope. The web server now reaches **every private repo of the logged-in user** without the user configuring anything, which raises the stakes of C1.
- `/api/health` builds a new `GitHubClient` on **every page load**. Each load shells out to `gh` and calls `GET /rate_limit` with a 10 s timeout, so an offline page load can hang for 10 s.
- Tests running on a developer machine with `gh` logged in can pick up real credentials whenever a code path builds `GitHubClient()` without an explicit token.

*Fix*: make this opt-in (`--use-gh-auth`, or an explicit setting in the web UI), or at least log clearly which credential source is in use. Create the client once per process and cache the rate-limit result in `health`. In tests, force `token=""` / patch `shutil.which`.

### M2. A root-level skill still downloads the whole repository **[verified]**
Children are now excluded, but a `SKILL.md` at the repo root still collects every other file. In the check, 30 unrelated `src/*.py` files were downloaded through raw requests. Locally, the whole tree is walked and read. On a JetBrains-size monorepo, that means thousands of requests and a large memory footprint, and SEC rules run over the entire product source.

*Fix*: for a root skill, limit the file set to files referenced from `SKILL.md` plus conventional subfolders (`scripts/`, `reference/`, `assets/`). Add a test that counts raw requests.

### M3. Truncated trees still lose skills, and the warning disappears **[inferred from code]**
`remote.py:96-99` emits a progress event on truncation and carries on with the partial tree. The event is not part of `ScanResult`, so JSON/CI consumers never see it, and the CLI overwrites it on the next status line. Plan §2.4 asked for a targeted non-recursive walk as the fallback, and for a warning in the result. No test uses `simulate_truncated_tree`.

*Fix*: add `ScanResult.warnings: list[str]` and show it in both reporters. Do the fallback walk, or at least exit with a clear message under `--fail-on warn`.

### M4. The real-repository layout check is still missing **[verified]**
Unchanged since the previous review (M9):
- The only `network` test scans `JetBrains/kotlin`, is not pinned to a SHA, asserts an exact count ("6 skills") and matches on text output.
- The `mps`/`koog` fixtures are still synthetic.

Of the workshop's three corner cases, only the synthetic versions are covered.

### M5. Similarity is O(n²) with `difflib`, recomputed on every web request **[verified]**
`find_similar_skills` compares all pairs, and each pair runs `SequenceMatcher` on names and descriptions plus token cosine on bodies. Measured on synthetic skills: **100 skills: 2.1 s, 300 skills: 19.1 s.** The web endpoint `/api/scans/{id}/similar` recomputes on every call, and every threshold change and every "find similar" click is a call. It runs in the threadpool with no caching and no limit, so a few clicks on a large repo tie up the server.

*Fix*:
- Precompute token sets and vectors once per skill.
- Prune candidate pairs with an inverted index on name and description tokens, so only pairs that share a token are compared.
- Run `SequenceMatcher` only when the cheaper scores pass a floor.
- Cache the pairwise scores per `scan_id` and filter by threshold afterwards.

---

## 4. Minor

1. **`rm -rf ~/` and `rm -rf $HOME/` are not flagged** **[verified]**. `rm -rf ~`, `~/*` and `/` are. The trailing-slash form is the most common way this is written. Add both to the SEC-002 table test.
2. **The `Origin` allow-list accepts any port on localhost** (`web.py:886`: `startswith("http://localhost:")`). Any other local app, such as a dev server or a notebook, passes the origin check. The CSRF token still protects `POST`/`DELETE`, but `GET /api/scans/{id}` and `/similar` from that origin are allowed. Pin the exact origin `http://{host}:{port}` the server was started with. `testserver` should be allowed only in tests.
3. **`--host 0.0.0.0` does not work any more.** `TrustedHostMiddleware` accepts only `127.0.0.1`/`localhost`, so LAN clients get 400, while `run_server` still prints a "exposes to your local network" warning. Either drop the option or add the bind address to `allowed_hosts` explicitly.
4. **`--reload` ignores `--allow-local`**: `uvicorn.run("skill_atlas.web:create_app", factory=True)` calls the factory with no arguments.
5. **`similar` runs a full audit first.** `similar_command` runs every rule and downloads every companion file just to compare metadata. For remote targets that is the full API budget. Add a discovery-only mode to `Scanner` (skip rules and companion downloads).
6. **Similarity quirks**:
   - Two skills whose descriptions are both a placeholder (e.g. "TODO") get the 0.85 boost for "identical description".
   - `--skill` matches by substring of the path (`clean_q in s.path`) and silently takes the first hit, so `-s a` matches almost anything.
   - The web endpoint does not validate `threshold`/`top_k`, while the CLI does.
7. **The status bar is still missing items from plan §3.3**: elapsed time, event log, Retry button, and the "queued: position N" message. The server tracks `queued`, but never emits an event for it. On `eventSource.onerror` the UI stays in the running state.
8. **Untracked `sbx-claude.sh` / `sbx-junie.sh`** in the repo root. They contain no secrets (the key is fetched at run time), but they are neither committed nor ignored. Add them to `.gitignore`, or commit them under `scripts/` with a README note.

---

## 5. Suggested fix order

1. **C1**: remove the inline handlers and `'unsafe-inline'` scripts. It is small and closes a remotely triggerable script injection.
2. **M1**: make `gh auth token` opt-in and cache the health data. That limits the damage of any future web bug.
3. **M5**: prune and cache similarity before anyone points it at MPS.
4. **M2, M3**: remote correctness on large repos (root-skill scope, truncation warnings in the result).
5. **M4**: pinned network tests for the real MPS and koog layouts, which is the last open item of the workshop's corner-case task.
6. The minor items, starting with #1 (a one-line regex fix plus test).
