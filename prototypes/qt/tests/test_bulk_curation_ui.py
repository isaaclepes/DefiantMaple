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
from prototypes.qt.tests.gallery_wait import (
    close_windows_and_cleanup,
    wait_for_asset_at,
    wait_for_generation_after,
    wait_for_gateway_condition,
    wait_for_initial_generation,
    wait_for_page,
    wait_for_rank,
    wait_for_selected_asset,
    wait_for_startup_validation,
)


class BulkCurationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.windows = []
        self.addCleanup(lambda: close_windows_and_cleanup(self.windows, self.app, self.root))
        self.db = self.root / 'generated.sqlite3'
        catalog.initialize(self.db)
        with catalog.connect(self.db) as db:
            for identifier, rating, favorite in [('alpha', None, 0), ('beta', 4, 1), ('gamma', 2, 0)]:
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,rating,favorite) '
                           'VALUES(?,?,?,?,?,?,?)', (identifier, f'/generated/{identifier}.png', 'image/png', 'hash', 1, rating, favorite))
        self.window = GalleryWindow(self.db)
        self.windows.append(self.window)
        wait_for_initial_generation(self.window, expected_count=3)
        wait_for_startup_validation(self.window)
        self.window.show()
        self.app.processEvents()

    def select(self, *ids):
        selection = self.window.gallery.selectionModel()
        selection.clear()
        for identifier in ids:
            row = wait_for_rank(self.window, identifier)
            wait_for_asset_at(self.window, row, identifier)
            index = self.window.model.index(row)
            selection.select(index, QItemSelectionModel.SelectionFlag.Select)
        first_row = wait_for_rank(self.window, ids[0])
        selection.setCurrentIndex(self.window.model.index(first_row),
                                  QItemSelectionModel.SelectionFlag.NoUpdate)

    def selected_ids(self):
        selected = self.window.gallery.selectionModel().selectedIndexes()
        for index in selected:
            wait_for_page(self.window, index.row() // self.window.model.page_size,
                          generation=self.window.model._generation)
        return [self.window.model.loaded_asset_at(index.row())['asset_id'] for index in selected]

    def open_history(self):
        self.window.open_curation_history()
        wait_for_gateway_condition(
            self.window,
            lambda: self.window.bulk_curation_dialog is not None
            and self.window.bulk_curation_dialog.history_only,
            description='asynchronously opened bulk history dialog',
        )
        return self.window.bulk_curation_dialog

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
        wait_for_gateway_condition(
            self.window,
            lambda: '2 changed' in editor.effects.toPlainText() and editor.apply_button.isEnabled(),
            description='keyboard bulk curation preview',
        )
        self.assertTrue(editor.apply_button.isEnabled())
        self.assertIn('2 changed', editor.effects.toPlainText())
        editor.favorite_box.setCurrentIndex(editor.favorite_box.findData(False))
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertEqual(editor.effects.toPlainText(), '')
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: '2 changed' in editor.effects.toPlainText() and editor.apply_button.isEnabled(),
            description='bulk preview for captured alpha and beta',
        )
        self.select('gamma')
        previous_generation = self.window.model._generation
        self.window.model.set_metadata_filters(search='gamma')
        wait_for_generation_after(self.window, previous_generation,
                                  expected_count=1, description='gamma search generation')
        self.assertEqual(self.selected_ids(), [])
        self.assertEqual([target.asset_id for target in editor.targets], ['alpha', 'beta'])
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: 'Applied preview' in editor.effects.toPlainText()
            and editor.feedback.text().startswith('Group saved to catalog'),
            description='bulk apply after gallery filter drift',
        )
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
        wait_for_gateway_condition(
            self.window,
            lambda: 'changed since capture' in editor.feedback.text() and editor.plan is None,
            description='stale captured bulk preview refusal',
        )
        self.assertIn('changed since capture', editor.feedback.text())
        self.assertIsNone(editor.plan)
        previous_generation = self.window.model._generation
        self.window.model.refresh()
        wait_for_generation_after(self.window, previous_generation,
                                  expected_count=3, description='refresh after deliberate external revision edit')
        self.select('gamma')
        editor.reload()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.feedback.text().startswith('Same captured IDs reloaded.'),
            description='bulk reload of captured IDs and revisions',
        )
        self.assertEqual([target.asset_id for target in editor.targets], ['alpha', 'beta'])
        self.assertEqual(editor.rating_box.currentData(), 3)
        self.assertFalse(editor.apply_button.isEnabled())
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '2 changed' in editor.effects.toPlainText(),
            description='bulk preview after explicit captured-ID reload',
        )
        previous_generation = self.window.model._generation
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: 'Applied preview' in editor.effects.toPlainText()
            and editor.feedback.text().startswith('Group saved to catalog'),
            description='bulk curation apply completion',
        )
        self.assertEqual(api.get_curation(self.db, 'beta')['rating'], 3)
        wait_for_generation_after(
            self.window,
            previous_generation,
            expected_count=3,
            description='explicitly reloaded bulk apply generation',
        )
        wait_for_selected_asset(self.window, 'gamma')
        self.assertEqual(self.window._selected_asset()['asset_id'], 'gamma')

    def test_conflict_between_preview_and_apply_clears_stale_effects_and_writes_nothing(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '2 changed' in editor.effects.toPlainText(),
            description='bulk preview before conflicting apply',
        )
        with catalog.connect(self.db) as db: db.execute("UPDATE assets SET sha256='changed' WHERE asset_id='beta'")
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: 'outcome requires reload' in editor.feedback.text()
            and editor.effects.toPlainText() == '' and not editor.apply_button.isEnabled(),
            description='conflicting bulk apply refusal',
        )
        self.assertIn('outcome requires reload', editor.feedback.text())
        self.assertNotIn('Group saved to catalog', editor.feedback.text())
        self.assertEqual(editor.effects.toPlainText(), '')
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], None)
        self.assertEqual(api.list_curation_batches(self.db), [])

    def test_reopen_history_without_selection_exact_group_undo_and_single_dialog_exclusion(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.favorite_box.setCurrentIndex(editor.favorite_box.findData(True))
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '1 changed' in editor.effects.toPlainText(),
            description='whole-group history preview',
        )
        previous_batch_ids = {row['batch_id'] for row in api.list_curation_batches(self.db)}
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.feedback.text().startswith('Group saved to catalog'),
            description='whole-group history batch saved',
        )
        new_batches = [row['batch_id'] for row in api.list_curation_batches(self.db)
                       if row['batch_id'] not in previous_batch_ids]
        self.assertEqual(len(new_batches), 1)
        batch_id = new_batches[0]
        self.assertIsNotNone(batch_id)
        wait_for_gateway_condition(
            self.window,
            lambda: editor.group_box.findData(batch_id) >= 0,
            description='exact newly saved history group published before closing editor',
        )
        self.assertEqual(editor.group_box.currentData(), batch_id)
        editor.close()
        self.window.gallery.selectionModel().clear()
        reopened = self.open_history()
        wait_for_gateway_condition(
            self.window,
            lambda: reopened.group_box.findData(batch_id) >= 0,
            description='saved curation group in reopened history',
        )
        reopened.group_box.setCurrentIndex(reopened.group_box.findData(batch_id))
        wait_for_gateway_condition(
            self.window,
            lambda: reopened.undo_batch_id == batch_id and reopened.undo_button.isEnabled(),
            description='loaded whole-group member details',
        )
        self.assertTrue(reopened.history_only)
        self.assertEqual(reopened.targets, ())
        self.assertEqual(reopened.undo_batch_id, batch_id)
        self.assertIn('alpha', reopened.group_effects.toPlainText())
        self.assertIn('beta', reopened.group_effects.toPlainText())
        single = self.window.edit_curation()  # no focused asset after explicit clear.
        self.assertIsNone(single)
        self.select('gamma')
        previous_generation = self.window.model._generation
        reopened.undo_group()
        wait_for_gateway_condition(
            self.window,
            lambda: reopened.feedback.text() == 'Entire displayed group undone in catalog.',
            description='whole-group undo completion',
        )
        self.assertEqual(api.get_curation(self.db, 'alpha')['favorite'], False)
        self.assertEqual(api.get_curation(self.db, 'beta')['favorite'], True)
        wait_for_generation_after(
            self.window,
            previous_generation,
            expected_count=3,
            description='whole-group undo gallery generation',
        )
        wait_for_selected_asset(self.window, 'gamma')
        self.assertEqual(self.window._selected_asset()['asset_id'], 'gamma')
        self.assertFalse(reopened.undo_button.isEnabled())
        self.assertIn('Entire displayed group undone', reopened.feedback.text())
        self.select('alpha')
        wait_for_selected_asset(self.window, 'alpha')
        single = self.window.edit_curation()
        self.assertIsNotNone(single)
        wait_for_gateway_condition(
            self.window,
            lambda: single.save_button.isEnabled()
            and single.feedback.text() == 'Current catalog values loaded.'
            and single.current.text().startswith('Current: Unrated · Not favorite')
            and not single.undo_button.isEnabled(),
            description='alpha curation values and history loaded after whole-group undo',
        )
        self.assertFalse(single.undo_button.isEnabled())
        self.assertEqual(api.list_curation_edits(self.db, 'alpha'), [])

    def test_exact_history_group_unchanged_member_single_undo_invalidates_group(self):
        single = api.set_curation(self.db, 'beta', rating=4, favorite=False, expected_revision=0)
        first = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('alpha', 'beta')), api.CurationChanges(rating=4)))
        second = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('gamma',)), api.CurationChanges(rating=5)))
        editor = self.open_history()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.group_box.findData(first['batch_id']) >= 0,
            description='first exact history group choice',
        )
        editor.group_box.setCurrentIndex(editor.group_box.findData(first['batch_id']))
        wait_for_gateway_condition(
            self.window,
            lambda: editor.undo_batch_id == first['batch_id'] and editor.undo_button.isEnabled(),
            description='first exact group details',
        )
        self.assertEqual(editor.undo_batch_id, first['batch_id'])
        self.assertNotIn('ID: gamma', editor.group_effects.toPlainText())
        api.undo_curation(self.db, single['edit_id'])
        editor.undo_group()
        wait_for_gateway_condition(
            self.window,
            lambda: 'Undo refused' in editor.feedback.text(),
            description='stale whole-group undo refusal',
        )
        self.assertIn('Undo refused', editor.feedback.text())
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], 4)
        self.assertEqual(api.get_curation(self.db, 'gamma')['rating'], 5)
        editor.group_box.setCurrentIndex(editor.group_box.findData(second['batch_id']))
        wait_for_gateway_condition(
            self.window,
            lambda: editor.undo_batch_id == second['batch_id'] and editor.undo_button.isEnabled(),
            description='second exact group details',
        )
        editor.undo_group()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.feedback.text() == 'Entire displayed group undone in catalog.',
            description='second whole-group undo completion',
        )
        self.assertEqual(api.get_curation(self.db, 'gamma')['rating'], 2)

    def test_history_keyboard_focus_group_choice_and_explicit_whole_group_undo(self):
        group = api.apply_curation_batch(self.db, api.preview_curation_batch(self.db,
            api.capture_curation(self.db, ('alpha', 'beta')), api.CurationChanges(rating=5)))
        editor = self.open_history()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.group_box.findData(group['batch_id']) >= 0,
            description='keyboard history group choice',
        )
        editor.activateWindow()
        self.app.processEvents()
        self.assertIs(editor.focusWidget(), editor.group_box)
        QTest.keyClick(editor.group_box, Qt.Key.Key_Home)
        self.assertIsNone(editor.undo_batch_id)
        QTest.keyClick(editor.group_box, Qt.Key.Key_End)
        wait_for_gateway_condition(
            self.window,
            lambda: editor.undo_batch_id == group['batch_id'],
            description='keyboard-selected whole-group detail publication',
        )
        self.assertEqual(editor.undo_batch_id, group['batch_id'])
        for _ in range(3):
            if editor.focusWidget() is editor.undo_button:
                break
            QTest.keyClick(editor.focusWidget(), Qt.Key.Key_Tab)
        self.assertIs(editor.focusWidget(), editor.undo_button)
        QTest.keyClick(editor.undo_button, Qt.Key.Key_Space)
        wait_for_gateway_condition(
            self.window,
            lambda: editor.feedback.text() == 'Entire displayed group undone in catalog.',
            description='keyboard whole-group undo completion',
        )
        self.assertTrue(api.get_curation_batch(self.db, group['batch_id'])['undone'])
        self.assertEqual(api.get_curation(self.db, 'alpha')['rating'], None)
        self.assertEqual(api.get_curation(self.db, 'beta')['rating'], 4)

    def test_large_selection_is_rejected_before_materializing_and_max_dialog_remains_bounded(self):
        with catalog.connect(self.db) as db:
            for index in range(257):
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) VALUES(?,?,?,?,?)',
                           (f'bounded-{index}', f'/generated/bounded-{index}.png', 'image/png', 'hash', 1))
        previous_generation = self.window.model._generation
        self.window.model.refresh()
        wait_for_generation_after(self.window, previous_generation, expected_count=260,
                                  description='expanded selection catalog generation')
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
        wait_for_gateway_condition(
            self.window,
            lambda: '256 targets' in editor.effects.toPlainText() and editor.apply_button.isEnabled(),
            description='maximum-size bulk preview',
        )
        self.assertIn('256 targets', editor.effects.toPlainText())

    def test_noop_and_storage_failure_are_truthful_preserve_controls_and_stable_selection(self):
        self.select('alpha', 'beta')
        editor = self.window.edit_bulk_curation()
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '0 changed' in editor.effects.toPlainText(),
            description='no-op bulk preview',
        )
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: 'No changes' in editor.feedback.text()
            and 'Completed without changes' in editor.effects.toPlainText(),
            description='no-op bulk apply completion',
        )
        self.assertIn('Completed without changes', editor.effects.toPlainText())
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '2 changed' in editor.effects.toPlainText(),
            description='bulk preview before storage failure',
        )
        with patch('prototypes.qt.app.curation.apply_curation_batch', side_effect=sqlite3.OperationalError('generated locked')):
            editor.apply()
            wait_for_gateway_condition(
                self.window,
                lambda: 'locked' in editor.feedback.text(),
                description='bulk storage failure outcome',
            )
        self.assertIn('locked', editor.feedback.text())
        self.assertEqual(editor.rating_box.currentData(), 5)
        editor.preview()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.apply_button.isEnabled() and '2 changed' in editor.effects.toPlainText(),
            description='bulk preview after storage failure',
        )
        editor.apply()
        wait_for_gateway_condition(
            self.window,
            lambda: editor.feedback.text().startswith('Group saved to catalog'),
            description='bulk recovery apply completion',
        )
        def restored_selection():
            model = self.window.model
            selection = self.window.gallery.selectionModel().selectedIndexes()
            selected_ids = []
            for index in selection:
                asset = model.loaded_asset_at(index.row())
                if asset is None:
                    return False
                selected_ids.append(asset['asset_id'])
            current = self.window._selected_asset()
            return (set(selected_ids) == {'alpha', 'beta'} and current is not None
                    and current['asset_id'] == 'alpha')

        wait_for_gateway_condition(
            self.window,
            restored_selection,
            description='restored alpha/beta selection after bulk recovery generation',
        )
        self.assertEqual(set(self.selected_ids()), {'alpha', 'beta'})
        self.assertEqual(self.window._selected_asset()['asset_id'], 'alpha')


if __name__ == '__main__':
    unittest.main()
