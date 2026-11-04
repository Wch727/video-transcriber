"""Measure the opening stereo channels without changing the source recording."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_text_extractor import detect_tools, ffmpeg_command


def db(value):
    return round(float(20 * np.log10(max(value, 1e-10))), 2)


source = Path(sys.argv[1])
result = subprocess.run([ffmpeg_command(detect_tools()), "-v", "error", "-i", str(source),
                         "-t", "30", "-ac", "2", "-ar", "16000", "-f", "f32le", "pipe:1"],
                        capture_output=True, check=True)
stereo = np.frombuffer(result.stdout, dtype=np.float32).reshape(-1, 2)
rows = []
for start in range(0, 30, 5):
    block = stereo[start * 16000:(start + 5) * 16000]
    left, right = block.T
    rows.append({
        "start": start, "end": start + 5,
        "left_rms_db": db(np.sqrt(np.mean(left ** 2))),
        "right_rms_db": db(np.sqrt(np.mean(right ** 2))),
        "mix_rms_db": db(np.sqrt(np.mean(((left + right) / 2) ** 2))),
        "difference_rms_db": db(np.sqrt(np.mean(((left - right) / 2) ** 2))),
        "correlation": round(float(np.corrcoef(left, right)[0, 1]), 4),
    })
print(json.dumps(rows, indent=2))
