"""Unwired A1 primitives: generated owned fixtures, no user-library enrollment."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from defiantmaple import thumbnail_budget as budget


class AccountingTests(unittest.TestCase):
    def test_selected_default_and_exact_boundary_never_credit_unknown_usage(self):
        policy = budget.BudgetPolicy()
        self.assertEqual(policy.byte_limit, 5368709120)
        request = budget.ObservedUsage(41988096, 8, 16)
        exact = budget.ObservedUsage(policy.byte_limit - request.logical_bytes, 1, 1)
        self.assertTrue(budget.admits(exact, request, policy))
        self.assertFalse(budget.admits(budget.ObservedUsage(exact.logical_bytes + 1, 1, 1), request))
        self.assertFalse(budget.admits(budget.ObservedUsage(policy.byte_limit + 1, 1, 1), budget.ObservedUsage(0, 0, 0)))

    def test_file_and_entry_budgets_are_independent(self):
        policy = budget.BudgetPolicy(byte_limit=100, file_limit=2, entry_limit=3)
        self.assertTrue(budget.admits(budget.ObservedUsage(0, 1, 1), budget.ObservedUsage(1, 1, 2), policy))
        self.assertFalse(budget.admits(budget.ObservedUsage(0, 2, 2), budget.ObservedUsage(1, 1, 1), policy))
        self.assertFalse(budget.admits(budget.ObservedUsage(0, 1, 3), budget.ObservedUsage(1, 0, 1), policy))

    def test_malformed_accounting_and_expanded_ceiling_refuse(self):
        for value in (-1, True, 1.5, '1'):
            with self.subTest(value=value), self.assertRaises(budget.BudgetRefusal):
                budget.ObservedUsage(value, 0, 0)
        with self.assertRaises(budget.BudgetRefusal):
            budget.ObservedUsage(0, 2, 1)
        with self.assertRaises(budget.BudgetRefusal):
            budget.BudgetPolicy(byte_limit=budget.DEFAULT_BYTES + 1)
        with self.assertRaises(budget.BudgetRefusal):
            budget.admits({}, budget.ObservedUsage(0, 0, 0))


@unittest.skipUnless(os.name == 'posix', 'Pinned inventory currently has only a POSIX adapter')
class PinnedInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dm-budget-generated-')
        self.addCleanup(temporary.cleanup)
        # macOS may expose its generated temp directory through /var -> /private/var.
        # Canonicalize only this owned fixture; production no-follow stays strict.
        self.root = Path(temporary.name).resolve(strict=True)

    def test_generated_temp_alias_is_canonicalized_without_admitting_symlink_roots(self):
        actual = self.root / 'actual'
        actual.mkdir(mode=0o700)
        alias = self.root / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        with tempfile.TemporaryDirectory(prefix='generated-', dir=alias) as name:
            lexical = Path(name)
            canonical = lexical.resolve(strict=True)
            self.assertNotEqual(lexical, canonical)
            with self.assertRaises(budget.BudgetRefusal):
                budget.PinnedRoot(lexical)
            with budget.PinnedRoot(canonical) as root:
                self.assertEqual(budget.inventory(root), budget.ObservedUsage(0, 0, 0))

    def test_unknown_legacy_staging_control_and_hardlinks_all_charged(self):
        data = self.root / 'legacy.png'
        data.write_bytes(b'legacy')
        (self.root / 'unknown').write_bytes(b'unknown!')
        (self.root / '.control').write_bytes(b'ctl')
        folder = self.root / 'nested'
        folder.mkdir()
        (folder / '.staging').write_bytes(b'stage')
        os.link(data, self.root / 'hardlink')
        before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                  for p in self.root.rglob('*') if p.is_file()}
        with budget.PinnedRoot(self.root) as root:
            usage = budget.inventory(root, budget.BudgetPolicy(byte_limit=1))
        self.assertEqual(usage, budget.ObservedUsage(6 + 8 + 3 + 5 + 6, 5, 6))
        self.assertFalse(budget.admits(usage, budget.ObservedUsage(1, 1, 1), budget.BudgetPolicy(byte_limit=1)))
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in before})

    def test_inventory_entry_file_and_depth_overflow_refuse_without_deletion(self):
        (self.root / 'one').write_bytes(b'1')
        (self.root / 'two').write_bytes(b'2')
        folder = self.root / 'nested'
        folder.mkdir()
        (folder / 'deeper').mkdir()
        for policy in (budget.BudgetPolicy(file_limit=1), budget.BudgetPolicy(entry_limit=1), budget.BudgetPolicy(depth_limit=1)):
            with self.subTest(policy=policy), budget.PinnedRoot(self.root) as root:
                with self.assertRaises(budget.BudgetRefusal):
                    budget.inventory(root, policy)
        self.assertEqual((self.root / 'one').read_bytes(), b'1')
        self.assertTrue((folder / 'deeper').is_dir())

    def test_symlink_and_nonregular_entries_refuse_without_following(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'preserve')
        nested = self.root / 'managed'
        nested.mkdir(mode=0o700)
        link = nested / 'link'
        link.symlink_to(outside)
        with budget.PinnedRoot(nested) as root, self.assertRaises(budget.BudgetRefusal):
            budget.inventory(root)
        link.unlink()
        os.mkfifo(nested / 'pipe')
        with budget.PinnedRoot(nested) as root, self.assertRaises(budget.BudgetRefusal):
            budget.inventory(root)
        self.assertEqual(outside.read_bytes(), b'preserve')
        self.assertTrue((nested / 'pipe').exists())

    def test_symlink_root_or_ancestor_and_nonprivate_root_refuse(self):
        actual = self.root / 'actual'
        actual.mkdir(mode=0o700)
        (actual / 'child').mkdir(mode=0o700)
        link = self.root / 'alias'
        link.symlink_to(actual, target_is_directory=True)
        for path in (link, link / 'child'):
            with self.subTest(path=path), self.assertRaises(budget.BudgetRefusal):
                budget.PinnedRoot(path)
        actual.chmod(0o755)
        with self.assertRaises(budget.BudgetRefusal):
            budget.PinnedRoot(actual)

    def test_root_replacement_and_closed_handle_refuse(self):
        actual = self.root / 'managed'
        actual.mkdir(mode=0o700)
        with budget.PinnedRoot(actual) as root:
            actual.rename(self.root / 'original')
            actual.mkdir(mode=0o700)
            with self.assertRaises(budget.BudgetRefusal):
                budget.inventory(root)
        with self.assertRaises(budget.BudgetRefusal):
            budget.inventory(root)
        self.assertTrue((self.root / 'original').is_dir())

    def test_file_replacement_between_stat_and_open_fails_closed(self):
        path = self.root / 'item'
        path.write_bytes(b'original')
        real_open = os.open
        swapped = False
        def racing_open(name, *args, **kwargs):
            nonlocal swapped
            if name == 'item' and not swapped:
                swapped = True
                path.rename(self.root / 'retained')
                path.write_bytes(b'replacement')
            return real_open(name, *args, **kwargs)
        with budget.PinnedRoot(self.root) as root, patch.object(budget.os, 'open', side_effect=racing_open):
            with self.assertRaises(budget.BudgetRefusal):
                budget.inventory(root)
        self.assertTrue(swapped)
        self.assertEqual((self.root / 'retained').read_bytes(), b'original')
        self.assertEqual(path.read_bytes(), b'replacement')

    def test_directory_replacement_and_growth_during_walk_refuse(self):
        nested = self.root / 'nested'
        nested.mkdir()
        real_open = os.open
        def racing_open(name, *args, **kwargs):
            if name == 'nested':
                nested.rename(self.root / 'retained')
                nested.mkdir()
            return real_open(name, *args, **kwargs)
        with budget.PinnedRoot(self.root) as root, patch.object(budget.os, 'open', side_effect=racing_open):
            with self.assertRaises(budget.BudgetRefusal):
                budget.inventory(root)
        self.assertTrue((self.root / 'retained').is_dir())

    def test_file_growth_during_inspection_refuses(self):
        path = self.root / 'item'
        path.write_bytes(b'old')
        real_fstat = os.fstat
        changed = False
        inode = path.stat().st_ino
        def growing_fstat(fd):
            nonlocal changed
            result = real_fstat(fd)
            if result.st_ino == inode and not changed:
                changed = True
                path.write_bytes(b'new and bigger')
            return result
        with budget.PinnedRoot(self.root) as root, patch.object(budget.os, 'fstat', side_effect=growing_fstat):
            with self.assertRaises(budget.BudgetRefusal):
                budget.inventory(root)
        self.assertTrue(changed)
        self.assertEqual(path.read_bytes(), b'new and bigger')

    def test_lexical_root_ancestry_is_bounded_before_opening(self):
        with self.assertRaises(budget.BudgetRefusal):
            budget.PinnedRoot(Path('/') / Path(*(['generated'] * 65)))

    def test_unsupported_adapter_refuses_explicitly(self):
        with patch.object(budget.os, 'name', 'unsupported'):
            with self.assertRaises(budget.InventoryUnsupported):
                budget.PinnedRoot(self.root)


class BoundedOutputTests(unittest.TestCase):
    def test_write_exact_limit_and_refused_overflow_leave_bytes_unchanged(self):
        stream = io.BytesIO()
        bounded = budget.BoundedOutput(stream, 4)
        self.assertEqual(bounded.write(b'abcd'), 4)
        with self.assertRaises(budget.BudgetRefusal):
            bounded.write(b'e')
        self.assertEqual(stream.getvalue(), b'abcd')
        with self.assertRaises(io.UnsupportedOperation):
            bounded.fileno()
        self.assertFalse(stream.closed)

    def test_seek_overwrite_and_truncate_remain_within_ceiling(self):
        stream = io.BytesIO(b'abcdefgh')
        bounded = budget.BoundedOutput(stream, 8)
        bounded.seek(-2, os.SEEK_END)
        bounded.write(b'XY')
        self.assertEqual(stream.getvalue(), b'abcdefXY')
        bounded.seek(-3, os.SEEK_CUR)
        self.assertEqual(bounded.tell(), 5)
        bounded.truncate()
        self.assertEqual(stream.getvalue(), b'abcde')
        for call in (lambda: bounded.seek(9), lambda: bounded.seek(-1),
                     lambda: bounded.seek(4, os.SEEK_END), lambda: bounded.truncate(9),
                     lambda: bounded.seek(True), lambda: bounded.seek(1, True)):
            with self.assertRaises(budget.BudgetRefusal):
                call()
        self.assertEqual(stream.getvalue(), b'abcde')

    def test_invalid_existing_output_and_limits_refuse(self):
        stream = io.BytesIO(b'12345')
        stream.seek(2)
        with self.assertRaises(budget.BudgetRefusal):
            budget.BoundedOutput(stream, 4)
        self.assertEqual(stream.tell(), 2)
        self.assertEqual(stream.getvalue(), b'12345')
        for limit in (0, True, -1, budget.MAX_OUTPUT_BYTES + 1):
            with self.assertRaises(budget.BudgetRefusal):
                budget.BoundedOutput(io.BytesIO(), limit)

    @unittest.skipUnless(os.name == 'posix', 'File-backed output requires POSIX append verification')
    def test_real_png_encoder_cannot_bypass_stream_limit_via_file_descriptor(self):
        with tempfile.TemporaryFile('w+b') as stream:
            bounded = budget.BoundedOutput(stream, 40)
            with Image.new('RGB', (8, 8), (30, 70, 110)) as image:
                with self.assertRaises(budget.BudgetRefusal):
                    image.save(bounded, format='PNG')
            self.assertLessEqual(os.fstat(stream.fileno()).st_size, 40)
            self.assertFalse(stream.closed)
        with tempfile.TemporaryFile('w+b') as stream:
            bounded = budget.BoundedOutput(stream, 1024)
            with Image.new('RGBA', (8, 8), (30, 70, 110, 90)) as image:
                image.save(bounded, format='PNG')
            bounded.flush()
            self.assertLessEqual(os.fstat(stream.fileno()).st_size, 1024)
            stream.seek(0)
            with Image.open(stream) as image:
                self.assertEqual(image.getpixel((0, 0)), (30, 70, 110, 90))

    def test_memory_png_and_unsupported_descriptor_adapter(self):
        stream = io.BytesIO()
        bounded = budget.BoundedOutput(stream, 1024)
        with Image.new('RGBA', (8, 8), (30, 70, 110, 90)) as image:
            image.save(bounded, format='PNG')
        stream.seek(0)
        with Image.open(stream) as decoded:
            self.assertEqual(decoded.getpixel((0, 0)), (30, 70, 110, 90))
        with tempfile.TemporaryFile('w+b') as file:
            with patch.object(budget.os, 'name', 'unsupported'):
                with self.assertRaises(budget.BudgetRefusal):
                    budget.BoundedOutput(file, 1024)
            self.assertEqual(os.fstat(file.fileno()).st_size, 0)

    def test_real_append_stream_refuses_before_any_bytes_change(self):
        with tempfile.TemporaryDirectory(prefix='dm-budget-append-') as name:
            path = Path(name) / 'generated.bin'
            path.write_bytes(b'abcd')
            before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            with path.open('a+b') as stream:
                stream.seek(0)
                with self.assertRaises(budget.BudgetRefusal):
                    budget.BoundedOutput(stream, 4)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode), before)

    @unittest.skipUnless(os.name == 'posix', 'Descriptor append flag inspection is POSIX only')
    def test_hidden_descriptor_append_flags_and_later_flag_change_refuse(self):
        import fcntl
        with tempfile.TemporaryDirectory(prefix='dm-budget-append-fd-') as name:
            path = Path(name) / 'generated.bin'
            path.write_bytes(b'abcd')
            fd = os.open(path, os.O_RDWR | os.O_APPEND)
            with os.fdopen(fd, 'r+b') as stream:
                self.assertNotIn('a', stream.mode)
                with self.assertRaises(budget.BudgetRefusal):
                    budget.BoundedOutput(stream, 4)
            with path.open('r+b', buffering=0) as stream:
                bounded = budget.BoundedOutput(stream, 4)
                flags = fcntl.fcntl(stream.fileno(), fcntl.F_GETFL)
                fcntl.fcntl(stream.fileno(), fcntl.F_SETFL, flags | os.O_APPEND)
                with self.assertRaises(budget.BudgetRefusal):
                    bounded.write(b'x')
                with self.assertRaises(budget.BudgetRefusal):
                    bounded.flush()
            self.assertEqual(path.read_bytes(), b'abcd')

    @unittest.skipUnless(os.name == 'posix', 'File-backed output requires POSIX append verification')
    def test_fd_capable_jpeg_encoder_must_use_bounded_writes(self):
        # ImageFile encoders can write directly to fileno(). Refusing that
        # capability forces this encoder through the checked Python writes.
        with tempfile.TemporaryFile('w+b') as stream:
            bounded = budget.BoundedOutput(stream, 64)
            with Image.new('RGB', (8, 8), (30, 70, 110)) as image:
                with self.assertRaises(budget.BudgetRefusal):
                    image.save(bounded, format='JPEG')
            self.assertLessEqual(os.fstat(stream.fileno()).st_size, 64)
            self.assertFalse(stream.closed)

    def test_underlying_write_error_retains_partial_data_without_cleanup(self):
        class FullDisk(io.BytesIO):
            def write(self, data):
                super().write(data[:2])
                raise OSError('Generated full disk')
        stream = FullDisk()
        bounded = budget.BoundedOutput(stream, 4)
        with self.assertRaises(OSError):
            bounded.write(b'abcd')
        self.assertEqual(stream.getvalue(), b'ab')
        self.assertFalse(stream.closed)
