"""Visual regression failure tracking and serialization for CI reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tests.visual.image_diff import VisualDiffResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FAILURES_PATH = REPO_ROOT / "artifacts" / "visual" / "failures.json"
COMPAT_FAILURES_PATH = REPO_ROOT / "tests" / "visual" / "out" / "failures.json"


def _to_rel_path(p: Path | str | None, root: Path = REPO_ROOT) -> str | None:
    if p is None:
        return None
    if isinstance(p, str) and not Path(p).is_absolute():
        return Path(p).as_posix()
    path_obj = Path(p).resolve()
    try:
        return path_obj.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path_obj.as_posix()


def clear_visual_failures(
    failures_path: Path | None = None,
    compat_path: Path | None = COMPAT_FAILURES_PATH,
) -> None:
    """Clear recorded visual failures before a test run."""
    target = failures_path or DEFAULT_FAILURES_PATH
    if target.exists():
        try:
            target.unlink()
        except OSError:
            pass
    if compat_path and compat_path.exists():
        try:
            compat_path.unlink()
        except OSError:
            pass


def load_visual_failures(failures_path: Path | None = None) -> list[dict[str, Any]]:
    """Load existing failure entries from failures.json."""
    target = failures_path or DEFAULT_FAILURES_PATH
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def record_visual_failures(
    results: list[VisualDiffResult],
    failures_path: Path | None = None,
    compat_path: Path | None = COMPAT_FAILURES_PATH,
    file_path: str = "tests/visual/test_walkthrough_screens.py",
    line_number: int = 40,
    title: str = "test_walkthrough_visual_regression",
    root_dir: Path = REPO_ROOT,
) -> Path:
    """Record mismatched snapshots into failures.json for CI explanation."""
    target = failures_path or DEFAULT_FAILURES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if compat_path:
        compat_path.parent.mkdir(parents=True, exist_ok=True)

    mismatches = [r for r in results if not r.matched]
    current_entries = load_visual_failures(target)

    # Filter out any existing record for this specific test title
    filtered = [e for e in current_entries if e.get("title") != title]

    if mismatches:
        snapshots = [
            {
                "name": r.actual_path.name,
                "message": r.message,
                "expected": _to_rel_path(r.baseline_path, root_dir),
                "actual": _to_rel_path(r.actual_path, root_dir),
                "diff": _to_rel_path(r.diff_path, root_dir) if r.diff_path else None,
            }
            for r in mismatches
        ]

        error_lines = [
            f"{len(mismatches)} visual regression(s) detected: "
            + "; ".join(f"{r.actual_path.stem}: {r.message}" for r in mismatches)
        ]

        rel_file = _to_rel_path(file_path, root_dir) or file_path

        entry = {
            "file": rel_file,
            "line": line_number,
            "title": title,
            "errors": error_lines,
            "snapshots": snapshots,
        }
        filtered.append(entry)

    json_str = json.dumps(filtered, indent=2) + "\n"
    target.write_text(json_str, encoding="utf-8")
    if compat_path:
        try:
            compat_path.write_text(json_str, encoding="utf-8")
        except OSError:
            pass

    return target
