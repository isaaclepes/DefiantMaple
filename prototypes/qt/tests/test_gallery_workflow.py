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
from prototypes.qt.tests.gallery_wait import (
    close_window_and_wait, wait_for_generation_after, wait_for_initial_generation,
    wait_for_gateway_condition, wait_for_review_write, wait_for_selected_asset,
    wait_for_startup_validation,
)


class GalleryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(strict=True)
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
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        with patch("prototypes.qt.app.QFileDialog.getExistingDirectory",
                   return_value=str(self.art)), patch(
                       "prototypes.qt.app.QInputDialog.getItem",
                       return_value=("Ignore Until Modified", True)):
            window._add_source_dialog()
        wait_for_gateway_condition(
            window,
            lambda: (window.scan_status.text().startswith('Source added.')
                     and bool(list_sources(created))
                     and window.source_box.currentData() == list_sources(created)[0]['source_id']),
            description='source addition and policy publication',
        )
        self.assertEqual(list_sources(created)[0]["existing_file_policy"],
                         "ignore_until_modified")
        self.assertEqual(window.source_box.currentData(), list_sources(created)[0]["source_id"])

    def test_late_source_add_reply_preserves_changed_and_returned_user_choice(self):
        window = GalleryWindow(self.db, enable_thumbnails=False,
                               cache_root=self.root / "thumbs",
                               private_root=self.root / "private")
        self.addCleanup(close_window_and_wait, window, self.app)
        window.show()
        wait_for_startup_validation(window)
        wait_for_gateway_condition(
            window, lambda: window.source_box.findData(self.source["source_id"]) >= 0,
            description="source choice before delayed add reply")
        window.source_box.setCurrentIndex(window.source_box.findData(self.source["source_id"]))
        captured_id = window.source_box.currentData()
        captured_epoch = window._source_choice_epoch
        other_root = self.root / "other-art"
        other_root.mkdir()
        new_source = add_source(self.db, other_root)
        window.source_box.setCurrentIndex(0)
        window.source_box.setCurrentIndex(window.source_box.findData(captured_id))
        self.assertEqual(window.source_box.currentData(), captured_id)
        self.assertNotEqual(window._source_choice_epoch, captured_epoch)

        window._source_added(list_sources(self.db), new_source["source_id"],
                             captured_id, captured_epoch)
        self.assertEqual(window.source_box.currentData(), captured_id)
        self.assertGreaterEqual(window.source_box.findData(new_source["source_id"]), 0)

    def test_scan_stays_responsive_then_shows_thumbnails_details_and_duplicates(self):
        (self.art / "unsupported.txt").write_text("fictional unsupported file")
        window = GalleryWindow(self.db, enable_thumbnails=True,
                               cache_root=self.root / "thumbs",
                               private_root=self.root / "private")
        self.addCleanup(close_window_and_wait, window, self.app)
        window.show()
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=0)
        wait_for_gateway_condition(
            window, lambda: window.source_box.findData(self.source['source_id']) >= 0,
            description='source list before scan',
        )
        window.source_box.setCurrentIndex(1)
        previous_generation = window.model._generation
        window.start_source_scan()
        first_scan_worker = window.scan_worker
        self.assertIsNotNone(first_scan_worker)
        while_running = []
        QTimer.singleShot(100, lambda: while_running.append(first_scan_worker.isRunning()))
        self.assertTrue(self.spin_until(lambda: first_scan_worker.isFinished()))
        self.assertEqual(while_running, [True])
        wait_for_generation_after(window, previous_generation, expected_count=2,
                                  description='scan result gallery generation')
        wait_for_gateway_condition(window, lambda: window.issues_list.count() == 1,
                                   description='scan issue publication')
        self.assertEqual(window.issues_list.count(), 1)
        self.assertIn("unsupported", window.issues_list.item(0).text())
        asset = window.model.loaded_asset_at(0)
        self.assertEqual(asset["source_id"], self.source["source_id"])
        window.gallery.setCurrentIndex(window.model.index(0))
        wait_for_selected_asset(window, asset['asset_id'], row=0)
        self.assertIn("provenance", window.detail.toPlainText())
        self.assertIn("fictional-art", window.detail.toPlainText())
        window.size_slider.setValue(192)
        self.assertEqual(window.delegate.cell_size, 192)
        window.thumbnails.lookup(asset, 192)
        self.assertTrue(self.spin_until(lambda: window.thumbnails.lookup(asset, 192)[0] is not None))
        self.assertTrue(thumbnail_for(self.db, asset["asset_id"], self.root / "thumbs",
                                      max_edge=192)["cache_hit"])
        window.refresh_duplicates()
        wait_for_gateway_condition(window, lambda: window.duplicates_list.count() == 1,
                                   description='duplicate list publication')
        self.assertEqual(window.duplicates_list.count(), 1)
        window._duplicate_selected(window.duplicates_list.item(0))
        previous_generation = window.model._generation
        window.apply_filters_button.click()
        wait_for_generation_after(window, previous_generation, expected_count=2,
                                  description='duplicate digest filter application')
        window.gallery.setCurrentIndex(window.model.index(0))
        wait_for_selected_asset(window, asset['asset_id'], row=0)
        previous_generation = window.model._generation
        window.set_selected_state("reviewed")
        wait_for_review_write(window, row=0, asset_id=asset['asset_id'],
                              previous_generation=previous_generation, state='reviewed')
        window.filter_box.setCurrentIndex(window.filter_box.findData("reviewed"))
        previous_generation = window.model._generation
        window.apply_filters_button.click()
        wait_for_generation_after(window, previous_generation, expected_count=1,
                                  description='reviewed filter application')
        self.assertEqual(window.model.rowCount(), 1)

    def test_cancel_then_rescan_retains_work(self):
        window = GalleryWindow(self.db, cache_root=self.root / "thumbs",
                               private_root=self.root / "private")
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=0)
        wait_for_gateway_condition(
            window, lambda: window.source_box.findData(self.source['source_id']) >= 0,
            description='source list before cancellable scan',
        )
        window.source_box.setCurrentIndex(1)
        window.start_source_scan()
        canceled_scan_worker = window.scan_worker
        self.assertIsNotNone(canceled_scan_worker)
        QTimer.singleShot(0, window.cancel_source_scan)
        self.assertTrue(self.spin_until(lambda: canceled_scan_worker.isFinished()))
        wait_for_gateway_condition(
            window, lambda: 'canceled' in window.scan_status.text().lower(),
            description='canceled scan completion publication',
        )
        self.assertIn("canceled", window.scan_status.text().lower())
        previous_generation = window.model._generation
        window.start_source_scan()
        completed_scan_worker = window.scan_worker
        self.assertIsNotNone(completed_scan_worker)
        self.assertTrue(self.spin_until(lambda: completed_scan_worker.isFinished()))
        wait_for_generation_after(window, previous_generation, expected_count=2,
                                  description='completed rescan gallery generation')


if __name__ == "__main__":
    unittest.main()
