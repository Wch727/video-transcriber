"""Optional CPU-only SenseVoice transcription, isolated from Whisper dependencies."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_recognizer():
    dependency_dir = ROOT / ".video_text_cache" / "asr-deps"
    if dependency_dir.is_dir() and str(dependency_dir) not in sys.path:
        sys.path.insert(0, str(dependency_dir))
    try:
        sherpa = importlib.import_module("sherpa_onnx")
    except ImportError as exc:
        raise RuntimeError("SenseVoice requires sherpa-onnx. See requirements-sensevoice.txt.") from exc
    from model_storage import model_directory
    model_dir = model_directory("sensevoice")
    if not all((model_dir / name).is_file() for name in ("model.int8.onnx", "tokens.txt")):
        raise RuntimeError("SenseVoice model missing. Run tools/setup_sensevoice.py first.")
    return sherpa.OfflineRecognizer.from_sense_voice(
        model=str(model_dir / "model.int8.onnx"), tokens=str(model_dir / "tokens.txt"),
        num_threads=4, language="zh", use_itn=True, debug=False,
    )


def transcribe(source: Path, output: Path, channel="left"):
    from transcription_support import decode_audio, save_review
    from video_text_extractor import detect_tools, ffmpeg_command, format_whisper_result, write_text

    print("[stage:model]", flush=True)
    recognizer = load_recognizer()
    print("[stage:decode]", flush=True)
    binary = ffmpeg_command(detect_tools())
    if not binary:
        raise RuntimeError("ffmpeg is required")
    audio = decode_audio(source, binary, channel)
    print("[stage:transcribe]", flush=True)
    segments = []
    window = 20 * 16000
    import numpy as np
    for start in range(0, len(audio), window):
        chunk = audio[start:start + window]
        gain = min(8.0, 0.95 / max(float(np.max(np.abs(chunk))), 1e-6))
        stream = recognizer.create_stream()
        stream.accept_waveform(16000, chunk * gain)
        recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        segments.append({"start": start / 16000, "end": (start + len(chunk)) / 16000,
                         "text": text or "[未识别出文字]",
                         "review_reasons": ["manual_review"]})
        print(f"{min(100, round((start + len(chunk)) / len(audio) * 100))}%| {start + len(chunk)}/{len(audio)}", flush=True)
    result = {"text": "\n".join(s["text"] for s in segments), "language": "zh", "segments": segments}
    print("[stage:export]", flush=True)
    write_text(output, format_whisper_result(result, "text"))
    save_review(output, source, result, model="sensevoice-int8", channel=channel,
                timing="20-second windows, not sentence alignment")
    return result


if __name__ == "__main__":
    transcribe(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "left")
