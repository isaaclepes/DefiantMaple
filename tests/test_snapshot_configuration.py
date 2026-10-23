"""Generated model/configuration tests; no backup or pruning execution."""
from dataclasses import asdict, replace
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from defiantmaple.admission import admission_session, LibraryInUseError
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.sources import add_source
from defiantmaple.snapshot_configuration import SnapshotConfiguration
from defiantmaple.scheduled_snapshots import (AuditRecord, ConfigurationTransition, PackageRecord, PhaseStatus,
    Policy, ScheduleError, StateUncertainError, ScheduleState, LockedDirectory,
    decode_document, encode_document)
from test_scheduled_snapshots import GeneratedFixture


class LedgerTests(GeneratedFixture):
    def package(self, sequence=1, **changes):
        operation = f"00000000-0000-4000-8000-{sequence:012d}"
        values = dict(schedule_id=self.locator.schedule_id, sequence=sequence,
                      operation_id=operation,
                      leaf=f"snapshot-{self.locator.schedule_id}-{sequence}-{operation}.dmbackup",
                      file_identity=(1, sequence), size=1024, sha256="a" * 64,
                      verified_utc=10000)
        return PackageRecord(**{**values, **changes})

    def test_verified_ledger_audit_and_exact_success_roundtrip(self):
        package = self.package()
        audit = AuditRecord(1, package.operation_id, 1, 10000, "verified", package)
        state = ScheduleState(self.locator, Policy(), PhaseStatus(10000, 10000, "verified"),
                              2, (package,), (audit,), package)
        self.assertEqual(decode_document(encode_document(state)), state)
        with self.assertRaises(ScheduleError):
            replace(state, packages=())
        with self.assertRaises(ScheduleError):
            replace(state, last_success=replace(package, sha256="b" * 64))
        transition = ConfigurationTransition(self.locator, package.operation_id, "pending")
        self.assertEqual(decode_document(encode_document(transition), transition=True), transition)
        with self.assertRaises(ScheduleError):
            replace(transition, phase=[])

    def test_foreign_duplicate_future_and_malformed_package_facts_refuse(self):
        package = self.package()
        for change in ({"sha256": "A" * 64}, {"size": True}, {"file_identity": (1, 0)},
                       {"leaf": "../unrelated.dmbackup"}):
            with self.assertRaises(ScheduleError):
                replace(package, **change)
        for values in ({"packages": (package,), "next_sequence": 1},
                       {"packages": (package, package), "next_sequence": 2},
                       {"packages": (self.package(schedule_id="00000000-0000-4000-8000-000000000099", leaf="snapshot-00000000-0000-4000-8000-000000000099-1-00000000-0000-4000-8000-000000000001.dmbackup"),), "next_sequence": 2}):
            with self.assertRaises(ScheduleError):
                replace(self.state, **values)
        with self.assertRaises(ScheduleError):
            AuditRecord(1, package.operation_id, 1, 10000, "delete_intent", package, package)
        with self.assertRaises(ScheduleError):
            replace(self.state, audit=(AuditRecord(1, package.operation_id, 2, 10000, "configured"),))

    def test_bounded_history_never_silently_drops_records(self):
        events = tuple(AuditRecord(n, self.locator.schedule_id, 1, n, "configured") for n in range(1, 4097))
        state = replace(self.state, audit=events)
        self.assertEqual(len(decode_document(encode_document(state)).audit), 4096)
        with self.assertRaises(ScheduleError):
            replace(state, audit=(*events, replace(events[-1], sequence=4097)))
        raw = json.loads(encode_document(self.state))
        raw["packages"] = [asdict(self.package())] * 1025
        with self.assertRaises(ScheduleError):
            decode_document(json.dumps(raw).encode())


class ConfigurationTests(GeneratedFixture):
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

    def coordinator(self, owner, **kwargs):
        return SnapshotConfiguration(owner, self.locators,
            cache_roots=(self.root / "cache",), utc=lambda: 10000, **kwargs)

    def test_enable_and_unchanged_reopen_discover_without_reselection(self):
        managed = self.root / "new-managed"
        before = self.database.read_bytes()
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            self.assertEqual(coordinator.discover().status, "unconfigured")
            self.assertFalse(coordinator.root.exists())
            configured = coordinator.configure(Policy(enabled=True), managed_directory=managed)
            self.assertEqual(configured.locator.revision, 1)
            self.assertEqual(len(configured.audit), 1)
        with admission_session(self.database, _registry_path=self.registry) as owner:
            reopened = self.coordinator(owner).discover()
            self.assertEqual(reopened.status, "configured")
            self.assertEqual(reopened.state, configured)
            self.assertEqual(reopened.reason, "package_reconciliation_required")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual({p.name for p in managed.iterdir()}, {"schedule.lock", "schedule.json"})

    def test_revision_compare_and_destination_change_preserve_prior_state(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            old = self.root / "old-configured"
            first = coordinator.configure(Policy(enabled=True), managed_directory=old)
            with self.assertRaises(ScheduleError):
                coordinator.configure(Policy(enabled=False), expected_revision=2)
            second = coordinator.configure(Policy(enabled=False), expected_revision=1)
            self.assertEqual(second.locator.revision, 2)
            self.assertEqual(len(second.audit), 2)
            before = (old / "schedule.json").read_bytes()
            third = coordinator.configure(Policy(), managed_directory=self.root / "new-configured", expected_revision=2)
            self.assertEqual(third.locator.revision, 3)
            self.assertNotEqual(third.locator.schedule_id, first.locator.schedule_id)
            self.assertEqual((old / "schedule.json").read_bytes(), before)
            self.assertEqual(coordinator.discover().state, third)
            with self.assertRaises(ScheduleError):
                coordinator.configure(Policy(enabled=True), expected_revision=1)

    def test_interrupted_state_then_locator_commit_suspends_no_old_policy_fallback(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            first = coordinator.configure(Policy(enabled=True), managed_directory=self.root / "configured")
            real_write = LockedDirectory.write
            def write(store, *args, **kwargs):
                if store.directory == coordinator.root and args[0] == coordinator.leaf:
                    raise OSError("generated locator persistence failure")
                return real_write(store, *args, **kwargs)
            with patch.object(LockedDirectory, "write", write):
                with self.assertRaises(StateUncertainError):
                    coordinator.configure(Policy(enabled=False), expected_revision=1)
            discovered = coordinator.discover()
            self.assertEqual(discovered.status, "suspended")
            self.assertEqual(discovered.locator, first.locator)
            self.assertIsNone(discovered.state)
            with self.assertRaises(ScheduleError):
                coordinator.configure(Policy(enabled=True), expected_revision=1)

    def test_destination_change_interruption_cannot_resume_matching_old_pair(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            old, new = self.root / "old-destination", self.root / "new-destination"
            first = coordinator.configure(Policy(enabled=True), managed_directory=old)
            old_bytes = (old / "schedule.json").read_bytes()
            unrelated = old / "unrelated.dmbackup"
            unrelated.write_bytes(b"fictional prior recovery point")
            real_write = LockedDirectory.write
            def write(store, *args, **kwargs):
                if store.directory == coordinator.root and args[0] == coordinator.leaf:
                    raise OSError("generated destination locator failure")
                return real_write(store, *args, **kwargs)
            with patch.object(LockedDirectory, "write", write):
                with self.assertRaises(StateUncertainError):
                    coordinator.configure(Policy(enabled=False), managed_directory=new, expected_revision=1)
            # The old state+locator still match, but the durable per-key intent
            # explicitly prevents their enabled old policy from resuming.
            self.assertEqual((old / "schedule.json").read_bytes(), old_bytes)
            self.assertEqual(unrelated.read_bytes(), b"fictional prior recovery point")
            self.assertTrue((new / "schedule.json").exists())
            discovered = coordinator.discover()
            self.assertEqual(discovered.status, "suspended")
            self.assertEqual(discovered.reason, "configuration_transition_pending")
            self.assertEqual(discovered.locator, first.locator)

    def test_destination_change_refuses_old_pending_outcomes_before_creation(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            old = self.root / "old-pending"
            first = coordinator.configure(Policy(enabled=True), managed_directory=old)
            operation = "00000000-0000-4000-8000-000000000001"
            package = PackageRecord(first.locator.schedule_id, 1, operation,
                f"snapshot-{first.locator.schedule_id}-1-{operation}.dmbackup",
                (1, 1), 1024, "a" * 64, 10000)
            statuses = [PhaseStatus(10000, None, "in_progress"),
                        PhaseStatus(10000, None, "uncertain"),
                        PhaseStatus(10000, None, "canceled", True),
                        PhaseStatus(10000, 10000, "cleanup_warning")]
            for index, status in enumerate(statuses):
                with self.subTest(status=status):
                    kwargs = dict(next_sequence=2, packages=(package,), last_success=package) if status.last_success_utc else {}
                    pending = replace(first, status=status, **kwargs)
                    with LockedDirectory(old, "schedule.lock") as store:
                        _, version = store.read("schedule.json")
                        store.write("schedule.json", pending, version)
                    before = (old / "schedule.json").read_bytes()
                    new = self.root / f"new-blocked-{index}"
                    with self.assertRaises(ScheduleError):
                        coordinator.configure(Policy(), managed_directory=new, expected_revision=1)
                    self.assertFalse(new.exists())
                    self.assertEqual((old / "schedule.json").read_bytes(), before)
                    self.assertEqual(coordinator.discover().status, "suspended")

    def test_destination_change_requires_old_lock_and_holds_it_through_commit(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            old = self.root / "old-locked"
            coordinator.configure(Policy(enabled=True), managed_directory=old)
            before = (old / "schedule.json").read_bytes()
            new = self.root / "new-after-lock"
            with LockedDirectory(old, "schedule.lock"):
                with self.assertRaises(LibraryInUseError):
                    coordinator.configure(Policy(), managed_directory=new, expected_revision=1)
                self.assertFalse(new.exists())
            real_write, observed = LockedDirectory.write, []
            def write(store, *args, **kwargs):
                if store.directory == coordinator.root and args[0] == coordinator.leaf:
                    with self.assertRaises(LibraryInUseError):
                        with LockedDirectory(old, "schedule.lock"):
                            self.fail("old schedule was released before locator commit")
                    observed.append("old_locked_at_locator_commit")
                return real_write(store, *args, **kwargs)
            with patch.object(LockedDirectory, "write", write):
                result = coordinator.configure(Policy(), managed_directory=new, expected_revision=1)
            self.assertEqual(observed, ["old_locked_at_locator_commit"])
            self.assertEqual(result.locator.revision, 2)
            self.assertEqual((old / "schedule.json").read_bytes(), before)

    def test_sqlite_sidecar_targets_refuse_before_any_directory_or_lock_creation(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            before = sorted(p.name for p in self.root.iterdir())
            for suffix in ("-journal", "-wal", "-shm"):
                target = Path(str(self.database) + suffix)
                with self.assertRaises(ValueError):
                    coordinator.configure(Policy(enabled=True), managed_directory=target)
                self.assertFalse(target.exists())
                self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute("CREATE TABLE fictional_writer_after_refusal(value TEXT)")
                db.execute("INSERT INTO fictional_writer_after_refusal VALUES('write still works')")
            self.assertFalse(Path(str(self.database) + "-journal").exists())

    def test_schema_and_identity_authentication_precedes_source_rows_and_absent_lookup(self):
        for damage in ("future", "identity"):
            database = self.root / (damage + ".sqlite3")
            shutil.copyfile(self.database, database)
            with closing(sqlite3.connect(database)) as db, db:
                if damage == "future":
                    db.execute("PRAGMA user_version=999")
                else:
                    db.execute("DROP TRIGGER library_identity_no_update")
            with admission_session(database, _registry_path=self.registry) as owner:
                coordinator = self.coordinator(owner)
                with patch("defiantmaple.snapshot_configuration._source_roots", side_effect=AssertionError("userdata queried")) as sources:
                    self.assertEqual(coordinator.discover().status, "suspended")
                    with self.assertRaises(ValueError):
                        coordinator.configure(Policy(enabled=True), managed_directory=self.root / (damage + "-managed"))
                    sources.assert_not_called()
                self.assertFalse(coordinator.root.exists())

    def test_native_busy_is_not_an_absent_configuration_or_generic_identity_error(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            busy = sqlite3.OperationalError("generated database busy")
            busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
            with patch("defiantmaple.snapshot_configuration._require_backup_catalog", side_effect=busy), patch("defiantmaple.snapshot_configuration._source_roots") as sources:
                self.assertEqual(coordinator.discover().status, "suspended")
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    coordinator.configure(Policy(enabled=True), managed_directory=self.root / "unused")
                self.assertIs(caught.exception, busy)
                sources.assert_not_called()
            self.assertFalse(coordinator.root.exists())

    def test_copy_does_not_follow_uuid_or_adopt_existing_managed_directory(self):
        copied = self.root / "copy.sqlite3"
        with admission_session(self.database, _registry_path=self.registry) as owner:
            first = self.coordinator(owner).configure(Policy(enabled=True), managed_directory=self.root / "original-configured")
        before = (Path(first.locator.binding.directory_path) / "schedule.json").read_bytes()
        shutil.copyfile(self.database, copied)
        with admission_session(copied, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            self.assertEqual(coordinator.discover().status, "unconfigured")
            with self.assertRaises(ScheduleError):
                coordinator.configure(Policy(enabled=True), managed_directory=first.locator.binding.directory_path)
        self.assertEqual((Path(first.locator.binding.directory_path) / "schedule.json").read_bytes(), before)

    def test_source_cache_and_locator_placement_refuse_before_creation(self):
        media = self.root / "media"
        media.mkdir(mode=0o700)
        add_source(self.database, media, existing_file_policy="inbox")
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            for target in (media / "snapshots", self.root / "cache/snapshots"):
                with self.assertRaises(ValueError):
                    coordinator.configure(Policy(enabled=True), managed_directory=target)
                self.assertFalse(target.exists())
            inside_media = SnapshotConfiguration(owner, media, cache_roots=(self.root / "cache",))
            with self.assertRaises(ValueError):
                inside_media.configure(Policy(enabled=True), managed_directory=self.root / "unused")
            self.assertFalse(inside_media.root.exists())

    def test_corruption_missing_state_and_directory_replacement_suspend(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            coordinator = self.coordinator(owner)
            managed = self.root / "configured"
            coordinator.configure(Policy(enabled=True), managed_directory=managed)
            state = managed / "schedule.json"
            original = state.read_bytes()
            state.write_bytes(b'{"broken":true}')
            self.assertEqual(coordinator.discover().status, "suspended")
            state.unlink()
            self.assertEqual(coordinator.discover().status, "suspended")
            state.touch(mode=0o600)
            state.write_bytes(original)
            managed.rename(self.root / "displaced-configured")
            managed.mkdir(mode=0o700)
            self.assertEqual(coordinator.discover().status, "suspended")
