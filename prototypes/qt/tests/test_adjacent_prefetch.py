"""Generated, deterministic adjacent-read scheduling and stale-delivery boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from functools import partial
import multiprocessing
import tempfile
import sys
import threading
import time
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace, MethodType
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QPixmap

from PIL import Image
from PySide6.QtWidgets import QApplication
from defiantmaple import catalog, cached_preview
from prototypes.qt.app import AssetModel, GalleryWindow, ThumbnailWorker, result_image
from prototypes.qt.tests.thumbnail_fixture import isolate_thumbnail_authority
from prototypes.qt.tests.gallery_wait import close_window_and_wait


def gated_cache_helper(entered, release, *args):
    """Test-only startup gate; release before running unchanged helper validation."""
    from defiantmaple.cached_preview import _cache_helper
    entered.set()
    if not release.wait(4):
        raise RuntimeError('generated helper readiness gate timed out')
    _cache_helper(*args)


@unittest.skipUnless(sys.platform == 'linux', 'Adjacent cache warming is Linux-first')
class AdjacentPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dm-adjacent-generated-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'catalog.sqlite3'
        catalog.initialize(self.db)
        self.owner=isolate_thumbnail_authority(self, self.db, self.root)
        self.rows = []
        for n in range(16):
            path = self.root / f'generated-{n:02}.png'
            Image.new('RGBA', (8,4), (n*10,60,90,255)).save(path)
            aid = catalog.index_file(self.db, path)
            with catalog.connect(self.db) as db:
                self.rows.append(dict(db.execute('SELECT * FROM assets WHERE asset_id=?',(aid,)).fetchone()))
        self.worker = ThumbnailWorker(self.db, self.root/'cache')
        self.addCleanup(self.worker.stop)

    def wait(self, predicate, clue='bounded worker progress'):
        end = time.monotonic()+5
        while not predicate() and time.monotonic()<end:
            self.app.processEvents()
            time.sleep(.002)
        self.assertTrue(predicate(), clue)

    @staticmethod
    def ready(_db, target, _root, edge, **kwargs):
        return cached_preview.CachedResult('ready','Generated validated-result seam',target,
            width=1,height=1,pixels=b'\x20\x40\x60\xff',requested_edge=edge,cache_edge=edge)

    def test_idle_ready_is_reused_without_second_read(self):
        worker = self.worker
        with patch('prototypes.qt.app.read_cached_preview',side_effect=self.ready) as read, \
             patch('prototypes.qt.app.thumbnail_for',side_effect=AssertionError('generation forbidden')) as generate:
            self.assertTrue(worker.replace_adjacent(self.rows[0],144))
            worker.start()
            key = worker.key(self.rows[0],144)
            self.wait(lambda:key in worker.pixmaps)
            pixels,error = worker.lookup(self.rows[0],144)
            self.assertIsNotNone(pixels)
            self.assertIsNone(error)
            self.assertEqual(read.call_count,1)
            self.assertEqual(generate.call_count,0)
            self.assertFalse(worker.pending)
            self.assertFalse(worker.errors)

    def test_foreground_clears_queued_adjacent_and_precedes_background(self):
        worker = self.worker
        reads=[]
        def read(*a,**kw):
            reads.append(a[1].asset_id)
            return self.ready(*a,**kw)
        with patch('prototypes.qt.app.read_cached_preview',side_effect=read):
            worker.begin_background(1,[self.rows[2]])
            self.assertTrue(worker.replace_adjacent(self.rows[0],144))
            worker.lookup(self.rows[1],144)
            worker.start()
            self.wait(lambda:len(reads)==2 and worker._delivery.is_set())
            self.assertEqual(reads,[self.rows[1]['asset_id'],self.rows[2]['asset_id']])
            self.assertNotIn(worker.key(self.rows[0],144),worker.pixmaps)

    def test_foreground_after_adjacent_selection_prevents_read_dispatch(self):
        worker = self.worker
        worker.replace_adjacent(self.rows[0],144)
        selected = worker._next_request()
        self.assertEqual(selected[0],'adjacent')
        worker.lookup(self.rows[1],144)
        original_next = worker._next_request
        first=[selected]
        def next_request():
            return first.pop() if first else original_next()
        with patch.object(worker,'_next_request',side_effect=next_request), \
             patch('prototypes.qt.app.read_cached_preview',side_effect=self.ready) as read:
            worker.start()
            self.wait(lambda:worker.key(self.rows[1],144) in worker.pixmaps)
            self.assertEqual([c.args[1].asset_id for c in read.call_args_list],[self.rows[1]['asset_id']])

    def test_adjacent_miss_does_not_generate_or_cache_error(self):
        worker=self.worker
        def miss(_db,target,_root,edge,**kw):
            return cached_preview.CachedResult('no_cache','Generated miss',target,requested_edge=edge)
        with patch('prototypes.qt.app.read_cached_preview',side_effect=miss) as read, \
             patch('prototypes.qt.app.thumbnail_for',side_effect=AssertionError('original generation')) as generate:
            worker.replace_adjacent(self.rows[0],144)
            worker.start()
            self.wait(lambda:read.call_count==1 and worker._adjacent_wanted is None)
            self.assertFalse(worker.results)
            self.assertFalse(worker.errors)
            self.assertFalse(worker.pixmaps)
            self.assertFalse(worker.pending)
            self.assertEqual(generate.call_count,0)

    def test_scroll_discards_active_result_without_canceling_owned_read(self):
        worker=self.worker
        entered,release=threading.Event(),threading.Event()
        active_cancel=[]
        def read(*a,**kw):
            if a[1].asset_id==self.rows[0]['asset_id']:
                active_cancel.append(kw['cancel_event'])
                entered.set()
                self.assertTrue(release.wait(4))
            return self.ready(*a,**kw)
        with patch('prototypes.qt.app.read_cached_preview',side_effect=read):
            worker.replace_adjacent(self.rows[0],144)
            worker.start()
            try:
                self.wait(entered.is_set)
                worker.invalidate_pending(cancel_active=False)
                self.assertFalse(active_cancel[0].is_set())
                worker.lookup(self.rows[1],144)
            finally:
                release.set()
            self.wait(lambda:worker.key(self.rows[1],144) in worker.pixmaps)
            self.assertNotIn(worker.key(self.rows[0],144),worker.pixmaps)

    def test_new_same_target_foreground_retains_its_own_request(self):
        worker=self.worker
        entered,release=threading.Event(),threading.Event()
        calls=[]
        def read(*a,**kw):
            calls.append(a[1].asset_id)
            if len(calls)==1:
                entered.set()
                self.assertTrue(release.wait(4))
            return self.ready(*a,**kw)
        with patch('prototypes.qt.app.read_cached_preview',side_effect=read):
            worker.replace_adjacent(self.rows[0],144)
            worker.start()
            try:
                self.wait(entered.is_set)
                worker.lookup(self.rows[0],144)
                self.assertTrue(worker.pending)
            finally:
                release.set()
            self.wait(lambda:worker.key(self.rows[0],144) in worker.pixmaps)
            self.assertEqual(len(calls),2)
            self.assertFalse(worker.pending)

    def test_query_or_edge_invalidation_discards_old_delivery(self):
        worker=self.worker
        for edge in (144,200):
            worker.replace_adjacent(self.rows[0],edge)
            epoch,generation,key,binding=worker._adjacent_wanted
            result=self.ready(self.db,binding[0],self.root,edge)
            worker.invalidate_pending()
            worker._received_adjacent(epoch,generation,self.rows[0],result_image(result),result)
            self.assertNotIn(key,worker.pixmaps)
            self.assertNotIn(key,worker.results)

    def test_binding_replacement_discards_old_delivery(self):
        worker=self.worker
        worker.replace_adjacent(self.rows[0],144)
        epoch,generation,key,binding=worker._adjacent_wanted
        result=self.ready(self.db,binding[0],self.root,144)
        changed=dict(self.rows[0],revision=self.rows[0]['revision']+1)
        worker.replace_adjacent(changed,144)
        worker._received_adjacent(epoch,generation,self.rows[0],result_image(result),result)
        self.assertNotIn(key,worker.pixmaps)

    def test_stale_incomplete_cleanup_retains_hold(self):
        worker=self.worker
        worker.replace_adjacent(self.rows[0],144)
        epoch,generation,key,binding=worker._adjacent_wanted
        worker.clear_adjacent()
        from PySide6.QtGui import QImage
        result=cached_preview.CachedResult('cleanup_failed','Generated uncertain child',binding[0],
                                          requested_edge=144,cleanup_complete=False)
        worker._received_adjacent(epoch,generation,self.rows[0],QImage(),result)
        self.assertTrue(worker.cleanup_failed)
        self.assertFalse(worker.replace_adjacent(self.rows[1],144))
        self.assertIn('cleanup failed',worker.lookup(self.rows[1],144)[1])
        self.assertFalse(worker.stop())

    def test_capacity_does_not_evict_existing_entries(self):
        worker=self.worker
        worker.replace_adjacent(self.rows[0],144)
        epoch,generation,key,binding=worker._adjacent_wanted
        result=self.ready(self.db,binding[0],self.root,144)
        worker.pixmaps.update((('existing',n),object()) for n in range(worker.pixmap_entry_limit))
        before=list(worker.pixmaps)
        worker._received_adjacent(epoch,generation,self.rows[0],result_image(result),result)
        self.assertEqual(list(worker.pixmaps),before)
        self.assertFalse(worker.replace_adjacent(self.rows[1],144))

    def test_metadata_capacity_declines_without_evicting_pixels(self):
        worker=self.worker
        worker.replace_adjacent(self.rows[0],144)
        epoch,generation,key,binding=worker._adjacent_wanted
        result=self.ready(self.db,binding[0],self.root,144)
        worker.results.update((('metadata',n),object()) for n in range(256))
        before=list(worker.results)
        worker._received_adjacent(epoch,generation,self.rows[0],result_image(result),result)
        self.assertEqual(list(worker.results),before)
        self.assertFalse(worker.pixmaps)
        self.assertTrue(worker._delivery.is_set())
        self.assertFalse(worker.replace_adjacent(self.rows[1],144))

    def test_edge_and_availability_replacement_discard_old_delivery(self):
        worker=self.worker
        for replacement,edge in ((self.rows[0],200),(dict(self.rows[0],source_health='offline'),144)):
            worker.replace_adjacent(self.rows[0],144)
            epoch,generation,key,binding=worker._adjacent_wanted
            result=self.ready(self.db,binding[0],self.root,144)
            worker.replace_adjacent(replacement,edge)
            worker._received_adjacent(epoch,generation,self.rows[0],result_image(result),result)
            self.assertNotIn(key,worker.pixmaps)
            self.assertTrue(worker._delivery.is_set())

    def test_real_cache_helper_and_close_with_gui_ack_withheld(self):
        from defiantmaple import thumbnail
        from prototypes.qt import app as gallery
        cache=self.root/'cache'
        thumbnail.thumbnail_for(self.db,self.rows[0]['asset_id'],cache,max_edge=144)
        before={p:p.read_bytes() for p in cache.rglob('*') if p.is_file()}
        originals_before={p:p.read_bytes() for p in self.root.glob('generated-*.png')}
        catalog_before=self.db.read_bytes()
        worker=self.worker
        with patch('prototypes.qt.app.thumbnail_for',side_effect=AssertionError('read-only warming generated original')), \
             patch('prototypes.qt.app.read_cached_preview',wraps=gallery.read_cached_preview) as read:
            worker.replace_adjacent(self.rows[0],144)
            worker.start()
            self.wait(lambda:worker.key(self.rows[0],144) in worker.pixmaps)
            self.assertIsNotNone(worker.lookup(self.rows[0],144)[0])
            self.assertEqual(read.call_count,1)
            self.assertTrue(worker.stop())
        # A fresh worker owns a real spawned cache helper; stop without pumping
        # Qt deliveries. The one-image acknowledgment must not prevent close.
        closing=ThumbnailWorker(self.db,cache)
        self.addCleanup(closing.stop)
        context=multiprocessing.get_context('spawn')
        entered,release=context.Event(),context.Event()
        processes=[]
        retain=self.owner.retain_process
        def retained(process):
            retain(process)
            processes.append(process)
        with patch.object(self.owner,'retain_process',side_effect=retained), \
             patch('defiantmaple.cached_preview._cache_helper',partial(gated_cache_helper,entered,release)), \
             patch('prototypes.qt.app.thumbnail_for',side_effect=AssertionError('read-only close generated original')):
            closing.replace_adjacent(self.rows[0],144)
            closing.start()
            try:
                self.wait(entered.is_set)
                self.assertTrue(processes[0].is_alive(), 'owned helper is genuinely active')
            finally:
                release.set()
            self.assertTrue(closing.stop(), 'close must not require GUI delivery acknowledgment')
            self.assertFalse(closing.isRunning())
            self.assertFalse(closing._delivery.is_set(), 'GUI acknowledgment deliberately withheld')
            self.assertFalse(processes[0].is_alive())
        self.wait(lambda:self.owner.reap_owned_processes()==0)
        self.assertEqual(before,{p:p.read_bytes() for p in cache.rglob('*') if p.is_file()})
        self.assertEqual(originals_before,{p:p.read_bytes() for p in self.root.glob('generated-*.png')})
        self.assertEqual(catalog_before,self.db.read_bytes())

    def test_missing_peek_never_submits_page(self):
        model=AssetModel(self.db)
        self.addCleanup(model.close)
        model.read_mode='async'
        model._actionable=True
        model._cache.clear()
        with patch.object(model,'request_page') as request:
            self.assertIsNone(model.loaded_asset_at(0,request_missing=False))
            request.assert_not_called()
            model.loaded_asset_at(0)
            request.assert_called_once_with(0)

    def scheduler(self):
        """Deterministic uniform grid, with real worker admission and delivery."""
        worker = self.worker
        index = lambda row: SimpleNamespace(row=lambda: row, isValid=lambda: 0 <= row < len(self.rows))
        model = SimpleNamespace(_actionable=True, rowCount=lambda: len(self.rows), index=index,
            loaded_asset_at=Mock(side_effect=lambda row, **kw: self.rows[row] if 0 <= row < len(self.rows) else None))
        viewport = SimpleNamespace(rect=lambda: QRect(0, 0, 200, 200))
        gallery = SimpleNamespace(viewport=lambda: viewport, gridSize=lambda: QSize(100, 100),
            indexAt=lambda point: index(point.y() // 100 * 2 + point.x() // 100),
            visualRect=lambda idx: QRect(idx.row() % 2 * 100, idx.row() // 2 * 100, 100, 100))
        window = SimpleNamespace(thumbnails=worker, _closing=False, _startup_validated=True,
            model=model, gallery=gallery, delegate=SimpleNamespace(cell_size=96),
            _adjacent_direction=1, _adjacent_timer=Mock())
        for name in ('_reset_adjacent_plan', '_schedule_adjacent', '_prefetch_adjacent',
                     '_adjacent_completed', '_adjacent_background_completed'):
            setattr(window, name, MethodType(getattr(GalleryWindow, name), window))
        window._reset_adjacent_plan()
        worker.adjacent_completed.connect(lambda *args: window._adjacent_completed(*args))
        for row in self.rows[:4]:
            result = self.ready(None, worker.binding(row)[0], None, 96)
            worker._store_pixmap(worker.key(row, 96), QPixmap.fromImage(result_image(result)))
            worker.bindings[worker.key(row, 96)] = worker.binding(row)
        return window

    def deliver_adjacent(self, status='ready'):
        worker = self.worker
        epoch, generation, asset, edge = worker._adjacent_request
        worker._adjacent_request = None
        result = self.ready(None, worker.binding(asset)[0], None, edge)
        if status != 'ready':
            from dataclasses import replace
            result = replace(result, status=status, pixels=b'')
        worker._received_adjacent(epoch, generation, asset, result_image(result), result)
        return worker.key(asset, edge)

    def test_bounded_plan_warms_multiple_rows_and_reuses_all_pixels(self):
        window = self.scheduler()
        keys = []
        for _ in range(4):
            window._prefetch_adjacent()
            keys.append(self.deliver_adjacent())
        window._prefetch_adjacent()
        self.assertEqual(keys, [self.worker.key(row, 96) for row in self.rows[4:8]])
        self.assertIsNone(self.worker._adjacent_request)
        self.assertEqual(len(window._adjacent_attempted), 4)
        for row in self.rows[4:8]:
            self.assertIsNotNone(self.worker.lookup(row, 96)[0])
        self.assertTrue(self.worker.requests.empty())
        self.assertTrue(all(call.kwargs == {'request_missing': False}
                            for call in window.model.loaded_asset_at.call_args_list))

    def test_two_misses_yield_until_relevant_current_background_ready(self):
        window = self.scheduler()
        for _ in range(2):
            window._prefetch_adjacent()
            self.deliver_adjacent('no_cache')
        self.assertTrue(window._adjacent_yielded)
        starts = window._adjacent_timer.start.call_count
        for _ in range(5):
            window._prefetch_adjacent()
        self.assertIsNone(self.worker._adjacent_request)
        self.assertEqual(window._adjacent_timer.start.call_count, starts)
        self.assertFalse(self.worker.errors)
        self.worker.begin_background(7, self.rows)
        self.assertEqual(self.worker._next_request()[0], 'background')
        window._adjacent_background_completed(6, self.rows[4]['asset_id'], 'ready', '')
        window._adjacent_background_completed(7, self.rows[12]['asset_id'], 'ready', '')
        window._adjacent_background_completed(7, self.rows[4]['asset_id'], 'no_cache', '')
        self.assertTrue(window._adjacent_yielded)
        window._adjacent_background_completed(7, self.rows[4]['asset_id'], 'ready', '')
        self.assertFalse(window._adjacent_yielded)
        window._prefetch_adjacent()
        self.assertEqual(self.worker._adjacent_request[2]['asset_id'], self.rows[4]['asset_id'])

    def test_plan_foreground_preempts_and_stale_completion_cannot_advance(self):
        window = self.scheduler()
        window._prefetch_adjacent()
        stale = window._adjacent_inflight
        self.worker.lookup(self.rows[10], 96)
        window._prefetch_adjacent()
        self.assertIsNone(self.worker._adjacent_request)
        starts = window._adjacent_timer.start.call_count
        window._adjacent_completed(*stale, 'ready')
        self.assertEqual(window._adjacent_timer.start.call_count, starts)
        self.assertEqual(len(window._adjacent_attempted), 1)

    def test_plan_caps_examined_rows_even_for_unsupported_media(self):
        window = self.scheduler()
        window.model.rowCount = lambda: 1000
        window.gallery.visualRect = lambda _idx: QRect(0, 200, 100, 100)
        video = dict(self.rows[4], media_type='video/generated')
        window.model.loaded_asset_at.side_effect = lambda row, **kw: self.rows[row] if row < 4 else video
        window._prefetch_adjacent()
        self.assertEqual(window.model.loaded_asset_at.call_count, 4 + 32)
        self.assertEqual(window._adjacent_candidates, [])
        self.assertIsNone(self.worker._adjacent_request)

    def test_completion_acknowledges_before_pumping_and_stale_signal_is_ignored(self):
        window = self.scheduler()
        observed = []
        self.worker.adjacent_completed.connect(lambda *_: observed.append(self.worker._delivery.is_set()))
        window._prefetch_adjacent()
        stale = window._adjacent_inflight
        self.worker._delivery.clear()
        self.deliver_adjacent()
        self.assertEqual(observed, [True])
        window._prefetch_adjacent()
        current = window._adjacent_inflight
        window._adjacent_completed(*stale, 'no_cache')
        self.assertEqual(window._adjacent_inflight, current)
        self.assertEqual(window._adjacent_misses, 0)

    def test_plan_admission_never_evicts_visible_pixels(self):
        window = self.scheduler()
        worker = self.worker
        visible = tuple(worker.pixmaps)
        worker.pixmap_byte_limit = worker.pixmap_bytes
        window._prefetch_adjacent()
        self.assertIsNone(worker._adjacent_request)
        self.assertEqual(tuple(worker.pixmaps), visible)
        worker.pixmap_byte_limit += 1  # not enough for another raster
        window._prefetch_adjacent()
        self.deliver_adjacent()
        self.assertEqual(tuple(worker.pixmaps), visible)
        self.assertLessEqual(worker.pixmap_bytes, worker.pixmap_byte_limit)

    def test_gallery_neighbor_direction_and_resize_guards(self):
        with patch('prototypes.qt.app.read_cached_preview',side_effect=self.ready), \
             patch('prototypes.qt.app.thumbnail_for',side_effect=AssertionError('unexpected generator')):
            window=GalleryWindow(self.db,enable_thumbnails=True,cache_root=self.root/'window-cache',
                private_root=self.root/'private',schedule_application_data_root=self.root/'schedule',
                external_settings_path=self.root/'external.json')
            self.addCleanup(close_window_and_wait,window,self.app)
            window.preparation.stop()
            window.resize(1024,620)
            window.show()
            worker=window.thumbnails
            self.wait(lambda:window._startup_validated and window.model._actionable)
            self.wait(lambda:len(worker.pixmaps)>=5 and not worker.pending)
            self.wait(lambda:window._adjacent_attempt is not None,'idle completion schedules adjacent warming')
            forward=window._adjacent_attempt
            self.assertEqual(forward[-1],1)
            self.wait(lambda:forward[1] in worker.pixmaps)
            saved=window.model._cache.copy()
            window.model._cache.clear()
            try:
                with patch.object(window.model,'request_page') as request:
                    window._prefetch_adjacent()
                    request.assert_not_called()
            finally:
                window.model._cache.update(saved)
            # Scrolling updates direction/epoch and clears the one attempted signature.
            bar=window.gallery.verticalScrollBar()
            bar.setValue(bar.maximum())
            self.assertEqual(window._adjacent_direction,1)
            oldepoch=worker._adjacent_epoch
            bar.setValue(max(0,bar.value()-186))
            self.assertEqual(window._adjacent_direction,-1)
            self.assertGreater(worker._adjacent_epoch,oldepoch)
            generation=worker.generation
            window._resize_cells(200)
            self.assertGreater(worker.generation,generation)
            self.assertIsNone(worker._adjacent_wanted)
            self.assertIsNone(window._adjacent_attempt)
