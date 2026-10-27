"""Owned synchronous scheduled backup/reconciliation and opt-in retention.

Call off the UI thread. A pending cleanup keeps its source reference, native
stores and shared operation slot; the caller must retain/reap this coordinator.
Only actual recovery Process objects are observed, never authority tokens.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import threading
import uuid
import weakref

from . import recovery
from .admission import current_session
from .snapshot_control import require_run
from .scheduled_snapshots import (AuditRecord, LockedDirectory, PackageRecord,
    PhaseStatus, ScheduleError, StateUncertainError, _private_regular,
    _stat_identity, validate_pair)

_SLOTS = weakref.WeakKeyDictionary()
_SLOTS_LOCK = threading.Lock()
_PENDING = set()  # Strong fail-closed ownership if callers lose their UI reference.


def _slot(owner):
    if current_session(owner.path) is not owner:
        raise ScheduleError("Operation requires its actual admitted library owner")
    with _SLOTS_LOCK:
        return _SLOTS.setdefault(owner, threading.Lock())


@contextmanager
def recovery_operation_slot(owner):
    """Shared admission-scoped slot for future manual-recovery integration."""
    slot = _slot(owner)
    if not slot.acquire(blocking=False):
        raise ScheduleError("A recovery operation or owned cleanup is already active")
    try:
        yield
    finally:
        slot.release()


@dataclass(frozen=True)
class OperationResult:
    status: str
    state: object
    success_currently_verified: bool
    cleanup_pending: bool
    error: str | None = None


class SnapshotOperations:
    def __init__(self, configuration, *, cancel_event=None):
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ScheduleError("External cancellation requires a threading.Event")
        self._external_cancel = cancel_event is not None
        self.config = configuration
        self.owner = configuration.owner
        self.cancel = cancel_event if cancel_event is not None else threading.Event()
        self.active = False
        self.records = []
        self._stores = None
        self._slot = None
        self.state = None
        self.version = None
        self._registered_package = None

    def request_cancel(self):
        self.cancel.set()

    def _check_cancel(self):
        if self.cancel.is_set():
            raise ScheduleError("Scheduled operation canceled")

    def _started(self, operation, process, stages):
        record = {"operation": operation, "process": process, "pid": process.pid,
                  "stages": tuple(stages), "exit": None, "cleanup_errors": []}
        self.records.append(record)
        if operation == "inspect":
            # Inspection has no source-writing authority, but is still an owned
            # application child. The backup path retains itself in recovery._run.
            self.owner.retain_process(process)

    def _begin(self):
        # A fresh job's externally owned event is sticky: never erase a cancel
        # received before QThread.run or between actor creation and assignment.
        if self._external_cancel:
            self._check_cancel()
        if self.active:
            raise ScheduleError("Operation or cleanup already active")
        self._slot = _slot(self.owner)
        if not self._slot.acquire(blocking=False):
            raise ScheduleError("A recovery operation or cleanup is already active")
        retained = False
        self._stores = ExitStack()
        try:
            self.owner.retain()
            retained = True
            self.active = True
            _PENDING.add(self)
            if not self._external_cancel:
                self.cancel.clear()  # Preserve the original reusable actor API.
            self._check_cancel()
            self.records = []
            self._registered_package = None
            self.config._placement()
            self._check_cancel()
            locators = self._stores.enter_context(LockedDirectory(self.config.root, self.config.leaf + ".lock"))
            self.locators = locators
            self._check_cancel()
            locator, _ = locators.read(self.config.leaf, locator=True)
            transition, _ = locators.read(self.config.transition_leaf, transition=True)
            if locator is None or transition is None or transition.phase != "committed" or transition.locator != locator:
                raise ScheduleError("Schedule configuration needs explicit reconciliation")
            self.config._placement(locator.binding.directory_path)
            locator.binding.validate(self.owner)
            self.managed = self._stores.enter_context(LockedDirectory(locator.binding.directory_path, "schedule.lock"))
            self.state, self.version = self.managed.read("schedule.json")
            validate_pair(locator, self.state, self.owner)
            self._check_cancel()
        except BaseException:
            self._stores.close()
            if retained:
                self.owner.release()
            self.active = False
            _PENDING.discard(self)
            self._slot.release()
            raise

    def _save(self, state):
        self.owner.validate()
        self.config._placement(self.managed.directory)
        self.version = self.managed.write("schedule.json", state, self.version)
        self.state = state

    def _audit(self, state, event, operation, *, package=None, error=None):
        entry = AuditRecord(state.audit[-1].sequence + 1 if state.audit else 1,
                            operation, state.locator.revision, int(self.config.utc()),
                            event, package=package, error_code=error)
        return replace(state, audit=(*state.audit, entry))

    def _facts(self, leaf):
        self.managed.validate()
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.managed.fd)
        try:
            before = os.fstat(fd)
            _private_regular(before)
            if before.st_size > recovery.MAX_PACKAGE_BYTES:
                raise ScheduleError("Managed package exceeds the package limit")
            digest, length = hashlib.sha256(), 0
            while True:
                if self.cancel.is_set():
                    raise recovery.RecoveryError("Scheduled recovery canceled")
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                length += len(chunk)
                if length > recovery.MAX_PACKAGE_BYTES:
                    raise ScheduleError("Managed package grew beyond its limit")
                digest.update(chunk)
            after = os.fstat(fd)
            named = os.stat(leaf, dir_fd=self.managed.fd, follow_symlinks=False)
            _private_regular(after)
            _private_regular(named)
            signature = lambda info: (_stat_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if signature(before) != signature(after) or signature(named) != signature(after) or length != before.st_size:
                raise ScheduleError("Managed package changed during hashing")
            return _stat_identity(before), length, digest.hexdigest()
        finally:
            os.close(fd)

    def _inspect(self, leaf, expected=None):
        self._check_cancel()
        before = self._facts(leaf)
        if expected is not None and before != (expected.file_identity, expected.size, expected.sha256):
            raise ScheduleError("Managed package differs from its verified ledger")
        self._check_cancel()
        report = recovery.inspect_package(self.managed.directory / leaf, cancel_event=self.cancel,
                                         _process_started=self._started)
        after = self._facts(leaf)
        manifest, details = report["manifest"], report["catalog"]
        if before != after or manifest["kind"] != "metadata-only" or manifest["catalog_schema"] != 7 or manifest.get("library_id") != self.state.locator.binding.library_id or details["schema_version"] != 7 or details["library_id"] != self.state.locator.binding.library_id:
            raise ScheduleError("Managed package verification/binding changed")
        return after

    def _reconcile(self):
        from .snapshot_retention import pending_intent
        if pending_intent(self.state) is not None:
            from .snapshot_pruning import describe_pending
            raise ScheduleError(describe_pending(self))
        allowed = {"schedule.json", "schedule.lock", *(p.leaf for p in self.state.packages)}
        if any(name not in allowed for name in self.managed.names()):
            raise ScheduleError("Unknown package/stage or directory bound; explicit review required")
        for package in self.state.packages:
            self._inspect(package.leaf, package)
        status = self.state.status
        if status.cleanup_pending or status.outcome in {"in_progress", "uncertain", "cleanup_warning"}:
            raise ScheduleError("Interrupted or uncertain operation requires explicit reconciliation")
        return self.state.last_success is not None

    def _cleanup(self):
        pending = False
        for record in self.records:
            process = record["process"]
            report = recovery.reap_recovery_workers(0, _only_process=process)
            record["cleanup_errors"] = report["cleanup_errors"]
            if process.is_alive() or report["remaining_workers"]:
                pending = True
                continue
            process.join(0)
            record["exit"] = process.exitcode
            # Original _run (or its one deferred filtered reaper) owns stage
            # cleanup. A name reused after that cleanup is not ours to unlink.
            # Leftover/recreated names require explicit review, never a blind
            # second pathname deletion by this coordinator.
            for stage in record["stages"]:
                try:
                    stage.lstat()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    record["cleanup_errors"].append("Cannot verify stage absence: " + type(exc).__name__)
                else:
                    record["cleanup_errors"].append("Stage name remains or was replaced; explicit review required")
            pending = pending or bool(record["cleanup_errors"])
        self.owner.reap_owned_processes()  # Nonblocking sentinel polling, not exit proof.
        return not pending

    def _release(self):
        self._stores.close()
        self.owner.release()
        self.active = False
        self._slot.release()
        _PENDING.discard(self)

    def reap_owned_cleanup(self):
        """Never kill or join unrelated processes; do not infer exit from timeout."""
        if not self.active:
            return True
        if not self._cleanup():
            return False
        if self.state is not None and self.state.status.cleanup_pending:
            try:
                self._save(replace(self.state, status=replace(self.state.status, cleanup_pending=False)))
            except (ValueError, OSError):
                # Cleanup exit is proven, but durable uncertainty still blocks
                # future work via the existing interrupted/uncertain status.
                pass
        self._release()
        return True

    def _finish(self, result):
        try:
            clean = self._cleanup()
        except Exception as exc:
            clean = False
            result = replace(result, error="Cleanup proof failed: " + str(exc)[:200])
        if clean:
            self._release()
            return result
        try:
            status = replace(self.state.status, cleanup_pending=True,
                             outcome="cleanup_warning" if self.state.last_success else "uncertain")
            self._save(replace(self.state, status=status))
        except (ValueError, OSError):
            pass  # Original durable in-progress/uncertain state remains fail-closed.
        _PENDING.add(self)
        return OperationResult("cleanup_pending", self.state, result.success_currently_verified, True, result.error)

    def reconcile(self):
        self._begin()
        try:
            verified = self._reconcile()
            result = OperationResult("reconciled", self.state, verified, False)
        except Exception as exc:
            result = OperationResult("suspended", self.state, False, False, str(exc)[:256])
        return self._finish(result)

    def backup(self):
        self._begin()
        package_path = None
        registered = False
        operation = str(uuid.uuid4())
        try:
            require_run(self.config, self.state.locator, self.locators)
            self._reconcile()
            require_run(self.config, self.state.locator, self.locators)
            if not self.state.policy.enabled:
                raise ScheduleError("Schedule is disabled")
            if len(self.state.audit) > 4092 or len(self.state.packages) >= 1024:
                raise ScheduleError("Managed state capacity exhausted")
            policy = self.state.policy
            if not policy.retention_enabled and ((policy.keep_count is not None and len(self.state.packages) >= policy.keep_count) or (policy.byte_limit is not None and sum(p.size for p in self.state.packages) >= policy.byte_limit)):
                stopped = replace(self.state, status=replace(self.state.status, outcome="cleanup_warning"))
                self._save(self._audit(stopped, "cleanup_warning", operation, error="storage_limit_reached"))
                raise ScheduleError("Storage limit reached; retention is disabled")
            sequence = self.state.next_sequence
            leaf = f"snapshot-{self.state.locator.schedule_id}-{sequence}-{operation}.dmbackup"
            package_path = self.managed.directory / leaf
            started = replace(self.state, next_sequence=sequence + 1,
                              status=PhaseStatus(int(self.config.utc()), self.state.status.last_success_utc, "in_progress"))
            self._save(self._audit(started, "attempt_started", operation))
            require_run(self.config, self.state.locator, self.locators)
            self._check_cancel()
            recovery.backup_metadata(self.owner.path, package_path, cache_roots=self.config.caches,
                                     cancel_event=self.cancel, _process_started=self._started)
            identity, size, digest = self._inspect(leaf)
            package = PackageRecord(self.state.locator.schedule_id, sequence, operation, leaf,
                                    identity, size, digest, int(self.config.utc()))
            complete = replace(self.state, packages=(*self.state.packages, package), last_success=package,
                               status=PhaseStatus(int(self.config.utc()), package.verified_utc, "verified"))
            complete = self._audit(complete, "verified", operation, package=package,
                                   error="cancel_after_publication" if self.cancel.is_set() else None)
            self._save(complete)
            registered = True
            self._registered_package = package
            if policy.retention_enabled:
                from .snapshot_pruning import prune_registered
                prune_registered(self, package)
            result = OperationResult("verified", self.state, True, False)
        except Exception as exc:
            published = False
            if package_path is not None:
                try:
                    package_path.lstat()
                    published = True  # Includes a replaced/symlink/unknown leaf.
                except FileNotFoundError:
                    pass
                except OSError:
                    published = True  # Failure to inspect is not absence proof.
            outcome = "suspended" if package_path is None else "uncertain" if published else "canceled" if self.cancel.is_set() else "failed"
            if self.state is not None and self.state.status.outcome == "in_progress":
                try:
                    failed = replace(self.state, status=replace(self.state.status, outcome=outcome))
                    self._save(self._audit(failed, outcome, operation, error="publication_unregistered" if published else "backup_failed"))
                except (ValueError, OSError):
                    outcome = "uncertain"
            currently_verified = False
            if registered and self.state.last_success is not None:
                point = self.state.last_success
                try:
                    currently_verified = self._facts(point.leaf) == (point.file_identity, point.size, point.sha256)
                except (ValueError, OSError):
                    pass
            result = OperationResult("verified_with_warning" if registered else outcome,
                                     self.state, currently_verified, False, str(exc)[:256])
        return self._finish(result)
