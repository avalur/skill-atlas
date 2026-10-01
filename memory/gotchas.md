# Hard-Learned Gotchas & Edge Cases

This document details non-obvious failure modes, security pitfalls, and edge cases discovered during development.

## 1. GitHub API SAML SSO & Anonymous Fallback
- **The Problem**: GitHub tokens obtained via `gh auth token` or `GITHUB_TOKEN` fail against repositories owned by SAML SSO-enforced organizations (e.g. `JetBrains/kotlin`). The API responds with `HTTP 403 Forbidden` and header `x-github-sso: required; url=...`.
- **The Paradox**: The repository is completely public, but an authenticated token without SSO authorization is rejected.
- **The Solution**: In `src/skill_atlas/git/github.py`, when a request encounters `403` with `x-github-sso` (or `401`), it automatically retries **anonymously** (stripping the `Authorization` header).
  - For public repositories, anonymous requests succeed (`HTTP 200`). Subsequent requests for the scan session stay unauthenticated.
  - For private repositories, anonymous requests return `404`, and the scanner surfaces the SAML SSO authorization URL to the user.

## 2. Rule `SCH-006` and Multi-Level Path Resolution
- **The Problem**: In monorepos (e.g. `JetBrains/kotlin`), skills located at `.claude/skills/<name>/SKILL.md` reference files far outside their local folder:
  - Relative upward references: `../../../compiler/fir/analysis-tests/AGENTS.md`
  - Root-anchored references: `/analysis/docs/contribution-guide/api-development.md`
- **Initial Flaw**: `SCH-006` previously checked only `skill.available_files` (files inside the skill's own subfolder), causing 4 false-positive `Broken Link Reference` errors and failing the scan.
- **The Solution**:
  - `Skill` model carries `repo_files: list[str]` (excluded from JSON serialization).
  - `discovery/local.py` gathers repo files via `git ls-files --cached --others`.
  - `discovery/remote.py` gathers repo files from the GitHub recursive git tree.
  - `SCH-006` resolves `..` paths and leading `/` paths against the repository root, while preventing directory traversal outside the repository boundary.

## 3. Companion Script Security Auditing
- Skills often package shell or python scripts (e.g. `scripts/run.sh`).
- Running rules solely on `SKILL.md` allows prompt injections, tokens, or dangerous commands (`rm -rf /`) in companion scripts to go undetected.
- Both local and remote discovery must collect all text companion files under 1 MB (skipping binary files defined in `BINARY_EXTENSIONS`).
- Rules `SEC-001` through `SEC-005` iterate over both `SKILL.md` and all companion files.

## 4. Timezone-Aware Commit Comparison
- Commit dates from Git or GitHub API contain diverse timezone offsets (`+02:00`, `-05:00`, `Z`).
- Comparing raw ISO strings alphabetically yields incorrect results (e.g. `12:00+02:00` vs `11:00Z`).
- Always parse timestamps into UTC `datetime` objects before sorting or picking the newest version for deduplication.

## 5. Duplicate Origin Isolation (Case A vs Case B)
- **Case A (`agent-config`)**: Skills duplicated between `.claude/skills/` and `.agents/skills/` are true mirrors. They are deduplicated, showing the newest copy, with `DSC-001` raised if copies are out of sync.
- **Case B (`product`)**: Multiple plugins in a monorepo may contain distinct skills with the same name (e.g. `plugins/git4idea/.../git-helper` vs `plugins/hg4idea/.../git-helper`). These must **never** be merged.

## 6. Rich Terminal Markup Escaping
- Manifest strings often contain brackets like `[ERROR]` or `<skill-name>`.
- Rich console rendering parses unescaped brackets as style tags, causing rendering crashes or garbled text.
- Always wrap dynamic text with `rich.markup.escape()` before console output.

## 7. GitHub Organization Scanning Pitfalls
- **Ambiguous owner URLs**: `https://github.com/<name>` can be an org, a user, or a reserved GitHub route. `parse_org_target()` excludes a frozen set of reserved paths (`settings`, `orgs`, `marketplace`, `login`, `search`, ...) and anything ending in `.git`. Two-segment repo URLs must be handled by the normal remote path, so org detection must run BEFORE remote detection in `scanner.scan`.
- **Org vs user endpoint**: `GET /orgs/{org}/repos` returns 404 for user accounts; always fall back to `GET /users/{org}/repos` before declaring the login not found.
- **Pagination stop condition**: Do not rely on a `Link` header alone in mocks; stop when a page returns fewer than `per_page` items (and guard `max_repos`). Requesting `per_page>100` is silently capped by GitHub to 100 — clamp locally so page-size math stays correct.
- **Primary vs secondary rate limits**: `GitHubClient._request` raises `RateLimitError` only when `X-RateLimit-Remaining==0` or the body mentions "rate limit". Secondary limits appear as HTTP 429 or 403 with a `Retry-After` header and must be retried via `_request_with_retry` (bounded, capped sleep) — do NOT let them raise immediately.
- **Thread safety**: `httpx.Client` is safe for concurrent requests across threads; reuse one shared client with an enlarged `httpx.Limits` pool. A `RateLimitError` raised in any worker must set the shared `cancel_event` and be re-raised after the pool drains so the CLI returns exit code 2.
- **Offline testing**: `uv sync` fails offline (blocked `pillow` download) and neither system python nor `.venv` ships `httpx`/`pytest`, so `tests/test_org_scan.py` runs only in CI. Validate locally with `py_compile` and the bundled ruff binary.
