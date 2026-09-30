"""High-energy, punchy synthwave / EDM background music generator in pure Python.

Features:
- 128 BPM upbeat energetic tempo
- Sidechain ducking pump for that signature modern electronic bounce
- Punchy 4-on-the-floor kick with low-end thump
- Crisp snare/clap on beats 2 and 4
- Stereo 16th-note rolling hi-hat groove with velocity accents
- Driving rolling octave synth bassline
- Sparkling stereo arpeggiated chords (Am - F - C - G)
- Catchy uplifting synth lead melody
- Master limiter, stereo widening, and smooth fade-in/fade-out
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


def generate_music_track(output_wav: str | Path, duration_sec: float = 35.0) -> Path:
    sample_rate = 44100
    bpm = 128
    beat_dur = 60.0 / bpm  # ~0.46875s
    sixteenth_dur = beat_dur / 4.0  # ~0.1171875s

    total_samples = int(sample_rate * duration_sec)
    left_channel = [0.0] * total_samples
    right_channel = [0.0] * total_samples

    def add_sample(idx: int, l_val: float, r_val: float) -> None:
        if 0 <= idx < total_samples:
            left_channel[idx] += l_val
            right_channel[idx] += r_val

    # Frequencies (equal temperament)
    # Uplifting synthwave progression: Am -> F -> C -> G
    chord_bass = [55.0, 43.65, 65.41, 49.00]
    chord_triads = [
        [220.0, 261.63, 329.63, 440.0],  # Am (A3, C4, E4, A4)
        [174.61, 220.0, 261.63, 349.23],  # F  (F3, A3, C4, F4)
        [261.63, 329.63, 392.0, 523.25],  # C  (C4, E4, G4, C5)
        [196.0, 246.94, 293.66, 392.0],  # G  (G3, B3, D4, G4)
    ]
    lead_notes = [
        # Bar 1 (Am)
        [440.0, 523.25, 659.25, 523.25, 440.0, 659.25, 783.99, 659.25],
        # Bar 2 (F)
        [349.23, 440.0, 523.25, 659.25, 523.25, 440.0, 523.25, 659.25],
        # Bar 3 (C)
        [523.25, 659.25, 783.99, 1046.5, 783.99, 659.25, 523.25, 659.25],
        # Bar 4 (G)
        [392.0, 493.88, 587.33, 783.99, 587.33, 493.88, 392.0, 493.88],
    ]

    random.seed(42)
    noise_table = [random.uniform(-1.0, 1.0) for _ in range(sample_rate * 2)]  # noqa: S311

    total_sixteenths = int(duration_sec / sixteenth_dur) + 1

    for s_idx in range(total_sixteenths):
        start_time = s_idx * sixteenth_dur
        start_sample = int(start_time * sample_rate)
        beat_in_bar = (s_idx // 4) % 4
        sixteenth_in_beat = s_idx % 4

        # 1. KICK DRUM (Every beat: 4-on-the-floor)
        if sixteenth_in_beat == 0:
            kick_dur = 0.28
            kick_samples = int(kick_dur * sample_rate)
            for i in range(kick_samples):
                t = i / sample_rate
                # Punchy pitch drop: 160Hz -> 45Hz
                freq = 45.0 + 115.0 * math.exp(-t * 30.0)
                env = math.exp(-t * 11.0)
                click = 0.35 * math.sin(2.0 * math.pi * 1100.0 * t) * math.exp(-t * 90.0)
                body = math.sin(2.0 * math.pi * freq * t)
                val = (body + click) * env * 0.8
                add_sample(start_sample + i, val, val)

        # 2. SNARE / CLAP (Beats 2 & 4 of each 4-beat bar)
        if beat_in_bar in (1, 3) and sixteenth_in_beat == 0:
            snare_dur = 0.26
            snare_samples = int(snare_dur * sample_rate)
            for i in range(snare_samples):
                t = i / sample_rate
                tone = math.sin(2.0 * math.pi * 190.0 * t) * math.exp(-t * 24.0)
                noise = noise_table[i % len(noise_table)] * math.exp(-t * 15.0)
                val = (tone * 0.35 + noise * 0.65) * 0.6
                add_sample(start_sample + i, val * 0.95, val * 1.05)

        # 3. HI-HAT GROOVE (16th notes with open off-beat accents)
        is_open_hat = sixteenth_in_beat == 2
        hat_dur = 0.13 if is_open_hat else 0.045
        hat_samples = int(hat_dur * sample_rate)
        hat_gain = 0.30 if is_open_hat else (0.19 if sixteenth_in_beat == 0 else 0.13)
        for i in range(hat_samples):
            t = i / sample_rate
            n_idx = (i * 3 + s_idx * 29) % len(noise_table)
            noise_hp = noise_table[n_idx] - noise_table[(n_idx - 1) % len(noise_table)]
            env = math.exp(-t * (24.0 if is_open_hat else 70.0))
            val = noise_hp * env * hat_gain
            # Stereo spread
            add_sample(start_sample + i, val * 1.15, val * 0.85)

        # Calculate sidechain ducking envelope from recent kick
        # Kicks happen when sixteenth_in_beat == 0
        t_since_kick = sixteenth_in_beat * sixteenth_dur

        # 4. ROLLING SYNTH BASSLINE
        bar_idx = (s_idx // 16) % 4
        base_f = chord_bass[bar_idx]
        bass_oct = 2.0 if (sixteenth_in_beat in (1, 3)) else 1.0
        bass_freq = base_f * bass_oct
        bass_samples = int(sixteenth_dur * 0.95 * sample_rate)
        for i in range(bass_samples):
            t = i / sample_rate
            local_t_kick = t_since_kick + t
            sc = 0.45 + 0.55 * (1.0 - math.exp(-local_t_kick * 16.0))
            env = math.exp(-t * 13.0)
            w = 2.0 * math.pi * bass_freq * t
            saw = (
                math.sin(w)
                + 0.55 * math.sin(2.0 * w)
                + 0.28 * math.sin(3.0 * w)
                + 0.14 * math.sin(4.0 * w)
            ) * 0.35
            val = saw * env * 0.52 * sc
            add_sample(start_sample + i, val, val)

        # 5. SPARKLING ARPEGGIATED SYNTH CHORDS
        triad = chord_triads[bar_idx]
        arp_note = triad[s_idx % len(triad)]
        arp_samples = int(sixteenth_dur * 1.8 * sample_rate)
        for i in range(arp_samples):
            t = i / sample_rate
            local_t_kick = t_since_kick + t
            sc = 0.55 + 0.45 * (1.0 - math.exp(-local_t_kick * 16.0))
            env = math.exp(-t * 8.5)
            w = 2.0 * math.pi * arp_note * t
            sound = (
                math.sin(w)
                + 0.32 * math.sin(3.0 * w)
                + 0.16 * math.sin(5.0 * w)
                + 0.08 * math.sin(7.0 * w)
            ) * 0.24
            pan_pos = (s_idx % 4) / 3.0
            l_gain = math.cos(pan_pos * math.pi * 0.5)
            r_gain = math.sin(pan_pos * math.pi * 0.5)
            val = sound * env * sc
            add_sample(start_sample + i, val * l_gain, val * r_gain)

        # 6. ENERGETIC SYNTH LEAD MELODY
        if sixteenth_in_beat in (0, 2):
            eighth_idx = (s_idx // 2) % 8
            lead_f = lead_notes[bar_idx][eighth_idx]
            lead_samples = int(sixteenth_dur * 2.9 * sample_rate)
            for i in range(lead_samples):
                t = i / sample_rate
                env = math.exp(-t * 4.2)
                w = 2.0 * math.pi * lead_f * t
                vibrato = 1.0 + 0.009 * math.sin(2.0 * math.pi * 5.8 * t)
                lead_sound = (
                    math.sin(w * vibrato)
                    + 0.45 * math.sin(2.0 * w * vibrato + 0.25)
                    + 0.22 * math.sin(3.0 * w * vibrato + 0.5)
                ) * 0.25
                add_sample(start_sample + i, lead_sound * env * 0.85, lead_sound * env * 0.85)

    # Master Limiter, Saturation & Fade In/Out
    fade_in_samples = int(sample_rate * 0.5)
    fade_out_samples = int(sample_rate * 2.2)

    max_peak = 0.0001
    for i in range(total_samples):
        if i < fade_in_samples:
            factor = i / fade_in_samples
            left_channel[i] *= factor
            right_channel[i] *= factor
        elif i >= total_samples - fade_out_samples:
            factor = (total_samples - 1 - i) / fade_out_samples
            left_channel[i] *= factor
            right_channel[i] *= factor

        # Warm analog-style tanh saturation
        left_channel[i] = math.tanh(left_channel[i] * 1.15)
        right_channel[i] = math.tanh(right_channel[i] * 1.15)
        max_peak = max(max_peak, abs(left_channel[i]), abs(right_channel[i]))

    gain = 0.94 / max_peak

    out_p = Path(output_wav).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_p), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        packed_frames = bytearray()
        for i in range(total_samples):
            l_val = int(max(-32767, min(32767, left_channel[i] * gain * 32767)))
            r_val = int(max(-32767, min(32767, right_channel[i] * gain * 32767)))
            packed_frames.extend(struct.pack("<hh", l_val, r_val))
        wf.writeframes(packed_frames)

    return out_p


if __name__ == "__main__":
    out = generate_music_track("artifacts/upbeat_demo_music.wav", duration_sec=35.0)
    print(f"Generated upbeat music: {out} ({out.stat().st_size} bytes)")
