# Skill Atlas

[![CI](https://github.com/avalur/skill-atlas/actions/workflows/ci.yml/badge.svg)](https://github.com/avalur/skill-atlas/actions/workflows/ci.yml)

> CLI tool for discovery, structural validation, and static security audit of AI Agent Skills.

## 🎯 Project Purpose

AI agents increasingly rely on extensions and capabilities (Agent Skills) structured as folders containing a `SKILL.md` specification, instructions, scripts, and manifests. 
As the number of skills grows, key challenges emerge:
1. **Validity and Consistency**: Missing required fields, broken script links, invalid YAML frontmatter.
2. **Security**: Leaked API keys and access tokens, potentially destructive shell commands (`rm -rf`, `curl | sh`), prompt injection attempts.
3. **Discoverability**: Vague or duplicate descriptions that prevent agents from routing and selecting the right tool.

`Skill Atlas` (`skill-atlas`) solves these problems by providing a fast, standalone static scanner CLI.

---

## 🚀 Planned Features (MVP / Iteration 1)

- **Git Repositories & Discovery**:
  - Scanning local directories and local Git repositories.
  - Remote Git repository ingestion (cloning remote URLs e.g. `https://github.com/...`).
  - Automatic skill discovery (locating `SKILL.md` manifests).
- **Provenance & Cataloging**:
  - Automatically captures the hosting repository name, skill name, and description.
  - Extracts the exact Git commit SHA and date when each skill was first introduced into the repository.
- **Specification & Schema**: Validation of frontmatter structure (`name`, `description`, `version`, resource references).
- **Security Audit (Level 1)**:
  - Detection of hardcoded secrets and API tokens (regex patterns).
  - Detection of dangerous shell patterns in companion scripts.
  - Basic checks for prompt injection and system prompt override patterns.
- **Reporting**:
  - Clear terminal summary with colored output (via `rich`) showing repository, skill name, description, commit, and audit status.
  - Structured `json` export for automated CI/CD pipelines, cataloging, and agent integrations.
- **Exit Codes**: Clean CI/CD integration (exit code `0` for clean, `1` for violations).

---

## 🛠 Tech Stack

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — fast Python package and environment manager
- Typer + Rich — modern CLI framework and terminal formatting
- Pydantic v2 — data model and schema validation
- Pytest — testing suite

---

## 📚 Documentation

- [SPEC.md](./SPEC.md) — Iteration 1 specification (CLI MVP).
- [AGENTS.md](./AGENTS.md) — Instructions, architectural conventions, and guidelines for AI agents.
