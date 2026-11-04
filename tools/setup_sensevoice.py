"""Download and verify the optional SenseVoice model; never uploads audio."""
import hashlib
from pathlib import Path
import urllib.request
import sys
import argparse
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_storage import model_directory, configure_model_root
BASE = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/"
FILES = {
    "model.int8.onnx": "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51",
    "tokens.txt": "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", help="Persist the model storage root, e.g. D:/VideoTextModels")
    args = parser.parse_args()
    if args.model_dir:
        selected = configure_model_root(args.model_dir)
        os.environ["VIDEO_TEXT_MODEL_DIR"] = str(selected)
    folder = model_directory("sensevoice")
    folder.mkdir(parents=True, exist_ok=True)
    for name, checksum in FILES.items():
        destination = folder / name
        if destination.is_file() and digest(destination) == checksum:
            print(f"Verified: {name}", flush=True)
            continue
        partial = folder / (name + ".partial")
        print(f"Downloading: {name}", flush=True)
        with urllib.request.urlopen(BASE + name, timeout=60) as response, partial.open("wb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
        if digest(partial) != checksum:
            raise RuntimeError(f"Checksum mismatch for {name}; download was not installed.")
        partial.replace(destination)
    print("SenseVoice ready.", flush=True)


if __name__ == "__main__":
    main()
