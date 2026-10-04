"""Collection controls and paged browsing use only fictional temporary data."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from defiantmaple import collections as api, metadata
from defiantmaple.catalog import initialize, index_file
from prototypes.qt.app import GalleryWindow


class CollectionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='defiantmaple-collections-ui-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'fictional.sqlite3'
        initialize(self.db)
        self.art = self.root / 'fictional-art'
        self.art.mkdir()
        Image.new('RGB', (16, 16), (30, 70, 140)).save(self.art / 'one.png')
        for name in ('two.png', 'three.png'):
            (self.art / name).write_bytes((self.art / 'one.png').read_bytes())
        (self.art / 'one.png.json').write_bytes(b'{"fictional":"unchanged"}')
        self.ids = [index_file(self.db, self.art / name)
                    for name in ('one.png', 'two.png', 'three.png')]
        tag = metadata.create_tag(self.db, 'Fictional tag')
        entity = metadata.create_entity(self.db, 'Project', 'Fictional project')
        metadata.assign_tag(self.db, self.ids[0], tag['tag_id'])
        metadata.assign_entity(self.db, self.ids[0], entity['entity_id'])
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                       "VALUES('fictional-source','Fictional',?,'inbox','offline')", (str(self.art),))
            db.execute("UPDATE assets SET source_id='fictional-source' WHERE asset_id IN (?,?)",
                       self.ids[:2])
            db.execute("UPDATE assets SET workflow_state='reviewed' WHERE asset_id=?", (self.ids[1],))
            db.execute("UPDATE assets SET media_type='video/mp4' WHERE asset_id=?", (self.ids[2],))
            db.execute("INSERT INTO source_entries VALUES(?, 'fictional-source',1,1,'d','i',1,1,"
                       "0,'missing',?,NULL)", (str(self.art / 'one.png'), self.ids[0]))
            db.commit()
        self.original_files = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                               for path in self.art.iterdir()}
        self.original_rows = self.snapshot_rows()
        self.addCleanup(self.assert_unchanged)

    def snapshot_rows(self):
        with closing(sqlite3.connect(self.db)) as db:
            return {table: db.execute(f'SELECT {"asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at,rating,favorite" if table == "assets" else "*"} FROM {table} ORDER BY 1').fetchall()
                    for table in ('assets', 'provenance', 'sources', 'source_entries', 'tags',
                                  'tag_aliases', 'entities', 'entity_aliases', 'asset_tags', 'asset_entities')}

    def assert_unchanged(self):
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns)
                          for path in self.art.iterdir()}, self.original_files)
        self.assertEqual(self.snapshot_rows(), self.original_rows)

    def window(self, database=None):
        window = GalleryWindow(database or self.db)
        self.addCleanup(window.close)
        return window

    def collection(self, name='Fictional sequence', members=None):
        record = api.create_collection(self.db, name)
        for asset_id in members if members is not None else self.ids:
            api.add_member(self.db, record['collection_id'], asset_id)
        return record['collection_id']

    def select_collection(self, window, collection_id):
        window.collection_box.setCurrentIndex(window.collection_box.findData(collection_id))

    def select_asset(self, window, asset_id):
        row = window.model.row_for_asset(asset_id)
        self.assertIsNotNone(row)
        window.gallery.setCurrentIndex(window.model.index(row))

    def visible_ids(self, window):
        return [window.model.asset_at(row)['asset_id'] for row in range(window.model.rowCount())]

    def test_empty_library_lifecycle_and_delete_confirmation(self):
        empty = self.root / 'empty.sqlite3'
        initialize(empty)
        window = self.window(empty)
        self.assertFalse(window.add_member_button.isEnabled())
        with patch('prototypes.qt.app.QInputDialog.getText', return_value=('  Empty collection  ', True)):
            window.create_collection_button.click()
        collection_id = window.collection_box.currentData()
        self.assertEqual(api.get_collection(empty, collection_id)['name'], 'Empty collection')
        self.assertTrue(window.rename_collection_button.isEnabled())
        with patch('prototypes.qt.app.QInputDialog.getText', return_value=('Renamed empty', True)):
            window.rename_collection_button.click()
        self.assertEqual(window.collection_box.currentData(), collection_id)
        self.assertEqual(api.get_collection(empty, collection_id)['name'], 'Renamed empty')
        with patch('prototypes.qt.app.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            window.delete_collection_button.click()
        self.assertEqual(len(api.list_collections(empty)), 1)
        with patch('prototypes.qt.app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as question:
            window.delete_collection_button.click()
        self.assertIn('Only this collection', question.call_args.args[2])
        self.assertEqual(api.list_collections(empty), [])
        self.assertIsNone(window.collection_box.currentData())
        self.assertEqual(window.model.rowCount(), 0)

    def test_add_remove_readd_order_selection_and_reopen(self):
        collection_id = self.collection(members=[])
        window = self.window()
        for asset_id in self.ids:
            self.select_asset(window, asset_id)
            with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
                window.add_member_button.click()
        self.select_collection(window, collection_id)
        self.assertEqual(self.visible_ids(window), self.ids)
        self.select_asset(window, self.ids[1])
        with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
            window.add_member_button.click()
        self.assertEqual(self.visible_ids(window), self.ids)
        window.move_up_button.click()
        self.assertEqual(self.visible_ids(window), [self.ids[1], self.ids[0], self.ids[2]])
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])
        window.remove_member_button.click()
        self.assertIsNone(window._selected_asset())
        self.select_collection(window, None)
        self.select_asset(window, self.ids[1])
        with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
            window.add_member_button.click()
        self.select_collection(window, collection_id)
        expected = [self.ids[0], self.ids[2], self.ids[1]]
        self.assertEqual(self.visible_ids(window), expected)
        window.close()
        reopened = self.window()
        self.select_collection(reopened, collection_id)
        self.assertEqual(self.visible_ids(reopened), expected)

    def test_add_rename_delete_dialogs_keep_captured_targets(self):
        first = self.collection('First', [])
        second = self.collection('Second', [self.ids[1]])
        window = self.window()
        self.select_asset(window, self.ids[0])

        def choose(*args):
            window.model.refresh()
            self.select_collection(window, second)
            self.select_asset(window, self.ids[1])
            return 'First', True

        with patch('prototypes.qt.app.QInputDialog.getItem', side_effect=choose):
            window._add_collection_member()
        self.assertEqual(api.list_members(self.db, first), [self.ids[0]])
        self.assertEqual(api.list_members(self.db, second), [self.ids[1]])
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])
        self.select_collection(window, first)

        def rename(*args):
            self.select_collection(window, second)
            return 'Renamed first', True

        with patch('prototypes.qt.app.QInputDialog.getText', side_effect=rename):
            window._rename_collection()
        self.assertEqual(api.get_collection(self.db, first)['name'], 'Renamed first')
        self.assertEqual(api.get_collection(self.db, second)['name'], 'Second')
        self.select_collection(window, first)

        def confirm(*args):
            self.select_collection(window, second)
            return QMessageBox.StandardButton.Yes

        with patch('prototypes.qt.app.QMessageBox.question', side_effect=confirm):
            window._delete_collection()
        self.assertEqual([item['collection_id'] for item in api.list_collections(self.db)], [second])
        self.assertEqual(window.collection_box.currentData(), second)
        self.assertEqual(window.model.rowCount(), 1)

    def test_filtered_views_preserve_members_and_refuse_moves(self):
        collection_id = self.collection(members=list(reversed(self.ids)))
        window = self.window()
        self.select_collection(window, collection_id)
        expected = list(reversed(self.ids))
        self.assertEqual(self.visible_ids(window), expected)
        filters = [
            (lambda: window.model.set_filter('new'), [self.ids[2], self.ids[0]]),
            (lambda: window.model.set_metadata_filters(source_id='fictional-source'), [self.ids[1], self.ids[0]]),
            (lambda: window.model.set_metadata_filters(media_type='image/png'), [self.ids[1], self.ids[0]]),
            (lambda: window.model.set_metadata_filters(search='one.png'), [self.ids[0]]),
            (lambda: window.model.set_duplicate_hash('no-matching-hash'), []),
        ]
        for apply, visible in filters:
            window.model.set_filter(None)
            window.model.set_metadata_filters()
            apply()
            self.assertEqual(self.visible_ids(window), visible)
            if visible:
                self.select_asset(window, visible[0])
            self.assertFalse(window.move_up_button.isEnabled())
            self.assertFalse(window.move_down_button.isEnabled())
            window._move_collection_member(1)
            self.assertEqual(api.list_members(self.db, collection_id), expected)
        window.model.set_metadata_filters()
        self.assertEqual(self.visible_ids(window), expected)
        offline = window.model.asset_at(window.model.row_for_asset(self.ids[0]))
        self.assertEqual(offline['source_health'], 'offline')
        self.assertEqual(offline['entry_disposition'], 'missing')

    def test_stale_neighbor_refuses_without_moving_another_member(self):
        collection_id = self.collection()
        window = self.window()
        self.select_collection(window, collection_id)
        self.select_asset(window, self.ids[1])
        operation = api.move_member

        def concurrent(*args, **kwargs):
            api.reorder_members(self.db, collection_id, [self.ids[0], self.ids[2], self.ids[1]])
            return operation(*args, **kwargs)

        with patch('prototypes.qt.app.collection_api.move_member', side_effect=concurrent):
            window.move_up_button.click()
        self.assertEqual(api.list_members(self.db, collection_id), [self.ids[0], self.ids[2], self.ids[1]])
        self.assertNotEqual(window.collection_feedback.text(), 'Collection saved.')
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])

    def test_collection_callbacks_after_close_and_dialog_close_do_not_access_model(self):
        collection_id = self.collection()
        window = self.window()
        self.select_collection(window, collection_id)

        def close_during_dialog(*args):
            window.close()
            return 'Closed before save', True

        with patch('prototypes.qt.app.QInputDialog.getText', side_effect=close_during_dialog), \
                patch('prototypes.qt.app.collection_api.rename_collection') as rename:
            window._rename_collection()
            rename.assert_not_called()
        with patch.object(window.model, 'asset_at', side_effect=AssertionError('Closed model')), \
                patch.object(window.model, 'refresh', side_effect=AssertionError('Closed model')), \
                patch('prototypes.qt.app.collection_api.list_collections', side_effect=AssertionError('Late API')):
            window.refresh_collections()
            window._collection_selected()
            window._refresh_collection_view()
            window._restore_asset_selection(self.ids[0])
            window._create_collection()
            window._rename_collection()
            window._delete_collection()
            window._add_collection_member()
            window._remove_collection_member()
            window._move_collection_member(1)
            window._update_collection_controls()
        self.assertEqual(api.get_collection(self.db, collection_id)['name'], 'Fictional sequence')

    def test_rival_removal_between_rank_and_page_load_repairs_view_without_retargeting(self):
        for index, (target_id, removed_id) in enumerate(((self.ids[2], self.ids[2]),
                                                       (self.ids[1], self.ids[0]))):
            with self.subTest(target=target_id, removed=removed_id):
                collection_id = self.collection(f'Rival removal {index}')
                window = self.window()
                self.select_collection(window, collection_id)
                window.model.refresh()
                self.assertEqual(window.model._cache, {})
                real_rank = window.model.row_for_asset

                def rank_then_remove(asset_id):
                    rank = real_rank(asset_id)
                    # Real rival connection commits after the read snapshot,
                    # before the view lazily fetches the now-shorter page.
                    api.remove_member(self.db, collection_id, removed_id)
                    return rank

                with patch.object(window.model, 'row_for_asset', side_effect=rank_then_remove):
                    window._restore_asset_selection(target_id)
                self.assertEqual(window.model.rowCount(), 2)
                self.assertIsNone(window._selected_asset())
                self.assertFalse(window.gallery.currentIndex().isValid())
                self.assertEqual(window.detail.toPlainText(), '')
                expected = [asset_id for asset_id in self.ids if asset_id != removed_id]
                self.assertEqual(self.visible_ids(window), expected)
                self.assertIsNone(window.model.data(window.model.index(2), window.model.AssetRole))
                self.assertEqual(api.list_members(self.db, collection_id), expected)

    def test_duplicate_name_rejection_is_visible(self):
        self.collection('Existing', [])
        window = self.window()
        with patch('prototypes.qt.app.QInputDialog.getText', return_value=('EXISTING', True)):
            window.create_collection_button.click()
        self.assertEqual(len(api.list_collections(self.db)), 1)
        self.assertNotEqual(window.collection_feedback.text(), 'Collection saved.')

    def test_paging_moves_across_boundary_without_full_member_fetch(self):
        paged = self.root / 'paged.sqlite3'
        initialize(paged)
        ids = [f'00000000-0000-0000-0000-{index:012d}' for index in range(514)]
        with closing(sqlite3.connect(paged)) as db:
            db.executemany('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) '
                           "VALUES(?,?,'image/png','fictional-hash',12)",
                           [(asset_id, f'/fictional/{index}.png') for index, asset_id in enumerate(ids)])
            db.commit()
        collection_id = api.create_collection(paged, 'Paged')['collection_id']
        with closing(sqlite3.connect(paged)) as db:
            db.executemany('INSERT INTO collection_members(collection_id,asset_id,position) VALUES(?,?,?)',
                           [(collection_id, asset_id, index * 3) for index, asset_id in enumerate(ids)])
            db.commit()
        window = self.window(paged)
        self.select_collection(window, collection_id)
        self.assertEqual(window.model.rowCount(), 514)
        self.select_asset(window, ids[255])
        with patch('prototypes.qt.app.collection_api.list_members', side_effect=AssertionError('Unbounded fetch')):
            window.move_down_button.click()
            self.assertEqual(window.gallery.currentIndex().row(), 256)
            self.assertEqual(window._selected_asset()['asset_id'], ids[255])
            self.assertEqual(window.model.asset_at(255)['asset_id'], ids[256])
            window.move_up_button.click()
        self.assertEqual(api.list_members(paged, collection_id), ids)
        self.select_asset(window, ids[0])
        self.assertFalse(window.move_up_button.isEnabled())
        self.select_asset(window, ids[-1])
        self.assertFalse(window.move_down_button.isEnabled())
        self.assertLessEqual(len(window.model._cache), window.model.max_cached_pages)


if __name__ == '__main__':
    unittest.main()
