#!/usr/bin/env python
"""Extract text from video files.

Supported modes:
  audio     Transcribe speech from the video's audio with the OpenAI API.
  whisper   Transcribe speech locally with openai-whisper, no API key required.
  subtitle  Extract embedded subtitle tracks with ffmpeg/ffprobe.
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
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MAX_UPLOAD_MB = 24.0


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


def _detect_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def detect_tools() -> ToolStatus:
    return ToolStatus(
        ffmpeg=which("ffmpeg"),
        ffprobe=which("ffprobe"),
        tesseract=which("tesseract"),
        openai_key=bool(os.getenv("OPENAI_API_KEY")),
        local_whisper=module_available("whisper"),
        imageio_ffmpeg=module_available("imageio_ffmpeg"),
        cuda_gpu=_detect_cuda(),
    )


def module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


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


def fail(message: str) -> None:
    raise SystemExit(f"Error: {message}")


def ensure_file(path: Path) -> Path:
    if not path.exists():
        fail(f"找不到文件: {path}")
    if not path.is_file():
        fail(f"不是文件: {path}")
    return path


def default_output(video: Path, mode: str, output_format: str = "txt") -> Path:
    suffix = {
        "audio": "transcript",
        "whisper": "transcript",
        "subtitle": "subtitles",
        "ocr": "ocr",
        "auto": "text",
    }.get(mode, "text")
    if mode == "subtitle":
        ext = "srt"
    else:
        ext = "txt" if output_format in {"text", "verbose_json"} else output_format
    if ext == "json":
        ext = "json"
    return video.with_name(f"{video.stem}_{suffix}.{ext}")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"已写入: {path}")


def dump_status(video: Path, status: ToolStatus) -> None:
    size_mb = video.stat().st_size / 1024 / 1024
    print(f"视频: {video}")
    print(f"大小: {size_mb:.2f} MB")
    print(f"ffmpeg: {status.ffmpeg or '未找到'}")
    print(f"ffprobe: {status.ffprobe or '未找到'}")
    print(f"tesseract: {status.tesseract or '未找到'}")
    print(f"OPENAI_API_KEY: {'已设置' if status.openai_key else '未设置'}")
    print(f"openai-whisper: {'已安装' if status.local_whisper else '未安装'}")
    print(f"imageio-ffmpeg: {'已安装' if status.imageio_ffmpeg else '未安装'}")


def subtitle_streams(video: Path, status: ToolStatus) -> list[dict[str, Any]]:
    if not status.ffprobe:
        fail("字幕提取需要安装 ffprobe，并确保它在 PATH 中。")
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


def extract_subtitles(video: Path, out: Path | None, status: ToolStatus) -> list[Path]:
    if not status.ffmpeg:
        fail("字幕提取需要安装 ffmpeg，并确保它在 PATH 中。")

    streams = subtitle_streams(video, status)
    if not streams:
        fail("视频里没有检测到内嵌字幕轨。")

    outputs: list[Path] = []
    for i, stream in enumerate(streams):
        if out and len(streams) == 1:
            output_path = out
        elif out:
            output_path = out.with_name(f"{out.stem}_{i}{out.suffix or '.srt'}")
        else:
            lang = stream.get("tags", {}).get("language", f"{i}")
            output_path = video.with_name(f"{video.stem}_subtitle_{i}_{lang}.srt")

        run_command(
            [
                status.ffmpeg,
                "-y",
                "-i",
                str(video),
                "-map",
                f"0:s:{i}",
                str(output_path),
            ]
        )
        outputs.append(output_path)
        print(f"已写入: {output_path}")
    return outputs


def api_response_to_text(response: Any, response_format: str) -> str:
    if isinstance(response, str):
        return response
    if response_format == "json":
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

    try:
        response = client.audio.transcriptions.create(**kwargs)
    finally:
        kwargs["file"].close()

    return api_response_to_text(response, response_format)


def split_audio_with_ffmpeg(
    video: Path,
    workdir: Path,
    status: ToolStatus,
    chunk_seconds: int,
) -> list[Path]:
    if not status.ffmpeg:
        fail("文件较大时需要 ffmpeg 来压缩或切分音频。")

    pattern = workdir / "chunk_%03d.mp3"
    run_command(
        [
            status.ffmpeg,
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            str(pattern),
        ]
    )
    chunks = sorted(workdir.glob("chunk_*.mp3"))
    if not chunks:
        fail("ffmpeg 没有生成音频切片，请确认视频包含音轨。")
    return chunks


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

    if response_format != "text":
        fail("大文件自动切片目前只支持 text 输出。请使用 --format text。")

    with tempfile.TemporaryDirectory(prefix="video_text_") as temp_name:
        temp_dir = Path(temp_name)
        chunks = split_audio_with_ffmpeg(video, temp_dir, status, chunk_seconds)
        parts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            print(f"转写切片 {index}/{len(chunks)}: {chunk.name}")
            text = transcribe_one_file(
                chunk,
                model=model,
                language=language,
                prompt=prompt,
                response_format="text",
            )
            parts.append(text.strip())
        write_text(out, "\n\n".join(part for part in parts if part))
    return out


def ensure_ffmpeg_for_whisper(status: ToolStatus) -> Path | None:
    if status.ffmpeg:
        return None
    try:
        import imageio_ffmpeg
    except ImportError:
        fail("本地 Whisper 需要 ffmpeg。可安装: python -m pip install imageio-ffmpeg")
    ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_exe.exists():
        fail(f"imageio-ffmpeg 返回的 ffmpeg 不存在: {ffmpeg_exe}")
    return ffmpeg_exe


def transcribe_with_local_whisper(
    video: Path,
    out: Path,
    *,
    model_name: str,
    language: str | None,
    task: str,
    verbose: bool,
    output_format: str = "text",
) -> Path:
    try:
        import whisper
    except ImportError:
        fail("未安装本地 Whisper。请先运行: python -m pip install openai-whisper imageio-ffmpeg")

    status = detect_tools()
    ffmpeg_exe = ensure_ffmpeg_for_whisper(status)
    old_path = os.environ.get("PATH", "")
    if ffmpeg_exe:
        # Whisper launches a literal "ffmpeg" command. imageio-ffmpeg ships a
        # versioned executable name, so expose a reusable ffmpeg.exe shim.
        shim_dir = out.parent / ".video_text_cache"
        shim_dir.mkdir(parents=True, exist_ok=True)
        shim = shim_dir / "ffmpeg.exe"
        if not shim.exists() or shim.stat().st_size != ffmpeg_exe.stat().st_size:
            shutil.copy2(ffmpeg_exe, shim)
        os.environ["PATH"] = str(shim.parent) + os.pathsep + old_path

    print(f"加载本地 Whisper 模型: {model_name}")
    print("第一次运行会下载模型；下载完成后可离线复用。")
    try:
        model = whisper.load_model(model_name)
        try:
            import torch
            use_fp16 = torch.cuda.is_available()
            if use_fp16:
                print("检测到 CUDA GPU，启用 fp16 加速。")
        except ImportError:
            use_fp16 = False
        result = model.transcribe(
            str(video),
            language=language,
            task=task,
            fp16=use_fp16,
            verbose=verbose,
        )
    finally:
        if ffmpeg_exe:
            os.environ["PATH"] = old_path

    text = format_whisper_result(result, output_format)
    write_text(out, text)
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
    if not status.ffmpeg:
        fail("画面 OCR 需要安装 ffmpeg。")
    if not status.tesseract:
        fail("画面 OCR 需要安装 tesseract，并安装对应语言包，例如 chi_sim 和 eng。")
    if interval <= 0:
        fail("--ocr-interval 必须大于 0。")

    with tempfile.TemporaryDirectory(prefix="video_ocr_") as temp_name:
        temp_dir = Path(temp_name)
        frame_pattern = temp_dir / "frame_%06d.png"
        fps = f"1/{interval:g}"
        run_command(
            [
                status.ffmpeg,
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
    total = int(round(seconds))
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
    if status.ffmpeg and status.ffprobe:
        try:
            streams = subtitle_streams(video, status)
            if streams:
                outputs = extract_subtitles(video, out.with_suffix(".srt"), status)
                return outputs[0]
        except (subprocess.CalledProcessError, SystemExit) as exc:
            print(f"字幕提取失败，改用音频转写: {exc}")

    if status.local_whisper:
        return transcribe_with_local_whisper(
            video,
            out,
            model_name=args.whisper_model,
            language=args.language,
            task=args.whisper_task,
            verbose=args.verbose,
            output_format=args.format,
        )

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
        choices=["auto", "audio", "whisper", "subtitle", "ocr"],
        default="whisper",
        help="提取模式。whisper=本地语音转文字，audio=OpenAI API，subtitle=内嵌字幕，ocr=画面文字。",
    )
    parser.add_argument("-o", "--out", type=Path, help="输出文件路径。默认根据视频名生成。")
    parser.add_argument(
        "--format",
        choices=["text", "json", "srt", "vtt"],
        default="text",
        help="OpenAI 转写输出格式。OCR 固定输出 txt。",
    )
    parser.add_argument("--model", default="whisper-1", help="OpenAI 音频转写模型名。")
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
    parser.add_argument("--language", help="语音语言代码，例如 zh/en。OCR 模式默认使用 chi_sim+eng。")
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

    output_format = args.format
    if args.mode == "ocr":
        output_format = "txt"
    out = args.out or default_output(video, args.mode, output_format)

    try:
        if args.mode == "subtitle":
            extract_subtitles(video, args.out, status)
        elif args.mode == "ocr":
            ocr_language = args.language or "chi_sim+eng"
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
