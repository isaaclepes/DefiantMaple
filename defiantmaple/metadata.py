"""Explicit local tags/entities. Identity and assignments never depend on paths."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unicodedata
import uuid

from .catalog import connect


ENTITY_TYPES = ("Character", "Artist", "Project", "Location", "Client", "Franchise")


def _name(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError("Metadata name must be text")
    if any(unicodedata.category(char) == "Cc" and not char.isspace() for char in value):
        raise ValueError("Metadata name contains a control character")
    display = " ".join(unicodedata.normalize("NFC", value).split())
    if not display:
        raise ValueError("Metadata name must not be empty")
    return display, unicodedata.normalize("NFC", display.casefold())


def _entity_type(value: str) -> str:
    if value not in ENTITY_TYPES:
        raise ValueError("Unknown entity type")
    return value


@contextmanager
def _transaction(database: Path, *, write=False):
    with connect(database) as db:
        # Reserve writes before name/hierarchy validation, and keep reads of
        # records+aliases on one snapshot. No pragmas/durability settings change.
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
        except sqlite3.IntegrityError as exc:
            raise ValueError("Metadata name, hierarchy or reference constraint failed") from exc


def _record(db, kind: str, record_id: str) -> dict:
    table, key = ("tags", "tag_id") if kind == "tag" else ("entities", "entity_id")
    row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (record_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown {kind}")
    fields = ("tag_id", "name", "parent_id") if kind == "tag" else ("entity_id", "entity_type", "name")
    result = {field: row[field] for field in fields}
    result["aliases"] = [item[0] for item in db.execute(
        f"SELECT alias FROM {kind}_aliases WHERE {key}=? ORDER BY normalized_alias", (record_id,))]
    return result


def _records(db, kind: str, *, asset_id=None, entity_type=None) -> list[dict]:
    table, key = ("tags", "tag_id") if kind == "tag" else ("entities", "entity_id")
    clauses, values = [], []
    if asset_id is not None:
        assignments = "asset_tags" if kind == "tag" else "asset_entities"
        clauses.append(f"{key} IN (SELECT {key} FROM {assignments} WHERE asset_id=?)")
        values.append(asset_id)
    if entity_type is not None:
        clauses.append("entity_type=?")
        values.append(entity_type)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order = "normalized_name," + key if kind == "tag" else "entity_type,normalized_name," + key
    rows = db.execute(f"SELECT * FROM {table}{where} ORDER BY {order}", values).fetchall()
    aliases = {}
    # Two batched queries keep listing independent of the number of records.
    for row in db.execute(f"SELECT {key},alias FROM {kind}_aliases ORDER BY normalized_alias"):
        aliases.setdefault(row[key], []).append(row["alias"])
    fields = ("tag_id", "name", "parent_id") if kind == "tag" else ("entity_id", "entity_type", "name")
    return [{**{field: row[field] for field in fields}, "aliases": aliases.get(row[key], [])}
            for row in rows]


def _asset_metadata(db, asset_id: str) -> dict:
    if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (asset_id,)).fetchone() is None:
        raise ValueError("Unknown asset")
    return {"asset_id": asset_id, "tags": _records(db, "tag", asset_id=asset_id),
            "entities": _records(db, "entity", asset_id=asset_id)}


def create_tag(database: Path, name: str, *, parent_id: str | None = None) -> dict:
    display, normalized = _name(name)
    record_id = str(uuid.uuid4())
    with _transaction(database, write=True) as db:
        if parent_id is not None:
            _record(db, "tag", parent_id)
        db.execute("INSERT INTO tags(tag_id,name,normalized_name,parent_id) VALUES(?,?,?,?)",
                   (record_id, display, normalized, parent_id))
        return _record(db, "tag", record_id)


def get_tag(database: Path, tag_id: str) -> dict:
    with _transaction(database) as db:
        return _record(db, "tag", tag_id)


def rename_tag(database: Path, tag_id: str, name: str) -> dict:
    display, normalized = _name(name)
    with _transaction(database, write=True) as db:
        _record(db, "tag", tag_id)
        db.execute("UPDATE tags SET name=?,normalized_name=? WHERE tag_id=?",
                   (display, normalized, tag_id))
        return _record(db, "tag", tag_id)


def list_tags(database: Path) -> list[dict]:
    with _transaction(database) as db:
        return _records(db, "tag")


def set_tag_parent(database: Path, tag_id: str, parent_id: str | None) -> dict:
    with _transaction(database, write=True) as db:
        _record(db, "tag", tag_id)
        if parent_id is not None:
            _record(db, "tag", parent_id)
        # A schema trigger enforces descendant cycles as well as API callers.
        db.execute("UPDATE tags SET parent_id=? WHERE tag_id=?", (parent_id, tag_id))
        return _record(db, "tag", tag_id)


def _edit_alias(database: Path, kind: str, record_id: str, alias: str, *, remove=False) -> dict:
    display, normalized = _name(alias)
    key = "tag_id" if kind == "tag" else "entity_id"
    with _transaction(database, write=True) as db:
        record = _record(db, kind, record_id)
        if remove:
            db.execute(f"DELETE FROM {kind}_aliases WHERE {key}=? AND normalized_alias=?",
                       (record_id, normalized))
        else:
            if kind == "tag":
                previous = db.execute("SELECT tag_id FROM tag_aliases WHERE normalized_alias=?",
                                      (normalized,)).fetchone()
            else:
                previous = db.execute("SELECT entity_id FROM entity_aliases "
                                      "WHERE entity_type=? AND normalized_alias=?",
                                      (record["entity_type"], normalized)).fetchone()
            if previous is not None:
                if previous[0] != record_id:
                    raise ValueError("Alias already names another record")
                return record
            if kind == "tag":
                db.execute("INSERT INTO tag_aliases(tag_id,alias,normalized_alias) VALUES(?,?,?)",
                           (record_id, display, normalized))
            else:
                db.execute("INSERT INTO entity_aliases(entity_id,entity_type,alias,normalized_alias) "
                           "VALUES(?,?,?,?)", (record_id, record["entity_type"], display, normalized))
        return _record(db, kind, record_id)


def add_tag_alias(database: Path, tag_id: str, alias: str) -> dict:
    return _edit_alias(database, "tag", tag_id, alias)


def remove_tag_alias(database: Path, tag_id: str, alias: str) -> dict:
    return _edit_alias(database, "tag", tag_id, alias, remove=True)


def create_entity(database: Path, entity_type: str, name: str) -> dict:
    entity_type = _entity_type(entity_type)
    display, normalized = _name(name)
    record_id = str(uuid.uuid4())
    with _transaction(database, write=True) as db:
        db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) VALUES(?,?,?,?)",
                   (record_id, entity_type, display, normalized))
        return _record(db, "entity", record_id)


def get_entity(database: Path, entity_id: str) -> dict:
    with _transaction(database) as db:
        return _record(db, "entity", entity_id)


def rename_entity(database: Path, entity_id: str, name: str) -> dict:
    display, normalized = _name(name)
    with _transaction(database, write=True) as db:
        _record(db, "entity", entity_id)
        db.execute("UPDATE entities SET name=?,normalized_name=? WHERE entity_id=?",
                   (display, normalized, entity_id))
        return _record(db, "entity", entity_id)


def list_entities(database: Path, *, entity_type: str | None = None) -> list[dict]:
    if entity_type is not None:
        _entity_type(entity_type)
    with _transaction(database) as db:
        return _records(db, "entity", entity_type=entity_type)


def add_entity_alias(database: Path, entity_id: str, alias: str) -> dict:
    return _edit_alias(database, "entity", entity_id, alias)


def remove_entity_alias(database: Path, entity_id: str, alias: str) -> dict:
    return _edit_alias(database, "entity", entity_id, alias, remove=True)


def _assignment(database: Path, asset_id: str, kind: str, record_id: str, *, remove=False) -> dict:
    table, key = ("asset_tags", "tag_id") if kind == "tag" else ("asset_entities", "entity_id")
    with _transaction(database, write=True) as db:
        _record(db, kind, record_id)
        if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (asset_id,)).fetchone() is None:
            raise ValueError("Unknown asset")
        if remove:
            db.execute(f"DELETE FROM {table} WHERE asset_id=? AND {key}=?", (asset_id, record_id))
        else:
            db.execute(f"INSERT INTO {table}(asset_id,{key}) VALUES(?,?) "
                       f"ON CONFLICT(asset_id,{key}) DO NOTHING", (asset_id, record_id))
        return _asset_metadata(db, asset_id)


def assign_tag(database: Path, asset_id: str, tag_id: str) -> dict:
    return _assignment(database, asset_id, "tag", tag_id)


def unassign_tag(database: Path, asset_id: str, tag_id: str) -> dict:
    return _assignment(database, asset_id, "tag", tag_id, remove=True)


def assign_entity(database: Path, asset_id: str, entity_id: str) -> dict:
    return _assignment(database, asset_id, "entity", entity_id)


def unassign_entity(database: Path, asset_id: str, entity_id: str) -> dict:
    return _assignment(database, asset_id, "entity", entity_id, remove=True)


def get_asset_metadata(database: Path, asset_id: str) -> dict:
    with _transaction(database) as db:
        return _asset_metadata(db, asset_id)


def find_tag(database: Path, name: str) -> dict | None:
    _, normalized = _name(name)
    with _transaction(database) as db:
        row = db.execute("SELECT tag_id FROM tags WHERE normalized_name=? "
                         "UNION SELECT tag_id FROM tag_aliases WHERE normalized_alias=?",
                         (normalized, normalized)).fetchone()
        return _record(db, "tag", row[0]) if row is not None else None


def find_entity(database: Path, entity_type: str, name: str) -> dict | None:
    entity_type = _entity_type(entity_type)
    _, normalized = _name(name)
    with _transaction(database) as db:
        row = db.execute("SELECT entity_id FROM entities WHERE entity_type=? AND normalized_name=? "
                         "UNION SELECT entity_id FROM entity_aliases "
                         "WHERE entity_type=? AND normalized_alias=?",
                         (entity_type, normalized, entity_type, normalized)).fetchone()
        return _record(db, "entity", row[0]) if row is not None else None
