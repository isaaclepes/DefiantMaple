"""Generated native fresh inventories; no backup children or retention deletion."""
from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from defiantmaple.admission import admission_session
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import LockedDirectory, Policy, ScheduleError
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from defiantmaple.snapshot_operations import SnapshotOperations
from test_scheduled_snapshots import GeneratedFixture


class InventoryTests(GeneratedFixture):
    def setUp(self):
        super().setUp()
        try:
            with private_local_parent(self.managed / 'capability-probe'):
                pass
        except ValueError as exc:
            if str(exc) in {'Recovery publication has no reviewed native adapter on this platform',
                            'Recovery requires a verified durable local filesystem'}:
                self.skipTest(str(exc))
            raise

    def test_retained_pin_sees_new_package_and_replaced_schedule_names(self):
        with LockedDirectory(self.managed, 'schedule.lock') as store:
            version = store.write('schedule.json', self.state, None)
            self.assertEqual(set(store.names()), {'schedule.json', 'schedule.lock'})
            pinned = store.fd
            package = self.managed / 'generated-new.dmbackup'
            package.write_bytes(b'generated package-shaped sentinel, not a backup')
            changed = replace(self.state, policy=Policy(enabled=True))
            store.write('schedule.json', changed, version)
            self.assertEqual(store.fd, pinned)
            for _ in range(3):
                self.assertEqual(set(store.names()), {'schedule.json', 'schedule.lock', package.name})
            self.assertEqual(package.read_bytes(), b'generated package-shaped sentinel, not a backup')

    def test_unknown_file_after_prior_reconcile_is_seen_and_preserved(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = SnapshotConfiguration(owner, self.locators, cache_roots=(self.root / 'cache',))
            config.configure(Policy(enabled=True), managed_directory=self.root / 'schedule')
            actor = SnapshotOperations(config)
            actor._begin()
            try:
                self.assertFalse(actor._reconcile())
                sentinel = actor.managed.directory / 'manual-unregistered.dmbackup'
                sentinel.write_bytes(b'unknown generated sentinel; never adopt or delete')
                with self.assertRaisesRegex(ScheduleError, 'Unknown package/stage'):
                    actor._reconcile()
                self.assertEqual(sentinel.read_bytes(), b'unknown generated sentinel; never adopt or delete')
            finally:
                actor._release()

    def test_fresh_scan_descriptor_rechecks_private_directory_facts(self):
        with LockedDirectory(self.managed, 'schedule.lock') as store:
            original = os.open
            def open_then_change(path, flags, *args, **kwargs):
                descriptor = original(path, flags, *args, **kwargs)
                if path == '.' and kwargs.get('dir_fd') == store.fd:
                    self.managed.chmod(0o755)
                return descriptor
            try:
                with patch.object(os, 'open', open_then_change):
                    with self.assertRaises(ScheduleError):
                        store.names()
            finally:
                self.managed.chmod(0o700)
            self.assertEqual(store.names(), ('schedule.lock',))


if __name__ == '__main__':
    unittest.main()
