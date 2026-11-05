import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

import video_text_gui as gui
from transcription_support import save_review


class FollowRecoveryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = patch.object(gui, "SETTINGS_FILE", self.root / "settings.json")
        self.settings.start()
        self.runtime = patch.object(gui.VideoTextWindow, "_refresh_runtime")
        self.runtime.start()
        self.window = gui.VideoTextWindow()
        self.window.output_dir.setText(str(self.root))
        self.source = self.root / "audio.wav"
        with wave.open(str(self.source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(bytes(32000 * 6))

    def tearDown(self):
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Discard):
            self.window.close()
        self.app.processEvents()
        self.runtime.stop()
        self.settings.stop()
        self.temp.cleanup()

    def load(self, text="[00:00:02 - 00:00:04] first words\n[00:00:04 - 00:00:06] second words\n", suffix=".txt"):
        output = self.root / ("transcript" + suffix)
        output.write_text(text, encoding="utf-8")
        self.window.jobs = [gui.Job(self.source, output, gui.STATUS_DONE)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        return output

    def test_follow_highlights_without_moving_cursor_or_modifying_text(self):
        output = self.load()
        editor = self.window.preview
        cursor = editor.textCursor()
        cursor.setPosition(1)
        editor.setTextCursor(cursor)
        self.window.media_player.follow_check.setChecked(True)
        self.window._follow_position(4500)
        self.assertEqual(editor.textCursor().position(), 1)
        self.assertFalse(editor.document().isModified())
        selections = editor.extraSelections()
        self.assertIn("second words", selections[0].cursor.selectedText())
        self.assertEqual(output.read_text(), editor.toPlainText())
        self.window._follow_position(500)
        self.assertFalse(editor.extraSelections())
        self.window.media_player.follow_check.setChecked(False)
        self.assertFalse(editor.extraSelections())

    def test_follow_pauses_during_edit_and_selection(self):
        self.load()
        self.window.media_player.follow_check.setChecked(True)
        editor = self.window.preview
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)
        self.window._follow_position(2500)
        self.assertFalse(editor.extraSelections())
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        editor.setTextCursor(cursor)
        editor.insertPlainText("edit")
        self.window._follow_position(4500)
        self.assertFalse(editor.extraSelections())
        self.assertTrue(editor.document().isModified())

    def test_follow_in_reading_view_and_srt_uses_existing_times(self):
        self.load("1\n00:00:02,100 --> 00:00:04,000\nfirst words\n\n2\n00:00:04,200 --> 00:00:06,000\nsecond words\n", ".srt")
        self.window.view_tabs.setCurrentIndex(1)
        self.window.media_player.follow_check.setChecked(True)
        self.window._follow_position(4300)
        selections = self.window.reading_view.extraSelections()
        self.assertIn("second words", selections[0].cursor.selectedText())
        self.window._follow_position(4100)
        self.assertFalse(self.window.reading_view.extraSelections())

    def test_sensevoice_follow_is_explicitly_interval_based(self):
        output = self.load()
        save_review(output, self.source, {"segments": [
            {"start": 2, "end": 4, "text": "first words"},
            {"start": 4, "end": 6, "text": "second words"}]}, model="sensevoice-int8", timing="20-second windows, not sentence alignment")
        self.window.preview_selected_output(force=True)
        self.assertIn("区间", self.window.media_player.follow_check.toolTip())

    def test_autosave_only_writes_recovery_snapshot(self):
        output = self.load("original")
        self.window.preview.insertPlainText("draft ")
        self.window._autosave_drafts()
        snapshots = list((self.root / ".transcribe_drafts").glob("*.json"))
        self.assertEqual(len(snapshots), 1)
        data = json.loads(snapshots[0].read_text(encoding="utf-8"))
        self.assertIn("draft", data["drafts"][0]["text"])
        self.assertEqual(output.read_text(), "original")
        self.window._save_preview()
        self.assertFalse(list((self.root / ".transcribe_drafts").glob("*.json")))

    def orphan(self, output, text, base_text):
        from draft_recovery import DraftRecovery, text_digest
        store = DraftRecovery(self.root / ".transcribe_drafts")
        stat = output.stat()
        store.save([{"output": str(output), "source": str(self.source), "text": text,
                     "base_hash": text_digest(base_text), "base_stamp": [stat.st_mtime_ns, stat.st_size], "mode": "sensevoice"}])
        store.close(discard=False)

    def test_crash_recovery_restores_draft_without_overwriting_original(self):
        output = self.load("original")
        self.orphan(output, "recovered draft", "original")
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Yes):
            self.window._offer_recovery()
        self.assertEqual(self.window.preview.toPlainText(), "recovered draft")
        self.assertTrue(self.window.preview.document().isModified())
        self.assertEqual(output.read_text(), "original")

    def test_changed_original_recovers_to_a_separate_file(self):
        output = self.load("original")
        self.orphan(output, "recovered draft", "original")
        output.write_text("external changes", encoding="utf-8")
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Yes):
            self.window._offer_recovery()
        self.assertEqual(output.read_text(), "external changes")
        self.assertNotEqual(self.window.preview_path, output)
        self.assertEqual(self.window.preview_path.read_text(), "recovered draft")

    def test_recovery_can_be_postponed_without_deleting_backup(self):
        output = self.load("original")
        self.orphan(output, "draft", "original")
        before = set((self.root / ".transcribe_drafts").glob("*.json"))
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Cancel):
            self.window._offer_recovery()
        self.assertTrue(all(path.exists() for path in before))
        self.assertEqual(self.window.preview.toPlainText(), "original")


if __name__ == "__main__":
    unittest.main()
