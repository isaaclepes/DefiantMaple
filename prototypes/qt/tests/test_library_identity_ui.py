"""Generated Qt identity disclosures, raw admission, and freshness regressions."""
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from defiantmaple import catalog
from defiantmaple.cached_preview import capture_target
from prototypes.qt.app import AssetModel
from prototypes.qt.comparison import _revision, _scratch_isolation
from prototypes.qt.preview import _fresh_original_admission
from prototypes.qt.gallery_filters import CatalogGateway, OperationSpec
from prototypes.qt.recovery_qt import RecoveryDialog, RecoveryWorker, _identity


def _count(db, _context):
    return db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]


class LibraryIdentityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / 'live.sqlite3'
        self.media = self.root / 'generated.png'
        Image.new('RGB', (2, 2), 'purple').save(self.media)
        catalog.initialize(self.database)
        self.asset_id = catalog.index_file(self.database, self.media)
        with catalog.connect(self.database) as db:
            self.library_id = catalog.library_identity(db)
            self.asset = dict(db.execute('SELECT * FROM assets WHERE asset_id=?', (self.asset_id,)).fetchone())

    def dialog(self):
        dialog = RecoveryDialog(self.database, (self.root / 'cache',))
        self.addCleanup(dialog.close)
        return dialog

    def corrupt_empty_identity(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('DROP TRIGGER library_identity_no_delete')
            db.execute('DELETE FROM library_identity')
            db.execute("""CREATE TRIGGER library_identity_no_delete BEFORE DELETE ON library_identity
                        BEGIN SELECT RAISE(ABORT,'Library identity is immutable'); END;""")
            db.commit()

    def test_reports_distinguish_legacy_absence_assignment_and_modern_preservation(self):
        legacy = {'manifest': {'package_version': 1, 'catalog_schema': 6},
                  'catalog': {'schema_version': 6, 'library_id': None, 'identity_status': 'legacy_absent'}}
        text = RecoveryDialog._format_result('inspect', legacy)
        self.assertIn('absent in legacy package', text)
        self.assertIn('Each restore assigns a fresh UUID', text)
        assigned = {'manifest': legacy['manifest'], 'catalog': str(self.root/'restored.sqlite3'),
                    'restored': {'schema_version': 7, 'library_id': self.library_id, 'identity_status': 'assigned_legacy'}}
        text = RecoveryDialog._format_result('restore', assigned)
        self.assertIn(self.library_id, text)
        self.assertIn('legacy package had no identity to preserve', text)
        modern = {'manifest': {'package_version': 2, 'catalog_schema': 7},
                  'catalog': str(self.root/'modern.sqlite3'),
                  'restored': {'schema_version': 7, 'library_id': self.library_id, 'identity_status': 'stored'}}
        text = RecoveryDialog._format_result('restore', modern)
        self.assertIn(self.library_id, text)
        self.assertIn('Stored library UUID preserved exactly', text)
        self.assertIn('browse-only', text)

    def test_restore_confirmation_discloses_legacy_assignment_and_defaults_to_no(self):
        dialog = self.dialog()
        package = self.root/'selected.dmbackup'
        target = self.root/'new.sqlite3'
        with patch('prototypes.qt.recovery_qt.QFileDialog.getOpenFileName', return_value=(str(package), '')), \
             patch('prototypes.qt.recovery_qt.QFileDialog.getSaveFileName', return_value=(str(target), '')), \
             patch('prototypes.qt.recovery_qt.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as confirm, \
             patch.object(dialog, '_start') as start:
            dialog.restore()
            text = confirm.call_args.args[2]
            self.assertIn('each restore assigns a fresh UUID', text)
            self.assertIn('Modern backups preserve their library UUID', text)
            self.assertEqual(confirm.call_args.args[-1], QMessageBox.StandardButton.No)
            start.assert_not_called()
            confirm.return_value = QMessageBox.StandardButton.Yes
            dialog.restore()
            start.assert_called_once_with('restore', package=package, output=target)
        self.assertFalse(target.exists())

    def test_same_library_uuid_copy_does_not_bypass_captured_inode_freshness(self):
        captured = _identity(self.database)
        replacement = self.root/'copy.sqlite3'
        shutil.copyfile(self.database, replacement)
        os.replace(replacement, self.database)
        with catalog.connect(self.database) as db:
            self.assertEqual(catalog.library_identity(db), self.library_id)
        self.assertNotEqual(_identity(self.database), captured)
        worker = RecoveryWorker('mapping', self.database, captured, ())
        results = []
        worker.delivered.connect(lambda status, value: results.append((status, value)))
        worker.run()
        self.assertEqual(results[0][0], 'error')
        self.assertIn('Library file changed', results[0][1])
        with self.assertRaisesRegex(ValueError, 'Catalog changed'):
            _fresh_original_admission(self.database, captured, self.asset)

    def test_raw_qt_readers_refuse_empty_identity_before_original_access(self):
        self.corrupt_empty_identity()
        target = capture_target(self.asset)
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path == self.media:
                self.fail('Invalid identity opened original media')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            with self.assertRaisesRegex(ValueError, 'singleton'):
                _fresh_original_admission(self.database, _identity(self.database), self.asset)
            with self.assertRaisesRegex(ValueError, 'singleton'):
                _revision(self.database, target, time.monotonic()+2)
            with self.assertRaisesRegex(ValueError, 'singleton'):
                _scratch_isolation(self.database, self.root/'scratch', self.root/'cache', target, time.monotonic()+2)
            with self.assertRaisesRegex(ValueError, 'singleton'):
                AssetModel(self.database)
        gateway = CatalogGateway(self.database, {'count': OperationSpec(False, _count)})
        failures, ready = [], []
        gateway.failed.connect(failures.append)
        gateway.ready.connect(lambda: ready.append(True))
        gateway.run()
        self.assertEqual(ready, [])
        self.assertEqual(len(failures), 1)
        self.assertIn('singleton', failures[0])

    def test_stale_worker_reply_does_not_publish_identity_or_replace_report(self):
        dialog = self.dialog()
        dialog.report.setPlainText('current selection report')
        stale = SimpleNamespace(operation='restore')
        dialog._delivered(stale, 'ok', {'restored': {'library_id': self.library_id}})
        self.assertEqual(dialog.report.toPlainText(), 'current selection report')
        self.assertEqual(dialog.database, self.database)
