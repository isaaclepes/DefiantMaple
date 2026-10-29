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
from PySide6.QtGui import QColor, QFontMetrics, QImage, QKeyEvent, QPainter, QPixmap, QPalette, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QStyle

from defiantmaple.catalog import index_file, initialize
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.tests.thumbnail_fixture import isolate_thumbnail_authority
from prototypes.qt.app import AssetDelegate, AssetModel, GalleryWindow, ThumbnailWorker
from prototypes.qt.identity import APP_ID, app_icon
from prototypes.qt.package import stage_linux_desktop_files
from prototypes.qt.preview import FullImageDialog, PreviewCanvas, PreviewLimits
from prototypes.qt.tests.gallery_wait import (
    close_window_and_wait, wait_for_asset_at, wait_for_generation_after,
    wait_for_initial_generation, wait_for_rank, wait_for_selected_asset,
    wait_for_gateway_condition, wait_for_startup_validation,
)


class ThumbnailThemePaintTests(unittest.TestCase):
    """Small offscreen render fixtures; no library, cache worker or decoder."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def palette(self, dark):
        palette = QPalette(self.app.palette())
        palette.setColor(QPalette.ColorRole.Base, QColor("#20252a" if dark else "#f5f1e9"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e4dfd6" if dark else "#172c36"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#385b87"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#fff3ab"))
        return palette

    def render(self, delegate, palette, mime="image/jpeg", selected=False):
        model = QStandardItemModel()
        item = QStandardItem()
        item.setData({"media_type": mime, "current_path": "generated.png",
                      "availability": "available"}, AssetModel.AssetRole)
        model.appendRow(item)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 160, 202)
        option.font = self.app.font()
        option.fontMetrics = QFontMetrics(option.font)
        option.palette = palette
        if selected:
            option.state |= QStyle.StateFlag.State_Selected
        image = QImage(160, 202, QImage.Format.Format_ARGB32)
        image.fill(palette.base().color())
        painter = QPainter(image)
        delegate.paint(painter, option, model.index(0, 0))
        painter.end()
        return image

    def contains(self, image, rect, color):
        return any(image.pixelColor(x, y) == color for y in range(rect.top(), rect.bottom() + 1)
                   for x in range(rect.left(), rect.right() + 1))

    def test_loading_error_and_media_placeholders_follow_light_and_dark_palette(self):
        class Pending:
            def lookup(self, *_args):
                return None, None
        class Refused:
            def lookup(self, *_args):
                return None, "Cache refused"
        for dark in (False, True):
            palette = self.palette(dark)
            for thumbnails in (Pending(), Refused(), None):
                delegate = AssetDelegate(thumbnails=thumbnails)
                for mime in ("image/jpeg", "image/png", "image/webp", "video/mp4", "other/type"):
                    with self.subTest(dark=dark, status=type(thumbnails).__name__, mime=mime):
                        image = self.render(delegate, palette, mime)
                        self.assertEqual(image.pixelColor(80, 20), palette.base().color())
                        self.assertTrue(self.contains(image, QRect(8, 8, 144, 152), palette.text().color()))

    def test_letterbox_and_transparent_pixels_repaint_from_palette_without_changing_alpha(self):
        pixmap = QPixmap(128, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.fillRect(QRect(0, 0, 64, 32), QColor(255, 0, 0, 128))
        painter.end()
        before = pixmap.toImage()
        class Cached:
            def lookup(self, *_args):
                return pixmap, None
        delegate = AssetDelegate(thumbnails=Cached())
        for dark in (False, True):
            palette = self.palette(dark)
            image = self.render(delegate, palette)
            self.assertEqual(image.pixelColor(80, 20), palette.base().color())
            self.assertEqual(image.pixelColor(80, 125), palette.base().color())
            self.assertEqual(image.pixelColor(130, 75), palette.base().color())
            self.assertNotEqual(image.pixelColor(20, 75), palette.base().color())
            self.assertNotEqual(image.pixelColor(20, 75), QColor("red"))
        self.assertEqual(pixmap.toImage(), before)
        self.assertEqual(before.pixelColor(20, 15).alpha(), 128)
        self.assertEqual(before.pixelColor(100, 15).alpha(), 0)

    def test_selection_retains_theme_highlight_and_legible_text(self):
        class Pending:
            def lookup(self, *_args):
                return None, None
        delegate = AssetDelegate(thumbnails=Pending())
        for dark in (False, True):
            palette = self.palette(dark)
            image = self.render(delegate, palette, selected=True)
            self.assertEqual(image.pixelColor(2, 2), palette.highlight().color())
            self.assertEqual(image.pixelColor(80, 20), palette.base().color())
            self.assertTrue(self.contains(image, QRect(8, 8, 144, 152), palette.text().color()))
            self.assertTrue(self.contains(image, QRect(8, 165, 144, 35), palette.highlightedText().color()))


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
        isolate_thumbnail_authority(self, self.db, self.root)

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
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=1)
        row = wait_for_rank(window, asset_id)
        return window, wait_for_asset_at(window, row, asset_id), source

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
        self.assertEqual(rendered.pixelColor(80, 20), option.palette.base().color())
        self.assertEqual(rendered.pixelColor(80, 70), QColor("#ff0000"))
        self.assertEqual(rendered.pixelColor(80, 125), option.palette.base().color())

    def test_all_sources_paints_real_cached_thumbnail(self):
        source = self.root / "all-sources.png"
        Image.new("RGB", (320, 80), (242, 28, 48)).save(source)
        asset_id = index_file(self.db, source)
        window = GalleryWindow(self.db, enable_thumbnails=True,
                               cache_root=self.root / "ui-cache",
                               private_root=self.root / "private")
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=1)
        wait_for_gateway_condition(
            window,
            lambda: window.source_box.count() >= 1 and window.source_box.currentIndex() == 0,
            description='All Sources choice in legacy source list',
        )
        self.assertEqual(window.source_box.currentIndex(), 0)
        self.assertIsNone(window.source_box.currentData())
        self.assertIs(window.delegate.thumbnails, window.thumbnails)
        window.show()
        self.app.processEvents()
        row = wait_for_rank(window, asset_id)
        wait_for_asset_at(window, row, asset_id)
        index = window.model.index(row)
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
        previous_generation = window.model._generation
        window.model.refresh()
        wait_for_generation_after(window, previous_generation, expected_count=2,
                                  description='second indexed asset generation')
        row = wait_for_rank(window, asset["asset_id"])
        wait_for_asset_at(window, row, asset["asset_id"])
        window.gallery.setCurrentIndex(window.model.index(row))
        wait_for_selected_asset(window, asset['asset_id'], row=row)
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
        self.assertEqual(dialog.zoom_100_button.accessibleName(), "Set zoom to 100 percent")
        dialog.zoom_100_button.click()
        self.assertAlmostEqual(dialog.canvas.transform().m11(), 1.0)
        self.assertFalse(dialog.canvas._fit)
        dialog.resize(800, 650)
        self.app.processEvents()
        self.assertAlmostEqual(dialog.canvas.transform().m11(), 1.0)
        dialog.canvas.zoom(1.25)
        self.app.sendEvent(dialog.zoom_in_button, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1,
                                                          Qt.KeyboardModifier.NoModifier, "1"))
        self.assertAlmostEqual(dialog.canvas.transform().m11(), 1.0)
        self.assertEqual(dialog.asset["asset_id"], asset["asset_id"])
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

    def test_hundred_percent_with_no_image_is_safe(self):
        canvas = PreviewCanvas()
        self.addCleanup(canvas.close)
        before = (canvas.transform(), canvas._fit, canvas._scale)
        canvas.zoom_100_percent()
        self.assertEqual((canvas.transform(), canvas._fit, canvas._scale), before)
        image = QPixmap(60, 20)
        image.fill(QColor(20, 40, 60, 80))
        canvas.set_image(image)
        canvas.zoom_100_percent()
        self.assertAlmostEqual(canvas.transform().m11(), 1.0)
        self.assertEqual(canvas._item.pixmap().toImage().pixelColor(0, 0).alpha(), 80)

    def test_exif_orientation_and_changed_source_error(self):
        source = self.root / "oriented.jpg"
        image = Image.new("RGB", (40, 20), (180, 20, 25))
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        asset_id = index_file(self.db, source)
        window = GalleryWindow(self.db)
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=1)
        row = wait_for_rank(window, asset_id)
        asset = wait_for_asset_at(window, row, asset_id)
        thumb = thumbnail_for(self.db, asset_id, self.root / "cache", max_edge=80)
        self.assertEqual((thumb["width"], thumb["height"]), (20, 40))
        dialog = FullImageDialog(asset, database=self.db)
        self.addCleanup(dialog.close)
        self.assertTrue(self.spin(lambda: dialog.canvas._item is not None))
        self.assertEqual((dialog.canvas._item.pixmap().width(),
                          dialog.canvas._item.pixmap().height()), (20, 40))
        source.write_bytes(source.read_bytes() + b"modified")
        changed = FullImageDialog(asset, database=self.db)
        self.addCleanup(changed.close)
        self.assertTrue(self.spin(lambda: "fingerprint" in changed.status.text().lower()))
        self.assertIsNone(changed.canvas._item)

    def test_close_during_decode_and_thumbnail_queue_invalidation(self):
        window, asset, _ = self.asset()
        dialog = FullImageDialog(asset, database=self.db)
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
