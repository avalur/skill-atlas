# Specification: Skill Atlas (`skill-atlas`) (Iteration 2: Tests, CI, Corner Cases & Web Interface)

**Specification Version**: 0.2.0  
**Status**: In Progress / Active Implementation  
**Target Release**: v0.2.0

---

## 1. Introduction and Goals

`Skill Atlas` (`skill-atlas`) is a static analysis and validation tool for AI Agent Skills.

With the growth of agent environments (Junie, Claude Code, OpenAI Codex, Cursor, etc.), skills are structured as standardized directories containing a `SKILL.md` manifest, instructions, and executable scripts.

### Key Goals for Iteration 2:
1. Complete CI harness (Ubuntu + macOS, Python 3.11/3.13) with deterministic integration tests.
2. Robust GitHub REST API remote ingestion (no `git clone`, handling pagination, rate limits, raw files, pinned refs).
3. Handling real-world repository layouts and corner cases:
   - Duplicates in `.claude`, `.agents`, etc.: display newest updated copy and detect stale copies (`DSC-001`).
   - Test data: classify test fixtures and avoid blocking exit codes unless `--include-test-data` is specified.
   - Product skills: distinguish skills bundled as product resources from agent configurations.
4. Core progress event streaming (`Stage`, `ProgressEvent`) providing real-time status updates.
5. Lightweight local web interface (`skill-atlas serve`) with real-time status bar and interactive catalog.
6. Multi-Repository Support with Search Query:
   - Multi-target ingestion across local directories and remote GitHub repositories in a single run via CLI arguments (`TARGETS...`), a targets file (`--targets-file / -T`), or the Web UI.
   - Audit-scoped search query (`--query / -q`) filtering skills prior to static rule evaluation to maximize scan throughput and minimize computation/network overhead.
   - Interactive multi-repository Web UI with multi-target input, dynamic repository faceted filter chips, and instant real-time search filtering.

---

## 2. Agent Skill Model & Provenance Metadata

In Skill Atlas, a skill is defined as a directory containing a `SKILL.md` file (at the top level or nested within a repository layout), enriched with provenance metadata from its hosting Git repository.

### Skill Entity Attributes:
- **`name`** (`str`): Skill identifier from `SKILL.md` frontmatter (or directory name fallback).
- **`description`** (`str`): Summary of what the skill does (extracted from YAML frontmatter).
- **`repo_name`** (`str | None`): Name of the repository (e.g. `owner/repo` or directory name for local repos).
- **`repo_url`** (`str | None`): Remote origin URL of the repository (if available).
- **`commit`** (`str | None`): Git commit hash (SHA) when this skill was first introduced into the repository.
- **`commit_date`** (`str | None`): Author date/timestamp (ISO 8601) of the introductory commit.
- **`updated_commit`** (`str | None`): Git commit hash (SHA) when the skill directory was last updated.
- **`updated_date`** (`str | None`): Author date/timestamp (ISO 8601) of the latest update.
- **`updated_source`** (`str`): Source of update metadata (`"git"` or `"mtime"`).
- **`origin`** (`str`): Origin classification (`agent-config`, `product`, `test-data`, `standalone`).
- **`duplicates`** (`list[DuplicateRef]`): References to other copies of this skill found in the repository.
- **`path`** (`str`): Path to the skill directory relative to the repository or scan root.
- **`version`** (`str | None`): Skill version from frontmatter.
- **`author`** (`str | None`): Author information if specified.
- **`tags`** (`list[str]`): Tags/categories from frontmatter.
- **`findings`** (`list[Finding]`): Structural and security findings detected during scan.

### `SKILL.md` Format:
The file consists of **YAML frontmatter** and a **Markdown body**:

```markdown
---
name: my-sample-skill
version: 1.0.0
description: A concise and clear description of what this skill does
author: Developer Name
tags:
  - git
  - automation
permissions:
  - filesystem:read
---

# My Sample Skill

Instructions for the agent on when and how to invoke this skill.
References to auxiliary scripts: [run.sh](scripts/run.sh).
```

### Skill Directory Structure:
```text
my-sample-skill/
├── SKILL.md            # Primary manifest and skill prompt (required)
├── scripts/            # Executable scripts (bash, python, etc.)
│   └── run.sh
└── reference/          # Supplementary documentation and schemas
    └── schema.json
```

---

## 3. Functional CLI Requirements

### 3.1. Discovery and Git Repository Ingestion
- **Target Ingestion**:
  - The CLI accepts one or more targets `TARGETS...` or a targets file `--targets-file / -T <path>`. Each target can be:
    - **Local Directory / Repository**: Path to a local folder or cloned Git repository. If the path is inside a Git repository, repository metadata and commit history are evaluated automatically.
    - **Remote Git Repository**: URL to a remote Git repository (e.g. `https://github.com/owner/repo.git`, `git@github.com:...`). The scanner scans the repository via the GitHub REST API and raw file downloads (without cloning), discovers skills, extracts provenance, and performs scanning. If a configured token encounters SAML SSO organization enforcement when accessing a public repository, the client automatically falls back to unauthenticated requests to complete the scan seamlessly.
    - **Single Skill Directory**: Path pointing directly to a directory containing `SKILL.md`.
  - **Multi-Target Ingestion**:
    - **Positional Arguments**: `skill-atlas scan TARGET1 TARGET2 ...` accepts multiple target directories or URLs. If no positional arguments and no `--targets-file` are provided, the target defaults to `.` (current directory).
    - **Targets File**: `--targets-file / -T <path>` reads repository paths and URLs from a text file, one per line. Lines starting with `#` (comments) and empty or whitespace-only lines are ignored.
    - **Target Merging & Normalization**: Targets provided via positional arguments and `--targets-file` are combined into an ordered list, normalized (stripped of whitespace and trailing slashes), and deduplicated while strictly preserving declaration order.
    - **Mixed Target Support**: The scanner seamlessly processes mixed workloads in a single run, routing local paths to local filesystem discovery and remote URLs to remote GitHub Tree API discovery.
    - **Validation & Error Handling**: If a specified `--targets-file` does not exist or contains no valid targets, or if an invalid argument is passed, the CLI produces an informative error message and exits with code `2`.
- **Cross-Repository Provenance & Deduplication Isolation**:
  - When scanning multiple repositories, skills with the same name across *different* repositories are treated as independent entities and are **never** deduplicated against each other.
  - Each skill preserves its respective `repo_name` (e.g. `org-a/skills` vs `org-b/skills`), canonical `repo_url`, and Git commit provenance.
  - Duplicate detection and stale copy checks (`DSC-001`) operate strictly within the boundary of each individual repository.
- **Deterministic Multi-Repository Ordering**:
  - Discovered skills across all repositories are sorted deterministically: primarily by `repo_name` ascending (treating empty/local targets consistently), and secondarily by `path` ascending.
- **Recursive Skill Discovery**:
  - All subdirectories containing a valid `SKILL.md` are discovered.
  - Standard utility and cache directories are ignored automatically: `.git`, `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.junie`.
- **Git Provenance Tracking**:
  - When skills are scanned inside a Git repository (local or remote), Skill Atlas extracts and retains:
    - **`repo_name`**: Extracted from remote origin URL (e.g. `owner/repo`), or repository directory name if offline.
    - **`repo_url`**: Canonical URL to the Git repository.
    - **`commit`**: The exact Git commit hash (SHA) when the skill (specifically `SKILL.md`) was first introduced to the repository (via `git log --diff-filter=A --follow --format="%H" -- <path>/SKILL.md`).
    - **`commit_date`**: The author timestamp of the introductory commit.

### 3.2. Built-in Rules for Iteration 1

Each rule is assigned a persistent identifier and a severity level:
- `ERROR` — Critical issue (blocks successful scan).
- `WARN` — Warning (potential issue or violation of best practices).
- `INFO` — Informational recommendation.

#### Group 1: Structure and Metadata (Schema Rules — `SCH`)
| Code | Level | Name | Description |
|---|---|---|---|
| `SCH-001` | ERROR | Missing Manifest | The `SKILL.md` file is missing in the discovered skill directory |
| `SCH-002` | ERROR | Invalid Frontmatter | YAML frontmatter is corrupted or cannot be parsed |
| `SCH-003` | ERROR | Missing Required Field | Missing required frontmatter field (`name` or `description`) |
| `SCH-004` | WARN  | Invalid Name Format | Skill name contains invalid characters (recommended: `^[a-z0-9_-]+$`) |
| `SCH-005` | WARN  | Short Description | `description` length is under 20 characters (insufficient for agent routing) |
| `SCH-006` | ERROR | Broken Link Reference | `SKILL.md` references local files or scripts that do not exist on disk |

#### Group 2: Security Audit (Security Rules — `SEC`)
| Code | Level | Name | Description |
|---|---|---|---|
| `SEC-001` | ERROR | Hardcoded Secret Detected | Detected exposed secrets (OpenAI `sk-...`, AWS `AKIA...`, GitHub `ghp_...`, private keys) |
| `SEC-002` | ERROR | Dangerous Shell Command | Usage of destructive commands (`rm -rf /`, `mkfs`, `:(){ :\|:& };:`) |
| `SEC-003` | WARN  | Unsafe Network Execution | Remote script execution without verification (`curl ... \| bash`, `wget ... \| sh`) |
| `SEC-004` | WARN  | Sensitive Path Access | Accessing sensitive file paths (`~/.ssh`, `~/.aws`, `/etc/shadow`) |
| `SEC-005` | WARN  | Prompt Injection Risk | Prompt override / safety bypass patterns (`ignore previous instructions`, `bypass safety`) |

#### Group 3: Discovery and Duplicates (Discovery Rules — `DSC`)
| Code | Level | Name | Description |
|---|---|---|---|
| `DSC-001` | WARN  | Stale Duplicate | Duplicate copies of the skill differ; showing the newest copy while older copy is stale |

---

### 3.3. Repository Layouts & Corner Cases

Skills may be placed in varied repository locations with distinct lifecycles:

1. **Origin Classification**:
   - `test-data`: Skills placed in test paths (`tests/`, `test/`, `fixtures/`, `testData/`, `test-resources/`, `src/test/`, `src/*Test/`). Used for test fixtures. Findings are non-blocking by default unless `--include-test-data` is specified.
   - `agent-config`: Skills configured for AI agent tools (`.claude/skills`, `.agents/skills`, `.junie/skills`, `.cursor/`, `.codex/`, `.github/skills`).
   - `product`: Skills shipped as product resources (`src/main/resources`, `resources/`, `plugins/*/`, `languages/*/`).
   - `standalone`: All other locations (e.g., dedicated `skills/` catalog).

2. **Duplicates Handling (Case A)**:
   - Skills with the same name are grouped together (test-data skills are kept isolated from non-test skills).
   - The copy with the newest `updated_date` is displayed as the primary entry (ties broken by lexicographic path order).
   - Secondary copies are recorded in `duplicates: list[DuplicateRef]` with their paths, update timestamps, and an `identical: bool` flag indicating whether directory contents match.
   - Rules are executed against the displayed primary copy, and all secondary duplicate copies are audited as well. Findings on secondary copies are attached to their `DuplicateRef` and propagated to the primary skill so they affect the pass/fail status and exit code.
   - If secondary copies differ in content, rule `DSC-001 Stale Duplicate` is reported with level `WARN`.
   - Symlinks are resolved to their target and counted once.

3. **Test Data Handling (Case B)**:
   - Skills classified as `test-data` are included in reporting but do not trigger a non-zero exit code unless `--include-test-data` is passed.

4. **Product Skills (Case C)**:
   - Shipped inside products or IDE plugins. All rules apply. Reported with `origin: product`.

---

### 3.4. Audit-Scoped Query Search & Filtering (`--query / -q`)

To optimize scan performance across large monorepos or multi-repository audits, Skill Atlas supports audit-scoped query filtering:

- **Filter Scope**: `--query / -q <text>` accepts a search query string.
- **Matching Criteria**: Matching is case-insensitive substring/token matching evaluated across:
  1. Skill identifier/name (`skill.name`)
  2. Description (`skill.description`)
  3. Skill path (`skill.path`)
  4. Repository name (`skill.repo_name`)
  5. Declared tags (`skill.tags`)
- **Matching Logic**:
  ```python
  def matches_query(skill: Skill, query: str) -> bool:
      q = query.strip().lower()
      if not q:
          return True
      tokens = [
          skill.name.lower(),
          skill.description.lower(),
          skill.path.lower(),
          (skill.repo_name or "").lower(),
          *(t.lower() for t in skill.tags),
      ]
      return any(q in token for token in tokens)
  ```
- **Audit-Scope Rule Optimization**:
  - Filtering occurs **before** static rule evaluation (`SCH-*`, `SEC-*`, `DSC-*`).
  - Only skills that match the query are audited by the rule engine.
  - Companion file fetches (e.g., downloading referenced scripts for security inspection) and rule evaluations are skipped entirely for non-matching skills, drastically minimizing network requests, execution time, and GitHub API quota consumption.
- **Reporting & Summary**:
  - The scan result and summary reflect only audited matching skills.
  - The CLI and JSON reports record the applied `query` string.
- **Zero Matching Skills Handling**:
  - If a query matches zero skills across all targets, the scan exits cleanly with code `0`.
  - The CLI outputs an informative notice: `0 skills matched query '<query>' across <N> target(s)`.

---

## 4. Command-Line Interface (CLI Specification)

### 4.1. Scan Command:
```bash
skill-atlas scan [TARGETS...] [OPTIONS]
```
- `TARGETS...`: Zero, one, or more paths to skill directories, local Git repositories, or remote Git repository URLs (e.g., `skill-atlas scan repo1 repo2 https://github.com/org/repo3.git`). If no positional arguments and no `--targets-file` are provided, defaults to `.` (current directory).

### 4.2. Scan Options:
- `--targets-file, -T <path>`: Read target repository paths or URLs from a newline-delimited text file (supports `#` comments and empty/whitespace lines).
- `--query, -q <text>`: Search query to filter skills across all repositories before static rule auditing.
- `--format, -f [text|json]`: Output report format (default: `text`).
- `--fail-on [error|warn]`: Minimum severity level triggering a non-zero exit code (default: `error`).
- `--rules, -r [all|schema|security|discovery]`: Filter rule categories (default: `all`).
- `--ignore <RULE_ID>`: Ignore specific rules (repeatable option).
- `--ref <branch|tag|sha>`: Pinned Git reference for remote scans (default: remote default branch).
- `--include-test-data`: Treat test fixture skills as blocking for exit codes.
- `--verbose, -v`: Verbose output (including passed checks).
- `--version`: Display application version.

### 4.3. Serve Command (Web UI):
```bash
skill-atlas serve [OPTIONS]
```
- `--host`: Server bind host (default: `127.0.0.1`).
- `--port`: Server bind port (default: `8765`).
- `--open`: Open browser automatically upon startup.
- `--allow-local`: Allow scanning local filesystem paths via web interface.
- `--reload`: Enable auto-reload on code changes (development).
- **Web UI Features**:
  - **Multi-Repository Input**: Target input supporting multiple repository URLs or local paths separated by newlines or commas, with pre-fill demo shortcuts.
  - **Dynamic Repository Faceted Filter Chips**: Interactive repository filter chips (`All Repos`, `repo1`, `repo2`, ...) dynamically populated from scanned repositories, functioning seamlessly alongside existing origin chips (`All`, `Agent Config`, `Product`, `Standalone`, `Test Data`).
  - **Instant Real-Time Search**: Search filter input querying across skill names, descriptions, tags, repo names, and paths simultaneously without full-page reloads.
  - **Multi-Target Progress Streaming**: Server-Sent Events (SSE) and status bar streaming discovery stages across multiple repositories (reporting target index, repository name, and rate limits in real time).
  - **Theme switcher**: Toggle between light and dark modes with manual toggle and system preference detection (persisted in `localStorage`).
  - **Interactive skill catalog**: Cards with pass/fail badges, findings breakdown, repository provenance, and duplicate origin badges.
  - **Status filtering**: Quick toggles for `All statuses`, `Passed only`, `Failed only`.
  - **Interactive Similar Skills panel**: Customizable similarity threshold (`0.3` - `0.8`), cross-repository match discovery, and direct per-skill similarity search from catalog items.
  - **Export Results**: Download full scan results as JSON conforming to the multi-target schema.

### 4.4. `similar` Command Syntax:
```bash
skill-atlas similar [TARGET] [OPTIONS]
```
- `TARGET`: Directory path, local Git repo, or remote Git URL (default: `.`).
- `--skill`, `-s`: Specific skill name or path to query similar skills for.
- `--threshold`, `-t`: Minimum similarity score threshold between `0.0` and `1.0` (default: `0.5`).
- `--top-k`, `-k`: Maximum number of matches to return (default: `10`).
- `--format`, `-f`: Output format (`text` or `json`, default: `text`).
- `--ref`: Pinned Git reference for remote scans.
- `--include-test-data`: Include test-data skills in similarity analysis.
- `--verbose`, `-v`: Output detailed score breakdown per feature.

### 4.5. Non-AI Similarity Heuristics:
The similarity engine calculates a multi-feature composite score between `0.0` and `1.0`:
1. **Name Similarity** (weight `0.30`): Normalized token Jaccard similarity and character sequence ratio.
2. **Description Similarity** (weight `0.40`): Bag-of-words cosine token similarity (stop words removed) and Jaccard overlap.
3. **Tags Similarity** (weight `0.15`): Jaccard similarity of declared tags.
4. **Body / Instructions Similarity** (weight `0.10`): Cosine token similarity across markdown prompt instructions.
5. **Companion Files Similarity** (weight `0.05`): Matching script and file basenames.

Dynamic re-weighting occurs when optional attributes (tags, files, body) are absent. Each match includes human-readable reasons explaining why the skills are similar.

### 4.6. Exit Codes:
- `0`: Success (all checks passed or findings are below `--fail-on` threshold, or 0 skills matched `--query`, or similar search completed).
- `1`: Violations found at or above `--fail-on` threshold (default: `ERROR`).
- `2`: Fatal CLI error (invalid options, non-existent target path, empty or non-existent targets file, argument parsing failure, rate limit exhausted).

---

## 5. Output Data Formats

### 5.1. Terminal Text Output (`--format text`):
Informative rich table (`rich.table`) displaying multi-target status, active query badges, and aggregated summary stats:
```text
🔍 Scanning skills across 2 targets:
  • https://github.com/example/skills-repo.git (repo: example/skills-repo)
  • tests/fixtures/valid_skill (repo: valid_skill)
🔎 Filter query: 'git'
Found 2 matching skills (filtered from 5 total)...

[FAIL] my-broken-git-skill
  Repo:        example/skills-repo
  Commit:      a1b2c3d4e5f67890123456789abcdef012345678 (2024-03-15T14:30:00Z)
  Description: Demonstrates broken frontmatter and unsafe shell script execution
  Path:        skills/my-broken-git-skill
  ❌ [ERROR] SCH-003: Missing required field 'description' in SKILL.md:4
  ⚠️  [WARN]  SEC-003: Unsafe pipe to shell found in scripts/install.sh:12 ('curl | bash')

[PASS] git-helper
  Repo:        example/skills-repo
  Commit:      8f9e0d1c2b3a4567890abcdef1234567890abcde (2024-01-10T09:15:00Z)
  Description: Git automation workflows for agent pipelines
  Path:        skills/git-helper
  ✅ All checks passed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary:
  Scanned Targets: 2
  Scanned Skills: 2
  Passed: 1
  Failed: 1
  Total Findings: 2 (1 Error, 1 Warning, 0 Info)
Status: FAILED (Exit Code 1)
```

### 5.2. JSON Output (`--format json`):
```json
{
  "version": "0.2.0",
  "target": "https://github.com/example/skills-repo.git",
  "targets": [
    "https://github.com/example/skills-repo.git",
    "tests/fixtures/valid_skill"
  ],
  "query": "git",
  "summary": {
    "total_skills": 2,
    "passed": 1,
    "failed": 1,
    "findings_count": {
      "error": 1,
      "warn": 1,
      "info": 0
    },
    "by_origin": {
      "agent-config": 0,
      "product": 0,
      "standalone": 2,
      "test-data": 0
    }
  },
  "skills": [
    {
      "name": "my-broken-git-skill",
      "description": "Demonstrates broken frontmatter and unsafe shell script execution",
      "repo_name": "example/skills-repo",
      "repo_url": "https://github.com/example/skills-repo.git",
      "commit": "a1b2c3d4e5f67890123456789abcdef012345678",
      "commit_date": "2024-03-15T14:30:00Z",
      "path": "skills/my-broken-git-skill",
      "origin": "standalone",
      "valid": false,
      "findings": [
        {
          "rule_id": "SCH-003",
          "severity": "ERROR",
          "message": "Missing required field 'description'",
          "file": "SKILL.md",
          "line": 4,
          "suggestion": "Add a descriptive 'description' field to YAML frontmatter"
        },
        {
          "rule_id": "SEC-003",
          "severity": "WARN",
          "message": "Unsafe pipe to shell found in scripts/install.sh:12 ('curl | bash')",
          "file": "scripts/install.sh",
          "line": 12,
          "suggestion": "Avoid executing scripts piped directly from network tools"
        }
      ]
    },
    {
      "name": "git-helper",
      "description": "Git automation workflows for agent pipelines",
      "repo_name": "example/skills-repo",
      "repo_url": "https://github.com/example/skills-repo.git",
      "commit": "8f9e0d1c2b3a4567890abcdef1234567890abcde",
      "commit_date": "2024-01-10T09:15:00Z",
      "path": "skills/git-helper",
      "origin": "standalone",
      "valid": true,
      "findings": []
    }
  ],
  "warnings": []
}
```

### 5.3. Data Models and API Contracts

#### `ScanResult` Model
The core scan aggregation model preserves backward compatibility with single-target consumers while providing structured multi-target metadata and query context:

```python
class ScanResult(BaseModel):
    version: str = Field(default=__version__)
    target: str  # Primary/first target for backward compatibility
    targets: list[str] = Field(default_factory=list)  # All scanned targets (normalized)
    query: str | None = None  # Active query string or None if unconstrained
    summary: ScanSummary
    skills: list[Skill]
    warnings: list[str] = Field(default_factory=list)
```

- **Backward Compatibility Contract**:
  - `target` is guaranteed to be a string representing the primary target (the first target in `targets`, or `""` if empty). Existing consumers expecting `result.target` or `"target": "..."` will continue operating without modification.
  - `targets` contains the complete array of scanned targets (paths or URLs) in normalization order.
  - `query` contains the optional query string if `--query / -q` was supplied, or `None` (`null` in JSON).

#### `ScanRequest` Model (FastAPI Web API: `POST /api/scans`)
The Web API request model accepts single-target or multi-target specifications along with search query parameters:

```python
class ScanRequest(BaseModel):
    target: str = ""  # Backward compatibility: single target string
    targets: list[str] = Field(default_factory=list)  # List of target paths or URLs
    query: str | None = None  # Optional search query filter
    ref: str | None = None  # Pinned Git reference for remote scans
    fail_on: Literal["error", "warn"] = "error"
    rules: Literal["all", "schema", "security", "discovery"] = "all"
    ignore: list[str] = Field(default_factory=list)
    include_test_data: bool = False
```

- **Target Ingestion Normalization**:
  - If `targets` is empty and `target` is non-empty, `targets` is populated as `[target]`.
  - If both `target` and `targets` are provided, they are merged and deduplicated.
  - In UI interactions, multiple targets may be supplied separated by newlines or commas.

---

## 6. Architecture & Module Structure

```text
               ┌─────────────────────────┐
               │    CLI / Web Interface  │ (Typer / FastAPI UI)
               └────────────┬────────────┘
                            │ (targets: list[str], query: str | None)
               ┌────────────▼────────────┐
               │  Scanner Orchestrator   │
               └──────┬───────────┬──────┘
                      │           │
     ┌────────────────▼────┐     ┌▼────────────────────┐
     │ Multi-Target Loop   │     │ Audit Query Filter  │
     │ - Local discovery   │────►│ - matches_query()   │
     │ - Remote GitHub tree│     │ - Pre-audit prune   │
     └─────────────────────┘     └─────────┬───────────┘
                                           │ (Matching skills only)
                                 ┌─────────▼───────────┐
                                 │ Deduplication & Log │
                                 │ - Intra-repo DSC-001│
                                 │ - Git provenance    │
                                 └─────────┬───────────┘
                                           │
                                 ┌─────────▼───────────┐
                                 │   Rule Registry     │
                                 │   - Schema: SCH-*   │
                                 │   - Security: SEC-* │
                                 └─────────┬───────────┘
                                           │
                                 ┌─────────▼───────────┐
                                 │ Unified ScanResult  │
                                 │ - Aggregated stats  │
                                 │ - Target & Query    │
                                 └─────────┬───────────┘
                                           │
                      ┌────────────────────┴────────────────────┐
                      ▼                                         ▼
           ┌─────────────────────┐                   ┌─────────────────────┐
           │  Reporters Engine   │                   │  Interactive Web UI │
           │  - ConsoleReporter  │                   │  - Repo filter chips│
           │  - JsonReporter     │                   │  - Real-time search │
           └─────────────────────┘                   └─────────────────────┘
```

---

## 7. Development Roadmap (Iteration 1)

1. **Phase 1: Project Setup & Infrastructure**
   - Configure `pyproject.toml` (uv, typer, pydantic, rich, pytest, ruff).
   - Package structure and CLI entrypoint skeleton.
2. **Phase 2: Data Models, Git Ingestion & Discovery**
   - Pydantic models: `Skill`, `Finding`, `ScanResult` (including `repo_name`, `commit`, `commit_date`, `description`).
   - Git repository ingestion (local repos via git inspection and remote Git URLs via GitHub REST API without cloning).
   - Git commit provenance resolution (identifying commit where skill/`SKILL.md` was added).
   - Recursive skill discovery and `SKILL.md` frontmatter/body parser.
3. **Phase 3: Rule Engine**
   - Base `Rule` class.
   - Implement schema rules `SCH-001` through `SCH-006`.
   - Implement security rules `SEC-001` through `SEC-005`.
4. **Phase 4: Reporters & CLI Integration**
   - Console reporting via Rich (displaying repo name, skill name, description, commit).
   - JSON serialization.
   - Exit code handling.
5. **Phase 5: Testing & Documentation**
   - Unit tests for individual rules and Git provenance resolution.
   - Integration test with fixture repositories and directories.

---

## 8. Discussion Points

1. **Skill Formats**: Is supporting `SKILL.md` (frontmatter + markdown) sufficient for Iteration 1, or might standalone `skill.yaml` / `skill.json` files be needed during the workshop?
2. **Security Rule Severity**: Should `SEC-005` (prompt injection heuristic) default to `WARN` or `ERROR`?
3. **Package Manager & Toolchain**: Confirmed (`uv` and Python 3.11+ approved as standard toolchain).

---

## 9. Live QA Browser Video Testing (`browser-video-tester`)

The `browser-video-tester` agent skill enables autonomous, human-like QA testing of web features:
1. **Visual Simulation**: Renders a floating on-screen cursor with click ripples and action title banners.
2. **Live Video Capture**: Generates high-fps recordings of browser flows and converts them to `.mp4` using `ffmpeg`.
3. **Automated Audit**: Audits browser JavaScript console errors and HTTP network failures.
4. **Structured Artifacts**: Outputs `test_session.mp4`, `report.md`, `timeline.json`, and step keyframe screenshots under `artifacts/browser_tests/`.

---

## 10. The Skill Map (Clustering, AI & Jev Classification)

The Skill Map provides high-level functional clustering and thematic visualization of discovered skills:
1. **Without AI (Heuristic)**:
   - Groups skills using shared keywords in skill names, descriptions, and tags combined with pairwise similarity graphs.
   - Names clusters by dominant domain keywords and generates actionable reasons for grouping.
2. **With AI (Claude Code `claude -p`)**:
   - Clusters skills non-interactively using Claude CLI prompt, generating concise category titles and rationale.
   - Supports deterministic record and replay (`--record` / `--replay`) for offline environments and CI pipelines.
3. **With TypeSafe Jev (System One Classification)**:
   - Classifies skills into typed functional domains (`memory_and_state`, `code_and_review`, `security_and_audit`, `data_and_sync`, `general_automation`) using TypeSafe AI's Jev model via the `Choice` API (`typesafe-sdk`).
4. **Ground-Truth Benchmark Check**:
   - 10-skill benchmark dataset with manual golden groupings to validate and compare clustering quality against human judgment.
5. **Interactive Web View**:
   - `Skill Map` drawer and interactive cards in Web UI, supporting instant filtering and replayable test fixtures.

---

## 11. Visual Regression Testing & Failure Reporting

Visual testing provides automated pixel-level diffing and actionable failure reporting in CI:
1. **Deterministic Execution**:
   - Fixed viewport (`1280x720`), standardized fonts, disabled animations/transitions, and video capture.
   - Compares captured screens against Git-tracked golden baselines (`tests/visual/baselines/`).
2. **Failure Serialization (`failures.json`)**:
   - Failed comparisons are serialized to `artifacts/visual/failures.json` containing test metadata, diff statistics, and repo-relative paths to `expected`, `actual`, and `diff` PNG images.
3. **Automated Asset Publication (`scripts/publish-assets.sh`)**:
   - On visual test failures, CI commits differing screenshots directly to the orphan `demo-assets` branch without dirtying the working directory.
   - Generates permanent, immutable raw GitHub URLs for all snapshot assets.
4. **Rich Multi-Channel Reporting (`scripts/visual-report.sh` / `scripts/ui-report.sh`)**:
   - **Terminal Log**: Displays failed test titles, locations, diff percentages, and direct image links.
   - **GitHub Actions Annotations**: Emits `::error` annotations directly on the failed file/line with diff links.
   - **Job Summary**: Appends an image table (`Expected | Actual | Diff`) rendering screenshots side by side to `$GITHUB_STEP_SUMMARY`.
   - **Remediation**: Displays exact copy-paste command (`UPDATE_BASELINES=1 uv run pytest tests/visual`) to re-render baselines when changes are intentional.
