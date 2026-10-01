# Known Issues & Backlog

This document captures verified findings, resolved review items, and potential future improvements for `Skill Atlas`.

## 1. Resolved Review Items (`claude-review-iteration-2-followup.md`)
- **[C1] Stored XSS in Similar Skills panel**: Resolved. Replaced inline HTML string interpolation and inline `onclick` handlers with safe DOM element creation (`createElement`, `appendChild`) and direct event listener binding.
- **[M1] `gh` CLI token escalation & health rate-limit**: Resolved. Token lookup is now cached, and the `/api/health` endpoint caches rate limit responses (TTL: 30s) to avoid burning API quota on frequent frontend polls. An informative status bar hint is displayed when no token is active.
- **[M2] Root-level skill repository downloads**: Resolved. Restricted companion file discovery for root-level `SKILL.md` to standard directories (`scripts/`, `reference/`, `assets/`, `docs/`, `bin/`) and explicit links found in markdown body, preventing runaway file downloads.
- **[M3] Tree truncation visibility**: Resolved. Added `warnings: list[str]` to `ScanResult`, ensuring repository tree truncation (>100k files) is reported in JSON and terminal outputs and triggers a non-zero exit code when `--fail-on warn` is set.
- **[M4] Real-repository layout integration tests**: Resolved. Added pinned-SHA network integration tests for MPS and Koog in `tests/integration/test_network.py` with graceful quota skip handlers.
- **[M5] Quadratic similarity comparison**: Resolved. Implemented `_SkillFeatures` token precomputation, unpromising pair pruning, and per-scan similarity result caching in `ScanJob`.
- **[Bug] Client-wide SAML fallback**: Resolved. A SAML 403 on one target (e.g. `JetBrains/kotlin`) used to switch the shared `GitHubClient` to anonymous mode for all later targets of a multi-repository scan, exhausting the 60 req/h anonymous quota. The fallback is now tracked per owner; regression test `test_remote_saml_fallback_is_scoped_to_one_owner`.
- **Minor Polish Items**:
  - Enhanced `SEC-002` regex with trailing slash and glob support (`rm -rf ~/`, `rm -rf $HOME/*`).
  - Added port pinning in Origin header middleware (`http://{host}:{port}`).
  - Added CLI `:sample` target and `--sample` flag for fast local fixture auditing.
  - Added test-data detection for `integration-tests?` directories.

## 2. Future Improvements Backlog
- **Product research candidates** (`research/product-research.md`, 2026-10-01): skill lineage (origin + copies), org-wide inventory with change alerts, SARIF/PR annotations, pre-install trust card (recommended for the mockup), evasion-resistant rules (hidden Unicode, padding, context-file writes). Each has a primary metric and a guardrail in the document.
- **GitLab & Bitbucket Remote Discovery**: Extend remote discovery engine to support GitLab and Bitbucket REST APIs using the same zero-clone tree inspection approach.
- **Custom Rule Plugins**: Allow loading user-defined Python validation rules dynamically from a local configuration directory.
- **Similarity Visualization**: Add an interactive graph view to the Web UI connecting similar skills across repositories.
