"""Tiny privileged helper for one root-controlled cgroup-v2 leaf."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path

GIB = 1024**3
NAME = re.compile(r"^dm-direct-boot-[0-9a-f]{16}$")
CONTROLLER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
ROOT = Path("/sys/fs/cgroup")
REQUIRED_CONTROLLERS = {"cpu", "memory", "pids"}
LIMITS = {
    "memory.max": str(3 * GIB),
    "memory.swap.max": "0",
    "pids.max": "64",
    "cpu.max": "200000 100000",
}


def own_cgroup_relative() -> str:
    matches = [line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::")]
    if len(matches) != 1 or not matches[0].startswith("/") or ".." in Path(matches[0]).parts:
        raise RuntimeError("unified cgroup identity")
    return matches[0]


def own_cgroup() -> Path:
    return ROOT / own_cgroup_relative().lstrip("/")


def leaf(name: str) -> Path:
    if not NAME.fullmatch(name):
        raise RuntimeError("cgroup name")
    if not ROOT.is_dir():
        raise RuntimeError("cgroup control parent")
    return ROOT / name


def identity(path: Path) -> list[int]:
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("cgroup path type")
    return [info.st_dev, info.st_ino]


def relative_cgroup(path: Path) -> str:
    relative = path.relative_to(ROOT)
    return "/" if str(relative) == "." else "/" + str(relative)


def controller_state() -> dict[str, list[str]]:
    controllers = sorted(set((ROOT / "cgroup.controllers").read_text().split()))
    enabled = sorted(set((ROOT / "cgroup.subtree_control").read_text().replace("+", "").split()))
    if (not REQUIRED_CONTROLLERS.issubset(controllers)
            or not REQUIRED_CONTROLLERS.issubset(enabled)):
        raise RuntimeError("required root controllers not enabled")
    return {"controllers": controllers, "subtree_control": enabled}


def controller_argument(raw: str) -> list[str]:
    values = raw.split(",") if raw else []
    if (not values or len(values) != len(set(values)) or values != sorted(values)
            or any(not CONTROLLER.fullmatch(value) for value in values)):
        raise RuntimeError("controller argument")
    return values


def write_exact(path: Path, value: str) -> None:
    path.write_text(value)
    if path.read_text().strip() != value.strip():
        raise RuntimeError("cgroup write readback: " + path.name)


def read_limits(target: Path) -> dict[str, str]:
    observed = {name: (target / name).read_text().strip() for name in LIMITS}
    if observed != LIMITS:
        raise RuntimeError("cgroup limits changed")
    return observed


def member_pids(target: Path) -> list[int]:
    values = (target / "cgroup.procs").read_text().split()
    if any(not value.isdecimal() or int(value) <= 0 for value in values):
        raise RuntimeError("cgroup member syntax")
    pids = [int(value) for value in values]
    if len(pids) != len(set(pids)):
        raise RuntimeError("duplicate cgroup member")
    return sorted(pids)


def process_fact(pid: int) -> dict | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        end = raw.rfind(")")
        fields = raw[end + 2 :].split()
        groups = [line[3:] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines() if line.startswith("0::")]
        status = Path(f"/proc/{pid}/status").read_text().splitlines()
        uids = [int(value) for line in status if line.startswith("Uid:") for value in line.split()[1:]]
        gids = [int(value) for line in status if line.startswith("Gid:") for value in line.split()[1:]]
        if end < 0 or len(fields) < 20 or len(groups) != 1 or len(uids) != 4 or len(gids) != 4:
            return None
        return {"pid": pid, "start_ticks": int(fields[19]), "cgroup": groups[0], "uids": uids, "gids": gids}
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None


def exact_process(fact: dict | None, *, pid: int, start_ticks: int, uid: int, gid: int, cgroup: str) -> bool:
    return bool(
        fact and fact.get("pid") == pid and fact.get("start_ticks") == start_ticks
        and fact.get("cgroup") == cgroup and fact.get("uids") == [uid] * 4
        and fact.get("gids") == [gid] * 4
    )


def write_member(target: Path, pid: int) -> None:
    with (target / "cgroup.procs").open("w", encoding="ascii") as stream:
        stream.write(str(pid))


def create(name: str) -> dict:
    if os.geteuid() != 0:
        raise RuntimeError("privileged create")
    target = leaf(name)
    control_identity = identity(ROOT)
    controls = controller_state()
    source_cgroup = own_cgroup_relative()
    source = own_cgroup()
    if source == ROOT or relative_cgroup(source) != source_cgroup:
        raise RuntimeError("source cgroup must differ from control parent")
    source_identity = identity(source)
    target.mkdir(mode=0o755)
    try:
        for filename, value in LIMITS.items():
            write_exact(target / filename, value)
        if member_pids(target) or "populated 0" not in (target / "cgroup.events").read_text():
            raise RuntimeError("new cgroup not empty")
        if (identity(ROOT) != control_identity or controller_state() != controls
                or own_cgroup_relative() != source_cgroup or identity(source) != source_identity):
            raise RuntimeError("cgroup create identity changed")
        return {
            "path": str(target), "identity": identity(target),
            "control_parent": {
                "path": str(ROOT), "identity": control_identity, "cgroup": "/", **controls,
            },
            "source": {
                "path": str(source), "identity": source_identity, "cgroup": source_cgroup,
            },
            **read_limits(target),
        }
    except BaseException:
        try:
            target.rmdir()
        except OSError:
            pass
        raise


def attach(
    name: str, control_identity: list[int], source_identity: list[int],
    target_identity: list[int], expected_controllers: list[str], expected_enabled: list[str],
    pid: int, start_ticks: int, uid: int, gid: int, source_cgroup: str,
) -> dict:
    if (os.geteuid() != 0 or len(control_identity) != 2 or len(source_identity) != 2
            or len(target_identity) != 2
            or pid <= 0 or start_ticks <= 0 or uid <= 0 or gid <= 0):
        raise RuntimeError("privileged attach arguments")
    target = leaf(name)
    controls = {"controllers": expected_controllers, "subtree_control": expected_enabled}
    if (controller_state() != controls or identity(ROOT) != control_identity
            or identity(target) != target_identity):
        raise RuntimeError("cgroup identity changed")
    source = ROOT / source_cgroup.lstrip("/")
    if (source == ROOT or relative_cgroup(source) != source_cgroup
            or own_cgroup_relative() != source_cgroup or own_cgroup() != source
            or identity(source) != source_identity):
        raise RuntimeError("source cgroup mismatch")
    limits = read_limits(target)
    if member_pids(target) or "populated 0" not in (target / "cgroup.events").read_text():
        raise RuntimeError("attach target not empty")
    before = process_fact(pid)
    if not exact_process(before, pid=pid, start_ticks=start_ticks, uid=uid, gid=gid, cgroup=source_cgroup):
        raise RuntimeError("attach process identity")
    write_member(target, pid)
    destination = relative_cgroup(target)
    after = process_fact(pid)
    if not exact_process(after, pid=pid, start_ticks=start_ticks, uid=uid, gid=gid, cgroup=destination):
        raise RuntimeError("attached process identity")
    if member_pids(target) != [pid]:
        raise RuntimeError("attached membership")
    if (identity(ROOT) != control_identity or controller_state() != controls
            or identity(source) != source_identity or own_cgroup_relative() != source_cgroup
            or identity(target) != target_identity):
        raise RuntimeError("cgroup identity changed after attach")
    if read_limits(target) != limits:
        raise RuntimeError("cgroup limits changed after attach")
    return {
        "operation": "attach",
        "control_parent": {
            "path": str(ROOT), "identity": control_identity, "cgroup": "/", **controls,
        },
        "source": {"path": str(source), "identity": source_identity, "cgroup": source_cgroup},
        "leaf": {"path": str(target), "identity": target_identity},
        "limits": limits, "before": before, "after": after, "members": [pid],
    }


def destroy(name: str, target_identity: list[int]) -> dict:
    if os.geteuid() != 0 or len(target_identity) != 2:
        raise RuntimeError("privileged destroy arguments")
    target = leaf(name)
    if identity(target) != target_identity:
        raise RuntimeError("cgroup identity changed")
    if member_pids(target) or "populated 0" not in (target / "cgroup.events").read_text():
        raise RuntimeError("cgroup not empty")
    target.rmdir()
    return {"removed": not target.exists(), "path": str(target), "identity": target_identity}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="op", required=True)
    make = sub.add_parser("create")
    make.add_argument("name")
    move = sub.add_parser("attach")
    move.add_argument("name")
    move.add_argument("control_device", type=int)
    move.add_argument("control_inode", type=int)
    move.add_argument("source_device", type=int)
    move.add_argument("source_inode", type=int)
    move.add_argument("device", type=int)
    move.add_argument("inode", type=int)
    move.add_argument("controllers")
    move.add_argument("subtree_control")
    move.add_argument("pid", type=int)
    move.add_argument("start_ticks", type=int)
    move.add_argument("uid", type=int)
    move.add_argument("gid", type=int)
    move.add_argument("source_cgroup")
    remove = sub.add_parser("destroy")
    remove.add_argument("name")
    remove.add_argument("device", type=int)
    remove.add_argument("inode", type=int)
    args = parser.parse_args()
    if args.op == "create":
        value = create(args.name)
    elif args.op == "attach":
        value = attach(
            args.name, [args.control_device, args.control_inode],
            [args.source_device, args.source_inode], [args.device, args.inode],
            controller_argument(args.controllers), controller_argument(args.subtree_control),
            args.pid, args.start_ticks, args.uid, args.gid, args.source_cgroup,
        )
    else:
        value = destroy(args.name, [args.device, args.inode])
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
