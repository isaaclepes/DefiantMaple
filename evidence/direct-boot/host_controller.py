"""One authenticated image download and one bounded offline direct-QEMU boot."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import resource
import select
import selectors
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
_POLICY_SPEC = importlib.util.spec_from_file_location("dm_direct_boot_policy", HERE / "policy.py")
if _POLICY_SPEC is None or _POLICY_SPEC.loader is None:
    raise RuntimeError("exact policy source loader unavailable")
policy = importlib.util.module_from_spec(_POLICY_SPEC)
_POLICY_SPEC.loader.exec_module(policy)
_KEYRING_SPEC = importlib.util.spec_from_file_location("dm_direct_boot_keyring", HERE / "keyring_bootstrap.py")
if _KEYRING_SPEC is None or _KEYRING_SPEC.loader is None:
    raise RuntimeError("exact keyring-bootstrap source loader unavailable")
keyring_bootstrap = importlib.util.module_from_spec(_KEYRING_SPEC)
_KEYRING_SPEC.loader.exec_module(keyring_bootstrap)
ALLOWED_EVIDENCE = {
    "host.json": policy.STREAM_MAX,
    "apt-plan.log": policy.STREAM_MAX,
    "apt-metadata.json": policy.STREAM_MAX,
    "apt-metadata-failure.json": policy.STREAM_MAX,
    "apt-plan.json": policy.STREAM_MAX,
    "apt-observation.json": policy.STREAM_MAX,
    "host-inventory-failure.json": policy.STREAM_MAX,
    "keyring-bootstrap.json": policy.STREAM_MAX,
    "keyring-cleanup.json": policy.STREAM_MAX,
    "image.json": policy.STREAM_MAX,
    "qemu-img-info.raw.json": policy.STREAM_MAX,
    "qemu-img-info-failure.json": 16384,
    "qemu-img-check.raw.json": policy.STREAM_MAX,
    "qemu-img-check-failure.json": 16384,
    "qemu-stderr.log": policy.STREAM_MAX,
    "watchdog-stderr.log": policy.STREAM_MAX,
    "qemu-startup.json": 16384,
    "boot-config.json": policy.STREAM_MAX,
    "cgroup-create.json": 16384,
    "cgroup-attach.json": policy.STREAM_MAX,
    "cleanup-wait.json": 16384,
    "cgroup-destroy.json": 16384,
    "watchdog-ready.json": 16384,
    "watchdog-result.json": 16384,
    "serial.json": policy.STREAM_MAX,
    "guest-result.json": policy.STREAM_MAX,
    "qmp.json": policy.STREAM_MAX,
    "lifecycle.json": policy.STREAM_MAX,
    "receipt.json": policy.STREAM_MAX,
    "failure.json": policy.STREAM_MAX,
    "source-hashes.txt": policy.STREAM_MAX,
}
QEMU_SYSTEM = Path("/usr/bin/qemu-system-x86_64")
QEMU_IMG = Path("/usr/bin/qemu-img")
CLOUD_LOCALDS = Path("/usr/bin/cloud-localds")
SEABIOS = Path("/usr/share/seabios/bios-256k.bin")
DPKG_QUERY = "/usr/bin/dpkg-query"
DPKG_OUTPUT_MAX = 4096
PACKAGE_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?")
CGROUP_ROOT = Path("/sys/fs/cgroup")
CGROUP_NAME = re.compile(r"dm-direct-boot-[0-9a-f]{16}")
REQUIRED_CGROUP_CONTROLLERS = {"cpu", "memory", "pids"}
CGROUP_LIMITS = {
    "memory.max": str(3 * policy.GIB), "memory.swap.max": "0",
    "pids.max": "64", "cpu.max": "200000 100000",
}
LIFECYCLE_RECEIPTS = {
    "cgroup.json": "cgroup-create.json",
    "cleanup-wait.json": "cleanup-wait.json",
    "cgroup-destroy.json": "cgroup-destroy.json",
    "watchdog-ready.json": "watchdog-ready.json",
    "watchdog-result.json": "watchdog-result.json",
}


def canonical(value: object) -> bytes:
    return policy.canonical(value)


def exclusive(path: Path, data: bytes, mode: int = 0o600, cap: int = policy.STREAM_MAX) -> None:
    if len(data) > cap:
        raise RuntimeError("exclusive output cap: " + path.name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_write(path: Path, value: object) -> None:
    exclusive(path, canonical(value))


def atomic_json_publish(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    exclusive(temporary, canonical(value))
    os.replace(temporary, path)


def proc_fact(pid: int) -> dict | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        end = raw.rfind(")")
        fields = raw[end + 2 :].split()
        groups = [line[3:] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines() if line.startswith("0::")]
        if end < 0 or len(fields) < 20 or len(groups) != 1:
            return None
        return {"pid": pid, "start_ticks": int(fields[19]), "cgroup": groups[0]}
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None


def private_root(raw: str) -> Path:
    root = Path(raw)
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    resolved = root.resolve(strict=True)
    if resolved.parent != runner_temp or resolved != root.absolute() or root.is_symlink():
        raise RuntimeError("work root must be a fresh direct child of RUNNER_TEMP")
    st = resolved.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise RuntimeError("work root owner/mode")
    if any(ch in str(resolved) for ch in ",\n\r"):
        raise RuntimeError("unsupported work-root characters")
    return resolved


def free_bytes(path: Path) -> int:
    info = os.statvfs(path)
    return info.f_bavail * info.f_frsize


def mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable missing")


def secure_system_file(path: Path, cap: int) -> dict:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise RuntimeError("system tool owner/type/mode: " + str(path))
    digest, size = policy.sha_file(path, cap)
    return {"path": str(path), "sha256": digest, "bytes": size}


def launch_executable_identity(path: Path, expected: dict, cap: int) -> dict:
    """Bind launch content to the exact stable path inode used for exec proof."""
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or before.st_nlink < 1 or before.st_size > cap):
            raise RuntimeError("launch executable owner/type/mode/cap")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            total += len(block)
            if total > cap:
                raise RuntimeError("launch executable grew beyond cap")
            digest.update(block)
        after = os.fstat(fd)
        current = path.lstat()
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise RuntimeError("launch executable identity changed")
    finally:
        os.close(fd)
    observed = {"path": str(path), "sha256": digest.hexdigest(), "bytes": total}
    if observed != expected:
        raise RuntimeError("launch executable content changed")
    return {**observed, "device": after.st_dev, "inode": after.st_ino}


def bounded_dpkg_query(argv: list[str]) -> dict:
    """Retain two bounded streams for one fixed read-only dpkg database query."""
    if not argv or argv[0] != DPKG_QUERY:
        raise RuntimeError("dpkg query executable")

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (DPKG_OUTPUT_MAX, DPKG_OUTPUT_MAX))

    environment = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "LANGUAGE": "C.UTF-8", "HOME": "/nonexistent",
    }
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
                cwd="/", env=environment, close_fds=True, start_new_session=True,
                preexec_fn=limits,
            )
        except OSError as exc:
            return {
                "argv": argv, "returncode": None, "timed_out": False,
                "exec_error": type(exc).__name__, "stdout_bytes": 0,
                "stdout_sha256": policy.sha_bytes(b""), "stdout_text": "",
                "stdout_truncated": False, "stderr_bytes": 0,
                "stderr_sha256": policy.sha_bytes(b""), "stderr_text": "",
                "stderr_truncated": False,
            }
        timed_out = False
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(DPKG_OUTPUT_MAX + 1)
        stderr = stderr_file.read(DPKG_OUTPUT_MAX + 1)
    return {
        "argv": argv, "returncode": process.returncode, "timed_out": timed_out,
        "exec_error": None, "stdout_bytes": len(stdout),
        "stdout_sha256": policy.sha_bytes(stdout),
        "stdout_text": stdout[:DPKG_OUTPUT_MAX].decode("utf-8", "replace"),
        "stdout_truncated": len(stdout) >= DPKG_OUTPUT_MAX,
        "stderr_bytes": len(stderr), "stderr_sha256": policy.sha_bytes(stderr),
        "stderr_text": stderr[:DPKG_OUTPUT_MAX].decode("utf-8", "replace"),
        "stderr_truncated": len(stderr) >= DPKG_OUTPUT_MAX,
    }


def accepted_query(record: dict) -> bool:
    return (
        record.get("returncode") == 0 and record.get("timed_out") is False
        and record.get("exec_error") is None
        and record.get("stdout_truncated") is False
        and record.get("stderr_truncated") is False
        and record.get("stderr_bytes") == 0
    )


class PackageOwnershipError(RuntimeError):
    def __init__(self, message: str, observation: dict):
        super().__init__(message)
        self.observation = observation


def ownership_result(record: dict, queried_path: str) -> dict:
    """Classify the entire output; diversion package names never become owners."""
    expected_no_match = "dpkg-query: no path found matching pattern " + queried_path + "\n"
    if (
        queried_path.startswith("/") and not any(value in queried_path for value in ("\x00", "\n", "\r"))
        and record.get("returncode") == 1 and record.get("timed_out") is False
        and record.get("exec_error") is None
        and record.get("stdout_truncated") is False
        and record.get("stderr_truncated") is False
        and record.get("stdout_bytes") == 0 and record.get("stdout_text") == ""
        and record.get("stderr_bytes") == len(expected_no_match.encode("utf-8"))
        and record.get("stderr_text") == expected_no_match
    ):
        return {"classification": "no-match", "owner": None}
    if not accepted_query(record):
        return {"classification": "query-failure", "owner": None}
    lines = record["stdout_text"].splitlines()
    if len(lines) == 1:
        prefix, separator, observed = lines[0].rpartition(": ")
        owners = [value.strip() for value in prefix.split(",")]
        if (separator and observed == queried_path and len(owners) == 1
                and PACKAGE_NAME.fullmatch(owners[0])):
            return {"classification": "one-owner", "owner": owners[0]}
    if len(lines) != 2:
        return {"classification": "ambiguous", "owner": None}
    diversion_records = []
    for line in lines:
        prefix, separator, path = line.rpartition(": ")
        if not separator or not path.startswith("/") or "\x00" in path:
            return {"classification": "ambiguous", "owner": None}
        if prefix.startswith("diversion by ") and prefix.endswith(" from"):
            package = prefix[len("diversion by ") : -len(" from")]
            if not PACKAGE_NAME.fullmatch(package):
                return {"classification": "ambiguous", "owner": None}
            diversion_records.append(("package", package, "from", path))
        elif prefix.startswith("diversion by ") and prefix.endswith(" to"):
            package = prefix[len("diversion by ") : -len(" to")]
            if not PACKAGE_NAME.fullmatch(package):
                return {"classification": "ambiguous", "owner": None}
            diversion_records.append(("package", package, "to", path))
        elif prefix == "local diversion from":
            diversion_records.append(("local", None, "from", path))
        elif prefix == "local diversion to":
            diversion_records.append(("local", None, "to", path))
        else:
            return {"classification": "ambiguous", "owner": None}
    from_records = [item for item in diversion_records if item[2] == "from"]
    to_records = [item for item in diversion_records if item[2] == "to"]
    if (len(from_records) == 1 and len(to_records) == 1
            and from_records[0][0:2] == to_records[0][0:2]
            and from_records[0][3] == queried_path and to_records[0][3] != queried_path):
        return {"classification": "diversion-only", "owner": None}
    return {"classification": "ambiguous", "owner": None}


def package_for_file(requested: Path, resolved: Path) -> dict:
    requested_path = str(requested)
    resolved_path = str(resolved)
    requested_query = bounded_dpkg_query([DPKG_QUERY, "-S", requested_path])
    requested_result = ownership_result(requested_query, requested_path)
    queries = [{"path": requested_path, "query": requested_query, **requested_result}]
    owner = requested_result["owner"] if requested_result["classification"] == "one-owner" else None
    if (requested_result["classification"] in {"diversion-only", "no-match"}
            and resolved_path != requested_path):
        canonical_query = bounded_dpkg_query([DPKG_QUERY, "-S", resolved_path])
        canonical_result = ownership_result(canonical_query, resolved_path)
        queries.append({"path": resolved_path, "query": canonical_query, **canonical_result})
        owner = canonical_result["owner"] if canonical_result["classification"] == "one-owner" else None
    if owner is None:
        raise PackageOwnershipError(
            "ambiguous package ownership: " + str(requested),
            {"requested": requested_path, "resolved": resolved_path, "ownership_queries": queries},
        )
    version_query = bounded_dpkg_query([
        DPKG_QUERY, "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n", owner,
    ])
    if not accepted_query(version_query):
        raise PackageOwnershipError(
            "package version query: " + owner,
            {"requested": requested_path, "resolved": resolved_path, "ownership_queries": queries,
             "package": owner, "version_query": version_query},
        )
    raw_version = version_query["stdout_text"]
    fields = raw_version[:-1].split("\t") if raw_version.endswith("\n") and raw_version.count("\n") == 1 else []
    if (len(fields) != 3 or fields[0] != owner or len(fields[1]) > 128
            or not re.fullmatch(r"[0-9A-Za-z.+:~\-]+", fields[1])
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", fields[2])):
        raise PackageOwnershipError(
            "package version identity: " + owner,
            {"requested": requested_path, "resolved": resolved_path, "ownership_queries": queries,
             "package": owner, "version_query": version_query},
        )
    return {
        "package": owner, "version": fields[1], "architecture": fields[2],
        "requested": str(requested), "resolved": str(resolved),
        "ownership_queries": queries, "version_query": version_query,
    }


def ldd_observations(raw: str) -> list[dict]:
    if "not found" in raw:
        raise RuntimeError("unresolved QEMU shared library")
    requested: set[Path] = set()
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.startswith("linux-vdso.so."):
            continue
        token = value.split("=>", 1)[1].strip().split(" ", 1)[0] if "=>" in value else value.split(" ", 1)[0]
        if not token.startswith("/"):
            raise RuntimeError("unparsed ldd line: " + value[:256])
        requested.add(Path(token))
    if not requested or len(requested) > 128:
        raise RuntimeError("QEMU library observation count")
    facts = []
    for path in sorted(requested, key=str):
        resolved = path.resolve(strict=True)
        fact = secure_system_file(resolved, 512 * policy.MIB)
        fact["package"] = package_for_file(path, resolved)
        facts.append(fact)
    return facts


def command(argv: list[str], *, timeout: int, output_cap: int = policy.STREAM_MAX, fsize: int | None = None) -> bytes:
    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if fsize is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))

    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "HOME": os.environ["RUNNER_TEMP"]},
        close_fds=True,
        start_new_session=True,
        preexec_fn=limits,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise RuntimeError("command timeout: " + argv[0])
    if len(out) > output_cap:
        raise RuntimeError("command output cap: " + argv[0])
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}): {argv[0]}: {out[-2048:]!r}")
    return out


def preflight(root: Path) -> None:
    if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
        raise RuntimeError("requires Linux x86_64")
    os_release = dict(
        line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line
    )
    if os_release.get("ID", "").strip('"') != "ubuntu" or os_release.get("VERSION_ID", "").strip('"') != "24.04":
        raise RuntimeError("requires Ubuntu 24.04")
    if free_bytes(root) < 6 * policy.GIB or mem_available() < 4 * policy.GIB:
        raise RuntimeError("preflight disk/RAM floor")
    evidence = root / "evidence"
    evidence.mkdir(mode=0o700)
    nonce = os.urandom(16).hex()
    st = root.stat()
    context = {"schema": "dm-direct-boot-context-v1", "nonce": nonce, "root_identity": [st.st_dev, st.st_ino]}
    json_write(root / "context.json", context)
    json_write(
        evidence / "host.json",
        {
            "schema": "dm-direct-boot-host-v1",
            "scope": "trusted-ephemeral-runner-observation-not-provider-attestation",
            "uname": list(os.uname()),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "root_identity": context["root_identity"],
            "preflight_free_bytes": free_bytes(root),
            "preflight_mem_available": mem_available(),
        },
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("image redirect forbidden")


def download(root: Path) -> None:
    if free_bytes(root) < 6 * policy.GIB:
        raise RuntimeError("download preflight disk floor")
    image = root / "base.qcow2"
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(policy.IMAGE_URL, headers={"User-Agent": "dm-direct-boot-source-v1"})
    deadline = time.monotonic() + 6 * 60
    digest = hashlib.sha256()
    total = 0
    fd = os.open(image, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        with os.fdopen(fd, "wb") as output, opener.open(request, timeout=20) as response:
            final = urllib.parse.urlsplit(response.geturl())
            expected = urllib.parse.urlsplit(policy.IMAGE_URL)
            if final != expected or response.status != 200:
                raise RuntimeError("image URL/status")
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > policy.IMAGE_MAX:
                raise RuntimeError("image Content-Length cap")
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError("image download deadline")
                block = response.read(64 * 1024)
                if not block:
                    break
                total += len(block)
                if total > policy.IMAGE_MAX:
                    raise RuntimeError("image byte cap")
                output.write(block)
                digest.update(block)
                if free_bytes(root) < policy.FREE_FLOOR:
                    raise RuntimeError("free-space floor during image download")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            image.unlink()
        except FileNotFoundError:
            pass
        raise
    if digest.hexdigest() != policy.IMAGE_SHA256:
        raise RuntimeError("authenticated image SHA-256 mismatch")
    json_write(
        root / "evidence" / "image.json",
        {
            "schema": "dm-direct-boot-image-v1",
            "url": policy.IMAGE_URL,
            "sha256": digest.hexdigest(),
            "bytes": total,
            "signed_metadata_basis": {
                "SHA256SUMS_sha256": "0449a33b78dddb301a3ce2b80398984bc3e1f7880e27b86a31e58bdcbd3d3816",
                "SHA256SUMS_gpg_sha256": "68aae716a548e466e58afddd8b767c54c791f40f1d20d1d12e27c471edb535e5",
                "signer_fingerprint": "D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81",
                "note": "metadata authenticated in prior reviewed source-only tranche; this run verifies downloaded complete bytes",
            },
        },
    )


def host_inventory(root: Path, apt_plan: Path, apt_sources: Path, apt_lists: Path, apt_keyring_receipt: Path) -> None:
    plan = json.loads(apt_plan.read_bytes())
    observed = []
    for item in plan["packages"]:
        name = item["name"]
        version = command(["dpkg-query", "-W", "-f=${Version}", name], timeout=5, output_cap=4096).decode()
        if version != item["version"]:
            raise RuntimeError("installed package version differs from simulated plan: " + name)
        paths = command(["dpkg-query", "-L", name], timeout=10).decode("utf-8", "strict").splitlines()
        manifest = hashlib.sha256()
        regular = 0
        for raw in sorted(set(paths)):
            path = Path(raw)
            try:
                if path.is_file() and not path.is_symlink():
                    digest, size = policy.sha_file(path, 512 * policy.MIB)
                    manifest.update(raw.encode() + b"\0" + str(size).encode() + b"\0" + digest.encode() + b"\n")
                    regular += 1
            except (FileNotFoundError, PermissionError, RuntimeError):
                continue
        observed.append({"name": name, "version": version, "regular_files": regular, "installed_file_manifest_sha256": manifest.hexdigest(), "simulated_origin": item["origin"]})
    keyring_receipt = keyring_bootstrap.verify_receipt(apt_keyring_receipt)
    keyring = Path(keyring_receipt["directory"]["path"]) / keyring_receipt["file"]["name"]
    key_sha, key_bytes = policy.sha_file(keyring, 16 * policy.MIB)
    if (key_sha != keyring_bootstrap.KEY_SHA256 or key_bytes != keyring_bootstrap.KEY_BYTES
            or keyring_receipt["accepted_signer"] != keyring_bootstrap.ARCHIVE_SIGNER):
        raise RuntimeError("private Ubuntu archive keyring pin")
    inreleases = []
    for path in sorted(apt_lists.glob("*InRelease")):
        digest, size = policy.sha_file(path, 4 * policy.MIB)
        inreleases.append({"name": path.name, "sha256": digest, "bytes": size})
    if len(inreleases) != 3:
        raise RuntimeError("expected exactly three authenticated Noble InRelease files")
    tools = {
        "qemu-system-x86_64": secure_system_file(QEMU_SYSTEM, 512 * policy.MIB),
        "qemu-img": secure_system_file(QEMU_IMG, 512 * policy.MIB),
        "cloud-localds": secure_system_file(CLOUD_LOCALDS, 16 * policy.MIB),
        "seabios": secure_system_file(SEABIOS, 4 * policy.MIB),
    }
    qemu_version = command([str(QEMU_SYSTEM), "--version"], timeout=5, output_cap=16384).decode("utf-8", "replace")
    ldd = command(["/usr/bin/ldd", str(QEMU_SYSTEM)], timeout=10).decode("utf-8", "strict")
    try:
        qemu_libraries = ldd_observations(ldd)
    except PackageOwnershipError as exc:
        json_write(
            root / "evidence" / "host-inventory-failure.json",
            {"schema": "dm-direct-boot-host-inventory-failure-v1", "error": str(exc),
             "package_observation": exc.observation},
        )
        raise
    json_write(
        root / "evidence" / "apt-observation.json",
        {
            "schema": "dm-direct-boot-apt-observation-v1",
            "claim_limit": "authenticated package selection and observed installed bytes; not complete immutable host closure",
            "sources_sha256": policy.sha_bytes(apt_sources.read_bytes()),
            "archive_keyring": {
                "path": str(keyring),
                "sha256": key_sha,
                "bytes": key_bytes,
                "directory_identity": keyring_receipt["directory"]["identity"],
                "file_identity": keyring_receipt["file"]["identity"],
                "uid": keyring_receipt["file"]["uid"],
                "gid": keyring_receipt["file"]["gid"],
                "mode": keyring_receipt["file"]["mode"],
                "accepted_signer": keyring_receipt["accepted_signer"],
                "claim_limit": "reviewed public-key bytes in an ephemeral APT-readable path; not provider or host attestation",
            },
            "inrelease": inreleases,
            "packages": observed,
            "tools": tools,
            "qemu_version": qemu_version,
            "qemu_ldd_output": ldd,
            "qemu_libraries": qemu_libraries,
        },
    )


def read_context(root: Path) -> dict:
    raw = (root / "context.json").read_bytes()
    if len(raw) > 4096:
        raise RuntimeError("context cap")
    value = json.loads(raw)
    st = root.stat()
    if value.get("root_identity") != [st.st_dev, st.st_ino] or not policy.NONCE.fullmatch(value.get("nonce", "")):
        raise RuntimeError("work-root context identity")
    return value


def make_seed(root: Path, nonce: str, source: bytes, source_sha: str) -> Path:
    seed_dir = root / "seed-input"
    seed_dir.mkdir(mode=0o700)
    config = {"schema": "dm-direct-boot-guest-config-v1", "nonce": nonce, "base_sha256": policy.IMAGE_SHA256, "source_sha256": source_sha}
    def b64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")
    user = (
        "#cloud-config\npackage_update: false\npackage_upgrade: false\nmanage_etc_hosts: false\n"
        "apt:\n  preserve_sources_list: true\n"
        "write_files:\n"
        "  - path: /var/lib/dm-direct-boot/guest_bootstrap.py\n    owner: root:root\n    permissions: '0500'\n    encoding: b64\n    content: " + b64(source) + "\n"
        "  - path: /var/lib/dm-direct-boot/config.json\n    owner: root:root\n    permissions: '0400'\n    encoding: b64\n    content: " + b64(canonical(config)) + "\n"
        "runcmd:\n  - [ /usr/bin/python3, -I, -B, /var/lib/dm-direct-boot/guest_bootstrap.py ]\n"
        "power_state:\n  delay: now\n  mode: poweroff\n  message: dm direct boot measurement complete\n  timeout: 30\n  condition: true\n"
    ).encode()
    meta = ("instance-id: dm-direct-boot-" + nonce + "\nlocal-hostname: dm-direct-boot\n").encode()
    network = b"version: 2\nethernets: {}\n"
    for name, data in (("user-data", user), ("meta-data", meta), ("network-config", network)):
        exclusive(seed_dir / name, data, mode=0o400, cap=512 * policy.MIB)
    seed = root / "seed.iso"
    command(
        [str(CLOUD_LOCALDS), "--disk-format=raw", "--network-config=" + str(seed_dir / "network-config"), str(seed), str(seed_dir / "user-data"), str(seed_dir / "meta-data")],
        timeout=30,
        fsize=policy.SEED_MAX,
    )
    if seed.stat().st_size > policy.SEED_MAX:
        raise RuntimeError("seed cap")
    seed.chmod(0o400)
    return seed


def wait_direct_child(pid: int, options: int) -> tuple[int, int]:
    """The single source-level waitpid owner for the direct child."""
    return os.waitpid(pid, options)


def spawn_qemu(argv: list[str], inert_home: Path) -> tuple[int, int, int, int, int, dict]:
    fds: list[int] = []
    try:
        for _ in range(3):
            fds.extend(os.pipe2(os.O_CLOEXEC))
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
    read_gate, write_gate, stderr_read, stderr_write, exec_read, exec_write = fds
    try:
        pid = os.fork()
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
    if pid == 0:
        try:
            os.close(write_gate)
            os.close(stderr_read)
            os.close(exec_read)
            os.setsid()
            if os.read(read_gate, 1) != b"G":
                os._exit(125)
            os.close(read_gate)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (policy.OVERLAY_MAX, policy.OVERLAY_MAX))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            os.umask(0o077)
            null_fd = os.open("/dev/null", os.O_RDWR | os.O_NOCTTY)
            for target_fd in (0, 1):
                os.dup2(null_fd, target_fd)
            os.dup2(stderr_write, 2)
            if null_fd > 2:
                os.close(null_fd)
            if stderr_write > 2:
                os.close(stderr_write)
            env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "HOME": str(inert_home), "TMPDIR": str(inert_home)}
            os.execve(argv[0], argv, env)
        except BaseException as exc:
            error_type = type(exc).__name__
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
                error_type = "Exception"
            error_number = getattr(exc, "errno", None)
            if not isinstance(error_number, int):
                error_number = None
            try:
                os.write(exec_write, canonical({"error_type": error_type, "errno": error_number}))
            except OSError:
                pass
            os._exit(126)
    os.close(read_gate)
    os.close(stderr_write)
    os.close(exec_write)
    pidfd = None
    try:
        os.set_blocking(stderr_read, False)
        os.set_blocking(exec_read, False)
        pidfd = os.pidfd_open(pid, 0)
        fact = proc_fact(pid)
        if fact is None:
            raise RuntimeError("QEMU child identity unavailable")
        return pid, pidfd, write_gate, stderr_read, exec_read, fact
    except BaseException as original:
        for fd in (write_gate, stderr_read, exec_read):
            try:
                os.close(fd)
            except OSError:
                pass
        if pidfd is not None:
            try:
                os.close(pidfd)
            except OSError:
                pass
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            wait_direct_child(pid, 0)
        except BaseException as cleanup_error:
            raise original from cleanup_error
        raise original


def drain_qemu_stderr(fd: int, captured: bytearray, state: dict) -> bool:
    """Drain without blocking; retain only the first STREAM_MAX bytes."""
    if state.get("truncated"):
        return True
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return True
        if not chunk:
            return False
        remaining = max(0, policy.STREAM_MAX - len(captured))
        captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            state["truncated"] = True
            state["bytes_observed_at_least"] = policy.STREAM_MAX + 1
            # Return immediately so the caller enters exact-child cleanup;
            # a continuously writable pipe must not monopolize the controller.
            return True
        elif not state["truncated"]:
            state["bytes_observed_at_least"] = len(captured)


def read_exec_sentinel(fd: int, captured: bytearray) -> bool:
    """Return True only after the close-on-exec writer has closed."""
    while True:
        try:
            chunk = os.read(fd, 512)
        except BlockingIOError:
            return False
        if not chunk:
            return True
        captured.extend(chunk)
        if len(captured) > 4096:
            raise RuntimeError("exec sentinel cap")


def verify_live_qemu_exe(pid: int, expected_fact: dict, expected_tool: dict) -> dict:
    if proc_fact(pid) != expected_fact:
        raise RuntimeError("QEMU identity before executable verification")
    path = Path(f"/proc/{pid}/exe")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 512 * policy.MIB:
            raise RuntimeError("QEMU executable type/size")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            total += len(block)
            if total > 512 * policy.MIB:
                raise RuntimeError("QEMU executable grew beyond cap")
            digest.update(block)
        after = os.fstat(fd)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise RuntimeError("QEMU executable changed while read")
    finally:
        os.close(fd)
    observed = {
        "path": str(QEMU_SYSTEM), "sha256": digest.hexdigest(), "bytes": total,
        "device": after.st_dev, "inode": after.st_ino,
    }
    if observed != expected_tool or proc_fact(pid) != expected_fact:
        raise RuntimeError("QEMU executable identity")
    return {
        "verified": True, "sha256": observed["sha256"], "bytes": total,
        "device": observed["device"], "inode": observed["inode"],
        "pid": pid, "start_ticks": expected_fact["start_ticks"],
        "cgroup": expected_fact["cgroup"],
    }


def socket_lstat(path: Path) -> dict:
    if path.name not in {"serial.sock", "qmp.sock"}:
        raise RuntimeError("diagnostic socket name")
    try:
        value = path.lstat()
    except FileNotFoundError:
        return {"name": path.name, "exists": False}
    if stat.S_ISSOCK(value.st_mode):
        kind = "socket"
    elif stat.S_ISLNK(value.st_mode):
        kind = "symlink"
    elif stat.S_ISREG(value.st_mode):
        kind = "regular"
    elif stat.S_ISDIR(value.st_mode):
        kind = "directory"
    else:
        kind = "other"
    return {
        "name": path.name, "exists": True, "type": kind,
        "mode": stat.S_IMODE(value.st_mode), "uid": value.st_uid, "gid": value.st_gid,
        "nlink": value.st_nlink, "size": value.st_size,
        "device": value.st_dev, "inode": value.st_ino,
    }


def wait_status_fact(status: int) -> dict:
    if os.WIFEXITED(status):
        return {"kind": "exited", "code": os.WEXITSTATUS(status)}
    if os.WIFSIGNALED(status):
        return {"kind": "signaled", "signal": os.WTERMSIG(status), "core_dumped": os.WCOREDUMP(status)}
    raise RuntimeError("unsupported direct-child wait status")


def reap_direct_child(pid: int, pidfd: int, state: dict, phase: str) -> bool:
    """Consume the exact direct child once after held-pidfd readiness."""
    if state["reaped"] or not select.select([pidfd], [], [], 0)[0]:
        return False
    if state["wait_attempted"]:
        raise RuntimeError("direct-child wait already attempted")
    state["wait_attempted"] = True
    waited, status = wait_direct_child(pid, os.WNOHANG)
    if waited != pid:
        raise RuntimeError("pidfd ready without direct-child wait status")
    state.update({"reaped": True, "status": status, "phase": phase})
    return True


def validate_qemu_completion(
    *, stderr_open: bool, stderr_state: dict, exec_open: bool, exec_bytes: bytes,
    exec_identity: dict | None, child_state: dict,
) -> dict:
    if stderr_state.get("truncated") is not False or stderr_open:
        raise RuntimeError("QEMU stderr final state")
    if exec_open or exec_bytes or not isinstance(exec_identity, dict) or exec_identity.get("verified") is not True:
        raise RuntimeError("QEMU exec final state")
    if (child_state.get("wait_attempted") is not True
            or child_state.get("reaped") is not True
            or child_state.get("phase") != "runtime"):
        raise RuntimeError("QEMU direct-child final state")
    observed = wait_status_fact(child_state.get("status"))
    if observed != {"kind": "exited", "code": 0}:
        raise RuntimeError("QEMU did not exit zero")
    return observed


def preserve_primary_during_diagnostic(primary: str, label: str, action) -> str:
    """Run failure-only evidence work without replacing the triggering error."""
    try:
        action()
    except BaseException as exc:
        return primary + "; " + label + " failed: " + type(exc).__name__
    return primary


def cgroup_members(cgroup: Path) -> list[int]:
    values = (cgroup / "cgroup.procs").read_text().split()
    if any(not value.isdecimal() or int(value) <= 0 for value in values):
        raise RuntimeError("cgroup member syntax")
    pids = [int(value) for value in values]
    if len(pids) != len(set(pids)):
        raise RuntimeError("duplicate cgroup member")
    return sorted(pids)


def cgroup_control_state() -> dict[str, list[str]]:
    controllers = sorted(set((CGROUP_ROOT / "cgroup.controllers").read_text().split()))
    enabled = sorted(set((CGROUP_ROOT / "cgroup.subtree_control").read_text().replace("+", "").split()))
    if (not REQUIRED_CGROUP_CONTROLLERS.issubset(controllers)
            or not REQUIRED_CGROUP_CONTROLLERS.issubset(enabled)):
        raise RuntimeError("required root cgroup controllers")
    return {"controllers": controllers, "subtree_control": enabled}


def cgroup_receipt(cg: dict, cgroup: Path) -> tuple[dict, dict, list[int], list[int], list[int]]:
    if (not CGROUP_NAME.fullmatch(cgroup.name) or cgroup.parent != CGROUP_ROOT
            or cg.get("path") != str(cgroup)):
        raise RuntimeError("cgroup direct root leaf")
    control = cg.get("control_parent")
    source = cg.get("source")
    leaf_identity = cg.get("identity")
    if (not isinstance(control, dict) or control.get("path") != str(CGROUP_ROOT)
            or control.get("cgroup") != "/" or not isinstance(source, dict)
            or not isinstance(leaf_identity, list) or len(leaf_identity) != 2):
        raise RuntimeError("cgroup receipt fields")
    control_identity = control.get("identity")
    source_identity = source.get("identity")
    source_cgroup = source.get("cgroup")
    if (not isinstance(control_identity, list) or len(control_identity) != 2
            or not isinstance(source_identity, list) or len(source_identity) != 2
            or not isinstance(source_cgroup, str) or not source_cgroup.startswith("/")
            or source_cgroup == "/" or ".." in Path(source_cgroup).parts):
        raise RuntimeError("cgroup receipt identity")
    source_path = CGROUP_ROOT / source_cgroup.lstrip("/")
    if source.get("path") != str(source_path) or source_path == CGROUP_ROOT:
        raise RuntimeError("cgroup source receipt")
    control_stat = CGROUP_ROOT.stat()
    source_stat = source_path.stat()
    leaf_stat = cgroup.stat()
    if (not stat.S_ISDIR(control_stat.st_mode) or not stat.S_ISDIR(source_stat.st_mode)
            or not stat.S_ISDIR(leaf_stat.st_mode)
            or [control_stat.st_dev, control_stat.st_ino] != control_identity
            or [source_stat.st_dev, source_stat.st_ino] != source_identity
            or [leaf_stat.st_dev, leaf_stat.st_ino] != leaf_identity):
        raise RuntimeError("cgroup receipt identity changed")
    observed_controls = cgroup_control_state()
    if (control.get("controllers") != observed_controls["controllers"]
            or control.get("subtree_control") != observed_controls["subtree_control"]):
        raise RuntimeError("cgroup controller receipt changed")
    return control, source, control_identity, source_identity, leaf_identity


def receipt_identity(value: object, label: str) -> list[int]:
    if (not isinstance(value, list) or len(value) != 2
            or any(not isinstance(item, int) or item <= 0 for item in value)):
        raise RuntimeError("lifecycle receipt identity: " + label)
    return value


def receipt_fact(value: object, label: str) -> dict:
    if (not isinstance(value, dict) or set(value) != {"pid", "start_ticks", "cgroup"}
            or not isinstance(value.get("pid"), int) or value["pid"] <= 0
            or not isinstance(value.get("start_ticks"), int) or value["start_ticks"] <= 0
            or not isinstance(value.get("cgroup"), str) or not value["cgroup"].startswith("/")
            or len(value["cgroup"]) > 512):
        raise RuntimeError("lifecycle process fact: " + label)
    return value


def receipt_privileged_fact(value: object, label: str) -> dict:
    if (not isinstance(value, dict)
            or set(value) != {"pid", "start_ticks", "cgroup", "uids", "gids"}):
        raise RuntimeError("lifecycle privileged process fact: " + label)
    receipt_fact({key: value[key] for key in ("pid", "start_ticks", "cgroup")}, label)
    for key in ("uids", "gids"):
        ids = value.get(key)
        if (not isinstance(ids, list) or len(ids) != 4
                or any(not isinstance(item, int) or item <= 0 for item in ids)
                or len(set(ids)) != 1):
            raise RuntimeError("lifecycle privileged process ids: " + label)
    return value


def load_fixed_receipt(path: Path, cap: int = 16384) -> tuple[bytes, object]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RuntimeError("lifecycle receipt open: " + path.name) from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_size <= 0 or before.st_size > cap):
            raise RuntimeError("lifecycle receipt owner/type/mode/cap: " + path.name)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(cap + 1)
        after = os.fstat(fd)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        current = path.lstat()
        if (len(raw) != before.st_size or identity(before) != identity(after)
                or identity(after) != identity(current)):
            raise RuntimeError("lifecycle receipt changed while read: " + path.name)
    finally:
        os.close(fd)
    return raw, json.loads(raw)


def read_fixed_private_log(path: Path, cap: int = policy.STREAM_MAX) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RuntimeError("diagnostic log open: " + path.name) from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o077
                or before.st_size > cap):
            raise RuntimeError("diagnostic log owner/type/mode/cap: " + path.name)
        raw = b""
        while len(raw) <= cap:
            block = os.read(fd, min(65536, cap + 1 - len(raw)))
            if not block:
                break
            raw += block
        after = os.fstat(fd)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        current = path.lstat()
        if (len(raw) != before.st_size or len(raw) > cap
                or identity(before) != identity(after) or identity(after) != identity(current)):
            raise RuntimeError("diagnostic log changed while read: " + path.name)
        return raw
    finally:
        os.close(fd)


def validate_create_receipt(value: object) -> dict:
    expected = {"path", "identity", "control_parent", "source", *CGROUP_LIMITS}
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError("cgroup create receipt fields")
    path = Path(value["path"]) if isinstance(value.get("path"), str) else Path(".")
    if path.parent != CGROUP_ROOT or not CGROUP_NAME.fullmatch(path.name):
        raise RuntimeError("cgroup create receipt path")
    receipt_identity(value["identity"], "leaf")
    control = value["control_parent"]
    source = value["source"]
    if (not isinstance(control, dict)
            or set(control) != {"path", "identity", "cgroup", "controllers", "subtree_control"}
            or control.get("path") != str(CGROUP_ROOT) or control.get("cgroup") != "/"):
        raise RuntimeError("cgroup create control parent")
    receipt_identity(control["identity"], "control-parent")
    for key in ("controllers", "subtree_control"):
        controllers = control.get(key)
        if (not isinstance(controllers, list) or controllers != sorted(set(controllers))
                or any(not isinstance(item, str) or len(item) > 32 for item in controllers)
                or not REQUIRED_CGROUP_CONTROLLERS.issubset(controllers)):
            raise RuntimeError("cgroup create controller receipt")
    if (not isinstance(source, dict) or set(source) != {"path", "identity", "cgroup"}
            or not isinstance(source.get("cgroup"), str) or source["cgroup"] in ("", "/")
            or not source["cgroup"].startswith("/") or ".." in Path(source["cgroup"]).parts
            or source.get("path") != str(CGROUP_ROOT / source["cgroup"].lstrip("/"))):
        raise RuntimeError("cgroup create source")
    receipt_identity(source["identity"], "source")
    if any(value.get(name) != expected_value for name, expected_value in CGROUP_LIMITS.items()):
        raise RuntimeError("cgroup create limits")
    return value


def validate_attach_receipt(value: object, create: dict) -> dict:
    expected = {
        "operation", "control_parent", "source", "leaf", "limits",
        "before", "after", "members",
    }
    if (not isinstance(value, dict) or set(value) != expected
            or value.get("operation") != "attach"
            or value.get("control_parent") != create["control_parent"]
            or value.get("source") != create["source"]
            or value.get("leaf") != {"path": create["path"], "identity": create["identity"]}
            or value.get("limits") != CGROUP_LIMITS):
        raise RuntimeError("cgroup attach receipt binding")
    members = value.get("members")
    before = receipt_privileged_fact(value.get("before"), "attach-before")
    after = receipt_privileged_fact(value.get("after"), "attach-after")
    if (not isinstance(members, list) or len(members) != 1
            or members[0] != before["pid"] or after["pid"] != before["pid"]
            or after["start_ticks"] != before["start_ticks"]
            or after["uids"] != before["uids"] or after["gids"] != before["gids"]
            or before["cgroup"] != create["source"]["cgroup"]
            or after["cgroup"] != "/" + Path(create["path"]).name):
        raise RuntimeError("cgroup attach process binding")
    return value


def validate_lifecycle_receipts(
    values: dict[str, object], attachment: object | None = None,
) -> None:
    create = validate_create_receipt(values["cgroup-create.json"])
    path = create["path"]
    identity = create["identity"]
    attach = validate_attach_receipt(attachment, create) if attachment is not None else None
    destroy = values.get("cgroup-destroy.json")
    if destroy is not None and (
        not isinstance(destroy, dict) or set(destroy) != {"removed", "path", "identity"}
        or destroy.get("removed") is not True or destroy.get("path") != path
        or destroy.get("identity") != identity
    ):
        raise RuntimeError("cgroup destroy receipt")
    cleanup = values.get("cleanup-wait.json")
    if cleanup is not None and (
        not isinstance(cleanup, dict)
        or set(cleanup) != {"cgroup_empty", "handoff_seen", "watchdog_result_seen"}
        or cleanup.get("cgroup_empty") is not True
        or not isinstance(cleanup.get("handoff_seen"), bool)
        or not isinstance(cleanup.get("watchdog_result_seen"), bool)
    ):
        raise RuntimeError("cleanup wait receipt")
    if destroy is not None and cleanup is None:
        raise RuntimeError("destroy receipt without cleanup proof")
    ready = values.get("watchdog-ready.json")
    if ready is not None:
        if not isinstance(ready, dict) or set(ready) != {"ready", "qemu", "watchdog"} or ready.get("ready") is not True:
            raise RuntimeError("watchdog ready receipt")
        receipt_fact(ready.get("qemu"), "watchdog-ready-qemu")
        receipt_fact(ready.get("watchdog"), "watchdog-ready-watchdog")
    result = values.get("watchdog-result.json")
    if result is not None:
        if (not isinstance(result, dict)
                or set(result) != {"forced_cleanup", "reason", "cgroup_empty", "events", "cgroup_counters", "cgroup_counter_error"}
                or not isinstance(result.get("forced_cleanup"), bool)
                or not isinstance(result.get("cgroup_empty"), bool)
                or not isinstance(result.get("reason"), str) or len(result["reason"]) > 256
                or not isinstance(result.get("events"), list) or len(result["events"]) > 128):
            raise RuntimeError("watchdog result receipt")
        counters = result.get("cgroup_counters")
        counter_error = result.get("cgroup_counter_error")
        if counters is None:
            if (not isinstance(counter_error, dict)
                    or set(counter_error) != {"error_type", "message", "message_truncated"}
                    or not isinstance(counter_error.get("error_type"), str)
                    or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", counter_error["error_type"])
                    or not isinstance(counter_error.get("message"), str) or len(counter_error["message"]) > 256
                    or not isinstance(counter_error.get("message_truncated"), bool)):
                raise RuntimeError("watchdog cgroup counter error")
        else:
            if counter_error is not None or not isinstance(counters, dict) or set(counters) != {"memory.events", "pids.events"}:
                raise RuntimeError("watchdog cgroup counter files")
            for name, values in counters.items():
                if (not isinstance(values, dict) or not values or len(values) > 32
                        or any(not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", key)
                               or not isinstance(number, int) or isinstance(number, bool) or number < 0
                               for key, number in values.items())):
                    raise RuntimeError("watchdog cgroup counters: " + name)
        for event in result["events"]:
            if (not isinstance(event, dict) or set(event) != {"op", "signal", "identity"}
                    or event.get("op") != "pidfd_send_signal"
                    or event.get("signal") not in (signal.SIGTERM, signal.SIGKILL)):
                raise RuntimeError("watchdog event receipt")
            fact = receipt_fact(event.get("identity"), "watchdog-event")
            if fact["cgroup"] != "/" + Path(path).name:
                raise RuntimeError("watchdog event cgroup binding")
    if cleanup is not None and cleanup["watchdog_result_seen"] != (result is not None):
        raise RuntimeError("cleanup watchdog result binding")
    if result is not None and (cleanup is None or result["cgroup_empty"] is not True):
        raise RuntimeError("watchdog result lifecycle binding")
    if ready is None and result is not None:
        if (cleanup["handoff_seen"] is not False or result["forced_cleanup"] is not True
                or result["reason"] not in {
                    "controller-cleanup-request-before-handoff",
                    "parent-exited-before-handoff",
                    "handoff-timeout",
                }):
            raise RuntimeError("pre-handoff watchdog lifecycle binding")
    if ready is not None:
        if (result is None or attach is None or cleanup is None
                or cleanup["handoff_seen"] is not True):
            raise RuntimeError("watchdog ready lifecycle binding")
        if (ready["qemu"]["pid"] != attach["after"]["pid"]
                or ready["qemu"]["start_ticks"] != attach["after"]["start_ticks"]
                or ready["qemu"]["cgroup"] != attach["after"]["cgroup"]
                or ready["watchdog"]["cgroup"] != create["source"]["cgroup"]):
            raise RuntimeError("watchdog ready process binding")


def retain_lifecycle_receipts(root: Path) -> None:
    evidence = root / "evidence"
    create_path = root / "cgroup.json"
    if not create_path.exists() and not create_path.is_symlink():
        return
    raw_values: dict[str, bytes] = {}
    values: dict[str, object] = {}
    for source_name, evidence_name in LIFECYCLE_RECEIPTS.items():
        source = root / source_name
        if source.exists() or source.is_symlink():
            raw, value = load_fixed_receipt(source)
            raw_values[evidence_name] = raw
            values[evidence_name] = value
    attachment = evidence / "cgroup-attach.json"
    attach = None
    if attachment.exists():
        _, attach = load_fixed_receipt(attachment, policy.STREAM_MAX)
    validate_lifecycle_receipts(values, attach)
    for name, raw in raw_values.items():
        destination = evidence / name
        if destination.exists() or destination.is_symlink():
            observed, _ = load_fixed_receipt(destination, ALLOWED_EVIDENCE[name])
            if observed != raw:
                raise RuntimeError("lifecycle evidence changed: " + name)
        else:
            exclusive(destination, raw, cap=ALLOWED_EVIDENCE[name])


def attach_qemu(cg: dict, cgroup: Path, pid: int, pidfd: int, before: dict) -> tuple[dict, dict]:
    control, source, control_identity, source_identity, leaf_identity = cgroup_receipt(cg, cgroup)
    if before.get("cgroup") != source.get("cgroup"):
        raise RuntimeError("paused child source cgroup")
    if cgroup_members(cgroup):
        raise RuntimeError("cgroup not empty before privileged attach")
    argv = [
        "/usr/bin/sudo", sys.executable, "-I", "-B", str(HERE / "cgroup_admin.py"), "attach",
        cgroup.name, str(control_identity[0]), str(control_identity[1]),
        str(source_identity[0]), str(source_identity[1]),
        str(leaf_identity[0]), str(leaf_identity[1]),
        ",".join(control["controllers"]), ",".join(control["subtree_control"]),
        str(pid), str(before["start_ticks"]),
        str(os.getuid()), str(os.getgid()), str(before["cgroup"]),
    ]
    receipt_raw = command(argv, timeout=10, output_cap=16384)
    receipt = json.loads(receipt_raw)
    expected_cgroup = "/" + str(cgroup.relative_to("/sys/fs/cgroup"))
    after = proc_fact(pid)
    if (select.select([pidfd], [], [], 0)[0] or after is None
            or after != {"pid": pid, "start_ticks": before["start_ticks"], "cgroup": expected_cgroup}):
        raise RuntimeError("paused child post-attach identity")
    if cgroup_members(cgroup) != [pid]:
        raise RuntimeError("paused child post-attach membership")
    cgroup_receipt(cg, cgroup)
    if policy.verify_limits(lambda name: (cgroup / name).read_text()) != receipt.get("limits"):
        raise RuntimeError("privileged attach limit receipt")
    if (receipt.get("operation") != "attach" or receipt.get("members") != [pid]
            or receipt.get("control_parent") != control
            or receipt.get("source") != source
            or receipt.get("leaf") != {"path": str(cgroup), "identity": leaf_identity}):
        raise RuntimeError("privileged attach receipt binding")
    receipt_after = receipt.get("after")
    receipt_before = receipt.get("before")
    if (not isinstance(receipt_before, dict) or receipt_before.get("pid") != pid
            or receipt_before.get("start_ticks") != before["start_ticks"]
            or receipt_before.get("cgroup") != before["cgroup"]
            or receipt_before.get("uids") != [os.getuid()] * 4
            or receipt_before.get("gids") != [os.getgid()] * 4):
        raise RuntimeError("privileged attach source receipt")
    if (not isinstance(receipt_after, dict) or receipt_after.get("pid") != pid
            or receipt_after.get("start_ticks") != before["start_ticks"]
            or receipt_after.get("cgroup") != expected_cgroup
            or receipt_after.get("uids") != [os.getuid()] * 4
            or receipt_after.get("gids") != [os.getgid()] * 4):
        raise RuntimeError("privileged attach process receipt")
    return receipt, after


def connect_unix(path: Path, deadline: float, progress=None) -> socket.socket:
    while time.monotonic() < deadline:
        if progress is not None:
            progress()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(path))
            sock.setblocking(False)
            return sock
        except (FileNotFoundError, ConnectionRefusedError):
            sock.close()
            time.sleep(0.05)
    raise RuntimeError("Unix socket connect deadline: " + path.name)


def qmp_handshake(
    sock: socket.socket, stderr_fd: int, stderr_prefix: bytearray, stderr_state: dict,
) -> tuple[bytearray, list[dict], int, bool]:
    """Read the two strict QMP lines while concurrently draining QEMU stderr."""
    sock.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(sock, selectors.EVENT_READ, "qmp")
    selector.register(stderr_fd, selectors.EVENT_READ, "stderr")
    qmp_buffer = bytearray()
    qmp_total = 0
    stderr_open = True

    def line(deadline: float) -> bytes:
        nonlocal qmp_buffer, qmp_total, stderr_open
        while time.monotonic() < deadline:
            if b"\n" in qmp_buffer:
                raw, _, qmp_buffer = qmp_buffer.partition(b"\n")
                return raw + b"\n"
            ready = selector.select(min(0.1, max(0, deadline - time.monotonic())))
            for key, _ in ready:
                if key.data == "stderr":
                    stderr_open = drain_qemu_stderr(stderr_fd, stderr_prefix, stderr_state)
                    if not stderr_open:
                        selector.unregister(stderr_fd)
                else:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise RuntimeError("QMP closed during handshake")
                    qmp_total = policy.charge_stream(qmp_total, len(chunk), policy.STREAM_MAX)
                    qmp_buffer.extend(chunk)
            if stderr_state["truncated"]:
                raise RuntimeError("QEMU stderr cap")
        raise RuntimeError("QMP handshake deadline")

    try:
        greeting = line(time.monotonic() + 3)
        hello = json.loads(greeting)
        if "QMP" not in hello:
            raise RuntimeError("QMP greeting")
        sock.sendall(b'{"execute":"qmp_capabilities"}\r\n')
        reply = line(time.monotonic() + 3)
        if json.loads(reply) != {"return": {}}:
            raise RuntimeError("QMP capability negotiation")
        return qmp_buffer, [], qmp_total, stderr_open
    finally:
        selector.close()


def retain_and_validate_qemu_img_info(
    evidence: Path, raw: bytes, *, base_path: Path, physical_size: int,
    allocated_size: int,
) -> dict:
    raw_path = evidence / "qemu-img-info.raw.json"
    exclusive(raw_path, raw, cap=policy.STREAM_MAX)
    try:
        parsed = json.loads(raw)
        return policy.validate_qemu_img_info(
            parsed, base_path=base_path, physical_size=physical_size,
            allocated_size=allocated_size,
        )
    except Exception as exc:
        error_type = type(exc).__name__
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
            error_type = "Exception"
        message = str(exc)
        json_write(
            evidence / "qemu-img-info-failure.json",
            {
                "schema": "dm-qemu-img-info-failure-v1",
                "accepted": False,
                "error_type": error_type,
                "error": message[:1024],
                "error_truncated": len(message) > 1024,
                "raw_bytes": len(raw),
                "raw_sha256": policy.sha_bytes(raw),
            },
        )
        raise


def retain_and_validate_qemu_img_check(evidence: Path, raw: bytes, *, base_path: Path) -> dict:
    raw_path = evidence / "qemu-img-check.raw.json"
    exclusive(raw_path, raw, cap=policy.STREAM_MAX)
    try:
        parsed = json.loads(raw)
        return policy.validate_qemu_img_check(parsed, base_path=base_path)
    except Exception as exc:
        error_type = type(exc).__name__
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
            error_type = "Exception"
        message = str(exc)
        json_write(
            evidence / "qemu-img-check-failure.json",
            {
                "schema": "dm-qemu-img-check-failure-v1",
                "accepted": False,
                "error_type": error_type,
                "error": message[:1024],
                "error_truncated": len(message) > 1024,
                "raw_bytes": len(raw),
                "raw_sha256": policy.sha_bytes(raw),
            },
        )
        raise


def boot(root: Path, cgroup_json: Path) -> None:
    context = read_context(root)
    evidence = root / "evidence"
    apt_raw = (evidence / "apt-observation.json").read_bytes()
    if len(apt_raw) > policy.STREAM_MAX:
        raise RuntimeError("APT observation cap")
    expected_tools = json.loads(apt_raw).get("tools")
    if not isinstance(expected_tools, dict):
        raise RuntimeError("APT tool observations missing")
    for name, path, cap in (
        ("qemu-system-x86_64", QEMU_SYSTEM, 512 * policy.MIB),
        ("qemu-img", QEMU_IMG, 512 * policy.MIB),
        ("cloud-localds", CLOUD_LOCALDS, 16 * policy.MIB),
        ("seabios", SEABIOS, 4 * policy.MIB),
    ):
        if secure_system_file(path, cap) != expected_tools.get(name):
            raise RuntimeError("system tool changed after authenticated APT observation: " + name)
    base = root / "base.qcow2"
    base_sha, base_size = policy.sha_file(base, policy.IMAGE_MAX)
    if base_sha != policy.IMAGE_SHA256:
        raise RuntimeError("base recheck before parsing")
    base_stat = base.stat()
    allocated_size = base_stat.st_blocks * 512
    if not 0 <= allocated_size <= policy.IMAGE_MAX:
        raise RuntimeError("base allocated-size bound")
    info_raw = command([str(QEMU_IMG), "info", "--output=json", str(base)], timeout=20)
    image_info = retain_and_validate_qemu_img_info(
        evidence, info_raw, base_path=base, physical_size=base_size,
        allocated_size=allocated_size,
    )
    check_raw = command([str(QEMU_IMG), "check", "--output=json", str(base)], timeout=60)
    image_check = retain_and_validate_qemu_img_check(evidence, check_raw, base_path=base)
    source = (HERE / "guest_bootstrap.py").read_bytes()
    source_sha = policy.sha_bytes(source)
    seed = make_seed(root, context["nonce"], source, source_sha)
    seed_sha, _ = policy.sha_file(seed, policy.SEED_MAX)
    overlay = root / "overlay.qcow2"
    command([str(QEMU_IMG), "create", "-f", "qcow2", "-F", "qcow2", "-b", str(base), str(overlay)], timeout=20, fsize=policy.OVERLAY_MAX)
    overlay.chmod(0o600)
    overlay_initial, _ = policy.sha_file(overlay, policy.OVERLAY_MAX)
    cg = json.loads(cgroup_json.read_bytes())
    cgroup = Path(cg["path"])
    cst = cgroup.stat()
    if cg.get("identity") != [cst.st_dev, cst.st_ino]:
        raise RuntimeError("cgroup identity")
    control, source_cgroup, _, _, _ = cgroup_receipt(cg, cgroup)
    limits = policy.verify_limits(lambda name: (cgroup / name).read_text())
    if (cgroup / "cgroup.procs").read_text().strip():
        raise RuntimeError("cgroup not initially empty")
    qemu = str(QEMU_SYSTEM)
    bios = SEABIOS
    serial_socket = root / "serial.sock"
    qmp_socket = root / "qmp.sock"
    inert_home = root / "qemu-no-write-home"
    inert_home.mkdir(mode=0o500)
    normalized = {
        str(base): "$WORK/base.qcow2", str(overlay): "$WORK/overlay.qcow2", str(seed): "$WORK/seed.iso",
        str(serial_socket): "$WORK/serial.sock", str(qmp_socket): "$WORK/qmp.sock", str(bios): "$SEABIOS/bios-256k.bin", qemu: "$QEMU",
    }
    argv_template = [
        qemu, "-nodefaults", "-no-user-config", "-machine", "pc,accel=tcg", "-accel", "tcg,thread=single",
        "-cpu", "max", "-m", "2048", "-smp", "2", "-bios", str(bios), "-display", "none", "-nic", "none",
        "-monitor", "none", "-parallel", "none", "-no-reboot", "-boot", "strict=on",
        "-drive", "if=none,id=root,file=" + str(overlay) + ",format=qcow2,cache=none,aio=threads",
        "-device", "virtio-blk-pci,drive=root,bootindex=1",
        "-drive", "if=none,id=seed,file=" + str(seed) + ",format=raw,readonly=on",
        "-device", "virtio-blk-pci,drive=seed",
        "-chardev", "socket,id=serial0,path=" + str(serial_socket) + ",server=on,wait=off",
        "-serial", "chardev:serial0", "-qmp", "unix:" + str(qmp_socket) + ",server=on,wait=off",
        "-fw_cfg", "name=opt/dm/binding,string=<CONFIG_BINDING>",
    ]
    def normalize(token: str) -> str:
        for actual, label in sorted(normalized.items(), key=lambda pair: -len(pair[0])):
            token = token.replace(actual, label)
        return token
    document = {
        "schema": "dm-direct-boot-config-v1", "nonce": context["nonce"], "base_sha256": base_sha,
        "guest_source_sha256": source_sha, "seed_sha256": seed_sha, "overlay_initial_sha256": overlay_initial,
        "argv_template": [normalize(arg) for arg in argv_template], "machine": "pc,accel=tcg", "memory_mib": 2048, "cpus": 2,
    }
    binding = policy.boot_binding(document)
    argv = [arg.replace("<CONFIG_BINDING>", binding) for arg in argv_template]
    json_write(evidence / "boot-config.json", {**document, "binding": binding, "image_info": image_info, "image_check": image_check, "cgroup_limits": limits})
    launch_qemu = None
    for name, path, cap in (("qemu-system-x86_64", QEMU_SYSTEM, 512 * policy.MIB), ("seabios", SEABIOS, 4 * policy.MIB)):
        observed_tool = secure_system_file(path, cap)
        if observed_tool != expected_tools[name]:
            raise RuntimeError("launch-time tool digest changed: " + name)
        if name == "qemu-system-x86_64":
            launch_qemu = launch_executable_identity(path, observed_tool, cap)
    if launch_qemu is None:
        raise RuntimeError("launch-time QEMU identity missing")
    parent = proc_fact(os.getpid())
    if parent is None or parent.get("cgroup") != source_cgroup.get("cgroup"):
        raise RuntimeError("controller identity")
    wd_stderr_fd = os.open(
        root / "watchdog.stderr",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    wd_stderr = os.fdopen(wd_stderr_fd, "wb")
    watchdog = subprocess.Popen(
        [sys.executable, "-I", "-B", str(HERE / "qemu_watchdog.py"), str(root), str(os.getpid()), str(parent["start_ticks"]), str(cgroup), str(cst.st_dev), str(cst.st_ino)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=wd_stderr, close_fds=True, start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (policy.STREAM_MAX, policy.STREAM_MAX)),
    )
    pid = pidfd = gate = stderr_fd = exec_fd = fact = None
    natural = False
    primary = None
    qmp_events: list[dict] = []
    serial = bytearray()
    child_state = {"status": None, "reaped": False, "wait_attempted": False, "phase": None}
    exit_observed_before_cleanup = False
    stderr_open = True
    stderr_prefix = bytearray()
    stderr_state = {"truncated": False, "bytes_observed_at_least": 0}
    exec_open = True
    exec_bytes = bytearray()
    exec_identity = None
    stages = []
    socket_snapshots = {}
    diagnostics_written = False

    def record_stage(name: str) -> None:
        if name in socket_snapshots or len(stages) >= 12:
            raise RuntimeError("QEMU startup stage ledger")
        stages.append(name)
        socket_snapshots[name] = [socket_lstat(serial_socket), socket_lstat(qmp_socket)]

    def drain_stderr() -> None:
        nonlocal stderr_open
        if stderr_fd is not None and stderr_open:
            stderr_open = drain_qemu_stderr(stderr_fd, stderr_prefix, stderr_state)

    def startup_progress() -> None:
        nonlocal exec_open, exec_identity, exit_observed_before_cleanup
        drain_stderr()
        if stderr_state["truncated"]:
            raise RuntimeError("QEMU stderr cap")
        if exec_fd is not None and exec_open:
            exec_open = not read_exec_sentinel(exec_fd, exec_bytes)
        exited = pidfd is not None and bool(select.select([pidfd], [], [], 0)[0])
        if exited:
            exit_observed_before_cleanup = True
        if exec_bytes:
            raise RuntimeError("QEMU execve sentinel error")
        if not exec_open and exec_identity is None:
            if exited:
                raise RuntimeError("QEMU exited before live executable proof")
            try:
                exec_identity = verify_live_qemu_exe(pid, fact, launch_qemu)
            except BaseException:
                exec_identity = {"verified": False, "reason": "live-executable-verification-failed"}
                raise
        if exited:
            raise RuntimeError("QEMU exited before socket readiness")

    def reap_if_exited(phase: str) -> None:
        if pid is None or pidfd is None:
            return
        reap_direct_child(pid, pidfd, child_state, phase)

    def persist_diagnostics() -> None:
        nonlocal diagnostics_written, exec_open
        if diagnostics_written:
            return
        drain_stderr()
        if exec_fd is not None and exec_open:
            exec_open = not read_exec_sentinel(exec_fd, exec_bytes)
        if stderr_fd is not None and stderr_open:
            # The direct child is expected to be gone before persistence. A
            # still-open pipe is reported as incomplete rather than trusted.
            stderr_state["truncated"] = True
        if not wd_stderr.closed:
            wd_stderr.close()
        watchdog_raw = read_fixed_private_log(root / "watchdog.stderr")
        exclusive(evidence / "qemu-stderr.log", bytes(stderr_prefix), cap=policy.STREAM_MAX)
        exclusive(evidence / "watchdog-stderr.log", watchdog_raw, cap=policy.STREAM_MAX)
        exec_error = None
        if exec_bytes:
            try:
                candidate = json.loads(bytes(exec_bytes))
                if (isinstance(candidate, dict) and set(candidate) == {"error_type", "errno"}
                        and isinstance(candidate["error_type"], str)
                        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", candidate["error_type"])
                        and (candidate["errno"] is None
                             or (isinstance(candidate["errno"], int)
                                 and not isinstance(candidate["errno"], bool)))):
                    exec_error = candidate
                else:
                    exec_error = {"error_type": "MalformedSentinel", "errno": None}
            except (UnicodeError, json.JSONDecodeError):
                exec_error = {"error_type": "MalformedSentinel", "errno": None}
        json_write(
            evidence / "qemu-startup.json",
            {
                "schema": "dm-qemu-startup-diagnostics-v1",
                "qemu": fact if pid is not None else None,
                "stages": stages,
                "socket_snapshots": socket_snapshots,
                "exec_sentinel_closed": not exec_open,
                "exec_error": exec_error,
                "exec_identity": exec_identity,
                "exit_observed_before_cleanup": exit_observed_before_cleanup,
                "direct_child_wait_attempted": child_state["wait_attempted"],
                "direct_child_reaped": child_state["reaped"],
                "direct_child_exit_phase": child_state["phase"],
                "direct_child_wait_status": wait_status_fact(child_state["status"]) if child_state["status"] is not None else None,
                "stderr": {
                    "retained_prefix_bytes": len(stderr_prefix),
                    "retained_prefix_sha256": policy.sha_bytes(bytes(stderr_prefix)),
                    "bytes_observed_at_least": stderr_state["bytes_observed_at_least"],
                    "truncated": stderr_state["truncated"],
                },
                "watchdog_stderr": {
                    "bytes": len(watchdog_raw), "sha256": policy.sha_bytes(watchdog_raw),
                },
                "primary_error": primary,
                "claim_limit": "startup diagnostics only; not proof of guest boot, G0, E1, or E2",
            },
        )
        diagnostics_written = True
    try:
        record_stage("before-spawn")
        pid, pidfd, gate, stderr_fd, exec_fd, fact = spawn_qemu(argv, inert_home)
        record_stage("child-paused")
        attachment, fact = attach_qemu(cg, cgroup, pid, pidfd, fact)
        json_write(evidence / "cgroup-attach.json", attachment)
        record_stage("child-attached")
        atomic_json_publish(root / "qemu-handoff.json", {
            "qemu": fact, "cgroup_path": str(cgroup), "cgroup_identity": cg["identity"],
            "attach_receipt_sha256": policy.sha_bytes(canonical(attachment)),
        })
        ready_deadline = time.monotonic() + 10
        while not (root / "watchdog-ready.json").exists():
            if watchdog.poll() is not None or time.monotonic() > ready_deadline:
                raise RuntimeError("watchdog readiness")
            time.sleep(0.05)
        record_stage("watchdog-ready")
        os.write(gate, b"G")
        os.close(gate); gate = None
        record_stage("gate-released")
        expected_cgroup = "/" + str(cgroup.relative_to("/sys/fs/cgroup"))
        if proc_fact(pid) is None or proc_fact(pid)["cgroup"] != expected_cgroup:
            raise RuntimeError("QEMU effective cgroup membership")
        policy.verify_limits(lambda name: (cgroup / name).read_text())
        startup_progress()
        serial_sock = connect_unix(serial_socket, time.monotonic() + 5, startup_progress)
        record_stage("serial-connected")
        qmp_sock = connect_unix(qmp_socket, time.monotonic() + 5, startup_progress)
        record_stage("qmp-connected")
        startup_progress()
        if exec_identity is None or exec_identity.get("verified") is not True:
            raise RuntimeError("QEMU exec not positively identified")
        qmp_buffer, qmp_events, qmp_total, stderr_open = qmp_handshake(
            qmp_sock, stderr_fd, stderr_prefix, stderr_state,
        )
        selector = selectors.DefaultSelector()
        selector.register(serial_sock, selectors.EVENT_READ, "serial")
        selector.register(qmp_sock, selectors.EVENT_READ, "qmp")
        deadline = time.monotonic() + 10 * 60
        while time.monotonic() < deadline:
            drain_stderr()
            if stderr_state["truncated"]:
                raise RuntimeError("QEMU stderr cap")
            reap_if_exited("runtime")
            if child_state["reaped"]:
                break
            if watchdog.poll() is not None:
                raise RuntimeError("watchdog exited during QEMU")
            if overlay.stat().st_size > policy.OVERLAY_MAX or free_bytes(root) < policy.FREE_FLOOR:
                raise RuntimeError("runtime file/free-space bound")
            for key, _ in selector.select(0.1):
                chunk = key.fileobj.recv(65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "serial":
                    serial.extend(chunk)
                    if len(serial) > policy.SERIAL_MAX:
                        raise RuntimeError("serial cap")
                else:
                    qmp_total = policy.charge_stream(qmp_total, len(chunk), policy.STREAM_MAX)
                    qmp_buffer.extend(chunk)
                    while b"\r\n" in qmp_buffer:
                        line, _, qmp_buffer = qmp_buffer.partition(b"\r\n")
                        if line:
                            message = json.loads(line)
                            if "event" in message:
                                qmp_events.append(message)
        else:
            raise RuntimeError("QEMU boot deadline")
        # The final guest frame and SHUTDOWN event may already be queued when
        # waitpid reports exit. Drain only the existing bounded socket data.
        drain_deadline = time.monotonic() + 1
        while selector.get_map() and time.monotonic() < drain_deadline:
            ready = selector.select(0.05)
            if not ready:
                continue
            for key, _ in ready:
                chunk = key.fileobj.recv(65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "serial":
                    serial.extend(chunk)
                    if len(serial) > policy.SERIAL_MAX:
                        raise RuntimeError("serial cap")
                else:
                    qmp_total = policy.charge_stream(qmp_total, len(chunk), policy.STREAM_MAX)
                    qmp_buffer.extend(chunk)
                    while b"\r\n" in qmp_buffer:
                        line, _, qmp_buffer = qmp_buffer.partition(b"\r\n")
                        if line:
                            message = json.loads(line)
                            if "event" in message:
                                qmp_events.append(message)
        selector.close(); serial_sock.close(); qmp_sock.close()
        drain_stderr()
        validate_qemu_completion(
            stderr_open=stderr_open, stderr_state=stderr_state, exec_open=exec_open,
            exec_bytes=bytes(exec_bytes), exec_identity=exec_identity, child_state=child_state,
        )
        if not policy.qmp_shutdown_seen(qmp_events):
            raise RuntimeError("guest-requested QMP shutdown inference absent/ambiguous")
        guest = policy.parse_frame(bytes(serial), nonce=context["nonce"], binding=binding, guest_source_sha256=source_sha)
        if (cgroup / "cgroup.procs").read_text().strip() or "populated 0" not in (cgroup / "cgroup.events").read_text():
            raise RuntimeError("normal cgroup empty proof")
        memory_events = dict(line.split() for line in (cgroup / "memory.events").read_text().splitlines())
        if int(memory_events.get("oom", "-1")) != 0 or int(memory_events.get("oom_kill", "-1")) != 0:
            raise RuntimeError("cgroup OOM evidence")
        after = base.stat()
        if (after.st_dev, after.st_ino, after.st_size) != (base_stat.st_dev, base_stat.st_ino, base_stat.st_size):
            raise RuntimeError("base identity changed")
        if policy.sha_file(base, policy.IMAGE_MAX)[0] != policy.IMAGE_SHA256:
            raise RuntimeError("base final digest changed")
        overlay_final, overlay_bytes = policy.sha_file(overlay, policy.OVERLAY_MAX)
        json_write(evidence / "serial.json", {"sha256": policy.sha_bytes(bytes(serial)), "bytes": len(serial), "raw_retained": False})
        json_write(evidence / "guest-result.json", guest)
        json_write(evidence / "qmp.json", {"shutdown_inference": "QMP guest=true plus controlled cloud-init poweroff; not guest attestation", "events": qmp_events})
        json_write(evidence / "lifecycle.json", {"qemu_exit": 0, "natural": True, "forced_cleanup": False, "no_oom": True, "cgroup_empty": True, "base_unchanged": True, "overlay_final_sha256": overlay_final, "overlay_final_bytes": overlay_bytes})
        exclusive(root / "watchdog-release", b"normal\n", cap=32)
        watchdog.wait(timeout=10)
        result = json.loads((root / "watchdog-result.json").read_bytes())
        if watchdog.returncode or result.get("forced_cleanup") is not False or result.get("cgroup_empty") is not True:
            raise RuntimeError("watchdog normal handoff")
        record_stage("normal-watchdog-release")
        persist_diagnostics()
        natural = True
    except BaseException as exc:
        primary = type(exc).__name__ + ": " + str(exc)[:1024]
        # Diagnostics must never delay or suppress the safety cleanup path.
        primary = preserve_primary_during_diagnostic(
            primary, "failure snapshot", lambda: record_stage("failure-observed"),
        )
        if gate is not None:
            os.close(gate)
        try:
            exclusive(root / "cleanup-request", b"failure\n", cap=32)
        except FileExistsError:
            pass
        try:
            watchdog.wait(timeout=20)
        except subprocess.TimeoutExpired:
            primary += "; watchdog wait timeout"
        primary = preserve_primary_during_diagnostic(
            primary, "cleanup snapshot", lambda: record_stage("failure-cleanup-finished"),
        )
        primary = preserve_primary_during_diagnostic(primary, "stderr drain", drain_stderr)
        primary = preserve_primary_during_diagnostic(
            primary, "direct-child reap", lambda: reap_if_exited("after-watchdog-cleanup"),
        )
        primary = preserve_primary_during_diagnostic(primary, "diagnostics", persist_diagnostics)
        if not (evidence / "failure.json").exists():
            json_write(evidence / "failure.json", {"schema": "dm-direct-boot-failure-v1", "error": primary, "measurement_success": False})
    finally:
        if pidfd is not None:
            os.close(pidfd)
        for fd in (stderr_fd, exec_fd):
            if fd is not None:
                os.close(fd)
        if not wd_stderr.closed:
            wd_stderr.close()
    receipt = {"schema": "dm-direct-boot-intermediate-v1", "boot_success": natural and primary is None, "cgroup_removal_pending": True, "claim": "offline boot measurement only; G0/E1/E2 remain zero", "primary_error": primary}
    json_write(root / "boot-result.json", receipt)
    if not receipt["boot_success"]:
        raise RuntimeError("direct boot measurement failed: " + str(primary))


def export(root: Path, destination: Path) -> None:
    evidence = root / "evidence"
    _, observed = policy.ensure_evidence_allowlist(evidence, ALLOWED_EVIDENCE)
    temporary = destination.with_name(destination.name + ".partial-" + str(os.getpid()))
    temporary.mkdir(mode=0o700)
    for name in sorted(observed):
        target = temporary / name
        exclusive(target, (evidence / name).read_bytes(), cap=ALLOWED_EVIDENCE[name])
    json_write(temporary / "artifact-manifest.json", {"schema": "dm-direct-boot-artifact-v1", "files": observed})
    manifest_cap = ALLOWED_EVIDENCE | {"artifact-manifest.json": policy.STREAM_MAX}
    policy.ensure_evidence_allowlist(temporary, manifest_cap)
    os.rename(temporary, destination)


def verify_export(root: Path, destination: Path) -> None:
    _, evidence = policy.ensure_evidence_allowlist(root / "evidence", ALLOWED_EVIDENCE)
    manifest_cap = ALLOWED_EVIDENCE | {"artifact-manifest.json": policy.STREAM_MAX}
    policy.ensure_evidence_allowlist(destination, manifest_cap)
    raw = (destination / "artifact-manifest.json").read_bytes()
    if len(raw) > policy.STREAM_MAX:
        raise RuntimeError("artifact manifest cap")
    manifest = json.loads(raw)
    if manifest != {"schema": "dm-direct-boot-artifact-v1", "files": evidence}:
        raise RuntimeError("export no longer matches current evidence")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=("preflight", "download", "inventory", "boot", "retain-receipts", "export", "verify-export"),
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--apt-plan")
    parser.add_argument("--apt-sources")
    parser.add_argument("--apt-lists")
    parser.add_argument("--apt-keyring-receipt")
    parser.add_argument("--cgroup-json")
    parser.add_argument("--destination")
    args = parser.parse_args()
    root = private_root(args.root)
    if args.operation == "preflight":
        preflight(root)
    elif args.operation == "download":
        download(root)
    elif args.operation == "inventory":
        host_inventory(root, Path(args.apt_plan), Path(args.apt_sources), Path(args.apt_lists), Path(args.apt_keyring_receipt))
    elif args.operation == "boot":
        boot(root, Path(args.cgroup_json))
    elif args.operation == "retain-receipts":
        retain_lifecycle_receipts(root)
    elif args.operation == "export":
        export(root, Path(args.destination))
    else:
        verify_export(root, Path(args.destination))


if __name__ == "__main__":
    main()
