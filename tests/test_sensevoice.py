import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import sensevoice_backend
from transcription_support import review_path
from video_text_extractor import build_parser


class SenseVoiceTests(unittest.TestCase):
    def test_default_engine_is_sensevoice(self):
        self.assertEqual(build_parser().parse_args(["recording.m4a"]).mode, "sensevoice")
    def test_cli_accepts_optional_engine(self):
        args = build_parser().parse_args(["recording.m4a", "--mode", "sensevoice"])
        self.assertEqual(args.mode, "sensevoice")

    def test_all_audio_windows_are_preserved_even_when_no_text(self):
        recognizer = Mock()
        first, second = Mock(), Mock()
        first.result.text = ""
        second.result.text = "recognized"
        recognizer.create_stream.side_effect = [first, second]
        audio = np.zeros(21 * 16000, dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.txt"
            with patch.object(sensevoice_backend, "load_recognizer", return_value=recognizer), patch("transcription_support.decode_audio", return_value=audio), patch("video_text_extractor.detect_tools"), patch("video_text_extractor.ffmpeg_command", return_value="ffmpeg"):
                result = sensevoice_backend.transcribe(Path("input.wav"), output)
            self.assertEqual(len(result["segments"]), 2)
            self.assertEqual(result["segments"][0]["start"], 0)
            self.assertEqual(result["segments"][0]["end"], 20)
            self.assertEqual(result["segments"][1]["start"], 20)
            self.assertEqual(result["segments"][1]["end"], 21)
            self.assertIn("未识别出文字", output.read_text(encoding="utf-8"))
            self.assertTrue(review_path(output).is_file())


if __name__ == "__main__":
    unittest.main()
