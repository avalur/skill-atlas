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

## 🚀 Features (v0.2.0)

- **Git Repositories & Discovery**:
  - Scanning local directories and local Git repositories.
  - Remote Git repository ingestion directly via GitHub REST API (zero disk waste, no cloning).
  - Pinned branch/tag/commit reference support (`--ref`).
- **Layout Intelligence & Provenance**:
  - **Origin Classification**: Automatically labels skills by category (`agent-config`, `product`, `test-data`, `standalone`).
  - **Deduplication & Stale Copy Detection (`DSC-001`)**: Groups duplicate copies across `.claude`, `.agents`, etc., displays the newest copy, and alerts if copies have drifted.
  - **Test Data Isolation**: Classifies test fixtures and excludes their findings from blocking exit codes unless `--include-test-data` is specified.
  - **Git Provenance**: Automatically resolves the introductory commit and the latest update commit and timestamp for each skill.
- **Specification & Security Audit**:
  - Schema consistency (`SCH-001` through `SCH-006`).
  - Static security auditing for exposed secrets, destructive commands, unsafe pipes, sensitive paths, and prompt injection (`SEC-001` through `SEC-005`).
- **Heuristic Similarity Discovery (No AI)**:
  - Find similar and overlapping skills using fast, transparent heuristics (`skill-atlas similar`).
  - Multi-feature composite scoring (name token overlap, description TF-IDF/cosine similarity, shared tags, prompt structure, companion script names).
  - Human-readable match reasons and feature breakdown.
- **Interactive Local Web Interface**:
  - Launch an interactive local catalog with `skill-atlas serve` (supporting `--reload` for development).
  - Pinned real-time status bar reporting exact operations, progress, and rate limit budget.
  - Light and dark theme switcher with system preference detection and localStorage persistence.
  - Interactive "Find Similar" tool with threshold controls, keyword and status filters, and instant JSON download.
- **Reporting & CI/CD**:
  - Formatted terminal output via Rich.
  - Machine-readable structured JSON export.
  - Deterministic exit codes (`0`, `1`, `2`).

---

## ⚡ Quickstart

```bash
# Install dependencies
uv sync

# Scan local directory or repository
uv run skill-atlas scan ./skills

# Scan remote GitHub repository without cloning
uv run skill-atlas scan https://github.com/JetBrains/kotlin

# Find similar skills in a repository or folder
uv run skill-atlas similar ./skills --threshold 0.5

# Launch local interactive Web UI
uv run skill-atlas serve
```

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
