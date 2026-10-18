"""Recovery child ownership startup-failure cleanup, generated stages only."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import os
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from defiantmaple import recovery
from defiantmaple.catalog import initialize


class AdmissionRecoveryTests(unittest.TestCase):
    def test_post_start_retention_failure_still_kills_child_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "generated.stage"
            stage.write_bytes(b"generated staging")
            state = {"alive": False}
            def started():
                state["alive"] = True
            def killed():
                state["alive"] = False
            process = SimpleNamespace(start=Mock(side_effect=started),
                                      is_alive=lambda: state["alive"], kill=Mock(side_effect=killed), join=Mock())
            receive, send = Mock(), Mock()
            context = SimpleNamespace(Pipe=lambda **_: (receive, send), Event=threading.Event,
                                      Process=lambda **_: process)
            owner = SimpleNamespace(retain_process=Mock(side_effect=RuntimeError("generated retention failure")))
            with patch.object(recovery.multiprocessing, "get_context", return_value=context), \
                 patch.object(recovery, "current_session", return_value=owner), \
                 patch.object(recovery, "reap_recovery_workers", return_value={"remaining_workers": 0}):
                with self.assertRaisesRegex(RuntimeError, "retention failure"):
                    recovery._run("backup", (root / "catalog.sqlite3",), (stage,), root / "package.dmbackup")
            process.start.assert_called_once()
            owner.retain_process.assert_called_once_with(process)
            process.kill.assert_called_once()
            self.assertFalse(stage.exists())
            receive.close.assert_called_once()
            send.close.assert_called_once()

    def test_readonly_backup_identity_guard_preserves_only_native_contention(self):
        for code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED,
                     sqlite3.SQLITE_BUSY | (2 << 8), sqlite3.SQLITE_LOCKED | (1 << 8),
                     sqlite3.SQLITE_ERROR, None):
            with self.subTest(code=code):
                native = sqlite3.OperationalError("generated sqlite failure")
                if code is not None:
                    native.sqlite_errorcode = code
                wrapped = ValueError("Library identity schema is missing or invalid")
                wrapped.__cause__ = native
                with patch.object(recovery, "require_current_catalog", side_effect=wrapped):
                    with self.assertRaises(Exception) as captured:
                        recovery._require_backup_catalog(object())
                expected = native if code is not None and code & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else wrapped
                self.assertIs(captured.exception, expected)
        generic = ValueError("database is locked")
        with patch.object(recovery, "require_current_catalog", side_effect=generic):
            with self.assertRaises(ValueError) as captured:
                recovery._require_backup_catalog(object())
        self.assertIs(captured.exception, generic)

    def test_readonly_backup_authenticates_schema_and_identity_before_source_roots(self):
        @contextmanager
        def generated_parent(leaf):
            descriptor = os.open(Path(leaf).parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                yield Path(leaf), descriptor
            finally:
                os.close(descriptor)

        if not hasattr(os, "O_DIRECTORY"):
            self.skipTest("This generated dirfd guard oracle exercises POSIX backup admission")
        for corruption in ("malformed_identity", "future_schema"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                catalog = root / "generated.sqlite3"
                initialize(catalog)
                db = sqlite3.connect(catalog)
                try:
                    if corruption == "future_schema":
                        db.execute("PRAGMA user_version=999")
                    else:
                        trigger = db.execute("SELECT sql FROM sqlite_master WHERE name='library_identity_no_update'").fetchone()[0]
                        db.execute("DROP TRIGGER library_identity_no_update")
                        db.execute("PRAGMA ignore_check_constraints=ON")
                        db.execute("UPDATE library_identity SET library_id='generated-invalid-uuid'")
                        db.execute(trigger)
                    db.commit()
                finally:
                    db.close()
                before = hashlib.sha256(catalog.read_bytes()).hexdigest()
                package, snapshot, stage = (root / name for name in ("generated.dmbackup", "snapshot", "stage"))
                with patch.object(recovery, "private_local_parent", generated_parent), \
                     patch.object(recovery, "_source_roots", side_effect=AssertionError("userdata query reached")) as roots:
                    with self.assertRaises(ValueError):
                        recovery._backup_worker(catalog, package, snapshot, stage, (), threading.Event(), 1)
                roots.assert_not_called()
                self.assertEqual(hashlib.sha256(catalog.read_bytes()).hexdigest(), before)
                self.assertEqual({p.name for p in root.iterdir()}, {catalog.name})


if __name__ == "__main__":
    unittest.main()
