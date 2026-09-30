"""Unit tests for visual image diffing and baseline update engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.visual.image_diff import (
    VisualDiffResult,
    compare_images,
    should_update_baselines,
)


def _create_solid_image(
    path: Path, size: tuple[int, int] = (200, 200), color: tuple[int, int, int] = (40, 40, 40)
) -> Path:
    img = Image.new("RGB", size, color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def test_exact_match(tmp_path: Path) -> None:
    baseline = _create_solid_image(tmp_path / "baseline.png", color=(50, 100, 150))
    actual = _create_solid_image(tmp_path / "actual.png", color=(50, 100, 150))

    result = compare_images(baseline, actual)

    assert isinstance(result, VisualDiffResult)
    assert result.matched is True
    assert result.diff_percent == 0.0
    assert result.diff_pixels == 0
    assert result.total_pixels == 200 * 200


def test_minor_deviation_within_tolerance(tmp_path: Path) -> None:
    w, h = 200, 200
    baseline = _create_solid_image(tmp_path / "baseline.png", (w, h), (40, 40, 40))

    actual_img = Image.new("RGB", (w, h), (40, 40, 40))
    # Change 10 pixels out of 40,000 (0.025% diff)
    for i in range(10):
        actual_img.putpixel((i, 0), (255, 255, 255))
    actual_path = tmp_path / "actual.png"
    actual_img.save(actual_path)

    result = compare_images(baseline, actual_path, tolerance_percent=0.5)

    assert result.matched is True
    assert result.diff_pixels == 10
    assert result.diff_percent < 0.1
    assert result.diff_path is None


def test_visual_regression_exceeding_tolerance(tmp_path: Path) -> None:
    w, h = 200, 200
    baseline = _create_solid_image(tmp_path / "baseline.png", (w, h), (40, 40, 40))

    actual_img = Image.new("RGB", (w, h), (40, 40, 40))
    # Alter 100x40 = 4,000 pixels out of 40,000 (10.0% diff)
    for x in range(100):
        for y in range(40):
            actual_img.putpixel((x, y), (255, 0, 0))
    actual_path = tmp_path / "actual.png"
    actual_img.save(actual_path)

    diff_path = tmp_path / "diff.png"
    result = compare_images(
        baseline, actual_path, diff_output_path=diff_path, tolerance_percent=0.5
    )

    assert result.matched is False
    assert result.diff_percent == pytest.approx(10.0, rel=1e-2)
    assert result.diff_pixels == 4000
    assert result.diff_path == diff_path
    assert diff_path.exists(), "Diff highlight image must be generated"
    assert "exceeds tolerance" in result.message


def test_missing_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "nonexistent_baseline.png"
    actual = _create_solid_image(tmp_path / "actual.png")

    result = compare_images(baseline, actual)

    assert result.matched is False
    assert result.diff_percent == 100.0
    assert "UPDATE_BASELINES=1" in result.message


def test_missing_actual_image(tmp_path: Path) -> None:
    baseline = _create_solid_image(tmp_path / "baseline.png")
    actual = tmp_path / "nonexistent_actual.png"

    result = compare_images(baseline, actual)

    assert result.matched is False
    assert "Actual image not found" in result.message


def test_dimension_mismatch(tmp_path: Path) -> None:
    baseline = _create_solid_image(tmp_path / "baseline.png", size=(200, 200))
    actual = _create_solid_image(tmp_path / "actual.png", size=(300, 200))

    diff_path = tmp_path / "dim_diff.png"
    result = compare_images(baseline, actual, diff_output_path=diff_path)

    assert result.matched is False
    assert "dimensions mismatch" in result.message.lower()
    assert diff_path.exists()


def test_baseline_update_flag(tmp_path: Path) -> None:
    baseline = tmp_path / "baselines" / "screen.png"
    actual = _create_solid_image(tmp_path / "captured.png", color=(100, 150, 200))

    assert not baseline.exists()

    result = compare_images(baseline, actual, update_baseline=True)

    assert result.matched is True
    assert baseline.exists()
    assert "updated successfully" in result.message


def test_baseline_update_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / "baselines" / "screen_env.png"
    actual = _create_solid_image(tmp_path / "captured_env.png", color=(10, 20, 30))

    monkeypatch.setenv("UPDATE_BASELINES", "1")
    assert should_update_baselines() is True

    result = compare_images(baseline, actual)
    assert result.matched is True
    assert baseline.exists()
