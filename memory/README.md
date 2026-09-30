# Shared Memory (`memory/`)

This directory serves as the persistent, shared memory for all AI agents and developers collaborating on the `Skill Atlas` project.

## Purpose
Agent sessions are inherently stateless or subject to context truncation. The files in `memory/` capture hard-earned knowledge, consensus decisions from previous discussions, architectural patterns, operational traps (gotchas), and known pending issues.

## Directives for AI Agents
1. **ALWAYS read `memory/` before starting any task**: Load context from relevant memory documents before planning or modifying code.
2. **ALWAYS update `memory/` using the `shared-memory` skill**: Whenever you introduce a new architectural decision, solve a non-trivial bug/gotcha, alter workflows, or complete a major iteration, update the corresponding files in `memory/`.
3. **Commit memory updates with code**: Keep memory in sync with codebase changes in the same Pull Request.

## Index of Memory Documents

| Document | Description |
|---|---|
| [architecture.md](architecture.md) | System components, hybrid remote/local discovery, scanner engine, Web UI server, and similarity algorithm. |
| [workflows.md](workflows.md) | Branching policy, Pull Request workflow, Definition of Done, testing strategy, language policy, and commit trailers. |
| [gotchas.md](gotchas.md) | Lessons learned: SAML SSO fallback, `SCH-006` repo-root path resolution, companion script auditing, rate limits, and worktrees. |
| [rules-and-skills.md](rules-and-skills.md) | Rule taxonomy (`SCH-001..006`, `SEC-001..005`, `DSC-001`), skill layout origins (`agent-config`, `product`, `test-data`), and similarity scoring. |
| [known-issues.md](known-issues.md) | Active review findings from code audits (XSS prevention, token opt-in, similarity caching) slated for subsequent fixes. |
