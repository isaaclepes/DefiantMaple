"""Generated nondeletion package descriptor lifetime tests; reviewed before run."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple.recovery_storage import (PackageInUseError, leased_package,
    package_lease, private_local_parent, regular_existing)


class PackageLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / 'fictional.dmbackup'
        self.package.write_bytes(b'fictional lease bytes; never a recovery package')
        self.stack = self.enterContext(ExitStack())
        try:
            _, self.directory = self.stack.enter_context(private_local_parent(self.package))
        except ValueError as exc:
            detail = str(exc)
            if detail == 'Recovery publication has no reviewed native adapter on this platform':
                self.skipTest('Package lease native test requires the reviewed Linux storage adapter; ' + detail)
            if detail == 'Recovery requires a verified durable local filesystem':
                self.skipTest('Package lease native test requires qualified local backing; ' + detail)
            raise

    def descriptor(self):
        descriptor, _ = regular_existing(self.package, self.directory)
        self.addCleanup(os.close, descriptor)
        return descriptor

    def test_shared_readers_coexist_and_exclusive_is_typed_busy(self):
        first, second, exclusive = (self.descriptor() for _ in range(3))
        with package_lease(first), package_lease(second):
            self.assertFalse(os.get_inheritable(first))
            with self.assertRaises(PackageInUseError):
                with package_lease(exclusive, exclusive=True):
                    self.fail('exclusive acquired while actual shared FDs held')
        with package_lease(exclusive, exclusive=True):
            with self.assertRaises(PackageInUseError):
                with package_lease(first):
                    self.fail('reader acquired while actual exclusive FD held')

    def test_exception_releases_lease_but_does_not_close_caller_fd(self):
        descriptor, other = self.descriptor(), self.descriptor()
        with self.assertRaisesRegex(RuntimeError, 'generated'):
            with package_lease(descriptor):
                raise RuntimeError('generated exception')
        os.fstat(descriptor)
        with package_lease(other, exclusive=True):
            pass

    def test_leased_package_owns_and_closes_its_exact_fd(self):
        with leased_package(self.package, self.directory) as (descriptor, _):
            self.assertEqual(os.read(descriptor, 1024), self.package.read_bytes())
        with self.assertRaises(OSError):
            os.fstat(descriptor)
        with package_lease(self.descriptor(), exclusive=True):
            pass

    def test_named_replacement_after_lease_acquisition_refuses_before_read(self):
        from defiantmaple import recovery_storage
        original = package_lease
        @contextmanager
        def replace_name(descriptor, **kwargs):
            with original(descriptor, **kwargs):
                self.package.rename(self.root / 'original-kept.dmbackup')
                self.package.write_bytes(b'replacement sentinel; do not adopt')
                yield descriptor
        with patch.object(recovery_storage, 'package_lease', replace_name):
            with self.assertRaisesRegex(ValueError, 'name changed'):
                with leased_package(self.package, self.directory):
                    self.fail('substituted name was accepted')
        self.assertEqual(self.package.read_bytes(), b'replacement sentinel; do not adopt')
        with package_lease(self.descriptor(), exclusive=True):
            pass

    @unittest.skipUnless(hasattr(os, 'fork'), 'fork unavailable')
    def test_fork_child_closes_inherited_fd_without_unlocking_parent(self):
        descriptor, other = self.descriptor(), self.descriptor()
        with package_lease(descriptor):
            read, write = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(read)
                try:
                    try:
                        os.fstat(descriptor)
                    except OSError:
                        os.write(write, b'closed')
                    else:
                        os.write(write, b'leaked')
                finally:
                    os.close(write)
                    os._exit(0)
            os.close(write)
            try:
                self.assertEqual(os.read(read, 32), b'closed')
                _, status = os.waitpid(pid, 0)
                self.assertEqual(status, 0)
                with self.assertRaises(PackageInUseError):
                    with package_lease(other, exclusive=True):
                        self.fail('fork child unlocked original parent')
            finally:
                os.close(read)
        with package_lease(other, exclusive=True):
            pass


class PackageLeaseBoundaryTests(unittest.TestCase):
    def test_unsupported_native_guard_refuses_before_opening_package(self):
        from defiantmaple import recovery_storage
        for platform in ('darwin', 'win32'):
            with self.subTest(platform=platform), \
                    patch.object(recovery_storage.sys, 'platform', platform), \
                    patch.object(recovery_storage, 'regular_existing') as opened:
                with self.assertRaisesRegex(ValueError, 'no reviewed native adapter'):
                    with private_local_parent(Path('/fictional-package.dmbackup')):
                        self.fail('unsupported publication adapter accepted')
                opened.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'No reviewed package-use lease adapter'):
                    with package_lease(-1):
                        self.fail('unsupported package lease adapter accepted')


if __name__ == '__main__':
    unittest.main()
