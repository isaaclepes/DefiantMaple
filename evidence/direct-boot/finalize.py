"""Create the final exclusive receipt only after workflow-level cleanup outcome is known."""

import argparse
import json
import os
import shutil
from pathlib import Path


def exclusive(path: Path, value: object) -> None:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def downgrade_receipt(path: Path, value: object) -> None:
    """A later failure may monotonically replace a not-yet-uploaded success receipt."""
    temporary = path.with_name(path.name + ".failure-replacement")
    exclusive(temporary, value)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=("success", "failure"))
    parser.add_argument("--reason", default="")
    parser.add_argument("--source-hashes", type=Path)
    parser.add_argument("--apt-plan", type=Path)
    args = parser.parse_args()
    evidence = args.root / "evidence"
    evidence.mkdir(mode=0o700, exist_ok=True)
    if args.source_hashes and not (evidence / "source-hashes.txt").exists():
        shutil.copyfile(args.source_hashes, evidence / "source-hashes.txt")
    if args.apt_plan and args.apt_plan.exists() and not (evidence / "apt-plan.json").exists():
        shutil.copyfile(args.apt_plan, evidence / "apt-plan.json")
    success = args.status == "success"
    if success:
        boot = json.loads((args.root / "boot-result.json").read_bytes())
        removed = json.loads((args.root / "cgroup-destroy.json").read_bytes())
        if boot.get("schema") != "dm-direct-boot-intermediate-v1" or boot.get("boot_success") is not True:
            raise RuntimeError("final success without successful boot intermediate")
        if removed.get("removed") is not True:
            raise RuntimeError("final success without cgroup removal proof")
    if not success and not (evidence / "failure.json").exists():
        exclusive(evidence / "failure.json", {"schema": "dm-direct-boot-failure-v1", "error": args.reason[:1024], "measurement_success": False})
    receipt_path = evidence / "receipt.json"
    receipt = {
        "schema": "dm-direct-boot-receipt-v1",
        "success": success,
        "forced_cleanup_cannot_pass": True,
        "cgroup_removed": success,
        "claim": "offline boot measurement only; no ENOSPC, product import, G0, E1, or E2",
        "reason": args.reason[:1024] if not success else None,
    }
    if not receipt_path.exists():
        exclusive(receipt_path, receipt)
    elif not success and json.loads(receipt_path.read_bytes()).get("success") is True:
        downgrade_receipt(receipt_path, receipt)


if __name__ == "__main__":
    main()
