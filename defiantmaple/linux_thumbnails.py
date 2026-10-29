"""Linux managed thumbnail writes. No cache eviction or uncertain reclamation."""
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import threading
import time

from .admission import admission_session, current_session, registry_path
from .cached_preview import (MANAGED_NAMESPACE, CacheReadLimits, capture_target,
                             managed_directory, read_bounded_cache_file, hash_bounded_cache_file)
from .catalog import connect, require_original_access
from .managed_thumbnail_admission import (ManagedOperation, capture_association,
                                         CONTROL_LIMIT, EXTERNAL_CONTROLS, RESERVATION)
from .thumbnail_budget import (BoundedOutput, BudgetPolicy, BudgetRefusal, ObservedUsage,
                               PinnedRoot, ProtectedAccountingRoot, admits, inventory)

_BOOTSTRAP = threading.Lock()
DEFAULT_POLICY = BudgetPolicy()


class CacheWriteHeld(BudgetRefusal):
    """Budget/ownership refusal; never an asset or source-health mutation."""


def default_authority_root():
    """Fixed OS-account locator, deliberately independent of HOME/XDG overrides."""
    return registry_path().parent / 'thumbnail-cache-authority-v1'


def _identity(info):
    return (info.st_dev, info.st_ino)


def _ensure_directory(path):
    """Bootstrap directories only, no link traversal or permission repair."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or len(path.parts) > 64:
        raise CacheWriteHeld('Cache location is unsupported')
    created_identity = None
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in path.parts[1:]:
            created = False
            try:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(name, 0o700, dir_fd=descriptor)
                    created = True
                except FileExistsError:
                    pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            if name == path.parts[-1] and created:
                created_identity = _identity(os.fstat(child))
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)
    return created_identity


@contextmanager
def _ownership(database):
    owner = current_session(database)
    if owner is None:
        with admission_session(database) as owner:
            yield owner
    else:
        owner.retain()
        try:
            yield owner
        finally:
            owner.release()


@contextmanager
def _serialized(cancel):
    deadline = time.monotonic() + 2
    while not _BOOTSTRAP.acquire(timeout=.02):
        if cancel is not None and cancel.is_set():
            raise CacheWriteHeld('Cache preparation canceled before write admission')
        if time.monotonic() >= deadline:
            raise CacheWriteHeld('Cache write admission is busy')
    try:
        if cancel is not None and cancel.is_set():
            raise CacheWriteHeld('Cache preparation canceled before write admission')
        yield
    finally:
        _BOOTSTRAP.release()


def _cache_parent(cache_root):
    path = Path(cache_root).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if '..' in path.parts:
        raise CacheWriteHeld('Cache parent must be a lexical absolute location')
    return path


def _preflight(parent):
    try:
        pinned = ProtectedAccountingRoot(parent)
    except FileNotFoundError:
        usage = ObservedUsage(0, 0, 0)
    except BudgetRefusal:
        # PinnedRoot wraps absent-root OSError: distinguish only a genuinely
        # missing lexical location; symlink/non-directory errors still refuse.
        try:
            parent.lstat()
        except FileNotFoundError:
            usage = ObservedUsage(0, 0, 0)
        else:
            raise
    else:
        with pinned:
            usage = inventory(pinned, DEFAULT_POLICY)
    prospective = ObservedUsage(RESERVATION.logical_bytes + EXTERNAL_CONTROLS.logical_bytes + 3 * CONTROL_LIMIT,
                                RESERVATION.regular_files + EXTERNAL_CONTROLS.regular_files + 4,
                                RESERVATION.entries + EXTERNAL_CONTROLS.entries + 8)
    if not admits(usage, prospective, DEFAULT_POLICY):
        raise CacheWriteHeld('Cache budget or entry limit reached; no cached files were removed')


def _mkdir_chain(root, components):
    descriptors = []
    parent = root.fd
    try:
        for index, name in enumerate(components):
            if Path(name).name != name or name in ('.', '..'):
                raise CacheWriteHeld('Unsafe cache operation name')
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
            except FileExistsError:
                if index == len(components) - 1:
                    raise CacheWriteHeld('Cache operation destination already exists')
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            info = os.fstat(child)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                os.close(child)
                raise CacheWriteHeld('Cache operation directory ownership is unsafe')
            descriptors.append(child)
            parent = child
        return _identity(os.fstat(parent))
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def write_encoded_output(payload, encoded):
    """Child-only exclusive bounded write after all original checks succeeded."""
    proof = payload['managed']
    root_path, output = Path(proof['root']), Path(payload['output'])
    if not output.is_relative_to(root_path) or '..' in output.parts:
        raise CacheWriteHeld('Managed output is outside its captured root')
    if len(encoded) > 20 * 1024 ** 2:
        raise CacheWriteHeld('Encoded PNG exceeds its output bound')
    with PinnedRoot(root_path) as root:
        if list(_identity(os.fstat(root.fd))) != proof['root_identity']:
            raise CacheWriteHeld('Managed root changed before child output')
        pending = read_bounded_cache_file(root_path / '.managed-pending-v1.json', CONTROL_LIMIT)
        if hashlib.sha256(pending).hexdigest() != proof['pending_sha256']:
            raise CacheWriteHeld('Managed pending authorization changed')
        with PinnedRoot(output.parent) as parent:
            if list(_identity(os.fstat(parent.fd))) != proof['output_parent_identity']:
                raise CacheWriteHeld('Managed operation directory changed')
            descriptor = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent.fd)
            try:
                position = 0
                while position < len(encoded):
                    written = os.write(descriptor, encoded[position:position + 1024 ** 2])
                    if written <= 0:
                        raise CacheWriteHeld('Encoded output write made no progress')
                    position += written
                os.fsync(descriptor)
                info = os.fstat(descriptor)
                if info.st_size != len(encoded) or not stat.S_ISREG(info.st_mode):
                    raise CacheWriteHeld('Managed output size changed')
                os.fsync(parent.fd)
                return list(_identity(info))
            finally:
                os.close(descriptor)


def _publish_manifest(path, manifest, *, root_path, root_identity, parent_identity):
    data = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(data) > CONTROL_LIMIT:
        raise CacheWriteHeld('Cache manifest exceeds its output bound')
    staging = '.manifest-stage.json'
    with PinnedRoot(root_path) as root, PinnedRoot(path.parent) as parent:
        if (_identity(os.fstat(root.fd)) != tuple(root_identity)
                or _identity(os.fstat(parent.fd)) != tuple(parent_identity)
                or not path.parent.is_relative_to(root.path)):
            raise CacheWriteHeld('Managed publication root or directory changed')
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent.fd)
        try:
            position = 0
            while position < len(data):
                written = os.write(descriptor, data[position:])
                if written <= 0:
                    raise CacheWriteHeld('Manifest write made no progress')
                position += written
            os.fsync(descriptor)
            identity = _identity(os.fstat(descriptor))
            root.validate()
            parent.validate()
            os.link(staging, path.name, src_dir_fd=parent.fd, dst_dir_fd=parent.fd,
                    follow_symlinks=False)
            os.fsync(parent.fd)
            # Only this operation's newly created stage; final pair is immutable.
            if _identity(os.stat(staging, dir_fd=parent.fd, follow_symlinks=False)) != identity:
                raise CacheWriteHeld('Manifest staging identity changed')
            os.unlink(staging, dir_fd=parent.fd)
        finally:
            os.close(descriptor)


def _placement(database, parent):
    database_path = Path(database).resolve(strict=True)
    if database_path == parent or parent in database_path.parents:
        raise CacheWriteHeld('Cache location must not contain the catalog')
    with connect(database) as db:
        for row in db.execute('SELECT root_path FROM sources'):
            root = Path(row[0])
            if not root.is_absolute() or '..' in root.parts:
                raise CacheWriteHeld('Registered source placement is unresolved')
            if parent == root or root in parent.parents or parent in root.parents:
                raise CacheWriteHeld('Cache location must be outside registered source folders')
        prefix = str(parent).rstrip(os.sep) + os.sep
        # Bound Python memory: ask existence, never materialize all asset paths.
        original = db.execute('SELECT 1 FROM assets WHERE current_path=? OR substr(current_path,1,?)=? LIMIT 1',
                              (str(parent), len(prefix), prefix)).fetchone()
        if original is not None:
            raise CacheWriteHeld('Cache location must not contain original media')


def thumbnail_for_linux(database, asset_id, cache_root, max_edge, limits, cancel_event):
    from . import thumbnail as codec
    if type(max_edge) is not int or not 32 <= max_edge <= 2048:
        raise ValueError('max_edge must be an integer from 32 through 2048')
    if cancel_event is not None and cancel_event.is_set():
        raise codec.ThumbnailCancelled('thumbnail generation canceled')
    parent = _cache_parent(cache_root)
    with _ownership(database):
        with connect(database) as catalog:
            row = catalog.execute('SELECT * FROM assets WHERE asset_id=?', (asset_id,)).fetchone()
            require_original_access(catalog, row['source_id'] if row else None,
                                    row['current_path'] if row else None)
        if row is None:
            raise ValueError('Unknown asset_id')
        asset = dict(row)
        if not asset['media_type'].startswith('image/'):
            raise codec.ThumbnailError('unsupported_media: thumbnails require an image asset')
        target = capture_target(asset)
        if target.byte_size > limits.max_source_bytes:
            raise codec.ThumbnailError('oversized_image: source exceeds max_source_bytes')
        fingerprint = f'sha256-{target.sha256}-bytes-{target.byte_size}'
        basename = f'thumbnail-v1-e{max_edge}-b{limits.max_source_bytes}-d{limits.max_dimension}-p{limits.max_pixels}'
        expected = {'cache_schema': 1, 'asset_id': target.asset_id, 'source_fingerprint': fingerprint,
                    'source_sha256': target.sha256, 'source_bytes': target.byte_size,
                    'media_type': target.media_type, 'max_edge': max_edge, 'decoder': 'Pillow',
                    'decoder_version': codec.PILLOW_VERSION, 'max_source_bytes': limits.max_source_bytes,
                    'max_dimension': limits.max_dimension, 'max_pixels': limits.max_pixels}
        legacy = parent / target.asset_id[:2] / target.asset_id / fingerprint
        result = codec._cached_result(legacy / (basename + '.png'), legacy / (basename + '.json'), expected)
        if result:
            return result
        if (legacy / (basename + '.png')).exists() or (legacy / (basename + '.json')).exists():
            raise CacheWriteHeld('Legacy cache entry refused; existing files were preserved')
        try:
            candidate = managed_directory(parent, target, max_edge, manifest_name=basename + '.json')
        except FileNotFoundError:
            candidate = None
        if candidate is not None:
            result = codec._cached_result(candidate / (basename + '.png'), candidate / (basename + '.json'), expected)
            if result:
                return result
            raise CacheWriteHeld('Committed managed cache entry refused; existing files were preserved')
        _placement(database, parent)
        with _serialized(cancel_event):
            _placement(database, parent)
            _preflight(parent)
            authority = Path(default_authority_root())
            _ensure_directory(authority.parent)
            with PinnedRoot(authority.parent):
                _ensure_directory(authority)
            _ensure_directory(parent)
            managed = parent / MANAGED_NAMESPACE
            created_managed_identity = _ensure_directory(managed)
            association = capture_association(database)
            with ManagedOperation(authority, managed, association, policy=DEFAULT_POLICY,
                                  cancel_event=cancel_event, accounting_parent=parent,
                                  require_created_or_bound=True,
                                  created_managed_identity=created_managed_identity) as operation:
                try:
                    # Reuse a pair that another cooperating same-process request
                    # committed before we acquired the serial write boundary.
                    candidate = managed_directory(parent, target, max_edge, manifest_name=basename + '.json')
                    if candidate is not None:
                        hit = codec._cached_result(candidate / (basename + '.png'), candidate / (basename + '.json'), expected)
                        if hit:
                            operation.finish()
                            return hit
                        raise CacheWriteHeld('Committed managed cache entry refused')
                    components = ['data', target.asset_id[:2], target.asset_id, fingerprint,
                                  'op-' + operation.token.replace('-', '')]
                    parent_identity = _mkdir_chain(operation.managed, components)
                    output = managed.joinpath(*components) / (basename + '.png')
                    payload = {'database': str(database), 'catalog_identity': (association.device, association.inode),
                               'asset_id': target.asset_id, 'revision': target.revision, 'source_id': target.source_id,
                               'source': target.path, 'output': str(output), 'source_sha256': target.sha256,
                               'source_bytes': target.byte_size, 'max_edge': max_edge,
                               'limits': codec.asdict(limits), 'managed': {
                                   'root': str(managed), 'root_identity': list(_identity(os.fstat(operation.managed.fd))),
                                   'pending_sha256': hashlib.sha256(operation.pending.expected).hexdigest(),
                                   'output_parent_identity': list(parent_identity)}}
                    result = codec._run_decoder(payload, limits.timeout_seconds, cancel_event,
                                                managed_operation=operation)
                    if cancel_event is not None and cancel_event.is_set():
                        raise codec.ThumbnailCancelled('thumbnail generation canceled')
                    identity = result.pop('managed_identity')
                    info = output.lstat()
                    if list(_identity(info)) != identity or not stat.S_ISREG(info.st_mode):
                        raise CacheWriteHeld('Managed child output identity changed')
                    digest, output_size = hash_bounded_cache_file(output, codec.MAX_CACHE_PNG_BYTES)
                    if digest != result['output_sha256'] or output_size != result['output_bytes']:
                        raise CacheWriteHeld('Managed child output content changed')
                    manifest = {**expected, **result}
                    manifest.pop('ok', None)
                    _placement(database, parent)
                    _publish_manifest(output.with_suffix('.json'), manifest, root_path=managed,
                                      root_identity=payload['managed']['root_identity'],
                                      parent_identity=parent_identity)
                    operation.finish()
                    return {**manifest, 'cache_hit': False, 'path': str(output)}
                except BaseException as error:
                    if operation._uncertain_start:
                        operation.recovery_held = True
                    else:
                        try:
                            operation.rollback_known()
                        except BaseException:
                            operation.recovery_held = True
                    if operation.recovery_held:
                        raise CacheWriteHeld(
                            'Managed child start or cleanup is uncertain; cache generation held') from error
                    raise
