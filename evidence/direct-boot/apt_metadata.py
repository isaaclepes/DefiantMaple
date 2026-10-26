"""Collect exact-version Installed-Size facts from authenticated local APT lists."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("dm_direct_boot_apt_guard", HERE / "apt_guard.py")
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load exact sibling apt_guard")
apt_guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(apt_guard)

APT_CACHE = Path("/usr/bin/apt-cache")
FILE_MAX = 16 * 1024**2
QUERY_MAX = 128 * 1024
TOTAL_MAX = 1024**2


def sha_file(path: Path, cap: int, *, allow_empty: bool = False) -> tuple[str, int]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (info.st_size <= 0 and not allow_empty) or info.st_size > cap:
            raise RuntimeError("tool/source file type or size")
        digest = hashlib.sha256()
        size = 0
        while block := os.read(fd, min(65536, cap + 1 - size)):
            size += len(block)
            if size > cap:
                raise RuntimeError("tool/source file grew beyond cap")
            digest.update(block)
        return digest.hexdigest(), size
    finally:
        os.close(fd)


def lists_manifest(root: Path) -> dict:
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError("APT lists contain redirection/special entry")
        if stat.S_ISDIR(info.st_mode):
            continue
        file_sha, size = sha_file(path, 512 * 1024**2, allow_empty=True)
        relative = str(path.relative_to(root))
        count += 1
        total += size
        if count > 128 or total > 1024**3:
            raise RuntimeError("APT lists manifest cap")
        digest.update(relative.encode("utf-8") + b"\0" + str(size).encode() + b"\0" + file_sha.encode() + b"\n")
    if count == 0:
        raise RuntimeError("APT lists manifest empty")
    return {"regular_files": count, "total_bytes": total, "sha256": digest.hexdigest()}


def parse_stanza(raw: bytes, expected: dict) -> dict:
    text = raw.decode("utf-8", "strict")
    paragraphs = [part for part in text.split("\n\n") if part.strip()]
    if len(paragraphs) != 1:
        raise ValueError("apt-cache exact query returned ambiguous package records")
    fields: dict[str, str] = {}
    active = None
    for line in paragraphs[0].splitlines():
        if line.startswith((" ", "\t")):
            if active is None:
                raise ValueError("apt-cache malformed continuation")
            fields[active] += "\n" + line
            continue
        name, separator, value = line.partition(":")
        if not separator or not name or name in fields:
            raise ValueError("apt-cache malformed/duplicate field")
        fields[name] = value.strip()
        active = name
    for name in ("Package", "Version", "Architecture", "Installed-Size"):
        if name not in fields:
            raise ValueError("apt-cache required field missing: " + name)
    expected_name = expected["name"].split(":", 1)[0]
    if (fields["Package"], fields["Version"], fields["Architecture"]) != (expected_name, expected["version"], expected["architecture"]):
        raise ValueError("apt-cache package/version/architecture differs from plan")
    if not fields["Installed-Size"].isdigit():
        raise ValueError("apt-cache Installed-Size is not an integer")
    size = int(fields["Installed-Size"])
    if size <= 0 or size > apt_guard.MAX_NEW_BYTES // 1024:
        raise ValueError("apt-cache Installed-Size outside per-package bound")
    return {
        "name": expected_name,
        "version": expected["version"],
        "architecture": expected["architecture"],
        "installed_size_kib": size,
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
    }


def bounded_query(argv: list[str]) -> bytes:
    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (QUERY_MAX, QUERY_MAX))

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "APT_CONFIG": "/dev/null", "HOME": "/nonexistent"},
            timeout=10,
            check=False,
            close_fds=True,
            preexec_fn=limits,
        )
        stdout.seek(0); raw = stdout.read(QUERY_MAX + 1)
        stderr.seek(0); error = stderr.read(QUERY_MAX + 1)
    if result.returncode != 0 or error or not raw or len(raw) > QUERY_MAX:
        raise RuntimeError("bounded apt-cache exact-version query failed")
    return raw


def cache_argv(source_list: Path, lists: Path, name: str, version: str) -> list[str]:
    return [
        str(APT_CACHE),
        "-o", "Dir::Etc::sourcelist=" + str(source_list),
        "-o", "Dir::Etc::sourceparts=-",
        "-o", "Dir::State::lists=" + str(lists),
        "-o", "Dir::Cache::pkgcache=",
        "-o", "Dir::Cache::srcpkgcache=",
        "--no-all-versions", "show", name + "=" + version,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("source_list", type=Path)
    parser.add_argument("lists", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    allowed = {line.strip() for line in args.allowlist.read_text().splitlines() if line.strip() and not line.startswith("#")}
    transaction = apt_guard.parse_transaction(args.plan.read_text(), allowed)
    tool_sha, tool_bytes = sha_file(APT_CACHE, FILE_MAX)
    tool_info = APT_CACHE.stat()
    if tool_info.st_uid != 0 or tool_info.st_mode & 0o022:
        raise RuntimeError("apt-cache owner/mode")
    source_sha, _ = sha_file(args.source_list, QUERY_MAX)
    list_info = args.lists.lstat()
    if not stat.S_ISDIR(list_info.st_mode) or stat.S_ISLNK(list_info.st_mode) or list_info.st_uid not in (0, os.getuid()) or list_info.st_mode & 0o022:
        raise RuntimeError("APT lists directory identity/mode")
    authenticated_lists = lists_manifest(args.lists)
    records = []
    charged = 0
    for package in transaction["packages"]:
        raw = bounded_query(cache_argv(args.source_list, args.lists, package["name"].split(":", 1)[0], package["version"]))
        charged += len(raw)
        if charged > TOTAL_MAX:
            raise RuntimeError("aggregate apt-cache metadata cap")
        records.append(parse_stanza(raw, package))
    if sha_file(APT_CACHE, FILE_MAX) != (tool_sha, tool_bytes):
        raise RuntimeError("apt-cache changed during metadata collection")
    if lists_manifest(args.lists) != authenticated_lists:
        raise RuntimeError("APT lists changed during metadata collection")
    result = {
        "schema": "dm-apt-installed-size-v1",
        "apt_cache": {"path": str(APT_CACHE), "sha256": tool_sha, "bytes": tool_bytes, "uid": tool_info.st_uid, "mode": stat.S_IMODE(tool_info.st_mode)},
        "source_list_sha256": source_sha,
        "lists_identity": [list_info.st_dev, list_info.st_ino],
        "lists_manifest": authenticated_lists,
        "records": records,
    }
    data = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    if len(data) > TOTAL_MAX:
        raise RuntimeError("APT installed-size metadata JSON cap")
    with args.output.open("xb") as output:
        output.write(data)


if __name__ == "__main__":
    main()
