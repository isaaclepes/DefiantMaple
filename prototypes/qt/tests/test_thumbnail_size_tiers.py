"""Named sizes retain existing numeric cache edges."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from benchmarks.generate_catalog import generate
from prototypes.qt.app import GalleryWindow, THUMBNAIL_SIZE_TIERS
from prototypes.qt.tests.thumbnail_fixture import isolate_thumbnail_authority
from prototypes.qt.tests.gallery_wait import close_window_and_wait, wait_for_initial_generation

class ThumbnailSizeTierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_names_edges_default_noop_and_intentional_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'catalog.sqlite3'
            generate(database, 3)
            isolate_thumbnail_authority(self, database, Path(directory))
            window = GalleryWindow(database, enable_thumbnails=False,
                                   private_root=Path(directory) / "private")
            try:
                wait_for_initial_generation(window, expected_count=3)
                self.assertEqual(THUMBNAIL_SIZE_TIERS, (("Tiny",96),("Small",128),
                                 ("Medium",144),("Large",192),("Extra large",224)))
                self.assertEqual(window.size_box.accessibleName(), 'Thumbnail size')
                self.assertEqual(window.size_box.currentText(), 'Medium')
                self.assertEqual(window.delegate.cell_size, 144)
                preparation = Mock(paused=True)
                window.preparation = preparation
                with patch.object(window, '_invalidate_thumbnails') as invalidate:
                    for index, (label, edge) in enumerate(THUMBNAIL_SIZE_TIERS):
                        invalidate.reset_mock()
                        window.size_box.setCurrentIndex(index)
                        self.assertEqual(window.size_box.currentText(), label)
                        self.assertEqual(window.delegate.cell_size, edge)
                        self.assertEqual(window.gallery.gridSize().width(), edge + 8)
                        self.assertEqual(window.gallery.gridSize().height(), edge + 50)
                        invalidate.assert_called_once_with()
                        window._resize_cells(edge)
                        window.size_box.setCurrentIndex(index)
                        invalidate.assert_called_once_with()
                    preparation.resume.assert_not_called()
                    # A running pass is resumed once after actual size change;
                    # selecting that same size again must not restart it.
                    preparation.paused = False
                    invalidate.reset_mock()
                    window.size_box.setCurrentIndex(2)
                    invalidate.assert_called_once_with()
                    preparation.resume.assert_called_once_with()
                    window._resize_cells(144)
                    preparation.resume.assert_called_once_with()
                    invalidate.assert_called_once_with()
            finally:
                window.preparation = None
                close_window_and_wait(window, self.app)
