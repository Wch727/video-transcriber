#!/usr/bin/env python
"""Extract text from video files.

Supported modes:
  audio     Transcribe speech from the video's audio with the OpenAI API.
  whisper   Transcribe speech locally with openai-whisper, no API key required.
  subtitle  Extract embedded subtitle tracks with ffmpeg and ffprobe.
  ocr       OCR visible text from sampled video frames with ffmpeg + tesseract.
  auto      Try embedded subtitles first, then local Whisper, then OpenAI.

Examples:
  python video_text_extractor.py 4-1.mp4 --mode audio --language zh
  python video_text_extractor.py 4-1.mp4 --mode whisper --whisper-model base
  python video_text_extractor.py 4-1.mp4 --mode subtitle
  python video_text_extractor.py 4-1.mp4 --mode ocr --ocr-interval 2
"""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


if sys.platform == "win32":
    import io

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DEFAULT_MAX_UPLOAD_MB = 24.0


def _load_ocr_languages() -> tuple[dict[str, str], dict[str, str]]:
    """Load shared OCR language maps from ``ocr_languages.json``."""
    json_path = Path(__file__).resolve().parent / "ocr_languages.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data.get("map", {}), data.get("aliases", {})
        except Exception:
            pass
    # Fallback hard-coded values so the tool still works if the JSON is missing.
    lang_map: dict[str, str] = {
        "zh": "chi_sim", "en": "eng", "ja": "jpn", "ko": "kor", "es": "spa",
        "fr": "fra", "de": "deu", "it": "ita", "pt": "por", "ru": "rus",
        "ar": "ara", "hi": "hin", "vi": "vie", "th": "tha", "tr": "tur",
        "nl": "nld", "sv": "swe", "pl": "pol", "uk": "ukr", "id": "ind",
        "ms": "msa", "bn": "ben", "ur": "urd", "fa": "fas", "he": "heb",
        "el": "ell", "cs": "ces", "da": "dan", "fi": "fin", "hu": "hun",
        "ro": "ron", "no": "nor", "ca": "cat", "la": "lat", "sk": "slk",
        "sl": "slv", "hr": "hrv", "sr": "srp", "bg": "bul", "lt": "lit",
        "lv": "lav", "et": "est", "sw": "swa", "ml": "mal", "ta": "tam",
        "te": "tel", "ka": "kat", "kk": "kaz", "ne": "nep", "am": "amh",
        "my": "mya", "km": "khm", "lo": "lao", "mn": "mon", "az": "aze",
        "uz": "uzb",
    }
    aliases: dict[str, str] = {
        "zh-cn": "chi_sim", "zh-sg": "chi_sim", "zh-hans": "chi_sim",
        "zh-tw": "chi_tra", "zh-hk": "chi_tra", "zh-mo": "chi_tra", "zh-hant": "chi_tra",
    }
    return lang_map, aliases


_TESSERACT_LANG_MAP, _TESSERACT_LANG_ALIASES = _load_ocr_languages()


def map_ocr_language_part(part: str) -> str:
    normalized = part.lower()
    alias_key = normalized.replace("_", "-")
    if alias_key in _TESSERACT_LANG_ALIASES:
        return _TESSERACT_LANG_ALIASES[alias_key]
    if "_" in normalized:
        base_language = normalized.split("_", 1)[0]
        if base_language in _TESSERACT_LANG_MAP:
            return _TESSERACT_LANG_MAP[base_language]
    if "-" in normalized:
        normalized = normalized.split("-", 1)[0]
    return _TESSERACT_LANG_MAP.get(normalized, normalized)


def map_ocr_language(code: str) -> str:
    stripped = code.strip()
    if not stripped:
        fail("--language 不能为空。")
    parts = [part for part in re.split(r"[+ ]+", stripped) if part]
    if len(parts) > 1:
        return "+".join(map_ocr_language_part(part) for part in parts)
    return map_ocr_language_part(stripped)


def normalize_speech_language(code: str | None) -> str | None:
    if not code:
        return None
    normalized = code.strip()
    if not normalized:
        return None
    return re.split(r"[-_]", normalized, maxsplit=1)[0].lower()


@dataclass(frozen=True)
class ToolStatus:
    ffmpeg: str | None
    ffprobe: str | None
    tesseract: str | None
    openai_key: bool
    local_whisper: bool
    imageio_ffmpeg: bool
    cuda_gpu: bool


def which(name: str) -> str | None:
    return shutil.which(name)


def first_existing(paths: list[Path]) -> str | None:
    for path in paths:
        if path.exists():
            return str(path)
    return None


def winget_ffmpeg_executable(name: str) -> str | None:
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    root = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
    if not root.exists():
        return None
    matches = sorted(root.glob(f"Gyan.FFmpeg_*/*/bin/{name}.exe"), reverse=True)
    return str(matches[0]) if matches else None


def tesseract_executable() -> str | None:
    return which("tesseract") or first_existing([
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
    ])


def tesseract_language_parts(language: str) -> list[str]:
    return [part for part in re.split(r"[+ ]+", language.strip()) if part]


def tesseract_data_dirs(status: ToolStatus) -> list[Path]:
    dirs = [Path(__file__).resolve().parent / "tessdata"]
    tessdata_prefix = os.getenv("TESSDATA_PREFIX")
    if tessdata_prefix:
        prefix = Path(tessdata_prefix)
        dirs.extend([prefix, prefix / "tessdata"])
    if status.tesseract:
        dirs.append(Path(status.tesseract).resolve().parent / "tessdata")
    unique_dirs: list[Path] = []
    seen: set[Path] = set()
    for data_dir in dirs:
        resolved = data_dir.expanduser()
        if resolved not in seen:
            unique_dirs.append(resolved)
            seen.add(resolved)
    return unique_dirs


def _find_tessdata_dir_for_parts(parts: list[str], status: ToolStatus) -> Path | None:
    """Return a directory that contains all ``parts`` as ``.traineddata`` files.

    Strategy:
    1. Exact match — single directory that has every required file.
    2. Combined match — copy missing files from other directories into the best
       candidate so that all required languages end up in one place.  The
       combined directory lives under ``.video_text_cache`` and is reused across
       calls while the process is running.
    """
    dirs = tesseract_data_dirs(status)
    if not parts:
        return dirs[0] if dirs else None

    # ---- pass 1: exact match ----
    for data_dir in dirs:
        if data_dir.exists() and all((data_dir / f"{part}.traineddata").exists() for part in parts):
            return data_dir

    # ---- pass 2: try to build a combined dir ----
    if len(parts) == 1:
        # Only one language — pick the first directory that has it.
        for data_dir in dirs:
            if data_dir.exists() and (data_dir / f"{parts[0]}.traineddata").exists():
                return data_dir
        return None

    # Find the "best" candidate directory (most languages already present).
    best_dir: Path | None = None
    best_hits = -1
    missing_by_dir: dict[Path, list[str]] = {}
    for data_dir in dirs:
        if not data_dir.exists():
            missing_by_dir[data_dir] = parts
            continue
        hits = [p for p in parts if (data_dir / f"{p}.traineddata").exists()]
        missing = [p for p in parts if p not in hits]
        missing_by_dir[data_dir] = missing
        if len(hits) > best_hits:
            best_hits = len(hits)
            best_dir = data_dir

    if best_dir is None or best_hits == 0:
        return None

    missing = missing_by_dir.get(best_dir, [])
    if not missing:
        # Shouldn't happen (would have been caught by pass 1), but be safe.
        return best_dir

    # Build a dedicated combined directory so we never mutate a user-owned
    # Tesseract install or the project's own tessdata/.
    try:
        cache_root = Path(__file__).resolve().parent / ".video_text_cache"
        combined_dir = cache_root / "tessdata_combined"
        combined_dir.mkdir(parents=True, exist_ok=True)

        for part in missing:
            src: Path | None = None
            for d in dirs:
                candidate = d / f"{part}.traineddata"
                if candidate.exists():
                    src = candidate
                    break
            if src is None:
                # One required language cannot be found anywhere.
                return None
            dst = combined_dir / f"{part}.traineddata"
            if not dst.exists():
                shutil.copy2(src, dst)

        # Also make sure the languages already in best_dir are discoverable
        # by adding symlinks (or copies on systems that don't support symlinks).
        for part in parts:
            combined_file = combined_dir / f"{part}.traineddata"
            if not combined_file.exists():
                candidate = best_dir / f"{part}.traineddata"
                if candidate.exists():
                    try:
                        combined_file.symlink_to(candidate)
                    except OSError:
                        shutil.copy2(candidate, combined_file)

        return combined_dir
    except OSError:
        return None


def tesseract_data_dir_for(language: str, status: ToolStatus) -> Path | None:
    parts = tesseract_language_parts(language)
    return _find_tessdata_dir_for_parts(parts, status)


def default_ocr_language(status: ToolStatus) -> str:
    if tesseract_data_dir_for("chi_sim+eng", status):
        return "chi_sim+eng"
    if tesseract_data_dir_for("eng", status):
        return "eng"
    for data_dir in tesseract_data_dirs(status):
        if not data_dir.exists():
            continue
        languages = sorted(path.stem for path in data_dir.glob("*.traineddata") if path.stem != "osd")
        if languages:
            return languages[0]
    return "chi_sim+eng"


def _detect_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def detect_tools() -> ToolStatus:
    return ToolStatus(
        ffmpeg=which("ffmpeg") or winget_ffmpeg_executable("ffmpeg"),
        ffprobe=which("ffprobe") or winget_ffmpeg_executable("ffprobe"),
        tesseract=tesseract_executable(),
        openai_key=bool(os.getenv("OPENAI_API_KEY")),
        local_whisper=module_available("whisper"),
        imageio_ffmpeg=module_available("imageio_ffmpeg"),
        cuda_gpu=_detect_cuda(),
    )


def module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def imageio_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_exe.exists():
        return None
    return str(ffmpeg_exe)


def ffmpeg_command(status: ToolStatus) -> str | None:
    return status.ffmpeg or imageio_ffmpeg_exe()


def run_command(command: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print("+ " + " ".join(command))
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@contextmanager
def local_temp_dir(parent: Path, prefix: str):
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = parent / f"{prefix}{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def fail(message: str) -> None:
    raise SystemExit(f"Error: {message}")


def ensure_file(path: Path) -> Path:
    if not path.exists():
        fail(f"找不到文件: {path}")
    if not path.is_file():
        fail(f"不是文件: {path}")
    return path


def ensure_output_file(path: Path) -> Path:
    if path.exists() and path.is_dir():
        fail(f"输出路径是目录，请指定文件路径: {path}")
    if path.parent.exists() and not path.parent.is_dir():
        fail(f"输出目录不是文件夹: {path.parent}")
    return path


def default_output(video: Path, mode: str, output_format: str = "txt") -> Path:
    suffix = {
        "audio": "transcript",
        "whisper": "transcript",
        "sensevoice": "sensevoice",
        "subtitle": "subtitles",
        "ocr": "ocr",
        "auto": "text",
    }.get(mode, "text")
    ext = "txt" if output_format in {"text", "verbose_json"} else output_format
    return video.with_name(f"{video.stem}_{suffix}.{ext}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"已写入: {path}")


def _tool_version(exe: str | None, arg: str = "-version") -> str | None:
    """Return the first line of --version/-version output for *exe*, or None."""
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, arg], capture_output=True, text=True, timeout=5,
        )
        first = (result.stdout or result.stderr or "").splitlines()
        return first[0].strip() if first else None
    except Exception:
        return None


def dump_status(video: Path, status: ToolStatus) -> None:
    size_mb = video.stat().st_size / 1024 / 1024
    ffmpeg = status.ffmpeg or imageio_ffmpeg_exe()
    print(f"视频: {video}")
    print(f"大小: {size_mb:.2f} MB")
    ffmpeg_ver = _tool_version(ffmpeg)
    print(f"ffmpeg: {ffmpeg_ver or (ffmpeg or '未找到')}")
    ffprobe_ver = _tool_version(status.ffprobe)
    print(f"ffprobe: {ffprobe_ver or (status.ffprobe or '未找到')}")
    tess_ver = _tool_version(status.tesseract, "--version")
    print(f"tesseract: {tess_ver or (status.tesseract or '未找到')}")
    print(f"OPENAI_API_KEY: {'已设置' if status.openai_key else '未设置'}")
    print(f"openai-whisper: {'已安装' if status.local_whisper else '未安装'}")
    print(f"imageio-ffmpeg: {'已安装' if status.imageio_ffmpeg else '未安装'}")


def subtitle_streams(video: Path, status: ToolStatus) -> list[dict[str, Any]]:
    if status.ffprobe:
        result = run_command(
            [
                status.ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-select_streams",
                "s",
                "-of",
                "json",
                str(video),
            ],
            quiet=True,
        )
        data = json.loads(result.stdout or "{}")
        return data.get("streams", [])

    fail("检测内嵌字幕需要 ffprobe。请安装包含 ffprobe 的完整 ffmpeg，并加入 PATH。")


def subtitle_muxer(output_format: str | None) -> str | None:
    if output_format == "vtt":
        return "webvtt"
    if output_format == "srt":
        return "srt"
    return None


def subtitle_suffix(output_format: str | None) -> str:
    if output_format in {"srt", "vtt"}:
        return f".{output_format}"
    return ".srt"


def extract_subtitles(
    video: Path,
    out: Path | None,
    status: ToolStatus,
    *,
    output_format: str | None = None,
) -> list[Path]:
    ffmpeg = ffmpeg_command(status)
    if not ffmpeg:
        fail("字幕提取需要安装 ffmpeg，并确保它在 PATH 中。")

    streams = subtitle_streams(video, status)
    if not streams:
        fail("视频里没有检测到内嵌字幕轨。")

    outputs: list[Path] = []
    default_suffix = subtitle_suffix(output_format)
    for i, stream in enumerate(streams):
        if out and i == 0:
            output_path = out
        elif out:
            output_path = out.with_name(f"{out.stem}_{i}{out.suffix or default_suffix}")
        else:
            lang = stream.get("tags", {}).get("language", f"{i}")
            output_path = video.with_name(f"{video.stem}_subtitle_{i}_{lang}{default_suffix}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-map",
            f"0:s:{i}",
        ]
        muxer = subtitle_muxer(output_format)
        if muxer:
            command.extend(["-f", muxer])
        command.append(str(output_path))
        run_command(command)
        outputs.append(output_path)
        print(f"已写入: {output_path}")
    return outputs


def parse_subtitle_time(value: str) -> float:
    timestamp = value.strip().split()[0].replace(",", ".")
    hours, minutes, seconds = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_srt_segments(path: Path) -> list[dict[str, Any]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace").strip())
    segments: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip("\ufeff ") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        text = " ".join(line.strip() for line in lines[1:] if line.strip())
        if text:
            segments.append({
                "start": parse_subtitle_time(start_raw),
                "end": parse_subtitle_time(end_raw),
                "text": text,
            })
    return segments


def write_subtitle_segments(out: Path, segments: list[dict[str, Any]], output_format: str) -> Path:
    if output_format == "json":
        payload = {
            "text": " ".join(str(segment["text"]) for segment in segments),
            "segments": segments,
        }
        write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    elif output_format == "srt":
        blocks = []
        for index, segment in enumerate(segments, start=1):
            start = format_subtitle_time(float(segment["start"]), comma=True)
            end = format_subtitle_time(float(segment["end"]), comma=True)
            blocks.append(f"{index}\n{start} --> {end}\n{segment['text']}")
        write_text(out, "\n\n".join(blocks) + ("\n" if blocks else ""))
    elif output_format == "vtt":
        blocks = ["WEBVTT"]
        for segment in segments:
            start = format_subtitle_time(float(segment["start"]), comma=False)
            end = format_subtitle_time(float(segment["end"]), comma=False)
            blocks.append(f"{start} --> {end}\n{segment['text']}")
        write_text(out, "\n\n".join(blocks) + "\n")
    else:
        text = "\n".join(str(segment["text"]) for segment in segments)
        write_text(out, text + ("\n" if text else ""))
    return out


def extract_subtitles_as(video: Path, out: Path, status: ToolStatus, output_format: str) -> Path:
    if output_format in {"srt", "vtt"}:
        outputs = extract_subtitles(video, out, status, output_format=output_format)
        return outputs[0]

    with local_temp_dir(out.parent, "video_subtitle_") as temp_dir:
        temp_srt = temp_dir / "embedded.srt"
        outputs = extract_subtitles(video, temp_srt, status)
        segments = read_srt_segments(outputs[0])
    return write_subtitle_segments(out, segments, output_format)


def api_response_to_text(response: Any, response_format: str) -> str:
    if isinstance(response, str):
        return response
    if response_format in {"json", "verbose_json"}:
        if hasattr(response, "model_dump_json"):
            return response.model_dump_json(indent=2)
        return json.dumps(response, ensure_ascii=False, indent=2)
    text = getattr(response, "text", None)
    if text:
        return text
    if hasattr(response, "model_dump"):
        return json.dumps(response.model_dump(), ensure_ascii=False, indent=2)
    return str(response)


def transcribe_one_file(
    media_path: Path,
    *,
    model: str,
    language: str | None,
    prompt: str | None,
    response_format: str,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        fail("需要安装 openai 包: python -m pip install openai")
        raise exc

    if not os.getenv("OPENAI_API_KEY"):
        fail(
            "未检测到 OPENAI_API_KEY。请先在 PowerShell 中设置: "
            '$env:OPENAI_API_KEY="你的 API Key"'
        )

    client = OpenAI()
    kwargs: dict[str, Any] = {
        "model": model,
        "file": media_path.open("rb"),
        "response_format": response_format,
    }
    if language:
        kwargs["language"] = language
    if prompt:
        kwargs["prompt"] = prompt
    if response_format == "verbose_json":
        kwargs["timestamp_granularities"] = ["segment"]

    try:
        response = client.audio.transcriptions.create(**kwargs)
    finally:
        kwargs["file"].close()

    return api_response_to_text(response, response_format)


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    start: float


def split_audio_with_ffmpeg(
    video: Path,
    workdir: Path,
    status: ToolStatus,
    chunk_seconds: int,
) -> list[AudioChunk]:
    ffmpeg = ffmpeg_command(status)
    if not ffmpeg:
        fail("文件较大时需要 ffmpeg 来压缩或切分音频。")

    pattern = workdir / "chunk_%03d.wav"
    manifest = workdir / "chunks.csv"
    run_command(
        [
            ffmpeg,
            "-y",
            "-nostdin",
            "-i",
            str(video),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            "-segment_list",
            str(manifest),
            "-segment_list_type",
            "csv",
            str(pattern),
        ]
    )
    chunks = []
    with manifest.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) != 3:
                fail("ffmpeg 返回了无效的音频切片清单。")
            path = workdir / Path(row[0]).name
            start, end = float(row[1]), float(row[2])
            if not path.is_file() or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                fail("ffmpeg 返回了无效的音频切片或时间戳。")
            if chunks and start < chunks[-1].start:
                fail("ffmpeg 音频切片时间戳顺序错误。")
            chunks.append(AudioChunk(path, start))
    if not chunks:
        fail("ffmpeg 没有生成音频切片，请确认视频包含音轨。")
    return chunks


@dataclass
class _ChunkSegment:
    """A single transcribed segment with absolute start/end times."""

    start: float
    end: float
    text: str


@dataclass
class _ChunkTranscript:
    """Parsed chunk transcription with optional timestamped segments."""

    text: str
    segments: list[_ChunkSegment]


def _parse_openai_verbose_transcript(raw: str) -> _ChunkTranscript:
    """Parse verbose OpenAI transcription JSON into text plus segments."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _ChunkTranscript(text=raw.strip(), segments=[])
    if not isinstance(payload, dict):
        return _ChunkTranscript(text=str(payload).strip(), segments=[])

    transcript_text = (payload.get("text") or "").strip()
    segments: list[_ChunkSegment] = []
    for seg in payload.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        segment_text = (seg.get("text") or "").strip()
        if not segment_text:
            continue
        segments.append(
            _ChunkSegment(
                start=float(seg.get("start", 0)),
                end=float(seg.get("end", 0)),
                text=segment_text,
            )
        )
    return _ChunkTranscript(text=transcript_text, segments=segments)


def _merge_chunks_into_segments(
    segments_per_chunk: list[list[_ChunkSegment]],
    chunk_starts: list[float],
) -> list[_ChunkSegment]:
    """Shift per-chunk segments to absolute times and flatten."""
    merged: list[_ChunkSegment] = []
    if len(segments_per_chunk) != len(chunk_starts):
        raise ValueError("Missing chunk start timestamps")
    for offset, segs in zip(chunk_starts, segments_per_chunk):
        for seg in segs:
            merged.append(
                _ChunkSegment(
                    start=seg.start + offset,
                    end=seg.end + offset,
                    text=seg.text,
                )
            )
    return merged


def transcribe_audio(
    video: Path,
    out: Path,
    status: ToolStatus,
    *,
    model: str,
    language: str | None,
    prompt: str | None,
    response_format: str,
    max_upload_mb: float,
    chunk_seconds: int,
) -> Path:
    size_mb = video.stat().st_size / 1024 / 1024
    if size_mb <= max_upload_mb:
        text = transcribe_one_file(
            video,
            model=model,
            language=language,
            prompt=prompt,
            response_format=response_format,
        )
        write_text(out, text)
        return out

    # For chunked transcription we request verbose JSON so we can preserve
    # per-segment timestamps; the final output is reformatted afterwards.
    final_format = response_format
    api_format = "verbose_json"

    with local_temp_dir(out.parent, "video_text_") as temp_dir:
        upload_limit = int(max_upload_mb * 1024 * 1024)
        safe_chunk_seconds = chunk_seconds
        if upload_limit > 0:
            # 16 kHz mono PCM16: reserve room for the WAV header and packet rounding.
            safe_chunk_seconds = min(chunk_seconds, (upload_limit - 65536) // 32000)
            if safe_chunk_seconds < 1:
                fail("上传大小上限过小，无法生成安全的音频切片；请将 --max-upload-mb 设为至少 0.1。")
        chunks = split_audio_with_ffmpeg(video, temp_dir, status, safe_chunk_seconds)
        if upload_limit > 0 and any(chunk.path.stat().st_size > upload_limit for chunk in chunks):
            fail("音频切片仍超过上传大小上限，尚未上传；请减小 --chunk-seconds。")
        segments_per_chunk: list[list[_ChunkSegment]] = []
        chunk_texts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            print(f"转写切片 {index}/{len(chunks)}: {chunk.path.name}")
            raw = transcribe_one_file(
                chunk.path,
                model=model,
                language=language,
                prompt=prompt,
                response_format=api_format,
            )
            transcript = _parse_openai_verbose_transcript(raw)
            if final_format in {"srt", "vtt"} and transcript.text and not transcript.segments:
                fail(f"切片 {index} 返回了正文但没有时间戳，无法生成完整字幕。请改用 TXT 或 JSON。")
            segments_per_chunk.append(transcript.segments)
            chunk_texts.append(transcript.text or " ".join(s.text for s in transcript.segments))

        merged = _merge_chunks_into_segments(segments_per_chunk, [chunk.start for chunk in chunks])
        if final_format == "json":
            payload = {
                "text": "\n\n".join(chunk_texts) or " ".join(s.text for s in merged),
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text} for s in merged
                ],
            }
            write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        elif final_format == "srt":
            blocks: list[str] = []
            for idx, seg in enumerate(merged, start=1):
                start = format_subtitle_time(seg.start, comma=True)
                end = format_subtitle_time(seg.end, comma=True)
                blocks.append(f"{idx}\n{start} --> {end}\n{seg.text}")
            write_text(out, "\n\n".join(blocks) + ("\n" if blocks else ""))
        elif final_format == "vtt":
            blocks = ["WEBVTT"]
            for seg in merged:
                start = format_subtitle_time(seg.start, comma=False)
                end = format_subtitle_time(seg.end, comma=False)
                blocks.append(f"{start} --> {end}\n{seg.text}")
            write_text(out, "\n\n".join(blocks) + "\n")
        else:
            lines = [
                f"[{format_seconds(s.start)} - {format_seconds(s.end)}] {s.text}"
                for s in merged
            ]
            if chunk_texts:
                write_text(out, "\n\n".join(chunk_texts) + "\n")
            elif lines:
                write_text(out, "\n".join(lines) + "\n")
            else:
                write_text(out, "\n\n".join(chunk_texts) + ("\n" if chunk_texts else ""))

    return out


def transcribe_with_local_whisper(
    video: Path,
    out: Path,
    *,
    model_name: str,
    language: str | None,
    task: str,
    verbose: bool,
    output_format: str = "text",
    prompt: str | None = None,
    audio_channel: str = "mix",
    enhance_audio: bool = False,
) -> Path:
    try:
        import whisper
    except ImportError:
        fail("未安装本地 Whisper。请运行: python -m pip install openai-whisper imageio-ffmpeg")
    from transcription_support import audio_duration, iter_audio_chunks, save_review

    status = detect_tools()
    ffmpeg = ffmpeg_command(status)
    if not ffmpeg:
        fail("需要 ffmpeg 来读取音频。请安装 imageio-ffmpeg 或完整 ffmpeg。")
    duration = audio_duration(video, status.ffprobe)
    print("[stage:decode]", flush=True)
    print("[stage:model]", flush=True)
    print(f"加载 Whisper 模型: {model_name}；未缓存的模型首次使用需要下载。", flush=True)
    from model_storage import model_directory
    cache_dir = model_directory("whisper")
    model = whisper.load_model(model_name, download_root=str(cache_dir))
    print("[stage:transcribe]", flush=True)
    result = {"text": "", "language": language, "segments": []}
    texts = []
    with closing(iter_audio_chunks(video, ffmpeg, audio_channel, enhance_audio, chunk_seconds=600)) as chunks:
        for offset, audio in chunks:
            partial = model.transcribe(
                audio,
                language=result["language"],
                task=task,
                fp16=status.cuda_gpu,
                verbose=verbose,
                initial_prompt=prompt or None,
                condition_on_previous_text=False,
                temperature=(0.0, 0.2, 0.4),
                beam_size=5,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            result["language"] = result["language"] or partial.get("language")
            texts.append(partial.get("text") or "")
            for segment in partial.get("segments") or []:
                shifted = dict(segment, start=segment["start"] + offset, end=segment["end"] + offset)
                if segment.get("words"):
                    shifted["words"] = [dict(word, start=word["start"] + offset, end=word["end"] + offset)
                                        for word in segment["words"]]
                result["segments"].append(shifted)
            print(f"已处理音频至 {format_seconds(offset + len(audio) / 16000)}", flush=True)
            if duration:
                print(f"{min(99, round((offset + len(audio) / 16000) / duration * 100))}%| audio processed", flush=True)
    if duration:
        print("100%| recognition complete", flush=True)
    result["text"] = " ".join(text.strip() for text in texts if text.strip())
    print("[stage:export]", flush=True)
    write_text(out, format_whisper_result(result, output_format))
    save_review(out, video, result, model=model_name, channel=audio_channel,
                enhance=enhance_audio, prompt=prompt or "", task=task, chunk_seconds=600)
    return out


def format_whisper_result(result: dict[str, Any], output_format: str) -> str:
    segments = result.get("segments") or []

    if output_format == "json":
        payload = {
            "text": (result.get("text") or "").strip(),
            "language": result.get("language"),
            "segments": [
                {
                    "start": float(segment.get("start", 0)),
                    "end": float(segment.get("end", 0)),
                    "text": str(segment.get("text", "")).strip(),
                }
                for segment in segments
                if str(segment.get("text", "")).strip()
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if output_format == "srt":
        blocks = []
        for index, segment in enumerate(segments, start=1):
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            start = format_subtitle_time(float(segment.get("start", 0)), comma=True)
            end = format_subtitle_time(float(segment.get("end", 0)), comma=True)
            blocks.append(f"{index}\n{start} --> {end}\n{text}")
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    if output_format == "vtt":
        blocks = ["WEBVTT"]
        for segment in segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            start = format_subtitle_time(float(segment.get("start", 0)), comma=False)
            end = format_subtitle_time(float(segment.get("end", 0)), comma=False)
            blocks.append(f"{start} --> {end}\n{text}")
        return "\n\n".join(blocks) + "\n"

    lines = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = format_seconds(float(segment.get("start", 0)))
        end = format_seconds(float(segment.get("end", 0)))
        lines.append(f"[{start} - {end}] {text}")
    if lines:
        return "\n".join(lines) + "\n"

    text = (result.get("text") or "").strip()
    return text + ("\n" if text else "")


def normalize_ocr_text(text: str) -> str:
    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def ocr_frames(
    video: Path,
    out: Path,
    status: ToolStatus,
    *,
    interval: float,
    language: str,
) -> Path:
    ffmpeg = ffmpeg_command(status)
    if not ffmpeg:
        fail("画面 OCR 需要安装 ffmpeg。")
    if not status.tesseract:
        fail("画面 OCR 需要安装 tesseract，并安装对应语言包，例如 chi_sim 和 eng。")
    if interval <= 0:
        fail("--ocr-interval 必须大于 0。")
    tessdata_dir = tesseract_data_dir_for(language, status)
    if not tessdata_dir:
        fail(f"缺少 OCR 语言包: {language}。请安装对应 traineddata，或改用已安装语言。")

    with local_temp_dir(out.parent, "video_ocr_") as temp_dir:
        frame_pattern = temp_dir / "frame_%06d.png"
        fps = f"1/{interval:g}"
        run_command(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-vf",
                f"fps={fps}",
                str(frame_pattern),
            ]
        )
        frames = sorted(temp_dir.glob("frame_*.png"))
        if not frames:
            fail("没有抽取到视频帧。")

        blocks: list[str] = []
        last_text = ""
        for index, frame in enumerate(frames):
            seconds = index * interval
            result = run_command(
                [
                    status.tesseract,
                    str(frame),
                    "stdout",
                    "-l",
                    language,
                    "--psm",
                    "6",
                    "--tessdata-dir",
                    str(tessdata_dir),
                ],
                quiet=True,
            )
            text = normalize_ocr_text(result.stdout)
            if text and text != last_text:
                timestamp = format_seconds(seconds)
                blocks.append(f"[{timestamp}]\n{text}")
                last_text = text

        write_text(out, "\n\n".join(blocks))
        return out


def format_seconds(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_subtitle_time(seconds: float, *, comma: bool) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def run_auto(video: Path, out: Path, status: ToolStatus, args: argparse.Namespace) -> Path:
    if ffmpeg_command(status):
        try:
            streams = subtitle_streams(video, status)
            if streams:
                if args.format in {"srt", "vtt"}:
                    outputs = extract_subtitles(video, out, status, output_format=args.format)
                    return outputs[0]
                with local_temp_dir(out.parent, "video_subtitle_") as temp_dir:
                    temp_srt = temp_dir / "embedded.srt"
                    outputs = extract_subtitles(video, temp_srt, status)
                    segments = read_srt_segments(outputs[0])
                if segments:
                    return write_subtitle_segments(out, segments, args.format)
                print("内嵌字幕为空，改用音频转写。")
        except (ValueError, subprocess.CalledProcessError, SystemExit) as exc:
            print(f"字幕提取失败，改用音频转写: {exc}")

    if status.local_whisper:
        try:
            return transcribe_with_local_whisper(
                video,
                out,
                model_name=args.whisper_model,
                language=args.language,
                task=args.whisper_task,
                verbose=args.verbose,
                output_format=args.format,
                prompt=args.prompt,
                audio_channel=args.audio_channel,
                enhance_audio=args.enhance_audio,
            )
        except (OSError, RuntimeError, subprocess.CalledProcessError, SystemExit) as exc:
            print(f"本地 Whisper 转写失败: {exc}")

    if not args.allow_cloud_fallback:
        fail("本地识别不可用或失败，已停止，未上传音频。只有显式添加 --allow-cloud-fallback 才允许云端回退。")
    if args.whisper_task == "translate":
        fail("Auto 云端回退不支持翻译任务，已停止，未上传音频。请使用本地 Whisper。")
    print("已授权云端回退，将使用 OpenAI API 上传并转写音频。", flush=True)
    return transcribe_audio(
        video,
        out,
        status,
        model=args.model,
        language=args.language,
        prompt=args.prompt,
        response_format=args.format,
        max_upload_mb=args.max_upload_mb,
        chunk_seconds=args.chunk_seconds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从视频中提取文字、字幕或语音转写。")
    parser.add_argument("video", type=Path, help="输入视频文件，例如 4-1.mp4")
    parser.add_argument(
        "--mode",
        choices=["auto", "audio", "whisper", "sensevoice", "subtitle", "ocr"],
        default="sensevoice",
        help="默认 sensevoice=本地中文转写；whisper=多语言语音转写，audio=OpenAI API，subtitle=内嵌字幕，ocr=画面文字。",
    )
    parser.add_argument("-o", "--out", type=Path, help="输出文件路径。默认根据视频名生成。")
    parser.add_argument(
        "--format",
        choices=["text", "json", "srt", "vtt"],
        default="text",
        help="OpenAI 转写输出格式。OCR 固定输出 txt。",
    )
    parser.add_argument("--model", default="whisper-1", help="OpenAI 音频转写模型名。")
    parser.add_argument("--allow-cloud-fallback", action="store_true",
                        help="仅用于 auto：允许本地识别不可用或失败后上传音频到 OpenAI API，默认禁止。")
    parser.add_argument(
        "--whisper-model",
        default="base",
        help="本地 Whisper 模型名：tiny/base/small/medium/large。越大越准也越慢。",
    )
    parser.add_argument(
        "--whisper-task",
        choices=["transcribe", "translate"],
        default="transcribe",
        help="本地 Whisper 任务：transcribe=原语言转写，translate=翻译成英文。",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示本地 Whisper 的详细转写进度。",
    )
    parser.add_argument("--language", help="语音语言代码，例如 zh/en。OCR 模式会从已安装语言包中选择默认值。")
    parser.add_argument("--audio-channel", choices=["mix", "left", "right"], default="mix", help="音频声道")
    parser.add_argument("--enhance-audio", action="store_true", help="轻度降噪并平衡人声音量")
    parser.add_argument("--prompt", help="给转写模型的提示词，例如专有名词、课程主题等。")
    parser.add_argument(
        "--max-upload-mb",
        type=float,
        default=DEFAULT_MAX_UPLOAD_MB,
        help="超过该大小时尝试用 ffmpeg 切片后再转写。",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=600,
        help="大文件转写时每个音频切片的秒数。",
    )
    parser.add_argument(
        "--ocr-interval",
        type=float,
        default=2.0,
        help="OCR 模式每隔多少秒抽一帧。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检测工具和配置，不调用转写/OCR。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    video = ensure_file(args.video)
    status = detect_tools()

    if args.dry_run:
        dump_status(video, status)
        return 0

    if args.max_upload_mb <= 0:
        fail("--max-upload-mb 必须大于 0。")
    if args.chunk_seconds <= 0:
        fail("--chunk-seconds 必须大于 0。")
    if args.mode == "ocr" and args.format != "text":
        fail("OCR 模式只支持 text 输出。请移除 --format 或使用 --format text。")
    if args.mode != "ocr":
        args.language = normalize_speech_language(args.language)

    output_format = args.format
    if args.mode == "ocr":
        output_format = "txt"
    out = ensure_output_file(args.out or default_output(video, args.mode, output_format))
    if out.resolve() == video.resolve():
        fail("输出路径不能与输入音视频相同。")

    try:
        if args.mode == "sensevoice":
            if args.format != "text":
                fail("SenseVoice 校对模式目前只输出 TXT；时间戳是约 20 秒的音频区间。")
            if args.language and args.language != "zh":
                fail("SenseVoice 交叉校对模式目前固定识别中文。")
            if args.prompt or args.enhance_audio:
                fail("SenseVoice 校对模式不使用术语提示或降噪，请移除 --prompt / --enhance-audio。")
            from sensevoice_backend import transcribe
            try:
                transcribe(video, out, args.audio_channel)
            except RuntimeError as exc:
                fail(str(exc))
        elif args.mode == "subtitle":
            extract_subtitles_as(video, out, status, args.format)
        elif args.mode == "ocr":
            ocr_language = map_ocr_language(args.language) if args.language else default_ocr_language(status)
            ocr_frames(video, out, status, interval=args.ocr_interval, language=ocr_language)
        elif args.mode == "whisper":
            transcribe_with_local_whisper(
                video,
                out,
                model_name=args.whisper_model,
                language=args.language,
                task=args.whisper_task,
                verbose=args.verbose,
                output_format=args.format,
                prompt=args.prompt,
                audio_channel=args.audio_channel,
                enhance_audio=args.enhance_audio,
            )
        elif args.mode == "auto":
            run_auto(video, out, status, args)
        else:
            transcribe_audio(
                video,
                out,
                status,
                model=args.model,
                language=args.language,
                prompt=args.prompt,
                response_format=args.format,
                max_upload_mb=args.max_upload_mb,
                chunk_seconds=args.chunk_seconds,
            )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        fail(message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
