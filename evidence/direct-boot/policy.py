"""Pure, fail-closed policy helpers for the direct-QEMU boot proposal."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

GIB = 1024**3
MIB = 1024**2
IMAGE_URL = (
    "https://cloud-images.ubuntu.com/releases/noble/release-20261017/"
    "ubuntu-24.04-server-cloudimg-amd64.img"
)
IMAGE_SHA256 = "04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94"
IMAGE_MAX = 1536 * MIB
OVERLAY_MAX = GIB
SEED_MAX = 4 * MIB
SERIAL_MAX = 4 * MIB
STREAM_MAX = MIB
EVIDENCE_MAX = 8 * MIB
FRAME_MAX = 64 * 1024
VIRTUAL_MAX = 8 * GIB
FREE_FLOOR = 3 * GIB

HEX64 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def charge_stream(total: int, incoming: int, cap: int) -> int:
    if any(not isinstance(value, int) or isinstance(value, bool) for value in (total, incoming, cap)):
        raise ValueError("stream ledger types")
    if total < 0 or incoming < 0 or cap <= 0 or total > cap - incoming:
        raise ValueError("cumulative stream cap")
    return total + incoming


def sha_file(path: Path, cap: int) -> tuple[str, int]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            raise RuntimeError(f"unsupported file or size: {path.name}")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 64 * 1024)
            if not block:
                break
            total += len(block)
            if total > cap:
                raise RuntimeError(f"file grew beyond cap: {path.name}")
            digest.update(block)
        return digest.hexdigest(), total
    finally:
        os.close(fd)


def boot_binding(document: dict) -> str:
    required = {
        "schema", "nonce", "base_sha256", "guest_source_sha256", "seed_sha256",
        "overlay_initial_sha256", "argv_template", "machine", "memory_mib", "cpus",
    }
    if set(document) != required or document["schema"] != "dm-direct-boot-config-v1":
        raise ValueError("boot config fields")
    if not NONCE.fullmatch(document["nonce"]):
        raise ValueError("nonce")
    for key in ("base_sha256", "guest_source_sha256", "seed_sha256", "overlay_initial_sha256"):
        if not HEX64.fullmatch(document[key]):
            raise ValueError(key)
    argv = document["argv_template"]
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv) or sum(item.count("<CONFIG_BINDING>") for item in argv) != 1:
        raise ValueError("argv binding placeholder")
    return sha_bytes(canonical(document))


def parse_frame(stream: bytes, *, nonce: str, binding: str, guest_source_sha256: str) -> dict:
    """Extract exactly one bounded guest frame from otherwise untrusted serial bytes."""
    if len(stream) > SERIAL_MAX:
        raise ValueError("serial cap")
    prefix = b"DMFRAME3 "
    candidates = [line for line in stream.splitlines() if line.startswith(prefix)]
    if len(candidates) != 1:
        raise ValueError("guest frame count")
    parts = candidates[0].split(b" ", 3)
    if len(parts) != 4 or parts[0] != b"DMFRAME3":
        raise ValueError("guest frame syntax")
    try:
        length = int(parts[1].decode("ascii"))
        claimed = parts[2].decode("ascii")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("guest frame header") from exc
    payload = parts[3]
    if length != len(payload) or not 0 < length <= FRAME_MAX or not HEX64.fullmatch(claimed):
        raise ValueError("guest frame length/digest syntax")
    if sha_bytes(payload) != claimed:
        raise ValueError("guest frame digest")
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("guest frame JSON") from exc
    required = {
        "schema", "result", "scope", "nonce", "binding", "source_sha256", "uname",
        "uid", "gid", "python", "cmdline_sha256", "tools",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("guest result fields")
    if (
        value["schema"] != "dm-direct-boot-result-v1"
        or value["result"] != "measured"
        or value["scope"] != "offline-bootstrap-only-no-product-no-g0"
        or value["nonce"] != nonce
        or value["binding"] != binding
        or value["source_sha256"] != guest_source_sha256
    ):
        raise ValueError("guest result binding")
    uname = value["uname"]
    if not isinstance(uname, list) or len(uname) != 5 or not all(isinstance(item, str) and len(item) <= 512 for item in uname):
        raise ValueError("guest uname")
    if (
        not isinstance(value["uid"], int) or isinstance(value["uid"], bool) or value["uid"] != 0
        or not isinstance(value["gid"], int) or isinstance(value["gid"], bool) or value["gid"] != 0
        or not isinstance(value["python"], str) or not 0 < len(value["python"]) <= 2048
    ):
        raise ValueError("guest scalar identity")
    if not isinstance(value["cmdline_sha256"], str) or not HEX64.fullmatch(value["cmdline_sha256"]):
        raise ValueError("guest cmdline digest")
    expected_paths = {
        "/usr/bin/python3", "/usr/bin/cloud-init", "/usr/bin/dpkg-query", "/usr/bin/systemctl", "/usr/bin/sha256sum",
        "/boot/vmlinuz-" + uname[2], "/boot/config-" + uname[2],
    }
    tools = value["tools"]
    if not isinstance(tools, list) or len(tools) != len(expected_paths):
        raise ValueError("guest tool inventory count")
    seen = set()
    fields = {"requested", "resolved", "sha256", "bytes", "mode", "owner"}
    for fact in tools:
        if not isinstance(fact, dict) or set(fact) != fields or fact["requested"] not in expected_paths or fact["requested"] in seen:
            raise ValueError("guest tool record fields/path")
        seen.add(fact["requested"])
        if fact["resolved"] is None:
            if any(fact[key] is not None for key in ("sha256", "bytes", "mode", "owner")):
                raise ValueError("absent guest tool record")
            continue
        if not isinstance(fact["resolved"], str) or not fact["resolved"].startswith("/") or len(fact["resolved"]) > 4096:
            raise ValueError("guest tool resolved path")
        if not isinstance(fact["sha256"], str) or not HEX64.fullmatch(fact["sha256"]):
            raise ValueError("guest tool digest")
        if not isinstance(fact["bytes"], int) or isinstance(fact["bytes"], bool) or not 0 <= fact["bytes"] <= 256 * MIB:
            raise ValueError("guest tool bytes")
        if not isinstance(fact["mode"], int) or isinstance(fact["mode"], bool) or not 0 <= fact["mode"] <= 0o7777:
            raise ValueError("guest tool mode")
        owner = fact["owner"]
        if owner is not None and (
            not isinstance(owner, dict) or set(owner) != {"package", "version"}
            or not isinstance(owner["package"], str) or not 0 < len(owner["package"]) <= 128
            or owner["version"] is not None and (not isinstance(owner["version"], str) or not 0 < len(owner["version"]) <= 512)
        ):
            raise ValueError("guest tool package owner")
    if seen != expected_paths or next(f for f in tools if f["requested"] == "/usr/bin/python3")["resolved"] is None:
        raise ValueError("guest tool inventory completeness")
    return value


def validate_qemu_img_info(value: dict, *, base_path: Path, physical_size: int) -> dict:
    if not isinstance(value, dict):
        raise ValueError("qemu-img result")
    permitted = {
        "virtual-size", "filename", "cluster-size", "format", "actual-size",
        "format-specific", "dirty-flag", "corrupt", "snapshots",
    }
    if set(value) - permitted:
        raise ValueError("unknown qemu-img fields")
    if value.get("format") != "qcow2" or value.get("filename") != str(base_path):
        raise ValueError("base format/path")
    virtual = value.get("virtual-size")
    actual = value.get("actual-size", physical_size)
    if not isinstance(virtual, int) or not 0 < virtual <= VIRTUAL_MAX:
        raise ValueError("virtual size")
    if not isinstance(actual, int) or actual < 0 or actual > IMAGE_MAX:
        raise ValueError("actual size")
    if value.get("snapshots") not in (None, []):
        raise ValueError("snapshots")
    if value.get("dirty-flag") is True or value.get("corrupt") is True:
        raise ValueError("dirty/corrupt image")
    specific = value.get("format-specific")
    if not isinstance(specific, dict) or specific.get("type") != "qcow2" or not isinstance(specific.get("data"), dict):
        raise ValueError("qcow format-specific")
    data = specific["data"]
    forbidden = {"backing-filename", "full-backing-filename", "data-file", "full-data-file", "encrypt"}
    if forbidden.intersection(data):
        raise ValueError("external/encrypted qcow feature")
    allowed_data = {"compat", "compression-type", "lazy-refcounts", "refcount-bits", "corrupt", "extended-l2"}
    if set(data) - allowed_data:
        raise ValueError("unknown qcow format feature")
    if (
        data.get("compat") != "1.1"
        or data.get("compression-type") not in (None, "zlib")
        or data.get("lazy-refcounts") is not False
        or data.get("refcount-bits") != 16
        or data.get("corrupt", False) is not False
        or data.get("extended-l2") is not False
    ):
        raise ValueError("unsupported qcow compatibility/refcount feature")
    return {"format": "qcow2", "virtual_size": virtual, "physical_size": physical_size}


def validate_qemu_img_check(value: dict, *, base_path: Path) -> dict:
    required = {"filename", "format", "check-errors", "image-end-offset", "total-clusters", "allocated-clusters", "fragmented-clusters", "compressed-clusters"}
    optional = {"corruptions", "leaks", "corruptions-fixed", "leaks-fixed"}
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - optional:
        raise ValueError("qemu-img check fields")
    if value["filename"] != str(base_path) or value["format"] != "qcow2":
        raise ValueError("qemu-img check image identity")
    for key, number in value.items():
        if key in {"filename", "format"}:
            continue
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            raise ValueError("qemu-img check scalar: " + key)
    for key in ("check-errors", "corruptions", "leaks", "corruptions-fixed", "leaks-fixed"):
        if value.get(key, 0) != 0:
            raise ValueError("qemu-img consistency failure: " + key)
    if not 0 < value["image-end-offset"] <= IMAGE_MAX or value["total-clusters"] <= 0:
        raise ValueError("qemu-img check size/count")
    if value["allocated-clusters"] > value["total-clusters"]:
        raise ValueError("qemu-img allocated cluster count")
    if value["fragmented-clusters"] > value["allocated-clusters"] or value["compressed-clusters"] > value["allocated-clusters"]:
        raise ValueError("qemu-img cluster subtype count")
    return {key: value[key] for key in sorted(value)}


def parse_cpu_max(raw: str) -> tuple[int, int]:
    parts = raw.strip().split()
    if len(parts) != 2 or parts[0] == "max":
        raise ValueError("unbounded cpu.max")
    quota, period = map(int, parts)
    if quota != 200000 or period != 100000:
        raise ValueError("unexpected cpu.max")
    return quota, period


def verify_limits(read_text) -> dict:
    values = {
        "memory.max": read_text("memory.max").strip(),
        "memory.swap.max": read_text("memory.swap.max").strip(),
        "pids.max": read_text("pids.max").strip(),
        "cpu.max": read_text("cpu.max").strip(),
    }
    if values["memory.max"] != str(3 * GIB) or values["memory.swap.max"] != "0":
        raise ValueError("memory cgroup readback")
    if values["pids.max"] != "64":
        raise ValueError("pids cgroup readback")
    parse_cpu_max(values["cpu.max"])
    return values


def qmp_shutdown_seen(messages: list[dict]) -> bool:
    shutdown = [m for m in messages if m.get("event") == "SHUTDOWN"]
    return len(shutdown) == 1 and shutdown[0].get("data", {}).get("guest") is True


def ensure_evidence_allowlist(root: Path, allowlist: dict[str, int]) -> tuple[int, dict[str, dict]]:
    observed: dict[str, dict] = {}
    total = 0
    for entry in root.iterdir():
        if entry.name not in allowlist or entry.is_symlink() or not entry.is_file():
            raise ValueError(f"unexpected evidence entry: {entry.name}")
        digest, size = sha_file(entry, allowlist[entry.name])
        total += size
        observed[entry.name] = {"sha256": digest, "bytes": size}
    if total > EVIDENCE_MAX:
        raise ValueError("aggregate retained evidence cap")
    return total, observed
