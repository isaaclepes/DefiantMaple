"""Fictional catalogs only: backup ordering, authenticity and atomic upgrades."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple import catalog
from defiantmaple.__main__ import main


LEGACY_V1 = """
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
"""


def snapshot(path):
    with contextlib.closing(sqlite3.connect(path)) as db:
        return db.execute("PRAGMA user_version").fetchone()[0], tuple(db.iterdump())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "fictional.sqlite3"

    def legacy(self, version, *, populated=True, sql=None):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.executescript(sql or {1: LEGACY_V1, 2: catalog.SCHEMA_V2,
                                    3: catalog.SCHEMA_V3, 4: catalog.SCHEMA}[version])
            if populated:
                if version >= 2:
                    db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,"
                               "health,health_detail,initial_scan_completed,last_scan_at) "
                               "VALUES('fictional-source','Fictional','/fictional','reviewed',"
                               "'offline','fictional unavailable',1,'previous scan')")
                db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
                           "workflow_state,discovered_at) VALUES('fictional-asset','/fictional.png',"
                           "'image/png','fictional-hash',12,'needs_review','original time')")
                db.execute("INSERT INTO provenance VALUES('fictional-provenance','fictional-asset',"
                           "'fictional-import','{\"fictional\":true}','original provenance time')")
                if version >= 2:
                    db.execute("UPDATE assets SET source_id='fictional-source'")
                    db.execute("INSERT INTO source_entries VALUES('/fictional.png','fictional-source',"
                               "12,1,'fictional-device','fictional-inode',2,3,1,'missing',"
                               "'fictional-asset','fictional previous error')")
                if version >= 3:
                    db.execute("INSERT INTO tags VALUES('fictional-parent','Parent','parent',NULL)")
                    db.execute("INSERT INTO tags VALUES('fictional-child','Child','child','fictional-parent')")
                    db.execute("INSERT INTO tag_aliases VALUES('child alias','fictional-child','Child alias')")
                    db.execute("INSERT INTO entities VALUES('fictional-entity','Character','Fictional','fictional')")
                    db.execute("INSERT INTO entity_aliases VALUES('Character','fictional alias',"
                               "'fictional-entity','Fictional alias')")
                    db.execute("INSERT INTO asset_tags VALUES('fictional-asset','fictional-child')")
                    db.execute("INSERT INTO asset_entities VALUES('fictional-asset','fictional-entity')")
                db.commit()
        return snapshot(self.path)

    def assert_original_rows(self, path, version, populated):
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            if not populated:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 0)
                return
            self.assertEqual(db.execute("SELECT asset_id,current_path,sha256,workflow_state,"
                                        "discovered_at FROM assets").fetchone(),
                             ('fictional-asset', '/fictional.png', 'fictional-hash',
                              'needs_review', 'original time'))
            self.assertEqual(db.execute("SELECT * FROM provenance").fetchone(),
                             ('fictional-provenance', 'fictional-asset', 'fictional-import',
                              '{"fictional":true}', 'original provenance time'))
            if version >= 2:
                self.assertEqual(db.execute("SELECT source_id,health,health_detail,"
                                            "initial_scan_completed,last_scan_at FROM sources").fetchone(),
                                 ('fictional-source','offline','fictional unavailable',1,'previous scan'))
                self.assertEqual(db.execute("SELECT * FROM source_entries").fetchone(),
                                 ('/fictional.png','fictional-source',12,1,'fictional-device',
                                  'fictional-inode',2,3,1,'missing','fictional-asset',
                                  'fictional previous error'))
                self.assertEqual(db.execute("SELECT source_id FROM assets").fetchone()[0],
                                 'fictional-source')
            if version >= 3:
                self.assertEqual(db.execute("SELECT * FROM tags ORDER BY tag_id").fetchall(),
                                 [('fictional-child','Child','child','fictional-parent'),
                                  ('fictional-parent','Parent','parent',None)])
                self.assertEqual(db.execute("SELECT * FROM tag_aliases").fetchall(),
                                 [('child alias','fictional-child','Child alias')])
                self.assertEqual(db.execute("SELECT * FROM entities").fetchall(),
                                 [('fictional-entity','Character','Fictional','fictional')])
                self.assertEqual(db.execute("SELECT * FROM entity_aliases").fetchall(),
                                 [('Character','fictional alias','fictional-entity','Fictional alias')])
                self.assertEqual(db.execute("SELECT * FROM asset_tags").fetchall(),
                                 [('fictional-asset','fictional-child')])
                self.assertEqual(db.execute("SELECT * FROM asset_entities").fetchall(),
                                 [('fictional-asset','fictional-entity')])

    def test_fresh_and_current_results_and_durability_settings(self):
        result = catalog.initialize(self.path)
        self.assertEqual(result, dict(schema_version=4, previous_version=0, created=True,
                                     migrated=False, backup_path=None))
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], 'delete')
            self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(catalog.initialize(self.path, create=False),
                         dict(schema_version=4, previous_version=4, created=False,
                              migrated=False, backup_path=None))
        self.assertEqual(list(self.root.glob('*.backup.sqlite3')), [])

    def test_empty_and_populated_legacy_upgrade_backup_and_restore(self):
        for version in (1, 2, 3):
            for populated in (False, True):
                with self.subTest(version=version, populated=populated):
                    self.path = self.root / f'v{version}-{populated}.sqlite3'
                    original = self.legacy(version, populated=populated)
                    result = catalog.initialize(self.path, create=False)
                    self.assertEqual({key: result[key] for key in result if key != 'backup_path'},
                                     dict(schema_version=4, previous_version=version,
                                          created=False, migrated=True))
                    backup = Path(result['backup_path'])
                    self.assertTrue(backup.is_file())
                    self.assertEqual(snapshot(backup), original)
                    self.assert_original_rows(self.path, version, populated)
                    self.assert_original_rows(backup, version, populated)
                    restored = self.root / f'restored-{version}-{populated}.sqlite3'
                    shutil.copyfile(backup, restored)
                    self.assertEqual(snapshot(restored), original)
                    catalog.initialize(restored, create=False)
                    self.assert_original_rows(restored, version, populated)
                    with contextlib.closing(sqlite3.connect(self.path)) as db:
                        catalog._validate_catalog_schema(db, 4)
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM collections").fetchone()[0], 0)
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_members").fetchone()[0], 0)
                    self.assertEqual(len(list(self.root.glob(f'{self.path.name}*.backup.sqlite3'))), 1)

    def test_canonical_v1_and_previous_alter_based_v2_are_supported(self):
        start = catalog.SCHEMA_V2.index("CREATE TABLE assets")
        end = catalog.SCHEMA_V2.index("CREATE TABLE source_entries")
        canonical_v1 = catalog.SCHEMA_V2[start:end].replace(
            "    source_id TEXT REFERENCES sources(source_id),\n", "") + "PRAGMA user_version=1;"
        for previous_version in (1, 2):
            with self.subTest(previous_version=previous_version):
                self.path = self.root / f'canonical-{previous_version}.sqlite3'
                self.legacy(1, sql=canonical_v1)
                if previous_version == 2:
                    # This is the old production ALTER path, with source_id last.
                    with contextlib.closing(sqlite3.connect(self.path)) as db:
                        db.executescript(catalog.MIGRATE_1_TO_2)
                original = snapshot(self.path)
                result = catalog.initialize(self.path, create=False)
                self.assertEqual(result['previous_version'], previous_version)
                self.assertEqual(snapshot(Path(result['backup_path'])), original)
                self.assert_original_rows(self.path, 1, True)

    def test_backup_name_collision_never_overwrites_unrelated_output(self):
        original = self.legacy(2)
        import uuid
        fixed = uuid.UUID(int=1)
        collision = self.path.with_name(f"{self.path.name}.v2.{fixed.hex}.backup.sqlite3")
        collision.write_bytes(b'fictional unrelated existing output')
        with patch.object(catalog.uuid, 'uuid4', return_value=fixed):
            with self.assertRaises(catalog.CatalogMigrationError) as failure:
                catalog.initialize(self.path, create=False)
        self.assertIsNone(failure.exception.backup_path)
        self.assertEqual(collision.read_bytes(), b'fictional unrelated existing output')
        self.assertEqual(snapshot(self.path), original)

    def test_real_backup_failure_precedes_every_migration_statement(self):
        original = self.legacy(1)
        real_connect = sqlite3.connect

        class FailingReader(sqlite3.Connection):
            def backup(self, *args, **kwargs):
                raise OSError('fictional backup failure')

        def connect(*args, **kwargs):
            if str(args[0]) == self.path.resolve().as_uri() + '?mode=ro':
                kwargs['factory'] = FailingReader
            return real_connect(*args, **kwargs)

        with patch.object(catalog.sqlite3, 'connect', side_effect=connect), \
                patch.object(catalog, '_migrate_one_to_two') as migration:
            with self.assertRaises(catalog.CatalogMigrationError) as failure:
                catalog.initialize(self.path, create=False)
            self.assertIsNone(failure.exception.backup_path)
            migration.assert_not_called()
        self.assertEqual(snapshot(self.path), original)
        self.assertEqual(list(self.root.glob('*.backup.sqlite3')), [])

    def test_bad_backup_verification_is_removed_before_migration(self):
        original = self.legacy(2)
        with patch.object(catalog, '_verify_integrity', side_effect=ValueError('fictional corrupt copy')), \
                patch.object(catalog, '_migrate_two_to_three') as migration:
            with self.assertRaises(catalog.CatalogMigrationError) as failure:
                catalog.initialize(self.path, create=False)
            self.assertIsNone(failure.exception.backup_path)
            migration.assert_not_called()
        self.assertEqual(snapshot(self.path), original)
        self.assertEqual(list(self.root.glob('*.backup.sqlite3')), [])

    def test_full_intermediate_ddl_and_data_failure_roll_back_original_and_keep_backup(self):
        for version in (1, 2):
            with self.subTest(version=version):
                self.path = self.root / f'failed-v{version}.sqlite3'
                original = self.legacy(version)
                migrate = catalog._migrate_two_to_three

                def fail(db):
                    migrate(db)
                    db.execute("UPDATE assets SET workflow_state='reviewed'")
                    raise OSError('fictional failure after intermediate DDL and data')

                with patch.object(catalog, '_migrate_two_to_three', side_effect=fail):
                    with self.assertRaises(catalog.CatalogMigrationError) as failure:
                        catalog.initialize(self.path, create=False)
                backup = Path(failure.exception.backup_path)
                self.assertEqual(snapshot(self.path), original)
                self.assertEqual(snapshot(backup), original)
                retry = catalog.initialize(self.path, create=False)
                self.assertNotEqual(retry['backup_path'], str(backup))
                self.assertEqual(snapshot(backup), original)
                self.assert_original_rows(self.path, version, True)

    def test_invalid_legacy_rows_roll_back_canonical_rebuild(self):
        self.legacy(1)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE assets SET workflow_state='invalid-fictional-state'")
            db.commit()
        original = snapshot(self.path)
        with self.assertRaises(catalog.CatalogMigrationError) as failure:
            catalog.initialize(self.path, create=False)
        self.assertEqual(snapshot(self.path), original)
        self.assertEqual(snapshot(Path(failure.exception.backup_path)), original)

    def test_v4_failure_rolls_back_every_prior_upgrade_step_and_metadata_write(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                self.path = self.root / f'failed-v4-from-{version}.sqlite3'
                original = self.legacy(version)
                migrate = catalog._migrate_three_to_four

                def fail(db):
                    migrate(db)
                    db.execute("UPDATE assets SET workflow_state='organized'")
                    db.execute("INSERT INTO tags VALUES('fictional-failure-tag','Failure','failure',NULL)")
                    db.execute("INSERT INTO collections VALUES('fictional-failure-collection','Failure','failure')")
                    db.execute("INSERT INTO collection_members VALUES("
                               "'fictional-failure-collection','fictional-asset',0)")
                    raise OSError('fictional failure after v4 DDL and data')

                with patch.object(catalog, '_migrate_three_to_four', side_effect=fail), \
                        patch.object(catalog, '_verified_backup', wraps=catalog._verified_backup) as backup:
                    with self.assertRaises(catalog.CatalogMigrationError) as failure:
                        catalog.initialize(self.path, create=False)
                    backup.assert_called_once_with(self.path, version)
                saved = Path(failure.exception.backup_path)
                self.assertEqual(snapshot(self.path), original)
                self.assertEqual(snapshot(saved), original)
                self.assert_original_rows(self.path, version, True)
                self.assertEqual(len(list(self.root.glob(f'{self.path.name}*.backup.sqlite3'))), 1)
                retry = catalog.initialize(self.path, create=False)
                self.assertNotEqual(retry['backup_path'], str(saved))
                self.assertEqual(snapshot(saved), original)
                self.assert_original_rows(self.path, version, True)

    def test_v3_upgrade_preserves_metadata_without_recreating_v3_tables(self):
        original = self.legacy(3)
        with patch.object(catalog, '_migrate_two_to_three', side_effect=AssertionError('v3 already exists')), \
                patch.object(catalog, '_migrate_three_to_four', wraps=catalog._migrate_three_to_four) as upgrade:
            result = catalog.initialize(self.path, create=False)
            upgrade.assert_called_once()
        self.assertEqual(snapshot(Path(result['backup_path'])), original)
        self.assert_original_rows(self.path, 3, True)

    def test_noncanonical_collection_keys_checks_and_delete_actions_are_refused(self):
        mutations = {
            'missing-name-unique': catalog.COLLECTIONS_SCHEMA.replace(
                'normalized_name TEXT NOT NULL UNIQUE', 'normalized_name TEXT NOT NULL'),
            'missing-member-unique': catalog.COLLECTIONS_SCHEMA.replace(
                'PRIMARY KEY(collection_id,asset_id)', 'PRIMARY KEY(collection_id,position)'),
            'missing-order-unique': catalog.COLLECTIONS_SCHEMA.replace(
                ',\n    UNIQUE(collection_id,position)', ''),
            'negative-order': catalog.COLLECTIONS_SCHEMA.replace('position>=0', 'position>=-1'),
            'fractional-order': catalog.COLLECTIONS_SCHEMA.replace("typeof(position)='integer' AND ", ''),
            'asset-delete-action': catalog.COLLECTIONS_SCHEMA.replace(
                'REFERENCES assets(asset_id) ON DELETE CASCADE', 'REFERENCES assets(asset_id) ON DELETE RESTRICT'),
            'collection-delete-action': catalog.COLLECTIONS_SCHEMA.replace(
                'REFERENCES collections(collection_id) ON DELETE CASCADE',
                'REFERENCES collections(collection_id) ON DELETE RESTRICT'),
        }
        for name, schema in mutations.items():
            with self.subTest(name=name):
                self.path = self.root / f'forged-v4-{name}.sqlite3'
                original = self.legacy(4, populated=False, sql=catalog.SCHEMA_V3 + schema)
                before = self.path.read_bytes()
                with patch.object(catalog, '_verified_backup', wraps=catalog._verified_backup) as backup, \
                        patch.object(catalog, '_migrate_three_to_four', wraps=catalog._migrate_three_to_four) as upgrade:
                    with self.assertRaisesRegex(ValueError, 'declarations do not match'):
                        catalog.initialize(self.path, create=False)
                    backup.assert_not_called()
                    upgrade.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(snapshot(self.path), original)
                self.assertEqual(list(self.root.glob(f'{self.path.name}*.backup.sqlite3')), [])

    def test_writer_is_reserved_before_backup_and_committed_wal_rows_are_copied(self):
        original = self.legacy(2)
        with contextlib.closing(sqlite3.connect(self.path)) as live:
            self.assertEqual(live.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            live.execute("UPDATE assets SET byte_size=29")
            live.commit()
            original = snapshot(self.path)
            real_backup = catalog._verified_backup

            def guarded_backup(path, version):
                with contextlib.closing(sqlite3.connect(path, timeout=0)) as rival:
                    with self.assertRaises(sqlite3.OperationalError):
                        rival.execute('BEGIN IMMEDIATE')
                return real_backup(path, version)

            with patch.object(catalog, '_verified_backup', side_effect=guarded_backup):
                result = catalog.initialize(self.path, create=False)
            self.assertEqual(snapshot(Path(result['backup_path'])), original)
            self.assertEqual(live.execute('SELECT byte_size FROM assets').fetchone()[0], 29)
            self.assertEqual(live.execute('PRAGMA journal_mode').fetchone()[0], 'wal')

    def test_existing_open_refuses_missing_unversioned_unknown_and_future_without_creation(self):
        missing = self.root / 'missing-directory' / 'missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            catalog.initialize(missing, create=False)
        self.assertFalse(missing.parent.exists())
        for name, script in [('empty',''), ('unknown','CREATE TABLE user_data(value TEXT);'),
                             ('future','PRAGMA user_version=99;')]:
            with self.subTest(name=name):
                path = self.root / f'{name}.sqlite3'
                with contextlib.closing(sqlite3.connect(path)) as db:
                    db.executescript(script)
                original = snapshot(path)
                with self.assertRaises(ValueError):
                    catalog.initialize(path, create=False)
                self.assertEqual(snapshot(path), original)
                self.assertEqual(list(self.root.glob(f'{name}*.backup.sqlite3')), [])
        empty = self.root / 'empty.sqlite3'
        self.assertTrue(catalog.initialize(empty)['created'])

    def test_schema_claim_missing_fk_partial_predicate_check_unique_or_trigger_body_is_refused(self):
        mutations = [
            (2, catalog.SCHEMA_V2.replace('source_id TEXT REFERENCES sources(source_id)', 'source_id TEXT')),
            (2, catalog.SCHEMA_V2.replace('WHERE asset_id IS NOT NULL', "WHERE disposition='indexed'")),
            (2, catalog.SCHEMA_V2.replace('CHECK (byte_size >= 0)', 'CHECK (byte_size >= -1)')),
            (3, catalog.SCHEMA_V3.replace('normalized_name TEXT NOT NULL UNIQUE', 'normalized_name TEXT NOT NULL')),
            (3, catalog.SCHEMA_V3.replace("BEGIN SELECT RAISE(ABORT,'Tag name collides with alias'); END;",
                                       'BEGIN SELECT 1; END;')),
            (3, catalog.SCHEMA_V3.replace('FOREIGN KEY(entity_id,entity_type)', 'FOREIGN KEY(entity_id,normalized_alias)')),
        ]
        for index, (version, script) in enumerate(mutations):
            with self.subTest(index=index):
                self.path = self.root / f'forged-{index}.sqlite3'
                self.legacy(version, populated=False, sql=script)
                original = snapshot(self.path)
                with self.assertRaises(ValueError):
                    catalog.initialize(self.path, create=False)
                self.assertEqual(snapshot(self.path), original)
                self.assertEqual(list(self.root.glob(f'forged-{index}*.backup.sqlite3')), [])

    def test_generated_columns_are_refused_before_backup_or_migration(self):
        for version in (1, 2, 3, 4):
            for storage, hidden in (('VIRTUAL', 2), ('STORED', 3)):
                with self.subTest(version=version, storage=storage):
                    self.path = self.root / f'generated-v{version}-{storage}.sqlite3'
                    schema = {1: LEGACY_V1, 2: catalog.SCHEMA_V2,
                              3: catalog.SCHEMA_V3, 4: catalog.SCHEMA}[version]
                    original = self.legacy(version, sql=schema +
                        'ALTER TABLE assets ADD COLUMN unexpected_value TEXT '
                        f'GENERATED ALWAYS AS (current_path) {storage};')
                    before = self.path.read_bytes()
                    with contextlib.closing(sqlite3.connect(self.path)) as db:
                        # Reproduce the omission that previously let these pass.
                        self.assertNotIn('unexpected_value',
                                         [row[1] for row in db.execute('PRAGMA table_info(assets)')])
                        self.assertEqual(db.execute('PRAGMA table_xinfo(assets)').fetchall()[-1][6],
                                         hidden)
                        self.assertEqual(db.execute('SELECT unexpected_value FROM assets').fetchone(),
                                         ('/fictional.png',))
                    with patch.object(catalog, '_verified_backup', wraps=catalog._verified_backup) as backup, \
                            patch.object(catalog, '_migrate_one_to_two', wraps=catalog._migrate_one_to_two) as v1, \
                            patch.object(catalog, '_migrate_two_to_three', wraps=catalog._migrate_two_to_three) as v2:
                        with self.assertRaisesRegex(ValueError, 'generated/hidden columns'):
                            catalog.initialize(self.path, create=False)
                        backup.assert_not_called()
                        v1.assert_not_called()
                        v2.assert_not_called()
                    self.assertEqual(self.path.read_bytes(), before)
                    self.assertEqual(snapshot(self.path), original)
                    self.assertEqual(list(self.root.glob(f'{self.path.name}*.backup.sqlite3')), [])

    def test_unique_index_collations_and_directions_are_refused_before_backup_or_migration(self):
        for version in (2, 3, 4):
            schema = {2: catalog.SCHEMA_V2, 3: catalog.SCHEMA_V3, 4: catalog.SCHEMA}[version]
            mutations = {
                'path-collation': schema.replace('current_path TEXT NOT NULL UNIQUE',
                                                'current_path TEXT NOT NULL UNIQUE COLLATE NOCASE'),
                'partial-collation': schema.replace('ON source_entries(asset_id)',
                                                   'ON source_entries(asset_id COLLATE NOCASE)'),
                'partial-direction': schema.replace('ON source_entries(asset_id)',
                                                   'ON source_entries(asset_id DESC)'),
            }
            for name, script in mutations.items():
                with self.subTest(version=version, mutation=name):
                    self.path = self.root / f'index-v{version}-{name}.sqlite3'
                    original = self.legacy(version, sql=script)
                    before = self.path.read_bytes()
                    with patch.object(catalog, '_verified_backup', wraps=catalog._verified_backup) as backup, \
                            patch.object(catalog, '_migrate_two_to_three', wraps=catalog._migrate_two_to_three) as migration:
                        with self.assertRaisesRegex(ValueError, 'declarations do not match'):
                            catalog.initialize(self.path, create=False)
                        backup.assert_not_called()
                        migration.assert_not_called()
                    self.assertEqual(self.path.read_bytes(), before)
                    self.assertEqual(snapshot(self.path), original)
                    self.assertEqual(list(self.root.glob(f'{self.path.name}*.backup.sqlite3')), [])

    def test_legacy_v1_path_uniqueness_policy_is_canonicalized(self):
        self.legacy(1, sql=LEGACY_V1.replace('current_path TEXT NOT NULL UNIQUE',
                                           'current_path TEXT NOT NULL UNIQUE COLLATE NOCASE'))
        original = snapshot(self.path)
        result = catalog.initialize(self.path, create=False)
        self.assertEqual(snapshot(Path(result['backup_path'])), original)
        self.assert_original_rows(self.path, 1, True)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            catalog._validate_catalog_schema(db, 4)
            # The historical declaration is rebuilt with canonical equality.
            for name in ('/fictional/Fictional.png', '/fictional/fictional.png'):
                db.execute('INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) '
                           'VALUES(?,?,?,?,?)', (name, name, 'image/png', 'fictional-hash', 12))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 3)

    def test_cli_init_reports_locatable_verified_original_backup(self):
        original = self.legacy(2)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['init', str(self.path)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['database'], str(self.path))
        self.assertEqual(result['schema_version'], 4)
        self.assertEqual(result['previous_version'], 2)
        self.assertTrue(result['migrated'])
        self.assertFalse(result['created'])
        self.assertEqual(snapshot(Path(result['backup_path'])), original)


if __name__ == '__main__':
    unittest.main()
