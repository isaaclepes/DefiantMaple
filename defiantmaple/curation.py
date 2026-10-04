"""Explicit user catalog overrides and revision-checked single-asset undo.

Revisions track catalog-observed changes. A source change not yet scanned does
not advance them; these operations never write source files or undo file edits.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import uuid

from contextlib import contextmanager
import sqlite3

from .catalog import connect


@contextmanager
def _transaction(database: Path, *, write=False):
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Catalog curation constraint failed: {exc}") from exc


class CurationConflict(ValueError):
    """The captured state changed; reload before explicitly editing again."""


class RatingMode(Enum):
    ALL = "all"
    UNRATED = "unrated"
    EXACT = "exact"
    AT_LEAST = "at_least"


@dataclass(frozen=True)
class RatingFilter:
    mode: RatingMode = RatingMode.ALL
    stars: int | None = None

    def __post_init__(self):
        if not isinstance(self.mode, RatingMode):
            raise ValueError("Rating filter mode must be a RatingMode")
        if self.mode in (RatingMode.EXACT, RatingMode.AT_LEAST):
            _rating(self.stars)
            if self.stars is None:
                raise ValueError("A star filter requires 1–5 stars")
        elif self.stars is not None:
            raise ValueError("All/unrated filters do not accept stars")


class FavoriteFilter(Enum):
    ALL = "all"
    FAVORITES = "favorites"
    NOT_FAVORITES = "not_favorites"


def _rating(value):
    if value is not None and (type(value) is not int or not 1 <= value <= 5):
        raise ValueError("Rating must be unrated (None) or an integer from 1 to 5")


def _state(db, asset_id):
    row = db.execute("SELECT asset_id,rating,favorite,revision FROM assets WHERE asset_id=?",
                     (asset_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown asset")
    # Authority identifies the field policy, not authorship of default values.
    return {**dict(row), "favorite": bool(row["favorite"]), "authority": "catalog_user_managed"}


def get_curation(database: Path, asset_id: str) -> dict:
    with _transaction(database) as db:
        return _state(db, asset_id)


def set_curation(database: Path, asset_id: str, *, rating: int | None,
                 favorite: bool, expected_revision: int) -> dict:
    """Atomically edit a captured UUID; require the revision displayed to the user."""
    _rating(rating)
    if type(favorite) is not bool:
        raise ValueError("Favorite must be boolean")
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected revision must be a nonnegative integer")
    with _transaction(database, write=True) as db:
        before = _state(db, asset_id)
        if before["revision"] != expected_revision:
            raise CurationConflict("Asset changed since it was loaded. Reload current values before saving.")
        if (before["rating"], before["favorite"]) == (rating, favorite):
            return {**before, "changed": False, "edit_id": None}
        db.execute("UPDATE assets SET rating=?,favorite=? WHERE asset_id=? AND revision=?",
                   (rating, int(favorite), asset_id, expected_revision))
        after = _state(db, asset_id)
        edit_id = str(uuid.uuid4())
        db.execute("INSERT INTO curation_edits(edit_id,asset_id,before_rating,before_favorite,"
                   "after_rating,after_favorite,expected_revision) VALUES(?,?,?,?,?,?,?)",
                   (edit_id, asset_id, before["rating"], int(before["favorite"]), rating,
                    int(favorite), after["revision"]))
        return {**after, "changed": True, "edit_id": edit_id}


def list_curation_edits(database: Path, asset_id: str) -> list[dict]:
    """Durable newest-first history; undo availability remains checked at execution."""
    with _transaction(database) as db:
        _state(db, asset_id)
        return [dict(row) for row in db.execute(
            "SELECT * FROM curation_edits WHERE asset_id=? ORDER BY expected_revision DESC",
            (asset_id,))]


def undo_curation(database: Path, edit_id: str) -> dict:
    """Restore one edit only if its resulting asset revision still matches."""
    with _transaction(database, write=True) as db:
        edit = db.execute("SELECT * FROM curation_edits WHERE edit_id=?", (edit_id,)).fetchone()
        if edit is None:
            raise ValueError("Unknown curation edit")
        if edit["undone"]:
            raise CurationConflict("This catalog edit has already been undone.")
        current = _state(db, edit["asset_id"])
        if (current["revision"] != edit["expected_revision"] or
                (current["rating"], int(current["favorite"])) !=
                (edit["after_rating"], edit["after_favorite"])):
            raise CurationConflict("Undo refused: asset content, path or catalog metadata changed after this edit.")
        db.execute("UPDATE assets SET rating=?,favorite=? WHERE asset_id=? AND revision=?",
                   (edit["before_rating"], edit["before_favorite"], edit["asset_id"],
                    edit["expected_revision"]))
        db.execute("UPDATE curation_edits SET undone=1 WHERE edit_id=?", (edit_id,))
        return {**_state(db, edit["asset_id"]), "changed": True, "edit_id": edit_id}
