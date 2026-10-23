"""Phase/ownership unit evidence with injected recovery results, not backups."""
from pathlib import Path
from dataclasses import replace
import hashlib
import uuid
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from defiantmaple import recovery
from defiantmaple.controlled_configuration import ControlledEnableOperation, EnableRequest
from defiantmaple.admission import admission_session
from defiantmaple.snapshot_operations import SnapshotOperations, recovery_operation_slot
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import Policy, ScheduleError, PackageRecord, PhaseStatus
from defiantmaple.snapshot_control import ControlStore, LiveStopSession
from test_scheduled_snapshots import GeneratedFixture


class OperationPhaseTests(GeneratedFixture):
    def setUp(self):
        super().setUp()
        try:
            with private_local_parent(self.root / "capability-probe"):
                pass
        except ValueError as exc:
            if str(exc) in {"Recovery publication has no reviewed native adapter on this platform",
                            "Recovery requires a verified durable local filesystem"}:
                self.skipTest(str(exc))
            raise

    def actor(self, owner):
        config = SnapshotConfiguration(owner, self.locators, cache_roots=(self.root / "cache",), utc=lambda: 10000)
        enable = ControlledEnableOperation(config, EnableRequest.capture(None, None))
        try:
            enable.run(Policy(enabled=True), managed_directory=self.root / "operation-managed")
        finally:
            enable.finish_thread()
        return SnapshotOperations(config)

    def test_prepublication_failure_records_no_false_success_and_releases_slot(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            with patch.object(recovery, "backup_metadata", side_effect=recovery.RecoveryError("generated failure")):
                result = actor.backup()
            self.assertEqual(result.status, "failed")
            self.assertIsNone(result.state.last_success)
            self.assertEqual(result.state.status.outcome, "failed")
            self.assertFalse(actor.active)
            with recovery_operation_slot(owner):
                with self.assertRaises(ScheduleError):
                    actor.reconcile()

    def test_published_unregistered_failure_stays_uncertain_and_keeps_file(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            def fail(_source, package, **kwargs):
                Path(package).write_bytes(b"generated unregistered publication")
                raise recovery.RecoveryError("generated late publication failure")
            with patch.object(recovery, "backup_metadata", side_effect=fail):
                result = actor.backup()
            self.assertEqual(result.status, "uncertain")
            self.assertIsNone(result.state.last_success)
            packages = list(actor.managed.directory.glob("*.dmbackup"))
            self.assertEqual(len(packages), 1)
            before = packages[0].read_bytes()
            self.assertEqual(actor.reconcile().status, "suspended")
            self.assertEqual(packages[0].read_bytes(), before)

    def test_registered_success_kept_when_cleanup_is_pending(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            def publish(_source, package, **kwargs):
                Path(package).write_bytes(b"fictional package result")
            with patch.object(recovery, "backup_metadata", side_effect=publish), patch.object(actor, "_inspect", return_value=((1, 1), 1024, "a" * 64)), patch.object(actor, "_cleanup", return_value=False):
                result = actor.backup()
            try:
                self.assertEqual(result.status, "cleanup_pending")
                self.assertTrue(result.success_currently_verified)
                self.assertTrue(result.state.status.cleanup_pending)
                self.assertIsNotNone(result.state.last_success)
                with self.assertRaises(ScheduleError):
                    with recovery_operation_slot(owner):
                        self.fail("cleanup released shared slot")
            finally:
                with patch.object(actor, "_cleanup", return_value=True):
                    self.assertTrue(actor.reap_owned_cleanup())

    def test_stage_name_recreated_after_original_cleanup_is_preserved(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            actor._begin()
            stage = actor.managed.directory / ".recovery-generated.snapshot"
            stage.write_bytes(b"original generated stage")
            self.assertEqual(recovery._cleanup_stages((stage,)), [])
            self.assertFalse(stage.exists())
            stage.write_bytes(b"replacement sentinel; not coordinator-owned")
            before = stage.stat()
            process = SimpleNamespace(is_alive=Mock(return_value=False), join=Mock(), exitcode=0)
            actor.records.append({"process": process, "stages": (stage,), "cleanup_errors": [], "exit": None})
            try:
                self.assertFalse(actor._cleanup())
                self.assertEqual(stage.read_bytes(), b"replacement sentinel; not coordinator-owned")
                self.assertEqual((stage.stat().st_dev, stage.stat().st_ino), (before.st_dev, before.st_ino))
                self.assertFalse(actor.reap_owned_cleanup())
                self.assertTrue(actor.active)
            finally:
                # Explicit disposal of this generated test sentinel only.
                stage.unlink()
                self.assertTrue(actor.reap_owned_cleanup())


    def test_saved_stop_vetoes_backup_but_readonly_reconcile_preserves_it(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            locator = actor.config.discover().locator
            stopped, version = LiveStopSession(actor.config).request(locator, utc=10001, reason='disable')
            with patch.object(recovery, 'backup_metadata') as backup:
                result = actor.backup()
                self.assertEqual(result.status, 'suspended')
                backup.assert_not_called()
            self.assertEqual(actor.reconcile().status, 'reconciled')
            with ControlStore(actor.config.root, owner.path) as control:
                self.assertEqual(control.read_control(), (stopped, version))

    def test_missing_or_revision_mismatched_control_cannot_start_backup(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            with ControlStore(actor.config.root, owner.path) as control:
                value, version = control.read_control()
                control.write_control(replace(value, locator=replace(value.locator, revision=2)), version)
            with patch.object(recovery, 'backup_metadata') as backup:
                self.assertEqual(actor.backup().status, 'suspended')
                backup.assert_not_called()
            (actor.config.root / (actor.config.leaf + '.control')).unlink()
            with patch.object(recovery, 'backup_metadata') as backup:
                self.assertEqual(actor.backup().status, 'suspended')
                backup.assert_not_called()

    def test_stop_after_attempt_save_is_seen_before_original_backup_api(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            save = actor._save
            def save_then_stop(state):
                save(state)
                if state.status.outcome == 'in_progress':
                    LiveStopSession(actor.config).request(state.locator, utc=10001, reason='checkpoint stop')
            with patch.object(actor, '_save', side_effect=save_then_stop):
                with patch.object(recovery, 'backup_metadata') as backup:
                    result = actor.backup()
                    backup.assert_not_called()
            self.assertIsNone(result.state.last_success)
            self.assertFalse(actor.active)

    def test_native_prune_checkpoint_observes_stop_without_unlink(self):
        # Injected durable package facts, NOT evidence of a real backup/inspect.
        from defiantmaple.snapshot_pruning import _validate
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            actor._begin()
            try:
                operation = str(uuid.uuid4())
                leaf = f'snapshot-{actor.state.locator.schedule_id}-1-{operation}.dmbackup'
                path = actor.managed.directory / leaf
                payload = b'generated ledger-bound non-package sentinel'
                path.write_bytes(payload)
                path.chmod(0o600)
                point = PackageRecord(actor.state.locator.schedule_id, 1, operation, leaf,
                    (path.stat().st_dev, path.stat().st_ino), len(payload), hashlib.sha256(payload).hexdigest(), 10000)
                actor._save(replace(actor.state, policy=replace(actor.state.policy, retention_enabled=True),
                    packages=(point,), last_success=point, next_sequence=2,
                    status=PhaseStatus(10000, 10000, 'verified')))
                actor._registered_package = point
                _validate(actor, point)
                LiveStopSession(actor.config).request(actor.state.locator, utc=10001, reason='prune stop')
                with self.assertRaises(ScheduleError):
                    _validate(actor, point)
                self.assertEqual(path.read_bytes(), payload)
                self.assertEqual(actor.state.last_success, point)
            finally:
                actor._release()


    def test_source_replaced_during_control_read_cannot_start_backup(self):
        import shutil
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            original_read = ControlStore.read_control
            changed = False
            def read_then_replace(control):
                nonlocal changed
                value = original_read(control)
                if not changed:
                    changed = True
                    pinned = self.database.with_name('pinned-original.sqlite3')
                    self.database.rename(pinned)
                    shutil.copyfile(pinned, self.database)
                return value
            with patch.object(ControlStore, 'read_control', read_then_replace):
                with patch.object(recovery, 'backup_metadata') as backup:
                    result = actor.backup()
                    backup.assert_not_called()
            self.assertTrue(changed)
            self.assertEqual(result.status, 'suspended')
            self.assertFalse(actor.active)

    def test_source_replaced_during_final_control_checkpoint_is_refused(self):
        import shutil
        from defiantmaple.snapshot_control import require_run
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            actor._begin()
            original_read = ControlStore.read_control
            changed = False
            def read_then_replace(control):
                nonlocal changed
                value = original_read(control)
                if not changed:
                    changed = True
                    pinned = self.database.with_name('pinned-checkpoint-original.sqlite3')
                    self.database.rename(pinned)
                    shutil.copyfile(pinned, self.database)
                return value
            try:
                with patch.object(ControlStore, 'read_control', read_then_replace):
                    with self.assertRaises((ValueError, OSError)):
                        require_run(actor.config, actor.state.locator, actor.locators)
                self.assertTrue(changed)
            finally:
                actor._release()

    def test_malformed_and_contended_control_refuse_backup_api(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            path = actor.config.root / (actor.config.leaf + '.control')
            original = path.read_bytes()
            path.write_bytes(b'{"schema":"malformed generated control"}\n')
            with patch.object(recovery, 'backup_metadata') as backup:
                self.assertEqual(actor.backup().status, 'suspended')
                backup.assert_not_called()
            path.write_bytes(original)
            with ControlStore(actor.config.root, owner.path):
                with patch.object(recovery, 'backup_metadata') as backup:
                    self.assertEqual(actor.backup().status, 'suspended')
                    backup.assert_not_called()


    def test_external_cancel_during_begin_barrier_is_not_erased(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            config = self.actor(owner).config
            external = threading.Event()
            actor = SnapshotOperations(config, cancel_event=external)
            entered, release = threading.Event(), threading.Event()
            errors = []
            original = config._placement
            def placement_then_pause(*args, **kwargs):
                original(*args, **kwargs)
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('generated begin barrier deadline')
            def invoke():
                try:
                    actor.reconcile()
                except BaseException as exc:
                    errors.append(exc)
            with patch.object(config, '_placement', side_effect=placement_then_pause):
                with patch('defiantmaple.snapshot_operations.LockedDirectory') as stores:
                    with patch.object(recovery, 'inspect_package') as inspect:
                        thread = threading.Thread(target=invoke)
                        thread.start()
                        try:
                            self.assertTrue(entered.wait(5))
                            actor.request_cancel()
                        finally:
                            release.set()
                            thread.join(5)
                        self.assertFalse(thread.is_alive())
                        stores.assert_not_called()
                        inspect.assert_not_called()
            self.assertIs(actor.cancel, external)
            self.assertTrue(external.is_set())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ScheduleError)
            self.assertFalse(actor.active)
            with recovery_operation_slot(owner):
                pass

    def test_default_internal_actor_retains_reusable_cancel_reset(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            actor = self.actor(owner)
            actor.request_cancel()
            actor._begin()
            try:
                self.assertFalse(actor.cancel.is_set())
            finally:
                actor._release()


class StickyCancelGuardTests(unittest.TestCase):
    def test_preset_external_cancel_refuses_before_native_or_sqlite_entry(self):
        external = threading.Event()
        external.set()
        owner = Mock()
        config = SimpleNamespace(owner=owner, _placement=Mock())
        actor = SnapshotOperations(config, cancel_event=external)
        with patch('defiantmaple.snapshot_operations._slot') as slot:
            with patch('defiantmaple.snapshot_operations.LockedDirectory') as stores:
                with self.assertRaises(ScheduleError):
                    actor.reconcile()
                slot.assert_not_called()
                stores.assert_not_called()
        config._placement.assert_not_called()
        owner.validate.assert_not_called()
        owner.retain.assert_not_called()
        self.assertTrue(external.is_set())


class ScopedReaperTests(unittest.TestCase):
    def test_scoped_reaper_never_joins_or_cleans_unrelated_process(self):
        owned = SimpleNamespace(join=Mock(), is_alive=Mock(return_value=False))
        other = SimpleNamespace(join=Mock(side_effect=AssertionError("unrelated join")), is_alive=Mock(return_value=True))
        entries = [(other, (Path("foreign-stage"),)), (owned, (Path("generated-owned-stage"),))]
        with patch.object(recovery, "_UNREAPED_WORKERS", entries), patch.object(recovery, "_cleanup_stages", return_value=[]) as cleanup:
            result = recovery.reap_recovery_workers(0, _only_process=owned)
            self.assertEqual(result, {"remaining_workers": 0, "cleanup_errors": []})
            owned.join.assert_called_once_with(0)
            other.join.assert_not_called()
            cleanup.assert_called_once_with((Path("generated-owned-stage"),))
            self.assertEqual(entries, [(other, (Path("foreign-stage"),))])

    def test_default_reaper_preserves_its_eight_worker_bound(self):
        processes = [SimpleNamespace(join=Mock(), is_alive=Mock(return_value=False)) for _ in range(9)]
        entries = [(process, (Path(f"generated-{index}"),)) for index, process in enumerate(processes)]
        with patch.object(recovery, "_UNREAPED_WORKERS", entries), patch.object(recovery, "_cleanup_stages", return_value=[]) as cleanup:
            result = recovery.reap_recovery_workers(0)
            self.assertEqual(result["remaining_workers"], 1)
            self.assertEqual(cleanup.call_count, 8)
            processes[-1].join.assert_not_called()
            self.assertIs(entries[0][0], processes[-1])

    def test_started_observer_and_inspector_retention_errors_use_original_cleanup(self):
        for retention_failure in (False, True):
            with self.subTest(retention_failure=retention_failure):
                alive = [True]
                process = SimpleNamespace(start=Mock(), join=Mock(), pid=123,
                    is_alive=Mock(side_effect=lambda: alive[0]),
                    kill=Mock(side_effect=lambda: alive.__setitem__(0, False)))
                receive, send, cancel = Mock(), Mock(), Mock()
                context = SimpleNamespace(Pipe=Mock(return_value=(receive, send)),
                    Event=Mock(return_value=cancel), Process=Mock(return_value=process))
                actor = object.__new__(SnapshotOperations)
                actor.records = []
                actor.owner = SimpleNamespace(retain_process=Mock(side_effect=RuntimeError("generated retention failure")))
                callback = actor._started if retention_failure else Mock(side_effect=RuntimeError("generated observer failure"))
                with patch.object(recovery.multiprocessing, "get_context", return_value=context), patch.object(recovery, "_UNREAPED_WORKERS", []), patch.object(recovery, "_cleanup_stages", return_value=[]) as cleanup:
                    with self.assertRaises(RuntimeError):
                        recovery._run("inspect", (Path("fictional.dmbackup"), Path("generated-stage")),
                                      (Path("generated-stage"),), None, _process_started=callback)
                    process.start.assert_called_once()
                    process.kill.assert_called_once()
                    process.join.assert_called()
                    cleanup.assert_called_once_with((Path("generated-stage"),))
                    receive.close.assert_called()
                if retention_failure:
                    self.assertIs(actor.records[0]["process"], process)
                    actor.owner.retain_process.assert_called_once_with(process)
