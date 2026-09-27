"""Fail CI if tracked files contain private evaluation artifacts or paths."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from defiantmaple.private_eval import sanitize_public_summary


PRIVATE_PARTS = {"private-eval", "private-evaluations", "artwork-evaluation", ".private"}
PRIVATE_SUFFIXES = {".sqlite3", ".safetensors", ".pt", ".pth", ".onnx"}
PUBLIC_FIXTURE_FILES = {
    "benchmarks/image-embedding-results/fixture-manifest.json",
    "benchmarks/image-embedding-results/dinov2-small-cpu.json",
    "benchmarks/image-embedding-results/siglip-base-cpu.json",
}
HISTORICAL_CI_REPORTS = {
    f"benchmarks/results/2026-09-25/{stack}-{platform}.json"
    for stack in ("qt", "tauri")
    for platform in ("linux-x64", "macos-arm64", "windows-x64")
}
CI_PACKAGE_PREFIXES = (
    "/home/runner/work/DefiantMaple/DefiantMaple/",
    "/Users/runner/work/DefiantMaple/DefiantMaple/",
    "D:\\a\\DefiantMaple\\DefiantMaple\\",
)
ABSOLUTE_UNIX = re.compile(r"/(?:home|Users|mnt|media|run/media)/[^\s\"']+")
ABSOLUTE_WINDOWS = re.compile(r"(?:[A-Za-z]:\\|\\\\[^\\]+\\)")
PRIVATE_LABEL_KEYS = {"anonymous_id", "private_notes", "rights_status", "asset_id",
                      "source_sha256", "image_sha256", "current_path", "absolute_path",
                      "per_image", "label", "top_label", "character_name", "file_name",
                      "filename", "query", "vector"}


def _strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _check_json(path: Path, relative: str, errors: list[str]) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        errors.append(f"{relative}: invalid JSON report or fixture")
        return
    for value in _strings(data):
        # These six pre-existing public benchmark reports record the GitHub
        # runner's package path. They are CI workspace paths, not user art.
        if (relative in HISTORICAL_CI_REPORTS and isinstance(data, dict)
                and value == data.get("package_path")
                and value.startswith(CI_PACKAGE_PREFIXES)):
            continue
        if ABSOLUTE_UNIX.search(value) or ABSOLUTE_WINDOWS.search(value):
            errors.append(f"{relative}: absolute private filesystem path")
            break
    if isinstance(data, dict) and data.get("schema") == "defiantmaple.private-eval-summary.v1":
        try:
            sanitize_public_summary(data)
        except (ValueError, TypeError, KeyError):
            errors.append(f"{relative}: identifying data in public summary")
    elif relative not in PUBLIC_FIXTURE_FILES:
        keys = {value for value in _strings(data) if value in PRIVATE_LABEL_KEYS}
        if keys:
            errors.append(f"{relative}: private per-image fields in report or fixture")
    else:
        # This is the one intentionally public, fictional, generated fixture.
        if relative.endswith("fixture-manifest.json"):
            from benchmarks.embedding_fixture import CHARACTERS
            labels = {character[0] for character in CHARACTERS}
            if {item.get("label") for item in data.get("items", [])} != labels:
                errors.append(f"{relative}: unreviewed fixture labels")
        elif relative.endswith("-cpu.json"):
            from benchmarks.embedding_fixture import CHARACTERS
            labels = {character[0] for character in CHARACTERS}
            details = data.get("retrieval", {}).get("per_query", [])
            if any(item.get("label") not in labels or item.get("top_label") not in labels
                   for item in details):
                errors.append(f"{relative}: unreviewed per-image labels")


def validate(root: Path) -> list[str]:
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    errors = []
    for raw in files:
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="replace")
        path = root / relative
        parts = {part.lower() for part in Path(relative).parts}
        if parts & PRIVATE_PARTS or path.suffix.lower() in PRIVATE_SUFFIXES or ".private." in path.name:
            errors.append(f"{relative}: private artifact convention")
            continue
        if path.suffix.lower() == ".json" and (
            "benchmark" in relative or "fixture" in relative or "report" in relative
        ):
            _check_json(path, relative, errors)
        elif path.suffix.lower() in {".md", ".py", ".txt"}:
            # Catch accidental disclosure of the user's NAS location without
            # embedding that location itself in this public checker.
            content = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"/(?:home|Users)/[^\s]+/NAS/(?:development/)?Graphics", content):
                errors.append(f"{relative}: private artwork path")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Public artifact privacy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
