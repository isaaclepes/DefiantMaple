"""Opt-in, local-only curation and evaluation of rights-cleared assets.

The private store and model cache must be outside every artwork source. Nothing
in this module adds character suggestions to the catalog or changes asset rows.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

from .catalog import connect
from .sources import list_sources


ROLES = ("reference", "query", "near-lookalike-negative")
RIGHTS = ("artist_owned", "permission_granted", "uncertain")
ANONYMOUS_ID = re.compile(r"character-[0-9]{3,}")
PRIVATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS selections (
    asset_id TEXT PRIMARY KEY,
    anonymous_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('reference','query','near-lookalike-negative')),
    rights_status TEXT NOT NULL CHECK(rights_status IN
      ('artist_owned','permission_granted','uncertain')),
    private_notes TEXT NOT NULL DEFAULT '',
    source_sha256 TEXT NOT NULL,
    selected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""


def default_private_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "DefiantMaple" / "private-evaluations"


def assert_outside_sources(target: Path, source_roots) -> None:
    target = Path(target).expanduser().resolve(strict=False)
    for root in source_roots:
        root = Path(root).expanduser().resolve(strict=False)
        if target == root or root in target.parents:
            raise ValueError("Application data must be outside every artwork source")


def assert_outside_git(target: Path) -> None:
    target = Path(target).expanduser().resolve(strict=False)
    if any((parent / ".git").is_file() or (parent / ".git" / "HEAD").exists()
           for parent in (target, *target.parents)):
        raise ValueError("Private libraries, manifests, caches, and vectors must be outside Git")


def assert_library_locations(database: Path, cache_root: Path, source_root: Path) -> None:
    """Prevent a library, cache, or private manifest from entering source art."""
    source_root = Path(source_root).expanduser().resolve(strict=False)
    assert_outside_sources(database, [source_root])
    assert_outside_sources(cache_root, [source_root])
    assert_outside_sources(default_private_root(), [source_root])
    assert_outside_git(database)
    assert_outside_git(cache_root)


class PrivateSelectionStore:
    def __init__(self, path: Path, catalog: Path):
        self.path = Path(path).expanduser().resolve(strict=False)
        self.catalog = Path(catalog).expanduser().resolve(strict=True)
        assert_outside_sources(self.path, [s["root_path"] for s in list_sources(self.catalog)])
        assert_outside_git(self.path)
        if self.path == self.catalog:
            raise ValueError("Private selections require a separate database")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(PRIVATE_SCHEMA)

    def select(self, asset_id: str, anonymous_id: str, role: str,
               rights_status: str, private_notes: str = "") -> None:
        if not ANONYMOUS_ID.fullmatch(anonymous_id):
            raise ValueError("Use an anonymous identifier such as character-001")
        if role not in ROLES or rights_status not in RIGHTS:
            raise ValueError("Unknown evaluation role or rights status")
        if len(private_notes) > 4000:
            raise ValueError("Private notes exceed 4000 characters")
        with connect(self.catalog) as db:
            asset = db.execute("SELECT sha256 FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        if asset is None:
            raise ValueError("Unknown catalog asset")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO selections(asset_id,anonymous_id,role,rights_status,"
                "private_notes,source_sha256) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(asset_id) DO UPDATE SET anonymous_id=excluded.anonymous_id,"
                "role=excluded.role,rights_status=excluded.rights_status,"
                "private_notes=excluded.private_notes,source_sha256=excluded.source_sha256",
                (asset_id, anonymous_id, role, rights_status, private_notes, asset["sha256"]),
            )

    def entries(self, *, include_uncertain: bool = False) -> list[dict]:
        query = "SELECT * FROM selections"
        if not include_uncertain:
            query += " WHERE rights_status<>'uncertain'"
        query += " ORDER BY anonymous_id,role,asset_id"
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query)]


PUBLIC_KEYS = {"schema", "dataset_counts", "recall_at_1", "recall_at_5",
               "mean_reciprocal_rank", "latency_ms_p50", "memory_rss_peak_mib",
               "false_match_categories"}
COUNT_KEYS = {"characters", "references", "queries", "negatives", "excluded_uncertain"}
CATEGORY_KEYS = {"lookalike", "style_shift", "other"}


def sanitize_public_summary(raw: dict) -> dict:
    """Reject unknown fields instead of attempting to scrub identifying values."""
    if set(raw) != PUBLIC_KEYS or raw.get("schema") != "defiantmaple.private-eval-summary.v1":
        raise ValueError("Public summary contains unknown or missing fields")
    counts = raw["dataset_counts"]
    categories = raw["false_match_categories"]
    if set(counts) != COUNT_KEYS or not set(categories) <= CATEGORY_KEYS:
        raise ValueError("Public summary contains identifying category fields")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("Dataset counts must be nonnegative integers")
    if any(type(value) is not int or value < 0 for value in categories.values()):
        raise ValueError("False-match categories must be aggregate counts")
    for key in PUBLIC_KEYS - {"schema", "dataset_counts", "false_match_categories"}:
        value = raw[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                                  or value < 0):
            raise ValueError("Public metrics must be finite nonnegative numbers")
    for key in ("recall_at_1", "recall_at_5", "mean_reciprocal_rank"):
        if raw[key] is not None and raw[key] > 1:
            raise ValueError("Retrieval metrics must be in 0..1")
    return json.loads(json.dumps(raw, sort_keys=True))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
