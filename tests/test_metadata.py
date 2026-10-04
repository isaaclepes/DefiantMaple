"""Metadata behavior uses only temporary fictional media/catalog records."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid

from defiantmaple import metadata as m
from defiantmaple.catalog import connect, index_file, initialize


PNG = b'\x89PNG\r\n\x1a\nfictional metadata fixture'


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'catalog.sqlite3'
        initialize(self.db)
        self.first_file = self.root / 'fictional-first.png'
        self.second_file = self.root / 'fictional-second.png'
        self.first_file.write_bytes(PNG)
        self.second_file.write_bytes(PNG)
        self.first = index_file(self.db, self.first_file)
        self.second = index_file(self.db, self.second_file)

    def test_normalization_alias_resolution_rename_and_idempotent_removal(self):
        tag = m.create_tag(self.db, '  Cafe\u0301\t Fictional\nLabel  ')
        tag_id = tag['tag_id']
        self.assertEqual(str(uuid.UUID(tag_id)), tag_id)
        self.assertEqual(tag['name'], 'Café Fictional Label')
        with self.assertRaises(ValueError):
            m.create_tag(self.db, 'CAFÉ  fictional label')
        alias = m.add_tag_alias(self.db, tag_id, '  StrAße  ')
        self.assertEqual(alias['aliases'], ['StrAße'])
        self.assertEqual(m.add_tag_alias(self.db, tag_id, 'STRASSE'), alias)
        self.assertEqual(m.find_tag(self.db, 'strasse'), alias)
        self.assertEqual(m.find_tag(self.db, 'cafe\u0301 fictional label'), alias)
        renamed = m.rename_tag(self.db, tag_id, 'CAFÉ Fictional LABEL')
        self.assertEqual(renamed['tag_id'], tag_id)
        self.assertEqual(renamed['aliases'], ['StrAße'])
        m.rename_tag(self.db, tag_id, 'Replacement')
        self.assertIsNone(m.find_tag(self.db, 'Café Fictional Label'))
        self.assertEqual(m.find_tag(self.db, 'STRASSE')['name'], 'Replacement')
        self.assertEqual(m.remove_tag_alias(self.db, tag_id, 'strasse')['aliases'], [])
        self.assertEqual(m.remove_tag_alias(self.db, tag_id, 'STRASSE')['aliases'], [])
        self.assertIsNone(m.find_tag(self.db, 'STRASSE'))

    def test_nfc_casefold_and_non_nfkc_behavior(self):
        m.create_tag(self.db, 'ﬀ')
        with self.assertRaises(ValueError):
            m.create_tag(self.db, 'ff')  # Unicode casefold itself folds this ligature.
        narrow = m.create_tag(self.db, 'A')
        wide = m.create_tag(self.db, 'Ａ')  # NFC does not apply NFKC width folding.
        self.assertNotEqual(narrow['tag_id'], wide['tag_id'])
        self.assertEqual(m.find_tag(self.db, 'a'), narrow)
        accent = m.create_tag(self.db, 'é')
        plain = m.create_tag(self.db, 'e')
        self.assertNotEqual(accent['tag_id'], plain['tag_id'])

    def test_invalid_names_fail_without_writes(self):
        for value in ('', ' \t\n', 'fictional\x00name', 'fictional\x07name', None, 3):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                m.create_tag(self.db, value)
        self.assertEqual(m.list_tags(self.db), [])
        tag = m.create_tag(self.db, 'Valid')
        with self.assertRaises(ValueError):
            m.rename_tag(self.db, tag['tag_id'], '\x00')
        with self.assertRaises(ValueError):
            m.add_tag_alias(self.db, tag['tag_id'], '\x01')
        self.assertEqual(m.get_tag(self.db, tag['tag_id']), tag)

    def test_tag_shared_canonical_alias_namespace_both_directions(self):
        first = m.create_tag(self.db, 'First')
        second = m.create_tag(self.db, 'Second')
        m.add_tag_alias(self.db, first['tag_id'], 'Alternate')
        for action in (lambda: m.create_tag(self.db, 'ALTERNATE'),
                       lambda: m.rename_tag(self.db, second['tag_id'], 'alternate'),
                       lambda: m.add_tag_alias(self.db, second['tag_id'], 'Alternate'),
                       lambda: m.add_tag_alias(self.db, second['tag_id'], 'FIRST'),
                       lambda: m.add_tag_alias(self.db, first['tag_id'], 'First'),
                       lambda: m.rename_tag(self.db, first['tag_id'], 'Alternate')):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(m.get_tag(self.db, second['tag_id']), second)
        self.assertEqual(m.find_tag(self.db, 'alternate')['tag_id'], first['tag_id'])

    def test_six_entity_types_namespaces_aliases_and_rename(self):
        self.assertEqual(m.ENTITY_TYPES,
                         ('Character','Artist','Project','Location','Client','Franchise'))
        records = [m.create_entity(self.db, kind, 'Fictional Name') for kind in m.ENTITY_TYPES]
        self.assertEqual(len({item['entity_id'] for item in records}), 6)
        for entity in records:
            kind, record_id = entity['entity_type'], entity['entity_id']
            alias = m.add_entity_alias(self.db, record_id, 'Fictional Alias')
            self.assertEqual(m.add_entity_alias(self.db, record_id, 'FICTIONAL ALIAS'), alias)
            self.assertEqual(m.find_entity(self.db, kind, 'fictional alias'), alias)
            with self.assertRaises(ValueError):
                m.create_entity(self.db, kind, 'fictional alias')
            with self.assertRaises(ValueError):
                m.create_entity(self.db, kind, 'fictional name')
            with self.assertRaises(ValueError):
                m.add_entity_alias(self.db, record_id, 'Fictional Name')
            renamed = m.rename_entity(self.db, record_id, 'Replacement')
            self.assertEqual(renamed['entity_id'], record_id)
            self.assertEqual(renamed['aliases'], ['Fictional Alias'])
            self.assertIsNone(m.find_entity(self.db, kind, 'Fictional Name'))
            self.assertEqual(m.list_entities(self.db, entity_type=kind), [renamed])
            self.assertEqual(m.remove_entity_alias(self.db, record_id, 'fictional alias')['aliases'], [])
            self.assertEqual(m.remove_entity_alias(self.db, record_id, 'fictional alias')['aliases'], [])
        self.assertEqual([item['entity_type'] for item in m.list_entities(self.db)],
                         sorted(m.ENTITY_TYPES))
        other = m.create_entity(self.db, 'Character', 'Other')
        canonical = records[0]['entity_id']
        with self.assertRaises(ValueError):
            m.add_entity_alias(self.db, other['entity_id'], 'Replacement')
        m.add_entity_alias(self.db, canonical, 'Occupied Alias')
        with self.assertRaises(ValueError):
            m.add_entity_alias(self.db, other['entity_id'], 'occupied alias')
        with self.assertRaises(ValueError):
            m.rename_entity(self.db, other['entity_id'], 'Occupied Alias')
        self.assertEqual(m.get_entity(self.db, other['entity_id']), other)

    def test_parent_self_descendant_cycles_clear_and_no_assignment_propagation(self):
        parent = m.create_tag(self.db, 'Parent')
        child = m.create_tag(self.db, 'Child', parent_id=parent['tag_id'])
        grandchild = m.create_tag(self.db, 'Grandchild', parent_id=child['tag_id'])
        m.assign_tag(self.db, self.first, grandchild['tag_id'])
        for tag_id, parent_id in ((parent['tag_id'], parent['tag_id']),
                                  (parent['tag_id'], grandchild['tag_id']),
                                  (child['tag_id'], grandchild['tag_id'])):
            with self.assertRaises(ValueError):
                m.set_tag_parent(self.db, tag_id, parent_id)
        self.assertEqual(m.get_tag(self.db, parent['tag_id'])['parent_id'], None)
        metadata = m.get_asset_metadata(self.db, self.first)
        self.assertEqual([item['tag_id'] for item in metadata['tags']], [grandchild['tag_id']])
        m.set_tag_parent(self.db, grandchild['tag_id'], parent['tag_id'])
        self.assertEqual([item['tag_id'] for item in m.get_asset_metadata(self.db, self.first)['tags']],
                         [grandchild['tag_id']])
        self.assertIsNone(m.set_tag_parent(self.db, grandchild['tag_id'], None)['parent_id'])
        with self.assertRaises(sqlite3.IntegrityError), connect(self.db) as db:
            db.execute('UPDATE tags SET parent_id=? WHERE tag_id=?',
                       (child['tag_id'], parent['tag_id']))

    def test_many_to_many_same_hash_separate_and_idempotent_assign_unassign(self):
        self.assertNotEqual(self.first, self.second)
        tag = m.create_tag(self.db, 'Shared')
        extra = m.create_tag(self.db, 'Additional')
        entities = [m.create_entity(self.db, kind, 'Fictional') for kind in m.ENTITY_TYPES]
        once = m.assign_tag(self.db, self.first, tag['tag_id'])
        self.assertEqual(m.assign_tag(self.db, self.first, tag['tag_id']), once)
        self.assertEqual(m.get_asset_metadata(self.db, self.second)['tags'], [])
        m.assign_tag(self.db, self.second, tag['tag_id'])
        m.assign_tag(self.db, self.first, extra['tag_id'])
        for entity in entities:
            once = m.assign_entity(self.db, self.first, entity['entity_id'])
            self.assertEqual(m.assign_entity(self.db, self.first, entity['entity_id']), once)
        self.assertEqual(len(m.get_asset_metadata(self.db, self.first)['entities']), 6)
        self.assertEqual(m.get_asset_metadata(self.db, self.second)['entities'], [])
        m.unassign_tag(self.db, self.first, tag['tag_id'])
        removed = m.unassign_tag(self.db, self.first, tag['tag_id'])
        self.assertEqual(removed['tags'], [extra])
        self.assertEqual(m.get_asset_metadata(self.db, self.second)['tags'], [tag])
        for entity in entities:
            m.unassign_entity(self.db, self.first, entity['entity_id'])
            m.unassign_entity(self.db, self.first, entity['entity_id'])
        self.assertEqual(m.get_asset_metadata(self.db, self.first)['entities'], [])
        with connect(self.db) as db:
            self.assertEqual(len({row[0] for row in db.execute('SELECT sha256 FROM assets')}), 1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_assignment_survives_catalog_path_change_and_missing_observation(self):
        tag = m.create_tag(self.db, 'Stable')
        entity = m.create_entity(self.db, 'Project', 'Stable project')
        m.assign_tag(self.db, self.first, tag['tag_id'])
        original = m.assign_entity(self.db, self.first, entity['entity_id'])
        with connect(self.db) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                       "VALUES('fictional-source','Fictional','/fictional','inbox')")
            db.execute("UPDATE assets SET current_path='/fictional-new-path.png',"
                       "source_id='fictional-source' WHERE asset_id=?", (self.first,))
            db.execute("INSERT INTO source_entries VALUES('/fictional-new-path.png','fictional-source',"
                       "1,1,'fictional-device','fictional-inode',1,1,0,'missing',?,NULL)", (self.first,))
        self.assertEqual(m.get_asset_metadata(self.db, self.first), original)
        self.assertEqual(m.get_asset_metadata(self.db, self.second)['tags'], [])

    def test_source_sidecar_bytes_mtimes_and_existing_catalog_state_remain_unchanged(self):
        sidecar = self.root / 'fictional-first.png.json'
        sidecar.write_bytes(b'{"fictional":"original sidecar"}')
        paths = (self.first_file, self.second_file, sidecar)
        before = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                  for path in paths}
        with connect(self.db) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                       "VALUES('fictional-source','Fictional','/fictional','reviewed','offline')")
            db.execute("UPDATE assets SET source_id='fictional-source' WHERE asset_id=?", (self.first,))
            db.execute("INSERT INTO source_entries VALUES('/fictional.png','fictional-source',"
                       "1,1,'fictional-device','fictional-inode',1,1,1,'missing',?,"
                       "'fictional existing error')", (self.first,))
            sources = [tuple(row) for row in db.execute('SELECT * FROM sources')]
            entries = [tuple(row) for row in db.execute('SELECT * FROM source_entries')]
            assets = [tuple(row) for row in db.execute('SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at,rating,favorite FROM assets ORDER BY asset_id')]
            provenance = [tuple(row) for row in db.execute('SELECT * FROM provenance ORDER BY provenance_id')]
        tag = m.create_tag(self.db, 'Explicit')
        m.add_tag_alias(self.db, tag['tag_id'], 'Alias')
        m.assign_tag(self.db, self.first, tag['tag_id'])
        entity = m.create_entity(self.db, 'Artist', 'Explicit artist')
        m.add_entity_alias(self.db, entity['entity_id'], 'Artist alias')
        m.assign_entity(self.db, self.first, entity['entity_id'])
        m.rename_tag(self.db, tag['tag_id'], 'Renamed')
        self.assertEqual({path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                          for path in paths}, before)
        with connect(self.db) as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources')], sources)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM source_entries')], entries)
            self.assertEqual([tuple(row) for row in db.execute('SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at,rating,favorite FROM assets ORDER BY asset_id')], assets)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM provenance ORDER BY provenance_id')], provenance)

    def test_unknown_ids_types_and_parents_are_rejected(self):
        tag = m.create_tag(self.db, 'Valid')
        entity = m.create_entity(self.db, 'Client', 'Valid')
        actions = [lambda: m.get_tag(self.db, 'unknown'), lambda: m.get_entity(self.db, 'unknown'),
                   lambda: m.get_asset_metadata(self.db, 'unknown'),
                   lambda: m.create_tag(self.db, 'Child', parent_id='unknown'),
                   lambda: m.set_tag_parent(self.db, tag['tag_id'], 'unknown'),
                   lambda: m.assign_tag(self.db, 'unknown', tag['tag_id']),
                   lambda: m.unassign_tag(self.db, self.first, 'unknown'),
                   lambda: m.assign_entity(self.db, 'unknown', entity['entity_id']),
                   lambda: m.unassign_entity(self.db, self.first, 'unknown'),
                   lambda: m.create_entity(self.db, 'character', 'Invalid'),
                   lambda: m.list_entities(self.db, entity_type='Unknown'),
                   lambda: m.find_entity(self.db, 'Unknown', 'Unknown')]
        for action in actions:
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(m.get_asset_metadata(self.db, self.first)['tags'], [])

    def test_concurrent_collisions_and_opposite_parent_edits_serialize(self):
        barrier = threading.Barrier(2)

        def create(name):
            barrier.wait(timeout=5)
            try:
                return m.create_tag(self.db, name)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ['Concurrent', 'CONCURRENT']))
        self.assertEqual(sum(result is not None for result in results), 1)
        first = m.create_tag(self.db, 'Parent A')
        second = m.create_tag(self.db, 'Parent B')
        barrier = threading.Barrier(2)

        def parent(pair):
            barrier.wait(timeout=5)
            try:
                return m.set_tag_parent(self.db, *pair)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(parent, [(first['tag_id'], second['tag_id']),
                                             (second['tag_id'], first['tag_id'])]))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertFalse(m.get_tag(self.db, first['tag_id'])['parent_id'] == second['tag_id']
                         and m.get_tag(self.db, second['tag_id'])['parent_id'] == first['tag_id'])


if __name__ == '__main__':
    unittest.main()
