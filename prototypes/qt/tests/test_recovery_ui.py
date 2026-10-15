"""Generated catalog recovery and child-time original refusal checks."""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from defiantmaple.catalog import (RESTORE_PENDING_APPLICATION_ID, initialize, index_file,
                                  restored_root_review_detail)
from defiantmaple.recovery import backup_metadata, restore_metadata
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.sources import add_source
from prototypes.qt.preview import PreviewLimits, _decode_original
from prototypes.qt.recovery_qt import RecoveryDialog, _identity
from prototypes.qt.app import AssetModel, GalleryWindow
from prototypes.qt.tests.gallery_wait import wait_for_startup_validation


class _Sender:
    def __init__(self):
        self.value = None

    def send(self, value):
        self.value = value

    def close(self):
        pass


class RecoveryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "live.sqlite3"
        self.package = self.root / "backup.dmbackup"
        self.restored = self.root / "restored.sqlite3"
        (self.root / "media").mkdir(mode=0o700)
        self.media = self.root / "media" / "fictional.png"
        Image.new("RGB", (2, 2), "purple").save(self.media)
        initialize(self.database)
        self.asset_id = index_file(self.database, self.media)
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            self.asset = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (self.asset_id,)).fetchone())

    def _spin(self, predicate, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(.01)
        return False

    def _mark_restore_pending(self):
        """Construct generated pending state without exercising native publication."""
        with closing(sqlite3.connect(self.database)) as source_db, \
                closing(sqlite3.connect(self.restored)) as db:
            source_db.backup(db)
            db.execute(f"PRAGMA application_id={RESTORE_PENDING_APPLICATION_ID}")
            rows = db.execute("SELECT source_id,root_path FROM sources").fetchall()
            for source_id, root_path in rows:
                db.execute("UPDATE sources SET enabled=0,health='paused',health_detail=? WHERE source_id=?",
                           (restored_root_review_detail(source_id, root_path), source_id))
            db.commit()

    def _require_native_publication(self):
        try:
            with private_local_parent(self.root / ".native-capability-probe"):
                pass
        except ValueError as exc:
            detail = str(exc)
            if detail == "Recovery publication has no reviewed native adapter on this platform":
                self.skipTest(f"Native Qt backup/restore requires the reviewed Linux PCIe NVMe adapter; {detail}")
            if detail == "Recovery requires a verified durable local filesystem":
                self.skipTest(f"Native Qt backup/restore requires reviewed PCIe NVMe backing; {detail}")
            raise

    def test_restored_pending_child_refuses_before_original_open(self):
        self._mark_restore_pending()
        sender = _Sender()
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == self.media:
                self.fail("Pending restored catalog opened original media")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open):
            _decode_original(self.restored, _identity(self.restored), self.asset,
                             str(self.root / "decoded.png"), PreviewLimits(), sender)
        self.assertIsNone(sender.value[0])
        self.assertIn("browse-only", sender.value[1])
        self.assertFalse((self.root / "decoded.png").exists())

    def test_dialog_worker_restore_preserves_active_catalog_and_reports_standalone_limit(self):
        self._require_native_publication()
        original_identity = _identity(self.database)
        dialog = RecoveryDialog(self.database, (self.root / "cache",))
        self.addCleanup(dialog.close)
        dialog._start("backup", output=self.package)
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertTrue(self.package.exists(), dialog.report.toPlainText())
        dialog._start("inspect", package=self.package, package_identity=_identity(self.package))
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertIn("Digest and catalog integrity: verified", dialog.report.toPlainText())
        dialog._start("restore", package=self.package, package_identity=_identity(self.package),
                      output=self.restored)
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertTrue(self.restored.exists(), dialog.report.toPlainText())
        self.assertEqual(_identity(self.database), original_identity)
        self.assertEqual(dialog.database, self.database)
        restored_dialog = RecoveryDialog(self.restored, (self.root / "cache",))
        self.addCleanup(restored_dialog.close)
        restored_dialog.load_mapping()
        self.assertTrue(self._spin(lambda: restored_dialog.worker is None))
        self.assertEqual(restored_dialog.mapping["state"], "restore_pending")
        self.assertEqual(restored_dialog.mapping["standalone_assets"], 1)
        restored_dialog.activate()
        self.assertIn("durable relink review", restored_dialog.status.text())
        self.assertFalse(restored_dialog.report.toPlainText().find("defiantmaple:restored-root-review") >= 0)

    def test_linked_root_review_leaves_hold_and_sources_disabled(self):
        self.database.unlink()
        initialize(self.database)
        source = add_source(self.database, self.media.parent)
        index_file(self.database, self.media, source_id=source["source_id"])
        self._mark_restore_pending()
        dialog = RecoveryDialog(self.restored, (self.root / "cache",))
        self.addCleanup(dialog.close)
        dialog.load_mapping()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertEqual(len(dialog.mapping["sources"]), 1)
        self.assertTrue(dialog.mapping["sources"][0]["held"])
        with patch("prototypes.qt.recovery_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes):
            dialog.activate()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        dialog.load_mapping()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertEqual(dialog.mapping["state"], "active")
        self.assertFalse(dialog.mapping["sources"][0]["enabled"])
        self.assertTrue(dialog.mapping["sources"][0]["held"])

    def test_qt_per_source_enable_clears_only_selected_reviewed_hold(self):
        if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
            self.skipTest("Qt per-source enable proof requires POSIX effective-ID and O_DIRECTORY semantics")
        self.database.unlink()
        initialize(self.database)
        source = add_source(self.database, self.media.parent)
        index_file(self.database, self.media, source_id=source["source_id"])
        self._mark_restore_pending()
        dialog = RecoveryDialog(self.restored, (self.root / "cache",))
        self.addCleanup(dialog.close)
        dialog.load_mapping()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        with patch("prototypes.qt.recovery_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes):
            dialog.activate()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        dialog.load_mapping()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertEqual(dialog.mapping["state"], "active")
        dialog.roots.setCurrentRow(0)
        with patch("prototypes.qt.recovery_qt.QMessageBox.exec",
                   return_value=QMessageBox.StandardButton.Yes):
            dialog.enable_selected()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        dialog.load_mapping()
        self.assertTrue(self._spin(lambda: dialog.worker is None))
        self.assertTrue(dialog.mapping["sources"][0]["enabled"])
        self.assertFalse(dialog.mapping["sources"][0]["held"])

    def test_unknown_marker_refuses_long_lived_sync_reader(self):
        model = AssetModel(self.database, read_mode="synchronous")
        self.addCleanup(model.close)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("PRAGMA application_id=12345")
        with self.assertRaisesRegex(ValueError, "Unsupported catalog application_id"):
            model.asset_at(0)

    def test_close_cancels_off_gui_worker_and_waits_for_owned_exit(self):
        entered = threading.Event()
        exited = threading.Event()

        def bounded_backup(_database, _output, *, cache_roots, cancel_event):
            entered.set()
            while not cancel_event.wait(.01):
                pass
            exited.set()
            raise ValueError("generated cancellation")

        dialog = RecoveryDialog(self.database, (self.root / "cache",))
        self.addCleanup(dialog.close)
        dialog.show()
        with patch("prototypes.qt.recovery_qt.backup_metadata", side_effect=bounded_backup):
            dialog._start("backup", output=self.package)
            self.assertTrue(self._spin(entered.is_set))
            self.assertFalse(dialog.close())
            self.assertTrue(self._spin(lambda: dialog.worker is None and exited.is_set()))
            self.assertTrue(self._spin(lambda: not dialog.isVisible()))

    def test_parent_close_retries_after_recovery_worker_finishes(self):
        entered = threading.Event()
        release = threading.Event()
        exited = threading.Event()

        def delayed_backup(_database, _output, *, cache_roots, cancel_event):
            entered.set()
            try:
                release.wait(5)
                return {"generated": True}
            finally:
                exited.set()

        window = GalleryWindow(self.database, enable_thumbnails=False,
                               cache_root=self.root / "cache",
                               private_root=self.root / "private")
        self.addCleanup(window.close)
        window.show()
        wait_for_startup_validation(window)
        dialog = window.open_recovery()
        self.assertIsNotNone(dialog)
        with patch("prototypes.qt.recovery_qt.backup_metadata", side_effect=delayed_backup):
            dialog._start("backup", output=self.package)
            self.assertTrue(self._spin(entered.is_set))
            self.assertFalse(window.close())
            self.assertTrue(window.isVisible())
            self.assertIsNotNone(dialog.worker)
            self.assertTrue(dialog.worker.isRunning())
            release.set()
            self.assertTrue(self._spin(lambda: exited.is_set() and not window.isVisible(), seconds=8))
            self.assertIsNone(dialog.worker)


if __name__ == "__main__":
    unittest.main()
