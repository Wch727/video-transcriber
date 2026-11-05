"""Playback-follow highlighting for the desktop transcript window."""

from bisect import bisect_right
import math

from PySide6.QtGui import QTextDocument

from review_player import highlight_playback, timestamp_ms
from transcription_support import parse_transcript_segments


class PlaybackFollower:
    """Use an explicit window adapter without importing the main GUI module.

    The adapter supplies preview, reading_view, preview_path, media_player,
    view_tabs, find_bar, tr(), _reading_dirty, and optional review state:
    _review_stale, _review_source_mismatch, and _review_data.
    """

    def __init__(self, window):
        self.window = window
        self.rows = []
        self.starts = []
        self.key = None
        self.source = None

    def clear(self) -> None:
        self.key = None
        window = self.window
        if hasattr(window, "preview"):
            window.preview.setExtraSelections([])
            window.reading_view.setExtraSelections([])

    def rebuild(self) -> None:
        self.clear()
        self.rows = []
        self.starts = []
        window = self.window
        check = window.media_player.follow_check
        check.setEnabled(False)
        if (not window.preview_path or window.preview.document().isModified()
                or getattr(window, "_review_stale", False)
                or getattr(window, "_review_source_mismatch", False)):
            return
        suffix = window.preview_path.suffix.lower()
        check.setToolTip(window.tr("follow_intervals") if suffix == ".txt" else window.tr("follow_timestamps"))
        try:
            segments = parse_transcript_segments(window.preview.toPlainText(), suffix)
            metadata = getattr(window, "_review_data", None)
            if metadata and [s.get("text") for s in metadata["segments"]] == [s["text"] for s in segments]:
                for segment, original in zip(segments, metadata["segments"]):
                    start, end = float(original["start"]), float(original["end"])
                    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                        raise ValueError("Invalid review timing")
                    segment.update(start=start, end=end)
        except (ValueError, TypeError, KeyError, OverflowError):
            return
        headers = []
        block = window.preview.document().firstBlock()
        while block.isValid():
            text = block.text()
            if timestamp_ms(text) is not None and (text.lstrip().startswith("[") or "-->" in text):
                headers.append(block)
            block = block.next()
        if suffix != ".json" and len(headers) != len(segments):
            return
        read_position = 0
        for index, segment in enumerate(segments):
            lines = segment["text"].splitlines()
            edit_range = None
            if suffix != ".json":
                header = headers[index]
                offset = header.position() + (header.text().find("]") + 1 if suffix == ".txt" else header.length() - 1)
                found = window.preview.document().find(lines[0].strip(), offset, QTextDocument.FindCaseSensitively)
                if not found.isNull():
                    last = found.block()
                    for _line in lines[1:]:
                        last = last.next()
                    if last.isValid() and (index + 1 == len(headers) or last.position() < headers[index + 1].position()):
                        edit_range = (found.selectionStart(), last.position() + last.length() - 1)
            read_range = None
            if not window._reading_dirty:
                clean_lines = [line.strip() for line in lines if line.strip()]
                found = window.reading_view.document().find(clean_lines[0], read_position, QTextDocument.FindCaseSensitively)
                if not found.isNull():
                    last = found.block()
                    for _line in clean_lines[1:]:
                        last = last.next().next() if last.next().isValid() else last.next()
                    if last.isValid():
                        end = found.selectionEnd() if len(clean_lines) == 1 else last.position() + last.length() - 1
                        read_range = (found.selectionStart(), end)
                        read_position = end
            self.rows.append((round(segment["start"] * 1000), round(segment["end"] * 1000), edit_range, read_range))
        self.rows.sort(key=lambda row: row[0])
        self.starts = [row[0] for row in self.rows]
        self.source = window.media_player.source_path
        column = 3 if window.view_tabs.currentIndex() == 1 else 2
        check.setEnabled(self.source is not None and any(row[column] for row in self.rows))

    def update(self, position: int) -> None:
        window = self.window
        check = window.media_player.follow_check
        editor = window.reading_view if window.view_tabs.currentIndex() == 1 else window.preview
        if (not check.isChecked() or not check.isEnabled()
                or window.preview.document().isModified()
                or editor.textCursor().hasSelection() or window.find_bar.isVisible()
                or window.media_player.source_path != self.source):
            self.clear()
            return
        index = bisect_right(self.starts, position) - 1
        if index < 0 or position >= self.rows[index][1]:
            self.clear()
            return
        span = self.rows[index][3 if editor is window.reading_view else 2]
        if span is None:
            self.clear()
            return
        key = (index, window.view_tabs.currentIndex())
        if key != self.key:
            self.clear()
            highlight_playback(editor, *span)
            self.key = key
