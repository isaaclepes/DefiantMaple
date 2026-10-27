"""Explicit, bounded Linux bootstrap for the private schedule locator directory.

This does not admit recovery packages or user-selected managed destinations.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import stat
import sys

from .recovery_storage import _local_backing, _mount_type
from .scheduled_snapshots import StateUncertainError


def _identity(info):
    return info.st_dev, info.st_ino


def _admit(info, *, owned=False, private=False, newly_created=False):
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
        raise ValueError("Schedule locator parent is redirected or writable by other users")
    if owned and info.st_uid != os.geteuid():
        raise ValueError("Schedule locator profile directory must be user-owned")
    if private and info.st_mode & 0o077:
        raise ValueError("Schedule locator directory must be private")
    if newly_created and stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("New schedule locator profile directory must be mode 0700")


def _open_child(parent_fd, name, expected=None):
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        current = os.fstat(descriptor)
        if _identity(before) != _identity(current) or (expected is not None and _identity(current) != expected):
            raise ValueError("Schedule locator path changed during admission")
        return descriptor, current
    except BaseException:
        os.close(descriptor)
        raise


def _plan(application_data_root, profile):
    app = Path(application_data_root)
    if not app.is_absolute() or ".." in app.parts:
        raise ValueError("Schedule locator profile path is invalid")
    if profile == "implicit_linux_default":
        if app.name != "DefiantMaple":
            raise ValueError("Schedule locator default profile path is invalid")
        expected = Path.home() / ".local" / "share" / "DefiantMaple"
        if app != expected:
            raise ValueError("Schedule locator default profile changed")
        return Path.home(), (".local", "share", "DefiantMaple", "scheduled-snapshots-v1")
    if profile == "explicit_xdg":
        if app.name != "DefiantMaple":
            raise ValueError("Schedule locator XDG profile path is invalid")
        base = os.environ.get("XDG_DATA_HOME")
        if not base or app != Path(base) / "DefiantMaple":
            raise ValueError("Schedule locator XDG profile changed")
        return Path(base), ("DefiantMaple", "scheduled-snapshots-v1")
    if profile == "custom":
        return app, ("scheduled-snapshots-v1",)
    raise ValueError("Unknown schedule locator profile")


def bootstrap_locator_directory(application_data_root, *, profile="custom"):
    """Create only the fixed missing profile suffix during explicit configure."""
    if sys.platform != "linux" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Schedule locator bootstrap has no reviewed native adapter on this platform")
    base, suffix = _plan(application_data_root, profile)
    created = False
    with ExitStack() as stack:
        root_fd = stack.enter_context(_closing_fd(os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)))
        chain = [(Path("/"), root_fd, os.fstat(root_fd))]
        created_paths = set()
        _admit(chain[0][2])
        for part in base.parts[1:]:
            try:
                descriptor, info = _open_child(chain[-1][1], part)
            except FileNotFoundError as exc:
                raise ValueError("Schedule locator profile base must already exist") from exc
            stack.enter_context(_closing_fd(descriptor))
            path = chain[-1][0] / part
            _admit(info)
            chain.append((path, descriptor, info))
        _admit(chain[-1][2], owned=True)
        for index, part in enumerate(suffix):
            parent_path, parent_fd, parent_info = chain[-1]
            try:
                _admit(parent_info, owned=True, private=(parent_path in created_paths))
                if not _local_backing(*_mount_type(parent_path)):
                    raise ValueError("Recovery requires a verified durable local filesystem")
                _revalidate(chain, created_paths)
                try:
                    descriptor, info = _open_child(parent_fd, part)
                    newly_created = False
                except FileNotFoundError:
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent_fd)
                    except FileExistsError as exc:
                        raise ValueError("Schedule locator profile changed during creation") from exc
                    created = newly_created = True
                    descriptor, info = _open_child(parent_fd, part)
                stack.enter_context(_closing_fd(descriptor))
                path = parent_path / part
                chain.append((path, descriptor, info))
                if newly_created:
                    created_paths.add(path)
                _admit(info, owned=True, private=(index == len(suffix) - 1 or newly_created),
                       newly_created=newly_created)
                if not _local_backing(*_mount_type(path)):
                    raise ValueError("Recovery requires a verified durable local filesystem")
                # Reestablish the entry's durability on every explicit Enable.
                # A prior attempt may have created it before an fsync failure.
                try:
                    os.fsync(descriptor)
                    os.fsync(parent_fd)
                except OSError as exc:
                    raise StateUncertainError("Schedule locator profile durability uncertain") from exc
                _revalidate(chain, created_paths)
            except StateUncertainError:
                raise
            except (ValueError, OSError) as exc:
                if created:
                    raise StateUncertainError("Schedule locator directory created; durability or identity uncertain") from exc
                raise


def _revalidate(chain, created_paths):
    """Check every pinned fd is still named by its original lexical path."""
    with ExitStack() as stack:
        descriptor = stack.enter_context(_closing_fd(os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)))
        if _identity(os.fstat(descriptor)) != _identity(chain[0][2]):
            raise ValueError("Schedule locator ancestor changed")
        for path, original_fd, original_info in chain[1:]:
            next_fd, named = _open_child(descriptor, path.name, _identity(original_info))
            stack.enter_context(_closing_fd(next_fd))
            _admit(named, owned=(path == chain[-1][0] or original_info.st_uid == os.geteuid()),
                   private=(path in created_paths or path.name == "scheduled-snapshots-v1"),
                   newly_created=(path in created_paths))
            if _identity(os.fstat(original_fd)) != _identity(named):
                raise ValueError("Schedule locator ancestor changed")
            descriptor = next_fd


class _closing_fd:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def __enter__(self):
        return self.descriptor

    def __exit__(self, *_args):
        os.close(self.descriptor)
