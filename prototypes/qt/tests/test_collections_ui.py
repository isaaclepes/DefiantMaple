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
from prototypes.qt.tests.gallery_wait import (
    close_windows_and_cleanup,
    wait_for_all_asset_ids,
    wait_for_asset_at,
    close_window_and_wait,
    wait_for_collection_record,
    wait_for_generation_after,
    wait_for_gateway_condition,
    wait_for_initial_generation,
    wait_for_rank,
    wait_for_selected_asset,
    wait_for_startup_validation,
)


class CollectionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='defiantmaple-collections-ui-'))
        self.windows = []
        self.addCleanup(self._cleanup_fixture)
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
            indexed_path = db.execute("SELECT current_path FROM assets WHERE asset_id=?",
                                      (self.ids[0],)).fetchone()[0]
            db.execute("INSERT INTO source_entries VALUES(?, 'fictional-source',1,1,'d','i',1,1,"
                       "0,'missing',?,NULL)", (indexed_path, self.ids[0]))
            db.commit()
        self.original_files = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                               for path in self.art.iterdir()}
        self.original_rows = self.snapshot_rows()

    def _cleanup_fixture(self):
        close_windows_and_cleanup(self.windows, self.app, self.root,
                                  verify=self.assert_unchanged)

    def snapshot_rows(self):
        with closing(sqlite3.connect(self.db)) as db:
            return {table: db.execute(f'SELECT {"asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at,rating,favorite" if table == "assets" else "*"} FROM {table} ORDER BY 1').fetchall()
                    for table in ('assets', 'provenance', 'sources', 'source_entries', 'tags',
                                  'tag_aliases', 'entities', 'entity_aliases', 'asset_tags', 'asset_entities')}

    def assert_unchanged(self):
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns)
                          for path in self.art.iterdir()}, self.original_files)
        self.assertEqual(self.snapshot_rows(), self.original_rows)

    def window(self, database=None, *, expected_count=3):
        window = GalleryWindow(database or self.db)
        self.windows.append(window)
        wait_for_initial_generation(window, expected_count=expected_count)
        wait_for_startup_validation(window)
        return window

    def collection(self, name='Fictional sequence', members=None):
        record = api.create_collection(self.db, name)
        for asset_id in members if members is not None else self.ids:
            api.add_member(self.db, record['collection_id'], asset_id)
        return record['collection_id']

    def select_collection(self, window, collection_id):
        if collection_id is not None:
            wait_for_collection_record(window, collection_id, current=False)
        if window.collection_box.currentData() != collection_id:
            previous_generation = window.model._generation
            index = window.collection_box.findData(collection_id)
            self.assertGreaterEqual(index, 0)
            window.collection_box.setCurrentIndex(index)
            wait_for_generation_after(window, previous_generation,
                                      description=f'collection {collection_id!r} view')

    def select_asset(self, window, asset_id):
        row = wait_for_rank(window, asset_id)
        self.assertIsNotNone(row)
        wait_for_asset_at(window, row, asset_id)
        window.gallery.setCurrentIndex(window.model.index(row))
        wait_for_selected_asset(window, asset_id, row=row)

    def visible_ids(self, window):
        return wait_for_all_asset_ids(window)

    def test_empty_library_lifecycle_and_delete_confirmation(self):
        empty = self.root / 'empty.sqlite3'
        initialize(empty)
        window = self.window(empty, expected_count=0)
        self.assertFalse(window.add_member_button.isEnabled())
        with patch('prototypes.qt.app.QInputDialog.getText', return_value=('  Empty collection  ', True)):
            window.create_collection_button.click()
        wait_for_gateway_condition(window, lambda: window.collection_box.count() == 2,
                                   description='created empty collection choice')
        collection_id = window.collection_box.currentData()
        self.assertEqual(api.get_collection(empty, collection_id)['name'], 'Empty collection')
        wait_for_gateway_condition(
            window,
            lambda: (window.model._collection_id == collection_id and window.model._actionable
                     and window.collection_box.currentData() == collection_id),
            description='created empty collection view and controls ready',
        )
        self.assertTrue(window.rename_collection_button.isEnabled())
        with patch('prototypes.qt.app.QInputDialog.getText', return_value=('Renamed empty', True)):
            window.rename_collection_button.click()
        wait_for_gateway_condition(window, lambda: window.collection_box.currentText() == 'Renamed empty',
                                   description='renamed empty collection choice')
        self.assertEqual(window.collection_box.currentData(), collection_id)
        self.assertEqual(api.get_collection(empty, collection_id)['name'], 'Renamed empty')
        with patch('prototypes.qt.app.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            window.delete_collection_button.click()
        self.assertEqual(len(api.list_collections(empty)), 1)
        wait_for_gateway_condition(
            window,
            lambda: window.delete_collection_button.isEnabled(),
            description='empty collection delete control ready after decline',
        )
        with patch('prototypes.qt.app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as question:
            window.delete_collection_button.click()
        wait_for_gateway_condition(
            window,
            lambda: window.collection_box.count() == 1 and window.model.rowCount() == 0,
            description='deleted empty collection choice and view',
        )
        self.assertIn('Only this collection', question.call_args.args[2])
        self.assertEqual(api.list_collections(empty), [])
        self.assertIsNone(window.collection_box.currentData())
        self.assertEqual(window.model.rowCount(), 0)

    def test_add_remove_readd_order_selection_and_reopen(self):
        collection_id = self.collection(members=[])
        window = self.window()
        wait_for_collection_record(window, collection_id, current=False)
        for asset_id in self.ids:
            self.select_asset(window, asset_id)
            with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
                previous_generation = window.model._generation
                window.add_member_button.click()
            wait_for_generation_after(window, previous_generation,
                                      description=f'added captured member {asset_id}')
        self.select_collection(window, collection_id)
        self.assertEqual(self.visible_ids(window), self.ids)
        self.select_asset(window, self.ids[1])
        with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
            previous_generation = window.model._generation
            window.add_member_button.click()
        wait_for_generation_after(window, previous_generation,
                                  description='re-added captured collection member')
        wait_for_selected_asset(window, self.ids[1])
        self.assertEqual(self.visible_ids(window), self.ids)
        self.assertEqual(window.collection_box.currentData(), collection_id)
        wait_for_gateway_condition(
            window,
            lambda: window.move_up_button.isEnabled(),
            description='reordered collection controls ready for selected second member',
        )
        self.assertTrue(window.move_up_button.isEnabled())
        previous_generation = window.model._generation
        window.move_up_button.click()
        wait_for_generation_after(window, previous_generation,
                                  description='moved collection member generation')
        wait_for_selected_asset(window, self.ids[1])
        self.assertEqual(self.visible_ids(window), [self.ids[1], self.ids[0], self.ids[2]])
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])
        previous_generation = window.model._generation
        window.remove_member_button.click()
        wait_for_generation_after(window, previous_generation, expected_count=2,
                                  description='removed collection member generation')
        self.assertIsNone(window._selected_asset())
        self.select_collection(window, None)
        self.select_asset(window, self.ids[1])
        with patch('prototypes.qt.app.QInputDialog.getItem', return_value=('Fictional sequence', True)):
            previous_generation = window.model._generation
            window.add_member_button.click()
        wait_for_generation_after(window, previous_generation,
                                  description='added member after collection reset')
        self.select_collection(window, collection_id)
        expected = [self.ids[0], self.ids[2], self.ids[1]]
        self.assertEqual(self.visible_ids(window), expected)
        close_window_and_wait(window, self.app)
        reopened = self.window()
        self.select_collection(reopened, collection_id)
        self.assertEqual(self.visible_ids(reopened), expected)

    def test_add_rename_delete_dialogs_keep_captured_targets(self):
        first = self.collection('First', [])
        second = self.collection('Second', [self.ids[1]])
        window = self.window()
        wait_for_collection_record(window, first, current=False)
        self.select_asset(window, self.ids[0])

        def choose(*args):
            window.model.refresh()
            self.select_collection(window, second)
            self.select_asset(window, self.ids[1])
            return 'First', True

        previous_generation = window.model._generation
        with patch('prototypes.qt.app.QInputDialog.getItem', side_effect=choose):
            window._add_collection_member()
        wait_for_generation_after(window, previous_generation,
                                  description='captured collection add after dialog selection drift')
        self.assertEqual(api.list_members(self.db, first), [self.ids[0]])
        self.assertEqual(api.list_members(self.db, second), [self.ids[1]])
        wait_for_selected_asset(window, self.ids[1])
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])
        self.select_collection(window, first)

        def rename(*args):
            self.select_collection(window, second)
            return 'Renamed first', True

        previous_generation = window.model._generation
        with patch('prototypes.qt.app.QInputDialog.getText', side_effect=rename):
            window._rename_collection()
        wait_for_generation_after(window, previous_generation,
                                  description='captured collection rename after selection drift')
        self.assertEqual(api.get_collection(self.db, first)['name'], 'Renamed first')
        self.assertEqual(api.get_collection(self.db, second)['name'], 'Second')
        self.select_collection(window, first)

        def confirm(*args):
            self.select_collection(window, second)
            self.assertEqual(window.collection_box.currentData(), second)
            return QMessageBox.StandardButton.Yes

        previous_generation = window.model._generation
        with patch('prototypes.qt.app.QMessageBox.question', side_effect=confirm):
            window._delete_collection()
        wait_for_generation_after(window, previous_generation, expected_count=1,
                                  description='captured collection delete after selection drift')
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
            previous_generation = window.model._generation
            window.model.set_filter(None)
            window.model.set_metadata_filters()
            apply()
            wait_for_generation_after(window, previous_generation, expected_count=len(visible),
                                      description='filtered collection view generation')
            self.assertEqual(self.visible_ids(window), visible)
            if visible:
                self.select_asset(window, visible[0])
            self.assertFalse(window.move_up_button.isEnabled())
            self.assertFalse(window.move_down_button.isEnabled())
            window._move_collection_member(1)
            self.assertEqual(api.list_members(self.db, collection_id), expected)
        previous_generation = window.model._generation
        window.model.set_metadata_filters()
        wait_for_generation_after(window, previous_generation, expected_count=3,
                                  description='cleared collection filters generation')
        self.assertEqual(self.visible_ids(window), expected)
        row = wait_for_rank(window, self.ids[0])
        wait_for_asset_at(window, row, self.ids[0])
        offline = window.model.loaded_asset_at(row)
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
            previous_generation = window.model._generation
            window.move_up_button.click()
            wait_for_generation_after(window, previous_generation,
                                      description='stale-neighbor refusal view repair')
        wait_for_selected_asset(window, self.ids[1])
        self.assertEqual(api.list_members(self.db, collection_id), [self.ids[0], self.ids[2], self.ids[1]])
        self.assertNotEqual(window.collection_feedback.text(), 'Collection saved.')
        self.assertEqual(window._selected_asset()['asset_id'], self.ids[1])

    def test_collection_callbacks_after_close_and_dialog_close_do_not_access_model(self):
        collection_id = self.collection()
        window = self.window()
        window.show()
        self.select_collection(window, collection_id)

        def close_during_dialog(*args):
            close_window_and_wait(window, self.app)
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
                model = window.model
                self.assertIn(0, model._cache)
                self.assertFalse(model._pending_pages)
                # The atomic first-page publication is part of the new contract. Evict only
                # this test-owned cache after publication to recreate the former lazy-page
                # boundary without mutating the generation or catalog.
                model._cache.clear()
                previous_generation = model._generation
                real_request_rank = model.request_rank
                real_request_page = model.request_page
                rival_committed = False
                pages_after_rival = []
                callback_errors = []

                def request_rank(asset_id, callback):
                    def ranked(row, error):
                        nonlocal rival_committed
                        if not error and row is not None:
                            # The read rank has succeeded. A separate real catalog connection
                            # commits before the app callback requests the uncached page.
                            api.remove_member(self.db, collection_id, removed_id)
                            if model._pending_pages:
                                callback_errors.append(AssertionError(
                                    'rank callback reached with an earlier page request pending'))
                                callback(None, 'test race setup found a pending page request')
                                return
                            # Viewport activity may have repopulated page zero since the initial
                            # cache eviction. Evict it again after the rival commit to preserve
                            # the original rank-to-lazy-page race boundary.
                            model._cache.clear()
                            rival_committed = True
                        callback(row, error)
                    return real_request_rank(asset_id, ranked)

                def request_page(page):
                    if rival_committed:
                        pages_after_rival.append(page)
                    return real_request_page(page)

                with patch.object(model, 'request_rank', side_effect=request_rank), \
                        patch.object(model, 'request_page', side_effect=request_page):
                    window._restore_asset_selection(target_id)
                    wait_for_gateway_condition(
                        window,
                        lambda: bool(callback_errors) or model._generation > previous_generation,
                        description='rank callback and rival removal outcome',
                    )
                    self.assertEqual(callback_errors, [])
                    wait_for_generation_after(window, previous_generation, expected_count=2,
                                              description='rival-removal repaired gallery generation')
                    self.assertTrue(rival_committed)
                    self.assertIn(0, pages_after_rival,
                                  'rank callback must request an uncached page after rival commit')
                    wait_for_gateway_condition(
                        window,
                        lambda: not window.gallery.currentIndex().isValid()
                        and window.detail.toPlainText() == '',
                        description='refused stale target remains unselected after repair',
                    )
                self.assertEqual(model.rowCount(), 2)
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
        wait_for_gateway_condition(
            window,
            lambda: bool(window.collection_feedback.text()),
            description='duplicate collection name refusal',
        )
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
        window = self.window(paged, expected_count=514)
        self.select_collection(window, collection_id)
        self.assertEqual(window.model.rowCount(), 514)
        self.select_asset(window, ids[255])
        with patch('prototypes.qt.app.collection_api.list_members', side_effect=AssertionError('Unbounded fetch')):
            self.assertEqual(window.collection_box.currentData(), collection_id)
            self.assertEqual(window.model._collection_id, collection_id)
            self.assertEqual(window._selected_asset()['asset_id'], ids[255])
            wait_for_gateway_condition(
                window,
                lambda: window.move_down_button.isEnabled(),
                description='page-boundary selected member controls ready',
            )
            wait_for_asset_at(window, 256, ids[256])
            prior_feedback = window.collection_feedback.text()
            window.move_down_button.click()
            wait_for_gateway_condition(
                window,
                lambda: window.collection_feedback.text() != prior_feedback,
                description='paged move-down Core result',
            )
            self.assertEqual(window.collection_feedback.text(), 'Collection saved.')
            wait_for_selected_asset(window, ids[255], row=256)
            self.assertEqual(window.gallery.currentIndex().row(), 256)
            self.assertEqual(window._selected_asset()['asset_id'], ids[255])
            self.assertEqual(window.model.asset_at(255)['asset_id'], ids[256])
            previous_generation = window.model._generation
            window.move_up_button.click()
            wait_for_generation_after(
                window,
                previous_generation,
                expected_count=514,
                description='paged move-up refreshed generation',
            )
            wait_for_selected_asset(window, ids[255], row=255)
            wait_for_asset_at(window, 256, ids[256])
            self.assertEqual(window.collection_feedback.text(), 'Collection saved.')
            self.assertEqual(window.model.asset_at(255)['asset_id'], ids[255])
            self.assertEqual(window.model.asset_at(256)['asset_id'], ids[256])
        self.assertEqual(api.list_members(paged, collection_id), ids)
        self.select_asset(window, ids[0])
        self.assertFalse(window.move_up_button.isEnabled())
        self.select_asset(window, ids[-1])
        self.assertFalse(window.move_down_button.isEnabled())
        self.assertLessEqual(len(window.model._cache), window.model.max_cached_pages)


if __name__ == '__main__':
    unittest.main()
