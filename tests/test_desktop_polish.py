import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox

import video_text_gui as gui
from review_player import AudioReviewPlayer, TranscriptEdit


class DesktopPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = patch.object(gui, "SETTINGS_FILE", self.root / "settings.json", create=True)
        self.settings.start()
        self.runtime = patch.object(gui.VideoTextWindow, "_refresh_runtime")
        self.runtime.start()
        self.window = gui.VideoTextWindow()
        self.window.output_dir.setText(str(self.root))

    def tearDown(self):
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Discard):
            self.window.close()
        self.app.processEvents()
        self.runtime.stop()
        self.settings.stop()
        self.temp.cleanup()

    def load_text(self, text="[00:00:02 - 00:00:04] first words\n[00:00:04 - 00:00:06] second words\n"):
        output = self.root / "transcript.txt"
        output.write_text(text, encoding="utf-8")
        self.window.jobs = [gui.Job(self.root / "source.wav", output, gui.STATUS_DONE)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        return output

    def test_refresh_does_not_reload_editor_or_destroy_undo_and_selection(self):
        self.load_text()
        editor = self.window.preview
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.setTextCursor(cursor)
        editor.insertPlainText("addition")
        cursor = editor.textCursor()
        cursor.setPosition(10)
        cursor.setPosition(15, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)
        expected_selection = cursor.selectedText()
        with patch.object(editor, "setPlainText", wraps=editor.setPlainText) as reload:
            self.window.refresh_table()
            reload.assert_not_called()
        self.assertEqual(editor.textCursor().selectedText(), expected_selection)
        self.assertTrue(editor.document().isUndoAvailable())
        editor.undo()
        self.assertNotIn("addition", editor.toPlainText())

    def test_reading_view_uses_draft_without_changing_original(self):
        output = self.load_text()
        original = output.read_text(encoding="utf-8")
        self.window.preview.insertPlainText("edited ")
        # Use a normal body edit, not an invalid prefix before the timestamp.
        self.window.preview.setPlainText(original.replace("first", "corrected"))
        self.window.preview.document().setModified(True)
        self.window.view_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertIn("corrected words", self.window.reading_view.toPlainText())
        self.assertNotIn("00:00", self.window.reading_view.toPlainText())
        self.assertTrue(self.window.reading_view.isReadOnly())
        self.assertEqual(output.read_text(encoding="utf-8"), original)
        self.window.view_tabs.setCurrentIndex(0)
        self.assertTrue(self.window.preview.document().isModified())

    def test_find_replace_is_literal_undoable_and_disabled_in_reading_view(self):
        self.load_text("[00:00:00 - 00:00:02] a.b a.b aXb\n")
        self.window.show_find(replace=True)
        self.window.find_input.setText("a.b")
        self.window.replace_input.setText("term")
        self.window.replace_all()
        self.assertIn("term term aXb", self.window.preview.toPlainText())
        self.window.preview.undo()
        self.assertIn("a.b a.b aXb", self.window.preview.toPlainText())
        self.window.view_tabs.setCurrentIndex(1)
        self.window.replace_all()
        self.assertIn("a.b a.b aXb", self.window.preview.toPlainText())

    def test_plain_copy_does_not_copy_time_labels(self):
        self.load_text("[00:00:00 - 00:00:02] 123\n456\n")
        self.window.copy_preview()
        self.assertEqual(self.app.clipboard().text(), "123\n456\n")

    def test_keyboard_shortcuts_do_not_capture_normal_typing(self):
        self.load_text()
        self.window.show()
        self.window.activateWindow()
        self.window.preview.setFocus()
        self.app.processEvents()
        with patch.object(self.window.media_player, "toggle_play") as play, patch.object(self.window.media_player, "seek_relative") as seek:
            QTest.keyClick(self.window.preview, Qt.Key_Space, Qt.ControlModifier)
            QTest.keyClick(self.window.preview, Qt.Key_Left, Qt.AltModifier)
            QTest.keyClick(self.window.preview, Qt.Key_Right, Qt.AltModifier)
            play.assert_called_once()
            self.assertEqual([call.args[0] for call in seek.call_args_list], [-3000, 3000])
        before = self.window.preview.toPlainText()
        QTest.keyClick(self.window.preview, Qt.Key_Space)
        self.assertEqual(len(self.window.preview.toPlainText()), len(before) + 1)

    def test_safe_preferences_round_trip_without_cloud_consent_or_parallelism(self):
        self.window._set_combo_data(self.window.mode_combo, "auto")
        self.window.model_combo.setCurrentText("small")
        self.window._set_combo_data(self.window.channel_combo, "left")
        self.window.allow_cloud_check.setChecked(True)
        self.window.parallel_spin.setValue(4)
        self.window._save_preferences()
        stored = json.loads(gui.SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("allow_cloud", stored)
        self.assertNotIn("prompt", stored)
        other = gui.VideoTextWindow()
        try:
            self.assertEqual(other.output_directory(), self.root)
            self.assertEqual(other.mode_combo.currentData(), "auto")
            self.assertEqual(other.channel_combo.currentData(), "left")
            self.assertFalse(other.allow_cloud_check.isChecked())
            self.assertEqual(other.max_parallel, 1)
        finally:
            other.close()

    def test_open_result_checks_file_and_reports_failure(self):
        output = self.load_text()
        with patch("video_text_gui.QDesktopServices.openUrl", return_value=True) as open_url:
            self.window.open_selected_output()
            self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()), output)
        output.unlink()
        with patch("video_text_gui.QDesktopServices.openUrl") as open_url, patch("video_text_gui.QMessageBox.warning") as warning:
            self.window.open_selected_output()
            open_url.assert_not_called()
            warning.assert_called_once()

    def test_progress_accepts_actual_cli_decimal_and_completion_lines(self):
        self.window.jobs = [gui.Job(self.root / "source.wav", self.root / "out.txt", gui.STATUS_RUNNING)]
        self.window.refresh_table()
        self.window._parse_progress("24%| 20.00/83.20", 0)
        self.assertEqual(self.window.jobs[0].progress, 24)
        self.window._parse_progress("100%| recognition complete", 0)
        self.assertEqual(self.window.jobs[0].progress, 100)

    def test_completed_output_path_is_not_retargeted_by_setting_changes(self):
        output = self.load_text()
        self.window.output_dir.setText(str(self.root / "new-output"))
        self.assertEqual(self.window.jobs[0].output, output)
        self.assertEqual(self.window.preview_path, output)

    def test_close_cancel_and_failed_save_keep_drafts(self):
        output = self.load_text()
        self.window.preview.insertPlainText("edited ")
        original = output.read_text(encoding="utf-8")
        for choice in (QMessageBox.Cancel, QMessageBox.Save):
            event = QCloseEvent()
            with patch("video_text_gui.QMessageBox.question", return_value=choice), patch("video_text_gui.QMessageBox.warning"), patch.object(self.window, "_write_draft", side_effect=OSError("read only")):
                self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertTrue(self.window.preview.document().isModified())
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_close_save_writes_current_and_other_drafts(self):
        first = self.load_text("first")
        second = self.root / "second.txt"
        second.write_text("second", encoding="utf-8")
        self.window.jobs.append(gui.Job(self.root / "second.wav", second, gui.STATUS_DONE))
        self.window.preview.insertPlainText("edited ")
        self.window.refresh_table()
        self.window.table.selectRow(1)
        self.window.preview.insertPlainText("changed ")
        event = QCloseEvent()
        with patch("video_text_gui.QMessageBox.question", return_value=QMessageBox.Save):
            self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertIn("edited", first.read_text(encoding="utf-8"))
        self.assertIn("changed", second.read_text(encoding="utf-8"))
        self.assertFalse(self.window._drafts)

    def test_background_job_does_not_steal_review_selection(self):
        self.load_text()
        self.window.jobs.append(gui.Job(self.root / "other.wav", self.root / "other.txt"))
        process = Mock()
        process.poll.return_value = 0
        with patch("video_text_gui.subprocess.Popen", return_value=process), patch("video_text_gui.threading.Thread"):
            self.window._start_job(1)
        self.assertEqual(self.window.table.currentRow(), 0)
        self.assertEqual(self.window.preview_path, self.root / "transcript.txt")
        self.window.active_processes.clear()

    def test_corrupt_preferences_keep_safe_defaults(self):
        gui.SETTINGS_FILE.write_text(json.dumps({"ui_lang": [], "mode": 12, "output_dir": []}), encoding="utf-8")
        other = gui.VideoTextWindow()
        try:
            self.assertEqual(other.ui_lang, "zh")
            self.assertEqual(other.mode_combo.currentData(), "sensevoice")
            self.assertFalse(other.allow_cloud_check.isChecked())
        finally:
            other.close()

    def test_external_modification_is_not_overwritten(self):
        output = self.load_text("original")
        self.window.preview.insertPlainText("draft ")
        output.write_text("external update", encoding="utf-8")
        with patch("video_text_gui.QMessageBox.warning") as warning:
            self.window._save_preview()
            warning.assert_called_once()
        self.assertEqual(output.read_text(encoding="utf-8"), "external update")

    def test_plain_copy_keeps_literal_arrows_and_json_text_without_segments(self):
        self.load_text("123\na --> b\n")
        self.window.copy_preview()
        self.assertEqual(self.app.clipboard().text(), "123\na --> b\n")
        output = self.root / "result.json"
        output.write_text(json.dumps({"text": "complete text", "segments": []}), encoding="utf-8")
        self.window.jobs = [gui.Job(self.root / "source.wav", output, gui.STATUS_DONE)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        self.window.copy_preview()
        self.assertEqual(self.app.clipboard().text(), "complete text\n")


class PlaybackPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_relative_seek_is_clamped(self):
        widget = AudioReviewPlayer()
        widget.source_path = Path("source.wav")
        with patch.object(widget.player, "position", return_value=1000), patch.object(widget.player, "duration", return_value=5000), patch.object(widget.player, "setPosition") as seek:
            widget.seek_relative(-3000)
            seek.assert_called_with(0)
            widget.seek_relative(10000)
            seek.assert_called_with(5000)
        widget.set_source(None)
        widget.close()

    def test_single_click_timestamp_seeks_but_body_click_does_not(self):
        editor = TranscriptEdit()
        editor.resize(600, 150)
        editor.setPlainText("[00:00:02 - 00:00:04] body words")
        editor.show()
        self.app.processEvents()
        signal = QSignalSpy(editor.seekRequested)
        cursor = editor.textCursor()
        cursor.setPosition(4)
        QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=editor.cursorRect(cursor).center())
        self.assertEqual(signal.count(), 1)
        self.assertEqual(signal.at(0)[0], 2000)
        cursor.setPosition(26)
        QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=editor.cursorRect(cursor).center())
        self.assertEqual(signal.count(), 1)
        editor.close()


if __name__ == "__main__":
    unittest.main()
