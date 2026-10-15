"""Generated-fixture smoke for the actual spawned metadata recovery worker."""
from __future__ import annotations

import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import stat
import time

from defiantmaple.catalog import RESTORE_PENDING_APPLICATION_ID, restored_root_review_detail
from defiantmaple.recovery import (RecoveryError, backup_metadata, inspect_package,
                                  reap_recovery_workers, restore_metadata)
from defiantmaple.recovery_storage import private_local_parent


SCHEMA = "defiantmaple.recovery-worker-smoke.v1"
_UNSUPPORTED = frozenset({
    "Recovery publication has no reviewed native adapter on this platform",
    "Recovery requires a verified durable local filesystem",
})


def _tables(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        if [row[0] for row in db.execute("PRAGMA integrity_check")] != ["ok"]:
            raise ValueError("Generated recovery smoke catalog integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Generated recovery smoke catalog foreign keys failed")
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: sorted((tuple(row) for row in db.execute(
                    'SELECT * FROM "' + name.replace('"', '""') + '"')), key=repr)
                for name in names}


def _check_restored_tables(before: dict, after: dict) -> None:
    if before.keys() != after.keys() or "sources" not in before:
        raise ValueError("Recovery smoke table inventory changed")
    for name in before:
        if name != "sources" and before[name] != after[name]:
            raise ValueError(f"Recovery smoke table changed: {name}")
    # Restored sources must retain every other column while entering the
    # browse-only review hold. There is no automatic root activation or scan.
    if len(before["sources"]) != len(after["sources"]):
        raise ValueError("Recovery smoke source count changed")


def _sources(path: Path) -> list[dict]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY source_id")]


def _original_paths(path: Path) -> list[Path]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        return [Path(row[0]) for row in db.execute("SELECT current_path FROM assets")]


def _assert_no_stage(parent: Path) -> None:
    if list(parent.glob(".recovery-*")):
        raise ValueError("Recovery smoke retained a worker stage")
    report = reap_recovery_workers(0)
    if report != {"remaining_workers": 0, "cleanup_errors": []}:
        raise ValueError(f"Recovery smoke retained worker ownership: {report}")


def _catalog_family(path: Path) -> dict[str, tuple | None]:
    family = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        member = Path(str(path) + suffix)
        if member.is_file():
            info = member.stat()
            family[suffix or "main"] = (hashlib.sha256(member.read_bytes()).hexdigest(),
                                         info.st_size, stat.S_IMODE(info.st_mode), info.st_mtime_ns)
        else:
            family[suffix or "main"] = None
    return family


def run_recovery_smoke(catalog: Path, package: Path, restored: Path,
                       cache_root: Path) -> dict:
    """Use only generated private paths; never open the fictional original."""
    catalog, package, restored, cache_root = map(Path, (catalog, package, restored, cache_root))
    if (not all(path.is_absolute() for path in (catalog, package, restored, cache_root))
            or len({catalog.parent, package.parent, restored.parent, cache_root.parent}) != 1):
        raise ValueError("Recovery smoke requires one absolute generated fixture")
    parent = catalog.parent
    invalid = parent / "truncated.dmbackup"
    if not invalid.is_file() or invalid.read_bytes() != b"invalid" or package.exists() or restored.exists():
        raise ValueError("Recovery smoke fixture is not fresh and truncated")
    before_tables = _tables(catalog)
    before_catalog_family = _catalog_family(catalog)
    if list((parent / "fictional-source").iterdir()) or list(cache_root.iterdir()):
        raise ValueError("Recovery smoke source/cache fixture is not empty")
    originals = _original_paths(catalog)
    if originals != [parent / "fictional-source" / "never-created.png"]:
        raise ValueError("Recovery smoke requires only its fictional original path")

    try:
        with private_local_parent(package):
            pass
        unsupported = None
    except ValueError as exc:
        unsupported = str(exc)
        if unsupported not in _UNSUPPORTED:
            raise

    started = time.monotonic()
    try:
        inspect_package(invalid, timeout_seconds=25)
    except RecoveryError as exc:
        expected = unsupported or "Recovery package size is invalid"
        if expected not in str(exc) or "worker remains owned" in str(exc):
            raise ValueError(f"Spawned recovery inspection refused unexpectedly: {exc}") from exc
    else:
        raise ValueError("Truncated recovery package was accepted")
    _assert_no_stage(parent)

    if unsupported:
        if _tables(catalog) != before_tables or _catalog_family(catalog) != before_catalog_family:
            raise ValueError("Refusal-only recovery smoke changed generated catalog")
        if list((parent / "fictional-source").iterdir()) or list(cache_root.iterdir()):
            raise ValueError("Refusal-only recovery smoke changed generated source or cache")
        return {"schema": SCHEMA, "status": "refusal_only", "reason": unsupported,
                "spawned_inspect_refusal": True, "worker_reaped": True,
                "catalog_unchanged": True, "source_cache_unchanged": True,
                "publication_qualified": False,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}

    backup = backup_metadata(catalog, package, cache_roots=(cache_root,), timeout_seconds=25)
    inspected = inspect_package(package, timeout_seconds=25)
    if backup["manifest"] != inspected["manifest"] or backup["catalog"] != inspected["catalog"]:
        raise ValueError("Spawned backup and inspection disagreed")
    result = restore_metadata(package, restored, cache_roots=(cache_root,),
                              live_catalog=catalog, timeout_seconds=25)
    if result["restored"]["state"] != "restore_pending" or not result["source_paths_unverified"]:
        raise ValueError("Spawned restore did not remain browse-only")
    after_tables = _tables(restored)
    _check_restored_tables(before_tables, after_tables)
    source_before, source_after = _sources(catalog), _sources(restored)
    if len(source_before) != len(source_after):
        raise ValueError("Restored source count changed")
    for original, restored_source in zip(source_before, source_after):
        expected = {**original, "enabled": 0, "health": "paused",
                    "health_detail": restored_root_review_detail(original["source_id"], original["root_path"])}
        if restored_source != expected:
            raise ValueError("Restored source did not retain a disabled review hold")
    with closing(sqlite3.connect(restored.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA application_id").fetchone()[0] != RESTORE_PENDING_APPLICATION_ID:
            raise ValueError("Restored catalog lacks its browse-only marker")
    if _tables(catalog) != before_tables or _catalog_family(catalog) != before_catalog_family:
        raise ValueError("Recovery smoke changed its live catalog")
    if list((parent / "fictional-source").iterdir()) or list(cache_root.iterdir()):
        raise ValueError("Recovery smoke changed generated source or cache")
    _assert_no_stage(parent)
    return {"schema": SCHEMA, "status": "publication_passed",
            "spawned_inspect_refusal": True, "spawned_backup": True,
            "spawned_inspect": True, "spawned_restore": True,
            "worker_reaped": True, "catalog_unchanged": True,
            "source_cache_unchanged": True,
            "all_tables_preserved": True, "sources_held": len(source_after),
            "publication_qualified": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000)}
