"""Boundedly gate workflow cleanup on watchdog/cgroup empty proof."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def bounded_json(path: Path, cap: int = 65536) -> dict:
    data = path.read_bytes()
    if len(data) > cap:
        raise RuntimeError("JSON cap: " + path.name)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError("JSON object required: " + path.name)
    return value


def identity_ok(path: Path, identity: list[int]) -> bool:
    try:
        st = path.stat()
        return [st.st_dev, st.st_ino] == identity
    except FileNotFoundError:
        return False


def empty(path: Path, identity: list[int]) -> bool:
    if not identity_ok(path, identity):
        raise RuntimeError("cgroup identity changed")
    return not (path / "cgroup.procs").read_text().strip() and "populated 0" in (path / "cgroup.events").read_text()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--cgroup-json", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 45:
        raise RuntimeError("cleanup wait bound")
    cg = bounded_json(args.cgroup_json, 4096)
    path = Path(cg["path"])
    identity = cg["identity"]
    if not path.is_absolute() or not str(path).startswith("/sys/fs/cgroup/") or not isinstance(identity, list) or len(identity) != 2:
        raise RuntimeError("cgroup receipt fields")
    deadline = time.monotonic() + args.timeout
    handoff_seen = (args.root / "qemu-handoff.json").exists()
    watchdog = None
    while time.monotonic() < deadline:
        if (args.root / "qemu-handoff.json").exists():
            handoff_seen = True
        result = args.root / "watchdog-result.json"
        if result.exists():
            watchdog = bounded_json(result)
            if watchdog.get("cgroup_empty") is not True:
                raise RuntimeError("watchdog did not prove empty cgroup")
            break
        if not handoff_seen and empty(path, identity):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("cleanup proof deadline")
    if handoff_seen and watchdog is None:
        raise RuntimeError("QEMU handoff requires atomic watchdog result")
    if not empty(path, identity):
        raise RuntimeError("final cgroup empty readback")
    print(json.dumps({"cgroup_empty": True, "handoff_seen": handoff_seen, "watchdog_result_seen": watchdog is not None}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
