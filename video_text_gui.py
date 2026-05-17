from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import END, filedialog, messagebox
import tkinter as tk
from tkinter import ttk


APP_DIR = Path(__file__).resolve().parent
EXTRACTOR = APP_DIR / "video_text_extractor.py"

SUPPORTED_VIDEO_TYPES = {
    "All supported": ["*.mp4", "*.mov", "*.mkv", "*.webm", "*.m4v", "*.avi"],
    "MP4": ["*.mp4"],
    "MOV": ["*.mov"],
    "MKV": ["*.mkv"],
    "WEBM": ["*.webm"],
    "M4V": ["*.m4v"],
    "AVI": ["*.avi"],
}

LANGUAGE_OPTIONS = [
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
    ("Custom code", "custom"),
]

OUTPUT_FORMATS = {
    "TXT": ("text", ".txt"),
    "SRT": ("srt", ".srt"),
    "VTT": ("vtt", ".vtt"),
    "JSON": ("json", ".json"),
}

UI = {
    "zh": {
        "title": "Video Text Extractor",
        "tagline": "本地视频转写工具，不需要 API Key",
        "app_language": "界面语言",
        "input": "输入",
        "video_format": "视频格式",
        "video_file": "视频文件",
        "browse": "浏览",
        "use_41": "使用 4-1.mp4",
        "use_42": "使用 4-2.mp4",
        "settings": "转写设置",
        "language": "转写语言",
        "custom_code": "自定义语言代码",
        "model": "Whisper 模型",
        "model_hint": "tiny 最快，base 均衡，small 更准但更慢。",
        "task": "任务",
        "transcribe": "原文转写",
        "translate": "翻译成英文",
        "output": "输出",
        "output_format": "输出格式",
        "output_file": "输出文件",
        "save_as": "另存为",
        "start": "开始转写",
        "cancel": "取消",
        "open_folder": "打开输出文件夹",
        "preview": "结果预览",
        "log": "运行日志",
        "ready": "就绪",
        "running": "转写中",
        "done": "完成",
        "failed": "失败",
        "video_missing": "请选择有效的视频文件。",
        "output_missing": "请选择输出文件。",
        "starting": "正在启动转写...",
        "saved": "已保存",
        "done_box": "转写完成",
        "failed_box": "转写失败",
        "missing_file": "找不到文件",
        "select_video": "选择视频",
        "select_output": "选择输出文件",
        "runtime": "运行环境",
        "whisper_ready": "本地 Whisper",
        "ffmpeg_ready": "ffmpeg",
        "openai_key": "OpenAI Key",
        "available": "可用",
        "missing": "缺失",
        "latest": "最近输出会显示在这里",
    },
    "en": {
        "title": "Video Text Extractor",
        "tagline": "Local video transcription, no API key required",
        "app_language": "App language",
        "input": "Input",
        "video_format": "Video format",
        "video_file": "Video file",
        "browse": "Browse",
        "use_41": "Use 4-1.mp4",
        "use_42": "Use 4-2.mp4",
        "settings": "Transcription",
        "language": "Language",
        "custom_code": "Custom language code",
        "model": "Whisper model",
        "model_hint": "tiny is fastest, base is balanced, small is more accurate.",
        "task": "Task",
        "transcribe": "Transcribe",
        "translate": "Translate to English",
        "output": "Output",
        "output_format": "Output format",
        "output_file": "Output file",
        "save_as": "Save as",
        "start": "Start transcription",
        "cancel": "Cancel",
        "open_folder": "Open output folder",
        "preview": "Preview",
        "log": "Log",
        "ready": "Ready",
        "running": "Running",
        "done": "Done",
        "failed": "Failed",
        "video_missing": "Please choose a valid video file.",
        "output_missing": "Please choose an output file.",
        "starting": "Starting transcription...",
        "saved": "Saved",
        "done_box": "Transcription complete",
        "failed_box": "Transcription failed",
        "missing_file": "Missing file",
        "select_video": "Choose video",
        "select_output": "Choose output file",
        "runtime": "Runtime",
        "whisper_ready": "Local Whisper",
        "ffmpeg_ready": "ffmpeg",
        "openai_key": "OpenAI key",
        "available": "Ready",
        "missing": "Missing",
        "latest": "The latest result will appear here",
    },
}


class VideoTextApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Video Text Extractor")
        self.geometry("1080x760")
        self.minsize(960, 680)
        self.configure(bg="#eef3f8")

        self.process: subprocess.Popen[str] | None = None
        self.worker: threading.Thread | None = None

        self.ui_language = tk.StringVar(value="zh")
        self.video_path = tk.StringVar()
        self.video_type = tk.StringVar(value="All supported")
        self.transcript_language = tk.StringVar(value=self._language_display("English", "en"))
        self.custom_language = tk.StringVar()
        self.model = tk.StringVar(value="base")
        self.task = tk.StringVar(value="transcribe")
        self.output_format = tk.StringVar(value="TXT")
        self.output_path = tk.StringVar()
        self.status_key = "ready"

        self.language_display_to_code: dict[str, str] = {}
        self.custom_language_frame: ttk.Frame | None = None
        self.preview: tk.Text | None = None
        self.log: tk.Text | None = None
        self.progress: ttk.Progressbar | None = None
        self.start_button: ttk.Button | None = None
        self.cancel_button: ttk.Button | None = None
        self.status_label: ttk.Label | None = None

        self._build_style()
        self._build_ui()
        self._load_first_video()

    def tr(self, key: str) -> str:
        return UI[self.ui_language.get()][key]

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background="#eef3f8")
        style.configure("Surface.TFrame", background="#ffffff")
        style.configure("Muted.TFrame", background="#f8fafc")
        style.configure("Header.TFrame", background="#162033")
        style.configure("Title.TLabel", background="#162033", foreground="#ffffff", font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background="#162033", foreground="#b8c7dc", font=("Segoe UI", 10))
        style.configure("TLabel", background="#ffffff", foreground="#1b2535", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI", 12, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#162033", foreground="#dbeafe", font=("Segoe UI", 10, "bold"))
        style.configure("Metric.TLabel", background="#f8fafc", foreground="#334155", font=("Segoe UI", 9))
        style.configure("Primary.TButton", background="#2563eb", foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=(16, 9))
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#94a3b8")])
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("TCombobox", padding=(6, 4))
        style.configure("TEntry", padding=(6, 5))
        style.configure("TRadiobutton", background="#ffffff", foreground="#1b2535", font=("Segoe UI", 10))
        style.configure("Horizontal.TProgressbar", troughcolor="#e2e8f0", background="#2563eb")

    def _build_ui(self) -> None:
        for child in self.winfo_children():
            child.destroy()

        self.language_display_to_code = {}
        shell = ttk.Frame(self, style="App.TFrame", padding=18)
        shell.pack(fill="both", expand=True)

        self._build_header(shell)
        body = ttk.Frame(shell, style="App.TFrame")
        body.pack(fill="both", expand=True, pady=(14, 0))

        controls = ttk.Frame(body, style="Surface.TFrame", padding=18)
        controls.pack(side="left", fill="y", padx=(0, 14))
        controls.configure(width=390)

        output = ttk.Frame(body, style="Surface.TFrame", padding=18)
        output.pack(side="right", fill="both", expand=True)

        self._build_controls(controls)
        self._build_output(output)
        self._toggle_custom_language()
        self._set_status(self.status_key)

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Header.TFrame", padding=(20, 16))
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)

        title_area = ttk.Frame(header, style="Header.TFrame")
        title_area.grid(row=0, column=0, sticky="w")
        ttk.Label(title_area, text=self.tr("title"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_area, text=self.tr("tagline"), style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))

        right = ttk.Frame(header, style="Header.TFrame")
        right.grid(row=0, column=1, sticky="e")
        ttk.Label(right, text=self.tr("app_language"), style="Subtitle.TLabel").pack(anchor="e")
        selector = ttk.Combobox(
            right,
            values=["中文", "English"],
            state="readonly",
            width=13,
        )
        selector.set("中文" if self.ui_language.get() == "zh" else "English")
        selector.pack(anchor="e", pady=(3, 8))
        selector.bind("<<ComboboxSelected>>", lambda event: self._change_ui_language(selector.get()))
        self.status_label = ttk.Label(right, text="", style="Status.TLabel")
        self.status_label.pack(anchor="e")

    def _build_controls(self, parent: ttk.Frame) -> None:
        self._section(parent, self.tr("runtime"))
        metrics = ttk.Frame(parent, style="Muted.TFrame", padding=12)
        metrics.pack(fill="x", pady=(8, 18))
        status = self._runtime_status()
        self._metric(metrics, self.tr("whisper_ready"), status["whisper"])
        self._metric(metrics, self.tr("ffmpeg_ready"), status["ffmpeg"])
        self._metric(metrics, self.tr("openai_key"), status["openai"])

        self._section(parent, self.tr("input"))
        self._label(parent, self.tr("video_format"), top=10)
        ttk.Combobox(parent, textvariable=self.video_type, values=list(SUPPORTED_VIDEO_TYPES), state="readonly").pack(fill="x")

        self._label(parent, self.tr("video_file"), top=10)
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.video_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.tr("browse"), command=self._browse_video).pack(side="left", padx=(8, 0))

        quick = ttk.Frame(parent, style="Surface.TFrame")
        quick.pack(fill="x", pady=(8, 18))
        ttk.Button(quick, text=self.tr("use_41"), command=lambda: self._set_video(APP_DIR / "4-1.mp4")).pack(side="left")
        ttk.Button(quick, text=self.tr("use_42"), command=lambda: self._set_video(APP_DIR / "4-2.mp4")).pack(side="left", padx=(8, 0))

        self._section(parent, self.tr("settings"))
        self._label(parent, self.tr("language"), top=10)
        language_box = ttk.Combobox(
            parent,
            textvariable=self.transcript_language,
            values=self._language_values(),
            state="readonly",
        )
        language_box.pack(fill="x")
        language_box.bind("<<ComboboxSelected>>", lambda _event: self._on_transcript_language_change())

        self.custom_language_frame = ttk.Frame(parent, style="Surface.TFrame")
        self._label(self.custom_language_frame, self.tr("custom_code"), top=8)
        ttk.Entry(self.custom_language_frame, textvariable=self.custom_language).pack(fill="x")

        self._label(parent, self.tr("model"), top=10)
        ttk.Combobox(parent, textvariable=self.model, values=["tiny", "base", "small", "medium"], state="readonly").pack(fill="x")
        ttk.Label(parent, text=self.tr("model_hint"), style="Hint.TLabel").pack(anchor="w", pady=(4, 0))

        self._label(parent, self.tr("task"), top=10)
        task_row = ttk.Frame(parent, style="Surface.TFrame")
        task_row.pack(fill="x")
        ttk.Radiobutton(task_row, text=self.tr("transcribe"), variable=self.task, value="transcribe").pack(side="left")
        ttk.Radiobutton(task_row, text=self.tr("translate"), variable=self.task, value="translate").pack(side="left", padx=(14, 0))

        self._section(parent, self.tr("output"), top=18)
        self._label(parent, self.tr("output_format"), top=10)
        fmt = ttk.Combobox(parent, textvariable=self.output_format, values=list(OUTPUT_FORMATS), state="readonly")
        fmt.pack(fill="x")
        fmt.bind("<<ComboboxSelected>>", lambda _event: self._suggest_output_path())

        self._label(parent, self.tr("output_file"), top=10)
        output_row = ttk.Frame(parent, style="Surface.TFrame")
        output_row.pack(fill="x")
        ttk.Entry(output_row, textvariable=self.output_path).pack(side="left", fill="x", expand=True)
        ttk.Button(output_row, text=self.tr("save_as"), command=self._browse_output).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(parent, style="Surface.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        self.start_button = ttk.Button(actions, text=self.tr("start"), style="Primary.TButton", command=self._start)
        self.start_button.pack(side="left", fill="x", expand=True)
        self.cancel_button = ttk.Button(actions, text=self.tr("cancel"), command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Button(parent, text=self.tr("open_folder"), command=self._open_output_folder).pack(fill="x", pady=(10, 0))

    def _build_output(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Surface.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text=self.tr("preview"), style="Section.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(top, mode="indeterminate", length=170)
        self.progress.pack(side="right")

        preview_frame = ttk.Frame(parent, style="Surface.TFrame")
        preview_frame.pack(fill="both", expand=True, pady=(10, 16))
        self.preview = tk.Text(
            preview_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbfdff",
            fg="#111827",
            insertbackground="#111827",
            relief="solid",
            bd=1,
            padx=12,
            pady=10,
        )
        preview_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=preview_scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        preview_scroll.pack(side="right", fill="y")
        self.preview.insert(END, self.tr("latest"))

        ttk.Label(parent, text=self.tr("log"), style="Section.TLabel").pack(anchor="w")
        log_frame = ttk.Frame(parent, style="Surface.TFrame")
        log_frame.pack(fill="x", pady=(10, 0))
        self.log = tk.Text(
            log_frame,
            height=9,
            wrap="word",
            font=("Consolas", 9),
            bg="#111827",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            padx=12,
            pady=10,
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _runtime_status(self) -> dict[str, bool]:
        from video_text_extractor import detect_tools

        status = detect_tools()
        return {
            "whisper": status.local_whisper,
            "ffmpeg": bool(status.ffmpeg or status.imageio_ffmpeg),
            "openai": status.openai_key,
        }

    def _metric(self, parent: ttk.Frame, label: str, ok: bool) -> None:
        frame = ttk.Frame(parent, style="Muted.TFrame")
        frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        color = "#15803d" if ok else "#b45309"
        value = self.tr("available") if ok else self.tr("missing")
        ttk.Label(frame, text=label, style="Metric.TLabel").pack(anchor="w")
        ttk.Label(frame, text=value, background="#f8fafc", foreground=color, font=("Segoe UI", 10, "bold")).pack(anchor="w")

    def _section(self, parent: ttk.Frame, text: str, top: int = 0) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", pady=(top, 0))

    def _label(self, parent: ttk.Frame, text: str, top: int = 0) -> None:
        ttk.Label(parent, text=text).pack(anchor="w", pady=(top, 4))

    def _language_display(self, name: str, code: str) -> str:
        return name if not code else f"{name} ({code})"

    def _language_values(self) -> list[str]:
        values = []
        current_display = self.transcript_language.get()
        for name, code in LANGUAGE_OPTIONS:
            value = self._language_display(name, code)
            self.language_display_to_code[value] = code
            values.append(value)
        if current_display in values:
            self.transcript_language.set(current_display)
        else:
            self.transcript_language.set(self._language_display("English", "en"))
        return values

    def _change_ui_language(self, value: str) -> None:
        self.ui_language.set("en" if value == "English" else "zh")
        self._build_ui()
        self._suggest_output_path()

    def _on_transcript_language_change(self) -> None:
        self._toggle_custom_language()
        self._suggest_output_path()

    def _toggle_custom_language(self) -> None:
        if not self.custom_language_frame:
            return
        if self._language_code(raw=True) == "custom":
            self.custom_language_frame.pack(fill="x")
        else:
            self.custom_language_frame.pack_forget()

    def _load_first_video(self) -> None:
        for name in ["4-2.mp4", "4-1.mp4"]:
            candidate = APP_DIR / name
            if candidate.exists():
                self._set_video(candidate)
                return

    def _set_video(self, path: Path) -> None:
        if path.exists():
            self.video_path.set(str(path))
            self._suggest_output_path()
        else:
            messagebox.showwarning(self.tr("missing_file"), str(path))

    def _browse_video(self) -> None:
        patterns = SUPPORTED_VIDEO_TYPES[self.video_type.get()]
        filetypes = [(self.video_type.get(), " ".join(patterns)), ("All files", "*.*")]
        selected = filedialog.askopenfilename(initialdir=APP_DIR, title=self.tr("select_video"), filetypes=filetypes)
        if selected:
            self.video_path.set(selected)
            self._suggest_output_path()

    def _browse_output(self) -> None:
        fmt_name = self.output_format.get()
        extension = OUTPUT_FORMATS[fmt_name][1]
        selected = filedialog.asksaveasfilename(
            initialdir=APP_DIR,
            initialfile=Path(self.output_path.get()).name or f"transcript{extension}",
            title=self.tr("select_output"),
            defaultextension=extension,
            filetypes=[(fmt_name, f"*{extension}"), ("All files", "*.*")],
        )
        if selected:
            self.output_path.set(selected)

    def _suggest_output_path(self) -> None:
        raw_video = self.video_path.get().strip()
        if not raw_video:
            return
        video = Path(raw_video)
        fmt_name = self.output_format.get()
        extension = OUTPUT_FORMATS[fmt_name][1]
        language = self._language_code()
        suffix = language or "auto"
        self.output_path.set(str(video.with_name(f"{video.stem}_transcript_{suffix}{extension}")))

    def _language_code(self, raw: bool = False) -> str | None:
        code = self.language_display_to_code.get(self.transcript_language.get(), "")
        if raw:
            return code
        if code == "custom":
            return self.custom_language.get().strip() or None
        return code or None

    def _command(self) -> list[str]:
        video = Path(self.video_path.get().strip())
        output = Path(self.output_path.get().strip())
        fmt = OUTPUT_FORMATS[self.output_format.get()][0]
        command = [
            sys.executable,
            "-u",
            str(EXTRACTOR),
            str(video),
            "--mode",
            "whisper",
            "--whisper-model",
            self.model.get(),
            "--format",
            fmt,
            "-o",
            str(output),
        ]
        language = self._language_code()
        if language:
            command.extend(["--language", language])
        if self.task.get() == "translate":
            command.extend(["--whisper-task", "translate"])
        return command

    def _start(self) -> None:
        video = Path(self.video_path.get().strip())
        output = Path(self.output_path.get().strip())
        if not video.exists():
            messagebox.showerror(self.tr("missing_file"), self.tr("video_missing"))
            return
        if not output.name:
            messagebox.showerror(self.tr("missing_file"), self.tr("output_missing"))
            return
        output.parent.mkdir(parents=True, exist_ok=True)

        self._set_status("running")
        if self.start_button:
            self.start_button.configure(state="disabled")
        if self.cancel_button:
            self.cancel_button.configure(state="normal")
        if self.progress:
            self.progress.start(12)
        if self.preview:
            self.preview.delete("1.0", END)
        if self.log:
            self.log.delete("1.0", END)
        self._append_log(self.tr("starting") + "\n")

        self.worker = threading.Thread(target=self._run_process, args=(self._command(), output), daemon=True)
        self.worker.start()

    def _run_process(self, command: list[str], output: Path) -> None:
        try:
            self.process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.after(0, self._append_log, line)

            return_code = self.process.wait()
            if return_code == 0:
                self.after(0, self._finish_success, output)
            else:
                self.after(0, self._finish_error, f"Process exited with code {return_code}.")
        except Exception as exc:
            self.after(0, self._finish_error, f"{type(exc).__name__}: {exc}")
        finally:
            self.process = None

    def _finish_success(self, output: Path) -> None:
        self._set_status("done")
        self._finish_buttons()
        self._append_log(f"\n{self.tr('saved')}: {output}\n")
        if output.exists() and self.preview:
            content = output.read_text(encoding="utf-8", errors="replace")
            self.preview.delete("1.0", END)
            self.preview.insert(END, content)
        messagebox.showinfo(self.tr("done_box"), f"{self.tr('saved')}:\n{output}")

    def _finish_error(self, message: str) -> None:
        self._set_status("failed")
        self._finish_buttons()
        self._append_log(f"\n{message}\n")
        messagebox.showerror(self.tr("failed_box"), message)

    def _finish_buttons(self) -> None:
        if self.progress:
            self.progress.stop()
        if self.start_button:
            self.start_button.configure(state="normal")
        if self.cancel_button:
            self.cancel_button.configure(state="disabled")

    def _cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._append_log("\nCancel requested.\n")
            self._set_status("running")

    def _set_status(self, key: str) -> None:
        self.status_key = key
        if self.status_label:
            self.status_label.configure(text=self.tr(key))

    def _append_log(self, text: str) -> None:
        if self.log:
            self.log.insert(END, text)
            self.log.see(END)

    def _open_output_folder(self) -> None:
        path = Path(self.output_path.get().strip()).parent if self.output_path.get().strip() else APP_DIR
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)


if __name__ == "__main__":
    app = VideoTextApp()
    app.mainloop()
