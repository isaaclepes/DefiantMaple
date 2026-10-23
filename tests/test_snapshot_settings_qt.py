"""Presentation/action guards only; fake controller never performs persistence."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototypes' / 'qt'))
from defiantmaple.scheduled_snapshots import Policy
if QApplication is not None:
    from scheduled_snapshots_qt import ScheduleView
    from snapshot_settings_qt import SnapshotSettingsDialog
    class Controller(QObject):
        changed = Signal(object)
        idleChanged = Signal(bool)
        def __init__(self):
            super().__init__()
            self.view = ScheduleView('unconfigured')
            self.idle = True
            self.closing = False
            self.calls = []
        def capture_enable(self):
            self.calls.append(('capture',))
            return object()
        def enable(self, request, policy, **kwargs):
            self.calls.append(('enable', request, policy, kwargs))
        def disable(self, **kwargs): self.calls.append(('disable', kwargs))
        def snapshot_now(self): self.calls.append(('snapshot',))
        def check(self): self.calls.append(('check',))


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class SnapshotSettingsTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.controller = Controller()
        self.dialog = SnapshotSettingsDialog(self.controller)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'new-dedicated-snapshots'
        self.dialog.destination.setText(str(self.target))

    def tearDown(self):
        self.dialog.close(); self.dialog.deleteLater(); self.controller.deleteLater()

    def state(self, policy, *, point=None):
        locator = SimpleNamespace(revision=1, binding=SimpleNamespace(directory_path=str(self.target)))
        return SimpleNamespace(policy=policy, locator=locator, last_success=point,
            status=SimpleNamespace(last_attempt_utc=10002, outcome='cleanup_warning'))

    def test_explicit_save_omits_retention_by_default_and_does_not_create_directory(self):
        self.assertFalse(self.dialog.retention.isChecked())
        self.dialog.enable.click()
        self.assertEqual([entry[0] for entry in self.controller.calls], ['capture', 'enable'])
        _, _, policy, arguments = self.controller.calls[-1]
        self.assertFalse(policy.retention_enabled)
        self.assertEqual(policy.interval_seconds, 86400)
        self.assertEqual(arguments['managed_directory'], self.target)
        self.assertFalse(self.target.exists())

    def test_missing_caps_and_out_of_range_bytes_refuse_before_capture(self):
        self.dialog.keep_enabled.setChecked(False)
        self.dialog.enable.click()
        self.assertIn('at least one', self.dialog.feedback.text())
        self.assertEqual(self.controller.calls, [])
        self.dialog.bytes_enabled.setChecked(True)
        self.dialog.bytes_limit.setText('1')
        self.dialog.enable.click()
        self.assertEqual(self.controller.calls, [])
        self.dialog.bytes_limit.setText(str(2**40))
        self.dialog.enable.click()
        self.assertEqual(self.controller.calls[-1][2].byte_limit, 2**40)
        self.assertFalse(self.target.exists())

    def test_dirty_policy_cannot_silently_capture_newer_saved_cas(self):
        self.dialog._edit()  # A draft is being edited against the presented view.
        self.controller.view = ScheduleView('stopped', locator=SimpleNamespace(revision=2), control_version='new')
        self.controller.changed.emit(self.controller.view)
        self.dialog.enable.click()
        self.assertIn('refresh', self.dialog.feedback.text())
        self.assertEqual(self.controller.calls, [])

    def test_dialog_close_does_not_stop_or_cancel_window_schedule(self):
        self.dialog.show()
        self.dialog.close()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.controller.calls, [])

    def test_status_preserves_history_warning_and_exact_nonminute_saved_interval(self):
        point = SimpleNamespace(sequence=7, verified_utc=10000)
        state = self.state(Policy(enabled=True, interval_seconds=901), point=point)
        self.controller.view = ScheduleView('stopped', state, state.locator,
            control_version='saved', currently_verified=False, recovery_review_required=True)
        self.controller.changed.emit(self.controller.view)
        text = self.dialog.status.text()
        self.assertIn('Scheduling disabled', text)
        self.assertIn('#7', text)
        self.assertIn('not currently reverified', text)
        self.assertIn('Recovery review required', text)
        self.assertEqual(self.dialog.policy().interval_seconds, 901)
        self.dialog.interval.setValue(20)
        self.assertEqual(self.dialog.policy().interval_seconds, 1200)

    def test_busy_retention_off_requests_stop_without_claiming_policy_saved(self):
        state = self.state(Policy(enabled=True, retention_enabled=True))
        self.controller.view = ScheduleView('ready', state, state.locator, control_version='saved')
        self.controller.idle = False
        self.controller.changed.emit(self.controller.view)
        self.dialog.retention.setChecked(False)
        self.assertTrue(self.dialog.enable.isEnabled())
        self.dialog.enable.click()
        self.assertEqual(self.controller.calls, [('disable', {'reason': 'retention-off requested'})])
        self.assertIn('after cleanup', self.dialog.feedback.text())

    def test_unsupported_view_disables_only_scheduling_actions_and_does_no_work(self):
        self.controller.view = ScheduleView('unsupported', error='Original native adapter unavailable')
        self.controller.changed.emit(self.controller.view)
        self.assertFalse(self.dialog.enable.isEnabled())
        self.assertFalse(self.dialog.snapshot.isEnabled())
        self.assertIn('Original native adapter unavailable', self.dialog.status.text())
        self.assertEqual(self.controller.calls, [])

    def test_sampled_timing_readout_does_not_claim_live_countdown_after_clock_advances(self):
        from dataclasses import replace
        from scheduled_snapshots_qt import ScheduleTiming, SnapshotController
        from snapshot_settings_qt import status_text
        from defiantmaple.scheduled_snapshots import DueState, PhaseStatus
        now = [100]
        controller = SnapshotController(SimpleNamespace(owner=SimpleNamespace()),
            utc=lambda: 10000, monotonic=lambda: now[0])
        try:
            controller.view = ScheduleView('ready')
            controller.due = DueState(Policy(True, 900, False, 10, None),
                PhaseStatus(10000, None, 'failed'), utc=lambda: 10000, monotonic=lambda: now[0])
            sample = replace(controller.view, timing=controller.timing_status())
            now[0] += 1000
            text = status_text(sample)
            self.assertIn('At the last status update, next due was in approximately 900 seconds', text)
            self.assertEqual(sample.timing.remaining_seconds, 900)
            current = replace(controller.view, timing=controller.timing_status())
            self.assertIn('At the last status update, the next run was due', status_text(current))
            self.assertFalse(controller._jobs)
            self.assertFalse(controller.timer.isActive())
        finally:
            controller.deleteLater()
