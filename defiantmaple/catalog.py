"""Per-library SQLite foundation. Original media is only opened for reading."""
from contextlib import closing, contextmanager
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid

from .media import sniff

SCHEMA_VERSION = 5

SCHEMA_V2 = """
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


METADATA_SCHEMA = """
CREATE TABLE tags (
    tag_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL CHECK(name<>''),
    normalized_name TEXT NOT NULL UNIQUE CHECK(normalized_name<>''),
    parent_id TEXT REFERENCES tags(tag_id) ON DELETE RESTRICT,
    CHECK(parent_id IS NULL OR parent_id<>tag_id)
);
CREATE TABLE tag_aliases (
    normalized_alias TEXT NOT NULL PRIMARY KEY CHECK(normalized_alias<>''),
    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    alias TEXT NOT NULL CHECK(alias<>'')
);
CREATE INDEX tag_aliases_owner ON tag_aliases(tag_id);
CREATE TABLE entities (
    entity_id TEXT NOT NULL PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK(entity_type IN
      ('Character','Artist','Project','Location','Client','Franchise')),
    name TEXT NOT NULL CHECK(name<>''),
    normalized_name TEXT NOT NULL CHECK(normalized_name<>''),
    UNIQUE(entity_type,normalized_name),
    UNIQUE(entity_id,entity_type)
);
CREATE TABLE entity_aliases (
    entity_type TEXT NOT NULL,
    normalized_alias TEXT NOT NULL CHECK(normalized_alias<>''),
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL CHECK(alias<>''),
    PRIMARY KEY(entity_type,normalized_alias),
    FOREIGN KEY(entity_id,entity_type) REFERENCES entities(entity_id,entity_type)
      ON DELETE CASCADE
);
CREATE INDEX entity_aliases_owner ON entity_aliases(entity_id);
CREATE TABLE asset_tags (
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY(asset_id,tag_id)
);
CREATE INDEX asset_tags_tag ON asset_tags(tag_id);
CREATE TABLE asset_entities (
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    PRIMARY KEY(asset_id,entity_id)
);
CREATE INDEX asset_entities_entity ON asset_entities(entity_id);
CREATE TRIGGER tags_insert_namespace BEFORE INSERT ON tags
WHEN EXISTS(SELECT 1 FROM tag_aliases WHERE normalized_alias=NEW.normalized_name)
BEGIN SELECT RAISE(ABORT,'Tag name collides with alias'); END;
CREATE TRIGGER tags_update_namespace BEFORE UPDATE OF normalized_name ON tags
WHEN EXISTS(SELECT 1 FROM tag_aliases WHERE normalized_alias=NEW.normalized_name)
BEGIN SELECT RAISE(ABORT,'Tag name collides with alias'); END;
CREATE TRIGGER tag_aliases_insert_namespace BEFORE INSERT ON tag_aliases
WHEN EXISTS(SELECT 1 FROM tags WHERE normalized_name=NEW.normalized_alias)
BEGIN SELECT RAISE(ABORT,'Tag alias collides with name'); END;
CREATE TRIGGER tag_aliases_update_namespace BEFORE UPDATE OF normalized_alias ON tag_aliases
WHEN EXISTS(SELECT 1 FROM tags WHERE normalized_name=NEW.normalized_alias)
BEGIN SELECT RAISE(ABORT,'Tag alias collides with name'); END;
CREATE TRIGGER entities_insert_namespace BEFORE INSERT ON entities
WHEN EXISTS(SELECT 1 FROM entity_aliases WHERE entity_type=NEW.entity_type
            AND normalized_alias=NEW.normalized_name)
BEGIN SELECT RAISE(ABORT,'Entity name collides with alias'); END;
CREATE TRIGGER entities_update_namespace BEFORE UPDATE OF normalized_name,entity_type ON entities
WHEN EXISTS(SELECT 1 FROM entity_aliases WHERE entity_type=NEW.entity_type
            AND normalized_alias=NEW.normalized_name)
BEGIN SELECT RAISE(ABORT,'Entity name collides with alias'); END;
CREATE TRIGGER entity_aliases_insert_namespace BEFORE INSERT ON entity_aliases
WHEN EXISTS(SELECT 1 FROM entities WHERE entity_type=NEW.entity_type
            AND normalized_name=NEW.normalized_alias)
BEGIN SELECT RAISE(ABORT,'Entity alias collides with name'); END;
CREATE TRIGGER entity_aliases_update_namespace BEFORE UPDATE OF normalized_alias,entity_type ON entity_aliases
WHEN EXISTS(SELECT 1 FROM entities WHERE entity_type=NEW.entity_type
            AND normalized_name=NEW.normalized_alias)
BEGIN SELECT RAISE(ABORT,'Entity alias collides with name'); END;
CREATE TRIGGER tags_parent_cycle BEFORE UPDATE OF parent_id ON tags
WHEN NEW.parent_id IS NOT NULL AND EXISTS(
    WITH RECURSIVE ancestors(tag_id,parent_id) AS (
      SELECT tag_id,parent_id FROM tags WHERE tag_id=NEW.parent_id
      UNION SELECT tags.tag_id,tags.parent_id FROM tags
      JOIN ancestors ON tags.tag_id=ancestors.parent_id
    ) SELECT 1 FROM ancestors WHERE tag_id=NEW.tag_id
)
BEGIN SELECT RAISE(ABORT,'Tag hierarchy cycle'); END;
PRAGMA user_version = 3;
"""

COLLECTIONS_SCHEMA = """
CREATE TABLE collections (
    collection_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL CHECK(name<>''),
    normalized_name TEXT NOT NULL UNIQUE CHECK(normalized_name<>'')
);
CREATE TABLE collection_members (
    collection_id TEXT NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK(typeof(position)='integer' AND position>=0),
    PRIMARY KEY(collection_id,asset_id),
    UNIQUE(collection_id,position)
);
CREATE INDEX collection_members_asset ON collection_members(asset_id);
PRAGMA user_version = 4;
"""

# Ratings/favorites are explicit user catalog overrides, never imported candidates.
CURATION_SCHEMA = """
ALTER TABLE assets ADD COLUMN rating INTEGER
    CHECK(rating IS NULL OR (typeof(rating)='integer' AND rating BETWEEN 1 AND 5));
ALTER TABLE assets ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0
    CHECK(typeof(favorite)='integer' AND favorite IN (0,1));
ALTER TABLE assets ADD COLUMN revision INTEGER NOT NULL DEFAULT 0
    CHECK(typeof(revision)='integer' AND revision>=0);
CREATE TABLE curation_edits (
    edit_id TEXT NOT NULL PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE RESTRICT,
    before_rating INTEGER CHECK(before_rating IS NULL OR
        (typeof(before_rating)='integer' AND before_rating BETWEEN 1 AND 5)),
    before_favorite INTEGER NOT NULL CHECK(typeof(before_favorite)='integer' AND before_favorite IN (0,1)),
    after_rating INTEGER CHECK(after_rating IS NULL OR
        (typeof(after_rating)='integer' AND after_rating BETWEEN 1 AND 5)),
    after_favorite INTEGER NOT NULL CHECK(typeof(after_favorite)='integer' AND after_favorite IN (0,1)),
    expected_revision INTEGER NOT NULL CHECK(typeof(expected_revision)='integer' AND expected_revision>0),
    undone INTEGER NOT NULL DEFAULT 0 CHECK(typeof(undone)='integer' AND undone IN (0,1)),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(asset_id,expected_revision)
);
CREATE TRIGGER assets_identity_immutable BEFORE UPDATE OF asset_id ON assets
WHEN NEW.asset_id IS NOT OLD.asset_id
BEGIN SELECT RAISE(ABORT,'Asset identity is immutable'); END;
CREATE TRIGGER assets_revision_monotonic BEFORE UPDATE OF revision ON assets
WHEN NEW.revision<>OLD.revision+1
BEGIN SELECT RAISE(ABORT,'Asset revision must advance by one'); END;
CREATE TRIGGER assets_prevent_replace BEFORE INSERT ON assets
WHEN EXISTS(SELECT 1 FROM assets WHERE asset_id=NEW.asset_id OR current_path=NEW.current_path)
BEGIN SELECT RAISE(ABORT,'Asset replacement would reset revision'); END;
CREATE TRIGGER assets_revision AFTER UPDATE OF current_path,media_type,sha256,byte_size,
    workflow_state,source_id,discovered_at,rating,favorite ON assets
WHEN NEW.current_path IS NOT OLD.current_path OR NEW.media_type IS NOT OLD.media_type
  OR NEW.sha256 IS NOT OLD.sha256 OR NEW.byte_size IS NOT OLD.byte_size
  OR NEW.workflow_state IS NOT OLD.workflow_state OR NEW.source_id IS NOT OLD.source_id
  OR NEW.discovered_at IS NOT OLD.discovered_at OR NEW.rating IS NOT OLD.rating
  OR NEW.favorite IS NOT OLD.favorite
BEGIN UPDATE assets SET revision=revision+1 WHERE asset_id=NEW.asset_id; END;
"""

# Revisions include direct SQL/cascade changes, not just the public metadata API.
for _table, _fields in (("asset_tags", ("asset_id", "tag_id")),
                         ("asset_entities", ("asset_id", "entity_id")),
                         ("collection_members", ("asset_id", "collection_id", "position")),
                         ("source_entries", ("asset_id", "current_path", "source_id", "byte_size",
                                             "modified_ns", "device", "inode", "disposition"))):
    for _op, _rows in (("INSERT", ("NEW",)), ("DELETE", ("OLD",)),
                      ("UPDATE", ("OLD", "NEW"))):
        _when = (" WHEN " + " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in _fields)
                 if _op == "UPDATE" else "")
        _targets = ",".join(f"{row}.asset_id" for row in _rows)
        CURATION_SCHEMA += (f"CREATE TRIGGER {_table}_revision_{_op.lower()} AFTER {_op} ON {_table}{_when}\n"
                           f"BEGIN UPDATE assets SET revision=revision+1 WHERE asset_id IN ({_targets}); END;\n")
for _table, _assignment, _key, _fields in (
    ("tags", "asset_tags", "tag_id", ("name", "normalized_name", "parent_id")),
    ("tag_aliases", "asset_tags", "tag_id", ("normalized_alias", "tag_id", "alias")),
    ("entities", "asset_entities", "entity_id", ("entity_type", "name", "normalized_name")),
    ("entity_aliases", "asset_entities", "entity_id", ("entity_type", "normalized_alias", "entity_id", "alias")),
    ("collections", "collection_members", "collection_id", ("name", "normalized_name")),
):
    for _op in (("INSERT", "DELETE", "UPDATE") if "aliases" in _table else ("UPDATE",)):
        _rows = ("OLD", "NEW") if _op == "UPDATE" else (("NEW",) if _op == "INSERT" else ("OLD",))
        _when = (" WHEN " + " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in _fields)
                 if _op == "UPDATE" else "")
        _targets = ",".join(f"{row}.{_key}" for row in _rows)
        CURATION_SCHEMA += (f"CREATE TRIGGER {_table}_revision_{_op.lower()} AFTER {_op} ON {_table}{_when}\n"
                           f"BEGIN UPDATE assets SET revision=revision+1 WHERE asset_id IN "
                           f"(SELECT asset_id FROM {_assignment} WHERE {_key} IN ({_targets})); END;\n")
CURATION_SCHEMA += "PRAGMA user_version = 5;\n"
SCHEMA_V3 = SCHEMA_V2 + METADATA_SCHEMA
SCHEMA_V4 = SCHEMA_V3 + COLLECTIONS_SCHEMA
SCHEMA = SCHEMA_V4 + CURATION_SCHEMA

class CatalogMigrationError(ValueError):
    """A refused/rolled-back upgrade; verified backup, if any, stays private."""

    def __init__(self, message: str, *, backup_path: Path | None = None):
        super().__init__(message)
        self.backup_path = str(backup_path) if backup_path is not None else None


def _execute_schema(db, script: str) -> None:
    # complete_statement understands trigger bodies; split(';') does not.
    # Connection.executescript would commit a caller's reserved transaction.
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError("Incomplete internal schema statement")


_BASE_COLUMNS = {
    "assets": {"asset_id": "TEXT", "current_path": "TEXT", "media_type": "TEXT",
               "sha256": "TEXT", "byte_size": "INTEGER", "workflow_state": "TEXT",
               "discovered_at": "TEXT"},
    "provenance": {"provenance_id": "TEXT", "asset_id": "TEXT", "source_kind": "TEXT",
                   "details_json": "TEXT", "recorded_at": "TEXT"},
}
_SOURCE_COLUMNS = {
    "sources": {"source_id": "TEXT", "name": "TEXT", "root_path": "TEXT",
                "recursive": "INTEGER", "existing_file_policy": "TEXT", "enabled": "INTEGER",
                "health": "TEXT", "health_detail": "TEXT", "initial_scan_completed": "INTEGER",
                "created_at": "TEXT", "last_scan_at": "TEXT"},
    "source_entries": {"current_path": "TEXT", "source_id": "TEXT", "byte_size": "INTEGER",
                       "modified_ns": "INTEGER", "device": "TEXT", "inode": "TEXT",
                       "stable_since_ns": "INTEGER", "observed_at_ns": "INTEGER",
                       "preexisting": "INTEGER", "disposition": "TEXT", "asset_id": "TEXT",
                       "last_error": "TEXT"},
}
_METADATA_COLUMNS = {
    "tags": {"tag_id": "TEXT", "name": "TEXT", "normalized_name": "TEXT", "parent_id": "TEXT"},
    "tag_aliases": {"normalized_alias": "TEXT", "tag_id": "TEXT", "alias": "TEXT"},
    "entities": {"entity_id": "TEXT", "entity_type": "TEXT", "name": "TEXT", "normalized_name": "TEXT"},
    "entity_aliases": {"entity_type": "TEXT", "normalized_alias": "TEXT", "entity_id": "TEXT", "alias": "TEXT"},
    "asset_tags": {"asset_id": "TEXT", "tag_id": "TEXT"},
    "asset_entities": {"asset_id": "TEXT", "entity_id": "TEXT"},
}
_PRIMARY_KEYS = {
    "assets": ("asset_id",), "provenance": ("provenance_id",),
    "sources": ("source_id",), "source_entries": ("current_path",),
    "tags": ("tag_id",), "tag_aliases": ("normalized_alias",),
    "entities": ("entity_id",), "entity_aliases": ("entity_type", "normalized_alias"),
    "asset_tags": ("asset_id", "tag_id"), "asset_entities": ("asset_id", "entity_id"),
}
_REQUIRED_LOOKUP_INDEXES = {
    # Bound this policy to the new v4 table; historical non-unique indexes
    # remain outside declaration authentication for retained v1/v2/v3 shapes.
    "collection_members": {"collection_members_asset"},
}


def _sql_key(sql: str | None) -> tuple[str, ...]:
    # Ignore formatting and SQL keyword case, but keep quoted literals intact.
    return tuple(token if token.startswith("'") else token.casefold()
                 for token in re.findall(r"'(?:''|[^'])*'|[a-zA-Z_][a-zA-Z_0-9]*|[^\s]", sql or "")
                 if token != ";")


def _checks(sql: str) -> set[tuple[str, ...]]:
    tokens = _sql_key(sql)
    result = set()
    for offset, token in enumerate(tokens):
        if token != "check" or tokens[offset + 1] != "(":
            continue
        depth, end = 1, offset + 2
        while depth:
            if tokens[end] == "(":
                depth += 1
            elif tokens[end] == ")":
                depth -= 1
            end += 1
        result.add(tokens[offset + 2:end - 1])
    return result


def _table_signature(db, table: str) -> tuple:
    # table_info omits generated and virtual-table hidden columns. Every
    # supported catalog shape has ordinary columns, including legacy v1.
    info = db.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
    if any(row[6] for row in info):
        raise ValueError(f"Catalog generated/hidden columns are unsupported: {table}")
    columns = {row[1]: (row[2].upper(), row[3], _sql_key(row[4])) for row in info}
    primary = tuple(row[1] for row in sorted(info, key=lambda row: row[5]) if row[5])
    foreign_groups = {}
    for row in db.execute(f'PRAGMA foreign_key_list("{table}")'):
        foreign_groups.setdefault(row[0], []).append(row)
    foreign = set()
    for rows in foreign_groups.values():
        rows.sort(key=lambda row: row[1])
        foreign.add((rows[0][2], rows[0][5], rows[0][6], rows[0][7],
                     tuple((row[3], row[4]) for row in rows)))
    unique = set()
    required_names = _REQUIRED_LOOKUP_INDEXES.get(table, ())
    lookups = {}
    for index in db.execute(f'PRAGMA index_list("{table}")').fetchall():
        if not index[2] and index[1] not in required_names:
            continue
        quoted = index[1].replace('"', '""')
        # Authenticate comparison semantics as well as names; NOCASE path
        # uniqueness would merge distinct files on a case-sensitive filesystem.
        fields = tuple((row[2], row[3], row[4].casefold())
                       for row in db.execute(f'PRAGMA index_xinfo("{quoted}")') if row[5])
        if index[1] in required_names:
            # index_list ties the name to this table and reports uniqueness
            # and partialness. index_xinfo supplies ordered real/expression
            # keys, direction and collation, independent of SQL formatting.
            lookups[index[1]] = (index[2], index[4], fields)
        if not index[2]:
            continue
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                         (index[1],)).fetchone()[0]
        tokens = _sql_key(sql)
        predicate = tokens[tokens.index("where") + 1:] if "where" in tokens else ()
        unique.add((fields, predicate))
    table_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone()[0]
    return columns, primary, foreign, unique, _checks(table_sql), lookups


@lru_cache(maxsize=4)
def _reference_signatures(version: int) -> tuple[dict, dict]:
    # Inspect declarations rather than trusting user_version or trigger names.
    # Column order and SQLite-generated index/FK identifiers are immaterial.
    with closing(sqlite3.connect(":memory:")) as reference:
        reference.executescript(SCHEMA_V2 + (METADATA_SCHEMA if version >= 3 else "")
                               + (COLLECTIONS_SCHEMA if version >= 4 else "")
                               + (CURATION_SCHEMA if version >= 5 else ""))
        tables = [row[0] for row in reference.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        return ({table: _table_signature(reference, table) for table in tables},
                {row[0]: _sql_key(row[1]) for row in reference.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='trigger'")})


def _validate_catalog_schema(db, version: int) -> None:
    """Authenticate declarations, required v4 lookups, FKs/uniques/trigger bodies.

    The published legacy v1 shape may lack later constraints. Its upgrade
    rebuilds these two tables into the canonical v2 schema, without changing
    rows; constraint-invalid legacy data aborts and rolls back the whole upgrade.
    """
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='view' LIMIT 1").fetchone():
        raise ValueError("Catalog views do not match supported schema")
    triggers = {row[0]: _sql_key(row[1]) for row in db.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
    if version == 1:
        if tables != set(_BASE_COLUMNS) or triggers:
            raise ValueError("Catalog does not match legacy schema")
        for table, expected in _BASE_COLUMNS.items():
            signature = _table_signature(db, table)
            if ({key: value[0] for key, value in signature[0].items()} != expected
                    or signature[1] != _PRIMARY_KEYS[table]):
                raise ValueError("Catalog columns/keys do not match legacy schema")
        # Preserve v1's historical path-uniqueness policy. Its rebuild below
        # replaces accepted legacy declarations with canonical comparisons.
        if not any(tuple(field[0] for field in fields) == ("current_path",) and not predicate
                   for fields, predicate in _table_signature(db, "assets")[3]):
            raise ValueError("Catalog asset path uniqueness is missing")
        return
    expected_tables, expected_triggers = _reference_signatures(version)
    if tables != set(expected_tables) or triggers != expected_triggers:
        raise ValueError("Catalog tables/triggers do not match supported schema")
    for table, expected in expected_tables.items():
        if _table_signature(db, table) != expected:
            raise ValueError(f"Catalog declarations do not match supported schema: {table}")


def _verify_integrity(db) -> None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Catalog integrity verification failed")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Catalog foreign-key verification failed")
    # Also check legacy provenance lacking a declared FK, without rewriting it.
    if db.execute("SELECT 1 FROM provenance LEFT JOIN assets USING(asset_id) "
                  "WHERE assets.asset_id IS NULL LIMIT 1").fetchone():
        raise ValueError("Catalog contains orphaned provenance")


def _verified_backup(path: Path, version: int) -> Path:
    backup = path.with_name(f"{path.name}.v{version}.{uuid.uuid4().hex}.backup.sqlite3")
    descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        reader = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            destination = sqlite3.connect(backup)
            try:
                reader.backup(destination)
            finally:
                destination.close()
        finally:
            reader.close()
        check = sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)
        try:
            if check.execute("PRAGMA user_version").fetchone()[0] != version:
                raise ValueError("Backup version differs from original catalog")
            _validate_catalog_schema(check, version)
            _verify_integrity(check)
        finally:
            check.close()
        return backup
    except BaseException:
        # Only this exclusively created, unverified output may be removed.
        backup.unlink(missing_ok=True)
        raise


def _migrate_one_to_two(db) -> None:
    # Canonicalize accepted legacy constraints without rewriting any row values.
    # Renaming preserves old FKs between the old tables until both are dropped.
    db.execute("ALTER TABLE provenance RENAME TO legacy_provenance")
    db.execute("ALTER TABLE assets RENAME TO legacy_assets")
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='index' "
                          "AND tbl_name IN ('legacy_assets','legacy_provenance') "
                          "AND sql IS NOT NULL").fetchall():
        quoted = row[0].replace('"', '""')
        db.execute(f'DROP INDEX "{quoted}"')
    _execute_schema(db, SCHEMA_V2)
    fields = ",".join(_BASE_COLUMNS["assets"])
    db.execute(f"INSERT INTO assets({fields}) SELECT {fields} FROM legacy_assets")
    fields = ",".join(_BASE_COLUMNS["provenance"])
    db.execute(f"INSERT INTO provenance({fields}) SELECT {fields} FROM legacy_provenance")
    db.execute("DROP TABLE legacy_provenance")
    db.execute("DROP TABLE legacy_assets")


def _migrate_two_to_three(db) -> None:
    _execute_schema(db, METADATA_SCHEMA)


def _migrate_three_to_four(db) -> None:
    _execute_schema(db, COLLECTIONS_SCHEMA)


def _migrate_four_to_five(db) -> None:
    _execute_schema(db, CURATION_SCHEMA)


def initialize(path: Path, *, create: bool = True) -> dict:
    """Create v5 or atomically upgrade; create=False never creates a catalog.

    Call before application workers/model connections open. BEGIN IMMEDIATE
    reserves the only writer while a separate read-only connection backs up the
    original state; no schema/data mutation precedes verified backup completion.
    """
    if type(create) is not bool:
        raise ValueError("create must be boolean")
    path = Path(path).resolve(strict=False)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path.as_uri() + ("?mode=rwc" if create else "?mode=rw"),
                         uri=True, isolation_level=None)
    backup = None
    upgrading = False
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            if not create or db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone():
                raise ValueError("Refusing to initialize an unversioned or unknown catalog")
            _execute_schema(db, SCHEMA)
        elif version in (1, 2, 3, 4, 5):
            _validate_catalog_schema(db, version)
            if version != SCHEMA_VERSION:
                upgrading = True
                backup = _verified_backup(path, version)
                if version == 1:
                    _migrate_one_to_two(db)
                if version <= 2:
                    _migrate_two_to_three(db)
                if version <= 3:
                    _migrate_three_to_four(db)
                _migrate_four_to_five(db)
            else:
                db.rollback()
                return {"schema_version": SCHEMA_VERSION, "previous_version": version,
                        "created": False, "migrated": False, "backup_path": None}
        else:
            raise ValueError("Refusing to initialize an unknown or newer database")
        _validate_catalog_schema(db, SCHEMA_VERSION)
        _verify_integrity(db)
        db.commit()
        return {"schema_version": SCHEMA_VERSION, "previous_version": version,
                "created": version == 0, "migrated": upgrading,
                "backup_path": str(backup) if backup is not None else None}
    except BaseException as exc:
        if db.in_transaction:
            db.rollback()
        if upgrading and isinstance(exc, Exception):
            raise CatalogMigrationError("Catalog upgrade failed; migration rolled back",
                                        backup_path=backup) from exc
        raise
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
    require_identity: bool = True,
) -> None:
    """Atomically update catalog and observation metadata for a proven rename."""
    old_path = Path(old_path).resolve(strict=False)
    new_path = Path(new_path).resolve(strict=True)
    if old_path.exists():
        raise ValueError("Rename source path reappeared before reconciliation")
    observed = new_path.stat()
    if (observed.st_size, observed.st_mtime_ns) != (byte_size, modified_ns):
        raise ValueError("Rename target changed before reconciliation")
    if require_identity and (str(observed.st_dev), str(observed.st_ino)) != (device, inode):
        raise ValueError("Rename target identity changed before reconciliation")
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
