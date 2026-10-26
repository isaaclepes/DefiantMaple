"""Independent exact-pidfd watchdog for the one QEMU cgroup."""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import selectors
import signal
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")
CGROUP_NAME = re.compile(r"dm-direct-boot-[0-9a-f]{16}")
COUNTER_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}")


def valid_leaf(path: Path) -> bool:
    return path.parent == CGROUP_ROOT and bool(CGROUP_NAME.fullmatch(path.name))


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


def open_verified_pidfd(expected: dict) -> int:
    before = proc_fact(expected["pid"])
    if before != expected:
        raise ProcessLookupError("process identity changed before pidfd_open")
    fd = os.pidfd_open(expected["pid"], 0)
    if proc_fact(expected["pid"]) != expected:
        os.close(fd)
        raise ProcessLookupError("process identity changed during pidfd_open")
    return fd


def publish(path: Path, value: dict) -> None:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(data) > 16384:
        raise RuntimeError("watchdog evidence cap")
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def cgroup_ok(path: Path, identity: list[int]) -> bool:
    if not valid_leaf(path):
        return False
    try:
        st = path.stat()
        return [st.st_dev, st.st_ino] == identity
    except FileNotFoundError:
        return False


def members(path: Path, identity: list[int]) -> list[dict]:
    if not cgroup_ok(path, identity):
        raise RuntimeError("cgroup identity changed")
    facts = []
    for raw in (path / "cgroup.procs").read_text().split():
        fact = proc_fact(int(raw))
        if fact is None:
            continue
        expected = "/" + path.name
        if fact["cgroup"] != expected:
            raise RuntimeError("cgroup member identity mismatch")
        facts.append(fact)
    return facts


def signal_members(path: Path, identity: list[int], signum: int, events: list[dict]) -> None:
    for fact in members(path, identity):
        try:
            fd = open_verified_pidfd(fact)
        except ProcessLookupError:
            continue
        try:
            signal.pidfd_send_signal(fd, signum, None, 0)
            events.append({"op": "pidfd_send_signal", "signal": signum, "identity": fact})
        except ProcessLookupError:
            pass
        finally:
            os.close(fd)


def wait_empty(path: Path, identity: list[int], deadline: float) -> bool:
    while time.monotonic() < deadline:
        if not members(path, identity) and "populated 0" in (path / "cgroup.events").read_text():
            return True
        time.sleep(0.1)
    return False


def cgroup_counters(path: Path, identity: list[int]) -> dict[str, dict[str, int]]:
    if not cgroup_ok(path, identity):
        raise RuntimeError("cgroup identity changed before counter read")
    result = {}
    for name in ("memory.events", "pids.events"):
        raw = (path / name).read_text()
        if len(raw.encode()) > 4096:
            raise RuntimeError("cgroup counter cap: " + name)
        values = {}
        lines = raw.splitlines()
        if not lines or len(lines) > 32:
            raise RuntimeError("cgroup counter lines: " + name)
        for line in lines:
            parts = line.split()
            if (len(parts) != 2 or not COUNTER_NAME.fullmatch(parts[0])
                    or not parts[1].isdecimal() or parts[0] in values):
                raise RuntimeError("cgroup counter syntax: " + name)
            values[parts[0]] = int(parts[1])
        result[name] = dict(sorted(values.items()))
    if not cgroup_ok(path, identity):
        raise RuntimeError("cgroup identity changed during counter read")
    return result


def counter_diagnostics(path: Path, identity: list[int]) -> tuple[dict | None, dict | None]:
    try:
        return cgroup_counters(path, identity), None
    except BaseException as exc:
        error_type = type(exc).__name__
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
            error_type = "Exception"
        message = str(exc)
        return None, {
            "error_type": error_type, "message": message[:256],
            "message_truncated": len(message) > 256,
        }


def publish_cleanup_result(
    work: Path, path: Path, identity: list[int], core: dict,
) -> dict | None:
    counters, counter_error = counter_diagnostics(path, identity)
    publish(
        work / "watchdog-result.json",
        {**core, "cgroup_counters": counters, "cgroup_counter_error": counter_error},
    )
    return counter_error


def cleanup(path: Path, identity: list[int], qemu_fd: int | None, qemu: dict | None) -> tuple[bool, list[dict]]:
    events: list[dict] = []
    if qemu_fd is not None and qemu is not None and not select.select([qemu_fd], [], [], 0)[0]:
        try:
            signal.pidfd_send_signal(qemu_fd, signal.SIGTERM, None, 0)
            events.append({"op": "pidfd_send_signal", "signal": signal.SIGTERM, "identity": qemu})
        except ProcessLookupError:
            pass
    signal_members(path, identity, signal.SIGTERM, events)
    if wait_empty(path, identity, time.monotonic() + 10):
        return True, events
    signal_members(path, identity, signal.SIGKILL, events)
    return wait_empty(path, identity, time.monotonic() + 5), events


def pre_handoff_reason(work: Path, parent_selector: selectors.BaseSelector, deadline: float) -> str | None:
    while not (work / "qemu-handoff.json").exists():
        if (work / "cleanup-request").exists():
            return "controller-cleanup-request-before-handoff"
        if parent_selector.select(0.1):
            return "parent-exited-before-handoff"
        if time.monotonic() >= deadline:
            return "handoff-timeout"
    return None


def finish_forced_cleanup(
    path: Path, identity: list[int], qemu_fd: int | None, qemu: dict | None,
    reason: str, forced: bool,
) -> tuple[str, list[dict]]:
    if not forced:
        return reason, []
    empty, events = cleanup(path, identity, qemu_fd, qemu)
    if not empty:
        reason += ":cgroup-not-empty"
    return reason, events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    parser.add_argument("parent_pid", type=int)
    parser.add_argument("parent_start", type=int)
    parser.add_argument("cgroup", type=Path)
    parser.add_argument("cgroup_device", type=int)
    parser.add_argument("cgroup_inode", type=int)
    args = parser.parse_args()
    if not valid_leaf(args.cgroup):
        raise RuntimeError("cgroup direct root leaf")
    identity = [args.cgroup_device, args.cgroup_inode]
    parent = proc_fact(args.parent_pid)
    if parent is None or parent["start_ticks"] != args.parent_start:
        raise RuntimeError("parent identity")
    parent_fd = open_verified_pidfd(parent)
    if proc_fact(os.getpid())["cgroup"] == "/" + args.cgroup.name:
        raise RuntimeError("watchdog inside guest cgroup")
    selector = selectors.DefaultSelector()
    selector.register(parent_fd, selectors.EVENT_READ)
    qemu_fd = None
    qemu = None
    reason = "watchdog-deadline"
    forced = True
    events: list[dict] = []
    try:
        handoff_deadline = time.monotonic() + 30
        before_handoff = pre_handoff_reason(args.work, selector, handoff_deadline)
        if before_handoff is not None:
            reason = before_handoff
        else:
            raw = (args.work / "qemu-handoff.json").read_bytes()
            if len(raw) > 4096:
                raise RuntimeError("handoff cap")
            handoff = json.loads(raw)
            qemu = handoff["qemu"]
            if handoff.get("cgroup_path") != str(args.cgroup) or handoff.get("cgroup_identity") != identity:
                raise RuntimeError("handoff cgroup binding")
            qemu_fd = open_verified_pidfd(qemu)
            publish(args.work / "watchdog-ready.json", {"ready": True, "qemu": qemu, "watchdog": proc_fact(os.getpid())})
            deadline = time.monotonic() + 10 * 60
            while time.monotonic() < deadline:
                if (args.work / "watchdog-release").exists():
                    if not select.select([qemu_fd], [], [], 0)[0] or not wait_empty(args.cgroup, identity, time.monotonic() + 2):
                        reason = "invalid-normal-release"
                        break
                    forced = False
                    reason = "normal-release"
                    break
                if (args.work / "cleanup-request").exists():
                    reason = "controller-cleanup-request"
                    break
                if selector.select(0.1):
                    reason = "parent-exited"
                    break
        reason, events = finish_forced_cleanup(
            args.cgroup, identity, qemu_fd, qemu, reason, forced,
        )
        counter_error = publish_cleanup_result(
            args.work, args.cgroup, identity,
            {
                "forced_cleanup": forced, "reason": reason,
                "cgroup_empty": not members(args.cgroup, identity), "events": events,
            },
        )
        if counter_error is not None:
            raise RuntimeError("cgroup counter diagnostics failed after cleanup receipt")
    finally:
        if qemu_fd is not None:
            os.close(qemu_fd)
        selector.close()
        os.close(parent_fd)


if __name__ == "__main__":
    main()
