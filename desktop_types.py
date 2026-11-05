"""Shared queue record and task states."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATUS_WAITING = "waiting"

STATUS_RUNNING = "running"

STATUS_DONE = "done"

STATUS_CANCELLED = "cancelled"

STATUS_FAILED = "failed"

@dataclass
class Job:
    video: Path
    output: Path
    status: str = STATUS_WAITING
    mode: str = "whisper"
    stage: str = ""
    progress: int | None = None
