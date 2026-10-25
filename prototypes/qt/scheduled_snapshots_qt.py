"""Asynchronous scheduled-snapshot controller foundations, not window wiring.

Admission, stores and recovery remain in Core. A dialog never owns this object's
lifetime. Real worker/native helpers require exact review before execution.
"""
from dataclasses import dataclass, replace
import math
import threading
import time

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot

from defiantmaple.controlled_configuration import EnableRequest, ControlledEnableOperation
from defiantmaple.scheduled_snapshots import DueState, ScheduleError, StateUncertainError, LockedDirectory, validate_pair
from defiantmaple.snapshot_control import ControlStore, LiveStopSession
from defiantmaple.snapshot_operations import SnapshotOperations
from defiantmaple.snapshot_retention import pending_intent


@dataclass(frozen=True)
class ScheduleTiming:
    # Relative monotonic delay only: a wall-clock due timestamp is not implied.
    remaining_seconds: int | None = None
    active: bool = False
    pending: bool = False
    manual_deferred: bool = False
    clock_adjusted: bool = False
    suspended: bool = False


@dataclass(frozen=True)
class ScheduleView:
    phase: str
    state: object = None
    locator: object = None
    control: object = None
    control_version: object = None
    currently_verified: bool = False
    error: str | None = None
    recovery_review_required: bool = False
    timing: ScheduleTiming | None = None


@dataclass(frozen=True)
class _StopAcknowledgment:
    control: object
    version: object
    view: ScheduleView
    observation_failed: bool = False


class _ScheduleJob(QThread):
    def __init__(self, owner, kind, epoch, callback, parent):
        super().__init__(parent)
        self.owner, self.kind, self.epoch = owner, kind, epoch
        self.callback = callback
        self.cancel_event = threading.Event()
        self.actor = None
        self.result = None
        self.error = None
        self.error_state_uncertain = False
        self.retained = False
        self.outcome = None

    def start_owned(self):
        self.owner.retain()
        self.retained = True
        try:
            self.start()
        except BaseException:
            # An injected/late start error can follow a real native start. Its
            # finished signal, not that exception, must release ownership.
            if not self.isRunning() and not self.isFinished():
                self.owner.release()
                self.retained = False
            raise

    def cancel(self):
        self.cancel_event.set()
        if self.actor is not None:
            self.actor.request_cancel()

    def run(self):
        try:
            if self.cancel_event.is_set():
                self.result = ScheduleView('canceled')
                return
            self.owner.validate()
            if self.cancel_event.is_set():
                self.result = ScheduleView('canceled')
                return
            self.result = self.callback(self)
        except BaseException as exc:
            self.error_state_uncertain = isinstance(exc, StateUncertainError)
            self.error = type(exc).__name__ + ': ' + str(exc)
        # Owner is deliberately retained after run returns, until actual Qt
        # finished is delivered to the controller. Result delivery is no proof.


class SnapshotController(QObject):
    changed = Signal(object)
    idleChanged = Signal(bool)

    def __init__(self, configuration, parent=None, *, utc=time.time,
                 monotonic=time.monotonic, job_factory=_ScheduleJob):
        super().__init__(parent)
        self.config, self.owner = configuration, configuration.owner
        self.utc, self.monotonic = utc, monotonic
        self._job_factory = job_factory
        self.view = ScheduleView('not_checked')
        self.epoch = 0
        self.closing = False
        self._jobs = {}
        self._lanes = {}
        self._pending_actors = []
        self._enable_requests = {}
        self._stop_intent = None
        self._queued_stop = None
        self.due = None
        self._manual_registry = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._deadline_event)
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setSingleShot(True)
        self.cleanup_timer.timeout.connect(self._cleanup_event)

    @property
    def idle(self):
        return not self._jobs and not self._pending_actors and not self._manual_busy()

    def _manual_busy(self):
        return self._manual_registry is not None and self._manual_registry.busy

    def attach_manual_registry(self, registry):
        if self._manual_registry is not None or registry.owner is not self.owner or registry.busy:
            raise ScheduleError('Manual registry must be idle and belong to this window owner')
        self._manual_registry = registry
        registry.admission_gate = self._admit_manual
        registry.reservationAdded.connect(lambda record: self._observe_stop_actor(record.actor))
        registry.busyChanged.connect(self._manual_changed)

    def _admit_manual(self):
        if (self.closing or self._jobs or self._pending_actors or self._stop_intent is not None
                or self._queued_stop is not None):
            raise ScheduleError('Scheduling work or stop acknowledgment still owns this library; wait for cleanup')

    def _manual_changed(self, busy):
        self.idleChanged.emit(self.idle)
        self._publish(self.view)
        if not busy:
            self._maybe_ack_stop()
            if self._stop_intent is None and self._queued_stop is None:
                self._idle_event()

    def timing_status(self):
        due = self.due
        if due is None:
            return ScheduleTiming(suspended=self.view.phase not in {'unconfigured', 'not_checked'})
        remaining = None
        if not due.suspended and due.policy.enabled and self.view.phase == 'ready' and not self.closing:
            remaining = math.ceil(max(0, due.deadline - self.monotonic()))
        return ScheduleTiming(remaining, due.active, due.pending,
            bool(getattr(self, '_manual_registry', None) and self._manual_registry.busy and due.pending),
            due.clock_changed, due.suspended or self.closing or self.view.phase != 'ready')

    def _publish(self, view):
        self.view = view
        self.view = replace(view, timing=self.timing_status())
        self.changed.emit(self.view)

    def invalidate_requests(self):
        self.epoch += 1
        self._enable_requests.clear()
        self.timer.stop()
        if self.due is not None:
            self.due.request_cancel()

    def capture_enable(self):
        """UI action captures presented CAS now; it performs no disk read."""
        if self.closing or not self.idle or self.view.phase not in {'unconfigured', 'ready', 'stopped'}:
            raise ScheduleError('Check scheduling status before explicit Enable')
        request = EnableRequest.capture(self.view.control_version,
            None if self.view.locator is None else self.view.locator.revision)
        self._enable_requests = {request.request_id: (request, self.epoch)}
        return request

    def consume_enable(self, request):
        """One live controller/epoch, exact object and one use, never reconstruction."""
        saved = self._enable_requests.get(request.request_id)
        if (self.closing or saved is None or saved[0] is not request
                or saved[1] != self.epoch):
            raise ScheduleError('Explicit Enable action is stale or already consumed')
        del self._enable_requests[request.request_id]
        return request

    def _start_job(self, kind, callback, *, lane='work', actor_factory=None):
        if self.closing and kind not in {'cleanup', 'stop_save'}:
            raise ScheduleError('Library is closing; no new scheduling work')
        if lane in self._lanes:
            raise ScheduleError('This scheduling worker lane is already occupied')
        job = self._job_factory(self.owner, kind, self.epoch, callback, self)
        if actor_factory is not None:
            try:
                job.actor = actor_factory(job)  # Before any actual QThread.start.
                self._observe_stop_actor(job.actor)
            except BaseException:
                job.deleteLater()
                raise
        job.finished.connect(self._job_finished, Qt.ConnectionType.QueuedConnection)
        self._jobs[job] = lane
        self._lanes[lane] = job
        self.idleChanged.emit(False)
        try:
            job.start_owned()
        except BaseException as exc:
            if job.isRunning() or job.isFinished():
                job.error = 'Worker start acknowledgment failed: ' + type(exc).__name__ + ': ' + str(exc)
                job.cancel()
                return job
            del self._jobs[job]
            del self._lanes[lane]
            job.deleteLater()
            self.idleChanged.emit(self.idle)
            raise
        return job

    def check(self):
        if (self.closing or self._manual_busy() or 'work' in self._lanes or self._pending_actors
                or 'stop' in self._lanes or self._stop_intent is not None
                or self._queued_stop is not None):
            # Do not invalidate a stop acknowledgment's no-work attestation by
            # creating new reconciliation children while its transaction waits.
            return False
        self.timer.stop()
        self._publish(ScheduleView('checking', state=self.view.state,
                                   locator=self.view.locator))
        def lookup(job):
            if job.cancel_event.is_set():
                return ScheduleView('canceled')
            discovery = self.config.discover()
            if job.cancel_event.is_set():
                return ScheduleView('canceled')
            if discovery.locator is None or discovery.state is None:
                return ScheduleView(discovery.status, state=discovery.state,
                                    locator=discovery.locator, error=discovery.reason)
            actor = job.actor
            report = actor.reconcile()  # Actual original inspection off UI.
            # Re-read actual control AFTER the main operation, before any timer
            # rearm. A saved stop may have arrived during real inspection.
            with ControlStore(self.config.root, self.owner.path) as store:
                if store.identity != actor.locators.identity:
                    raise ScheduleError('Locator directory changed during scheduling check')
                control, version = store.read_control()
            self.owner.validate()
            if report.cleanup_pending:
                phase = 'cleanup_pending'
            elif control is None:
                phase = 'suspended'
            elif control.action == 'stop_requested':
                phase = 'saved_stop_cleanup_unknown'
            elif control.action == 'stopped':
                phase = 'stopped'
            elif not control.permits(discovery.locator) or report.status != 'reconciled':
                phase = 'suspended'
            else:
                phase = 'ready'
            # A changed revision during reconciliation must not reuse old facts.
            if report.state is not None and report.state.locator != discovery.locator:
                phase = 'suspended'
            return ScheduleView(phase, report.state, discovery.locator, control,
                version, report.success_currently_verified,
                report.error or ('Control is missing; explicit configuration required' if control is None else None))
        self._start_job('check', lookup, actor_factory=lambda job: SnapshotOperations(self.config, cancel_event=job.cancel_event))
        return True

    def _observe_stop_actor(self, actor):
        for intent in (self._stop_intent, self._queued_stop):
            if intent is not None:
                intent['session'].observe_actor(actor)

    def _read_result_view(self, state, actor, *, verified=False, error=None):
        with ControlStore(self.config.root, self.owner.path) as store:
            pin = getattr(actor, 'locators', None)
            if pin is not None and store.identity != pin.identity:
                raise ScheduleError('Locator directory changed during operation')
            control, version = store.read_control()
        self.owner.validate()
        phase = 'ready'
        if actor.active:
            phase = 'cleanup_pending'
        elif control is None or not control.permits(state.locator):
            phase = ('saved_stop_cleanup_unknown' if control is not None
                     and control.action == 'stop_requested' else
                     'stopped' if control is not None and control.action == 'stopped' else 'suspended')
        elif state.status.cleanup_pending or state.status.outcome in {'in_progress', 'uncertain', 'cleanup_warning'}:
            phase = 'suspended'
        return ScheduleView(phase, state, state.locator, control, version, verified, error)

    def enable(self, request, policy, *, managed_directory=None):
        if not self.idle:
            raise ScheduleError('Actual operation cleanup must finish before Enable')
        self.consume_enable(request)
        self.invalidate_requests()
        self._stop_intent = None
        self._queued_stop = None
        self._publish(ScheduleView('enabling', self.view.state, self.view.locator))
        def factory(job):
            operation = ControlledEnableOperation(self.config, request)
            operation.actor.cancel = job.cancel_event
            return operation
        def configure(job):
            return job.actor.run(policy, managed_directory=managed_directory)
        self._start_job('enable', configure, actor_factory=factory)

    def snapshot_now(self):
        return self._dispatch_backup(manual=True)

    def _dispatch_backup(self, *, manual=False):
        if (self.closing or not self.idle or self.due is None
                or self.view.phase != 'ready' or self._stop_intent is not None):
            if manual:
                raise ScheduleError('Schedule is stopped, suspended or busy')
            return False
        self.due.start(manual=manual, recovery_idle=True)
        self._publish(self.view)
        def backup(job):
            job.outcome = job.actor.backup()
            return self._read_result_view(job.outcome.state, job.actor,
                verified=job.outcome.success_currently_verified, error=job.outcome.error)
        try:
            self._start_job('backup', backup, actor_factory=lambda job:
                SnapshotOperations(self.config, cancel_event=job.cancel_event))
        except BaseException:
            self.due.finish('failed')
            raise
        return True

    def disable(self, *, reason='explicit disable'):
        if self.closing or self.view.locator is None:
            raise ScheduleError('A checked configured library is required to save a stop')
        locator = self.view.locator
        self.invalidate_requests()
        self.due = None
        intent = {'session': LiveStopSession(self.config), 'locator': locator,
                  'epoch': self.epoch, 'reason': reason, 'saved': None, 'acked': False, 'ack_failed': False}
        for job in self._jobs:
            if job.actor is not None:
                intent['session'].observe_actor(job.actor)
            if job.kind not in {'stop_save', 'stop_ack', 'cleanup'}:
                job.cancel()
        if self._manual_registry is not None:
            for reservation in self._manual_registry.reservations():
                intent['session'].observe_actor(reservation.actor)
        for actor in self._pending_actors:
            intent['session'].observe_actor(actor)
            actor.request_cancel()
        self._publish(ScheduleView('stopping_not_saved', self.view.state, locator))
        if 'stop' in self._lanes:
            self._queued_stop = intent  # One latest request; never parallel writers.
        else:
            self._stop_intent = intent
            self._start_stop_save(intent)

    def _start_stop_save(self, intent):
        def save(job):
            return intent['session'].request(intent['locator'], utc=int(self.utc()), reason=intent['reason'])
        job = self._start_job('stop_save', save, lane='stop')
        job.stop_intent = intent

    def _observe_stopped(self, control, version, locator, job):
        """Fresh durable state after ack; no recursive locks or child pipeline.

        Original ack has returned/released control before this upstream lock
        acquisition. A stale main reply is never a substitute for this read.
        """
        self.config._placement()
        with LockedDirectory(self.config.root, self.config.leaf + '.lock') as pointers:
            current, locator_version = pointers.read(self.config.leaf, locator=True)
            transition, transition_version = pointers.read(self.config.transition_leaf, transition=True)
            if (current != locator or transition is None or transition.phase != 'committed'
                    or transition.locator != current):
                raise ScheduleError('Configuration changed after stop acknowledgment')
            self.config._placement(locator.binding.directory_path)
            with LockedDirectory(locator.binding.directory_path, 'schedule.lock') as managed:
                state, state_version = managed.read('schedule.json')
                validate_pair(locator, state, self.owner)
                review = (state.status.cleanup_pending or state.status.outcome in
                          {'in_progress', 'uncertain', 'cleanup_warning'} or pending_intent(state) is not None)
                verified = False
                error = 'Recovery review required; scheduling is stopped' if review else None
                if state.last_success is not None:
                    # Borrow the SAME authenticated store; never _begin/reconcile
                    # or reacquire native locks and never launch an inspector.
                    facts = SnapshotOperations(self.config, cancel_event=job.cancel_event)
                    facts.managed = managed
                    point = state.last_success
                    try:
                        verified = facts._facts(point.leaf) == (point.file_identity, point.size, point.sha256)
                    except (ValueError, OSError) as exc:
                        review = True
                        error = 'Last verified snapshot needs review: ' + type(exc).__name__
                    if not verified:
                        review = True
                        error = error or 'Last verified snapshot changed; review required'
                self.owner.validate()
                if (managed.read('schedule.json') != (state, state_version)
                        or pointers.read(self.config.leaf, locator=True) != (current, locator_version)
                        or pointers.read(self.config.transition_leaf, transition=True) != (transition, transition_version)):
                    raise ScheduleError('Durable state changed during stopped-status observation')
                with ControlStore(self.config.root, self.owner.path) as store:
                    if store.identity != pointers.identity or store.read_control() != (control, version):
                        raise ScheduleError('Control changed after stop acknowledgment')
                pointers.validate()
                managed.validate()
                self.owner.validate()
                return ScheduleView('stopped', state, locator, control, version,
                                    verified, error, review)

    def _maybe_ack_stop(self):
        intent = self._stop_intent
        if (self.closing or intent is None or intent['saved'] is None or intent['acked'] or intent.get('ack_failed', False)
                or self._queued_stop is not None or self._jobs or self._pending_actors or self._manual_busy()):
            return
        request, version = intent['saved']
        def acknowledge(job):
            control, saved_version = intent['session'].acknowledge(
                request, version, intent['locator'], thread_finished=True, queued_work=False)
            try:
                view = self._observe_stopped(control, saved_version, intent['locator'], job)
            except Exception as exc:
                # Ack was saved, but never copy stale UI state or claim current
                # package verification when authoritative observation failed.
                view = ScheduleView('stop_saved_status_unknown', locator=intent['locator'],
                    control=control, control_version=saved_version, currently_verified=False,
                    error='Stop saved; current durable status needs review: ' + type(exc).__name__ + ': ' + str(exc),
                    recovery_review_required=True)
                return _StopAcknowledgment(control, saved_version, view, observation_failed=True)
            return _StopAcknowledgment(control, saved_version, view)
        job = self._start_job('stop_ack', acknowledge, lane='stop')
        job.stop_intent = intent

    @Slot()
    def _job_finished(self):
        job = self.sender()
        lane = self._jobs.pop(job, None)
        if lane is None:
            return
        self._lanes.pop(lane, None)
        try:
            if job.kind == 'cleanup' and job.error is None:
                observed, remaining = job.result
                self._pending_actors = [actor for actor in self._pending_actors
                    if all(actor is not known for known in observed)] + list(remaining)
            if job.actor is not None:
                self._observe_stop_actor(job.actor)
                if job.actor.active and all(actor is not job.actor for actor in self._pending_actors):
                    self._pending_actors.append(job.actor)
            intent = getattr(job, 'stop_intent', None)
            if job.kind == 'stop_save' and job.error is None and intent is not None:
                intent['saved'] = job.result
            if (job.kind == 'stop_ack' and intent is self._stop_intent and intent is not None
                    and job.epoch == self.epoch
                    and (job.error is not None or job.result.observation_failed)):
                # Retain this exact saved request/CAS and its work veto. A fresh
                # explicit Disable creates a new intent; ordinary wakes cannot retry.
                intent['ack_failed'] = True
            if (job.kind == 'stop_ack' and job.error is None and intent is not None
                    and not job.result.observation_failed):
                intent['acked'] = True
                if intent is self._stop_intent and self._queued_stop is None:
                    # Persisted control/CAS stays in the immutable view below.
                    # This session's authority/actors have completed their scope;
                    # later refresh jobs must not consume its bounded actor budget.
                    self._stop_intent = None
            if job.epoch == self.epoch and not self.closing:
                if job.error:
                    self.due = None
                    phase = ('stop_save_uncertain' if job.error_state_uncertain else 'stop_not_saved') if job.kind == 'stop_save' else 'stop_saved_status_unknown' if job.kind == 'stop_ack' else 'suspended'
                    self._publish(ScheduleView(phase, self.view.state, self.view.locator,
                        error=job.error, recovery_review_required=job.kind == 'stop_ack' or (job.kind == 'stop_save' and job.error_state_uncertain)))
                elif job.kind == 'stop_ack':
                    self._publish(job.result.view)
                elif job.kind == 'stop_save':
                    request, version = job.result
                    self._publish(ScheduleView('stop_saved_waiting_cleanup', self.view.state,
                        intent['locator'], request, version, self.view.currently_verified))
                elif job.kind in {'check', 'backup'}:
                    if type(job.result) is not ScheduleView:
                        self.due = None
                        self._publish(ScheduleView('suspended', error='Worker finished without a checked status'))
                    else:
                        self._publish(job.result)
                        if self.view.phase == 'ready':
                            if job.kind == 'backup' and self.due is not None and self.due.active:
                                result = job.outcome
                                outcome = result.status if result.status in {'verified', 'failed', 'canceled'} else 'uncertain'
                                self.due.finish(outcome,
                                    verified_utc=self.view.state.status.last_success_utc if outcome == 'verified' else None,
                                    cleanup_complete=not job.actor.active)
                            else:
                                self.due = DueState(self.view.state.policy, self.view.state.status,
                                                   utc=self.utc, monotonic=self.monotonic)
                        else:
                            self.due = None
                elif job.kind == 'enable':
                    self._publish(ScheduleView('cleanup_pending', job.result, job.result.locator))
        finally:
            if job.retained:
                job.owner.release()
                job.retained = False
            job.deleteLater()
            if self._queued_stop is not None and 'stop' not in self._lanes:
                self._stop_intent, self._queued_stop = self._queued_stop, None
                self._start_stop_save(self._stop_intent)
            elif self._pending_actors and 'cleanup' not in self._lanes:
                self.cleanup_timer.start(250)
            else:
                self._maybe_ack_stop()
                if (not self.closing and not self._jobs and not self._pending_actors
                        and self._stop_intent is None):
                    if job.kind in {'enable', 'cleanup'}:
                        self.check()  # Actual config/control after cleanup, off UI.
                    else:
                        self._idle_event()
            self.idleChanged.emit(self.idle)

    def _idle_event(self):
        # Explicit completion/UI events may evaluate immediately; timer-driven
        # wakeups alone remain minute-bounded.
        if self.due is not None and self.view.phase == 'ready' and not self.closing:
            if self.due.poll(recovery_idle=self.idle):
                self._dispatch_backup()
                return
        self._arm_deadline()

    def _arm_deadline(self):
        self.timer.stop()
        self._publish(self.view)
        if self.closing or self.due is None or self.due.suspended or self._jobs or self._pending_actors:
            return
        remaining = max(0, self.due.deadline - self.monotonic())
        # At most once/minute, no tight scheduling I/O poll. Explicit UI/job
        # events can act sooner. Qt's signed-int timer bound is respected.
        self.timer.start(min(2**31 - 1, max(60000, math.ceil(remaining * 1000))))

    @Slot()
    def _deadline_event(self):
        if self.due is not None and not self.closing:
            if self.due.poll(recovery_idle=self.idle):
                self._dispatch_backup()
            else:
                self._arm_deadline()

    @Slot()
    def _cleanup_event(self):
        if not self._pending_actors or 'cleanup' in self._lanes:
            return
        actors = tuple(self._pending_actors)
        def reap(job):
            remaining = []
            for actor in actors:
                clean = (actor.finish_thread() if isinstance(actor, ControlledEnableOperation)
                         else actor.reap_owned_cleanup())
                if not clean:
                    remaining.append(actor)
            return actors, remaining
        self._start_job('cleanup', reap, lane='cleanup')

    def cancel_operation(self):
        # Cancel is not durable Disable. Preserve completion/ledger observation;
        # do not discard a real result merely because cancellation was requested.
        self._enable_requests.clear()
        if self.due is not None:
            self.due.request_cancel()
        for job in self._jobs:
            if job.kind not in {'stop_save', 'stop_ack', 'cleanup'}:
                job.cancel()
        for actor in self._pending_actors:
            actor.request_cancel()
        self._publish(self.view)

    def resume_after_close_refusal(self):
        if not self.idle:
            raise ScheduleError('Owned cleanup must finish before reopening controls')
        self.closing = False
        self.due = None
        if self._manual_registry is not None:
            self._manual_registry.closing = False
        return self.check()  # Real off-UI observation; no warning/intent repair.

    def begin_close(self):
        self.closing = True
        if self._manual_registry is not None:
            self._manual_registry.begin_close()
        self.invalidate_requests()
        for job in self._jobs:
            if job.kind not in {'stop_save', 'stop_ack', 'cleanup'}:
                job.cancel()
        for actor in self._pending_actors:
            actor.request_cancel()
        if self._pending_actors:
            self.cleanup_timer.start(250)
        return self.idle
