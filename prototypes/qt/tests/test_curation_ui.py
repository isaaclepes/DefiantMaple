"""Generated temporary fixtures exercise captured edits and composed gallery filters."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, curation as api, collections
from defiantmaple.curation import RatingFilter, RatingMode, FavoriteFilter
from prototypes.qt.app import AssetModel, CurationDialog, GalleryWindow
from prototypes.qt.tests.gallery_wait import (
    close_windows_and_cleanup,
    wait_for_all_asset_ids,
    wait_for_asset_at,
    wait_for_collection_record,
    wait_for_detail,
    wait_for_generation_after,
    wait_for_gateway_condition,
    wait_for_initial_generation,
    wait_for_rank,
    wait_for_selected_asset,
)


class CurationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.windows = []
        self.addCleanup(self._cleanup_fixture)
        self.db = self.root / 'catalog.sqlite3'
        catalog.initialize(self.db)
        with catalog.connect(self.db) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                       "VALUES('source','Generated','/generated','inbox')")
            for index, rating, favorite, state, source in (
                (0, None, 1, 'reviewed', 'source'), (1, 4, 1, 'reviewed', 'source'),
                (2, 5, 0, 'reviewed', 'source'), (3, 4, 1, 'new', None)):
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,'
                           'rating,favorite,workflow_state,source_id) VALUES(?,?,?,?,?,?,?,?,?)',
                           (f'asset-{index}', f'/generated/{index}.png', 'image/png', 'same-hash',
                            1, rating, favorite, state, source))
        self.window = GalleryWindow(self.db)
        self.windows.append(self.window)
        wait_for_initial_generation(self.window, expected_count=4)

    def _cleanup_fixture(self):
        close_windows_and_cleanup(self.windows, self.app, self.root)

    def select(self, asset_id):
        row = wait_for_rank(self.window, asset_id)
        wait_for_asset_at(self.window, row, asset_id)
        self.window.gallery.setCurrentIndex(self.window.model.index(row))
        wait_for_selected_asset(self.window, asset_id, row=row)

    def ids(self):
        return wait_for_all_asset_ids(self.window)

    def test_captured_identity_selection_drift_keyboard_save_and_independent_values(self):
        self.window.show()
        self.select('asset-0')
        editor = self.window.edit_curation()
        self.addCleanup(editor.close)
        wait_for_gateway_condition(
            self.window,
            lambda: editor.save_button.isEnabled()
            and editor.feedback.text() == 'Current catalog values loaded.',
            description='curation editor loaded captured asset values',
        )
        self.select('asset-1')
        self.assertIn('asset-0', editor.target.text())
        with self.assertRaises(AttributeError): editor.asset_id = 'asset-1'
        editor.rating_box.setFocus()
        self.app.processEvents()
        QTest.keyClick(editor.rating_box, Qt.Key.Key_End)
        self.assertEqual(editor.rating_box.currentData(), 5)
        editor.favorite_box.setChecked(False)
        editor.save_button.setFocus()
        QTest.keyClick(editor.save_button, Qt.Key.Key_Space)
        wait_for_gateway_condition(
            self.window,
            lambda: ('Current: 5 stars · Not favorite' in editor.current.text()
                     and editor.save_button.isEnabled()
                     and editor.feedback.text() == 'Rating and favorite saved to catalog.'),
            description='refreshed captured curation values and terminal save feedback',
        )
        self.assertEqual((api.get_curation(self.db, 'asset-0')['rating'], api.get_curation(self.db, 'asset-0')['favorite']), (5, False))
        self.assertEqual(api.get_curation(self.db, 'asset-1')['rating'], 4)
        wait_for_selected_asset(self.window, 'asset-1')
        self.assertEqual(self.window._selected_asset()['asset_id'], 'asset-1')
        self.assertEqual(editor.feedback.text(), 'Rating and favorite saved to catalog.')
        self.assertIn('5 stars', editor.current.text())
        self.assertIn('Not favorite', editor.current.text())

    def test_durable_undo_reopen_and_stale_history_not_offered(self):
        editor = CurationDialog(self.db, 'asset-0')
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(3))
        editor.save()
        editor.close()
        reopened = CurationDialog(self.db, 'asset-0')
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.undo_button.isEnabled())
        reopened.undo()
        self.assertEqual(api.get_curation(self.db, 'asset-0')['rating'], None)
        self.assertFalse(reopened.undo_button.isEnabled())
        self.assertEqual(reopened.feedback.text(), 'Latest rating/favorite edit undone in catalog.')
        reopened.rating_box.setCurrentIndex(reopened.rating_box.findData(4))
        reopened.save()
        reopened.rating_box.setCurrentIndex(reopened.rating_box.findData(5))
        reopened.save()
        reopened.undo()
        self.assertFalse(reopened.undo_button.isEnabled())
        self.assertIn('Undo unavailable', reopened.current.text())

    def test_stale_save_and_aba_undo_refusal_preserve_choices_until_explicit_reload(self):
        editor = CurationDialog(self.db, 'asset-0')
        self.addCleanup(editor.close)
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(4))
        editor.save()
        with catalog.connect(self.db) as db:
            db.execute("UPDATE assets SET workflow_state='new' WHERE asset_id='asset-0'")
            db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id='asset-0'")
        before = api.get_curation(self.db, 'asset-0')
        editor.undo()
        self.assertIn('Undo refused', editor.feedback.text())
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        editor.save()
        self.assertIn('changed since it was loaded', editor.feedback.text())
        self.assertEqual(editor.rating_box.currentData(), 5)
        self.assertEqual(api.get_curation(self.db, 'asset-0'), before)
        editor.reload()
        self.assertEqual(editor.rating_box.currentData(), 4)
        self.assertFalse(editor.undo_button.isEnabled())

    def test_noop_and_storage_failure_are_truthful(self):
        editor = CurationDialog(self.db, 'asset-1')
        self.addCleanup(editor.close)
        editor.save()
        self.assertEqual(editor.feedback.text(), 'No changes to save.')
        self.assertEqual(api.list_curation_edits(self.db, 'asset-1'), [])
        editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
        with patch('prototypes.qt.app.curation.set_curation', side_effect=sqlite3.OperationalError('generated database is locked')):
            editor.save()
        self.assertIn('not saved', editor.feedback.text())
        self.assertIn('locked', editor.feedback.text())
        self.assertEqual(api.get_curation(self.db, 'asset-1')['rating'], 4)

    def test_typed_filters_compose_with_state_source_media_path_duplicates_and_collection_order(self):
        collection = collections.create_collection(self.db, 'Sequence')
        for asset in ('asset-2', 'asset-1', 'asset-0', 'asset-3'):
            collections.add_member(self.db, collection['collection_id'], asset)
        self.window.refresh_collections()
        wait_for_collection_record(self.window, collection['collection_id'], current=False)
        model = self.window.model
        previous_generation = model._generation
        model.set_collection(collection['collection_id'])
        model.set_filter('reviewed')
        model.set_metadata_filters(source_id='source', media_type='image/png', search='.png')
        model.set_duplicate_hash('same-hash')
        model.set_curation_filters(rating=RatingFilter(RatingMode.AT_LEAST, 4), favorite=FavoriteFilter.ALL)
        wait_for_generation_after(self.window, previous_generation, expected_count=2,
                                  description='composed collection and typed-filter generation')
        self.assertEqual(self.ids(), ['asset-2', 'asset-1'])
        self.assertEqual(wait_for_rank(self.window, 'asset-1'), 1)
        previous_generation = model._generation
        model.set_curation_filters(rating=RatingFilter(RatingMode.EXACT, 4), favorite=FavoriteFilter.FAVORITES)
        wait_for_generation_after(self.window, previous_generation, expected_count=1,
                                  description='exact-rating favorite generation')
        self.assertEqual(self.ids(), ['asset-1'])
        previous_generation = model._generation
        model.set_curation_filters(rating=RatingFilter(RatingMode.UNRATED), favorite=FavoriteFilter.FAVORITES)
        wait_for_generation_after(self.window, previous_generation, expected_count=1,
                                  description='unrated-favorite generation')
        self.assertEqual(self.ids(), ['asset-0'])
        previous_generation = model._generation
        model.set_curation_filters(favorite=FavoriteFilter.NOT_FAVORITES)
        wait_for_generation_after(self.window, previous_generation, expected_count=1,
                                  description='nonfavorite generation')
        self.assertEqual(self.ids(), ['asset-2'])
        before = self.ids()
        for rating, favorite in [('4', FavoriteFilter.ALL), (RatingFilter(), True)]:
            with self.assertRaises(ValueError): model.set_curation_filters(rating=rating, favorite=favorite)
        self.assertEqual(self.ids(), before)
        self.assertEqual(collections.list_members(self.db, collection['collection_id']), ['asset-2', 'asset-1', 'asset-0', 'asset-3'])

    def test_filter_widgets_and_accessible_gallery_values(self):
        previous_generation = self.window.model._generation
        self.window.rating_filter_box.setCurrentIndex(self.window.rating_filter_box.findData(RatingFilter(RatingMode.EXACT, 4)))
        self.window.favorite_filter_box.setCurrentIndex(self.window.favorite_filter_box.findData(FavoriteFilter.FAVORITES))
        self.assertEqual(self.window.model._generation, previous_generation)
        self.assertEqual(self.ids(), ['asset-0', 'asset-1', 'asset-2', 'asset-3'])
        self.window.apply_filters_button.click()
        wait_for_generation_after(self.window, previous_generation, expected_count=2,
                                  description='composed rating/favorite filter-widget generation')
        self.assertEqual(self.ids(), ['asset-1', 'asset-3'])
        text = self.window.model.data(self.window.model.index(0), Qt.ItemDataRole.AccessibleTextRole)
        self.assertIn('rating 4', text)
        self.assertIn('favorite', text)
        self.assertTrue(self.window.model.has_active_filters)
        with self.assertRaises(ValueError): RatingFilter(RatingMode.EXACT, True)
        with self.assertRaises(ValueError): RatingFilter('exact', 4)
        with self.assertRaises(ValueError): RatingFilter(RatingMode.ALL, 4)


if __name__ == '__main__':
    unittest.main()
