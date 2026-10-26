"""Validate one simulated official-Noble APT transaction before installation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_NEW_BYTES = 1024**3
INSTALL = re.compile(r"^Inst ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?) \((\S+) ([^)]+)\)$")
CONFIGURE = re.compile(r"^Conf ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?) \((\S+) ([^)]+)\)$")
SUMMARY = re.compile(r"^(\d+) upgraded, (\d+) newly installed, (\d+) to remove and (\d+) not upgraded\.$")
ARCHITECTURE = re.compile(r"^.+ \[([a-z0-9]+)\]$")
ORIGIN = re.compile(r"(?:^| )Ubuntu:24\.04/(?:noble|noble-updates|noble-security)(?: |$)")
SHA256 = re.compile(r"[0-9a-f]{64}")


def parse_transaction(text: str, allowed: set[str]) -> dict:
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
        arch = ARCHITECTURE.fullmatch(origin)
        if arch is None:
            raise ValueError("APT package architecture missing: " + name)
        packages.append({"name": name, "version": version, "origin": origin, "architecture": arch.group(1)})
    if not packages or len(packages) > 96 or len({p["name"] for p in packages}) != len(packages):
        raise ValueError("APT transaction count/uniqueness")
    configured = []
    for line in text.splitlines():
        if line.startswith(("Remv ", "Purg ")):
            raise ValueError("APT transaction removes a package")
        if not line.startswith("Conf "):
            continue
        match = CONFIGURE.fullmatch(line)
        if not match:
            raise ValueError("unparsed APT Conf line")
        configured.append(match.groups())
    expected = [(p["name"], p["version"], p["origin"]) for p in packages]
    if configured != expected:
        raise ValueError("APT configure set/order differs from install set")
    summaries = [SUMMARY.fullmatch(line) for line in text.splitlines()]
    summaries = [match for match in summaries if match]
    if len(summaries) != 1:
        raise ValueError("APT transaction summary missing/ambiguous")
    upgraded, newly, removed, not_upgraded = map(int, summaries[0].groups())
    if upgraded != 0 or removed != 0 or newly != len(packages):
        raise ValueError("APT transaction summary permits upgrade/removal or differs from Inst set")
    return {"packages": packages, "transaction": {"upgraded": upgraded, "newly_installed": newly, "removed": removed, "not_upgraded": not_upgraded}}


def parse_plan(text: str, allowed: set[str], metadata: dict) -> dict:
    transaction = parse_transaction(text, allowed)
    if not isinstance(metadata, dict) or set(metadata) != {"schema", "apt_cache", "source_list_sha256", "lists_identity", "lists_manifest", "records"}:
        raise ValueError("APT installed-size metadata fields")
    if metadata["schema"] != "dm-apt-installed-size-v2" or not SHA256.fullmatch(metadata["source_list_sha256"]):
        raise ValueError("APT installed-size metadata schema/source")
    if not (isinstance(metadata["lists_identity"], list) and len(metadata["lists_identity"]) == 2 and all(type(item) is int and item >= 0 for item in metadata["lists_identity"])):
        raise ValueError("APT lists identity")
    lists = metadata["lists_manifest"]
    if not (isinstance(lists, dict) and set(lists) == {"regular_files", "index_files", "auxiliary_files", "total_bytes", "sha256", "administrative"}
            and type(lists["regular_files"]) is int and 0 < lists["regular_files"] <= 128
            and type(lists["index_files"]) is int and 0 < lists["index_files"] <= lists["regular_files"]
            and type(lists["auxiliary_files"]) is int and lists["auxiliary_files"] >= 0
            and lists["regular_files"] == lists["index_files"] + lists["auxiliary_files"]
            and type(lists["total_bytes"]) is int and 0 <= lists["total_bytes"] <= MAX_NEW_BYTES
            and SHA256.fullmatch(lists["sha256"])):
        raise ValueError("APT lists manifest")
    administrative = lists["administrative"]
    if not (isinstance(administrative, list) and len(administrative) == 3
            and all(isinstance(item, dict) and set(item) == {"name", "kind", "uid", "gid", "mode"} for item in administrative)):
        raise ValueError("APT lists administrative manifest")
    lock, partial, auxfiles = administrative
    if not (lock["name"] == "lock" and lock["kind"] == "empty-lock"
            and lock["uid"] == 0 and lock["gid"] == 0 and lock["mode"] in (0o600, 0o640)):
        raise ValueError("APT lists lock manifest")
    if not (partial["name"] == "partial" and partial["kind"] == "opaque-directory"
            and type(partial["uid"]) is int and partial["uid"] > 0 and partial["gid"] == 0 and partial["mode"] == 0o700):
        raise ValueError("APT lists partial manifest")
    if not (auxfiles["name"] == "auxfiles" and auxfiles["kind"] == "hashed-directory"
            and auxfiles["uid"] == partial["uid"] and auxfiles["gid"] == 0 and auxfiles["mode"] == 0o755):
        raise ValueError("APT lists auxfiles manifest")
    tool = metadata["apt_cache"]
    if not (isinstance(tool, dict) and set(tool) == {"path", "sha256", "bytes", "uid", "mode"}
            and tool["path"] == "/usr/bin/apt-cache" and SHA256.fullmatch(tool["sha256"])
            and type(tool["bytes"]) is int and tool["bytes"] > 0 and tool["bytes"] <= 16 * 1024**2
            and tool["uid"] == 0 and type(tool["mode"]) is int and not tool["mode"] & 0o022):
        raise ValueError("APT cache tool identity")
    records = metadata["records"]
    packages = transaction["packages"]
    if not isinstance(records, list) or len(records) != len(packages):
        raise ValueError("APT installed-size record count")
    estimated = 0
    for package, record in zip(packages, records):
        if not isinstance(record, dict) or set(record) != {"name", "version", "architecture", "installed_size_kib", "metadata_sha256"}:
            raise ValueError("APT installed-size record fields")
        if (record["name"], record["version"], record["architecture"]) != (package["name"].split(":", 1)[0], package["version"], package["architecture"]):
            raise ValueError("APT installed-size record differs from exact plan")
        size = record["installed_size_kib"]
        if type(size) is not int or size <= 0 or size > MAX_NEW_BYTES // 1024 or not SHA256.fullmatch(record["metadata_sha256"]):
            raise ValueError("APT Installed-Size invalid")
        estimated += size * 1024
    if estimated > MAX_NEW_BYTES:
        raise ValueError("APT installed-size cap")
    return {"schema": "dm-apt-plan-v2", "estimated_new_bytes": estimated, **transaction, "installed_size_basis": metadata}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("installed_size_metadata", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    allowed = {
        line.strip()
        for line in args.allowlist.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    metadata = json.loads(args.installed_size_metadata.read_bytes())
    result = parse_plan(args.plan.read_text(), allowed, metadata)
    data = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    fd = args.output.open("xb")
    with fd:
        fd.write(data)


if __name__ == "__main__":
    main()
