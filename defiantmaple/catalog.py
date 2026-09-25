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

SCHEMA = """
CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,
    current_path TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    workflow_state TEXT NOT NULL DEFAULT 'new'
      CHECK (workflow_state IN ('new','needs_review','reviewed','organized','ignored','error')),
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
PRAGMA user_version = 1;
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
        if version != 1:
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
        if version == 1:
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


def index_file(database: Path, path: Path) -> str:
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
                raise ValueError("Indexed path content changed; reconciliation is not implemented")
            return existing["asset_id"]
        asset_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) VALUES(?,?,?,?,?)",
            (asset_id, str(path), detected.mime, checksum, before.st_size),
        )
        db.execute("INSERT INTO provenance VALUES(?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (
            str(uuid.uuid4()), asset_id, "filesystem", json.dumps({
                "original_path": str(path), "detection_method": detected.method,
                "decoder_validated": False,
            }),
        ))
        return asset_id


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
