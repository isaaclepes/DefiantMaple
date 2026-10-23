"""Scheduled-snapshot state foundations; no timers, backup or deletion entrypoint.

The caller supplies admitted generated/real library ownership and explicitly
chosen private directories. Importing this module never accesses user settings.
"""
from contextlib import ExitStack, closing, contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import stat
import uuid

from .admission import _Handle, _checked_handle, current_session
from .catalog import library_identity, validate_library_id
from .recovery_storage import private_local_parent


class ScheduleError(ValueError):
    pass


class StateUncertainError(ScheduleError):
    """A state name may have been published; stop and reconcile before retry."""


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ScheduleError("Unsupported scheduled snapshot document fields")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ScheduleError("Invalid scheduled snapshot integer")
    return value


def _uuid(value):
    if type(value) is not str:
        raise ScheduleError("Invalid schedule identity")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ScheduleError("Invalid schedule identity") from exc
    if str(parsed) != value or parsed.version != 4:
        raise ScheduleError("Invalid schedule identity")
    return value


def _path(value):
    if type(value) is not str or len(os.fsencode(value)) > 32768 or "\0" in value:
        raise ScheduleError("Invalid schedule path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ScheduleError("Schedule path must be absolute and normalized")
    return value


def _identity(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ScheduleError("Invalid native schedule identity")
    return (_integer(value[0], 1, 2**64 - 1), _integer(value[1], 1, 2**128 - 1))


@dataclass(frozen=True)
class Binding:
    catalog_path: str
    parent_identity: tuple[int, int]
    file_identity: tuple[int, int]
    library_id: str
    directory_path: str
    directory_identity: tuple[int, int]

    def __post_init__(self):
        _path(self.catalog_path)
        _path(self.directory_path)
        try:
            validate_library_id(self.library_id)
        except ValueError as exc:
            raise ScheduleError("Invalid bound library identity") from exc
        for name in ("parent_identity", "file_identity", "directory_identity"):
            object.__setattr__(self, name, _identity(getattr(self, name)))

    @classmethod
    def capture(cls, owner, directory):
        if current_session(owner.path) is not owner:
            raise ScheduleError("An active in-process admission session is required")
        owner.validate()
        directory = Path(directory)
        _path(str(directory))
        with _checked_handle(directory, directory=True) as handle:
            with closing(sqlite3.connect(owner.path.as_uri() + "?mode=ro", uri=True)) as db:
                identity = library_identity(db)
            result = cls(str(owner.path), owner.parent.identity, owner.file.identity,
                         identity, str(directory), handle.identity)
        owner.validate()
        return result

    def validate(self, owner):
        if Binding.capture(owner, self.directory_path) != self:
            raise ScheduleError("Library or managed directory changed; configure this location explicitly")


@dataclass(frozen=True)
class Policy:
    enabled: bool = False
    interval_seconds: int = 86400
    retention_enabled: bool = False
    keep_count: int | None = 10
    byte_limit: int | None = None

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.retention_enabled) is not bool:
            raise ScheduleError("Invalid schedule policy flags")
        _integer(self.interval_seconds, 900, 30 * 86400)
        if self.keep_count is not None:
            _integer(self.keep_count, 1, 1000)
        if self.byte_limit is not None:
            _integer(self.byte_limit, 2**20, 2**40)
        if self.keep_count is None and self.byte_limit is None:
            raise ScheduleError("A bounded storage policy is required")


@dataclass(frozen=True)
class Locator:
    schedule_id: str
    revision: int
    binding: Binding

    def __post_init__(self):
        _uuid(self.schedule_id)
        _integer(self.revision, 1, 2**63 - 1)
        if type(self.binding) is not Binding:
            raise ScheduleError("Invalid locator binding")


@dataclass(frozen=True)
class ConfigurationTransition:
    locator: Locator
    operation_id: str
    phase: str

    def __post_init__(self):
        if type(self.locator) is not Locator or type(self.phase) is not str or self.phase not in {"pending", "committed"}:
            raise ScheduleError("Invalid configuration transition")
        _uuid(self.operation_id)


@dataclass(frozen=True)
class PhaseStatus:
    # Separate last verified success from a later pruning/cleanup warning.
    last_attempt_utc: int | None = None
    last_success_utc: int | None = None
    outcome: str = "never"
    cleanup_pending: bool = False

    def __post_init__(self):
        for value in (self.last_attempt_utc, self.last_success_utc):
            if value is not None:
                _integer(value, 0, 253402300799)
        if type(self.cleanup_pending) is not bool:
            raise ScheduleError("Invalid cleanup state")
        if type(self.outcome) is not str or self.outcome not in {"never", "in_progress", "verified", "failed",
                                "canceled", "uncertain", "cleanup_warning", "interrupted", "reconciled"}:
            raise ScheduleError("Invalid schedule outcome")
        if self.outcome in {"verified", "cleanup_warning"} and self.last_success_utc is None:
            raise ScheduleError("Verified outcome requires a success record")


@dataclass(frozen=True)
class PackageRecord:
    schedule_id: str
    sequence: int
    operation_id: str
    leaf: str
    file_identity: tuple[int, int]
    size: int
    sha256: str
    verified_utc: int

    def __post_init__(self):
        _uuid(self.schedule_id)
        _uuid(self.operation_id)
        _integer(self.sequence, 1, 2**63 - 1)
        if self.leaf != f"snapshot-{self.schedule_id}-{self.sequence}-{self.operation_id}.dmbackup":
            raise ScheduleError("Package leaf does not match managed identity")
        object.__setattr__(self, "file_identity", _identity(self.file_identity))
        _integer(self.size, 1, 16 * 2**30 + 65536 + 20)
        if type(self.sha256) is not str or not re.fullmatch("[0-9a-f]{64}", self.sha256):
            raise ScheduleError("Invalid package digest")
        _integer(self.verified_utc, 0, 253402300799)


@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    operation_id: str
    revision: int
    utc: int
    event: str
    package: PackageRecord | None = None
    survivor: PackageRecord | None = None
    error_code: str | None = None

    def __post_init__(self):
        for value in (self.sequence, self.revision):
            _integer(value, 1, 2**63 - 1)
        _uuid(self.operation_id)
        _integer(self.utc, 0, 253402300799)
        if type(self.event) is not str or self.event not in {"configured", "attempt_started", "published", "verified", "delete_intent", "deleted", "failed", "canceled", "uncertain", "cleanup_warning", "reconciled"}:
            raise ScheduleError("Invalid schedule audit event")
        for record in (self.package, self.survivor):
            if record is not None and type(record) is not PackageRecord:
                raise ScheduleError("Invalid audit package facts")
        if self.event in {"published", "verified", "delete_intent", "deleted"} and self.package is None:
            raise ScheduleError("Audit event requires package facts")
        if self.event == "delete_intent" and (self.survivor is None or self.survivor.sequence <= self.package.sequence):
            raise ScheduleError("Deletion intent requires a newer survivor")
        if self.error_code is not None and (type(self.error_code) is not str or not re.fullmatch("[a-z][a-z0-9_]{0,63}", self.error_code)):
            raise ScheduleError("Invalid audit error code")


@dataclass(frozen=True)
class ScheduleState:
    locator: Locator
    policy: Policy = Policy()
    status: PhaseStatus = PhaseStatus()
    next_sequence: int = 1
    packages: tuple[PackageRecord, ...] = ()
    audit: tuple[AuditRecord, ...] = ()
    last_success: PackageRecord | None = None

    def __post_init__(self):
        if type(self.locator) is not Locator or type(self.policy) is not Policy or type(self.status) is not PhaseStatus:
            raise ScheduleError("Invalid schedule state types")
        _integer(self.next_sequence, 1, 2**63 - 1)
        for name, records, kind, limit in (("packages", self.packages, PackageRecord, 1024), ("audit", self.audit, AuditRecord, 4096)):
            if not isinstance(records, (list, tuple)) or len(records) > limit or any(type(r) is not kind for r in records):
                raise ScheduleError("Schedule ledger/audit bound or type invalid")
            object.__setattr__(self, name, tuple(records))
            sequences = [r.sequence for r in records]
            if sequences != sorted(set(sequences)):
                raise ScheduleError("Schedule ledger/audit sequences must be strictly ordered")
        if any(p.schedule_id != self.locator.schedule_id or p.sequence >= self.next_sequence for p in self.packages):
            raise ScheduleError("Package ledger belongs to a different schedule/sequence")
        if len({p.operation_id for p in self.packages}) != len(self.packages):
            raise ScheduleError("Duplicate package operation identity")
        for event in self.audit:
            if event.revision > self.locator.revision or any(p is not None and p.schedule_id != self.locator.schedule_id for p in (event.package, event.survivor)):
                raise ScheduleError("Audit belongs to a different schedule/revision")
        if self.last_success is not None and (type(self.last_success) is not PackageRecord or self.last_success not in self.packages or self.last_success.verified_utc != self.status.last_success_utc):
            raise ScheduleError("Last success must reference its exact recorded package")
        if self.status.last_success_utc is not None and self.last_success is None:
            raise ScheduleError("Saved success timestamp requires package facts")


def locator_leaf(canonical_catalog: Path) -> str:
    spelling = _path(str(canonical_catalog))
    raw = spelling.encode("utf-16le", "surrogatepass") if os.name == "nt" else os.fsencode(spelling)
    return hashlib.sha256(b"dm-schedule-locator-v1\n" + raw).hexdigest() + ".json"


def locator_directory(application_data_root: Path) -> Path:
    return Path(_path(str(application_data_root))) / "scheduled-snapshots-v1"


def encode_document(value) -> bytes:
    if type(value) is ScheduleState:
        document = {"schema": "defiantmaple.schedule-state.v1", **asdict(value)}
    elif type(value) is Locator:
        document = {"schema": "defiantmaple.schedule-locator.v1", **asdict(value)}
    elif type(value) is ConfigurationTransition:
        document = {"schema": "defiantmaple.schedule-transition.v1", **asdict(value)}
    else:
        raise ScheduleError("Unsupported schedule document")
    raw = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
    if len(raw) > (65536 if type(value) is Locator else 131072 if type(value) is ConfigurationTransition else 4 * 2**20):
        raise ScheduleError("Schedule document exceeds its bound")
    return raw


def decode_document(raw: bytes, *, locator=False, transition=False):
    if locator and transition:
        raise ScheduleError("Conflicting document kinds")
    if type(raw) is not bytes or len(raw) > (65536 if locator else 131072 if transition else 4 * 2**20):
        raise ScheduleError("Schedule document exceeds its bound")
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ScheduleError("Duplicate schedule document key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ScheduleError("Nonfinite schedule value")))
        if transition:
            _fields(value, ("schema", "locator", "operation_id", "phase"))
            if value["schema"] != "defiantmaple.schedule-transition.v1":
                raise ScheduleError("Unsupported configuration transition version")
            loc = value["locator"]
            _fields(loc, ("schedule_id", "revision", "binding"))
        elif locator:
            _fields(value, ("schema", "schedule_id", "revision", "binding"))
            if value["schema"] != "defiantmaple.schedule-locator.v1":
                raise ScheduleError("Unsupported schedule locator version")
            loc = value
        else:
            _fields(value, ("schema", "locator", "policy", "status", "next_sequence", "packages", "audit", "last_success"))
            if value["schema"] != "defiantmaple.schedule-state.v1":
                raise ScheduleError("Unsupported schedule state version")
            loc = value["locator"]
            _fields(loc, ("schedule_id", "revision", "binding"))
        _fields(loc["binding"], Binding.__dataclass_fields__)
        result = Locator(loc["schedule_id"], loc["revision"], Binding(**loc["binding"]))
        if locator:
            return result
        if transition:
            return ConfigurationTransition(result, value["operation_id"], value["phase"])
        _fields(value["policy"], Policy.__dataclass_fields__)
        _fields(value["status"], PhaseStatus.__dataclass_fields__)
        if type(value["packages"]) is not list or len(value["packages"]) > 1024 or type(value["audit"]) is not list or len(value["audit"]) > 4096:
            raise ScheduleError("Schedule ledger/audit exceeds its bound")
        def package(raw):
            _fields(raw, PackageRecord.__dataclass_fields__)
            return PackageRecord(**raw)
        packages = tuple(package(p) for p in value["packages"])
        audit = []
        for raw in value["audit"]:
            _fields(raw, AuditRecord.__dataclass_fields__)
            audit.append(AuditRecord(**{**raw, "package": None if raw["package"] is None else package(raw["package"]),
                                       "survivor": None if raw["survivor"] is None else package(raw["survivor"])}))
        return ScheduleState(result, Policy(**value["policy"]), PhaseStatus(**value["status"]), value["next_sequence"], packages, tuple(audit), None if value["last_success"] is None else package(value["last_success"]))
    except (UnicodeError, json.JSONDecodeError, TypeError, KeyError, RecursionError) as exc:
        raise ScheduleError("Malformed schedule document") from exc


@dataclass(frozen=True)
class Version:
    identity: tuple[int, int]
    sha256: str


class LockedDirectory:
    """Explicit existing qualified directory; lifetime pins native lock and fd.

    Caller lock ordering is locator then managed directory, see locked_stores.
    No target deletion or automatic profile/directory creation is implemented.
    """
    def __init__(self, directory, lock_leaf):
        self.directory = Path(directory)
        self.lock_leaf = lock_leaf
        self._stack = ExitStack()
        self.fd = None

    def __enter__(self):
        _leaf(self.lock_leaf)
        try:
            _, self.fd = self._stack.enter_context(private_local_parent(self.directory / self.lock_leaf))
            self.identity = _stat_identity(os.fstat(self.fd))
            self.lock = _Handle(self.directory / self.lock_leaf, lock=True)
            self._stack.callback(self.lock.close)
            lock_info = os.fstat(self.lock.raw)
            _private_regular(lock_info)
            if lock_info.st_size:
                raise ScheduleError("Permanent schedule lock must be empty")
            self.lock.acquire()
            self.validate()
            return self
        except BaseException:
            self._stack.close()
            self.fd = None
            raise

    def __exit__(self, *args):
        self._stack.close()
        self.fd = None

    def validate(self):
        if self.fd is None:
            raise ScheduleError("Schedule directory is not locked")
        _private_directory(os.fstat(self.fd))
        with _checked_handle(self.directory, directory=True) as current:
            _private_directory(os.fstat(current.raw))
            if current.identity != self.identity:
                raise ScheduleError("Schedule directory changed")
        # Recheck the lexical ancestors as well as the pinned and named leaf;
        # private permissions at entry do not authorize later unsafe operations.
        with private_local_parent(self.directory / self.lock_leaf):
            pass
        pinned = os.fstat(self.lock.raw)
        _private_regular(pinned)
        if pinned.st_size:
            raise ScheduleError("Permanent schedule lock must remain empty")
        with _checked_handle(self.directory / self.lock_leaf) as current:
            named = os.fstat(current.raw)
            _private_regular(named)
            if named.st_size:
                raise ScheduleError("Permanent schedule lock must remain empty")
            if current.identity != self.lock.identity:
                raise ScheduleError("Permanent schedule lock changed")

    def names(self, *, limit=1026):
        """Fresh native directory description per bounded inventory, never dup.

        A retained directory description can cache enumeration state while state
        and package names are published/replaced. Open '.' relative to the pin
        and authenticate both descriptions before and after each fresh scan.
        """
        _integer(limit, 1, 1026)
        self.validate()
        descriptor = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            def validate_scan():
                for info in (os.fstat(self.fd), os.fstat(descriptor)):
                    _private_directory(info)
                    if _stat_identity(info) != self.identity:
                        raise ScheduleError('Inventory directory differs from its native pin')
            validate_scan()
            names = []
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) > limit:
                        raise ScheduleError('Managed directory inventory exceeds its bound')
            validate_scan()
            self.validate()
            return tuple(names)
        finally:
            os.close(descriptor)

    def read(self, leaf, *, locator=False, transition=False):
        _leaf(leaf)
        if leaf == self.lock_leaf:
            raise ScheduleError("Permanent schedule lock is not a state document")
        self.validate()
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None, None
        try:
            before = os.fstat(fd)
            limit = 65536 if locator else 131072 if transition else 4 * 2**20
            _private_regular(before)
            if before.st_size > limit:
                raise ScheduleError("Schedule document exceeds its bound")
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(fd)
            _private_regular(after)
            named = os.stat(leaf, dir_fd=self.fd, follow_symlinks=False)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, _stat_identity(before)) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, _stat_identity(after)) or _stat_identity(named) != _stat_identity(before):
                raise ScheduleError("Schedule document changed while reading")
            document = decode_document(raw, locator=locator, transition=transition)
            expected_leaf = (locator_leaf(Path(document.locator.binding.catalog_path)) + ".transition") if transition else locator_leaf(Path(document.binding.catalog_path)) if locator else "schedule.json"
            if leaf != expected_leaf:
                raise ScheduleError("Schedule document is stored under the wrong key")
            return document, Version(_stat_identity(before), hashlib.sha256(raw).hexdigest())
        finally:
            os.close(fd)

    def write(self, leaf, value, expected):
        _leaf(leaf)
        locator = type(value) is Locator
        transition = type(value) is ConfigurationTransition
        expected_leaf = (locator_leaf(Path(value.locator.binding.catalog_path)) + ".transition") if transition else locator_leaf(Path(value.binding.catalog_path)) if locator else "schedule.json"
        if leaf != expected_leaf or leaf == self.lock_leaf:
            raise ScheduleError("State document does not match its schedule leaf")
        raw = encode_document(value)
        _, current = self.read(leaf, locator=locator, transition=transition)
        if current != expected:
            raise ScheduleError("Schedule document changed; reload before updating")
        stage = ".schedule-" + uuid.uuid4().hex + ".stage"
        fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        stage_identity, published = _stat_identity(os.fstat(fd)), False
        try:
            data = memoryview(raw)
            while data:
                written = os.write(fd, data)
                if written <= 0:
                    raise OSError("Schedule state write made no progress")
                data = data[written:]
            os.fsync(fd)
            self.validate()
            _, current = self.read(leaf, locator=locator, transition=transition)
            if current != expected:
                raise ScheduleError("Schedule document changed before publication")
            if expected is None:
                os.link(stage, leaf, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            else:
                os.replace(stage, leaf, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            published = True
            if expected is None:
                os.unlink(stage, dir_fd=self.fd)
            os.fsync(self.fd)
            document, version = self.read(leaf, locator=locator, transition=transition)
            expected_version = Version(stage_identity, hashlib.sha256(raw).hexdigest())
            if document != value or version != expected_version:
                raise StateUncertainError("Published schedule state changed; reconcile before retry")
            return version
        except BaseException as exc:
            if published:
                raise StateUncertainError("Schedule state may be published; reconcile before retry") from exc
            raise
        finally:
            os.close(fd)
            # Once published, retain any leftover stage for reconciliation.
            # A second cleanup failure must not mask publication uncertainty.
            if not published:
                try:
                    candidate = os.stat(stage, dir_fd=self.fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if _stat_identity(candidate) == stage_identity:
                        os.unlink(stage, dir_fd=self.fd)


def _leaf(value):
    if type(value) is not str or not value or len(value) > 255 or value in {".", ".."} or "/" in value or "\\" in value or "\0" in value:
        raise ScheduleError("Invalid schedule leaf")


def _stat_identity(info):
    return info.st_dev, info.st_ino


def _private_regular(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
        raise ScheduleError("Schedule state must be a private owned regular file")


def _private_directory(info):
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ScheduleError("Schedule directory must remain private and user-owned")


@contextmanager
def locked_stores(locator_root, locator_name, managed_directory):
    _leaf(locator_name)
    with LockedDirectory(locator_root, locator_name + ".lock") as locators:
        with LockedDirectory(managed_directory, "schedule.lock") as managed:
            yield locators, managed


def validate_pair(locator, state, owner):
    if type(locator) is not Locator or type(state) is not ScheduleState or locator != state.locator:
        raise ScheduleError("Schedule configuration revision/binding mismatch; reconcile explicitly")
    locator.binding.validate(owner)
    return state


class DueState:
    """Clock-injected one-active/one-pending intent state; never launches work."""
    def __init__(self, policy, status, *, utc, monotonic):
        if type(policy) is not Policy or type(status) is not PhaseStatus:
            raise ScheduleError("Invalid scheduler state")
        self.policy, self.status = policy, status
        self.utc, self.monotonic = utc, monotonic
        self.active = self.pending = False
        wall, now = self._clocks()
        self.clock_changed = status.last_attempt_utc is not None and wall < status.last_attempt_utc
        self.interrupted = status.outcome == "in_progress"
        self.suspended = self.interrupted or status.cleanup_pending or status.outcome in {"uncertain", "cleanup_warning"}
        remaining = 0 if status.last_attempt_utc is None else max(0, policy.interval_seconds - (wall - status.last_attempt_utc))
        self.deadline = now + (policy.interval_seconds if self.clock_changed else remaining)
        self._anchor = self.deadline - policy.interval_seconds
        self._last_monotonic = now

    def _clocks(self):
        values = self.utc(), self.monotonic()
        if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in values):
            raise ScheduleError("Invalid scheduler clock")
        return values

    def poll(self, *, recovery_idle=True):
        _, now = self._clocks()
        if now < self._last_monotonic:
            self.suspended = True
            raise ScheduleError("Monotonic clock moved backwards")
        self._last_monotonic = now
        if not self.policy.enabled or self.suspended:
            return False
        if now >= self.deadline:
            self.pending = True
        return self.pending and not self.active and recovery_idle

    def start(self, *, manual=False, recovery_idle=True):
        if self.suspended or self.active or not recovery_idle or not self.policy.enabled:
            raise ScheduleError("Schedule cannot start while disabled, busy or suspended")
        if not manual and not self.poll(recovery_idle=recovery_idle):
            raise ScheduleError("Schedule is not due")
        wall, _ = self._clocks()
        self.active, self.pending = True, False
        self.status = PhaseStatus(int(wall), self.status.last_success_utc, "in_progress")

    def finish(self, outcome, *, verified_utc=None, cleanup_complete=True):
        if not self.active:
            raise ScheduleError("No schedule operation is active")
        if outcome not in {"verified", "failed", "canceled", "uncertain", "cleanup_warning"}:
            raise ScheduleError("Invalid completion outcome")
        if type(cleanup_complete) is not bool or (outcome == "verified" and verified_utc is None):
            raise ScheduleError("Completion requires explicit verification and cleanup facts")
        wall, now = self._clocks()
        success = self.status.last_success_utc if verified_utc is None else _integer(verified_utc, 0, 253402300799)
        self.status = PhaseStatus(int(wall), success, outcome, not cleanup_complete)
        self.active, self.pending = not cleanup_complete, False
        self.suspended = outcome in {"uncertain", "cleanup_warning"} or not cleanup_complete
        self.deadline = now + self.policy.interval_seconds
        self._anchor = now

    def reconfigure(self, policy):
        if type(policy) is not Policy:
            raise ScheduleError("Invalid schedule policy")
        self.policy, self.pending = policy, False
        if not self.active:
            _, now = self._clocks()
            self.deadline = now if self.status.last_attempt_utc is None else self._anchor + policy.interval_seconds

    def request_cancel(self):
        self.pending = False
        return self.active  # Caller must keep ownership and await actual cleanup.

    def reconciled(self):
        if self.active:
            raise ScheduleError("Cannot reconcile while owned cleanup is active")
        self.suspended = self.interrupted = False
        self.status = PhaseStatus(self.status.last_attempt_utc, self.status.last_success_utc, "reconciled")
        _, now = self._clocks()
        self.deadline = now
        self._anchor = now - self.policy.interval_seconds
