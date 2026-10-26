"""Validate one simulated official-Noble APT transaction before installation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_NEW_BYTES = 1024**3
INSTALL = re.compile(r"^Inst ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?) \((\S+) ([^)]+)\)$")
SPACE = re.compile(r"After this operation, ([0-9.,]+) ([kMGT]?B) of additional disk space will be used\.")
UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
ORIGIN = re.compile(r"(?:^| )Ubuntu:24\.04/(?:noble|noble-updates|noble-security)(?: |$)")


def parse_plan(text: str, allowed: set[str]) -> dict:
    if len(text.encode()) > 1024**2:
        raise ValueError("APT plan log cap")
    packages = []
    for line in text.splitlines():
        if not line.startswith("Inst "):
            continue
        match = INSTALL.fullmatch(line)
        if not match:
            raise ValueError("unparsed APT Inst line")
        name, version, origin = match.groups()
        bare = name.split(":", 1)[0]
        if bare not in allowed:
            raise ValueError("package outside reviewed allowlist: " + bare)
        if not ORIGIN.search(origin):
            raise ValueError("package outside official Noble pockets: " + name)
        packages.append({"name": name, "version": version, "origin": origin})
    if not packages or len(packages) > 96 or len({p["name"] for p in packages}) != len(packages):
        raise ValueError("APT transaction count/uniqueness")
    sizes = [SPACE.search(line) for line in text.splitlines()]
    sizes = [match for match in sizes if match]
    if len(sizes) != 1:
        raise ValueError("APT installed-size estimate missing/ambiguous")
    amount = float(sizes[0].group(1).replace(",", ""))
    estimated = int(amount * UNITS[sizes[0].group(2)])
    if estimated < 0 or estimated > MAX_NEW_BYTES:
        raise ValueError("APT installed-size cap")
    return {"schema": "dm-apt-plan-v1", "estimated_new_bytes": estimated, "packages": packages}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    allowed = {
        line.strip()
        for line in args.allowlist.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    result = parse_plan(args.plan.read_text(), allowed)
    data = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    fd = args.output.open("xb")
    with fd:
        fd.write(data)


if __name__ == "__main__":
    main()
