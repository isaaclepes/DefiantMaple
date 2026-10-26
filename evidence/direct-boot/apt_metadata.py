"""Collect exact-version Installed-Size facts from authenticated local APT lists."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import grp
import pwd
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
DIAGNOSTIC_TEXT_MAX = 16 * 1024
DIAGNOSTIC_RAW_TEXT_TOTAL_MAX = 512 * 1024
LIST_FILES_MAX = 128
LIST_BYTES_MAX = 1024**3
LIST_FILE_MAX = 512 * 1024**2


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


def _administrative_record(name: str, info: os.stat_result, *, root_uid: int, root_gid: int, sandbox_uid: int) -> dict:
    mode = stat.S_IMODE(info.st_mode)
    if name == "lock":
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != root_uid or info.st_gid != root_gid
                or mode not in (0o600, 0o640) or info.st_size != 0 or info.st_nlink != 1):
            raise RuntimeError("APT lists lock identity/mode/size")
        return {"name": name, "kind": "empty-lock", "uid": info.st_uid, "gid": info.st_gid, "mode": mode}
    expected_mode = {"partial": 0o700, "auxfiles": 0o755}[name]
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != sandbox_uid or info.st_gid != root_gid
            or mode != expected_mode):
        raise RuntimeError("APT lists administrative directory identity/mode: " + name)
    return {
        "name": name,
        "kind": "opaque-directory" if name == "partial" else "hashed-directory",
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": mode,
    }


def lists_manifest(
    root: Path,
    *,
    root_uid: int = 0,
    root_gid: int | None = None,
    sandbox_uid: int | None = None,
) -> dict:
    if root_gid is None:
        root_gid = grp.getgrnam("root").gr_gid
    if sandbox_uid is None:
        sandbox_uid = pwd.getpwnam("_apt").pw_uid
    digest = hashlib.sha256()
    count = 0
    total = 0
    index_count = 0
    auxiliary_count = 0
    administrative: dict[str, dict] = {}
    with os.scandir(root) as entries:
        top = sorted(entries, key=lambda entry: entry.name)
    for entry in top:
        info = entry.stat(follow_symlinks=False)
        if entry.name in ("lock", "partial", "auxfiles"):
            administrative[entry.name] = _administrative_record(
                entry.name, info, root_uid=root_uid, root_gid=root_gid, sandbox_uid=sandbox_uid
            )
            continue
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("APT lists contain unknown directory/redirection/special entry")
        path = Path(entry.path)
        file_sha, size = sha_file(path, LIST_FILE_MAX, allow_empty=True)
        count += 1
        index_count += 1
        total += size
        if count > LIST_FILES_MAX or total > LIST_BYTES_MAX:
            raise RuntimeError("APT lists manifest cap")
        digest.update(b"index\0" + entry.name.encode("utf-8") + b"\0" + str(size).encode() + b"\0" + file_sha.encode() + b"\n")
    if set(administrative) != {"lock", "partial", "auxfiles"}:
        raise RuntimeError("APT lists administrative entries missing")
    aux = root / "auxfiles"
    with os.scandir(aux) as entries:
        auxiliary = sorted(entries, key=lambda entry: entry.name)
    for entry in auxiliary:
        info = entry.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != root_uid or info.st_gid != root_gid
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise RuntimeError("APT auxfiles child identity/type/mode")
        path = Path(entry.path)
        file_sha, size = sha_file(path, LIST_FILE_MAX, allow_empty=True)
        count += 1
        auxiliary_count += 1
        total += size
        if count > LIST_FILES_MAX or total > LIST_BYTES_MAX:
            raise RuntimeError("APT lists manifest cap")
        digest.update(b"aux\0" + entry.name.encode("utf-8") + b"\0" + str(size).encode() + b"\0" + file_sha.encode() + b"\n")
    ordered_admin = [administrative[name] for name in ("lock", "partial", "auxfiles")]
    for record in ordered_admin:
        digest.update(b"admin\0" + json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    if index_count == 0:
        raise RuntimeError("APT lists manifest empty")
    return {
        "regular_files": count,
        "index_files": index_count,
        "auxiliary_files": auxiliary_count,
        "total_bytes": total,
        "sha256": digest.hexdigest(),
        "administrative": ordered_admin,
    }


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


def diagnostic_text_cap(package_count: int) -> int:
    if package_count <= 0 or package_count > 96:
        raise ValueError("APT diagnostic package count")
    return min(DIAGNOSTIC_TEXT_MAX, DIAGNOSTIC_RAW_TEXT_TOTAL_MAX // (2 * package_count))


def bounded_query(argv: list[str], package: dict, *, text_cap: int = DIAGNOSTIC_TEXT_MAX) -> tuple[bytes, dict]:
    if text_cap <= 0 or text_cap > DIAGNOSTIC_TEXT_MAX:
        raise ValueError("APT query diagnostic text cap")
    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (QUERY_MAX, QUERY_MAX))

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        timed_out = False
        launch_error = None
        result = None
        try:
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
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError as exc:
            launch_error = type(exc).__name__ + ": " + str(exc)[:1024]
        stdout.seek(0); raw = stdout.read(QUERY_MAX + 1)
        stderr.seek(0); error = stderr.read(QUERY_MAX + 1)
    reasons = []
    returncode = None if result is None else result.returncode
    if timed_out:
        reasons.append("timeout")
    if launch_error is not None:
        reasons.append("launch-error")
    if returncode not in (0, None):
        reasons.append("nonzero-returncode")
    if error:
        reasons.append("stderr-nonempty")
    if not raw:
        reasons.append("stdout-empty")
    if len(raw) > QUERY_MAX:
        reasons.append("stdout-cap")
    if len(error) > QUERY_MAX:
        reasons.append("stderr-cap")
    diagnostic = {
        "name": package["name"],
        "version": package["version"],
        "architecture": package["architecture"],
        "argv": argv,
        "returncode": returncode,
        "outcome": "timeout" if timed_out else ("exec-error" if launch_error is not None else "exit"),
        "timed_out": timed_out,
        "launch_error": launch_error,
        "stdout_bytes": len(raw),
        "stdout_sha256": hashlib.sha256(raw).hexdigest(),
        "stdout_capture_truncated": len(raw) > QUERY_MAX,
        "stdout_text_encoding": "base64",
        "stdout_text": base64.b64encode(raw[:text_cap]).decode("ascii"),
        "stdout_text_bytes": min(len(raw), text_cap),
        "stdout_text_truncated": len(raw) > text_cap,
        "stderr_bytes": len(error),
        "stderr_sha256": hashlib.sha256(error).hexdigest(),
        "stderr_capture_truncated": len(error) > QUERY_MAX,
        "stderr_text_encoding": "base64",
        "stderr_text": base64.b64encode(error[:text_cap]).decode("ascii"),
        "stderr_text_bytes": min(len(error), text_cap),
        "stderr_text_truncated": len(error) > text_cap,
        "failure_reasons": reasons,
        "parse_status": "not-attempted",
        "parse_error": None,
        "accepted": not reasons,
    }
    return raw, diagnostic


def failure_bytes(value: dict) -> bytes:
    bounded = copy.deepcopy(value)
    bounded["excerpt_bytes_reduced_to_fit"] = 0
    while True:
        data = json.dumps(bounded, sort_keys=True, separators=(",", ":")).encode()
        if len(data) <= TOTAL_MAX:
            return data
        changed = False
        for query in bounded.get("queries", []):
            for stream in ("stdout", "stderr"):
                field = stream + "_text"
                encoded = query.get(field)
                if not isinstance(encoded, str) or not encoded:
                    continue
                keep = (len(encoded) // 2) // 4 * 4
                reduced = encoded[:keep]
                old_bytes = query[stream + "_text_bytes"]
                new_bytes = len(base64.b64decode(reduced, validate=True)) if reduced else 0
                query[field] = reduced
                query[stream + "_text_bytes"] = new_bytes
                query[stream + "_text_truncated"] = True
                bounded["excerpt_bytes_reduced_to_fit"] += old_bytes - new_bytes
                changed = True
        if not changed:
            raise RuntimeError("APT query diagnostic summary exceeds JSON cap")


def write_failure(path: Path, value: dict) -> None:
    data = failure_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def collect_queries(packages: list[dict], source_list: Path, lists: Path) -> tuple[list[dict], list[dict], list[str], int]:
    records = []
    diagnostics = []
    failures = []
    charged = 0
    text_cap = diagnostic_text_cap(len(packages))
    for package in packages:
        argv = cache_argv(source_list, lists, package["name"].split(":", 1)[0], package["version"])
        raw, diagnostic = bounded_query(argv, package, text_cap=text_cap)
        charged += len(raw)
        if charged > TOTAL_MAX:
            diagnostic["failure_reasons"].append("aggregate-stdout-cap")
            diagnostic["accepted"] = False
        if diagnostic["accepted"]:
            try:
                records.append(parse_stanza(raw, package))
                diagnostic["parse_status"] = "ok"
            except (UnicodeDecodeError, ValueError) as exc:
                diagnostic["failure_reasons"].append("metadata-parse-error")
                diagnostic["parse_error"] = type(exc).__name__ + ": " + str(exc)[:1024]
                diagnostic["parse_status"] = "error"
                diagnostic["accepted"] = False
        diagnostics.append(diagnostic)
        if not diagnostic["accepted"]:
            failures.append(package["name"])
    return records, diagnostics, failures, charged


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
    parser.add_argument("failure_output", type=Path)
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
    records, diagnostics, failures, charged = collect_queries(
        transaction["packages"], args.source_list, args.lists
    )
    integrity_errors = []
    try:
        if sha_file(APT_CACHE, FILE_MAX) != (tool_sha, tool_bytes):
            integrity_errors.append("apt-cache-changed")
    except (OSError, RuntimeError) as exc:
        integrity_errors.append("apt-cache-recheck-error:" + type(exc).__name__ + ":" + str(exc)[:512])
    try:
        if lists_manifest(args.lists) != authenticated_lists:
            integrity_errors.append("apt-lists-changed")
    except (OSError, RuntimeError) as exc:
        integrity_errors.append("apt-lists-recheck-error:" + type(exc).__name__ + ":" + str(exc)[:512])
    if failures or integrity_errors:
        write_failure(args.failure_output, {
            "schema": "dm-apt-query-failure-v1",
            "measurement_only": True,
            "install_permitted": False,
            "query_count": len(diagnostics),
            "failed_packages": failures,
            "integrity_errors": integrity_errors,
            "aggregate_stdout_bytes": charged,
            "per_stream_text_bytes_cap": diagnostic_text_cap(len(transaction["packages"])),
            "aggregate_raw_text_bytes_cap": DIAGNOSTIC_RAW_TEXT_TOTAL_MAX,
            "queries": diagnostics,
        })
        raise RuntimeError("bounded apt-cache batch failed; see private failure evidence")
    result = {
        "schema": "dm-apt-installed-size-v2",
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
