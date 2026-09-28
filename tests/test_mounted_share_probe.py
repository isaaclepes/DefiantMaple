"""Owned local fixtures only; these tests do not validate a network protocol."""
from __future__ import annotations

import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmarks import mounted_share_probe as probe


class MountedShareProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="defiantmaple-probe-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.scratch = self.base / "scratch"
        self.scratch.mkdir()
        self.local = self.base / "local-session"

    def session(self):
        return probe.new_session(self.scratch, self.local, count=128)

    def prepare(self):
        state = self.session()
        return probe._perform(state, "prepare")

    def test_parent_contents_are_not_scanned_or_deleted(self):
        outsider = self.scratch / "untouched-private-sentinel.png"
        outsider.write_bytes(b"not an input fixture")
        nested = self.scratch / "preexisting-directory"
        nested.mkdir()
        (nested / "keep").write_text("keep", encoding="utf-8")
        state = self.prepare()
        self.assertEqual(len(probe._snapshot(state)["assets"]), 128)
        root = Path(state["fixture_root"])
        self.assertNotEqual(root, self.scratch)
        probe._perform(state, "cleanup")
        self.assertFalse(root.exists())
        self.assertEqual(outsider.read_bytes(), b"not an input fixture")
        self.assertEqual((nested / "keep").read_text(), "keep")
        self.assertTrue(self.local.exists())

    def test_refuse_reused_relative_nested_and_repository_state(self):
        self.session()
        with self.assertRaisesRegex(ValueError, "new directory"):
            self.session()
        with self.assertRaisesRegex(ValueError, "absolute"):
            probe.new_session(Path("scratch"), self.base / "other")
        with self.assertRaisesRegex(ValueError, "outside"):
            probe.new_session(self.scratch, self.scratch / "catalog")
        with self.assertRaisesRegex(ValueError, "outside"):
            probe.new_session(self.scratch, Path(probe.__file__).resolve().parents[1] / "unsafe-session")
        for count in (0, 64, 127, True, 100001):
            with self.subTest(count=count), self.assertRaises(ValueError):
                probe.new_session(self.scratch, self.base / "unused", count=count)

    def test_substituted_marker_unknown_members_and_modified_files_block_cleanup(self):
        state = self.prepare()
        root = Path(state["fixture_root"])
        marker = root / probe.MARKER_NAME
        correct = marker.read_text()
        marker.write_text("{}")
        with self.assertRaisesRegex(ValueError, "marker"):
            probe._perform(state, "cleanup")
        marker.write_text(correct)
        stranger = root / "not-owned.txt"
        stranger.write_text("keep")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            probe._perform(state, "cleanup")
        stranger.unlink()
        path = root / next(iter(state["manifest"]))
        path.write_bytes(b"changed fixture")
        with self.assertRaisesRegex(ValueError, "changed"):
            probe._perform(state, "cleanup")
        self.assertTrue(marker.exists())
        self.assertTrue(path.exists())

    def test_symlink_marker_and_directory_are_rejected(self):
        state = self.prepare()
        root = Path(state["fixture_root"])
        marker = root / probe.MARKER_NAME
        backup = self.base / "marker-backup"
        marker.rename(backup)
        try:
            marker.symlink_to(backup)
        except (OSError, NotImplementedError):
            backup.rename(marker)
            self.skipTest("This host cannot create test symlinks")
        with self.assertRaisesRegex(ValueError, "marker"):
            probe._perform(state, "cleanup")
        marker.unlink()
        backup.rename(marker)
        extra = root / "linked-directory"
        extra.symlink_to(self.scratch, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            probe._perform(state, "cleanup")
        extra.unlink()
        probe._perform(state, "cleanup")

    def test_root_substitution_before_destructive_member_check_preserves_outsider(self):
        state = self.prepare()
        root = Path(state["fixture_root"])
        saved = self.base / "original-owned-root"
        outsider = self.base / "unowned-directory"
        (outsider / "baseline").mkdir(parents=True)
        sentinel = outsider / "baseline" / "fictional-000000.png"
        sentinel.write_bytes(b"unowned sentinel must survive")
        # First ensure this host supports a directory symlink.
        trial_link = self.base / "trial-link"
        try:
            trial_link.symlink_to(outsider, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("This host cannot create test symlinks")
        trial_link.unlink()
        real_safe_file = probe._safe_file
        calls = 0

        def substitute_before_first_unlink(actual_root, relative):
            nonlocal calls
            calls += 1
            # _inventory validates all members first. Substitute immediately
            # before the first destructive member check, reproducing the review.
            if calls == len(state["manifest"]) + 1:
                root.rename(saved)
                root.symlink_to(outsider, target_is_directory=True)
            return real_safe_file(actual_root, relative)

        with patch.object(probe, "_safe_file", side_effect=substitute_before_first_unlink):
            with self.assertRaisesRegex(ValueError, "substituted"):
                probe._perform(state, "cleanup")
        self.assertEqual(sentinel.read_bytes(), b"unowned sentinel must survive")
        self.assertEqual(len(list((saved / "baseline").iterdir())), 128)
        root.unlink()
        saved.rename(root)
        probe._perform(state, "cleanup")

    def test_unmeasured_baseline_is_not_reported_as_configured_count(self):
        state = self.session()
        report = probe.public_report(state)
        self.assertIsNone(report["baseline_assets"])
        self.assertEqual(report["configured_count"], 128)
        self.assertEqual(report["fixture_files"], 0)
        state = probe._perform(state, "prepare")
        self.assertEqual(probe.public_report(state)["baseline_assets"], 128)

    def test_protocol_labels_require_evidence_and_never_infer_from_path(self):
        with self.assertRaisesRegex(ValueError, "cannot attest"):
            probe.new_session(self.scratch, self.local, count=128, protocol="smb")
        with self.assertRaisesRegex(ValueError, "requires local operator evidence"):
            probe.new_session(self.scratch, self.local, count=128,
                              environment_kind="mounted_scratch", protocol="smb")
        evidence = self.base / "mount.private.txt"
        evidence.write_text("Operator captured protocol verification outside harness.")
        state = probe.new_session(self.scratch, self.local, count=128,
                                  environment_kind="mounted_scratch", protocol="smb",
                                  mount_evidence=evidence)
        report = probe.public_report(state)
        self.assertEqual(report["protocol_evidence"], "operator_attested")
        self.assertFalse(report["protocol_independently_verified_by_harness"])
        self.assertEqual(len(report["mount_evidence_sha256"]), 64)

    def test_retention_checks_actual_uuid_and_pending_progression(self):
        before = {"assets": ["original-uuid"], "entries": {
            "indexed": {"asset_id": "original-uuid", "disposition": "indexed"},
            "pending": {"asset_id": None, "disposition": "pending"}}}
        after = {"assets": ["original-uuid", "new-uuid"], "entries": {
            "indexed": {"asset_id": "original-uuid", "disposition": "indexed"},
            "pending": {"asset_id": "new-uuid", "disposition": "indexed"}}}
        self.assertTrue(probe._retained(before, after))
        after["assets"] = ["replacement-uuid", "new-uuid"]
        after["entries"]["indexed"]["asset_id"] = "replacement-uuid"
        self.assertFalse(probe._retained(before, after))
        after["assets"] = ["original-uuid", "new-uuid"]
        after["entries"]["indexed"]["asset_id"] = "original-uuid"
        after["entries"]["pending"]["disposition"] = "missing"
        self.assertFalse(probe._retained(before, after))

    def test_out_of_order_and_successfully_cached_interrupt_are_inconclusive(self):
        state = self.prepare()
        for action in ("offline", "recover"):
            with self.assertRaisesRegex(ValueError, "protocol order"):
                probe._perform(state, action)
        reached = []
        result = probe._perform(state, "interrupt", gate=reached.append)
        self.assertEqual(reached, ["observation"])
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(probe.public_report(result)["complete"])
        with self.assertRaisesRegex(ValueError, "protocol order"):
            probe._perform(result, "recover")

    def test_local_loss_recovery_checks_both_phases_and_stable_uuids(self):
        # Renaming this generated child is local synthetic loss, never SMB/NFS.
        state = self.session()
        state = probe.execute(self.local, "prepare", timeout=120)
        original = set(probe._snapshot(state)["assets"])
        for phase in ("observation", "indexing"):
            with self.subTest(phase=phase):
                saved = self.base / f"unavailable-{phase}"

                def disconnect(actual_phase, _timeout):
                    self.assertEqual(actual_phase, phase)
                    private = probe._load(self.local)
                    Path(private["fixture_root"]).rename(saved)
                    return True

                state = probe.execute(self.local, "interrupt", timeout=120, confirm=disconnect)
                self.assertEqual(state["status"], f"{phase}_interrupted")
                self.assertTrue(original.issubset(probe._snapshot(state)["assets"]))
                state = probe.execute(self.local, "offline", timeout=120)
                self.assertEqual(state["status"], f"{phase}_offline")
                saved.rename(Path(state["fixture_root"]))
                state = probe.execute(self.local, "recover", timeout=120)
        report = probe.public_report(state)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(probe._snapshot(state)["assets"]), 256)
        self.assertEqual(len(probe._snapshot(state)["entries"]), 257)  # marker is unsupported
        self.assertEqual(report["environment_kind"], "local_fixture")
        self.assertEqual(report["protocol"], "unknown")
        self.assertEqual(report["protocol_evidence"], "not_tested")
        self.assertTrue(all(event["uuid_set_retained"] for trial in report["trials"]
                            for event in trial["events"]))
        rendered = json.dumps(report)
        self.assertNotIn(str(self.base), rendered)
        self.assertNotIn(state["session_id"], rendered)
        self.assertNotIn(next(iter(original)), rendered)
        state = probe.execute(self.local, "cleanup", timeout=120)
        self.assertTrue(state["cleaned"])

    def test_unconfirmed_gate_stops_without_claiming_offline_or_recovery(self):
        state = self.prepare()
        before = probe._snapshot(state)
        result = probe.execute(self.local, "interrupt", timeout=120,
                               confirm=lambda _phase, _timeout: False)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(probe._snapshot(result), before)
        probe._inventory(result)
        report = probe.public_report(result)
        self.assertFalse(report["complete"])
        self.assertEqual(report["timed_out_actions"], ["interrupt"])
        self.assertEqual(report["trials"][0]["events"], [])

    def test_public_report_allowlists_events_and_nested_scan_fields(self):
        state = self.prepare()
        state["events"].append({"phase": "observation", "action": "interrupt",
                                "private_path": "/private/should-never-publish",
                                "asset_id": "private-uuid", "scan": {
                                    "complete": False, "canceled": False, "health": "offline",
                                    "errors": [{"path": "/private/should-never-publish"}],
                                    "totals": {"missing": 0, "private": "/private/should-never-publish"}}})
        rendered = json.dumps(probe.public_report(state))
        self.assertNotIn("should-never-publish", rendered)
        self.assertNotIn("private-uuid", rendered)
        self.assertNotIn("errors", rendered)

    def test_timeout_reaps_worker_and_refuses_further_protocol_progress(self):
        self.session()
        state = probe.execute(self.local, "prepare", timeout=0.001)
        self.assertEqual(state["status"], "inconclusive")
        self.assertFalse((self.local / probe.WORKER_LOCK).exists())
        self.assertEqual(probe.public_report(state)["timed_out_actions"], ["prepare"])
        with self.assertRaisesRegex(ValueError, "protocol order"):
            probe.execute(self.local, "interrupt")
        for timeout in (0, -1, math.inf, math.nan, 3601):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                probe.execute(self.local, "cleanup", timeout=timeout)

    def test_unreapable_worker_keeps_lock_and_cannot_export_success(self):
        state = self.prepare()
        worker = Mock()
        worker.pid = 12345
        worker.stdin = io.StringIO()
        worker.stdout = io.StringIO()
        worker.poll.return_value = None
        worker.wait.side_effect = subprocess.TimeoutExpired("fixed worker", 2)
        with patch.object(probe.subprocess, "Popen", return_value=worker):
            result = probe.execute(self.local, "cleanup", timeout=0.001)
        self.assertEqual(result["status"], "blocked_worker")
        self.assertTrue((self.local / probe.WORKER_LOCK).exists())
        worker.terminate.assert_called_once()
        worker.kill.assert_called_once()
        # Even stale persisted completion must not be exported as success.
        state["status"] = "complete"
        probe._save(state)
        report = probe.public_report(probe._load(self.local))
        self.assertEqual(report["status"], "worker_active_or_unreaped")
        self.assertFalse(report["complete"])
        with self.assertRaises(FileExistsError):
            probe.execute(self.local, "cleanup")

    def test_done_message_followed_by_failed_exit_is_inconclusive(self):
        self.prepare()
        worker = Mock()
        worker.pid = 12345
        worker.stdin = io.StringIO()
        worker.stdout = io.StringIO('{"kind": "done", "status": "complete"}\n')
        worker.poll.return_value = 1
        worker.returncode = 1
        with patch.object(probe.subprocess, "Popen", return_value=worker):
            result = probe.execute(self.local, "cleanup", timeout=1)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse((self.local / probe.WORKER_LOCK).exists())
        self.assertFalse(probe.public_report(result)["complete"])

    def test_worker_lock_prevents_cleanup_or_a_second_worker(self):
        state = self.prepare()
        lock = self.local / probe.WORKER_LOCK
        lock.write_text("Unreaped worker")
        report = probe.public_report(state)
        self.assertEqual(report["status"], "worker_active_or_unreaped")
        self.assertFalse(report["complete"])
        with self.assertRaises(FileExistsError):
            probe.execute(self.local, "cleanup")
        self.assertTrue(Path(state["fixture_root"]).exists())


if __name__ == "__main__":
    unittest.main()
