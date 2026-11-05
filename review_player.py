"""Native audio playback and timestamp navigation for transcript proofreading."""

from pathlib import Path
import re

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QSlider,
    QComboBox, QStyle, QPlainTextEdit, QSizePolicy, QCheckBox, QTextEdit,
)


def timestamp_ms(text: str) -> int | None:
    match = re.match(r"\s*\[?(\d{2,}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", text)
    if not match:
        return None
    hours, minutes, seconds = map(int, match.group(1, 2, 3))
    if minutes >= 60 or seconds >= 60:
        return None
    fraction = int((match.group(4) or "").ljust(3, "0") or "0")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + fraction


def clock_text(milliseconds: int) -> str:
    seconds = max(0, milliseconds // 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def tool_icon(style, standard, color="#356b5a"):
    pixmap = style.standardIcon(standard).pixmap(18, 18)
    image = pixmap.toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            ink = QColor(color)
            lightness = (pixel.red() + pixel.green() + pixel.blue()) / 3
            ink.setAlpha(round(pixel.alpha() * min(1.0, (255 - lightness) / 110)))
            image.setPixelColor(x, y, ink)
    return QIcon(QPixmap.fromImage(image))


class TranscriptEdit(QPlainTextEdit):
    seekRequested = Signal(int)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton or self.textCursor().hasSelection():
            return
        cursor = self.cursorForPosition(event.position().toPoint())
        text = cursor.block().text()
        label = re.match(r"\s*\[?\d{2,}:\d{2}:\d{2}(?:[.,]\d{1,3})?", text)
        if label and cursor.positionInBlock() <= label.end():
            position = timestamp_ms(text)
            if position is not None:
                self.seekRequested.emit(position)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        position = timestamp_ms(self.textCursor().block().text())
        if position is not None:
            self.seekRequested.emit(position)


class TimestampHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        match = re.match(r"\s*(?:\[\d{2,}:\d{2}:\d{2}[^\]]*\]|\d{2,}:\d{2}:\d{2}.*?-->.*)", text)
        if match:
            style = QTextCharFormat()
            style.setForeground(QColor("#6d7c82"))
            self.setFormat(0, match.end(), style)


def highlight_playback(editor: QPlainTextEdit, start: int, end: int) -> None:
    selection = QTextEdit.ExtraSelection()
    selection.cursor = QTextCursor(editor.document())
    selection.cursor.setPosition(start)
    selection.cursor.setPosition(end, QTextCursor.KeepAnchor)
    selection.format.setBackground(QColor("#e8f0fd"))
    selection.format.setProperty(QTextFormat.FullWidthSelection, True)
    editor.setExtraSelections([selection])
    anchor = QTextCursor(editor.document())
    anchor.setPosition(start)
    rect = editor.cursorRect(anchor)
    if rect.top() < 0 or rect.bottom() > editor.viewport().height():
        delta = round((rect.top() - editor.viewport().height() * 0.25) / max(1, editor.fontMetrics().lineSpacing()))
        bar = editor.verticalScrollBar()
        bar.setValue(bar.value() + delta)


class AudioReviewPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path = None
        self.language = "zh"
        self._requested_path = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.setObjectName("audioPlayer")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        self.filename = QLabel()
        self.filename.setObjectName("audioFilename")
        self.filename.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading = QHBoxLayout()
        heading.addWidget(self.filename, 1)
        self.follow_check = QCheckBox()
        self.follow_check.setEnabled(False)
        heading.addWidget(self.follow_check)
        layout.addLayout(heading)
        row = QHBoxLayout()
        self.play_button = QToolButton()
        self.play_button.setIcon(tool_icon(self.style(), QStyle.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_play)
        row.addWidget(self.play_button)
        self.back_button = QToolButton()
        self.back_button.setIcon(tool_icon(self.style(), QStyle.SP_MediaSeekBackward))
        self.back_button.clicked.connect(lambda: self.seek_relative(-3000))
        row.addWidget(self.back_button)
        self.forward_button = QToolButton()
        self.forward_button.setIcon(tool_icon(self.style(), QStyle.SP_MediaSeekForward))
        self.forward_button.clicked.connect(lambda: self.seek_relative(3000))
        row.addWidget(self.forward_button)
        for button in (self.play_button, self.back_button, self.forward_button):
            button.setFixedSize(32, 32)
            button.setObjectName("iconButton")
        self.position_label = QLabel("00:00")
        self.position_label.setMinimumWidth(48)
        row.addWidget(self.position_label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.slider.sliderReleased.connect(lambda: self.player.setPosition(self.slider.value()))
        row.addWidget(self.slider, 1)
        self.duration_label = QLabel("00:00")
        self.duration_label.setMinimumWidth(48)
        row.addWidget(self.duration_label)
        self.speed = QComboBox()
        for rate in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.speed.addItem(f"{rate:g}x", rate)
        self.speed.setCurrentIndex(2)
        self.speed.setFixedWidth(76)
        self.speed.currentIndexChanged.connect(lambda: self.player.setPlaybackRate(self.speed.currentData()))
        row.addWidget(self.speed)
        layout.addLayout(row)
        self.error_label = QLabel()
        self.error_label.setObjectName("audioError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.errorOccurred.connect(self._error)
        self.set_language("zh")
        for button in (self.play_button, self.back_button, self.forward_button):
            button.setEnabled(False)

    def set_language(self, language):
        self.language = language
        self.follow_check.setText("跟随文字" if language == "zh" else "Follow text")
        self.play_button.setToolTip("播放 / 暂停 (Ctrl+Space)" if language == "zh" else "Play / pause (Ctrl+Space)")
        self.back_button.setToolTip("后退 3 秒 (Alt+Left)" if language == "zh" else "Back 3 seconds (Alt+Left)")
        self.forward_button.setToolTip("前进 3 秒 (Alt+Right)" if language == "zh" else "Forward 3 seconds (Alt+Right)")
        self.speed.setToolTip("播放速度" if language == "zh" else "Playback speed")
        if self.source_path is None and self._requested_path is None:
            self.filename.setText("未选择音视频" if language == "zh" else "No media selected")

    def set_source(self, path: Path | None):
        resolved = path.resolve() if path is not None and path.is_file() else None
        if resolved == self.source_path and path == self._requested_path:
            return
        self.player.stop()
        self._requested_path = path
        self.source_path = resolved
        self.error_label.hide()
        self.player.setSource(QUrl.fromLocalFile(str(resolved)) if resolved else QUrl())
        for button in (self.play_button, self.back_button, self.forward_button):
            button.setEnabled(resolved is not None)
        if resolved:
            self.filename.setText(resolved.name)
            self.filename.setToolTip(str(resolved))
        else:
            self.filename.setText(path.name if path else ("未选择音视频" if self.language == "zh" else "No media selected"))
            self.filename.setToolTip(str(path) if path else "")
            if path is not None:
                self.error_label.setText("音视频文件已移动或删除，请重新添加。" if self.language == "zh" else "Media file is missing. Add it again from its current location.")
                self.error_label.show()
        self.slider.setValue(0)
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.source_path:
            self.player.play()

    def seek(self, milliseconds: int):
        if self.source_path:
            duration = self.player.duration()
            self.player.setPosition(min(max(0, milliseconds), duration) if duration > 0 else max(0, milliseconds))

    def seek_relative(self, milliseconds: int):
        self.seek(self.player.position() + milliseconds)

    def _position_changed(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
        self.position_label.setText(clock_text(position))

    def _duration_changed(self, duration):
        self.slider.setRange(0, max(0, duration))
        self.duration_label.setText(clock_text(duration))

    def _playback_changed(self, state):
        self.play_button.setIcon(tool_icon(self.style(),
            QStyle.SP_MediaPause if state == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay))

    def _error(self, *_args):
        hint = "无法播放，请检查文件是否可读。" if self.language == "zh" else "Cannot play this media. Check that the file is readable."
        self.error_label.setText(hint + " " + self.player.errorString())
        self.error_label.show()
