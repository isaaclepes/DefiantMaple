"""Cooperative, explicit application ownership; low-level Core APIs stay unwrapped.

The v1 registry/key protocol is shared with the Rust comparison executable.
No PID file or serialized value grants authority. See the reviewed design.
"""
from __future__ import annotations
from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path
import stat
import sys
import threading


class AdmissionError(ValueError):
    pass


class LibraryInUseError(AdmissionError):
    pass


def key_bytes(kind: str, identity: tuple[int, int], leaf: bytes = b"") -> bytes:
    if kind not in ("directory", "path", "file") or any(type(n) is not int or n < 0 for n in identity):
        raise AdmissionError("Invalid admission resource identity")
    platform = "windows" if sys.platform == "win32" else "posix"
    return (f"dm-admission-v1\n{kind}\n{platform}\n{identity[0]}\n{identity[1]}\n{leaf.hex()}\n").encode("ascii")


def registry_path() -> Path:
    if sys.platform == "win32":
        from ctypes import wintypes
        # FOLDERID_LocalAppData: F1B32785-6FBA-4FCF-9D55-7B8E7F157091.
        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                        ("d", ctypes.c_ubyte * 8)]
        folder = GUID(0xF1B32785, 0x6FBA, 0x4FCF, (ctypes.c_ubyte * 8)(0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91))
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                               ctypes.POINTER(ctypes.c_void_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        pointer = ctypes.c_void_p()
        if shell.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(pointer)) != 0:
            raise AdmissionError("Cannot establish the OS account admission registry")
        if not pointer.value:
            raise AdmissionError("OS account known-folder path is missing")
        try:
            home = Path(ctypes.wstring_at(pointer))
        finally:
            ole = ctypes.WinDLL("ole32")
            ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ole.CoTaskMemFree(pointer)
        if not home.is_absolute():
            raise AdmissionError("OS account known-folder path must be absolute")
        return home / "DefiantMaple" / "admission-v1"
    if sys.platform not in ("linux", "darwin"):
        raise AdmissionError("No native library admission adapter for this platform")
    import pwd
    if os.getuid() != os.geteuid():
        raise AdmissionError("Library admission refuses differing real and effective users")
    try:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError) as exc:
        raise AdmissionError("Cannot establish the OS account admission registry") from exc
    if not home.is_absolute():
        raise AdmissionError("OS account home must be absolute")
    return home / ".defiantmaple" / "admission-v1"


def _registry(path: Path) -> Path:
    for directory in (path.parent, path):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise AdmissionError("Admission registry must be an ordinary directory")
        if sys.platform != "win32" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise AdmissionError("Admission registry must be private and user-owned")
        if sys.platform == "win32" and getattr(info, "st_file_attributes", 0) & 0x400:
            raise AdmissionError("Admission registry cannot be a reparse point")
    return path


if sys.platform == "win32":
    from ctypes import wintypes
    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]
    class _FILEINFO(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("creation", wintypes.FILETIME),
                    ("access", wintypes.FILETIME), ("write", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("sizehigh", wintypes.DWORD), ("sizelow", wintypes.DWORD),
                    ("links", wintypes.DWORD), ("indexhigh", wintypes.DWORD), ("indexlow", wintypes.DWORD)]
    class _FILE_ID_INFO(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_uint64), ("identifier", ctypes.c_ubyte * 16)]
    if ctypes.sizeof(_FILE_ID_INFO) != 24 or _FILE_ID_INFO.identifier.offset != 8:
        raise RuntimeError("Unsupported Windows FILE_ID_INFO native structure layout")
    _win = ctypes.WinDLL("kernel32", use_last_error=True)
    _win.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _win.CreateFileW.restype = wintypes.HANDLE
    _win.CloseHandle.argtypes = [wintypes.HANDLE]
    _win.CloseHandle.restype = wintypes.BOOL
    _win.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_FILEINFO)]
    _win.GetFileInformationByHandle.restype = wintypes.BOOL
    _win.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _win.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _win.GetFileType.argtypes = [wintypes.HANDLE]
    _win.GetFileType.restype = wintypes.DWORD
    _win.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _win.LockFileEx.restype = wintypes.BOOL
    _win.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _win.UnlockFileEx.restype = wintypes.BOOL
    _win.GetCurrentProcess.restype = wintypes.HANDLE
    _win.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                     ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                     wintypes.BOOL, wintypes.DWORD]
    _win.DuplicateHandle.restype = wintypes.BOOL


def _duplicate_sentinel(sentinel):
    if sys.platform != "win32":
        return os.dup(sentinel)
    duplicate = wintypes.HANDLE()
    current = _win.GetCurrentProcess()
    if not _win.DuplicateHandle(current, sentinel, current, ctypes.byref(duplicate), 0, False, 2):
        raise ctypes.WinError(ctypes.get_last_error())
    return duplicate.value


def _close_sentinel(sentinel):
    if sys.platform == "win32":
        _win.CloseHandle(sentinel)
    else:
        os.close(sentinel)


class _Handle:
    def __init__(self, path: Path, *, directory=False, lock=False, create=False):
        self.raw = None
        self.locked = False
        self.path = path
        if sys.platform == "win32":
            access = 0xC0000000 if lock else 0x80  # GENERIC_RW / FILE_READ_ATTRIBUTES
            share = 3 if lock else 7
            flags = 0x00200000 | (0x02000000 if directory else 0)  # OPEN_REPARSE_POINT/BACKUP_SEMANTICS
            raw = _win.CreateFileW(str(path), access, share, None, 4 if lock else (1 if create else 3), flags, None)
            if raw == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            self.raw = raw
            self.overlapped = _OVERLAPPED()
            try:
                info = _FILEINFO()
                if not _win.GetFileInformationByHandle(raw, ctypes.byref(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if _win.GetFileType(raw) != 1:
                    raise AdmissionError("Admission resource must be a disk file")
                if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
                    raise AdmissionError("Admission resource has unexpected type or redirection")
                identity = _FILE_ID_INFO()
                if not _win.GetFileInformationByHandleEx(raw, 18, ctypes.byref(identity), ctypes.sizeof(identity)):
                    raise AdmissionError("Native Windows128-bit file identity is unavailable")
                self.identity = (int(identity.volume), int.from_bytes(identity.identifier, "little"))
            except BaseException:
                self.close()
                raise
        else:
            flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
            if directory:
                flags |= os.O_DIRECTORY
            if lock:
                flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
            elif create:
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            self.raw = os.open(path, flags, 0o600)
            try:
                info = os.fstat(self.raw)
                if (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode)):
                    raise AdmissionError("Admission resource has unexpected type")
                if lock and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                    raise AdmissionError("Admission lock must be private and user-owned")
                self.identity = (int(info.st_dev), int(info.st_ino))
            except BaseException:
                self.close()
                raise
        if not self.identity[1] or (sys.platform == "win32" and not self.identity[0]):
            self.close()
            raise AdmissionError("Cannot establish physical file identity")

    def acquire(self):
        if sys.platform == "win32":
            if not _win.LockFileEx(self.raw, 3, 0, 1, 0, ctypes.byref(self.overlapped)):
                error = ctypes.get_last_error()
                if error in (32, 33, 158):
                    raise LibraryInUseError("Library already in use; close the other application and retry")
                raise ctypes.WinError(error)
        else:
            import fcntl
            try:
                fcntl.flock(self.raw, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LibraryInUseError("Library already in use; close the other application and retry") from exc
        self.locked = True

    def close(self, *, inherited=False):
        if self.raw is None:
            return
        raw, self.raw = self.raw, None
        if sys.platform == "win32":
            if self.locked and not inherited:
                _win.UnlockFileEx(raw, 0, 1, 0, ctypes.byref(self.overlapped))
            _win.CloseHandle(raw)
        else:
            # Closing an inherited fd must NEVER explicitly unlock the shared OFD.
            try:
                os.close(raw)
            except OSError:
                if not inherited:
                    raise
        self.locked = False


_manager_lock = threading.RLock()
_owners: dict[tuple[str, str], "_AdmissionSession"] = {}


class _AdmissionSession:
    """Retained native owner; call ready() after new-file initialization.

    destination=True reserves an absent restore name. pin_stage()/bind_published()
    keep physical ownership across existing atomic recovery publication.
    """
    def __init__(self, path: Path, *, create=False, destination=False, _registry_path=None):
        self.pid = os.getpid()
        self.path = Path(path).resolve(strict=False)
        self.registry = _registry(Path(_registry_path) if _registry_path is not None else registry_path())
        self.handles = []
        self.references = 1
        self.closed = False
        self.released = threading.Event()
        self.owned_processes = []
        self.cleanup_failures = []
        self.coordinator_claimed = False
        self.coordinator_closing = False
        self.untracked_children = 0
        self.file = None
        self.gate = None
        self.destination = destination
        self.created = False
        try:
            self.parent = self._pin(self.path.parent, directory=True)
            self.gate = self._lock("directory", self.parent.identity)
            leaf = (self.path.name.encode("utf-16le", "surrogatepass") if sys.platform == "win32"
                    else os.fsencode(self.path.name))
            self._lock("path", self.parent.identity, leaf)
            if destination:
                if self.path.exists() or self.path.is_symlink():
                    raise FileExistsError("Restore destination already exists")
            else:
                try:
                    self.file = self._pin(self.path)
                except FileNotFoundError:
                    if not create:
                        raise
                    self.file = self._pin(self.path, create=True)
                    self.created = True
                self._lock("file", self.file.identity)
                self.validate()
                if not self.created:
                    self.ready()
        except BaseException:
            self._close()
            raise

    def _pin(self, path, **kwargs):
        handle = _Handle(path, **kwargs)
        self.handles.append(handle)
        return handle

    def _lock(self, kind, identity, leaf=b""):
        filename = hashlib.sha256(key_bytes(kind, identity, leaf)).hexdigest() + ".lock"
        handle = self._pin(self.registry / filename, lock=True)
        handle.acquire()
        return handle

    def validate(self):
        if self.closed or self.pid != os.getpid():
            raise AdmissionError("Library ownership is no longer valid in this process")
        with _checked_handle(self.path.parent, directory=True) as parent:
            if parent.identity != self.parent.identity:
                raise AdmissionError("Library parent changed; close this library and reopen")
        if self.file is not None and not self.destination:
            with _checked_handle(self.path) as current:
                if current.identity != self.file.identity:
                    raise AdmissionError("Library file changed; close this library and reopen")
        elif self.destination and self.path.exists():
            raise AdmissionError("Restore destination is no longer absent")
        return self

    def ready(self):
        with _manager_lock:
            self.validate()
            if self.gate is not None:
                self.gate.close()
                self.gate = None
            return self

    def pin_stage(self, stage: Path):
        with _manager_lock:
            if not self.destination or self.file is not None:
                raise AdmissionError("No unbound restore destination ownership")
            self.validate()
            self.file = self._pin(Path(stage))
            self._lock("file", self.file.identity)

    def bind_published(self):
        with _manager_lock:
            if not self.destination or self.file is None:
                raise AdmissionError("Restore has no pinned publication stage")
            with _checked_handle(self.path) as final:
                if final.identity != self.file.identity:
                    raise AdmissionError("Published restore identity differs from pinned stage")
            self.destination = False
            self.ready()

    def retain(self):
        with _manager_lock:
            self.validate()
            self.references += 1
        return self

    def release(self):
        with _manager_lock:
            if self.closed:
                return
            if self.pid != os.getpid():
                raise AdmissionError("Cannot release another process's ownership")
            self.references -= 1
            if self.references == 0:
                self._close()
                for key, owner in list(_owners.items()):
                    if owner is self:
                        del _owners[key]

    def claim_coordinator(self):
        """One independent GUI job coordinator per participating session."""
        with _manager_lock:
            self.validate()
            if self.coordinator_claimed:
                raise LibraryInUseError("Library already has an open window; use or close that window")
            self.coordinator_claimed = True
            self.references += 1
        return self

    def release_coordinator(self):
        with _manager_lock:
            if self.coordinator_claimed:
                self.coordinator_closing = True
                self._finish_coordinator()

    def _finish_coordinator(self):
        if self.coordinator_closing and not self.untracked_children and not any(not r["done"] for r in self.owned_processes):
            self.coordinator_claimed = False
            self.coordinator_closing = False
            self.release()

    def retain_process(self, process):
        """Hold ownership until an already-started owned process actually exits."""
        with _manager_lock:
            # Cleanup ownership must survive stale catalog identity: stale owners
            # reject new work, but still own the children they already started.
            if self.closed or self.pid != os.getpid():
                raise AdmissionError("Cannot retain cleanup for a closed/foreign owner")
            self.references += 1
            try:
                sentinel = _duplicate_sentinel(process.sentinel)
            except BaseException as exc:
                self.untracked_children += 1
                self.cleanup_failures.append(f"Cannot retain owned process exit handle: {type(exc).__name__}")
                # Fail closed: the cleanup reference is not dropped on uncertainty.
                raise
            record = {"sentinel": sentinel, "done": False, "lock": threading.Lock(), "waiter": None}
            self.owned_processes.append(record)
            try:
                record["waiter"] = _duplicate_sentinel(sentinel)
            except BaseException as exc:
                self.cleanup_failures.append(f"Cannot duplicate reaper exit handle: {type(exc).__name__}")
                raise
            def reap():
                # Multiprocessing Process.join/is_alive are not safe to race with
                # caller join/close. A duplicated kernel sentinel is an exit oracle.
                from multiprocessing.connection import wait
                try:
                    wait([record["waiter"]])
                    self._finish_process(record)
                except BaseException as exc:
                    self.cleanup_failures.append(f"Owned process exit wait failed: {type(exc).__name__}")
                finally:
                    with _manager_lock:
                        _close_sentinel(record["waiter"])
                        record["waiter"] = None
                        if record["done"] and record in self.owned_processes:
                            self.owned_processes.remove(record)
            thread = threading.Thread(target=reap, name="library-owned-process", daemon=True)
            try:
                thread.start()
            except BaseException as exc:
                _close_sentinel(record["waiter"])
                record["waiter"] = None
                self.cleanup_failures.append(f"Owned process reaper did not start: {type(exc).__name__}")
                # Keep the ref and duplicated sentinel. Explicit bounded reaping can
                # recover it later; never release a live child's cleanup ownership.
                raise

    def _finish_process(self, record):
        with _manager_lock:
            with record["lock"]:
                if not record["done"]:
                    record["done"] = True
                    _close_sentinel(record["sentinel"])
                    self.release()
                    self._finish_coordinator()
                    if record["waiter"] is None and record in self.owned_processes:
                        self.owned_processes.remove(record)

    def reap_owned_processes(self):
        """Nonblocking recovery if a reaper could not start or its wait failed."""
        from multiprocessing.connection import wait
        with _manager_lock:
            records = tuple(self.owned_processes)
        for record in records:
            with record["lock"]:
                ready = not record["done"] and bool(wait([record["sentinel"]], timeout=0))
            if ready:
                self._finish_process(record)
        with _manager_lock:
            return self.untracked_children + sum(not record["done"] for record in self.owned_processes)

    def _close(self, *, inherited=False):
        if self.closed:
            return
        self.closed = True
        for handle in reversed(self.handles):
            handle.close(inherited=inherited)
        if inherited:
            for record in self.owned_processes:
                if not record["done"]:
                    try:
                        _close_sentinel(record["sentinel"])
                    except OSError:
                        pass
                if record["waiter"] is not None:
                    try:
                        _close_sentinel(record["waiter"])
                    except OSError:
                        pass
        self.released.set()


@contextmanager
def _checked_handle(path, **kwargs):
    handle = _Handle(path, **kwargs)
    try:
        yield handle
    finally:
        handle.close()


@contextmanager
def admission_session(path: Path, *, create=False, destination=False, _registry_path=None):
    """Opt in to application coordination around a whole Core operation."""
    canonical = Path(path).resolve(strict=False)
    registry = Path(_registry_path) if _registry_path is not None else registry_path()
    key = (str(registry), str(canonical))
    with _manager_lock:
        owner = _owners.get(key)
        if owner is not None:
            if create or destination:
                raise AdmissionError("Cannot borrow an existing session for creation or restore")
            owner.retain()
        else:
            owner = _AdmissionSession(canonical, create=create, destination=destination, _registry_path=registry)
            _owners[key] = owner
    try:
        yield owner
    finally:
        owner.release()


def current_session(path: Path):
    """Return a validated same-process owner if this operation participates."""
    canonical = Path(path).resolve(strict=False)
    with _manager_lock:
        for owner in _owners.values():
            if owner.path == canonical and owner.pid == os.getpid() and not owner.closed:
                return owner.validate()
    return None


def _after_fork():
    global _manager_lock
    for owner in tuple(_owners.values()):
        owner._close(inherited=True)
    _owners.clear()
    _manager_lock = threading.RLock()


def _before_fork():
    _manager_lock.acquire()


def _after_fork_parent():
    _manager_lock.release()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(before=_before_fork, after_in_parent=_after_fork_parent,
                        after_in_child=_after_fork)
