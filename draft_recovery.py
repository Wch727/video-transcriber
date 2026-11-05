"""Local per-session crash drafts; source/output paths are never opened.

Callers own returned RecoveryBatch objects and must release or discard them.
Closing a store affects only its own session, not any claimed orphan batches.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def text_digest(text: str) -> str:
    """SHA-256 of UTF-8 text, treating CRLF and LF as the same newline."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _valid_drafts(drafts: object) -> bool:
    if not isinstance(drafts, list):
        return False
    for entry in drafts:
        if not isinstance(entry, dict):
            return False
        if any(not isinstance(entry.get(key), str) for key in ("output", "source", "text")):
            return False
        digest = entry.get("base_hash")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            return False
        stamp = entry.get("base_stamp")
        if not isinstance(stamp, (list, tuple)) or len(stamp) != 2:
            return False
        if any(type(value) is not int or value < 0 for value in stamp):
            return False
        if "mode" in entry and not isinstance(entry["mode"], str):
            return False
    return True


def _regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    # Do not follow symlinks or Windows reparse points outside recovery storage.
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISREG(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & reparse)


def _try_lock(path: Path) -> BinaryIO | None:
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        if not _regular_file(path):
            return None
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        stream = os.fdopen(descriptor, "r+b")
    except BaseException:
        os.close(descriptor)
        raise
    try:
        if os.name == "nt":
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        stream.close()
        if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return None
        raise
    except BaseException:
        stream.close()
        raise
    return stream


class RecoveryBatch:
    """A validated orphan snapshot with an exclusively held session lock.

    release() and discard() are idempotent. After release, discard is a no-op:
    another scanner may already own the snapshot at that point.
    """

    def __init__(self, path: Path, drafts: list[dict], lock: BinaryIO):
        self.path = path
        self.drafts = drafts
        self._lock = lock

    def discard(self) -> None:
        """Remove this snapshot, then release its claim; IO failures propagate."""
        if self._lock is not None:
            self.path.unlink(missing_ok=True)
            self.release()

    def release(self) -> None:
        """Leave the snapshot intact and release the OS lock."""
        if self._lock is not None:
            self._lock.close()
            self._lock = None


class DraftRecovery:
    """Recovery store for one GUI session, using only the supplied directory.

    save() raises ValueError for invalid entries, and save()/scan() raise
    RuntimeError after close(). Filesystem errors are not hidden. Serialize
    calls on each store/batch in the caller (for example, on the GUI thread).
    """

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = str(uuid.uuid4())
        self._path = self.directory / (self.session_id + ".json")
        self._lock = _try_lock(self.directory / (self.session_id + ".lock"))
        if self._lock is None:
            raise OSError("Could not acquire recovery session lock")
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Draft recovery store is closed")

    def save(self, entries: list[dict]) -> None:
        """Atomically replace this session's snapshot, or remove it if empty."""
        self._require_open()
        if not _valid_drafts(entries):
            raise ValueError("Invalid recovery draft entries")
        if not entries:
            self._path.unlink(missing_ok=True)
            return
        payload = {"version": 1, "session_id": self.session_id, "drafts": entries}
        descriptor, name = tempfile.mkstemp(
            prefix=self.session_id + ".", suffix=".tmp", dir=self.directory,
        )
        temporary = Path(name)
        try:
            try:
                stream = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
            except BaseException:
                os.close(descriptor)
                raise
            with stream:
                json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def scan(self) -> list[RecoveryBatch]:
        """Claim valid unlocked snapshots; skip corrupt files without deletion."""
        self._require_open()
        batches = []
        try:
            for path in sorted(self.directory.iterdir()):
                if path.suffix != ".json" or path == self._path or not _regular_file(path):
                    continue
                lock = _try_lock(path.with_suffix(".lock"))
                if lock is None:
                    continue
                try:
                    if not _regular_file(path):
                        continue
                    try:
                        with path.open("r", encoding="utf-8") as stream:
                            payload = json.load(stream)
                    except (FileNotFoundError, UnicodeError, ValueError, RecursionError):
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if type(payload.get("version")) is not int or payload["version"] != 1:
                        continue
                    if payload.get("session_id") != path.stem or not _valid_drafts(payload.get("drafts")):
                        continue
                    batches.append(RecoveryBatch(path, payload["drafts"], lock))
                    lock = None
                finally:
                    if lock is not None:
                        lock.close()
        except BaseException:
            # No batches reached the caller, so do not leave invisible claims.
            for batch in batches:
                batch.release()
            raise
        return batches

    def close(self, discard: bool = True) -> None:
        """Close only this session, retaining its snapshot when discard=False."""
        if self._closed:
            return
        try:
            if discard:
                self._path.unlink(missing_ok=True)
        finally:
            self._lock.close()
            self._closed = True
