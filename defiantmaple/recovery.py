"""Explicit schema-7 metadata backup, inspection and isolated restore.

The first production storage adapter is Linux/local/private only. Unsupported
platforms refuse instead of substituting an unsafe rename/copy publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import sys
import threading
import time
import uuid

from .admission import admission_session, current_session
from .catalog import (SCHEMA_VERSION, RESTORE_PENDING_APPLICATION_ID,
                      _validate_catalog_schema, _verify_integrity,
                      catalog_state, connect, restored_root_review_detail,
                      library_identity, validate_library_id, _migrate_six_to_seven,
                      require_current_catalog)
from .recovery_storage import (absent, create_stage, private_local_parent,
                               publish, regular_existing)

MAGIC = b"DMETA1\0\0"
HEADER = struct.Struct(">8sIQ")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024**3
MAX_PACKAGE_BYTES = HEADER.size + MAX_MANIFEST_BYTES + MAX_SNAPSHOT_BYTES
MAX_REVIEW_SOURCES = 10_000
MAX_SOURCE_ROOT_BYTES = 4096
OMISSIONS = ["original_media", "derived_previews_and_cache", "out_of_catalog_settings"]
_LEGACY_MANIFEST_KEYS = frozenset({"kind", "package_version", "catalog_schema", "snapshot_bytes",
                            "snapshot_sha256", "created_utc", "omissions", "source_paths_unverified"})
_MANIFEST_KEYS = _LEGACY_MANIFEST_KEYS | {"library_id"}
_UNREAPED_WORKERS = []  # (process, owned stage paths)
_UNREAPED_LOCK = threading.Lock()


class RecoveryError(ValueError):
    """A recovery operation refused before claiming a verified outcome."""


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError("Duplicate recovery manifest key")
        result[key] = value
    return result


def _manifest(raw: bytes, length: int) -> dict:
    if not 0 < len(raw) <= MAX_MANIFEST_BYTES:
        raise RecoveryError("Recovery manifest length is invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(RecoveryError("Nonfinite manifest value")))
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise RecoveryError("Recovery manifest is malformed") from exc
    if type(value) is not dict or _canonical_json(value) != raw:
        raise RecoveryError("Recovery manifest is not canonical or has unsupported fields")
    pair = (value.get("package_version"), value.get("catalog_schema"))
    if pair == (1, 6):
        keys = _LEGACY_MANIFEST_KEYS
    elif pair == (2, 7):
        keys = _MANIFEST_KEYS
    else:
        raise RecoveryError("Recovery manifest is not canonical or has unsupported fields: package/schema version pair")
    if set(value) != keys:
        raise RecoveryError("Recovery manifest has unsupported fields")
    if pair == (2, 7):
        validate_library_id(value["library_id"])
    if (value["kind"] != "metadata-only" or type(value["package_version"]) is not int
            or type(value["catalog_schema"]) is not int
            or type(value["snapshot_bytes"]) is not int
            or value["snapshot_bytes"] != length or type(value["snapshot_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", value["snapshot_sha256"])
            or type(value["created_utc"]) is not str or len(value["created_utc"]) > 40
            or value["omissions"] != OMISSIONS or value["source_paths_unverified"] is not True):
        raise RecoveryError("Recovery manifest declarations are unsupported")
    try:
        created = datetime.fromisoformat(value["created_utc"])
    except ValueError as exc:
        raise RecoveryError("Recovery manifest creation time is invalid") from exc
    if created.tzinfo is None or created.utcoffset().total_seconds() != 0:
        raise RecoveryError("Recovery manifest creation time must be UTC")
    return value


def _verify_snapshot(path: Path, expected_schema: int = SCHEMA_VERSION) -> dict:
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=.1)
    try:
        if expected_schema not in (6, 7) or db.execute("PRAGMA user_version").fetchone()[0] != expected_schema:
            raise RecoveryError("Unsupported recovery catalog schema")
        state = catalog_state(db)
        _validate_catalog_schema(db, expected_schema)
        _verify_integrity(db)
        roots = _source_roots(db)
        return {"state": state, "schema_version": expected_schema,
                "library_id": library_identity(db) if expected_schema == 7 else None,
                "identity_status": "stored" if expected_schema == 7 else "legacy_absent",
                "assets": db.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
                "sources": len(roots),
                "standalone_assets": db.execute("SELECT COUNT(*) FROM assets WHERE source_id IS NULL").fetchone()[0]}
    finally:
        db.close()


def _source_roots(db) -> list[tuple[str, str]]:
    summary = db.execute("SELECT COUNT(*),COALESCE(MAX(length(CAST(root_path AS BLOB))),0) FROM sources").fetchone()
    if summary[0] > MAX_REVIEW_SOURCES or summary[1] > MAX_SOURCE_ROOT_BYTES:
        raise RecoveryError("Recovery source mapping exceeds review bounds")
    rows = [(row[0], row[1]) for row in db.execute(
        "SELECT source_id,root_path FROM sources ORDER BY source_id")]
    for source_id, root_text in rows:
        root = Path(root_text)
        if (not root.is_absolute() or ".." in root.parts or str(root) != root_text
                or not source_id or len(source_id.encode("utf-8")) > 256):
            raise RecoveryError("Recovery source mapping contains an unsafe path or ID")
    return rows


def _outside_sources(target: Path, roots: list[tuple[str, str]]) -> None:
    for _, root_text in roots:
        root = Path(root_text)
        try:
            locations = (root, root.resolve(strict=False))
        except (OSError, RuntimeError) as exc:
            raise RecoveryError("Recovery source placement cannot be resolved safely") from exc
        if any(target == location or location in target.parents for location in locations):
            raise RecoveryError("Recovery output cannot be placed inside a media source")


def _cleanup_stages(paths: tuple[Path, ...]) -> list[str]:
    errors = []
    for path in paths:
        for owned in (path, *(Path(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal"))):
            try:
                owned.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{owned.name}: {type(exc).__name__}")
    return errors


def reap_recovery_workers(timeout_seconds: float = 0.1) -> dict:
    """Retry bounded reaping for an OS worker that ignored its kill request."""
    if type(timeout_seconds) not in (int, float) or not 0 <= timeout_seconds <= .25:
        raise RecoveryError("Recovery reap wait must be at most 0.25 seconds")
    with _UNREAPED_LOCK:
        survivors = []
        cleanup_errors = []
        for worker, paths in _UNREAPED_WORKERS[:8]:
            worker.join(timeout_seconds)
            if worker.is_alive():
                survivors.append((worker, paths))
            else:
                cleanup_errors.extend(_cleanup_stages(paths))
        survivors.extend(_UNREAPED_WORKERS[8:])
        _UNREAPED_WORKERS[:] = survivors
        return {"remaining_workers": len(survivors), "cleanup_errors": cleanup_errors}


def _cache_roots(value: tuple[Path, ...]) -> tuple[Path, ...]:
    if type(value) is not tuple or len(value) > 128:
        raise RecoveryError("Captured cache roots must be a bounded tuple")
    result = []
    for item in value:
        root = Path(item)
        if not root.is_absolute() or ".." in root.parts or str(root) != str(item):
            raise RecoveryError("Captured cache root must be an absolute canonical path")
        result.extend((root, root.resolve(strict=False)))
    return tuple(result)


def _outside_caches(target: Path, roots: tuple[Path, ...]) -> None:
    if any(target == root or root in target.parents for root in roots):
        raise RecoveryError("Recovery output cannot be placed inside a captured cache root")


def _outside_catalog_family(target: Path, live_catalog: Path | None) -> None:
    if live_catalog is None:
        return
    family = {live_catalog, *(Path(str(live_catalog) + suffix)
                               for suffix in ("-wal", "-shm", "-journal"))}
    if target in family:
        raise RecoveryError("Recovery output cannot use the live catalog or SQLite sidecar name")


def _absent_catalog_family(catalog: Path, dirfd: int) -> None:
    absent(catalog, dirfd)
    for suffix in ("-wal", "-shm", "-journal"):
        absent(Path(str(catalog) + suffix), dirfd)


def _hash_file(path: Path, limit: int = MAX_SNAPSHOT_BYTES) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise RecoveryError("Recovery snapshot exceeds the size bound")
            digest.update(chunk)
    return size, digest.hexdigest()


def _logical_fingerprint(path: Path, *, exclude_identity: bool = False) -> str:
    """Hash rows except source holds and, only for legacy upgrade, new identity."""
    digest = hashlib.sha256()
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=.1)
    try:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in tables:
            if exclude_identity and table == "library_identity":
                continue
            columns = [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]
            if table == "sources":
                columns = [column for column in columns if column not in
                           ("enabled", "health", "health_detail")]
            digest.update(table.encode("utf-8") + b"\0")
            select = ",".join(f'"{column}"' for column in columns)
            for row in db.execute(f'SELECT {select} FROM "{table}" ORDER BY rowid'):
                encoded = repr(tuple(row)).encode("utf-8")
                digest.update(len(encoded).to_bytes(8, "big") + encoded)
        return digest.hexdigest()
    finally:
        db.close()


def _check_snapshot_page_budget(total_pages: int, page_size: int) -> None:
    if (type(total_pages) is not int or type(page_size) is not int
            or total_pages < 0 or not 512 <= page_size <= 65536
            or total_pages * page_size > MAX_SNAPSHOT_BYTES):
        raise RecoveryError("Recovery snapshot would exceed its 16 GiB size bound")


def _read_package(package: Path, snapshot: Path, cancel) -> tuple[dict, dict]:
    with private_local_parent(package) as (package, directory):
        descriptor, initial = regular_existing(package, directory)
        try:
            if initial.st_size < HEADER.size or initial.st_size > MAX_PACKAGE_BYTES:
                raise RecoveryError("Recovery package size is invalid")
            header = os.read(descriptor, HEADER.size)
            if len(header) != HEADER.size:
                raise RecoveryError("Recovery package header is truncated")
            magic, manifest_length, snapshot_length = HEADER.unpack(header)
            if (magic != MAGIC or not 0 < manifest_length <= MAX_MANIFEST_BYTES
                    or not 0 < snapshot_length <= MAX_SNAPSHOT_BYTES
                    or initial.st_size != HEADER.size + manifest_length + snapshot_length):
                raise RecoveryError("Recovery package framing is invalid")
            raw = os.read(descriptor, manifest_length)
            if len(raw) != manifest_length:
                raise RecoveryError("Recovery package manifest is truncated")
            manifest = _manifest(raw, snapshot_length)
            with private_local_parent(snapshot) as (snapshot, output_dir):
                output_fd = create_stage(snapshot, output_dir)
                try:
                    digest = hashlib.sha256()
                    remaining = snapshot_length
                    while remaining:
                        if cancel.is_set():
                            raise RecoveryError("Recovery inspection canceled")
                        block = os.read(descriptor, min(1024 * 1024, remaining))
                        if not block:
                            raise RecoveryError("Recovery package snapshot is truncated")
                        digest.update(block)
                        view = memoryview(block)
                        while view:
                            view = view[os.write(output_fd, view):]
                        remaining -= len(block)
                    os.fsync(output_fd)
                finally:
                    os.close(output_fd)
            after = os.fstat(descriptor)
            if ((initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise RecoveryError("Recovery package changed during inspection")
            if digest.hexdigest() != manifest["snapshot_sha256"]:
                raise RecoveryError("Recovery snapshot digest differs from manifest")
            details = _verify_snapshot(snapshot, manifest["catalog_schema"])
            if manifest["package_version"] == 2 and manifest["library_id"] != details["library_id"]:
                raise RecoveryError("Recovery manifest library identity differs from snapshot")
            return manifest, details
        finally:
            os.close(descriptor)


def _require_backup_catalog(db) -> str:
    """Authenticate RO source handles while preserving native contention errors."""
    try:
        return require_current_catalog(db)
    except ValueError as exc:
        cause = exc.__cause__
        if (isinstance(cause, sqlite3.Error)
                and isinstance(getattr(cause, "sqlite_errorcode", None), int)
                and cause.sqlite_errorcode & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)):
            raise cause
        raise


def _backup_worker(database: Path, package: Path, snapshot: Path, stage: Path,
                   cache_roots: tuple[Path, ...], cancel,
                   seconds: float) -> dict:
    _outside_catalog_family(package, database)
    if package.suffix != ".dmbackup":
        raise RecoveryError("Recovery package must use a .dmbackup leaf")
    with private_local_parent(database) as (database, source_dir):
        descriptor, initial = regular_existing(database, source_dir)
        os.close(descriptor)
        with private_local_parent(package) as (package, output_dir):
            absent(package, output_dir)
            live = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=.1)
            try:
                _require_backup_catalog(live)
                source_roots = _source_roots(live)
            finally:
                live.close()
            _outside_sources(database, source_roots)
            _outside_sources(package, source_roots)
            _outside_caches(database, cache_roots)
            _outside_caches(package, cache_roots)
            source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=.1)
            destination = None
            try:
                if source.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    raise RecoveryError("Unsupported source catalog schema")
                _require_backup_catalog(source)
                page_size = source.execute("PRAGMA page_size").fetchone()[0]
                _check_snapshot_page_budget(source.execute("PRAGMA page_count").fetchone()[0], page_size)
                output_fd = create_stage(snapshot, output_dir)
                os.close(output_fd)
                destination = sqlite3.connect(snapshot, timeout=.1)
                deadline = time.monotonic() + seconds
                previous = None
                restarts = 0

                def progress(status, remaining, total):
                    nonlocal previous, restarts
                    if cancel.is_set() or time.monotonic() >= deadline:
                        raise RecoveryError("Recovery backup canceled or timed out")
                    _check_snapshot_page_budget(total, page_size)
                    if previous is not None and remaining > previous:
                        restarts += 1
                        if restarts > 8:
                            raise RecoveryError("Recovery backup starved by concurrent writes")
                    previous = remaining

                source.backup(destination, pages=256, progress=progress, sleep=.01)
            finally:
                if destination is not None:
                    destination.close()
                source.close()
            if os.stat(database).st_dev != initial.st_dev or os.stat(database).st_ino != initial.st_ino:
                raise RecoveryError("Source catalog identity changed during backup")
            details = _verify_snapshot(snapshot)
            snapshot_db = sqlite3.connect(snapshot.as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                snapshot_roots = _source_roots(snapshot_db)
                _outside_sources(database, snapshot_roots)
                _outside_sources(package, snapshot_roots)
            finally:
                snapshot_db.close()
            length, digest = _hash_file(snapshot)
            manifest = {"kind": "metadata-only", "package_version": 2,
                        "catalog_schema": SCHEMA_VERSION, "library_id": details["library_id"],
                        "snapshot_bytes": length,
                        "snapshot_sha256": digest,
                        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "omissions": OMISSIONS, "source_paths_unverified": True}
            raw = _canonical_json(manifest)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise RecoveryError("Recovery manifest exceeds its bound")
            package_fd = create_stage(stage, output_dir)
            try:
                with snapshot.open("rb") as image:
                    chunks = (HEADER.pack(MAGIC, len(raw), length), raw)
                    for block in chunks:
                        view = memoryview(block)
                        while view:
                            view = view[os.write(package_fd, view):]
                    while block := image.read(1024 * 1024):
                        if cancel.is_set():
                            raise RecoveryError("Recovery backup canceled")
                        view = memoryview(block)
                        while view:
                            view = view[os.write(package_fd, view):]
                os.fsync(package_fd)
            finally:
                os.close(package_fd)
            # Reinspect the closed package through the same untrusted-input
            # path before any final name can be created.
            snapshot.unlink()
            verified_manifest, verified_details = _read_package(stage, snapshot, cancel)
            if verified_manifest != manifest or verified_details != details:
                raise RecoveryError("Closed recovery package differs from verified snapshot")
            absent(package, output_dir)
            package_length, package_digest = _hash_file(stage, MAX_PACKAGE_BYTES)
            publish(stage, package, output_dir, package_length, package_digest)
            return {"package": str(package), "manifest": manifest, "catalog": details}


def _inspect_worker(package: Path, snapshot: Path, cancel) -> dict:
    manifest, details = _read_package(package, snapshot, cancel)
    return {"package": str(package), "manifest": manifest, "catalog": details}


def _restore_worker(package: Path, catalog: Path, stage: Path,
                    cache_roots: tuple[Path, ...], live_catalog: Path | None, cancel) -> dict:
    _outside_catalog_family(catalog, live_catalog)
    if catalog.suffix != ".sqlite3":
        raise RecoveryError("Restored catalog must use a .sqlite3 leaf")
    with admission_session(catalog, destination=True) as ownership:
        with private_local_parent(catalog) as (catalog, output_dir):
            _absent_catalog_family(catalog, output_dir)
            _outside_caches(catalog, cache_roots)
            manifest, before = _read_package(package, stage, cancel)
            source_snapshot = sqlite3.connect(stage.as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                _outside_sources(catalog, _source_roots(source_snapshot))
            finally:
                source_snapshot.close()
            ownership.pin_stage(stage)
            before_fingerprint = _logical_fingerprint(stage)
            if cancel.is_set():
                raise RecoveryError("Recovery restore canceled")
            db = sqlite3.connect(stage, isolation_level=None, timeout=.1)
            try:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute("BEGIN IMMEDIATE")
                if manifest["catalog_schema"] == 6:
                    _migrate_six_to_seven(db)
                for source_id, root_path in _source_roots(db):
                    db.execute("UPDATE sources SET enabled=0,health='paused',health_detail=? WHERE source_id=?",
                               (restored_root_review_detail(source_id, root_path), source_id))
                db.execute(f"PRAGMA application_id={RESTORE_PENDING_APPLICATION_ID}")
                db.commit()
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.close()
            if any(stage.with_name(stage.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
                raise RecoveryError("Restored catalog has an unclosed SQLite sidecar")
            after = _verify_snapshot(stage)
            after_fingerprint = _logical_fingerprint(stage, exclude_identity=manifest["catalog_schema"] == 6)
            if (after["state"] != "restore_pending" or before["assets"] != after["assets"]
                    or before["sources"] != after["sources"]
                    or before["standalone_assets"] != after["standalone_assets"]
                    or before_fingerprint != after_fingerprint
                    or (manifest["catalog_schema"] == 7 and before["library_id"] != after["library_id"])):
                raise RecoveryError("Restored catalog verification differs from package")
            if manifest["catalog_schema"] == 6:
                after["identity_status"] = "assigned_legacy"
            descriptor = os.open(stage.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=output_dir)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _absent_catalog_family(catalog, output_dir)
            restored_length, restored_digest = _hash_file(stage)
            publish(stage, catalog, output_dir, restored_length, restored_digest,
                    before_link=lambda: _absent_catalog_family(catalog, output_dir))
            ownership.bind_published()
            return {"catalog": str(catalog), "manifest": manifest,
                    "restored": after, "source_paths_unverified": True}


def _worker_main(operation: str, arguments: tuple, send, cancel) -> None:
    try:
        # SQLite itself may be given malformed pages; keep that work out of UI/Core callers.
        if sys.platform == "linux":
            import resource
            ceiling = 1024 * 1024 * 1024
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            bounded = min(value for value in (soft, hard, ceiling)
                          if value != resource.RLIM_INFINITY)
            resource.setrlimit(resource.RLIMIT_AS, (bounded, hard))
        if operation == "backup":
            result = _backup_worker(*arguments[:-1], cancel, arguments[-1])
        elif operation == "inspect":
            result = _inspect_worker(*arguments, cancel)
        elif operation == "restore":
            result = _restore_worker(*arguments, cancel)
        else:
            raise RecoveryError("Unknown recovery worker operation")
        send.send((True, result))
    except BaseException as exc:
        send.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        send.close()


def _run(operation: str, arguments: tuple, stage_paths: tuple[Path, ...],
         final: Path | None, *, cancel_event=None, timeout_seconds: float = 120) -> dict:
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 120:
        raise RecoveryError("Recovery timeout must be positive and at most 120 seconds")
    if reap_recovery_workers(.05)["remaining_workers"]:
        raise RecoveryError("Earlier recovery worker still owns staging; retry its bounded reap first")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    cancel = context.Event()
    process = context.Process(target=_worker_main, args=(operation, arguments, send, cancel), daemon=True)
    source_catalog = arguments[0] if operation == "backup" else arguments[4] if operation == "restore" else None
    owner = current_session(source_catalog) if source_catalog is not None else None
    try:
        process.start()
    except BaseException:
        receive.close()
        send.close()
        raise
    send.close()
    deadline = time.monotonic() + timeout_seconds
    outcome = None
    failure = None
    try:
        if owner is not None:
            owner.retain_process(process)
        while process.is_alive():
            if cancel_event is not None and cancel_event.is_set():
                cancel.set()
                break
            if time.monotonic() >= deadline:
                cancel.set()
                break
            process.join(.05)
        if process.is_alive():
            process.join(.25)
        if process.is_alive():
            process.kill()
            process.join(.25)
            if process.is_alive():
                raise RecoveryError("Recovery worker did not exit after kill; outcome uncertain")
        if receive.poll():
            outcome = receive.recv()
        if cancel_event is not None and cancel_event.is_set():
            raise RecoveryError("Recovery operation canceled; publication state requires inspection")
        if time.monotonic() >= deadline:
            raise RecoveryError("Recovery worker deadline elapsed; publication state requires inspection")
        if outcome is None:
            raise RecoveryError("Recovery worker exited without a verified result")
        if not outcome[0]:
            raise RecoveryError(outcome[1])
    except BaseException as exc:
        failure = exc
    finally:
        receive.close()
        if process.is_alive():
            process.kill()
            process.join(.25)
        if process.is_alive():
            with _UNREAPED_LOCK:
                _UNREAPED_WORKERS.append((process, stage_paths))
            failure = RecoveryError(f"{failure}; recovery worker remains owned for bounded reaping"
                                    if failure else "Recovery worker remains owned for bounded reaping")
        cleanup_errors = [] if process.is_alive() else _cleanup_stages(stage_paths)
        if cleanup_errors:
            note = "Recovery staging cleanup failed (" + ", ".join(cleanup_errors) + "); inspect target before retry"
            failure = RecoveryError(f"{failure}; {note}" if failure else note)
    if failure is not None:
        raise failure
    return outcome[1]


def backup_metadata(database: Path, package: Path, *, cache_roots: tuple[Path, ...], cancel_event=None,
                    timeout_seconds: float = 120) -> dict:
    database, package = Path(database), Path(package)
    cache_roots = _cache_roots(cache_roots)
    _outside_catalog_family(package, database)
    if package.suffix != ".dmbackup":
        raise RecoveryError("Recovery package must use a .dmbackup leaf")
    if database == package:
        raise RecoveryError("Backup destination must differ from the catalog")
    suffix = uuid.uuid4().hex
    snapshot = package.with_name(f".recovery-{suffix}.snapshot")
    stage = package.with_name(f".recovery-{suffix}.package")
    return _run("backup", (database, package, snapshot, stage, cache_roots, timeout_seconds),
                (snapshot, stage), package, cancel_event=cancel_event,
                timeout_seconds=timeout_seconds)


def inspect_package(package: Path, *, cancel_event=None, timeout_seconds: float = 120) -> dict:
    package = Path(package)
    snapshot = package.with_name(f".recovery-{uuid.uuid4().hex}.inspect")
    return _run("inspect", (package, snapshot), (snapshot,), None,
                cancel_event=cancel_event, timeout_seconds=timeout_seconds)


def restore_metadata(package: Path, catalog: Path, *, cache_roots: tuple[Path, ...],
                     live_catalog: Path | None, cancel_event=None,
                     timeout_seconds: float = 120) -> dict:
    package, catalog = Path(package), Path(catalog)
    cache_roots = _cache_roots(cache_roots)
    live_catalog = Path(live_catalog) if live_catalog is not None else None
    _outside_catalog_family(catalog, live_catalog)
    if catalog.suffix != ".sqlite3":
        raise RecoveryError("Restored catalog must use a .sqlite3 leaf")
    if package == catalog:
        raise RecoveryError("Restore destination must differ from the package")
    stage = catalog.with_name(f".recovery-{uuid.uuid4().hex}.restore")
    return _run("restore", (package, catalog, stage, cache_roots, live_catalog), (stage,), catalog,
                cancel_event=cancel_event, timeout_seconds=timeout_seconds)


def review_restored_sources(database: Path, captured: list[tuple[str, str]]) -> dict:
    """Clear browse-only state after complete captured mapping review, without enabling roots."""
    if type(captured) is not list or len(captured) > MAX_REVIEW_SOURCES or any(
            type(item) is not tuple or len(item) != 2 or any(type(part) is not str for part in item)
            or len(item[0].encode("utf-8")) > 256
            or len(item[1].encode("utf-8")) > MAX_SOURCE_ROOT_BYTES
            for item in captured):
        raise RecoveryError("Captured source mapping is invalid or exceeds its bound")
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        if catalog_state(db) != "restore_pending":
            raise RecoveryError("Catalog is not awaiting restored-source review")
        actual = _source_roots(db)
        if actual != captured:
            raise RecoveryError("Restored source mapping changed; review it again")
        standalone = db.execute("SELECT COUNT(*) FROM assets WHERE source_id IS NULL").fetchone()[0]
        if standalone:
            raise RecoveryError(f"{standalone} standalone assets require a later durable relink review")
        if db.execute("SELECT 1 FROM sources WHERE enabled<>0 LIMIT 1").fetchone():
            raise RecoveryError("Restored source activation changed unexpectedly")
        if any(db.execute("SELECT health_detail FROM sources WHERE source_id=?", (source_id,)).fetchone()[0]
               != restored_root_review_detail(source_id, root_path)
               for source_id, root_path in actual):
            raise RecoveryError("Restored source review hold changed unexpectedly")
        db.execute("PRAGMA application_id=0")
        return {"reviewed_sources": len(actual), "standalone_assets": 0,
                "state": "active", "sources_enabled": 0}


def enable_reviewed_source(database: Path, source_id: str, captured_root: str) -> dict:
    """Enable one previously reviewed source with exact ID/path capture; no scan."""
    if type(source_id) is not str or type(captured_root) is not str:
        raise RecoveryError("Source review target is invalid")
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        if catalog_state(db) != "active":
            raise RecoveryError("Restored catalog still awaits source review")
        row = db.execute("SELECT root_path,health_detail,enabled FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if (row is None or row[0] != captured_root or row[2] != 0
                or row[1] != restored_root_review_detail(source_id, captured_root)):
            raise RecoveryError("Source path changed; review the mapping again")
        root = Path(captured_root)
        if not root.is_absolute() or ".." in root.parts or str(root) != captured_root:
            raise RecoveryError("Reviewed source root is unsafe")
        for part in (Path("/"), *reversed(root.parents), root):
            info = part.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RecoveryError("Reviewed source root is unavailable or redirected")
        if not os.access(root, os.R_OK | os.X_OK, effective_ids=True):
            raise RecoveryError("Reviewed source root lacks directory read/search access")
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.close(descriptor)
        db.execute("UPDATE sources SET enabled=1,health='paused',health_detail=NULL WHERE source_id=?",
                   (source_id,))
        return {"source_id": source_id, "root_path": captured_root, "enabled": True}
