"""Generated-fixture comparison and viewer ownership regressions."""
from contextlib import closing
import hashlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import QItemSelectionModel, QTimer, Qt
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple.catalog import initialize, index_file
from defiantmaple import cached_preview as cache_api
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import GalleryWindow, ThumbnailWorker
from prototypes.qt.comparison import ComparisonDialog, ComparisonWorker, OriginalLimits, _OriginalFile
from prototypes.qt.preview import FullImageDialog, FullImageWorker, _FULL_IMAGE_OWNERS


def malformed_legacy(asset, output, limits, sender):
    sender.send((None, ""))
    sender.close()


def stalled_original(database, asset, target, cache_root, limits, deadline, sender, request):
    time.sleep(30)


def eof_original(database, asset, target, cache_root, limits, deadline, sender, request):
    sender.close()


def partial_original(database, asset, target, cache_root, limits, deadline, sender, request):
    os.write(sender.fileno(), struct.pack("!i", 1024) + b"{")
    time.sleep(30)


def malformed_original(database, asset, target, cache_root, limits, deadline, sender, request):
    from prototypes.qt.comparison import _send_reply
    _send_reply(sender, {"stage": "decoded", "request": request, "base": "/tmp"})
    sender.close()


def partial_decoded_original(database, asset, target, cache_root, limits, deadline, sender, request):
    from prototypes.qt.comparison import _send_reply, _read_reply
    _send_reply(sender, {"stage": "safe_temp_base", "request": request,
                        "base": str(Path(tempfile.gettempdir()).resolve(strict=True)),
                        "enforced": False, "note": "Injected transport fault only"})
    _read_reply(sender)
    os.write(sender.fileno(), struct.pack("!i", 1024) + b"{")
    time.sleep(30)


def guarded_refused_original(*args):
    from prototypes.qt.comparison import _comparison_original
    with patch("prototypes.qt.comparison._OriginalFile", side_effect=AssertionError("original I/O attempted")):
        _comparison_original(*args)


def change_catalog_after_decode(*args):
    from prototypes.qt.comparison import _comparison_original, _OriginalFile
    verify = _OriginalFile.verify
    database, _, target = args[:3]
    def changed(original, *values):
        verify(original, *values)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE assets SET sha256=? WHERE asset_id=?", ("0" * 64, target.asset_id))
    with patch.object(_OriginalFile, "verify", changed):
        _comparison_original(*args)


class ReplacementContext:
    """Picklable top-level children through the actual spawn context."""
    def __init__(self, target):
        self.context = multiprocessing.get_context("spawn")
        self.target = target

    def Pipe(self, **kwargs):
        return self.context.Pipe(**kwargs)

    def Process(self, *, target, args):
        return self.context.Process(target=self.target, args=args)


class UnreapedProcess:
    pid = 1

    def __init__(self):
        self.alive = True
        self.terminated = self.killed = 0

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated += 1

    def kill(self):
        self.killed += 1

    def join(self, seconds):
        pass


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="defiantmaple-comparison-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(strict=True)
        self.db = self.root / "catalog.sqlite3"
        initialize(self.db)
        self.media = self.root / "fictional.png"
        Image.new("RGBA", (80, 40), (210, 20, 30, 73)).save(self.media)
        asset_id = index_file(self.db, self.media)
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            self.asset = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())

    def spin(self, predicate, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(.005)
        return False

    def drain(self, worker):
        worker.cancel()
        self.assertTrue(self.spin(lambda: not worker.isRunning()))
        if not worker.cleanup_complete:
            worker.retry_cleanup()
            self.assertTrue(self.spin(lambda: not worker.isRunning()))
        self.assertTrue(worker.cleanup_complete)

    def start_worker(self, mode="original", asset=None, limits=OriginalLimits()):
        worker = ComparisonWorker(self.db, self.root / "cache", asset or self.asset,
                                  ("generated", mode, time.monotonic()), mode, limits)
        worker.received_images = []
        worker.delivered.connect(lambda outcome, image: worker.received_images.append(image))
        self.addCleanup(lambda: self.drain(worker))
        worker.start()
        self.assertTrue(self.spin(lambda: not worker.isRunning()))
        return worker

    def source_backed(self, asset=None):
        asset = asset or self.asset
        info = Path(asset["current_path"]).stat()
        source_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                       "VALUES(?,'Generated',?,'inbox','paused')", (source_id, str(self.root)))
            db.execute("UPDATE assets SET source_id=? WHERE asset_id=?", (source_id, asset["asset_id"]))
            db.execute("INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                       "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
                       "VALUES(?,?,?,?,?,?,?,?,1,'indexed',?)", (asset["current_path"], source_id,
                       info.st_size, info.st_mtime_ns, str(info.st_dev), str(info.st_ino),
                       info.st_mtime_ns, info.st_mtime_ns, asset["asset_id"]))
        return dict(asset, source_id=source_id, source_health="paused", entry_disposition="indexed",
                    entry_path=asset["current_path"], entry_source_id=source_id,
                    source_relation_count=1, linked_entry_count=1)

    def second_asset(self):
        path = self.root / "oriented.jpg"
        source = Image.new("RGB", (60, 20), (220, 30, 40))
        for x in range(30):
            for y in range(20):
                source.putpixel((x, y), (20, 30, 230))
        exif = Image.Exif()
        exif[274] = 6
        source.save(path, exif=exif, quality=100, subsampling=0)
        source.close()
        asset_id = index_file(self.db, path)
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())

    def dialog(self):
        assets = [self.asset, self.second_asset()]
        for asset in assets:
            thumbnail_for(self.db, asset["asset_id"], self.root / "cache", max_edge=128)
        dialog = ComparisonDialog(self.db, self.root / "cache", assets)
        self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close()))
        dialog.show()
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        return dialog

    def test_real_legacy_success_is_after_reap_and_accepted_close_clears_pixels(self):
        dialog = FullImageDialog(self.asset)
        self.addCleanup(lambda: self.drain(dialog.worker))
        dialog.show()
        self.assertTrue(self.spin(lambda: dialog.canvas._item is not None), dialog.status.text())
        self.assertTrue(dialog.worker.cleanup_complete)
        self.assertIsNone(dialog.worker._process)
        self.assertIsNone(dialog.worker._temporary)
        self.assertEqual(dialog.canvas._item.pixmap().toImage().pixelColor(0, 0).alpha(), 73)
        self.assertTrue(self.spin(lambda: not dialog.worker.isRunning()))
        self.assertTrue(dialog.close())
        self.assertIsNone(dialog.canvas._item)

    def test_async_close_and_queued_image_cannot_repaint_closed_inspector(self):
        dialog = FullImageDialog(self.asset)
        self.addCleanup(lambda: self.drain(dialog.worker))
        dialog.show()
        dialog.close()
        # A queued successful delivery racing a close must not present pixels.
        dialog.worker.loaded.emit(QImage(2, 2, QImage.Format.Format_RGBA8888), 2, 2)
        self.assertTrue(self.spin(lambda: not dialog.worker.isRunning() and not dialog.isVisible()))
        self.assertIsNone(dialog.canvas._item)

    def test_failed_reap_retains_scratch_and_cleanup_only_retry_never_decodes(self):
        worker = FullImageWorker(self.asset)
        process = UnreapedProcess()
        worker._process = process
        worker._temporary = tempfile.TemporaryDirectory(dir=self.root, prefix="owned-")
        owned = Path(worker._temporary.name)
        worker.cleanup_complete = False
        worker._cleanup_only = True
        self.addCleanup(lambda: self.drain(worker))
        try:
            worker.start()
            self.assertTrue(self.spin(lambda: not worker.isRunning()))
            self.assertFalse(worker.cleanup_complete)
            self.assertIs(worker._process, process)
            self.assertTrue(owned.exists())
            self.assertIn(worker, _FULL_IMAGE_OWNERS)
            replacement = FullImageWorker(self.asset)
            errors = []
            replacement.failed.connect(errors.append)
            replacement.start()
            self.assertTrue(self.spin(lambda: not replacement.isRunning()))
            self.app.processEvents()
            self.assertIn("pending cleanup", " ".join(errors))
            process.alive = False
            with patch("prototypes.qt.preview._decode_original", side_effect=AssertionError("cleanup decoded")), \
                    patch("prototypes.qt.preview.multiprocessing.get_context", side_effect=AssertionError("cleanup spawned")):
                self.assertTrue(worker.retry_cleanup())
                self.assertTrue(self.spin(lambda: not worker.isRunning()))
            self.assertTrue(worker.cleanup_complete)
            self.assertFalse(owned.exists())
            self.assertNotIn(worker, _FULL_IMAGE_OWNERS)
        finally:
            process.alive = False

    def test_legacy_setup_failures_are_actionable_and_clean(self):
        for point in ("prototypes.qt.preview.tempfile.TemporaryDirectory",
                      "prototypes.qt.preview.multiprocessing.get_context"):
            with self.subTest(point=point), patch(point, side_effect=OSError("generated setup failure")):
                worker = FullImageWorker(self.asset)
                errors = []
                worker.failed.connect(errors.append)
                worker.start()
                self.assertTrue(self.spin(lambda: not worker.isRunning()))
                self.app.processEvents()
                self.assertIn("generated setup failure", " ".join(errors))
                self.assertTrue(worker.cleanup_complete)
                self.assertIsNone(worker._temporary)

    def test_legacy_pipe_process_and_malformed_child_failures_remain_owned(self):
        real = multiprocessing.get_context("spawn")
        for context in (SimpleNamespace(Pipe=lambda **_: (_ for _ in ()).throw(OSError("pipe failure"))),
                        SimpleNamespace(Pipe=real.Pipe,
                                        Process=lambda **_: (_ for _ in ()).throw(OSError("process failure"))),
                        ReplacementContext(malformed_legacy)):
            with self.subTest(context=context), patch("prototypes.qt.preview.multiprocessing.get_context", return_value=context):
                worker = FullImageWorker(self.asset)
                errors = []
                worker.failed.connect(errors.append)
                self.addCleanup(lambda worker=worker: self.drain(worker))
                worker.start()
                self.assertTrue(self.spin(lambda: not worker.isRunning()))
                self.app.processEvents()
                self.assertTrue(errors)
                self.assertTrue(worker.cleanup_complete)
                self.assertIsNone(worker._temporary)
                self.assertIsNone(worker._process)

    def test_real_original_orientation_alpha_and_metadata_only_drift(self):
        images = []
        worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("alpha",), "original")
        worker.delivered.connect(lambda outcome, image: images.append(image))
        self.addCleanup(lambda: self.drain(worker))
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE assets SET rating=4 WHERE asset_id=?", (self.asset["asset_id"],))
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        worker.start()
        self.assertTrue(self.spin(lambda: not worker.isRunning()))
        self.app.processEvents()
        self.assertEqual(worker.outcome.status, "ready", worker.outcome.message)
        self.assertTrue(worker.outcome.metadata_drift)
        self.assertEqual(worker.outcome.observed_revision, self.asset["revision"] + 1)
        self.assertEqual(images[0].pixelColor(0, 0).alpha(), 73)
        self.assertEqual(worker.target.revision, self.asset["revision"])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        oriented = self.start_worker(asset=self.second_asset())
        self.assertEqual(oriented.outcome.status, "ready", oriented.outcome.message)
        self.assertEqual((oriented.outcome.width, oriented.outcome.height), (20, 60))
        top = oriented.received_images[0].pixelColor(10, 5)
        bottom = oriented.received_images[0].pixelColor(10, 55)
        self.assertGreater(top.blue(), 200)
        self.assertLess(top.red(), 40)
        self.assertGreater(bottom.red(), 200)
        self.assertLess(bottom.blue(), 60)
        if os.name == "posix" and os.sys.platform != "darwin":
            self.assertTrue(worker.outcome.address_space_enforced)

    def test_changed_source_and_symlink_refuse_without_cache_or_catalog_writes(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.media.write_bytes(self.media.read_bytes() + b"changed")
        worker = self.start_worker()
        self.assertEqual(worker.outcome.status, "refused")
        self.assertIn("fingerprint", worker.outcome.message)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        outside = self.root / "outside.png"
        Image.new("RGBA", (80, 40), (210, 20, 30, 73)).save(outside)
        self.media.unlink()
        try:
            self.media.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Host cannot create generated symlink: {exc}")
        refused = self.start_worker()
        self.assertEqual(refused.outcome.status, "refused")
        self.assertIn("nonlinked", refused.outcome.message)

    def test_exact_limits_timeout_and_child_start_refusal(self):
        for fields in ({"max_pixels": 8_388_609}, {"max_rgba_bytes": 32 * 1024 * 1024 + 1},
                       {"timeout_seconds": 13}, {"address_space_bytes": 512 * 1024 * 1024 + 1}):
            with self.assertRaises(ValueError):
                OriginalLimits(**fields)
        restricted = self.start_worker(limits=OriginalLimits(max_pixels=100))
        self.assertEqual(restricted.outcome.status, "refused")
        with patch("prototypes.qt.comparison.multiprocessing.get_context", side_effect=OSError("generated startup")):
            failed = self.start_worker()
        self.assertIn("generated startup", failed.outcome.message)
        self.assertTrue(failed.cleanup_complete)
        replacement = ReplacementContext(stalled_original)
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=replacement):
            began = time.monotonic()
            expired = self.start_worker(limits=OriginalLimits(timeout_seconds=.3))
        self.assertIn("deadline", expired.outcome.message)
        self.assertTrue(expired.cleanup_complete)
        self.assertIsNone(expired._process)
        self.assertLess(time.monotonic() - began, 3.5)

    def test_cache_cleanup_retry_reaps_without_new_child_or_pixels(self):
        worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("cleanup",), "cache")
        process = UnreapedProcess()
        process.alive = False
        scratch = tempfile.TemporaryDirectory(dir=self.root, prefix="owned-cache-")
        owned = Path(scratch.name)
        with cache_api._OWNERSHIP_LOCK:
            cache_api._ORPHANS[-123] = (process, scratch)
        worker.cleanup_complete = False
        worker.cancel()
        with patch("defiantmaple.cached_preview.multiprocessing.get_context", side_effect=AssertionError("cleanup spawned")):
            self.assertTrue(worker.retry_cleanup())
            self.assertTrue(self.spin(lambda: not worker.isRunning()))
        self.assertTrue(worker.cleanup_complete)
        self.assertEqual(worker.outcome.status, "cancelled")
        self.assertFalse(owned.exists())
        self.assertNotIn(-123, cache_api._ORPHANS)

    def test_original_close_error_still_releases_parent_handles(self):
        original = _OriginalFile(self.media)
        stream = original.stream
        try:
            original.stream = SimpleNamespace(close=lambda: (_ for _ in ()).throw(OSError("close failure")))
            with self.assertRaisesRegex(OSError, "close failure"):
                original.close()
            self.assertFalse(original.tree.handles)
            self.assertIsNone(original.stream)
            original.close()
        finally:
            stream.close()

    def test_two_panes_real_cache_original_independent_keys_and_truthful_failed_replacement(self):
        dialog = self.dialog()
        left, right = dialog.panes.values()
        self.assertEqual(left.result.status, "ready", left.status.text())
        self.assertEqual(right.result.status, "ready", right.status.text())
        self.assertIn("fallback 128", left.status.text())
        right_scale = right.canvas._scale
        left.canvas.setFocus()
        QTest.keyClick(left.canvas, Qt.Key.Key_Plus)
        self.assertFalse(left.canvas._fit)
        self.assertEqual(right.canvas._scale, right_scale)
        QTest.keyClick(left.canvas, Qt.Key.Key_F)
        self.assertTrue(left.canvas._fit)
        left.background_box.setCurrentText("Dark")
        self.assertNotEqual(left.canvas.backgroundBrush().color(), right.canvas.backgroundBrush().color())
        QTest.keyClick(left.canvas, Qt.Key.Key_F11)
        self.assertTrue(dialog.isFullScreen())
        QTest.keyClick(left.canvas, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isFullScreen())
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.request("left", "original"))
        self.assertFalse(dialog.request("left", "cache"))
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        self.assertEqual(left.result.mode, "original")
        self.assertEqual(left.result.status, "ready", left.status.text())
        self.media.unlink()
        self.assertTrue(dialog.request("left", "original"))
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        self.assertEqual(left.result.status, "refused")
        self.assertIn("still showing previous original", left.status.text())
        self.assertEqual(right.result.mode, "cache")
        self.assertIsNotNone(right.canvas._item)
        QTest.keyClick(left.canvas, Qt.Key.Key_Escape)
        self.assertTrue(self.spin(lambda: not dialog.isVisible()))
        self.assertIsNone(left.canvas._item)
        self.assertIsNone(right.canvas._item)

    def test_gallery_captures_view_order_refuses_counts_and_pending_other_viewer(self):
        self.second_asset()
        window = GalleryWindow(self.db, cache_root=self.root / "cache")
        self.addCleanup(lambda: (window.close(), self.spin(lambda: not window.inspect_dialog or not window.inspect_dialog.worker.isRunning()), window.close()))
        selection = window.gallery.selectionModel()
        selection.select(window.model.index(1), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(window.model.index(1), QItemSelectionModel.SelectionFlag.NoUpdate)
        with patch.object(selection, "selectedIndexes", side_effect=AssertionError("unbounded materialization")):
            self.assertIsNone(window.compare_selected())
        selection.select(window.model.index(0), QItemSelectionModel.SelectionFlag.Select)
        window.inspect_dialog = FullImageDialog(dict(window.model.asset_at(0)), window)
        inspector = window.inspect_dialog
        self.assertIsNone(window.compare_selected())
        self.assertIsNone(window.comparison_dialog)
        self.assertTrue(self.spin(lambda: not inspector.worker.isRunning()))
        dialog = window.compare_selected()
        self.assertIsNotNone(dialog)
        self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close()))
        captured = tuple(window.model.asset_at(row)["asset_id"] for row in (0, 1))
        self.assertEqual(tuple(target.asset_id for target in dialog.targets), captured)
        window.model.set_metadata_filters(search="no matches")
        self.assertEqual(tuple(target.asset_id for target in dialog.targets), captured)
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))

    def test_offline_original_button_and_direct_action_refuse_without_worker(self):
        assets = [dict(self.asset, source_id=str(uuid.uuid4()), source_health="offline",
                       entry_disposition="missing"), self.second_asset()]
        dialog = ComparisonDialog(self.db, self.root / "empty-cache", assets)
        self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close()))
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        prior = dialog.worker
        self.assertFalse(dialog.panes["left"].original_button.isEnabled())
        self.assertFalse(dialog.request("left", "original"))
        self.assertIs(dialog.worker, prior)
        self.assertIn("unavailable", dialog.feedback.text())

    def test_fresh_source_health_and_relation_refuse_before_original_io(self):
        asset = self.source_backed()
        eligible = self.start_worker(asset=asset)
        self.assertEqual(eligible.outcome.status, "ready", eligible.outcome.message)
        wrapper = ReplacementContext(guarded_refused_original)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE sources SET health='offline'")
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper):
            refused = self.start_worker(asset=asset)
        self.assertIn("unavailable", refused.outcome.message)
        self.assertNotIn("I/O attempted", refused.outcome.message)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE sources SET health='paused'")
            db.execute("UPDATE source_entries SET current_path=current_path || '.different'")
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper):
            refused = self.start_worker(asset=asset)
        self.assertIn("relation", refused.outcome.message)
        self.assertNotIn("I/O attempted", refused.outcome.message)

    def test_catalog_content_change_after_decode_refuses_delivery(self):
        wrapper = ReplacementContext(change_catalog_after_decode)
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper):
            refused = self.start_worker()
        self.assertEqual(refused.outcome.status, "refused")
        self.assertIn("content or source location changed", refused.outcome.message)
        self.assertTrue(refused.received_images[0].isNull())

    def test_corrupt_cache_pane_isolated_and_no_automatic_original_generation(self):
        assets = [self.asset, self.second_asset()]
        for asset in assets:
            thumbnail_for(self.db, asset["asset_id"], self.root / "cache", max_edge=128)
        path = next(path for path in (self.root / "cache").rglob("*.png")
                    if self.asset["asset_id"] in path.parts)
        path.write_bytes(b"generated-corruption")
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with patch("prototypes.qt.comparison._comparison_original", side_effect=AssertionError("automatic original")), \
                patch("prototypes.qt.app.thumbnail_for", side_effect=AssertionError("automatic generation")):
            dialog = ComparisonDialog(self.db, self.root / "cache", assets)
            self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close()))
            self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        self.assertEqual(dialog.panes["left"].result.status, "refused")
        self.assertEqual(dialog.panes["right"].result.status, "ready")
        self.assertIsNone(dialog.panes["left"].canvas._item)
        self.assertIsNotNone(dialog.panes["right"].canvas._item)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_comparison_active_close_reaps_and_blocks_other_viewer_and_late_results(self):
        self.second_asset()
        window = GalleryWindow(self.db, cache_root=self.root / "cache")
        selection = window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(window.model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(window.model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        dialog = window.compare_selected()
        self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close(), window.close()))
        self.assertIsNone(window.inspect_selected())
        self.assertIsNone(window.inspect_dialog)
        self.assertTrue(self.spin(lambda: not dialog.worker.isRunning() and not dialog.isVisible()))
        previous = dialog.worker.outcome
        if previous is not None:
            dialog._delivered(previous, QImage(1, 1, QImage.Format.Format_RGBA8888))
        self.assertTrue(all(pane.canvas._item is None for pane in dialog.panes.values()))
        self.assertTrue(dialog.worker.cleanup_complete)
        inspector = window.inspect_selected()
        self.assertIsNotNone(inspector)
        self.addCleanup(lambda: (inspector.close(), self.drain(inspector.worker), inspector.close()))

    def test_labels_are_plain_text_and_cached_target_remains_after_path_drift(self):
        assets = [dict(self.asset, current_path=str(self.root / "<img src=fictional>.png")), self.second_asset()]
        dialog = ComparisonDialog(self.db, self.root / "cache", assets)
        self.addCleanup(lambda: (dialog.close(), self.spin(lambda: not dialog.worker.isRunning()), dialog.close()))
        self.assertTrue(self.spin(lambda: not dialog.active and not dialog.queue))
        pane = dialog.panes["left"]
        self.assertEqual(pane.identity.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(pane.status.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn("<img src=fictional>.png", pane.identity.text())
        self.assertIn("&lt;img", pane.identity.toolTip())
        self.assertNotIn("<img", pane.identity.toolTip())
        resources = []
        class LiteralDocument(QTextDocument):
            def loadResource(self, kind, url):
                resources.append(url)
                return None
        document = LiteralDocument()
        document.setHtml(pane.identity.toolTip())
        document.documentLayout().documentSize()
        self.assertEqual(document.toPlainText(), "<img src=fictional>.png")
        self.assertFalse(resources)
        self.assertEqual(pane.target.path, assets[0]["current_path"])
        self.assertEqual(pane.target.asset_id, self.asset["asset_id"])

    def test_null_or_wrong_size_detached_image_is_refusal_in_both_modes(self):
        thumbnail_for(self.db, self.asset["asset_id"], self.root / "cache", max_edge=128)
        for replacement in (QImage(), QImage(2, 2, QImage.Format.Format_RGBA8888)):
            with self.subTest(null=replacement.isNull()):
                with patch("prototypes.qt.comparison.result_image", return_value=replacement):
                    cached = self.start_worker("cache")
                self.assertEqual(cached.outcome.status, "refused")
                self.assertIn("copy could not be created", cached.outcome.message)
                with patch("prototypes.qt.comparison.QImage", side_effect=lambda *args: replacement) as image:
                    image.Format = QImage.Format
                    original = self.start_worker()
                self.assertEqual(original.outcome.status, "refused")
                self.assertIn("copy could not be created", original.outcome.message)

    def test_real_pending_child_heartbeat_cancel_and_reap(self):
        wrapper = ReplacementContext(stalled_original)
        worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("responsive",), "original")
        self.addCleanup(lambda: self.drain(worker))
        timer = QTimer()
        ticks = []
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper):
            worker.start()
            try:
                self.assertTrue(self.spin(lambda: worker._process is not None and worker._process.pid is not None))
                timer.start()
                self.assertTrue(self.spin(lambda: len(ticks) >= 2, 2))
                self.assertTrue(worker.isRunning())
                self.assertIsNone(worker.outcome)
                worker.cancel()
                self.assertTrue(self.spin(lambda: not worker.isRunning()))
                self.assertTrue(worker.cleanup_complete)
                self.assertIsNone(worker._process)
            finally:
                timer.stop()
                self.drain(worker)

    def test_gallery_one_outstanding_delivery_stale_ack_and_stop_without_gui_ack(self):
        thumbnail_for(self.db, self.asset["asset_id"], self.root / "cache", max_edge=128)
        worker = ThumbnailWorker(self.db, self.root / "cache")
        self.addCleanup(worker.stop)
        worker.finished_item.disconnect(worker._received)
        sent = []
        worker.finished_item.connect(lambda *args: sent.append(args), Qt.ConnectionType.DirectConnection)
        for edge in range(32, 64):
            worker.lookup(self.asset, edge)
        worker.start()
        self.assertTrue(self.spin(lambda: len(sent) == 1))
        self.assertFalse(worker._delivery.is_set())
        self.assertEqual(worker.requests.qsize(), 31)
        # Fill the bounded queue while the GUI deliberately withholds ack.
        worker.lookup(self.asset, 64)
        worker.lookup(self.asset, 65)
        self.assertEqual(worker.requests.qsize(), 32)
        self.assertEqual(len(sent), 1)
        old = sent[0]
        worker.invalidate_pending()
        worker.lookup(self.asset, 96)
        worker._received(*old)  # Stale result still acknowledges in finally.
        self.assertTrue(self.spin(lambda: len(sent) == 2))
        self.assertFalse(worker._delivery.is_set())
        self.assertTrue(worker.stop())  # No GUI ack is available during wait.
        self.assertFalse(worker.isRunning())
        self.assertEqual(worker.requests.qsize(), 0)
        worker._received(*sent[1])
        self.assertTrue(worker._delivery.is_set())
        self.assertFalse(worker.pixmaps)

    def test_original_scratch_overlap_refuses_before_child_start_and_cleans_only_owned_temp(self):
        original_temp = tempfile.TemporaryDirectory
        def inside_cache(**kwargs):
            cache = self.root / "cache"
            cache.mkdir(exist_ok=True)
            kwargs.pop("dir", None)
            return original_temp(dir=cache, **kwargs)
        with patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=inside_cache):
            refused = self.start_worker()
        self.assertEqual(refused.outcome.status, "refused")
        self.assertIn("scratch", refused.outcome.message)
        self.assertFalse(list((self.root / "cache").iterdir()))
        self.assertTrue(self.media.exists())

    def test_source_cli_sixth_smoke_uses_real_workers_and_preserves_fixtures(self):
        import json
        right = self.second_asset()
        self.source_backed(right)
        cache = self.root / "cache"
        for asset in (self.asset, right):
            thumbnail_for(self.db, asset["asset_id"], cache, max_edge=256)
        Path(right["current_path"]).rename(self.root / "unavailable.jpg")
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE sources SET health='offline'")
            db.execute("UPDATE source_entries SET disposition='missing'")
        def snapshot():
            return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in self.root.rglob("*") if path.is_file()}
        before = snapshot()
        completed = subprocess.run([sys.executable, "-m", "prototypes.qt.app", "--catalog", str(self.db),
            "--smoke-comparison-ids", self.asset["asset_id"], right["asset_id"],
            "--smoke-cache-root", str(cache)], capture_output=True, text=True, timeout=40)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["cache_sizes"], [[80, 40], [20, 60]])
        self.assertEqual(receipt["original_size"], [80, 40])
        self.assertEqual(receipt["original_top_rgba"][3], 73)
        self.assertTrue(receipt["unavailable_original_refused"])
        self.assertTrue(receipt["cleanup_complete"])
        self.assertEqual(snapshot(), before)

    def test_first_stage_malformed_and_partial_frame_deadline_create_no_scratch(self):
        wrapper = ReplacementContext(malformed_original)
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper), \
                patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=AssertionError("scratch created")):
            malformed = self.start_worker()
        self.assertIn("safe-temp-base", malformed.outcome.message)
        self.assertIsNone(malformed._temporary)
        if os.name == "nt":
            self.skipTest("Partial byte-stream frame injection applies to POSIX Connection; Windows pipe messages differ")
        for target, stage in ((partial_original, "safe_temp_base"), (partial_decoded_original, "decoded")):
            with self.subTest(stage=stage):
                wrapper = ReplacementContext(target)
                worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("partial", stage), "original")
                self.addCleanup(lambda worker=worker: self.drain(worker))
                with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=wrapper):
                    worker.start()
                    self.assertTrue(self.spin(lambda: worker.receipt_stage == stage))
                    self.assertTrue(worker.isRunning())
                    self.assertIsNone(worker.outcome)
                    owned = Path(worker._temporary.name) if worker._temporary is not None else None
                    self.assertEqual(owned is None, stage == "safe_temp_base")
                    real_clock = time.monotonic
                    # Expire the actual in-flight request only after observing a
                    # real partial frame, rather than timing out slow spawn setup.
                    with patch("prototypes.qt.comparison.time.monotonic", side_effect=lambda: real_clock() + 20):
                        self.assertTrue(self.spin(lambda: not worker.isRunning(), 3))
                self.assertIn("deadline", worker.outcome.message)
                self.assertTrue(worker.cleanup_complete)
                self.assertIsNone(worker._process)
                self.assertIsNone(worker._temporary)
                self.assertFalse(worker._watchdog.is_alive())
                if owned is not None:
                    self.assertFalse(owned.exists())

    def test_alias_temp_base_inside_source_or_cache_refuses_before_creation(self):
        with tempfile.TemporaryDirectory(prefix="defiantmaple-comparison-alias-") as temporary:
            outside = Path(temporary).resolve(strict=True)
            physical = outside / "physical"
            physical.mkdir()
            alias = outside / "alias"
            try:
                alias.symlink_to(physical, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Host cannot create generated directory alias: {exc}")
            for kind in ("source", "cache"):
                with self.subTest(kind=kind):
                    with closing(sqlite3.connect(self.db)) as db, db:
                        db.execute("DELETE FROM sources")
                    if kind == "source":
                        with closing(sqlite3.connect(self.db)) as db, db:
                            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                                       "VALUES(?,'Generated alias',?,'inbox','offline')", (str(uuid.uuid4()), str(alias)))
                    before = list(physical.iterdir())
                    worker = ComparisonWorker(self.db, alias if kind == "cache" else self.root / "cache",
                                              self.asset, ("alias", kind), "original")
                    self.addCleanup(lambda worker=worker: self.drain(worker))
                    with patch.dict(os.environ, {"TMPDIR": str(alias)}), \
                            patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=AssertionError("scratch created")):
                        worker.start()
                        self.assertTrue(self.spin(lambda: not worker.isRunning()))
                    self.assertEqual(worker.outcome.status, "refused")
                    self.assertIn("scratch overlaps", worker.outcome.message)
                    self.assertNotIn("scratch created", worker.outcome.message)
                    self.assertTrue(worker.cleanup_complete)
                    self.assertIsNone(worker._temporary)
                    self.assertEqual(list(physical.iterdir()), before)

    def test_catalog_directory_temp_base_refuses_before_scratch_creation(self):
        with tempfile.TemporaryDirectory(prefix="defiantmaple-comparison-media-") as temporary:
            media = Path(temporary).resolve(strict=True) / "elsewhere.png"
            Image.new("RGB", (20, 10)).save(media)
            asset_id = index_file(self.db, media)
            with closing(sqlite3.connect(self.db)) as db:
                db.row_factory = sqlite3.Row
                asset = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
            before = sorted(path.name for path in self.root.iterdir())
            with patch.dict(os.environ, {"TMPDIR": str(self.root)}), \
                    patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=AssertionError("scratch created")):
                worker = self.start_worker(asset=asset)
            self.assertEqual(worker.outcome.status, "refused")
            self.assertIn("catalog directory", worker.outcome.message)
            self.assertNotIn("scratch created", worker.outcome.message)
            self.assertIsNone(worker._temporary)
            self.assertEqual(sorted(path.name for path in self.root.iterdir()), before)

    def test_first_stage_eof_and_cancel_reap_without_creating_scratch(self):
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=ReplacementContext(eof_original)), \
                patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=AssertionError("scratch created")):
            eof = self.start_worker()
        self.assertEqual(eof.outcome.status, "refused")
        self.assertTrue(eof.cleanup_complete)
        self.assertIsNone(eof._temporary)
        worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("before-scratch-cancel",), "original")
        self.addCleanup(lambda: self.drain(worker))
        with patch("prototypes.qt.comparison.multiprocessing.get_context", return_value=ReplacementContext(stalled_original)), \
                patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=AssertionError("scratch created")):
            worker.start()
            self.assertTrue(self.spin(lambda: worker._process is not None and worker._process.pid is not None))
            worker.cancel()
            self.assertTrue(self.spin(lambda: not worker.isRunning()))
        self.assertTrue(worker.cleanup_complete)
        self.assertIsNone(worker._process)
        self.assertIsNone(worker._temporary)

    def test_comparison_failed_reap_retains_owner_and_retry_cannot_spawn(self):
        worker = ComparisonWorker(self.db, self.root / "cache", self.asset, ("unreaped",), "original")
        process = UnreapedProcess()
        worker._process = process
        worker._temporary = tempfile.TemporaryDirectory(prefix="defiantmaple-comparison-owned-")
        owned = Path(worker._temporary.name)
        worker.cleanup_complete = False
        worker._cleanup_only = True
        self.addCleanup(lambda: self.drain(worker))
        try:
            worker.start()
            self.assertTrue(self.spin(lambda: not worker.isRunning()))
            self.assertEqual(worker.outcome.status, "cleanup_failed")
            self.assertFalse(worker.cleanup_complete)
            self.assertIs(worker._process, process)
            self.assertIn(worker, _FULL_IMAGE_OWNERS)
            self.assertTrue(owned.exists())
            process.alive = False
            with patch("prototypes.qt.comparison.multiprocessing.get_context", side_effect=AssertionError("cleanup spawned")):
                self.assertTrue(worker.retry_cleanup())
                self.assertTrue(self.spin(lambda: not worker.isRunning()))
            self.assertTrue(worker.cleanup_complete)
            self.assertIsNone(worker._process)
            self.assertFalse(owned.exists())
            self.assertNotIn(worker, _FULL_IMAGE_OWNERS)
        finally:
            process.alive = False


if __name__ == "__main__":
    unittest.main()
