"""Platform-neutral Qt controller guards; no admitted/native worker evidence."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

try:
    from PySide6.QtCore import QEventLoop, QTimer, QObject, Signal
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototypes' / 'qt'))
if QApplication is not None:
    from scheduled_snapshots_qt import ScheduleView, SnapshotController, _ScheduleJob
from defiantmaple.scheduled_snapshots import DueState, PhaseStatus, Policy, ScheduleError


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class ControllerGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.owner = Mock()
        self.config = SimpleNamespace(owner=self.owner)
        self.controller = SnapshotController(self.config, utc=lambda: 10000, monotonic=lambda: 100)
        self.controller.view = ScheduleView('unconfigured')

    def tearDown(self):
        self.controller.timer.stop()
        self.controller.cleanup_timer.stop()
        self.controller.deleteLater()

    def test_timing_projects_monotonic_deadline_and_one_pending_without_utc(self):
        self.controller.view = ScheduleView('ready')
        self.controller.due = DueState(Policy(True, 900, False, 10, None),
            PhaseStatus(9990, None, 'failed'), utc=lambda: 10000, monotonic=lambda: 100)
        timing = self.controller.timing_status()
        self.assertEqual(timing.remaining_seconds, 890)
        self.assertFalse(timing.pending)
        self.controller.due.pending = True
        self.controller._manual_registry = SimpleNamespace(busy=True)
        timing = self.controller.timing_status()
        self.assertTrue(timing.pending)
        self.assertTrue(timing.manual_deferred)
        self.controller.due.suspended = True
        self.assertIsNone(self.controller.timing_status().remaining_seconds)

    def test_timing_reports_backward_wall_restart_without_fabricated_wall_due(self):
        self.controller.view = ScheduleView('ready')
        self.controller.due = DueState(Policy(True, 900, False, 10, None),
            PhaseStatus(11000, None, 'failed'), utc=lambda: 10000, monotonic=lambda: 100)
        timing = self.controller.timing_status()
        self.assertTrue(timing.clock_adjusted)
        self.assertEqual(timing.remaining_seconds, 900)
        self.controller.view = ScheduleView('suspended')
        self.assertTrue(self.controller.timing_status().suspended)
        self.assertIsNone(self.controller.timing_status().remaining_seconds)

    def test_cancel_requests_actual_work_but_preserves_stop_lane_and_result_epoch(self):
        work, stop = Mock(kind='backup'), Mock(kind='stop_save')
        self.controller._jobs = {work: 'work', stop: 'stop'}
        actor = Mock()
        self.controller._pending_actors = [actor]
        epoch = self.controller.epoch
        self.controller.cancel_operation()
        work.cancel.assert_called_once()
        stop.cancel.assert_not_called()
        actor.request_cancel.assert_called_once()
        self.assertEqual(self.controller.epoch, epoch)
        self.assertEqual(self.controller.view.phase, 'unconfigured')
        self.controller._jobs.clear()
        self.controller._pending_actors.clear()

    def test_stop_ack_rejects_prebegin_manual_reservation_even_when_actor_inactive(self):
        self.controller._manual_registry = SimpleNamespace(busy=True)
        self.controller._stop_intent = {'saved': ('request', 'version'), 'acked': False}
        with patch.object(self.controller, '_start_job') as start:
            self.controller._maybe_ack_stop()
        start.assert_not_called()

    def test_enable_is_exact_live_object_single_use_and_controller_scoped(self):
        request = self.controller.capture_enable()
        with self.assertRaises(ScheduleError):
            self.controller.consume_enable(replace(request))
        other = SnapshotController(self.config)
        try:
            with self.assertRaises(ScheduleError):
                other.consume_enable(request)
        finally:
            other.deleteLater()
        self.assertIs(self.controller.consume_enable(request), request)
        with self.assertRaises(ScheduleError):
            self.controller.consume_enable(request)

    def test_newer_capture_and_stop_epoch_invalidate_queued_enable(self):
        first = self.controller.capture_enable()
        second = self.controller.capture_enable()
        self.assertEqual(len(self.controller._enable_requests), 1)
        with self.assertRaises(ScheduleError):
            self.controller.consume_enable(first)
        self.controller.invalidate_requests()
        with self.assertRaises(ScheduleError):
            self.controller.consume_enable(second)

    def test_deadline_timer_is_minute_bounded_and_never_starts_a_worker(self):
        controller = self.controller
        controller.due = DueState(Policy(enabled=True), PhaseStatus(),
                                  utc=lambda: 10000, monotonic=lambda: 100)
        controller._arm_deadline()
        self.assertGreaterEqual(controller.timer.interval(), 60000)
        controller._deadline_event()
        self.assertTrue(controller.due.pending)
        self.assertEqual(controller._jobs, {})
        controller.due.suspended = True
        controller._arm_deadline()
        self.assertFalse(controller.timer.isActive())

    def test_close_disarms_and_blocks_new_main_jobs(self):
        request = self.controller.capture_enable()
        self.assertTrue(self.controller.begin_close())
        self.assertFalse(self.controller.timer.isActive())
        with self.assertRaises(ScheduleError):
            self.controller.consume_enable(request)
        with self.assertRaises(ScheduleError):
            self.controller._start_job('check', lambda job: None)
        self.assertFalse(self.controller.check())

    def test_canceled_before_run_performs_no_owner_validation_or_callback(self):
        callback = Mock()
        job = _ScheduleJob(self.owner, 'check', 0, callback, self.controller)
        job.cancel()
        job.run()  # Synchronous unit call: no QThread/native worker is started.
        self.assertEqual(job.result.phase, 'canceled')
        self.owner.validate.assert_not_called()
        callback.assert_not_called()
        self.assertTrue(job.cancel_event.is_set())
        job.deleteLater()

    def test_cancel_during_owner_validation_prevents_discovery_dispatch(self):
        callback = Mock()
        job = _ScheduleJob(self.owner, 'check', 0, callback, self.controller)
        self.owner.validate.side_effect = job.cancel
        job.run()  # Synchronous guard oracle, not an actual worker test.
        self.assertEqual(job.result.phase, 'canceled')
        callback.assert_not_called()
        self.assertTrue(job.cancel_event.is_set())
        job.deleteLater()

    def test_cancel_before_actor_assignment_stays_set_in_external_event(self):
        from defiantmaple.snapshot_operations import SnapshotOperations
        callback = Mock()
        job = _ScheduleJob(self.owner, 'check', 0, callback, self.controller)
        job.cancel()
        actor = SnapshotOperations(self.config, cancel_event=job.cancel_event)
        job.actor = actor
        with patch('defiantmaple.snapshot_operations._slot') as slot:
            with self.assertRaises(ScheduleError):
                actor.reconcile()
            slot.assert_not_called()
        self.assertIs(actor.cancel, job.cancel_event)
        self.assertTrue(actor.cancel.is_set())
        job.deleteLater()


if QApplication is not None:
    class _Readiness(QObject):
        changed = Signal()


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class ControllerThreadTests(unittest.TestCase):
    """Actual QThreads with injected in-memory backends; no recovery Process."""
    def setUp(self):
        import threading
        self.app = QApplication.instance() or QApplication([])
        self.monitor = _Readiness()
        self.owner = Mock()
        self.config = SimpleNamespace(owner=self.owner)
        self.controller = SnapshotController(self.config)
        self.release_events = []
        self.controller.view = ScheduleView('ready', locator=object())
        self.authoritative_state = None
        self.authoritative_verified = False
        self.authoritative_review = False
        self.observation_error = None
        def observe(control, version, locator, job):
            if self.observation_error is not None:
                raise self.observation_error
            return ScheduleView('stopped', self.authoritative_state, locator, control,
                version, self.authoritative_verified,
                'Recovery review required' if self.authoritative_review else None,
                self.authoritative_review)
        observation = patch.object(self.controller, '_observe_stopped', side_effect=observe)
        observation.start()
        self.addCleanup(observation.stop)

    def event(self):
        import threading
        event = threading.Event()
        self.release_events.append(event)
        return event

    def wait_until(self, predicate, timeout=4000):
        if predicate():
            return
        loop = QEventLoop()
        deadline = QTimer()
        deadline.setSingleShot(True)
        def changed(*args):
            if predicate():
                loop.quit()
        signals = (self.monitor.changed, self.controller.changed, self.controller.idleChanged)
        for signal in signals:
            signal.connect(changed)
        deadline.timeout.connect(loop.quit)
        deadline.start(timeout)
        try:
            # Close the set/emit race between initial predicate and signal
            # connections. No sleep or worker deadline is a readiness oracle.
            if not predicate():
                loop.exec()
            self.assertTrue(predicate(), 'named Qt readiness deadline elapsed')
        finally:
            deadline.stop()
            for signal in signals:
                signal.disconnect(changed)

    def tearDown(self):
        for event in self.release_events:
            event.set()
        self.controller.begin_close()
        self.wait_until(lambda: self.controller.idle)
        self.controller.cleanup_timer.stop()
        self.controller.deleteLater()

    def test_actual_finished_retains_job_and_owner_until_queued_delivery(self):
        entered, release = self.event(), self.event()
        def work(job):
            entered.set(); self.monitor.changed.emit()
            if not release.wait(3):
                raise RuntimeError('generated main deadline')
            return 'actual callback result'
        job = self.controller._start_job('injected_main', work)
        self.wait_until(entered.is_set)
        self.assertFalse(self.controller.idle)
        self.assertTrue(job.retained)
        self.owner.release.assert_not_called()
        release.set()
        self.wait_until(lambda: self.controller.idle)
        self.owner.release.assert_called_once()

    def test_start_failure_unwinds_unstarted_job(self):
        class BeforeStart(_ScheduleJob):
            def start(self):
                raise RuntimeError('generated start failure')
        self.controller._job_factory = BeforeStart
        with self.assertRaises(RuntimeError):
            self.controller._start_job('injected_main', lambda job: None)
        self.assertTrue(self.controller.idle)
        self.owner.retain.assert_called_once()
        self.owner.release.assert_called_once()

    def test_late_start_failure_keeps_real_live_thread_until_finished(self):
        entered, release = self.event(), self.event()
        class AfterStart(_ScheduleJob):
            def start_owned(job):
                super().start_owned()
                # The injected error is specifically AFTER actual run entry;
                # otherwise sticky cancellation correctly skips the callback.
                if not entered.wait(3):
                    raise RuntimeError('generated late-start entry deadline')
                raise RuntimeError('generated lost start acknowledgment')
        self.controller._job_factory = AfterStart
        def work(job):
            entered.set(); self.monitor.changed.emit()
            if not release.wait(3):
                raise RuntimeError('generated main deadline')
        job = self.controller._start_job('injected_main', work)
        self.wait_until(entered.is_set)
        self.assertIn(job, self.controller._jobs)
        self.assertTrue(job.retained)
        self.assertFalse(self.controller.idle)
        release.set()
        self.wait_until(lambda: self.controller.idle)
        self.assertEqual(self.controller.view.phase, 'suspended')
        self.owner.release.assert_called_once()

    def test_stop_save_while_main_blocked_ack_waits_finished_and_exact_cleanup(self):
        import scheduled_snapshots_qt as module
        main_entered, main_release = self.event(), self.event()
        cleanup_entered, cleanup_release = self.event(), self.event()
        saved, acked = self.event(), self.event()
        controller, owner, monitor = self.controller, self.owner, self.monitor
        class Actor:
            active = True
            def __init__(self):
                self.owner = owner
            def request_cancel(self):
                pass
            def reap_owned_cleanup(self):
                cleanup_entered.set(); monitor.changed.emit()
                if not cleanup_release.wait(3):
                    raise RuntimeError('generated cleanup deadline')
                self.active = False
                return True
        actor = Actor()
        class StopSession:
            def __init__(self, config):
                self.actors = []
            def observe_actor(self, observed):
                if all(item is not observed for item in self.actors):
                    self.actors.append(observed)
            def request(self, locator, **kwargs):
                saved.set(); monitor.changed.emit()
                return SimpleNamespace(action='stop_requested'), 'exact_saved_version'
            def acknowledge(self, request, version, locator, **kwargs):
                if any(item.active for item in self.actors):
                    raise AssertionError('acknowledged active actor')
                if version != 'exact_saved_version' or not kwargs['thread_finished'] or kwargs['queued_work']:
                    raise AssertionError('acknowledged wrong request facts')
                acked.set(); monitor.changed.emit()
                return SimpleNamespace(action='stopped'), 'stopped_version'
        def work(job):
            main_entered.set(); monitor.changed.emit()
            if not main_release.wait(3):
                raise RuntimeError('generated main deadline')
        with patch.object(module, 'LiveStopSession', StopSession):
            main_job = controller._start_job('injected_main', work, actor_factory=lambda job: actor)
            main_finished = self.event()
            main_job.finished.connect(main_finished.set)
            self.wait_until(main_entered.is_set)
            controller.disable()
            self.wait_until(lambda: saved.is_set() and controller.view.phase == 'stop_saved_waiting_cleanup')
            self.assertTrue(main_job.isRunning())
            self.assertFalse(acked.is_set())
            main_release.set()
            self.wait_until(cleanup_entered.is_set)
            self.assertTrue(main_finished.is_set())
            self.assertFalse(controller.idle)
            self.assertFalse(acked.is_set())
            cleanup_release.set()
            self.wait_until(lambda: controller.idle and controller.view.phase == 'stopped')
            self.assertTrue(acked.is_set())
            self.assertFalse(actor.active)
        self.assertEqual(owner.retain.call_count, owner.release.call_count)

    def test_close_blocks_late_ack_but_retains_inflight_saved_stop(self):
        import scheduled_snapshots_qt as module
        entered, release, acked = self.event(), self.event(), self.event()
        monitor = self.monitor
        class StopSession:
            def __init__(self, config):
                pass
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                entered.set(); monitor.changed.emit()
                if not release.wait(3):
                    raise RuntimeError('generated stop-save deadline')
                return SimpleNamespace(action='stop_requested'), 'saved'
            def acknowledge(self, *args, **kwargs):
                acked.set()
                raise AssertionError('close scheduled a late ack')
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(entered.is_set)
            self.assertFalse(self.controller.begin_close())
            self.assertFalse(self.controller.timer.isActive())
            release.set()
            self.wait_until(lambda: self.controller.idle)
            self.assertFalse(acked.is_set())
            self.assertIsNotNone(self.controller._stop_intent['saved'])

    def test_repeated_disable_queues_latest_request_and_never_acks_older(self):
        import scheduled_snapshots_qt as module
        first_entered, first_release = self.event(), self.event()
        monitor = self.monitor
        sessions, acknowledgments = [], []
        class StopSession:
            def __init__(self, config):
                self.number = len(sessions) + 1
                sessions.append(self)
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                if self.number == 1:
                    first_entered.set(); monitor.changed.emit()
                    if not first_release.wait(3):
                        raise RuntimeError('generated first save deadline')
                return SimpleNamespace(action='stop_requested', number=self.number), self.number
            def acknowledge(self, request, version, locator, **kwargs):
                acknowledgments.append((self.number, request.number, version))
                return SimpleNamespace(action='stopped', number=self.number), self.number + 10
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(first_entered.is_set)
            self.controller.disable(reason='newer explicit disable')
            first_release.set()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
        self.assertEqual(acknowledgments, [(2, 2, 2)])
        self.assertEqual(self.controller.view.control.number, 2)

    def test_failed_stop_save_is_visible_and_no_off_ack_is_invented(self):
        import scheduled_snapshots_qt as module
        class StopSession:
            def __init__(self, config):
                pass
            def request(self, locator, **kwargs):
                raise OSError('generated persistence failure StateUncertainError')
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(lambda: self.controller.idle)
        self.assertEqual(self.controller.view.phase, 'stop_not_saved')
        self.assertIn('generated persistence failure', self.controller.view.error)
        self.assertFalse(self.controller.timer.isActive())
        self.assertIsNone(self.controller._stop_intent['saved'])

    def test_uncertain_stop_save_label_keeps_live_veto_and_genuine_finished_ownership(self):
        import scheduled_snapshots_qt as module
        from snapshot_settings_qt import SnapshotSettingsDialog
        from PySide6.QtCore import Qt
        from defiantmaple.scheduled_snapshots import StateUncertainError
        entered, release = self.event(), self.event()
        sessions, finished = [], []
        self.controller.view = ScheduleView('ready', locator=SimpleNamespace(revision=1))
        class StopSession:
            def __init__(self, config):
                self.acknowledge = Mock()
                sessions.append(self)
            def request(self, locator, **kwargs):
                entered.set()
                self_monitor.changed.emit()
                if not release.wait(3):
                    raise RuntimeError('uncertain request release deadline')
                # Deliberately no magic error words: classification must retain the type.
                raise StateUncertainError('generated reply unavailable')
        self_monitor = self.monitor
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(entered.is_set)
            job = next(job for job in self.controller._jobs if job.kind == 'stop_save')
            job.finished.connect(lambda: finished.append((job.retained, job.error_state_uncertain)), Qt.ConnectionType.DirectConnection)
            self.assertTrue(job.retained)
            self.owner.release.assert_not_called()
            release.set()
            self.assertTrue(job.wait(3000), 'genuine uncertainty job did not finish')
            self.assertEqual(finished, [(True, True)])
            self.assertTrue(job.retained)  # Native finish precedes original queued consumer.
            self.owner.release.assert_not_called()
            self.wait_until(lambda: self.controller.idle)
        self.owner.release.assert_called_once()
        self.assertEqual(self.controller.view.phase, 'stop_save_uncertain')
        self.assertIn('generated reply unavailable', self.controller.view.error)
        self.assertTrue(self.controller.view.recovery_review_required)
        self.assertFalse(self.controller.view.currently_verified)
        self.assertIsNone(self.controller._stop_intent['saved'])
        self.assertFalse(self.controller._stop_intent['acked'])
        sessions[0].acknowledge.assert_not_called()
        self.assertFalse(self.controller.timer.isActive())
        self.assertIsNone(self.controller.due)
        self.assertFalse(self.controller.check())  # Existing live-veto gate; no false Refresh promise.
        with self.assertRaises(ScheduleError):
            self.controller.capture_enable()
        with self.assertRaises(ScheduleError):
            self.controller.snapshot_now()
        dialog = SnapshotSettingsDialog(self.controller)
        try:
            self.assertIn('Stop save uncertain; scheduling suspended', dialog.status.text())
            self.assertNotIn('Stop request was not saved', dialog.status.text())
            self.assertFalse(dialog.enable.isEnabled())
            self.assertFalse(dialog.snapshot.isEnabled())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_enable_dispatch_waits_actual_finished_and_offui_actor_cleanup(self):
        import scheduled_snapshots_qt as module
        import threading
        entered, release = self.event(), self.event()
        monitor, owner = self.monitor, self.owner
        instances = []
        class EnableOperation:
            def __init__(self, config, request):
                self.owner = owner
                self.request = request
                self.active = False
                self.actor = SimpleNamespace(cancel=threading.Event())
                instances.append(self)
            def request_cancel(self):
                self.actor.cancel.set()
            def run(self, policy, **kwargs):
                self.active = True
                entered.set(); monitor.changed.emit()
                if not release.wait(3):
                    raise RuntimeError('generated Enable deadline')
                return SimpleNamespace(locator=object())
            def finish_thread(self):
                self.active = False
                return True
        self.controller.view = ScheduleView('unconfigured')
        self.config.discover = Mock(return_value=SimpleNamespace(
            status='unconfigured', state=None, locator=None, reason=None))
        request = self.controller.capture_enable()
        with patch.object(module, 'ControlledEnableOperation', EnableOperation):
            self.controller.enable(request, Policy(enabled=True))
            self.wait_until(entered.is_set)
            self.assertFalse(self.controller.idle)
            self.assertTrue(instances[0].active)
            with self.assertRaises(ScheduleError):
                self.controller.consume_enable(request)
            release.set()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'unconfigured')
            self.assertFalse(instances[0].active)
        self.assertEqual(owner.retain.call_count, owner.release.call_count)

    def test_failed_ack_settles_once_retains_veto_and_fresh_disable_can_succeed(self):
        import scheduled_snapshots_qt as module
        from PySide6.QtCore import Qt
        from defiantmaple.scheduled_snapshots import StateUncertainError
        for failure in (OSError('prepublication failure'), StateUncertainError('readback unavailable')):
            with self.subTest(failure=type(failure).__name__):
                sessions, attempts, finished = [], [], []
                entered, release = self.event(), self.event()
                monitor = self.monitor
                self.controller.view = ScheduleView('ready', locator=SimpleNamespace(revision=1))
                old_enable = self.controller.capture_enable()
                class StopSession:
                    def __init__(self, config):
                        self.number = len(sessions) + 1
                        sessions.append(self)
                    def observe_actor(self, actor):
                        pass
                    def request(self, locator, **kwargs):
                        self.requested = SimpleNamespace(action='stop_requested', number=self.number)
                        return self.requested, self.number
                    def acknowledge(self, request, version, locator, **kwargs):
                        attempts.append((self.number, request, version))
                        if self.number == 1:
                            entered.set(); monitor.changed.emit()
                            if not release.wait(3):
                                raise RuntimeError('first failed ack release deadline')
                            raise failure
                        return SimpleNamespace(action='stopped', number=self.number), self.number + 10
                with patch.object(module, 'LiveStopSession', StopSession):
                    self.controller.disable()
                    self.wait_until(entered.is_set)
                    intent = self.controller._stop_intent
                    saved = intent['saved']
                    job = next(job for job in self.controller._jobs if job.kind == 'stop_ack')
                    job.finished.connect(lambda: finished.append(job.retained), Qt.ConnectionType.DirectConnection)
                    release.set()
                    self.assertTrue(job.wait(3000))
                    self.assertEqual(finished, [True])
                    self.assertTrue(job.retained)
                    self.wait_until(lambda: self.controller.idle)
                    self.assertIs(self.controller._stop_intent, intent)
                    self.assertIs(intent['saved'], saved)
                    self.assertIs(saved[0], sessions[0].requested)
                    self.assertTrue(intent['ack_failed'])
                    self.assertFalse(intent['acked'])
                    self.assertEqual(self.controller.view.phase, 'stop_saved_status_unknown')
                    self.assertTrue(self.controller.view.recovery_review_required)
                    self.assertFalse(self.controller.view.currently_verified)
                    for _ in range(3):
                        self.controller._idle_event()
                        self.controller._cleanup_event()
                        self.controller._maybe_ack_stop()
                        self.controller._start_job('cleanup', lambda job: ((), ()), lane='cleanup')
                        self.wait_until(lambda: self.controller.idle)
                    self.assertEqual(len(attempts), 1)
                    self.assertIsNone(self.controller.due)
                    self.assertFalse(self.controller.timer.isActive())
                    self.assertFalse(self.controller.check())
                    with self.assertRaises(ScheduleError):
                        self.controller.capture_enable()
                    with self.assertRaises(ScheduleError):
                        self.controller.enable(old_enable, Policy(True, 900, False, 10, None))
                    with self.assertRaises(ScheduleError):
                        self.controller.snapshot_now()
                    self.controller.disable(reason='fresh explicit request')
                    self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
                    self.assertEqual([item[0] for item in attempts], [1, 2])
                    self.assertIsNone(self.controller._stop_intent)
                    self.assertEqual(self.controller.view.control.number, 2)
                    self.assertIsNot(sessions[0].requested, sessions[1].requested)
                self.assertEqual(self.owner.retain.call_count, self.owner.release.call_count)

    def test_older_failed_ack_cannot_latch_newer_explicit_disable(self):
        import scheduled_snapshots_qt as module
        entered, release = self.event(), self.event()
        sessions, attempts = [], []
        monitor = self.monitor
        class StopSession:
            def __init__(self, config):
                self.number = len(sessions) + 1
                sessions.append(self)
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                return SimpleNamespace(action='stop_requested', number=self.number), self.number
            def acknowledge(self, request, version, locator, **kwargs):
                attempts.append(self.number)
                if self.number == 1:
                    entered.set(); monitor.changed.emit()
                    if not release.wait(3):
                        raise RuntimeError('older ack release deadline')
                    raise OSError('older epoch ack failure')
                return SimpleNamespace(action='stopped', number=self.number), self.number + 10
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(entered.is_set)
            old_intent = self.controller._stop_intent
            self.controller.disable(reason='newer explicit disable')
            new_intent = self.controller._queued_stop
            self.assertGreater(new_intent['epoch'], old_intent['epoch'])
            release.set()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
            self.assertEqual(attempts, [1, 2])
            self.assertFalse(new_intent['ack_failed'])
            self.assertTrue(new_intent['acked'])
            self.assertEqual(self.controller.view.control.number, 2)
            self.assertIsNone(self.controller.view.error)

    def test_refresh_during_held_stop_ack_starts_no_main_or_backend_call(self):
        import scheduled_snapshots_qt as module
        entered, release = self.event(), self.event()
        monitor = self.monitor
        self.config.discover = Mock()
        class StopSession:
            def __init__(self, config):
                pass
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                return SimpleNamespace(action='stop_requested'), 'saved'
            def acknowledge(self, request, version, locator, **kwargs):
                entered.set(); monitor.changed.emit()
                if not release.wait(3):
                    raise RuntimeError('generated held acknowledgment deadline')
                return SimpleNamespace(action='stopped'), 'stopped'
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(entered.is_set)
            self.assertFalse(self.controller.check())
            self.assertNotIn('work', self.controller._lanes)
            self.config.discover.assert_not_called()
            self.assertEqual(self.controller.view.phase, 'stop_saved_waiting_cleanup')
            release.set()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
        self.assertIsNone(self.controller._stop_intent)

    def test_completed_stop_session_is_not_a_lifetime_actor_inventory(self):
        import scheduled_snapshots_qt as module
        sessions = []
        class StopSession:
            def __init__(self, config):
                self.actors = []
                sessions.append(self)
            def observe_actor(self, actor):
                if len(self.actors) >= 64:
                    raise AssertionError('completed session retained later actors')
                self.actors.append(actor)
            def request(self, locator, **kwargs):
                return SimpleNamespace(action='stop_requested'), 'saved'
            def acknowledge(self, request, version, locator, **kwargs):
                return SimpleNamespace(action='stopped'), 'exact_stopped_CAS'
        self.config.discover = Mock(return_value=SimpleNamespace(
            status='unconfigured', state=None, locator=None, reason=None))
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
            self.assertIsNone(self.controller._stop_intent)
            self.assertEqual(self.controller.view.control_version, 'exact_stopped_CAS')
            self.assertEqual(self.controller.view.control.action, 'stopped')
            previous = tuple(sessions[0].actors)
            for _ in range(66):
                self.assertTrue(self.controller.check())
                self.wait_until(lambda: self.controller.idle)
            self.assertEqual(tuple(sessions[0].actors), previous)
            self.assertEqual(self.config.discover.call_count, 66)

    def test_stopped_view_uses_fresh_durable_success_warning_not_old_epoch_result(self):
        import scheduled_snapshots_qt as module
        entered, release = self.event(), self.event()
        monitor = self.monitor
        previous = SimpleNamespace(last_success=SimpleNamespace(point='previous'))
        actual = SimpleNamespace(last_success=SimpleNamespace(point='newly_registered'),
            status=SimpleNamespace(outcome='cleanup_warning', cleanup_pending=True))
        locator = self.controller.view.locator
        self.controller.view = ScheduleView('ready', previous, locator, currently_verified=True)
        class StopSession:
            def __init__(self, config):
                pass
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                return SimpleNamespace(action='stop_requested'), 'saved'
            def acknowledge(self, request, version, locator, **kwargs):
                return SimpleNamespace(action='stopped'), 'stopped'
        def old_main(job):
            entered.set(); monitor.changed.emit()
            if not release.wait(3):
                raise RuntimeError('generated late durable success deadline')
            # In-memory backend stands in for an actual durable commit AFTER
            # Disable. The original UI reply deliberately remains stale.
            self.authoritative_state = actual
            self.authoritative_review = True
            self.authoritative_verified = False
            return ScheduleView('ready', previous, locator, currently_verified=True)
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller._start_job('backup', old_main)
            self.wait_until(entered.is_set)
            self.controller.disable()
            self.wait_until(lambda: self.controller.view.phase == 'stop_saved_waiting_cleanup')
            release.set()
            self.wait_until(lambda: self.controller.idle and self.controller.view.phase == 'stopped')
        self.assertIs(self.controller.view.state, actual)
        self.assertEqual(self.controller.view.state.last_success.point, 'newly_registered')
        self.assertTrue(self.controller.view.recovery_review_required)
        self.assertIn('review', self.controller.view.error.lower())
        self.assertFalse(self.controller.view.currently_verified)
        self.assertIsNone(self.controller.due)
        self.assertFalse(self.controller.timer.isActive())

    def test_saved_stop_observation_failure_does_not_copy_stale_verified_state(self):
        import scheduled_snapshots_qt as module
        self.controller.view = ScheduleView('ready', SimpleNamespace(last_success='old'),
            self.controller.view.locator, currently_verified=True)
        self.observation_error = OSError('generated durable-state read failure')
        class StopSession:
            def __init__(self, config):
                pass
            def observe_actor(self, actor):
                pass
            def request(self, locator, **kwargs):
                return SimpleNamespace(action='stop_requested'), 'saved'
            def acknowledge(self, request, version, locator, **kwargs):
                return SimpleNamespace(action='stopped'), 'stopped'
        with patch.object(module, 'LiveStopSession', StopSession):
            self.controller.disable()
            self.wait_until(lambda: self.controller.idle
                            and self.controller.view.phase == 'stop_saved_status_unknown')
        self.assertEqual(self.controller.view.phase, 'stop_saved_status_unknown')
        self.assertEqual(self.controller.view.control.action, 'stopped')
        self.assertIsNone(self.controller.view.state)
        self.assertFalse(self.controller.view.currently_verified)
        self.assertTrue(self.controller.view.recovery_review_required)
        self.assertIn('durable-state read failure', self.controller.view.error)
        self.assertFalse(self.controller.timer.isActive())
        intent = self.controller._stop_intent
        self.assertTrue(intent['ack_failed'])
        self.assertFalse(intent['acked'])
        self.assertIsNotNone(intent['saved'])
        self.assertFalse(self.controller.check())
        self.controller._start_job('cleanup', lambda job: ((), ()), lane='cleanup')
        self.wait_until(lambda: self.controller.idle)
        self.assertIs(self.controller._stop_intent, intent)
        self.assertEqual(self.controller.view.phase, 'stop_saved_status_unknown')
