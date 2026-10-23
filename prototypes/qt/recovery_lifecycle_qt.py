"""Window-owned admitted manual jobs; independent of dialog/scheduler settings.

No profile I/O or worker starts at import. Callers must keep their window alive
while busy. Standalone legacy dialogs remain unchanged until explicit wiring.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot

from defiantmaple import recovery
from defiantmaple.manual_recovery_operation import ManualRecoveryOperation
from defiantmaple.scheduled_snapshots import ScheduleError

_PENDING = set()


@dataclass(frozen=True)
class ManualCall:
    operation: str
    database: Path
    catalog_identity: tuple | None = None
    cache_roots: tuple = ()
    package: Path | None = None
    package_identity: tuple | None = None
    output: Path | None = None
    captured: object = None
    view_epoch: tuple | None = None

    def execute(self, actor):
        # Reuse original UI mapping/identity guards and Core functions. This
        # dispatch never changes restore holds, source enable rules or scanning.
        from prototypes.qt.recovery_qt import _identity, _source_mapping
        if Path(self.database) != actor.owner.path:
            raise ScheduleError('Manual action differs from its admitted library')
        actor.owner.validate()
        # Native admission IDs and Python stat IDs are different namespaces
        # on Windows. Keep the original UI guard entirely in stat space.
        identity = self.catalog_identity or _identity(self.database)
        if self.operation != 'inspect' and _identity(self.database) != identity:
            raise ValueError('Library file changed; reopen it before recovery')
        if self.package is not None:
            selected = self.package_identity or _identity(self.package)
            if _identity(self.package) != selected:
                raise ValueError('Selected package changed; select it again')
        if actor.cancel.is_set():
            raise ScheduleError('Manual recovery canceled before dispatch')
        if self.operation == 'backup':
            value = actor.backup(self.database, self.output, cache_roots=self.cache_roots)
        elif self.operation == 'inspect':
            value = actor.inspect(self.package)
        elif self.operation == 'restore':
            value = actor.restore(self.package, self.output, cache_roots=self.cache_roots,
                                  live_catalog=self.database)
        elif self.operation == 'mapping':
            value = actor._invoke(_source_mapping, self.database)
        elif self.operation == 'review':
            value = actor._invoke(recovery.review_restored_sources, self.database, self.captured)
        elif self.operation == 'enable':
            value = actor._invoke(recovery.enable_reviewed_source, self.database, *self.captured)
        else:
            raise ValueError('Unknown recovery operation')
        if self.operation in {'review', 'enable'} and _identity(self.database) != identity:
            raise ValueError('Catalog changed during source review; reopen before refreshing')
        return value


class _ManualJob(QThread):
    def __init__(self, actor, call, parent):
        super().__init__(parent)
        self.actor = actor
        self.operation = call.operation
        self.view_epoch = call.view_epoch
        self.call = replace(call, captured=deepcopy(call.captured))
        self.result = None
        self.error = None

    def cancel(self):
        self.actor.request_cancel()

    def run(self):
        try:
            if self.actor.cancel.is_set():
                raise ScheduleError('Manual recovery canceled before startup')
            self.actor.begin()
            self.result = self.call.execute(self.actor)
        except BaseException as exc:
            self.error = type(exc).__name__ + ': ' + str(exc)


class _CleanupJob(QThread):
    def __init__(self, actor, parent):
        super().__init__(parent)
        self.actor = actor
        self.clean = False
        self.error = None

    def run(self):
        try:
            # Called only AFTER actual main QThread.finished delivery.
            self.clean = self.actor.finish_thread() is True and not self.actor.active
        except BaseException as exc:
            self.error = type(exc).__name__ + ': ' + str(exc)


@dataclass
class ManualReservation:
    identity: str
    actor: object
    worker: object
    retained: bool = False
    thread_finished: bool = False
    cleanup: object = None
    start_error: str | None = None
    cleanup_error: str | None = None
    cleanup_verified: bool = False


@dataclass(frozen=True)
class ManualCompletion:
    identity: str
    worker: object
    operation: str
    result: object
    error: str | None
    never_started: bool = False


class ManualJobRegistry(QObject):
    """One visible reservation covers start, actual thread and cleanup lifetimes."""
    busyChanged = Signal(bool)
    reservationAdded = Signal(object)
    lifecycleComplete = Signal(object)
    cleanupWarning = Signal(str)

    def __init__(self, owner, parent=None, *, actor_factory=ManualRecoveryOperation,
                 worker_factory=_ManualJob, cleanup_factory=_CleanupJob):
        super().__init__(parent)
        self.owner = owner
        self._actor_factory = actor_factory
        self._worker_factory = worker_factory
        self._cleanup_factory = cleanup_factory
        self._records = {}
        self.closing = False
        self.admission_gate = None
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self.retry_cleanup)

    @property
    def busy(self):
        return bool(self._records)

    def reservations(self):
        # These are actual local actors/QThreads, never serialized authority.
        return tuple(self._records.values())

    def start(self, call):
        if self.closing or self.busy:
            raise ScheduleError('Manual recovery or cleanup is already reserved')
        if type(call) is not ManualCall:
            raise ScheduleError('A captured manual action is required')
        if self.admission_gate is not None:
            self.admission_gate()  # Same GUI turn as reservation insertion/start.
        actor = self._actor_factory(self.owner)
        worker = self._worker_factory(actor, call, self)
        record = ManualReservation(str(uuid.uuid4()), actor, worker)
        self._records[worker] = record
        _PENDING.add(self)
        worker.finished.connect(self._main_finished, Qt.ConnectionType.QueuedConnection)
        # Reservations/stop-scope listeners see this BEFORE start or actor.begin.
        self.busyChanged.emit(True)
        self.reservationAdded.emit(record)
        try:
            if self.closing:
                raise ScheduleError('Window closed before manual worker start')
            self.owner.retain()
            record.retained = True
            worker.start()
        except BaseException as exc:
            record.start_error = type(exc).__name__ + ': ' + str(exc)
            if worker.isRunning() or worker.isFinished():
                worker.cancel()
            else:
                self._complete(record, never_started=True)
                raise
        return record

    @Slot()
    def _main_finished(self):
        worker = self.sender()
        record = self._records.get(worker)
        if record is None:
            return
        record.thread_finished = True
        self._start_cleanup(record)

    def _start_cleanup(self, record):
        if not record.thread_finished or record.cleanup is not None:
            return
        cleanup = None
        try:
            cleanup = self._cleanup_factory(record.actor, self)
            record.cleanup = cleanup
            cleanup.finished.connect(self._cleanup_finished, Qt.ConnectionType.QueuedConnection)
            cleanup.start()
        except BaseException as exc:
            record.cleanup_error = 'Cleanup start: ' + type(exc).__name__ + ': ' + str(exc)
            self.cleanupWarning.emit(record.cleanup_error)
            if cleanup is not None and not cleanup.isRunning() and not cleanup.isFinished():
                record.cleanup = None
                cleanup.deleteLater()
            # Keep reservation/owner until an actual cleanup thread proves clean.

    @Slot()
    def _cleanup_finished(self):
        cleanup = self.sender()
        record = next((r for r in self._records.values() if r.cleanup is cleanup), None)
        if record is None:
            return
        record.cleanup = None
        if cleanup.error:
            record.cleanup_error = cleanup.error
            self.cleanupWarning.emit(cleanup.error)
        if cleanup.clean is True:
            record.cleanup_verified = True
            self._complete(record)
        elif not cleanup.error:
            self._retry.start(250)  # Owned cleanup only; never dispatch new work.
        cleanup.deleteLater()

    def _complete(self, record, *, never_started=False):
        if not never_started and (not record.thread_finished or not record.cleanup_verified or record.actor.active):
            raise ScheduleError('Actual manual lifecycle cleanup is not complete')
        self._records.pop(record.worker, None)
        if record.retained:
            self.owner.release()
            record.retained = False
        error = record.start_error or record.cleanup_error or record.worker.error
        completion = ManualCompletion(record.identity, record.worker,
            record.worker.call.operation, record.worker.result, error, never_started)
        self.lifecycleComplete.emit(completion)
        record.worker.deleteLater()
        if not self._records:
            _PENDING.discard(self)
        self.busyChanged.emit(self.busy)

    @Slot()
    def retry_cleanup(self):
        for record in tuple(self._records.values()):
            self._start_cleanup(record)

    def cancel(self):
        for record in self._records.values():
            record.worker.cancel()

    def begin_close(self):
        self.closing = True
        self.cancel()
        return not self.busy
