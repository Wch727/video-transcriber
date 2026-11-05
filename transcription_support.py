"""Audio preparation and conservative transcript review helpers."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import subprocess
import tempfile
from collections import defaultdict, deque
from pathlib import Path


def _audio_command(source: Path, ffmpeg: str, channel: str, enhance: bool) -> list[str]:
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
    return command


def iter_audio_chunks(source: Path, ffmpeg: str, channel: str = "mix", enhance: bool = False,
                      *, chunk_seconds: int = 20):
    """Decode continuously, retaining only one bounded PCM window in memory."""
    import numpy as np

    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")
    command = _audio_command(source, ffmpeg, channel, enhance)
    chunk_bytes = int(chunk_seconds * 16000) * 4
    if chunk_bytes < 4:
        raise ValueError("Audio window must contain at least one sample")
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        samples = 0
        try:
            while True:
                data = process.stdout.read(chunk_bytes)
                if not data:
                    break
                if len(data) % 4:
                    raise RuntimeError("Incomplete PCM sample from ffmpeg")
                audio = np.frombuffer(data, dtype="<f4").copy()
                yield samples / 16000, audio
                samples += len(audio)
            if process.wait(timeout=30):
                errors.seek(0)
                raise RuntimeError(errors.read(65536).decode("utf-8", errors="replace").strip()
                                   or "Audio decoding failed")
            if not samples:
                raise RuntimeError("Audio contains no samples")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def decode_audio(source: Path, ffmpeg: str, channel: str = "mix", enhance: bool = False):
    """Return a complete array for diagnostic tools; recognition uses the iterator."""
    import numpy as np
    return np.concatenate([audio for _, audio in iter_audio_chunks(source, ffmpeg, channel, enhance)])


def audio_duration(source: Path, ffprobe: str | None) -> float:
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True, check=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        duration = float(result.stdout.strip())
        return duration if math.isfinite(duration) and duration > 0 else 0.0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


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
               "options": options, "segments": review_segments(result),
               "document_sha256": _text_hash(output.read_text(encoding="utf-8"))}
    review_path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def review_matches_text(data: dict, text: str) -> bool:
    return not data.get("document_sha256") or data["document_sha256"] == _text_hash(text)


_STAMP = r"\d{2,}:\d{2}:\d{2}(?:[.,]\d{1,3})?"


def _stamp_seconds(stamp: str) -> float:
    hours, minutes, seconds = stamp.replace(",", ".").split(":")
    if int(minutes) >= 60 or float(seconds) >= 60:
        raise ValueError("Invalid transcript timestamp")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_transcript_segments(text: str, suffix: str) -> list[dict]:
    if not text.strip() and suffix == ".txt":
        return []
    segments = []
    if suffix == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
            raise ValueError("JSON must contain a segments array")
        segments = payload["segments"]
        if "text" in payload:
            if not isinstance(payload["text"], str):
                raise ValueError("JSON text must be a string")
            joined = "".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict))
            if "".join(payload["text"].split()) != "".join(joined.split()):
                raise ValueError("JSON text and segments disagree; update both before saving")
    elif suffix == ".txt":
        markers = list(re.finditer(rf"^\[({_STAMP}) - ({_STAMP})\][ \t]*", text, re.MULTILINE))
        if not markers or text[:markers[0].start()].strip():
            raise ValueError("Keep the timestamp labels when editing; export a reading copy to remove them.")
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            body = text[marker.end():end].strip()
            if re.search(r"^\[\d", body, re.MULTILINE):
                raise ValueError("Invalid transcript timestamp")
            segments.append({"start": _stamp_seconds(marker[1]), "end": _stamp_seconds(marker[2]), "text": body})
    elif suffix in {".srt", ".vtt"}:
        body = text.replace("\r\n", "\n").strip()
        if suffix == ".vtt":
            if not body.startswith("WEBVTT\n") and body != "WEBVTT":
                raise ValueError("Missing WEBVTT header")
            body = body[len("WEBVTT"):].strip()
        for block in re.split(r"\n[ \t]*\n", body) if body else []:
            lines = block.splitlines()
            timing_index = 0 if "-->" in lines[0] else 1
            if timing_index >= len(lines):
                raise ValueError("Missing subtitle timing")
            timing = re.fullmatch(rf"({_STAMP})\s+-->\s+({_STAMP})(?:[ \t]+.*)?", lines[timing_index])
            if not timing:
                raise ValueError("Invalid subtitle timing")
            segments.append({"start": _stamp_seconds(timing[1]), "end": _stamp_seconds(timing[2]),
                             "text": "\n".join(lines[timing_index + 1:]).strip()})
    else:
        raise ValueError("Unsupported transcript format")
    result = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            raise ValueError("Invalid transcript segment")
        start, end = float(segment["start"]), float(segment["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError("Invalid transcript timing range")
        if not segment["text"].strip():
            raise ValueError("Remove the entire segment instead of leaving empty text")
        result.append({"start": start, "end": end, "text": segment["text"].strip()})
    return result


def save_edited_transcript(output: Path, text: str) -> None:
    """Stage both documents; roll back metadata if replacing the transcript fails."""
    sidecar = review_path(output)
    with tempfile.TemporaryDirectory(prefix=".transcript-save-", dir=output.parent) as directory:
        staging = Path(directory)
        new_text = staging / "transcript"
        new_text.write_text(text, encoding="utf-8", newline="\n")
        if sidecar.exists():
            original = sidecar.read_bytes()
            data = json.loads(original)
            if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
                raise ValueError("Invalid review file; transcript was not saved")
            if not review_matches_text(data, output.read_text(encoding="utf-8")):
                raise ValueError("Review data is out of date; restore the matching transcript or transcribe again before saving.")
            suffix = output.suffix.lower()
            def timing_key(segment):
                values = (float(segment["start"]), float(segment["end"]))
                if suffix == ".txt":
                    return tuple(int(value) for value in values)
                if suffix in {".srt", ".vtt"}:
                    return tuple(round(value * 1000) for value in values)
                return values
            old = defaultdict(deque)
            for segment in data["segments"]:
                old[timing_key(segment)].append(segment)
            segments = parse_transcript_segments(text, output.suffix.lower())
            for segment in segments:
                candidates = old.get(timing_key(segment))
                previous = candidates.popleft() if candidates else None
                segment["reasons"] = list(previous.get("reasons", [])) if previous else ["manual_review"]
                segment["edited"] = previous is None or previous.get("edited", False) or segment["text"] != previous.get("text")
                if previous:
                    segment.update(start=previous["start"], end=previous["end"])
            data.update(segments=segments, document_sha256=_text_hash(text))
            new_review, backup = staging / "review", staging / "review-backup"
            new_review.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            backup.write_bytes(original)
            os.replace(new_review, sidecar)
            try:
                os.replace(new_text, output)
            except OSError:
                os.replace(backup, sidecar)
                raise
        else:
            os.replace(new_text, output)


def reading_copy(text: str) -> str:
    """Remove TXT/SRT/VTT time labels, retaining the actual recognized wording."""
    lines = []
    source_lines = text.splitlines()
    timing_line = re.compile(rf"^{_STAMP}\s+-->\s+{_STAMP}(?:[ \t]+.*)?$")
    for index, line in enumerate(source_lines):
        line = line.strip()
        cue_number = line.isdigit() and index + 1 < len(source_lines) and timing_line.fullmatch(source_lines[index + 1].strip())
        if not line or (line == "WEBVTT" and index == 0) or cue_number or timing_line.fullmatch(line):
            continue
        line = re.sub(rf"^\[{_STAMP} - {_STAMP}\]\s*", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def plain_transcript_text(text: str, suffix: str) -> str:
    if suffix.lower() != ".json":
        return reading_copy(text)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Expected a transcript JSON object")
    if isinstance(payload.get("text"), str) and payload["text"].strip():
        return payload["text"].strip() + ("\n" if payload["text"].strip() else "")
    segments = payload.get("segments")
    if segments is None and payload.get("text") == "":
        return ""
    if not isinstance(segments, list) or any(not isinstance(s, dict) or not isinstance(s.get("text"), str) for s in segments):
        raise ValueError("Expected transcript text or text segments")
    return "\n".join(s["text"] for s in segments) + ("\n" if segments else "")
