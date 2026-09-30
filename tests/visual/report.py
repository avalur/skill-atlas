"""HTML report generator for visual regression test results."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.visual.image_diff import VisualDiffResult


def generate_visual_report(
    results: list[VisualDiffResult],
    report_path: Path,
    video_path: Path | None = None,
    commit_sha: str = "local",
) -> Path:
    """Generate a self-contained HTML visual regression report."""
    total_screens = len(results)
    passed_screens = sum(1 for r in results if r.matched)
    failed_screens = total_screens - passed_screens
    status_class = "pass" if failed_screens == 0 else "fail"
    status_text = "ALL PASSED" if failed_screens == 0 else f"{failed_screens} FAILED"

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Relative paths for images and video from report_path.parent
    report_dir = report_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    def rel(p: Path | None) -> str:
        if not p or not p.exists():
            return ""
        try:
            return str(p.relative_to(report_dir))
        except ValueError:
            return str(p)

    video_rel = rel(video_path) if video_path else ""

    cards_html = []
    for r in results:
        screen_name = r.actual_path.stem
        card_class = "card-pass" if r.matched else "card-fail"
        badge_class = "badge-pass" if r.matched else "badge-fail"
        badge_text = "MATCHED" if r.matched else "REGRESSION"

        b_rel = rel(r.baseline_path)
        a_rel = rel(r.actual_path)
        d_rel = rel(r.diff_path) if r.diff_path else ""

        diff_info = (
            "0.0% diff"
            if r.matched and r.diff_percent == 0.0
            else f"{r.diff_percent:.2f}% diff ({r.diff_pixels:,} / {r.total_pixels:,} px)"
        )

        images_html = f"""
        <div class="image-grid">
          <div class="image-panel">
            <div class="panel-label">Golden Baseline</div>
            <img src="{b_rel}" alt="Baseline {screen_name}" loading="lazy" />
          </div>
          <div class="image-panel">
            <div class="panel-label">Actual ({commit_sha})</div>
            <img src="{a_rel}" alt="Actual {screen_name}" loading="lazy" />
          </div>
        """
        if d_rel:
            images_html += f"""
          <div class="image-panel diff-panel">
            <div class="panel-label diff-label">Diff Highlight</div>
            <img src="{d_rel}" alt="Diff {screen_name}" loading="lazy" />
          </div>
            """
        images_html += "</div>"

        cards_html.append(
            f"""
        <div class="screen-card {card_class}">
          <div class="screen-header">
            <div class="screen-title">
              <span class="screen-name">{screen_name}</span>
              <span class="badge {badge_class}">{badge_text}</span>
            </div>
            <div class="screen-meta">{diff_info}</div>
          </div>
          <div class="screen-message">{r.message}</div>
          {images_html}
        </div>
        """
        )

    all_cards = "\n".join(cards_html)

    video_section = ""
    if video_rel:
        video_section = f"""
        <div class="video-container">
          <h3>Recorded Walkthrough Video</h3>
          <video controls autoplay muted loop preload="metadata">
            <source src="{video_rel}" type="video/webm">
            Your browser does not support WebM video playback.
          </video>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Skill Atlas - Visual Regression Report</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --success: #10b981;
      --error: #ef4444;
      --border-fail: rgba(239, 68, 68, 0.4);
      --border-pass: rgba(16, 185, 129, 0.2);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 2rem 1.5rem;
    }}
    .container {{
      max-width: 1400px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 2rem;
      flex-wrap: wrap;
      gap: 1rem;
    }}
    .title-area h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.025em;
    }}
    .title-area p {{
      color: var(--text-muted);
      font-size: 0.875rem;
      margin-top: 0.25rem;
    }}
    .stats-bar {{
      display: flex;
      gap: 1rem;
    }}
    .stat-pill {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      padding: 0.5rem 1rem;
      text-align: center;
    }}
    .stat-val {{
      font-size: 1.25rem;
      font-weight: 700;
    }}
    .stat-lbl {{
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .status-pass {{ color: var(--success); }}
    .status-fail {{ color: var(--error); }}
    .video-container {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      padding: 1.25rem;
      margin-bottom: 2rem;
    }}
    .video-container h3 {{
      font-size: 1.1rem;
      margin-bottom: 0.75rem;
    }}
    .video-container video {{
      width: 100%;
      max-height: 480px;
      border-radius: 0.5rem;
      background: #000;
    }}
    .screen-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      padding: 1.25rem;
      margin-bottom: 1.75rem;
    }}
    .card-fail {{
      border-color: var(--border-fail);
      box-shadow: 0 0 16px rgba(239, 68, 68, 0.1);
    }}
    .screen-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }}
    .screen-title {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    .screen-name {{
      font-size: 1.15rem;
      font-weight: 600;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      font-size: 0.75rem;
      font-weight: 700;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-pass {{ background: rgba(16, 185, 129, 0.15); color: var(--success); }}
    .badge-fail {{ background: rgba(239, 68, 68, 0.2); color: var(--error); }}
    .screen-meta {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .screen-message {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 1rem;
    }}
    .image-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 1rem;
      margin-top: 0.5rem;
    }}
    .image-panel {{
      background: #080c14;
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      overflow: hidden;
    }}
    .panel-label {{
      background: #172033;
      padding: 0.35rem 0.75rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .diff-label {{
      background: #3b141e;
      color: #f87171;
    }}
    .image-panel img {{
      display: block;
      width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-area">
        <h1>Skill Atlas Visual Regression Report</h1>
        <p>Commit: <code>{commit_sha}</code> &bull; Generated: {timestamp}</p>
      </div>
      <div class="stats-bar">
        <div class="stat-pill">
          <div class="stat-val status-{status_class}">{status_text}</div>
          <div class="stat-lbl">Status</div>
        </div>
        <div class="stat-pill">
          <div class="stat-val">{total_screens}</div>
          <div class="stat-lbl">Screens</div>
        </div>
        <div class="stat-pill">
          <div class="stat-val status-pass">{passed_screens}</div>
          <div class="stat-lbl">Passed</div>
        </div>
        <div class="stat-pill">
          <div class="stat-val status-fail">{failed_screens}</div>
          <div class="stat-lbl">Failed</div>
        </div>
      </div>
    </header>

    {video_section}

    <main>
      {all_cards}
    </main>
  </div>
</body>
</html>
"""
    report_path.write_text(html, encoding="utf-8")
    return report_path
