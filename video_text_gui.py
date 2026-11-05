from __future__ import annotations

import desktop_layout
import desktop_queue
from desktop_runtime import safe_part, file_size, python_console_executable, get_video_thumbnail, get_video_duration, suggest_model
import desktop_workspace
import desktop_recovery
from desktop_follow import PlaybackFollower
from desktop_preferences import restore_preferences, save_preferences
from desktop_strings import STRINGS
from desktop_options import VIDEO_EXTS, VIDEO_FILTERS, MODES, LANGUAGES, OUTPUT_FORMATS
from desktop_types import Job, STATUS_WAITING, STATUS_RUNNING, STATUS_DONE, STATUS_CANCELLED, STATUS_FAILED

import json
import os
import hashlib
import shutil
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QProcess
from PySide6.QtGui import QAction, QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)

APP_DIR = Path(__file__).resolve().parent
EXTRACTOR = APP_DIR / "video_text_extractor.py"
HISTORY_FILE = APP_DIR / ".transcribe_history.json"
SETTINGS_FILE = APP_DIR / ".transcribe_settings.json"


class VideoTextWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("音视频转写 · 校对工作台")
        self.resize(1380, 880)
        self.setMinimumSize(980, 680)
        self.setAcceptDrops(True)

        self.preview_path: Path | None = None
        self._preview_signature = None
        self._preview_versions = {}
        self._preview_hashes = {}
        self._preview_sources = {}
        self._drafts: dict[Path, str] = {}
        self._reading_dirty = True
        self._runtime_status = None
        self.follower = PlaybackFollower(self)
        self.draft_store = None
        self._recovery_batches = []
        self._recovery_loading = False
        self._closing = False
        self._autosave_warning = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(2000)
        self.autosave_timer.timeout.connect(self._autosave_drafts)
        self.last_input_dir = str(APP_DIR)
        self.burn_process: QProcess | None = None
        self.jobs: list[Job] = []
        self.active_processes: dict[int, subprocess.Popen[str]] = {}
        self.process_outputs: deque[tuple[int, int, str]] = deque(maxlen=2000)
        self.process_finishes: deque[tuple[int, int, int]] = deque(maxlen=256)
        self.process_generation = 0
        self.process_pump = QTimer(self)
        self.process_pump.setInterval(80)
        self.process_pump.timeout.connect(self._drain_process_events)
        self.max_parallel = 1
        self.language_to_code: dict[str, str] = {}
        self.ui_lang = "zh"
        self.history: list[dict] = self._load_history()

        self._build_actions()
        self._build_ui()
        self._apply_style()
        self._restore_preferences()
        self._retranslate()
        self._refresh_history_list()

        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(lambda message: self.statusBar().setVisible(bool(message)))
        self.statusBar().hide()
        self._init_recovery()

    def tr(self, key: str) -> str:
        return STRINGS[self.ui_lang].get(key, key)

    def _build_actions(self) -> None:
        self.shortcuts = {}
        commands = {
            "add": ("Ctrl+O", lambda: self.add_videos()),
            "save": ("Ctrl+S", lambda: self._save_preview()),
            "play": ("Ctrl+Space", lambda: self.media_player.toggle_play()),
            "back": ("Alt+Left", lambda: self.media_player.seek_relative(-3000)),
            "forward": ("Alt+Right", lambda: self.media_player.seek_relative(3000)),
            "find": ("Ctrl+F", lambda: self.show_find()),
            "replace": ("Ctrl+H", lambda: self.show_find(replace=True)),
            "next": ("F3", lambda: self.find_text()),
            "previous": ("Shift+F3", lambda: self.find_text(backward=True)),
            "next_review": ("Alt+Down", lambda: self.navigate_review(1)),
            "previous_review": ("Alt+Up", lambda: self.navigate_review(-1)),
        }
        for name, (shortcut, callback) in commands.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            if name == "play":
                action.setAutoRepeat(False)
            self.addAction(action)
            self.shortcuts[name] = action

    def _build_ui(self) -> None:
        return desktop_layout.build_ui(self)


    def _build_settings(self, layout: QVBoxLayout) -> None:
        return desktop_layout.build_settings(self, layout)


    def _build_queue(self, layout: QVBoxLayout) -> None:
        return desktop_layout.build_queue(self, layout)


    def _build_preview(self, layout: QVBoxLayout) -> None:
        return desktop_layout.build_preview(self, layout)


    def _build_find_bar(self, layout: QVBoxLayout) -> None:
        return desktop_layout.build_find_bar(self, layout)


    def _preview_text_changed(self) -> None:
        return desktop_workspace.preview_text_changed(self)


    def _change_view(self, index: int) -> None:
        return desktop_workspace.change_view(self, index)


    def _plain_text(self) -> str:
        return desktop_workspace.plain_text(self)


    def _update_reading_view(self) -> None:
        return desktop_workspace.update_reading_view(self)


    def _update_editor_controls(self) -> None:
        return desktop_workspace.update_editor_controls(self)


    def _clear_follow(self) -> None:
        return self.follower.clear()


    def _rebuild_follow(self) -> None:
        return self.follower.rebuild()


    def _follow_position(self, position: int) -> None:
        return self.follower.update(position)


    def show_find(self, replace: bool=False) -> None:
        return desktop_workspace.show_find(self, replace)


    def hide_find(self) -> None:
        return desktop_workspace.hide_find(self)


    def find_text(self, backward: bool=False) -> bool:
        return desktop_workspace.find_text(self, backward)


    def replace_current(self) -> None:
        return desktop_workspace.replace_current(self)


    def replace_all(self) -> None:
        return desktop_workspace.replace_all(self)


    def navigate_review(self, direction: int) -> None:
        return desktop_workspace.navigate_review(self, direction)


    def _adjust_review_height(self) -> None:
        self.review_list.setMaximumHeight(120 if self.height() >= 800 else (56 if self.find_bar.isVisible() else 68))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "review_list"):
            self._adjust_review_height()

    def _apply_style(self) -> None:
        self.setStyleSheet((APP_DIR / "desktop.qss").read_text(encoding="utf-8"))

    def _toggle_language(self) -> None:
        self.ui_lang = "en" if self.ui_lang == "zh" else "zh"
        self._retranslate()

    def _retranslate(self) -> None:
        s = STRINGS[self.ui_lang]
        self.setWindowTitle("音视频转写 · 校对工作台" if self.ui_lang == "zh" else "Transcription · Review workspace")
        self.title_label.setText(s["title"])
        self.subtitle_label.setText(s["subtitle"])
        self.lang_toggle.setText(s["lang_toggle"])
        self.add_button.setText(s["add_videos"])
        self.status_badge.setText(self._batch_status_text(s))
        self.heading_label.setText(s["page_title"])
        self.caption_label.setText(s["page_caption"])
        self.open_folder_button.setText(s["open_folder"])
        self.settings_group.setTitle(s["settings"])
        self.mode_label.setText(s["mode"])
        self.format_label.setText(s["video_format"])
        self.language_label.setText(s["language"])
        self.custom_label.setText(s["custom_code"])
        self.model_label.setText(s["model"])
        self.output_label.setText(s["output"])
        self.folder_label.setText(s["output_folder"])
        self.model_location_label.setText("模型目录" if self.ui_lang == "zh" else "Model storage")
        self.task_label.setText(s["task"])
        self.transcribe_radio.setText(s["transcribe"])
        self.translate_radio.setText(s["translate_en"])
        self.parallel_label.setText(s["parallel"])
        self.queue_label.setText(s["queue"])
        self.remove_button.setText(s["remove"])
        self.clear_button.setText(s["clear"])
        self.table.setHorizontalHeaderLabels([
            "", s["col_video"], s["col_size"], s["col_output"], s["col_status"]
        ])
        self.preview_title.setText(s["preview"])
        self.copy_button.setText("")
        self.copy_button.setToolTip(s["copy_preview"])
        self.save_preview_btn.setText("")
        self.save_preview_btn.setToolTip(s["save_preview"])
        self.preview.setPlaceholderText(s["preview_placeholder"])
        self.log_title.setText(s["log"])
        self.start_button.setText(s["start"])
        self.cancel_button.setText(s["cancel"])
        self.burn_button.setText(s["burn_sub"])
        self.details_tabs.setTabText(0, s["log"])
        self.details_tabs.setTabText(1, s["history"])
        self.skip_button.setText(s["skip"])
        self.history_label.setText(s["history"])
        self.history_load_btn.setText(s["history_load"])
        self.history_clear_btn.setText(s["history_clear"])
        self.output_browse_button.setToolTip(s["output_folder"])
        self._refresh_history_list()
        self._refresh_runtime()
        self.media_player.set_language(self.ui_lang)
        self.advanced_button.setText(self.tr("advanced"))
        self.enhance_check.setText(self.tr("enhance"))
        self.allow_cloud_check.setText(self.tr("allow_cloud"))
        self.enhance_check.setToolTip(self.tr("enhance_tip"))
        self.terms_label.setText(self.tr("terms"))
        self.terms_edit.setPlaceholderText(self.tr("terms_hint"))
        self.channel_label.setText(self.tr("channel"))
        for index, code in enumerate(("mix", "left", "right")):
            self.channel_combo.setItemText(index, self.tr("channel_" + code))
        self.reading_button.setToolTip(self.tr("reading_copy"))
        self.reading_button.setToolTip(self.tr("more_actions"))
        self.copy_button.setToolTip(self.tr("copy_plain"))
        self.save_preview_btn.setToolTip(self.tr("save_preview") + " (Ctrl+S)")
        self.view_tabs.setTabText(0, self.tr("edit_view"))
        self.view_tabs.setTabText(1, self.tr("read_view"))
        self.shortcuts["find"].setText(self.tr("find"))
        self.shortcuts["replace"].setText(self.tr("replace"))
        self.open_result_action.setText(self.tr("open_result"))
        self.reading_export_action.setText(self.tr("reading_copy"))
        self.copy_original_action.setText(self.tr("copy_original"))
        self.recovery_action.setText(self.tr("recovery_title"))
        self.find_input.setPlaceholderText(self.tr("find_hint"))
        self.replace_input.setPlaceholderText(self.tr("replace_hint"))
        self.replace_button.setText(self.tr("replace"))
        self.replace_all_button.setText(self.tr("replace_all"))
        self.find_previous.setToolTip(self.tr("find") + " (Shift+F3)")
        self.find_next.setToolTip(self.tr("find") + " (F3)")
        self.find_close.setToolTip("Esc")
        self.details_button.setToolTip(self.tr("details"))
        self.review_button.setToolTip(self.tr("review_tip"))
        self.review_button.setText(self.tr("review_stale") if getattr(self, "_review_stale", False)
                                   else self.tr("review_count").format(self.review_list.count()))
        for index, (key, _display) in enumerate(MODES):
            self.mode_combo.setItemText(index, self.tr("mode_" + key))
        self._update_model_hint()
        self.refresh_table()
        self._rebuild_follow()

    def _batch_status_text(self, strings: dict[str, str]) -> str:
        statuses = {job.status for job in self.jobs}
        if self.active_processes or STATUS_RUNNING in statuses:
            return strings["running_status"]
        if statuses and STATUS_WAITING not in statuses:
            return " · ".join(f"{strings[key]} {sum(job.status == status for job in self.jobs)}"
                              for status, key in ((STATUS_DONE, "done_status"), (STATUS_FAILED, "failed_status"), (STATUS_CANCELLED, "cancelled_status"))
                              if status in statuses)
        return strings["ready_status"]

    def _status_text(self, status: str) -> str:
        s = STRINGS[self.ui_lang]
        return {
            STATUS_WAITING: s["waiting_status"],
            STATUS_RUNNING: s["running_status"],
            STATUS_DONE: s["done_status"],
            STATUS_CANCELLED: s["cancelled_status"],
            STATUS_FAILED: s["failed_status"],
        }.get(status, status)

    def _refresh_runtime(self) -> None:
        from video_text_extractor import detect_tools, ffmpeg_command

        if self._runtime_status is None:
            self._runtime_status = detect_tools()
        status = self._runtime_status
        s = STRINGS[self.ui_lang]
        rows = [
            (s['local_whisper'], status.local_whisper),
            ("ffmpeg", bool(ffmpeg_command(status))),
            ("Tesseract OCR", bool(status.tesseract)),
            (s['openai_key'], status.openai_key),
            (s['gpu'], status.cuda_gpu),
        ]
        self.runtime_list.clear()
        for label, ok in rows:
            text = f"{label}  ·  {s['ready'] if ok else s['missing']}"
            item = QListWidgetItem(text)
            if ok:
                item.setForeground(QColor("#197661"))
            else:
                item.setForeground(QColor("#a77528"))
            self.runtime_list.addItem(item)

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        self.allow_cloud_check.setVisible(mode == "auto")
        self.allow_cloud_check.setChecked(False)
        uses_whisper_settings = mode in {"whisper", "auto"}
        has_output_format = mode not in {"subtitle", "ocr", "sensevoice"}
        self.model_label.setVisible(uses_whisper_settings)
        self.model_combo.setVisible(uses_whisper_settings)
        self.model_hint.setVisible(uses_whisper_settings or mode == "sensevoice")
        self.task_label.setVisible(uses_whisper_settings)
        self.transcribe_radio.setVisible(uses_whisper_settings)
        self.translate_radio.setVisible(uses_whisper_settings)
        self.language_label.setVisible(mode not in {"subtitle", "sensevoice"})
        self.language_combo.setVisible(mode not in {"subtitle", "sensevoice"})
        self._toggle_custom_language()
        self.output_label.setVisible(True)
        self.output_combo.setVisible(True)
        self.output_combo.setEnabled(has_output_format)
        if not has_output_format:
            self.output_combo.setCurrentText("SRT" if mode == "subtitle" else "TXT")
        self.parallel_label.setVisible(uses_whisper_settings)
        self.parallel_spin.setVisible(uses_whisper_settings)
        for name in ("channel_combo", "channel_label", "enhance_check"):
            if hasattr(self, name):
                getattr(self, name).setVisible(uses_whisper_settings or (mode == "sensevoice" and name != "enhance_check"))
        if hasattr(self, "terms_edit"):
            self.terms_label.setVisible(mode in {"whisper", "auto", "audio"})
            self.terms_edit.setVisible(mode in {"whisper", "auto", "audio"})
        self.refresh_outputs()
        self._update_model_hint()
        if mode not in {"whisper", "auto"}:
            self.parallel_spin.setValue(1)

    def _on_parallel_changed(self, value: int) -> None:
        self.max_parallel = value

    def _toggle_custom_language(self) -> None:
        mode = self.mode_combo.currentData()
        is_custom = self.language_to_code.get(self.language_combo.currentText()) == "custom"
        visible = is_custom and mode not in {"subtitle", "sensevoice"}
        self.custom_label.setVisible(visible)
        self.custom_language.setVisible(visible)

    def _update_model_hint(self, *_args) -> None:
        sizes = {"tiny": "75 MB", "base": "145 MB", "small": "461 MB", "medium": "1.4 GB", "large-v3": "2.9 GB", "turbo": "1.6 GB"}
        model = self.model_combo.currentText()
        from model_storage import model_directory
        sensevoice = self.mode_combo.currentData() == "sensevoice"
        cached = (model_directory("sensevoice") / "model.int8.onnx").is_file() if sensevoice else (model_directory("whisper") / f"{model}.pt").is_file()
        size = "239 MB" if sensevoice else sizes.get(model, "")
        self.model_hint.setText(self.tr("model_cached") if cached else self.tr("model_size").format(size))

    # --- Drag and drop ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in VIDEO_EXTS:
                self.add_video_path(path)

    # --- Core operations ---

    def add_videos(self) -> None:
        selected = self.format_combo.currentText()
        pattern = VIDEO_FILTERS[selected]
        s = STRINGS[self.ui_lang]
        filters = f"{selected} ({pattern});;All files (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, s["add_videos"], self.last_input_dir, filters)
        for raw_path in paths:
            self.add_video_path(Path(raw_path))

    def add_video_path(self, path: Path) -> None:
        if self.active_processes:
            return
        path = path.expanduser()
        s = STRINGS[self.ui_lang]
        if not path.exists():
            QMessageBox.warning(self, s["missing_file"], s["missing_file_msg"].format(path))
            return
        if not path.is_file():
            QMessageBox.warning(self, s["missing_file"], s["missing_file_msg"].format(path))
            return
        path = path.resolve()
        self.last_input_dir = str(path.parent)
        if any(job.video == path for job in self.jobs):
            return
        mode = self.mode_combo.currentData()
        self.jobs.append(Job(video=path, output=self.output_path_for(path), mode=mode))
        self.refresh_outputs()
        self._update_model_hint(path)

    def remove_selected(self) -> None:
        if self.active_processes:
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.jobs):
                del self.jobs[row]
        self.refresh_table()

    def clear_queue(self) -> None:
        if self.active_processes:
            return
        self.jobs.clear()
        self.refresh_table()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, STRINGS[self.ui_lang]["output_folder"], str(self.output_directory()))
        if path:
            self.output_dir.setText(path)

    def refresh_outputs(self, *_signal_args, reconfigure: bool = False) -> None:
        mode = self.mode_combo.currentData()
        used = {job.output for job in self.jobs if job.status != STATUS_WAITING and not reconfigure}
        for job in self.jobs:
            if job.status != STATUS_WAITING and not reconfigure:
                continue
            job.mode = mode
            output = self.output_path_for(job.video)
            if output in used:
                digest = hashlib.sha256(str(job.video.resolve()).encode("utf-8")).hexdigest()[:8]
                output = output.with_name(f"{output.stem}_{digest}{output.suffix}")
            used.add(output)
            job.output = output
        if hasattr(self, "table"):
            self.refresh_table()

    def output_directory(self) -> Path:
        raw = Path(self.output_dir.text().strip() or APP_DIR)
        return raw if raw.is_absolute() else APP_DIR / raw

    def output_path_for(self, video: Path) -> Path:
        output_dir = self.output_directory()
        mode = self.mode_combo.currentData()
        if mode == "subtitle":
            return output_dir / f"{video.stem}_subtitles.srt"
        if mode == "ocr":
            return output_dir / f"{video.stem}_ocr.txt"
        if mode == "sensevoice":
            return output_dir / f"{video.stem}_sensevoice_zh.txt"
        fmt, suffix = OUTPUT_FORMATS[self.output_combo.currentText()]
        language = self.language_code() or "auto"
        return output_dir / f"{video.stem}_transcript_{safe_part(language)}{suffix}"

    def language_code(self) -> str | None:
        code = self.language_to_code.get(self.language_combo.currentText(), "")
        if code == "custom":
            return self.custom_language.text().strip() or None
        return code or None

    def refresh_table(self) -> None:
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.jobs))
        for row, job in enumerate(self.jobs):
            # Do not spawn ffmpeg on the GUI thread when rebuilding the queue.
            thumb_item = QTableWidgetItem(job.video.suffix.lstrip(".").upper())
            thumb_item.setForeground(QColor("#697b75"))
            thumb_item.setTextAlignment(Qt.AlignCenter)
            thumb_item.setFlags(thumb_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, thumb_item)
            # Data columns
            status_text = self._status_text(job.status)
            if job.status == STATUS_RUNNING and job.stage:
                status_text = self.tr("stage_" + job.stage)
                if job.progress is not None:
                    status_text += f" {job.progress}%"
            values = [job.video.name, file_size(job.video), str(job.output), status_text]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(str(job.output) if col == 0 else value)
                if col == 3 and job.status == STATUS_FAILED:
                    item.setForeground(QColor("#a44036"))
                    item.setToolTip(self.tr("job_error"))
                if col in {1, 3}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col + 1, item)
        if 0 <= selected < len(self.jobs):
            self.table.selectRow(selected)
        self.table.blockSignals(False)
        self.preview_selected_output()
        if hasattr(self, "status_badge"):
            self.status_badge.setText(self._batch_status_text(STRINGS[self.ui_lang]))

    @staticmethod
    def _output_stamp(path: Path | None):
        try:
            stat = path.stat() if path is not None else None
            return (stat.st_mtime_ns, stat.st_size) if stat else None
        except OSError:
            return None

    def preview_selected_output(self, force: bool=False) -> None:
        return desktop_workspace.preview_selected_output(self, force)


    def command_for(self, job: Job) -> list[str]:
        mode = job.mode
        fmt, _suffix = OUTPUT_FORMATS[self.output_combo.currentText()]
        if mode == "subtitle":
            fmt = "srt"
        elif mode in {"ocr", "sensevoice"}:
            fmt = "text"
        command = [
            python_console_executable(), "-u", str(EXTRACTOR),
            str(job.video),
            "--mode", mode,
            "--format", fmt,
            "-o", str(job.output),
        ]
        if mode in {"whisper", "auto"}:
            if mode == "auto" and self.allow_cloud_check.isChecked():
                command.append("--allow-cloud-fallback")
            command.extend(["--whisper-model", self.model_combo.currentText()])
            language = self.language_code()
            if language:
                command.extend(["--language", language])
            if self.translate_radio.isChecked():
                command.extend(["--whisper-task", "translate"])
        elif mode == "ocr":
            language = self.language_code()
            if language:
                command.extend(["--language", language])
        elif mode == "audio":
            language = self.language_code()
            if language:
                command.extend(["--language", language])
        if mode in {"whisper", "auto", "sensevoice"}:
            command.extend(["--audio-channel", self.channel_combo.currentData()])
            if mode != "sensevoice" and self.enhance_check.isChecked():
                command.append("--enhance-audio")
        if mode in {"whisper", "auto", "audio"} and self.terms_edit.toPlainText().strip():
            command.extend(["--prompt", self.terms_edit.toPlainText().strip()])
        return command

    # --- Parallel job execution ---

    def start_jobs(self) -> None:
        s = STRINGS[self.ui_lang]
        if self.active_processes or self.burn_process is not None:
            return
        if not self.jobs:
            QMessageBox.information(self, s["queue_empty"], s["queue_empty_msg"])
            return
        if self.mode_combo.currentData() == "auto" and self.allow_cloud_check.isChecked():
            if QMessageBox.question(self, s["cloud_title"], s["cloud_warning"],
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        try:
            self.output_directory().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, s["missing_file"], str(exc))
            return
        self.refresh_outputs(reconfigure=True)
        self._save_preferences()
        reserved = set()
        for job in self.jobs:
            original = job.output
            counter = 2
            while job.output.exists() or job.output in reserved:
                job.output = original.with_name(f"{original.stem}_{counter}{original.suffix}")
                counter += 1
            reserved.add(job.output)
        self.process_generation += 1
        self._clear_process_queues()
        for job in self.jobs:
            job.status = STATUS_WAITING
            job.stage = ""
            job.progress = None
        self.log.clear()
        self.preview_selected_output()
        self.progress.setRange(0, 0)
        self.status_badge.setText(s["running_status"])
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.skip_button.setText(s["skip"])
        self.skip_button.setVisible(True)
        self._set_editing_enabled(False)
        self.refresh_table()
        self._save_history_entry()
        self._fill_parallel_slots()

    def _fill_parallel_slots(self) -> None:
        return desktop_queue.fill_parallel_slots(self)

    def _next_waiting_index(self) -> int | None:
        return desktop_queue.next_waiting_index(self)

    def _start_job(self, index: int) -> None:
        return desktop_queue.start_job(self, index)

    def _read_process_stream(self, generation: int, index: int, process: subprocess.Popen[str]) -> None:
        return desktop_queue.read_process_stream(self, generation, index, process)

    def _drain_process_events(self) -> None:
        return desktop_queue.drain_process_events(self)

    def _parse_progress(self, text: str, index: int | None=None) -> None:
        return desktop_queue.parse_progress(self, text, index)

    def _job_finished(self, index: int, exit_code: int) -> None:
        return desktop_queue.job_finished(self, index, exit_code)

    def _job_start_failed(self, index: int, message: str) -> None:
        return desktop_queue.job_start_failed(self, index, message)

    def finish_batch(self) -> None:
        return desktop_queue.finish_batch(self)

    def cancel_all(self) -> None:
        return desktop_queue.cancel_all(self)

    def skip_current(self) -> None:
        return desktop_queue.skip_current(self)

    def closeEvent(self, event) -> None:
        self._autosave_drafts()
        if self.preview_path is not None and self.preview.document().isModified():
            self._drafts[self.preview_path] = self.preview.toPlainText()
        if self._drafts:
            choice = QMessageBox.question(self, self.tr("close_title"), self.tr("unsaved"),
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if choice == QMessageBox.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.Save:
                try:
                    if self.active_processes:
                        raise ValueError(self.tr("running_status"))
                    for output, text in list(self._drafts.items()):
                        self._write_draft(output, text)
                        self._drafts.pop(output, None)
                    self.preview.document().setModified(False)
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    QMessageBox.warning(self, self.tr("save_preview"), self.tr("save_failed") + "\n\n" + str(exc))
                    event.ignore()
                    return
        self._save_preferences()
        self._closing = True
        self.autosave_timer.stop()
        self.media_player.set_source(None)
        if self.burn_process is not None:
            self.burn_process.kill()
            self.burn_process.waitForFinished(3000)
        if self.active_processes:
            self.cancel_all()
        for batch in self._recovery_batches:
            batch.release()
        self._recovery_batches.clear()
        if self.draft_store is not None:
            try:
                self.draft_store.close()
            except OSError as exc:
                self.append_log(f"Draft backup cleanup failed: {exc}\n")
            self.draft_store = None
        super().closeEvent(event)

    def _clear_process_queues(self) -> None:
        return desktop_queue.clear_process_queues(self)

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.history_load_btn,
            self.history_clear_btn,
            self.mode_combo,
            self.allow_cloud_check,
            self.format_combo,
            self.language_combo,
            self.custom_language,
            self.model_combo,
            self.output_combo,
            self.output_dir,
            self.output_browse_button,
            self.transcribe_radio,
            self.translate_radio,
            self.parallel_spin,
            self.channel_combo,
            self.enhance_check,
            self.terms_edit,
            self.burn_button,
        ):
            widget.setEnabled(enabled)
        if enabled:
            self.output_combo.setEnabled(self.mode_combo.currentData() not in {"sensevoice", "subtitle", "ocr"})
        self.preview_selected_output()

    # --- Progress & log ---

    def append_log(self, text: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)

    def copy_preview(self) -> None:
        return desktop_workspace.copy_preview(self)


    def _write_draft(self, output: Path, text: str) -> None:
        return desktop_workspace.write_draft(self, output, text)


    def _save_preview(self) -> None:
        return desktop_workspace.save_preview(self)


    def _load_review(self, output: Path | None, source: Path | None) -> None:
        return desktop_workspace.load_review(self, output, source)


    def _seek_review_item(self, item) -> None:
        return desktop_workspace.seek_review_item(self, item)


    def export_reading_copy(self) -> None:
        return desktop_workspace.export_reading_copy(self)


    def open_output_folder(self) -> None:
        path = self.preview_path.parent if self.preview_path else self.output_directory()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            s = STRINGS[self.ui_lang]
            QMessageBox.warning(self, s["missing_file"], str(exc))
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            s = STRINGS[self.ui_lang]
            QMessageBox.warning(self, s["missing_file"], str(exc))

    def open_selected_output(self) -> None:
        path = self.preview_path
        if path is None or not path.is_file():
            QMessageBox.warning(self, self.tr("open_result"), self.tr("missing_file_msg").format(path or self.output_directory()))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, self.tr("open_result"), self.tr("open_failed"))

    # --- Burn subtitles ---

    def burn_subtitles(self) -> None:
        if self.active_processes or self.burn_process is not None:
            return
        from video_text_extractor import detect_tools, ffmpeg_command, local_temp_dir
        s = STRINGS[self.ui_lang]
        status = detect_tools()
        ffmpeg = ffmpeg_command(status)
        if not ffmpeg:
            QMessageBox.warning(self, s["burn_title"], s["burn_ffmpeg_missing"])
            return

        video_path, _ = QFileDialog.getOpenFileName(
            self, s["burn_input_title"], str(APP_DIR),
            "Video files (*.mp4 *.mov *.mkv *.webm *.m4v *.avi);;All files (*.*)")
        if not video_path:
            return

        srt_path, _ = QFileDialog.getOpenFileName(
            self, s["burn_srt_title"], str(Path(video_path).parent),
            "SRT files (*.srt);;All files (*.*)")
        if not srt_path:
            return

        video_p = Path(video_path).resolve()
        output_path = video_p.with_name(f"{video_p.stem}_subtitled.mp4")
        counter = 2
        while output_path.exists():
            output_path = video_p.with_name(f"{video_p.stem}_subtitled_{counter}.mp4")
            counter += 1

        # A fixed relative subtitle filename avoids both layers of filter escaping.
        context = local_temp_dir(output_path.parent, "burn_subtitle_")
        try:
            temp_dir = context.__enter__()
            shutil.copy2(srt_path, temp_dir / "subtitle.srt")
        except OSError as exc:
            context.__exit__(type(exc), exc, exc.__traceback__)
            self.append_log(f"Error: {exc}\n")
            return
        process = QProcess(self)
        self.burn_process = process
        process.setWorkingDirectory(str(temp_dir))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda: self.append_log(bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")))
        completed = False

        def finish(code: int, *_args) -> None:
            nonlocal completed
            if completed:
                return
            completed = True
            context.__exit__(None, None, None)
            self.burn_process = None
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self._set_editing_enabled(True)
            self.append_log((s["burn_done"].format(output_path) if code == 0 else "Subtitle burn failed.") + "\n")
            self.status_badge.setText(self._batch_status_text(s))
            process.deleteLater()

        process.finished.connect(finish)
        process.errorOccurred.connect(lambda error: finish(1) if error == QProcess.FailedToStart else None)
        self.start_button.setEnabled(False)
        self._set_editing_enabled(False)
        self.cancel_button.setEnabled(True)
        self.status_badge.setText(s["burn_sub"])
        process.start(ffmpeg, [
            "-nostdin", "-n", "-i", str(video_p),
            "-vf", "subtitles=subtitle.srt", "-c:a", "aac", str(output_path),
        ])

    def _ffmpeg_filter_path(self, path: str) -> str:
        value = Path(path).resolve().as_posix()
        replacements = {
            "\\": "/",
            ":": r"\:",
            "'": r"\'",
            " ": r"\ ",
            ",": r"\,",
            "[": r"\[",
            "]": r"\]",
            ";": r"\;",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value

    # --- History ---

    def _init_recovery(self) -> None:
        return desktop_recovery.init_recovery(self, SETTINGS_FILE)


    def _autosave_drafts(self) -> bool:
        return desktop_recovery.autosave_drafts(self)


    def _offer_recovery(self) -> None:
        return desktop_recovery.offer_recovery(self)


    def _restore_preferences(self) -> None:
        return restore_preferences(self, SETTINGS_FILE)


    def _save_preferences(self) -> None:
        return save_preferences(self, SETTINGS_FILE)


    def _load_history(self) -> list[dict]:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history_entry(self) -> None:
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": [str(j.video) for j in self.jobs],
            "mode": self.mode_combo.currentData(),
            "model": self.model_combo.currentText(),
            "language": self.language_code() or "auto",
            "format": self.output_combo.currentText(),
            "translate": self.translate_radio.isChecked(),
            "channel": self.channel_combo.currentData(),
            "enhance": self.enhance_check.isChecked(),
            "prompt": self.terms_edit.toPlainText(),
        }
        self.history.insert(0, entry)
        self.history = self.history[:50]
        try:
            HISTORY_FILE.write_text(json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        self.history_list.clear()
        if not self.history:
            s = STRINGS[self.ui_lang]
            self.history_list.addItem(s["history_empty"])
            return
        for entry in self.history[:20]:
            files = ", ".join(Path(f).name for f in entry.get("files", [])[:3])
            mode = entry.get("mode", "whisper")
            time_str = entry.get("time", "")
            self.history_list.addItem(f"[{time_str}] {mode} | {files}")

    def _load_selected_history(self) -> None:
        if self.active_processes:
            return
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.history):
            return
        entry = self.history[row]
        self._restore_history_settings(entry)
        for file_str in entry.get("files", []):
            p = Path(file_str)
            if p.exists() and not any(j.video == p for j in self.jobs):
                self.jobs.append(Job(video=p, output=self.output_path_for(p), mode=self.mode_combo.currentData()))
        self.refresh_outputs()

    def _restore_history_settings(self, entry: dict) -> None:
        self._set_combo_data(self.mode_combo, entry.get("mode", "whisper"))
        self.model_combo.setCurrentText(entry.get("model", "base"))
        self._set_combo_text(self.output_combo, entry.get("format", "TXT"))
        self._set_language_code(entry.get("language", "auto"))
        self.translate_radio.setChecked(bool(entry.get("translate", False)))
        self.transcribe_radio.setChecked(not self.translate_radio.isChecked())
        self._set_combo_data(self.channel_combo, entry.get("channel", "mix"))
        self.enhance_check.setChecked(bool(entry.get("enhance", False)))
        self.terms_edit.setPlainText(entry.get("prompt", ""))
        self.refresh_outputs()

    def _set_combo_data(self, combo: QComboBox, data: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return

    def _set_combo_text(self, combo: QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_language_code(self, code: str) -> None:
        normalized = "" if code in {"", "auto", None} else str(code)
        for i in range(self.language_combo.count()):
            text = self.language_combo.itemText(i)
            if self.language_to_code.get(text) == normalized:
                self.language_combo.setCurrentIndex(i)
                return
        for i in range(self.language_combo.count()):
            text = self.language_combo.itemText(i)
            if self.language_to_code.get(text) == "custom":
                self.language_combo.setCurrentIndex(i)
                self.custom_language.setText(normalized)
                return

    def _clear_history(self) -> None:
        self.history.clear()
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        self._refresh_history_list()


def main() -> int:
    app = QApplication(sys.argv)
    if sys.platform == "win32":
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "segoeui.ttf"):
            QFontDatabase.addApplicationFont(str(font_dir / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = VideoTextWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
