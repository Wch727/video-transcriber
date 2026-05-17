# Video Text Extractor

一个本地视频转文字小工具，支持桌面窗口和命令行两种用法。默认使用本地 OpenAI Whisper 模型，不需要 OpenAI API Key。

## 功能

- 桌面 GUI：双击启动，选择视频、语言、模型和输出格式。
- 多语言转写：支持 English、Chinese、Japanese、Korean、Spanish、French、German、Italian、Portuguese、Russian、Arabic、Hindi、Vietnamese、Thai 等，也支持自定义 Whisper 语言代码。
- 多种输出格式：TXT、SRT、VTT、JSON。
- 本地运行：视频留在本机，Whisper 模型下载后可离线复用。
- 命令行模式：适合批处理或快速转写。
- 可选画面 OCR：`local_video_ocr.js` 可从视频画面中识别字幕或课件文字。

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

第一次使用某个 Whisper 模型时会自动下载模型文件，例如 `tiny`、`base`、`small`。下载完成后会缓存在本机。

## 启动桌面版

双击：

```text
start_video_text_gui.bat
```

或在 PowerShell 中运行：

```powershell
python .\video_text_gui.py
```

桌面窗口支持：

- 选择视频格式：MP4、MOV、MKV、WEBM、M4V、AVI。
- 选择视频文件。
- 切换界面语言：中文 / English。
- 选择转写语言或自动识别。
- 选择 Whisper 模型：`tiny` 最快，`base` 均衡，`small` 更准但更慢。
- 选择任务：原文转写或翻译成英文。
- 选择输出格式：TXT、SRT、VTT、JSON。

## 命令行用法

英文视频转英文文本：

```powershell
python .\video_text_extractor.py .\4-2.mp4 --mode whisper --whisper-model base --language en -o .\4-2_transcript_en.txt
```

输出字幕文件：

```powershell
python .\video_text_extractor.py .\4-2.mp4 --mode whisper --whisper-model base --language en --format srt -o .\4-2.srt
```

自动识别语言：

```powershell
python .\video_text_extractor.py .\your_video.mp4 --mode whisper --whisper-model base -o .\transcript.txt
```

翻译成英文：

```powershell
python .\video_text_extractor.py .\your_video.mp4 --mode whisper --whisper-task translate --format vtt -o .\translated.vtt
```

## 输出格式

- `text` / TXT：带时间戳的普通文本。
- `srt` / SRT：常见字幕格式。
- `vtt` / VTT：Web 字幕格式。
- `json` / JSON：包含完整文本、语言和分段时间。

## 画面 OCR

如果视频里有字幕、课件文字或标题，但你想识别画面文字，可以使用：

```powershell
npm install
```

```powershell
node .\local_video_ocr.js .\4-1.mp4 --interval 1 -o .\4-1_ocr_local.txt
```

默认只识别画面底部区域，更适合字幕。识别整张画面：

```powershell
node .\local_video_ocr.js .\4-1.mp4 --full-frame --interval 3 -o .\4-1_full_frame_ocr.txt
```

## 项目文件

- `video_text_gui.py`：桌面 GUI。
- `video_text_extractor.py`：核心转写脚本。
- `local_video_ocr.js`：本地画面 OCR。
- `start_video_text_gui.bat`：Windows 双击启动器。
- `requirements.txt`：Python 依赖。

## GitHub 发布说明

仓库默认忽略视频、转写结果、缓存、上传文件和 Python 编译缓存。示例视频请不要提交到仓库中，避免仓库过大。
