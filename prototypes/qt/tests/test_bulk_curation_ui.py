"""Generated offscreen outcomes for captured multi-selection, preview and whole-group undo."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, curation as api
from prototypes.qt.app import BulkCurationDialog, GalleryWindow


class BulkCurationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'generated.sqlite3'
        catalog.initialize(self.db)
        with catalog.connect(self.db) as db:
            for identifier, rating, favorite in [('alpha', None, 0), ('beta', 4, 1), ('gamma', 2, 0)]:
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,rating,favorite) '
                           'VALUES(?,?,?,?,?,?,?)', (identifier, f'/generated/{identifier}.png', 'image/png', 'hash', 1, rating, favorite))
        self.window = GalleryWindow(self.db)
        self.addCleanup(self.window.close)
        self.window.show()
        self.app.processEvents()

    def select(self, *ids):
        selection = self.window.gallery.selectionModel()
        selection.clear()
        for identifier in ids:
            index = self.window.model.index(self.window.model.row_for_asset(identifier))
            selection.select(index, QItemSelectionModel.SelectionFlag.Select)
        selection.setCurrentIndex(self.window.model.index(self.window.model.row_for_asset(ids[0])),
                                  QItemSelectionModel.SelectionFlag.NoUpdate)

    def selected_ids(self):
        return [self.window.model.asset_at(index.row())['asset_id'] for index in self.window.gallery.selectionModel().selectedIndexes()]

    def test_keyboard_multiselection_captured_ids_control_invalidation_and_selection_filter_drift(self):
        self.select('alpha')
        gallery = self.window.gallery
        gallery.setFocus()
        self.app.processEvents()
        QTest.keyClick(gallery, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(gallery, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(set(self.selected_ids()), {'alpha', 'beta'})
        self.assertIn('2 selected', self.window.selection_label.text())
        editor = self.window.edit_bulk_curation()
        self.assertEqual([target.asset_id for target in editor.targets], ['alpha', 'beta'])
        with self.assertRaises(AttributeError): editor.targets = ()
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview_button.setFocus()
        QTest.keyClick(editor.preview_button, Qt.Key.Key_Space)
        self.assertTrue(editor.apply_button.isEnabled())
        self.assertIn('2 changed', editor.effects.toPlainText())
        editor.favorite_box.setCurrentIndex(editor.favorite_box.findData(False))
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertEqual(editor.effects.toPlainText(), '')
        editor.preview()
        self.select('gamma')
        self.window.model.set_metadata_filters(search='gamma')
        self.assertEqual(self.selected_ids(), [])
        self.assertEqual([target.asset_id for target in editor.targets], ['alpha', 'beta'])
        editor.apply()
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], 5)
        self.assertEqual(api.get_curation(self.db, 'beta')['rating'], 5)
        self.assertEqual(api.get_curation(self.db, 'gamma')['rating'], 2)
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertIn('Applied preview', editor.effects.toPlainText())

    def test_displayed_revision_is_captured_and_explicit_reload_keeps_ids_choices(self):
        self.select('alpha', 'beta')
        with catalog.connect(self.db) as db: db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id='beta'")
        editor = self.window.edit_bulk_curation()
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(3))
        editor.preview()
        self.assertIn('changed since capture', editor.feedback.text())
        self.assertIsNone(editor.plan)
        self.select('gamma')
        editor.reload()
        self.assertEqual([target.asset_id for target in editor.targets], ['alpha', 'beta'])
        self.assertEqual(editor.rating_box.currentData(), 3)
        self.assertFalse(editor.apply_button.isEnabled())
        editor.preview()
        editor.apply()
        self.assertEqual(api.get_curation(self.db, 'beta')['rating'], 3)
        self.assertEqual(self.window._selected_asset()['asset_id'], 'gamma')

    def test_conflict_between_preview_and_apply_clears_stale_effects_and_writes_nothing(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        with catalog.connect(self.db) as db: db.execute("UPDATE assets SET sha256='changed' WHERE asset_id='beta'")
        editor.apply()
        self.assertIn('Entire group was not applied', editor.feedback.text())
        self.assertEqual(editor.effects.toPlainText(), '')
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], None)
        self.assertEqual(api.list_curation_batches(self.db), [])

    def test_reopen_history_without_selection_exact_group_undo_and_single_dialog_exclusion(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.favorite_box.setCurrentIndex(editor.favorite_box.findData(True))
        editor.preview()
        editor.apply()
        batch_id = editor.group_box.currentData()
        editor.close()
        self.window.gallery.selectionModel().clear()
        reopened = self.window.open_curation_history()
        self.assertTrue(reopened.history_only)
        self.assertEqual(reopened.targets, ())
        self.assertEqual(reopened.undo_batch_id, batch_id)
        self.assertIn('alpha', reopened.group_effects.toPlainText())
        self.assertIn('beta', reopened.group_effects.toPlainText())
        single = self.window.edit_curation()  # no focused asset after explicit clear.
        self.assertIsNone(single)
        self.select('gamma')
        reopened.undo_group()
        self.assertEqual(api.get_curation(self.db, 'alpha')['favorite'], False)
        self.assertEqual(api.get_curation(self.db, 'beta')['favorite'], True)
        self.assertEqual(self.window._selected_asset()['asset_id'], 'gamma')
        self.assertFalse(reopened.undo_button.isEnabled())
        self.assertIn('Entire displayed group undone', reopened.feedback.text())
        self.select('alpha')
        single = self.window.edit_curation()
        self.assertFalse(single.undo_button.isEnabled())
        self.assertEqual(api.list_curation_edits(self.db, 'alpha'), [])

    def test_exact_history_group_unchanged_member_single_undo_invalidates_group(self):
        single = api.set_curation(self.db, 'beta', rating=4, favorite=False, expected_revision=0)
        first = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('alpha', 'beta')), api.CurationChanges(rating=4)))
        second = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('gamma',)), api.CurationChanges(rating=5)))
        editor = self.window.open_curation_history()
        editor.group_box.setCurrentIndex(editor.group_box.findData(first['batch_id']))
        self.assertEqual(editor.undo_batch_id, first['batch_id'])
        self.assertNotIn('ID: gamma', editor.group_effects.toPlainText())
        api.undo_curation(self.db, single['edit_id'])
        editor.undo_group()
        self.assertIn('Undo refused', editor.feedback.text())
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], 4)
        self.assertEqual(api.get_curation(self.db, 'gamma')['rating'], 5)
        editor.group_box.setCurrentIndex(editor.group_box.findData(second['batch_id']))
        editor.undo_group()
        self.assertEqual(api.get_curation(self.db, 'gamma')['rating'], 2)

    def test_history_keyboard_focus_group_choice_and_explicit_whole_group_undo(self):
        group = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('alpha', 'beta')), api.CurationChanges(rating=5)))
        editor = self.window.open_curation_history()
        editor.activateWindow()
        self.app.processEvents()
        self.assertIs(editor.focusWidget(), editor.group_box)
        QTest.keyClick(editor.group_box, Qt.Key.Key_Home)
        self.assertIsNone(editor.undo_batch_id)
        QTest.keyClick(editor.group_box, Qt.Key.Key_End)
        self.assertEqual(editor.undo_batch_id, group['batch_id'])
        for _ in range(3):
            if editor.focusWidget() is editor.undo_button:
                break
            QTest.keyClick(editor.focusWidget(), Qt.Key.Key_Tab)
        self.assertIs(editor.focusWidget(), editor.undo_button)
        QTest.keyClick(editor.undo_button, Qt.Key.Key_Space)
        self.assertTrue(api.get_curation_batch(self.db, group['batch_id'])['undone'])
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], None)
        self.assertEqual(api.get_curation(self.db, 'beta')['rating'], 4)

    def test_large_selection_is_rejected_before_materializing_and_max_dialog_remains_bounded(self):
        with catalog.connect(self.db) as db:
            for index in range(257):
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) VALUES(?,?,?,?,?)',
                           (f'bounded-{index}', f'/generated/bounded-{index}.png', 'image/png', 'hash', 1))
        self.window.model.refresh()
        self.window.gallery.selectionModel().select(QItemSelection(self.window.model.index(0), self.window.model.index(256)),
                                                     QItemSelectionModel.SelectionFlag.Select)
        with patch.object(self.window.gallery.selectionModel(), 'selectedIndexes', side_effect=AssertionError('overbound materialization')):
            self.assertIsNone(self.window.edit_bulk_curation())
        self.assertIn('between 1 and 256', self.window.selection_label.text())
        targets = api.capture_curation(self.db, tuple(f'bounded-{index}' for index in range(256)))
        editor = BulkCurationDialog(self.db, targets)
        self.addCleanup(editor.close)
        editor.show()
        self.app.processEvents()
        self.assertLessEqual(editor.target_list.height(), 90)
        self.assertLessEqual(editor.height(), 900)
        self.assertTrue(editor.preview_button.isVisible())
        self.assertTrue(editor.undo_button.isVisible())
        editor.preview_button.setFocus()
        QTest.keyClick(editor.preview_button, Qt.Key.Key_Space)
        self.assertIn('256 targets', editor.effects.toPlainText())

    def test_noop_and_storage_failure_are_truthful_preserve_controls_and_stable_selection(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.preview()
        editor.apply()
        self.assertIn('No changes', editor.feedback.text())
        self.assertIn('Completed without changes', editor.effects.toPlainText())
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        with patch('prototypes.qt.app.curation.apply_curation_batch', side_effect=sqlite3.OperationalError('generated locked')):
            editor.apply()
        self.assertIn('locked', editor.feedback.text())
        self.assertEqual(editor.rating_box.currentData(), 5)
        editor.preview()
        editor.apply()
        self.assertEqual(set(self.selected_ids()), {'alpha', 'beta'})
        self.assertEqual(self.window._selected_asset()['asset_id'], 'alpha')


if __name__ == '__main__':
    unittest.main()
