"""Native audio playback and timestamp navigation for transcript proofreading."""

from pathlib import Path
import re

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QSlider,
    QComboBox, QStyle, QPlainTextEdit, QSizePolicy,
)


def timestamp_ms(text: str) -> int | None:
    match = re.match(r"\s*\[?(\d{2,}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", text)
    if not match:
        return None
    hours, minutes, seconds = map(int, match.group(1, 2, 3))
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

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        position = timestamp_ms(self.textCursor().block().text())
        if position is not None:
            self.seekRequested.emit(position)


class AudioReviewPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path = None
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
        layout.addWidget(self.filename)
        row = QHBoxLayout()
        self.play_button = QToolButton()
        self.play_button.setIcon(tool_icon(self.style(), QStyle.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_play)
        row.addWidget(self.play_button)
        self.position_label = QLabel("00:00")
        self.position_label.setMinimumWidth(42)
        row.addWidget(self.position_label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.slider.sliderReleased.connect(lambda: self.player.setPosition(self.slider.value()))
        row.addWidget(self.slider, 1)
        self.duration_label = QLabel("00:00")
        row.addWidget(self.duration_label)
        self.speed = QComboBox()
        for rate in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.speed.addItem(f"{rate:g}x", rate)
        self.speed.setCurrentIndex(2)
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
        self.play_button.setEnabled(False)

    def set_language(self, language):
        self.play_button.setToolTip("播放 / 暂停" if language == "zh" else "Play / pause")
        self.speed.setToolTip("播放速度" if language == "zh" else "Playback speed")
        if self.source_path is None:
            self.filename.setText("未选择音视频" if language == "zh" else "No media selected")

    def set_source(self, path: Path | None):
        resolved = path.resolve() if path is not None and path.is_file() else None
        if resolved == self.source_path:
            return
        self.player.stop()
        self.source_path = resolved
        self.error_label.hide()
        self.player.setSource(QUrl.fromLocalFile(str(resolved)) if resolved else QUrl())
        self.play_button.setEnabled(resolved is not None)
        if resolved:
            self.filename.setText(resolved.name)
            self.filename.setToolTip(str(resolved))
        else:
            self.filename.clear()
        self.slider.setValue(0)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.source_path:
            self.player.play()

    def seek(self, milliseconds: int):
        if self.source_path:
            self.player.setPosition(max(0, milliseconds))

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
        self.error_label.setText(self.player.errorString())
        self.error_label.show()
