# Development Workflows & Standards

This document formalizes the operational protocols, git conventions, and quality gates enforced in `Skill Atlas`.

## 1. Language & Communication Policy
- **Interactive User Communication**: **Russian**. All conversational replies, status updates, problem analyses, and design discussions with the user are in Russian.
- **Repository Artifacts**: **Strictly English**. Code, docstrings, inline comments, specifications, memory documents, READMEs, PR titles/descriptions, and git commit messages must be in English.

## 2. Git & Pull Request Protocol
Direct pushes to `main` are **strictly prohibited**. Every change follows the PR lifecycle:

1. **Dedicated Branch**:
   ```bash
   git checkout -b <prefix>/<short-description>
   # Prefixes: feat/, fix/, docs/, refactor/, test/
   ```
2. **Local Pre-Flight Checks**:
   Always run and verify:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```
3. **Commit with Junie Co-Author**:
   When committing changes, attach the Junie co-author trailer:
   ```bash
   git commit -m "feat: description" --trailer "Co-authored-by: Junie <junie@jetbrains.com>"
   ```
4. **Push & Open Pull Request**:
   ```bash
   git push -u origin <branch-name>
   gh pr create --title "type(scope): concise title" --body "Concise summary of changes and verification"
   ```
5. **CI Verification**:
   Monitor GitHub Actions CI checks (`ubuntu-latest` and `macos-latest` on Python 3.11 and 3.13):
   ```bash
   gh pr checks
   ```
   If red, inspect logs with `gh run view --log-failed`, resolve issues, and push again.
6. **Merge**:
   Merge only after green CI and explicit confirmation:
   ```bash
   gh pr merge <pr_number> --merge
   git checkout main && git pull origin main
   ```

## 3. Definition of Done (DoD)
A task is considered complete only when:
- [x] All unit and integration tests pass locally (`uv run pytest`).
- [x] Ruff linter and formatter checks are clean.
- [x] Spec (`SPEC.md`) and memory (`memory/`) are updated in the same change when applicable.
- [x] Feature branch pushed and PR opened via `gh pr create`.
- [x] CI checks pass on GitHub Actions across the full OS/Python matrix.
- [x] Pull Request is cleanly merged into `main`.

## 4. Multi-Agent Worktrees & Sandboxing
- `sbx-claude.sh <name>` and `sbx-junie.sh <name>` scripts provision isolated git worktrees at `../<name>` with centralized model proxy credentials.
- Worktrees like `filter` and `similar` allow concurrent agent development without working directory conflicts.
- Always check `git worktree list` when inspecting repository state across sessions.
