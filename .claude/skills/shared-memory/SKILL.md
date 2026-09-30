---
name: shared-memory
version: 1.0.0
description: Maintain and update the project's shared memory directory (memory/) across AI agent sessions. Use to recall past decisions or record new architectural choices, gotchas, workflows, and rules.
author: Skill Atlas Team
tags:
  - memory
  - documentation
  - agents
  - knowledge-base
---

# Shared Memory Maintenance

This skill provides operational protocols for consulting and maintaining shared memory in the `memory/` directory across all AI agent sessions.

## Core Rules

1. **ALWAYS Read Before a Task**: Inspect the relevant documents in `memory/` before starting work to avoid re-deriving existing knowledge, violating established workflows, or hitting documented edge cases.
2. **ALWAYS Update with this Skill**: Keep the shared memory accurate and comprehensive whenever you discover new insights or introduce changes.

## When to Update Shared Memory

- **New Architecture or Data Models**: Update `memory/architecture.md` when adding or modifying backend models, CLI flags, scanner discovery mechanisms, or web endpoints.
- **Gotchas and Traps**: Update `memory/gotchas.md` immediately upon uncovering an obscure bug, regex edge case, authorization hurdle (such as GitHub SAML SSO), or path resolution issue.
- **Workflow or Standard Changes**: Update `memory/workflows.md` when updating Git branch conventions, Definition of Done, testing matrices, or CI requirements.
- **Rule Engine Updates**: Update `memory/rules-and-skills.md` when introducing new validation rules (`SCH`, `SEC`, `DSC`), updating layout heuristics, or tweaking similarity metrics.
- **Audit Findings / Review Items**: Update `memory/known-issues.md` when code review uncovers pending vulnerabilities or architectural debt slated for future iterations.

## Directory Structure

```text
memory/
├── README.md           # Master index and quick guide
├── architecture.md     # Component architecture and system design
├── workflows.md        # PR workflow, DoD, CI matrix, and guidelines
├── gotchas.md          # Failure modes, SAML SSO fallback, path traps
├── rules-and-skills.md # Complete catalog of rules, layouts, and similarity
└── known-issues.md     # Backlog of audit findings from code reviews
```

## Integrity Verification

To verify that all required memory documents are present, non-empty, and indexed, run the companion script:
[Verification Script](scripts/verify_memory.py)
