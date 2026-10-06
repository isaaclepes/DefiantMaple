"""Meaningful cache-only async delivery and immutable Qt lifecycle regressions."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from defiantmaple.catalog import initialize, index_file
from defiantmaple.cached_preview import CachedResult, capture_target, generation_refusal, availability_text
from defiantmaple.sources import add_source, scan_sources
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import AssetModel, GalleryWindow, ThumbnailWorker
from prototypes.qt.cached_preview import CachedPreviewDialog, CachedPreviewWorker, result_image


class CachedPreviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="defiantmaple-cache-qt-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.db = self.root / "catalog.sqlite3"
        initialize(self.db)
        self.art = self.root / "generated"
        self.art.mkdir()
        self.media = self.art / ("fictional.png" if os.name == "nt" else "<fictional>.png")
        Image.new("RGBA", (80, 40), (20, 150, 230, 61)).save(self.media)
        self.source = add_source(self.db, self.art, existing_file_policy="inbox")
        scan_sources(self.db, source_id=self.source["source_id"], quiet_seconds=0)
        scan_sources(self.db, source_id=self.source["source_id"], quiet_seconds=0)
        model = AssetModel(self.db)
        self.asset = dict(model.asset_at(0))
        model.close()
        self.cache = self.root / "cache"
        thumbnail_for(self.db, self.asset["asset_id"], self.cache, max_edge=128)

    def spin(self, predicate, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                self.app.processEvents()
                return True
            time.sleep(.005)
        return False

    def snapshot(self):
        return (hashlib.sha256(self.db.read_bytes()).hexdigest(),
                {str(p.relative_to(self.cache)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.cache.rglob('*') if p.is_file()})

    def observed(self, health="offline", disposition="indexed"):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE sources SET health=?", (health,))
            db.execute("UPDATE source_entries SET disposition=?", (disposition,))
        model = AssetModel(self.db)
        row = dict(model.asset_at(0))
        model.close()
        return row

    def test_actual_unavailable_cache_delivery_reopen_metadata_and_guards(self):
        self.art.rename(self.root / "unavailable")
        # Explicit failed scan establishes Offline; return of the file alone is not recovery.
        scan_sources(self.db, source_id=self.source["source_id"], quiet_seconds=0)
        before = self.snapshot()
        with patch("prototypes.qt.app.thumbnail_for", side_effect=AssertionError("original generation")):
            for _ in range(2):
                window = GalleryWindow(self.db, enable_thumbnails=True, cache_root=self.cache,
                                       private_root=self.root / "private")
                try:
                    window.gallery.setCurrentIndex(window.model.index(0))
                    self.app.processEvents()
                    row = window.model.asset_at(0)
                    self.assertEqual(row["source_health"], "offline")
                    self.assertFalse(window.inspect_button.isEnabled())
                    self.assertFalse(window.open_external_button.isEnabled())
                    self.assertFalse(window.open_folder_button.isEnabled())
                    self.assertTrue(window.external_settings_button.isEnabled())
                    self.assertTrue(window.curation_button.isEnabled())
                    self.assertTrue(window.cached_button.isEnabled())
                    self.assertIsNone(window.inspect_selected())
                    window.thumbnails.lookup(row, 144)
                    self.assertTrue(self.spin(lambda: window.thumbnails.lookup(row, 144)[0] is not None))
                    dialog = window.view_cached_selected()
                    self.assertTrue(self.spin(lambda: dialog.result is not None))
                    self.assertEqual(dialog.result.status, "ready")
                    self.assertEqual((dialog.result.width, dialog.result.height), (80, 40))
                    self.assertIn("size fallback 128 (requested 2048)", dialog.status.text())
                    self.assertIn("last source observation: offline", dialog.status.text())
                    self.assertEqual(dialog.status.textFormat(), Qt.TextFormat.PlainText)
                    self.assertIn("asset_id", window.detail.toPlainText())
                    dialog.background_box.setCurrentText("Dark")
                    dialog.zoom_in_button.click()
                    dialog.fit_button.click()
                finally:
                    self.assertTrue(window.close())
        self.assertEqual(before, self.snapshot())
        (self.root / "unavailable").rename(self.art)
        model = AssetModel(self.db)
        self.assertEqual(model.asset_at(0)["source_health"], "offline")
        model.close()
        scan_sources(self.db, source_id=self.source["source_id"], quiet_seconds=0)
        model = AssetModel(self.db)
        self.assertIsNone(generation_refusal(model.asset_at(0)))
        model.close()

    def test_denied_missing_scanning_and_unresolved_read_cache_without_generator(self):
        self.media.unlink()
        with patch("prototypes.qt.app.thumbnail_for", side_effect=AssertionError("generator")):
            for health, disposition in (("permission_denied", "indexed"), ("paused", "missing"),
                                        ("scanning", "indexed"), ("error", "error")):
                row = self.observed(health, disposition)
                worker = ThumbnailWorker(self.db, self.cache)
                worker.start()
                try:
                    worker.lookup(row, 144)
                    self.assertTrue(self.spin(lambda: worker.lookup(row, 144)[0] is not None))
                    self.assertIn(health.replace('_', ' '), worker.description(row, 144))
                    self.assertIsNotNone(generation_refusal(row))
                finally:
                    self.assertTrue(worker.stop())

    def test_actual_alpha_aspect_orientation_and_owned_raw_qimage(self):
        worker = CachedPreviewWorker(self.db, self.asset, self.cache)
        delivered = []
        worker.completed.connect(lambda image, result: delivered.append((image, result, QThread.currentThread())))
        worker.start()
        self.assertTrue(self.spin(lambda: delivered and not worker.isRunning()))
        image, result, receiving_thread = delivered[0]
        self.assertEqual(receiving_thread, self.app.thread())
        self.assertEqual((image.width(), image.height()), (80, 40))
        self.assertEqual(image.pixelColor(0, 0).alpha(), 61)
        del worker
        self.assertEqual(image.pixelColor(0, 0).blue(), 230)
        # Legacy policy transposes EXIF orientation before cache publication.
        oriented = self.art / "oriented.jpg"
        exif = Image.Exif(); exif[274] = 6
        Image.new("RGB", (60, 30), (255, 0, 20)).save(oriented, exif=exif)
        asset_id = index_file(self.db, oriented)
        thumbnail_for(self.db, asset_id, self.cache, max_edge=128)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
        oriented.unlink()
        second = CachedPreviewWorker(self.db, row, self.cache)
        second.start()
        self.assertTrue(self.spin(lambda: not second.isRunning()))
        self.assertEqual((second.outcome.width, second.outcome.height), (30, 60))
        self.assertTrue(second.outcome.cleanup_complete)
        if sys.platform.startswith("linux"):
            self.assertTrue(result.address_space_enforced)
            self.assertIn("536870912", result.address_space_note)

    def test_actual_revision_drift_preserves_target_and_content_drift_refuses(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE assets SET revision=revision+1,rating=4")
        dialog = CachedPreviewDialog(self.db, self.asset, self.cache)
        try:
            self.assertTrue(self.spin(lambda: dialog.result is not None))
            self.assertTrue(dialog.result.catalog_drift)
            self.assertEqual(dialog.target, capture_target(self.asset))
            self.assertIn("catalog metadata/location changed", dialog.status.text())
        finally:
            self.assertTrue(dialog.close())
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE assets SET sha256=?", ('a' * 64,))
        second = CachedPreviewDialog(self.db, self.asset, self.cache)
        try:
            self.assertTrue(self.spin(lambda: second.result is not None))
            self.assertEqual(second.result.status, "refused")
            self.assertIsNone(second.canvas._item)
            self.assertIn("Indexed content changed", second.status.text())
        finally:
            self.assertTrue(second.close())

    def test_pending_inspector_does_not_retarget_on_selection_filter_refresh(self):
        started, release = threading.Event(), threading.Event()
        target = capture_target(self.asset)
        def waiting(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(3))
            return CachedResult("ready", "cached", target, width=2, height=1, pixels=b'\xff\x00\x00\xff' * 2,
                                requested_edge=2048, cache_edge=128, catalog_drift=True)
        window = GalleryWindow(self.db, cache_root=self.cache, private_root=self.root / "private")
        self.addCleanup(window.close)
        with patch("prototypes.qt.cached_preview.read_cached_preview", side_effect=waiting):
            window.gallery.setCurrentIndex(window.model.index(0))
            dialog = window.view_cached_selected()
            self.assertTrue(self.spin(started.is_set))
            window.model.set_metadata_filters(search="absent")
            window.model.refresh()
            self.assertEqual(dialog.target, target)
            release.set()
            self.assertTrue(self.spin(lambda: dialog.result is not None))
            self.assertEqual(dialog.result.target, target)
            self.assertTrue(dialog.close())

    def test_actual_miss_boundary_fresh_requery_and_no_upgrade(self):
        # Cache-only read blocked briefly, then availability changes before miss is returned.
        entered, release = threading.Event(), threading.Event()
        def miss(database, target, cache, edge, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return CachedResult("no_cache", "No cached preview", target, requested_edge=edge)
        for initial_unavailable in (False, True):
            row = self.observed("offline" if initial_unavailable else "paused")
            release.clear(); entered.clear()
            worker = ThumbnailWorker(self.db, self.root / "empty")
            with patch("prototypes.qt.app.read_cached_preview", side_effect=miss), patch(
                    "prototypes.qt.app.thumbnail_for", side_effect=AssertionError("must not generate")):
                worker.start()
                try:
                    worker.lookup(row, 144)
                    self.assertTrue(self.spin(entered.is_set))
                    self.observed("paused" if initial_unavailable else "offline")
                    release.set()
                    self.assertTrue(self.spin(lambda: worker.lookup(row, 144)[1] is not None))
                    self.assertIn("Original unavailable", worker.lookup(row, 144)[1])
                finally:
                    release.set(); self.assertTrue(worker.stop())

    def test_available_and_standalone_miss_generates_then_validates_off_gui(self):
        row = self.asset
        worker = ThumbnailWorker(self.db, self.root / "fresh")
        worker.start()
        try:
            worker.lookup(row, 144)
            self.assertTrue(self.spin(lambda: worker.lookup(row, 144)[0] is not None, seconds=12))
            result = worker.results[worker.key(row, 144)]
            self.assertEqual(result.status, "ready")
            self.assertEqual(result.cache_edge, 144)
            self.assertEqual(result.pixels, b"")
        finally:
            self.assertTrue(worker.stop())
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE source_entries SET asset_id=NULL")
            db.execute("UPDATE assets SET source_id=NULL")
        model = AssetModel(self.db)
        standalone = model.asset_at(0); model.close()
        self.assertIsNone(generation_refusal(standalone))
        self.assertIn("availability unchecked", availability_text(standalone))

    def test_same_generation_new_binding_rejects_old_callback_before_delivery(self):
        entered_a, release_a = threading.Event(), threading.Event()
        entered_b, release_b = threading.Event(), threading.Event()
        row_b = dict(self.asset, revision=self.asset["revision"] + 1,
                     current_path=str(self.art / "relocated.png"), entry_path=str(self.art / "relocated.png"))
        def waiting(database, target, cache, edge, **kwargs):
            if target.revision == self.asset["revision"]:
                entered_a.set()
                self.assertTrue(release_a.wait(3))
            else:
                entered_b.set()
                self.assertTrue(release_b.wait(3))
            return CachedResult("ready", "cached", target, width=2, height=1,
                                pixels=b'\xff\x00\x00\xff' * 2,
                                requested_edge=edge, cache_edge=128)
        worker = ThumbnailWorker(self.db, self.cache)
        with patch("prototypes.qt.app.read_cached_preview", side_effect=waiting):
            worker.start()
            try:
                worker.lookup(self.asset, 128)
                self.assertTrue(self.spin(entered_a.is_set))
                worker.lookup(row_b, 128)
                release_a.set()
                self.assertTrue(self.spin(entered_b.is_set))
                self.app.processEvents()
                self.assertFalse(worker.pixmaps)
                self.assertFalse(worker.results)
                self.assertEqual(len(worker.pending), 1)
                release_b.set()
                self.assertTrue(self.spin(lambda: worker.lookup(row_b, 128)[0] is not None))
                key = worker.key(row_b, 128)
                self.assertEqual(worker.results[key].target, capture_target(row_b))
                self.assertEqual(worker.bindings[key], worker.binding(row_b))
                worker.invalidate_pending()
                self.assertFalse(worker._wanted)
            finally:
                release_a.set(); release_b.set()
                self.assertTrue(worker.stop())

    def test_responsive_cancel_close_and_late_signals_are_refused(self):
        started, cancel_seen, heartbeat = threading.Event(), threading.Event(), threading.Event()
        target = capture_target(self.asset)
        def waiting(database, target, cache, edge, limits, cancel):
            started.set()
            self.assertTrue(cancel.wait(3))
            cancel_seen.set()
            return CachedResult("cancelled", "Canceled", target, requested_edge=edge)
        with patch("prototypes.qt.cached_preview.read_cached_preview", side_effect=waiting):
            dialog = CachedPreviewDialog(self.db, self.asset, self.cache)
            self.assertTrue(self.spin(started.is_set))
            QTimer.singleShot(0, heartbeat.set)
            self.assertTrue(self.spin(heartbeat.is_set))
            self.assertFalse(cancel_seen.is_set())
            self.assertTrue(dialog.close())
            self.assertTrue(cancel_seen.is_set())
            late = CachedResult("ready", "late", target, width=1, height=1,
                                pixels=b'\x00\x00\x00\xff', requested_edge=2048, cache_edge=128)
            dialog._received(result_image(late), late)
            self.assertIsNone(dialog.canvas._item)
            self.assertIsNone(dialog.result)
        worker = ThumbnailWorker(self.db, self.cache)
        worker.lookup(self.asset, 144)
        old = worker.generation
        worker.invalidate_pending()
        worker._received(old, self.asset, QImage(), CachedResult("refused", "late", target, requested_edge=144))
        self.assertFalse(worker.errors)
        self.assertFalse(worker.pending)
        self.assertLessEqual(worker.requests.qsize(), 32)

    def test_cleanup_failure_retains_dialog_and_refuses_replacement(self):
        target = capture_target(self.asset)
        outcome = CachedResult("cleanup_failed", "owned", target, cleanup_complete=False)
        with patch("prototypes.qt.cached_preview.read_cached_preview", return_value=outcome):
            dialog = CachedPreviewDialog(self.db, self.asset, self.cache)
            self.assertTrue(self.spin(lambda: not dialog.worker.isRunning()))
            self.assertFalse(dialog.close())
            self.assertIn("ownership retained", dialog.status.text())
            # Test-only recovery avoids leaking its parentless widget.
            dialog.worker.outcome = CachedResult("cancelled", "reaped", target)
            self.assertTrue(dialog.close())
        worker = ThumbnailWorker(self.db, self.cache)
        worker._received(-1, self.asset, QImage(), outcome)
        self.assertTrue(worker.cleanup_failed)
        self.assertIn("replacement refused", worker.lookup(self.asset, 144)[1])

    def test_large_fallback_grid_is_reduced_and_metadata_has_no_raw_buffer(self):
        large = self.art / "large.png"
        Image.new("RGBA", (1024, 512), (20, 150, 230, 61)).save(large)
        asset_id = index_file(self.db, large)
        thumbnail_for(self.db, asset_id, self.cache, max_edge=2048)
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
        large.unlink()
        worker = ThumbnailWorker(self.db, self.cache)
        worker.start()
        try:
            worker.lookup(row, 128)
            self.assertTrue(self.spin(lambda: worker.lookup(row, 128)[0] is not None))
            pixmap = worker.lookup(row, 128)[0]
            self.assertEqual((pixmap.width(), pixmap.height()), (128, 64))
            self.assertEqual(pixmap.toImage().pixelColor(0, 0).alpha(), 61)
            result = worker.results[worker.key(row, 128)]
            self.assertEqual((result.width, result.height, result.cache_edge), (1024, 512, 2048))
            self.assertEqual(result.pixels, b"")
            self.assertIn("1024 × 512 pixels", worker.description(row, 128))
            self.assertIn("size fallback 2048", worker.description(row, 128))
            self.assertLessEqual(len(worker.results), 256)
        finally:
            self.assertTrue(worker.stop())

    def test_corrupt_preferred_cache_and_unsafe_root_refuse_without_generation(self):
        png = next(self.cache.rglob("*.png"))
        original = png.read_bytes()
        png.write_bytes(b"corrupt")
        with patch("prototypes.qt.app.thumbnail_for", side_effect=AssertionError("repair/generation")):
            worker = ThumbnailWorker(self.db, self.cache)
            worker.start()
            try:
                worker.lookup(self.asset, 128)
                self.assertTrue(self.spin(lambda: worker.lookup(self.asset, 128)[1] is not None))
                self.assertIn("refused", worker.lookup(self.asset, 128)[1])
                self.assertFalse(worker.pixmaps)
            finally:
                self.assertTrue(worker.stop())
        png.write_bytes(original)
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.cache, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Cache symlink capability unavailable on this host")
        worker = CachedPreviewWorker(self.db, self.asset, alias)
        worker.start()
        self.assertTrue(self.spin(lambda: not worker.isRunning()))
        self.assertEqual(worker.outcome.status, "refused")
        self.assertEqual(worker.outcome.pixels, b"")

    def test_malformed_identity_is_per_item_refusal_and_does_not_destroy_gallery(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE assets SET sha256='malformed'")
        window = GalleryWindow(self.db, cache_root=self.cache, private_root=self.root / "private")
        try:
            window.gallery.setCurrentIndex(window.model.index(0))
            row = window.model.asset_at(0)
            worker = ThumbnailWorker(self.db, self.cache)
            self.assertIn("invalid indexed identity", worker.lookup(row, 144)[1])
            self.assertEqual(worker.requests.qsize(), 0)
            self.assertIsNone(window.view_cached_selected())
            self.assertIn("invalid indexed identity", window.statusBar().currentMessage())
            self.assertTrue(window.curation_button.isEnabled())
        finally:
            self.assertTrue(window.close())

    def test_cli_cache_only_smoke_with_unavailable_original_preserves_fixture(self):
        self.media.rename(self.art / "moved.png")
        before = self.snapshot()
        completed = subprocess.run([sys.executable, '-m', 'prototypes.qt.app', '--catalog', str(self.db),
                                    '--smoke-cached-preview-id', self.asset['asset_id'],
                                    '--smoke-cache-root', str(self.cache)],
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        import json
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual((result['width'], result['height']), (80, 40))
        self.assertEqual(result['address_space_bytes'], 512 * 1024 * 1024)
        self.assertTrue(result['cleanup_complete'])
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
