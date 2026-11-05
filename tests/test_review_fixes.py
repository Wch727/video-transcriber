import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import video_text_extractor as core
import transcription_support as support


class CloudConsentTests(unittest.TestCase):
    def test_auto_never_falls_back_without_consent(self):
        for installed in (False, True):
            args = core.build_parser().parse_args(["input.wav", "--mode", "auto"])
            status = core.ToolStatus(None, None, None, True, installed, False, False)
            with self.subTest(installed=installed), patch.object(core, "ffmpeg_command", return_value=None), patch.object(core, "transcribe_with_local_whisper", side_effect=RuntimeError("failed")), patch.object(core, "transcribe_audio") as cloud:
                with self.assertRaisesRegex(SystemExit, "allow-cloud-fallback"):
                    core.run_auto(Path("input.wav"), Path("out.txt"), status, args)
                cloud.assert_not_called()

    def test_explicit_consent_allows_fallback(self):
        args = core.build_parser().parse_args(["input.wav", "--mode", "auto", "--allow-cloud-fallback"])
        status = core.ToolStatus(None, None, None, True, False, False, False)
        with patch.object(core, "ffmpeg_command", return_value=None), patch.object(core, "transcribe_audio", return_value=Path("out.txt")) as cloud:
            core.run_auto(Path("input.wav"), Path("out.txt"), status, args)
            cloud.assert_called_once()

    def test_cloud_cannot_silently_change_translation_into_transcription(self):
        args = core.build_parser().parse_args(["input.wav", "--mode", "auto", "--allow-cloud-fallback", "--whisper-task", "translate"])
        status = core.ToolStatus(None, None, None, True, False, False, False)
        with patch.object(core, "ffmpeg_command", return_value=None), patch.object(core, "transcribe_audio") as cloud:
            with self.assertRaisesRegex(SystemExit, "翻译"):
                core.run_auto(Path("input.wav"), Path("out.txt"), status, args)
            cloud.assert_not_called()


class ActualChunkTimingTests(unittest.TestCase):
    def test_wav_window_is_capped_and_oversized_chunks_are_not_uploaded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "large.wav"
            source.write_bytes(bytes(2 * 1024 * 1024))
            with patch.object(core, "split_audio_with_ffmpeg", return_value=[core.AudioChunk(source, 0)]) as split, patch.object(core, "transcribe_one_file") as cloud:
                with self.assertRaisesRegex(SystemExit, "尚未上传"):
                    core.transcribe_audio(source, root / "out.txt", None, model="whisper-1", language=None,
                                          prompt=None, response_format="text", max_upload_mb=1, chunk_seconds=600)
                self.assertEqual(split.call_args.args[-1], 30)
                cloud.assert_not_called()

    def test_merge_uses_recorded_start_times(self):
        segments = [[core._ChunkSegment(0.1, 0.8, "first")], [], [core._ChunkSegment(0.2, 0.9, "third")]]
        merged = core._merge_chunks_into_segments(segments, [0.0, 10.008, 20.016])
        self.assertAlmostEqual(merged[1].start, 20.216)
        self.assertAlmostEqual(merged[1].end, 20.916)

    def test_real_ffmpeg_manifest_records_all_chunks(self):
        status = core.detect_tools()
        binary = core.ffmpeg_command(status)
        if not binary:
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.wav"
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(bytes(16000 * 2 * 3))
            chunks = core.split_audio_with_ffmpeg(source, root, status, 1)
            self.assertGreaterEqual(len(chunks), 3)
            self.assertEqual(chunks[0].start, 0.0)
            self.assertTrue(all(chunk.path.is_file() for chunk in chunks))
            self.assertGreater(chunks[1].start, chunks[0].start)
            cumulative_samples = 0
            for chunk in chunks:
                decoded = support.decode_audio(chunk.path, binary)
                self.assertAlmostEqual(chunk.start, cumulative_samples / 16000, places=5)
                cumulative_samples += len(decoded)
            self.assertEqual(cumulative_samples, 3 * 16000)
            with patch.object(core, "split_audio_with_ffmpeg", return_value=chunks), patch.object(core, "transcribe_one_file", return_value='{"text":"word","segments":[{"start":0,"end":0.2,"text":"word"}]}'):
                core.transcribe_audio(source, root / "out.json", status, model="whisper-1", language=None,
                                      prompt=None, response_format="json", max_upload_mb=0, chunk_seconds=1)
            result = json.loads((root / "out.json").read_text())
            self.assertAlmostEqual(result["segments"][1]["start"], chunks[1].start)


class ReviewSaveTests(unittest.TestCase):
    def test_stale_sidecar_cannot_be_revalidated_by_saving(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.txt"
            output.write_text("[00:00:02 - 00:00:04] original", encoding="utf-8")
            support.save_review(output, Path("source.wav"), {"segments": [{"start": 2, "end": 4, "text": "original"}]})
            output.write_text("[00:00:02 - 00:00:04] external edit", encoding="utf-8")
            original_review = support.review_path(output).read_bytes()
            with self.assertRaisesRegex(ValueError, "out of date"):
                support.save_edited_transcript(output, "[00:00:02 - 00:00:04] new edit")
            self.assertIn("external edit", output.read_text())
            self.assertEqual(support.review_path(output).read_bytes(), original_review)

    def test_text_only_edits_preserve_precise_review_times(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.txt"
            output.write_text("[00:00:02 - 00:00:04] wrong", encoding="utf-8")
            support.save_review(output, Path("source.wav"), {"segments": [
                {"start": 2.125, "end": 4.875, "text": "wrong", "review_reasons": ["low_confidence"]}]})
            support.save_edited_transcript(output, "[00:00:02 - 00:00:04] corrected")
            segment = json.loads(support.review_path(output).read_text(encoding="utf-8"))["segments"][0]
            self.assertEqual((segment["start"], segment["end"]), (2.125, 4.875))
            self.assertEqual(segment["reasons"], ["low_confidence"])

    def test_json_text_and_segments_must_not_disagree(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            output.write_text("original", encoding="utf-8")
            support.save_review(output, Path("source.wav"), {"segments": []})
            text = json.dumps({"text": "corrected", "segments": [{"start": 0, "end": 1, "text": "wrong"}]})
            with self.assertRaises(ValueError):
                support.save_edited_transcript(output, text)
            self.assertEqual(output.read_text(), "original")

    def test_edits_update_sidecar_in_all_supported_formats(self):
        formats = {
            ".txt": "[00:00:02 - 00:00:04] corrected\n",
            ".srt": "1\n00:00:02,000 --> 00:00:04,000\ncorrected\n",
            ".vtt": "WEBVTT\n\n00:00:02.000 --> 00:00:04.000\ncorrected\n",
            ".json": json.dumps({"text": "corrected", "segments": [{"start": 2, "end": 4, "text": "corrected"}]}),
        }
        with tempfile.TemporaryDirectory() as directory:
            for suffix, text in formats.items():
                output = Path(directory) / ("out" + suffix)
                output.write_text("original", encoding="utf-8")
                support.save_review(output, Path("source.wav"), {"segments": [
                    {"start": 2, "end": 4, "text": "wrong", "review_reasons": ["manual_review"]}]}, model="sensevoice")
                support.save_edited_transcript(output, text)
                data = json.loads(support.review_path(output).read_text(encoding="utf-8"))
                self.assertEqual(data["segments"][0]["text"], "corrected")
                self.assertEqual(data["segments"][0]["reasons"], ["manual_review"])
                self.assertEqual(data["options"]["model"], "sensevoice")
                self.assertEqual(output.read_text(encoding="utf-8"), text)
                self.assertTrue(support.review_matches_text(data, text))
                self.assertFalse(support.review_matches_text(data, text + "modified"))

    def test_invalid_timestamps_do_not_change_either_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.txt"
            output.write_text("original", encoding="utf-8")
            support.save_review(output, Path("source.wav"), {"segments": [{"start": 2, "end": 4, "text": "wrong"}]})
            original_review = support.review_path(output).read_bytes()
            with self.assertRaises(ValueError):
                support.save_edited_transcript(output, "timestamps removed")
            self.assertEqual(output.read_text(), "original")
            self.assertEqual(support.review_path(output).read_bytes(), original_review)

    def test_failed_replace_rolls_back_review(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.txt"
            output.write_text("original", encoding="utf-8")
            support.save_review(output, Path("source.wav"), {"segments": [{"start": 2, "end": 4, "text": "wrong"}]})
            original_review = support.review_path(output).read_bytes()
            replace = os.replace
            def fail_output(src, dest):
                if Path(dest) == output:
                    raise OSError("read only")
                return replace(src, dest)
            with patch("transcription_support.os.replace", side_effect=fail_output), self.assertRaises(OSError):
                support.save_edited_transcript(output, "[00:00:02 - 00:00:04] corrected\n")
            self.assertEqual(output.read_text(), "original")
            self.assertEqual(support.review_path(output).read_bytes(), original_review)


class StreamingAudioTests(unittest.TestCase):
    def test_duration_probe_only_returns_finite_positive_values(self):
        for raw, expected in (("83.2", 83.2), ("nan", 0), ("inf", 0), ("-1", 0), ("invalid", 0)):
            with patch("transcription_support.subprocess.run", return_value=Mock(stdout=raw)):
                self.assertEqual(support.audio_duration(Path("source.wav"), "ffprobe"), expected)
        self.assertEqual(support.audio_duration(Path("source.wav"), None), 0)

    def test_real_decoder_preserves_samples_and_last_partial_chunk(self):
        binary = core.ffmpeg_command(core.detect_tools())
        if not binary:
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "audio.wav"
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(bytes(16000 * 2 * 2 + 8000 * 2))
            chunks = list(support.iter_audio_chunks(source, binary, chunk_seconds=1))
            self.assertEqual([offset for offset, _ in chunks], [0, 1, 2])
            self.assertEqual([len(audio) for _, audio in chunks], [16000, 16000, 8000])
            with self.assertRaises(RuntimeError):
                list(support.iter_audio_chunks(source.with_name("missing.wav"), binary))

    def test_closing_decoder_terminates_child(self):
        process = Mock()
        process.stdout.read.return_value = np.zeros(16000, dtype="<f4").tobytes()
        process.poll.return_value = None
        with patch("transcription_support.subprocess.Popen", return_value=process):
            iterator = support.iter_audio_chunks(Path("source.wav"), "ffmpeg", chunk_seconds=1)
            next(iterator)
            iterator.close()
        process.terminate.assert_called_once()
        process.wait.assert_called()
        process.stdout.close.assert_called_once()

    def test_whisper_processes_bounded_windows_and_offsets_segments(self):
        model = Mock()
        model.transcribe.side_effect = [
            {"text": "first", "language": "en", "segments": [{"start": 1, "end": 2, "text": "first"}]},
            {"text": "second", "language": "en", "segments": [{"start": 0, "end": 1, "text": "second"}]},
        ]
        whisper = Mock()
        whisper.load_model.return_value = model
        status = core.ToolStatus("ffmpeg", None, None, False, True, False, False)
        chunks = [(0, np.zeros(16000)), (600, np.zeros(16000))]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            with patch.dict("sys.modules", {"whisper": whisper}), patch.object(core, "detect_tools", return_value=status), patch("transcription_support.iter_audio_chunks", return_value=(chunk for chunk in chunks)) as decoder:
                core.transcribe_with_local_whisper(Path("source.wav"), output, model_name="small", language=None,
                                                   task="transcribe", verbose=False, output_format="json")
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["segments"][1]["start"], 600)
            self.assertEqual(model.transcribe.call_count, 2)
            self.assertEqual(decoder.call_args.kwargs["chunk_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
