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


class CurationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
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
        self.addCleanup(self.window.close)

    def select(self, asset_id):
        row = self.window.model.row_for_asset(asset_id)
        self.window.gallery.setCurrentIndex(self.window.model.index(row))

    def ids(self):
        return [self.window.model.asset_at(row)['asset_id'] for row in range(self.window.model.rowCount())]

    def test_captured_identity_selection_drift_keyboard_save_and_independent_values(self):
        self.window.show()
        self.select('asset-0')
        editor = self.window.edit_curation()
        self.addCleanup(editor.close)
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
        self.assertEqual((api.get_curation(self.db, 'asset-0')['rating'], api.get_curation(self.db, 'asset-0')['favorite']), (5, False))
        self.assertEqual(api.get_curation(self.db, 'asset-1')['rating'], 4)
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
        model = self.window.model
        model.set_collection(collection['collection_id'])
        model.set_filter('reviewed')
        model.set_metadata_filters(source_id='source', media_type='image/png', search='.png')
        model.set_duplicate_hash('same-hash')
        model.set_curation_filters(rating=RatingFilter(RatingMode.AT_LEAST, 4), favorite=FavoriteFilter.ALL)
        self.assertEqual(self.ids(), ['asset-2', 'asset-1'])
        self.assertEqual(model.row_for_asset('asset-1'), 1)
        model.set_curation_filters(rating=RatingFilter(RatingMode.EXACT, 4), favorite=FavoriteFilter.FAVORITES)
        self.assertEqual(self.ids(), ['asset-1'])
        model.set_curation_filters(rating=RatingFilter(RatingMode.UNRATED), favorite=FavoriteFilter.FAVORITES)
        self.assertEqual(self.ids(), ['asset-0'])
        model.set_curation_filters(favorite=FavoriteFilter.NOT_FAVORITES)
        self.assertEqual(self.ids(), ['asset-2'])
        before = self.ids()
        for rating, favorite in [('4', FavoriteFilter.ALL), (RatingFilter(), True)]:
            with self.assertRaises(ValueError): model.set_curation_filters(rating=rating, favorite=favorite)
        self.assertEqual(self.ids(), before)
        self.assertEqual(collections.list_members(self.db, collection['collection_id']), ['asset-2', 'asset-1', 'asset-0', 'asset-3'])

    def test_filter_widgets_and_accessible_gallery_values(self):
        self.window.rating_filter_box.setCurrentIndex(self.window.rating_filter_box.findData(RatingFilter(RatingMode.EXACT, 4)))
        self.window.favorite_filter_box.setCurrentIndex(self.window.favorite_filter_box.findData(FavoriteFilter.FAVORITES))
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
