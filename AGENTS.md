# AGENTS.md — AI Agent Guidelines (Skill Atlas)

## Project Overview
`Skill Atlas` (`skill-atlas`) is a command-line interface (CLI) tool for discovery, structural validation, and static security auditing of AI Agent Skills.

## Language & Communication Policy
- **User Communication**: Russian (as requested by the user during interactive sessions).
- **Repository Artifacts**: Strictly English for all code, comments, documentation, commit messages, specifications, and issues.

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
- Run tests: `uv run pytest -v`
- Run opt-in real GitHub API tests: `uv run pytest -m network`
- Run linter: `uv run ruff check .`
- Run formatter check: `uv run ruff format --check .`
- Format code: `uv run ruff format .`

## Specs
Read `./SPEC.md` first. Update it in the same change as the code.

## Tests
Integration tests for every case in the spec (every rule, every CLI option, every exit code, every corner-case layout in SPEC §3.3).

## Definition of Done
- All tests pass locally: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`
- Pushed; CI is green for this commit
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
