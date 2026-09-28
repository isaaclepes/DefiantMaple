import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from benchmarks.generate_catalog import generate
from defiantmaple.archive import Limits, inspect_archive, unsafe_path
from defiantmaple.catalog import SCHEMA_VERSION, connect, duplicates, index_file, initialize, list_assets
from defiantmaple.media import sniff
from defiantmaple.__main__ import main

PNG = b'\x89PNG\r\n\x1a\n' + b'fixture payload (not a decoded image)'


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'catalog.sqlite3'

    def archive(self, entries, compression=zipfile.ZIP_STORED):
        path = self.root / 'export.zip'
        with zipfile.ZipFile(path, 'w', compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return path

    def test_type_hints_ignore_extensions(self):
        for data, extension in [(PNG, 'png'), (b'\xff\xd8\xffabc', 'jpg'),
                                (b'GIF89aabc', 'gif'), (b'RIFF0000WEBP', 'webp'),
                                (b'\x00\x00\x00\x18ftypmp42', 'mp4')]:
            with self.subTest(extension=extension):
                self.assertEqual(sniff(data).extension, extension)
        for data in (b'', b'not an image.jpg', b'RIFF0000WAVE', b'0000ftypavif'):
            self.assertIsNone(sniff(data))

    def test_preview_preserves_paths_and_never_extracts(self):
        path = self.archive([('uuid/content.jpg', PNG), ('uuid.dat', PNG),
                             ('notes.txt', b'hello'), ('inner.dat', b'PK\x03\x04xx')])
        before = set(self.root.iterdir())
        result = inspect_archive(path)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertEqual(result['items'][0]['original_member_path'], 'uuid/content.jpg')
        self.assertEqual(result['items'][1]['proposed_name'], 'asset_00002.png')
        self.assertIn('decoder_validation_pending', result['items'][0]['warnings'])
        self.assertFalse(result['items'][2]['candidate'])
        self.assertIn('nested_archive_not_expanded', result['items'][3]['warnings'])

    def test_traversal_and_cross_platform_paths_are_blocked(self):
        for name in ('../escape.png', '/absolute.png', 'C:/evil.png', 'C:evil.png',
                     '..\\evil.png', '\\\\server\\file', 'a/../b', 'a:stream', 'a\x00b'):
            with self.subTest(name=name):
                self.assertTrue(unsafe_path(name))
        path = self.archive([('../escape.png', PNG), ('safe.dat', PNG)])
        result = inspect_archive(path)
        self.assertFalse(result['items'][0]['candidate'])
        self.assertTrue(result['items'][1]['candidate'])

    def test_symlink_rejected_without_reading_target(self):
        entry = zipfile.ZipInfo('link.png')
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        result = inspect_archive(self.archive([(entry, PNG)]))
        self.assertIn('link_or_special_file', result['items'][0]['warnings'])
        self.assertFalse(result['items'][0]['candidate'])

    def test_limits_reject_before_probe(self):
        path = self.archive([('one', PNG), ('two', PNG)])
        for policy in (replace(Limits(), archive_bytes=1), replace(Limits(), members=1),
                       replace(Limits(), total_bytes=1)):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                inspect_archive(path, policy)
        report = inspect_archive(path, replace(Limits(), member_bytes=1))
        self.assertIn('member_size_limit', report['items'][0]['warnings'])
        with self.assertRaises(ValueError):
            Limits(prefix_bytes=0)

    def test_compression_bomb_member_not_probed(self):
        path = self.archive([('bomb.png', PNG + b'0' * 100_000)], zipfile.ZIP_DEFLATED)
        result = inspect_archive(path, replace(Limits(), ratio=10))
        self.assertIn('compression_ratio_limit', result['items'][0]['warnings'])
        self.assertFalse(result['items'][0]['candidate'])

    def test_corrupt_member_failure_is_isolated(self):
        path = self.archive([('bad.dat', PNG), ('good.dat', PNG)])
        raw = bytearray(path.read_bytes())
        start = raw.index(PNG)
        raw[start] ^= 255
        path.write_bytes(raw)
        result = inspect_archive(path)
        self.assertIn('probe_failed:BadZipFile', result['items'][0]['warnings'])
        self.assertTrue(result['items'][1]['candidate'])

    def test_catalog_persistence_identity_provenance_and_duplicates(self):
        initialize(self.db)
        one = self.root / 'one.dat'
        two = self.root / 'two.dat'
        one.write_bytes(PNG)
        two.write_bytes(PNG)
        first = index_file(self.db, one)
        initialize(self.db)  # idempotent; does not erase records
        self.assertEqual(first, index_file(self.db, one))
        self.assertNotEqual(first, index_file(self.db, two))
        self.assertEqual(len(list_assets(self.db)), 2)
        self.assertEqual(duplicates(self.db)[0]['asset_count'], 2)
        with connect(self.db) as db:
            details = json.loads(db.execute('SELECT details_json FROM provenance').fetchone()[0])
            self.assertFalse(details['decoder_validated'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM provenance').fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE assets SET workflow_state='invalid'")
        self.assertEqual(one.read_bytes(), PNG)
        self.assertEqual(len(list_assets(self.db, limit=1, offset=1)), 1)

    def test_changed_content_requires_reconciliation(self):
        initialize(self.db)
        path = self.root / 'image.png'
        path.write_bytes(PNG)
        index_file(self.db, path)
        path.write_bytes(PNG + b'changed')
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            index_file(self.db, path)
        self.assertEqual(list_assets(self.db)[0]['byte_size'], len(PNG))

    def test_change_during_read_creates_no_record(self):
        initialize(self.db)
        path = self.root / 'image.png'
        path.write_bytes(PNG)
        with patch('defiantmaple.catalog.fingerprint', side_effect=[1, 1, 1, 2]):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                index_file(self.db, path)
        self.assertEqual(list_assets(self.db), [])

    def test_database_rollback(self):
        initialize(self.db)
        with self.assertRaises(RuntimeError):
            with connect(self.db) as db:
                db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                           "VALUES('id','path','image/png','hash',1)")
                raise RuntimeError('interrupted')
        self.assertEqual(list_assets(self.db), [])

    def test_benchmark_fixture_populates_comparison_data_once(self):
        result = generate(self.db, 101, batch_size=13)
        self.assertEqual(result['assets'], 101)
        self.assertEqual(result['catalog_schema_version'], SCHEMA_VERSION)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(
                result['catalog_schema_version'],
                db.execute('PRAGMA user_version').fetchone()[0],
            )
        self.assertEqual(len(list_assets(self.db, limit=1000)), 101)
        self.assertEqual(len(duplicates(self.db)), 1)
        with self.assertRaisesRegex(ValueError, 'must be empty'):
            generate(self.db, 1)

    def test_unknown_database_not_overwritten(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            with db:
                db.execute('CREATE TABLE user_data (value TEXT)')
        with self.assertRaises(ValueError):
            initialize(self.db)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            self.assertIsNotNone(db.execute('SELECT * FROM user_data'))

    def test_read_does_not_create_missing_database(self):
        with self.assertRaises(sqlite3.OperationalError):
            list_assets(self.db)
        self.assertFalse(self.db.exists())

    def test_future_schema_not_downgraded(self):
        initialize(self.db)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            with db:
                db.execute('PRAGMA user_version = 99')
        with self.assertRaises(ValueError):
            initialize(self.db)
        with self.assertRaises(ValueError):
            list_assets(self.db)

    def test_cli_errors_and_json(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['init', str(self.db)]), 0)
        self.assertEqual(json.loads(output.getvalue())['schema_version'], SCHEMA_VERSION)
        bad = self.root / 'bad.zip'
        bad.write_bytes(b'not a zip')
        with contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(main(['inspect-zip', str(bad)]), 1)
        self.assertIn('error', json.loads(output.getvalue()))


if __name__ == '__main__':
    unittest.main()
