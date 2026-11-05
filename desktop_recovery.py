"""Desktop autosave scheduling and user-confirmed recovery orchestration."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from desktop_types import Job, STATUS_DONE
from draft_recovery import DraftRecovery, text_digest

def init_recovery(window, settings_path: Path) -> None:
    try:
        window.draft_store = DraftRecovery(settings_path.parent / ".transcribe_drafts")
        window._recovery_batches = window.draft_store.scan()
        if window._recovery_batches:
            QTimer.singleShot(0, window._offer_recovery)
    except OSError as exc:
        window.append_log(window.tr("recovery_error") + f"\n{exc}\n")
        window.statusBar().showMessage(window.tr("recovery_error"), 10000)

def autosave_drafts(window) -> bool:
    if window.draft_store is None or window._closing or window._recovery_loading:
        return False
    pending = dict(window._drafts)
    if window.preview_path is not None:
        if window.preview.document().isModified():
            pending[window.preview_path] = window.preview.toPlainText()
        else:
            pending.pop(window.preview_path, None)
    entries = []
    for output, text in pending.items():
        if output not in window._preview_versions or output not in window._preview_hashes or output not in window._preview_sources:
            window.statusBar().showMessage(window.tr("recovery_error"), 10000)
            return False
        entries.append({"output": str(output.resolve()), "source": str(window._preview_sources[output].resolve()),
                        "text": text, "base_hash": window._preview_hashes[output],
                        "base_stamp": list(window._preview_versions[output]),
                        "mode": next((job.mode for job in window.jobs if job.output == output), "whisper")})
    try:
        window.draft_store.save(entries)
        window._autosave_warning = False
        return True
    except (OSError, ValueError, RuntimeError) as exc:
        if not window._autosave_warning:
            window.append_log(window.tr("recovery_error") + f"\n{exc}\n")
            window.statusBar().showMessage(window.tr("recovery_error"), 10000)
            window._autosave_warning = True
        return False

def offer_recovery(window) -> None:
    if window.draft_store is None or window._closing:
        return
    try:
        if not window._recovery_batches:
            window._recovery_batches = window.draft_store.scan()
        count = sum(len(batch.drafts) for batch in window._recovery_batches)
        if not count:
            return
        choice = QMessageBox.question(window, window.tr("recovery_title"), window.tr("recovery_found").format(count),
                                      QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
        if choice == QMessageBox.Cancel:
            return
        if choice == QMessageBox.No:
            for batch in window._recovery_batches:
                batch.discard()
            window._recovery_batches.clear()
            return
        restored = []
        complete = []
        window._recovery_loading = True
        try:
            for batch in window._recovery_batches:
                successful = True
                for entry in batch.drafts:
                    try:
                        output, source = Path(entry["output"]), Path(entry["source"])
                        if not output.is_absolute() or not source.is_absolute():
                            raise ValueError("Recovery paths must be absolute")
                        output, source = output.resolve(), source.resolve()
                        current = output.read_text(encoding="utf-8") if output.is_file() else None
                        if current is not None and text_digest(current) == text_digest(entry["text"]):
                            continue
                        pending = window._drafts.get(output)
                        if output == window.preview_path and window.preview.document().isModified():
                            pending = window.preview.toPlainText()
                        existing = next((job for job in window.jobs if job.output == output), None)
                        conflict = pending is not None and pending != entry["text"]
                        conflict |= existing is not None and existing.video.resolve() != source.resolve()
                        unchanged = current is not None and text_digest(current) == entry["base_hash"] and not conflict
                        if not unchanged:
                            folder = window.output_directory()
                            folder.mkdir(parents=True, exist_ok=True)
                            suffix = output.suffix.lower() if output.suffix.lower() in {".txt", ".srt", ".vtt", ".json"} else ".txt"
                            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=folder,
                                                             prefix=output.stem[:80] + "_recovered_", suffix=suffix, delete=False) as stream:
                                output = Path(stream.name)
                                stream.write(entry["text"])
                                stream.flush()
                                os.fsync(stream.fileno())
                        if not any(job.output == output for job in window.jobs):
                            window.jobs.append(Job(source, output, STATUS_DONE, mode=entry.get("mode", "whisper")))
                        window._preview_versions[output] = window._output_stamp(output)
                        window._preview_hashes[output] = entry["base_hash"] if unchanged else text_digest(entry["text"])
                        window._preview_sources[output] = source
                        if unchanged:
                            window._drafts[output] = entry["text"]
                        restored.append(output)
                    except (OSError, ValueError, UnicodeError) as exc:
                        successful = False
                        window.append_log(window.tr("recovery_error") + f"\n{exc}\n")
                if successful:
                    complete.append(batch)
        finally:
            window._recovery_loading = False
        window.refresh_table()
        if restored:
            row = next(i for i, job in enumerate(window.jobs) if job.output == restored[0])
            window.table.selectRow(row)
            window.preview_selected_output(force=True)
        if window._autosave_drafts():
            for batch in complete:
                batch.discard()
                window._recovery_batches.remove(batch)
        window.statusBar().showMessage(window.tr("recovery_done").format(len(restored)), 9000)
    except (OSError, ValueError, RuntimeError) as exc:
        window.statusBar().showMessage(window.tr("recovery_error"), 10000)
        window.append_log(window.tr("recovery_error") + f"\n{exc}\n")
