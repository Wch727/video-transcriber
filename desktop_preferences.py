"""Desktop preferences using an explicit window adapter and settings path."""

import json
import os
import tempfile
from pathlib import Path


def restore_preferences(window, path: Path) -> None:
    """Restore supported widget state through the window's existing helpers."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        window.append_log(f"Preferences could not be read; using defaults: {exc}\n")
        return
    if not isinstance(data, dict):
        return
    if isinstance(data.get("ui_lang"), str) and data["ui_lang"] in {"zh", "en"}:
        window.ui_lang = data["ui_lang"]
    for key, widget in (("output_dir", window.output_dir),):
        if isinstance(data.get(key), str) and data[key].strip():
            widget.setText(data[key])
    if isinstance(data.get("last_input_dir"), str):
        window.last_input_dir = data["last_input_dir"]
    for key, widget in (("mode", window.mode_combo), ("channel", window.channel_combo)):
        if isinstance(data.get(key), str):
            window._set_combo_data(widget, data[key])
    for key, widget in (("model", window.model_combo), ("format", window.output_combo), ("file_type", window.format_combo)):
        if isinstance(data.get(key), str):
            window._set_combo_text(widget, data[key])
    if isinstance(data.get("language"), str):
        window._set_language_code(data["language"])
    window.translate_radio.setChecked(data.get("translate") is True)
    window.transcribe_radio.setChecked(not window.translate_radio.isChecked())
    window.enhance_check.setChecked(data.get("enhance") is True)
    rate = data.get("playback_rate")
    if isinstance(rate, (float, int)) and not isinstance(rate, bool):
        index = window.media_player.speed.findData(rate)
        if index >= 0:
            window.media_player.speed.setCurrentIndex(index)
    window._on_mode_changed()
    window.allow_cloud_check.setChecked(False)
    window.parallel_spin.setValue(1)


def save_preferences(window, path: Path) -> None:
    """Atomically save preferences without cloud consent or parallelism."""
    data = {
        "version": 1, "ui_lang": window.ui_lang, "output_dir": window.output_dir.text(),
        "last_input_dir": window.last_input_dir, "mode": window.mode_combo.currentData(),
        "model": window.model_combo.currentText(), "format": window.output_combo.currentText(),
        "language": window.language_code() or "auto", "channel": window.channel_combo.currentData(),
        "translate": window.translate_radio.isChecked(), "enhance": window.enhance_check.isChecked(),
        "file_type": window.format_combo.currentText(), "playback_rate": window.media_player.speed.currentData(),
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".transcribe-settings-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError as exc:
        window.append_log(window.tr("prefs_error") + f"\n{exc}\n")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                window.append_log(f"Preferences temporary file cleanup failed: {exc}\n")
