from __future__ import annotations

import json
import os
import hashlib
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QProcess
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase, QIcon, QImage, QPixmap
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
    QScrollArea,
    QTabWidget,
    QStyle,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from review_player import AudioReviewPlayer, TranscriptEdit, tool_icon
from transcription_support import review_path, reading_copy

APP_DIR = Path(__file__).resolve().parent
EXTRACTOR = APP_DIR / "video_text_extractor.py"
HISTORY_FILE = APP_DIR / ".transcribe_history.json"

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wmv", ".flv",
    ".mpg", ".mpeg", ".3gp", ".ts", ".mts", ".m2ts", ".ogv",
    ".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma",
}

VIDEO_FILTERS = {
    "All supported": "*.mp4 *.mov *.mkv *.webm *.m4v *.avi *.wmv *.flv *.mpg *.mpeg *.3gp *.ts *.mts *.m2ts *.ogv *.m4a *.mp3 *.wav *.flac *.aac *.ogg *.opus *.wma",
    "Audio": "*.m4a *.mp3 *.wav *.flac *.aac *.ogg *.opus *.wma",
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
    ("sensevoice", "Chinese cross-check"),
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
        "advanced": "高级设置",
        "enhance": "轻度人声增强",
        "enhance_tip": "轻度降噪和平衡音量。会改变音色，可关闭后对比。",
        "terms": "专业术语",
        "terms_hint": "填写录音中确实出现的术语，以逗号分隔",
        "channel": "声道",
        "channel_mix": "混合",
        "channel_left": "左声道",
        "channel_right": "右声道",
        "reading_copy": "导出无时间戳副本，保留原词句",
        "details": "日志与历史",
        "review_tip": "根据模型置信信号提示，需回听确认；未标注的内容也可能有误。",
        "review_count": "待核对 {}",
        "model_size": "首次使用未缓存模型约下载 {}",
        "model_cached": "模型已缓存，可离线转写",
        "stage_decode": "准备音频",
        "stage_model": "加载模型",
        "stage_transcribe": "识别中",
        "stage_export": "保存转写",
        "mode_whisper": "本地语音转写",
        "mode_sensevoice": "中文交叉校对 · SenseVoice",
        "mode_audio": "云端语音转写",
        "mode_subtitle": "提取内嵌字幕",
        "mode_ocr": "识别画面文字",
        "mode_auto": "自动选择",
        "title": "音视频转写",
        "subtitle": "TRANSCRIPTION STUDIO",
        "ready": "就绪",
        "missing": "缺失",
        "local_whisper": "本地 Whisper",
        "openai_key": "OpenAI 密钥",
        "add_videos": "添加音视频",
        "status_ready": "就绪",
        "status_running": "运行中",
        "status_done": "完成",
        "status_cancelled": "已取消",
        "waiting_status": "等待中",
        "page_title": "转写与校对",
        "page_caption": "音频 · 视频 · 字幕",
        "open_folder": "打开输出目录",
        "settings": "设置",
        "mode": "模式",
        "video_format": "文件类型",
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
        "col_video": "文件",
        "col_size": "大小",
        "col_output": "输出",
        "col_status": "状态",
        "preview": "转写稿",
        "copy_preview": "复制预览",
        "preview_placeholder": "转写完成后将在此显示。",
        "log": "日志",
        "start": "开始",
        "cancel": "取消",
        "skip": "跳过当前",
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
        "advanced": "Advanced settings",
        "enhance": "Gentle voice enhancement",
        "enhance_tip": "Light denoising and volume balancing; compare with enhancement disabled.",
        "terms": "Terminology",
        "terms_hint": "Terms actually spoken, separated by commas",
        "channel": "Channel",
        "channel_mix": "Mix",
        "channel_left": "Left",
        "channel_right": "Right",
        "reading_copy": "Export a copy without timestamps; keep original wording",
        "details": "Logs and history",
        "review_tip": "Model signals suggest manual review; unflagged text can also be wrong.",
        "review_count": "Review {}",
        "model_size": "Uncached model downloads about {} on first use",
        "model_cached": "Model cached · available offline",
        "stage_decode": "Preparing audio",
        "stage_model": "Loading model",
        "stage_transcribe": "Transcribing",
        "stage_export": "Saving transcript",
        "mode_whisper": "Local transcription",
        "mode_sensevoice": "Chinese cross-check · SenseVoice",
        "mode_audio": "Cloud transcription",
        "mode_subtitle": "Embedded subtitles",
        "mode_ocr": "Visual text",
        "mode_auto": "Automatic",
        "title": "Transcription",
        "subtitle": "TRANSCRIPTION STUDIO",
        "ready": "Ready",
        "missing": "Missing",
        "local_whisper": "Local Whisper",
        "openai_key": "OpenAI key",
        "add_videos": "Add media",
        "status_ready": "Ready",
        "status_running": "Running",
        "status_done": "Done",
        "status_cancelled": "Cancelled",
        "waiting_status": "Waiting",
        "page_title": "Transcription Workspace",
        "page_caption": "Audio · Video · Subtitles",
        "open_folder": "Open output folder",
        "settings": "Settings",
        "mode": "Mode",
        "video_format": "File type",
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
        "col_video": "File",
        "browse": "Choose output folder",
        "col_size": "Size",
        "col_output": "Output",
        "col_status": "Status",
        "preview": "Preview",
        "copy_preview": "Copy preview",
        "preview_placeholder": "Completed transcript appears here.",
        "log": "Log",
        "start": "Start",
        "cancel": "Cancel",
        "skip": "Skip current",
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
    stage: str = ""
    progress: int | None = None


def safe_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("._") or "auto"


def file_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "—"
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.2f} GB"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024:.1f} KB"


THUMB_CACHE: dict[Path, QPixmap | None] = {}


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
    if path.suffix.lower() in {".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma"}:
        return None
    THUMB_CACHE[path] = None
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
        self.setWindowTitle("音视频转写 · 校对工作台")
        self.resize(1380, 880)
        self.setMinimumSize(980, 680)
        self.setAcceptDrops(True)

        self.preview_path: Path | None = None
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
        sidebar.setFixedWidth(304)
        outer.addWidget(sidebar)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 24, 20, 16)
        side.setSpacing(16)
        brand = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("appTitle")
        brand.addWidget(self.title_label, 1)
        self.lang_toggle = QPushButton()
        self.lang_toggle.setFixedWidth(48)
        self.lang_toggle.clicked.connect(self._toggle_language)
        brand.addWidget(self.lang_toggle)
        side.addLayout(brand)
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("appSubtitle")
        side.addWidget(self.subtitle_label)
        self.add_button = QPushButton()
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self.add_videos)
        side.addWidget(self.add_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 2, 0)
        self._build_settings(settings_layout)
        settings_layout.addStretch()
        scroll.setWidget(settings)
        side.addWidget(scroll, 1)
        self.runtime_list = QListWidget()
        self.runtime_list.setObjectName("runtimeList")
        self.runtime_list.setFixedHeight(135)
        self.advanced_layout.addWidget(self.runtime_list)
        self.status_badge = QLabel()
        self.status_badge.setObjectName("statusBadge")
        side.addWidget(self.status_badge)

        content = QFrame()
        content.setObjectName("content")
        outer.addWidget(content, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(16)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.heading_label = QLabel()
        self.heading_label.setObjectName("pageTitle")
        titles.addWidget(self.heading_label)
        self.caption_label = QLabel()
        self.caption_label.setObjectName("pageCaption")
        titles.addWidget(self.caption_label)
        header.addLayout(titles, 1)
        self.open_folder_button = QPushButton()
        self.open_folder_button.clicked.connect(self.open_output_folder)
        header.addWidget(self.open_folder_button)
        layout.addLayout(header)

        self.media_player = AudioReviewPlayer(self)
        layout.addWidget(self.media_player)
        workspace = QSplitter(Qt.Vertical)
        queue = QWidget()
        queue_layout = QVBoxLayout(queue)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        self._build_queue(queue_layout)
        queue.setMaximumHeight(180)
        workspace.addWidget(queue)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self._build_preview(editor_layout)
        workspace.addWidget(editor)
        workspace.setSizes([125, 500])
        layout.addWidget(workspace, 1)

        self.details_tabs = QTabWidget()
        self.details_tabs.setMaximumHeight(170)
        logs = QWidget()
        logs_layout = QVBoxLayout(logs)
        logs_layout.setContentsMargins(0, 8, 0, 0)
        self.log_title = QLabel()
        self.log_title.hide()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        logs_layout.addWidget(self.log)
        self.details_tabs.addTab(logs, "")
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        self.history_label = QLabel()
        row.addWidget(self.history_label, 1)
        self.history_load_btn = QPushButton()
        self.history_load_btn.clicked.connect(self._load_selected_history)
        row.addWidget(self.history_load_btn)
        self.history_clear_btn = QPushButton()
        self.history_clear_btn.clicked.connect(self._clear_history)
        row.addWidget(self.history_clear_btn)
        history_layout.addLayout(row)
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self._load_selected_history)
        history_layout.addWidget(self.history_list)
        self.details_tabs.addTab(history, "")
        self.details_tabs.setVisible(False)
        layout.addWidget(self.details_tabs)

        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        footer.addWidget(self.progress, 1)
        self.start_button = QPushButton()
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_jobs)
        footer.addWidget(self.start_button)
        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_all)
        footer.addWidget(self.cancel_button)
        self.skip_button = QPushButton()
        self.skip_button.setEnabled(False)
        self.skip_button.setVisible(False)
        self.skip_button.clicked.connect(self.skip_current)
        footer.addWidget(self.skip_button)
        self.burn_button = QPushButton()
        self.burn_button.clicked.connect(self.burn_subtitles)
        footer.addWidget(self.burn_button)
        self.details_button = QToolButton()
        self.details_button.setCheckable(True)
        self.details_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.details_button.toggled.connect(self.details_tabs.setVisible)
        footer.addWidget(self.details_button)
        layout.addLayout(footer)
        icons = {
            self.add_button: QStyle.SP_FileDialogNewFolder,
            self.start_button: QStyle.SP_MediaPlay,
            self.cancel_button: QStyle.SP_MediaStop,
            self.skip_button: QStyle.SP_MediaSkipForward,
            self.open_folder_button: QStyle.SP_DirOpenIcon,
            self.output_browse_button: QStyle.SP_DirOpenIcon,
            self.save_preview_btn: QStyle.SP_DialogSaveButton,
            self.copy_button: QStyle.SP_FileIcon,
            self.remove_button: QStyle.SP_TrashIcon,
            self.clear_button: QStyle.SP_DialogResetButton,
        }
        for button, icon in icons.items():
            color = "#ffffff" if button in (self.add_button, self.start_button) else "#356b5a"
            button.setIcon(tool_icon(self.style(), icon, color))

    def _build_settings(self, layout: QVBoxLayout) -> None:
        self.settings_group = QGroupBox()
        form = QVBoxLayout(self.settings_group)
        form.setContentsMargins(0, 12, 0, 0)
        form.setSpacing(8)
        layout.addWidget(self.settings_group)
        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        for key, display in MODES:
            self.mode_combo.addItem(display, key)
        form.addWidget(self.mode_label)
        form.addWidget(self.mode_combo)
        grid = QGridLayout()
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        for name, code in LANGUAGES:
            label = name if not code else f"{name} ({code})"
            self.language_to_code[label] = code
            self.language_combo.addItem(label)
        self.model_label = QLabel()
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3", "turbo"])
        self.model_combo.setCurrentText("small")
        grid.addWidget(self.language_label, 0, 0)
        grid.addWidget(self.model_label, 0, 1)
        grid.addWidget(self.language_combo, 1, 0)
        grid.addWidget(self.model_combo, 1, 1)
        self.output_label = QLabel()
        self.output_combo = QComboBox()
        self.output_combo.addItems(OUTPUT_FORMATS)
        self.channel_label = QLabel()
        self.channel_combo = QComboBox()
        for code in ("mix", "left", "right"):
            self.channel_combo.addItem(code, code)
        grid.addWidget(self.output_label, 2, 0)
        grid.addWidget(self.channel_label, 2, 1)
        grid.addWidget(self.output_combo, 3, 0)
        grid.addWidget(self.channel_combo, 3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        form.addLayout(grid)
        self.model_hint = QLabel()
        self.model_hint.setWordWrap(True)
        self.model_hint.setObjectName("modelHint")
        form.addWidget(self.model_hint)
        self.enhance_check = QCheckBox()
        form.addWidget(self.enhance_check)
        self.terms_label = QLabel()
        form.addWidget(self.terms_label)
        self.terms_edit = QPlainTextEdit()
        self.terms_edit.setFixedHeight(70)
        form.addWidget(self.terms_edit)
        self.custom_label = QLabel()
        self.custom_language = QLineEdit()
        form.addWidget(self.custom_label)
        form.addWidget(self.custom_language)
        self.advanced_button = QToolButton()
        self.advanced_button.setCheckable(True)
        self.advanced_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_button.setArrowType(Qt.RightArrow)
        form.addWidget(self.advanced_button)
        self.advanced_widget = QWidget()
        self.advanced_layout = QVBoxLayout(self.advanced_widget)
        self.advanced_layout.setContentsMargins(0, 4, 0, 0)
        self.format_label = QLabel()
        self.format_combo = QComboBox()
        self.format_combo.addItems(VIDEO_FILTERS)
        self.advanced_layout.addWidget(self.format_label)
        self.advanced_layout.addWidget(self.format_combo)
        self.folder_label = QLabel()
        self.output_dir = QLineEdit(str(APP_DIR / "outputs"))
        self.output_browse_button = QToolButton()
        self.output_browse_button.clicked.connect(self.choose_output_dir)
        folder = QHBoxLayout()
        folder.addWidget(self.output_dir, 1)
        folder.addWidget(self.output_browse_button)
        self.advanced_layout.addWidget(self.folder_label)
        self.advanced_layout.addLayout(folder)
        from model_storage import model_root
        self.model_location_label = QLabel()
        self.model_location = QLineEdit(str(model_root()))
        self.model_location.setReadOnly(True)
        self.model_location.setToolTip(str(model_root()))
        self.advanced_layout.addWidget(self.model_location_label)
        self.advanced_layout.addWidget(self.model_location)
        self.task_label = QLabel()
        self.transcribe_radio = QRadioButton()
        self.translate_radio = QRadioButton()
        self.transcribe_radio.setChecked(True)
        self.task_group = QButtonGroup(self)
        self.task_group.addButton(self.transcribe_radio)
        self.task_group.addButton(self.translate_radio)
        tasks = QHBoxLayout()
        tasks.addWidget(self.transcribe_radio)
        tasks.addWidget(self.translate_radio)
        self.advanced_layout.addWidget(self.task_label)
        self.advanced_layout.addLayout(tasks)
        self.parallel_label = QLabel()
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.valueChanged.connect(self._on_parallel_changed)
        self.advanced_layout.addWidget(self.parallel_label)
        self.advanced_layout.addWidget(self.parallel_spin)
        form.addWidget(self.advanced_widget)
        self.advanced_widget.hide()
        self.advanced_button.toggled.connect(self.advanced_widget.setVisible)
        self.advanced_button.toggled.connect(lambda checked: self.advanced_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.language_combo.currentTextChanged.connect(self._toggle_custom_language)
        self.language_combo.currentTextChanged.connect(self.refresh_outputs)
        self.custom_language.textChanged.connect(self.refresh_outputs)
        self.output_combo.currentTextChanged.connect(self.refresh_outputs)
        self.output_dir.textChanged.connect(self.refresh_outputs)
        self.model_combo.currentTextChanged.connect(self._update_model_hint)
        self._toggle_custom_language()
        self._on_mode_changed()
        for combo in self.settings_group.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(4)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
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

        self.review_button = QPushButton()
        self.review_button.setCheckable(True)
        title_row.addWidget(self.review_button)
        self.reading_button = QToolButton()
        self.reading_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.reading_button.clicked.connect(self.export_reading_copy)
        title_row.addWidget(self.reading_button)
        self.review_list = QListWidget()
        self.review_list.setObjectName("reviewList")
        self.review_list.setMaximumHeight(120)
        self.review_list.itemClicked.connect(self._seek_review_item)
        self.review_button.toggled.connect(self.review_list.setVisible)
        layout.addWidget(self.review_list)
        self.review_list.hide()
        self.preview = TranscriptEdit()
        self.preview.setObjectName("transcriptEditor")
        self.preview.setReadOnly(True)
        self.preview.seekRequested.connect(self.media_player.seek)
        self.save_preview_btn.setEnabled(False)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.preview, 1)

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
        self.enhance_check.setToolTip(self.tr("enhance_tip"))
        self.terms_label.setText(self.tr("terms"))
        self.terms_edit.setPlaceholderText(self.tr("terms_hint"))
        self.channel_label.setText(self.tr("channel"))
        for index, code in enumerate(("mix", "left", "right")):
            self.channel_combo.setItemText(index, self.tr("channel_" + code))
        self.reading_button.setToolTip(self.tr("reading_copy"))
        self.details_button.setToolTip(self.tr("details"))
        self.review_button.setToolTip(self.tr("review_tip"))
        for index, (key, _display) in enumerate(MODES):
            self.mode_combo.setItemText(index, self.tr("mode_" + key))
        self._update_model_hint()
        self.refresh_table()

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

    def refresh_outputs(self) -> None:
        mode = self.mode_combo.currentData()
        used: set[Path] = set()
        for job in self.jobs:
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
                if col in {1, 3}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col + 1, item)
        if 0 <= selected < len(self.jobs):
            self.table.selectRow(selected)
        self.table.blockSignals(False)
        self.preview_selected_output()
        if hasattr(self, "status_badge"):
            self.status_badge.setText(self._batch_status_text(STRINGS[self.ui_lang]))

    def preview_selected_output(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        job = self.jobs[rows[0]] if rows and rows[0] < len(self.jobs) else None
        target = job.output if job else None
        self.media_player.set_source(job.video if job else None)
        self._load_review(target, job.video if job else None)
        # Preserve unsaved edits per output while switching tasks or refreshing rows.
        if not hasattr(self, "_drafts"):
            self._drafts: dict[Path, str] = {}
        if self.preview_path is not None and self.preview.document().isModified():
            self._drafts[self.preview_path] = self.preview.toPlainText()
        self.preview_path = None
        self.preview.clear()
        editable = target is not None and target.is_file() and not self.active_processes
        self.preview.setReadOnly(not editable)
        self.save_preview_btn.setEnabled(editable)
        if target is not None and target.is_file():
            try:
                text = self._drafts.get(target)
                if text is None:
                    text = target.read_text(encoding="utf-8", errors="replace")
                self.preview.setPlainText(text)
                self.preview_path = target
                self.preview.document().setModified(target in self._drafts)
            except OSError as exc:
                self.append_log(f"Preview error: {exc}\n")
        elif target is not None:
            self.preview.setPlaceholderText(self.tr("output_will_be").format(target))
        else:
            self.preview.setPlaceholderText(self.tr("preview_placeholder"))

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
        try:
            self.output_directory().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, s["missing_file"], str(exc))
            return
        self.refresh_outputs()
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
        while len(self.active_processes) < self.max_parallel:
            idx = self._next_waiting_index()
            if idx is None:
                break
            self._start_job(idx)
        if not self.active_processes and self._next_waiting_index() is None:
            self.finish_batch()

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
        self.preview.setReadOnly(True)
        self.save_preview_btn.setEnabled(False)
        threading.Thread(target=self._read_process_stream, args=(generation, index, process), daemon=True).start()
        self.process_pump.start()

    def _read_process_stream(self, generation: int, index: int, process: subprocess.Popen[str]) -> None:
        exit_code = 1
        try:
            if process.stdout is not None:
                for text in process.stdout:
                    self.process_outputs.append((generation, index, text))
            exit_code = process.wait()
        except Exception as exc:
            self.process_outputs.append((generation, index, f"Process error: {exc}\n"))
            if process.poll() is None:
                process.kill()
            process.wait()
            exit_code = 1
        if process.stdout is not None:
            process.stdout.close()
        self.process_finishes.append((generation, index, exit_code))

    def _drain_process_events(self) -> None:
        for _ in range(min(len(self.process_outputs), 200)):
            generation, index, text = self.process_outputs.popleft()
            if generation != self.process_generation:
                continue
            self.append_log(text)
            self._parse_progress(text, index)

        while self.process_finishes:
            generation, index, exit_code = self.process_finishes.popleft()
            if generation != self.process_generation:
                continue
            self._job_finished(index, exit_code)

        if not self.active_processes:
            self.process_pump.stop()

    def _parse_progress(self, text: str, index: int | None = None) -> None:
        job = self.jobs[index] if index is not None and 0 <= index < len(self.jobs) else None
        stage = re.search(r"\[stage:(\w+)\]", text)
        if stage:
            self.status_badge.setText(self.tr("stage_" + stage.group(1)))
            if job is not None:
                job.stage = stage.group(1)
        match = re.search(r"(\d+)%\|.*?(\d+)/(\d+)", text)
        if match:
            pct = int(match.group(1))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            if job is not None:
                job.progress = pct
        if job is not None and job.status == STATUS_RUNNING:
            status = self.tr("stage_" + job.stage) if job.stage else self._status_text(job.status)
            if job.progress is not None:
                status += f" {job.progress}%"
            item = self.table.item(index, 4)
            if item is not None:
                item.setText(status)

    def _job_finished(self, index: int, exit_code: int) -> None:
        if index is None or index not in self.active_processes or index >= len(self.jobs):
            return
        del self.active_processes[index]

        job = self.jobs[index]
        s = STRINGS[self.ui_lang]
        if exit_code == 0:
            job.status = STATUS_DONE
            self.append_log(f"{s['saved'].format(job.output)}\n")
            if not job.output.is_file():
                job.status = STATUS_FAILED
                self.append_log("Process exited without creating its output.\n")
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

    def finish_batch(self) -> None:
        s = STRINGS[self.ui_lang]
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_badge.setText(s["failed_status"] if any(job.status == STATUS_FAILED for job in self.jobs) else self._batch_status_text(s))
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.skip_button.setVisible(False)
        self._set_editing_enabled(True)

    def cancel_all(self) -> None:
        if self.burn_process is not None:
            self.burn_process.kill()
            return
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

    def skip_current(self) -> None:
        """Kill the currently selected running job and advance to the next one."""
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        index = rows[0]
        if index >= len(self.jobs):
            return
        job = self.jobs[index]
        if job.status != STATUS_RUNNING:
            return
        # Kill the process if it is still alive.
        process = self.active_processes.get(index)
        if process:
            if process.poll() is None:
                process.kill()
            del self.active_processes[index]
        job.status = STATUS_CANCELLED
        s = STRINGS[self.ui_lang]
        self.append_log(f"\nSkipped: {job.video.name}\n")
        self.refresh_table()
        # Advance to next waiting job without touching process_generation so
        # that other still-running parallel jobs keep their finish events valid.
        self._fill_parallel_slots()
        if not self.active_processes and self._next_waiting_index() is None:
            self.finish_batch()

    def closeEvent(self, event) -> None:
        self.media_player.set_source(None)
        if self.burn_process is not None:
            self.burn_process.kill()
            self.burn_process.waitForFinished(3000)
        if self.active_processes:
            self.cancel_all()
        super().closeEvent(event)

    def _clear_process_queues(self) -> None:
        self.process_outputs.clear()
        self.process_finishes.clear()

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
        QApplication.clipboard().setText(self.preview.toPlainText())

    def _save_preview(self) -> None:
        if self.preview_path is None or self.active_processes or self.preview.isReadOnly():
            return
        try:
            self.preview_path.write_text(self.preview.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, self.tr("save_preview"), str(exc))
            return
        self._drafts.pop(self.preview_path, None)
        self.preview.document().setModified(False)
        self.append_log(f"Preview saved: {self.preview_path}\n")

    def _load_review(self, output: Path | None, source: Path | None) -> None:
        self.review_list.clear()
        if output is not None:
            try:
                data = json.loads(review_path(output).read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("segments", []), list):
                    raise ValueError("Invalid review file")
                if source is not None and Path(data.get("source", "")).resolve() == source.resolve():
                    for segment in data.get("segments", []):
                        if isinstance(segment, dict) and segment.get("reasons"):
                            seconds = int(segment["start"])
                            item = QListWidgetItem(f"{seconds // 60:02d}:{seconds % 60:02d}  {segment['text']}")
                            item.setData(Qt.UserRole, int(segment["start"] * 1000))
                            self.review_list.addItem(item)
            except (OSError, ValueError, TypeError, KeyError):
                pass
        count = self.review_list.count()
        self.review_button.setText(self.tr("review_count").format(count))
        self.review_button.setEnabled(count > 0)
        if not count:
            self.review_button.setChecked(False)
            self.review_list.hide()

    def _seek_review_item(self, item) -> None:
        milliseconds = item.data(Qt.UserRole)
        self.media_player.seek(milliseconds)
        seconds = milliseconds // 1000
        stamp = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
        cursor = self.preview.document().find(stamp)
        if not cursor.isNull():
            self.preview.setTextCursor(cursor)
            self.preview.ensureCursorVisible()

    def export_reading_copy(self) -> None:
        if self.preview_path is None:
            return
        text = self.preview.toPlainText()
        try:
            if self.preview_path.suffix.lower() == ".json":
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise ValueError("Expected a transcript JSON object")
                text = payload.get("text") or "\n".join(s["text"] for s in payload.get("segments", []))
            else:
                text = reading_copy(text)
            path = self.preview_path.with_name(self.preview_path.stem + "_reading.txt")
            counter = 2
            while path.exists():
                path = self.preview_path.with_name(self.preview_path.stem + f"_reading_{counter}.txt")
                counter += 1
            path.write_text(text, encoding="utf-8")
            self.append_log(self.tr("saved").format(path) + "\n")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, self.tr("reading_copy"), str(exc))

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
