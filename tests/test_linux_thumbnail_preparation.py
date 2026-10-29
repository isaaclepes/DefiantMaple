"""Actual Linux managed writer/read integration with isolated generated state."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from defiantmaple import catalog, cached_preview, thumbnail


@unittest.skipUnless(sys.platform == 'linux', 'Managed preparation is Linux-first')
class LinuxManagedThumbnailTests(unittest.TestCase):
    def setUp(self):
        from defiantmaple import linux_thumbnails
        self.api = linux_thumbnails
        temp = tempfile.TemporaryDirectory(prefix='dm-linux-preparation-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(strict=True)
        self.database, self.cache = self.root / 'catalog.sqlite3', self.root / 'cache'
        catalog.initialize(self.database)
        self.authority = self.root / 'authority'
        factory = patch.object(self.api, 'default_authority_root', return_value=self.authority)
        factory.start()
        self.addCleanup(factory.stop)
        registry = patch('defiantmaple.admission.registry_path', return_value=self.root / 'admission')
        registry.start()
        self.addCleanup(registry.stop)

    def image(self, number=0):
        source = self.root / f'generated-{number}.png'
        Image.new('RGBA', (16, 8), (number, 70, 110, 90)).save(source)
        aid = catalog.index_file(self.database, source)
        with catalog.connect(self.database) as db:
            row = dict(db.execute('SELECT * FROM assets WHERE asset_id=?', (aid,)).fetchone())
        return source, row

    def signature(self, path):
        info = path.stat()
        return (hashlib.sha256(path.read_bytes()).hexdigest(), info.st_mode, info.st_mtime_ns)

    def test_real_generation_commits_then_cache_read_and_revisit_reuse(self):
        source, row = self.image()
        before = self.signature(source), self.signature(self.database)
        original = thumbnail._run_decoder
        with patch.object(thumbnail, '_run_decoder', wraps=original) as decoder:
            result = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
            self.assertFalse(result['cache_hit'])
            self.assertEqual(decoder.call_count, 1)
            self.assertTrue(Path(result['path']).is_relative_to(self.cache / cached_preview.MANAGED_NAMESPACE))
            again = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
            self.assertTrue(again['cache_hit'])
            self.assertEqual(decoder.call_count, 1)
        read = cached_preview.read_cached_preview(self.database, cached_preview.capture_target(row), self.cache, 144)
        self.assertEqual(read.status, 'ready', read.message)
        self.assertEqual((read.width, read.height), (16, 8))
        self.assertFalse((self.cache / cached_preview.MANAGED_NAMESPACE / '.managed-pending-v1.json').exists())
        self.assertEqual((self.signature(source), self.signature(self.database)), before)
        self.assertEqual(list(self.cache.rglob('.manifest-stage.json')), [])

    def test_exact_requested_edge_and_custom_policy_reuse(self):
        source, row = self.image()
        first = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=64)
        second = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=128)
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(second['max_edge'], 128)
        limits = thumbnail.ThumbnailLimits(max_source_bytes=1024 ** 2, max_dimension=1000, max_pixels=1000000)
        with patch.object(thumbnail, '_run_decoder', wraps=thumbnail._run_decoder) as decoder:
            custom = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=128, limits=limits)
            again = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=128, limits=limits)
            self.assertFalse(custom['cache_hit'])
            self.assertTrue(again['cache_hit'])
            self.assertEqual(decoder.call_count, 1)

    def test_registered_source_placement_refuses_before_bootstrap(self):
        from defiantmaple.sources import add_source
        source, row = self.image()
        watched = self.root / 'watched'
        watched.mkdir()
        add_source(self.database, watched)
        before = self.signature(source), self.signature(self.database)
        inside = watched / 'cache'
        with self.assertRaises(self.api.CacheWriteHeld):
            thumbnail.thumbnail_for(self.database, row['asset_id'], inside, max_edge=144)
        self.assertFalse(inside.exists())
        self.assertFalse(self.authority.exists())
        self.assertEqual((self.signature(source), self.signature(self.database)), before)

    def test_publication_refuses_substituted_operation_directory(self):
        source, row = self.image()
        original = self.api._publish_manifest
        replacements = []
        def substitute(path, manifest, **kwargs):
            old = path.parent
            retained = old.with_name(old.name + '-retained')
            old.rename(retained)
            old.mkdir(mode=0o700)
            os.link(retained / path.with_suffix('.png').name, old / path.with_suffix('.png').name)
            replacements.append((old, retained))
            return original(path, manifest, **kwargs)
        with patch.object(self.api, '_publish_manifest', side_effect=substitute):
            with self.assertRaises(self.api.CacheWriteHeld):
                thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertEqual(len(replacements), 1)
        for directory in replacements[0]:
            self.assertEqual(list(directory.glob('*.json')), [])
            self.assertEqual(len(list(directory.glob('*.png'))), 1)

    def test_uncertain_prior_owner_holds_writes_but_validated_reads_continue(self):
        from defiantmaple.managed_thumbnail_admission import ManagedOperation, RecoveryHeld, capture_association
        source, row = self.image()
        thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        other_source, other = self.image(1)
        with self.assertRaises(RecoveryHeld):
            with ManagedOperation(self.authority, self.cache / cached_preview.MANAGED_NAMESPACE,
                                  capture_association(self.database), accounting_parent=self.cache):
                pass
        raw = cached_preview.read_cached_preview(self.database, cached_preview.capture_target(row), self.cache, 144)
        self.assertEqual(raw.status, 'ready', raw.message)
        with self.assertRaises(RecoveryHeld):
            thumbnail.thumbnail_for(self.database, other['asset_id'], self.cache, max_edge=144)
        self.assertTrue(source.is_file() and other_source.is_file())

    def test_budget_preflight_preserves_unknown_and_does_not_create_authority(self):
        from defiantmaple.thumbnail_budget import BudgetPolicy
        source, row = self.image()
        self.cache.mkdir()
        unknown = self.cache / 'unknown'
        unknown.write_bytes(b'preserve')
        before = self.signature(unknown), self.signature(source), self.signature(self.database)
        with patch.object(self.api, 'DEFAULT_POLICY', BudgetPolicy(byte_limit=1024)):
            with self.assertRaises(self.api.CacheWriteHeld):
                thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertFalse(self.authority.exists())
        self.assertEqual((self.signature(unknown), self.signature(source), self.signature(self.database)), before)

    def test_uncommitted_residue_is_ignored_charged_and_not_deleted(self):
        source, row = self.image()
        result = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        operation = Path(result['path']).parent
        manifest = Path(result['path']).with_suffix('.json')
        retained = manifest.read_bytes()
        manifest.rename(operation / '.interrupted-manifest')
        before = self.signature(Path(result['path']))
        second = thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertNotEqual(result['path'], second['path'])
        self.assertEqual(self.signature(Path(result['path'])), before)
        self.assertEqual((operation / '.interrupted-manifest').read_bytes(), retained)
        self.assertEqual(cached_preview.read_cached_preview(self.database, cached_preview.capture_target(row), self.cache, 144).status, 'ready')

    def test_existing_empty_namespace_is_not_adopted(self):
        source, row = self.image()
        managed = self.cache / cached_preview.MANAGED_NAMESPACE
        managed.mkdir(parents=True, mode=0o700)
        identity = managed.stat().st_ino
        before = (managed.stat().st_mode, managed.stat().st_mtime_ns, tuple(managed.iterdir()))
        with self.assertRaisesRegex(Exception, 'adoption is refused'):
            thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertEqual(managed.stat().st_ino, identity)
        self.assertEqual((managed.stat().st_mode, managed.stat().st_mtime_ns, tuple(managed.iterdir())), before)
        self.assertFalse((managed / '.managed-domain-v1.json').exists())
        self.assertTrue(source.is_file())

    def test_ambiguous_start_holds_immediately_and_preserves_pending(self):
        source, row = self.image()
        def uncertain(payload, timeout, cancel_event, *, managed_operation):
            managed_operation._uncertain_start = True
            raise RuntimeError('injected ambiguous dispatch')
        with patch.object(thumbnail, '_run_decoder', side_effect=uncertain):
            with self.assertRaisesRegex(self.api.CacheWriteHeld, 'generation held'):
                thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertTrue((self.cache / cached_preview.MANAGED_NAMESPACE / '.managed-pending-v1.json').is_file())
        self.assertTrue(source.is_file())

    def test_failed_known_cleanup_holds_immediately(self):
        from defiantmaple.managed_thumbnail_admission import ManagedOperation
        source, row = self.image()
        with patch.object(thumbnail, '_run_decoder', side_effect=RuntimeError('injected decoder failure')):
            with patch.object(ManagedOperation, 'rollback_known', side_effect=RuntimeError('injected cleanup failure')):
                with self.assertRaisesRegex(self.api.CacheWriteHeld, 'generation held'):
                    thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertTrue((self.cache / cached_preview.MANAGED_NAMESPACE / '.managed-pending-v1.json').is_file())
        self.assertTrue(source.is_file())

    def test_unknown_namespace_tree_is_unchanged_by_refused_bootstrap(self):
        source, row = self.image()
        managed = self.cache / cached_preview.MANAGED_NAMESPACE
        managed.mkdir(parents=True, mode=0o700)
        nested = managed / 'unknown-directory'
        nested.mkdir(mode=0o700)
        (nested / 'unknown-data').write_bytes(b'preserve unknown ownership')
        def snapshot():
            return [(str(path.relative_to(managed)), path.lstat().st_mode,
                     path.lstat().st_mtime_ns, path.lstat().st_ino,
                     path.read_bytes() if path.is_file() else None)
                    for path in [managed, *sorted(managed.rglob('*'))]]
        before = snapshot()
        with self.assertRaisesRegex(Exception, 'adoption is refused'):
            thumbnail.thumbnail_for(self.database, row['asset_id'], self.cache, max_edge=144)
        self.assertEqual(snapshot(), before)
        self.assertTrue(source.is_file())
