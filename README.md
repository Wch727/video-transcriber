# Video Text Extractor

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Whisper](https://img.shields.io/badge/Powered%20by-OpenAI%20Whisper-orange)

A local video-to-text tool with a desktop GUI and CLI. Uses OpenAI Whisper locally by default — no API key required.

一个本地视频转文字工具，支持桌面 GUI 和命令行。默认使用本地 Whisper 模型，无需 API Key。

---

## Features / 功能

- **Desktop GUI** — Add video files, choose language/model/format, batch process with one click.
- **桌面 GUI** — 添加视频，选择语言/模型/格式，一键批量处理。
- **5 Transcription Modes** — Local Whisper, OpenAI API, embedded subtitle extraction, visual OCR, auto-select best.
- **5 种转写模式** — 本地 Whisper、OpenAI API、内嵌字幕提取、画面 OCR、自动选择最佳方式。
- **Auto Language Detection** — Whisper automatically detects the spoken language.
- **自动识别语言** — Whisper 自动检测视频中的语音语言。
- **Translate to English** — Translate any language speech into English text.
- **翻译成英文** — 将任意语言的语音翻译成英文文本。
- **55+ Languages** — English, Chinese, Japanese, Korean, Spanish, French, German, Arabic, Hindi, Thai, and many more.
- **55+ 种语言** — 英语、中文、日语、韩语、西班牙语、法语、德语、阿拉伯语、印地语、泰语等。
- **Multiple Output Formats** — TXT, SRT (subtitles), VTT (web subtitles), JSON (full metadata).
- **多种输出格式** — TXT、SRT（字幕）、VTT（Web 字幕）、JSON（完整元数据）.
- **Drag & Drop** — Drag video files directly into the window to add them.
- **拖拽添加** — 直接把视频文件拖到窗口即可添加。
- **Real-time Progress** — Progress bar shows actual percentage from Whisper.
- **实时进度** — 进度条显示 Whisper 的真实转写百分比。
- **Parallel Processing** — Run 1-4 transcription jobs simultaneously.
- **并行转写** — 同时运行 1-4 个转写任务。
- **Burn Subtitles** — Hardcode SRT subtitles into video using ffmpeg.
- **烧录字幕** — 用 ffmpeg 把 SRT 字幕硬编码到视频中。
- **Model Auto-recommend** — Suggests the best Whisper model based on video duration.
- **模型自动推荐** — 根据视频时长推荐最合适的 Whisper 模型。
- **Transcription History** — Save and reload past transcription jobs with parameters.
- **转写历史** — 保存和加载历史转写记录及参数。
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

### GUI Guide / GUI 使用说明

**Layout / 界面布局：**
- **Left sidebar** — Runtime status, add videos button, language toggle.
- **左侧边栏** — 运行状态检测、添加视频按钮、界面语言切换。
- **Left panel** — Settings: mode, format, language, model, output, task, parallel count.
- **左侧设置面板** — 模式、格式、语言、模型、输出、任务、并行数。
- **Right panel** — Queue table, preview area, log, and history.
- **右侧主区域** — 队列表格、预览区、日志、历史记录。

**Steps / 操作步骤：**

1. **Add videos** — Click the sidebar button, or drag video files into the window.
   **添加视频** — 点击侧边栏按钮，或直接拖拽视频文件到窗口。
2. **Choose mode** — Whisper (local), OpenAI API, subtitles, OCR, or auto.
   **选择模式** — Whisper（本地）、OpenAI API、字幕提取、OCR 或自动。
3. **Choose language** — Auto detect, specific language, or custom code.
   **选择语言** — 自动识别、指定语言或自定义代码。
4. **Choose model** — `tiny` fastest, `base` balanced, `small`/`medium` more accurate.
   **选择模型** — `tiny` 最快，`base` 均衡，`small`/`medium` 更准。
5. **Choose output** — TXT, SRT, VTT, or JSON.
   **选择输出格式** — TXT、SRT、VTT 或 JSON。
6. **Choose task** — Transcribe (original language) or translate to English.
   **选择任务** — 转写（原语言）或翻译成英文。
7. **Click Start** — Jobs process in the queue. Progress shows real percentage.
   **点击开始** — 队列中的任务依次处理，进度条显示真实百分比。

**Other / 其他：**
- Burn subtitles: click the red "Burn subtitles" button, select video + SRT file.
  烧录字幕：点击红色"烧录字幕"按钮，选择视频和 SRT 文件。
- History: double-click a past record in the history panel to reload it.
  历史记录：双击历史面板中的记录可重新加载。
- Parallel: set 1-4 in the "Parallel" spinner for concurrent jobs.
  并行数：在"并行数"中设置 1-4，多个任务同时处理。

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

Extract embedded subtitles:

```powershell
python video_text_extractor.py video.mp4 --mode subtitle
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
