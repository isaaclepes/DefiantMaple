"""Generated identity/migration/legacy recovery regressions; no user catalogs."""
from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from defiantmaple import catalog, recovery
from defiantmaple.recovery_storage import private_local_parent


class LibraryIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'library.sqlite3'

    def dump(self, path):
        with closing(sqlite3.connect(path)) as db:
            return tuple(db.iterdump()), db.execute('PRAGMA user_version').fetchone()[0], db.execute('PRAGMA application_id').fetchone()[0]

    def identity(self, path=None):
        with catalog.connect(path or self.path) as db:
            return catalog.library_identity(db)

    def legacy(self, *, pending=False):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(catalog.SCHEMA_V6)
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,enabled,health,health_detail) "
                       "VALUES('source','Generated','/generated/media','inbox',0,'paused',?)",
                       (catalog.restored_root_review_detail('source', '/generated/media') if pending else None,))
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at) "
                       "VALUES('asset','/generated/standalone.png','image/png','generated',1,'needs_review','original')")
            if pending:
                db.execute(f'PRAGMA application_id={catalog.RESTORE_PENDING_APPLICATION_ID}')
            db.commit()
        return self.path.read_bytes()

    def package_legacy(self):
        original = self.legacy(pending=True)
        manifest = {'kind': 'metadata-only', 'package_version': 1, 'catalog_schema': 6,
                    'snapshot_bytes': len(original), 'snapshot_sha256': hashlib.sha256(original).hexdigest(),
                    'created_utc': '2026-10-16T00:00:00+00:00', 'omissions': recovery.OMISSIONS,
                    'source_paths_unverified': True}
        raw = recovery._canonical_json(manifest)
        package = self.root / 'legacy.dmbackup'
        package.write_bytes(recovery.HEADER.pack(recovery.MAGIC, len(raw), len(original)) + raw + original)
        return package

    def require_native(self):
        try:
            with private_local_parent(self.root / 'probe'):
                pass
        except ValueError as exc:
            if str(exc) in ('Recovery publication has no reviewed native adapter on this platform',
                            'Recovery requires a verified durable local filesystem'):
                self.skipTest(f'Native package publication requires reviewed Linux PCIe NVMe adapter: {exc}')
            raise

    def test_creation_reopen_relocation_and_copy_preserve_identity(self):
        catalog.initialize(self.path)
        original = self.identity()
        parsed = uuid.UUID(original)
        self.assertEqual(parsed.version, 4)
        self.assertEqual(parsed.variant, uuid.RFC_4122)
        catalog.initialize(self.path, create=False)
        self.assertEqual(self.identity(), original)
        moved = self.root / 'moved.sqlite3'
        self.path.rename(moved)
        self.assertEqual(self.identity(moved), original)
        copied = self.root / 'copy.sqlite3'
        shutil.copyfile(moved, copied)
        self.assertEqual(self.identity(copied), original)
        another = self.root / 'other.sqlite3'
        catalog.initialize(another)
        self.assertNotEqual(self.identity(another), original)

    def test_migration_preserves_verified_original_backup_prior_backups_and_pending_holds(self):
        self.legacy(pending=True)
        original = self.dump(self.path)
        historical = self.root / 'library.sqlite3.v5.historical.backup.sqlite3'
        historical.write_bytes(b'prior recovery point')
        with closing(sqlite3.connect(self.path)) as db:
            old_rows = {table: db.execute(f'SELECT * FROM {table}').fetchall()
                        for table in ('assets', 'sources')}
        result = catalog.initialize(self.path, create=False)
        self.assertEqual((result['previous_version'], result['schema_version']), (6, 7))
        self.assertEqual(self.dump(Path(result['backup_path'])), original)
        self.assertEqual(historical.read_bytes(), b'prior recovery point')
        with catalog.connect(self.path) as db:
            self.assertEqual(catalog.catalog_state(db), 'restore_pending')
            for table, rows in old_rows.items():
                self.assertEqual([tuple(row) for row in db.execute(f'SELECT * FROM {table}')], rows)
            with self.assertRaisesRegex(ValueError, 'browse-only'):
                catalog.require_original_access(db)
        self.assertEqual(self.identity(), self.identity())

    def test_failed_migration_rolls_back_identity_and_preserves_backup(self):
        original = self.legacy()
        original_dump = self.dump(self.path)
        real = catalog._migrate_six_to_seven
        def fail_after_identity(db):
            real(db)
            raise ValueError('injected after identity')
        with patch.object(catalog, '_migrate_six_to_seven', side_effect=fail_after_identity):
            with self.assertRaises(catalog.CatalogMigrationError) as caught:
                catalog.initialize(self.path, create=False)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.dump(Path(caught.exception.backup_path)), original_dump)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 6)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='library_identity'").fetchone())

    def test_identity_is_immutable_including_replace_with_recursive_triggers_off(self):
        catalog.initialize(self.path)
        identity = self.identity()
        with catalog.connect(self.path) as db:
            db.execute('PRAGMA recursive_triggers=OFF')
            for sql in ("UPDATE library_identity SET library_id=?", "DELETE FROM library_identity",
                        "INSERT OR REPLACE INTO library_identity VALUES(1,?)",
                        "REPLACE INTO library_identity VALUES(1,?)",
                        "INSERT INTO library_identity VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET library_id=excluded.library_id"):
                with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
                    db.execute(sql, (str(uuid.uuid4()),) if '?' in sql else ())
            self.assertEqual(catalog.library_identity(db), identity)

    def test_missing_invalid_or_unauthenticated_identity_refuses_without_repair(self):
        for mutation in ('empty', 'invalid', 'nil', 'uppercase', 'blob', 'duplicate', 'trigger'):
            with self.subTest(mutation=mutation):
                self.path = self.root / f'{mutation}.sqlite3'
                catalog.initialize(self.path)
                with closing(sqlite3.connect(self.path)) as db:
                    if mutation == 'trigger':
                        db.execute('DROP TRIGGER library_identity_no_update')
                    else:
                        db.execute('DROP TRIGGER library_identity_no_update')
                        db.execute('DROP TRIGGER library_identity_no_delete')
                        db.execute('DROP TRIGGER library_identity_no_replace')
                        db.execute('PRAGMA ignore_check_constraints=ON')
                        if mutation == 'empty':
                            db.execute('DELETE FROM library_identity')
                        elif mutation == 'duplicate':
                            db.execute('INSERT INTO library_identity VALUES(2,?)', (str(uuid.uuid4()),))
                        else:
                            value = {'invalid': 'x'*36, 'nil': str(uuid.UUID(int=0)),
                                     'uppercase': '12345678-ABCD-4234-8234-123456789ABC', 'blob': b'x'*36}[mutation]
                            db.execute('UPDATE library_identity SET library_id=?', (value,))
                        # Restore exact declarations so tests exercise data validation too.
                        for statement in catalog.LIBRARY_IDENTITY_SCHEMA.split('CREATE TRIGGER ')[1:]:
                            db.executescript('CREATE TRIGGER ' + statement.split('PRAGMA user_version')[0])
                    db.commit()
                original = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    catalog.initialize(self.path, create=False)
                with self.assertRaises(ValueError):
                    with catalog.connect(self.path):
                        pass
                with self.assertRaises(ValueError):
                    recovery._verify_snapshot(self.path)
                self.assertEqual(self.path.read_bytes(), original)

    def test_ordinary_identity_read_never_runs_integrity_or_asset_scan(self):
        catalog.initialize(self.path)
        with catalog.connect(self.path) as db:
            statements = []
            db.set_trace_callback(statements.append)
            catalog.library_identity(db)
        self.assertFalse(any('integrity_check' in sql.lower() or 'from assets' in sql.lower()
                             for sql in statements))

    def test_manifest_pair_dispatch_and_identity_validation(self):
        package = self.package_legacy()
        header = package.read_bytes()[:recovery.HEADER.size]
        _, size, length = recovery.HEADER.unpack(header)
        raw = package.read_bytes()[recovery.HEADER.size:recovery.HEADER.size+size]
        old = recovery._manifest(raw, length)
        for version, schema in ((1, 7), (2, 6), (3, 7), (True, 6), (1, True)):
            candidate = dict(old, package_version=version, catalog_schema=schema)
            with self.subTest(version=version, schema=schema), self.assertRaises(ValueError):
                recovery._manifest(recovery._canonical_json(candidate), length)
        modern = dict(old, package_version=2, catalog_schema=7, library_id=str(uuid.uuid4()))
        self.assertEqual(recovery._manifest(recovery._canonical_json(modern), length), modern)
        for invalid in (None, str(uuid.UUID(int=0)), modern['library_id'].upper(), 'x'*36):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                recovery._manifest(recovery._canonical_json(dict(modern, library_id=invalid)), length)

    def test_legacy_inspection_is_unchanged_and_each_restore_assigns_distinct_identity(self):
        self.require_native()
        package = self.package_legacy()
        before = package.read_bytes()
        inspected = recovery.inspect_package(package)
        self.assertEqual(inspected['catalog']['identity_status'], 'legacy_absent')
        self.assertIsNone(inspected['catalog']['library_id'])
        before_fingerprint = recovery._logical_fingerprint(self.path)
        identities = []
        for number in (1, 2):
            target = self.root / f'restored-{number}.sqlite3'
            result = recovery.restore_metadata(package, target, cache_roots=(), live_catalog=None)
            identities.append(self.identity(target))
            self.assertEqual(result['restored']['identity_status'], 'assigned_legacy')
            self.assertEqual(result['restored']['library_id'], identities[-1])
            self.assertEqual(result['restored']['state'], 'restore_pending')
            self.assertEqual(recovery._logical_fingerprint(target, exclude_identity=True), before_fingerprint)
            with catalog.connect(target) as db:
                source = db.execute('SELECT enabled,health,health_detail FROM sources').fetchone()
                self.assertEqual(tuple(source), (0, 'paused', catalog.restored_root_review_detail('source', '/generated/media')))
                with self.assertRaisesRegex(ValueError, 'browse-only'):
                    catalog.require_original_access(db)
        self.assertNotEqual(*identities)
        self.assertEqual(package.read_bytes(), before)
        self.assertEqual(list(self.root.glob('*.backup.sqlite3')), [])

    def test_modern_package_binds_and_preserves_identity_and_rejects_mismatch(self):
        self.require_native()
        catalog.initialize(self.path)
        package = self.root / 'modern.dmbackup'
        result = recovery.backup_metadata(self.path, package, cache_roots=())
        self.assertEqual((result['manifest']['package_version'], result['manifest']['catalog_schema']), (2, 7))
        expected = self.identity()
        self.assertEqual(result['manifest']['library_id'], expected)
        restored = self.root / 'modern-restored.sqlite3'
        result = recovery.restore_metadata(package, restored, cache_roots=(), live_catalog=self.path)
        self.assertEqual(result['restored']['identity_status'], 'stored')
        self.assertEqual(self.identity(restored), expected)
        self.assertEqual(recovery._logical_fingerprint(restored), recovery._logical_fingerprint(self.path))
        data = package.read_bytes()
        _, size, length = recovery.HEADER.unpack(data[:recovery.HEADER.size])
        manifest = recovery._manifest(data[recovery.HEADER.size:recovery.HEADER.size+size], length)
        raw = recovery._canonical_json(dict(manifest, library_id=str(uuid.uuid4())))
        bad = self.root / 'mismatch.dmbackup'
        bad.write_bytes(recovery.HEADER.pack(recovery.MAGIC, len(raw), length) + raw + data[recovery.HEADER.size+size:])
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            recovery.inspect_package(bad)
        refused = self.root / 'refused.sqlite3'
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            recovery.restore_metadata(bad, refused, cache_roots=(), live_catalog=self.path)
        self.assertFalse(refused.exists())

    def test_backup_refuses_invalid_identity_before_claiming_package(self):
        self.require_native()
        catalog.initialize(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER library_identity_no_delete')
            db.execute('DELETE FROM library_identity')
            db.execute("""CREATE TRIGGER library_identity_no_delete BEFORE DELETE ON library_identity
                        BEGIN SELECT RAISE(ABORT,'Library identity is immutable'); END;""")
            db.commit()
        before = self.path.read_bytes()
        target = self.root / 'invalid.dmbackup'
        with self.assertRaisesRegex(ValueError, 'singleton'):
            recovery.backup_metadata(self.path, target, cache_roots=())
        self.assertFalse(target.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_legacy_restore_migration_failure_preserves_package_and_no_destination(self):
        self.require_native()
        package = self.package_legacy()
        before = package.read_bytes()
        stage = self.root / '.owned-stage.sqlite3'
        target = self.root / 'failed.sqlite3'
        real = recovery._migrate_six_to_seven
        def fail_after_identity(db):
            real(db)
            raise ValueError('injected legacy-stage migration failure')
        import threading
        try:
            with patch.object(recovery, '_migrate_six_to_seven', side_effect=fail_after_identity):
                with self.assertRaisesRegex(ValueError, 'legacy-stage'):
                    recovery._restore_worker(package, target, stage, (), None, threading.Event())
            self.assertFalse(target.exists())
            self.assertEqual(package.read_bytes(), before)
            with closing(sqlite3.connect(stage)) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 6)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='library_identity'").fetchone())
            self.assertEqual(list(self.root.glob('*.backup.sqlite3')), [])
        finally:
            stage.unlink(missing_ok=True)

    def test_raw_cached_and_gallery_admission_refuses_empty_identity_before_data_reads(self):
        from defiantmaple.cached_preview import CachedTarget, _asset_snapshot, fresh_generation_refusal
        from defiantmaple.gallery_query import _require_snapshot
        catalog.initialize(self.path)
        target = CachedTarget(str(uuid.uuid4()), 'a'*64, 1, 'image/png', 0,
                              str((self.root / 'generated.png').resolve()), None)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER library_identity_no_delete')
            db.execute('DELETE FROM library_identity')
            db.execute("""CREATE TRIGGER library_identity_no_delete BEFORE DELETE ON library_identity
                        BEGIN SELECT RAISE(ABORT,'Library identity is immutable'); END;""")
            db.commit()
        with self.assertRaisesRegex(ValueError, 'singleton'):
            _asset_snapshot(self.path, target, time.monotonic()+2)
        reason = fresh_generation_refusal(self.path, target, {'source_id': None})
        self.assertIn('singleton', reason)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            context = SimpleNamespace(data_version=1, file_identity=(1, 2), check=lambda: None)
            with self.assertRaisesRegex(ValueError, 'singleton'):
                _require_snapshot(db, context)
            with self.assertRaisesRegex(ValueError, 'singleton'):
                catalog.require_original_access(db)

    def test_valid_pending_raw_catalog_admission_still_allows_metadata(self):
        from defiantmaple.gallery_query import _require_snapshot
        catalog.initialize(self.path)
        expected = self.identity()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(f'PRAGMA application_id={catalog.RESTORE_PENDING_APPLICATION_ID}')
            db.execute('BEGIN')
            context = SimpleNamespace(data_version=1, file_identity=(1, 2), check=lambda: None)
            _require_snapshot(db, context)
            self.assertEqual(catalog.require_current_catalog(db), expected)
            with self.assertRaisesRegex(ValueError, 'browse-only'):
                catalog.require_original_access(db)
