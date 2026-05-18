from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_DIR = Path(__file__).resolve().parent
EXTRACTOR = APP_DIR / "video_text_extractor.py"
HISTORY_FILE = APP_DIR / ".transcribe_history.json"

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wmv", ".flv",
    ".mpg", ".mpeg", ".3gp", ".ts", ".mts", ".m2ts", ".ogv",
}

VIDEO_FILTERS = {
    "All supported": "*.mp4 *.mov *.mkv *.webm *.m4v *.avi *.wmv *.flv *.mpg *.mpeg *.3gp *.ts *.mts *.m2ts *.ogv",
    "MP4": "*.mp4",
    "MOV": "*.mov",
    "MKV": "*.mkv",
    "WEBM": "*.webm",
    "M4V": "*.m4v",
    "AVI": "*.avi",
    "WMV": "*.wmv",
    "FLV": "*.flv",
    "MPEG/MPG": "*.mpeg *.mpg",
    "Transport Stream": "*.ts *.mts *.m2ts",
    "OGV": "*.ogv",
}

MODES = [
    ("whisper", "Local Whisper"),
    ("audio", "OpenAI API"),
    ("subtitle", "Embedded subtitles"),
    ("ocr", "Visual OCR"),
    ("auto", "Auto (best)"),
]

LANGUAGES = [
    ("Auto detect", ""),
    ("English", "en"),
    ("Chinese", "zh"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Italian", "it"),
    ("Portuguese", "pt"),
    ("Russian", "ru"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("Vietnamese", "vi"),
    ("Thai", "th"),
    ("Turkish", "tr"),
    ("Dutch", "nl"),
    ("Swedish", "sv"),
    ("Polish", "pl"),
    ("Ukrainian", "uk"),
    ("Indonesian", "id"),
    ("Malay", "ms"),
    ("Bengali", "bn"),
    ("Urdu", "ur"),
    ("Persian", "fa"),
    ("Hebrew", "he"),
    ("Greek", "el"),
    ("Czech", "cs"),
    ("Danish", "da"),
    ("Finnish", "fi"),
    ("Hungarian", "hu"),
    ("Romanian", "ro"),
    ("Norwegian", "no"),
    ("Catalan", "ca"),
    ("Latin", "la"),
    ("Slovak", "sk"),
    ("Slovenian", "sl"),
    ("Croatian", "hr"),
    ("Serbian", "sr"),
    ("Bulgarian", "bg"),
    ("Lithuanian", "lt"),
    ("Latvian", "lv"),
    ("Estonian", "et"),
    ("Swahili", "sw"),
    ("Malayalam", "ml"),
    ("Tamil", "ta"),
    ("Telugu", "te"),
    ("Georgian", "ka"),
    ("Kazakh", "kk"),
    ("Nepali", "ne"),
    ("Amharic", "am"),
    ("Burmese", "my"),
    ("Khmer", "km"),
    ("Lao", "lo"),
    ("Mongolian", "mn"),
    ("Azerbaijani", "az"),
    ("Uzbek", "uz"),
    ("Custom code", "custom"),
]

OUTPUT_FORMATS = {
    "TXT": ("text", ".txt"),
    "SRT": ("srt", ".srt"),
    "VTT": ("vtt", ".vtt"),
    "JSON": ("json", ".json"),
}

STRINGS = {
    "zh": {
        "title": "视频文字\n提取器",
        "subtitle": "本地转写工作室\n基于 Whisper",
        "ready": "就绪",
        "missing": "缺失",
        "local_whisper": "本地 Whisper",
        "openai_key": "OpenAI 密钥",
        "add_videos": "添加视频",
        "status_ready": "就绪",
        "status_running": "运行中",
        "status_done": "完成",
        "status_cancelled": "已取消",
        "waiting_status": "等待中",
        "page_title": "转写工作区",
        "page_caption": "批量处理视频，选择语言，导出文本或字幕。",
        "open_folder": "打开输出目录",
        "settings": "设置",
        "mode": "模式",
        "video_format": "视频格式",
        "language": "语言",
        "custom_code": "自定义代码",
        "model": "模型",
        "output": "输出格式",
        "output_folder": "输出目录",
        "task": "任务",
        "transcribe": "转写",
        "translate_en": "翻译成英文",
        "parallel": "并行数",
        "queue": "队列",
        "remove": "移除",
        "clear": "清空",
        "col_video": "视频",
        "col_size": "大小",
        "col_output": "输出",
        "col_status": "状态",
        "preview": "预览",
        "copy_preview": "复制预览",
        "preview_placeholder": "转写完成后将在此显示。",
        "log": "日志",
        "start": "开始",
        "cancel": "取消",
        "burn_sub": "烧录字幕",
        "history": "历史记录",
        "history_load": "加载",
        "history_clear": "清空历史",
        "queue_empty": "队列为空",
        "queue_empty_msg": "请先添加至少一个视频。",
        "missing_file": "文件缺失",
        "missing_file_msg": "找不到文件：\n{}",
        "burn_title": "烧录字幕到视频",
        "burn_need_srt": "请先选择一个 SRT 输出的转写任务。",
        "burn_ffmpeg_missing": "需要 ffmpeg 才能烧录字幕。",
        "burn_done": "字幕已烧录：\n{}",
        "burn_input_title": "选择视频文件",
        "burn_srt_title": "选择 SRT 字幕文件",
        "lang_toggle": "EN",
        "ready_status": "就绪",
        "running_status": "运行中",
        "done_status": "完成",
        "cancelled_status": "已取消",
        "failed_status": "失败",
        "starting": "开始处理：{}",
        "saved": "已保存：{}",
        "failed_code": "失败，退出码 {}",
        "output_will_be": "输出将保存到：\n{}",
        "suggest_model": "推荐模型: {}",
        "history_empty": "暂无历史记录",
        "gpu": "CUDA GPU",
        "save_preview": "保存预览",
    },
    "en": {
        "title": "Video Text\nExtractor",
        "subtitle": "Local transcription studio\nPowered by Whisper",
        "ready": "Ready",
        "missing": "Missing",
        "local_whisper": "Local Whisper",
        "openai_key": "OpenAI key",
        "add_videos": "Add videos",
        "status_ready": "Ready",
        "status_running": "Running",
        "status_done": "Done",
        "status_cancelled": "Cancelled",
        "waiting_status": "Waiting",
        "page_title": "Transcription Workspace",
        "page_caption": "Batch videos, choose languages, export text or subtitles.",
        "open_folder": "Open output folder",
        "settings": "Settings",
        "mode": "Mode",
        "video_format": "Video format",
        "language": "Language",
        "custom_code": "Custom code",
        "model": "Model",
        "output": "Output",
        "output_folder": "Output folder",
        "task": "Task",
        "transcribe": "Transcribe",
        "translate_en": "Translate to English",
        "parallel": "Parallel",
        "queue": "Queue",
        "remove": "Remove",
        "clear": "Clear",
        "col_video": "Video",
        "col_size": "Size",
        "col_output": "Output",
        "col_status": "Status",
        "preview": "Preview",
        "copy_preview": "Copy preview",
        "preview_placeholder": "Completed transcript appears here.",
        "log": "Log",
        "start": "Start",
        "cancel": "Cancel",
        "burn_sub": "Burn subtitles",
        "history": "History",
        "history_load": "Load",
        "history_clear": "Clear history",
        "queue_empty": "Queue empty",
        "queue_empty_msg": "Add at least one video first.",
        "missing_file": "Missing file",
        "missing_file_msg": "Cannot find:\n{}",
        "burn_title": "Burn subtitles into video",
        "burn_need_srt": "Select a task with SRT output first.",
        "burn_ffmpeg_missing": "ffmpeg is required to burn subtitles.",
        "burn_done": "Subtitles burned:\n{}",
        "burn_input_title": "Select video file",
        "burn_srt_title": "Select SRT subtitle file",
        "lang_toggle": "中",
        "ready_status": "Ready",
        "running_status": "Running",
        "done_status": "Done",
        "cancelled_status": "Cancelled",
        "failed_status": "Failed",
        "starting": "Starting: {}",
        "saved": "Saved: {}",
        "failed_code": "Failed with exit code {}",
        "output_will_be": "Output will be saved to:\n{}",
        "suggest_model": "Suggested: {}",
        "history_empty": "No history yet",
        "gpu": "CUDA GPU",
        "save_preview": "Save preview",
    },
}

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


def safe_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._") or "auto"


def file_size(path: Path) -> str:
    size = path.stat().st_size
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.2f} GB"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024:.1f} KB"


THUMB_CACHE: dict[Path, QPixmap] = {}


def python_console_executable() -> str:
    executable = Path(sys.executable)
    if sys.platform == "win32" and executable.name.lower() == "pythonw.exe":
        python_exe = executable.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return sys.executable


def get_video_thumbnail(path: Path) -> QPixmap | None:
    if path in THUMB_CACHE:
        return THUMB_CACHE[path]
    try:
        from video_text_extractor import detect_tools, ffmpeg_command, local_temp_dir
        status = detect_tools()
        ffmpeg = ffmpeg_command(status)
        if not ffmpeg:
            return None
        with local_temp_dir(APP_DIR / ".video_text_cache", "thumb_") as temp_dir:
            tmp_path = temp_dir / "frame.jpg"
            subprocess.run(
                [ffmpeg, "-y", "-i", str(path), "-vframes", "1", "-vf", "scale=80:-1", str(tmp_path)],
                capture_output=True, timeout=10,
            )
            pixmap = QPixmap(str(tmp_path))
            if not pixmap.isNull():
                THUMB_CACHE[path] = pixmap
                return pixmap
    except Exception:
        pass
    return None


def get_video_duration(path: Path) -> float:
    try:
        from video_text_extractor import detect_tools
        status = detect_tools()
        ffprobe = status.ffprobe
        if not ffprobe:
            return 0.0
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def suggest_model(duration_sec: float) -> str:
    if duration_sec <= 0:
        return "base"
    if duration_sec < 120:
        return "small"
    if duration_sec < 600:
        return "base"
    return "tiny"


class VideoTextWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Text Extractor")
        self.resize(1380, 880)
        self.setMinimumSize(1100, 750)
        self.setAcceptDrops(True)

        self.jobs: list[Job] = []
        self.active_processes: dict[int, subprocess.Popen[str]] = {}
        self.process_outputs: queue.Queue[tuple[int, int, str]] = queue.Queue()
        self.process_finishes: queue.Queue[tuple[int, int, int]] = queue.Queue()
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
        self._refresh_runtime()
        self._retranslate()
        self._refresh_history_list()

    def tr(self, key: str) -> str:
        return STRINGS[self.ui_lang].get(key, key)

    def _build_actions(self) -> None:
        add_action = QAction("Add videos", self)
        add_action.triggered.connect(self.add_videos)
        self.addAction(add_action)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(282)
        outer.addWidget(sidebar)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(22, 22, 22, 22)
        side_layout.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setObjectName("appTitle")
        side_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("appSubtitle")
        side_layout.addWidget(self.subtitle_label)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        lang_icon = QLabel("\U0001f310")
        lang_icon.setObjectName("langIcon")
        lang_row.addWidget(lang_icon)
        self.lang_toggle = QPushButton()
        self.lang_toggle.setObjectName("langToggle")
        self.lang_toggle.setFixedWidth(48)
        self.lang_toggle.clicked.connect(self._toggle_language)
        lang_row.addWidget(self.lang_toggle)
        lang_row.addStretch(1)
        side_layout.addLayout(lang_row)

        self.runtime_list = QListWidget()
        self.runtime_list.setObjectName("runtimeList")
        self.runtime_list.setFixedHeight(160)
        side_layout.addWidget(self.runtime_list)

        side_layout.addSpacing(4)
        self.add_button = QPushButton()
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self.add_videos)
        side_layout.addWidget(self.add_button)

        side_layout.addStretch(1)

        self.status_badge = QLabel()
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(self.status_badge)

        content = QFrame()
        content.setObjectName("content")
        outer.addWidget(content, 1)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 22, 24, 22)
        content_layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        heading_box = QVBoxLayout()
        self.heading_label = QLabel()
        self.heading_label.setObjectName("pageTitle")
        heading_box.addWidget(self.heading_label)
        self.caption_label = QLabel()
        self.caption_label.setObjectName("pageCaption")
        heading_box.addWidget(self.caption_label)
        header.addLayout(heading_box, 1)

        self.open_folder_button = QPushButton()
        self.open_folder_button.clicked.connect(self.open_output_folder)
        header.addWidget(self.open_folder_button)
        content_layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("splitter")
        content_layout.addWidget(splitter, 1)

        left_panel = QFrame()
        left_panel.setObjectName("panel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(14)
        splitter.addWidget(left_panel)
        self._build_settings(left_layout)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        splitter.addWidget(right_panel)

        queue_frame = QFrame()
        queue_frame.setObjectName("panel")
        queue_inner = QVBoxLayout(queue_frame)
        queue_inner.setContentsMargins(18, 18, 18, 18)
        queue_inner.setSpacing(10)
        self._build_queue(queue_inner)
        right_layout.addWidget(queue_frame, 2)

        preview_frame = QFrame()
        preview_frame.setObjectName("panel")
        preview_inner = QVBoxLayout(preview_frame)
        preview_inner.setContentsMargins(18, 18, 18, 18)
        preview_inner.setSpacing(10)
        self._build_preview(preview_inner)
        right_layout.addWidget(preview_frame, 3)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        log_container = QFrame()
        log_container.setObjectName("panel")
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(14, 14, 14, 14)
        log_layout.setSpacing(6)
        self.log_title = QLabel()
        self.log_title.setObjectName("sectionTitle")
        log_layout.addWidget(self.log_title)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        log_layout.addWidget(self.log)
        bottom_row.addWidget(log_container, 1)

        hist_container = QFrame()
        hist_container.setObjectName("panel")
        hist_layout = QVBoxLayout(hist_container)
        hist_layout.setContentsMargins(14, 14, 14, 14)
        hist_layout.setSpacing(6)
        hist_header = QHBoxLayout()
        self.history_label = QLabel()
        self.history_label.setObjectName("sectionTitle")
        hist_header.addWidget(self.history_label)
        hist_header.addStretch(1)
        self.history_load_btn = QPushButton()
        self.history_load_btn.clicked.connect(self._load_selected_history)
        hist_header.addWidget(self.history_load_btn)
        self.history_clear_btn = QPushButton()
        self.history_clear_btn.clicked.connect(self._clear_history)
        hist_header.addWidget(self.history_clear_btn)
        hist_layout.addLayout(hist_header)
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(120)
        self.history_list.itemDoubleClicked.connect(self._load_selected_history)
        hist_layout.addWidget(self.history_list)
        bottom_row.addWidget(hist_container, 1)
        right_layout.addLayout(bottom_row, 2)

        splitter.setSizes([420, 780])

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)
        footer_layout.setSpacing(12)
        content_layout.addWidget(footer)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        footer_layout.addWidget(self.progress, 1)

        self.start_button = QPushButton()
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_jobs)
        footer_layout.addWidget(self.start_button)

        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_all)
        footer_layout.addWidget(self.cancel_button)

        self.burn_button = QPushButton()
        self.burn_button.setObjectName("burnButton")
        self.burn_button.clicked.connect(self.burn_subtitles)
        footer_layout.addWidget(self.burn_button)

    def _build_settings(self, layout: QVBoxLayout) -> None:
        self.settings_group = QGroupBox()
        settings_layout = QGridLayout(self.settings_group)
        settings_layout.setContentsMargins(14, 18, 14, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(12)
        layout.addWidget(self.settings_group)

        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        for key, display in MODES:
            self.mode_combo.addItem(display, key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        settings_layout.addWidget(self.mode_label, 0, 0)
        settings_layout.addWidget(self.mode_combo, 0, 1)

        self.format_label = QLabel()
        self.format_combo = QComboBox()
        self.format_combo.addItems(VIDEO_FILTERS.keys())
        settings_layout.addWidget(self.format_label, 1, 0)
        settings_layout.addWidget(self.format_combo, 1, 1)

        self.language_label = QLabel()
        self.language_combo = QComboBox()
        for name, code in LANGUAGES:
            label = name if not code else f"{name} ({code})"
            self.language_to_code[label] = code
            self.language_combo.addItem(label)
            if code == "en":
                self.language_combo.setCurrentText(label)
        self.language_combo.currentTextChanged.connect(self._toggle_custom_language)
        self.language_combo.currentTextChanged.connect(self.refresh_outputs)
        settings_layout.addWidget(self.language_label, 2, 0)
        settings_layout.addWidget(self.language_combo, 2, 1)

        self.custom_label = QLabel()
        self.custom_language = QLineEdit()
        self.custom_language.setPlaceholderText("e.g. en, zh, es")
        self.custom_language.textChanged.connect(self.refresh_outputs)
        settings_layout.addWidget(self.custom_label, 3, 0)
        settings_layout.addWidget(self.custom_language, 3, 1)

        self.model_label = QLabel()
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3", "turbo"])
        self.model_combo.setCurrentText("base")
        model_row.addWidget(self.model_combo, 1)
        self.model_hint = QLabel()
        self.model_hint.setObjectName("modelHint")
        model_row.addWidget(self.model_hint)
        settings_layout.addWidget(self.model_label, 4, 0)
        settings_layout.addLayout(model_row, 4, 1)

        self.output_label = QLabel()
        self.output_combo = QComboBox()
        self.output_combo.addItems(OUTPUT_FORMATS.keys())
        self.output_combo.currentTextChanged.connect(self.refresh_outputs)
        settings_layout.addWidget(self.output_label, 5, 0)
        settings_layout.addWidget(self.output_combo, 5, 1)

        self.folder_label = QLabel()
        self.output_dir = QLineEdit(str(APP_DIR / "outputs"))
        self.output_dir.textChanged.connect(self.refresh_outputs)
        self.output_browse_button = QToolButton()
        self.output_browse_button.setText("...")
        self.output_browse_button.clicked.connect(self.choose_output_dir)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(self.output_browse_button)
        settings_layout.addWidget(self.folder_label, 6, 0)
        settings_layout.addLayout(output_row, 6, 1)

        self.task_label = QLabel()
        task_box = QHBoxLayout()
        task_box.setContentsMargins(0, 0, 0, 0)
        self.task_group = QButtonGroup(self)
        self.transcribe_radio = QRadioButton()
        self.translate_radio = QRadioButton()
        self.transcribe_radio.setChecked(True)
        self.task_group.addButton(self.transcribe_radio)
        self.task_group.addButton(self.translate_radio)
        task_box.addWidget(self.transcribe_radio)
        task_box.addWidget(self.translate_radio)
        settings_layout.addWidget(self.task_label, 7, 0)
        settings_layout.addLayout(task_box, 7, 1)

        self.parallel_label = QLabel()
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.setValue(1)
        self.parallel_spin.valueChanged.connect(self._on_parallel_changed)
        settings_layout.addWidget(self.parallel_label, 8, 0)
        settings_layout.addWidget(self.parallel_spin, 8, 1)

        self._toggle_custom_language()
        self._on_mode_changed()

    def _build_queue(self, layout: QVBoxLayout) -> None:
        queue_header = QHBoxLayout()
        self.queue_label = QLabel()
        self.queue_label.setObjectName("sectionTitle")
        queue_header.addWidget(self.queue_label)
        queue_header.addStretch(1)

        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(self.remove_selected)
        queue_header.addWidget(self.remove_button)

        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear_queue)
        queue_header.addWidget(self.clear_button)
        layout.addLayout(queue_header)

        self.table = QTableWidget(0, 5)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.preview_selected_output)
        layout.addWidget(self.table, 1)

    def _build_preview(self, layout: QVBoxLayout) -> None:
        title_row = QHBoxLayout()
        self.preview_title = QLabel()
        self.preview_title.setObjectName("sectionTitle")
        title_row.addWidget(self.preview_title)
        title_row.addStretch(1)
        self.save_preview_btn = QPushButton()
        self.save_preview_btn.clicked.connect(self._save_preview)
        title_row.addWidget(self.save_preview_btn)
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.copy_preview)
        title_row.addWidget(self.copy_button)
        layout.addLayout(title_row)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(False)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.preview, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI", "Microsoft YaHei UI";
                font-size: 13px;
                color: #142033;
            }
            #sidebar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a2332, stop:1 #0d1117);
                border-right: 1px solid #0d1117;
            }
            #appTitle {
                color: #e6edf3;
                font-size: 28px;
                font-weight: 800;
                line-height: 1.05;
            }
            #appSubtitle {
                color: #8b949e;
                font-size: 13px;
                line-height: 1.35;
            }
            #langIcon {
                font-size: 16px;
                color: #8b949e;
            }
            #langToggle {
                background: #21262d;
                color: #58a6ff;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 700;
            }
            #langToggle:hover {
                background: #30363d;
                border-color: #58a6ff;
            }
            #statusBadge {
                color: #e6edf3;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #238636, stop:1 #2ea043);
                border-radius: 16px;
                padding: 9px 12px;
                font-weight: 700;
            }
            #content {
                background: #f6f8fa;
            }
            #pageTitle {
                font-size: 24px;
                font-weight: 800;
                color: #0d1117;
            }
            #pageCaption {
                color: #656d76;
                font-size: 13px;
            }
            #panel {
                background: white;
                border: 1px solid #d0d7de;
                border-radius: 14px;
            }
            #footer {
                background: white;
                border: 1px solid #d0d7de;
                border-radius: 14px;
            }
            #sectionTitle {
                font-size: 15px;
                font-weight: 800;
                color: #0d1117;
            }
            #modelHint {
                color: #656d76;
                font-size: 11px;
                font-style: italic;
            }
            QGroupBox {
                border: 1px solid #d0d7de;
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: 800;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #24292f;
            }
            QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 8px;
                selection-background-color: #b6d4fe;
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {
                border-color: #58a6ff;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #656d76;
                margin-right: 4px;
            }
            QPlainTextEdit {
                font-family: "Cascadia Mono", Consolas, monospace;
                line-height: 1.4;
            }
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 10px;
                gridline-color: #e8ecf0;
            }
            QTableWidget::item:selected {
                background: #ddf4ff;
                color: #0d1117;
            }
            QHeaderView::section {
                background: #f6f8fa;
                color: #24292f;
                border: none;
                border-bottom: 1px solid #d0d7de;
                padding: 8px;
                font-weight: 700;
            }
            QListWidget#runtimeList, QListWidget {
                background: #161b22;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 12px;
                padding: 6px;
            }
            QListWidget#runtimeList::item, QListWidget::item {
                padding: 3px 6px;
                border-radius: 4px;
            }
            QListWidget#runtimeList::item:hover, QListWidget::item:hover {
                background: #21262d;
            }
            QPushButton {
                background: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 9px;
                padding: 9px 13px;
                color: #24292f;
                font-weight: 650;
            }
            QPushButton:hover {
                background: #e8ecf0;
                border-color: #afb8c1;
            }
            QPushButton:pressed {
                background: #d0d7de;
            }
            QPushButton:disabled {
                color: #8c959f;
                background: #f6f8fa;
                border-color: #e8ecf0;
            }
            QPushButton#primaryButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2f81f7, stop:1 #1f6feb);
                color: white;
                border: 1px solid #1a73e8;
            }
            QPushButton#primaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4c9aff, stop:1 #2f81f7);
            }
            QPushButton#primaryButton:pressed {
                background: #1a5cc7;
            }
            QPushButton#primaryButton:disabled {
                background: #94b8e8;
                border-color: #8aacdb;
            }
            QPushButton#burnButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #da3633, stop:1 #b62324);
                color: white;
                border: 1px solid #a11d1e;
            }
            QPushButton#burnButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f47067, stop:1 #da3633);
            }
            QProgressBar {
                border: 1px solid #d0d7de;
                border-radius: 9px;
                text-align: center;
                background: #f6f8fa;
                height: 22px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2f81f7, stop:1 #58a6ff);
                border-radius: 8px;
            }
            QRadioButton {
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QSplitter::handle {
                background: transparent;
                width: 8px;
            }
            """
        )

    def _toggle_language(self) -> None:
        self.ui_lang = "en" if self.ui_lang == "zh" else "zh"
        self._retranslate()

    def _retranslate(self) -> None:
        s = STRINGS[self.ui_lang]
        self.setWindowTitle("Video Text Extractor")
        self.title_label.setText(s["title"])
        self.subtitle_label.setText(s["subtitle"])
        self.lang_toggle.setText(s["lang_toggle"])
        self.add_button.setText(f"➕ {s['add_videos']}")
        self.status_badge.setText(self._batch_status_text(s))
        self.heading_label.setText(s["page_title"])
        self.caption_label.setText(s["page_caption"])
        self.open_folder_button.setText(f"\U0001f4c2 {s['open_folder']}")
        self.settings_group.setTitle(s["settings"])
        self.mode_label.setText(s["mode"])
        self.format_label.setText(s["video_format"])
        self.language_label.setText(s["language"])
        self.custom_label.setText(s["custom_code"])
        self.model_label.setText(s["model"])
        self.output_label.setText(s["output"])
        self.folder_label.setText(s["output_folder"])
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
        self.copy_button.setText(f"\U0001f4cb {s['copy_preview']}")
        self.save_preview_btn.setText(f"\U0001f4be {s['save_preview']}")
        self.preview.setPlaceholderText(s["preview_placeholder"])
        self.log_title.setText(s["log"])
        self.start_button.setText(f"▶ {s['start']}")
        self.cancel_button.setText(s["cancel"])
        self.burn_button.setText(f"\U0001f525 {s['burn_sub']}")
        self.history_label.setText(s["history"])
        self.history_load_btn.setText(s["history_load"])
        self.history_clear_btn.setText(s["history_clear"])
        self._refresh_history_list()
        self._refresh_runtime()

    def _batch_status_text(self, strings: dict[str, str]) -> str:
        statuses = {job.status for job in self.jobs}
        if self.active_processes or STATUS_RUNNING in statuses:
            return strings["running_status"]
        if STATUS_FAILED in statuses:
            return strings["failed_status"]
        if STATUS_CANCELLED in statuses:
            return strings["cancelled_status"]
        if statuses and statuses <= {STATUS_DONE}:
            return strings["done_status"]
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

        status = detect_tools()
        s = STRINGS[self.ui_lang]
        rows = [
            (f"⚙ {s['local_whisper']}", status.local_whisper),
            (f"\U0001f3a5 ffmpeg", bool(ffmpeg_command(status))),
            ("🔎 Tesseract OCR", bool(status.tesseract)),
            (f"\U0001f511 {s['openai_key']}", status.openai_key),
            (f"\U0001f7e2 {s['gpu']}", status.cuda_gpu),
        ]
        self.runtime_list.clear()
        for label, ok in rows:
            text = f"{'  ✓' if ok else '  ✗'}  {label}"
            item = QListWidgetItem(text)
            if ok:
                item.setForeground(QColor("#3fb950"))
            else:
                item.setForeground(QColor("#f0883e"))
            self.runtime_list.addItem(item)

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        uses_whisper_settings = mode in {"whisper", "auto"}
        has_output_format = mode not in {"subtitle", "ocr"}
        self.model_label.setVisible(uses_whisper_settings)
        self.model_combo.setVisible(uses_whisper_settings)
        self.model_hint.setVisible(uses_whisper_settings)
        self.task_label.setVisible(uses_whisper_settings)
        self.transcribe_radio.setVisible(uses_whisper_settings)
        self.translate_radio.setVisible(uses_whisper_settings)
        self.language_label.setVisible(mode != "subtitle")
        self.language_combo.setVisible(mode != "subtitle")
        self._toggle_custom_language()
        self.output_label.setVisible(has_output_format)
        self.output_combo.setVisible(has_output_format)
        self.parallel_label.setVisible(uses_whisper_settings)
        self.parallel_spin.setVisible(uses_whisper_settings)
        self.refresh_outputs()

    def _on_parallel_changed(self, value: int) -> None:
        self.max_parallel = value

    def _toggle_custom_language(self) -> None:
        mode = self.mode_combo.currentData()
        is_custom = self.language_to_code.get(self.language_combo.currentText()) == "custom"
        visible = is_custom and mode != "subtitle"
        self.custom_label.setVisible(visible)
        self.custom_language.setVisible(visible)

    def _update_model_hint(self, video_path: Path) -> None:
        duration = get_video_duration(video_path)
        suggested = suggest_model(duration)
        s = STRINGS[self.ui_lang]
        if duration > 0:
            mins = int(duration // 60)
            secs = int(duration % 60)
            self.model_hint.setText(f"{mins}:{secs:02d} → {s['suggest_model'].format(suggested)}")
        else:
            self.model_hint.setText(s["suggest_model"].format(suggested))

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
        paths, _ = QFileDialog.getOpenFileNames(self, s["add_videos"], str(APP_DIR), filters)
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
        if any(job.video == path for job in self.jobs):
            return
        mode = self.mode_combo.currentData()
        self.jobs.append(Job(video=path, output=self.output_path_for(path), mode=mode))
        self.refresh_table()
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

    def refresh_outputs(self) -> None:
        mode = self.mode_combo.currentData()
        for job in self.jobs:
            job.mode = mode
            job.output = self.output_path_for(job.video)
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
        fmt, suffix = OUTPUT_FORMATS[self.output_combo.currentText()]
        language = self.language_code() or "auto"
        return output_dir / f"{video.stem}_transcript_{safe_part(language)}{suffix}"

    def language_code(self) -> str | None:
        code = self.language_to_code.get(self.language_combo.currentText(), "")
        if code == "custom":
            return self.custom_language.text().strip() or None
        return code or None

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.jobs))
        for row, job in enumerate(self.jobs):
            # Thumbnail column
            thumb = get_video_thumbnail(job.video)
            thumb_item = QTableWidgetItem()
            if thumb:
                thumb_item.setIcon(QIcon(thumb.scaled(64, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            thumb_item.setFlags(thumb_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, thumb_item)
            # Data columns
            values = [job.video.name, file_size(job.video), str(job.output), self._status_text(job.status)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in {1, 3}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col + 1, item)
        if hasattr(self, "status_badge"):
            self.status_badge.setText(self._batch_status_text(STRINGS[self.ui_lang]))

    def preview_selected_output(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        job = self.jobs[rows[0]]
        if job.output.exists():
            self.preview.setPlainText(job.output.read_text(encoding="utf-8", errors="replace"))
        else:
            s = STRINGS[self.ui_lang]
            self.preview.setPlainText(s["output_will_be"].format(job.output))

    def command_for(self, job: Job) -> list[str]:
        mode = job.mode
        fmt, _suffix = OUTPUT_FORMATS[self.output_combo.currentText()]
        if mode == "subtitle":
            fmt = "srt"
        elif mode == "ocr":
            fmt = "text"
        command = [
            python_console_executable(), "-u", str(EXTRACTOR),
            str(job.video),
            "--mode", mode,
            "--format", fmt,
            "-o", str(job.output),
        ]
        if mode in {"whisper", "auto"}:
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
        return command

    # --- Parallel job execution ---

    def start_jobs(self) -> None:
        s = STRINGS[self.ui_lang]
        if not self.jobs:
            QMessageBox.information(self, s["queue_empty"], s["queue_empty_msg"])
            return
        try:
            self.output_directory().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, s["missing_file"], str(exc))
            return
        self.refresh_outputs()
        self.process_generation += 1
        self._clear_process_queues()
        for job in self.jobs:
            job.status = STATUS_WAITING
        self.log.clear()
        self.preview.clear()
        self.progress.setRange(0, 0)
        self.status_badge.setText(s["running_status"])
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._set_editing_enabled(False)
        self.refresh_table()
        self._save_history_entry()
        self._fill_parallel_slots()

    def _fill_parallel_slots(self) -> None:
        while len(self.active_processes) < self.max_parallel:
            idx = self._next_waiting_index()
            if idx is None:
                break
            self._start_job(idx)

    def _next_waiting_index(self) -> int | None:
        for i, job in enumerate(self.jobs):
            if job.status == STATUS_WAITING:
                return i
        return None

    def _start_job(self, index: int) -> None:
        job = self.jobs[index]
        job.status = STATUS_RUNNING
        self.refresh_table()
        self.table.selectRow(index)
        s = STRINGS[self.ui_lang]
        self.append_log(f"\n{s['starting'].format(job.video.name)}\n")

        command = self.command_for(job)
        generation = self.process_generation
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=str(APP_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._job_start_failed(index, str(exc))
            return

        self.active_processes[index] = process
        threading.Thread(target=self._read_process_stream, args=(generation, index, process), daemon=True).start()
        self.process_pump.start()

    def _read_process_stream(self, generation: int, index: int, process: subprocess.Popen[str]) -> None:
        exit_code = 1
        try:
            if process.stdout is not None:
                for text in process.stdout:
                    self.process_outputs.put((generation, index, text))
            exit_code = process.wait()
        except Exception as exc:
            self.process_outputs.put((generation, index, f"Process error: {exc}\n"))
            polled = process.poll()
            exit_code = 1 if polled is None else polled
        self.process_finishes.put((generation, index, exit_code))

    def _drain_process_events(self) -> None:
        while True:
            try:
                generation, _index, text = self.process_outputs.get_nowait()
            except queue.Empty:
                break
            if generation != self.process_generation:
                continue
            self.append_log(text)
            self._parse_progress(text)

        while True:
            try:
                generation, index, exit_code = self.process_finishes.get_nowait()
            except queue.Empty:
                break
            if generation != self.process_generation:
                continue
            self._job_finished(index, exit_code)

        if not self.active_processes:
            self.process_pump.stop()

    def _parse_progress(self, text: str) -> None:
        match = re.search(r"(\d+)%\|.*?(\d+)/(\d+)", text)
        if match:
            pct = int(match.group(1))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)

    def _job_finished(self, index: int, exit_code: int) -> None:
        if index is None or index not in self.active_processes or index >= len(self.jobs):
            return
        del self.active_processes[index]

        job = self.jobs[index]
        s = STRINGS[self.ui_lang]
        if exit_code == 0:
            job.status = STATUS_DONE
            self.append_log(f"{s['saved'].format(job.output)}\n")
            if job.output.exists():
                self.preview.setPlainText(job.output.read_text(encoding="utf-8", errors="replace"))
        else:
            job.status = STATUS_FAILED
            self.append_log(f"{s['failed_code'].format(exit_code)}\n")
        self.refresh_table()

        self._fill_parallel_slots()
        if not self.active_processes and self._next_waiting_index() is None:
            self.finish_batch()

    def _job_start_failed(self, index: int, message: str) -> None:
        if index >= len(self.jobs):
            return
        self.jobs[index].status = STATUS_FAILED
        self.append_log(f"Process error: {message}\n")
        self.refresh_table()
        self._fill_parallel_slots()
        if not self.active_processes and self._next_waiting_index() is None:
            self.finish_batch()

    def finish_batch(self) -> None:
        s = STRINGS[self.ui_lang]
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_badge.setText(s["failed_status"] if any(job.status == STATUS_FAILED for job in self.jobs) else self._batch_status_text(s))
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_editing_enabled(True)

    def cancel_all(self) -> None:
        for process in self.active_processes.values():
            if process.poll() is None:
                process.kill()
        self.active_processes.clear()
        self.process_generation += 1
        self._clear_process_queues()
        self.process_pump.stop()
        s = STRINGS[self.ui_lang]
        for job in self.jobs:
            if job.status in {STATUS_WAITING, STATUS_RUNNING}:
                job.status = STATUS_CANCELLED
        self.refresh_table()
        self.finish_batch()
        self.status_badge.setText(s["cancelled_status"])

    def closeEvent(self, event) -> None:
        if self.active_processes:
            self.cancel_all()
        super().closeEvent(event)

    def _clear_process_queues(self) -> None:
        for events in (self.process_outputs, self.process_finishes):
            while True:
                try:
                    events.get_nowait()
                except queue.Empty:
                    break

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.history_load_btn,
            self.history_clear_btn,
            self.mode_combo,
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
            self.burn_button,
            self.save_preview_btn,
        ):
            widget.setEnabled(enabled)

    # --- Progress & log ---

    def append_log(self, text: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)

    def copy_preview(self) -> None:
        QApplication.clipboard().setText(self.preview.toPlainText())

    def _save_preview(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        job = self.jobs[rows[0]]
        text = self.preview.toPlainText()
        job.output.parent.mkdir(parents=True, exist_ok=True)
        job.output.write_text(text, encoding="utf-8")
        self.append_log(f"Preview saved: {job.output}\n")

    def open_output_folder(self) -> None:
        path = self.output_directory()
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

    # --- Burn subtitles ---

    def burn_subtitles(self) -> None:
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

        video_p = Path(video_path)
        output_path = video_p.parent / f"{video_p.stem}_subtitled.mp4"

        self.append_log(f"\nBurning subtitles: {video_p.name}\n")
        try:
            with local_temp_dir(output_path.parent, "burn_subtitle_") as temp_dir:
                temp_srt = temp_dir / "subtitle.srt"
                shutil.copy2(srt_path, temp_srt)
                cmd = [
                    ffmpeg, "-y",
                    "-i", video_path,
                    "-vf", f"subtitles='{self._ffmpeg_filter_path(str(temp_srt))}'",
                    "-c:a", "copy",
                    str(output_path),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                self.append_log(f"{s['burn_done'].format(output_path)}\n")
                QMessageBox.information(self, s["burn_title"], s["burn_done"].format(output_path))
            else:
                self.append_log(f"ffmpeg error: {result.stderr[-500:]}\n")
        except Exception as e:
            self.append_log(f"Error: {e}\n")

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
        self.refresh_table()

    def _restore_history_settings(self, entry: dict) -> None:
        self._set_combo_data(self.mode_combo, entry.get("mode", "whisper"))
        self.model_combo.setCurrentText(entry.get("model", "base"))
        self._set_combo_text(self.output_combo, entry.get("format", "TXT"))
        self._set_language_code(entry.get("language", "auto"))
        self.translate_radio.setChecked(bool(entry.get("translate", False)))
        self.transcribe_radio.setChecked(not self.translate_radio.isChecked())
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
    app.setFont(QFont("Segoe UI", 10))
    window = VideoTextWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
