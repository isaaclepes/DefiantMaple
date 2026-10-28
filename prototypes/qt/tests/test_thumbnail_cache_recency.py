"""In-memory cache eviction regressions; no decoder, catalog or original I/O."""
import os
from pathlib import Path
import tempfile
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from defiantmaple.cached_preview import CachedResult, capture_target
from prototypes.qt.app import AssetDelegate, AssetModel, ThumbnailWorker


class ThumbnailCacheRecencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dm-memory-recency-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.worker = ThumbnailWorker(self.root / "unused.sqlite3", self.root / "unused-cache")
        self.addCleanup(self.worker.stop)

    def asset(self, number):
        return {"asset_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"generated-recency-{number}")),
                "sha256": f"{number:064x}", "byte_size": 1, "media_type": "image/png",
                "revision": 0, "source_id": None,
                "current_path": str(self.root / f"generated-{number}.png")}

    def deliver(self, asset, edge=128, status="ready"):
        self.assertEqual(self.worker.lookup(asset, edge), (None, None))
        generation, captured, queued_edge = self.worker.requests.get_nowait()
        image = QImage(1, 1, QImage.Format.Format_RGBA8888)
        image.fill(QColor(32, 64, 96))
        if status != "ready":
            image = QImage()
        result = CachedResult(status, "Generated cache fixture", capture_target(captured),
                              width=1, height=1, pixels=b"\x20\x40\x60\xff",
                              requested_edge=queued_edge, cache_edge=queued_edge)
        self.worker._received(generation, captured, image, result)

    def paint(self, asset):
        model = QStandardItemModel()
        item = QStandardItem()
        item.setData(asset, AssetModel.AssetRole)
        model.appendRow(item)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 160, 202)
        option.font = self.app.font()
        option.fontMetrics = QFontMetrics(option.font)
        option.palette = self.app.palette()
        rendered = QImage(160, 202, QImage.Format.Format_ARGB32)
        rendered.fill(option.palette.base().color())
        painter = QPainter(rendered)
        AssetDelegate(cell_size=128, thumbnails=self.worker).paint(painter, option, model.index(0, 0))
        painter.end()
        return rendered

    def test_just_painted_image_survives_next_delivery_at_capacity(self):
        for number in range(256):
            self.deliver(self.asset(number))
        visible = self.asset(0)
        self.assertEqual(self.paint(visible).pixelColor(80, 80), QColor(32, 64, 96))
        self.deliver(self.asset(256))
        self.assertTrue(self.worker.key(visible, 128) in self.worker.pixmaps,
                        "A just-painted visible image must not be evicted before a cold entry")
        self.assertNotIn(self.worker.key(self.asset(1), 128), self.worker.pixmaps)
        self.assertEqual(len(self.worker.results), 256)
        self.assertEqual(len(self.worker.pixmaps), 256)
        self.assertEqual(self.paint(visible).pixelColor(80, 80), QColor(32, 64, 96))
        self.assertTrue(self.worker.requests.empty())

    def test_error_hit_preserves_its_metadata_and_evicts_the_cold_entry(self):
        visible = self.asset(0)
        self.deliver(visible, status="refused")
        for number in range(1, 256):
            self.deliver(self.asset(number))
        key = self.worker.key(visible, 128)
        error = self.worker.lookup(visible, 128)[1]
        binding = self.worker.bindings[key]
        self.assertIsNotNone(error)
        self.deliver(self.asset(256))
        self.assertTrue(key in self.worker.errors)
        self.assertEqual(self.worker.lookup(visible, 128), (None, error))
        self.assertEqual(self.worker.bindings[key], binding)
        self.assertNotIn(self.worker.key(self.asset(1), 128), self.worker.results)
        self.assertEqual(len(self.worker.results), 256)
        self.assertEqual(len(self.worker.pixmaps), 255)
        self.assertEqual(len(self.worker.errors), 1)
        self.assertEqual(set(self.worker.bindings), set(self.worker.results))
        self.assertEqual(set(self.worker.pixmaps) | set(self.worker.errors), set(self.worker.results))
        self.assertTrue(self.worker.requests.empty())

    def test_binding_change_and_stale_delivery_cannot_refresh_old_entries(self):
        original, other = self.asset(0), self.asset(1)
        self.deliver(original)
        self.deliver(other)
        old_pixels = self.worker.pixmaps[self.worker.key(original, 128)].toImage()
        revised = dict(original, revision=1)
        self.assertEqual(self.worker.lookup(revised, 128), (None, None))
        key = self.worker.key(original, 128)
        self.assertNotIn(key, self.worker.results)
        self.assertNotIn(key, self.worker.pixmaps)
        order = tuple(self.worker.results)
        image = QImage(1, 1, QImage.Format.Format_RGBA8888)
        image.fill(QColor(32, 64, 96))
        late = CachedResult("ready", "Generated late fixture", capture_target(original),
                            width=1, height=1, pixels=b"\x20\x40\x60\xff",
                            requested_edge=128, cache_edge=128)
        self.worker._received(self.worker.generation, original, image, late)
        self.assertEqual(tuple(self.worker.results), order)
        self.assertNotIn(key, self.worker.pixmaps)
        self.assertEqual(self.worker._wanted[key], (self.worker.generation, self.worker.binding(revised)))
        self.worker._received(self.worker.generation - 1, original, image, late)
        self.assertEqual(tuple(self.worker.results), order)
        self.assertTrue(self.worker._delivery.is_set())
        self.deliver(revised)
        self.assertEqual(self.worker.results[key].target, capture_target(revised))
        self.assertEqual(self.worker.pixmaps[key].toImage(), old_pixels)
        self.assertFalse(self.worker.pending)
        self.assertTrue(self.worker.requests.empty())

    def test_requested_sizes_keep_distinct_keys_and_only_the_hit_is_refreshed(self):
        asset = self.asset(0)
        self.deliver(asset, edge=128)
        self.deliver(asset, edge=144)
        small, large = self.worker.key(asset, 128), self.worker.key(asset, 144)
        self.assertNotEqual(small, large)
        self.assertEqual(tuple(self.worker.results), (small, large))
        self.assertIsNotNone(self.worker.lookup(asset, 128)[0])
        self.assertEqual(tuple(self.worker.results), (large, small))
        self.assertEqual(tuple(self.worker.pixmaps), (large, small))
        self.assertEqual(len(self.worker.results), 2)
        self.assertTrue(self.worker.requests.empty())
