"""Internal A2 managed-domain protocol, deliberately unwired and recovery-held.

Explicit private roots only; this module selects no real-account authority and
never deletes cache data. Unknown prior-owner reservations refuse. Production
writer/output/publication/platform integration remains a separate prerequisite.
"""
from dataclasses import dataclass
import hashlib
import json
import multiprocessing
from multiprocessing.process import BaseProcess
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time
import uuid

from .catalog import require_current_catalog, validate_library_id
from .thumbnail_budget import (BudgetPolicy, BudgetRefusal, ObservedUsage,
                               PinnedRoot, ProtectedAccountingRoot, admits, inventory)

CONTROL_LIMIT = 16 * 1024
RESERVATION = ObservedUsage(41 * 1024 ** 2, 8, 16)
EXTERNAL_CONTROLS = ObservedUsage(64 * 1024, 4, 4)
GATE = '.managed-admission-gate-v1'
AUTHORITY = '.managed-authority-v1.json'
DOMAIN = '.managed-domain-v1.json'
PENDING = '.managed-pending-v1.json'
_LIFETIME = threading.Lock()
_LIVE = set()


class AdmissionBusy(BudgetRefusal):
    pass


class RecoveryHeld(BudgetRefusal):
    pass


def _before_fork():
    _LIFETIME.acquire()


def _after_parent_fork():
    _LIFETIME.release()


def _after_child_fork():
    # close(), never LOCK_UN: copied descriptors share their parent's flock.
    for owner in tuple(_LIVE):
        owner._discard_inherited()
    _LIVE.clear()
    _LIFETIME.release()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(before=_before_fork, after_in_parent=_after_parent_fork,
                        after_in_child=_after_child_fork)


def _identity(info):
    return (info.st_dev, info.st_ino)


def _stable(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_uid, info.st_nlink)


def _canonical(data):
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    if len(raw) > CONTROL_LIMIT:
        raise BudgetRefusal('Managed control exceeds its bound')
    return raw


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BudgetRefusal('Duplicate managed control field')
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BudgetRefusal('Managed control schema is unknown or incomplete') from exc
    if type(result) is not dict:
        raise BudgetRefusal('Managed control must be an object')
    return result


@dataclass(frozen=True)
class LibraryAssociation:
    library_id: str
    catalog_path: str
    device: int
    inode: int

    def __post_init__(self):
        validate_library_id(self.library_id)
        if (type(self.catalog_path) is not str or '\x00' in self.catalog_path or not Path(self.catalog_path).is_absolute()
                or '..' in Path(self.catalog_path).parts
                or len(self.catalog_path.encode('utf-8')) > 4096):
            raise BudgetRefusal('Catalog association path is unsupported')
        if type(self.device) is not int or self.device < 0 or type(self.inode) is not int or self.inode <= 0:
            raise BudgetRefusal('Catalog association identity is unsupported')

    def record(self):
        return {'library_id': self.library_id, 'catalog_path': self.catalog_path,
                'catalog_device': self.device, 'catalog_inode': self.inode}


class _CaptureDescriptor:
    def __init__(self):
        self.fd = None

    def _discard_inherited(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def capture_association(database: Path) -> LibraryAssociation:
    """Read-only local-catalog capture; never original-media access or enrollment."""
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
        raise BudgetRefusal('Catalog association native capture is unsupported')
    canonical = Path(database).resolve(strict=True)
    owner = _CaptureDescriptor()
    with _LIFETIME:
        owner.fd = os.open(canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        _LIVE.add(owner)
    try:
        before = os.fstat(owner.fd)
        if not stat.S_ISREG(before.st_mode):
            raise BudgetRefusal('Catalog association requires an ordinary file')
        db = sqlite3.connect(canonical.as_uri() + '?mode=ro', uri=True, timeout=.25)
        try:
            identity = require_current_catalog(db)
        finally:
            db.close()
        if _identity(before) != _identity(canonical.stat()) or _identity(before) != _identity(os.fstat(owner.fd)):
            raise BudgetRefusal('Catalog changed during association capture')
        return LibraryAssociation(identity, str(canonical), before.st_dev, before.st_ino)
    finally:
        with _LIFETIME:
            if owner.fd is not None:
                os.close(owner.fd)
                owner.fd = None
            _LIVE.discard(owner)


@dataclass
class _Control:
    root: PinnedRoot
    name: str
    fd: int
    identity: tuple
    expected: bytes
    metadata: tuple


class ManagedOperation:
    """Explicit operation ownership; finish()/rollback_known() is mandatory.

    No root is created/adopted by this API. It pins two supplied private roots,
    uses permanent zero-byte gates, binds a new empty managed domain, and creates
    one durable pending control. All data writes remain the future caller's
    responsibility. Context exit closes handles, never silently reclaims data.
    Bootstrap callers may require a captured newly created managed identity;
    then existing namespaces are usable only with an already matching binding.
    """
    def __init__(self, authority_path: Path, managed_path: Path, association: LibraryAssociation,
                 *, policy: BudgetPolicy = BudgetPolicy(), cancel_event=None, wait_seconds=.5,
                 accounting_parent: Path | None = None,
                 require_created_or_bound=False, created_managed_identity=None):
        if os.name != 'posix' or not hasattr(os, 'register_at_fork'):
            raise BudgetRefusal('Managed admission native adapter is unsupported')
        if type(association) is not LibraryAssociation or type(policy) is not BudgetPolicy:
            raise BudgetRefusal('Managed admission requires typed association and policy')
        if type(wait_seconds) not in (int, float) or not 0 < wait_seconds <= 2:
            raise BudgetRefusal('Managed gate wait must be positive and at most two seconds')
        if not admits(ObservedUsage(0, 0, 0), EXTERNAL_CONTROLS, policy):
            raise BudgetRefusal('Policy cannot hold the bounded control allowance')
        self.authority_path, self.managed_path = Path(authority_path), Path(managed_path)
        self.accounting_path = None if accounting_parent is None else Path(accounting_parent)
        self.accounting = None
        self.require_created_or_bound = require_created_or_bound
        self.created_managed_identity = created_managed_identity
        self.association, self.policy = association, policy
        self.cancel_event, self.wait_seconds = cancel_event, wait_seconds
        self.owner_pid = os.getpid()
        self._fds = set()
        self._pins = []
        self._gates = []
        self._created = []
        self._captured_controls = {}
        self._children = []
        self._uncertain_start = False
        self._ready = False
        self._completed = False
        self._entered = False
        self._closed = False
        self._forked = False
        self.pending = None
        self.recovery_held = False
        self.token = str(uuid.uuid4())

    def _owner(self):
        if os.getpid() != self.owner_pid or self._forked:
            raise BudgetRefusal('Copied managed operation cannot be used after fork')
        if self._closed:
            raise BudgetRefusal('Managed operation is closed')

    def _pin(self, path, root_type=PinnedRoot):
        with _LIFETIME:
            root = root_type(path)
            self._pins.append(root)
            self._fds.update(root._handles)
            return root

    def _open(self, root, name, flags, mode=0o600):
        with _LIFETIME:
            descriptor = os.open(name, flags, mode, dir_fd=root.fd)
            self._fds.add(descriptor)
            return descriptor

    def _close_fd(self, descriptor):
        with _LIFETIME:
            self._fds.remove(descriptor)
            os.close(descriptor)

    def _discard_inherited(self):
        for descriptor in self._fds:
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._fds.clear()
        for root in self._pins:
            root._handles.clear()
        self._gates.clear()
        self._forked = True

    def _regular_control(self, descriptor):
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > CONTROL_LIMIT):
            raise BudgetRefusal('Managed control ownership/type/bound is unsafe')
        return info

    def _gate(self, root, *, create=True):
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT
        try:
            descriptor = self._open(root, GATE, flags)
        except FileNotFoundError as error:
            raise RecoveryHeld('Existing managed namespace has no recognized gate; adoption is refused') from error
        info = self._regular_control(descriptor)
        if info.st_size:
            raise BudgetRefusal('Managed gate is not an empty permanent file')
        self._gates.append((root, descriptor, _identity(info)))

    def _validate_gates(self):
        self._owner()
        if capture_association(Path(self.association.catalog_path)) != self.association:
            raise RecoveryHeld('Captured catalog association changed')
        for root, descriptor, identity in self._gates:
            root.validate()
            info = self._regular_control(descriptor)
            named = os.stat(GATE, dir_fd=root.fd, follow_symlinks=False)
            if info.st_size or _identity(info) != identity or _identity(named) != identity:
                raise BudgetRefusal('Managed gate identity changed')

    def _wait_gates(self):
        import fcntl
        identities = [gate[2] for gate in self._gates]
        if len(set(identities)) != len(identities):
            raise BudgetRefusal('Managed gates alias one physical file')
        deadline = time.monotonic() + self.wait_seconds
        for _, descriptor, _ in sorted(self._gates, key=lambda gate: gate[2]):
            while True:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    raise AdmissionBusy('Managed admission canceled before gate acquisition')
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise AdmissionBusy('Managed admission is busy')
                    if self.cancel_event is None:
                        time.sleep(.01)
                    else:
                        self.cancel_event.wait(.01)
        self._validate_gates()

    def _read(self, root, name):
        try:
            descriptor = self._open(root, name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if (root, name) in self._captured_controls:
                raise RecoveryHeld('Captured managed control disappeared')
            return None
        try:
            before = self._regular_control(descriptor)
            raw = os.read(descriptor, CONTROL_LIMIT + 1)
            after = os.fstat(descriptor)
            named = os.stat(name, dir_fd=root.fd, follow_symlinks=False)
            if len(raw) != before.st_size or _stable(before) != _stable(after) or _stable(named) != _stable(before):
                raise BudgetRefusal('Managed control changed while reading')
            signature = (_stable(before), hashlib.sha256(raw).hexdigest())
            key = (root, name)
            if key in self._captured_controls and self._captured_controls[key] != signature:
                raise RecoveryHeld('Captured managed control identity or bytes changed')
            value = _json(raw)
            self._captured_controls[key] = signature
            return value
        finally:
            self._close_fd(descriptor)

    def _new(self, root, name, value):
        data = _canonical(value)
        descriptor = self._open(root, name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW)
        info = self._regular_control(descriptor)
        control = _Control(root, name, descriptor, _identity(info), b'', _stable(info))
        self._created.append(control)
        try:
            while len(control.expected) < len(data):
                written = os.write(descriptor, data[len(control.expected):])
                if written <= 0:
                    raise BudgetRefusal('Managed control write made no progress')
                control.expected = data[:len(control.expected) + written]
            os.fsync(descriptor)
            os.fsync(root.fd)
        except BaseException:
            actual = os.pread(descriptor, CONTROL_LIMIT + 1, 0)
            if data.startswith(actual):
                control.expected = actual
            else:
                self.recovery_held = True
            raise
        finally:
            control.metadata = _stable(os.fstat(descriptor))
        self._captured_controls[(root, name)] = (control.metadata, hashlib.sha256(control.expected).hexdigest())
        return control

    def _names(self, root):
        names = set()
        descriptor = self._open(root, '.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if _identity(os.fstat(descriptor)) != _identity(os.fstat(root.fd)):
                raise RecoveryHeld('Managed enumeration root identity changed')
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    names.add(entry.name)
                    if len(names) > self.policy.entry_limit:
                        raise BudgetRefusal('Managed control namespace exceeds its entry bound')
        finally:
            self._close_fd(descriptor)
        return names

    def _outside_usage(self):
        if self.accounting is None:
            return EXTERNAL_CONTROLS
        legacy = inventory(self.accounting, self.policy, managed_child=self.managed)
        return ObservedUsage(legacy.logical_bytes + EXTERNAL_CONTROLS.logical_bytes,
                             legacy.regular_files + EXTERNAL_CONTROLS.regular_files,
                             legacy.entries + EXTERNAL_CONTROLS.entries)

    def _binding(self):
        value = dict(schema='managed-thumbnail-association-v1', **self.association.record(),
                     authority_path=str(self.authority.path), authority_identity=list(_identity(os.fstat(self.authority.fd))),
                     managed_path=str(self.managed.path), managed_identity=list(_identity(os.fstat(self.managed.fd))))
        if self.accounting is not None:
            value.update(schema='managed-thumbnail-association-v2', accounting_path=str(self.accounting.path),
                         accounting_identity=list(_identity(os.fstat(self.accounting.fd))))
        return value

    @staticmethod
    def _valid_binding(value):
        expected = {'schema', 'library_id', 'catalog_path', 'catalog_device', 'catalog_inode',
                    'authority_path', 'authority_identity', 'managed_path', 'managed_identity'}
        if type(value) is not dict:
            raise BudgetRefusal('Managed association must be an object')
        version = value.get('schema')
        if version == 'managed-thumbnail-association-v2':
            expected |= {'accounting_path', 'accounting_identity'}
        if set(value) != expected or version not in ('managed-thumbnail-association-v1', 'managed-thumbnail-association-v2'):
            raise BudgetRefusal('Managed association schema is unknown')
        LibraryAssociation(value['library_id'], value['catalog_path'], value['catalog_device'], value['catalog_inode'])
        for kind in (('authority', 'managed', 'accounting') if version.endswith('v2') else ('authority', 'managed')):
            path, identity = value[kind + '_path'], value[kind + '_identity']
            if (type(path) is not str or '\x00' in path or not Path(path).is_absolute() or '..' in Path(path).parts
                    or len(path.encode('utf-8')) > 4096 or type(identity) is not list or len(identity) != 2
                    or any(type(part) is not int or part < 0 for part in identity) or identity[1] <= 0):
                raise BudgetRefusal('Managed association identity/path is unsupported')

    def _initialize(self):
        self._baseline_authority = self._names(self.authority)
        self._baseline_managed = self._names(self.managed)
        inventory(self.authority, self.policy)
        inventory(self.managed, self.policy)
        role = {'schema': 'managed-thumbnail-authority-v1',
                'identity': list(_identity(os.fstat(self.authority.fd)))}
        actual_role = self._read(self.authority, AUTHORITY)
        if actual_role is None:
            if self._baseline_authority != {GATE}:
                raise RecoveryHeld('Authority root is not a new empty owned namespace')
            self._new(self.authority, AUTHORITY, role)
        else:
            if (set(actual_role) != {'schema', 'identity'}
                    or type(actual_role.get('identity')) is not list
                    or len(actual_role['identity']) != 2
                    or any(type(part) is not int or part < 0 for part in actual_role['identity'])
                    or actual_role['identity'][1] <= 0 or actual_role != role):
                raise RecoveryHeld('Authority role is unknown or changed')
        for name in self._baseline_authority - {GATE, AUTHORITY}:
            if not name.startswith('association-') or not name.endswith('.json'):
                raise RecoveryHeld('Authority contains an unknown control')
            value = self._read(self.authority, name)
            self._valid_binding(value)
            if name != 'association-' + value['library_id'] + '.json':
                raise RecoveryHeld('Authority association name is inconsistent')
        self.binding_name = 'association-' + self.association.library_id + '.json'
        expected = self._binding()
        actual = self._read(self.authority, self.binding_name)
        domain = self._read(self.managed, DOMAIN)
        if domain is not None:
            self._valid_binding(domain)
        if actual is None and domain is None:
            if (self.require_created_or_bound
                    and self.created_managed_identity != _identity(os.fstat(self.managed.fd))):
                raise RecoveryHeld('Managed namespace was not created by this bootstrap; adoption is refused')
            if self._baseline_managed != {GATE}:
                raise RecoveryHeld('Managed domain is not new; adoption is refused')
            self._new(self.authority, self.binding_name, expected)
            self._new(self.managed, DOMAIN, expected)
        elif actual != expected or domain != expected:
            raise RecoveryHeld('Library/root association changed or enrollment is incomplete')
        self.binding = expected
        # Any pending filename, even malformed/empty, is charged and held.
        if PENDING in self._names(self.managed):
            raise RecoveryHeld('Previous managed operation remains recovery-held')
        usage = inventory(self.managed, self.policy)
        outside = self._outside_usage()
        combined = ObservedUsage(usage.logical_bytes + outside.logical_bytes,
                                 usage.regular_files + outside.regular_files,
                                 usage.entries + outside.entries)
        if not admits(combined, RESERVATION, self.policy):
            raise BudgetRefusal('Managed thumbnail budget cannot reserve this operation')
        self.pending = self._new(self.managed, PENDING, {
            'schema': 'managed-thumbnail-pending-v1', 'token': self.token,
            'library_id': self.association.library_id, 'owner_pid': self.owner_pid,
            'binding_sha256': hashlib.sha256(_canonical(expected)).hexdigest(),
            'reserved_bytes': RESERVATION.logical_bytes,
            'reserved_files': RESERVATION.regular_files, 'reserved_entries': RESERVATION.entries})

    def __enter__(self):
        self._owner()
        if self._entered:
            raise BudgetRefusal('Managed operation cannot be nested or reused')
        self._entered = True
        with _LIFETIME:
            _LIVE.add(self)
        try:
            self.authority = self._pin(self.authority_path)
            self.managed = self._pin(self.managed_path)
            if self.accounting_path is not None:
                self.accounting = self._pin(self.accounting_path, ProtectedAccountingRoot)
                if (self.managed.path.parent != self.accounting.path
                        or _identity(os.fstat(self.managed._handles[-2])) != _identity(os.fstat(self.accounting.fd))):
                    raise BudgetRefusal('Managed namespace is not the captured accounting child')
                aid = _identity(os.fstat(self.authority.fd))
                pid = _identity(os.fstat(self.accounting.fd))
                if (aid in {_identity(os.fstat(fd)) for fd in self.accounting._handles}
                        or pid in {_identity(os.fstat(fd)) for fd in self.authority._handles}):
                    raise BudgetRefusal('Accounting parent and authority alias or nest')
            authority_id = _identity(os.fstat(self.authority.fd))
            managed_id = _identity(os.fstat(self.managed.fd))
            if (authority_id in {_identity(os.fstat(fd)) for fd in self.managed._handles}
                    or managed_id in {_identity(os.fstat(fd)) for fd in self.authority._handles}):
                raise BudgetRefusal('Authority and managed roots alias or nest')
            # Refuse a policy unable to hold even the known empty-domain
            # controls+reservation before creating permanent enrollment files.
            baseline = ObservedUsage(len(_canonical(self._binding())), 2, 2)
            outside = self._outside_usage()
            prospective = ObservedUsage(RESERVATION.logical_bytes + outside.logical_bytes,
                                        RESERVATION.regular_files + outside.regular_files,
                                        RESERVATION.entries + outside.entries)
            if not admits(baseline, prospective, self.policy):
                raise BudgetRefusal('Policy cannot admit the bounded operation and control baseline')
            self._gate(self.authority)
            # An unknown existing namespace must remain untouched even when
            # enrollment will refuse. Only the captured newly created root may
            # receive a gate; bound roots must already have their permanent gate.
            create_managed_gate = (not self.require_created_or_bound
                                   or self.created_managed_identity == managed_id)
            self._gate(self.managed, create=create_managed_gate)
            self._wait_gates()
            self._initialize()
            self._ready = True
            return self
        except BaseException:
            if self._created:
                try:
                    self._rollback_enrollment()
                except BaseException:
                    self.recovery_held = True
            self.close()
            raise

    def _check_created(self, control):
        info = self._regular_control(control.fd)
        named = os.stat(control.name, dir_fd=control.root.fd, follow_symlinks=False)
        raw = os.pread(control.fd, CONTROL_LIMIT + 1, 0)
        if (_identity(info) != control.identity or _stable(info) != control.metadata
                or _stable(named) != control.metadata or raw != control.expected):
            raise RecoveryHeld('Owned managed control was changed or substituted')

    def _post_inventory(self):
        self._validate_gates()
        usage = inventory(self.managed, self.policy)
        inventory(self.authority, self.policy)
        if not admits(usage, self._outside_usage(), self.policy):
            raise RecoveryHeld('Observed usage/control allowance exceeds a terminal ceiling')
        for root, name in tuple(self._captured_controls):
            self._read(root, name)

    def _unlink_owned(self, control):
        self._check_created(control)
        # Sync preceding metadata while the owned pending is still present.
        # Successful unlink is the terminal visible effect; no power-loss
        # durability of removal is claimed (a replayed pending fails closed).
        os.fsync(control.root.fd)
        self._check_created(control)
        os.unlink(control.name, dir_fd=control.root.fd)
        self._close_fd(control.fd)
        self._created.remove(control)

    def _rollback_enrollment(self):
        self._owner()
        if self._ready or self._children or self._uncertain_start or self.recovery_held:
            raise RecoveryHeld('Enrollment rollback eligibility is unknown')
        self._post_inventory()
        for root, baseline in ((self.authority, self._baseline_authority), (self.managed, self._baseline_managed)):
            created_names = {c.name for c in self._created if c.root is root}
            if self._names(root) != baseline | created_names:
                raise RecoveryHeld('Enrollment inventory contains unexplained changes')
        for control in self._created:
            self._check_created(control)
        for control in tuple(reversed(self._created)):
            self._unlink_owned(control)

    def start_child(self, process):
        self._owner()
        if not self._ready or self._completed or self.pending is None:
            raise BudgetRefusal('Managed pending operation is not ready')
        if self._children:
            raise BudgetRefusal('Only one child dispatch is permitted per reservation')
        if (not isinstance(process, BaseProcess) or process.pid is not None
                or process._parent_pid != self.owner_pid or process._closed
                or multiprocessing.current_process().daemon):
            raise BudgetRefusal('Child startup precondition refused before dispatch')
        self._validate_gates()
        self._check_created(self.pending)
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise AdmissionBusy('Managed admission canceled before child dispatch')
        self._children.append(process)
        try:
            process.start()
        except BaseException:
            self._uncertain_start = True
            raise
        if process.pid is None:
            self._uncertain_start = True
            raise RecoveryHeld('Child startup outcome is unknown')

    def finish(self):
        self._owner()
        if not self._ready or self._completed or self.pending is None or self._uncertain_start:
            raise RecoveryHeld('Managed terminal eligibility is unknown')
        for process in self._children:
            if process.exitcode is None or process.is_alive():
                raise RecoveryHeld('Owned child exit is not confirmed')
            process.join(0)
        self._post_inventory()
        if self._read(self.authority, self.binding_name) != self.binding or self._read(self.managed, DOMAIN) != self.binding:
            raise RecoveryHeld('Managed association changed before release')
        self._unlink_owned(self.pending)
        self.pending = None
        self._completed = True
        self.recovery_held = False

    def rollback_known(self):
        """Explicit known-failure release; same terminal proof as successful finish."""
        self.finish()

    def close(self):
        if os.getpid() != self.owner_pid or self._forked:
            raise BudgetRefusal('Copied managed operation cannot be closed after fork')
        if self._closed:
            return
        self._owner()
        self.recovery_held = self.recovery_held or self.pending is not None
        with _LIFETIME:
            for root in self._pins:
                for descriptor in root._handles:
                    self._fds.remove(descriptor)
                root.close()
            self._pins.clear()
            while self._fds:
                descriptor = self._fds.pop()
                os.close(descriptor)
            _LIVE.discard(self)
        self._gates.clear()
        self._closed = True

    def __exit__(self, exc_type, exc, traceback):
        held = self.pending is not None
        self.close()
        if exc_type is None and held:
            raise RecoveryHeld('Operation exited without explicit terminal release')
