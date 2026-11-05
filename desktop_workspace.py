"""Transcript binding, reading, literal search and safe editing actions."""
from __future__ import annotations

import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidgetItem
from draft_recovery import text_digest
from transcription_support import plain_transcript_text, review_path, review_matches_text, save_edited_transcript

def preview_text_changed(window) -> None:
    window._clear_follow()
    if window.draft_store is not None and not window._closing and not window._recovery_loading and not window.autosave_timer.isActive():
        window.autosave_timer.start()
    window._reading_dirty = True
    if window.view_tabs.currentIndex() == 1:
        window.reading_timer.start()

def change_view(window, index: int) -> None:
    window.editor_stack.setCurrentIndex(index)
    if index == 1:
        window._update_reading_view()
    window.replace_row.setVisible(index == 0 and getattr(window, "_replace_visible", False))
    window._update_editor_controls()
    window._rebuild_follow()
    window._follow_position(window.media_player.player.position())

def plain_text(window) -> str:
    return plain_transcript_text(window.preview.toPlainText(), window.preview_path.suffix if window.preview_path else ".txt")

def update_reading_view(window) -> None:
    if not window._reading_dirty:
        return
    window._reading_dirty = False
    try:
        text = window._plain_text()
        window.reading_view.setPlainText("\n\n".join(text.rstrip("\n").splitlines()))
        window.reading_view.setPlaceholderText("")
        window.reading_view.setToolTip("")
    except (ValueError, TypeError, KeyError) as exc:
        window.reading_view.clear()
        window.reading_view.setPlaceholderText(window.tr("reading_invalid"))
        window.reading_view.setToolTip(str(exc))
    window._rebuild_follow()

def update_editor_controls(window) -> None:
    exists = window.preview_path is not None and window.preview_path.is_file()
    editable = exists and not window.active_processes
    window.save_preview_btn.setEnabled(editable)
    window.copy_button.setEnabled(exists)
    window.open_result_action.setEnabled(exists)
    window.reading_export_action.setEnabled(exists)
    window.copy_original_action.setEnabled(exists)
    can_replace = editable and window.view_tabs.currentIndex() == 0
    window.replace_button.setEnabled(can_replace)
    window.replace_all_button.setEnabled(can_replace)

def show_find(window, replace: bool = False) -> None:
    if replace:
        window.view_tabs.setCurrentIndex(0)
    window._replace_visible = replace
    window.replace_row.setVisible(replace and window.view_tabs.currentIndex() == 0)
    window.find_bar.show()
    window._adjust_review_height()
    editor = window.preview if window.view_tabs.currentIndex() == 0 else window.reading_view
    selection = editor.textCursor().selectedText()
    if selection and "\u2029" not in selection:
        window.find_input.setText(selection)
    window.find_input.setFocus()
    window.find_input.selectAll()

def hide_find(window) -> None:
    window.find_bar.hide()
    window._adjust_review_height()
    (window.preview if window.view_tabs.currentIndex() == 0 else window.reading_view).setFocus()

def find_text(window, backward: bool = False) -> bool:
    needle = window.find_input.text()
    if not needle:
        return False
    editor = window.preview if window.view_tabs.currentIndex() == 0 else window.reading_view
    flags = QTextDocument.FindBackward if backward else QTextDocument.FindFlags()
    found = editor.document().find(needle, editor.textCursor(), flags)
    if found.isNull():
        found = editor.document().find(needle, editor.document().characterCount() - 1 if backward else 0, flags)
    if found.isNull():
        window.statusBar().showMessage(window.tr("find_missing"), 4000)
        return False
    editor.setTextCursor(found)
    editor.ensureCursorVisible()
    return True

def replace_current(window) -> None:
    if window.view_tabs.currentIndex() != 0 or window.preview.isReadOnly() or not window.find_input.text():
        return
    cursor = window.preview.textCursor()
    if cursor.selectedText().casefold() != window.find_input.text().casefold():
        if not window.find_text():
            return
        cursor = window.preview.textCursor()
    cursor.insertText(window.replace_input.text())
    window.preview.setTextCursor(cursor)
    window.find_text()

def replace_all(window) -> None:
    if window.view_tabs.currentIndex() != 0 or window.preview.isReadOnly() or not window.find_input.text():
        return
    cursor = QTextCursor(window.preview.document())
    cursor.beginEditBlock()
    count = 0
    while True:
        found = window.preview.document().find(window.find_input.text(), cursor)
        if found.isNull():
            break
        found.insertText(window.replace_input.text())
        cursor.setPosition(found.position())
        count += 1
    cursor.endEditBlock()
    window.preview.setTextCursor(cursor)
    window.statusBar().showMessage(window.tr("replaced").format(count), 4000)

def navigate_review(window, direction: int) -> None:
    count = window.review_list.count()
    if not count:
        return
    row = window.review_list.currentRow()
    row = (row + direction) % count if row >= 0 else (0 if direction > 0 else count - 1)
    window.review_button.setChecked(True)
    window.review_list.setCurrentRow(row)
    window._seek_review_item(window.review_list.item(row))

def preview_selected_output(window, force: bool = False) -> None:
    rows = sorted({index.row() for index in window.table.selectedIndexes()})
    job = window.jobs[rows[0]] if rows and rows[0] < len(window.jobs) else None
    target = job.output if job else None
    window.media_player.set_source(job.video if job else None)
    signature = (target, job.video if job else None, window._output_stamp(target))
    editable = target is not None and target.is_file() and not window.active_processes
    window.preview.setReadOnly(not editable)
    window._update_editor_controls()
    if signature == window._preview_signature and not force:
        return
    # Preserve unsaved edits per output while switching tasks or refreshing rows.
    if window.preview_path is not None and window.preview.document().isModified():
        window._drafts[window.preview_path] = window.preview.toPlainText()
        window._autosave_drafts()
    window._preview_signature = signature
    window.preview_path = None
    window.preview.clear()
    editable = target is not None and target.is_file() and not window.active_processes
    window.preview.setReadOnly(not editable)
    window.save_preview_btn.setEnabled(editable)
    if target is not None and target.is_file():
        try:
            text = window._drafts.get(target)
            if text is None:
                text = target.read_text(encoding="utf-8")
                window._preview_versions[target] = window._output_stamp(target)
                window._preview_hashes[target] = text_digest(text)
            window._preview_sources[target] = job.video
            window.preview.setPlainText(text)
            window.preview_path = target
            window.preview.document().setModified(target in window._drafts)
        except (OSError, UnicodeError) as exc:
            window.append_log(f"Preview error: {exc}\n")
    elif target is not None:
        window.preview.setPlaceholderText(window.tr("output_will_be").format(target))
    else:
        window.preview.setPlaceholderText(window.tr("preview_placeholder"))
    window._load_review(target, job.video if job else None)
    window._update_editor_controls()
    if window.view_tabs.currentIndex() == 1:
        window._update_reading_view()

def copy_preview(window) -> None:
    if window.preview_path is None:
        return
    try:
        QApplication.clipboard().setText(window._plain_text())
        window.statusBar().showMessage(window.tr("copied"), 3500)
    except (ValueError, TypeError, KeyError) as exc:
        QMessageBox.warning(window, window.tr("copy_plain"), window.tr("reading_invalid") + "\n\n" + str(exc))

def write_draft(window, output: Path, text: str) -> None:
    if not output.is_file() or window._output_stamp(output) != window._preview_versions.get(output):
        raise ValueError(window.tr("external_change"))
    if output in window._preview_hashes and text_digest(output.read_text(encoding="utf-8")) != window._preview_hashes[output]:
        raise ValueError(window.tr("external_change"))
    save_edited_transcript(output, text)
    window._preview_versions[output] = window._output_stamp(output)
    window._preview_hashes[output] = text_digest(text)

def save_preview(window) -> None:
    if window.preview_path is None or window.active_processes or window.preview.isReadOnly():
        return
    try:
        window._write_draft(window.preview_path, window.preview.toPlainText())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        QMessageBox.warning(window, window.tr("save_preview"), window.tr("save_failed") + "\n\n" + str(exc))
        return
    window._drafts.pop(window.preview_path, None)
    window.preview.document().setModified(False)
    window._autosave_drafts()
    source = next((job.video for job in window.jobs if job.output == window.preview_path), None)
    window._preview_signature = (window.preview_path, source, window._output_stamp(window.preview_path))
    window._load_review(window.preview_path, source)
    window.append_log(f"Preview saved: {window.preview_path}\n")
    window.statusBar().showMessage(window.tr("saved").format(window.preview_path.name), 4000)

def load_review(window, output: Path | None, source: Path | None) -> None:
    window.review_list.clear()
    window._review_data = None
    window._review_source_mismatch = False
    stale = False
    if output is not None:
        try:
            data = json.loads(review_path(output).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("segments", []), list):
                raise ValueError("Invalid review file")
            if not review_matches_text(data, output.read_text(encoding="utf-8")):
                stale = True
                raise ValueError("Review file no longer matches the transcript")
            if source is not None and Path(data.get("source", "")).resolve() == source.resolve():
                window._review_data = data
                for segment in data.get("segments", []):
                    if isinstance(segment, dict) and segment.get("reasons"):
                        seconds = int(segment["start"])
                        end = int(segment["end"])
                        item = QListWidgetItem(f"{seconds // 60:02d}:{seconds % 60:02d} - {end // 60:02d}:{end % 60:02d}  {segment['text']}")
                        item.setToolTip(segment["text"])
                        item.setData(Qt.UserRole, int(segment["start"] * 1000))
                        item.setData(Qt.UserRole + 1, segment["text"])
                        window.review_list.addItem(item)
            elif source is not None:
                window._review_source_mismatch = True
        except (OSError, ValueError, TypeError, KeyError):
            pass
    count = window.review_list.count()
    window._review_stale = stale
    window.review_button.setText(window.tr("review_stale") if stale else window.tr("review_count").format(count))
    window.review_button.setEnabled(count > 0)
    if not count:
        window.review_button.setChecked(False)
        window.review_list.hide()
    window._rebuild_follow()

def seek_review_item(window, item) -> None:
    window.view_tabs.setCurrentIndex(0)
    milliseconds = item.data(Qt.UserRole)
    window.media_player.seek(milliseconds)
    seconds = milliseconds // 1000
    stamp = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    cursor = window.preview.document().find(stamp)
    if cursor.isNull() and item.data(Qt.UserRole + 1):
        cursor = window.preview.document().find(item.data(Qt.UserRole + 1))
    if not cursor.isNull():
        window.preview.setTextCursor(cursor)
        window.preview.ensureCursorVisible()
    window.preview.setFocus()

def export_reading_copy(window) -> None:
    if window.preview_path is None:
        return
    try:
        text = window._plain_text()
        path = window.preview_path.with_name(window.preview_path.stem + "_reading.txt")
        counter = 2
        while path.exists():
            path = window.preview_path.with_name(window.preview_path.stem + f"_reading_{counter}.txt")
            counter += 1
        path.write_text(text, encoding="utf-8")
        window.append_log(window.tr("saved").format(path) + "\n")
        window.statusBar().showMessage(window.tr("saved").format(path.name), 5000)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        QMessageBox.warning(window, window.tr("reading_copy"), str(exc))
