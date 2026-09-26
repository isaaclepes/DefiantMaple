import os
from configparser import ConfigParser
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from benchmarks.generate_catalog import generate
from prototypes.qt.app import AssetModel, GalleryWindow, REVIEW_STATES, _rss_bytes
from prototypes.qt.package import add_nuitka_download_consent, bundle_launchable, find_artifact


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
        (executable.parent / "QtQmlModels").write_bytes(b"helper")
        (root / "DefiantMapleQt.bin").write_bytes(b"standalone")
        bundle = find_artifact(root)
        self.assertEqual(bundle, root / "DefiantMapleQt.app")
        self.assertEqual(bundle_launchable(bundle), executable)

    def test_current_process_memory_is_measurable(self):
        self.assertGreater(_rss_bytes() or 0, 0)

    def test_windows_packaging_allows_unattended_tool_download(self):
        spec = Path(self.temp.name) / "pysidedeploy.spec"
        spec.write_text("[nuitka]\nextra_args = --quiet\n", encoding="utf-8")
        add_nuitka_download_consent(spec)
        config = ConfigParser()
        config.read(spec, encoding="utf-8")
        self.assertIn("--assume-yes-for-downloads", config.get("nuitka", "extra_args"))


if __name__ == "__main__":
    unittest.main()
