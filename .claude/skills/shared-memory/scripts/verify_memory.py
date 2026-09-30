#!/usr/bin/env python3
"""Verification script for Skill Atlas shared memory integrity."""

import sys
from pathlib import Path

REQUIRED_FILES = [
    "README.md",
    "architecture.md",
    "workflows.md",
    "gotchas.md",
    "rules-and-skills.md",
    "known-issues.md",
]


def verify_memory() -> int:
    # Resolve repository root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    memory_dir = repo_root / "memory"

    if not memory_dir.is_dir():
        print(f"ERROR: memory directory not found at {memory_dir}")
        return 1

    missing = []
    empty = []
    for filename in REQUIRED_FILES:
        target = memory_dir / filename
        if not target.is_file():
            missing.append(filename)
        elif target.stat().st_size == 0:
            empty.append(filename)

    if missing:
        print(f"ERROR: Missing memory files: {', '.join(missing)}")
        return 1
    if empty:
        print(f"ERROR: Empty memory files: {', '.join(empty)}")
        return 1

    readme_content = (memory_dir / "README.md").read_text(encoding="utf-8")
    for filename in REQUIRED_FILES:
        if filename != "README.md" and filename not in readme_content:
            print(f"WARNING: {filename} is not referenced in memory/README.md")

    print(f"SUCCESS: Shared memory verified ({len(REQUIRED_FILES)} files present and valid).")
    return 0


if __name__ == "__main__":
    sys.exit(verify_memory())
