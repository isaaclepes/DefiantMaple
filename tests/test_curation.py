"""Generated catalogs: explicit override authority, durable CAS edits and undo."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from defiantmaple import catalog, curation as api, metadata, collections
from defiantmaple.sources import add_source, scan_sources


PNG = b'\x89PNG\r\n\x1a\nfictional generated pixels'


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'catalog.sqlite3'
        catalog.initialize(self.db)
        self.art = self.root / 'art'
        self.art.mkdir()
        self.file = self.art / 'one.png'
        self.file.write_bytes(PNG)
        self.asset = catalog.index_file(self.db, self.file)
        other = self.art / 'two.png'
        other.write_bytes(PNG)
        self.other = catalog.index_file(self.db, other)

    def state(self):
        return api.get_curation(self.db, self.asset)

    def edit(self, rating=4, favorite=True):
        return api.set_curation(self.db, self.asset, rating=rating, favorite=favorite,
                                expected_revision=self.state()['revision'])

    def snapshot(self):
        with closing(sqlite3.connect(self.db)) as db:
            return tuple(db.iterdump())

    def test_independent_rating_favorite_reopen_noop_and_single_edit_undo(self):
        self.assertEqual((self.state()['rating'], self.state()['favorite']), (None, False))
        first = self.edit(None, True)
        self.assertEqual((first['rating'], first['favorite']), (None, True))
        result = self.edit(5, True)
        snapshot = self.snapshot()
        noop = self.edit(5, True)
        self.assertFalse(noop['changed'])
        self.assertIsNone(noop['edit_id'])
        self.assertEqual(self.snapshot(), snapshot)
        catalog.initialize(self.db, create=False)
        self.assertEqual(self.state()['authority'], 'catalog_user_managed')
        self.assertEqual(api.list_curation_edits(self.db, self.asset)[0]['edit_id'], result['edit_id'])
        undone = api.undo_curation(self.db, result['edit_id'])
        self.assertEqual((undone['rating'], undone['favorite']), (None, True))
        self.assertGreater(undone['revision'], result['revision'])
        for edit in (result, first):
            with self.assertRaises(api.CurationConflict):
                api.undo_curation(self.db, edit['edit_id'])
        self.edit(3, False)
        self.assertEqual((self.state()['rating'], self.state()['favorite']), (3, False))

    def test_invalid_api_values_unknown_ids_and_stale_noop_are_atomic(self):
        result = self.edit()
        before = self.snapshot()
        for rating in (0, 6, -1, True, 3.0, '3', [], {}):
            with self.subTest(rating=rating), self.assertRaises(ValueError):
                self.edit(rating)
        for favorite in (0, 1, 'yes', None):
            with self.assertRaises(ValueError):
                self.edit(favorite=favorite)
        for revision in (True, -1, 1.0, '1'):
            with self.assertRaises(ValueError):
                api.set_curation(self.db, self.asset, rating=4, favorite=True, expected_revision=revision)
        with self.assertRaises(api.CurationConflict):
            api.set_curation(self.db, self.asset, rating=4, favorite=True,
                             expected_revision=result['revision'] - 1)
        for operation in (lambda: api.get_curation(self.db, 'unknown'),
                          lambda: api.undo_curation(self.db, 'unknown'),
                          lambda: api.set_curation(self.db, 'unknown', rating=3, favorite=True, expected_revision=0)):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(self.snapshot(), before)

    def test_sql_constraints_revision_reset_identity_and_replace_refused(self):
        self.edit()
        before = self.snapshot()
        with catalog.connect(self.db) as db:
            for field, values in (('rating', [0, 6, -1, 1.25, 'invalid']),
                                  ('favorite', [2, -1, 0.5, 'invalid', None]),
                                  ('revision', [-1, 0, 1.5, 'invalid', None])):
                for value in values:
                    with self.subTest(field=field, value=value), self.assertRaises(sqlite3.IntegrityError):
                        db.execute(f'UPDATE assets SET {field}=? WHERE asset_id=?', (value, self.asset))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE assets SET asset_id=? WHERE asset_id=?', ('replacement-id', self.asset))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT OR REPLACE INTO assets(asset_id,current_path,media_type,sha256,byte_size) '
                           'SELECT asset_id,current_path,media_type,sha256,byte_size FROM assets WHERE asset_id=?',
                           (self.asset,))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM assets WHERE asset_id=?', (self.asset,))
        self.assertEqual(self.snapshot(), before)

    def test_path_content_state_aba_refuses_undo_even_when_result_values_return(self):
        for field, alternative in (('current_path', '/fictional/changed.png'), ('sha256', 'changed'),
                                   ('byte_size', 999), ('media_type', 'video/mp4'),
                                   ('workflow_state', 'reviewed')):
            with self.subTest(field=field):
                edit = self.edit(3 if self.state()['rating'] != 3 else 4)
                with catalog.connect(self.db) as db:
                    original = db.execute(f'SELECT {field} FROM assets WHERE asset_id=?', (self.asset,)).fetchone()[0]
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id=?', (alternative, self.asset))
                    db.execute(f'UPDATE assets SET {field}=? WHERE asset_id=?', (original, self.asset))
                before = self.snapshot()
                with self.assertRaises(api.CurationConflict):
                    api.undo_curation(self.db, edit['edit_id'])
                self.assertEqual(self.snapshot(), before)

    def test_rating_aba_competing_writers_and_unrelated_asset(self):
        revision = self.state()['revision']
        barrier = threading.Barrier(2)
        outcomes = []
        def writer(stars):
            barrier.wait()
            try:
                outcomes.append(api.set_curation(self.db, self.asset, rating=stars, favorite=False,
                                                  expected_revision=revision))
            except api.CurationConflict as exc:
                outcomes.append(exc)
        threads = [threading.Thread(target=writer, args=(stars,)) for stars in (2, 5)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        original = self.edit(4, True)
        self.edit(1, False)
        self.edit(4, True)
        with self.assertRaises(api.CurationConflict):
            api.undo_curation(self.db, original['edit_id'])
        eligible = self.edit(5, True)
        api.set_curation(self.db, self.other, rating=1, favorite=True,
                         expected_revision=api.get_curation(self.db, self.other)['revision'])
        api.undo_curation(self.db, eligible['edit_id'])

    def test_assignment_taxonomy_alias_and_collection_changes_invalidate(self):
        tag = metadata.create_tag(self.db, 'Tag')
        entity = metadata.create_entity(self.db, 'Character', 'Entity')
        collection = collections.create_collection(self.db, 'Collection')
        metadata.assign_tag(self.db, self.asset, tag['tag_id'])
        metadata.assign_entity(self.db, self.asset, entity['entity_id'])
        collections.add_member(self.db, collection['collection_id'], self.asset)
        actions = [lambda: metadata.rename_tag(self.db, tag['tag_id'], 'Renamed'),
                   lambda: metadata.add_tag_alias(self.db, tag['tag_id'], 'Alias'),
                   lambda: metadata.remove_tag_alias(self.db, tag['tag_id'], 'Alias'),
                   lambda: metadata.rename_entity(self.db, entity['entity_id'], 'Renamed'),
                   lambda: metadata.add_entity_alias(self.db, entity['entity_id'], 'Alias'),
                   lambda: metadata.remove_entity_alias(self.db, entity['entity_id'], 'Alias'),
                   lambda: collections.rename_collection(self.db, collection['collection_id'], 'Renamed'),
                   lambda: collections.remove_member(self.db, collection['collection_id'], self.asset),
                   lambda: metadata.unassign_tag(self.db, self.asset, tag['tag_id']),
                   lambda: metadata.unassign_entity(self.db, self.asset, entity['entity_id'])]
        for action in actions:
            edit = self.edit(3 if self.state()['rating'] != 3 else 4)
            action()
            with self.assertRaises(api.CurationConflict):
                api.undo_curation(self.db, edit['edit_id'])

    def test_entity_alias_direct_update_reassignment_and_taxonomy_noop(self):
        a = metadata.create_entity(self.db, 'Character', 'A')
        b = metadata.create_entity(self.db, 'Character', 'B')
        metadata.assign_entity(self.db, self.asset, a['entity_id'])
        metadata.assign_entity(self.db, self.other, b['entity_id'])
        metadata.add_entity_alias(self.db, a['entity_id'], 'Alias')
        edit = self.edit()
        metadata.rename_entity(self.db, a['entity_id'], 'A')
        self.assertEqual(self.state()['revision'], edit['revision'])
        with catalog.connect(self.db) as db:
            db.execute('UPDATE entity_aliases SET alias=? WHERE entity_id=?', ('ALIAS', a['entity_id']))
        with self.assertRaises(api.CurationConflict): api.undo_curation(self.db, edit['edit_id'])
        first_rev, other_rev = self.state()['revision'], api.get_curation(self.db, self.other)['revision']
        with catalog.connect(self.db) as db:
            db.execute('UPDATE entity_aliases SET entity_id=? WHERE entity_id=?', (b['entity_id'], a['entity_id']))
        self.assertGreater(self.state()['revision'], first_rev)
        self.assertGreater(api.get_curation(self.db, self.other)['revision'], other_rev)

    def test_scan_authority_source_bytes_and_observed_pending_missing_refuse(self):
        source = add_source(self.db, self.art, existing_file_policy='inbox')
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=0)
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=0)
        sidecar = self.art / 'one.png.json'
        sidecar.write_bytes(b'{"rating":1,"favorite":false}')
        before = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.art.iterdir()}
        edit = self.edit()
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=0)
        self.assertEqual(self.state()['revision'], edit['revision'])
        self.assertEqual({p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.art.iterdir()}, before)
        self.assertEqual((self.state()['rating'], self.state()['favorite']), (4, True))
        self.file.write_bytes(PNG + b'new content')
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=60)
        with self.assertRaises(api.CurationConflict): api.undo_curation(self.db, edit['edit_id'])
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=0)
        self.assertEqual((self.state()['rating'], self.state()['favorite']), (4, True))
        missing_edit = self.edit(5)
        self.file.unlink()
        scan_sources(self.db, source_id=source['source_id'], quiet_seconds=0)
        with self.assertRaises(api.CurationConflict): api.undo_curation(self.db, missing_edit['edit_id'])

    def test_journal_failure_rolls_back_edit_and_undo_including_revision(self):
        with catalog.connect(self.db) as db:
            db.execute("CREATE TRIGGER generated_edit_failure BEFORE INSERT ON curation_edits "
                       "BEGIN SELECT RAISE(ABORT,'generated journal write failure'); END")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'journal write failure'):
            self.edit()
        self.assertEqual(self.snapshot(), before)
        with catalog.connect(self.db) as db:
            db.execute('DROP TRIGGER generated_edit_failure')
        edit = self.edit()
        with catalog.connect(self.db) as db:
            db.execute("CREATE TRIGGER generated_undo_failure BEFORE UPDATE OF undone ON curation_edits "
                       "BEGIN SELECT RAISE(ABORT,'generated undo journal failure'); END")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'undo journal failure'):
            api.undo_curation(self.db, edit['edit_id'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.state()['revision'], edit['revision'])
        with catalog.connect(self.db) as db:
            db.execute('DROP TRIGGER generated_undo_failure')
        restored = api.undo_curation(self.db, edit['edit_id'])
        self.assertEqual((restored['rating'], restored['favorite']), (None, False))

    def test_v4_backup_upgrade_preservation_failure_rollback_and_schema_authentication(self):
        old = self.root / 'v4.sqlite3'
        with closing(sqlite3.connect(old)) as db:
            db.executescript(catalog.SCHEMA_V4)
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                       "VALUES('old-id','/old.png','image/png','old-hash',12)")
            db.execute("INSERT INTO collections VALUES('c','Collection','collection')")
            db.execute("INSERT INTO collection_members VALUES('c','old-id',7)")
            db.commit()
            original = tuple(db.iterdump())
        real = catalog._migrate_four_to_five
        def fail(db):
            real(db)
            db.execute("UPDATE assets SET rating=5")
            raise OSError('generated post-DDL failure')
        with patch.object(catalog, '_migrate_four_to_five', side_effect=fail):
            with self.assertRaises(catalog.CatalogMigrationError) as failure:
                catalog.initialize(old, create=False)
        for path in (old, Path(failure.exception.backup_path)):
            with closing(sqlite3.connect(path)) as db: self.assertEqual(tuple(db.iterdump()), original)
        result = catalog.initialize(old, create=False)
        self.assertEqual(result['schema_version'], 6)
        self.assertEqual(api.get_curation(old, 'old-id')['revision'], 0)
        self.assertEqual(collections.list_members(old, 'c'), ['old-id'])
        with closing(sqlite3.connect(old)) as db:
            db.execute('DROP TRIGGER source_entries_revision_update')
            db.commit()
        with self.assertRaisesRegex(ValueError, 'tables/triggers'):
            catalog.initialize(old, create=False)


if __name__ == '__main__':
    unittest.main()
