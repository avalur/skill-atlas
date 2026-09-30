"""Image comparison and diff generation engine for visual regression testing."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageChops, ImageDraw

if TYPE_CHECKING:
    import pytest


@dataclass
class VisualDiffResult:
    matched: bool
    diff_percent: float
    total_pixels: int
    diff_pixels: int
    baseline_path: Path
    actual_path: Path
    diff_path: Path | None = None
    message: str = ""


def should_update_baselines(pytest_config: pytest.Config | None = None) -> bool:
    """Check if baseline update mode is enabled via environment variable or pytest option."""
    env_val = os.environ.get("UPDATE_BASELINES", "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    if pytest_config is not None:
        try:
            return bool(pytest_config.getoption("--update-baselines", default=False))
        except (ValueError, AttributeError):
            pass
    return False


def create_highlight_diff(
    baseline: Image.Image,
    actual: Image.Image,
    mask: Image.Image,
) -> Image.Image:
    """Generate a highlight image with dimmed background and bright red changed pixels."""
    base_rgb = actual.convert("RGB")
    dimmed = Image.blend(base_rgb, Image.new("RGB", base_rgb.size, (40, 40, 40)), 0.6)
    highlight = dimmed.copy()
    red_overlay = Image.new("RGB", base_rgb.size, (255, 0, 75))
    highlight.paste(red_overlay, (0, 0), mask=mask)
    return highlight


def create_side_by_side_diff(
    baseline: Image.Image,
    actual: Image.Image,
    highlight: Image.Image,
) -> Image.Image:
    """Generate a 3-panel comparison image: Baseline | Actual | Highlight Diff."""
    w, h = baseline.size
    header_h = 32
    canvas = Image.new("RGB", (w * 3, h + header_h), (24, 24, 27))
    draw = ImageDraw.Draw(canvas)

    # Text labels
    draw.text((16, 8), "BASELINE (GOLDEN)", fill=(200, 200, 200))
    draw.text((w + 16, 8), "ACTUAL (CAPTURED)", fill=(200, 200, 200))
    draw.text((w * 2 + 16, 8), "DIFF HIGHLIGHT", fill=(255, 90, 90))

    canvas.paste(baseline.convert("RGB"), (0, header_h))
    canvas.paste(actual.convert("RGB"), (w, header_h))
    canvas.paste(highlight.convert("RGB"), (w * 2, header_h))
    return canvas


def compare_images(
    baseline_path: Path | str,
    actual_path: Path | str,
    diff_output_path: Path | str | None = None,
    tolerance_percent: float = 0.5,
    color_threshold: int = 15,
    update_baseline: bool = False,
    pytest_config: pytest.Config | None = None,
) -> VisualDiffResult:
    """Compare baseline and actual PNG images.

    If difference exceeds tolerance_percent, generates a diff highlight image
    marking changed pixels and returns matched=False.
    """
    baseline_p = Path(baseline_path).resolve()
    actual_p = Path(actual_path).resolve()
    diff_out_p = Path(diff_output_path).resolve() if diff_output_path else None

    # Check if baseline update is requested
    if update_baseline or should_update_baselines(pytest_config):
        if not actual_p.exists():
            return VisualDiffResult(
                matched=False,
                diff_percent=100.0,
                total_pixels=0,
                diff_pixels=0,
                baseline_path=baseline_p,
                actual_path=actual_p,
                message=f"Cannot update baseline: actual image does not exist at {actual_p}",
            )
        baseline_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(actual_p, baseline_p)
        return VisualDiffResult(
            matched=True,
            diff_percent=0.0,
            total_pixels=0,
            diff_pixels=0,
            baseline_path=baseline_p,
            actual_path=actual_p,
            message=f"Baseline updated successfully at {baseline_p}",
        )

    if not actual_p.exists():
        return VisualDiffResult(
            matched=False,
            diff_percent=100.0,
            total_pixels=0,
            diff_pixels=0,
            baseline_path=baseline_p,
            actual_path=actual_p,
            message=f"Actual image not found at {actual_p}",
        )

    if not baseline_p.exists():
        return VisualDiffResult(
            matched=False,
            diff_percent=100.0,
            total_pixels=0,
            diff_pixels=0,
            baseline_path=baseline_p,
            actual_path=actual_p,
            message=(
                f"Baseline image not found at {baseline_p}. "
                "If this is a new screen or intentional UI change, run with "
                "UPDATE_BASELINES=1 (or pytest --update-baselines) to create it."
            ),
        )

    with Image.open(baseline_p) as b_img, Image.open(actual_p) as a_img:
        if b_img.size != a_img.size:
            msg = (
                f"Image dimensions mismatch: baseline is {b_img.size}, but actual is {a_img.size}."
            )
            if diff_out_p:
                max_w = max(b_img.width, a_img.width)
                max_h = max(b_img.height, a_img.height)
                header_h = 32
                canvas = Image.new("RGB", (max_w * 2, max_h + header_h), (24, 24, 27))
                draw = ImageDraw.Draw(canvas)
                draw.text((16, 8), f"BASELINE {b_img.size}", fill=(200, 200, 200))
                draw.text(
                    (max_w + 16, 8),
                    f"ACTUAL {a_img.size} (MISMATCH)",
                    fill=(255, 90, 90),
                )
                canvas.paste(b_img.convert("RGB"), (0, header_h))
                canvas.paste(a_img.convert("RGB"), (max_w, header_h))
                diff_out_p.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(diff_out_p)

            return VisualDiffResult(
                matched=False,
                diff_percent=100.0,
                total_pixels=max(b_img.width * b_img.height, a_img.width * a_img.height),
                diff_pixels=max(b_img.width * b_img.height, a_img.width * a_img.height),
                baseline_path=baseline_p,
                actual_path=actual_p,
                diff_path=diff_out_p,
                message=msg,
            )

        b_rgb = b_img.convert("RGB")
        a_rgb = a_img.convert("RGB")
        w, h = b_rgb.size
        total_pixels = w * h

        r, g, b = ImageChops.difference(b_rgb, a_rgb).split()
        max_diff = ImageChops.lighter(ImageChops.lighter(r, g), b)
        mask = max_diff.point(lambda p: 255 if p > color_threshold else 0)

        hist = mask.histogram()
        diff_pixels = hist[255]
        diff_percent = (diff_pixels / total_pixels) * 100.0

        matched = diff_percent <= tolerance_percent

        if not matched:
            msg = (
                f"Visual regression detected: {diff_percent:.2f}% pixels differ "
                f"({diff_pixels}/{total_pixels}), which exceeds tolerance {tolerance_percent:.2f}%. "
                "If this visual change was intentional, update baselines with "
                "UPDATE_BASELINES=1 (or pytest --update-baselines)."
            )
            if diff_out_p:
                highlight = create_highlight_diff(b_img, a_img, mask)
                side_by_side = create_side_by_side_diff(b_img, a_img, highlight)
                diff_out_p.parent.mkdir(parents=True, exist_ok=True)
                side_by_side.save(diff_out_p)
        else:
            msg = (
                f"Images match within tolerance: {diff_percent:.2f}% diff "
                f"({diff_pixels}/{total_pixels} pixels, tolerance: {tolerance_percent:.2f}%)."
            )

        return VisualDiffResult(
            matched=matched,
            diff_percent=diff_percent,
            total_pixels=total_pixels,
            diff_pixels=diff_pixels,
            baseline_path=baseline_p,
            actual_path=actual_p,
            diff_path=diff_out_p if not matched else None,
            message=msg,
        )
