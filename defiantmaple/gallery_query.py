"""Immutable gallery predicates and bounded, snapshot-owned catalog reads.

The caller owns one established SQLite read transaction. In the Qt path that
owner is CatalogGateway: it executes the first SELECT before creating the
ReadContext, and closes the transaction after a handler returns. This module
never opens a connection or a transaction, and never reads source media.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
import sqlite3
import unicodedata
from typing import Any

from .curation import FavoriteFilter, RatingFilter, RatingMode
from .metadata import ENTITY_TYPES
from .catalog import require_current_catalog, is_restored_root_review_detail


PAGE_SIZE = 256
LOOKUP_SIZE = 64
DETAIL_LIST_SIZE = 64
MAX_ROW_TEXT_BYTES = 6_144
MAX_DETAIL_BYTES = 65_536
OVERFLOW_TEXT = "[unavailable: oversized catalog text]"
REVIEW_STATES = frozenset(("new", "needs_review", "reviewed", "organized", "ignored", "error"))
MEDIA_TYPES = frozenset(("image/png", "image/jpeg", "image/gif", "image/webp"))


class GalleryOrder(str, Enum):
    LIBRARY = "library"
    MANUAL_COLLECTION = "manual_collection"


class LookupKind(str, Enum):
    TAG = "tag"
    ENTITY = "entity"


class StaleFilter(ValueError):
    """A selected canonical catalog identity was deleted before Apply."""


class ViewChanged(ValueError):
    """A later operation no longer belongs to the published catalog view."""


class StaleTarget(ValueError):
    """A captured asset identity/revision is no longer in this view."""


def _optional_text(value: str | None, label: str, cap: int) -> None:
    if value is None:
        return
    if type(value) is not str or len(value) > cap:
        raise ValueError(f"{label} must be text of at most {cap} code points")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError(f"{label} contains a control character")


@dataclass(frozen=True)
class GalleryQuery:
    state: str | None = None
    source_id: str | None = None
    media_type: str | None = None
    tag_id: str | None = None
    entity_id: str | None = None
    rating: RatingFilter = RatingFilter()
    favorite: FavoriteFilter = FavoriteFilter.ALL
    path_text: str = ""
    duplicate_digest: str | None = None
    collection_id: str | None = None
    order: GalleryOrder = GalleryOrder.LIBRARY

    def __post_init__(self) -> None:
        if self.state is not None and (type(self.state) is not str or self.state not in REVIEW_STATES):
            raise ValueError("Unknown review state")
        if self.media_type is not None and (type(self.media_type) is not str
                                            or self.media_type not in MEDIA_TYPES):
            raise ValueError("Unknown gallery media type")
        for name in ("source_id", "tag_id", "entity_id", "collection_id"):
            _optional_text(getattr(self, name), name, 256)
            if getattr(self, name) == "":
                raise ValueError(f"{name} cannot be empty")
        _optional_text(self.duplicate_digest, "duplicate digest", 256)
        if self.duplicate_digest == "":
            raise ValueError("Duplicate digest cannot be empty")
        if type(self.rating) is not RatingFilter or type(self.favorite) is not FavoriteFilter:
            raise ValueError("Curation facets require typed filter values")
        _optional_text(self.path_text, "literal path", 512)
        if type(self.path_text) is not str:
            raise ValueError("Literal path must be text")
        object.__setattr__(self, "path_text", self.path_text.strip())
        if type(self.order) is not GalleryOrder:
            raise ValueError("Unknown gallery order")
        expected = (GalleryOrder.MANUAL_COLLECTION if self.collection_id is not None
                    else GalleryOrder.LIBRARY)
        if self.order is not expected:
            raise ValueError("Gallery order must match its collection base view")

    def clear_filters(self) -> GalleryQuery:
        """Clear every facet and digest, retaining the manual collection base."""
        return GalleryQuery(collection_id=self.collection_id, order=self.order)

    def with_facets(self, **changes: Any) -> GalleryQuery:
        """Apply selected facet changes; an untouched duplicate digest persists."""
        allowed = {"state", "source_id", "media_type", "tag_id", "entity_id", "rating",
                   "favorite", "path_text", "duplicate_digest"}
        if not set(changes) <= allowed:
            raise ValueError("Unknown or base-view gallery facet")
        return replace(self, **changes)


@dataclass(frozen=True)
class CompiledQuery:
    from_sql: str
    where_sql: str
    params: tuple[Any, ...]
    order_sql: str
    sort_sql: str


@dataclass(frozen=True)
class ViewToken:
    reader_incarnation: str
    file_identity: tuple[int, int]
    data_version: int
    generation: int
    query: GalleryQuery
    count: int


@dataclass(frozen=True)
class GalleryPage:
    token: ViewToken
    page: int
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GalleryFirstPage:
    token: ViewToken
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GalleryRank:
    token: ViewToken
    asset_id: str
    row: int | None


@dataclass(frozen=True)
class GalleryDetail:
    token: ViewToken
    asset_id: str
    revision: int
    value: dict[str, Any]
    incomplete: bool
    reason: str = ""


@dataclass(frozen=True)
class LookupPage:
    kind: str
    rows: tuple[dict[str, Any], ...]
    next_cursor: tuple[str, ...] | None
    incomplete: bool = False


def _literal_like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def compile_query(query: GalleryQuery) -> CompiledQuery:
    if type(query) is not GalleryQuery:
        raise TypeError("Expected a frozen GalleryQuery")
    clauses: list[str] = []
    params: list[Any] = []
    if query.collection_id is not None:
        from_sql = "assets JOIN collection_members AS members ON members.asset_id=assets.asset_id"
        clauses.append("members.collection_id=?")
        params.append(query.collection_id)
        sort_sql = "members.position"
    else:
        from_sql = "assets"
        sort_sql = "assets.discovered_at"
    for field, value in (("workflow_state", query.state), ("source_id", query.source_id),
                         ("media_type", query.media_type)):
        if value is not None:
            clauses.append(f"assets.{field}=?")
            params.append(value)
    if query.rating.mode is RatingMode.UNRATED:
        clauses.append("assets.rating IS NULL")
    elif query.rating.mode in (RatingMode.EXACT, RatingMode.AT_LEAST):
        clauses.append("assets.rating" + ("=?" if query.rating.mode is RatingMode.EXACT else ">=?"))
        params.append(query.rating.stars)
    if query.favorite is not FavoriteFilter.ALL:
        clauses.append("assets.favorite=?")
        params.append(int(query.favorite is FavoriteFilter.FAVORITES))
    if query.duplicate_digest is not None:
        clauses.append("assets.sha256=?")
        params.append(query.duplicate_digest)
    if query.path_text:
        clauses.append("assets.current_path LIKE ? ESCAPE '\\'")
        params.append(_literal_like(query.path_text))
    if query.tag_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM asset_tags AS at WHERE at.asset_id=assets.asset_id AND at.tag_id=?)")
        params.append(query.tag_id)
    if query.entity_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM asset_entities AS ae WHERE ae.asset_id=assets.asset_id AND ae.entity_id=?)")
        params.append(query.entity_id)
    return CompiledQuery(from_sql, " WHERE " + " AND ".join(clauses) if clauses else "",
                         tuple(params), sort_sql + ",assets.asset_id", sort_sql)


def _require_snapshot(db: sqlite3.Connection, context: Any) -> None:
    require_current_catalog(db)
    if not db.in_transaction:
        raise RuntimeError("Gallery query requires an established read transaction")
    if (type(context.data_version) is not int or
            type(context.file_identity) is not tuple or len(context.file_identity) != 2):
        raise TypeError("Gallery query requires gateway snapshot identity")
    context.check()


def _validate_selected(db: sqlite3.Connection, query: GalleryQuery) -> None:
    for table, column, value, label in (
        ("sources", "source_id", query.source_id, "source"),
        ("tags", "tag_id", query.tag_id, "tag"),
        ("entities", "entity_id", query.entity_id, "entity"),
        ("collections", "collection_id", query.collection_id, "collection"),
    ):
        if value is not None and db.execute(
            f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (value,),
        ).fetchone() is None:
            raise StaleFilter(f"Selected {label} no longer exists; choose it again")


_TEXT_FIELDS = (
    ("asset_id", "assets.asset_id", 256, 1_024),
    ("current_path", "assets.current_path", 1_024, 4_096),
    ("media_type", "assets.media_type", 256, 1_024),
    ("sha256", "assets.sha256", 256, 1_024),
    ("workflow_state", "assets.workflow_state", 256, 1_024),
    ("discovered_at", "assets.discovered_at", 256, 1_024),
    ("source_id", "assets.source_id", 256, 1_024),
    ("entry_disposition", "source_entries.disposition", 256, 1_024),
    ("entry_path", "source_entries.current_path", 1_024, 4_096),
    ("entry_source_id", "source_entries.source_id", 256, 1_024),
    ("source_health", "sources.health", 256, 1_024),
)


def _overflow_condition() -> str:
    total = "+".join(f"COALESCE(length(CAST({expression} AS BLOB)),0)"
                     for _, expression, _, _ in _TEXT_FIELDS)
    fields = [_field_overflow(expression, points, size)
              for _, expression, points, size in _TEXT_FIELDS]
    return f"(({total})>{MAX_ROW_TEXT_BYTES} OR " + " OR ".join(fields) + ")"


def _field_overflow(expression: str, points: int, size: int) -> str:
    return (f"(COALESCE(length({expression}),0)>{points} OR "
            f"COALESCE(length(CAST({expression} AS BLOB)),0)>{size} OR "
            f"COALESCE(instr({expression},char(0)),0)>0)")


def _guarded(expression: str, *, points: int, size: int) -> str:
    return (f"CASE WHEN {expression} IS NULL THEN NULL WHEN NOT "
            f"{_field_overflow(expression, points, size)} THEN {expression} "
            f"ELSE '{OVERFLOW_TEXT}' END")


def _page_sql(compiled: CompiledQuery, *, extra: str = "") -> str:
    overflow = _overflow_condition()
    columns = [f"CASE WHEN {expression} IS NULL THEN NULL WHEN {overflow} "
               f"THEN '{OVERFLOW_TEXT}' ELSE {expression} END AS {name}"
               for name, expression, _, _ in _TEXT_FIELDS]
    columns.extend((
        "assets.byte_size", "assets.rating", "assets.favorite", "assets.revision",
        "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id) AS linked_entry_count",
        "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id "
        "AND e.source_id=assets.source_id AND e.current_path=assets.current_path "
        "AND e.disposition='indexed') AS source_relation_count",
        f"CASE WHEN {overflow} THEN 1 ELSE 0 END AS overflow",
    ))
    return ("SELECT " + ",".join(columns) + " FROM " + compiled.from_sql + " "
            "LEFT JOIN source_entries ON source_entries.asset_id=assets.asset_id "
            "AND source_entries.current_path=assets.current_path "
            "AND source_entries.source_id=assets.source_id "
            "LEFT JOIN sources ON sources.source_id=assets.source_id" +
            compiled.where_sql + extra)


def _page_rows(db: sqlite3.Connection, compiled: CompiledQuery, page: int) -> tuple[dict[str, Any], ...]:
    if type(page) is not int or page < 0:
        raise ValueError("Gallery page must be a nonnegative integer")
    sql = _page_sql(compiled, extra=f" ORDER BY {compiled.order_sql} LIMIT ? OFFSET ?")
    rows = []
    for row in db.execute(sql, (*compiled.params, PAGE_SIZE, page * PAGE_SIZE)):
        item = dict(row)
        item["targetable"] = not bool(item["overflow"])
        rows.append(item)
    return tuple(rows)


def _token(context: Any, query: GalleryQuery, generation: int,
           reader_incarnation: str, count: int) -> ViewToken:
    if type(generation) is not int or generation < 0 or type(reader_incarnation) is not str or not reader_incarnation:
        raise ValueError("Gallery token needs a generation and reader incarnation")
    return ViewToken(reader_incarnation, context.file_identity, context.data_version,
                     generation, query, count)


def count_first_page(db: sqlite3.Connection, context: Any, query: GalleryQuery,
                     generation: int, reader_incarnation: str) -> GalleryFirstPage:
    """Validate selected identities and publish count plus page zero together."""
    _require_snapshot(db, context)
    compiled = compile_query(query)
    _validate_selected(db, query)
    count = db.execute("SELECT COUNT(*) FROM " + compiled.from_sql + compiled.where_sql,
                       compiled.params).fetchone()[0]
    context.check()
    rows = _page_rows(db, compiled, 0) if count else ()
    context.check()
    return GalleryFirstPage(_token(context, query, generation, reader_incarnation, count), rows)


def _current_view(db: sqlite3.Connection, context: Any, query: GalleryQuery,
                  token: ViewToken, reader_incarnation: str,
                  generation: int) -> CompiledQuery:
    _require_snapshot(db, context)
    if (type(token) is not ViewToken or token.reader_incarnation != reader_incarnation
            or token.file_identity != context.file_identity
            or token.data_version != context.data_version or token.query != query
            or token.generation != generation):
        raise ViewChanged("Gallery view changed; reload count and first page")
    return compile_query(query)


def later_page(db: sqlite3.Connection, context: Any, query: GalleryQuery,
               token: ViewToken, reader_incarnation: str, generation: int,
               page: int) -> GalleryPage:
    compiled = _current_view(db, context, query, token, reader_incarnation, generation)
    if type(page) is not int or page < 1 or page * PAGE_SIZE >= token.count:
        raise ValueError("Gallery later page is outside the published view")
    rows = _page_rows(db, compiled, page)
    context.check()
    return GalleryPage(token, page, rows)


def rank_for_asset(db: sqlite3.Connection, context: Any, query: GalleryQuery,
                   token: ViewToken, reader_incarnation: str, generation: int,
                   asset_id: str) -> GalleryRank:
    compiled = _current_view(db, context, query, token, reader_incarnation, generation)
    _optional_text(asset_id, "asset ID", 256)
    if not asset_id:
        raise ValueError("Asset ID is required")
    where = compiled.where_sql + (" AND " if compiled.where_sql else " WHERE ")
    target = (f"SELECT {compiled.sort_sql} AS sort_key,assets.asset_id AS target_id FROM "
              + compiled.from_sql + where + "assets.asset_id=?")
    preceding = ("SELECT COUNT(*) FROM " + compiled.from_sql + where +
                 f"({compiled.order_sql}) < (target.sort_key,target.target_id)")
    row = db.execute(f"SELECT ({preceding}) FROM ({target}) AS target",
                     (*compiled.params, *compiled.params, asset_id)).fetchone()
    context.check()
    return GalleryRank(token, asset_id, row[0] if row is not None else None)


def _limited_rows(db: sqlite3.Connection, sql: str, params: tuple[Any, ...],
                  text_fields: tuple[tuple[str, str, int, int], ...]) -> tuple[tuple[dict[str, Any], ...], bool]:
    projections = [f"{_guarded(expr, points=points, size=size)} AS {name}"
                   for name, expr, points, size in text_fields]
    condition = " OR ".join(_field_overflow(expr, points, size)
                            for _, expr, points, size in text_fields)
    projections.append(f"CASE WHEN {condition} THEN 1 ELSE 0 END AS _overflow")
    rows = [dict(row) for row in db.execute(sql.format(columns=",".join(projections)),
                                            (*params, DETAIL_LIST_SIZE + 1))]
    too_many = len(rows) > DETAIL_LIST_SIZE
    rows = rows[:DETAIL_LIST_SIZE]
    overflow = False
    for row in rows:
        overflow = bool(row.pop("_overflow")) or overflow
    return tuple(rows), too_many or overflow


def detail_for_asset(db: sqlite3.Connection, context: Any, query: GalleryQuery,
                     token: ViewToken, reader_incarnation: str, generation: int,
                     asset_id: str, revision: int) -> GalleryDetail:
    compiled = _current_view(db, context, query, token, reader_incarnation, generation)
    _optional_text(asset_id, "asset ID", 256)
    if not asset_id or type(revision) is not int or revision < 0:
        raise ValueError("Detail requires a captured asset ID and revision")
    where = compiled.where_sql + (" AND " if compiled.where_sql else " WHERE ")
    sql = _page_sql(compiled, extra=where[len(compiled.where_sql):] +
                    "assets.asset_id=? AND assets.revision=? LIMIT 1")
    selected = db.execute(sql, (*compiled.params, asset_id, revision)).fetchone()
    if selected is None:
        raise StaleTarget("Captured gallery target changed or left this view")
    asset = dict(selected)
    asset["targetable"] = not bool(asset["overflow"])
    if not asset["targetable"]:
        return GalleryDetail(token, asset_id, revision,
                             {"asset": asset, "source": None, "provenance": (),
                              "metadata": {"tags": (), "entities": ()}},
                             True, "Catalog detail contains oversized text")
    source = None
    if asset["source_id"] is not None:
        source_row = db.execute(
            "SELECT " + ",".join((
                f"{_guarded('name', points=256, size=1024)} AS name",
                f"{_guarded('root_path', points=1024, size=4096)} AS root_path",
                f"{_guarded('existing_file_policy', points=256, size=1024)} AS existing_file_policy",
                f"{_guarded('health', points=256, size=1024)} AS health",
                f"{_guarded('health_detail', points=1024, size=4096)} AS health_detail",
                "CASE WHEN " + " OR ".join((
                    _field_overflow("name", 256, 1024),
                    _field_overflow("root_path", 1024, 4096),
                    _field_overflow("existing_file_policy", 256, 1024),
                    _field_overflow("health", 256, 1024),
                    _field_overflow("health_detail", 1024, 4096),
                )) + " THEN 1 ELSE 0 END AS _overflow",
            )) + " FROM sources WHERE source_id=?", (asset["source_id"],)
        ).fetchone()
        source = dict(source_row) if source_row else None
        if (source is not None and is_restored_root_review_detail(
                source["health_detail"], asset["source_id"], source["root_path"])):
            source["health_detail"] = "Restored root requires explicit review before enable"
    source_incomplete = bool(source.pop("_overflow")) if source is not None else False
    provenance, prov_incomplete = _limited_rows(
        db, "SELECT {columns} FROM provenance WHERE asset_id=? ORDER BY recorded_at LIMIT ?",
        (asset_id,), (("source_kind", "source_kind", 256, 1_024),
                      ("details_json", "details_json", 1_024, 4_096),
                      ("recorded_at", "recorded_at", 256, 1_024)))
    tags, tags_incomplete = _limited_rows(
        db, "SELECT {columns} FROM asset_tags at JOIN tags t ON t.tag_id=at.tag_id "
        "WHERE at.asset_id=? ORDER BY t.normalized_name,t.tag_id LIMIT ?",
        (asset_id,), (("tag_id", "t.tag_id", 256, 1_024),
                      ("name", "t.name", 256, 1_024),
                      ("parent_id", "t.parent_id", 256, 1_024)))
    entities, entities_incomplete = _limited_rows(
        db, "SELECT {columns} FROM asset_entities ae JOIN entities e ON e.entity_id=ae.entity_id "
        "WHERE ae.asset_id=? ORDER BY e.normalized_name,e.entity_type,e.entity_id LIMIT ?",
        (asset_id,), (("entity_id", "e.entity_id", 256, 1_024),
                      ("entity_type", "e.entity_type", 256, 1_024),
                      ("name", "e.name", 256, 1_024)))
    tag_aliases, ta_incomplete = _limited_rows(
        db, "SELECT {columns} FROM asset_tags at JOIN tag_aliases ta ON ta.tag_id=at.tag_id "
        "WHERE at.asset_id=? ORDER BY ta.normalized_alias,ta.tag_id LIMIT ?",
        (asset_id,), (("tag_id", "ta.tag_id", 256, 1_024),
                      ("alias", "ta.alias", 256, 1_024)))
    entity_aliases, ea_incomplete = _limited_rows(
        db, "SELECT {columns} FROM asset_entities ae JOIN entity_aliases ea ON ea.entity_id=ae.entity_id "
        "WHERE ae.asset_id=? ORDER BY ea.normalized_alias,ea.entity_id LIMIT ?",
        (asset_id,), (("entity_id", "ea.entity_id", 256, 1_024),
                      ("alias", "ea.alias", 256, 1_024)))
    aliases_by_tag: dict[str, list[str]] = {}
    for item in tag_aliases:
        aliases_by_tag.setdefault(item["tag_id"], []).append(item["alias"])
    aliases_by_entity: dict[str, list[str]] = {}
    for item in entity_aliases:
        aliases_by_entity.setdefault(item["entity_id"], []).append(item["alias"])
    for item in tags:
        item["aliases"] = aliases_by_tag.get(item["tag_id"], [])
    for item in entities:
        item["aliases"] = aliases_by_entity.get(item["entity_id"], [])
    incomplete = any((prov_incomplete, tags_incomplete, entities_incomplete,
                      ta_incomplete, ea_incomplete, source_incomplete))
    value = {"asset": asset, "source": source, "provenance": provenance,
             "metadata": {"asset_id": asset_id, "tags": tags, "entities": entities}}
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_DETAIL_BYTES:
        return GalleryDetail(token, asset_id, revision,
                             {"asset": asset, "source": None, "provenance": (),
                              "metadata": {"tags": (), "entities": ()}},
                             True, "Catalog detail exceeds 64 KiB")
    context.check()
    return GalleryDetail(token, asset_id, revision, value, incomplete,
                         "Catalog detail has unavailable or excess records" if incomplete else "")


def normalize_lookup_text(value: str) -> str:
    if type(value) is not str or len(value) > 128:
        raise ValueError("Picker text must be at most 128 code points")
    if any(unicodedata.category(char) == "Cc" and not char.isspace() for char in value):
        raise ValueError("Picker text contains a control character")
    display = " ".join(unicodedata.normalize("NFC", value).split())
    return unicodedata.normalize("NFC", display.casefold())


def _prefix_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def lookup_taxonomy(db: sqlite3.Connection, context: Any, kind: LookupKind,
                    prefix: str, cursor: tuple[str, ...] | None = None,
                    entity_type: str | None = None) -> LookupPage:
    _require_snapshot(db, context)
    if type(kind) is not LookupKind:
        raise ValueError("Unknown taxonomy picker kind")
    normalized = normalize_lookup_text(prefix)
    if entity_type is not None and (kind is not LookupKind.ENTITY or entity_type not in ENTITY_TYPES):
        raise ValueError("Unknown picker entity category")
    if kind is LookupKind.TAG:
        expected = 2
        table, alias, key = "tags", "t", "tag_id"
        order = "t.normalized_name,t.tag_id"
        match = ("(t.normalized_name LIKE ? ESCAPE '\\' OR EXISTS "
                 "(SELECT 1 FROM tag_aliases ta WHERE ta.tag_id=t.tag_id "
                 "AND ta.normalized_alias LIKE ? ESCAPE '\\'))")
        fields = (("id", "t.tag_id", 256, 1_024), ("name", "t.name", 256, 1_024),
                  ("normalized_name", "t.normalized_name", 256, 1_024))
    else:
        expected = 3
        table, alias, key = "entities", "e", "entity_id"
        order = "e.normalized_name,e.entity_type,e.entity_id"
        match = ("(e.normalized_name LIKE ? ESCAPE '\\' OR EXISTS "
                 "(SELECT 1 FROM entity_aliases ea WHERE ea.entity_id=e.entity_id "
                 "AND ea.entity_type=e.entity_type "
                 "AND ea.normalized_alias LIKE ? ESCAPE '\\'))")
        fields = (("id", "e.entity_id", 256, 1_024), ("name", "e.name", 256, 1_024),
                  ("normalized_name", "e.normalized_name", 256, 1_024),
                  ("entity_type", "e.entity_type", 256, 1_024))
    if cursor is not None and (type(cursor) is not tuple or len(cursor) != expected
                               or any(type(part) is not str or len(part) > 256 for part in cursor)):
        raise ValueError("Invalid taxonomy cursor")
    pattern = _prefix_like(normalized)
    clauses = [match]
    params: list[Any] = [pattern, pattern]
    if entity_type is not None:
        clauses.append("e.entity_type=?")
        params.append(entity_type)
    if cursor is not None:
        clauses.append(f"({order}) > (" + ",".join("?" for _ in cursor) + ")")
        params.extend(cursor)
    projections = [f"{_guarded(expr, points=points, size=size)} AS {name}"
                   for name, expr, points, size in fields]
    projections.append("CASE WHEN " + " OR ".join(
        _field_overflow(expr, points, size) for _, expr, points, size in fields
    ) + " THEN 1 ELSE 0 END AS _overflow")
    sql = ("SELECT " + ",".join(projections) + f" FROM {table} {alias} WHERE " +
           " AND ".join(clauses) + f" ORDER BY {order} LIMIT ?")
    found = [dict(row) for row in db.execute(sql, (*params, LOOKUP_SIZE + 1))]
    context.check()
    page = found[:LOOKUP_SIZE]
    incomplete = False
    for item in page:
        unavailable = bool(item.pop("_overflow"))
        incomplete = unavailable or incomplete
        item["selectable"] = not unavailable
    last = page[-1] if page else None
    if kind is LookupKind.TAG:
        next_cursor = ((last["normalized_name"], last["id"])
                       if len(found) > LOOKUP_SIZE and last is not None and last["selectable"] else None)
    else:
        next_cursor = ((last["normalized_name"], last["entity_type"], last["id"])
                       if len(found) > LOOKUP_SIZE and last is not None and last["selectable"] else None)
    return LookupPage(kind.value, tuple(page), next_cursor, incomplete)


def lookup_sources(db: sqlite3.Connection, context: Any, prefix: str = "",
                   cursor: tuple[str, str] | None = None) -> LookupPage:
    _require_snapshot(db, context)
    _optional_text(prefix, "source picker text", 128)
    if type(prefix) is not str:
        raise ValueError("Source picker text must be text")
    if cursor is not None and (type(cursor) is not tuple or len(cursor) != 2
                               or any(type(part) is not str or len(part) > 256 for part in cursor)):
        raise ValueError("Invalid source cursor")
    clauses = ["name LIKE ? ESCAPE '\\'"]
    params: list[Any] = [_prefix_like(prefix.strip())]
    if cursor is not None:
        clauses.append("(name,source_id) > (?,?)")
        params.extend(cursor)
    sql = ("SELECT " + ",".join((
        f"{_guarded('source_id', points=256, size=1024)} AS id",
        f"{_guarded('name', points=256, size=1024)} AS name",
        f"{_guarded('health', points=256, size=1024)} AS health",
        "CASE WHEN " + " OR ".join((
            _field_overflow("source_id", 256, 1024),
            _field_overflow("name", 256, 1024),
            _field_overflow("health", 256, 1024),
        )) + " THEN 1 ELSE 0 END AS _overflow",
    )) + " FROM sources WHERE " + " AND ".join(clauses) +
           " ORDER BY name,source_id LIMIT ?")
    found = [dict(row) for row in db.execute(sql, (*params, LOOKUP_SIZE + 1))]
    context.check()
    page = found[:LOOKUP_SIZE]
    incomplete = False
    for item in page:
        unavailable = bool(item.pop("_overflow"))
        incomplete = unavailable or incomplete
        item["selectable"] = not unavailable
    last = page[-1] if page else None
    next_cursor = ((last["name"], last["id"])
                   if len(found) > LOOKUP_SIZE and last is not None and last["selectable"] else None)
    return LookupPage("source", tuple(page), next_cursor, incomplete)
