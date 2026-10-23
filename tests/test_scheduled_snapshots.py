"""Generated-only state foundations; no scheduler/retention worker is launched."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple import catalog
from defiantmaple.admission import admission_session, LibraryInUseError
from defiantmaple.recovery_storage import private_local_parent
from defiantmaple.scheduled_snapshots import (Binding, DueState, Locator, LockedDirectory,
    PhaseStatus, Policy, ScheduleError, ScheduleState, StateUncertainError,
    decode_document, encode_document, locator_leaf, locked_stores, validate_pair)


class Clock:
    def __init__(self):
        self.wall, self.mono = 100000, 100

    def scheduler(self, policy=None, status=None):
        return DueState(policy or Policy(enabled=True, interval_seconds=900),
                        status or PhaseStatus(), utc=lambda: self.wall,
                        monotonic=lambda: self.mono)


class TimingTests(unittest.TestCase):
    def test_opt_in_immediate_once_and_no_catchup_overlap(self):
        clock = Clock()
        due = clock.scheduler(Policy())
        self.assertFalse(due.poll())
        due.reconfigure(Policy(enabled=True, interval_seconds=900))
        self.assertTrue(due.poll())
        due.start()
        clock.mono += 100000
        self.assertFalse(due.poll())
        with self.assertRaises(ScheduleError):
            due.start(manual=True)
        due.finish("verified", verified_utc=clock.wall)
        self.assertFalse(due.poll())
        clock.mono += 900
        self.assertFalse(due.poll(recovery_idle=False))
        self.assertTrue(due.poll())

    def test_live_wall_jumps_and_interval_edit_use_monotonic(self):
        clock = Clock()
        due = clock.scheduler()
        due.start()
        due.finish("failed")
        clock.wall += 1000000
        self.assertFalse(due.poll())
        due.reconfigure(Policy(enabled=True, interval_seconds=1800))
        self.assertFalse(due.poll())
        clock.wall = 0
        clock.mono += 1800
        self.assertTrue(due.poll())

    def test_restart_overdue_once_backwards_wall_waits_interval(self):
        clock = Clock()
        due = clock.scheduler(status=PhaseStatus(90000, 90000, "verified"))
        self.assertTrue(due.poll())
        due.start()
        due.finish("failed")
        self.assertFalse(due.poll())
        clock.wall = 80000
        backward = clock.scheduler(status=PhaseStatus(90000, 90000, "verified"))
        self.assertTrue(backward.clock_changed)
        self.assertFalse(backward.poll())
        clock.mono += 900
        self.assertTrue(backward.poll())

    def test_interrupted_or_uncertain_requires_explicit_reconciliation(self):
        clock = Clock()
        for outcome in ("in_progress", "uncertain", "cleanup_warning"):
            due = clock.scheduler(status=PhaseStatus(90000, 90000, outcome))
            self.assertFalse(due.poll())
            with self.assertRaises(ScheduleError):
                due.start(manual=True)
            due.reconciled()
            self.assertTrue(due.poll())

    def test_success_survives_later_cleanup_failure_without_release(self):
        clock = Clock()
        due = clock.scheduler()
        due.start()
        due.finish("cleanup_warning", verified_utc=clock.wall, cleanup_complete=False)
        self.assertEqual(due.status.last_success_utc, clock.wall)
        self.assertTrue(due.active)
        self.assertTrue(due.request_cancel())
        self.assertFalse(due.poll())
        with self.assertRaises(ScheduleError):
            due.reconciled()
        due.finish("cleanup_warning", cleanup_complete=True)
        self.assertFalse(due.active)
        self.assertEqual(due.status.last_success_utc, clock.wall)
        self.assertTrue(due.suspended)

    def test_every_incomplete_cleanup_outcome_suspends_after_restart(self):
        clock = Clock()
        for outcome in ("verified", "failed", "canceled", "uncertain", "cleanup_warning"):
            with self.subTest(outcome=outcome):
                due = clock.scheduler()
                due.start()
                kwargs = {"verified_utc": clock.wall} if outcome in {"verified", "cleanup_warning"} else {}
                due.finish(outcome, cleanup_complete=False, **kwargs)
                self.assertTrue(due.status.cleanup_pending)
                reopened = clock.scheduler(status=due.status)
                self.assertTrue(reopened.suspended)
                self.assertFalse(reopened.poll())
                with self.assertRaises(ScheduleError):
                    reopened.start(manual=True)
                reopened.reconciled()
                self.assertFalse(clock.scheduler(status=reopened.status).suspended)

    def test_disable_clears_due_intent_without_claiming_active_exit(self):
        due = Clock().scheduler()
        due.start()
        due.reconfigure(Policy())
        self.assertTrue(due.active)
        self.assertTrue(due.request_cancel())
        self.assertFalse(due.poll())
        due.finish("canceled")
        self.assertFalse(due.active)

    def test_invalid_clock_and_monotonic_regression_refuse(self):
        clock = Clock()
        clock.wall = float("nan")
        with self.assertRaises(ScheduleError):
            clock.scheduler()
        clock.wall = 100000
        due = clock.scheduler()
        clock.mono -= 1
        with self.assertRaises(ScheduleError):
            due.poll()
        self.assertTrue(due.suspended)


class GeneratedFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "generated.sqlite3"
        catalog.initialize(self.database)
        self.managed = self.root / "managed"
        self.locators = self.root / "locators"
        self.managed.mkdir(mode=0o700)
        self.locators.mkdir(mode=0o700)
        self.registry = self.root / "admission"
        with admission_session(self.database, _registry_path=self.registry) as owner:
            self.binding = Binding.capture(owner, self.managed)
        self.locator = Locator("00000000-0000-4000-8000-000000000050", 1, self.binding)
        self.state = ScheduleState(self.locator)


class DocumentTests(GeneratedFixture):
    def test_strict_roundtrip_and_invalid_documents_do_not_become_defaults(self):
        self.assertEqual(decode_document(encode_document(self.state)), self.state)
        self.assertEqual(decode_document(encode_document(self.locator), locator=True), self.locator)
        original = json.loads(encode_document(self.state))
        for mutate in (lambda v: v.update(extra=True),
                       lambda v: v.update(schema="future"),
                       lambda v: v["policy"].update(enabled=1),
                       lambda v: v["policy"].update(keep_count=0),
                       lambda v: v["locator"].update(revision=True),
                       lambda v: v["locator"]["binding"].update(file_identity=[1, 0])):
            value = json.loads(json.dumps(original))
            mutate(value)
            with self.assertRaises((ScheduleError, ValueError)):
                decode_document(json.dumps(value).encode())
        for raw in (b'{"schema":1,"schema":2}', b'[]', b'NaN', b'\xff', b'[' * 2000):
            with self.assertRaises(ScheduleError):
                decode_document(raw)
        with self.assertRaises(ScheduleError):
            decode_document(b" " * 65537, locator=True)

    def test_same_uuid_copy_cannot_inherit_original_binding_or_key(self):
        copied = self.root / "copy.sqlite3"
        shutil.copyfile(self.database, copied)
        self.assertNotEqual(locator_leaf(copied), locator_leaf(self.database))
        with admission_session(copied, _registry_path=self.registry) as owner:
            with self.assertRaises(ScheduleError):
                self.binding.validate(owner)

    def test_unchanged_reopen_matches_but_revisions_and_replaced_directory_refuse(self):
        with admission_session(self.database, _registry_path=self.registry) as owner:
            self.assertEqual(validate_pair(self.locator, self.state, owner), self.state)
            with self.assertRaises(ScheduleError):
                validate_pair(replace(self.locator, revision=2), self.state, owner)
            self.managed.rename(self.root / "old-managed")
            self.managed.mkdir(mode=0o700)
            with self.assertRaises(ScheduleError):
                validate_pair(self.locator, self.state, owner)

    def test_policy_and_success_types_are_not_truthy_coercions(self):
        for args in ({"enabled": 1}, {"retention_enabled": "yes"},
                     {"interval_seconds": 899}, {"interval_seconds": True},
                     {"keep_count": None, "byte_limit": None}, {"byte_limit": 0}):
            with self.assertRaises(ScheduleError):
                Policy(**args)
        with self.assertRaises(ScheduleError):
            PhaseStatus(outcome="verified")


class PersistenceTests(GeneratedFixture):
    def setUp(self):
        super().setUp()
        try:
            with private_local_parent(self.managed / "capability-probe"):
                pass
        except ValueError as exc:
            if str(exc) in {"Recovery publication has no reviewed native adapter on this platform",
                            "Recovery requires a verified durable local filesystem"}:
                self.skipTest(str(exc))
            raise

    def test_restart_pair_load_and_cas_conflict_preserve_external_state(self):
        leaf = locator_leaf(self.database)
        with locked_stores(self.locators, leaf, self.managed) as (locators, managed):
            locator_version = locators.write(leaf, self.locator, None)
            version = managed.write("schedule.json", self.state, None)
        with locked_stores(self.locators, leaf, self.managed) as (locators, managed):
            locator, reopened_version = locators.read(leaf, locator=True)
            state, read_version = managed.read("schedule.json")
            self.assertEqual((reopened_version, read_version), (locator_version, version))
            with admission_session(self.database, _registry_path=self.registry) as owner:
                validate_pair(locator, state, owner)
            changed = replace(self.state, policy=Policy(enabled=True))
            new_version = managed.write("schedule.json", changed, version)
            with self.assertRaises(ScheduleError):
                managed.write("schedule.json", self.state, version)
            self.assertEqual(managed.read("schedule.json"), (changed, new_version))

    def test_file_fsync_failure_leaves_original_and_no_private_stage(self):
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            version = managed.write("schedule.json", self.state, None)
            before = (self.managed / "schedule.json").read_bytes()
            with patch("defiantmaple.scheduled_snapshots.os.fsync", side_effect=OSError("generated disk failure")):
                with self.assertRaises(OSError):
                    managed.write("schedule.json", replace(self.state, policy=Policy(enabled=True)), version)
            self.assertEqual((self.managed / "schedule.json").read_bytes(), before)
            self.assertEqual(list(self.managed.glob("*.stage")), [])

    def test_post_publication_directory_fsync_failure_is_uncertain(self):
        real_fsync = os.fsync
        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("generated directory sync failure")
            return real_fsync(fd)
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            version = managed.write("schedule.json", self.state, None)
            changed = replace(self.state, policy=Policy(enabled=True))
            with patch("defiantmaple.scheduled_snapshots.os.fsync", side_effect=fsync):
                with self.assertRaises(StateUncertainError):
                    managed.write("schedule.json", changed, version)
            self.assertEqual(managed.read("schedule.json")[0], changed)

    def test_symlink_fifo_unsafe_mode_and_lock_replacement_refuse(self):
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            version = managed.write("schedule.json", self.state, None)
            path = self.managed / "schedule.json"
            path.chmod(0o644)
            with self.assertRaises(ScheduleError):
                managed.read("schedule.json")
            path.chmod(0o600)
            path.rename(self.managed / "original.json")
            path.symlink_to(self.managed / "original.json")
            with self.assertRaises(OSError):
                managed.read("schedule.json")
            path.unlink()
            os.mkfifo(path, 0o600)
            with self.assertRaises(ScheduleError):
                managed.read("schedule.json")
            path.unlink()
            (self.managed / "original.json").rename(path)
            (self.managed / "schedule.lock").rename(self.managed / "old.lock")
            (self.managed / "schedule.lock").touch(mode=0o600)
            with self.assertRaises(ScheduleError):
                managed.write("schedule.json", self.state, version)

    def test_nonblocking_lock_and_permanent_lock_identity(self):
        with LockedDirectory(self.managed, "schedule.lock"):
            info = (self.managed / "schedule.lock").stat()
            with self.assertRaises(LibraryInUseError):
                with LockedDirectory(self.managed, "schedule.lock"):
                    self.fail("second schedule lock acquired")
        with LockedDirectory(self.managed, "schedule.lock"):
            after = (self.managed / "schedule.lock").stat()
            self.assertEqual((info.st_dev, info.st_ino, info.st_size), (after.st_dev, after.st_ino, after.st_size))

    def test_post_enter_directory_and_lock_permission_link_mutations_refuse(self):
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            version = managed.write("schedule.json", self.state, None)
            before = (self.managed / "schedule.json").read_bytes()
            for target in (self.managed, self.managed / "schedule.lock"):
                original = stat.S_IMODE(target.stat().st_mode)
                try:
                    target.chmod(original | 0o020)
                    with self.assertRaises(ScheduleError):
                        managed.read("schedule.json")
                    with self.assertRaises(ScheduleError):
                        managed.write("schedule.json", self.state, version)
                finally:
                    target.chmod(original)
            alias = self.managed / "additional-lock-link"
            os.link(self.managed / "schedule.lock", alias)
            try:
                with self.assertRaises(ScheduleError):
                    managed.read("schedule.json")
                with self.assertRaises(ScheduleError):
                    managed.write("schedule.json", self.state, version)
            finally:
                alias.unlink()
            (self.managed / "schedule.lock").write_bytes(b"changed")
            with self.assertRaises(ScheduleError):
                managed.read("schedule.json")
            with self.assertRaises(ScheduleError):
                managed.write("schedule.json", self.state, version)
            self.assertEqual((self.managed / "schedule.json").read_bytes(), before)

    def test_permission_change_after_stage_sync_prevents_publication(self):
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            version = managed.write("schedule.json", self.state, None)
            before = (self.managed / "schedule.json").read_bytes()
            real_fsync = os.fsync
            def fsync(fd):
                result = real_fsync(fd)
                if stat.S_ISREG(os.fstat(fd).st_mode):
                    self.managed.chmod(0o720)
                return result
            try:
                with patch("defiantmaple.scheduled_snapshots.os.fsync", side_effect=fsync):
                    with self.assertRaises(ScheduleError):
                        managed.write("schedule.json", replace(self.state, policy=Policy(enabled=True)), version)
            finally:
                self.managed.chmod(0o700)
            self.assertEqual((self.managed / "schedule.json").read_bytes(), before)
            self.assertEqual(list(self.managed.glob("*.stage")), [])

    def test_successful_link_then_stage_unlink_failure_preserves_uncertainty(self):
        real_unlink = os.unlink
        with LockedDirectory(self.managed, "schedule.lock") as managed:
            def unlink(path, *args, **kwargs):
                if str(path).endswith(".stage"):
                    raise OSError("generated stage unlink failure")
                return real_unlink(path, *args, **kwargs)
            with patch("defiantmaple.scheduled_snapshots.os.unlink", side_effect=unlink):
                with self.assertRaises(StateUncertainError):
                    managed.write("schedule.json", self.state, None)
            self.assertTrue((self.managed / "schedule.json").exists())
            stages = list(self.managed.glob("*.stage"))
            self.assertEqual(len(stages), 1)
            # Both names remain as evidence; after explicit generated-fixture
            # reconciliation the published file is again singly linked/readable.
            stages[0].unlink()
            self.assertEqual(managed.read("schedule.json")[0], self.state)

    def test_final_named_removal_or_valid_substitution_is_not_write_success(self):
        real_fsync = os.fsync
        for operation in ("remove", "substitute"):
            with self.subTest(operation=operation):
                path = self.managed / "schedule.json"
                if path.exists():
                    path.unlink()
                with LockedDirectory(self.managed, "schedule.lock") as managed:
                    version = managed.write("schedule.json", self.state, None)
                    changed = replace(self.state, policy=Policy(enabled=True))
                    def fsync(fd):
                        result = real_fsync(fd)
                        if stat.S_ISDIR(os.fstat(fd).st_mode):
                            path.unlink()
                            if operation == "substitute":
                                # The bytes are even identical to the requested
                                # document; replacing its native identity refuses.
                                path.touch(mode=0o600)
                                path.write_bytes(encode_document(changed))
                        return result
                    with patch("defiantmaple.scheduled_snapshots.os.fsync", side_effect=fsync):
                        with self.assertRaises(StateUncertainError):
                            managed.write("schedule.json", changed, version)
