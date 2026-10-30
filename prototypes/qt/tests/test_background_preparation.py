"""Generated offscreen Linux functional preparation, no real-account state."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from defiantmaple import catalog, thumbnail, cached_preview
from defiantmaple.admission import admission_session
from prototypes.qt.app import GalleryWindow, ThumbnailWorker
from prototypes.qt.background_preparation import BackgroundPreparation
from prototypes.qt.tests.test_metadata_name_preview import _wait_export_condition


@unittest.skipUnless(sys.platform == 'linux', 'Functional background preparation is Linux-first')
class BackgroundPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from defiantmaple import linux_thumbnails
        temporary = tempfile.TemporaryDirectory(prefix='dm-idle-preparation-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)
        self.database, self.cache = self.root / 'catalog.sqlite3', self.root / 'cache'
        catalog.initialize(self.database)
        authority = patch.object(linux_thumbnails, 'default_authority_root', return_value=self.root / 'authority')
        authority.start()
        self.addCleanup(authority.stop)
        self.owner_context = admission_session(self.database, _registry_path=self.root / 'admission')
        self.owner = self.owner_context.__enter__()
        self.addCleanup(self.owner_context.__exit__, None, None, None)
        self.window = None
        self.rows = []
        self.sources = []

    def fixture(self, count):
        originals = self.root / 'originals'
        originals.mkdir()
        for number in range(count):
            path = originals / f'generated-{number:04d}.png'
            Image.new('RGBA', (8, 4), (number % 256, number // 256, 110, 90)).save(path)
            aid = catalog.index_file(self.database, path)
            self.sources.append(path)
            with catalog.connect(self.database) as db:
                self.rows.append(dict(db.execute('SELECT * FROM assets WHERE asset_id=?', (aid,)).fetchone()))
        self.before = {p: self.signature(p) for p in [self.database, *self.sources]}

    @staticmethod
    def signature(path):
        info = path.stat()
        return hashlib.sha256(path.read_bytes()).hexdigest(), info.st_mode, info.st_mtime_ns

    def open_window(self):
        self.window = GalleryWindow(self.database, enable_thumbnails=True, cache_root=self.cache,
                                    private_root=self.root / 'private',
                                    schedule_application_data_root=self.root / 'schedule',
                                    external_settings_path=self.root / 'external.json')
        self.addCleanup(self.close_window)
        self.assertIs(self.window._admission_owner, self.owner,
                      'Window must reuse the generated fixture admission authority')
        return self.window

    def wait(self, predicate, clue):
        _wait_export_condition(predicate)
        self.assertTrue(predicate(), clue)

    def close_window(self):
        if self.window is None:
            return
        window = self.window
        window.close()
        self.wait(lambda: not window.catalog_client.gateway.isRunning()
                  and (window.thumbnails is None or not window.thumbnails.isRunning())
                  and window._admission_owner is None, 'Owned window workers and library coordinator closed')
        self.window = None

    def assert_originals_unchanged(self):
        self.assertEqual({p: self.signature(p) for p in self.before}, self.before)

    def test_idle_small_query_populates_unpainted_rows_and_closes(self):
        self.fixture(4)
        window = self.open_window()  # Deliberately hidden: no paint/scroll demand.
        self.wait(lambda: window.preparation.ready == 4 and not window.preparation.active,
                  'Idle hidden gallery prepared all four real generated images')
        self.assertEqual(window.preparation.processed, 4)
        self.assertEqual(len(list(self.cache.rglob('*.png'))), 4)
        self.assertEqual(len(window.thumbnails.pixmaps), 0)
        self.assertEqual(window.thumbnails.requests.maxsize, 32)
        self.close_window()
        self.assert_originals_unchanged()

    def test_foreground_backlog_then_idle_background_and_disk_only_memory(self):
        self.fixture(16)
        worker = ThumbnailWorker(self.database, self.cache)
        trace = []
        worker.updated.connect(lambda aid: trace.append(('foreground', aid)))
        worker.background_completed.connect(lambda _epoch, aid, _status, _message: trace.append(('background', aid)))
        def cached(_database, target, _root, edge, **_kwargs):
            return cached_preview.CachedResult('ready', 'Generated scheduling fixture', target,
                width=1, height=1, pixels=b'\x20\x40\x60\xff', requested_edge=edge, cache_edge=edge)
        with patch('prototypes.qt.app.read_cached_preview', side_effect=cached):
            worker.begin_background(1, self.rows[:8])
            for row in self.rows[8:]:
                worker.lookup(row, 144)
            worker.start()
            try:
                self.wait(lambda: len(trace) == 16, 'Both classes progress through existing acknowledged worker')
            finally:
                self.assertTrue(worker.stop())
        self.assertEqual([kind for kind, _ in trace], ['foreground'] * 8 + ['background'] * 8)
        self.assertEqual(len(worker.pixmaps), 8)
        self.assertLessEqual(worker.requests.qsize(), 32)
        self.assert_originals_unchanged()

    def test_foreground_arriving_during_background_waits_only_for_active_job(self):
        self.fixture(3)
        worker = ThumbnailWorker(self.database, self.cache)
        entered, release = threading.Event(), threading.Event()
        trace = []
        worker.updated.connect(lambda aid: trace.append(('foreground', aid)))
        worker.background_completed.connect(lambda _e, aid, _s, _m: trace.append(('background', aid)))
        first = self.rows[0]['asset_id']
        def cached(_database, target, _root, edge, *, cancel_event):
            if target.asset_id == first:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('Generated active-job fixture timed out')
                self.assertFalse(cancel_event.is_set(), 'Foreground demand preserves active ownership')
            return cached_preview.CachedResult('ready', 'Generated active-job fixture', target,
                width=1, height=1, pixels=b'\x20\x40\x60\xff', requested_edge=edge, cache_edge=edge)
        with patch('prototypes.qt.app.read_cached_preview', side_effect=cached):
            worker.begin_background(1, self.rows[:2])
            worker.start()
            try:
                self.wait(entered.is_set, 'First background job is already active')
                worker.lookup(self.rows[2], 144)
                release.set()
                self.wait(lambda: len(trace) == 3, 'Active background completes, visible demand runs, idle resumes')
            finally:
                release.set()
                self.assertTrue(worker.stop())
        self.assertEqual(trace, [('background', first), ('foreground', self.rows[2]['asset_id']),
                                 ('background', self.rows[1]['asset_id'])])
        self.assertFalse(worker.cleanup_failed)
        self.assert_originals_unchanged()

    def test_background_cleanup_failure_blocks_next_foreground_job(self):
        self.fixture(2)
        worker = ThumbnailWorker(self.database, self.cache)
        entered, release = threading.Event(), threading.Event()
        calls = []
        def failed(_database, target, _root, edge, **_kwargs):
            calls.append(target.asset_id)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Generated cleanup fixture timed out')
            return cached_preview.CachedResult('cleanup_failed', 'Generated owned cleanup failure', target,
                                               requested_edge=edge, cleanup_complete=False)
        with patch('prototypes.qt.app.read_cached_preview', side_effect=failed):
            worker.begin_background(1, self.rows[:1])
            worker.start()
            try:
                self.wait(entered.is_set, 'Background operation owns the active slot')
                worker.lookup(self.rows[1], 144)
                release.set()
                self.wait(lambda: not worker.isRunning(), 'Cleanup failure stops dispatch')
                self.assertTrue(worker.cleanup_failed)
                self.assertEqual(calls, [self.rows[0]['asset_id']])
                self.assertIn('cleanup failed', worker.lookup(self.rows[1], 144)[1])
            finally:
                release.set()
                self.assertFalse(worker.stop(), 'Unresolved cleanup remains visible to the owner')
                self.assertTrue(worker.wait(2500))
        self.assert_originals_unchanged()

    def test_pause_cancels_active_background_and_ignores_late_delivery(self):
        self.fixture(2)
        entered, cancelled = threading.Event(), threading.Event()
        def blocked(_database, target, _root, edge, *, cancel_event):
            entered.set()
            if not cancel_event.wait(5):
                raise RuntimeError('Generated cancellation fixture timed out')
            cancelled.set()
            return cached_preview.CachedResult('cancelled', 'Generated cancellation', target,
                                               requested_edge=edge)
        with patch('prototypes.qt.app.read_cached_preview', side_effect=blocked):
            window = self.open_window()
            self.wait(entered.is_set, 'Background reader entered before pause')
            epoch = window.preparation.epoch
            window.preparation.stop()
            self.wait(cancelled.is_set, 'Pause cancels the in-flight reader')
            window.thumbnails.background_completed.emit(epoch, self.rows[0]['asset_id'], 'ready', 'late')
            self.app.processEvents()
            self.assertEqual(window.preparation.processed, 0)
            self.assertTrue(window.preparation.paused)
            self.assertFalse(window.preparation.active)
            self.assertIn('cached previews remain available', window.preparation_status.text())
            self.assertEqual(window.preparation_toggle.text(), 'Resume preparation')
            self.close_window()
        self.assertFalse(list(self.cache.rglob('*.png')))
        self.assert_originals_unchanged()

    def test_close_cancels_inflight_background_and_releases_owned_workers(self):
        self.fixture(2)
        entered, cancelled = threading.Event(), threading.Event()
        def blocked(_database, target, _root, edge, *, cancel_event):
            entered.set()
            if not cancel_event.wait(5):
                raise RuntimeError('Generated close fixture timed out')
            cancelled.set()
            return cached_preview.CachedResult('cancelled', 'Generated close cancellation', target,
                                               requested_edge=edge)
        with patch('prototypes.qt.app.read_cached_preview', side_effect=blocked):
            window = self.open_window()
            worker = window.thumbnails
            self.wait(entered.is_set, 'Reader is active before closing')
            self.close_window()
            self.assertTrue(cancelled.is_set())
            self.assertFalse(worker.isRunning())
            self.assertFalse(worker.cleanup_failed)
            self.assertEqual(window.preparation.processed, 0)
        self.assert_originals_unchanged()

    def test_budget_hold_pauses_ui_and_does_not_advertise_completion(self):
        self.fixture(2)
        from defiantmaple.thumbnail_budget import BudgetRefusal
        with patch('prototypes.qt.app.read_cached_preview', side_effect=BudgetRefusal('Generated quota exhausted')):
            window = self.open_window()
            self.wait(lambda: window.preparation.paused, 'Quota refusal pauses preparation')
            self.assertFalse(window.preparation.active)
            self.assertEqual(window.preparation.processed, 1)
            self.assertEqual(window.preparation.ready, 0)
            self.assertIn('Preparation held:', window.preparation_status.text())
            self.assertIn('Generated quota exhausted', window.preparation_status.text())
            self.assertEqual(window.preparation_toggle.text(), 'Resume preparation')
            self.assertFalse(list(self.cache.rglob('*.png')))
            self.close_window()
        self.assert_originals_unchanged()

    def test_stale_query_page_and_completion_do_not_feed_new_generation(self):
        self.fixture(1)
        class Model(QObject):
            generationPublished = Signal(int)
            actionabilityChanged = Signal(bool)
        model = Model()
        old_token = SimpleNamespace(count=257)
        new_token = SimpleNamespace(count=1)
        model._actionable, model._token = True, old_token
        model._generation, model._query, model._reader_incarnation = 1, object(), 'generated'
        model._cache = {0: [self.rows[0]] * 256}
        callbacks = []
        model.catalog_client = SimpleNamespace(submit=lambda *a, **kw: (callbacks.append(kw['callback']), None))
        worker = ThumbnailWorker(self.database, self.cache)
        preparation = BackgroundPreparation(model, worker)
        model.generationPublished.emit(1)
        old_epoch = preparation.epoch
        preparation._next_page(old_epoch)
        self.assertEqual(len(callbacks), 1)
        # Reader/generation identity guards hold even before an actionability
        # signal or token replacement has reached this controller.
        stale_reply = SimpleNamespace(status='ok', value=SimpleNamespace(
            token=old_token, page=1, rows=self.rows))
        model._reader_incarnation = 'replacement-reader'
        callbacks[0](stale_reply)
        self.assertEqual(preparation.page, 0)
        self.assertTrue(preparation.active)
        model._reader_incarnation = 'generated'
        model._generation = 2
        callbacks[0](stale_reply)
        self.assertEqual(preparation.page, 0)
        self.assertTrue(preparation.active)
        model._generation = 1
        model._actionable = False
        model.actionabilityChanged.emit(False)
        self.assertFalse(preparation.active)
        self.assertFalse(preparation.paused, 'Query refresh preserves automatic preparation intent')
        self.assertIsNone(preparation.token)
        with worker._background_lock:
            self.assertFalse(worker._background_enabled)
            self.assertFalse(worker._background_rows)
        # Even a successful old reply arriving during refresh cannot restart work.
        callbacks[0](SimpleNamespace(status='ok', value=SimpleNamespace(
            token=old_token, page=1, rows=self.rows)))
        self.assertEqual(preparation.processed, 0)
        model._actionable = True
        model._token, model._generation, model._cache = new_token, 2, {0: self.rows}
        model.generationPublished.emit(2)
        current_epoch = preparation.epoch
        callbacks[0](SimpleNamespace(status='ok', value=SimpleNamespace(
            token=old_token, page=1, rows=self.rows)))
        worker.background_completed.emit(old_epoch, self.rows[0]['asset_id'], 'ready', 'stale')
        worker.background_page_needed.emit(old_epoch)
        self.assertEqual(preparation.epoch, current_epoch)
        self.assertEqual(preparation.page, 0)
        self.assertEqual(preparation.processed, 0)
        self.assertEqual(preparation.total, 1)
        with worker._background_lock:
            self.assertEqual(list(worker._background_rows), self.rows)
        preparation.stop()
        self.assert_originals_unchanged()

    def test_real_260_idle_priority_pause_resume_and_persistent_revisit(self):
        self.fixture(260)
        trace = []
        stats = {'max_queue': 0, 'max_background_page': 0, 'max_pixmaps': 0}
        started = time.monotonic()
        deadline = started + 300
        original = thumbnail._run_decoder
        with patch.object(thumbnail, '_run_decoder', wraps=original) as decoder:
            window = self.open_window()  # Never shown or scrolled.
            worker = window.thumbnails
            worker.background_completed.connect(lambda _e, aid, _s, _m: trace.append(('background', aid)))
            worker.updated.connect(lambda aid: trace.append(('foreground', aid)))
            self.wait(lambda: window.preparation.processed >= 2, 'Unpainted real rows progress while idle')
            first_ids = {row['asset_id'] for row in window.model._cache[0]}
            target = next(row for row in self.rows if row['asset_id'] not in first_ids)
            before = len(trace)
            worker.lookup(target, 144)
            self.wait(lambda: worker.key(target, 144) in worker.pixmaps,
                      'Late visible request overtakes remaining background candidates')
            following = trace[before:]
            visible_index = following.index(('foreground', target['asset_id']))
            self.assertLessEqual(visible_index, 1, 'Only the already-active background operation may finish first')
            previous = window.preparation.processed
            while window.preparation.active:
                self.assertLess(time.monotonic(), deadline, 'Finite260-image functional deadline')
                self.wait(lambda: window.preparation.processed > previous or not window.preparation.active,
                          'Each acknowledged real row makes progress')
                previous = window.preparation.processed
                stats['max_queue'] = max(stats['max_queue'], worker.requests.qsize())
                with worker._background_lock:
                    stats['max_background_page'] = max(stats['max_background_page'], len(worker._background_rows))
                stats['max_pixmaps'] = max(stats['max_pixmaps'], len(worker.pixmaps))
                if previous and previous % 64 == 0:
                    print(f'Generated preparation progress: {previous}/260', flush=True)
            self.assertEqual(window.preparation.ready, 260, window.preparation.message)
            self.assertEqual(window.preparation.unavailable, 0)
            self.assertEqual(window.preparation.page, 1)
            self.assertEqual(len(list(self.cache.rglob('*.png'))), 260)
            self.assertEqual(decoder.call_count, 260, 'Already-prepared foreground item is reused by background')
            self.assertLessEqual(stats['max_queue'], 32)
            self.assertLessEqual(stats['max_background_page'], 256)
            self.assertLessEqual(stats['max_pixmaps'], 1, 'Offscreen preparation must not fill visible LRU')
            window.preparation.stop()
            self.assertTrue(window.preparation.paused)
            self.assertFalse(window.preparation.active)
            window.preparation.resume()
            self.wait(lambda: window.preparation.active and not window.preparation.paused,
                      'Resume publishes a fresh query and continues from validated disk')
            previous = window.preparation.processed
            while window.preparation.active:
                self.assertLess(time.monotonic(), deadline, 'Finite260-image repeat deadline')
                self.wait(lambda: window.preparation.processed > previous or not window.preparation.active,
                          'Cached second pass progresses without original generation')
                previous = window.preparation.processed
            self.assertEqual(window.preparation.ready, 260)
            self.assertEqual(decoder.call_count, 260, 'Second pass must not decode originals again')
            self.close_window()
            # A fresh worker has no pixmaps and still reuses the persisted pair.
            fresh = ThumbnailWorker(self.database, self.cache)
            fresh.start()
            try:
                fresh.lookup(self.rows[0], 144)
                self.wait(lambda: fresh.key(self.rows[0], 144) in fresh.pixmaps,
                          'Memory-cold revisit reads persistent generated cache')
            finally:
                self.assertTrue(fresh.stop())
            self.assertEqual(decoder.call_count, 260)
        self.assert_originals_unchanged()
        print('Generated260 acceptance: ' + str(dict(stats, original_decodes=260,
              cached_second_pass=260, elapsed_seconds=round(time.monotonic() - started, 3))), flush=True)
