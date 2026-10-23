"""Generated controlled-configuration ordering/fault evidence; no real workers."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from defiantmaple.admission import admission_session
from defiantmaple.controlled_configuration import ControlledEnableOperation, EnableRequest
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import Policy, ScheduleError, StateUncertainError
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from defiantmaple.snapshot_control import ControlStore, LiveStopSession
from defiantmaple.snapshot_operations import recovery_operation_slot
from test_scheduled_snapshots import GeneratedFixture


class ControlledConfigurationTests(GeneratedFixture):
    def setUp(self):
        super().setUp()
        try:
            with private_local_parent(self.root / 'capability-probe'):
                pass
        except ValueError as exc:
            if str(exc) in {'Recovery publication has no reviewed native adapter on this platform',
                            'Recovery requires a verified durable local filesystem'}:
                self.skipTest(str(exc))
            raise

    def config(self, owner):
        return SnapshotConfiguration(owner, self.locators, cache_roots=(), utc=lambda: 10000)

    def first_enable(self, config):
        operation = ControlledEnableOperation(config, EnableRequest.capture(None, None))
        try:
            state = operation.run(Policy(enabled=True), managed_directory=self.root / 'managed-enabled')
        finally:
            self.assertTrue(operation.finish_thread())
        return state

    def test_fresh_enable_exact_run_and_slot_until_thread_finished(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.config(owner)
            operation = ControlledEnableOperation(config, EnableRequest.capture(None, None))
            try:
                state = operation.run(Policy(enabled=True), managed_directory=self.root / 'managed-enabled')
                with ControlStore(config.root, owner.path) as control:
                    value, version = control.read_control()
                self.assertTrue(value.permits(state.locator))
                self.assertEqual(operation.control_version, version)
                with self.assertRaises(ScheduleError):
                    with recovery_operation_slot(owner):
                        pass
                with self.assertRaises(ScheduleError):
                    operation.run(Policy(enabled=True))
            finally:
                self.assertTrue(operation.finish_thread())
            with recovery_operation_slot(owner):
                pass

    def test_captured_enable_cannot_replace_later_saved_stop(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.config(owner)
            initial = self.first_enable(config)
            with ControlStore(config.root, owner.path) as control:
                _, version = control.read_control()
            captured = EnableRequest.capture(version, initial.locator.revision)
            session = LiveStopSession(config)
            stopped, stop_version = session.request(initial.locator, utc=10001, reason='later disable')
            original_state = (Path(initial.locator.binding.directory_path) / 'schedule.json').read_bytes()
            operation = ControlledEnableOperation(config, captured)
            try:
                with self.assertRaises(ScheduleError):
                    operation.run(Policy(enabled=True, interval_seconds=1800))
            finally:
                operation.finish_thread()
            self.assertEqual((Path(initial.locator.binding.directory_path) / 'schedule.json').read_bytes(), original_state)
            with ControlStore(config.root, owner.path) as control:
                self.assertEqual(control.read_control(), (stopped, stop_version))

    def test_saved_request_cannot_be_enabled_by_reconstructed_session(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.config(owner)
            initial = self.first_enable(config)
            _, version = LiveStopSession(config).request(initial.locator, utc=10001, reason='saved stop')
            operation = ControlledEnableOperation(config, EnableRequest.capture(version, initial.locator.revision))
            try:
                with self.assertRaises(ScheduleError):
                    operation.run(Policy(enabled=True))
            finally:
                operation.finish_thread()

    def test_lost_run_readback_ack_leaves_actual_valid_committed_run(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.config(owner)
            operation = ControlledEnableOperation(config, EnableRequest.capture(None, None))
            original = ControlStore.write_control
            def publish_then_fail(store, value, expected):
                original(store, value, expected)
                raise StateUncertainError('generated lost run acknowledgment')
            try:
                with patch.object(ControlStore, 'write_control', publish_then_fail):
                    with self.assertRaises(StateUncertainError):
                        operation.run(Policy(enabled=True), managed_directory=self.root / 'managed-enabled')
            finally:
                operation.finish_thread()
            discovery = config.discover()
            self.assertEqual(discovery.status, 'configured')
            with ControlStore(config.root, owner.path) as control:
                actual, _ = control.read_control()
            self.assertTrue(actual.permits(discovery.locator))

    def test_borrowed_context_expires_and_default_configure_stays_uncontrolled(self):
        from contextlib import contextmanager
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.config(owner)
            contexts = []
            @contextmanager
            def transaction(context):
                contexts.append(context)
                class Commit:
                    def commit(self, state):
                        context.validate()
                        self.state = state
                yield Commit()
            config.configure(Policy(enabled=True), managed_directory=self.root / 'borrowed', _transaction=transaction)
            with self.assertRaises(ScheduleError):
                contexts[0].validate()
            self.assertFalse((config.root / (config.leaf + '.control')).exists())
