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

## 7. SAML Fallback Disables the Token for the Whole Multi-Target Scan
- **The Problem**: `Scanner.scan()` shares one `GitHubClient` across all targets. When one target returns `403` with `x-github-sso` (e.g. `JetBrains/kotlin` for a token that is not SSO-authorized for `jetbrains-enterprise`), the client sets `_auth_disabled = True`, and **every later target** in the same scan runs anonymously.
- **Symptom**: Scanning `JetBrains/kotlin` together with other repos exhausts the anonymous quota (60 req/h) and fails with "GitHub rate limit reached … configured token exhausted", although the token itself still has ~5000 requests left.
- **Workarounds**: SSO-authorize the token for the enterprise (GitHub → Settings → Applications → GitHub CLI → Organization access → Grant), list SAML-protected repos last, or demo with non-SAML repos (`cursor/plugins`).
- **Fix pending**: make the anonymous fallback per repository owner instead of per client (see `known-issues.md`).
