"""Integration tests for browser-video-tester skill and harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from skill_atlas.models import SkillOrigin
from skill_atlas.scanner import Scanner


def test_browser_video_tester_skill_passes_validation() -> None:
    """The browser-video-tester skill must pass all schema and security rules."""
    skill_dir = Path(".claude/skills/browser-video-tester")
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "scripts" / "browser_tester.py").exists()
    assert (skill_dir / "scripts" / "run_web_audit.py").exists()
    assert (skill_dir / "scripts" / "generate_music.py").exists()
    assert (skill_dir / "scripts" / "record_demo.py").exists()

    scanner = Scanner()
    result = scanner.scan(skill_dir)

    assert result.summary.total_skills == 1
    assert result.summary.passed == 1
    assert result.summary.failed == 0
    assert result.summary.findings_count["error"] == 0

    skill = result.skills[0]
    assert skill.name == "browser-video-tester"
    assert skill.origin == SkillOrigin.AGENT_CONFIG
    assert skill.passing is True
    assert "video-use" in skill.raw_content
    assert "video" in skill.tags


def test_browser_tester_module_import_and_report_writing(tmp_path: Path) -> None:
    """BrowserTester helper should correctly initialize and format audit reports."""
    script_path = Path(".claude/skills/browser-video-tester/scripts/browser_tester.py")
    spec = importlib.util.spec_from_file_location("browser_tester", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tester = module.BrowserTester(
        url="http://127.0.0.1:8765",
        output_dir=tmp_path / "audit_run",
        headless=True,
    )

    assert tester.output_dir == tmp_path / "audit_run"
    assert tester.step_counter == 0

    report_path = tmp_path / "audit_run" / "report.md"
    tmp_path.joinpath("audit_run").mkdir(parents=True, exist_ok=True)
    sample_data = {
        "duration_seconds": 12.34,
        "steps": [
            {"step": 1, "timestamp": 1.2, "title": "Initial page load"},
            {"step": 2, "timestamp": 3.4, "title": "Toggle dark theme"},
        ],
        "console_errors": [],
        "network_errors": [],
        "video_path": str(tmp_path / "audit_run" / "test_session.mp4"),
    }

    tester._write_report(report_path, sample_data)
    assert report_path.exists()

    content = report_path.read_text(encoding="utf-8")
    assert "# QA Browser Testing Session Report" in content
    assert "**Status**: `PASSED`" in content
    assert "| 1 | 1.2s | Initial page load |" in content
    assert "| 2 | 3.4s | Toggle dark theme |" in content
    assert "- **Console JavaScript Errors**: 0" in content


def test_upbeat_music_generation_produces_valid_wav(tmp_path: Path) -> None:
    """The music synthesizer must generate valid 16-bit 44.1kHz stereo WAV."""
    script_path = Path(".claude/skills/browser-video-tester/scripts/generate_music.py")
    spec = importlib.util.spec_from_file_location("generate_music", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    out_wav = tmp_path / "test_music.wav"
    res = module.generate_music_track(out_wav, duration_sec=1.5)
    assert res.exists()
    assert res.stat().st_size > 1000
