"""Internal, unwired managed-thumbnail budget prerequisites.

No production writer calls this module. Inventory is an observed cooperative
snapshot, not an atomic filesystem quota. Enrollment, durable reservations and
owned publication are separate prerequisites before active write admission.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import io
import os
from pathlib import Path
import stat

GIB = 1024 ** 3
DEFAULT_BYTES = 5 * GIB
MAX_OUTPUT_BYTES = 20 * 1024 ** 2


class BudgetRefusal(ValueError):
    pass


class InventoryUnsupported(BudgetRefusal):
    pass


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise BudgetRefusal(f"{name} must be an integer at least {minimum}")
    return value


@dataclass(frozen=True)
class BudgetPolicy:
    byte_limit: int = DEFAULT_BYTES
    file_limit: int = 10000
    entry_limit: int = 20000
    depth_limit: int = 32

    def __post_init__(self):
        for name in ('byte_limit', 'file_limit', 'entry_limit', 'depth_limit'):
            _integer(getattr(self, name), name, minimum=1)
        if self.byte_limit > DEFAULT_BYTES or self.file_limit > 10000 or self.entry_limit > 20000 or self.depth_limit > 32:
            raise BudgetRefusal('Policy may tighten but not expand prerequisite ceilings')


@dataclass(frozen=True)
class ObservedUsage:
    logical_bytes: int
    regular_files: int
    entries: int

    def __post_init__(self):
        for name in ('logical_bytes', 'regular_files', 'entries'):
            _integer(getattr(self, name), name)
        if self.regular_files > self.entries:
            raise BudgetRefusal('Regular-file count exceeds entry count')


def admits(usage: ObservedUsage, additional: ObservedUsage, policy: BudgetPolicy = BudgetPolicy()) -> bool:
    """Pure conservative arithmetic; not a lock, reservation or write permit."""
    if type(usage) is not ObservedUsage or type(additional) is not ObservedUsage or type(policy) is not BudgetPolicy:
        raise BudgetRefusal('Accounting requires typed usage and policy')
    return (usage.logical_bytes + additional.logical_bytes <= policy.byte_limit
            and usage.regular_files + additional.regular_files <= policy.file_limit
            and usage.entries + additional.entries <= policy.entry_limit)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _same_object(left, right):
    return (left.st_dev, left.st_ino, left.st_mode) == (right.st_dev, right.st_ino, right.st_mode)


def _supported():
    if (os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
            or os.stat not in os.supports_follow_symlinks or os.scandir not in os.supports_fd):
        raise InventoryUnsupported('Pinned no-follow inventory is unsupported on this platform')


class PinnedRoot:
    """Explicit borrowed-by-inventory root; caller owns its context lifetime.

    All lexical ancestors are pinned without following symlinks. This does not
    enroll/adopt a root or confer persistent library ownership. Only an ordinary
    private current-user root is accepted; unsupported platforms fail closed.
    """
    def __init__(self, path: Path):
        _supported()
        self.path = Path(path)
        self._handles = []
        self._names = []
        if (not self.path.is_absolute() or '..' in self.path.parts
                or self.path == Path(self.path.anchor) or len(self.path.parts) - 1 > 64):
            raise BudgetRefusal('Managed root must be an absolute non-root lexical path')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            self._handles.append(os.open(self.path.anchor, flags))
            for name in self.path.parts[1:]:
                before = os.stat(name, dir_fd=self._handles[-1], follow_symlinks=False)
                fd = os.open(name, flags, dir_fd=self._handles[-1])
                self._handles.append(fd)
                self._names.append(name)
                if not stat.S_ISDIR(before.st_mode) or not _same_object(before, os.fstat(fd)):
                    raise BudgetRefusal('Managed root ancestry changed while opening')
            info = os.fstat(self.fd)
            self._check_permissions(info)
            self.validate()
        except OSError as exc:
            self.close()
            raise BudgetRefusal('Managed root could not be pinned safely') from exc
        except BaseException:
            self.close()
            raise

    def _check_permissions(self, info):
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise BudgetRefusal('Managed root must be private and current-user owned')

    @property
    def fd(self):
        if not self._handles:
            raise BudgetRefusal('Pinned root is closed')
        return self._handles[-1]

    def validate(self):
        if not self._handles:
            raise BudgetRefusal('Pinned root is closed')
        for parent, child, name in zip(self._handles, self._handles[1:], self._names):
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or not _same_object(before, os.fstat(child)):
                raise BudgetRefusal('Pinned root path no longer names its captured directories')
        info = os.fstat(self.fd)
        self._check_permissions(info)

    def close(self):
        while self._handles:
            os.close(self._handles.pop())

    def __enter__(self):
        self.validate()
        return self

    def __exit__(self, *_):
        self.close()


class ProtectedAccountingRoot(PinnedRoot):
    """Read-only accounting of an owner-controlled parent; never a write root."""
    def _check_permissions(self, info):
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise BudgetRefusal('Accounting parent must be current-user controlled')


@contextmanager
def _fresh_entries(fd):
    # A pinned directory opened before an entry is created may retain an old
    # enumeration view on some filesystems. Reopen relative to that exact inode,
    # rather than reusing its cursor or resolving the pathname again.
    fresh = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        if _identity(os.fstat(fresh)) != _identity(os.fstat(fd)):
            raise BudgetRefusal('Inventory enumeration root changed')
        with os.scandir(fresh) as entries:
            yield entries
    finally:
        os.close(fresh)


def inventory(root: PinnedRoot, policy: BudgetPolicy = BudgetPolicy(),
              *, managed_child: PinnedRoot | None = None) -> ObservedUsage:
    """Count every regular pathname, including unknown data and hard-link aliases.

    Bounds limit entries/depth, not elapsed blocking filesystem syscalls.
    No contents are decoded, no entries are deleted, and an over-byte-limit
    result is retained as usage. Unsafe/incomplete/over-count traversal refuses.
    Concurrent mutation detected during inspection refuses; changes after checks
    require the future cooperating writer gate and are not an atomic guarantee.
    """
    if type(root) not in (PinnedRoot, ProtectedAccountingRoot) or type(policy) is not BudgetPolicy:
        raise BudgetRefusal('Inventory requires a pinned root and typed policy')
    skipped = None
    if managed_child is not None:
        if (type(root) is not ProtectedAccountingRoot or type(managed_child) is not PinnedRoot
                or managed_child.path.parent != root.path):
            raise BudgetRefusal('Accounting exclusion requires the exact private immediate child')
        managed_child.validate()
        if _same_object(os.fstat(root.fd), os.fstat(managed_child.fd)):
            raise BudgetRefusal('Accounting parent and managed child alias')
        skipped = managed_child.path.name
    total = files = entries = 0
    skipped_seen = False
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0)

    def walk(fd, depth):
        nonlocal total, files, entries, skipped_seen
        before_directory = os.fstat(fd)
        if before_directory.st_uid != os.getuid():
            raise BudgetRefusal('Inventory directory has unsupported ownership')
        with _fresh_entries(fd) as children:
            for entry in children:
                entries += 1
                if entries > policy.entry_limit:
                    raise BudgetRefusal('Inventory entry ceiling exceeded')
                before = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if before.st_uid != os.getuid():
                    raise BudgetRefusal('Inventory entry has unsupported ownership')
                if stat.S_ISDIR(before.st_mode):
                    if depth == 0 and entry.name == skipped:
                        if not _same_object(before, os.fstat(managed_child.fd)):
                            raise BudgetRefusal('Managed child identity changed during accounting')
                        skipped_seen = True
                        continue
                    if depth + 1 > policy.depth_limit:
                        raise BudgetRefusal('Inventory depth ceiling exceeded')
                    child = os.open(entry.name, directory_flags, dir_fd=fd)
                    try:
                        if _identity(before) != _identity(os.fstat(child)):
                            raise BudgetRefusal('Inventory directory changed while opening')
                        walk(child, depth + 1)
                        after = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                        if _identity(before) != _identity(after):
                            raise BudgetRefusal('Inventory directory changed while inspecting')
                    finally:
                        os.close(child)
                elif stat.S_ISREG(before.st_mode):
                    files += 1
                    if files > policy.file_limit:
                        raise BudgetRefusal('Inventory file ceiling exceeded')
                    child = os.open(entry.name, file_flags, dir_fd=fd)
                    try:
                        opened = os.fstat(child)
                        after = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                        if not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened) or _identity(opened) != _identity(after):
                            raise BudgetRefusal('Inventory file changed while inspecting')
                        total += opened.st_size
                    finally:
                        os.close(child)
                else:
                    raise BudgetRefusal('Inventory refuses links and nonregular entries')
        if _identity(before_directory) != _identity(os.fstat(fd)):
            raise BudgetRefusal('Inventory directory changed during enumeration')
    try:
        root.validate()
        walk(root.fd, 0)
        root.validate()
        if managed_child is not None:
            managed_child.validate()
            if not skipped_seen:
                raise BudgetRefusal('Captured managed child is absent from accounting parent')
    except OSError as exc:
        raise BudgetRefusal('Inventory could not complete safely') from exc
    return ObservedUsage(total, files, entries)


class BoundedOutput:
    """Borrow a seekable binary output without exposing an encoder-bypass fd.

    Accepts memory buffers or POSIX descriptors with verified non-append flags.
    Caller supplies a quiescent stream without pending external writes, and
    owns stream lifetime and staging/cleanup. External writes through an
    alias or a dishonest underlying stream are outside this cooperative wrapper.
    No close, unlink, publication, reservation or production integration occurs.
    """
    def __init__(self, stream, byte_limit):
        self._stream = stream
        self.byte_limit = _integer(byte_limit, 'Output ceiling', minimum=1)
        if self.byte_limit > MAX_OUTPUT_BYTES:
            raise BudgetRefusal('Output ceiling exceeds the supported maximum')
        self._check_overwrite_stream()
        position = stream.tell()
        try:
            end = stream.seek(0, os.SEEK_END)
        finally:
            stream.seek(position, os.SEEK_SET)
        if position < 0 or position > byte_limit or end > byte_limit:
            raise BudgetRefusal('Existing output exceeds its ceiling')

    def _check_overwrite_stream(self):
        mode = getattr(self._stream, 'mode', '')
        if isinstance(mode, str) and 'a' in mode:
            raise BudgetRefusal('Append output cannot enforce a position-based ceiling')
        try:
            descriptor = self._stream.fileno()
        except (AttributeError, io.UnsupportedOperation):
            if not isinstance(self._stream, io.BytesIO):
                raise BudgetRefusal('Output overwrite semantics cannot be verified')
            return
        if os.name != 'posix' or type(descriptor) is not int:
            raise BudgetRefusal('Output descriptor append verification is unsupported')
        import fcntl
        try:
            if fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_APPEND:
                raise BudgetRefusal('Append descriptor cannot enforce a position-based ceiling')
        except OSError as exc:
            raise BudgetRefusal('Output descriptor flags could not be verified') from exc

    def tell(self):
        position = self._stream.tell()
        if not 0 <= position <= self.byte_limit:
            raise BudgetRefusal('Output position exceeds its ceiling')
        return position

    def write(self, data):
        self._check_overwrite_stream()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError('Output requires binary data')
        view = memoryview(data)
        if not view.c_contiguous:
            raise BudgetRefusal('Output requires a contiguous buffer')
        if view.nbytes > self.byte_limit - self.tell():
            raise BudgetRefusal('Output write exceeds its ceiling')
        return self._stream.write(data)

    def seek(self, offset, whence=os.SEEK_SET):
        if type(offset) is not int or type(whence) is not int:
            raise BudgetRefusal('Seek requires integer offset and mode')
        if whence == os.SEEK_SET:
            target = offset
        elif whence == os.SEEK_CUR:
            target = self.tell() + offset
        elif whence == os.SEEK_END:
            position = self.tell()
            try:
                target = self._stream.seek(0, os.SEEK_END) + offset
            finally:
                self._stream.seek(position, os.SEEK_SET)
        else:
            raise BudgetRefusal('Unsupported seek mode')
        if not 0 <= target <= self.byte_limit:
            raise BudgetRefusal('Output seek exceeds its ceiling')
        return self._stream.seek(target, os.SEEK_SET)

    def truncate(self, size=None):
        target = self.tell() if size is None else _integer(size, 'Truncate size')
        if target > self.byte_limit:
            raise BudgetRefusal('Output truncate exceeds its ceiling')
        return self._stream.truncate(target)

    def flush(self):
        self._check_overwrite_stream()
        return self._stream.flush()

    def fileno(self):
        # ImageFile encoders otherwise may bypass write() using the raw fd.
        raise io.UnsupportedOperation('Bounded encoder output does not expose a descriptor')
