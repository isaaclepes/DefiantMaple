"""Generated participating-window ownership, refusal and startup cleanup."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from defiantmaple.admission import LibraryInUseError, admission_session
from defiantmaple.catalog import initialize
from prototypes.qt.admission_smoke import frozen_admission_smoke
from prototypes.qt.app import GalleryWindow
from prototypes.qt.tests.gallery_wait import close_window_and_wait, wait_for_initial_generation


class LibraryAdmissionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "generated.sqlite3"
        initialize(self.catalog)
        self.registry = self.root / "registry"

    def window(self):
        return GalleryWindow(self.catalog, cache_root=self.root / "cache", private_root=self.root / "private")

    def test_same_process_second_window_refuses_without_breaking_nested_core(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            window = self.window()
            window.show()
            try:
                wait_for_initial_generation(window, expected_count=0)
                with admission_session(self.catalog, _registry_path=self.registry) as nested:
                    self.assertIs(owner, nested)
                    with self.assertRaises(LibraryInUseError):
                        self.window()
                self.assertTrue(owner.coordinator_claimed)
            finally:
                close_window_and_wait(window, self.app)
            self.assertFalse(owner.coordinator_claimed)
        self.assertTrue(owner.closed)

    def test_invalid_preflight_does_not_leak_gui_claim(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            with patch("prototypes.qt.app.assert_outside_git", side_effect=ValueError("generated invalid location")):
                with self.assertRaisesRegex(ValueError, "invalid location"):
                    GalleryWindow(self.catalog, enable_thumbnails=True, cache_root=self.root / "cache")
            self.assertFalse(owner.coordinator_claimed)
        self.assertTrue(owner.closed)

    def test_gateway_start_failure_releases_unstarted_gui_claim(self):
        with admission_session(self.catalog, _registry_path=self.registry) as owner:
            with patch("prototypes.qt.app.GalleryCatalogClient.start", side_effect=RuntimeError("generated start failure")):
                with self.assertRaisesRegex(RuntimeError, "start failure"):
                    self.window()
            self.assertFalse(owner.coordinator_claimed)
        self.assertTrue(owner.closed)

    def test_source_executable_exclusion_release_and_catalog_preservation_smoke(self):
        result = frozen_admission_smoke((sys.executable, "-m", "prototypes.qt.app"), dict(os.environ))
        self.assertTrue(result["second_client_refused"])
        self.assertTrue(result["released_and_reopened"])
        self.assertTrue(result["catalog_unchanged"])


if __name__ == "__main__":
    unittest.main()
