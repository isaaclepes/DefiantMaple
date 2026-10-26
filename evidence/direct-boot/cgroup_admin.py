"""Tiny privileged helper: create/read or remove one owned cgroup-v2 leaf."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

GIB = 1024**3
NAME = re.compile(r"^dm-direct-boot-[0-9a-f]{16}$")
ROOT = Path("/sys/fs/cgroup")


def own_cgroup() -> Path:
    matches = [line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::")]
    if len(matches) != 1 or ".." in Path(matches[0]).parts:
        raise RuntimeError("unified cgroup identity")
    return ROOT / matches[0].lstrip("/")


def leaf(name: str) -> Path:
    if not NAME.fullmatch(name):
        raise RuntimeError("cgroup name")
    parent = own_cgroup()
    if not parent.is_dir():
        raise RuntimeError("cgroup parent")
    return parent / name


def write_exact(path: Path, value: str) -> None:
    path.write_text(value)
    if path.read_text().strip() != value.strip():
        raise RuntimeError("cgroup write readback: " + path.name)


def create(name: str, uid: int, gid: int) -> dict:
    if os.geteuid() != 0 or uid <= 0 or gid <= 0:
        raise RuntimeError("privileged create arguments")
    target = leaf(name)
    parent = target.parent
    controllers = set((parent / "cgroup.controllers").read_text().split())
    enabled = set((parent / "cgroup.subtree_control").read_text().replace("+", "").split())
    required = {"cpu", "memory", "pids"}
    if not required.issubset(controllers) or not required.issubset(enabled):
        raise RuntimeError("required controllers not delegated")
    target.mkdir(mode=0o755)
    try:
        write_exact(target / "memory.max", str(3 * GIB))
        write_exact(target / "memory.swap.max", "0")
        write_exact(target / "pids.max", "64")
        write_exact(target / "cpu.max", "200000 100000")
        os.chown(target / "cgroup.procs", uid, gid)
        st = target.stat()
        result = {
            "path": str(target),
            "identity": [st.st_dev, st.st_ino],
            "memory.max": (target / "memory.max").read_text().strip(),
            "memory.swap.max": (target / "memory.swap.max").read_text().strip(),
            "pids.max": (target / "pids.max").read_text().strip(),
            "cpu.max": (target / "cpu.max").read_text().strip(),
        }
        return result
    except BaseException:
        try:
            target.rmdir()
        except OSError:
            pass
        raise


def destroy(name: str, identity: list[int]) -> dict:
    if os.geteuid() != 0 or len(identity) != 2:
        raise RuntimeError("privileged destroy arguments")
    target = leaf(name)
    st = target.stat()
    if [st.st_dev, st.st_ino] != identity:
        raise RuntimeError("cgroup identity changed")
    if (target / "cgroup.procs").read_text().strip() or "populated 0" not in (target / "cgroup.events").read_text():
        raise RuntimeError("cgroup not empty")
    target.rmdir()
    return {"removed": not target.exists(), "path": str(target), "identity": identity}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="op", required=True)
    make = sub.add_parser("create")
    make.add_argument("name")
    make.add_argument("uid", type=int)
    make.add_argument("gid", type=int)
    remove = sub.add_parser("destroy")
    remove.add_argument("name")
    remove.add_argument("device", type=int)
    remove.add_argument("inode", type=int)
    args = parser.parse_args()
    value = create(args.name, args.uid, args.gid) if args.op == "create" else destroy(args.name, [args.device, args.inode])
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
