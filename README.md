# Video Text Extractor

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/Desktop-PySide6-41CD52)
![Whisper](https://img.shields.io/badge/Local-Whisper-FFB020)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4)
![License](https://img.shields.io/badge/License-MIT-2EA043)

把视频里的语音、字幕轨或画面文字提取成可编辑文本。

默认走本地 Whisper，不需要 API Key；也可以切换到 OpenAI API、内嵌字幕提取、画面 OCR，或者直接导出 SRT/VTT 字幕。

> 适合课程视频、会议录屏、英文视频转英文稿、字幕文件制作、以及把屏幕里的字幕/幻灯片文字提取出来。

## Highlights

| 能力 | 说明 |
| --- | --- |
| 桌面软件体验 | PySide6 图形界面，双击启动，拖拽视频，队列批量处理 |
| 本地优先 | 本地 Whisper 转写，视频不离开电脑，模型下载后可复用 |
| 5 种模式 | Local Whisper、OpenAI API、Embedded Subtitles、Visual OCR、Auto |
| 多语言 | 支持自动识别，也可指定 `en`、`zh`、`ja`、`ko`、`es`、`fr` 等语言 |
| 多格式输出 | `TXT`、`SRT`、`VTT`、`JSON` |
| 批量和历史 | 支持 1-4 个任务并行、实时日志、输出预览、历史记录恢复 |
| 字幕工作流 | 可生成字幕文件，也可把 SRT 硬烧进视频 |

## Quick Start

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动桌面版：

```powershell
python video_text_gui.py
```

也可以直接双击：

```text
start_video_text_gui.bat
```

最常见场景：英语视频转英语文字。

1. 模式选 `Local Whisper`
2. 语言选 `English (en)`
3. 任务选 `Transcribe`
4. 输出选 `TXT` 或 `SRT`
5. 点击开始

## Desktop App

桌面版是推荐入口。它会帮你处理文件队列、输出路径、模型参数和运行日志，适合不想每次敲命令的人。

### 操作流程

1. 添加视频：点击添加按钮，或者把 `.mp4` / `.mkv` / `.mov` / `.wmv` / `.flv` 等视频拖进窗口。
2. 选择模式：本地 Whisper、OpenAI API、内嵌字幕、画面 OCR 或 Auto。
3. 选择语言：不确定就选 Auto detect，明确语言就指定代码，例如 `en`、`zh`。
4. 选择模型：`tiny` 快，`base` 均衡，`small` / `medium` 更准但更慢。
5. 选择输出：TXT 用于阅读，SRT/VTT 用于字幕，JSON 用于后续处理。
6. 开始队列：运行中界面会锁住关键设置，避免任务和输出路径错乱。

### 模式怎么选

| 模式 | 适合场景 | 额外依赖 |
| --- | --- | --- |
| `Local Whisper` | 视频有语音，要转成文字；默认推荐 | `openai-whisper`、`imageio-ffmpeg` |
| `OpenAI API` | 想用远程 API 转写 | `OPENAI_API_KEY` |
| `Embedded subtitles` | 视频文件本身带字幕轨 | `ffmpeg`，`ffprobe` 推荐但不是硬依赖 |
| `Visual OCR` | 字幕或文字是画面的一部分，可在界面里指定 OCR 语言 | `tesseract` 和对应语言包 |
| `Auto (best)` | 先试字幕轨，再回退到语音转写 | 取决于命中的模式 |

## Command Line

GUI 之外，所有核心能力也能用命令行调用。

本地 Whisper 转写：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-model base --language en -o transcript.txt
```

自动识别语言：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-model base -o transcript.txt
```

导出 SRT 字幕：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --format srt -o subtitles.srt
```

导出 VTT 字幕：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --format vtt -o subtitles.vtt
```

导出 JSON 元数据：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --format json -o transcript.json
```

翻译成英文：

```powershell
python video_text_extractor.py video.mp4 --mode whisper --whisper-task translate -o translated.txt
```

提取内嵌字幕：

```powershell
python video_text_extractor.py video.mp4 --mode subtitle -o subtitles.srt
```

画面 OCR：

```powershell
python video_text_extractor.py video.mp4 --mode ocr --ocr-interval 2 -o ocr.txt
```

只检查环境，不执行转写：

```powershell
python video_text_extractor.py video.mp4 --dry-run
```

## Options

| 参数 | 说明 |
| --- | --- |
| `--mode` | `whisper`、`audio`、`subtitle`、`ocr`、`auto` |
| `--language` | 语言代码，例如 `en`、`zh`、`ja`、`ko`；语音模式也接受 `en-US` 这类地区码，会取主语言；不传则自动识别 |
| `--whisper-model` | `tiny`、`base`、`small`、`medium`、`large-v3`、`turbo` |
| `--whisper-task` | `transcribe` 原语言转写，`translate` 翻译成英文 |
| `--format` | `text`、`srt`、`vtt`、`json` |
| `--ocr-interval` | OCR 每隔多少秒抽一帧 |
| `-o`, `--out` | 输出文件路径，父目录会自动创建 |
| `--dry-run` | 只检测依赖和配置 |

## Dependencies

Python 依赖写在 `requirements.txt`：

| 包 | 用途 |
| --- | --- |
| `PySide6` | 桌面 GUI |
| `openai-whisper` | 本地语音转写 |
| `imageio-ffmpeg` | 提供可复用的 ffmpeg 可执行文件 |
| `openai` | OpenAI API 转写 |

可选系统工具：

| 工具 | 什么时候需要 |
| --- | --- |
| `ffmpeg` | 提取视频内嵌字幕轨、抽帧 OCR、音频切片 |
| `ffprobe` | 推荐安装，用于更准确地检测视频内嵌字幕轨；没有时会回退到 `ffmpeg` |
| `tesseract` | Python OCR 模式识别画面文字 |
| Chrome / Edge | Node.js 版画面 OCR 解码视频 |

说明：本地 Whisper 和部分视频处理会自动复用 `imageio-ffmpeg` 自带的 ffmpeg；如果通过 winget 安装 Gyan FFmpeg，程序也会自动查找 winget 安装目录里的 `ffmpeg.exe` / `ffprobe.exe`。`ffprobe` 不是硬依赖，但装完整 FFmpeg 套件会让字幕轨检测更稳。

## Visual OCR

Python CLI 的 `--mode ocr` 使用系统 `tesseract`。默认会优先使用 `chi_sim+eng`，如果只安装了英文语言包则自动退到 `eng`，也会识别 `TESSDATA_PREFIX` 或项目根目录 `tessdata` 里的语言包。自定义 OCR 语言可以写 `chi_sim+eng`，也可以写 `zh+en`，程序会映射成 Tesseract 语言包名。项目里还带一个 Node.js 版 OCR 工具，适合截取视频底部字幕区域或整帧画面：

```powershell
npm install
node local_video_ocr.js video.mp4 --interval 1 -o ocr_output.txt
```

识别整张画面：

```powershell
node local_video_ocr.js video.mp4 --full-frame --interval 3 -o full_ocr.txt
```

只识别底部字幕区域：

```powershell
node local_video_ocr.js video.mp4 --crop-bottom 0.42 --lang chi_sim+eng -o subtitle_ocr.txt
```

Node 版 OCR 的 `--lang` 也支持 `zh+en`、`EN`、`en-US`、`zh-TW` 这类别名写法，会自动映射到 Tesseract 语言包名。

## Output

默认输出目录是项目下的 `outputs` 文件夹。桌面版会按模式和语言自动生成文件名：

```text
video_transcript_en.txt
video_transcript_zh.srt
video_subtitles.srt
video_ocr.txt
```

历史记录保存在 `.transcribe_history.json`，已加入 `.gitignore`。视频、输出文件、缓存目录也默认不会提交到 Git。

## Troubleshooting

### 英语视频转英语稿为什么不要选 Translate？

`Transcribe` 是按原语言转写，英语视频会输出英文稿。`Translate to English` 是把非英语语音翻译成英文。

### subtitle 模式失败怎么办？

这个模式只处理“视频文件里真正存在的字幕轨”。如果字幕只是画面里看得见的字，用 OCR；如果是语音内容，用 Whisper。

### OCR 模式失败怎么办？

确认已经安装 `tesseract` 和语言包。英文常用 `eng`，简体中文常用 `chi_sim`，混合识别可用 `chi_sim+eng`。Windows 安装程序通常只自带 `eng` / `osd`，中文 OCR 需要把 `chi_sim.traineddata` 放进 Tesseract 的 `tessdata` 目录，或放进项目根目录的 `tessdata` 文件夹。

### 第一次转写为什么慢？

Whisper 首次会下载模型。模型越大越慢，越吃 CPU/GPU。短视频可先试 `base`，长视频可先用 `tiny` 或 `base`。

### OpenAI API 模式怎么设置 Key？

```powershell
$env:OPENAI_API_KEY="你的 API Key"
python video_text_extractor.py video.mp4 --mode audio --language en -o transcript.txt
```

## Project Structure

```text
video_text_gui.py          Desktop GUI
video_text_extractor.py    Core CLI engine
local_video_ocr.js         Node.js visual OCR helper
start_video_text_gui.bat   Windows launcher
requirements.txt           Python dependencies
package.json               Node.js OCR dependencies
LICENSE                    MIT license
```

## License

MIT. See [LICENSE](LICENSE).
