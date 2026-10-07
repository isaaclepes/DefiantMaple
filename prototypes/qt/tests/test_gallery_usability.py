"""Focused gallery rendering, full-source inspect, scheduling and identity regressions."""
import os
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from defiantmaple.catalog import index_file, initialize
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import AssetDelegate, GalleryWindow, ThumbnailWorker
from prototypes.qt.identity import APP_ID, app_icon
from prototypes.qt.package import stage_linux_desktop_files
from prototypes.qt.preview import FullImageDialog, PreviewLimits


class GalleryUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)
        self.db = self.root / "catalog.sqlite3"
        initialize(self.db)

    def spin(self, condition, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(.01)
        return False

    def asset(self, name="source.png", size=(320, 80), color=(230, 35, 60, 255)):
        source = self.root / name
        Image.new("RGBA", size, color).save(source)
        asset_id = index_file(self.db, source)
        window = GalleryWindow(self.db, enable_thumbnails=False)
        self.addCleanup(window.close)
        row = window.model.row_for_asset(asset_id)
        return window, window.model.asset_at(row), source

    def test_thumbnail_delegate_centers_without_stretching(self):
        window, asset, _ = self.asset()
        index = window.model.index(0)
        pixmap = QPixmap(128, 32)
        pixmap.fill(QColor("#ff0000"))
        class Cached:
            def lookup(self, *_args):
                return pixmap, None
        delegate = AssetDelegate(cell_size=144, thumbnails=Cached())
        rendered = QImage(160, 202, QImage.Format.Format_RGB32)
        rendered.fill(QColor("#ffffff"))
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 160, 202)
        option.font = self.app.font()
        option.fontMetrics = QFontMetrics(option.font)
        option.palette = self.app.palette()
        painter = QPainter(rendered)
        delegate.paint(painter, option, index)
        painter.end()
        self.assertEqual(rendered.pixelColor(80, 20), QColor("#577590"))
        self.assertEqual(rendered.pixelColor(80, 70), QColor("#ff0000"))
        self.assertEqual(rendered.pixelColor(80, 125), QColor("#577590"))

    def test_all_sources_paints_real_cached_thumbnail(self):
        source = self.root / "all-sources.png"
        Image.new("RGB", (320, 80), (242, 28, 48)).save(source)
        asset_id = index_file(self.db, source)
        window = GalleryWindow(self.db, enable_thumbnails=True,
                               cache_root=self.root / "ui-cache",
                               private_root=self.root / "private")
        self.addCleanup(window.close)
        self.assertEqual(window.source_box.currentIndex(), 0)
        self.assertIsNone(window.source_box.currentData())
        self.assertIs(window.delegate.thumbnails, window.thumbnails)
        window.show()
        self.app.processEvents()
        index = window.model.index(window.model.row_for_asset(asset_id))
        window.gallery.scrollTo(index)
        window.gallery.viewport().repaint()  # Paint must enqueue the visible asset.
        asset = window.model.asset_at(index.row())
        key = (asset_id, asset["sha256"], asset["byte_size"], 144)
        self.assertTrue(self.spin(lambda: key in window.thumbnails.pixmaps or
                                  key in window.thumbnails.errors))
        self.assertNotIn(key, window.thumbnails.errors)
        self.assertEqual(window.thumbnails.pixmaps[key].size().toTuple(), (144, 36))
        window.gallery.viewport().repaint()
        rect = window.gallery.visualRect(index)
        thumb = QRect(rect.left() + 8, rect.top() + 8,
                      rect.width() - 16, max(24, rect.height() - 50))
        screen_pixel = window.gallery.viewport().grab().toImage().pixelColor(thumb.center())
        self.assertEqual(screen_pixel, QColor(242, 28, 48))

    def test_original_pixels_orientation_and_captured_selection(self):
        window, asset, source = self.asset(size=(321, 81))
        second = self.root / "second.png"
        Image.new("RGB", (20, 20), (12, 30, 250)).save(second)
        index_file(self.db, second)
        window.model.refresh()
        row = window.model.row_for_asset(asset["asset_id"])
        window.gallery.setCurrentIndex(window.model.index(row))
        dialog = window.inspect_selected()
        self.addCleanup(dialog.close)
        self.assertIsInstance(dialog, FullImageDialog)
        self.assertTrue(self.spin(lambda: dialog.canvas._item is not None or
                                  "Loading" not in dialog.status.text()))
        self.assertIsNotNone(dialog.canvas._item, dialog.status.text())
        self.assertEqual((dialog.canvas._item.pixmap().width(),
                          dialog.canvas._item.pixmap().height()), (321, 81))
        self.assertEqual(dialog.canvas._item.pixmap().toImage().pixelColor(0, 0),
                         QColor(230, 35, 60, 255))
        self.assertIn("321 × 81", dialog.status.text())
        window.gallery.setCurrentIndex(window.model.index(1 - row))
        self.assertEqual(dialog.asset["asset_id"], asset["asset_id"])
        dialog.canvas.zoom(1.25)
        self.assertFalse(dialog.canvas._fit)
        dialog.fit_button.click()
        self.assertTrue(dialog.canvas._fit)
        dialog.background_box.setCurrentText("Dark")
        self.assertEqual(dialog.canvas.backgroundBrush().color(), QColor("#222222"))
        self.app.sendEvent(dialog.canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F11,
                                                   Qt.KeyboardModifier.NoModifier))
        self.assertTrue(dialog.isFullScreen())
        self.app.sendEvent(dialog.canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F11,
                                                   Qt.KeyboardModifier.NoModifier))
        self.assertFalse(dialog.isFullScreen())
        before_state = window.model.asset_at(row)["workflow_state"]
        self.app.sendEvent(dialog.canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_3,
                                                   Qt.KeyboardModifier.NoModifier, "3"))
        self.assertEqual(window.model.asset_at(row)["workflow_state"], before_state)
        self.app.sendEvent(dialog.canvas, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                                   Qt.KeyboardModifier.NoModifier))
        self.assertFalse(dialog.isVisible())
        self.assertEqual(source.stat().st_size, asset["byte_size"])

    def test_exif_orientation_and_changed_source_error(self):
        source = self.root / "oriented.jpg"
        image = Image.new("RGB", (40, 20), (180, 20, 25))
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        asset_id = index_file(self.db, source)
        window = GalleryWindow(self.db)
        self.addCleanup(window.close)
        asset = window.model.asset_at(window.model.row_for_asset(asset_id))
        thumb = thumbnail_for(self.db, asset_id, self.root / "cache", max_edge=80)
        self.assertEqual((thumb["width"], thumb["height"]), (20, 40))
        dialog = FullImageDialog(asset)
        self.addCleanup(dialog.close)
        self.assertTrue(self.spin(lambda: dialog.canvas._item is not None))
        self.assertEqual((dialog.canvas._item.pixmap().width(),
                          dialog.canvas._item.pixmap().height()), (20, 40))
        source.write_bytes(source.read_bytes() + b"modified")
        changed = FullImageDialog(asset)
        self.addCleanup(changed.close)
        self.assertTrue(self.spin(lambda: "fingerprint" in changed.status.text().lower()))
        self.assertIsNone(changed.canvas._item)

    def test_close_during_decode_and_thumbnail_queue_invalidation(self):
        window, asset, _ = self.asset()
        dialog = FullImageDialog(asset)
        dialog.close()
        self.assertTrue(self.spin(lambda: not dialog.worker.isRunning()))
        self.assertTrue(dialog.worker.cleanup_complete)
        self.assertTrue(dialog.close())
        self.assertFalse(dialog.worker.isRunning())
        worker = ThumbnailWorker(self.db, self.root / "cache")
        self.assertEqual(worker.lookup(asset, 96), (None, None))
        self.assertEqual(worker.requests.qsize(), 1)
        old_generation = worker.generation
        worker.invalidate_pending()
        self.assertEqual(worker.requests.qsize(), 0)
        self.assertFalse(worker.pending)
        self.assertGreater(worker.generation, old_generation)
        self.assertEqual(worker.lookup(asset, 128), (None, None))
        self.assertEqual(worker.requests.qsize(), 1)

    def test_active_thumbnail_cache_wait_does_not_block_close(self):
        window, asset, _ = self.asset(size=(128, 64))
        worker = ThumbnailWorker(self.db, self.root / "slow-cache")
        fingerprint = f"sha256-{asset['sha256']}-bytes-{asset['byte_size']}"
        item_root = self.root / "slow-cache" / asset["asset_id"][:2] / asset["asset_id"] / fingerprint
        item_root.mkdir(parents=True)
        policy = "b536870912-d32768-p80000000"
        (item_root / f".thumbnail-v1-e128-{policy}.lock").write_text(
            json.dumps({"expires_at": time.time() + 60, "token": "test"}))
        worker.start()
        self.assertEqual(worker.lookup(asset, 128), (None, None))
        self.assertTrue(self.spin(lambda: worker.requests.qsize() == 0))
        time.sleep(.1)
        began = time.monotonic()
        self.assertTrue(worker.stop())
        self.assertLess(time.monotonic() - began, 2.5)
        self.assertFalse(worker.isRunning())

    def test_thumbnail_decoder_start_failure_is_visible(self):
        _window, asset, _source = self.asset()
        worker = ThumbnailWorker(self.db, self.root / "error-cache")
        self.addCleanup(worker.stop)
        key = (asset["asset_id"], asset["sha256"], asset["byte_size"], 128)
        with patch("defiantmaple.thumbnail._run_decoder",
                   side_effect=RuntimeError("decoder process could not start")):
            worker.start()
            worker.lookup(asset, 128)
            self.assertTrue(self.spin(lambda: key in worker.errors))
            self.assertIn("decoder process could not start", worker.errors[key])
            self.assertTrue(worker.stop())
            self.assertTrue(worker.stop(), "Stopping an already-reaped worker must be safe")

    def test_desktop_identity_and_packaged_assets(self):
        self.assertEqual(APP_ID, "io.github.isaaclepes.DefiantMaple")
        self.assertFalse(app_icon().isNull())
        staged = stage_linux_desktop_files(self.root / "DefiantMapleQt.bin")
        desktop = (staged / f"{APP_ID}.desktop").read_text()
        self.assertIn("Name=DefiantMaple\n", desktop)
        self.assertIn(f"Icon={APP_ID}\n", desktop)
        self.assertIn("Exec=DefiantMapleQt.bin\n", desktop)
        self.assertTrue((staged / f"{APP_ID}.png").is_file())


if __name__ == "__main__":
    unittest.main()
