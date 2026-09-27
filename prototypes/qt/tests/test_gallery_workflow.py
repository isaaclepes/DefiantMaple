import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from defiantmaple.catalog import initialize
from defiantmaple.sources import add_source, list_sources
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import GalleryWindow, LibraryLauncher


class GalleryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "library.sqlite3"
        initialize(self.db)
        self.art = self.root / "fictional-art"
        self.art.mkdir()
        Image.new("RGBA", (96, 96), (100, 40, 180, 110)).save(self.art / "one.png")
        (self.art / "two.png").write_bytes((self.art / "one.png").read_bytes())
        self.source = add_source(self.db, self.art, existing_file_policy="inbox")

    def spin_until(self, condition, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                self.app.processEvents()
                return True
            time.sleep(.01)
        return False

    def test_launcher_creates_library_and_source_dialog_sets_policy(self):
        launcher = LibraryLauncher()
        self.addCleanup(launcher.close)
        created = self.root / "fresh.sqlite3"
        with patch("prototypes.qt.app.QFileDialog.getSaveFileName",
                   return_value=(str(created), "")):
            launcher.create_library()
        self.assertTrue(created.exists())
        window = launcher.gallery_window
        self.assertIsNotNone(window)
        self.addCleanup(window.close)
        with patch("prototypes.qt.app.QFileDialog.getExistingDirectory",
                   return_value=str(self.art)), patch(
                       "prototypes.qt.app.QInputDialog.getItem",
                       return_value=("Ignore Until Modified", True)):
            window._add_source_dialog()
        self.assertEqual(list_sources(created)[0]["existing_file_policy"],
                         "ignore_until_modified")
        self.assertEqual(window.source_box.currentData(), list_sources(created)[0]["source_id"])

    def test_scan_stays_responsive_then_shows_thumbnails_details_and_duplicates(self):
        (self.art / "unsupported.txt").write_text("fictional unsupported file")
        window = GalleryWindow(self.db, enable_thumbnails=True,
                               cache_root=self.root / "thumbs",
                               private_root=self.root / "private")
        self.addCleanup(window.close)
        window.show()
        window.source_box.setCurrentIndex(1)
        window.start_source_scan()
        while_running = []
        QTimer.singleShot(100, lambda: while_running.append(window.scan_worker.isRunning()))
        self.assertTrue(self.spin_until(lambda: not window.scan_worker.isRunning()))
        self.assertEqual(while_running, [True])
        self.assertEqual(window.model.rowCount(), 2)
        self.assertEqual(window.issues_list.count(), 1)
        self.assertIn("unsupported", window.issues_list.item(0).text())
        asset = window.model.asset_at(0)
        self.assertEqual(asset["source_id"], self.source["source_id"])
        window.gallery.setCurrentIndex(window.model.index(0))
        self.app.processEvents()
        self.assertIn("provenance", window.detail.toPlainText())
        self.assertIn("fictional-art", window.detail.toPlainText())
        window.size_slider.setValue(192)
        self.assertEqual(window.delegate.cell_size, 192)
        window.thumbnails.lookup(asset, 192)
        self.assertTrue(self.spin_until(lambda: window.thumbnails.lookup(asset, 192)[0] is not None))
        self.assertTrue(thumbnail_for(self.db, asset["asset_id"], self.root / "thumbs",
                                      max_edge=192)["cache_hit"])
        window.refresh_duplicates()
        self.assertEqual(window.duplicates_list.count(), 1)
        window._duplicate_selected(window.duplicates_list.item(0))
        self.assertEqual(window.model.rowCount(), 2)
        window.gallery.setCurrentIndex(window.model.index(0))
        window.set_selected_state("reviewed")
        self.assertEqual(window.model.asset_at(0)["workflow_state"], "reviewed")
        window.filter_box.setCurrentIndex(window.filter_box.findData("reviewed"))
        self.assertEqual(window.model.rowCount(), 1)

    def test_cancel_then_rescan_retains_work(self):
        window = GalleryWindow(self.db, cache_root=self.root / "thumbs",
                               private_root=self.root / "private")
        self.addCleanup(window.close)
        window.source_box.setCurrentIndex(1)
        window.start_source_scan()
        QTimer.singleShot(0, window.cancel_source_scan)
        self.assertTrue(self.spin_until(lambda: not window.scan_worker.isRunning()))
        self.assertIn("canceled", window.scan_status.text().lower())
        window.start_source_scan()
        self.assertTrue(self.spin_until(lambda: not window.scan_worker.isRunning()))
        self.assertEqual(window.model.rowCount(), 2)


if __name__ == "__main__":
    unittest.main()
