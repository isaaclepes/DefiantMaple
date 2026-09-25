import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from benchmarks.generate_catalog import generate
from prototypes.qt.app import AssetModel, GalleryWindow, REVIEW_STATES
from prototypes.qt.package import find_artifact


class QtPrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "catalog.sqlite3"
        generate(self.database, 1_001, batch_size=113)

    def test_model_pages_filters_and_updates(self):
        model = AssetModel(self.database)
        self.addCleanup(model.close)
        self.assertEqual(model.rowCount(), 1_001)
        self.assertEqual(model.data(model.index(0), model.AssetRole)["asset_id"],
                         "00000000-0000-0000-0000-000000000000")
        self.assertLessEqual(len(model._cache), model.max_cached_pages)
        model.set_filter("new")
        filtered_count = model.rowCount()
        self.assertGreater(filtered_count, 0)
        model.update_state(0, "reviewed")
        self.assertEqual(model.rowCount(), filtered_count - 1)
        with self.assertRaises(ValueError):
            model.set_filter("not-a-state")

    def test_window_controls_selection_and_review_state(self):
        window = GalleryWindow(self.database)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window.gallery.setCurrentIndex(window.model.index(5))
        self.app.processEvents()
        self.assertIn("asset_id", window.detail.toPlainText())
        window.size_slider.setValue(176)
        self.assertEqual(window.delegate.cell_size, 176)
        window.set_selected_state(REVIEW_STATES[2])
        self.assertEqual(window.model.asset_at(5)["workflow_state"], "reviewed")
        self.assertIn('"workflow_state": "reviewed"', window.detail.toPlainText())
        QApplication.sendEvent(window.gallery, QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Home,
            Qt.KeyboardModifier.NoModifier,
        ))
        self.app.processEvents()
        self.assertEqual(window.gallery.currentIndex().row(), 0)

    def test_packaging_prefers_macos_bundle_over_internal_executable(self):
        root = Path(self.temp.name) / "build"
        executable = root / "DefiantMapleQt.app" / "Contents" / "MacOS" / "DefiantMapleQt"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"executable")
        (root / "DefiantMapleQt.bin").write_bytes(b"standalone")
        self.assertEqual(find_artifact(root), root / "DefiantMapleQt.app")


if __name__ == "__main__":
    unittest.main()
