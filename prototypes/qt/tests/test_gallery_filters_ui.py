"""Generated Qt integration checks for gateway-owned gallery publication."""
from __future__ import annotations

import os
import builtins
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import sys
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox

from defiantmaple.catalog import connect, initialize
from defiantmaple import collections as collection_api, curation, metadata
from defiantmaple.gallery_query import GalleryPage, GalleryQuery
from prototypes.qt.app import BulkCurationDialog, GalleryWindow, MetadataEditor
from prototypes.qt.gallery_filters import CatalogReply, RequestClass
from prototypes.qt import gallery_operations


class GalleryFilterWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.callback_errors = []
        self.old_excepthook = sys.excepthook
        sys.excepthook = lambda kind, value, traceback: self.callback_errors.append((kind, value))
        self.temp = tempfile.TemporaryDirectory(prefix="gallery-ui-generated-")
        self.database = Path(self.temp.name) / "catalog.sqlite3"
        initialize(self.database)
        with connect(self.database) as db:
            for number in range(300):
                db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                           "VALUES(?,?,?,?,?)",
                           (f"generated-{number:04}", str(Path(self.temp.name) / f"{number:04}.png"),
                            "image/png", f"digest-{number:04}", 1))
        self.window = GalleryWindow(self.database, enable_thumbnails=False,
                                    private_root=Path(self.temp.name) / "private")
        self.window.show()

    def tearDown(self):
        closed = False
        try:
            self.window.close()
            self.until(lambda: self.window.catalog_client.gateway.close_complete and
                       not self.window.isVisible())
            closed = True
            self.assertEqual(self.callback_errors, [])
        finally:
            sys.excepthook = self.old_excepthook
            if closed:
                self.temp.cleanup()
            else:
                # Preserve owned SQLite paths if a worker did not actually stop.
                self.temp._finalizer.detach()

    def until(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail("Bounded GUI completion did not arrive")

    def test_draft_canonical_facets_apply_atomically_and_scan_target_is_independent(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                       "VALUES('source-one','Source One','/generated/source-one','inbox')")
            db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES('sky','Sky','sky')")
            db.execute("INSERT INTO tag_aliases(tag_id,alias,normalized_alias) "
                       "VALUES('sky','Azure','azure')")
            db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) "
                       "VALUES('robin-character','Character','Robin','robin')")
            db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) "
                       "VALUES('robin-artist','Artist','Robin','robin')")
            db.execute("UPDATE assets SET current_path=?, source_id='source-one', "
                       "workflow_state='reviewed',rating=5,favorite=1,sha256='shared' "
                       "WHERE asset_id='generated-0000'",
                       (str(Path(self.temp.name) / 'literal%_thing.png'),))
            db.execute("UPDATE assets SET current_path=?,source_id='source-one',sha256='shared' "
                       "WHERE asset_id='generated-0001'",
                       (str(Path(self.temp.name) / 'literalAXthing.png'),))
            db.execute("INSERT INTO asset_tags(asset_id,tag_id) VALUES('generated-0000','sky')")
            db.execute("INSERT INTO asset_entities(asset_id,entity_id) "
                       "VALUES('generated-0000','robin-character')")
        previous = self.window.model._generation
        self.window.model.refresh()
        self.until(lambda: self.window.model._generation > previous and self.window.model._actionable)
        with patch.object(self.window, "refresh_source_issues", side_effect=AssertionError("scan issues")):
            source = self.window.gallery_source_picker
            source.browse.click()
            self.until(lambda: source.results.count() == 1 and not source._loading)
            source.results.itemClicked.emit(source.results.item(0))
            self.assertEqual(source.selected_id, "source-one")
            self.assertIsNone(self.window.source_box.currentData())
            tag = self.window.gallery_tag_picker
            tag.text.setText("Azure")
            self.until(lambda: tag.results.count() == 1 and not tag._loading)
            tag.results.itemClicked.emit(tag.results.item(0))
            self.assertEqual(tag.selected_id, "sky")
            entity = self.window.gallery_entity_picker
            entity.text.setText("Robin")
            self.until(lambda: entity.results.count() == 2 and not entity._loading)
            labels = [entity.results.item(i).text() for i in range(2)]
            self.assertTrue(any("Character" in label for label in labels))
            self.assertTrue(any("Artist" in label for label in labels))
            choice = next(entity.results.item(i) for i in range(2)
                          if "Character" in entity.results.item(i).text())
            entity.results.itemClicked.emit(choice)
            self.assertEqual(entity.selected_id, "robin-character")
        self.window.filter_box.setCurrentIndex(self.window.filter_box.findData("reviewed"))
        self.window.type_box.setCurrentIndex(self.window.type_box.findData("image/png"))
        self.window.rating_filter_box.setCurrentIndex(
            self.window.rating_filter_box.findData(curation.RatingFilter(curation.RatingMode.EXACT, 5)))
        self.window.favorite_filter_box.setCurrentIndex(
            self.window.favorite_filter_box.findData(curation.FavoriteFilter.FAVORITES))
        self.window.search_box.setText("%_")
        duplicate = QListWidgetItem()
        duplicate.setData(Qt.ItemDataRole.UserRole, "shared")
        self.window._duplicate_selected(duplicate)
        self.assertEqual(self.window.model.rowCount(), 300)
        self.assertIsNone(self.window.model._query.tag_id)
        previous = self.window.model._generation
        self.window.apply_filters_button.click()
        self.until(lambda: self.window.model._generation > previous and
                   self.window.model._actionable and self.window.model._query.tag_id == "sky")
        self.assertEqual(self.window.model.rowCount(), 1)
        self.assertEqual(self.window.model.asset_at(0)["asset_id"], "generated-0000")
        self.assertEqual(self.window.model._query.entity_id, "robin-character")
        self.assertEqual(self.window.model._query.duplicate_digest, "shared")
        self.assertIsNone(self.window.source_box.currentData())

    def test_clear_keeps_manual_collection_but_removes_all_facets_and_digest(self):
        self.until(lambda: self.window.model._actionable)
        collection = collection_api.create_collection(self.database, "Gallery subset")
        collection_id = collection["collection_id"]
        collection_api.add_member(self.database, collection_id, "generated-0000")
        collection_api.add_member(self.database, collection_id, "generated-0001")
        self.window.refresh_collections()
        self.until(lambda: self.window.collection_box.findData(collection_id) >= 0)
        self.window.collection_box.setCurrentIndex(self.window.collection_box.findData(collection_id))
        self.until(lambda: self.window.model._actionable and self.window.model.rowCount() == 2)
        self.window.search_box.setText("0000.png")
        duplicate = QListWidgetItem()
        duplicate.setData(Qt.ItemDataRole.UserRole, "digest-0000")
        self.window._duplicate_selected(duplicate)
        previous = self.window.model._generation
        self.window.apply_filters_button.click()
        self.until(lambda: self.window.model._generation > previous and
                   self.window.model._actionable and self.window.model.rowCount() == 1)
        previous = self.window.model._generation
        self.window.clear_filters_button.click()
        self.until(lambda: self.window.model._generation > previous and
                   self.window.model._actionable and self.window.model.rowCount() == 2)
        self.assertEqual(self.window.model._query.collection_id, collection_id)
        self.assertIsNone(self.window.model._query.duplicate_digest)
        self.assertEqual(self.window.model._query.path_text, "")
        self.assertEqual(self.window.collection_box.currentData(), collection_id)
        self.assertFalse(self.window.gallery.currentIndex().isValid())

    def test_unresolved_and_deleted_canonical_choices_refuse_without_broadening(self):
        self.until(lambda: self.window.model._actionable)
        picker = self.window.gallery_tag_picker
        picker.text.setText("not chosen")
        previous = self.window.model._generation
        self.window.apply_filters_button.click()
        self.assertEqual(self.window.model._generation, previous)
        self.assertIn("Resolve or clear", self.window.filter_feedback.text())
        picker.set_choice("deleted-tag", "Deleted tag")
        self.window.apply_filters_button.click()
        self.until(lambda: self.window.model._actionable and
                   "StaleFilter" in self.window.model.last_filter_error)
        self.assertEqual(self.window.model.rowCount(), 300)
        self.assertIsNone(self.window.model._query.tag_id)
        self.assertEqual(picker.selected_id, "deleted-tag")
        self.assertIn("draft retained", self.window.filter_feedback.text())
        self.window.search_box.setText("x" * 513)
        previous = self.window.model._generation
        self.window.apply_filters_button.click()
        self.assertEqual(self.window.model._generation, previous)
        self.assertEqual(len(self.window.search_box.text()), 513)

    def test_taxonomy_lookup_replaces_sixty_four_rows_and_keyboard_return_applies(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.executemany("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                           ((f"tag-{i:03}", f"Tag {i:03}", f"tag {i:03}") for i in range(70)))
        picker = self.window.gallery_tag_picker
        picker.browse.click()
        self.until(lambda: picker.results.count() == 64 and picker.more.isEnabled())
        picker.more.click()
        self.until(lambda: picker.results.count() == 6 and not picker._loading)
        self.assertFalse(picker.more.isEnabled())
        picker.results.setCurrentRow(5)
        picker.text.setFocus()
        QTest.keyClick(picker.text, Qt.Key.Key_Return)
        self.assertEqual(picker.selected_id, "tag-069")
        previous = self.window.model._generation
        QTest.keyClick(picker.text, Qt.Key.Key_Return)
        self.until(lambda: self.window.model._generation > previous and self.window.model._actionable)
        self.assertEqual(self.window.model.rowCount(), 0)
        self.window.clear_filters_button.click()
        self.until(lambda: self.window.model._actionable and self.window.model.rowCount() == 300)
        QTest.keyClick(self.window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.search_box.hasFocus())

    def test_source_lookup_pages_without_scanning_and_unresolved_edit_blocks_apply(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.executemany(
                "INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                "VALUES(?,?,?,?)",
                ((f"source-{i:03}", f"Source {i:03}", f"/generated/source-{i:03}", "inbox")
                 for i in range(65)))
        picker = self.window.gallery_source_picker
        with patch.object(self.window, "refresh_source_issues", side_effect=AssertionError("source issues")):
            picker.browse.click()
            self.until(lambda: picker.results.count() == 64 and picker.more.isEnabled())
            picker.more.click()
            self.until(lambda: picker.results.count() == 1 and not picker._loading)
            picker.results.itemClicked.emit(picker.results.item(0))
            self.assertEqual(picker.selected_id, "source-064")
            self.assertIsNone(self.window.source_box.currentData())
            previous = self.window.model._generation
            picker.text.setText("unresolved")
            self.assertIsNone(picker.selected_id)
            self.window.apply_filters_button.click()
            self.assertEqual(self.window.model._generation, previous)
            self.assertIn("Resolve or clear", self.window.filter_feedback.text())
        picker.clear_choice()
        self.assertIsNone(picker.selected_id)
        self.assertEqual(self.window.model._generation, previous)

    def test_newer_draft_edit_during_apply_remains_unapplied(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.search_box.setText("0000.png")
        previous = model._generation
        self.window.apply_filters_button.click()
        self.window.search_box.setText("0001.png")
        self.until(lambda: model._generation > previous and model._actionable and
                   model._query.path_text == "0000.png")
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(self.window.search_box.text(), "0001.png")
        self.assertIn("newer edits remain unapplied", self.window.filter_feedback.text())
        previous = model._generation
        self.window.apply_filters_button.click()
        self.until(lambda: model._generation > previous and model._actionable and
                   model._query.path_text == "0001.png")
        self.assertEqual(model.asset_at(0)["asset_id"], "generated-0001")

    def test_failed_candidate_restore_cancelled_by_captured_dialog_write_recovers_old_view(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled() and "revision" in editor.state)
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        entered, release = threading.Event(), threading.Event()
        original = gallery_operations.count_first_page
        def hold_old_view(db, context, query, *args):
            if query == GalleryQuery():
                entered.set()
                release.wait(2)
            return original(db, context, query, *args)
        picker = self.window.gallery_tag_picker
        try:
            with patch.object(gallery_operations, "count_first_page", side_effect=hold_old_view):
                picker.set_choice("deleted-tag", "Deleted tag")
                self.window.apply_filters_button.click()
                self.until(entered.is_set)
                self.assertIsNone(model._tag_filter)
                self.assertFalse(model._actionable)
                editor.save()  # Already-open editor keeps its captured stable ID.
                release.set()
                self.until(lambda: model._actionable and not self.window._mutation_pending and
                           model._query == GalleryQuery())
        finally:
            release.set()
        self.assertEqual(model.rowCount(), 300)
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertIsNone(model._tag_filter)
        self.assertEqual(picker.selected_id, "deleted-tag")
        self.assertIn("draft retained", self.window.filter_feedback.text())
        self.assertEqual(editor.feedback.text(), "Rating and favorite saved to catalog.")
        editor.close()

    def test_deferred_deleted_filter_during_captured_write_restores_published_view(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled() and "revision" in editor.state)
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        original = curation.set_curation
        entered, release = threading.Event(), threading.Event()
        calls = []
        def delayed(*args, **kwargs):
            calls.append("write")
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)
        picker = self.window.gallery_tag_picker
        try:
            with patch.object(curation, "set_curation", side_effect=delayed):
                editor.save()
                self.until(entered.is_set)
                picker.set_choice("deleted-tag", "Deleted tag")
                self.window.apply_filters_button.click()
                self.assertFalse(model._actionable)
                self.assertEqual(model._tag_filter, "deleted-tag")
                self.assertEqual(model._query, GalleryQuery())
                release.set()
                self.until(lambda: model._actionable and not self.window._mutation_pending and
                           model._query == GalleryQuery() and model.rowCount() == 300 and
                           "draft retained" in self.window.filter_feedback.text())
        finally:
            release.set()
        self.assertEqual(calls, ["write"])
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertIsNone(model._tag_filter)
        self.assertEqual(picker.selected_id, "deleted-tag")
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        self.assertIsNone(self.window._selected_asset())
        self.assertEqual(editor.feedback.text(), "Rating and favorite saved to catalog.")
        editor.close()

    def test_apply_clears_loaded_multi_selection_detail_and_openers_without_row_zero_target(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        self.window._show_detail(model.index(0))
        self.until(lambda: self.window._selected_asset() is not None and
                   len(selection.selectedIndexes()) == 2)
        self.assertTrue(self.window.curation_button.isEnabled())
        self.assertTrue(self.window.bulk_curation_button.isEnabled())
        self.window.search_box.setText("0002.png")
        previous = model._generation
        self.window.apply_filters_button.click()
        self.assertFalse(model._actionable)
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        self.assertEqual(selection.selectedIndexes(), [])
        self.assertIsNone(self.window._selected_asset())
        self.assertIn("Updating catalog view", self.window.detail.toPlainText())
        self.assertNotIn("generated-0000", self.window.detail.toPlainText())
        self.assertFalse(self.window.curation_button.isEnabled())
        self.assertFalse(self.window.bulk_curation_button.isEnabled())
        self.until(lambda: model._generation > previous and model._actionable and
                   model.rowCount() == 1)
        self.assertEqual(model.asset_at(0)["asset_id"], "generated-0002")
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        self.assertEqual(selection.selectedIndexes(), [])
        self.assertIsNone(self.window._selected_asset())
        self.assertFalse(self.window.inspect_button.isEnabled())
        self.assertFalse(self.window.curation_button.isEnabled())

    def test_permitted_long_canonical_label_keeps_picker_width_bounded(self):
        self.until(lambda: self.window.model._actionable)
        picker = self.window.gallery_tag_picker
        self.app.processEvents()
        before_minimum, before_window = picker.minimumSizeHint().width(), self.window.width()
        long_name = "W" * 256
        picker.set_choice("long-tag", long_name)
        self.app.processEvents()
        self.assertEqual(picker.text.text(), long_name)
        self.assertEqual(picker.feedback.text(), f"Selected {long_name}")
        self.assertLessEqual(picker.minimumSizeHint().width(), before_minimum + 80)
        self.assertLessEqual(self.window.width(), before_window + 80)

    def test_shared_taxonomy_slot_supersession_clears_loading_and_allows_retry(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES('sky','Sky','sky')")
            db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) "
                       "VALUES('robin','Character','Robin','robin')")
        entered, release = threading.Event(), threading.Event()
        original = curation.list_curation_batches
        def hold_legacy(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)
        tag, entity = self.window.gallery_tag_picker, self.window.gallery_entity_picker
        try:
            with patch.object(curation, "list_curation_batches", side_effect=hold_legacy):
                self.window.open_curation_history()
                self.until(entered.is_set)
                tag.text.setText("Sky")
                self.assertTrue(tag._loading)
                entity.text.setText("Robin")
                self.until(lambda: not tag._loading)
                self.assertIn("replaced", tag.feedback.text().lower())
                self.assertTrue(entity._loading)
                release.set()
                self.until(lambda: entity.results.count() == 1 and not entity._loading)
        finally:
            release.set()
        tag.browse.click()
        self.until(lambda: tag.results.count() == 1 and not tag._loading)
        self.assertEqual(tag.results.item(0).data(Qt.ItemDataRole.UserRole)[0], "sky")

    def test_oversized_label_unsafe_cursor_input_and_html_like_name_are_plain_text(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.executemany("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                           ((f"tag-{i:03}", "L" * 300 if i == 63 else f"Tag {i:03}",
                             f"tag {i:03}") for i in range(65)))
            db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                       ("html-tag", "<b>literal</b>", "<b>literal</b>"))
        picker = self.window.gallery_tag_picker
        picker.text.setText("tag ")
        self.until(lambda: picker.results.count() == 64 and not picker._loading)
        self.assertFalse(picker.more.isEnabled())
        self.assertIn("refine the prefix", picker.feedback.text())
        self.assertFalse(bool(picker.results.item(63).flags() & Qt.ItemFlag.ItemIsEnabled))
        picker.text.setText("tag 064")
        self.until(lambda: picker.results.count() == 1 and not picker._loading)
        self.assertTrue(bool(picker.results.item(0).flags() & Qt.ItemFlag.ItemIsEnabled))
        picker.text.setText("x" * 129)
        self.assertEqual(len(picker.text.text()), 129)
        self.assertIn("at most 128", picker.feedback.text())
        picker.text.setText("<b>")
        self.until(lambda: picker.results.count() == 1 and not picker._loading)
        picker.results.itemClicked.emit(picker.results.item(0))
        self.assertEqual(picker.feedback.text(), "Selected <b>literal</b>")
        self.assertEqual(picker.feedback.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(self.window.filter_feedback.textFormat(), Qt.TextFormat.PlainText)

    def test_escape_dismisses_unresolved_picker_before_other_shortcuts(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES('sky','Sky','sky')")
        picker = self.window.gallery_tag_picker
        picker.text.setText("Sky")
        self.until(lambda: picker.results.isVisible() and not picker._loading)
        generation = self.window.model._generation
        picker.text.setFocus()
        QTest.keyClick(picker.text, Qt.Key.Key_Escape)
        self.assertFalse(picker.results.isVisible())
        self.assertEqual(picker.text.text(), "Sky")
        QTest.keyClick(picker.text, Qt.Key.Key_Escape)
        self.assertEqual(picker.text.text(), "")
        self.assertIsNone(picker.selected_id)
        self.assertEqual(self.window.model._generation, generation)

    def test_bounded_gallery_source_read_and_apply_do_not_touch_registered_media_root(self):
        self.until(lambda: self.window.model._actionable and self.window._startup_validated)
        source_root = Path(self.temp.name) / "registered-media"
        with connect(self.database) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                       "VALUES(?,?,?,?)", ("catalog-source", "Catalog Source", str(source_root), "inbox"))
            db.execute("UPDATE assets SET source_id='catalog-source' "
                       "WHERE asset_id='generated-0000'")
        original_stat, original_lstat = os.stat, os.lstat
        original_scandir, original_listdir = os.scandir, os.listdir
        original_os_open, original_open = os.open, builtins.open
        original_path_resolve, original_path_open = Path.resolve, Path.open
        touched = []
        def guarded(function):
            def call(path, *args, **kwargs):
                if isinstance(path, (str, bytes, os.PathLike)) and \
                        os.fsdecode(path).startswith(str(source_root)):
                    touched.append(str(path))
                    raise AssertionError("Gallery filter attempted source-media I/O")
                return function(path, *args, **kwargs)
            return call
        with (patch.object(os, "stat", guarded(original_stat)),
              patch.object(os, "lstat", guarded(original_lstat)),
              patch.object(os, "scandir", guarded(original_scandir)),
              patch.object(os, "listdir", guarded(original_listdir)),
              patch.object(os, "open", guarded(original_os_open)),
              patch.object(builtins, "open", guarded(original_open)),
              patch.object(Path, "resolve", guarded(original_path_resolve)),
              patch.object(Path, "open", guarded(original_path_open)),
              patch.object(self.window, "refresh_source_issues",
                           side_effect=AssertionError("Gallery source enumerated scan issues"))):
            picker = self.window.gallery_source_picker
            picker.browse.click()
            self.until(lambda: picker.results.count() == 1 and not picker._loading)
            picker.results.itemClicked.emit(picker.results.item(0))
            previous = self.window.model._generation
            self.window.apply_filters_button.click()
            self.until(lambda: self.window.model._generation > previous and
                       self.window.model._actionable and self.window.model.rowCount() == 1)
            self.assertEqual(self.window.model.asset_at(0)["asset_id"], "generated-0000")
        self.assertEqual(touched, [])

    def test_initial_page_later_page_and_review_write_publish_fresh_generation(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.assertEqual(model.rowCount(), 300)
        self.assertEqual(len(model._cache[0]), 256)
        self.assertEqual(model.asset_at(0)["asset_id"], "generated-0000")
        self.assertIsNone(model.loaded_asset_at(299))
        self.until(lambda: model.loaded_asset_at(299) is not None)
        self.assertEqual(model.asset_at(299)["asset_id"], "generated-0299")
        self.window.gallery.setCurrentIndex(model.index(0))
        captured = model.asset_at(0)
        generation = model._generation
        self.window.set_selected_state("reviewed")
        self.assertFalse(model._actionable)
        self.assertIsNone(self.window._selected_asset())
        self.until(lambda: model._actionable and model._generation > generation)
        with connect(self.database) as db:
            actual = db.execute("SELECT workflow_state FROM assets WHERE asset_id=?",
                                (captured["asset_id"],)).fetchone()[0]
        self.assertEqual(actual, "reviewed")
        self.assertEqual(model.rowCount(), 300)
        self.assertEqual(model.asset_at(0)["workflow_state"], "reviewed")

    def test_failed_candidate_does_not_target_previous_rows(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        original_token = model._token
        original_count = model.rowCount()
        self.window.gallery.setCurrentIndex(model.index(0))
        model._source_filter = "deleted-source"
        model.refresh()
        self.assertFalse(model._actionable)
        self.assertIsNone(self.window._selected_asset())
        self.until(lambda: model._actionable and model._token is not original_token)
        self.assertEqual(model.rowCount(), original_count)
        self.assertEqual(model.asset_at(0)["asset_id"], "generated-0000")
        self.assertIsNone(model._source_filter)
        self.assertIn("StaleFilter", model.last_filter_error)
        self.assertIn("StaleFilter", self.window.statusBar().currentMessage())
        self.assertFalse(self.window.gallery.currentIndex().isValid())

    def test_closed_metadata_editor_discards_late_taxonomy_reply(self):
        self.until(lambda: self.window.model._actionable and hasattr(self.window, "collection_records"))
        entered, release = threading.Event(), threading.Event()
        original = metadata.list_tags
        def delayed(database):
            entered.set()
            release.wait(2)
            return original(database)
        with patch.object(metadata, "list_tags", delayed):
            editor = MetadataEditor(self.database, None, None, self.window,
                                    catalog_window=self.window)
            editor.show()
            self.until(entered.is_set)
            editor.close()
            release.set()
            self.until(lambda: self.window.catalog_client.gateway.pending_count == 0)
            self.app.processEvents()
            self.assertEqual(editor.tags.list.count(), 0)
            self.assertTrue(editor._catalog_closed)

    def test_metadata_saved_feedback_survives_cancelled_old_read_and_real_error_remains_visible(self):
        self.until(lambda: self.window.model._actionable)
        target_id = "generated-0000"
        later_focus_id = "generated-0001"
        self.window.gallery.setCurrentIndex(self.window.model.index(1))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == later_focus_id)
        editor = MetadataEditor(self.database, target_id, "Generated target", self.window,
                                catalog_window=self.window)
        editor.show()
        try:
            self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))

            def saved_record(panel, name):
                panel.name.setText(name)
                panel.create_button.click()
                self.until(lambda: not self.window._mutation_pending and
                           editor.feedback.text() == "Catalog metadata saved." and
                           panel.selected_record() is not None and
                           panel.selected_record()["name"] == name)
                return panel.selected_record()[panel.id_field]

            tag_id = saved_record(editor.tags, "Rapid tag")
            editor.tags.assign_button.click()
            self.until(lambda: not self.window._mutation_pending and
                       editor.feedback.text() == "Catalog metadata saved." and
                       any(row["tag_id"] == tag_id for row in editor.asset_metadata["tags"]))
            entity_id = saved_record(editor.entities, "Rapid character")
            editor.entities.assign_button.click()
            self.until(lambda: not self.window._mutation_pending and
                       editor.feedback.text() == "Catalog metadata saved." and
                       any(row["entity_id"] == entity_id
                           for row in editor.asset_metadata["entities"]))
            assigned = metadata.get_asset_metadata(self.database, target_id)
            self.assertEqual([row["tag_id"] for row in assigned["tags"]], [tag_id])
            self.assertEqual([row["entity_id"] for row in assigned["entities"]], [entity_id])
            self.assertEqual(metadata.get_asset_metadata(self.database, later_focus_id)["tags"], [])
            self.assertEqual(metadata.get_asset_metadata(self.database, later_focus_id)["entities"], [])
            self.until(lambda: self.window._selected_asset() is not None and
                       self.window._selected_asset()["asset_id"] == later_focus_id)

            entered, release = threading.Event(), threading.Event()
            original_entities = metadata.list_entities
            cancelled = []
            def delayed_entities(database, *, entity_type=None):
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Held taxonomy read was not released")
                return original_entities(database, entity_type=entity_type)
            def completed(reply):
                if reply.category == RequestClass.LEGACY and reply.status == "cancelled":
                    cancelled.append(reply.request_id)
            self.window.catalog_client.gateway.completed.connect(completed)
            try:
                with patch.object(metadata, "list_entities", side_effect=delayed_entities):
                    editor.entities.refresh()
                    self.until(entered.is_set)
                    previous = self.window.model._generation
                    self.window.model.refresh()
                    release.set()
                    self.until(lambda: cancelled and
                               self.window.model._generation > previous and
                               self.window.model._actionable)
                self.assertEqual(editor.feedback.text(), "Catalog metadata saved.")
            finally:
                release.set()
                self.window.catalog_client.gateway.completed.disconnect(completed)

            with patch.object(metadata, "list_tags",
                              side_effect=ValueError("generated taxonomy read failure")):
                editor.tags.refresh()
                self.until(lambda: "generated taxonomy read failure" in editor.feedback.text())
            self.assertEqual([row["tag_id"] for row in
                              metadata.get_asset_metadata(self.database, target_id)["tags"]],
                             [tag_id])
        finally:
            editor.close()

    def test_metadata_write_does_not_restore_focus_over_explicit_apply(self):
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(1))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0001")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        entered, release = threading.Event(), threading.Event()
        original = metadata.create_tag
        calls = []
        def delayed(database, name):
            calls.append(name)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Held metadata write was not released")
            return original(database, name)
        delayed.__name__ = "create_tag"
        try:
            self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
            with patch.object(metadata, "create_tag", delayed):
                editor.tags.name.setText("Captured tag after Apply")
                editor.tags.create_button.click()
                self.until(entered.is_set)
                self.window.search_box.setText("0299.png")
                self.window.apply_filters_button.click()
                self.assertIsNone(self.window._metadata_focus_intent)
                self.assertFalse(self.window.gallery.currentIndex().isValid())
                release.set()
                self.until(lambda: not self.window._mutation_pending and
                           self.window.model._actionable and
                           self.window.model._query.path_text == "0299.png" and
                           self.window.model.rowCount() == 1)
            self.assertEqual(calls, ["Captured tag after Apply"])
            self.assertEqual([row["name"] for row in metadata.list_tags(self.database)],
                             ["Captured tag after Apply"])
            self.assertEqual(self.window.model.asset_at(0)["asset_id"], "generated-0299")
            self.assertFalse(self.window.gallery.currentIndex().isValid())
            self.assertIsNone(self.window._selected_asset())
            self.assertIsNone(self.window._metadata_focus_intent)
        finally:
            release.set()
            editor.close()

    def test_metadata_pending_rank_yields_to_later_choice_and_explicit_clear(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(1))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0001")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
        try:
            for number, later_choice in enumerate((True, False)):
                entered, release = threading.Event(), threading.Event()
                ranked = []
                original = gallery_operations.rank_for_asset
                def delayed(*args):
                    if args[-1] == "generated-0001":
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError("Held rank was not released")
                    return original(*args)
                def completed(reply):
                    if reply.category == RequestClass.RANK:
                        ranked.append(reply.request_id)
                self.window.catalog_client.gateway.completed.connect(completed)
                try:
                    with patch.object(gallery_operations, "rank_for_asset", delayed):
                        editor.tags.name.setText(f"Choice guard tag {number}")
                        editor.tags.create_button.click()
                        self.until(entered.is_set)
                        self.assertTrue(self.window.model._actionable)
                        if later_choice:
                            self.window.gallery.setCurrentIndex(self.window.model.index(2))
                            self.assertIsNone(self.window._metadata_focus_intent)
                        else:
                            selection = self.window.gallery.selectionModel()
                            self.assertFalse(selection.currentIndex().isValid())
                            selection.clear()
                            self.assertIsNone(self.window._metadata_focus_intent)
                        release.set()
                        self.until(lambda: ranked)
                    if later_choice:
                        self.until(lambda: self.window._selected_asset() is not None and
                                   self.window._selected_asset()["asset_id"] == "generated-0002")
                        self.window.gallery.setCurrentIndex(self.window.model.index(1))
                        self.until(lambda: self.window._selected_asset() is not None and
                                   self.window._selected_asset()["asset_id"] == "generated-0001")
                    else:
                        self.assertFalse(self.window.gallery.currentIndex().isValid())
                        self.assertIsNone(self.window._selected_asset())
                finally:
                    release.set()
                    self.window.catalog_client.gateway.completed.disconnect(completed)
            self.assertEqual([row["name"] for row in metadata.list_tags(self.database)],
                             ["Choice guard tag 0", "Choice guard tag 1"])
            self.assertEqual(metadata.get_asset_metadata(self.database, "generated-0000")["tags"], [])
        finally:
            editor.close()

    def test_metadata_rank_refusal_drops_focus_intent_before_next_write(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(1))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0001")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
        original = gallery_operations.rank_for_asset
        refused = []
        def refuse_rank(*args):
            if args[-1] == "generated-0001":
                raise ValueError("generated focus rank refusal")
            return original(*args)
        def completed(reply):
            if reply.category == RequestClass.RANK and reply.status == "error":
                refused.append(reply.request_id)
        self.window.catalog_client.gateway.completed.connect(completed)
        try:
            with patch.object(gallery_operations, "rank_for_asset", refuse_rank):
                editor.tags.name.setText("First rank refusal tag")
                editor.tags.create_button.click()
                self.until(lambda: refused and not self.window._mutation_pending and
                           self.window.model._actionable and
                           self.window._metadata_focus_intent is None)
            self.assertFalse(self.window.gallery.currentIndex().isValid())
            editor.tags.name.setText("Second no-focus tag")
            editor.tags.create_button.click()
            self.until(lambda: not self.window._mutation_pending and
                       self.window.model._actionable and
                       any(row["name"] == "Second no-focus tag"
                           for row in metadata.list_tags(self.database)))
            self.assertIsNone(self.window._metadata_focus_intent)
            self.assertFalse(self.window.gallery.currentIndex().isValid())
            self.assertEqual(metadata.get_asset_metadata(self.database, "generated-0000")["tags"], [])
        finally:
            self.window.catalog_client.gateway.completed.disconnect(completed)
            editor.close()

    def test_metadata_page_refusal_drops_focus_intent_without_late_retarget(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        model.request_page(1)
        self.until(lambda: 1 in model._cache)
        self.window.gallery.setCurrentIndex(model.index(299))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0299")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
        original = gallery_operations.later_page
        page_errors = []
        def refuse_page(*args):
            if args[-1] == 1:
                raise ValueError("generated focus page refusal")
            return original(*args)
        def completed(reply):
            if reply.category == RequestClass.PAGE and reply.status == "error":
                page_errors.append(reply.request_id)
        self.window.catalog_client.gateway.completed.connect(completed)
        try:
            with patch.object(gallery_operations, "later_page", refuse_page):
                editor.tags.name.setText("Page refusal tag")
                editor.tags.create_button.click()
                self.until(lambda: page_errors and model._actionable and
                           self.window._metadata_focus_intent is None and
                           1 in model._failed_pages)
            self.assertFalse(self.window.gallery.currentIndex().isValid())
            self.assertIsNone(self.window._selected_asset())
            self.app.processEvents()
            self.assertFalse(self.window.gallery.currentIndex().isValid())
        finally:
            self.window.catalog_client.gateway.completed.disconnect(completed)
            editor.close()

    def test_metadata_other_page_failure_does_not_cancel_focused_page_restore(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            db.executemany(
                "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                "VALUES(?,?,?,?,?)",
                ((f"generated-{number:04}", str(Path(self.temp.name) / f"{number:04}.png"),
                  "image/png", f"digest-{number:04}", 1)
                 for number in range(300, 600)))
        model = self.window.model
        previous = model._generation
        model.refresh()
        self.until(lambda: model._generation > previous and model._actionable and
                   model.rowCount() == 600)
        model.request_page(1)
        self.until(lambda: 1 in model._cache)
        self.window.gallery.setCurrentIndex(model.index(299))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0299")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
        original_page = gallery_operations.later_page
        original_request = model.request_page
        other_errors = []
        def fail_other_page(*args):
            if args[-1] == 2:
                raise ValueError("generated unrelated page failure")
            return original_page(*args)
        def request_other_first(page):
            if page == 1:
                original_request(2)
            original_request(page)
        def completed(reply):
            if reply.category == RequestClass.PAGE and reply.status == "error":
                other_errors.append(reply.request_id)
        self.window.catalog_client.gateway.completed.connect(completed)
        try:
            with (patch.object(gallery_operations, "later_page", fail_other_page),
                  patch.object(model, "request_page", request_other_first)):
                editor.tags.name.setText("Other page fails")
                editor.tags.create_button.click()
                self.until(lambda: other_errors and 2 in model._failed_pages and
                           self.window._selected_asset() is not None and
                           self.window._selected_asset()["asset_id"] == "generated-0299")
            self.assertIn(1, model._cache)
            self.assertNotIn(1, model._failed_pages)
            self.assertIsNone(self.window._metadata_focus_intent)
            self.assertEqual([row["name"] for row in metadata.list_tags(self.database)],
                             ["Other page fails"])
        finally:
            self.window.catalog_client.gateway.completed.disconnect(completed)
            editor.close()

    def test_metadata_late_page_reply_and_close_cannot_retarget_focus(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        model.request_page(1)
        self.until(lambda: 1 in model._cache)
        self.window.gallery.setCurrentIndex(model.index(299))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0299")
        editor = MetadataEditor(self.database, "generated-0000", "Captured A", self.window,
                                catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.assigned.text().startswith("Assigned tags:"))
        entered, release = threading.Event(), threading.Event()
        page_replies = []
        original = gallery_operations.later_page
        def delayed(*args):
            if args[-1] == 1:
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Held focus page was not released")
            return original(*args)
        def completed(reply):
            if reply.category == RequestClass.PAGE:
                page_replies.append(reply.request_id)
        self.window.catalog_client.gateway.completed.connect(completed)
        try:
            with patch.object(gallery_operations, "later_page", delayed):
                editor.tags.name.setText("Late page tag")
                editor.tags.create_button.click()
                self.until(entered.is_set)
                self.assertFalse(self.window.gallery.currentIndex().isValid())
                self.window.gallery.selectionModel().clear()
                self.assertIsNone(self.window._metadata_focus_intent)
                release.set()
                self.until(lambda: page_replies)
            self.assertFalse(self.window.gallery.currentIndex().isValid())
            self.assertIsNone(self.window._selected_asset())
            self.assertEqual([row["name"] for row in metadata.list_tags(self.database)],
                             ["Late page tag"])

            self.window.gallery.setCurrentIndex(model.index(299))
            self.until(lambda: self.window._selected_asset() is not None and
                       self.window._selected_asset()["asset_id"] == "generated-0299")
            rank_entered, rank_release = threading.Event(), threading.Event()
            original_rank = gallery_operations.rank_for_asset
            def held_rank(*args):
                if args[-1] == "generated-0299":
                    rank_entered.set()
                    if not rank_release.wait(5):
                        raise AssertionError("Held close rank was not released")
                return original_rank(*args)
            try:
                with patch.object(gallery_operations, "rank_for_asset", held_rank):
                    editor.tags.name.setText("Close guard tag")
                    editor.tags.create_button.click()
                    self.until(rank_entered.is_set)
                    editor.close()
                    self.window.close()
                    self.assertIsNone(self.window._metadata_focus_intent)
                    rank_release.set()
                    self.until(lambda: self.window.catalog_client.gateway.close_complete and
                               not self.window.isVisible())
            finally:
                rank_release.set()
        finally:
            release.set()
            self.window.catalog_client.gateway.completed.disconnect(completed)
            editor.close()

    def test_modal_mutation_refusal_is_visible_and_restores_button(self):
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled())
        self.window._mutation_pending = True
        try:
            editor.save()
            self.assertTrue(editor.save_button.isEnabled())
            self.assertIn("pending", editor.feedback.text())
        finally:
            self.window._mutation_pending = False
            editor.close()

    def test_worker_core_curation_failure_is_reported_without_edit(self):
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled() and "revision" in editor.state)
        before = curation.get_curation(self.database, "generated-0000")
        called = threading.Event()
        def fail(*_args, **_kwargs):
            called.set()
            raise sqlite3.OperationalError("generated worker write failure")
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        with patch.object(curation, "set_curation", side_effect=fail):
            editor.save()
            self.until(lambda: called.is_set() and not self.window._mutation_pending and
                       "outcome unknown" in editor.feedback.text() and
                       editor.save_button.isEnabled())
        self.assertIn("generated worker write failure", editor.feedback.text())
        self.assertEqual(curation.get_curation(self.database, "generated-0000"), before)
        self.assertEqual(curation.list_curation_edits(self.database, "generated-0000"), [])
        editor.close()

    def test_curation_save_preserves_later_focus_and_terminal_feedback(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled() and "revision" in editor.state)
        self.window.gallery.setCurrentIndex(model.index(1))
        self.until(lambda: self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0001")
        emitted = []
        editor.saved.connect(emitted.append)
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.favorite_box.setChecked(True)
        editor.save()
        self.until(lambda: model._actionable and not self.window._mutation_pending and
                   editor.save_button.isEnabled() and editor.state.get("rating") == 5 and
                   editor.feedback.text() == "Rating and favorite saved to catalog." and
                   self.window._selected_asset() is not None and
                   self.window._selected_asset()["asset_id"] == "generated-0001")
        self.assertEqual(emitted, ["generated-0000"])
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertEqual(curation.get_curation(self.database, "generated-0001")["rating"], None)
        self.assertEqual(self.window.gallery.currentIndex().row(), 1)
        editor.save()
        self.until(lambda: editor.save_button.isEnabled() and
                   editor.feedback.text() == "No changes to save.")
        self.assertEqual(emitted, ["generated-0000"])
        editor.reload()
        self.until(lambda: editor.feedback.text() == "Current catalog values loaded.")
        editor.close()

    def test_curation_commit_then_raise_keeps_unknown_outcome_and_reloads_actual_values(self):
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        editor = self.window.edit_curation()
        self.until(lambda: editor.save_button.isEnabled() and "revision" in editor.state)
        emitted = []
        editor.saved.connect(emitted.append)
        original_save = curation.set_curation
        calls = []
        def committed_then_raised(*args, **kwargs):
            calls.append("save")
            original_save(*args, **kwargs)
            raise RuntimeError("generated after save commit")
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        with patch.object(curation, "set_curation", side_effect=committed_then_raised):
            editor.save()
            self.until(lambda: not self.window._mutation_pending and
                       editor.save_button.isEnabled() and editor.state.get("rating") == 5 and
                       "outcome unknown" in editor.feedback.text())
        self.assertEqual(calls, ["save"])
        self.assertIn("generated after save commit", editor.feedback.text())
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertEqual(len(curation.list_curation_edits(self.database, "generated-0000")), 1)
        self.assertEqual(emitted, [])
        original_undo = curation.undo_curation
        def undone_then_raised(*args, **kwargs):
            calls.append("undo")
            original_undo(*args, **kwargs)
            raise RuntimeError("generated after undo commit")
        self.assertTrue(editor.undo_button.isEnabled())
        with patch.object(curation, "undo_curation", side_effect=undone_then_raised):
            editor.undo()
            self.until(lambda: not self.window._mutation_pending and
                       editor.save_button.isEnabled() and editor.state.get("rating") is None and
                       "undo outcome unknown" in editor.feedback.text())
        self.assertEqual(calls, ["save", "undo"])
        self.assertIn("generated after undo commit", editor.feedback.text())
        self.assertIsNone(curation.get_curation(self.database, "generated-0000")["rating"])
        self.assertEqual(emitted, [])
        editor.close()

    def test_bulk_write_restores_write_intent_selection_after_success_and_failure(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()

        def select_ids(*numbers, focus):
            selection.clear()
            for number in numbers:
                selection.select(model.index(number), QItemSelectionModel.SelectionFlag.Select)
            selection.setCurrentIndex(model.index(focus),
                                      QItemSelectionModel.SelectionFlag.NoUpdate)

        def selected_ids():
            return {model.loaded_asset_at(index.row())["asset_id"]
                    for index in selection.selectedIndexes()}

        select_ids(0, 1, focus=0)
        editor = self.window.edit_bulk_curation()
        self.assertEqual([target.asset_id for target in editor.targets],
                         ["generated-0000", "generated-0001"])
        # The dialog keeps its captured A/B targets, but the later B/C gallery
        # choice at write intent is the selection that should survive refresh.
        select_ids(1, 2, focus=2)
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        self.until(lambda: editor.apply_button.isEnabled() and
                   editor.plan is not None and editor.plan.changed_count == 2)
        generation = model._generation
        editor.apply()
        self.until(lambda: model._actionable and model._generation > generation and
                   not self.window._mutation_pending and
                   selected_ids() == {"generated-0001", "generated-0002"} and
                   self.window._loaded_focused_asset() is not None and
                   self.window._loaded_focused_asset()["asset_id"] == "generated-0002")
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertEqual(curation.get_curation(self.database, "generated-0001")["rating"], 5)
        self.assertIsNone(curation.get_curation(self.database, "generated-0002")["rating"])
        editor.close()

        # A dispatched Core failure still refreshes the view. It must not
        # silently replace the current B/C selection with the dialog's target.
        failed = self.window.edit_bulk_curation()
        self.assertEqual([target.asset_id for target in failed.targets],
                         ["generated-0001", "generated-0002"])
        failed.rating_box.setCurrentIndex(failed.rating_box.findData(4))
        failed.preview()
        self.until(lambda: failed.apply_button.isEnabled() and
                   failed.plan is not None and failed.plan.changed_count == 2)
        called = threading.Event()
        def storage_failure(*_args, **_kwargs):
            called.set()
            raise sqlite3.OperationalError("generated bulk write failure")
        generation = model._generation
        with patch.object(curation, "apply_curation_batch", side_effect=storage_failure):
            failed.apply()
            self.until(lambda: called.is_set() and model._actionable and
                       model._generation > generation and not self.window._mutation_pending and
                       selected_ids() == {"generated-0001", "generated-0002"})
        self.assertIn("outcome requires reload", failed.feedback.text())
        self.assertEqual(curation.get_curation(self.database, "generated-0001")["rating"], 5)
        self.assertIsNone(curation.get_curation(self.database, "generated-0002")["rating"])
        failed.close()

    def test_late_bulk_history_list_keeps_later_group_choice_and_undo_target(self):
        self.until(lambda: self.window.model._actionable)
        first = curation.apply_curation_batch(self.database, curation.preview_curation_batch(
            self.database, curation.capture_curation(self.database, ("generated-0000",)),
            curation.CurationChanges(rating=4)))
        second = curation.apply_curation_batch(self.database, curation.preview_curation_batch(
            self.database, curation.capture_curation(self.database, ("generated-0001",)),
            curation.CurationChanges(rating=5)))
        self.assertEqual({item["batch_id"] for item in curation.list_curation_batches(self.database)},
                         {first["batch_id"], second["batch_id"]})
        editor = BulkCurationDialog(self.database, (), self.window, history_only=True,
                                    catalog_window=self.window)
        editor.show()
        self.until(lambda: editor.group_box.findData(first["batch_id"]) >= 0 and
                   editor.group_box.findData(second["batch_id"]) >= 0)
        editor.group_box.setCurrentIndex(editor.group_box.findData(first["batch_id"]))
        self.until(lambda: editor.undo_batch_id == first["batch_id"])
        entered, release = threading.Event(), threading.Event()
        original = curation.list_curation_batches
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)
        try:
            with patch.object(curation, "list_curation_batches", side_effect=delayed):
                editor.refresh_history()
                self.until(entered.is_set)
                editor.group_box.setCurrentIndex(editor.group_box.findData(second["batch_id"]))
                release.set()
                self.until(lambda: editor.group_box.currentData() == second["batch_id"] and
                           editor.undo_batch_id == second["batch_id"] and
                           editor.undo_button.isEnabled())
        finally:
            release.set()
        editor.undo_group()
        self.until(lambda: curation.get_curation_batch(self.database, second["batch_id"])["undone"])
        self.assertFalse(curation.get_curation_batch(self.database, first["batch_id"])["undone"])
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 4)
        self.assertIsNone(curation.get_curation(self.database, "generated-0001")["rating"])
        editor.close()

    def test_filter_apply_during_bulk_write_wins_without_old_selection_restore(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        editor = self.window.edit_bulk_curation()
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        self.until(lambda: editor.apply_button.isEnabled() and editor.plan is not None)
        original = curation.apply_curation_batch
        entered, release = threading.Event(), threading.Event()
        calls = []
        def delayed(*args, **kwargs):
            calls.append("apply")
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)
        try:
            with patch.object(curation, "apply_curation_batch", side_effect=delayed):
                editor.apply()
                self.until(entered.is_set)
                self.window.filter_box.setCurrentIndex(
                    self.window.filter_box.findData("reviewed"))
                self.assertIsNone(model._query.state)
                self.window.apply_filters_button.click()
                self.assertFalse(model._actionable)
                self.assertEqual(selection.selectedIndexes(), [])
                release.set()
                self.until(lambda: model._actionable and not self.window._mutation_pending and
                           model._query.state == "reviewed" and model.rowCount() == 0)
        finally:
            release.set()
        self.assertEqual(calls, ["apply"])
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertEqual(curation.get_curation(self.database, "generated-0001")["rating"], 5)
        self.assertEqual(selection.selectedIndexes(), [])
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        self.assertIsNone(self.window._selected_asset())
        self.assertIsNone(self.window._pending_bulk_restore)
        self.assertFalse(self.window.curation_button.isEnabled())
        self.assertNotIn("generated-0000", self.window.detail.toPlainText())
        editor.close()

    def test_rapid_bulk_writes_carry_selection_through_pending_restores(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        editor = self.window.edit_bulk_curation()
        self.assertEqual([target.asset_id for target in editor.targets],
                         ["generated-0000", "generated-0001"])
        initial_revisions = tuple(target.revision for target in editor.targets)
        original_rank = model.request_rank
        held = []
        def delay_first_two_restores(asset_id, callback):
            if len(held) < 2:
                held.append((asset_id, callback))
            else:
                original_rank(asset_id, callback)
        with patch.object(model, "request_rank", side_effect=delay_first_two_restores):
            editor.preview()
            self.until(lambda: editor.apply_button.isEnabled() and
                       editor.plan is not None and editor.plan.changed_count == 0)
            editor.apply()
            self.until(lambda: "No changes" in editor.feedback.text() and
                       model._actionable and len(held) == 1)
            self.assertEqual(selection.selectedIndexes(), [])
            self.assertEqual(tuple(target.revision for target in curation.capture_curation(
                self.database, ("generated-0000", "generated-0001"))), initial_revisions)

            editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
            editor.preview()
            self.until(lambda: editor.apply_button.isEnabled() and
                       editor.plan is not None and editor.plan.changed_count == 2)
            failures = []
            def fail_once(*_args, **_kwargs):
                failures.append("failed-dispatch")
                raise sqlite3.OperationalError("generated bulk failure before commit")
            with patch.object(curation, "apply_curation_batch", side_effect=fail_once):
                editor.apply()
                self.until(lambda: "outcome requires reload" in editor.feedback.text() and
                           model._actionable and len(held) == 2)
            self.assertEqual(failures, ["failed-dispatch"])
            self.assertEqual(selection.selectedIndexes(), [])
            self.assertEqual(tuple(target.revision for target in curation.capture_curation(
                self.database, ("generated-0000", "generated-0001"))), initial_revisions)

            editor.preview()
            self.until(lambda: editor.apply_button.isEnabled() and
                       editor.plan is not None and editor.plan.changed_count == 2)
            editor.apply()
            self.until(lambda: editor.feedback.text().startswith("Group saved to catalog") and
                       model._actionable and
                       {model.loaded_asset_at(index.row())["asset_id"]
                        for index in selection.selectedIndexes()} ==
                       {"generated-0000", "generated-0001"})
            for _asset_id, callback in held:
                callback(0, "")
            self.app.processEvents()
        self.assertEqual({model.loaded_asset_at(index.row())["asset_id"]
                          for index in selection.selectedIndexes()},
                         {"generated-0000", "generated-0001"})
        self.assertEqual(curation.get_curation(self.database, "generated-0000")["rating"], 5)
        self.assertEqual(curation.get_curation(self.database, "generated-0001")["rating"], 5)
        self.assertEqual(tuple(target.revision for target in curation.capture_curation(
            self.database, ("generated-0000", "generated-0001"))),
            tuple(revision + 1 for revision in initial_revisions))
        self.assertEqual(len(curation.list_curation_batches(self.database)), 1)
        editor.close()

    def test_catalog_replacement_during_bulk_rank_restore_releases_old_intent(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        editor = self.window.edit_bulk_curation()
        held = []
        with patch.object(model, "request_rank",
                          side_effect=lambda asset_id, callback: held.append((asset_id, callback))):
            editor.preview()
            self.until(lambda: editor.apply_button.isEnabled() and
                       editor.plan is not None and editor.plan.changed_count == 0)
            editor.apply()
            self.until(lambda: model._actionable and len(held) == 1 and
                       self.window._bulk_restore_intent is not None)
            # B2a gateway tests exercise actual file replacement. Deliver the
            # same typed invalidation here while rank completion is withheld.
            model._invalidate_changed_view("catalog_replaced", "Catalog file replaced")
            self.until(lambda: not model._actionable and
                       self.window._bulk_restore_intent is None)
            held[0][1](0, "")
            self.app.processEvents()
        self.assertIsNone(self.window._pending_bulk_restore)
        self.assertEqual(selection.selectedIndexes(), [])
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        self.assertIsNone(self.window._selected_asset())
        self.assertFalse(self.window.curation_button.isEnabled())
        editor.close()

    def test_explicit_clear_on_blank_gallery_cancels_pending_bulk_restore(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        selection = self.window.gallery.selectionModel()
        for row in (0, 1):
            selection.select(model.index(row), QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(model.index(0), QItemSelectionModel.SelectionFlag.NoUpdate)
        editor = self.window.edit_bulk_curation()
        held = []
        with patch.object(model, "request_rank",
                          side_effect=lambda asset_id, callback: held.append((asset_id, callback))):
            editor.preview()
            self.until(lambda: editor.apply_button.isEnabled() and
                       editor.plan is not None and editor.plan.changed_count == 0)
            editor.apply()
            self.until(lambda: model._actionable and len(held) == 1 and
                       self.window._bulk_restore_intent is not None)
            self.assertEqual(selection.selectedIndexes(), [])
            self.assertFalse(selection.currentIndex().isValid())
            epoch = self.window._selection_epoch
            selection.clear()  # Explicit user intent even though Qt is already blank.
            self.assertGreater(self.window._selection_epoch, epoch)
            self.assertIsNone(self.window._pending_bulk_restore)
            self.assertIsNone(self.window._bulk_restore_intent)
            held[0][1](0, "")
            self.app.processEvents()
        self.assertEqual(selection.selectedIndexes(), [])
        self.assertFalse(selection.currentIndex().isValid())
        self.assertIsNone(self.window._selected_asset())
        self.assertFalse(self.window.curation_button.isEnabled())
        self.assertFalse(self.window.bulk_curation_button.isEnabled())
        editor.close()

    def test_worker_core_stale_neighbor_refuses_rival_reorder(self):
        self.until(lambda: self.window.model._actionable)
        ids = [f"generated-{number:04}" for number in range(3)]
        collection_id = collection_api.create_collection(self.database, "Generated rivals")["collection_id"]
        for asset_id in ids:
            collection_api.add_member(self.database, collection_id, asset_id)
        self.window.refresh_collections()
        self.until(lambda: any(record["collection_id"] == collection_id
                               for record in self.window.collection_records))
        self.window.collection_box.setCurrentIndex(self.window.collection_box.findData(collection_id))
        self.until(lambda: self.window.model._actionable and
                   self.window.model._collection_id == collection_id and
                   self.window.model.rowCount() == 3)
        self.window.gallery.setCurrentIndex(self.window.model.index(1))
        self.until(lambda: self.window._loaded_focused_asset() is not None and
                   self.window._loaded_focused_asset()["asset_id"] == ids[1])
        original = collection_api.move_member
        called = threading.Event()
        def rival(*args, **kwargs):
            called.set()
            collection_api.reorder_members(self.database, collection_id,
                                           [ids[0], ids[2], ids[1]])
            return original(*args, **kwargs)
        with patch.object(collection_api, "move_member", side_effect=rival):
            self.window._move_collection_member(-1)
            self.until(lambda: called.is_set() and not self.window._mutation_pending and
                       "stale captured neighbor" in self.window.collection_feedback.text())
        self.assertEqual(collection_api.list_members(self.database, collection_id),
                         [ids[0], ids[2], ids[1]])
        self.assertNotEqual(self.window.collection_feedback.text(), "Collection saved.")

    def test_empty_collection_create_and_delete_reconcile_base_once(self):
        self.window.close()
        self.until(lambda: self.window.catalog_client.gateway.close_complete)
        empty = Path(self.temp.name) / "empty-collections.sqlite3"
        initialize(empty)
        self.window = GalleryWindow(empty, enable_thumbnails=False,
                                    private_root=Path(self.temp.name) / "private-empty")
        self.window.show()
        self.until(lambda: self.window.model._actionable and
                   self.window.model.rowCount() == 0)
        published = []
        self.window.model.generationPublished.connect(published.append)
        with patch("prototypes.qt.app.QInputDialog.getText", return_value=("New empty", True)):
            self.window.create_collection_button.click()
        self.until(lambda: bool(collection_api.list_collections(empty)) and
                   self.window.model._actionable and
                   self.window.collection_box.currentData() is not None)
        identifier = collection_api.list_collections(empty)[0]["collection_id"]
        self.assertEqual(self.window.collection_box.currentData(), identifier)
        self.assertEqual(self.window.model._collection_id, identifier)
        self.assertEqual(len(published), 1)
        self.assertTrue(self.window.rename_collection_button.isEnabled())
        self.assertTrue(self.window.delete_collection_button.isEnabled())
        published.clear()
        with patch("prototypes.qt.app.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_collection_button.click()
        self.until(lambda: not collection_api.list_collections(empty) and
                   self.window.model._actionable and
                   self.window.collection_box.currentData() is None)
        self.assertIsNone(self.window.model._collection_id)
        self.assertEqual(len(published), 1)
        self.assertFalse(self.window.rename_collection_button.isEnabled())
        self.assertFalse(self.window.delete_collection_button.isEnabled())

    def test_late_collection_list_preserves_later_choice_and_captured_delete(self):
        self.until(lambda: self.window.model._actionable)
        first = collection_api.create_collection(self.database, "First")
        second = collection_api.create_collection(self.database, "Second")
        first_id, second_id = first["collection_id"], second["collection_id"]
        self.window.refresh_collections()
        self.until(lambda: len(self.window.collection_records) == 2)
        self.window.collection_box.setCurrentIndex(self.window.collection_box.findData(first_id))
        self.until(lambda: self.window.model._actionable and
                   self.window.model._collection_id == first_id)
        entered, release = threading.Event(), threading.Event()
        original = collection_api.list_collections
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)
        try:
            with patch.object(collection_api, "list_collections", side_effect=delayed):
                self.window.refresh_collections()
                self.until(entered.is_set)
                self.window.collection_box.setCurrentIndex(
                    self.window.collection_box.findData(second_id))
                self.assertEqual(self.window.collection_box.currentData(), second_id)
                release.set()
                self.until(lambda: self.window.model._actionable and
                           self.window.model._collection_id == second_id and
                           self.window.collection_box.currentData() == second_id)
        finally:
            release.set()
        self.window.collection_box.setCurrentIndex(self.window.collection_box.findData(first_id))
        self.until(lambda: self.window.model._actionable and
                   self.window.model._collection_id == first_id)
        def switch_before_confirm(*_args):
            self.window.collection_box.setCurrentIndex(
                self.window.collection_box.findData(second_id))
            return QMessageBox.StandardButton.Yes
        with patch("prototypes.qt.app.QMessageBox.question", side_effect=switch_before_confirm):
            self.window._delete_collection()
        self.until(lambda: self.window.model._actionable and
                   self.window.model._collection_id == second_id and
                   {record["collection_id"] for record in self.window.collection_records} == {second_id})
        self.assertEqual(self.window.collection_box.currentData(), second_id)
        self.assertEqual([record["collection_id"] for record in
                          collection_api.list_collections(self.database)], [second_id])

    def test_pending_apply_disables_row_actions_and_programmatic_review(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        self.assertTrue(self.window.curation_button.isEnabled())
        model.set_filter("reviewed")
        self.assertFalse(model._actionable)
        self.assertFalse(self.window.curation_button.isEnabled())
        self.assertFalse(self.window.curate_button.isEnabled())
        self.assertFalse(self.window.metadata_button.isEnabled())
        self.assertIsNone(self.window._selected_asset())
        self.window.set_selected_state("ignored")
        self.assertFalse(self.window._mutation_pending)
        self.until(lambda: model._actionable)
        with connect(self.database) as db:
            state = db.execute("SELECT workflow_state FROM assets WHERE asset_id='generated-0000'").fetchone()[0]
        self.assertEqual(state, "new")

    def test_delayed_page_cannot_restore_focus_after_filter_supersedes(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        entered, release = threading.Event(), threading.Event()
        original = gallery_operations.later_page
        def delayed(*args):
            entered.set()
            release.wait(2)
            return original(*args)
        try:
            with patch.object(gallery_operations, "later_page", delayed):
                self.window._restore_asset_selection("generated-0299")
                self.until(entered.is_set)
                self.window.model.set_filter("reviewed")
                expected_generation = self.window.model._generation
                release.set()
                self.until(lambda: self.window.model._actionable and
                           self.window.model._generation == expected_generation)
                self.assertEqual(self.window.model.rowCount(), 0)
                self.app.processEvents()
                self.assertFalse(self.window.gallery.currentIndex().isValid())
                self.assertIsNone(self.window._pending_restore)
        finally:
            release.set()

    def test_selection_change_without_focus_change_cancels_rank_restore(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        entered, release = threading.Event(), threading.Event()
        original = gallery_operations.rank_for_asset
        def delayed(*args):
            entered.set()
            release.wait(2)
            return original(*args)
        try:
            with patch.object(gallery_operations, "rank_for_asset", delayed):
                self.window._restore_asset_selection("generated-0299")
                self.until(entered.is_set)
                current = self.window.gallery.currentIndex()
                before_epoch = self.window._selection_epoch
                self.window.gallery.selectionModel().select(
                    model.index(1), QItemSelectionModel.SelectionFlag.Select)
                self.assertEqual(self.window.gallery.currentIndex(), current)
                self.assertGreater(self.window._selection_epoch, before_epoch)
                release.set()
                self.until(lambda: self.window.catalog_client.gateway.pending_count == 0)
                self.app.processEvents()
                self.assertEqual(self.window.gallery.currentIndex(), current)
                self.assertNotIn(1, model._pending_pages)
        finally:
            release.set()

    def test_model_resets_preserve_user_selection_epoch(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.setCurrentIndex(model.index(0))
        captured_epoch = self.window._selection_epoch
        model.invalidate_for_mutation()
        self.assertEqual(self.window._selection_epoch, captured_epoch)
        self.assertFalse(self.window.gallery.currentIndex().isValid())
        model.refresh()
        generation = model._generation
        self.until(lambda: model._actionable and model._generation == generation)
        self.assertEqual(self.window._selection_epoch, captured_epoch)
        self.window.gallery.setCurrentIndex(model.index(1))
        self.assertGreater(self.window._selection_epoch, captured_epoch)

    def test_detail_loading_disables_single_openers_but_not_review_digit(self):
        from prototypes.qt import gallery_operations
        self.until(lambda: self.window.model._actionable)
        entered, release = threading.Event(), threading.Event()
        original = gallery_operations.detail_for_asset
        def delayed(*args):
            entered.set()
            release.wait(2)
            return original(*args)
        try:
            with patch.object(gallery_operations, "detail_for_asset", delayed):
                self.window.gallery.setCurrentIndex(self.window.model.index(0))
                self.until(entered.is_set)
                self.assertFalse(self.window.inspect_button.isEnabled())
                self.assertFalse(self.window.cached_button.isEnabled())
                self.assertFalse(self.window.curation_button.isEnabled())
                self.assertFalse(self.window.metadata_button.isEnabled())
                self.assertIsNone(self.window.inspect_selected())
                self.assertIsNone(self.window.edit_curation())
                self.assertFalse(self.window._mutation_pending)
                self.window.set_selected_state("reviewed")
                self.assertTrue(self.window._mutation_pending)
                release.set()
                self.until(lambda: self.window.model._actionable and
                           not self.window._mutation_pending and
                           self.window.model.asset_at(0)["workflow_state"] == "reviewed")
        finally:
            release.set()

    def test_external_commit_invalidates_whole_view_before_page_delivery(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        stale_checks = []
        def checked(actionable):
            if not actionable:
                try:
                    model.asset_at(0)
                except (ValueError, IndexError):
                    stale_checks.append(True)
                else:
                    stale_checks.append(False)
        model.actionabilityChanged.connect(checked)
        old_generation = model._generation
        with connect(self.database) as db:
            db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id='generated-0000'")
        model.request_page(1)
        self.until(lambda: model._generation > old_generation and model._actionable)
        self.assertTrue(stale_checks and all(stale_checks))
        self.assertEqual(model.asset_at(0)["workflow_state"], "reviewed")
        self.assertEqual(model._token.generation, model._generation)
        old_generation = model._generation
        with connect(self.database) as db:
            db.execute("UPDATE assets SET workflow_state='organized' WHERE asset_id='generated-0000'")
        rank_results = []
        model.request_rank("generated-0299", lambda row, error: rank_results.append((row, error)))
        self.until(lambda: model._generation > old_generation and model._actionable)
        self.assertTrue(rank_results and rank_results[0][1])
        self.assertEqual(model.asset_at(0)["workflow_state"], "organized")
        old_generation = model._generation
        with connect(self.database) as db:
            db.execute("UPDATE assets SET workflow_state='ignored' WHERE asset_id='generated-0000'")
        details = []
        model.request_detail(model.asset_at(0), lambda value, error: details.append((value, error)))
        self.until(lambda: model._generation > old_generation and model._actionable)
        self.assertTrue(details and details[0][1])
        self.assertEqual(model.asset_at(0)["workflow_state"], "ignored")

    def test_lru_eviction_allows_same_token_page_zero_revisit(self):
        self.until(lambda: self.window.model._actionable)
        with connect(self.database) as db:
            for number in range(6_400):
                db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                           "VALUES(?,?,?,?,?)",
                           (f"eviction-{number:04}", str(Path(self.temp.name) / f"evict-{number:04}.png"),
                            "image/png", f"eviction-digest-{number:04}", 1))
        model = self.window.model
        model.refresh()
        generation = model._generation
        self.until(lambda: model._actionable and model._generation == generation and
                   model.rowCount() == 6_700)
        token = model._token
        first_id = model.asset_at(0)["asset_id"]
        # Keep the view from repainting page zero while the model's LRU is
        # exercised; a visible viewport legitimately re-requests that page.
        self.window.gallery.hide()
        for page in range(1, 26):
            model.request_page(page)
            self.until(lambda page=page: page in model._cache)
            self.assertLessEqual(len(model._cache), model.max_cached_pages)
        self.assertFalse(0 in model._cache)
        self.assertIsNone(model.loaded_asset_at(0))
        self.until(lambda: 0 in model._cache)
        self.assertEqual(model.asset_at(0)["asset_id"], first_id)
        self.assertEqual(model._token, token)
        self.assertLessEqual(len(model._cache), model.max_cached_pages)

    def test_scrolling_3650_assets_recovers_displaced_pages(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.hide()
        with connect(self.database) as db:
            db.executemany("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                           "VALUES(?,?,?,?,?)",
                           [(f"generated-{number:04}", str(Path(self.temp.name) / f"{number:04}.png"),
                             "image/png", f"digest-{number:04}", 1) for number in range(300, 3650)])
        model.refresh()
        self.until(lambda: model._actionable and model.rowCount() == 3650)
        entered, release = threading.Event(), threading.Event()
        original = gallery_operations.later_page
        failures, displaced = [], []
        model.loadFailed.connect(failures.append)
        self.window.catalog_client.gateway.completed.connect(
            lambda reply: displaced.append(reply) if reply.status == "superseded" else None)
        def held(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Generated page was not released")
            return original(*args)
        try:
            with patch.object(gallery_operations, "later_page", held):
                model.request_page(1)
                self.until(entered.is_set)
                for page in range(2, 15):
                    model.request_page(page)
                self.until(lambda: len(displaced) == 11)
                release.set()
                self.until(lambda: not model._pending_pages)
        finally:
            release.set()
        self.assertEqual(model._failed_pages, {})
        self.assertEqual(failures, [])
        # Repaint actual viewports near the end, at a displaced page, and back.
        self.window.gallery.show()
        self.window.gallery.doItemsLayout()
        self.until(lambda: self.window.gallery.visualRect(model.index(3649)).isValid())
        # Displace the page under a stationary viewport. Its retry must come
        # from the view's normal response to dataChanged, without a test read,
        # repaint request, or another scroll after the displacement.
        model._cache.pop(1, None)
        entered.clear()
        release.clear()
        try:
            with patch.object(gallery_operations, "later_page", held):
                model.request_page(2)
                self.until(entered.is_set)
                self.window.gallery.scrollTo(model.index(299))
                self.until(lambda: 1 in model._pending_pages)
                before = len(displaced)
                model.request_page(3)
                model.request_page(4)
                self.until(lambda: len(displaced) > before)
                release.set()
                self.until(lambda: 1 in model._cache and not model._pending_pages)
        finally:
            release.set()
        self.assertLess(len(displaced), 20, "Visible-page retry must settle without eviction churn")
        for row in (3500, 1200, 3649, 299):
            self.window.gallery.scrollTo(model.index(row))
            self.window.gallery.viewport().update()
            self.until(lambda row=row: row // model.page_size in model._cache)
            self.assertEqual(model.data(model.index(row), model.AssetRole)["asset_id"],
                             f"generated-{row:04}")
            self.assertNotIn("Loading catalog page", model.data(model.index(row)))
        self.assertEqual(model._failed_pages, {})
        self.assertEqual(failures, [])

    def test_page_queue_replacement_is_retryable_without_failure_or_retry_loop(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        self.window.gallery.hide()
        saved_client = model.catalog_client
        callbacks, failures = [], []
        model.loadFailed.connect(failures.append)
        class CapturingClient:
            def submit(self, _category, _operation, _args, **kwargs):
                callbacks.append(kwargs["callback"])
                return len(callbacks), ""
        try:
            model.catalog_client = CapturingClient()
            for status in ("superseded", "cancelled"):
                model.request_page(1)
                count = len(callbacks)
                callbacks[-1](CatalogReply(count, RequestClass.PAGE, model._generation,
                                           status, message="Newer catalog request replaced it"))
                self.app.processEvents()
                self.assertEqual(len(callbacks), count)
                self.assertNotIn(1, model._pending_pages)
                self.assertNotIn(1, model._failed_pages)
            self.assertEqual(failures, [])
        finally:
            model.catalog_client = saved_client
        # A real viewport read can now fetch the previously displaced page.
        self.assertIsNone(model.loaded_asset_at(299))
        self.until(lambda: model.loaded_asset_at(299) is not None)
        self.assertEqual(model.loaded_asset_at(299)["asset_id"], "generated-0299")

    def test_old_page_reply_cannot_clear_new_pending_key_or_retry_malformed_reply(self):
        self.until(lambda: self.window.model._actionable)
        model = self.window.model
        saved_client = model.catalog_client
        saved_generation, saved_token = model._generation, model._token
        callbacks = []
        class CapturingClient:
            def submit(self, _category, _operation, _args, **kwargs):
                callbacks.append(kwargs["callback"])
                return len(callbacks), ""
        try:
            model.catalog_client = CapturingClient()
            model.request_page(1)
            self.assertEqual(len(callbacks), 1)
            model._generation += 1
            model._token = replace(saved_token, generation=model._generation)
            model._pending_pages.clear()
            model.request_page(1)
            self.assertEqual(len(callbacks), 2)
            callbacks[0](CatalogReply(1, RequestClass.PAGE, saved_generation, "cancelled"))
            self.assertIn(1, model._pending_pages)
            callbacks[1](CatalogReply(2, RequestClass.PAGE, model._generation, "ok",
                                      GalleryPage(model._token, 2, ())))
            self.assertNotIn(1, model._pending_pages)
            self.assertIn(1, model._failed_pages)
            model.loaded_asset_at(299)
            self.assertEqual(len(callbacks), 2)
        finally:
            model.catalog_client = saved_client
            model._generation = saved_generation
            model._token = saved_token
            model._pending_pages.clear()
            model._failed_pages.clear()

    def test_file_replacement_refuses_captured_review_before_core_dispatch(self):
        self.until(lambda: self.window.model._actionable)
        self.window.gallery.setCurrentIndex(self.window.model.index(0))
        self.until(lambda: self.window._selected_asset() is not None)
        replacement = Path(self.temp.name) / "replacement.sqlite3"
        initialize(replacement)
        with connect(replacement) as db:
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                       "VALUES('replacement-only','/replacement.png','image/png','digest',0)")
        try:
            os.replace(replacement, self.database)
        except OSError as exc:
            self.skipTest(f"Atomic replacement unavailable: {exc}")
        self.window.set_selected_state("reviewed")
        self.until(lambda: not self.window._mutation_pending and
                   "reopen library" in self.window.statusBar().currentMessage())
        self.assertFalse(self.window.model._actionable)
        self.assertIsNone(self.window._selected_asset())
        with connect(self.database) as db:
            state = db.execute("SELECT workflow_state FROM assets WHERE asset_id='replacement-only'").fetchone()[0]
        self.assertEqual(state, "new")

    def test_root_validation_refusal_disables_all_catalog_controls(self):
        # The worker's registered startup validator is not allowed to publish
        # an actionable gallery or enabled controls after containment failure.
        from prototypes.qt import gallery_operations
        self.window.close()
        self.until(lambda: self.window.catalog_client.gateway.close_complete)
        with (patch.object(gallery_operations.source_api, "list_sources",
                           return_value=[{"root_path": str(self.temp.name),
                                          "source_id": "generated-invalid", "name": "Invalid",
                                          "health": "healthy", "health_detail": "",
                                          "existing_file_policy": "inbox"}]),
              patch.object(gallery_operations, "assert_outside_sources",
                           side_effect=ValueError("generated invalid source root"))):
            self.window = GalleryWindow(self.database, enable_thumbnails=False,
                                        private_root=Path(self.temp.name) / "private")
            self.window.show()
            self.until(lambda: "generated invalid source root" in
                       self.window.statusBar().currentMessage())
            self.assertFalse(self.window.centralWidget().isEnabled())
            self.assertFalse(self.window.model._actionable)
            self.assertEqual(self.window.model.rowCount(), 0)
            self.assertIn("generated invalid source root", self.window.statusBar().currentMessage())

    def test_held_startup_validation_publishes_scan_sources_and_collections(self):
        # The initial Apply has higher gateway priority than legacy reads.  A
        # source/collection list queued before it could be cancelled forever.
        from prototypes.qt import gallery_operations
        self.window.close()
        self.until(lambda: self.window.catalog_client.gateway.close_complete)
        root = Path(self.temp.name) / "registered-source"
        root.mkdir()
        with connect(self.database) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                       "VALUES('startup-source','Startup Source',?,'inbox')", (str(root),))
        collection_id = collection_api.create_collection(
            self.database, "Startup collection")["collection_id"]
        entered = threading.Event()
        release = threading.Event()
        original_list = gallery_operations.source_api.list_sources

        def held_list(database):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Held startup validation was not released")
            return original_list(database)

        try:
            with patch.object(gallery_operations.source_api, "list_sources",
                              side_effect=held_list):
                self.window = GalleryWindow(
                    self.database, enable_thumbnails=False,
                    private_root=Path(self.temp.name) / "private")
                self.window.show()
                self.until(entered.is_set)
                self.assertFalse(self.window.model._actionable)
                self.assertEqual(self.window.source_box.count(), 0)
                self.assertEqual(self.window.collection_box.count(), 0)
                release.set()
                self.until(lambda: self.window.model._actionable and
                           self.window.source_box.findData("startup-source") >= 0 and
                           self.window.collection_box.findData(collection_id) >= 0)
                self.assertEqual(self.window.source_box.count(), 2)
                self.assertEqual(self.window.collection_box.count(), 2)
                self.assertIsNone(self.window.source_box.currentData())
                self.assertIsNone(self.window.collection_box.currentData())
                self.assertEqual(self.window.model.rowCount(), 300)
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
