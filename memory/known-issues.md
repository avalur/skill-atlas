# Known Issues & Backlog

This document captures verified findings and improvement areas identified during code reviews (specifically `claude-review-iteration-2-followup.md`) to be addressed in subsequent iterations.

## 1. Security Vulnerabilities
- **[C1] Stored XSS in Similar Skills panel**:
  - `web.py` creates inline click handlers with `onclick="filterByKeyword('${escapeHtml(...)')"` in the Similar panel. HTML entity escaping decodes inside attribute values, enabling script injection if a hostile repository contains a malicious skill name.
  - *Target Fix*: Move script to dedicated static file, remove `'unsafe-inline'` from CSP, and bind event listeners via `addEventListener` with DOM element creation.

## 2. Architecture & Scanner Optimizations
- **[M1] Implicit `gh` CLI token escalation**:
  - `GitHubClient` automatically picks up `gh auth token`, granting access to private repositories without explicit user opt-in. `/api/health` queries rate-limits on every page hit.
  - *Target Fix*: Make CLI token resolution explicit/opt-in, and cache health endpoint responses.
- **[M2] Root-level skill repository downloads**:
  - If `SKILL.md` is placed at the root of a repository, the scanner currently attempts to download all files.
  - *Target Fix*: Restrict root skill companion collection to conventional folders (`scripts/`, `reference/`, `assets/`) and explicitly referenced links.
- **[M3] Tree truncation visibility**:
  - Truncated trees emit progress events but do not persist warnings into `ScanResult.warnings`.
  - *Target Fix*: Add `warnings: list[str]` to `ScanResult` and display in reporters.
- **[M5] Quadratic similarity comparison**:
  - Similarity pairwise comparison runs $O(n^2)$ `SequenceMatcher` calls on every web request.
  - *Target Fix*: Inverted index on tokens to prune candidate pairs, score precomputation, and per-scan cache.

## 3. Minor Polish Items
- `SEC-002` regex update: add trailing slash support for `rm -rf ~/` and `rm -rf $HOME/`.
- `Origin` header validation: pin exact `http://{host}:{port}` rather than wildcard port prefix.
- Untracked sandbox runners: track or ignore `sbx-claude.sh` and `sbx-junie.sh`.
