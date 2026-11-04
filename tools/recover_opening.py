"""Compare short-window Whisper hypotheses; keep results explicitly unverified."""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import whisper

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcription_support import decode_audio
from video_text_extractor import detect_tools, ffmpeg_command
from model_storage import model_directory

torch.set_num_threads(4)
source = Path(sys.argv[1])
output = Path("outputs/opening_comparison.json")
output.parent.mkdir(exist_ok=True)
model = whisper.load_model("small", download_root=str(model_directory("whisper")))
rows = []
binary = ffmpeg_command(detect_tools())
for channel in ("left", "right"):
    audio = decode_audio(source, binary, channel)[:30 * 16000]
    for start, end in ((0, 12), (10, 22), (20, 30)):
        samples = audio[start * 16000:end * 16000].copy()
        # Gain only: preserve the waveform; avoid aggressive noise removal.
        peak = float(np.max(np.abs(samples)))
        gain = min(8.0, 0.95 / max(peak, 1e-6))
        result = model.transcribe(
            samples * gain, language="zh", task="transcribe", fp16=False,
            condition_on_previous_text=False, temperature=(0.0, 0.2),
            beam_size=5, no_speech_threshold=0.6, verbose=False,
        )
        row = {"channel": channel, "start": start, "end": end, "gain": gain,
               "text": result["text"], "segments": result.get("segments", [])}
        rows.append(row)
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in row.items() if k != "segments"}, ensure_ascii=False), flush=True)
print(output, flush=True)
