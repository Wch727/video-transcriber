# Video Text Extractor

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Whisper](https://img.shields.io/badge/Powered%20by-OpenAI%20Whisper-orange)

A local video-to-text tool with a desktop GUI and CLI. Uses OpenAI Whisper locally by default — no API key required.

一个本地视频转文字工具，支持桌面 GUI 和命令行。默认使用本地 Whisper 模型，无需 API Key。

---

## Features / 功能

- **Desktop GUI** — Drag-and-drop video files, choose language/model/format, batch process with one click.
- **桌面 GUI** — 拖拽添加视频，选择语言/模型/格式，一键批量处理。
- **55+ Languages** — English, Chinese, Japanese, Korean, Spanish, French, German, Arabic, Hindi, Thai, and many more.
- **55+ 种语言** — 英语、中文、日语、韩语、西班牙语、法语、德语、阿拉伯语、印地语、泰语等。
- **Multiple Output Formats** — TXT, SRT (subtitles), VTT (web subtitles), JSON (full metadata).
- **多种输出格式** — TXT、SRT（字幕）、VTT（Web 字幕）、JSON（完整元数据）.
- **Local & Offline** — Videos stay on your machine. Whisper models are cached after first download.
- **本地离线** — 视频不离开本机，Whisper 模型首次下载后可离线复用。
- **CLI Mode** — Scriptable batch transcription for power users.
- **命令行模式** — 适合批处理或自动化场景。
- **Visual OCR** — Optional `local_video_ocr.js` extracts on-screen text from video frames.
- **画面 OCR** — 可选的 `local_video_ocr.js` 从视频画面中识别文字。
- **Bilingual UI** — Switch between Chinese and English interface with one click.
- **双语界面** — 一键切换中文/英文界面。

---

## Quick Start / 快速开始

### Install / 安装

```powershell
python -m pip install -r requirements.txt
```

Whisper models download automatically on first use (`tiny`, `base`, `small`, `medium`).

首次使用时自动下载 Whisper 模型。

### Launch GUI / 启动桌面版

Double-click `start_video_text_gui.bat` or run:

双击 `start_video_text_gui.bat`，或运行：

```powershell
python video_text_gui.py
```

---

## CLI Usage / 命令行用法

English video to text:

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-model base --language en
```

Output subtitles:

```powershell
python video_text_extractor.py video.mp4 --mode whisper --format srt -o subtitles.srt
```

Auto-detect language:

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-model base
```

Translate to English:

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-task translate --format vtt -o translated.vtt
```

### CLI Options / 命令行参数

| Flag | Description |
|------|-------------|
| `--mode` | `whisper` (local), `audio` (OpenAI API), `subtitle`, `ocr`, `auto` |
| `--whisper-model` | `tiny` / `base` / `small` / `medium` / `large` |
| `--language` | Language code: `en`, `zh`, `ja`, `es`, etc. |
| `--format` | `text`, `srt`, `vtt`, `json` |
| `--whisper-task` | `transcribe` (original) or `translate` (to English) |
| `-o` | Output file path |

---

## Output Formats / 输出格式

| Format | Description |
|--------|-------------|
| **TXT** | Timestamped plain text / 带时间戳的纯文本 |
| **SRT** | Standard subtitle format / 标准字幕格式 |
| **VTT** | Web subtitle format / Web 字幕格式 |
| **JSON** | Full text + language + segment metadata / 完整元数据 |

---

## Visual OCR / 画面 OCR

Extract on-screen text (subtitles, slides, titles) from video frames using `local_video_ocr.js`:

```powershell
npm install
node local_video_ocr.js video.mp4 --interval 1 -o ocr_output.txt
```

Full-frame OCR:

```powershell
node local_video_ocr.js video.mp4 --full-frame --interval 3 -o full_ocr.txt
```

---

## Project Structure / 项目结构

```
video_text_gui.py          # Desktop GUI / 桌面界面
video_text_extractor.py    # Core transcription engine / 核心转写引擎
local_video_ocr.js         # Visual OCR tool / 画面 OCR 工具
start_video_text_gui.bat   # Windows launcher / Windows 启动器
requirements.txt           # Python dependencies / Python 依赖
package.json               # Node.js dependencies (OCR) / Node.js 依赖
```

---

## License / 许可证

[MIT](LICENSE)
