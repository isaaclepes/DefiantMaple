"""Generated UI/worker outcomes; associations stay mocked and originals read-only."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, external_actions as api
from prototypes.qt.app import GalleryWindow, main
from prototypes.qt.external_actions import ExternalActionWorker


class ExternalActionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # UI expectations use the same canonical paths stored by the catalog.
        self.root = Path(self.temp.name).resolve(strict=True)
        self.db = self.root / "generated.sqlite3"
        catalog.initialize(self.db)
        self.files = []
        self.ids = []
        for name in ("alpha $(`literal`) ; ' café %.png", "beta.png"):
            path = self.root / name
            path.write_bytes(b"\x89PNG\r\n\x1a\nfictional" + name.encode())
            self.files.append(path)
            self.ids.append(catalog.index_file(self.db, path))
        self.log = self.root / "readonly-receipt.json"
        self.stub = self.root / "trusted_stub.py"
        self.stub.write_text("import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n")
        self.command = api.CommandSpec(sys.executable, (str(self.stub), str(self.log), "fixed $(`literal`)"))
        self.settings = api.ExternalSettings(self.command, self.command)
        self.window = GalleryWindow(self.db, external_settings=self.settings,
                                    external_settings_path=self.root / "local-settings.json")
        self.window.show()
        self.app.processEvents()
        self.select(0)
        self.before = self.snapshot()

    def tearDown(self):
        if self.window.external_worker is not None:
            self.window.cancel_external_action()
            self.wait(lambda: self.window.external_worker is None)
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate(), "bounded Qt work did not finish")
        self.app.processEvents()

    def select(self, number):
        index = self.window.model.index(self.window.model.row_for_asset(self.ids[number]))
        self.window.gallery.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def snapshot(self):
        with catalog.connect(self.db) as db:
            rows = list(db.iterdump())
        return rows, [(p.read_bytes(), p.stat().st_mtime_ns) for p in self.files]

    def test_keyboard_literal_file_folder_and_captured_identity_under_filter_config_drift(self):
        button = self.window.open_external_button
        button.setFocus()
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), button)
        QTest.keyClick(button, Qt.Key.Key_Space)
        worker = self.window.external_worker
        self.assertEqual(worker.target.asset_id, self.ids[0])
        self.assertFalse(button.isEnabled())
        self.assertIsNone(self.window.open_containing_folder())
        self.select(1)
        self.window.model.set_metadata_filters(search="beta")
        # A later configuration cannot retarget or replace the captured command.
        self.window.external_settings = api.ExternalSettings(api.CommandSpec(str(self.root / "missing-tool")), self.command)
        self.wait(lambda: self.window.external_worker is None)
        self.wait(self.log.exists)
        self.assertEqual(json.loads(self.log.read_text()), ["fixed $(`literal`)", str(self.files[0])])
        self.assertEqual(worker.outcome.status, "requested")
        self.assertIn(self.ids[0], self.window.external_feedback.text())
        self.assertEqual(self.snapshot(), self.before)
        self.window.model.set_metadata_filters()
        self.select(1)
        self.log.unlink()
        self.window.open_folder_button.setFocus()
        QTest.keyClick(self.window.open_folder_button, Qt.Key.Key_Space)
        self.wait(lambda: self.window.external_worker is None)
        self.wait(self.log.exists)
        self.assertEqual(json.loads(self.log.read_text()), ["fixed $(`literal`)", str(self.root)])
        self.assertEqual(self.snapshot(), self.before)

    def test_cached_display_revision_refuses_after_catalog_aba(self):
        # Materialize the displayed row before another writer advances it.
        target = api.capture_target(self.window._selected_asset())
        with catalog.connect(self.db) as db:
            db.execute("UPDATE assets SET rating=5 WHERE asset_id=?", (target.asset_id,))
            db.execute("UPDATE assets SET rating=NULL WHERE asset_id=?", (target.asset_id,))
        before = self.snapshot()
        worker = self.window.open_external_file()
        self.assertEqual(worker.target, target)
        self.wait(lambda: self.window.external_worker is None)
        self.assertEqual(worker.outcome.status, "refused")
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), before)

    def test_local_settings_dialog_keyboard_validation_save_and_lazy_load(self):
        dialog = self.window.open_external_settings()
        association, executable, arguments = dialog.fields[api.OpenAction.FILE]
        self.assertEqual(association.accessibleName(), "Open in Editor default application")
        executable.setText("relative-tool")
        dialog.save_button.setFocus()
        QTest.keyClick(dialog.save_button, Qt.Key.Key_Space)
        self.assertIn("absolute", dialog.feedback.text())
        self.assertIsNone(self.window.external_worker)
        executable.setText(sys.executable)
        arguments.setPlainText(str(self.stub) + "\n" + str(self.log) + "\nfixed literal")
        QTest.keyClick(dialog.save_button, Qt.Key.Key_Space)
        self.wait(lambda: self.window.external_worker is None)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.window.external_settings.file.fixed_args[-1], "fixed literal")
        self.assertEqual(self.snapshot(), self.before)
        self.window.external_settings = None
        worker = self.window.open_external_file()
        self.assertTrue(worker.settings_task)
        self.select(1)
        self.wait(lambda: self.window.external_worker is None)
        self.wait(self.log.exists)
        self.assertEqual(json.loads(self.log.read_text())[-1], str(self.files[0]))
        self.assertEqual(self.snapshot(), self.before)

    def test_gui_remains_responsive_cancellation_and_close_reap_worker(self):
        # A catalog writer holds the final worker validation, not the GUI.
        blocker = sqlite3.connect(self.db)
        blocker.execute("BEGIN EXCLUSIVE")
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        worker = self.window.open_external_file()
        QTest.qWait(100)
        self.assertGreater(len(ticks), 2)
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.wait(lambda: self.window.external_worker is None)
        self.wait(lambda: not self.window.isVisible())
        timer.stop()
        blocker.rollback()
        blocker.close()
        self.assertEqual(worker.outcome.status, "cancelled")
        self.assertFalse(worker.outcome.permit_sent)
        self.assertFalse(self.log.exists())
        with self.assertRaises(sqlite3.ProgrammingError):
            self.window.model._db.execute("SELECT 1")
        # Avoid closing the already closed model a second time in tearDown.
        self.window.close = lambda: True
        self.assertEqual(self.snapshot(), self.before)

    def test_known_default_association_rejection_and_local_url_encoding(self):
        with patch.object(QDesktopServices, "openUrl", return_value=True) as opened:
            api._default_association(str(self.files[0]))
            url = opened.call_args.args[0]
            self.assertTrue(url.isLocalFile())
            self.assertEqual(Path(url.toLocalFile()), self.files[0])
            self.assertEqual(url.scheme(), "file")
        with patch.object(QDesktopServices, "openUrl", return_value=False):
            with self.assertRaises(api.DispatchRejected):
                api._default_association(str(self.files[0]))
        self.assertEqual(self.snapshot(), self.before)

    def test_unreaped_ownership_blocks_replacement_and_close(self):
        error = RuntimeError("generated unreaped cleanup double")
        error.process = object()
        with patch.object(api, "execute_external_action", side_effect=error):
            worker = self.window.open_external_file()
            self.wait(lambda: not worker.isRunning())
            self.assertTrue(self.window.external_cleanup_failed)
            self.assertIs(self.window.external_worker, worker)
            self.assertIs(worker.unreaped_process, error.process)
            self.assertFalse(self.window.open_external_button.isEnabled())
            self.assertFalse(self.window.open_folder_button.isEnabled())
            self.assertIsNone(self.window.open_external_file())
            self.assertIsNone(self.window.open_external_settings())
            self.assertFalse(self.window.close())
            self.assertTrue(self.window.isVisible())
        # The policy double owns no real process; release it for test teardown.
        self.window.external_cleanup_failed = False
        self.window.external_worker = None
        worker.deleteLater()
        self.assertEqual(self.snapshot(), self.before)

    def test_html_like_filename_and_error_feedback_are_literal_plain_text(self):
        # The typed service adapter is mocked; this test isolates Qt rendering.
        # A literal '<' filename is valid on POSIX but forbidden on Windows.
        asset = dict(self.window._selected_asset())
        asset["current_path"] = str(self.root / "<b>fictional.png")
        if os.name != "nt":
            Path(asset["current_path"]).write_bytes(b"fictional generated bytes")
        def refuse(database, target, action, command, **kwargs):
            return api.ActionResult("refused", '<img src="file:///fictional-resource"> denied', target, action)
        with patch.object(self.window, "_selected_asset", return_value=asset), patch.object(api, "execute_external_action", side_effect=refuse):
            worker = self.window.open_external_file()
            self.assertIn("<b>fictional.png", self.window.external_feedback.text())
            self.assertEqual(self.window.external_feedback.textFormat(), Qt.TextFormat.PlainText)
            self.wait(lambda: self.window.external_worker is None)
        self.assertEqual(worker.outcome.status, "refused")
        self.assertIn('<b>fictional.png', self.window.external_feedback.text())
        self.assertIn('<img src="file:///fictional-resource">', self.window.external_feedback.text())
        self.assertEqual(self.window.external_feedback.textFormat(), Qt.TextFormat.PlainText)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_source_cli_probe_is_real_worker_read_only_and_never_dispatches(self):
        completed = subprocess.run([sys.executable, "-m", "prototypes.qt.app", "--catalog", str(self.db),
                                    "--smoke-external-probe-id", self.ids[0]],
                                   env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                   check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(completed.stdout), {"status": "probe_ready", "permit_sent": False,
                                                       "dispatched": False, "cleanup_complete": True})
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_probe_worker_withholds_permit_and_reaps_through_actual_qthread(self):
        worker = ExternalActionWorker(self.db, api.capture_target(self.window._selected_asset()),
                                      api.OpenAction.FILE, self.command, probe_only=True)
        worker.start()
        self.wait(lambda: not worker.isRunning())
        self.assertEqual(worker.outcome.status, "probe_ready")
        self.assertFalse(worker.outcome.permit_sent)
        self.assertFalse(worker.outcome.dispatched)
        self.assertTrue(worker.outcome.cleanup_complete)
        self.assertIsNone(worker.unreaped_process)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.snapshot(), self.before)
