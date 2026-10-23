"""Actual Qt lifecycle with injected actors; no native recovery Process evidence."""
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    from PySide6.QtCore import QObject, Signal, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototypes' / 'qt'))
if QApplication is not None:
    from prototypes.qt.recovery_lifecycle_qt import ManualCall, ManualJobRegistry, _ManualJob
    class Readiness(QObject):
        changed = Signal()


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class ManualLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.monitor = Readiness()
        self.owner = Mock()
        self.owner.path = Path('/generated/source.sqlite3')
        self.owner.file.identity = (1, 2)
        self.events = []
        self.actors = []
        outer = self
        class Actor:
            def __init__(self, owner):
                self.owner = owner
                self.cancel = threading.Event()
                self.active = False
                self.held = False
                self.begin_calls = 0
                self.cleanup_gate = None
                self.cleanup_entered = threading.Event()
                self.cleanup_error = False
                outer.actors.append(self)
            def begin(self):
                self.begin_calls += 1
                self.active = self.held = True
                self.owner.retain()
            def request_cancel(self):
                self.cancel.set()
            def finish_thread(self):
                self.cleanup_entered.set(); outer.monitor.changed.emit()
                if self.cleanup_gate is not None and not self.cleanup_gate.wait(3):
                    raise RuntimeError('generated cleanup barrier deadline')
                if self.cleanup_error:
                    raise RuntimeError('generated exact cleanup failure')
                if self.held:
                    self.held = False
                    self.owner.release()
                self.active = False
                return True
        self.actor_class = Actor
        self.registry = ManualJobRegistry(self.owner, actor_factory=Actor)
        self.completed = []
        self.registry.lifecycleComplete.connect(self.completed.append)
        self.call = ManualCall('inspect', self.owner.path, package=Path('/generated/package.dmbackup'))

    def event(self):
        event = threading.Event(); self.events.append(event)
        return event

    def wait_until(self, predicate):
        if predicate(): return
        loop, timer = QEventLoop(), QTimer()
        timer.setSingleShot(True)
        def ready(*args):
            if predicate(): loop.quit()
        signals = (self.monitor.changed, self.registry.busyChanged,
                   self.registry.lifecycleComplete, self.registry.cleanupWarning)
        for signal in signals: signal.connect(ready)
        timer.timeout.connect(loop.quit); timer.start(4000)
        try:
            if not predicate(): loop.exec()
            self.assertTrue(predicate(), 'named manual lifecycle readiness not reached')
        finally:
            timer.stop()
            for signal in signals: signal.disconnect(ready)

    def tearDown(self):
        for event in self.events: event.set()
        for actor in self.actors: actor.cleanup_error = False
        self.registry.begin_close(); self.registry.retry_cleanup()
        self.wait_until(lambda: not self.registry.busy)
        self.registry.deleteLater()

    def test_reservation_is_visible_before_thread_and_actor_begin(self):
        entered, release = self.event(), self.event()
        observed = []
        self.registry.reservationAdded.connect(lambda r: observed.append(
            (self.registry.busy, r.worker.isRunning(), r.actor.begin_calls)))
        def execute(actor):
            entered.set(); self.monitor.changed.emit()
            if not release.wait(3): raise RuntimeError('generated work deadline')
            return {'generated': True}
        with patch.object(ManualCall, 'execute', side_effect=execute):
            record = self.registry.start(self.call)
            self.wait_until(entered.is_set)
            self.assertEqual(observed, [(True, False, 0)])
            self.assertTrue(self.registry.busy)
            release.set(); self.wait_until(lambda: not self.registry.busy)
        self.assertEqual(self.completed[0].identity, record.identity)
        self.assertFalse(self.completed[0].never_started)
        self.assertEqual(self.owner.retain.call_count, self.owner.release.call_count)

    def test_finished_and_active_false_do_not_replace_cleanup_thread_proof(self):
        cleanup_release = self.event()
        with patch.object(ManualCall, 'execute', return_value={'generated': True}):
            record = self.registry.start(self.call)
            record.actor.cleanup_gate = cleanup_release
            self.wait_until(record.actor.cleanup_entered.is_set)
            record.actor.active = False  # Not authoritative cleanup proof.
            self.assertTrue(record.thread_finished)
            self.assertFalse(record.cleanup_verified)
            self.assertTrue(self.registry.busy)
            self.assertEqual(self.completed, [])
            self.owner.release.assert_not_called()
            cleanup_release.set(); self.wait_until(lambda: not self.registry.busy)
        self.assertEqual(len(self.completed), 1)

    def test_never_started_failure_releases_reservation_without_actor_begin(self):
        class BeforeStart(_ManualJob):
            def start(self): raise RuntimeError('generated start failure')
        self.registry._worker_factory = BeforeStart
        with self.assertRaises(RuntimeError): self.registry.start(self.call)
        self.assertFalse(self.registry.busy)
        self.assertEqual(self.actors[0].begin_calls, 0)
        self.assertTrue(self.completed[0].never_started)
        self.owner.release.assert_called_once()

    def test_live_start_error_keeps_thread_actor_and_reservation_until_cleanup(self):
        entered, release = self.event(), self.event()
        class AfterStart(_ManualJob):
            def start(job):
                super().start()
                if not entered.wait(3): raise RuntimeError('generated start-entry deadline')
                raise RuntimeError('generated lost start acknowledgment')
        self.registry._worker_factory = AfterStart
        def execute(actor):
            entered.set(); self.monitor.changed.emit()
            if not release.wait(3): raise RuntimeError('generated work deadline')
            return {'generated': True}
        with patch.object(ManualCall, 'execute', side_effect=execute):
            record = self.registry.start(self.call)
            self.assertTrue(self.registry.busy)
            self.assertTrue(record.worker.isRunning())
            self.assertTrue(record.actor.cancel.is_set())
            self.owner.release.assert_not_called()
            release.set(); self.wait_until(lambda: not self.registry.busy)
        self.assertIn('lost start acknowledgment', self.completed[0].error)
        self.assertFalse(self.completed[0].never_started)

    def test_cleanup_error_retains_owner_and_reservation_for_explicit_retry(self):
        entered, release = self.event(), self.event()
        def execute(actor):
            actor.cleanup_error = True
            entered.set(); self.monitor.changed.emit()
            if not release.wait(3): raise RuntimeError('generated work deadline')
        with patch.object(ManualCall, 'execute', side_effect=execute):
            record = self.registry.start(self.call)
            self.wait_until(entered.is_set)
            release.set()
            self.wait_until(lambda: record.cleanup_error is not None)
            self.assertTrue(self.registry.busy)
            self.assertEqual(self.completed, [])
            self.owner.release.assert_not_called()
            record.actor.cleanup_error = False
            self.registry.retry_cleanup()
            self.wait_until(lambda: not self.registry.busy)
        self.assertIn('exact cleanup failure', self.completed[0].error)

    def test_mapping_review_enable_use_original_functions_inside_actor_scope(self):
        from prototypes.qt import recovery_qt
        from defiantmaple import recovery
        actor = SimpleNamespace(owner=self.owner, cancel=threading.Event(), _invoke=Mock(return_value='scoped'))
        cases = [('mapping', None, recovery_qt._source_mapping),
                 ('review', [('id', '/generated/root')], recovery.review_restored_sources),
                 ('enable', ('id', '/generated/root'), recovery.enable_reviewed_source)]
        with patch.object(recovery_qt, '_identity', return_value=(1, 2)):
            for operation, captured, original in cases:
                call = ManualCall(operation, self.owner.path, catalog_identity=(1, 2), captured=captured)
                self.assertEqual(call.execute(actor), 'scoped')
                self.assertIs(actor._invoke.call_args.args[0], original)
                self.assertEqual(actor._invoke.call_args.args[1], self.owner.path)

    def test_default_stat_guard_does_not_compare_native_identity_namespace(self):
        from prototypes.qt import recovery_qt
        self.owner.file.identity = ('native-volume', b'native-file-id')
        actor = SimpleNamespace(owner=self.owner, cancel=threading.Event(),
                                _invoke=Mock(return_value='scoped'))
        with patch.object(recovery_qt, '_identity', return_value=(101, 202)):
            self.assertEqual(ManualCall('review', self.owner.path, captured=[]).execute(actor), 'scoped')
        actor._invoke.assert_called_once()
        self.owner.validate.assert_called_once()

    def test_default_stat_guard_still_refuses_changed_catalog(self):
        from prototypes.qt import recovery_qt
        actor = SimpleNamespace(owner=self.owner, cancel=threading.Event(), _invoke=Mock())
        with patch.object(recovery_qt, '_identity', side_effect=[(101, 202), (101, 203)]):
            with self.assertRaisesRegex(ValueError, 'Library file changed'):
                ManualCall('mapping', self.owner.path).execute(actor)
        actor._invoke.assert_not_called()

    def test_controller_manual_reservation_blocks_dispatch_and_stop_ack_until_cleanup(self):
        from scheduled_snapshots_qt import SnapshotController, ScheduleView
        from defiantmaple.scheduled_snapshots import DueState, Policy, PhaseStatus
        controller = SnapshotController(SimpleNamespace(owner=self.owner), utc=lambda: 10000, monotonic=lambda: 100)
        controller.attach_manual_registry(self.registry)
        controller.view = ScheduleView('ready')
        controller.due = DueState(Policy(True, 900, False, 10, None), PhaseStatus(),
                                  utc=lambda: 10000, monotonic=lambda: 100)
        gate, cleanup = self.event(), self.event()
        entered = threading.Event()
        def execute(actor):
            actor.cleanup_gate = cleanup
            entered.set(); self.monitor.changed.emit()
            gate.wait(3)
        try:
            with patch.object(ManualCall, 'execute', side_effect=execute):
                self.registry.start(self.call)
                self.wait_until(entered.is_set)
                self.assertFalse(controller.idle)
                self.assertFalse(controller.check())
                with self.assertRaises(ValueError): controller.capture_enable()
                controller._deadline_event()
                self.assertTrue(controller.due.pending)
                self.assertTrue(controller.timing_status().manual_deferred)
                gate.set()
                self.wait_until(lambda: self.actors[0].cleanup_entered.is_set())
                self.assertFalse(controller.idle)
                with patch.object(controller, '_dispatch_backup') as dispatch:
                    cleanup.set()
                    self.wait_until(lambda: not self.registry.busy)
                    dispatch.assert_called_once_with()
        finally:
            gate.set(); cleanup.set(); controller.timer.stop(); controller.deleteLater()

    def test_controller_gate_refuses_manual_before_actor_creation(self):
        from scheduled_snapshots_qt import SnapshotController
        controller = SnapshotController(SimpleNamespace(owner=self.owner))
        controller.attach_manual_registry(self.registry)
        controller._jobs[object()] = 'work'
        try:
            with self.assertRaises(ValueError): self.registry.start(self.call)
            self.assertFalse(self.registry.busy)
            self.assertFalse(self.actors)
        finally:
            controller._jobs.clear(); controller.deleteLater()

    def test_participating_dialog_waits_registry_cleanup_beyond_main_finished(self):
        from prototypes.qt.recovery_qt import RecoveryDialog
        from prototypes.qt import recovery_qt
        gate, cleanup = self.event(), self.event()
        self.actor_class.inspect = lambda actor, package: {'package': str(package)}
        original_begin = self.actor_class.begin
        def begin(actor):
            original_begin(actor); actor.cleanup_gate = cleanup
        self.actor_class.begin = begin
        dialog = RecoveryDialog(self.owner.path, (), registry=self.registry)
        try:
            with patch.object(recovery_qt, '_identity', return_value=(1, 2)):
                dialog._start('inspect', package=Path('/generated/package.dmbackup'))
                self.wait_until(lambda: self.actors[0].cleanup_entered.is_set())
                self.assertIsNotNone(dialog.worker)
                self.assertFalse(dialog.close())
                self.assertTrue(self.registry.busy)
                cleanup.set()
                self.wait_until(lambda: dialog.worker is None)
                self.assertFalse(self.registry.busy)
                self.assertTrue(dialog._closing)
        finally:
            cleanup.set()
            self.wait_until(lambda: not self.registry.busy)
            dialog.close(); dialog.deleteLater()
