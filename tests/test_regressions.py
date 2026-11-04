import json
import os
import tempfile
import subprocess
import time
import sys
import wave
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import video_text_extractor as core
from PySide6.QtWidgets import QApplication
from video_text_gui import VideoTextWindow, Job, VIDEO_EXTS


class ChunkTests(unittest.TestCase):
    def test_subtitle_detection_requires_structured_probe(self):
        status = core.ToolStatus(None, None, None, False, False, False, False)
        with self.assertRaisesRegex(SystemExit, "ffprobe"):
            core.subtitle_streams(Path("clip.mp4"), status)

    def test_silent_chunks_produce_valid_empty_vtt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.wav"
            source.write_bytes(b"audio")
            with patch.object(core, "split_audio_with_ffmpeg", return_value=[source]), patch.object(core, "transcribe_one_file", return_value='{"text":"","segments":[]}'):
                core.transcribe_audio(source, root / "out.vtt", None, model="whisper-1", language=None,
                                      prompt=None, response_format="vtt", max_upload_mb=0, chunk_seconds=10)
            self.assertEqual((root / "out.vtt").read_text(), "WEBVTT\n")

    def test_null_segments(self):
        result = core._parse_openai_verbose_transcript('{"text":"hello","segments":null}')
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.segments, [])

    def test_missing_chunk_timestamps_does_not_silently_drop_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.wav"
            source.write_bytes(b"audio")
            responses = [json.dumps({"text": "first", "segments": [{"start": 0, "end": 1, "text": "first"}]}),
                         json.dumps({"text": "second", "segments": []})]
            with patch.object(core, "split_audio_with_ffmpeg", return_value=[source, source]), patch.object(core, "transcribe_one_file", side_effect=responses):
                with self.assertRaises(SystemExit):
                    core.transcribe_audio(source, root / "out.srt", None, model="whisper-1", language=None,
                                          prompt=None, response_format="srt", max_upload_mb=0, chunk_seconds=10)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with patch.object(VideoTextWindow, "_refresh_runtime"):
            self.window = VideoTextWindow()
        self.window.output_dir.setText(str(self.root))

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_audio_supported(self):
        self.assertIn(".m4a", VIDEO_EXTS)

    def test_sensevoice_is_default_and_output_is_txt(self):
        self.assertEqual(self.window.mode_combo.currentData(), "sensevoice")
        self.assertEqual(self.window.output_combo.currentText(), "TXT")
        self.assertFalse(self.window.output_combo.isEnabled())
        job = Job(self.root / "input.wav", self.root / "output.txt", mode="sensevoice")
        command = self.window.command_for(job)
        self.assertEqual(command[command.index("--mode") + 1], "sensevoice")
        self.assertEqual(command[command.index("--format") + 1], "text")

    def test_new_audio_options_reach_cli(self):
        self.window._set_combo_data(self.window.mode_combo, "whisper")
        self.window._set_combo_data(self.window.channel_combo, "left")
        self.window.enhance_check.setChecked(True)
        self.window.terms_edit.setPlainText("DeepSeek, multi-agent")
        command = self.window.command_for(Job(self.root / "input.wav", self.root / "out.txt"))
        self.assertEqual(command[command.index("--audio-channel") + 1], "left")
        self.assertIn("--enhance-audio", command)
        self.assertEqual(command[command.index("--prompt") + 1], "DeepSeek, multi-agent")

    def test_each_task_has_its_own_progress(self):
        from video_text_gui import STATUS_RUNNING
        self.window.jobs = [Job(self.root / "one.wav", self.root / "one.txt", STATUS_RUNNING),
                            Job(self.root / "two.wav", self.root / "two.txt", STATUS_RUNNING)]
        self.window.refresh_table()
        self.window._parse_progress("[stage:transcribe]", 1)
        self.window._parse_progress("42%| progress 42/100", 1)
        self.assertEqual(self.window.jobs[1].progress, 42)
        self.assertIsNone(self.window.jobs[0].progress)
        self.assertIn("42%", self.window.table.item(1, 4).text())

    def test_native_player_loads_audio_and_seeks(self):
        source = self.root / "playback.wav"
        with wave.open(str(source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(bytes(96000))
        player = self.window.media_player
        player.set_source(source)
        deadline = time.monotonic() + 8
        while player.player.duration() == 0 and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertGreater(player.player.duration(), 2500)
        player.seek(1200)
        self.app.processEvents()
        self.assertAlmostEqual(player.player.position(), 1200, delta=50)
        player.speed.setCurrentIndex(0)
        self.assertEqual(player.player.playbackRate(), 0.5)

    def test_review_list_reads_sidecar_for_current_source(self):
        from transcription_support import save_review
        source, output = self.root / "input.wav", self.root / "out.txt"
        output.write_text("[00:00:02 - 00:00:04] words", encoding="utf-8")
        save_review(output, source, {"segments": [{"start": 2, "end": 4, "text": "words", "avg_logprob": -1.2}]})
        self.window.jobs = [Job(source, output)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        self.assertEqual(self.window.review_list.count(), 1)
        self.window.export_reading_copy()
        self.assertEqual((self.root / "out_reading.txt").read_text(), "words\n")
        self.assertIn("[00:00:02", output.read_text())

    def test_existing_transcript_is_not_overwritten_on_rerun(self):
        source = self.root / "input.wav"
        output = self.window.output_path_for(source)
        output.write_text("original", encoding="utf-8")
        self.window.jobs = [Job(source, output)]
        with patch.object(self.window, "_fill_parallel_slots"), patch.object(self.window, "_save_history_entry"):
            self.window.start_jobs()
        self.assertNotEqual(self.window.jobs[0].output, output)
        self.assertEqual(output.read_text(), "original")

    def test_same_stem_output_collision(self):
        a, b = self.root / "a" / "meeting.mp4", self.root / "b" / "meeting.mp4"
        self.window.jobs = [Job(a, self.root / "unused"), Job(b, self.root / "unused")]
        with patch.object(self.window, "refresh_table"):
            self.window.refresh_outputs()
        self.assertNotEqual(self.window.jobs[0].output, self.window.jobs[1].output)

    def test_placeholder_cannot_be_saved_as_transcript(self):
        out = self.root / "missing.txt"
        self.window.jobs = [Job(self.root / "input.wav", out)]
        with patch("video_text_gui.get_video_thumbnail", return_value=None):
            self.window.refresh_table()
        self.window.table.selectRow(0)
        self.window._save_preview()
        self.assertFalse(out.exists())

    def test_preview_drafts_stay_bound_to_their_file(self):
        first, second = self.root / "first.txt", self.root / "second.txt"
        first.write_text("first", encoding="utf-8")
        second.write_text("second", encoding="utf-8")
        self.window.jobs = [Job(self.root / "one.wav", first), Job(self.root / "two.wav", second)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        self.window.preview.insertPlainText("edited ")
        self.window.table.selectRow(1)
        self.assertEqual(self.window.preview.toPlainText(), "second")
        self.window.table.selectRow(0)
        self.assertIn("edited", self.window.preview.toPlainText())
        self.window._save_preview()
        self.assertIn("edited", first.read_text(encoding="utf-8"))
        self.assertEqual(second.read_text(encoding="utf-8"), "second")

    def test_skip_exited_process_cannot_overwrite_cancelled_status(self):
        from video_text_gui import STATUS_RUNNING, STATUS_CANCELLED
        from unittest.mock import Mock
        self.window.jobs = [Job(self.root / "one.wav", self.root / "out.txt", STATUS_RUNNING)]
        self.window.refresh_table()
        self.window.table.selectRow(0)
        process = Mock()
        process.poll.return_value = 0
        self.window.active_processes[0] = process
        self.window.skip_current()
        self.window._job_finished(0, 0)
        self.assertEqual(self.window.jobs[0].status, STATUS_CANCELLED)
        self.assertFalse(self.window.active_processes)

    def test_language_switch_and_mode_roundtrip(self):
        for mode in ("audio", "subtitle", "ocr", "auto", "whisper"):
            self.window._set_combo_data(self.window.mode_combo, mode)
            self.window._toggle_language()
        self.assertTrue(self.window.start_button.isEnabled())

    def test_real_parallel_subprocess_queue(self):
        from video_text_gui import STATUS_DONE
        self.window.jobs = [Job(self.root / f"input_{i}.wav", self.root / f"out_{i}.txt") for i in range(3)]
        self.window.max_parallel = 2
        def command(job):
            return [sys.executable, "-c", f"from pathlib import Path; Path({str(job.output)!r}).write_text('transcript', encoding='utf-8')"]
        with patch.object(self.window, "command_for", side_effect=command), patch.object(self.window, "_save_history_entry"):
            self.window.start_jobs()
            deadline = time.monotonic() + 15
            while (self.window.active_processes or self.window._next_waiting_index() is not None) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.02)
        self.assertTrue(all(job.status == STATUS_DONE for job in self.window.jobs))
        self.assertTrue(self.window.start_button.isEnabled())
        for job in self.window.jobs:
            self.assertEqual(job.output.read_text(), "transcript")

    def test_many_launch_failures_do_not_recurse(self):
        from video_text_gui import STATUS_FAILED
        self.window.jobs = [Job(self.root / f"missing_{i}.wav", self.root / f"out_{i}.txt") for i in range(1100)]
        with patch("video_text_gui.subprocess.Popen", side_effect=OSError("cannot launch")), patch.object(self.window, "refresh_table"), patch.object(self.window, "append_log"), patch.object(self.window, "finish_batch"):
            self.window._fill_parallel_slots()
        self.assertTrue(all(job.status == STATUS_FAILED for job in self.window.jobs))

    def test_real_subtitle_burn_special_path(self):
        from video_text_extractor import detect_tools, ffmpeg_command
        binary = ffmpeg_command(detect_tools())
        if not binary:
            self.skipTest("ffmpeg unavailable")
        folder = self.root / "test ' [sub]; (clip)"
        folder.mkdir()
        source, subtitle = folder / "video.mp4", folder / "captions.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\nTest\n", encoding="utf-8")
        subprocess.run([binary, "-v", "error", "-f", "lavfi", "-i", "color=size=160x90:duration=1",
                        "-c:v", "libx264", str(source)], check=True, capture_output=True)
        with patch("video_text_gui.QFileDialog.getOpenFileName", side_effect=[(str(source), ""), (str(subtitle), "")]):
            self.window.burn_subtitles()
        self.assertIsNotNone(self.window.burn_process)
        deadline = time.monotonic() + 30
        while self.window.burn_process is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertIsNone(self.window.burn_process)
        self.assertGreater((folder / "video_subtitled.mp4").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
