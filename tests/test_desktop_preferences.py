import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import desktop_preferences
from desktop_preferences import restore_preferences, save_preferences


class Control:
    def __init__(self, value):
        self.value = value

    def setText(self, value):
        self.value = value

    def text(self):
        return self.value

    def setChecked(self, value):
        self.value = value

    def isChecked(self):
        return self.value

    def setValue(self, value):
        self.value = value


class Combo:
    def __init__(self, choices):
        self.choices = choices
        self.index = 0

    def findData(self, value):
        return next((i for i, (_, data) in enumerate(self.choices) if data == value), -1)

    def setCurrentIndex(self, index):
        self.index = index

    def currentData(self):
        return self.choices[self.index][1]

    def currentText(self):
        return self.choices[self.index][0]


class Window:
    def __init__(self):
        self.ui_lang = "zh"
        self.output_dir = Control("original output")
        self.last_input_dir = "original input"
        self.mode_combo = Combo([("Local", "whisper"), ("Automatic", "auto")])
        self.channel_combo = Combo([("Mix", "mix"), ("Left", "left")])
        self.model_combo = Combo([("base", "base"), ("small", "small")])
        self.output_combo = Combo([("TXT", "TXT"), ("SRT", "SRT")])
        self.format_combo = Combo([("All", "all"), ("Audio", "audio")])
        self.translate_radio = Control(False)
        self.transcribe_radio = Control(True)
        self.enhance_check = Control(False)
        self.allow_cloud_check = Control(True)
        self.parallel_spin = Control(4)
        self.media_player = SimpleNamespace(speed=Combo([("1x", 1.0), ("1.5x", 1.5)]))
        self.code = ""
        self.logs = []
        self.mode_changes = 0

    def _set_combo_data(self, widget, value):
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)

    def _set_combo_text(self, widget, value):
        for index, (text, _) in enumerate(widget.choices):
            if text == value:
                widget.setCurrentIndex(index)
                break

    def _set_language_code(self, code):
        self.code = code

    def language_code(self):
        return self.code

    def _on_mode_changed(self):
        self.mode_changes += 1
        self.allow_cloud_check.setChecked(True)
        self.parallel_spin.setValue(8)

    def append_log(self, text):
        self.logs.append(text)

    def tr(self, key):
        return {"prefs_error": "Preferences save failed"}[key]


class DesktopPreferencesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "settings.json"
        self.window = Window()

    def write_config(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_restore_all_supported_state_and_reset_cloud_and_parallel_after_mode(self):
        self.write_config({
            "version": 1, "ui_lang": "en", "output_dir": "  output directory  ",
            "last_input_dir": "", "mode": "auto", "channel": "left", "model": "small",
            "format": "SRT", "file_type": "Audio", "language": "ja", "translate": True,
            "enhance": True, "playback_rate": 1.5, "allow_cloud": True, "parallel": 6,
        })
        restore_preferences(self.window, self.path)
        self.assertEqual(self.window.ui_lang, "en")
        self.assertEqual(self.window.output_dir.text(), "  output directory  ")
        self.assertEqual(self.window.last_input_dir, "")
        self.assertEqual(self.window.mode_combo.currentData(), "auto")
        self.assertEqual(self.window.channel_combo.currentData(), "left")
        self.assertEqual(self.window.model_combo.currentText(), "small")
        self.assertEqual(self.window.output_combo.currentText(), "SRT")
        self.assertEqual(self.window.format_combo.currentText(), "Audio")
        self.assertEqual(self.window.code, "ja")
        self.assertTrue(self.window.translate_radio.isChecked())
        self.assertFalse(self.window.transcribe_radio.isChecked())
        self.assertTrue(self.window.enhance_check.isChecked())
        self.assertEqual(self.window.media_player.speed.currentData(), 1.5)
        self.assertEqual(self.window.mode_changes, 1)
        self.assertFalse(self.window.allow_cloud_check.isChecked())
        self.assertEqual(self.window.parallel_spin.value, 1)
        self.assertEqual(self.window.logs, [])

    def test_missing_config_leaves_state_and_logs_unchanged(self):
        restore_preferences(self.window, self.path)
        self.assertEqual(self.window.mode_changes, 0)
        self.assertTrue(self.window.allow_cloud_check.isChecked())
        self.assertEqual(self.window.parallel_spin.value, 4)
        self.assertEqual(self.window.logs, [])

    def test_bad_json_encoding_and_read_errors_are_logged(self):
        for content in (b"{broken", b"\xff\xfe"):
            with self.subTest(content=content):
                self.window = Window()
                self.path.write_bytes(content)
                restore_preferences(self.window, self.path)
                self.assertEqual(self.window.ui_lang, "zh")
                self.assertEqual(self.window.mode_changes, 0)
                self.assertEqual(len(self.window.logs), 1)
                self.assertIn("Preferences could not be read; using defaults:", self.window.logs[0])
        self.window.logs.clear()
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            restore_preferences(self.window, self.path)
        self.assertIn("denied", self.window.logs[0])

    def test_non_object_config_is_ignored_without_applying_settings(self):
        for data in ([], None, "text", 1):
            with self.subTest(data=data):
                self.write_config(data)
                restore_preferences(self.window, self.path)
                self.assertEqual(self.window.mode_changes, 0)
                self.assertEqual(self.window.logs, [])

    def test_malformed_fields_keep_defaults_and_booleans_require_true(self):
        self.write_config({
            "ui_lang": [], "output_dir": "   ", "last_input_dir": 2,
            "mode": 12, "channel": None, "model": [], "format": False,
            "file_type": {}, "language": [], "translate": 1, "enhance": "true",
            "playback_rate": True,
        })
        self.window.media_player.speed.setCurrentIndex(1)
        restore_preferences(self.window, self.path)
        self.assertEqual(self.window.ui_lang, "zh")
        self.assertEqual(self.window.output_dir.text(), "original output")
        self.assertEqual(self.window.last_input_dir, "original input")
        self.assertEqual(self.window.mode_combo.currentData(), "whisper")
        self.assertEqual(self.window.channel_combo.currentData(), "mix")
        self.assertEqual(self.window.model_combo.currentText(), "base")
        self.assertEqual(self.window.output_combo.currentText(), "TXT")
        self.assertEqual(self.window.format_combo.currentText(), "All")
        self.assertEqual(self.window.code, "")
        self.assertFalse(self.window.translate_radio.isChecked())
        self.assertTrue(self.window.transcribe_radio.isChecked())
        self.assertFalse(self.window.enhance_check.isChecked())
        self.assertEqual(self.window.media_player.speed.currentData(), 1.5)

    def test_language_allowlist_and_unknown_options(self):
        for language, expected in (("en", "en"), ("zh", "zh"), ("fr", "zh")):
            with self.subTest(language=language):
                self.window = Window()
                self.write_config({"ui_lang": language, "mode": "unknown", "playback_rate": 99})
                restore_preferences(self.window, self.path)
                self.assertEqual(self.window.ui_lang, expected)
                self.assertEqual(self.window.mode_combo.currentData(), "whisper")
                self.assertEqual(self.window.media_player.speed.currentData(), 1.0)

    def test_save_exact_safe_fields_with_auto_language_fallback(self):
        self.window.output_dir.setText("\u8f93\u51fa")
        save_preferences(self.window, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {
            "version": 1, "ui_lang": "zh", "output_dir": "\u8f93\u51fa",
            "last_input_dir": "original input", "mode": "whisper", "model": "base",
            "format": "TXT", "language": "auto", "channel": "mix", "translate": False,
            "enhance": False, "file_type": "All", "playback_rate": 1.0,
        })
        self.assertEqual(set(self.root.iterdir()), {self.path})
        self.assertEqual(self.window.logs, [])

    def test_failed_atomic_replace_preserves_old_and_cleans_temp(self):
        self.path.write_bytes(b"old preferences")

        def failed_replace(source, target):
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertNotEqual(Path(source), self.path)
            self.assertEqual(Path(target), self.path)
            self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8"))["version"], 1)
            raise PermissionError("replace denied")

        with patch.object(desktop_preferences.os, "replace", side_effect=failed_replace):
            save_preferences(self.window, self.path)
        self.assertEqual(self.path.read_bytes(), b"old preferences")
        self.assertEqual(set(self.root.iterdir()), {self.path})
        self.assertEqual(self.window.logs, ["Preferences save failed\nreplace denied\n"])

    def test_failed_temp_creation_is_logged_without_changing_old(self):
        self.path.write_bytes(b"old preferences")
        with patch.object(desktop_preferences.tempfile, "NamedTemporaryFile", side_effect=OSError("no space")):
            save_preferences(self.window, self.path)
        self.assertEqual(self.path.read_bytes(), b"old preferences")
        self.assertEqual(set(self.root.iterdir()), {self.path})
        self.assertEqual(self.window.logs, ["Preferences save failed\nno space\n"])

    def test_failed_cleanup_is_logged(self):
        with patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")):
            save_preferences(self.window, self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.window.logs, ["Preferences temporary file cleanup failed: cleanup denied\n"])


if __name__ == "__main__":
    unittest.main()
