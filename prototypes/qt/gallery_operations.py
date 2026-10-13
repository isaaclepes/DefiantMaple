"""Closed, module-level catalog operations for the GalleryWindow gateway.

The GUI submits data and operation names only.  No Qt object or callback crosses
the worker boundary; existing Core services retain their arguments and checks.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from defiantmaple import collections, curation, metadata, catalog, sources as source_api
from defiantmaple.catalog import connect
from defiantmaple.gallery_query import (count_first_page, later_page,
                                        rank_for_asset, detail_for_asset,
                                        lookup_taxonomy, lookup_sources)
from defiantmaple.private_eval import PrivateSelectionStore, assert_outside_sources
from prototypes.qt.gallery_filters import OperationSpec


def first_page(db, context, *args):
    return count_first_page(db, context, *args)


def page(db, context, *args):
    return later_page(db, context, *args)


def rank(db, context, *args):
    return rank_for_asset(db, context, *args)


def detail(db, context, *args):
    return detail_for_asset(db, context, *args)


def taxonomy(db, context, *args):
    return lookup_taxonomy(db, context, *args)


def sources(db, context, *args):
    return lookup_sources(db, context, *args)


_READ_SERVICES = {
    "list_sources": (source_api, "list_sources"),
    "list_collections": (collections, "list_collections"),
    "duplicates": (catalog, "duplicates"),
    "list_tags": (metadata, "list_tags"),
    "list_entities": (metadata, "list_entities"),
    "get_asset_metadata": (metadata, "get_asset_metadata"),
    "get_curation": (curation, "get_curation"),
    "list_curation_edits": (curation, "list_curation_edits"),
    "capture_curation": (curation, "capture_curation"),
    "preview_curation_batch": (curation, "preview_curation_batch"),
    "list_curation_batches": (curation, "list_curation_batches"),
    "get_curation_batch": (curation, "get_curation_batch"),
}

_WRITE_SERVICES = {
    "create_collection": (collections, "create_collection"),
    "rename_collection": (collections, "rename_collection"),
    "delete_collection": (collections, "delete_collection"),
    "add_member": (collections, "add_member"),
    "remove_member": (collections, "remove_member"),
    "move_member": (collections, "move_member"),
    "add_source": (source_api, "add_source"),
    "create_tag": (metadata, "create_tag"),
    "rename_tag": (metadata, "rename_tag"),
    "set_tag_parent": (metadata, "set_tag_parent"),
    "add_tag_alias": (metadata, "add_tag_alias"),
    "remove_tag_alias": (metadata, "remove_tag_alias"),
    "create_entity": (metadata, "create_entity"),
    "rename_entity": (metadata, "rename_entity"),
    "add_entity_alias": (metadata, "add_entity_alias"),
    "remove_entity_alias": (metadata, "remove_entity_alias"),
    "assign_tag": (metadata, "assign_tag"),
    "unassign_tag": (metadata, "unassign_tag"),
    "assign_entity": (metadata, "assign_entity"),
    "unassign_entity": (metadata, "unassign_entity"),
    "set_curation": (curation, "set_curation"),
    "undo_curation": (curation, "undo_curation"),
    "apply_curation_batch": (curation, "apply_curation_batch"),
    "undo_curation_batch": (curation, "undo_curation_batch"),
}


def legacy_read(database: Path, context, name: str, *args, **kwargs):
    """Opaque Core listings remain unbounded and use their own connections."""
    context.check()
    if name == "source_issues":
        source_id, = args
        with connect(database) as db:
            return [dict(row) for row in db.execute(
                "SELECT current_path,disposition,last_error FROM source_entries "
                "WHERE source_id=? AND disposition IN ('error','unsupported','missing') "
                "ORDER BY disposition,current_path LIMIT 100", (source_id,))]
    if name == "validate_source_roots":
        cache_root, private_root = args
        records = source_api.list_sources(database)
        for source in records:
            roots = [source["root_path"]]
            assert_outside_sources(database, roots)
            assert_outside_sources(cache_root, roots)
            assert_outside_sources(private_root, roots)
        return records
    module, attribute = _READ_SERVICES[name]
    return getattr(module, attribute)(database, *args, **kwargs)


def mutation(database: Path, _context, name: str, *args, **kwargs):
    """Serial dispatch; callers own intent invalidation and outcome reload."""
    if name == "review_state":
        asset_id, revision, state = args
        if state not in ("new", "needs_review", "reviewed", "organized", "ignored", "error"):
            raise ValueError("Unknown review state")
        with connect(database) as db:
            cursor = db.execute(
                "UPDATE assets SET workflow_state=? WHERE asset_id=? AND revision=?",
                (state, asset_id, revision))
            if cursor.rowcount != 1:
                raise ValueError("Captured review target changed; reload the gallery")
        return {"asset_id": asset_id, "state": state}
    if name == "private_select":
        private_path, asset_id, anonymous_id, role, rights, notes = args
        store = PrivateSelectionStore(private_path, database)
        return store.select(asset_id, anonymous_id, role, rights, notes)
    module, attribute = _WRITE_SERVICES[name]
    return getattr(module, attribute)(database, *args, **kwargs)


OPERATIONS = {
    "first": OperationSpec(False, first_page),
    "page": OperationSpec(False, page),
    "rank": OperationSpec(False, rank),
    "detail": OperationSpec(False, detail),
    "taxonomy": OperationSpec(False, taxonomy),
    "sources": OperationSpec(False, sources),
    "legacy": OperationSpec(False, legacy_read),
    "mutation": OperationSpec(True, mutation),
}
