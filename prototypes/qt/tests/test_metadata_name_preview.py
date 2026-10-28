"""Read-only preview over generated metadata/media; no native desktop launch."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from defiantmaple import metadata, external_actions
from defiantmaple.catalog import connect, initialize, index_file
from prototypes.qt.app import GalleryWindow, MetadataEditor, MetadataNamePreview
from prototypes.qt.tests.gallery_wait import (close_window_and_wait, wait_for_startup_validation,
    wait_for_initial_generation, wait_for_selected_asset, wait_for_rank,
    wait_for_gateway_condition, wait_for_generation_after)


class MockSignal:
    def connect(self, callback):
        pass


class MetadataNamePreviewUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dm-name-preview-generated-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "generated.sqlite3"
        initialize(self.database)
        self.image = self.root / "fictional.png"
        Image.new("RGB", (16, 16), (30, 80, 120)).save(self.image)
        self.sidecar = self.root / "fictional.png.json"
        self.sidecar.write_text('{"fictional":true,"prompt":"keep original"}')
        self.asset_id = index_file(self.database, self.image)
        self.other_image = self.root / "other-fictional.png"
        self.other_image.write_bytes(self.image.read_bytes())
        self.other_id = index_file(self.database, self.other_image)
        tag = metadata.create_tag(self.database, "Fictional landscape")
        metadata.assign_tag(self.database, self.asset_id, tag["tag_id"])
        for kind in metadata.ENTITY_TYPES:
            item = metadata.create_entity(self.database, kind, "Fictional " + kind)
            metadata.assign_entity(self.database, self.asset_id, item["entity_id"])
        self.snapshot = metadata.get_asset_metadata(self.database, self.asset_id)
        self.before = self.files()
        self.catalog_dump = self.dump_catalog()
        self.addCleanup(self.assert_unchanged)

    def files(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode,
                         p.stat().st_uid, p.stat().st_gid) for p in self.root.iterdir()}

    def dump_catalog(self):
        with connect(self.database) as db:
            return tuple(db.iterdump())

    def assert_unchanged(self):
        self.assertEqual(self.dump_catalog(), self.catalog_dump)
        self.assertEqual(self.files(), self.before)

    def preview(self):
        dialog = MetadataNamePreview(self.asset_id, self.snapshot)
        self.addCleanup(dialog.close)
        return dialog

    def wait_export(self, condition, description):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(1)
        self.assertTrue(condition(), description)

    def test_save_selected_captured_names_and_cancel(self):
        # Filesystem serialization/publication is covered by NameExportTests.
        # This test bounds GUI delivery after an explicitly released backend,
        # rather than including a hosted filesystem's unbounded fsync latency.
        from defiantmaple.metadata_name_export import ExportResult
        dialog = self.preview()
        with patch("prototypes.qt.app.QFileDialog.getSaveFileName", return_value=("", "")):
            dialog.save_button.click()
        self.assertIn("Canceled", dialog.export_feedback.text())
        self.assertIsNone(dialog._export_worker)
        dialog.fields["Artist"].click()
        self.snapshot["entities"][0]["name"] = "later edited name"
        destination = "generated-selected-names.json"
        captured = []

        def attempt(result, expected_status):
            entered, release = threading.Event(), threading.Event()
            self.addCleanup(release.set)
            def controlled_backend(path, payload):
                captured.append((path, payload))
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("generated backend was not released")
                return result
            with patch("prototypes.qt.metadata_name_export.save_name_export", side_effect=controlled_backend), patch(
                    "prototypes.qt.app.QFileDialog.getSaveFileName", return_value=(destination, "")):
                dialog.save_button.click()
                self.wait_export(entered.is_set, "controlled backend entered")
                self.assertIsNotNone(dialog._export_worker)
                self.assertFalse(dialog.save_button.isEnabled())
                release.set()
                self.wait_export(lambda: dialog._export_worker is None, "GUI completion after backend release")
            self.assertIn(expected_status, dialog.export_feedback.text())
            self.assertTrue(dialog.save_button.isEnabled())
            self.assertTrue(all(box.isEnabled() for box in dialog.fields.values()))

        attempt(ExportResult(True), "Saved")
        doc = json.loads(captured[0][1])
        self.assertEqual(captured[0][0], destination)
        self.assertEqual(doc["names"], {"Artist": ["Fictional Artist"]})
        self.assertNotIn(self.asset_id.encode(), captured[0][1])
        self.assertNotIn("Location", doc["names"])
        attempt(ExportResult(False, error="File operation failed (FileExistsError, errno 17)"), "Not saved")
        self.assertEqual(captured[1], captured[0])
        attempt(ExportResult(True, cleanup_pending=True), "Saved")
        self.assertIn("temporary export file could not be removed", dialog.export_feedback.text())
        self.assertEqual(captured[2], captured[0])

    def test_worker_is_off_gui_payload_frozen_and_close_held(self):
        dialog = self.preview()
        dialog.show()
        entered, release = threading.Event(), threading.Event()
        seen = {}
        from defiantmaple.metadata_name_export import ExportResult
        def blocked_save(destination, payload):
            seen["thread"] = threading.get_ident()
            seen["payload"] = payload
            entered.set()
            release.wait(5)
            return ExportResult(False, error="generated write error")
        with patch("prototypes.qt.metadata_name_export.save_name_export", side_effect=blocked_save), patch(
                "prototypes.qt.app.QFileDialog.getSaveFileName", return_value=("generated.json", "")):
            dialog.fields["tags"].click()
            dialog.save_button.click()
            self.addCleanup(release.set)
            self.wait_export(entered.is_set, "generated worker entered")
            self.assertNotEqual(seen["thread"], threading.get_ident())
            self.assertFalse(dialog.save_button.isEnabled())
            self.assertTrue(all(not box.isEnabled() for box in dialog.fields.values()))
            dialog.projection["tags"].append("late mutation")
            self.assertNotIn(b"late mutation", seen["payload"])
            dialog.reject()
            dialog.close()
            self.assertTrue(dialog.isVisible())
            # GUI event processing reaches here while the filesystem worker waits.
            release.set()
            self.wait_export(lambda: dialog._export_worker is None, "generated failure returned")
        self.assertIn("Not saved", dialog.export_feedback.text())
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_parent_deletion_does_not_destroy_running_worker(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QWidget
        from defiantmaple.metadata_name_export import ExportResult
        from prototypes.qt.metadata_name_export import _ACTIVE
        parent = QWidget()
        dialog = MetadataNamePreview(self.asset_id, self.snapshot, parent)
        entered, release = threading.Event(), threading.Event()
        def blocked_save(destination, payload):
            entered.set()
            release.wait(5)
            return ExportResult(False, error="generated")
        with patch("prototypes.qt.metadata_name_export.save_name_export", side_effect=blocked_save), patch(
                "prototypes.qt.app.QFileDialog.getSaveFileName", return_value=("generated.json", "")):
            dialog.save_button.click()
            worker = dialog._export_worker
            self.addCleanup(release.set)
            self.wait_export(entered.is_set, "generated parent-deletion worker entered")
            parent.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertIn(worker, _ACTIVE)
            release.set()
            self.wait_export(lambda: worker not in _ACTIVE, "worker released after parent deletion")

    def test_worker_unexpected_exception_reports_unknown_not_not_saved(self):
        dialog = self.preview()
        with patch("prototypes.qt.metadata_name_export.save_name_export", side_effect=RuntimeError("private")), patch(
                "prototypes.qt.app.QFileDialog.getSaveFileName", return_value=("generated.json", "")):
            dialog.save_button.click()
            self.wait_export(lambda: dialog._export_worker is None, "unknown outcome returned")
        self.assertIn("unknown", dialog.export_feedback.text())
        self.assertNotIn("Not saved", dialog.export_feedback.text())
        self.assertNotIn("private", dialog.export_feedback.text())

    def test_defaults_redaction_selected_names_and_remove_again(self):
        dialog = self.preview()
        self.assertIn(self.asset_id, dialog.target.text())
        self.assertTrue(all(not box.isChecked() for box in dialog.fields.values()))
        self.assertEqual(dialog.projection, {})
        self.assertNotIn("Fictional", dialog.values.toPlainText())
        dialog.fields["tags"].click()
        dialog.fields["Artist"].click()
        self.assertEqual(dialog.projection, metadata.preview_metadata_names(self.snapshot, ("tags", "Artist")))
        self.assertIn("Fictional landscape", dialog.values.toPlainText())
        self.assertNotIn("Fictional Client", dialog.values.toPlainText())
        self.assertNotIn("Fictional Location", dialog.values.toPlainText())
        self.assertNotIn(self.asset_id, json.dumps(dialog.projection))
        dialog.fields["Location"].click()
        self.assertIn("Fictional Location", dialog.values.toPlainText())
        dialog.fields["Location"].click()
        self.assertNotIn("Fictional Location", dialog.values.toPlainText())
        dialog.fields["Client"].click()
        self.assertIn("Fictional Client", dialog.values.toPlainText())
        dialog.fields["Client"].click()
        self.assertNotIn("Fictional Client", dialog.values.toPlainText())

    def test_captured_snapshot_is_not_redirected_or_refreshed(self):
        dialog = self.preview()
        self.snapshot["asset_id"] = "different-id"
        self.snapshot["tags"][0]["name"] = "later change"
        dialog.fields["tags"].click()
        self.assertEqual(dialog.asset_id, self.asset_id)
        self.assertEqual(dialog.projection["tags"], ["Fictional landscape"])
        self.assertNotIn("later change", dialog.values.toPlainText())

    def test_existing_editor_entry_captures_target_and_empty_selection_disables(self):
        editor = MetadataEditor(self.database, self.asset_id)
        self.addCleanup(editor.close)
        self.assertTrue(editor.preview_button.isEnabled())
        with patch.object(MetadataNamePreview, "exec") as execute:
            editor.preview_button.click()
        execute.assert_called_once()
        empty = MetadataEditor(self.database)
        self.addCleanup(empty.close)
        self.assertFalse(empty.preview_button.isEnabled())

    def test_gallery_refresh_and_new_selection_do_not_retarget_open_preview(self):
        window = GalleryWindow(self.database, cache_root=self.root / "unused-cache",
                               private_root=self.root / "unused-private",
                               external_settings_path=self.root / "unused-settings.json",
                               external_settings=external_actions.ExternalSettings())
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=2)
        row = wait_for_rank(window, self.asset_id)
        window.gallery.setCurrentIndex(window.model.index(row))
        wait_for_selected_asset(window, self.asset_id, row=row)

        def inspect_editor(editor):
            self.addCleanup(editor.close)
            wait_for_gateway_condition(window, lambda: editor.preview_button.isEnabled(),
                                       description="captured preview metadata readiness")
            def inspect_preview(dialog):
                self.addCleanup(dialog.close)
                generation = window.model._generation
                window.model.refresh()
                wait_for_generation_after(window, generation, expected_count=2)
                other = wait_for_rank(window, self.other_id)
                window.gallery.setCurrentIndex(window.model.index(other))
                wait_for_selected_asset(window, self.other_id, row=other)
                dialog.fields["tags"].click()
                self.assertEqual(dialog.asset_id, self.asset_id)
                self.assertEqual(dialog.projection, {"tags": ["Fictional landscape"]})
                self.assertIn(self.asset_id, dialog.target.text())
                self.assertNotIn(self.other_id, dialog.target.text())
                return 0
            with patch.object(MetadataNamePreview, "exec", inspect_preview):
                editor.preview_button.click()
            return 0
        with patch.object(MetadataEditor, "exec", inspect_editor):
            window.metadata_button.click()

    def test_loading_and_oversize_capture_refuse_preview(self):
        waiting_window = SimpleNamespace(_legacy=Mock(), _closing=False,
            model=SimpleNamespace(_actionable=True, loadFailed=MockSignal(), actionabilityChanged=MockSignal()))
        editor = MetadataEditor(self.database, self.asset_id, catalog_window=waiting_window)
        self.addCleanup(editor.close)
        self.assertFalse(editor.preview_button.isEnabled())
        editor._update_preview_ready(True)  # The model becomes ready while this metadata read is pending.
        self.assertFalse(editor.preview_button.isEnabled())
        with patch.object(MetadataNamePreview, "exec") as execute:
            editor._preview_names()  # Matching placeholder ID is not a successful capture.
        execute.assert_not_called()
        editor._publish_asset_metadata(self.snapshot)
        self.assertTrue(editor.preview_button.isEnabled())
        editor.refresh()
        waiting_window._legacy.call_args.kwargs["on_error"]("generated refresh failure")
        editor._update_preview_ready(True)
        self.assertFalse(editor.preview_button.isEnabled())
        with patch.object(MetadataNamePreview, "exec") as execute:
            editor._preview_names()
        execute.assert_not_called()
        oversized = {"asset_id": self.asset_id, "tags": [{"name": "label"}] * 257, "entities": []}
        editor._publish_asset_metadata(oversized)
        with patch.object(MetadataNamePreview, "exec") as execute:
            editor.preview_button.click()
        execute.assert_not_called()
        self.assertIn("256", editor.feedback.text())

    def test_catalog_invalidation_prevents_new_preview_from_cached_matching_id(self):
        window = GalleryWindow(self.database, cache_root=self.root / "unused-cache",
                               private_root=self.root / "unused-private",
                               external_settings_path=self.root / "unused-settings.json",
                               external_settings=external_actions.ExternalSettings())
        self.addCleanup(close_window_and_wait, window, self.app)
        wait_for_startup_validation(window)
        wait_for_initial_generation(window, expected_count=2)
        editor = MetadataEditor(self.database, self.asset_id, catalog_window=window)
        self.addCleanup(editor.close)
        wait_for_gateway_condition(window, lambda: editor.preview_button.isEnabled(),
                                   description="captured metadata before invalidation")
        window.model._invalidate_changed_view("catalog_replaced", "generated invalidation")
        self.assertFalse(editor.preview_button.isEnabled())
        with patch.object(MetadataNamePreview, "exec") as execute:
            editor._preview_names()  # Programmatic entry cannot bypass disabled readiness.
        execute.assert_not_called()
        self.assertIn("unavailable", editor.feedback.text())
        editor._publish_asset_metadata(self.snapshot)  # A late cached callback cannot restore readiness.
        self.assertFalse(editor.preview_button.isEnabled())

    def test_preview_value_widget_has_no_copy_interaction(self):
        dialog = self.preview()
        dialog.fields["tags"].click()
        self.assertEqual(dialog.values.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        self.assertEqual(dialog.values.contextMenuPolicy(), Qt.ContextMenuPolicy.NoContextMenu)
        # Offscreen platform clipboard only; no desktop clipboard interaction.
        self.assertEqual(self.app.platformName(), "offscreen")
        clipboard = self.app.clipboard()
        clipboard.setText("generated offscreen sentinel")
        QTest.keyClick(dialog.values, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(dialog.values, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(clipboard.text(), "generated offscreen sentinel")


if __name__ == "__main__":
    unittest.main()
