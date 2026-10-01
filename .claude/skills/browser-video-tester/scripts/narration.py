"""Offline voice-over synthesis and audio mixing for demo videos.

Speech is synthesized locally with Piper (neural TTS) when a voice model is available,
falling back to the macOS `say` command. No text is sent to external services.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PIPER_MODELS = (
    Path.home() / "piper-models/en_US-lessac-medium/en_US-lessac-medium.onnx",
    Path.home() / ".voice-assistant/voices/en_US-amy-medium.onnx",
)
DEFAULT_SAY_VOICE = "Samantha"


@dataclass
class VoiceClip:
    """A synthesized narration line placed on the video timeline."""

    text: str
    path: Path
    duration: float
    start: float = 0.0  # seconds from the start of the browser session


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")


def media_duration(path: Path) -> float:
    """Return the duration of an audio or video file in seconds."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    res = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(res.stdout.strip())


def find_piper_model() -> Path | None:
    env_model = os.environ.get("SKILL_ATLAS_PIPER_MODEL")
    candidates = [Path(env_model)] if env_model else list(DEFAULT_PIPER_MODELS)
    return next((p for p in candidates if p.exists()), None)


class Narrator:
    """Synthesizes narration lines into WAV clips with a pleasant female voice."""

    def __init__(self, work_dir: Path, length_scale: float = 1.0) -> None:
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.length_scale = length_scale
        self.piper = shutil.which("piper")
        self.model = find_piper_model() if self.piper else None
        self._counter = 0

    @property
    def engine(self) -> str:
        return f"piper ({self.model.stem})" if self.model else f"say ({DEFAULT_SAY_VOICE})"

    def synthesize(self, text: str) -> VoiceClip:
        self._counter += 1
        out = self.work_dir / f"line_{self._counter:02d}.wav"
        if self.model and self.piper:
            subprocess.run(
                [
                    self.piper,
                    "-m",
                    str(self.model),
                    "-f",
                    str(out),
                    "--length-scale",
                    str(self.length_scale),
                    "--sentence-silence",
                    "0.25",
                ],
                input=text,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            aiff = out.with_suffix(".aiff")
            subprocess.run(
                ["say", "-v", DEFAULT_SAY_VOICE, "-o", str(aiff), text],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [ffmpeg_bin(), "-y", "-i", str(aiff), str(out)], capture_output=True, check=True
            )
        return VoiceClip(text=text, path=out, duration=media_duration(out))


def render_with_voiceover(
    video_in: Path,
    video_out: Path,
    clips: list[VoiceClip],
    trim_start: float = 0.0,
    music_wav: Path | None = None,
    music_volume: float = 0.12,
    timelapse: tuple[float, float] | None = None,
    timelapse_seconds: float = 6.0,
) -> float:
    """Mux narration clips (and optional ducked background music) into an H.264/AAC MP4.

    `clip.start` and `timelapse` values are relative to the untrimmed video. `trim_start`
    seconds are cut from the beginning, and the `timelapse` window (e.g. waiting for a long
    scan) is sped up to last `timelapse_seconds`. No narration may start inside that window.
    Returns the number of seconds removed by the timelapse.
    """
    cmd: list[str] = [ffmpeg_bin(), "-y", "-i", str(video_in)]
    for clip in clips:
        cmd += ["-i", str(clip.path)]

    filters: list[str] = []
    if timelapse and timelapse[1] - timelapse[0] > timelapse_seconds:
        lapse_start, lapse_end = timelapse
        factor = (lapse_end - lapse_start) / timelapse_seconds
        saved = (lapse_end - lapse_start) - timelapse_seconds
        filters += [
            f"[0:v]trim=start={trim_start:.3f}:end={lapse_start:.3f},setpts=PTS-STARTPTS[vpre]",
            f"[0:v]trim=start={lapse_start:.3f}:end={lapse_end:.3f},"
            f"setpts=(PTS-STARTPTS)/{factor:.4f}[vlapse]",
            f"[0:v]trim=start={lapse_end:.3f},setpts=PTS-STARTPTS[vpost]",
            "[vpre][vlapse][vpost]concat=n=3:v=1:a=0[vout]",
        ]
    else:
        lapse_end, saved = float("inf"), 0.0
        filters.append(f"[0:v]trim=start={trim_start:.3f},setpts=PTS-STARTPTS[vout]")

    voice_labels: list[str] = []
    for idx, clip in enumerate(clips, start=1):
        shift = saved if clip.start >= lapse_end else 0.0
        delay_ms = max(0, round((clip.start - trim_start - shift) * 1000))
        label = f"v{idx}"
        filters.append(
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        voice_labels.append(f"[{label}]")
    filters.append(
        f"{''.join(voice_labels)}amix=inputs={len(clips)}:normalize=0,"
        "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=120[voice]"
    )

    if music_wav:
        music_idx = len(clips) + 1
        cmd += ["-i", str(music_wav)]
        filters.append("[voice]asplit=2[voice_out][voice_key]")
        filters.append(
            f"[{music_idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"volume={music_volume}[music]"
        )
        filters.append(
            "[music][voice_key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[ducked]"
        )
        filters.append(
            "[voice_out][ducked]amix=inputs=2:normalize=0,alimiter=limit=0.95,apad[aout]"
        )
    else:
        filters.append("[voice]alimiter=limit=0.95,apad[aout]")

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "slow",
        "-crf",
        "22",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        str(video_out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg voice-over render failed:\n{res.stderr[-2000:]}")
    return saved
