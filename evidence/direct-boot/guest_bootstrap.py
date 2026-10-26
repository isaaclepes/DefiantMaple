"""Offline first-boot inventory. This file is injected verbatim into NoCloud."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import selectors
import stat
import subprocess
import sys
import time
from pathlib import Path

FRAME_MAX = 64 * 1024
FILE_MAX = 256 * 1024 * 1024
DIAG_MAX = 32 * 1024
CONFIG_MAX = 1 * 1024 * 1024
PROC_MODULES_MAX = 1 * 1024 * 1024
MODULE_MAX = 8 * 1024 * 1024
MODULE_AGGREGATE_MAX = 16 * 1024 * 1024
LINK_MAX = 512
ATTR_MAX = 128
BY_KEY_SCAN_MAX = 256
BY_KEY_VALID_MAX = 128
BY_KEY_ATTR_AGGREGATE_MAX = 24 * 1024
ACPI_SCAN_MAX = 1024
ACPI_MATCH_MAX = 8
MODULE_SCAN_MAX = 1024
MODULE_MATCH_MAX = 8
QUERY_STREAM_MAX = 4096
QUERY_TIMEOUT = 3.0
CONFIG = Path("/var/lib/dm-direct-boot/config.json")
FW_BINDING = Path("/sys/firmware/qemu_fw_cfg/by_name/opt/dm/binding/raw")
SERIAL = Path("/dev/ttyS0")
FW_ROOT = Path("/sys/firmware/qemu_fw_cfg")
ACPI_DEVICES = Path("/sys/bus/acpi/devices")
PROC_MODULES = Path("/proc/modules")
MODULE_SYSFS = Path("/sys/module/qemu_fw_cfg")
BOOT_ROOT = Path("/boot")
MODULES_ROOT = Path("/lib/modules")
RELEASE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+\-]{0,127}")
DECIMAL_SELECTOR = re.compile(r"[0-9]{1,5}")
DECIMAL_U32 = re.compile(r"[0-9]{1,10}")
ACPI_NAME = re.compile(r"QEMU0002:[0-9A-Fa-f]{2}")
MODULE_BASENAME = re.compile(r"qemu_fw_cfg\.ko(?:\.(?:gz|xz|zst))?")
PACKAGE_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]{0,127}(?::[a-z0-9][a-z0-9-]{0,31})?")
PACKAGE_VERSION = re.compile(r"[0-9A-Za-z.+:~\-]{1,512}")
TOOLS = (
    "/usr/bin/python3",
    "/usr/bin/cloud-init",
    "/usr/bin/dpkg-query",
    "/usr/bin/systemctl",
    "/usr/bin/sha256sum",
)


class DiagnosticCap(RuntimeError):
    pass


class DiagnosticChanged(RuntimeError):
    pass


class DiagnosticType(RuntimeError):
    pass


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


def mode_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def stat_value(st: os.stat_result) -> dict:
    return {
        "device": st.st_dev,
        "inode": st.st_ino,
        "mode": stat.S_IMODE(st.st_mode),
        "type": mode_type(st.st_mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "nlink": st.st_nlink,
        "size": st.st_size,
    }


def error_value(exc: BaseException) -> dict:
    if isinstance(exc, DiagnosticCap):
        status_value = "cap"
    elif isinstance(exc, DiagnosticChanged):
        status_value = "changed"
    elif isinstance(exc, DiagnosticType):
        status_value = "wrong-type"
    elif isinstance(exc, OSError):
        status_value = "unreadable"
    else:
        status_value = "unreadable"
    value = {"status": status_value, "error_type": type(exc).__name__}
    number = getattr(exc, "errno", None)
    if isinstance(number, int):
        value["errno"] = number
    return value


def path_fact(path: Path, allowed_follow_root: Path | None = None) -> dict:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {"status": "missing"}
    except OSError as exc:
        return error_value(exc)
    value = {"status": "ok", "lstat": stat_value(before)}
    if stat.S_ISLNK(before.st_mode):
        try:
            target = os.readlink(path)
        except OSError as exc:
            return {**value, **error_value(exc)}
        if len(os.fsencode(target)) > LINK_MAX:
            return {**value, "status": "cap", "target_bytes_over": LINK_MAX}
        value["target"] = target
        if allowed_follow_root is None:
            try:
                after = path.lstat()
            except OSError as exc:
                return {**value, **error_value(exc)}
            if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
                value["status"] = "changed"
            return value
        try:
            resolved = path.resolve(strict=True)
            root = allowed_follow_root.resolve(strict=True)
        except OSError as exc:
            failure = error_value(exc)
            value.update(failure)
            value["followed"] = failure
            try:
                after = path.lstat()
            except OSError as after_exc:
                return {**value, **error_value(after_exc)}
            if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
                value["status"] = "changed"
            return value
        else:
            if resolved != root and root not in resolved.parents:
                value["status"] = "wrong-type"
                value["followed"] = {"status": "wrong-type", "reason": "outside-root"}
                try:
                    after = path.lstat()
                except OSError as exc:
                    return {**value, **error_value(exc)}
                if (before.st_dev, before.st_ino, before.st_mode) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_mode,
                ):
                    value["status"] = "changed"
                return value
    try:
        followed = path.stat()
    except FileNotFoundError:
        value["followed"] = {"status": "missing"}
    except OSError as exc:
        value["followed"] = error_value(exc)
    else:
        value["followed"] = stat_value(followed)
    try:
        after = path.lstat()
    except OSError as exc:
        return {**value, **error_value(exc)}
    if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
        value["status"] = "changed"
    return value


def open_stable_directory(path: Path) -> tuple[int, os.stat_result, Path]:
    before = path.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise DiagnosticType("diagnostic directory type")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (before.st_dev, before.st_ino, before.st_mode)
            != (opened.st_dev, opened.st_ino, opened.st_mode)
        ):
            raise DiagnosticChanged("diagnostic directory changed before scan")
    except BaseException:
        os.close(fd)
        raise
    return fd, opened, Path("/proc/self/fd") / str(fd)


def close_stable_directory(path: Path, fd: int, opened: os.stat_result) -> None:
    try:
        held_after = os.fstat(fd)
        path_after = path.lstat()
    finally:
        os.close(fd)
    expected = (opened.st_dev, opened.st_ino, opened.st_mode)
    if (
        (held_after.st_dev, held_after.st_ino, held_after.st_mode) != expected
        or (path_after.st_dev, path_after.st_ino, path_after.st_mode) != expected
    ):
        raise DiagnosticChanged("diagnostic directory changed during scan")


def stable_file(path: Path, cap: int) -> tuple[bytes, dict]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise DiagnosticType("diagnostic file type")
        out = bytearray()
        while True:
            block = os.read(fd, min(65536, cap + 1 - len(out)))
            if not block:
                break
            out.extend(block)
            if len(out) > cap:
                raise DiagnosticCap("diagnostic file cap")
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (before.st_dev, before.st_ino, before.st_mode, before.st_size) != (
        after.st_dev, after.st_ino, after.st_mode, after.st_size
    ):
        raise DiagnosticChanged("diagnostic file changed")
    return bytes(out), {
        "status": "ok",
        **stat_value(after),
        "sha256": hashlib.sha256(out).hexdigest(),
        "bytes": len(out),
    }


def stable_path_file(path: Path, cap: int) -> tuple[bytes, dict]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise DiagnosticType("diagnostic path file type")
    raw, fact = stable_file(path, cap)
    after = path.lstat()
    expected = (before.st_dev, before.st_ino, before.st_mode, before.st_nlink, before.st_size)
    opened = (
        fact["device"],
        fact["inode"],
        stat.S_IFREG | fact["mode"],
        fact["nlink"],
        fact["size"],
    )
    final = (after.st_dev, after.st_ino, after.st_mode, after.st_nlink, after.st_size)
    if expected != opened or expected != final:
        raise DiagnosticChanged("diagnostic path file changed")
    return raw, fact


def sysfs_attr(path: Path, cap: int = ATTR_MAX) -> dict:
    try:
        raw, fact = stable_path_file(path, cap)
    except FileNotFoundError:
        return {"status": "missing"}
    except (OSError, RuntimeError) as exc:
        return error_value(exc)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        return {"status": "malformed", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        text = raw[:-1].decode("ascii", "strict")
    except UnicodeError:
        return {"status": "malformed", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return {"status": "ok", "value": text, "bytes": fact["bytes"], "sha256": fact["sha256"]}


def config_fact(release: str) -> dict:
    path = BOOT_ROOT / ("config-" + release)
    try:
        raw, fact = stable_path_file(path, CONFIG_MAX)
    except FileNotFoundError:
        return {"status": "missing"}
    except (OSError, RuntimeError) as exc:
        return error_value(exc)
    if fact["uid"] != 0 or fact["type"] != "regular" or fact["mode"] & 0o022:
        return {"status": "wrong-metadata", "file": fact}
    if raw and not raw.endswith(b"\n"):
        return {"status": "malformed", "file": fact}
    try:
        lines = raw.decode("ascii", "strict").splitlines()
    except UnicodeError:
        return {"status": "malformed", "file": fact}
    values = {}
    for key in ("CONFIG_FW_CFG_SYSFS", "CONFIG_FW_CFG_SYSFS_CMDLINE"):
        matches = [line for line in lines if line.startswith(key + "=") or line == "# " + key + " is not set"]
        if len(matches) == 0:
            values[key] = {"status": "missing"}
        elif len(matches) != 1:
            values[key] = {"status": "duplicate", "count": len(matches)}
        elif matches[0] == "# " + key + " is not set":
            values[key] = {"status": "ok", "value": "n"}
        else:
            candidate = matches[0].split("=", 1)[1]
            values[key] = (
                {"status": "ok", "value": candidate}
                if candidate in {"y", "m", "n"}
                else {"status": "malformed"}
            )
    return {"status": "ok", "file": fact, "values": values}


def scan_by_key() -> dict:
    root = FW_ROOT / "by_key"
    try:
        directory_fd, directory_identity, held_root = open_stable_directory(root)
    except FileNotFoundError:
        return {"status": "missing", "entries": []}
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "entries": []}
    total = 0
    valid = 0
    attr_bytes = 0
    entries = []
    status_value = "ok"
    scan_error = None
    try:
        with os.scandir(directory_fd) as iterator:
            for entry in iterator:
                total += 1
                if total > BY_KEY_SCAN_MAX:
                    status_value = "cap"
                    break
                name = entry.name
                if not DECIMAL_SELECTOR.fullmatch(name) or int(name) > 65535 or str(int(name)) != name:
                    continue
                valid += 1
                if valid > BY_KEY_VALID_MAX:
                    status_value = "cap"
                    break
                child = held_root / name
                child_fact = path_fact(child)
                record = {"selector": name, "path": child_fact}
                if (
                    child_fact.get("status") != "ok"
                    or child_fact.get("lstat", {}).get("type") != "directory"
                ):
                    record["coherent"] = False
                    entries.append(record)
                    continue
                for attribute in ("key", "name", "size"):
                    attr = sysfs_attr(child / attribute)
                    record[attribute] = attr
                    attr_bytes += attr.get("bytes", 0)
                if attr_bytes > BY_KEY_ATTR_AGGREGATE_MAX:
                    status_value = "cap"
                    entries.append(record)
                    break
                key_value = record["key"].get("value")
                size_value = record["size"].get("value")
                size_coherent = (
                    record["size"].get("status") == "ok"
                    and isinstance(size_value, str)
                    and DECIMAL_U32.fullmatch(size_value) is not None
                    and int(size_value) <= 4294967295
                    and str(int(size_value)) == size_value
                )
                record["coherent"] = (
                    record["key"].get("status") == "ok"
                    and key_value == name
                    and record["name"].get("status") == "ok"
                    and size_coherent
                )
                if record["name"].get("status") == "ok" and record["name"].get("value") == "opt/dm/binding":
                    record["binding_raw"] = path_fact(child / "raw")
                entries.append(record)
    except OSError as exc:
        scan_error = exc
    try:
        close_stable_directory(root, directory_fd, directory_identity)
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "total_seen": total, "valid_seen": valid, "entries": entries}
    if scan_error is not None:
        return {**error_value(scan_error), "total_seen": total, "valid_seen": valid, "entries": entries}
    entries.sort(key=lambda item: int(item["selector"]))
    return {
        "status": status_value,
        "directory": stat_value(directory_identity),
        "total_seen": total,
        "valid_seen": valid,
        "attribute_bytes": attr_bytes,
        "entries": entries,
    }


def scan_acpi() -> dict:
    try:
        directory_fd, directory_identity, held_root = open_stable_directory(ACPI_DEVICES)
    except FileNotFoundError:
        return {"status": "missing", "matches": []}
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "matches": []}
    total = 0
    matches = []
    status_value = "ok"
    scan_error = None
    try:
        with os.scandir(directory_fd) as iterator:
            for entry in iterator:
                total += 1
                if total > ACPI_SCAN_MAX:
                    status_value = "cap"
                    break
                if not ACPI_NAME.fullmatch(entry.name):
                    continue
                if len(matches) >= ACPI_MATCH_MAX:
                    status_value = "cap"
                    break
                child = held_root / entry.name
                matches.append(
                    {
                        "name": entry.name,
                        "path": path_fact(child),
                        "status_attr": sysfs_attr(child / "status", 4096),
                        "modalias": sysfs_attr(child / "modalias", 4096),
                        "driver": path_fact(child / "driver"),
                        "physical_node": path_fact(child / "physical_node"),
                    }
                )
    except OSError as exc:
        scan_error = exc
    try:
        close_stable_directory(ACPI_DEVICES, directory_fd, directory_identity)
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "total_seen": total, "matches": matches}
    if scan_error is not None:
        return {**error_value(scan_error), "total_seen": total, "matches": matches}
    matches.sort(key=lambda item: item["name"])
    return {
        "status": status_value,
        "directory": stat_value(directory_identity),
        "total_seen": total,
        "matches": matches,
    }


def proc_modules_fact() -> dict:
    try:
        raw, fact = stable_file(PROC_MODULES, PROC_MODULES_MAX)
    except (OSError, RuntimeError) as exc:
        return error_value(exc)
    if raw and not raw.endswith(b"\n"):
        return {"status": "malformed", "file": fact}
    try:
        lines = raw.decode("ascii", "strict").splitlines()
    except UnicodeError:
        return {"status": "malformed", "file": fact}
    matches = [line for line in lines if line.split(" ", 1)[0] == "qemu_fw_cfg"]
    if any(len(line.encode("ascii")) > 512 for line in matches):
        return {"status": "cap", "count": len(matches), "file": fact}
    malformed = [line for line in matches if len(line.split()) < 6]
    if malformed:
        status_value = "malformed"
    elif len(matches) > 1:
        status_value = "duplicate"
    else:
        status_value = "ok"
    return {"status": status_value, "count": len(matches), "rows": matches, "file": fact}


def module_files_fact(release: str) -> dict:
    parent = MODULES_ROOT / release / "kernel/drivers/firmware"
    try:
        directory_fd, directory_identity, held_parent = open_stable_directory(parent)
    except FileNotFoundError:
        return {"status": "missing", "files": []}
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "files": []}
    try:
        canonical_parent = parent.resolve(strict=True)
        canonical_modules_root = MODULES_ROOT.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        os.close(directory_fd)
        return {**error_value(exc), "files": []}
    expected_parent = canonical_modules_root / release / "kernel/drivers/firmware"
    if not canonical_parent.is_absolute() or canonical_parent != expected_parent:
        os.close(directory_fd)
        return {"status": "wrong-type", "reason": "parent-path-escape", "files": []}
    if len(os.fsencode(str(canonical_parent))) > LINK_MAX:
        os.close(directory_fd)
        return {"status": "cap", "files": []}
    total = 0
    aggregate = 0
    files = []
    status_value = "ok"
    scan_error = None
    try:
        with os.scandir(directory_fd) as iterator:
            for entry in iterator:
                total += 1
                if total > MODULE_SCAN_MAX:
                    status_value = "cap"
                    break
                if not MODULE_BASENAME.fullmatch(entry.name):
                    continue
                if len(files) >= MODULE_MATCH_MAX:
                    status_value = "cap"
                    break
                requested_path = parent / entry.name
                held_path = held_parent / entry.name
                requested = str(requested_path)
                try:
                    canonical_path = requested_path.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    files.append({"name": entry.name, "requested": requested, "canonical": None, **error_value(exc)})
                    continue
                if (
                    not canonical_path.is_absolute()
                    or canonical_path.parent != canonical_parent
                    or canonical_path.name != entry.name
                    or len(os.fsencode(str(canonical_path))) > LINK_MAX
                ):
                    files.append(
                        {
                            "name": entry.name,
                            "requested": requested,
                            "canonical": str(canonical_path),
                            "status": "wrong-type",
                        }
                    )
                    continue
                try:
                    raw, fact = stable_path_file(held_path, MODULE_MAX)
                except (OSError, RuntimeError) as exc:
                    files.append(
                        {
                            "name": entry.name,
                            "requested": requested,
                            "canonical": str(canonical_path),
                            **error_value(exc),
                        }
                    )
                    continue
                aggregate += len(raw)
                if aggregate > MODULE_AGGREGATE_MAX:
                    files.append(
                        {
                            "name": entry.name,
                            "requested": requested,
                            "canonical": str(canonical_path),
                            "status": "cap",
                            "bytes": len(raw),
                        }
                    )
                    status_value = "cap"
                    break
                files.append(
                    {
                        "name": entry.name,
                        "requested": requested,
                        "canonical": str(canonical_path),
                        **fact,
                    }
                )
    except OSError as exc:
        scan_error = exc
    try:
        close_stable_directory(parent, directory_fd, directory_identity)
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "total_seen": total, "files": files}
    if scan_error is not None:
        return {**error_value(scan_error), "total_seen": total, "files": files}
    files.sort(key=lambda item: item["name"])
    return {
        "status": status_value,
        "directory": stat_value(directory_identity),
        "total_seen": total,
        "aggregate_bytes": aggregate,
        "files": files,
    }


def diagnostic_tool_fact(raw: str) -> dict:
    requested = Path(raw)
    requested_fact = path_fact(requested)
    try:
        resolved = requested.resolve(strict=True)
    except FileNotFoundError:
        return {"status": "missing", "requested": requested_fact, "resolved": None}
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "requested": requested_fact, "resolved": None}
    if not resolved.is_absolute() or len(os.fsencode(str(resolved))) > LINK_MAX:
        return {"status": "cap", "requested": requested_fact, "resolved": None}
    try:
        raw_bytes, fact = stable_path_file(resolved, MODULE_MAX)
    except (OSError, RuntimeError) as exc:
        return {**error_value(exc), "requested": requested_fact, "resolved": str(resolved)}
    status_value = "ok" if fact["uid"] == 0 and not fact["mode"] & 0o022 else "wrong-metadata"
    owner = diagnostic_package_owner(str(resolved))
    requested_after = path_fact(requested)
    try:
        verify_bytes, verify_fact = stable_path_file(resolved, MODULE_MAX)
    except (OSError, RuntimeError) as exc:
        return {
            **error_value(exc),
            "requested": requested_fact,
            "requested_after": requested_after,
            "resolved": str(resolved),
            "file": fact,
            "owner": owner,
        }
    before_lstat = requested_fact.get("lstat", {})
    after_lstat = requested_after.get("lstat", {})
    if (
        requested_fact.get("status") != "ok"
        or requested_after.get("status") != "ok"
        or any(before_lstat.get(key) != after_lstat.get(key) for key in ("device", "inode", "mode", "type"))
        or any(fact.get(key) != verify_fact.get(key) for key in ("device", "inode", "mode", "size", "sha256"))
        or raw_bytes != verify_bytes
    ):
        status_value = "changed"
    return {
        "status": status_value,
        "requested": requested_fact,
        "requested_after": requested_after,
        "resolved": str(resolved),
        "file": fact,
        "file_after": verify_fact,
        "owner": owner,
        "bytes_read": len(raw_bytes) + len(verify_bytes),
    }


def bounded_query(argv: list[str]) -> dict:
    started = time.monotonic()
    try:
        child = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            close_fds=True,
        )
    except OSError as exc:
        return {"status": "unreadable", "error_type": type(exc).__name__, "errno": exc.errno}
    if child.stdout is None or child.stderr is None:
        child.kill()
        child.wait()
        return {"status": "unreadable", "error_type": "MissingPipe"}
    selector = selectors.DefaultSelector()
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = set()
    incomplete = set()
    timed_out = False
    try:
        for name, pipe in (("stdout", child.stdout), ("stderr", child.stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        deadline = started + QUERY_TIMEOUT
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready = selector.select(remaining)
            if not ready:
                timed_out = True
                break
            for key, _ in ready:
                name = key.data
                room = QUERY_STREAM_MAX + 1 - len(streams[name])
                try:
                    block = os.read(key.fd, min(65536, max(1, room)))
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                streams[name].extend(block)
                if len(streams[name]) > QUERY_STREAM_MAX:
                    overflow.add(name)
                    selector.unregister(key.fileobj)
            if overflow:
                break
        if timed_out or overflow:
            incomplete.update(key.data for key in selector.get_map().values())
            child.kill()
        try:
            returncode = child.wait(timeout=max(0.0, started + QUERY_TIMEOUT - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            returncode = child.wait(timeout=1)
    except BaseException:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=1)
        raise
    finally:
        selector.close()
        child.stdout.close()
        child.stderr.close()
    result = {
        "status": "ok",
        "argv": argv,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout_bytes": min(len(streams["stdout"]), QUERY_STREAM_MAX),
        "stderr_bytes": min(len(streams["stderr"]), QUERY_STREAM_MAX),
        "stdout_sha256": hashlib.sha256(streams["stdout"][:QUERY_STREAM_MAX]).hexdigest(),
        "stderr_sha256": hashlib.sha256(streams["stderr"][:QUERY_STREAM_MAX]).hexdigest(),
        "truncated": sorted(overflow),
        "incomplete": sorted(incomplete),
    }
    result["_stdout"] = bytes(streams["stdout"][:QUERY_STREAM_MAX])
    result["_stderr"] = bytes(streams["stderr"][:QUERY_STREAM_MAX])
    return result


def diagnostic_package_owner(path: str) -> dict:
    owner_query = bounded_query(["/usr/bin/dpkg-query", "-S", path])
    owner_stdout = owner_query.pop("_stdout", b"")
    owner_stderr = owner_query.pop("_stderr", b"")
    owner_record = {"status": "unreadable", "query": owner_query, "package": None, "version": None}
    if (
        owner_query.get("status") != "ok"
        or owner_query["returncode"] != 0
        or owner_query["timed_out"]
        or owner_query["truncated"]
        or owner_query["incomplete"]
        or owner_stderr
        or owner_stdout.count(b"\n") != 1
        or not owner_stdout.endswith(b"\n")
    ):
        return owner_record
    try:
        owner_line = owner_stdout[:-1].decode("ascii", "strict")
    except UnicodeError:
        return owner_record
    separator = ": "
    if separator not in owner_line:
        return owner_record
    package, owned_path = owner_line.split(separator, 1)
    if not PACKAGE_NAME.fullmatch(package) or owned_path != path:
        return owner_record
    version_query = bounded_query(["/usr/bin/dpkg-query", "-W", "-f=${Version}\\n", package])
    version_stdout = version_query.pop("_stdout", b"")
    version_stderr = version_query.pop("_stderr", b"")
    owner_record["package"] = package
    owner_record["version_query"] = version_query
    if (
        version_query.get("status") != "ok"
        or version_query["returncode"] != 0
        or version_query["timed_out"]
        or version_query["truncated"]
        or version_query["incomplete"]
        or version_stderr
        or version_stdout.count(b"\n") != 1
        or not version_stdout.endswith(b"\n")
    ):
        return owner_record
    try:
        version = version_stdout[:-1].decode("ascii", "strict")
    except UnicodeError:
        return owner_record
    if PACKAGE_VERSION.fullmatch(version):
        owner_record["version"] = version
        owner_record["status"] = "ok"
    return owner_record


def snapshot_complete(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("status") in {"unreadable", "cap", "changed", "malformed"}:
            return False
        return all(snapshot_complete(item) for item in value.values())
    if isinstance(value, list):
        return all(snapshot_complete(item) for item in value)
    return True


def collect_fwcfg_diagnostic(config: dict, source_sha: str) -> dict:
    release = platform.release()
    release_valid = RELEASE.fullmatch(release) is not None
    facts = {
        "release": {"status": "ok", "value": release} if release_valid else {"status": "malformed"},
        "kernel_config": config_fact(release) if release_valid else {"status": "not-collected-invalid-release"},
        "hierarchy": {
            str(path): path_fact(path, FW_ROOT)
            for path in (
                FW_ROOT,
                FW_ROOT / "by_key",
                FW_ROOT / "by_name",
                FW_ROOT / "by_name/opt",
                FW_ROOT / "by_name/opt/dm",
                FW_ROOT / "by_name/opt/dm/binding",
                FW_BINDING,
            )
        },
        "by_key": scan_by_key(),
        "acpi": scan_acpi(),
        "module_sysfs": path_fact(MODULE_SYSFS),
        "proc_modules": proc_modules_fact(),
        "module_files": (
            module_files_fact(release)
            if release_valid
            else {"status": "not-collected-invalid-release", "files": []}
        ),
        "modprobe": diagnostic_tool_fact("/usr/sbin/modprobe"),
    }
    value = {
        "schema": "dm-fwcfg-diagnostic-v1",
        "claim": "guest-self-report-only-not-attestation-not-success",
        "nonce": config["nonce"],
        "base_sha256": config["base_sha256"],
        "source_sha256": source_sha,
        "expected_name": "opt/dm/binding",
        "expected_path": str(FW_BINDING),
        "capture_valid": snapshot_complete(facts),
        "facts": facts,
    }
    payload = canonical(value)
    if 0 < len(payload) <= DIAG_MAX:
        return value
    return {
        "schema": "dm-fwcfg-diagnostic-v1",
        "claim": "guest-self-report-only-not-attestation-not-success",
        "nonce": config["nonce"],
        "base_sha256": config["base_sha256"],
        "source_sha256": source_sha,
        "expected_name": "opt/dm/binding",
        "expected_path": str(FW_BINDING),
        "capture_valid": False,
        "facts": {
            "status": "cap",
            "uncapped_bytes": len(payload),
            "uncapped_sha256": hashlib.sha256(payload).hexdigest(),
        },
    }


def emit_fwcfg_diagnostic(value: dict) -> None:
    payload = canonical(value)
    if not 0 < len(payload) <= DIAG_MAX:
        raise RuntimeError("fw_cfg diagnostic cap")
    line = (
        b"\nDMFWCFGDIAG1 "
        + str(len(payload)).encode()
        + b" "
        + hashlib.sha256(payload).hexdigest().encode()
        + b" "
        + payload
        + b"\n"
    )
    fd = os.open(SERIAL, os.O_WRONLY | os.O_NOCTTY)
    try:
        written = 0
        while written < len(line):
            count = os.write(fd, line[written:])
            if count <= 0:
                raise RuntimeError("diagnostic serial write")
            written += count
    finally:
        os.close(fd)


def main() -> None:
    config = json.loads(bounded_read(CONFIG, 8192))
    if set(config) != {"schema", "nonce", "base_sha256", "source_sha256"}:
        raise RuntimeError("config fields")
    source = Path(__file__).resolve(strict=True)
    source_sha, _ = sha_file(source)
    if source_sha != config["source_sha256"]:
        raise RuntimeError("injected source hash")
    emit_fwcfg_diagnostic(collect_fwcfg_diagnostic(config, source_sha))
    binding = bounded_read(FW_BINDING, 256).rstrip(b"\x00").decode("ascii")
    if len(binding) != 64 or any(c not in "0123456789abcdef" for c in binding):
        raise RuntimeError("fw_cfg binding")
    release = platform.release()
    inventory = [tool_fact(path) for path in TOOLS]
    inventory.extend(tool_fact(path) for path in ("/boot/vmlinuz-" + release, "/boot/config-" + release))
    cmdline = bounded_read(Path("/proc/cmdline"), 8192)
    receipt = {
        "schema": "dm-direct-boot-result-v1",
        "result": "measured",
        "scope": "offline-bootstrap-only-no-product-no-g0",
        "nonce": config["nonce"],
        "binding": binding,
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
