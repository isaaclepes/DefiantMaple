"""Manual collections reference catalog assets by ID and never open media."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid

from .catalog import connect
from .metadata import _name


_MAX_POSITION = (1 << 63) - 1


def _identifier(value: str, kind: str) -> None:
    # Existing legacy asset IDs remain valid; do not impose new UUID syntax.
    if not isinstance(value, str) or not value:
        raise ValueError(f"Unknown {kind}")


@contextmanager
def _transaction(database: Path, *, write=False):
    with connect(database) as db:
        # Lock before membership/name validation, including a captured neighbor.
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
        except sqlite3.IntegrityError as exc:
            raise ValueError("Collection name, membership or order constraint failed") from exc


def _record(db, collection_id: str) -> dict:
    _identifier(collection_id, "collection")
    row = db.execute("SELECT collection_id,name,(SELECT COUNT(*) FROM collection_members "
                     "WHERE collection_id=collections.collection_id) AS member_count "
                     "FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown collection")
    return dict(row)


def _asset(db, asset_id: str) -> None:
    _identifier(asset_id, "asset")
    if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (asset_id,)).fetchone() is None:
        raise ValueError("Unknown asset")


def _member_ids(db, collection_id: str) -> list[str]:
    return [row[0] for row in db.execute("SELECT asset_id FROM collection_members "
                                        "WHERE collection_id=? ORDER BY position,asset_id",
                                        (collection_id,))]


def create_collection(database: Path, name: str) -> dict:
    display, normalized = _name(name)
    collection_id = str(uuid.uuid4())
    with _transaction(database, write=True) as db:
        db.execute("INSERT INTO collections(collection_id,name,normalized_name) VALUES(?,?,?)",
                   (collection_id, display, normalized))
        return _record(db, collection_id)


def get_collection(database: Path, collection_id: str) -> dict:
    with _transaction(database) as db:
        return _record(db, collection_id)


def rename_collection(database: Path, collection_id: str, name: str) -> dict:
    display, normalized = _name(name)
    with _transaction(database, write=True) as db:
        _record(db, collection_id)
        db.execute("UPDATE collections SET name=?,normalized_name=? WHERE collection_id=?",
                   (display, normalized, collection_id))
        return _record(db, collection_id)


def list_collections(database: Path) -> list[dict]:
    with _transaction(database) as db:
        return [dict(row) for row in db.execute(
            "SELECT c.collection_id,c.name,COUNT(m.asset_id) AS member_count FROM collections c "
            "LEFT JOIN collection_members m ON m.collection_id=c.collection_id "
            "GROUP BY c.collection_id ORDER BY c.normalized_name,c.collection_id")]


def delete_collection(database: Path, collection_id: str) -> None:
    with _transaction(database, write=True) as db:
        _record(db, collection_id)
        db.execute("DELETE FROM collections WHERE collection_id=?", (collection_id,))


def list_members(database: Path, collection_id: str, *, limit: int | None = None,
                 offset: int = 0) -> list[str]:
    if limit is not None and (type(limit) is not int or not 1 <= limit <= _MAX_POSITION):
        raise ValueError("limit must be a positive integer or None")
    if type(offset) is not int or not 0 <= offset <= _MAX_POSITION:
        raise ValueError("offset must be a nonnegative integer")
    with _transaction(database) as db:
        _record(db, collection_id)
        return [row[0] for row in db.execute(
            "SELECT asset_id FROM collection_members WHERE collection_id=? "
            "ORDER BY position,asset_id LIMIT ? OFFSET ?",
            (collection_id, -1 if limit is None else limit, offset))]


def add_member(database: Path, collection_id: str, asset_id: str) -> dict:
    with _transaction(database, write=True) as db:
        collection = _record(db, collection_id)
        _asset(db, asset_id)
        if db.execute("SELECT 1 FROM collection_members WHERE collection_id=? AND asset_id=?",
                      (collection_id, asset_id)).fetchone():
            return collection
        maximum = db.execute("SELECT MAX(position) FROM collection_members WHERE collection_id=?",
                             (collection_id,)).fetchone()[0]
        if maximum == _MAX_POSITION:
            raise ValueError("Collection order exceeds supported range; reorder members first")
        position = 0 if maximum is None else maximum + 1
        db.execute("INSERT INTO collection_members(collection_id,asset_id,position) VALUES(?,?,?)",
                   (collection_id, asset_id, position))
        return _record(db, collection_id)


def remove_member(database: Path, collection_id: str, asset_id: str) -> dict:
    with _transaction(database, write=True) as db:
        _record(db, collection_id)
        _asset(db, asset_id)
        db.execute("DELETE FROM collection_members WHERE collection_id=? AND asset_id=?",
                   (collection_id, asset_id))
        return _record(db, collection_id)


def reorder_members(database: Path, collection_id: str, asset_ids: list[str]) -> dict:
    if not isinstance(asset_ids, (list, tuple)):
        raise ValueError("Reorder must supply a list or tuple of asset IDs")
    ordered = list(asset_ids)  # Capture caller input before waiting for the writer.
    for asset_id in ordered:
        _identifier(asset_id, "asset")
    if len(set(ordered)) != len(ordered):
        raise ValueError("Reorder must be an exact permutation of current members")
    with _transaction(database, write=True) as db:
        _record(db, collection_id)
        current = _member_ids(db, collection_id)
        if len(ordered) != len(current) or set(ordered) != set(current):
            raise ValueError("Reorder must be an exact permutation of current members")
        # A reserved transaction prevents a stale list from discarding a rival
        # add/remove. Delete+insert also avoids transient immediate UNIQUE clashes.
        db.execute("DELETE FROM collection_members WHERE collection_id=?", (collection_id,))
        db.executemany("INSERT INTO collection_members(collection_id,asset_id,position) VALUES(?,?,?)",
                       ((collection_id, asset_id, position) for position, asset_id in enumerate(ordered)))
        return _record(db, collection_id)


def move_member(database: Path, collection_id: str, asset_id: str, *, direction: int,
                expected_neighbor_id: str) -> dict:
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError("direction must be -1 or +1")
    with _transaction(database, write=True) as db:
        _record(db, collection_id)
        _asset(db, asset_id)
        _asset(db, expected_neighbor_id)
        member = db.execute("SELECT position FROM collection_members "
                            "WHERE collection_id=? AND asset_id=?",
                            (collection_id, asset_id)).fetchone()
        if member is None:
            raise ValueError("Asset is not a collection member")
        comparison, order = ("<", "DESC") if direction == -1 else (">", "ASC")
        neighbor = db.execute("SELECT asset_id,position FROM collection_members "
                              f"WHERE collection_id=? AND position{comparison}? "
                              f"ORDER BY position {order} LIMIT 1",
                              (collection_id, member["position"])).fetchone()
        if neighbor is None or neighbor["asset_id"] != expected_neighbor_id:
            raise ValueError("Collection boundary or stale captured neighbor")
        # Swap two rows rather than choosing a temporary position or rewriting
        # the collection. No other reader sees the intermediate deletion.
        db.execute("DELETE FROM collection_members WHERE collection_id=? AND asset_id IN (?,?)",
                   (collection_id, asset_id, expected_neighbor_id))
        db.executemany("INSERT INTO collection_members(collection_id,asset_id,position) VALUES(?,?,?)",
                       ((collection_id, asset_id, neighbor["position"]),
                        (collection_id, expected_neighbor_id, member["position"])))
        return _record(db, collection_id)
