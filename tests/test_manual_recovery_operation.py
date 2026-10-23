"""Injected ownership evidence only; no real recovery child is executed."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from defiantmaple import recovery
from defiantmaple.manual_recovery_operation import ManualRecoveryOperation
from defiantmaple.scheduled_snapshots import ScheduleError
from defiantmaple.snapshot_operations import recovery_operation_slot


class ManualOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.owner = Mock()
        self.owner.path = Path('/generated/catalog.sqlite3')
        self.routing = patch('defiantmaple.snapshot_operations.current_session', return_value=self.owner)
        self.routing.start()
        self.addCleanup(self.routing.stop)
        self.actor = ManualRecoveryOperation(self.owner)
        self.actor.begin()
        self.addCleanup(self.cleanup_actor)
        self.reaper = patch.object(recovery, 'reap_recovery_workers',
            return_value={'remaining_workers': 0, 'cleanup_errors': []})
        self.reaper.start()
        self.addCleanup(self.reaper.stop)

    def cleanup_actor(self):
        self.actor.records.clear()
        self.actor.finish_thread()

    def child(self, alive=False):
        process = Mock(pid=12345, exitcode=0)
        process.is_alive.return_value = alive
        return process

    def test_slot_survives_result_until_thread_finished(self):
        self.assertFalse(self.actor.reap())
        with self.assertRaises(ScheduleError):
            with recovery_operation_slot(self.owner):
                pass
        self.assertTrue(self.actor.finish_thread())
        with recovery_operation_slot(self.owner):
            pass
        self.owner.release.assert_called_once()

    def test_inspect_and_restore_other_owner_retain_child(self):
        for source, routed in ((None, None), (Path('/other.sqlite3'), Mock())):
            process = self.child()
            with patch('defiantmaple.manual_recovery_operation.current_session', return_value=routed):
                self.actor._observer(source)('inspect' if source is None else 'restore', process, ())
            self.owner.retain_process.assert_called_with(process)
        self.assertEqual(self.owner.retain_process.call_count, 2)

    def test_original_same_owner_not_double_retained(self):
        with patch('defiantmaple.manual_recovery_operation.current_session', return_value=self.owner):
            self.actor._observer(self.owner.path)('backup', self.child(), ())
        self.owner.retain_process.assert_not_called()

    def test_live_child_keeps_slot_until_exact_exit(self):
        process = self.child(True)
        self.actor._observer(None)('inspect', process, ())
        self.assertFalse(self.actor.finish_thread())
        self.owner.release.assert_not_called()
        process.is_alive.return_value = False
        self.assertTrue(self.actor.reap())
        recovery.reap_recovery_workers.assert_called_with(0, _only_process=process)

    def test_recreated_stage_never_deleted_or_acknowledged_clean(self):
        with TemporaryDirectory() as root:
            stage = Path(root) / 'original-stage'
            stage.write_bytes(b'replacement sentinel')
            self.actor._observer(None)('inspect', self.child(), (stage,))
            self.assertFalse(self.actor.finish_thread())
            self.assertEqual(stage.read_bytes(), b'replacement sentinel')
            self.owner.release.assert_not_called()

    def test_callback_retention_error_keeps_actual_record(self):
        self.owner.retain_process.side_effect = RuntimeError('injected retention failure')
        process = self.child(True)
        with self.assertRaises(RuntimeError):
            self.actor._observer(None)('inspect', process, ())
        self.assertIs(self.actor.records[0]['process'], process)
        self.assertFalse(self.actor.finish_thread())
        process.is_alive.return_value = False
        self.assertTrue(self.actor.reap())

    def test_restore_optional_observer_forwarded_without_changing_arguments(self):
        with patch.object(recovery, '_run', return_value={'generated': True}) as run:
            callback = Mock()
            result = recovery.restore_metadata(Path('/generated/a.dmbackup'), Path('/generated/b.sqlite3'),
                cache_roots=(), live_catalog=None, _process_started=callback)
            self.assertEqual(result, {'generated': True})
            self.assertIs(run.call_args.kwargs['_process_started'], callback)
            self.assertIsNone(run.call_args.args[1][4])
        with patch.object(recovery, '_run') as run:
            recovery.restore_metadata(Path('/generated/a.dmbackup'), Path('/generated/b.sqlite3'),
                cache_roots=(), live_catalog=None)
            self.assertIsNone(run.call_args.kwargs['_process_started'])

    def test_concurrent_invocation_refused_before_second_api_start(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        errors = []
        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('generated barrier deadline')
        def invoke():
            try:
                self.actor.inspect(Path('/generated/package.dmbackup'))
            except BaseException as exc:
                errors.append(exc)
        with patch.object(recovery, 'inspect_package', side_effect=blocked) as inspect:
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(ScheduleError):
                    self.actor.inspect(Path('/generated/second.dmbackup'))
                with self.assertRaises(ScheduleError):
                    self.actor.finish_thread()
                self.assertEqual(inspect.call_count, 1)
            finally:
                release.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

    def test_backup_wrong_source_refused_before_api_start(self):
        with patch.object(recovery, 'backup_metadata') as backup:
            with self.assertRaises(ScheduleError):
                self.actor.backup(Path('/another/catalog.sqlite3'), Path('/generated/new.dmbackup'),
                                  cache_roots=())
            backup.assert_not_called()
