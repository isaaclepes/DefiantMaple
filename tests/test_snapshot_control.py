"""Generated control-document tests; no backup, restore or deletion workers."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
import uuid

from defiantmaple.scheduled_snapshots import Binding, Locator, ScheduleError
from defiantmaple.snapshot_control import ScheduleControl, decode_control, encode_control


class ControlDocumentTests(unittest.TestCase):
    def setUp(self):
        self.locator = Locator(str(uuid.uuid4()), 1, Binding('/generated/catalog.sqlite3',
            (1, 2), (1, 3), str(uuid.uuid4()), '/generated/managed', (1, 4)))
        self.control = ScheduleControl(self.locator, str(uuid.uuid4()), 'run', 10000, 'explicit enable')

    def test_exact_roundtrip_and_binding(self):
        self.assertEqual(decode_control(encode_control(self.control)), self.control)
        self.assertTrue(self.control.permits(self.locator))
        self.assertFalse(self.control.permits(replace(self.locator, revision=2)))
        for action in ('stop_requested', 'stopped'):
            self.assertFalse(replace(self.control, action=action).permits(self.locator))

    def test_unknown_duplicate_or_future_fields_refused(self):
        raw = encode_control(self.control)
        with self.assertRaises(ScheduleError):
            decode_control(raw[:-2] + b',"action":"run"}\n')
        value = json.loads(raw)
        value['future'] = True
        with self.assertRaises(ScheduleError):
            decode_control(json.dumps(value).encode())
        value.pop('future')
        value['schema'] += '.future'
        with self.assertRaises(ScheduleError):
            decode_control(json.dumps(value).encode())

    def test_invalid_or_unbounded_input_refused(self):
        for change in ({'utc': True}, {'reason': 'x' * 1025}, {'action': 'enabled'},
                       {'request_id': 'not-a-uuid'}):
            with self.assertRaises(ScheduleError):
                replace(self.control, **change)
        with self.assertRaises(ScheduleError):
            decode_control(b' ' * 131073)


from unittest.mock import patch
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.snapshot_control import ControlStore
from defiantmaple.scheduled_snapshots import StateUncertainError
from test_scheduled_snapshots import GeneratedFixture


class DurableControlTests(GeneratedFixture):
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
        self.directory = self.root / 'control-private'
        self.directory.mkdir(mode=0o700)
        self.locator = Locator(str(uuid.uuid4()), 1, Binding(str(self.database),
            (1, 2), (1, 3), str(uuid.uuid4()), str(self.directory), (1, 4)))
        self.run = ScheduleControl(self.locator, str(uuid.uuid4()), 'run', 10000, 'explicit enable')

    def store(self):
        return ControlStore(self.directory, self.database)

    def test_stop_cas_and_restart_preserve_request(self):
        with self.store() as store:
            old = store.write_control(self.run, None)
            request, saved = store.request_stop(self.locator, utc=10001, reason='disable', expected=old)
            with self.assertRaises(ScheduleError):
                store.write_control(self.run, old)
        with self.store() as store:
            actual, version = store.read_control()
            self.assertEqual((actual, version), (request, saved))
            self.assertFalse(actual.permits(self.locator))
            # Reopening never automatically acknowledges cleanup.
            self.assertEqual(actual.action, 'stop_requested')

    def test_newer_stop_prevents_older_ack(self):
        with self.store() as store:
            initial = store.write_control(self.run, None)
            older, old_version = store.request_stop(self.locator, utc=10001, reason='first', expected=initial)
            newer, version = store.request_stop(self.locator, utc=10002, reason='second', expected=old_version)
            with self.assertRaises(ScheduleError):
                store._acknowledge_stop(older, old_version, self.locator)
            self.assertEqual(store.read_control(), (newer, version))
            with self.assertRaises(ScheduleError):
                store._acknowledge_stop(newer, version, replace(self.locator, revision=2))

    def test_published_stop_survives_failed_directory_fsync(self):
        import os
        with self.store() as store:
            initial = store.write_control(self.run, None)
            original = os.fsync
            def fail_directory(fd):
                if fd == store.fd:
                    raise OSError('generated directory-fsync failure')
                return original(fd)
            with patch('defiantmaple.snapshot_control.os.fsync', side_effect=fail_directory):
                with self.assertRaises(StateUncertainError):
                    store.request_stop(self.locator, utc=10001, reason='disable', expected=initial)
        with self.store() as store:
            actual, _ = store.read_control()
            self.assertEqual(actual.action, 'stop_requested')
            self.assertFalse(actual.permits(self.locator))

    def test_substitution_after_publish_cannot_acknowledge(self):
        import os
        with self.store() as store:
            initial = store.write_control(self.run, None)
            original = os.fsync
            changed = False
            def substitute(fd):
                nonlocal changed
                if fd == store.fd and not changed:
                    changed = True
                    substitute_path = self.directory / 'replacement'
                    substitute_path.write_bytes(encode_control(self.run))
                    substitute_path.chmod(0o600)
                    os.replace(substitute_path, self.directory / store.leaf)
                return original(fd)
            with patch('defiantmaple.snapshot_control.os.fsync', side_effect=substitute):
                with self.assertRaises(StateUncertainError):
                    store.request_stop(self.locator, utc=10001, reason='disable', expected=initial)
            self.assertTrue(changed)


from defiantmaple.admission import admission_session
from defiantmaple.scheduled_snapshots import Policy, LockedDirectory
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from defiantmaple.snapshot_control import LiveStopSession
from types import SimpleNamespace


class LiveStopTests(GeneratedFixture):
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

    def configured(self, owner):
        config = SnapshotConfiguration(owner, self.locators, cache_roots=(), utc=lambda: 10000)
        config.configure(Policy(enabled=True), managed_directory=self.root / 'session-managed')
        discovery = config.discover()
        self.assertEqual(discovery.status, 'configured')
        return config, discovery.locator

    def test_live_request_and_exact_ack_preserve_schedule_state(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config, locator = self.configured(owner)
            before = (Path(locator.binding.directory_path) / 'schedule.json').read_bytes()
            session = LiveStopSession(config)
            request, version = session.request(locator, utc=10001, reason='disable')
            with self.assertRaises(ScheduleError):
                LiveStopSession(config).acknowledge(request, version, locator,
                    thread_finished=True, queued_work=False)
            with self.assertRaises(ScheduleError):
                session.acknowledge(replace(request), version, locator,
                    thread_finished=True, queued_work=False)
            actor = SimpleNamespace(owner=owner, active=True)
            session.observe_actor(actor)
            with self.assertRaises(ScheduleError):
                session.acknowledge(request, version, locator,
                    thread_finished=True, queued_work=False)
            actor.active = False
            stopped, _ = session.acknowledge(request, version, locator,
                thread_finished=True, queued_work=False)
            self.assertEqual(stopped.action, 'stopped')
            self.assertEqual((Path(locator.binding.directory_path) / 'schedule.json').read_bytes(), before)

    def test_request_does_not_wait_for_upstream_operation_locks(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config, locator = self.configured(owner)
            session = LiveStopSession(config)
            with LockedDirectory(config.root, config.leaf + '.lock'):
                with LockedDirectory(locator.binding.directory_path, 'schedule.lock'):
                    request, _ = session.request(locator, utc=10001, reason='active operation stop')
            self.assertEqual(request.action, 'stop_requested')

    def test_source_replacement_refused_before_any_sqlite_query(self):
        import shutil
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config, locator = self.configured(owner)
            session = LiveStopSession(config)
            original = self.database.with_name('original-pinned.sqlite3')
            self.database.rename(original)
            shutil.copyfile(original, self.database)
            with patch('defiantmaple.snapshot_control.sqlite3.connect') as connect:
                with patch('defiantmaple.snapshot_control._require_backup_catalog') as guard:
                    with patch('defiantmaple.catalog.library_identity') as identity:
                        with self.assertRaises((ValueError, OSError)):
                            session.request(locator, utc=10001, reason='replaced source')
                        connect.assert_not_called()
                        guard.assert_not_called()
                        identity.assert_not_called()

    def test_superseded_saved_request_authority_is_bounded(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config, locator = self.configured(owner)
            session = LiveStopSession(config)
            older, old_version = session.request(locator, utc=10001, reason='first')
            newer, _ = session.request(locator, utc=10002, reason='second')
            self.assertEqual(tuple(session._requests), (newer.request_id,))
            with self.assertRaises(ScheduleError):
                session.acknowledge(older, old_version, locator,
                    thread_finished=True, queued_work=False)

    def test_actor_bound_fails_closed_without_discarding_uncertain_owners(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config, _ = self.configured(owner)
            session = LiveStopSession(config)
            actors = [SimpleNamespace(owner=owner, active=False) for _ in range(65)]
            for actor in actors[:64]:
                session.observe_actor(actor)
            session.observe_actor(actors[0])
            with self.assertRaises(ScheduleError):
                session.observe_actor(actors[64])
            self.assertEqual(len(session._actors), 64)
            self.assertTrue(all(actual is expected for actual, expected in zip(session._actors, actors)))
