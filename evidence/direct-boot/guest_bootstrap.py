"""Offline first-boot inventory. This file is injected verbatim into NoCloud."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

FRAME_MAX = 64 * 1024
FILE_MAX = 256 * 1024 * 1024
CONFIG = Path("/var/lib/dm-direct-boot/config.json")
DMI_BINDING = Path("/sys/class/dmi/id/product_serial")
BINDING_TRANSPORT = "qemu-smbios-type1-product-serial-v1"
SERIAL = Path("/dev/ttyS0")
TOOLS = (
    "/usr/bin/python3",
    "/usr/bin/cloud-init",
    "/usr/bin/dpkg-query",
    "/usr/bin/systemctl",
    "/usr/bin/sha256sum",
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def bounded_read(path: Path, cap: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            raise RuntimeError("file type/size")
        out = bytearray()
        while True:
            block = os.read(fd, min(65536, cap + 1 - len(out)))
            if not block:
                return bytes(out)
            out.extend(block)
            if len(out) > cap:
                raise RuntimeError("file growth")
    finally:
        os.close(fd)


def sha_file(path: Path) -> tuple[str, int]:
    data = bounded_read(path, FILE_MAX)
    return hashlib.sha256(data).hexdigest(), len(data)


def dmi_binding(path: Path = DMI_BINDING) -> str:
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != 0o400
        or before.st_nlink != 1
    ):
        raise RuntimeError("DMI binding metadata")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink,
        )
        if identity(opened) != identity(before):
            raise RuntimeError("DMI binding identity")
        raw = bytearray()
        while len(raw) <= 256:
            block = os.read(fd, 257 - len(raw))
            if not block:
                break
            raw.extend(block)
        if len(raw) > 256:
            raise RuntimeError("DMI binding cap")
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    after_path = os.lstat(path)
    if identity(after_fd) != identity(opened) or identity(after_path) != identity(opened):
        raise RuntimeError("DMI binding changed")
    if (
        len(raw) != 65
        or raw[-1:] != b"\n"
        or any(byte not in b"0123456789abcdef" for byte in raw[:64])
    ):
        raise RuntimeError("DMI binding bytes")
    return bytes(raw[:64]).decode("ascii")


def package_owner(path: str) -> dict | None:
    proc = subprocess.run(
        ["/usr/bin/dpkg-query", "-S", path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        timeout=3,
        check=False,
    )
    if proc.returncode or len(proc.stdout) > 4096:
        return None
    package = proc.stdout.decode("utf-8", "strict").split(":", 1)[0]
    if not package or len(package) > 128:
        return None
    version = subprocess.run(
        ["/usr/bin/dpkg-query", "-W", "-f=${Version}", package],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        timeout=3,
        check=False,
    )
    if version.returncode or len(version.stdout) > 512:
        return {"package": package, "version": None}
    return {"package": package, "version": version.stdout.decode("utf-8", "strict")}


def tool_fact(raw: str) -> dict:
    requested = Path(raw)
    try:
        resolved = requested.resolve(strict=True)
    except FileNotFoundError:
        return {"requested": raw, "resolved": None, "sha256": None, "bytes": None, "mode": None, "owner": None}
    digest, size = sha_file(resolved)
    st = resolved.stat()
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError("not regular")
    return {
        "requested": raw,
        "resolved": str(resolved),
        "sha256": digest,
        "bytes": size,
        "mode": stat.S_IMODE(st.st_mode),
        "owner": package_owner(str(resolved)),
    }


def main() -> None:
    config = json.loads(bounded_read(CONFIG, 8192))
    if set(config) != {"schema", "nonce", "base_sha256", "source_sha256", "binding_transport"}:
        raise RuntimeError("config fields")
    if config["schema"] != "dm-direct-boot-guest-config-v2" or config["binding_transport"] != BINDING_TRANSPORT:
        raise RuntimeError("config transport")
    source = Path(__file__).resolve(strict=True)
    source_sha, _ = sha_file(source)
    if source_sha != config["source_sha256"]:
        raise RuntimeError("injected source hash")
    binding = dmi_binding()
    release = platform.release()
    inventory = [tool_fact(path) for path in TOOLS]
    inventory.extend(tool_fact(path) for path in ("/boot/vmlinuz-" + release, "/boot/config-" + release))
    cmdline = bounded_read(Path("/proc/cmdline"), 8192)
    receipt = {
        "schema": "dm-direct-boot-result-v2",
        "result": "measured",
        "scope": "offline-bootstrap-only-no-product-no-g0",
        "nonce": config["nonce"],
        "binding": binding,
        "binding_transport": BINDING_TRANSPORT,
        "source_sha256": source_sha,
        "uname": list(os.uname()),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "python": sys.version,
        "cmdline_sha256": hashlib.sha256(cmdline).hexdigest(),
        "tools": inventory,
    }
    payload = canonical(receipt)
    if not 0 < len(payload) <= FRAME_MAX:
        raise RuntimeError("result frame cap")
    line = b"\nDMFRAME3 " + str(len(payload)).encode() + b" " + hashlib.sha256(payload).hexdigest().encode() + b" " + payload + b"\n"
    fd = os.open(SERIAL, os.O_WRONLY | os.O_NOCTTY)
    try:
        written = 0
        while written < len(line):
            count = os.write(fd, line[written:])
            if count <= 0:
                raise RuntimeError("serial write")
            written += count
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
