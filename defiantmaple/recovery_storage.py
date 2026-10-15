"""Strict local publication primitives for the first Linux recovery checkpoint.

Other platforms deliberately refuse until native handle/containment adapters
are reviewed. A caller cannot pass a test certification or bypass this policy.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import hashlib
import re
from pathlib import Path
import stat
import sys

_LOCAL_DURABLE_TYPES = frozenset({"btrfs", "ext4", "xfs", "zfs", "f2fs"})


def _mount_type(path: Path) -> tuple[str, str]:
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("Cannot establish local storage placement") from exc
    selected = (0, "", "")
    target = str(path)
    for line in lines:
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        details = after.split()
        if len(fields) < 5 or len(details) < 2:
            continue
        encoded_mount = fields[4]
        if re.search(r"\\(?![0-7]{3})", encoded_mount):
            raise ValueError("Cannot parse local storage mount path")
        mount = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), encoded_mount)
        if "\0" in mount:
            raise ValueError("Cannot parse local storage mount path")
        if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) > selected[0]:
            selected = (len(mount), details[0], details[1])
    if not selected[1]:
        raise ValueError("Cannot establish local storage mount")
    return selected[1], selected[2]


def _direct_local_block(name: str) -> bool:
    if not name or "/" in name:
        return False
    try:
        device = (Path("/sys/class/block") / name).resolve(strict=True)
        controllers = [part for part in device.parts if re.fullmatch(r"nvme[0-9]+", part)]
        if len(controllers) != 1:
            return False
        controller = (Path("/sys/class/nvme") / controllers[0]).resolve(strict=True)
        transport = (Path("/sys/class/nvme") / controllers[0] / "transport").read_text().strip()
    except (OSError, RuntimeError):
        return False
    return controller in device.parents and transport == "pcie" and "/pci" in str(controller)


def _local_backing(kind: str, source: str) -> bool:
    if kind not in _LOCAL_DURABLE_TYPES or not source.startswith("/dev/"):
        return False
    name = Path(source).name
    if not _direct_local_block(name):
        return False
    if kind == "btrfs":
        # A multi-device volume is local only when every backing device is.
        for volume in Path("/sys/fs/btrfs").iterdir():
            devices = volume / "devices"
            if devices.is_dir() and (devices / name).exists():
                names = [entry.name for entry in devices.iterdir()]
                return bool(names) and all(_direct_local_block(item) for item in names)
        return False
    return True


@contextmanager
def private_local_parent(leaf: Path):
    """Yield (absolute path, parent dirfd) for an absent or existing leaf."""
    if sys.platform != "linux" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Recovery publication has no reviewed native adapter on this platform")
    leaf = Path(leaf)
    if not leaf.is_absolute() or leaf.name in ("", ".", "..") or ".." in leaf.parts:
        raise ValueError("Recovery path must be an absolute file path")
    parent = leaf.parent
    # Walk lexically. resolve() would hide a symlink/reparse component.
    for part in (Path("/"), *reversed(parent.parents), parent):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise ValueError("Recovery parent is redirected or writable by other users")
    info = parent.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Recovery requires a user-owned private destination directory")
    if not _local_backing(*_mount_type(parent)):
        raise ValueError("Recovery requires a verified durable local filesystem")
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("Recovery parent changed during admission")
        yield leaf, descriptor
    finally:
        os.close(descriptor)


def regular_existing(leaf: Path, dirfd: int) -> tuple[int, os.stat_result]:
    descriptor = os.open(leaf.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("Recovery input must be a user-owned regular file")
        return descriptor, info
    except BaseException:
        os.close(descriptor)
        raise


def absent(leaf: Path, dirfd: int) -> None:
    try:
        os.stat(leaf.name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError(f"Recovery destination already exists: {leaf.name}")


def create_stage(leaf: Path, dirfd: int) -> int:
    return os.open(leaf.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                   0o600, dir_fd=dirfd)


class PublicationUncertain(OSError):
    """The final name may exist after a verified link; inspect before retry."""


def _digest_regular(name: str, dirfd: int) -> tuple[int, str]:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Recovery publication stage is not regular")
        digest = hashlib.sha256()
        size = 0
        while block := os.read(descriptor, 1024 * 1024):
            size += len(block)
            digest.update(block)
        return size, digest.hexdigest()
    finally:
        os.close(descriptor)


def publish(stage: Path, final: Path, dirfd: int, expected_size: int,
            expected_sha256: str, before_link=None) -> None:
    """Atomic create-if-absent publication; both names share this private dir."""
    if _digest_regular(stage.name, dirfd) != (expected_size, expected_sha256):
        raise ValueError("Closed recovery stage failed length/digest readback")
    if before_link is not None:
        before_link()
    os.link(stage.name, final.name, src_dir_fd=dirfd, dst_dir_fd=dirfd,
            follow_symlinks=False)
    try:
        left = os.stat(stage.name, dir_fd=dirfd, follow_symlinks=False)
        right = os.stat(final.name, dir_fd=dirfd, follow_symlinks=False)
        if not stat.S_ISREG(right.st_mode) or (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino):
            raise OSError("Published recovery file identity differs from verified stage")
        if _digest_regular(final.name, dirfd) != (expected_size, expected_sha256):
            raise OSError("Published recovery file failed length/digest readback")
        os.unlink(stage.name, dir_fd=dirfd)
        os.fsync(dirfd)
    except BaseException as exc:
        raise PublicationUncertain("Recovery final path may be published; inspect it before retry") from exc
