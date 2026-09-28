"""Explicit metadata UI and migration-opening tests with fictional local media."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from defiantmaple.catalog import CatalogMigrationError, SCHEMA_V2, initialize, index_file
from defiantmaple import metadata
from prototypes.qt.app import GalleryWindow, LibraryLauncher, MetadataEditor, main


class MetadataUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="defiantmaple-metadata-ui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / "library.sqlite3"
        initialize(self.database)
        self.art = self.root / "fictional-art"
        self.art.mkdir()
        Image.new("RGB", (16, 16), (20, 80, 140)).save(self.art / "one.png")
        (self.art / "two.png").write_bytes((self.art / "one.png").read_bytes())
        (self.art / "one.png.json").write_text('{"fictional":true}', encoding="utf-8")
        self.asset_ids = [index_file(self.database, self.art / name)
                          for name in ("one.png", "two.png")]
        self.original = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                         for path in self.art.iterdir()}
        self.addCleanup(self.assert_sources_unchanged)

    def assert_sources_unchanged(self):
        self.assertEqual(set(self.art.iterdir()), set(self.original))
        for path, original in self.original.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original)

    def editor(self, asset_id=None):
        dialog = MetadataEditor(self.database, asset_id, "fictional one.png" if asset_id else None)
        self.addCleanup(dialog.close)
        return dialog

    def create(self, panel, name):
        panel.name.setText(name)
        panel.create_button.click()
        self.assertEqual(panel.editor.feedback.text(), "Catalog metadata saved.")
        record = panel.selected_record()
        self.assertIsNotNone(record)
        return record

    def test_tag_canonical_alias_parents_assignment_and_reopen(self):
        editor = self.editor(self.asset_ids[0])
        panel = editor.tags
        parent_one = self.create(panel, "Landscape")
        parent_two = self.create(panel, "Palette")
        tag = self.create(panel, "  Moonlit   scene  ")
        self.assertEqual(tag["name"], "Moonlit scene")
        tag_id = tag["tag_id"]
        panel.name.setText("Moonlit landscape")
        panel.rename_button.click()
        self.assertEqual(panel.selected_record()["tag_id"], tag_id)
        self.assertEqual(panel.selected_record()["name"], "Moonlit landscape")
        panel.alias.setText("Night scene")
        panel.add_alias_button.click()
        self.assertEqual(panel.aliases.item(0).text(), "Night scene")
        panel.aliases.setCurrentRow(0)
        panel.remove_alias_button.click()
        self.assertEqual(panel.aliases.count(), 0)
        panel.alias.setText("Nocturnal")
        panel.add_alias_button.click()
        for parent_id in (parent_one["tag_id"], parent_two["tag_id"], None):
            panel.parent_box.setCurrentIndex(panel.parent_box.findData(parent_id))
            panel.parent_button.click()
            self.assertEqual(metadata.get_tag(self.database, tag_id)["parent_id"], parent_id)
        panel.parent_box.setCurrentIndex(panel.parent_box.findData(parent_one["tag_id"]))
        panel.parent_button.click()
        panel.assign_button.click()
        self.assertEqual([record["tag_id"] for record in editor.asset_metadata["tags"]], [tag_id])
        panel.unassign_button.click()
        self.assertEqual(editor.asset_metadata["tags"], [])
        panel.assign_button.click()
        editor.close()
        reopened = self.editor(self.asset_ids[0])
        reopened.tags.select_id(tag_id)
        self.assertEqual(reopened.tags.name.text(), "Moonlit landscape")
        self.assertEqual(reopened.tags.aliases.item(0).text(), "Nocturnal")
        self.assertEqual(reopened.tags.parent_box.currentData(), parent_one["tag_id"])
        self.assertEqual(reopened.asset_metadata["tags"][0]["tag_id"], tag_id)
        self.assertNotIn(parent_one["tag_id"], [record["tag_id"] for record in reopened.asset_metadata["tags"]])
        window = GalleryWindow(self.database)
        self.addCleanup(window.close)
        row = next(row for row in range(window.model.rowCount())
                   if window.model.asset_at(row)["asset_id"] == self.asset_ids[0])
        window.gallery.setCurrentIndex(window.model.index(row))
        details = json.loads(window.detail.toPlainText())
        self.assertEqual(details["metadata"]["tags"][0]["name"], "Moonlit landscape")
        self.assertEqual(window.model.rowCount(), 2)

    def test_all_entity_types_create_rename_alias_assign_unassign_and_reopen(self):
        editor = self.editor(self.asset_ids[0])
        panel = editor.entities
        identifiers = []
        self.assertEqual(tuple(panel.entity_type.itemText(row) for row in
                               range(panel.entity_type.count())), metadata.ENTITY_TYPES)
        for entity_type in metadata.ENTITY_TYPES:
            with self.subTest(entity_type=entity_type):
                panel.entity_type.setCurrentText(entity_type)
                record = self.create(panel, f"Fictional {entity_type}")
                identifier = record["entity_id"]
                identifiers.append(identifier)
                panel.name.setText(f"Renamed {entity_type}")
                panel.rename_button.click()
                self.assertEqual(panel.selected_record()["entity_id"], identifier)
                panel.alias.setText(f"Alias {entity_type}")
                panel.add_alias_button.click()
                panel.aliases.setCurrentRow(0)
                panel.remove_alias_button.click()
                self.assertEqual(panel.aliases.count(), 0)
                panel.alias.setText(f"Saved alias {entity_type}")
                panel.add_alias_button.click()
                panel.assign_button.click()
                self.assertIn(identifier, [item["entity_id"] for item in editor.asset_metadata["entities"]])
                panel.unassign_button.click()
                self.assertNotIn(identifier, [item["entity_id"] for item in editor.asset_metadata["entities"]])
                panel.assign_button.click()
        editor.close()
        reopened = self.editor(self.asset_ids[0])
        self.assertEqual({item["entity_id"] for item in reopened.asset_metadata["entities"]}, set(identifiers))
        for entity_type in metadata.ENTITY_TYPES:
            reopened.entities.entity_type.setCurrentText(entity_type)
            self.assertEqual(reopened.entities.name.text(), f"Renamed {entity_type}")
            self.assertEqual(reopened.entities.aliases.item(0).text(), f"Saved alias {entity_type}")
        self.assertEqual(metadata.get_asset_metadata(self.database, self.asset_ids[1])["entities"], [])
        launcher = LibraryLauncher()
        self.addCleanup(launcher.close)
        with patch("prototypes.qt.app.QFileDialog.getOpenFileName", return_value=(str(self.database), "")), \
                patch("prototypes.qt.app.QMessageBox.information") as information:
            launcher.open_library()
        information.assert_not_called()  # Current v3 opening creates no new backup.
        window = launcher.gallery_window
        self.assertIsNotNone(window)
        self.addCleanup(window.close)
        row = next(row for row in range(window.model.rowCount())
                   if window.model.asset_at(row)["asset_id"] == self.asset_ids[0])
        window.gallery.setCurrentIndex(window.model.index(row))
        persisted = json.loads(window.detail.toPlainText())["metadata"]["entities"]
        self.assertEqual({record["entity_id"] for record in persisted}, set(identifiers))

    def test_empty_library_can_manage_taxonomy_without_assignment(self):
        empty = self.root / "empty.sqlite3"
        initialize(empty)
        window = GalleryWindow(empty)
        self.addCleanup(window.close)
        self.assertTrue(window.metadata_button.isEnabled())
        opened = []

        def inspect(dialog):
            opened.append(dialog)
            self.assertIsNone(dialog.asset_id)
            self.create(dialog.tags, "Before indexing")
            self.create(dialog.entities, "Fictional Character")
            self.assertFalse(dialog.tags.assign_button.isEnabled())
            self.assertFalse(dialog.tags.unassign_button.isEnabled())
            self.assertFalse(dialog.entities.assign_button.isEnabled())
            self.assertFalse(dialog.entities.unassign_button.isEnabled())
            self.assertTrue(dialog.tags.rename_button.isEnabled())
            dialog.tags.set_assignment(True)  # Programmatic calls cannot bypass guard.
            return 0

        with patch.object(MetadataEditor, "exec", inspect):
            window.metadata_button.click()
        self.assertEqual(len(opened), 1)
        self.assertEqual(len(metadata.list_tags(empty)), 1)
        self.assertEqual(len(metadata.list_entities(empty)), 1)
        self.assertEqual(window.model.rowCount(), 0)

    def test_selection_change_and_model_reset_cannot_retarget_editor(self):
        window = GalleryWindow(self.database)
        self.addCleanup(window.close)
        window.gallery.setCurrentIndex(window.model.index(0))
        captured_id = window.model.asset_at(0)["asset_id"]
        other_id = window.model.asset_at(1)["asset_id"]
        targets = []

        def edit_after_selection_change(dialog):
            targets.append(dialog.asset_id)
            target_text = dialog.target.text()
            window.model.refresh()
            window.gallery.setCurrentIndex(window.model.index(1))
            tag = self.create(dialog.tags, "Fixed selection")
            dialog.tags.assign_button.click()
            entity = self.create(dialog.entities, "Fixed character")
            dialog.entities.assign_button.click()
            self.assertEqual(dialog.target.text(), target_text)
            self.assertIn(captured_id, target_text)
            self.assertEqual(dialog.asset_id, captured_id)
            assigned = metadata.get_asset_metadata(self.database, captured_id)
            self.assertEqual(assigned["tags"][0]["tag_id"], tag["tag_id"])
            self.assertEqual(assigned["entities"][0]["entity_id"], entity["entity_id"])
            return 0

        with patch.object(MetadataEditor, "exec", edit_after_selection_change):
            window._edit_metadata()
        self.assertEqual(targets, [captured_id])
        self.assertEqual(metadata.get_asset_metadata(self.database, other_id)["tags"], [])
        self.assertEqual(metadata.get_asset_metadata(self.database, other_id)["entities"], [])
        self.assertEqual(window.model.rowCount(), 2)
        self.assertEqual(json.loads(window.detail.toPlainText())["asset"]["asset_id"], other_id)

    def test_backend_rejections_are_visible_and_do_not_mutate_assignments(self):
        editor = self.editor(self.asset_ids[0])
        parent = self.create(editor.tags, "Parent")
        child = self.create(editor.tags, "Child")
        editor.tags.parent_box.setCurrentIndex(editor.tags.parent_box.findData(parent["tag_id"]))
        editor.tags.parent_button.click()
        editor.tags.select_id(parent["tag_id"])
        editor.tags.parent_box.setCurrentIndex(editor.tags.parent_box.findData(child["tag_id"]))
        editor.tags.parent_button.click()
        self.assertNotEqual(editor.feedback.text(), "Catalog metadata saved.")
        self.assertIsNone(metadata.get_tag(self.database, parent["tag_id"])["parent_id"])
        editor.tags.name.setText("Child")
        editor.tags.rename_button.click()
        self.assertNotEqual(editor.feedback.text(), "Catalog metadata saved.")
        self.assertEqual(metadata.get_asset_metadata(self.database, self.asset_ids[0])["tags"], [])

    def legacy_catalog(self, version):
        path = self.root / f"legacy-v{version}.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            if version == 2:
                db.executescript(SCHEMA_V2)
            else:
                db.executescript("""
                    CREATE TABLE assets (
                        asset_id TEXT PRIMARY KEY,current_path TEXT NOT NULL UNIQUE,
                        media_type TEXT NOT NULL,sha256 TEXT NOT NULL,byte_size INTEGER NOT NULL,
                        workflow_state TEXT NOT NULL,discovered_at TEXT NOT NULL
                    );
                    CREATE TABLE provenance (
                        provenance_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,
                        source_kind TEXT NOT NULL,details_json TEXT NOT NULL,recorded_at TEXT NOT NULL
                    );
                    PRAGMA user_version=1;
                """)
            with closing(sqlite3.connect(self.database)) as current:
                row = current.execute(
                    "SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at "
                    "FROM assets WHERE asset_id=?", (self.asset_ids[0],)).fetchone()
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at) "
                       "VALUES(?,?,?,?,?,?,?)", row)
            db.execute("INSERT INTO provenance VALUES(?,?,?,?,?)", (
                "fictional-provenance", self.asset_ids[0], "fictional", '{"original":true}', "2026-01-01"))
            db.commit()
        return path, row

    def test_launcher_migrates_v1_v2_before_gallery_and_displays_verified_backup(self):
        for version in (1, 2):
            with self.subTest(version=version):
                path, original = self.legacy_catalog(version)
                launcher = LibraryLauncher()
                self.addCleanup(launcher.close)
                real_show = launcher._show_gallery
                constructed = []

                def verified_before_construction(opened):
                    with closing(sqlite3.connect(opened)) as db:
                        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
                    constructed.append(opened)
                    real_show(opened)

                with patch("prototypes.qt.app.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                        patch.object(launcher, "_show_gallery", side_effect=verified_before_construction), \
                        patch("prototypes.qt.app.QMessageBox.information") as information:
                    launcher.open_library()
                self.assertEqual(constructed, [path])
                window = launcher.gallery_window
                self.assertIsNotNone(window)
                self.addCleanup(window.close)
                self.assertEqual(window.model.asset_at(0)["asset_id"], self.asset_ids[0])
                self.assertEqual(window.model.asset_at(0)["sha256"], original[3])
                text = information.call_args.args[2]
                backup = Path(text.split("Verified backup: ", 1)[1])
                self.assertTrue(backup.is_file())
                with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as db:
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
                    self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    restored = db.execute(
                        "SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at "
                        "FROM assets").fetchone()
                    self.assertEqual(restored, original)
                window.close()

    def test_launcher_refuses_missing_unknown_future_without_construction_or_changes(self):
        missing = self.root / "missing.sqlite3"
        unknown = self.root / "unknown.sqlite3"
        future = self.root / "future.sqlite3"
        unversioned = self.root / "unversioned.sqlite3"
        with closing(sqlite3.connect(unversioned)) as db:
            db.execute("CREATE TABLE user_records (value TEXT)")
            db.execute("INSERT INTO user_records VALUES ('fictional unknown database')")
            db.commit()
        unknown.write_bytes(b"fictional unknown file")
        with closing(sqlite3.connect(future)) as db:
            db.execute("PRAGMA user_version=99")
            db.commit()
        for path in (missing, unknown, unversioned, future):
            with self.subTest(path=path.name):
                before = path.read_bytes() if path.exists() else None
                launcher = LibraryLauncher()
                self.addCleanup(launcher.close)
                with patch("prototypes.qt.app.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                        patch("prototypes.qt.app.QMessageBox.warning") as warning, \
                        patch.object(launcher, "_show_gallery") as constructed:
                    launcher.open_library()
                constructed.assert_not_called()
                warning.assert_called_once()
                self.assertIsNone(launcher.gallery_window)
                self.assertEqual(path.read_bytes() if path.exists() else None, before)

    def test_launcher_abort_on_close_refusal_before_open_or_create_initialization(self):
        for action in ("open", "create"):
            with self.subTest(action=action):
                launcher = LibraryLauncher()
                self.addCleanup(launcher.close)
                previous = Mock()
                previous.close.return_value = False
                launcher.gallery_window = previous
                selected = self.database if action == "open" else self.root / "should-not-create.sqlite3"
                dialog = "getOpenFileName" if action == "open" else "getSaveFileName"
                with patch(f"prototypes.qt.app.QFileDialog.{dialog}", return_value=(str(selected), "")), \
                        patch("prototypes.qt.app.initialize") as migration, \
                        patch("prototypes.qt.app.GalleryWindow") as construction, \
                        patch("prototypes.qt.app.QMessageBox.warning") as warning:
                    (launcher.open_library if action == "open" else launcher.create_library)()
                migration.assert_not_called()
                construction.assert_not_called()
                warning.assert_called_once()
                self.assertIs(launcher.gallery_window, previous)
                previous.close.assert_called_once()
                if action == "create":
                    self.assertFalse(selected.exists())

    def test_queued_scan_callbacks_after_close_do_not_access_closed_model(self):
        class FinishingWorker(QThread):
            resultReady = Signal(dict)
            failed = Signal(str)
            progressChanged = Signal(dict)

            def cancel(self):
                pass

            def run(self):
                self.msleep(20)
                self.progressChanged.emit({"phase": "enumerating", "enumerated": 0})
                self.resultReady.emit({"canceled": False, "sources": [], "totals": {
                    "indexed": 0, "pending": 0, "ignored_existing": 0,
                    "overlap_skipped": 0, "unsupported": 0, "errors": 0}})
                self.failed.emit("fictional queued failure")

        window = GalleryWindow(self.database)
        self.addCleanup(window.close)
        worker = FinishingWorker(window)
        window.scan_worker = worker
        worker.resultReady.connect(window._scan_result)
        worker.failed.connect(window._scan_failed)
        worker.progressChanged.connect(window._scan_progress)
        worker.finished.connect(window._scan_finished)
        worker.start()
        with patch.object(window.model, "refresh", wraps=window.model.refresh) as refresh, \
                patch.object(window, "refresh_sources", wraps=window.refresh_sources) as sources, \
                patch.object(sys, "excepthook") as exceptions:
            self.assertTrue(window.close())
            self.assertFalse(worker.isRunning())
            self.app.processEvents()
            self.app.processEvents()
            refresh.assert_not_called()
            sources.assert_not_called()
            exceptions.assert_not_called()
        self.assertTrue(window._closing)
        with self.assertRaises(sqlite3.ProgrammingError):
            window.model._db.execute("SELECT 1")

    def test_direct_catalog_launch_migrates_before_construction_and_refuses_missing(self):
        path, original = self.legacy_catalog(2)
        fake_window = Mock()

        def constructed(database, **_kwargs):
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT asset_id FROM assets").fetchone()[0], original[0])
            return fake_window

        with patch("prototypes.qt.app.QApplication", return_value=self.app), \
                patch.object(self.app, "exec", return_value=0), \
                patch("prototypes.qt.app.GalleryWindow", side_effect=constructed) as gallery, \
                patch("prototypes.qt.app.QMessageBox.information") as information:
            self.assertEqual(main(["--catalog", str(path)]), 0)
        gallery.assert_called_once()
        information.assert_called_once()
        self.assertIn("Verified backup:", information.call_args.args[2])
        missing = self.root / "direct-missing.sqlite3"
        with patch("prototypes.qt.app.QApplication", return_value=self.app), \
                patch("prototypes.qt.app.GalleryWindow") as gallery, \
                patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as refused:
                main(["--catalog", str(missing)])
        self.assertEqual(refused.exception.code, 2)
        gallery.assert_not_called()
        self.assertFalse(missing.exists())

    def test_launcher_failure_surfaces_preserved_backup_without_construction(self):
        launcher = LibraryLauncher()
        self.addCleanup(launcher.close)
        backup = self.root / "verified-backup.private.sqlite3"
        failure = CatalogMigrationError("Fictional upgrade failure", backup_path=backup)
        with patch("prototypes.qt.app.QFileDialog.getOpenFileName", return_value=(str(self.database), "")), \
                patch("prototypes.qt.app.initialize", side_effect=failure), \
                patch("prototypes.qt.app.QMessageBox.warning") as warning, \
                patch.object(launcher, "_show_gallery") as construction:
            launcher.open_library()
        construction.assert_not_called()
        self.assertIn(str(backup), warning.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
