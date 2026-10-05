"""Explicit catalog overrides and revision-checked single/group undo.

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


MAX_BATCH_TARGETS = 256


class KeepValue(Enum):
    KEEP = "keep"


KEEP = KeepValue.KEEP


@dataclass(frozen=True)
class CapturedTarget:
    asset_id: str
    revision: int

    def __post_init__(self):
        if type(self.asset_id) is not str or not self.asset_id:
            raise ValueError("Captured asset ID must be a nonempty string")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("Captured revision must be a nonnegative integer")


@dataclass(frozen=True)
class CurationChanges:
    """KEEP retains each member's value; None clears rating, False clears favorite."""

    rating: int | None | KeepValue = KEEP
    favorite: bool | KeepValue = KEEP

    def __post_init__(self):
        if self.rating is not KEEP:
            _rating(self.rating)
        if self.favorite is not KEEP and type(self.favorite) is not bool:
            raise ValueError("Favorite change must be Keep or boolean")


@dataclass(frozen=True)
class CurationBatchEffect:
    target: CapturedTarget
    captured_path: str
    before_rating: int | None
    before_favorite: bool
    after_rating: int | None
    after_favorite: bool

    @property
    def changed(self):
        return (self.before_rating, self.before_favorite) != (self.after_rating, self.after_favorite)


@dataclass(frozen=True)
class CurationBatchPlan:
    effects: tuple[CurationBatchEffect, ...]
    changes: CurationChanges

    @property
    def changed_count(self):
        return sum(effect.changed for effect in self.effects)


def _targets(values):
    if type(values) is not tuple or not 1 <= len(values) <= MAX_BATCH_TARGETS:
        raise ValueError(f"Capture between 1 and {MAX_BATCH_TARGETS} targets as a tuple")
    if any(type(target) is not CapturedTarget for target in values):
        raise ValueError("Every target must contain an asset ID and revision")
    if len({target.asset_id for target in values}) != len(values):
        raise ValueError("Duplicate captured asset IDs are not allowed")
    return values


def capture_curation(database: Path, asset_ids) -> tuple[CapturedTarget, ...]:
    """Explicitly reload revisions for fixed IDs, never recapture gallery selection."""
    if type(asset_ids) not in (tuple, list) or not 1 <= len(asset_ids) <= MAX_BATCH_TARGETS:
        raise ValueError(f"Capture between 1 and {MAX_BATCH_TARGETS} asset IDs")
    if any(type(asset_id) is not str or not asset_id for asset_id in asset_ids):
        raise ValueError("Captured asset IDs must be nonempty strings")
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Duplicate captured asset IDs are not allowed")
    with _transaction(database) as db:
        return tuple(CapturedTarget(asset_id, _state(db, asset_id)["revision"]) for asset_id in asset_ids)


def _effect(db, target, changes):
    before = _state(db, target.asset_id)
    if before["revision"] != target.revision:
        raise CurationConflict(f"Asset {target.asset_id} changed since capture. Reload the same targets and preview again.")
    path = db.execute("SELECT current_path FROM assets WHERE asset_id=?", (target.asset_id,)).fetchone()[0]
    return CurationBatchEffect(target, path, before["rating"], before["favorite"],
        before["rating"] if changes.rating is KEEP else changes.rating,
        before["favorite"] if changes.favorite is KEEP else changes.favorite)


def preview_curation_batch(database: Path, targets: tuple[CapturedTarget, ...],
                           changes: CurationChanges) -> CurationBatchPlan:
    """Read one snapshot and calculate immutable effects without catalog mutation."""
    _targets(targets)
    if type(changes) is not CurationChanges:
        raise ValueError("Bulk changes require CurationChanges")
    with _transaction(database) as db:
        return CurationBatchPlan(tuple(_effect(db, target, changes) for target in targets), changes)


def apply_curation_batch(database: Path, plan: CurationBatchPlan) -> dict:
    """Revalidate the complete preview, then atomically write all effects and history."""
    if type(plan) is not CurationBatchPlan or type(plan.effects) is not tuple:
        raise ValueError("Apply requires a captured effects preview")
    if any(type(effect) is not CurationBatchEffect for effect in plan.effects):
        raise ValueError("Invalid preview effects")
    targets = _targets(tuple(effect.target for effect in plan.effects))
    if type(plan.changes) is not CurationChanges:
        raise ValueError("Invalid preview changes")
    with _transaction(database, write=True) as db:
        current = tuple(_effect(db, target, plan.changes) for target in targets)
        if current != plan.effects:
            raise CurationConflict("Preview no longer matches the captured catalog state. Reload and preview again.")
        if not plan.changed_count:
            return {"changed": False, "batch_id": None, "target_count": len(targets), "changed_count": 0}
        batch_id = str(uuid.uuid4())
        db.execute("INSERT INTO curation_batches(batch_id,target_count,changed_count) VALUES(?,?,?)",
                   (batch_id, len(targets), plan.changed_count))
        for position, effect in enumerate(plan.effects):
            if effect.changed:
                db.execute("UPDATE assets SET rating=?,favorite=? WHERE asset_id=? AND revision=?",
                    (effect.after_rating, int(effect.after_favorite), effect.target.asset_id, effect.target.revision))
            resulting = _state(db, effect.target.asset_id)
            db.execute("INSERT INTO curation_batch_items(batch_id,asset_id,position,captured_path,"
                       "before_rating,before_favorite,after_rating,after_favorite,expected_revision) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                (batch_id, effect.target.asset_id, position, effect.captured_path, effect.before_rating,
                 int(effect.before_favorite), effect.after_rating, int(effect.after_favorite), resulting["revision"]))
        return {"changed": True, "batch_id": batch_id, "target_count": len(targets), "changed_count": plan.changed_count}


def list_curation_batches(database: Path, *, limit: int = 50) -> list[dict]:
    """Bounded global group history, independent of gallery selection or filters."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("History limit must be an integer from 1 to 100")
    with _transaction(database) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM curation_batches ORDER BY recorded_at DESC,rowid DESC LIMIT ?", (limit,))]


def _batch(db, batch_id):
    header = db.execute("SELECT * FROM curation_batches WHERE batch_id=?", (batch_id,)).fetchone()
    if header is None:
        raise ValueError("Unknown curation group")
    members = [dict(row) for row in db.execute(
        "SELECT * FROM curation_batch_items WHERE batch_id=? ORDER BY position", (batch_id,))]
    changed = sum((member["before_rating"], member["before_favorite"]) !=
                  (member["after_rating"], member["after_favorite"]) for member in members)
    if (len(members) != header["target_count"] or changed != header["changed_count"] or
            [member["position"] for member in members] != list(range(len(members)))):
        raise ValueError("Curation group journal is incomplete; undo refused")
    eligible = not header["undone"]
    for member in members:
        current = _state(db, member["asset_id"])
        member["current_revision"] = current["revision"]
        member["eligible"] = (current["revision"] == member["expected_revision"] and
            (current["rating"], int(current["favorite"])) == (member["after_rating"], member["after_favorite"]))
        eligible = eligible and member["eligible"]
    return {**dict(header), "members": members, "eligible": bool(eligible)}


def get_curation_batch(database: Path, batch_id: str) -> dict:
    """Inspect one exact group's complete effects and current undo eligibility."""
    with _transaction(database) as db:
        return _batch(db, batch_id)


def undo_curation_batch(database: Path, batch_id: str) -> dict:
    """Restore the entire stored group only when every resulting member still matches."""
    with _transaction(database, write=True) as db:
        batch = _batch(db, batch_id)
        if not batch["eligible"]:
            raise CurationConflict("Undo refused: group already undone or a captured member's content, path or catalog metadata changed.")
        for member in batch["members"]:
            if (member["before_rating"], member["before_favorite"]) != (member["after_rating"], member["after_favorite"]):
                db.execute("UPDATE assets SET rating=?,favorite=? WHERE asset_id=? AND revision=?",
                    (member["before_rating"], member["before_favorite"], member["asset_id"], member["expected_revision"]))
        db.execute("UPDATE curation_batches SET undone=1 WHERE batch_id=?", (batch_id,))
        return {"changed": True, "batch_id": batch_id, "target_count": batch["target_count"], "changed_count": batch["changed_count"]}
