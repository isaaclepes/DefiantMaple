"""One authenticated image download and one bounded offline direct-QEMU boot."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import resource
import selectors
import signal
import socket
import stat
import subprocess
import sys
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
ALLOWED_EVIDENCE = {
    "host.json": policy.STREAM_MAX,
    "apt-plan.log": policy.STREAM_MAX,
    "apt-metadata.json": policy.STREAM_MAX,
    "apt-plan.json": policy.STREAM_MAX,
    "apt-observation.json": policy.STREAM_MAX,
    "image.json": policy.STREAM_MAX,
    "boot-config.json": policy.STREAM_MAX,
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


def package_for_file(requested: Path, resolved: Path) -> dict:
    output = None
    queried = None
    for candidate in dict.fromkeys((requested, resolved)):
        try:
            output = command(["/usr/bin/dpkg-query", "-S", str(candidate)], timeout=5, output_cap=16384).decode("utf-8", "strict")
            queried = candidate
            break
        except RuntimeError:
            continue
    if output is None:
        raise RuntimeError("no package ownership: " + str(requested))
    owners = sorted({line.rsplit(": ", 1)[0] for line in output.splitlines() if ": " in line})
    if len(owners) != 1 or not owners[0] or len(owners[0]) > 128:
        raise RuntimeError("ambiguous package ownership: " + str(requested))
    version = command(["/usr/bin/dpkg-query", "-W", "-f=${Version}", owners[0]], timeout=5, output_cap=4096).decode("utf-8", "strict")
    return {"package": owners[0], "version": version, "requested": str(requested), "resolved": str(resolved), "queried": str(queried)}


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


def host_inventory(root: Path, apt_plan: Path, apt_sources: Path, apt_lists: Path) -> None:
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
    keyring = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
    key_sha, key_bytes = policy.sha_file(keyring, 16 * policy.MIB)
    key_st = keyring.stat()
    if key_st.st_uid != 0 or key_st.st_mode & 0o022:
        raise RuntimeError("Ubuntu archive keyring owner/mode")
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
    json_write(
        root / "evidence" / "apt-observation.json",
        {
            "schema": "dm-direct-boot-apt-observation-v1",
            "claim_limit": "authenticated package selection and observed installed bytes; not complete immutable host closure",
            "sources_sha256": policy.sha_bytes(apt_sources.read_bytes()),
            "archive_keyring": {"sha256": key_sha, "bytes": key_bytes},
            "inrelease": inreleases,
            "packages": observed,
            "tools": tools,
            "qemu_version": qemu_version,
            "qemu_ldd_output": ldd,
            "qemu_libraries": ldd_observations(ldd),
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


def spawn_qemu(argv: list[str], cgroup: Path, inert_home: Path) -> tuple[int, int, int, dict]:
    read_gate, write_gate = os.pipe2(os.O_CLOEXEC)
    pid = os.fork()
    if pid == 0:
        try:
            os.close(write_gate)
            os.setsid()
            if os.read(read_gate, 1) != b"G":
                os._exit(125)
            os.close(read_gate)
            (cgroup / "cgroup.procs").write_text(str(os.getpid()))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (policy.OVERLAY_MAX, policy.OVERLAY_MAX))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            os.umask(0o077)
            null_fd = os.open("/dev/null", os.O_RDWR | os.O_NOCTTY)
            for target_fd in (0, 1, 2):
                os.dup2(null_fd, target_fd)
            if null_fd > 2:
                os.close(null_fd)
            env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "HOME": str(inert_home), "TMPDIR": str(inert_home)}
            os.execve(argv[0], argv, env)
        except BaseException:
            os._exit(126)
    os.close(read_gate)
    fact = proc_fact(pid)
    if fact is None:
        os.close(write_gate)
        raise RuntimeError("QEMU child identity unavailable")
    return pid, os.pidfd_open(pid, 0), write_gate, fact


def connect_unix(path: Path, deadline: float) -> socket.socket:
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(path))
            sock.setblocking(False)
            return sock
        except (FileNotFoundError, ConnectionRefusedError):
            sock.close()
            time.sleep(0.05)
    raise RuntimeError("Unix socket connect deadline: " + path.name)


def qmp_handshake(sock: socket.socket) -> tuple[bytearray, list[dict], int]:
    sock.settimeout(3)
    file = sock.makefile("rb", buffering=0)
    greeting = file.readline(policy.STREAM_MAX + 1)
    total = policy.charge_stream(0, len(greeting), policy.STREAM_MAX)
    hello = json.loads(greeting)
    if "QMP" not in hello:
        raise RuntimeError("QMP greeting")
    sock.sendall(b'{"execute":"qmp_capabilities"}\r\n')
    reply = file.readline(policy.STREAM_MAX + 1)
    total = policy.charge_stream(total, len(reply), policy.STREAM_MAX)
    if json.loads(reply) != {"return": {}}:
        raise RuntimeError("QMP capability negotiation")
    file.close()
    sock.setblocking(False)
    return bytearray(), [], total


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
    info_raw = command([str(QEMU_IMG), "info", "--output=json", str(base)], timeout=20)
    image_info = policy.validate_qemu_img_info(json.loads(info_raw), base_path=base, physical_size=base_size)
    check_raw = command([str(QEMU_IMG), "check", "--output=json", str(base)], timeout=60)
    image_check = policy.validate_qemu_img_check(json.loads(check_raw), base_path=base)
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
    for name, path, cap in (("qemu-system-x86_64", QEMU_SYSTEM, 512 * policy.MIB), ("seabios", SEABIOS, 4 * policy.MIB)):
        if secure_system_file(path, cap) != expected_tools[name]:
            raise RuntimeError("launch-time tool digest changed: " + name)
    parent = proc_fact(os.getpid())
    if parent is None:
        raise RuntimeError("controller identity")
    wd_stderr = (root / "watchdog.stderr").open("xb")
    watchdog = subprocess.Popen(
        [sys.executable, "-I", "-B", str(HERE / "qemu_watchdog.py"), str(root), str(os.getpid()), str(parent["start_ticks"]), str(cgroup), str(cst.st_dev), str(cst.st_ino)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=wd_stderr, close_fds=True, start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (policy.STREAM_MAX, policy.STREAM_MAX)),
    )
    pid = pidfd = gate = None
    natural = False
    primary = None
    qmp_events: list[dict] = []
    serial = bytearray()
    status = None
    try:
        pid, pidfd, gate, fact = spawn_qemu(argv, cgroup, inert_home)
        atomic_json_publish(root / "qemu-handoff.json", {"qemu": fact, "cgroup_path": str(cgroup), "cgroup_identity": cg["identity"]})
        ready_deadline = time.monotonic() + 10
        while not (root / "watchdog-ready.json").exists():
            if watchdog.poll() is not None or time.monotonic() > ready_deadline:
                raise RuntimeError("watchdog readiness")
            time.sleep(0.05)
        os.write(gate, b"G")
        os.close(gate); gate = None
        member_deadline = time.monotonic() + 3
        expected_cgroup = "/" + str(cgroup.relative_to("/sys/fs/cgroup"))
        while proc_fact(pid) and proc_fact(pid)["cgroup"] != expected_cgroup and time.monotonic() < member_deadline:
            time.sleep(0.02)
        if proc_fact(pid) is None or proc_fact(pid)["cgroup"] != expected_cgroup:
            raise RuntimeError("QEMU effective cgroup membership")
        policy.verify_limits(lambda name: (cgroup / name).read_text())
        serial_sock = connect_unix(serial_socket, time.monotonic() + 5)
        qmp_sock = connect_unix(qmp_socket, time.monotonic() + 5)
        qmp_buffer, qmp_events, qmp_total = qmp_handshake(qmp_sock)
        selector = selectors.DefaultSelector()
        selector.register(serial_sock, selectors.EVENT_READ, "serial")
        selector.register(qmp_sock, selectors.EVENT_READ, "qmp")
        deadline = time.monotonic() + 10 * 60
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited == pid:
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
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise RuntimeError("QEMU did not exit zero")
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
        natural = True
    except BaseException as exc:
        primary = type(exc).__name__ + ": " + str(exc)[:1024]
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
        if not (evidence / "failure.json").exists():
            json_write(evidence / "failure.json", {"schema": "dm-direct-boot-failure-v1", "error": primary, "measurement_success": False})
    finally:
        if pidfd is not None:
            os.close(pidfd)
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
    parser.add_argument("operation", choices=("preflight", "download", "inventory", "boot", "export", "verify-export"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--apt-plan")
    parser.add_argument("--apt-sources")
    parser.add_argument("--apt-lists")
    parser.add_argument("--cgroup-json")
    parser.add_argument("--destination")
    args = parser.parse_args()
    root = private_root(args.root)
    if args.operation == "preflight":
        preflight(root)
    elif args.operation == "download":
        download(root)
    elif args.operation == "inventory":
        host_inventory(root, Path(args.apt_plan), Path(args.apt_sources), Path(args.apt_lists))
    elif args.operation == "boot":
        boot(root, Path(args.cgroup_json))
    elif args.operation == "export":
        export(root, Path(args.destination))
    else:
        verify_export(root, Path(args.destination))


if __name__ == "__main__":
    main()
