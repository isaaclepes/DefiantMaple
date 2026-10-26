"""Create and verify one ephemeral APT-readable pinned Ubuntu public keyring."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SCHEMA = "dm-apt-keyring-bootstrap-v1"
PIN_SCHEMA = "enospc-ubuntu-archive-keyring-pin-v1"
KEY_NAME = "ubuntu-archive-keyring.gpg"
KEY_BYTES = 3607
KEY_SHA256 = "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31"
KEY_SHA512 = "4e344ffbb31f205af8c6db3c260222e4af886af4d5c28462106c579d7ae46f91153340eafad843186d7788370634d8097c117748921455e5bbb219bf08a28a40"
ARCHIVE_SIGNER = "F6ECB3762474EDA9D21B7022871920D1991BC93C!"
PRIMARY_FINGERPRINTS = [
    "790BC7277767219C42C86F933B4FE6ACC0B21F32",
    "843938DF228D22F7B3742BC0D94AA3F0EFE21092",
    "F6ECB3762474EDA9D21B7022871920D1991BC93C",
]
DIRECTORY_NAME = re.compile(r"dm-apt-keyring\.[A-Za-z0-9_-]{6,32}")
RECEIPT_MAX = 16 * 1024
TMP_ROOT = Path("/tmp")


def identity(info: os.stat_result) -> list[int]:
    return [info.st_dev, info.st_ino]


def exact_mode(info: os.stat_result) -> int:
    return stat.S_IMODE(info.st_mode)


def hash_fd(fd: int, cap: int) -> tuple[str, str, int]:
    os.lseek(fd, 0, os.SEEK_SET)
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    total = 0
    while block := os.read(fd, min(65536, cap + 1 - total)):
        total += len(block)
        if total > cap:
            raise RuntimeError("keyring exceeds byte cap")
        sha256.update(block)
        sha512.update(block)
    return sha256.hexdigest(), sha512.hexdigest(), total


def read_json(path: Path, cap: int = RECEIPT_MAX) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > cap:
            raise RuntimeError("JSON input type/size")
        raw = os.read(fd, cap + 1)
        if len(raw) != info.st_size:
            raise RuntimeError("JSON input changed or short read")
    finally:
        os.close(fd)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("JSON input object required")
    return value


def atomic_json(path: Path, value: dict) -> None:
    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(data) > RECEIPT_MAX:
        raise RuntimeError("JSON output cap")
    parent = path.parent
    parent_info = parent.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.getuid() or exact_mode(parent_info) != 0o700):
        raise RuntimeError("receipt parent owner/type/mode")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("JSON output already exists")
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeError("JSON output short write")
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    else:
        os.close(fd)
    try:
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def validate_pin(pin_path: Path) -> dict:
    pin = read_json(pin_path)
    member = pin.get("member")
    primary = pin.get("primary_keys")
    if (pin.get("schema") != PIN_SCHEMA or not isinstance(member, dict)
            or member.get("bytes") != KEY_BYTES or member.get("sha256") != KEY_SHA256
            or member.get("sha512") != KEY_SHA512
            or not isinstance(primary, list) or len(primary) != len(PRIMARY_FINGERPRINTS)
            or not all(isinstance(item, dict) for item in primary)
            or [item.get("fingerprint") for item in primary if isinstance(item, dict)] != PRIMARY_FINGERPRINTS
            or pin.get("subkey_fingerprints") != []
            or pin.get("apt_accepted_signers") != [ARCHIVE_SIGNER]):
        raise RuntimeError("archive-keyring pin mismatch")
    return pin


def validate_tmp() -> tuple[Path, os.stat_result]:
    parent = TMP_ROOT
    info = parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != 0
            or info.st_gid != 0 or exact_mode(info) != 0o1777):
        raise RuntimeError("/tmp owner/type/mode")
    return parent, info


def source_bytes(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != KEY_BYTES:
            raise RuntimeError("vendored keyring type/link/size")
        sha256, sha512, size = hash_fd(fd, KEY_BYTES)
        if (sha256, sha512, size) != (KEY_SHA256, KEY_SHA512, KEY_BYTES):
            raise RuntimeError("vendored keyring bytes mismatch")
        os.lseek(fd, 0, os.SEEK_SET)
        blocks = []
        remaining = KEY_BYTES + 1
        while remaining:
            block = os.read(fd, remaining)
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        data = b"".join(blocks)
        if len(data) != KEY_BYTES:
            raise RuntimeError("vendored keyring short read")
        return data
    finally:
        os.close(fd)


def _validate_receipt_shape(receipt: dict) -> None:
    required = {"schema", "tmp_identity", "directory", "file", "pin", "accepted_signer"}
    if set(receipt) != required or receipt.get("schema") != SCHEMA:
        raise RuntimeError("keyring receipt schema")
    directory = receipt.get("directory")
    file_record = receipt.get("file")
    pin = receipt.get("pin")
    if not all(isinstance(value, dict) for value in (directory, file_record, pin)):
        raise RuntimeError("keyring receipt records")
    path = directory.get("path")
    if (not isinstance(path, str) or Path(path).parent != TMP_ROOT
            or not DIRECTORY_NAME.fullmatch(Path(path).name)):
        raise RuntimeError("keyring receipt directory path")
    if receipt.get("accepted_signer") != ARCHIVE_SIGNER:
        raise RuntimeError("keyring receipt signer")
    if pin != {"bytes": KEY_BYTES, "sha256": KEY_SHA256, "sha512": KEY_SHA512}:
        raise RuntimeError("keyring receipt pin")
    if set(directory) != {"path", "identity", "uid", "gid", "mode"}:
        raise RuntimeError("keyring receipt directory fields")
    if set(file_record) != {"name", "identity", "uid", "gid", "mode", "nlink", "bytes", "sha256", "sha512"}:
        raise RuntimeError("keyring receipt file fields")
    if file_record.get("name") != KEY_NAME:
        raise RuntimeError("keyring receipt filename")


def verify_receipt(receipt_path: Path) -> dict:
    receipt_info = receipt_path.lstat()
    if (not stat.S_ISREG(receipt_info.st_mode) or stat.S_ISLNK(receipt_info.st_mode)
            or receipt_info.st_uid != os.getuid() or exact_mode(receipt_info) != 0o600 or receipt_info.st_nlink != 1):
        raise RuntimeError("keyring receipt identity/owner/mode")
    receipt = read_json(receipt_path)
    _validate_receipt_shape(receipt)
    parent, parent_info = validate_tmp()
    if receipt["tmp_identity"] != identity(parent_info):
        raise RuntimeError("/tmp identity changed")
    directory_path = Path(receipt["directory"]["path"])
    directory_info = directory_path.lstat()
    expected_directory = receipt["directory"]
    if (not stat.S_ISDIR(directory_info.st_mode) or stat.S_ISLNK(directory_info.st_mode)
            or identity(directory_info) != expected_directory["identity"]
            or directory_info.st_uid != expected_directory["uid"] or directory_info.st_gid != expected_directory["gid"]
            or directory_info.st_uid != os.getuid() or directory_info.st_gid != os.getgid()
            or exact_mode(directory_info) != expected_directory["mode"] or exact_mode(directory_info) != 0o755):
        raise RuntimeError("keyring directory identity/owner/mode")
    directory_fd = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(directory_fd)) != expected_directory["identity"]:
            raise RuntimeError("keyring directory path/fd identity")
        names = os.listdir(directory_fd)
        if names != [KEY_NAME]:
            raise RuntimeError("keyring directory contents")
        path_info = os.stat(KEY_NAME, dir_fd=directory_fd, follow_symlinks=False)
        expected_file = receipt["file"]
        if (not stat.S_ISREG(path_info.st_mode) or identity(path_info) != expected_file["identity"]
                or path_info.st_uid != expected_file["uid"] or path_info.st_gid != expected_file["gid"]
                or path_info.st_uid != os.getuid() or path_info.st_gid != os.getgid()
                or exact_mode(path_info) != expected_file["mode"] or exact_mode(path_info) != 0o444
                or path_info.st_nlink != expected_file["nlink"] or path_info.st_nlink != 1
                or path_info.st_size != expected_file["bytes"] or path_info.st_size != KEY_BYTES):
            raise RuntimeError("keyring file identity/owner/mode/link/size")
        file_fd = os.open(KEY_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            file_info = os.fstat(file_fd)
            if identity(file_info) != identity(path_info):
                raise RuntimeError("keyring file path/fd identity")
            sha256, sha512, size = hash_fd(file_fd, KEY_BYTES)
        finally:
            os.close(file_fd)
        if ((sha256, sha512, size) != (KEY_SHA256, KEY_SHA512, KEY_BYTES)
                or sha256 != expected_file["sha256"] or sha512 != expected_file["sha512"]):
            raise RuntimeError("keyring file bytes")
    finally:
        os.close(directory_fd)
    if directory_path.parent != parent:
        raise RuntimeError("keyring directory parent")
    return receipt


def create(source: Path, pin_path: Path, receipt_path: Path) -> dict:
    validate_pin(pin_path)
    data = source_bytes(source)
    parent, parent_info = validate_tmp()
    directory_path: Path | None = None
    try:
        directory_path = Path(tempfile.mkdtemp(prefix="dm-apt-keyring.", dir=parent))
        directory_info = directory_path.lstat()
        if (not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid != os.getuid()
                or directory_info.st_gid != os.getgid() or exact_mode(directory_info) != 0o700
                or not DIRECTORY_NAME.fullmatch(directory_path.name)):
            raise RuntimeError("new keyring directory identity/owner/mode")
        directory_fd = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            file_fd = os.open(KEY_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            try:
                view = memoryview(data)
                while view:
                    written = os.write(file_fd, view)
                    if written <= 0:
                        raise RuntimeError("keyring short write")
                    view = view[written:]
                os.fsync(file_fd)
                if hash_fd(file_fd, KEY_BYTES) != (KEY_SHA256, KEY_SHA512, KEY_BYTES):
                    raise RuntimeError("created keyring readback")
                os.fchmod(file_fd, 0o444)
                os.fsync(file_fd)
            finally:
                os.close(file_fd)
            os.fchmod(directory_fd, 0o755)
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        directory_info = directory_path.lstat()
        file_info = (directory_path / KEY_NAME).lstat()
        receipt = {
            "schema": SCHEMA,
            "tmp_identity": identity(parent_info),
            "directory": {"path": str(directory_path), "identity": identity(directory_info), "uid": directory_info.st_uid,
                          "gid": directory_info.st_gid, "mode": exact_mode(directory_info)},
            "file": {"name": KEY_NAME, "identity": identity(file_info), "uid": file_info.st_uid, "gid": file_info.st_gid,
                     "mode": exact_mode(file_info), "nlink": file_info.st_nlink, "bytes": file_info.st_size,
                     "sha256": KEY_SHA256, "sha512": KEY_SHA512},
            "pin": {"bytes": KEY_BYTES, "sha256": KEY_SHA256, "sha512": KEY_SHA512},
            "accepted_signer": ARCHIVE_SIGNER,
        }
        atomic_json(receipt_path, receipt)
        return verify_receipt(receipt_path)
    except BaseException:
        if directory_path is not None:
            try:
                key_path = directory_path / KEY_NAME
                key_info = key_path.lstat()
                if stat.S_ISREG(key_info.st_mode) and key_info.st_uid == os.getuid() and key_info.st_nlink == 1:
                    key_path.unlink()
                directory_path.rmdir()
            except OSError:
                pass
        raise


def destroy(receipt_path: Path, report_path: Path) -> dict:
    receipt: dict | None = None
    try:
        receipt = verify_receipt(receipt_path)
        directory_path = Path(receipt["directory"]["path"])
        parent, parent_info = validate_tmp()
        if identity(parent_info) != receipt["tmp_identity"] or directory_path.parent != parent:
            raise RuntimeError("keyring cleanup parent identity")
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if identity(os.fstat(parent_fd)) != receipt["tmp_identity"]:
                raise RuntimeError("keyring cleanup parent path/fd identity")
            directory_fd = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if identity(os.fstat(directory_fd)) != receipt["directory"]["identity"]:
                    raise RuntimeError("keyring cleanup directory identity")
                names = os.listdir(directory_fd)
                if names != [KEY_NAME]:
                    raise RuntimeError("keyring cleanup directory contents")
                file_info = os.stat(KEY_NAME, dir_fd=directory_fd, follow_symlinks=False)
                if identity(file_info) != receipt["file"]["identity"] or not stat.S_ISREG(file_info.st_mode):
                    raise RuntimeError("keyring cleanup file identity")
                os.unlink(KEY_NAME, dir_fd=directory_fd)
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            os.rmdir(directory_path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        if directory_path.exists() or directory_path.is_symlink():
            raise RuntimeError("keyring directory remained after cleanup")
        report = {
            "schema": "dm-apt-keyring-cleanup-v1",
            "status": "removed",
            "directory_identity": receipt["directory"]["identity"],
            "file_identity": receipt["file"]["identity"],
            "sha256": KEY_SHA256,
        }
        atomic_json(report_path, report)
        return report
    except BaseException as exc:
        report = {
            "schema": "dm-apt-keyring-cleanup-v1",
            "status": "failed",
            "error": type(exc).__name__ + ": " + str(exc)[:1024],
            "directory_identity": None if receipt is None else receipt["directory"]["identity"],
            "file_identity": None if receipt is None else receipt["file"]["identity"],
            "sha256": KEY_SHA256,
        }
        try:
            atomic_json(report_path, report)
        except BaseException:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--source", type=Path, required=True)
    create_parser.add_argument("--pin", type=Path, required=True)
    create_parser.add_argument("--receipt", type=Path, required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--receipt", type=Path, required=True)
    path_parser = sub.add_parser("path")
    path_parser.add_argument("--receipt", type=Path, required=True)
    destroy_parser = sub.add_parser("destroy")
    destroy_parser.add_argument("--receipt", type=Path, required=True)
    destroy_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "create":
        create(args.source, args.pin, args.receipt)
    elif args.operation == "verify":
        verify_receipt(args.receipt)
    elif args.operation == "path":
        receipt = verify_receipt(args.receipt)
        print(str(Path(receipt["directory"]["path"]) / KEY_NAME))
    else:
        destroy(args.receipt, args.report)


if __name__ == "__main__":
    main()
