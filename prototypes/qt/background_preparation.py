"""Linux current-query preparation over the existing gallery gateway/worker."""
from PySide6.QtCore import QObject, Signal
from defiantmaple.cached_preview import capture_target
from .gallery_filters import RequestClass


class BackgroundPreparation(QObject):
    changed = Signal(str, bool)

    def __init__(self, model, worker, parent=None):
        super().__init__(parent)
        self.model, self.worker = model, worker
        self.epoch = 0
        self.active = False
        self.paused = False
        self.processed = self.ready = self.unavailable = 0
        self.total = 0
        self.page = 0
        self.token = None
        self.message = 'Preview preparation waiting for the gallery'
        model.actionabilityChanged.connect(self._actionability_changed)
        model.generationPublished.connect(self._published)
        worker.background_completed.connect(self._completed)
        worker.background_page_needed.connect(self._next_page)

    def _announce(self, message=None):
        if message is not None:
            self.message = message
        self.changed.emit(f'{self.message} — {self.ready:,} cached, {self.unavailable:,} unavailable/refused; '
                          f'{self.processed:,}/{self.total:,} checked', self.active)

    def _actionability_changed(self, actionable):
        if actionable or self.paused:
            return
        # A query becomes nonactionable before its replacement is published.
        # Cancel its page and worker epoch immediately, retaining automatic
        # preparation intent for the next successful generation publication.
        self.active = False
        self.epoch += 1
        self.token = None
        self.worker.stop_background()
        self._announce('Preview preparation waiting for the gallery')

    def _published(self, _generation):
        if self.paused or not self.model._actionable or self.model._token is None:
            return
        self.epoch += 1
        self.token = self.model._token
        self.total = self.token.count
        self.page = 0
        self.processed = self.ready = self.unavailable = 0
        self.active = True
        self._announce('Preparing preview cache')
        rows = tuple(self.model._cache.get(0, ()))
        self._feed(rows, first=True)

    def _feed(self, rows, *, first=False):
        expected = min(256, max(0, self.total - self.page * 256))
        if len(rows) != expected or len(rows) > 256:
            self.stop('Gallery changed; resume to refresh preparation')
            return
        candidates = []
        for row in rows:
            try:
                capture_target(row)
            except (ValueError, KeyError, TypeError):
                self.processed += 1
                self.unavailable += 1
            else:
                candidates.append(dict(row))
        if first:
            self.worker.begin_background(self.epoch, candidates)
        else:
            self.worker.provide_background_page(self.epoch, candidates)
        self._announce()

    def _completed(self, epoch, _asset_id, status, message):
        if not self.active or epoch != self.epoch:
            return
        self.processed += 1
        if status == 'ready':
            self.ready += 1
        elif status in ('cache_held', 'cleanup_failed'):
            self.stop('Preparation held: ' + message)
            return
        else:
            self.unavailable += 1
        self._announce()

    def _next_page(self, epoch):
        if not self.active or epoch != self.epoch:
            return
        page = self.page + 1
        if page * 256 >= self.total:
            self.active = False
            self.worker.stop_background()
            self._announce('Preparation pass finished' if self.ready != self.total else 'All matching previews cached')
            return
        captured_epoch, token = self.epoch, self.token
        generation, query, incarnation = self.model._generation, self.model._query, self.model._reader_incarnation
        def received(reply):
            if not self.active or captured_epoch != self.epoch or token != self.model._token:
                return
            if reply.status != 'ok' or reply.value.token != token or reply.value.page != page:
                self.stop('Gallery changed or page unavailable; resume to refresh preparation')
                return
            self.page = page
            self._feed(reply.value.rows)
        _, reason = self.model.catalog_client.submit(
            RequestClass.PAGE, 'page', (query, token, incarnation, generation, page),
            context=f'preview-preparation:{self.epoch}:{page}', generation=generation, callback=received)
        if reason:
            self.stop('Preparation page unavailable; resume to retry')

    def stop(self, message='Preparation paused; cached previews remain available'):
        self.active = False
        self.paused = True
        self.epoch += 1
        self.worker.stop_background()
        self._announce(message)

    def resume(self):
        self.paused = False
        # Refresh only the read view, not metadata, to acquire one fresh token
        # and page zero even after the visible model evicted its old page zero.
        self.model.refresh()

    def toggle(self):
        if self.active:
            self.stop()
        else:
            self.resume()
