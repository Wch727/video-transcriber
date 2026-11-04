"""Audio preparation and conservative transcript review helpers."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def decode_audio(source: Path, ffmpeg: str, channel: str = "mix", enhance: bool = False):
    import numpy as np

    if channel not in {"mix", "left", "right"}:
        raise ValueError(f"Unknown audio channel: {channel}")
    filters = []
    if channel != "mix":
        # Upmix mono inputs first so either selection also works on mono recordings.
        filters.extend(["aformat=channel_layouts=stereo", f"pan=mono|c0=c{0 if channel == 'left' else 1}"])
    if enhance:
        filters.extend(["highpass=f=80", "afftdn=nf=-35", "dynaudnorm=f=150:g=9:p=0.9:m=8"])
    command = [ffmpeg, "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0", "-vn"]
    if filters:
        command.extend(["-af", ",".join(filters)])
    command.extend(["-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"])
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "Audio decoding failed")
    audio = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if not audio.size:
        raise RuntimeError("Audio contains no samples")
    return audio


def review_path(output: Path) -> Path:
    return output.with_name(output.name + ".review.json")


def review_segments(result: dict) -> list[dict]:
    segments = []
    for segment in result.get("segments") or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        reasons = list(segment.get("review_reasons") or [])
        for key, threshold, reason, greater in (
            ("avg_logprob", -0.8, "low_confidence", False),
            ("no_speech_prob", 0.5, "possible_noise", True),
            ("compression_ratio", 2.4, "possible_repetition", True),
        ):
            value = segment.get(key)
            if isinstance(value, (int, float)) and ((value > threshold) if greater else (value < threshold)):
                reasons.append(reason)
        segments.append({
            "start": float(segment.get("start", 0)), "end": float(segment.get("end", 0)),
            "text": text, "reasons": reasons,
        })
    return segments


def save_review(output: Path, source: Path, result: dict, **options) -> None:
    payload = {"version": 1, "source": str(source.resolve()), "language": result.get("language"),
               "options": options, "segments": review_segments(result)}
    review_path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reading_copy(text: str) -> str:
    """Remove TXT/SRT/VTT time labels, retaining the actual recognized wording."""
    lines = []
    source_lines = text.splitlines()
    for index, line in enumerate(source_lines):
        line = line.strip()
        cue_number = line.isdigit() and index + 1 < len(source_lines) and "-->" in source_lines[index + 1]
        if not line or (line == "WEBVTT" and index == 0) or cue_number or "-->" in line:
            continue
        line = re.sub(r"^\[\d{2,}:\d{2}:\d{2} - \d{2,}:\d{2}:\d{2}\]\s*", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")
