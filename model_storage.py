"""Persistent, explicit storage location shared by all local ASR engines."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / ".model_storage.json"


def model_root() -> Path:
    override = os.environ.get("VIDEO_TEXT_MODEL_DIR", "").strip()
    if override:
        selected = override
    elif CONFIG.is_file():
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        selected = payload["directory"]
        if not isinstance(selected, str) or not selected.strip():
            raise ValueError("Model directory is empty")
    else:
        return ROOT / ".video_text_cache"
    path = Path(selected).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def model_directory(engine: str) -> Path:
    if engine not in {"whisper", "sensevoice"}:
        raise ValueError(f"Unknown engine: {engine}")
    return model_root() / engine


def configure_model_root(directory: str) -> Path:
    path = Path(directory).expanduser().resolve()
    CONFIG.write_text(json.dumps({"directory": str(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
