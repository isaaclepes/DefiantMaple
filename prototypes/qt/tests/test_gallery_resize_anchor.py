"""Gallery reflow keeps a visible item in view without touching asset data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListView

from benchmarks.generate_catalog import generate
from prototypes.qt.app import AssetDelegate, GalleryView, GalleryWindow
from prototypes.qt.tests.thumbnail_fixture import isolate_thumbnail_authority
from prototypes.qt.tests.gallery_wait import close_window_and_wait, wait_for_initial_generation


class GalleryResizeAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = GalleryView()
        self.model = QStandardItemModel()
        self.model.appendColumn([QStandardItem(str(i)) for i in range(3650)])
        self.view.setModel(self.model)
        self.model.modelReset.connect(self.view._cancel_resize_anchor)
        self.view.setItemDelegate(AssetDelegate())
        self.view.setGridSize(QSize(152, 194))
        self.view.resize(1200, 600)
        self.view.show()
        self.wait(lambda: not self.view._resize_anchor_timer.isActive())
        self.wait(lambda: not self.view.visualRect(self.model.index(3649, 0)).isEmpty()
                  and self.view.verticalScrollBar().maximum() > 100000)

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def wait(self, predicate, details=None):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'gallery layout did not settle' +
                        (f': {details()}' if details is not None else ''))

    def layout_details(self, row):
        bar = self.view.verticalScrollBar()
        return (f'row={row}, rect={self.view.visualRect(self.model.index(row, 0))}, '
                f'viewport={self.view.viewport().rect()}, bar={bar.value()}/{bar.maximum()}, '
                f'anchor={self.view._resize_anchor}')

    def scroll_to(self, row):
        self.view.scrollTo(self.model.index(row, 0), QListView.ScrollHint.PositionAtTop)
        self.wait(lambda: self.view.visualRect(self.model.index(row, 0)).intersects(
            self.view.viewport().rect()), lambda: self.layout_details(row))
        return self.view._visible_anchor()[0].row()

    def assert_visible(self, row):
        self.assertTrue(self.view.visualRect(self.model.index(row, 0)).intersects(
            self.view.viewport().rect()), f'row {row} outside, rect={self.view.visualRect(self.model.index(row, 0))}, bar={self.view.verticalScrollBar().value()}, anchor={self.view._resize_anchor}')

    def test_width_changes_keep_top_asset_across_batched_reflow(self):
        self.view.setCurrentIndex(self.model.index(50, 0))
        row = self.scroll_to(2500)
        self.assertGreater(row, 2400)
        self.view.resize(850, 600)
        QTest.qWait(50)
        self.wait(lambda: self.view._resize_anchor is None)
        self.assert_visible(row)
        row = self.view._visible_anchor()[0].row()
        self.view.resize(1200, 600)
        QTest.qWait(50)
        self.wait(lambda: self.view._resize_anchor is None)
        self.assert_visible(row)

    def test_rapid_changes_and_bottom_do_not_jump_to_start(self):
        row = self.scroll_to(3649)
        self.view.resize(950, 600)
        self.view.resize(750, 600)
        self.view.resize(1050, 600)
        QTest.qWait(50)
        self.wait(lambda: self.view._resize_anchor is None)
        self.assert_visible(row)
        self.assertGreater(self.view._visible_anchor()[0].row(), 3500)

    def test_reflow_restoration_preserves_scroll_direction(self):
        row = self.scroll_to(2500)
        bar = self.view.verticalScrollBar()
        window = SimpleNamespace(
            gallery=self.view, thumbnails=Mock(),
            _adjacent_direction=-1,
            _adjacent_scroll=(self.view.horizontalScrollBar().value(), bar.value()),
            _reset_adjacent_plan=Mock(), _schedule_adjacent=Mock())
        bar.valueChanged.connect(lambda _value: GalleryWindow._reprioritize_thumbnails(window))
        self.view.resize(850, 600)
        QTest.qWait(50)
        self.wait(lambda: self.view._resize_anchor is None)
        self.assert_visible(row)
        self.assertEqual(window._adjacent_direction, -1)
        self.assertEqual(window._adjacent_scroll[1], bar.value())
        window.thumbnails.invalidate_pending.assert_called_with(cancel_active=False)
        # The next explicit navigation must update direction normally.
        self.view.scrollTo(self.model.index(2800, 0), QListView.ScrollHint.PositionAtTop)
        self.assertEqual(window._adjacent_direction, 1)

    def test_user_navigation_and_model_reset_cancel_pending_restore(self):
        self.scroll_to(2500)
        self.view.resize(850, 600)
        self.assertIsNotNone(self.view._resize_anchor)
        QTest.keyClick(self.view, Qt.Key.Key_Home)
        self.assertIsNone(self.view._resize_anchor)
        QTest.qWait(200)
        self.assertIsNone(self.view._resize_anchor)
        # The canceled restoration must stay canceled while batched reflow
        # finishes. A one-shot setup scroll before its new range exists can be
        # clamped; waiting for target visibility after that cannot fix it.
        bar = self.view.verticalScrollBar()
        last = self.model.index(self.model.rowCount() - 1, 0)
        self.wait(lambda: not self.view.visualRect(last).isEmpty()
                  and bar.maximum() > 0
                  and bar.maximum() + self.view.viewport().height()
                  >= bar.value() + self.view.visualRect(last).bottom(),
                  lambda: self.layout_details(last.row()))
        self.scroll_to(2500)
        self.view.resize(1000, 600)
        self.assertIsNotNone(self.view._resize_anchor)
        self.model.clear()
        self.assertIsNone(self.view._resize_anchor)
        QTest.qWait(50)
        self.assertFalse(self.view._resize_anchor_timer.isActive())


    def test_generated_catalog_splitter_resize_does_not_restart_query(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        database = root / 'catalog.sqlite3'
        generate(database, 1200)
        isolate_thumbnail_authority(self, database, root)
        window = GalleryWindow(database, enable_thumbnails=False, private_root=root / 'private')
        try:
            window.resize(1500, 900)
            window.show()
            wait_for_initial_generation(window, expected_count=1200)
            gallery = window.gallery
            self.wait(lambda: gallery.verticalScrollBar().maximum() > 10000)
            gallery.scrollTo(window.model.index(800, 0), QListView.ScrollHint.PositionAtTop)
            self.wait(lambda: gallery.visualRect(window.model.index(800, 0)).intersects(gallery.viewport().rect()))
            anchor = gallery._visible_anchor()[0].row()
            generation = window.model._generation
            token = window.model._token
            splitter = gallery.parentWidget()
            with patch.object(window.catalog_client, 'submit', wraps=window.catalog_client.submit) as submit:
                splitter.setSizes([650, 750])
                QTest.qWait(50)
                self.wait(lambda: gallery._resize_anchor is None)
                self.assertTrue(gallery.visualRect(window.model.index(anchor, 0)).intersects(gallery.viewport().rect()))
                self.assertEqual(window.model._generation, generation)
                self.assertEqual(window.model._token, token)
                self.assertTrue(all(call.args[1] not in ('first',) for call in submit.call_args_list))
        finally:
            close_window_and_wait(window, self.app)

if __name__ == '__main__':
    unittest.main()
