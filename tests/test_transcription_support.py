import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import video_text_extractor as core
from transcription_support import decode_audio, reading_copy, review_segments, review_path
from review_player import timestamp_ms


class SupportTests(unittest.TestCase):
    def test_numeric_speech_is_kept_in_reading_copy(self):
        self.assertEqual(reading_copy("[00:00:01 - 00:00:02] 123\n456\n"), "123\n456\n")

    def test_subtitle_timing_only_is_removed(self):
        self.assertEqual(reading_copy("1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond"), "First\nSecond\n")

    def test_review_signals_do_not_rewrite_text(self):
        original = {"segments": [{"start": 1.2, "end": 3, "text": " uncertain ", "avg_logprob": -1.2},
                                 {"start": 3, "end": 4, "text": "normal", "avg_logprob": -0.2}]}
        review = review_segments(original)
        self.assertEqual(review[0]["reasons"], ["low_confidence"])
        self.assertEqual(review[0]["text"], "uncertain")
        self.assertEqual(review[1]["reasons"], [])
        self.assertEqual(original["segments"][0]["text"], " uncertain ")

    def test_timestamp_navigation(self):
        self.assertEqual(timestamp_ms("[01:02:03 - 01:02:05] text"), 3723000)
        self.assertEqual(timestamp_ms("00:00:04,250 --> 00:00:05,100"), 4250)
        self.assertIsNone(timestamp_ms("plain text"))

    def test_real_ffmpeg_channels_and_silence(self):
        binary = core.ffmpeg_command(core.detect_tools())
        if binary is None:
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "stereo.wav"
            time = np.arange(16000) / 16000
            audio = np.column_stack([np.sin(time * 2 * np.pi * 440), np.sin(time * 2 * np.pi * 880)])
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(2)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes((audio * 10000).astype("<i2").tobytes())
            for channel, frequency in (("left", 440), ("right", 880)):
                decoded = decode_audio(source, binary, channel)
                peak = np.argmax(np.abs(np.fft.rfft(decoded)))
                self.assertAlmostEqual(peak, frequency, delta=2)
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(bytes(32000))
            silence = decode_audio(source, binary, "right", enhance=True)
            self.assertEqual(len(silence), 16000)
            self.assertLess(np.max(np.abs(silence)), 0.001)

    def test_local_options_reach_model_without_path_shim(self):
        model = Mock()
        model.transcribe.return_value = {"text": "hello", "language": "en", "segments": [
            {"text": "hello", "start": 0, "end": 1, "avg_logprob": -1.1}]}
        whisper = Mock()
        whisper.load_model.return_value = model
        status = core.ToolStatus("ffmpeg", None, None, False, True, False, False)
        path_before = os.environ.get("PATH")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "transcript.txt"
            with patch.dict(sys.modules, {"whisper": whisper}), patch.object(core, "detect_tools", return_value=status), patch("transcription_support.iter_audio_chunks", return_value=((offset, audio) for offset, audio in [(0, np.zeros(16000))])) as decoder:
                core.transcribe_with_local_whisper(root / "source.wav", output, model_name="small",
                    language="en", task="transcribe", verbose=False, prompt="technical term",
                    audio_channel="right", enhance_audio=True)
                decoder.assert_called_once_with(root / "source.wav", "ffmpeg", "right", True, chunk_seconds=600)
            options = model.transcribe.call_args.kwargs
            self.assertEqual(options["initial_prompt"], "technical term")
            self.assertFalse(options["condition_on_previous_text"])
            self.assertEqual(options["temperature"], (0.0, 0.2, 0.4))
            self.assertEqual(options["no_speech_threshold"], 0.6)
            self.assertEqual(os.environ.get("PATH"), path_before)
            self.assertTrue(output.is_file())
            self.assertTrue(review_path(output).is_file())
            self.assertFalse((root / ".video_text_cache").exists())

    def test_cli_local_options(self):
        args = core.build_parser().parse_args(["recording.m4a", "--audio-channel", "left", "--enhance-audio", "--prompt", "term"])
        self.assertEqual(args.audio_channel, "left")
        self.assertTrue(args.enhance_audio)
        self.assertEqual(args.prompt, "term")


if __name__ == "__main__":
    unittest.main()
