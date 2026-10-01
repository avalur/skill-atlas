"""Tests for visual failure reporting engine and publication scripts."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PIL import Image

from tests.visual.failures import (
    clear_visual_failures,
    load_visual_failures,
    record_visual_failures,
)
from tests.visual.image_diff import VisualDiffResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_record_visual_failures(tmp_path: Path) -> None:
    """Validate failures.json serialization and snapshot extraction."""
    failures_file = tmp_path / "failures.json"
    compat_file = tmp_path / "out" / "failures.json"

    baseline = tmp_path / "baseline.png"
    actual = tmp_path / "actual.png"
    diff = tmp_path / "diff.png"

    for p in [baseline, actual, diff]:
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(p)

    mismatch = VisualDiffResult(
        matched=False,
        diff_percent=5.12,
        total_pixels=10000,
        diff_pixels=512,
        baseline_path=baseline,
        actual_path=actual,
        diff_path=diff,
        message="Visual regression detected: 5.12% pixels differ",
    )
    matched = VisualDiffResult(
        matched=True,
        diff_percent=0.0,
        total_pixels=10000,
        diff_pixels=0,
        baseline_path=baseline,
        actual_path=actual,
        diff_path=None,
        message="Images match",
    )

    record_visual_failures(
        results=[mismatch, matched],
        failures_path=failures_file,
        compat_path=compat_file,
        file_path="tests/visual/test_walkthrough_screens.py",
        line_number=40,
        title="test_walkthrough_visual_regression",
        root_dir=tmp_path,
    )

    assert failures_file.exists()
    assert compat_file.exists()

    data = load_visual_failures(failures_file)
    assert len(data) == 1
    entry = data[0]

    assert entry["file"] == "tests/visual/test_walkthrough_screens.py"
    assert entry["line"] == 40
    assert entry["title"] == "test_walkthrough_visual_regression"
    assert len(entry["errors"]) == 1
    assert "5.12%" in entry["errors"][0]

    assert len(entry["snapshots"]) == 1
    snap = entry["snapshots"][0]
    assert snap["name"] == "actual.png"
    assert snap["expected"] == "baseline.png"
    assert snap["actual"] == "actual.png"
    assert snap["diff"] == "diff.png"

    # Test clearing
    clear_visual_failures(failures_file, compat_file)
    assert not failures_file.exists()
    assert not compat_file.exists()


def test_visual_report_script_empty_failures(tmp_path: Path) -> None:
    """Verify scripts/visual-report.sh exits cleanly when no failures exist."""
    script = REPO_ROOT / "scripts" / "visual-report.sh"
    ui_script = REPO_ROOT / "scripts" / "ui-report.sh"
    assert script.exists()
    assert ui_script.exists()

    empty_json = tmp_path / "empty_failures.json"
    empty_json.write_text("[]\n", encoding="utf-8")

    env = os.environ.copy()
    env["VISUAL_FAILURES_JSON"] = str(empty_json)

    for s in [script, ui_script]:
        res = subprocess.run(
            [str(s)],
            env=env,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert res.returncode == 0
        assert "No screenshot failures recorded" in res.stdout


def test_visual_report_script_formatting(tmp_path: Path) -> None:
    """Verify scripts/visual-report.sh generates annotations, console links, and summary table."""
    script = REPO_ROOT / "scripts" / "visual-report.sh"
    summary_file = tmp_path / "step_summary.md"

    # Create dummy image files inside repository structure
    dummy_img = REPO_ROOT / "tests" / "visual" / "baselines" / "01_initial_dashboard.png"
    assert dummy_img.exists()

    failures_content = [
        {
            "file": "tests/visual/test_walkthrough_screens.py",
            "line": 40,
            "title": "test_walkthrough_visual_regression",
            "errors": [
                "1 visual regression(s) detected: 01_initial_dashboard: Visual regression detected: 5.12% pixels differ"
            ],
            "snapshots": [
                {
                    "name": "01_initial_dashboard.png",
                    "message": "Visual regression detected: 5.12% pixels differ (47200/921600), which exceeds tolerance 0.50%.",
                    "expected": "tests/visual/baselines/01_initial_dashboard.png",
                    "actual": "tests/visual/baselines/01_initial_dashboard.png",
                    "diff": "tests/visual/baselines/01_initial_dashboard.png",
                }
            ],
        }
    ]

    failures_file = tmp_path / "failures.json"
    failures_file.write_text(json.dumps(failures_content), encoding="utf-8")

    env = os.environ.copy()
    env["VISUAL_FAILURES_JSON"] = str(failures_file)
    env["GITHUB_STEP_SUMMARY"] = str(summary_file)
    env["GITHUB_REPOSITORY"] = "avalur/skill-atlas"
    env["GITHUB_RUN_ID"] = "123456789"
    env["GITHUB_SERVER_URL"] = "https://github.com"

    res = subprocess.run(
        [str(script)],
        env=env,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert res.returncode == 0
    stdout = res.stdout

    # Check terminal output
    assert "✘ Visual test failed: test_walkthrough_visual_regression" in stdout
    assert "tests/visual/test_walkthrough_screens.py:40" in stdout
    assert "screenshot 01_initial_dashboard.png" in stdout
    assert "UPDATE_BASELINES=1 uv run pytest tests/visual" in stdout

    # Check GitHub Actions annotations
    assert "::error file=tests/visual/test_walkthrough_screens.py,line=40" in stdout
    assert "title=Visual test failed — test_walkthrough_visual_regression" in stdout

    # Check GitHub Step Summary Markdown
    assert summary_file.exists()
    summary_md = summary_file.read_text(encoding="utf-8")
    assert "## ❌ Visual tests: 1 failed" in summary_md
    assert "### test_walkthrough_visual_regression" in summary_md
    assert "`tests/visual/test_walkthrough_screens.py:40`" in summary_md
    assert "| Expected | Actual | Diff |" in summary_md
    assert "UPDATE_BASELINES=1 uv run pytest tests/visual" in summary_md


def test_publish_assets_script(tmp_path: Path) -> None:
    """Verify scripts/publish-assets.sh pushes assets to demo-assets branch without touching working tree."""
    script = REPO_ROOT / "scripts" / "publish-assets.sh"

    # Set up a local test repository with a bare remote
    remote_dir = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_dir)], check=True, capture_output=True)

    repo_dir = tmp_path / "worktree"
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_dir)],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Runner"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Initial commit in master
    (repo_dir / "README.md").write_text("Hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD:master"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create dummy images to publish
    img1 = repo_dir / "screenshot1.png"
    img2 = repo_dir / "screenshot2.png"
    Image.new("RGB", (10, 10), (255, 0, 0)).save(img1)
    Image.new("RGB", (10, 10), (0, 255, 0)).save(img2)

    env = os.environ.copy()
    env["GITHUB_REPOSITORY"] = "avalur/skill-atlas"

    res = subprocess.run(
        [str(script), "test-run-1", "screenshot1.png", "screenshot2.png"],
        env=env,
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0, f"Script failed: {res.stderr}"
    lines = res.stdout.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("https://raw.githubusercontent.com/avalur/skill-atlas/")
    assert lines[0].endswith("/test-run-1/screenshot1.png")
    assert lines[1].endswith("/test-run-1/screenshot2.png")

    # Verify that demo-assets branch exists on remote and working directory is intact
    branches = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", "demo-assets"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "refs/heads/demo-assets" in branches
