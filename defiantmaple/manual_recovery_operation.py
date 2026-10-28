"""Admission-scoped manual recovery ownership; no UI or scheduling side effects.

The caller keeps this actor and calls finish_thread only after its worker has
finished. Original recovery code alone deletes stages. Pending actors remain
strongly owned until exact child exit and stage absence have been established.
"""
import threading
from pathlib import Path

from . import recovery
from .admission import current_session
from .scheduled_snapshots import ScheduleError
from .snapshot_operations import _slot

_PENDING_MANUAL = set()


class ManualRecoveryOperation:
    def __init__(self, owner):
        self.owner = owner
        self.cancel = threading.Event()
        self.records = []
        self.active = False
        self.thread_finished = False
        self._lock = threading.RLock()
        self._invocation = threading.Lock()

    def begin(self):
        with self._lock:
            if self.active or self.thread_finished:
                raise ScheduleError("Manual recovery actor cannot be reused")
            slot = _slot(self.owner)
            if not slot.acquire(blocking=False):
                raise ScheduleError("A recovery operation or owned cleanup is already active")
            try:
                self.owner.validate()
                self.owner.retain()
            except BaseException:
                slot.release()
                raise
            self._slot = slot
            self.active = True
            _PENDING_MANUAL.add(self)
        return self

    def request_cancel(self):
        self.cancel.set()

    def _observer(self, source):
        def started(operation, process, stages):
            with self._lock:
                if not self.active or self.thread_finished:
                    raise ScheduleError("Manual recovery ownership is not active")
                self.records.append({"operation": operation, "process": process,
                                     "pid": process.pid, "stages": tuple(stages),
                                     "exit": None, "cleanup_errors": []})
                # Match original _run's source routing exactly. Inspection has
                # no original source owner. Restore can target another owner.
                routed = current_session(source) if source is not None else None
                if routed is not self.owner:
                    self.owner.retain_process(process)
        return started

    def _require_active(self):
        if not self.active or self.thread_finished:
            raise ScheduleError("Manual recovery ownership is not active")
        self.owner.validate()

    def _invoke(self, function, *args, **kwargs):
        if not self._invocation.acquire(blocking=False):
            raise ScheduleError("This manual actor already has an active invocation")
        try:
            self._require_active()
            return function(*args, **kwargs)
        finally:
            self._invocation.release()

    def backup(self, database, package, *, cache_roots, timeout_seconds=120):
        # The shared slot authenticates this source only, never another catalog.
        if Path(database) != self.owner.path:
            raise ScheduleError("Manual backup source differs from its admitted owner")
        return self._invoke(recovery.backup_metadata, database, package, cache_roots=cache_roots,
            timeout_seconds=timeout_seconds, cancel_event=self.cancel,
            _process_started=self._observer(database))

    def inspect(self, package, *, timeout_seconds=120):
        return self._invoke(recovery.inspect_package, package, timeout_seconds=timeout_seconds,
            cancel_event=self.cancel, _process_started=self._observer(None))

    def restore(self, package, catalog, *, cache_roots, live_catalog,
                timeout_seconds=120):
        return self._invoke(recovery.restore_metadata, package, catalog, cache_roots=cache_roots,
            live_catalog=live_catalog, timeout_seconds=timeout_seconds,
            cancel_event=self.cancel, _process_started=self._observer(live_catalog))

    def finish_thread(self):
        """Caller attests actual worker completion, never merely result delivery."""
        with self._lock:
            if not self.active:
                return True
            if self._invocation.locked():
                raise ScheduleError("Manual invocation has not finished")
            self.thread_finished = True
            return self.reap()

    def reap(self):
        with self._lock:
            if not self.active:
                return True
            if not self.thread_finished:
                return False
            clean = True
            for record in self.records:
                process = record["process"]
                report = recovery.reap_recovery_workers(0, _only_process=process)
                errors = list(report["cleanup_errors"])
                if process.is_alive() or report["remaining_workers"]:
                    clean = False
                else:
                    process.join(0)
                    record["exit"] = process.exitcode
                    for stage in record["stages"]:
                        try:
                            stage.lstat()
                        except FileNotFoundError:
                            pass
                        except OSError:
                            errors.append("Cannot verify original stage absence")
                        else:
                            errors.append("Stage name remains or was replaced; review required")
                record["cleanup_errors"] = errors
                clean = clean and not errors
            self.owner.reap_owned_processes()
            if clean:
                self.owner.release()
                self._slot.release()
                self.active = False
                _PENDING_MANUAL.discard(self)
            return clean
