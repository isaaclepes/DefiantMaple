"""Generated subprocess launch and spawn-import boundary regressions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from defiantmaple.catalog import connect, index_file, initialize
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


class LightweightLauncherTests(unittest.TestCase):
    def invoke(self, module, arguments, *, environment=None):
        env = os.environ.copy()
        env['QT_QPA_PLATFORM'] = 'offscreen'
        env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
        if environment:
            env.update(environment)
        return subprocess.run([sys.executable, '-B', '-m', module, *arguments], cwd=ROOT,
                              env=env, capture_output=True, text=True, timeout=30)

    def test_launcher_preserves_identity_help_and_argument_refusal(self):
        for module in ('prototypes.qt.app', 'prototypes.qt.launcher'):
            with self.subTest(module=module):
                identity = self.invoke(module, ['--smoke-identity'])
                self.assertEqual(identity.returncode, 0, identity.stderr)
                self.assertEqual(json.loads(identity.stdout), {
                    'application_name': 'DefiantMaple',
                    'desktop_file_name': 'io.github.isaaclepes.DefiantMaple',
                    'window_icon_available': True})
                help_result = self.invoke(module, ['--help'])
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn('--catalog', help_result.stdout)
                self.assertIn('--smoke-worker-thumbnail-id', help_result.stdout)
                refusal = self.invoke(module, ['--not-a-supported-option'])
                self.assertEqual(refusal.returncode, 2)
                self.assertIn('unrecognized arguments', refusal.stderr)
                self.assertEqual(refusal.stdout, '')

    def test_real_spawned_core_workers_do_not_import_qt_or_gallery(self):
        with tempfile.TemporaryDirectory(prefix='dm-launcher-generated-') as name:
            root = Path(name)
            database, cache = root / 'catalog.sqlite3', root / 'cache'
            source = root / 'generated.png'
            Image.new('RGB', (64, 48), (30, 70, 110)).save(source)
            initialize(database)
            aid = index_file(database, source)
            source_before = (source.read_bytes(), source.stat().st_mode, source.stat().st_mtime_ns)
            with connect(database) as db:
                catalog_before = tuple(db.iterdump())
            hooks = root / 'hooks'
            hooks.mkdir()
            markers = root / 'child-markers'
            markers.mkdir()
            # This hook runs in actual spawned interpreters before main replay.
            # A GUI import makes the real decoder/cache operation fail, rather
            # than merely asserting that a simulated run_name skipped imports.
            (hooks / 'sitecustomize.py').write_text('''import os,sys
from pathlib import Path
if '--multiprocessing-fork' in sys.argv:
    Path(os.environ['DM_GENERATED_CHILD_MARKERS'],str(os.getpid())).write_text('spawned')
    class CoreImportBoundary:
        def find_spec(self,fullname,path=None,target=None):
            if fullname=='prototypes.qt.app' or fullname=='PySide6' or fullname.startswith('PySide6.'):
                raise ImportError('Generated core-worker GUI import refusal')
    sys.meta_path.insert(0,CoreImportBoundary())
''')
            result = self.invoke('prototypes.qt.launcher', [
                '--catalog', str(database), '--smoke-cache-root', str(cache),
                '--smoke-worker-thumbnail-id', aid], environment={
                    'PYTHONPATH': str(hooks) + os.pathsep + str(ROOT),
                    'DM_GENERATED_CHILD_MARKERS': str(markers)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'width': 64, 'height': 48})
            self.assertEqual(len(tuple(markers.iterdir())), 3,
                             'Cold gallery delivery must run miss-reader, generator and validated reader')
            self.assertEqual((source.read_bytes(), source.stat().st_mode, source.stat().st_mtime_ns),
                             source_before)
            with connect(database) as db:
                self.assertEqual(tuple(db.iterdump()), catalog_before)
            self.assertEqual(len(tuple(cache.rglob('*.png'))), 1)
            self.assertEqual(len(tuple(cache.rglob('*.json'))), 1)
