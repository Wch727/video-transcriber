"""Run an independent local recognizer; hypotheses are not verified quotations."""
import json
import sys
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / ".video_text_cache" / "asr-deps"))
import sherpa_onnx
from transcription_support import decode_audio
from video_text_extractor import detect_tools, ffmpeg_command
from model_storage import model_directory

model_dir = model_directory("sensevoice")
recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model=str(model_dir / "model.int8.onnx"),
    tokens=str(model_dir / "tokens.txt"),
    num_threads=4, language="zh", use_itn=True, debug=False,
)
source = Path(sys.argv[1])
rows = []
for channel in ("left", "right"):
    samples = decode_audio(source, ffmpeg_command(detect_tools()), channel)
    for start, end in ((0, 12), (10, 22), (20, 32)):
        clip = samples[start * 16000:end * 16000]
        gain = min(8.0, 0.95 / max(float(np.max(np.abs(clip))), 1e-6))
        stream = recognizer.create_stream()
        stream.accept_waveform(16000, clip * gain)
        recognizer.decode_stream(stream)
        row = {"channel": channel, "start": start, "end": end, "text": stream.result.text}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
output = root / "outputs" / "opening_sensevoice.json"
output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
