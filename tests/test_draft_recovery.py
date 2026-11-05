import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import draft_recovery
from draft_recovery import DraftRecovery, RecoveryBatch, text_digest


class DraftRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "recovery"
        self.entry = {
            "output": str(self.root / "transcript.txt"),
            "source": str(self.root / "recording.wav"),
            "text": "private unsaved draft\nsecond line",
            "base_hash": "a" * 64,
            "base_stamp": [0, 123456789],
            "mode": "transcript",
        }

    def store(self):
        store = DraftRecovery(self.directory)
        self.addCleanup(store.close)
        return store

    def orphan(self, entries=None):
        store = self.store()
        store.save([self.entry] if entries is None else entries)
        path = self.directory / (store.session_id + ".json")
        store.close(discard=False)
        return path

    def scan(self, store):
        batches = store.scan()
        for batch in batches:
            self.addCleanup(batch.release)
        return batches

    def child_scan(self):
        script = (
            "import json, sys; from pathlib import Path; "
            "from draft_recovery import DraftRecovery; "
            "s = DraftRecovery(Path(sys.argv[1])); b = s.scan(); "
            "print(json.dumps([x.path.name for x in b])); "
            "[x.release() for x in b]; s.close()"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(self.directory)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=15, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_digest_normalizes_crlf_but_preserves_other_text(self):
        expected = hashlib.sha256(b"first\nsecond\n").hexdigest()
        self.assertEqual(text_digest("first\r\nsecond\r\n"), expected)
        self.assertEqual(text_digest("first\nsecond\n"), expected)
        self.assertNotEqual(text_digest("first\rsecond\n"), expected)
        self.assertNotEqual(text_digest("first\nsecond"), expected)
        self.assertEqual(text_digest("\u4e2d\u6587"), hashlib.sha256("\u4e2d\u6587".encode()).hexdigest())

    def test_creates_directory_unique_uuid_sessions_and_snapshot(self):
        first, second = self.store(), self.store()
        self.assertEqual(str(uuid.UUID(first.session_id)), first.session_id)
        self.assertNotEqual(first.session_id, second.session_id)
        first.save([self.entry])
        path = self.directory / (first.session_id + ".json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {
            "version": 1, "session_id": first.session_id, "drafts": [self.entry],
        })
        self.assertTrue((self.directory / (first.session_id + ".lock")).is_file())

    def test_empty_save_removes_only_own_snapshot(self):
        orphan = self.orphan()
        store = self.store()
        store.save([self.entry])
        store.save([])
        store.save([])
        self.assertFalse((self.directory / (store.session_id + ".json")).exists())
        self.assertTrue(orphan.exists())

    def test_failed_replace_preserves_previous_snapshot_and_cleans_temp(self):
        store = self.store()
        store.save([self.entry])
        path = self.directory / (store.session_id + ".json")
        previous = path.read_bytes()
        before = set(self.directory.iterdir())
        updated = dict(self.entry, text="newer private draft")
        temp_paths = []

        def fail_replace(source, target):
            temp_paths.append(Path(source))
            self.assertEqual(Path(source).parent, self.directory)
            self.assertEqual(Path(target), path)
            self.assertNotEqual(Path(source), path)
            raise OSError("replace failed")

        for _ in range(2):
            with patch.object(draft_recovery.os, "replace", side_effect=fail_replace):
                with self.assertRaises(OSError):
                    store.save([updated])
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(set(self.directory.iterdir()), before)
        self.assertNotEqual(temp_paths[0], temp_paths[1])

    def test_live_sessions_and_current_session_are_ignored(self):
        first, second = self.store(), self.store()
        first.save([self.entry])
        second.save([self.entry])
        self.assertEqual(self.scan(first), [])
        self.assertEqual(self.scan(second), [])
        self.assertEqual(self.child_scan(), [])

    def test_failed_sync_preserves_previous_snapshot_and_cleans_temp(self):
        store = self.store()
        store.save([self.entry])
        path = self.directory / (store.session_id + ".json")
        previous = path.read_bytes()
        before = set(self.directory.iterdir())
        with patch.object(draft_recovery.os, "fsync", side_effect=OSError("sync failed")):
            with self.assertRaises(OSError):
                store.save([dict(self.entry, text="new draft")])
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_retained_snapshot_is_recoverable_after_close(self):
        path = self.orphan()
        batches = self.scan(self.store())
        self.assertEqual(len(batches), 1)
        self.assertIsInstance(batches[0], RecoveryBatch)
        self.assertEqual(batches[0].path, path)
        self.assertEqual(batches[0].drafts, [self.entry])

    def test_crashed_process_snapshot_is_recoverable(self):
        script = (
            "import json, os, sys; from pathlib import Path; "
            "from draft_recovery import DraftRecovery; "
            "s = DraftRecovery(Path(sys.argv[1])); "
            "s.save(json.loads(sys.argv[2])); os._exit(0)"
        )
        subprocess.run(
            [sys.executable, "-B", "-c", script, str(self.directory), json.dumps([self.entry])],
            cwd=Path(__file__).resolve().parents[1], timeout=15, check=True,
            capture_output=True,
        )
        self.assertEqual(self.scan(self.store())[0].drafts, [self.entry])

    def test_claim_excludes_same_store_other_store_and_other_process(self):
        path = self.orphan()
        scanner = self.store()
        batch = self.scan(scanner)[0]
        self.assertEqual(self.scan(scanner), [])
        self.assertEqual(self.scan(self.store()), [])
        self.assertEqual(self.child_scan(), [])
        batch.release()
        self.assertEqual(self.child_scan(), [path.name])
        batch.release()
        self.assertTrue(path.exists())

    def test_discard_removes_only_claimed_snapshot_and_retains_lock_files(self):
        path = self.orphan()
        live = self.store()
        live.save([dict(self.entry, text="other live draft")])
        live_path = self.directory / (live.session_id + ".json")
        previous = live_path.read_bytes()
        batch = self.scan(self.store())[0]
        batch.discard()
        batch.discard()
        batch.release()
        self.assertFalse(path.exists())
        self.assertEqual(live_path.read_bytes(), previous)
        self.assertTrue(path.with_suffix(".lock").exists())

    def test_close_discards_only_own_snapshot_not_claimed_orphan(self):
        path = self.orphan()
        store = self.store()
        store.save([self.entry])
        batch = self.scan(store)[0]
        store.close()
        self.assertFalse((self.directory / (store.session_id + ".json")).exists())
        self.assertTrue(path.exists())
        self.assertEqual(self.child_scan(), [])
        batch.release()
        self.assertEqual(self.child_scan(), [path.name])

    def test_close_is_idempotent_and_save_or_scan_after_close_raise(self):
        store = self.store()
        store.save([self.entry])
        store.close(discard=False)
        store.close()
        self.assertTrue((self.directory / (store.session_id + ".json")).exists())
        with self.assertRaises(RuntimeError):
            store.save([])
        with self.assertRaises(RuntimeError):
            store.scan()

    def test_released_batch_cannot_delete_new_claimants_snapshot(self):
        path = self.orphan()
        old = self.scan(self.store())[0]
        old.release()
        current = self.scan(self.store())[0]
        old.discard()
        self.assertTrue(path.exists())
        self.assertEqual(self.child_scan(), [])
        current.discard()
        self.assertEqual(self.child_scan(), [])

    def test_malformed_snapshots_are_skipped_without_deletion(self):
        scanner = self.store()
        invalid_entries = [None, "text", {}, dict(self.entry, output=1),
                           dict(self.entry, source=None), dict(self.entry, text=[]),
                           dict(self.entry, base_hash="x" * 64),
                           dict(self.entry, base_hash="a" * 63),
                           dict(self.entry, base_stamp=[-1, 0]),
                           dict(self.entry, base_stamp=[0, True]),
                           dict(self.entry, base_stamp=[0, 1.5]),
                           dict(self.entry, base_stamp=[0]),
                           dict(self.entry, mode=3)]
        payloads = [None, [], {"version": 2, "drafts": []},
                    {"version": True, "drafts": []},
                    {"version": 1, "drafts": {}},
                    {"version": 1, "drafts": [], "session_id": "mismatch"}]
        payloads.extend({"version": 1, "drafts": [self.entry, entry]} for entry in invalid_entries)
        paths = []
        for payload in payloads:
            session_id = str(uuid.uuid4())
            path = self.directory / (session_id + ".json")
            if isinstance(payload, dict) and "session_id" not in payload:
                payload = dict(payload, session_id=session_id)
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths.append(path)
        for content in (b"{broken", b"\xff\xfe"):
            path = self.directory / (str(uuid.uuid4()) + ".json")
            path.write_bytes(content)
            paths.append(path)
        before = {path: path.read_bytes() for path in paths}
        valid = self.orphan()
        self.assertEqual([batch.path for batch in self.scan(scanner)], [valid])
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_optional_mode_may_be_absent_and_uppercase_hash_is_valid(self):
        entry = dict(self.entry, base_hash="ABCDEF01" * 8)
        del entry["mode"]
        self.orphan([entry])
        self.assertEqual(self.scan(self.store())[0].drafts, [entry])

    def test_invalid_save_raises_without_replacing_previous_snapshot(self):
        store = self.store()
        store.save([self.entry])
        path = self.directory / (store.session_id + ".json")
        previous = path.read_bytes()
        for entries in (None, {}, [dict(self.entry, base_hash="bad")], [dict(self.entry, base_stamp=[True, 0])]):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    store.save(entries)
                self.assertEqual(path.read_bytes(), previous)

    def test_directory_io_errors_propagate(self):
        blocker = self.root / "not-a-directory"
        blocker.write_text("block", encoding="utf-8")
        with self.assertRaises(OSError):
            DraftRecovery(blocker / "recovery")
        store = self.store()
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                store.scan()
        path = self.orphan()
        real_open = Path.open

        def denied_open(target, *args, **kwargs):
            if target == path:
                raise PermissionError("denied")
            return real_open(target, *args, **kwargs)

        with patch.object(Path, "open", denied_open):
            with self.assertRaises(PermissionError):
                store.scan()
        self.assertEqual([batch.path for batch in self.scan(store)], [path])

    def test_failed_discard_keeps_claim_until_success(self):
        path = self.orphan()
        batch = self.scan(self.store())[0]
        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                batch.discard()
        self.assertEqual(self.child_scan(), [])
        batch.discard()
        self.assertFalse(path.exists())

    def test_scan_failure_releases_all_unreturned_claims(self):
        paths = sorted([self.orphan(), self.orphan()])
        scanner = self.store()
        real_open = Path.open

        def fail_second(target, *args, **kwargs):
            if target == paths[1]:
                raise PermissionError("denied")
            return real_open(target, *args, **kwargs)

        with patch.object(Path, "open", fail_second):
            with self.assertRaises(PermissionError):
                scanner.scan()
        self.assertEqual(self.child_scan(), [path.name for path in paths])

    def test_no_target_access_output_or_text_outside_recovery_files(self):
        output = Path(self.entry["output"])
        source = Path(self.entry["source"])
        output.write_bytes(b"original transcript")
        source.write_bytes(b"fake media sentinel")
        stdout, stderr = io.StringIO(), io.StringIO()
        real_open = io.open

        def recovery_only(file, *args, **kwargs):
            if not isinstance(file, int):
                self.assertTrue(Path(file).is_relative_to(self.directory))
            return real_open(file, *args, **kwargs)

        entry = copy.deepcopy(self.entry)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with patch("io.open", side_effect=recovery_only):
                store = self.store()
                store.save([entry])
                store.close(discard=False)
                batch = self.scan(self.store())[0]
        self.assertEqual(batch.drafts, [self.entry])
        self.assertEqual(entry, self.entry)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(output.read_bytes(), b"original transcript")
        self.assertEqual(source.read_bytes(), b"fake media sentinel")
        for path in self.directory.iterdir():
            if path.suffix != ".json":
                self.assertEqual(path.stat().st_size, 0)
        self.assertEqual(set(self.root.iterdir()), {output, source, self.directory})


if __name__ == "__main__":
    unittest.main()
