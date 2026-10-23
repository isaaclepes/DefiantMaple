"""Durable schedule veto overlay, independent of managed state and its locks.

Importing does no I/O. Callers supply an existing authenticated locator and
private locator directory; this module never creates directories or follows UUIDs.
The control lock is always LAST, and a stop writer takes this lock alone.
"""
from contextlib import closing
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import uuid
import sqlite3

from .recovery import _require_backup_catalog

from .scheduled_snapshots import (Binding, Locator, LockedDirectory, ScheduleError,
    StateUncertainError, Version, _fields, _integer, _private_regular,
    _stat_identity, _uuid, locator_leaf, validate_pair)

_LIMIT = 131072
_SCHEMA = 'defiantmaple.schedule-control.v1'


@dataclass(frozen=True)
class ScheduleControl:
    locator: Locator
    request_id: str
    action: str
    utc: int
    reason: str

    def __post_init__(self):
        if type(self.locator) is not Locator:
            raise ScheduleError('Invalid schedule control binding')
        _uuid(self.request_id)
        if type(self.action) is not str or self.action not in {'run', 'stop_requested', 'stopped'}:
            raise ScheduleError('Invalid schedule control action')
        _integer(self.utc, 0, 2**63 - 1)
        if type(self.reason) is not str or len(self.reason.encode('utf-8')) > 1024 or '\0' in self.reason:
            raise ScheduleError('Invalid schedule control reason')

    def permits(self, locator):
        return self.action == 'run' and self.locator == locator


def encode_control(value):
    if type(value) is not ScheduleControl:
        raise ScheduleError('Unsupported schedule control')
    raw = json.dumps({'schema': _SCHEMA, **asdict(value)}, ensure_ascii=True,
                     sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    if len(raw) > _LIMIT:
        raise ScheduleError('Schedule control exceeds its bound')
    return raw


def decode_control(raw):
    if type(raw) is not bytes or len(raw) > _LIMIT:
        raise ScheduleError('Schedule control exceeds its bound')
    def pairs(entries):
        value = {}
        for key, item in entries:
            if key in value:
                raise ScheduleError('Duplicate schedule control key')
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ScheduleError('Nonfinite control value')))
        _fields(value, ('schema', 'locator', 'request_id', 'action', 'utc', 'reason'))
        if value.pop('schema') != _SCHEMA:
            raise ScheduleError('Unsupported schedule control schema')
        loc = value['locator']
        _fields(loc, ('schedule_id', 'revision', 'binding'))
        _fields(loc['binding'], Binding.__dataclass_fields__)
        value['locator'] = Locator(loc['schedule_id'], loc['revision'], Binding(**loc['binding']))
        return ScheduleControl(**value)
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ScheduleError('Invalid schedule control document') from exc


class ControlStore(LockedDirectory):
    def __init__(self, directory, catalog):
        self.leaf = locator_leaf(Path(catalog)) + '.control'
        super().__init__(directory, self.leaf + '.lock')

    def read_control(self):
        self.validate()
        try:
            fd = os.open(self.leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None, None
        try:
            before = os.fstat(fd)
            _private_regular(before)
            if before.st_size > _LIMIT:
                raise ScheduleError('Schedule control exceeds its bound')
            raw = bytearray()
            while len(raw) <= _LIMIT:
                chunk = os.read(fd, min(65536, _LIMIT + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            named = os.stat(self.leaf, dir_fd=self.fd, follow_symlinks=False)
            for info in (after, named):
                _private_regular(info)
            signature = lambda info: (_stat_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if signature(before) != signature(after) or signature(named) != signature(after):
                raise ScheduleError('Schedule control changed during reading')
            value = decode_control(bytes(raw))
            if locator_leaf(Path(value.locator.binding.catalog_path)) + '.control' != self.leaf:
                raise ScheduleError('Schedule control is stored under another key')
            self.validate()
            return value, Version(_stat_identity(before), hashlib.sha256(raw).hexdigest())
        finally:
            os.close(fd)

    def write_control(self, value, expected):
        raw = encode_control(value)
        if locator_leaf(Path(value.locator.binding.catalog_path)) + '.control' != self.leaf:
            raise ScheduleError('Schedule control key mismatch')
        if self.read_control()[1] != expected:
            raise ScheduleError('Schedule control changed; reload before updating')
        stage = '.control-' + uuid.uuid4().hex + '.stage'
        fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        identity, published = _stat_identity(os.fstat(fd)), False
        try:
            data = memoryview(raw)
            while data:
                written = os.write(fd, data)
                if written <= 0:
                    raise OSError('Control write made no progress')
                data = data[written:]
            os.fsync(fd)
            self.validate()
            if self.read_control()[1] != expected:
                raise ScheduleError('Control changed before publication')
            if expected is None:
                os.link(stage, self.leaf, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            else:
                os.replace(stage, self.leaf, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            published = True
            if expected is None:
                os.unlink(stage, dir_fd=self.fd)
            os.fsync(self.fd)
            document, version = self.read_control()
            if document != value or version != Version(identity, hashlib.sha256(raw).hexdigest()):
                raise StateUncertainError('Published control changed; do not acknowledge')
            return version
        except BaseException as exc:
            if published:
                raise StateUncertainError('Control may be published; do not acknowledge') from exc
            raise
        finally:
            os.close(fd)
            if not published:
                try:
                    info = os.stat(stage, dir_fd=self.fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if _stat_identity(info) == identity:
                        os.unlink(stage, dir_fd=self.fd)

    def request_stop(self, locator, *, utc, reason, expected):
        value = ScheduleControl(locator, str(uuid.uuid4()), 'stop_requested', utc, reason)
        return value, self.write_control(value, expected)

    def _acknowledge_stop(self, request, expected, locator):
        # same-live-session authority is supplied by the controller, never
        # reconstructed from a restarted document or PID absence.
        if request.action != 'stop_requested' or request.locator != locator:
            raise ScheduleError('Exact live-session cleanup acknowledgment required')
        current, version = self.read_control()
        if current != request or version != expected:
            raise ScheduleError('Stop request changed before acknowledgment')
        value = replace(request, action='stopped')
        return value, self.write_control(value, expected)


class LiveStopSession:
    """Nonpersistent authority for one controller lifetime's stop acknowledgments.

    A reconstructed session never imports requests from disk. The caller supplies
    its actual finished actor (or no actor when no work was ever queued). Qt must
    additionally attest its own finished signal and absence of queued work.
    """
    def __init__(self, configuration):
        self.config = configuration
        self.owner = configuration.owner
        self._requests = {}
        self._actors = []

    def _validate(self, locator):
        # Native admission and captured physical binding precede every SQLite
        # query, including placement's source-root authentication.
        self.config._validate_owner()
        if type(locator) is not Locator:
            raise ScheduleError('Invalid stop locator')
        binding = locator.binding
        if (binding.catalog_path != str(self.owner.path)
                or binding.parent_identity != self.owner.parent.identity
                or binding.file_identity != self.owner.file.identity):
            raise ScheduleError('Stop request differs from its admitted physical library')
        self.config._placement()
        self.owner.validate()
        with closing(sqlite3.connect(self.owner.path.as_uri() + '?mode=ro', uri=True)) as database:
            identity = _require_backup_catalog(database)
        self.owner.validate()
        if binding.library_id != identity:
            raise ScheduleError('Stop request differs from its admitted library identity')

    def observe_actor(self, actor):
        if actor.owner is not self.owner:
            raise ScheduleError('Actor belongs to another library owner')
        if all(known is not actor for known in self._actors):
            # Fail closed rather than drop a possibly unresolved actor merely
            # because an externally writable active flag became false.
            if len(self._actors) >= 64:
                raise ScheduleError('Stop session actor bound reached; cleanup review required')
            self._actors.append(actor)

    def request(self, locator, *, utc, reason):
        self._validate(locator)
        self.owner.retain()
        try:
            # Never acquire upstream locator/managed locks from the stop writer.
            with ControlStore(self.config.root, self.owner.path) as store:
                _, version = store.read_control()
                request, version = store.request_stop(locator, utc=utc, reason=reason, expected=version)
                # Only the latest saved request can ever be acknowledged.
                self._requests = {request.request_id: (request, version)}
                return request, version
        finally:
            self.owner.release()

    def acknowledge(self, request, version, locator, *, thread_finished, queued_work):
        self._validate(locator)
        saved = self._requests.get(request.request_id)
        if (thread_finished is not True or queued_work is not False or saved is None
                or saved[0] is not request or saved[1] != version):
            raise ScheduleError('This live session cannot acknowledge that stop')
        if any(actor.owner is not self.owner or actor.active for actor in self._actors):
            raise ScheduleError('Actual actor cleanup remains owned')
        self.owner.retain()
        try:
            # Establish the same committed config under upstream locks first.
            with LockedDirectory(self.config.root, self.config.leaf + '.lock') as pointers:
                current, _ = pointers.read(self.config.leaf, locator=True)
                transition, _ = pointers.read(self.config.transition_leaf, transition=True)
                if (current != locator or transition is None or transition.phase != 'committed'
                        or transition.locator != current):
                    raise ScheduleError('Configuration changed before stop acknowledgment')
                with LockedDirectory(locator.binding.directory_path, 'schedule.lock') as managed:
                    state, _ = managed.read('schedule.json')
                    validate_pair(locator, state, self.owner)
                    with ControlStore(self.config.root, self.owner.path) as store:
                        result = store._acknowledge_stop(request, version, locator)
            del self._requests[request.request_id]
            return result
        finally:
            self.owner.release()


def require_run(configuration, locator, locators):
    """Transient final checkpoint; never hold control across work or unlink.

    The caller already holds authenticated upstream stores. A stop that arrives
    after this checkpoint may race that bounded action; it vetoes the next one.
    """
    configuration._validate_owner()
    locators.validate()
    if locators.directory != configuration.root:
        raise ScheduleError('Control checkpoint has another locator directory')
    with ControlStore(configuration.root, configuration.owner.path) as control:
        if control.identity != locators.identity:
            raise ScheduleError('Control directory differs from the pinned configuration')
        value, _ = control.read_control()
        locators.validate()
        configuration._validate_owner()
        if value is None or not value.permits(locator):
            raise ScheduleError('Scheduled work is stopped or control needs review')
