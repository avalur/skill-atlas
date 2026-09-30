# AGENTS.md — AI Agent Guidelines (Skill Atlas)

## Project Overview
`Skill Atlas` (`skill-atlas`) is a command-line interface (CLI) tool for discovery, structural validation, and static security auditing of AI Agent Skills.

## Language & Communication Policy
- **User Communication**: Russian (as requested by the user during interactive sessions).
- **Repository Artifacts**: Strictly English for all code, comments, documentation, commit messages, specifications, and issues.

## Shared Memory Policy
To maintain continuity and collective intelligence across stateless agent sessions:
- **ALWAYS read `memory/` before a task**: Inspect `memory/README.md` and relevant memory documents (`architecture.md`, `workflows.md`, `gotchas.md`, `rules-and-skills.md`, `known-issues.md`) before analyzing or modifying code. Never start a task without checking what we previously learned.
- **ALWAYS update shared memory with the `shared-memory` skill**: Whenever you introduce architectural changes, resolve hard-learned gotchas, alter workflows, or complete major tasks, update the corresponding files in `memory/` following the guidelines in `.claude/skills/shared-memory/SKILL.md`.

## Tech Stack
- **Language**: Python >= 3.11
- **Package Management & Build**: `uv` (Fast Python package installer and resolver)
- **CLI Framework**: `typer` (with `rich` for formatted output)
- **Data Models & Validation**: `pydantic` v2
- **Markdown & Frontmatter Parsing**: `python-frontmatter` / `pyyaml`
- **Testing**: `pytest`
- **Linting & Formatting**: `ruff`

## Repository Structure
```text
skill-atlas/
├── AGENTS.md              # Instructions and conventions for AI agents
├── README.md              # Project overview and quickstart
├── SPEC.md                # Current iteration specification (CLI MVP)
├── pyproject.toml         # Project manifest and dependencies (uv)
├── .github/
│   └── pull_request_template.md # PR template with mandatory demo video section
├── memory/                # Shared project memory across AI agent sessions
│   ├── README.md          # Index and guide to shared memory
│   ├── architecture.md    # System architecture, engine pipeline, and Web UI
│   ├── workflows.md       # Git PR workflow, DoD, CI matrix, and policies
│   ├── gotchas.md         # SAML SSO, path resolution, companion files, rate limits
│   ├── rules-and-skills.md# Schema, security, and discovery rule taxonomy
│   └── known-issues.md    # Review findings and pending improvements
├── .claude/
│   └── skills/
│       └── shared-memory/ # Skill for maintaining project shared memory
│           ├── SKILL.md
│           └── scripts/
│               └── verify_memory.py
├── src/
│   └── skill_atlas/       # Package source code
│       ├── __init__.py
│       ├── cli.py         # CLI entrypoint (Typer commands)
│       ├── models.py      # Pydantic models (Skill, Finding, ScanResult)
│       ├── scanner.py     # Scan orchestrator
│       ├── git/           # Git repository ingestion and commit provenance
│       ├── discovery/     # Skill discovery across directories and repos
│       ├── parsers/       # SKILL.md and metadata parsing
│       ├── rules/         # Validation rules (schema, security)
│       ├── similarity.py  # Similarity calculation engine
│       ├── web.py         # FastAPI server and Web UI
│       └── reporters/     # Result reporting (console, json)
└── tests/                 # Tests (unit, integration, fixtures)
    ├── test_scanner.py
    └── fixtures/          # Skill test fixtures (valid, vulnerable)
```

## Standard Development Commands
- Install dependencies: `uv sync`
- Run CLI: `uv run skill-atlas --help`
- Scan directory or repo: `uv run skill-atlas scan ./skills` or `uv run skill-atlas scan https://github.com/org/repo.git`
- Start local web UI: `uv run skill-atlas serve`
- Run skill map (heuristic): `uv run skill-atlas map ./skills`
- Run skill map (Claude AI): `uv run skill-atlas map ./skills --ai`
- Run skill map (TypeSafe Jev): `uv run skill-atlas map ./skills --jev`
- Run tests: `uv run pytest -v`
- Run visual regression tests: `uv run pytest tests/visual`
- Update golden visual baselines: `UPDATE_BASELINES=1 uv run pytest tests/visual`
- Run opt-in real GitHub API tests: `uv run pytest -m network`
- Run linter: `uv run ruff check .`
- Run formatter check: `uv run ruff format --check .`
- Format code: `uv run ruff format .`

## Specs
Read `./SPEC.md` first. Update it in the same change as the code.

## Tests
Integration tests for every case in the spec (every rule, every CLI option, every exit code, every corner-case layout in SPEC §3.3).

## Git & Pull Request Workflow
- **Branching Policy**: Never commit or push directly to `main`. Every change (feature, bugfix, refactoring, doc update) must be developed in a dedicated branch (e.g. `feat/...`, `fix/...`, `docs/...`).
- **Pull Requests**: Open a pull request against `main` using `gh pr create` adhering to `.github/pull_request_template.md`. Feature PRs must always include a demo video / recording illustrating the feature.
- **Verification & CI**: Ensure all local tests and linter checks pass before pushing (`uv run pytest && uv run ruff check . && uv run ruff format --check .`). Verify CI checks are green on the Pull Request.
- **Merge**: Merge to `main` only via Pull Request after CI passes and user approval.

## Definition of Done
- All tests pass locally: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`
- Feature demo video / recording attached in the PR description (mandatory for all feature PRs)
- Changes committed and pushed to a dedicated feature branch (never push directly to `main`)
- Pull Request created against `main` via `gh pr create` following `.github/pull_request_template.md`
- CI is green for the Pull Request
- Red CI: read the logs (`gh run view --log-failed`), fix, push again

## Conventions for AI Agents
1. **Rule Modularity**: Every validation or security rule must be an isolated class/function with a unique identifier (e.g., `SEC-001`, `SCH-002`), a severity level (`INFO`, `WARN`, `ERROR`), a clear message, and an actionable remediation suggestion.
2. **Type Safety**: Strict typing across the codebase (Python type hints, Pydantic models for all structured entities).
3. **Determinism & Exit Codes**:
   - `0` — Scan completed successfully, no blocking issues found.
   - `1` — Errors detected at `ERROR` level (or `WARN` if `--fail-on warn` is specified).
   - `2` — CLI invocation error / invalid arguments / runtime crash.
4. **Git Provenance**: When scanning Git repositories (local or remote), always record the repository name, skill name, description, and the commit hash/date where the skill first appeared.
5. **Test Fixtures**: Every new schema or security rule must include a minimal fixture in `tests/fixtures/` covering both positive and negative cases.
6. **Output Format Support**: Always maintain structured JSON export capabilities alongside rich terminal output for CI/CD pipelines and agent workflows.
7. **Pull Request Workflow**: All new changes, fixes, and features must be submitted via Pull Requests from a dedicated feature branch adhering to `.github/pull_request_template.md`. Direct pushes to `main` are strictly prohibited. Feature PRs must always include a demo video / recording demonstrating the new capabilities.
8. **Shared Memory Maintenance**: Always read `memory/` before starting a task to understand project context and history. Always update `memory/` using the `shared-memory` skill whenever new patterns or decisions emerge.
9. **Visual Regression & Baseline Maintenance**: When modifying the Web UI (`src/skill_atlas/web.py`) or CSS, run visual tests (`uv run pytest tests/visual`). If visual changes are intentional, update golden baselines using `UPDATE_BASELINES=1 uv run pytest tests/visual` and commit the updated baseline images (`tests/visual/baselines/*.png`) alongside code in the PR branch.
