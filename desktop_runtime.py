"""Local runtime helpers used by the desktop presentation layer."""
from __future__ import annotations

import re
import sys
import subprocess
from pathlib import Path
from PySide6.QtGui import QPixmap
from desktop_options import APP_DIR

def safe_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._") or "auto"

def file_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "—"
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.2f} GB"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024:.1f} KB"

THUMB_CACHE: dict[Path, QPixmap | None] = {}

def python_console_executable() -> str:
    executable = Path(sys.executable)
    if sys.platform == "win32" and executable.name.lower() == "pythonw.exe":
        python_exe = executable.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return sys.executable

def get_video_thumbnail(path: Path) -> QPixmap | None:
    if path in THUMB_CACHE:
        return THUMB_CACHE[path]
    if path.suffix.lower() in {".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma"}:
        return None
    THUMB_CACHE[path] = None
    try:
        from video_text_extractor import detect_tools, ffmpeg_command, local_temp_dir
        status = detect_tools()
        ffmpeg = ffmpeg_command(status)
        if not ffmpeg:
            return None
        with local_temp_dir(APP_DIR / ".video_text_cache", "thumb_") as temp_dir:
            tmp_path = temp_dir / "frame.jpg"
            subprocess.run(
                [ffmpeg, "-y", "-i", str(path), "-vframes", "1", "-vf", "scale=80:-1", str(tmp_path)],
                capture_output=True, timeout=10,
            )
            pixmap = QPixmap(str(tmp_path))
            if not pixmap.isNull():
                THUMB_CACHE[path] = pixmap
                return pixmap
    except Exception:
        pass
    return None

def get_video_duration(path: Path) -> float:
    try:
        from video_text_extractor import detect_tools
        from transcription_support import audio_duration
        return audio_duration(path, detect_tools().ffprobe)
    except Exception:
        return 0.0

def suggest_model(duration_sec: float) -> str:
    if duration_sec <= 0:
        return "base"
    if duration_sec < 120:
        return "small"
    if duration_sec < 600:
        return "base"
    return "tiny"
