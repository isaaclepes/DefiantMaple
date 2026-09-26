"""Per-library SQLite foundation. Original media is only opened for reading."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import stat
import uuid

from .media import sniff

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    recursive INTEGER NOT NULL DEFAULT 1 CHECK (recursive IN (0,1)),
    existing_file_policy TEXT NOT NULL
      CHECK (existing_file_policy IN ('inbox','reviewed','ignore_until_modified')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    health TEXT NOT NULL DEFAULT 'paused'
      CHECK (health IN ('watching','scanning','paused','offline','permission_denied','error')),
    health_detail TEXT,
    initial_scan_completed INTEGER NOT NULL DEFAULT 0
      CHECK (initial_scan_completed IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_scan_at TEXT
);
CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,
    current_path TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    workflow_state TEXT NOT NULL DEFAULT 'new'
      CHECK (workflow_state IN ('new','needs_review','reviewed','organized','ignored','error')),
    source_id TEXT REFERENCES sources(source_id),
    discovered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX assets_hash ON assets(sha256);
CREATE INDEX assets_inbox ON assets(workflow_state, discovered_at);
CREATE TABLE provenance (
    provenance_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    source_kind TEXT NOT NULL,
    details_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX provenance_asset ON provenance(asset_id);
CREATE TABLE source_entries (
    current_path TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    modified_ns INTEGER NOT NULL,
    device TEXT NOT NULL,
    inode TEXT NOT NULL,
    stable_since_ns INTEGER NOT NULL,
    observed_at_ns INTEGER NOT NULL,
    preexisting INTEGER NOT NULL CHECK (preexisting IN (0,1)),
    disposition TEXT NOT NULL
      CHECK (disposition IN ('pending','ignored_existing','indexed','unsupported','missing','error')),
    asset_id TEXT REFERENCES assets(asset_id),
    last_error TEXT
);
CREATE INDEX source_entries_source ON source_entries(source_id, disposition);
CREATE UNIQUE INDEX source_entries_asset ON source_entries(asset_id)
  WHERE asset_id IS NOT NULL;
PRAGMA user_version = 2;
"""

MIGRATE_1_TO_2 = """
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    recursive INTEGER NOT NULL DEFAULT 1 CHECK (recursive IN (0,1)),
    existing_file_policy TEXT NOT NULL
      CHECK (existing_file_policy IN ('inbox','reviewed','ignore_until_modified')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    health TEXT NOT NULL DEFAULT 'paused'
      CHECK (health IN ('watching','scanning','paused','offline','permission_denied','error')),
    health_detail TEXT,
    initial_scan_completed INTEGER NOT NULL DEFAULT 0
      CHECK (initial_scan_completed IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_scan_at TEXT
);
ALTER TABLE assets ADD COLUMN source_id TEXT REFERENCES sources(source_id);
CREATE TABLE source_entries (
    current_path TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    modified_ns INTEGER NOT NULL,
    device TEXT NOT NULL,
    inode TEXT NOT NULL,
    stable_since_ns INTEGER NOT NULL,
    observed_at_ns INTEGER NOT NULL,
    preexisting INTEGER NOT NULL CHECK (preexisting IN (0,1)),
    disposition TEXT NOT NULL
      CHECK (disposition IN ('pending','ignored_existing','indexed','unsupported','missing','error')),
    asset_id TEXT REFERENCES assets(asset_id),
    last_error TEXT
);
CREATE INDEX source_entries_source ON source_entries(source_id, disposition);
CREATE UNIQUE INDEX source_entries_asset ON source_entries(asset_id)
  WHERE asset_id IS NOT NULL;
PRAGMA user_version = 2;
"""


@contextmanager
def connect(path: Path):
    # mode=rw avoids accidentally creating a catalog on a mistyped read command.
    uri = Path(path).resolve().as_uri() + "?mode=rw"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported catalog schema {version}; run init for a new catalog")
        with db:
            yield db
    finally:
        db.close()


def initialize(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version == 1:
            db.executescript("BEGIN IMMEDIATE;\n" + MIGRATE_1_TO_2 + "\nCOMMIT;")
            return
        if version != 0 or db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone():
            raise ValueError("Refusing to initialize an unknown or newer database")
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
    finally:
        db.close()


def fingerprint(s):
    """Return fields with consistent path/fd semantics on all three target OSes.

    Windows changed the meaning and precision of ``st_ctime`` across supported
    Python versions, and path/fd stat calls can consequently disagree for the
    same open file. Size and modification time are the portable stability
    signals used by this spike; the SHA-256 remains the content identity signal.
    """
    return s.st_size, s.st_mtime_ns


def index_file(
    database: Path,
    path: Path,
    *,
    source_id: str | None = None,
    workflow_state: str = "new",
    reconcile: bool = False,
) -> str:
    if workflow_state not in {
        "new", "needs_review", "reviewed", "organized", "ignored", "error"
    }:
        raise ValueError(f"Unknown workflow state: {workflow_state}")
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Only regular files can be indexed")
    digest = hashlib.sha256()
    with path.open("rb") as media:
        if fingerprint(before) != fingerprint(os.fstat(media.fileno())):
            raise ValueError("File changed before reading; retry after it is stable")
        prefix = media.read(4096)
        detected = sniff(prefix)
        if detected is None:
            raise ValueError("Unsupported or unrecognized media signature")
        digest.update(prefix)
        while chunk := media.read(1024 * 1024):
            digest.update(chunk)
        if fingerprint(before) != fingerprint(os.fstat(media.fileno())):
            raise ValueError("File changed while reading; retry after it is stable")
    if fingerprint(before) != fingerprint(path.stat()):
        raise ValueError("File replaced during indexing")
    checksum = digest.hexdigest()
    with connect(database) as db:
        existing = db.execute("SELECT * FROM assets WHERE current_path=?", (str(path),)).fetchone()
        if existing:
            if existing["sha256"] != checksum:
                if not reconcile:
                    raise ValueError("Indexed path content changed; reconciliation is not implemented")
                db.execute(
                    "UPDATE assets SET media_type=?,sha256=?,byte_size=?,workflow_state=?,"
                    "source_id=COALESCE(?,source_id) WHERE asset_id=?",
                    (detected.mime, checksum, before.st_size, workflow_state,
                     source_id, existing["asset_id"]),
                )
                db.execute(
                    "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json) "
                    "VALUES(?,?,?,?)",
                    (str(uuid.uuid4()), existing["asset_id"], "filesystem_change", json.dumps({
                        "path": str(path),
                        "previous_sha256": existing["sha256"],
                        "sha256": checksum,
                        "detection_method": detected.method,
                        "decoder_validated": False,
                    })),
                )
            elif source_id is not None and existing["source_id"] is None:
                db.execute(
                    "UPDATE assets SET source_id=?,workflow_state=? WHERE asset_id=?",
                    (source_id, workflow_state, existing["asset_id"]),
                )
            return existing["asset_id"]
        asset_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
            "workflow_state,source_id) VALUES(?,?,?,?,?,?,?)",
            (asset_id, str(path), detected.mime, checksum, before.st_size,
             workflow_state, source_id),
        )
        db.execute("INSERT INTO provenance VALUES(?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (
            str(uuid.uuid4()), asset_id, "filesystem", json.dumps({
                "original_path": str(path), "detection_method": detected.method,
                "decoder_validated": False, "source_id": source_id,
            }),
        ))
        return asset_id


def record_external_rename(
    database: Path,
    asset_id: str,
    old_path: Path,
    new_path: Path,
    source_id: str,
    *,
    byte_size: int,
    modified_ns: int,
    device: str,
    inode: str,
    observed_at_ns: int,
) -> None:
    """Atomically update catalog and observation metadata for a proven rename."""
    old_path = Path(old_path).resolve(strict=False)
    new_path = Path(new_path).resolve(strict=True)
    if old_path.exists():
        raise ValueError("Rename source path reappeared before reconciliation")
    observed = new_path.stat()
    observed_identity = (
        observed.st_size, observed.st_mtime_ns, str(observed.st_dev), str(observed.st_ino)
    )
    if observed_identity != (byte_size, modified_ns, device, inode):
        raise ValueError("Rename target changed before reconciliation")
    with connect(database) as db:
        asset = db.execute(
            "SELECT current_path FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if asset is None or asset["current_path"] != str(old_path):
            raise ValueError("Asset path changed before rename reconciliation")
        if db.execute(
            "SELECT 1 FROM assets WHERE current_path=? AND asset_id<>?",
            (str(new_path), asset_id),
        ).fetchone():
            raise ValueError("Rename target is already cataloged")
        changed = db.execute(
            "UPDATE source_entries SET current_path=?,source_id=?,byte_size=?,modified_ns=?,"
            "device=?,inode=?,observed_at_ns=?,disposition='indexed',last_error=NULL "
            "WHERE current_path=? AND asset_id=?",
            (str(new_path), source_id, byte_size, modified_ns, device, inode,
             observed_at_ns, str(old_path), asset_id),
        ).rowcount
        if changed != 1:
            raise ValueError("Source observation changed before rename reconciliation")
        db.execute(
            "UPDATE assets SET current_path=?,source_id=? WHERE asset_id=?",
            (str(new_path), source_id, asset_id),
        )
        db.execute(
            "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json) "
            "VALUES(?,?,?,?)",
            (str(uuid.uuid4()), asset_id, "filesystem_rename", json.dumps({
                "old_path": str(old_path), "new_path": str(new_path),
                "source_id": source_id,
            })),
        )


def list_assets(database: Path, limit: int = 100, offset: int = 0) -> list[dict]:
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("limit must be 1..1000 and offset must be nonnegative")
    with connect(database) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM assets ORDER BY discovered_at,asset_id LIMIT ? OFFSET ?", (limit, offset)
        )]


def duplicates(database: Path) -> list[dict]:
    with connect(database) as db:
        return [dict(row) for row in db.execute(
            "SELECT sha256,COUNT(*) AS asset_count FROM assets GROUP BY sha256 HAVING COUNT(*)>1"
        )]
