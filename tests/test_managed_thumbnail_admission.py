"""Generated A2 process/ownership tests; no account registry or product wiring."""
import errno
import json
import multiprocessing
import os
from pathlib import Path
import select
import signal
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from defiantmaple import managed_thumbnail_admission as managed
from defiantmaple.catalog import initialize
from defiantmaple.thumbnail_budget import BudgetPolicy, BudgetRefusal


def _child_observe_pending(path, ready, release):
    value = json.loads(Path(path).read_text())
    if value['schema'] != 'managed-thumbnail-pending-v1' or not value['reserved_bytes']:
        raise RuntimeError('Generated pending control was not complete before dispatch')
    ready.set()
    if not release.wait(15):
        raise RuntimeError('Generated child release deadline expired')


def _child_fail():
    raise SystemExit(7)


def _contend(authority, domain, database, result):
    try:
        association = managed.capture_association(Path(database))
        with managed.ManagedOperation(Path(authority), Path(domain), association, wait_seconds=.05) as operation:
            operation.finish()
        result.put('admitted')
    except managed.AdmissionBusy:
        result.put('busy')
    except managed.RecoveryHeld:
        result.put('held')
    except BaseException as exc:
        result.put(type(exc).__name__)


def _owner_for_loss(authority, domain, database, child_ready, child_release, result):
    association = managed.capture_association(Path(database))
    with managed.ManagedOperation(Path(authority), Path(domain), association) as operation:
        child = multiprocessing.get_context('spawn').Process(
            target=_child_observe_pending, args=(str(Path(domain) / managed.PENDING), child_ready, child_release))
        operation.start_child(child)
        result.put(child.pid)
        child.join(15)
        operation.finish()


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'register_at_fork'), 'A2 native adapter is POSIX only')
class ManagedAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dm-managed-a2-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(strict=True)
        self.authority, self.domain = self.root / 'authority', self.root / 'domain'
        self.authority.mkdir(mode=0o700)
        self.domain.mkdir(mode=0o700)
        self.database = self.root / 'generated.sqlite3'
        initialize(self.database)
        self.association = managed.capture_association(self.database)
        self.catalog_before = (self.database.read_bytes(), self.database.stat().st_mode, self.database.stat().st_mtime_ns)
        self.context = multiprocessing.get_context('spawn')

    def operation(self, **kw):
        return managed.ManagedOperation(self.authority, self.domain, self.association, **kw)

    def assert_catalog_unchanged(self):
        self.assertEqual((self.database.read_bytes(), self.database.stat().st_mode, self.database.stat().st_mtime_ns), self.catalog_before)

    def stop_process(self, process):
        if process.pid is None:
            return
        if process.is_alive():
            process.terminate()
        process.join(5)
        self.assertFalse(process.is_alive(), 'Generated process cleanup must finish')

    def test_durable_pending_precedes_real_child_and_clean_finish(self):
        ready, release = self.context.Event(), self.context.Event()
        child = self.context.Process(target=_child_observe_pending,
                                     args=(str(self.domain / managed.PENDING), ready, release))
        self.addCleanup(self.stop_process, child)
        with self.operation() as operation:
            self.assertTrue(all(not os.get_inheritable(fd) for fd in operation._fds))
            operation.start_child(child)
            self.assertTrue(ready.wait(5), 'Child observed durable pending')
            with self.assertRaises(managed.RecoveryHeld):
                operation.finish()
            release.set()
            child.join(5)
            self.assertEqual(child.exitcode, 0)
            operation.finish()
            self.assertFalse((self.domain / managed.PENDING).exists())
        with self.operation() as again:
            again.finish()
        self.assert_catalog_unchanged()

    def test_one_child_limit_and_repeated_close_are_safe(self):
        operation = self.operation()
        with operation:
            child = self.context.Process(target=_child_fail)
            self.addCleanup(self.stop_process, child)
            operation.start_child(child)
            child.join(5)
            with self.assertRaises(BudgetRefusal):
                operation.start_child(self.context.Process(target=_child_fail))
            operation.rollback_known()
        operation.close()

    def test_two_real_processes_cannot_overbook_and_next_can_progress(self):
        with self.operation() as operation:
            results = self.context.Queue()
            contender = self.context.Process(target=_contend,
                args=(str(self.authority), str(self.domain), str(self.database), results))
            self.addCleanup(self.stop_process, contender)
            contender.start()
            self.assertEqual(results.get(timeout=5), 'busy')
            contender.join(5)
            self.assertEqual(contender.exitcode, 0)
            operation.finish()
        results = self.context.Queue()
        next_process = self.context.Process(target=_contend,
            args=(str(self.authority), str(self.domain), str(self.database), results))
        self.addCleanup(self.stop_process, next_process)
        next_process.start()
        self.assertEqual(results.get(timeout=5), 'admitted')
        next_process.join(5)
        self.assertEqual(next_process.exitcode, 0)

    def test_same_process_nested_busy_and_cancellation_have_finite_outcomes(self):
        cancel = threading.Event()
        with self.operation() as operation:
            with self.assertRaises(BudgetRefusal):
                operation.__enter__()
            with self.assertRaises(managed.AdmissionBusy):
                with self.operation(wait_seconds=.01):
                    self.fail('Nested contender cannot enter')
            cancel.set()
            with self.assertRaises(managed.AdmissionBusy):
                with self.operation(cancel_event=cancel):
                    self.fail('Canceled contender cannot enter')
            operation.finish()

    def test_too_small_operation_policy_refuses_before_enrollment_control_writes(self):
        policy = BudgetPolicy(byte_limit=managed.EXTERNAL_CONTROLS.logical_bytes)
        with self.assertRaises(BudgetRefusal):
            with self.operation(policy=policy):
                self.fail('A policy without prospective operation capacity cannot enroll')
        self.assertEqual(tuple(self.authority.iterdir()), ())
        self.assertEqual(tuple(self.domain.iterdir()), ())

    def test_alias_and_nested_roots_refuse_before_gate_creation(self):
        for authority, domain in ((self.authority, self.authority),
                                  (self.root, self.domain), (self.domain, self.root)):
            with self.subTest(authority=authority, domain=domain), self.assertRaises(BudgetRefusal):
                with managed.ManagedOperation(authority, domain, self.association):
                    self.fail('Aliases/nesting are unsupported')
        self.assertFalse((self.domain / managed.GATE).exists())
        self.assertFalse((self.authority / managed.GATE).exists())

    def test_pending_from_prior_guard_is_held_without_pid_or_age_reclaim(self):
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation():
                pass
        pending = self.domain / managed.PENDING
        before = (pending.read_bytes(), pending.stat().st_mtime_ns, pending.stat().st_mode)
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation():
                self.fail('Unresolved prior pending cannot be adopted')
        self.assertEqual((pending.read_bytes(), pending.stat().st_mtime_ns, pending.stat().st_mode), before)

    def test_known_prestart_and_joined_failure_rollback_do_not_brick_domain(self):
        with self.operation() as operation:
            with self.assertRaises(BudgetRefusal):
                operation.start_child(object())
            operation.rollback_known()
        cancel = threading.Event()
        with self.operation(cancel_event=cancel) as operation:
            cancel.set()
            child = self.context.Process(target=_child_fail)
            with self.assertRaises(managed.AdmissionBusy):
                operation.start_child(child)
            self.assertIsNone(child.pid)
            operation.rollback_known()
        with self.operation() as operation:
            child = self.context.Process(target=_child_fail)
            self.addCleanup(self.stop_process, child)
            operation.start_child(child)
            child.join(5)
            self.assertEqual(child.exitcode, 7)
            operation.rollback_known()
        with self.operation() as operation:
            operation.finish()
        self.assert_catalog_unchanged()

    def test_ambiguous_start_failure_keeps_pending(self):
        operation = self.operation()
        with self.assertRaises(managed.RecoveryHeld):
            with operation:
                child = self.context.Process(target=_child_fail)
                with patch.object(child, 'start', side_effect=OSError('Generated uncertain start')):
                    with self.assertRaises(OSError):
                        operation.start_child(child)
                with self.assertRaises(managed.RecoveryHeld):
                    operation.rollback_known()
        self.assertTrue(operation.recovery_held)
        self.assertTrue((self.domain / managed.PENDING).is_file())

    def test_known_interrupted_enrollment_and_partial_pending_write_can_rollback(self):
        original = managed.ManagedOperation._new
        def refused_domain(operation, root, name, value):
            if name == managed.DOMAIN:
                raise OSError(errno.ENOSPC, 'Generated enrollment full disk')
            return original(operation, root, name, value)
        with patch.object(managed.ManagedOperation, '_new', new=refused_domain):
            with self.assertRaises(OSError):
                with self.operation():
                    self.fail('Generated enrollment failure')
        self.assertEqual({p.name for p in self.authority.iterdir()}, {managed.GATE})
        self.assertEqual({p.name for p in self.domain.iterdir()}, {managed.GATE})
        real_write = os.write
        def partial_pending(fd, data):
            if b'managed-thumbnail-pending-v1' in data:
                real_write(fd, data[:7])
                raise OSError(errno.ENOSPC, 'Generated partial pending full disk')
            return real_write(fd, data)
        with patch.object(managed.os, 'write', side_effect=partial_pending):
            with self.assertRaises(OSError):
                with self.operation():
                    self.fail('Generated partial pending failure')
        self.assertEqual({p.name for p in self.domain.iterdir()}, {managed.GATE})
        with self.operation() as operation:
            operation.finish()

    def test_substituted_pending_is_preserved_and_never_unlinked(self):
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation() as operation:
                pending = self.domain / managed.PENDING
                pending.rename(self.domain / 'retained-original')
                pending.write_bytes(b'foreign generated bytes')
                pending.chmod(0o600)
                with self.assertRaises(managed.RecoveryHeld):
                    operation.finish()
        self.assertEqual((self.domain / managed.PENDING).read_bytes(), b'foreign generated bytes')
        self.assertTrue((self.domain / 'retained-original').is_file())

    def test_final_inventory_counts_external_controls_before_pending_release(self):
        policy = BudgetPolicy(file_limit=14, entry_limit=40)
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation(policy=policy) as operation:
                for number in range(8):
                    (self.domain / f'unknown-{number}').write_bytes(b'x')
                # Managed11files fits14, plus4external controls exceeds14.
                with self.assertRaises(managed.RecoveryHeld):
                    operation.finish()
        self.assertTrue((self.domain / managed.PENDING).is_file())
        self.assertEqual(len(tuple(self.domain.glob('unknown-*'))), 8)

    def test_unknown_staging_and_hardlink_bytes_are_charged_before_reservation(self):
        with self.operation() as operation:
            operation.finish()
        data = self.domain / 'unknown-staging'
        data.write_bytes(b'unknown')
        os.link(data, self.domain / 'hardlink')
        with managed.PinnedRoot(self.domain) as pinned:
            usage = managed.inventory(pinned)
        # Tighten exactly below usage+external+the conservative operation.
        limit = usage.logical_bytes + managed.EXTERNAL_CONTROLS.logical_bytes + managed.RESERVATION.logical_bytes - 1
        policy = BudgetPolicy(byte_limit=limit)
        before = data.read_bytes()
        with self.assertRaises(BudgetRefusal):
            with self.operation(policy=policy):
                self.fail('Observed unknown aliases must not become free capacity')
        self.assertEqual(data.read_bytes(), before)
        self.assertFalse((self.domain / managed.PENDING).exists())

    def test_changed_catalog_copy_and_custom_root_refuse(self):
        with self.operation() as operation:
            operation.finish()
        copy = self.root / 'copied.sqlite3'
        shutil.copy2(self.database, copy)
        copied = managed.capture_association(copy)
        self.assertEqual(copied.library_id, self.association.library_id)
        self.assertNotEqual(copied.inode, self.association.inode)
        with self.assertRaises(managed.RecoveryHeld):
            with managed.ManagedOperation(self.authority, self.domain, copied):
                self.fail('A copied UUID grants no association')
        other = self.root / 'other-root'
        other.mkdir(mode=0o700)
        with self.assertRaises(managed.RecoveryHeld):
            with managed.ManagedOperation(self.authority, other, self.association):
                self.fail('Root rebinding is not implicit')
        self.assert_catalog_unchanged()

    def test_unknown_duplicate_extra_and_partial_controls_fail_closed(self):
        with self.operation() as operation:
            operation.finish()
        binding = self.authority / ('association-' + self.association.library_id + '.json')
        original = binding.read_bytes()
        variants = (b'{', b'{"schema":"x","schema":"y"}',
                    json.dumps(dict(json.loads(original), unexpected=True)).encode())
        for variant in variants:
            with self.subTest(variant=variant):
                binding.write_bytes(variant)
                with self.assertRaises(BudgetRefusal):
                    with self.operation():
                        self.fail('Unknown/incomplete controls refuse without repair')
                self.assertEqual(binding.read_bytes(), variant)
        binding.write_bytes(original)
        with self.operation() as operation:
            operation.finish()

    def test_same_content_association_control_replacement_is_not_owned_identity(self):
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation() as operation:
                domain = self.domain / managed.DOMAIN
                replacement = self.domain / 'generated-replacement'
                replacement.write_bytes(domain.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, domain)
                with self.assertRaises(managed.RecoveryHeld):
                    operation.finish()
        self.assertTrue((self.domain / managed.PENDING).is_file())

    def test_control_numeric_types_cannot_compare_equal_to_captured_integer_identity(self):
        with self.operation() as operation:
            operation.finish()
        for path, key in ((self.authority / managed.AUTHORITY, 'identity'),
                          (self.domain / managed.DOMAIN, 'managed_identity')):
            with self.subTest(path=path):
                original = path.read_bytes()
                value = json.loads(original)
                value[key] = [float(part) for part in value[key]]
                path.write_text(json.dumps(value))
                with self.assertRaises(BudgetRefusal):
                    with self.operation():
                        self.fail('JSON numeric coercion must not authorize a control')
                path.write_bytes(original)

    def test_root_or_catalog_replacement_during_operation_refuses(self):
        with self.assertRaises(managed.RecoveryHeld):
            with self.operation() as operation:
                original = self.root / 'retained-domain'
                self.domain.rename(original)
                self.domain.mkdir(mode=0o700)
                with self.assertRaises(BudgetRefusal):
                    operation.finish()
        self.assertTrue((original / managed.PENDING).is_file())

    @unittest.skipUnless(hasattr(os, 'fork'), 'Native fork lifetime check')
    def test_fork_child_closes_copied_handles_without_unlocking_parent(self):
        read, write = os.pipe()
        try:
            with self.operation() as operation:
                pid = os.fork()
                if pid == 0:
                    try:
                        os.close(read)
                        refused = False
                        try:
                            operation.finish()
                        except BudgetRefusal:
                            refused = True
                        os.write(write, json.dumps({'fds': len(operation._fds), 'refused': refused}).encode())
                    finally:
                        os._exit(0)
                os.close(write)
                write = None
                self.assertTrue(select.select([read], [], [], 5)[0])
                self.assertEqual(json.loads(os.read(read, 1024)), {'fds': 0, 'refused': True})
                self.assertEqual(os.waitpid(pid, 0)[1], 0)
                with self.assertRaises(managed.AdmissionBusy):
                    with self.operation(wait_seconds=.01):
                        self.fail('Fork child must not unlock parent gate')
                operation.finish()
        finally:
            os.close(read)
            if write is not None:
                os.close(write)

    @unittest.skipUnless(hasattr(os, 'fork'), 'Native fork lifetime check')
    def test_unrelated_live_fork_does_not_retain_closed_parent_gates(self):
        read, write = os.pipe()
        pid = None
        try:
            with self.assertRaises(managed.RecoveryHeld):
                with self.operation() as operation:
                    pid = os.fork()
                    if pid == 0:
                        try:
                            os.close(write)
                            os.read(read, 1)
                        finally:
                            os._exit(0)
            # Child remains blocked/alive. It must not retain gate descriptors.
            with self.assertRaises(managed.RecoveryHeld):
                with self.operation(wait_seconds=.05):
                    self.fail('Unresolved pending is held, not a busy inherited gate')
        finally:
            os.close(read)
            os.write(write, b'x')
            os.close(write)
            if pid is not None:
                self.assertEqual(os.waitpid(pid, 0)[1], 0)

    @unittest.skipUnless(hasattr(os, 'fork'), 'Native fork lifetime barrier check')
    def test_concurrent_fork_waits_for_open_register_boundary(self):
        opened, release_open = threading.Event(), threading.Event()
        fork_waiting, fork_done = threading.Event(), threading.Event()
        owner_ready, release_owner = threading.Event(), threading.Event()
        failures, results = [], []
        operation = self.operation()
        real_open, real_lifetime = os.open, managed._LIFETIME
        delayed = False
        read, write = os.pipe()
        class ObservedLifetime:
            def acquire(self):
                if threading.current_thread().name == 'generated-fork':
                    fork_waiting.set()
                return real_lifetime.acquire()
            def release(self):
                return real_lifetime.release()
            def __enter__(self):
                self.acquire()
                return self
            def __exit__(self, *_):
                self.release()
        def delayed_open(name, *args, **kwargs):
            nonlocal delayed
            descriptor = real_open(name, *args, **kwargs)
            if name == managed.GATE and not delayed:
                delayed = True
                opened.set()
                if not release_open.wait(5):
                    os.close(descriptor)
                    raise RuntimeError('Generated open/register release missing')
            return descriptor
        def own():
            try:
                with operation:
                    owner_ready.set()
                    if not release_owner.wait(5):
                        raise RuntimeError('Generated owner release missing')
                    operation.finish()
            except BaseException as exc:
                failures.append(exc)
        def fork():
            try:
                pid = os.fork()
                if pid == 0:
                    try:
                        os.close(read)
                        os.write(write, json.dumps({'fds': len(operation._fds),
                                                   'forked': operation._forked}).encode())
                    finally:
                        os._exit(0)
                results.append(os.waitpid(pid, 0)[1])
            except BaseException as exc:
                failures.append(exc)
            finally:
                fork_done.set()
        threads = [threading.Thread(target=own, name='generated-owner'),
                   threading.Thread(target=fork, name='generated-fork')]
        try:
            with patch.object(managed, '_LIFETIME', ObservedLifetime()):
                with patch.object(managed.os, 'open', side_effect=delayed_open) as mocked:
                    with patch.object(managed.os, 'supports_dir_fd', os.supports_dir_fd | {mocked}):
                        threads[0].start()
                        self.assertTrue(opened.wait(5), 'Opened fd before registration is deliberately held')
                        threads[1].start()
                        self.assertTrue(fork_waiting.wait(5), 'Fork before-hook reached lifetime mutex')
                        self.assertFalse(fork_done.is_set(), 'Fork cannot pass unregistered successful fd')
                        release_open.set()
                        self.assertTrue(owner_ready.wait(5))
                        self.assertTrue(fork_done.wait(5))
                        self.assertTrue(select.select([read], [], [], 5)[0])
                        self.assertEqual(json.loads(os.read(read, 1024)), {'fds': 0, 'forked': True})
                        release_owner.set()
                        for thread in threads:
                            thread.join(5)
                        self.assertFalse(any(thread.is_alive() for thread in threads))
        finally:
            release_open.set()
            release_owner.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(5)
            os.close(read)
            os.close(write)
        self.assertEqual(failures, [])
        self.assertEqual(results, [0])

    @unittest.skipUnless(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'),
                         'Exact orphan exit observation/signaling requires Linux pidfd')
    def test_owner_loss_keeps_capacity_held_while_orphan_exists(self):
        ready, release = self.context.Event(), self.context.Event()
        results = self.context.Queue()
        owner = self.context.Process(target=_owner_for_loss,
            args=(str(self.authority), str(self.domain), str(self.database), ready, release, results))
        self.addCleanup(self.stop_process, owner)
        owner.start()
        child_pid = results.get(timeout=5)
        self.assertTrue(ready.wait(5))
        descriptor = os.pidfd_open(child_pid)
        try:
            owner.terminate()
            owner.join(5)
            self.assertIsNotNone(owner.exitcode)
            with self.assertRaises(managed.RecoveryHeld):
                with self.operation():
                    self.fail('Lost-owner reservation cannot free live orphan capacity')
            release.set()
            self.assertTrue(select.select([descriptor], [], [], 5)[0], 'Generated orphan exit confirmed')
            with self.assertRaises(managed.RecoveryHeld):
                with self.operation():
                    self.fail('Even exited prior orphan needs separate reviewed recovery')
        finally:
            release.set()
            if not select.select([descriptor], [], [], 0)[0]:
                signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                self.assertTrue(select.select([descriptor], [], [], 5)[0])
            os.close(descriptor)
