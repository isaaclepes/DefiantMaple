"""Scoped Qt/PySide6 gallery prototype for the DefiantMaple stack spike."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
import uuid
import ctypes
import hashlib
import json
import multiprocessing
import os
import platform
import queue
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
import weakref

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    qVersion,
)
from PySide6.QtGui import (QColor, QDragEnterEvent, QDropEvent, QIcon, QKeyEvent,
                           QKeySequence, QPainter, QPixmap, QImage, QShortcut)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid as qt_is_valid

from defiantmaple.admission import admission_session, current_session
from defiantmaple.catalog import require_current_catalog, connect, duplicates, initialize
from defiantmaple import curation
from defiantmaple.curation import RatingFilter, RatingMode, FavoriteFilter
from defiantmaple import collections as collection_api, metadata
from defiantmaple.private_eval import (PrivateSelectionStore, assert_library_locations,
                                       assert_outside_git, assert_outside_sources,
                                       default_private_root)
from defiantmaple.sources import add_source, list_sources, scan_sources
from defiantmaple.thumbnail import ThumbnailCancelled, ThumbnailLimits, thumbnail_for
from prototypes.qt.comparison import ComparisonDialog
from prototypes.qt.identity import APP_ID, app_icon
from prototypes.qt.preview import FullImageDialog
from prototypes.qt.recovery_qt import RecoveryDialog
from prototypes.qt.cached_preview import CachedPreviewDialog, CachedPreviewWorker, result_image, preview_text
from defiantmaple.cached_preview import (CachedResult, capture_target, read_cached_preview,
                                        generation_refusal, fresh_generation_refusal, availability_text)
from prototypes.qt.external_actions import ExternalActionsMixin, ExternalActionWorker
from defiantmaple import external_actions
from defiantmaple.gallery_query import (GalleryOrder, GalleryQuery, LookupKind,
                                       normalize_lookup_text)
from prototypes.qt.gallery_filters import CatalogGateway, CatalogRequest, CatalogReply, RequestClass
from prototypes.qt.gallery_operations import OPERATIONS


REVIEW_STATES = (
    "new",
    "needs_review",
    "reviewed",
    "organized",
    "ignored",
    "error",
)


class GalleryCatalogClient(QObject):
    """GUI-owned dispatch. Callbacks and widget references never enter the worker."""

    failed = Signal(str)

    def __init__(self, database: Path, parent=None):
        super().__init__(parent)
        self.admission_owner = current_session(database)
        self.gateway = CatalogGateway(database, OPERATIONS, self)
        self.gateway.completed.connect(self._completed)
        self.gateway.failed.connect(self.failed)
        self._next_id = 0
        self._callbacks = {}

    def start(self):
        self.gateway.start()

    def submit(self, category: RequestClass, operation: str, args=(), *, kwargs=None,
               context="", generation=0, callback=None, retain=()):
        if self.admission_owner is not None:
            try:
                self.admission_owner.validate()
            except ValueError as exc:
                return None, str(exc)
        request_id = self._next_id
        self._next_id += 1
        request = CatalogRequest(request_id, category, operation, tuple(args),
                                 tuple((kwargs or {}).items()), context, generation)
        if callback is not None:
            self._callbacks[request_id] = callback
        try:
            admission = self.gateway.submit(request, retain=retain)
        except Exception:
            self._callbacks.pop(request_id, None)
            raise
        if not admission.accepted:
            self._callbacks.pop(request_id, None)
            return None, admission.reason
        return request_id, ""

    def _completed(self, reply):
        callback = self._callbacks.pop(reply.request_id, None)
        acknowledgement = self.gateway.acknowledge_result(reply.request_id)
        try:
            if callback is not None:
                callback(reply)
        finally:
            # The GUI callback holds the returned lease until it has handled
            # the actual outcome, including after the originating dialog closes.
            for resource in acknowledgement.resources:
                release = getattr(resource, "cleanup", None) or getattr(resource, "close", None)
                if release is not None:
                    release()


class AssetModel(QAbstractListModel):
    """SQLite-backed, page-cached model; rows are fetched only when requested."""

    generationPublished = Signal(int)
    pagePublished = Signal(int, int)
    loadFailed = Signal(str)
    actionabilityChanged = Signal(bool)
    filterRestored = Signal(object)

    AssetRole = Qt.ItemDataRole.UserRole + 1
    page_size = 256
    max_cached_pages = 24

    def __init__(self, database: Path, parent=None, *, read_mode="synchronous",
                 catalog_client: GalleryCatalogClient | None = None):
        super().__init__(parent)
        database = Path(database).resolve(strict=True)
        self.database = database
        if read_mode not in ("synchronous", "async"):
            raise ValueError("Unknown gallery read mode")
        if read_mode == "async" and catalog_client is None:
            raise ValueError("Async gallery requires a catalog client")
        self.read_mode = read_mode
        self.catalog_client = catalog_client
        self._db = None
        if read_mode == "synchronous":
            uri = database.as_uri() + "?mode=rw"
            self._db = sqlite3.connect(uri, uri=True)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys=ON")
            try:
                require_current_catalog(self._db)
            except BaseException:
                self._db.close()
                raise
        self._filter: str | None = None
        self._source_filter: str | None = None
        self._type_filter: str | None = None
        self._tag_filter: str | None = None
        self._entity_filter: str | None = None
        self._search: str = ""
        self._duplicate_hash: str | None = None
        self._collection_id: str | None = None
        self._rating_filter = RatingFilter()
        self._favorite_filter = FavoriteFilter.ALL
        self._cache: OrderedDict[int, list[dict]] = OrderedDict()
        self._pending_pages = set()
        self._failed_pages = {}
        self._generation = 0
        self._token = None
        self._query = GalleryQuery()
        self._candidate_query = None
        self._has_published = False
        self.last_filter_error = ""
        self._actionable = read_mode == "synchronous"
        self._reader_incarnation = uuid.uuid4().hex
        self._count = self._query_count() if read_mode == "synchronous" else 0
        # The owning window starts the first read only after its registered
        # source-root containment check completes on the gateway.

    @property
    def active_filter(self) -> str | None:
        return self._filter

    @property
    def has_active_filters(self) -> bool:
        return bool(self._filter or self._source_filter or self._type_filter
                    or self._tag_filter or self._entity_filter
                    or self._search or self._duplicate_hash
                    or self._rating_filter.mode != RatingMode.ALL
                    or self._favorite_filter != FavoriteFilter.ALL)

    def _asset_tables(self) -> str:
        return ("assets JOIN collection_members AS members ON members.asset_id=assets.asset_id"
                if self._collection_id is not None else "assets")

    def _order_fields(self) -> tuple[str, str]:
        return ("members.position" if self._collection_id is not None else
                "assets.discovered_at", "assets.asset_id")

    def close(self):
        if self._db is not None:
            self._db.close()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else self._count

    def roleNames(self):  # noqa: N802 - Qt API
        return {self.AssetRole: b"asset"}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self._count:
            return None
        asset = self.asset_at(index.row()) if self.read_mode == "synchronous" else self.loaded_asset_at(index.row())
        if asset is None:
            if role == self.AssetRole:
                return None
            if role == Qt.ItemDataRole.DisplayRole:
                return ("Catalog page unavailable: " + self._failed_pages[index.row() // self.page_size]
                        if index.row() // self.page_size in self._failed_pages else "Loading catalog page…")
            return None
        if role == self.AssetRole:
            return asset
        if role == Qt.ItemDataRole.DisplayRole:
            rating = f"{asset['rating']} stars" if asset['rating'] is not None else "Unrated"
            favorite = " · Favorite" if asset["favorite"] else ""
            return f"{Path(asset['current_path']).name}\n{asset['workflow_state']} · {rating}{favorite}"
        if role == Qt.ItemDataRole.ToolTipRole:
            provider = getattr(self, "preview_provider", None)
            preview = provider(asset) if provider else availability_text(asset)
            return asset["current_path"] + "\n" + preview
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                f"{Path(asset['current_path']).name}, {asset['media_type']}, "
                f"state {asset['workflow_state']}, rating {asset['rating'] or 'unrated'}, "
                f"{'favorite' if asset['favorite'] else 'not favorite'}, "
                + availability_text(asset)
            )
        return None

    def flags(self, index):
        flags = super().flags(index)
        if self.read_mode == "async" and index.isValid():
            asset = self.loaded_asset_at(index.row())
            if not self._actionable or asset is None or not asset.get("targetable", False):
                return flags & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable
        return flags

    def loaded_asset_at(self, row: int):
        if self.read_mode == "async" and not self._actionable:
            return None
        if not 0 <= row < self._count:
            return None
        page = row // self.page_size
        cached = self._cache.get(page)
        if cached is None:
            if self.read_mode == "async":
                self.request_page(page)
            return None
        self._cache.move_to_end(page)
        offset = row % self.page_size
        return cached[offset] if offset < len(cached) else None

    def _where(self) -> tuple[str, tuple]:
        clauses = []
        params = []
        if self._collection_id is not None:
            clauses.append("members.collection_id=?")
            params.append(self._collection_id)
        if self._filter:
            clauses.append("assets.workflow_state=?")
            params.append(self._filter)
        if self._source_filter:
            clauses.append("assets.source_id=?")
            params.append(self._source_filter)
        if self._type_filter:
            clauses.append("assets.media_type=?")
            params.append(self._type_filter)
        if self._rating_filter.mode == RatingMode.UNRATED:
            clauses.append("assets.rating IS NULL")
        elif self._rating_filter.mode in (RatingMode.EXACT, RatingMode.AT_LEAST):
            comparator = "=" if self._rating_filter.mode == RatingMode.EXACT else ">="
            clauses.append(f"assets.rating{comparator}?")
            params.append(self._rating_filter.stars)
        if self._favorite_filter != FavoriteFilter.ALL:
            clauses.append("assets.favorite=?")
            params.append(int(self._favorite_filter == FavoriteFilter.FAVORITES))
        if self._duplicate_hash:
            clauses.append("assets.sha256=?")
            params.append(self._duplicate_hash)
        if self._search:
            clauses.append("assets.current_path LIKE ? ESCAPE '\\'")
            escaped = self._search.replace("\\", "\\\\").replace("%", "\\%")
            escaped = escaped.replace("_", "\\_")
            params.append(f"%{escaped}%")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), tuple(params)

    def _query_count(self) -> int:
        self._check_sync_catalog()
        where, params = self._where()
        return self._db.execute(
            "SELECT COUNT(*) FROM " + self._asset_tables() + where, params
        ).fetchone()[0]

    def _load_page(self, page: int) -> list[dict]:
        self._check_sync_catalog()
        cached = self._cache.get(page)
        if cached is not None:
            self._cache.move_to_end(page)
            return cached
        where, params = self._where()
        rows = [dict(row) for row in self._db.execute(
            "SELECT assets.asset_id,assets.current_path,assets.media_type,assets.sha256,"
            "assets.byte_size,assets.workflow_state,assets.discovered_at,assets.source_id,"
            "assets.rating,assets.favorite,assets.revision,"
            "source_entries.disposition AS entry_disposition,"
            "source_entries.current_path AS entry_path,source_entries.source_id AS entry_source_id,"
            "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id) AS linked_entry_count,"
            "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id "
            "AND e.source_id=assets.source_id AND e.current_path=assets.current_path "
            "AND e.disposition='indexed') AS source_relation_count,"
            "sources.health AS source_health FROM " + self._asset_tables() + " "
            "LEFT JOIN source_entries ON source_entries.asset_id=assets.asset_id "
            "AND source_entries.current_path=assets.current_path "
            "AND source_entries.source_id=assets.source_id "
            "LEFT JOIN sources ON sources.source_id=assets.source_id" + where +
            " ORDER BY " + ",".join(self._order_fields()) + " LIMIT ? OFFSET ?",
            (*params, self.page_size, page * self.page_size),
        )]
        self._cache[page] = rows
        self._cache.move_to_end(page)
        while len(self._cache) > self.max_cached_pages:
            self._cache.popitem(last=False)
        return rows

    def asset_at(self, row: int) -> dict:
        if not 0 <= row < self._count:
            raise IndexError(row)
        if self.read_mode == "async":
            asset = self.loaded_asset_at(row)
            if asset is None or not asset.get("targetable", False):
                raise ValueError("Gallery row is loading or unavailable")
            return asset
        page = row // self.page_size
        return self._load_page(page)[row % self.page_size]

    def set_filter(self, state: str | None):
        if state == "all":
            state = None
        if state is not None and state not in REVIEW_STATES:
            raise ValueError(f"Unknown review state: {state}")
        if state == self._filter:
            return
        self._filter = state
        self.refresh()

    def set_metadata_filters(self, *, source_id=None, media_type=None, search=""):
        previous = (self._source_filter, self._type_filter, self._search, self._duplicate_hash)
        self._source_filter = source_id
        self._type_filter = media_type
        self._search = search.strip()
        self._duplicate_hash = None
        try:
            self.refresh()
        except ValueError:
            (self._source_filter, self._type_filter,
             self._search, self._duplicate_hash) = previous
            raise

    def set_curation_filters(self, *, rating=RatingFilter(), favorite=FavoriteFilter.ALL):
        if not isinstance(rating, RatingFilter) or not isinstance(favorite, FavoriteFilter):
            raise ValueError("Curation filters require RatingFilter and FavoriteFilter values")
        self._rating_filter, self._favorite_filter = rating, favorite
        self.refresh()

    def set_duplicate_hash(self, digest: str | None):
        self._duplicate_hash = digest
        self.refresh()

    def set_collection(self, collection_id: str | None):
        if collection_id != self._collection_id:
            self._collection_id = collection_id
            self.refresh()

    def _request_fields_from(self, query: GalleryQuery):
        self._filter, self._source_filter = query.state, query.source_id
        self._type_filter, self._tag_filter = query.media_type, query.tag_id
        self._entity_filter = query.entity_id
        self._rating_filter, self._favorite_filter = query.rating, query.favorite
        self._search, self._duplicate_hash = query.path_text, query.duplicate_digest

    def apply_query(self, query: GalleryQuery, *, defer_until_write=False):
        """Submit one complete typed candidate; the published query changes on success."""
        if self.read_mode != "async" or type(query) is not GalleryQuery:
            raise ValueError("Gallery controls require an async typed query")
        if query.collection_id != self._collection_id:
            raise ValueError("Filter Apply cannot change the collection base")
        self._request_fields_from(query)
        if defer_until_write:
            # The window owns the active mutation. Its terminal callback must
            # refresh the latest request, after the gateway acknowledges it.
            self._generation += 1
            self._candidate_query = query
            self._actionable = False
            self.actionabilityChanged.emit(False)
            return "Catalog change pending; latest filter will apply after it finishes"
        return self.refresh()

    def row_for_asset(self, asset_id: str) -> int | None:
        """Find a visible UUID's row without fetching all preceding assets."""
        if self.read_mode == "async":
            raise RuntimeError("Use request_rank for an async gallery")
        self._check_sync_catalog()
        where, params = self._where()
        conjunction = " AND " if where else " WHERE "
        fields = ",".join(self._order_fields())
        target = f"SELECT {self._order_fields()[0]} AS sort_key,assets.asset_id AS target_id " + \
                 "FROM " + self._asset_tables() + where + conjunction + "assets.asset_id=?"
        preceding = "SELECT COUNT(*) FROM " + self._asset_tables() + where + conjunction + \
                    f"({fields}) < (target.sort_key,target.target_id)"
        # Target lookup and rank share one SQLite statement/read snapshot.
        row = self._db.execute(f"SELECT ({preceding}) FROM ({target}) AS target",
                               (*params, *params, asset_id)).fetchone()
        return row[0] if row is not None else None

    def refresh(self):
        if self.read_mode == "async":
            candidate = GalleryQuery(
                state=self._filter, source_id=self._source_filter,
                media_type=self._type_filter, tag_id=self._tag_filter,
                entity_id=self._entity_filter, rating=self._rating_filter,
                favorite=self._favorite_filter, path_text=self._search,
                duplicate_digest=self._duplicate_hash,
                collection_id=self._collection_id,
                order=(GalleryOrder.MANUAL_COLLECTION if self._collection_id is not None
                       else GalleryOrder.LIBRARY))
            self._generation += 1
            generation = self._generation
            self._candidate_query = candidate
            self._actionable = False
            self.actionabilityChanged.emit(False)
            if self._count:
                self.dataChanged.emit(self.index(0), self.index(self._count - 1))
            _, reason = self.catalog_client.submit(
                RequestClass.APPLY, "first",
                (candidate, generation, self._reader_incarnation),
                generation=generation, callback=self._first_reply)
            if reason:
                self._candidate_failed(reason)
            return reason
        self.beginResetModel()
        self._cache.clear()
        self._count = self._query_count()
        self.endResetModel()

    def invalidate_for_mutation(self):
        if self.read_mode != "async":
            return
        self._generation += 1
        self.beginResetModel()
        self._cache.clear()
        self._pending_pages.clear()
        self._failed_pages.clear()
        self._token = None
        self._count = 0
        self._actionable = False
        self._candidate_query = None
        self.endResetModel()
        self.actionabilityChanged.emit(False)

    def _candidate_failed(self, reason: str):
        self.last_filter_error = reason
        # A failed candidate must stop being the requested predicate before
        # another captured mutation can cancel the old-view restoration.
        self._request_fields_from(self._query)
        self._collection_id = self._query.collection_id
        self.loadFailed.emit(reason)
        if not self._has_published:
            return
        # A failed candidate never silently revives old action targets. Read
        # the prior predicate again and publish only a fresh successful view.
        generation = self._generation
        old_query = self._query
        _, refusal = self.catalog_client.submit(
            RequestClass.APPLY, "first",
            (old_query, generation, self._reader_incarnation),
            generation=generation, callback=self._restore_reply)
        if refusal:
            self.loadFailed.emit(refusal)

    def _restore_reply(self, reply):
        if reply.generation != self._generation:
            return
        if self._view_changed(reply.status):
            self._invalidate_changed_view(reply.status, reply.message or reply.status)
            return
        if reply.status != "ok":
            return
        first = reply.value
        if first.token.query != self._query:
            return
        old = self._query
        self._request_fields_from(old)
        self._collection_id = old.collection_id
        self._publish_first(first, reply, restored=True)
        self.filterRestored.emit(old)

    def _publish_first(self, first, reply, *, restored=False):
        if (first.token.generation != self._generation or
                first.token.data_version != reply.data_version or
                first.token.file_identity != reply.file_identity):
            self.loadFailed.emit("Gallery publication lost its snapshot identity")
            return
        self.beginResetModel()
        self._query = first.token.query
        self._has_published = True
        if not restored:
            self.last_filter_error = ""
        self._candidate_query = None
        self._token = first.token
        self._count = first.token.count
        self._cache.clear()
        self._pending_pages.clear()
        self._failed_pages.clear()
        if first.rows:
            self._cache[0] = list(first.rows)
        self._actionable = True
        self.endResetModel()
        self.actionabilityChanged.emit(True)
        self.generationPublished.emit(self._generation)

    def _first_reply(self, reply):
        if reply.generation != self._generation:
            return
        if reply.status != "ok":
            if self._view_changed(reply.status):
                self._invalidate_changed_view(reply.status, reply.message or reply.status)
                return
            if reply.status not in ("superseded", "cancelled"):
                self._candidate_failed(reply.message or reply.status)
            return
        first = reply.value
        if (first.token.generation != self._generation or
                first.token.query != self._candidate_query):
            self._candidate_failed("Gallery publication lost its candidate")
            return
        self._publish_first(first, reply)

    def request_page(self, page: int):
        if (self.read_mode != "async" or not self._actionable or self._token is None
                or page in self._cache or page in self._pending_pages or page in self._failed_pages):
            return
        generation, token, query = self._generation, self._token, self._query
        self._pending_pages.add(page)
        def received(reply):
            if generation != self._generation or token != self._token:
                return
            self._pending_pages.discard(page)
            if reply.status != "ok":
                if self._view_changed(reply.status):
                    self._invalidate_changed_view(reply.status, reply.message)
                    return
                self._failed_pages[page] = reply.message or reply.status
                self.loadFailed.emit(self._failed_pages[page])
                start = page * self.page_size
                self.dataChanged.emit(self.index(start), self.index(min(self._count - 1, start + self.page_size - 1)))
                return
            value = reply.value
            if value.token != token:
                self._invalidate_changed_view("view_changed", "Catalog view changed while loading a page")
                return
            if page != 0 and value.page != page:
                reason = "Gallery page changed during delivery"
                self._failed_pages[page] = reason
                self.loadFailed.emit(reason)
                start = page * self.page_size
                self.dataChanged.emit(self.index(start), self.index(min(self._count - 1, start + self.page_size - 1)))
                return
            self._cache[page] = list(value.rows)
            self._cache.move_to_end(page)
            while len(self._cache) > self.max_cached_pages:
                self._cache.popitem(last=False)
            start = page * self.page_size
            end = min(self._count - 1, start + len(value.rows) - 1)
            if end >= start:
                self.dataChanged.emit(self.index(start), self.index(end))
            self.pagePublished.emit(generation, page)
        operation = "first" if page == 0 else "page"
        args = ((query, generation, self._reader_incarnation) if page == 0 else
                (query, token, self._reader_incarnation, generation, page))
        _, reason = self.catalog_client.submit(
            RequestClass.PAGE, operation, args, context=f"page:{page}",
            generation=generation, callback=received)
        if reason:
            self._pending_pages.discard(page)
            self._failed_pages[page] = reason
            self.loadFailed.emit(reason)

    @staticmethod
    def _view_changed(status: str) -> bool:
        return status in ("view_changed", "catalog_replaced", "catalog_unavailable")

    def _invalidate_changed_view(self, status: str, message: str):
        self.invalidate_for_mutation()
        self.loadFailed.emit(message)
        if status == "view_changed" or status == "stale_target":
            self.refresh()

    def request_rank(self, asset_id: str, callback):
        if self._token is None:
            callback(None, "Gallery view is loading")
            return
        generation, token, query = self._generation, self._token, self._query
        def received(reply):
            if generation != self._generation or token != self._token:
                return
            if reply.status != "ok":
                if self._view_changed(reply.status):
                    self._invalidate_changed_view(reply.status, reply.message)
                callback(None, reply.message or reply.status)
                return
            callback(reply.value.row, "")
        _, reason = self.catalog_client.submit(RequestClass.RANK, "rank",
            (query, token, self._reader_incarnation, generation, asset_id),
            generation=generation, callback=received)
        if reason:
            callback(None, reason)

    def request_detail(self, asset: dict, callback):
        if self._token is None or not asset.get("targetable", False):
            callback(None, "Gallery target is unavailable")
            return
        generation, token, query = self._generation, self._token, self._query
        asset_id, revision = asset["asset_id"], asset["revision"]
        def received(reply):
            if generation != self._generation or token != self._token:
                return
            if reply.status != "ok":
                if self._view_changed(reply.status) or reply.status == "stale_target":
                    self._invalidate_changed_view(reply.status, reply.message)
                callback(None, reply.message or reply.status)
                return
            value = reply.value
            if value.asset_id != asset_id or value.revision != revision:
                callback(None, "Captured detail target changed")
                return
            callback(value, "")
        _, reason = self.catalog_client.submit(RequestClass.DETAIL, "detail",
            (query, token, self._reader_incarnation, generation, asset_id, revision),
            generation=generation, callback=received)
        if reason:
            callback(None, reason)

    def details_for(self, asset_id: str) -> dict:
        if self.read_mode == "async":
            raise RuntimeError("Use request_detail for an async gallery")
        self._check_sync_catalog()
        asset = self._db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        if asset is None:
            raise ValueError("Unknown asset")
        source = (self._db.execute(
            "SELECT name,root_path,existing_file_policy,health,health_detail "
            "FROM sources WHERE source_id=?", (asset["source_id"],),
        ).fetchone() if asset["source_id"] else None)
        provenance = [dict(row) for row in self._db.execute(
            "SELECT source_kind,details_json,recorded_at FROM provenance "
            "WHERE asset_id=? ORDER BY recorded_at", (asset_id,),
        )]
        return {"asset": dict(asset), "source": dict(source) if source else None,
                "provenance": provenance,
                "metadata": metadata.get_asset_metadata(self.database, asset_id)}

    def _check_sync_catalog(self):
        if self._db is not None:
            require_current_catalog(self._db)

    def update_state(self, row: int, state: str):
        if self.read_mode == "async":
            raise RuntimeError("Use the window-owned catalog mutation for an async gallery")
        self._check_sync_catalog()
        if state not in REVIEW_STATES:
            raise ValueError(f"Unknown review state: {state}")
        asset = self.asset_at(row)
        with self._db:
            self._db.execute(
                "UPDATE assets SET workflow_state=? WHERE asset_id=?",
                (state, asset["asset_id"]),
            )
        if self._filter and self._filter != state:
            self.beginResetModel()
            self._cache.clear()
            self._count = self._query_count()
            self.endResetModel()
            return
        page = row // self.page_size
        if page in self._cache:
            self._cache[page][row % self.page_size]["workflow_state"] = state
        changed = self.index(row)
        self.dataChanged.emit(changed, changed, [
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.AccessibleTextRole,
            self.AssetRole,
        ])


class MetadataTaxonomyPanel(QWidget):
    """Canonical taxonomy controls; writes always use the backend API."""

    def __init__(self, editor, kind: str):
        super().__init__(editor)
        self.editor = editor
        self.kind = kind
        self.id_field = "tag_id" if kind == "tag" else "entity_id"
        self.records = []
        self.list = QListWidget()
        self.list.setAccessibleName(f"{kind.title()} canonical records")
        self.list.currentItemChanged.connect(self._selected)
        self.name = QLineEdit()
        self.name.setAccessibleName(f"{kind.title()} canonical name")
        self.name.setPlaceholderText("Canonical name")
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(self.create_record)
        self.rename_button = QPushButton("Rename selected")
        self.rename_button.clicked.connect(self.rename_record)
        self.aliases = QListWidget()
        self.aliases.setAccessibleName(f"{kind.title()} aliases")
        self.aliases.currentItemChanged.connect(self._update_buttons)
        self.alias = QLineEdit()
        self.alias.setAccessibleName(f"New {kind} alias")
        self.alias.setPlaceholderText("Alias")
        self.add_alias_button = QPushButton("Add alias")
        self.add_alias_button.clicked.connect(self.add_alias)
        self.remove_alias_button = QPushButton("Remove selected alias")
        self.remove_alias_button.clicked.connect(self.remove_alias)
        self.assign_button = QPushButton(f"Assign selected {kind}")
        self.assign_button.clicked.connect(lambda: self.set_assignment(True))
        self.unassign_button = QPushButton(f"Unassign selected {kind}")
        self.unassign_button.clicked.connect(lambda: self.set_assignment(False))
        layout = QVBoxLayout(self)
        if kind == "entity":
            self.entity_type = QComboBox()
            self.entity_type.addItems(metadata.ENTITY_TYPES)
            self.entity_type.setAccessibleName("Entity type")
            self.entity_type.currentIndexChanged.connect(self.refresh)
            layout.addWidget(self.entity_type)
        layout.addWidget(self.list, 2)
        layout.addWidget(self.name)
        names = QHBoxLayout()
        names.addWidget(self.create_button)
        names.addWidget(self.rename_button)
        layout.addLayout(names)
        if kind == "tag":
            self.parent_box = QComboBox()
            self.parent_box.setAccessibleName("Selected tag parent")
            self.parent_button = QPushButton("Set or clear parent")
            self.parent_button.clicked.connect(self.set_parent)
            parents = QHBoxLayout()
            parents.addWidget(self.parent_box, 1)
            parents.addWidget(self.parent_button)
            layout.addLayout(parents)
        layout.addWidget(QLabel("Aliases"))
        layout.addWidget(self.aliases, 1)
        layout.addWidget(self.alias)
        aliases = QHBoxLayout()
        aliases.addWidget(self.add_alias_button)
        aliases.addWidget(self.remove_alias_button)
        layout.addLayout(aliases)
        assignments = QHBoxLayout()
        assignments.addWidget(self.assign_button)
        assignments.addWidget(self.unassign_button)
        layout.addLayout(assignments)

    def selected_record(self):
        item = self.list.currentItem()
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((record for record in self.records
                     if record[self.id_field] == identifier), None)

    def refresh(self, *_args):
        selected = self.selected_record()
        identifier = selected[self.id_field] if selected else None
        if self.editor.catalog_window is not None:
            name = "list_tags" if self.kind == "tag" else "list_entities"
            kwargs = {} if self.kind == "tag" else {"entity_type": self.entity_type.currentText()}
            self.editor.catalog_window._legacy(
                f"metadata:{id(self)}", name, kwargs=kwargs,
                callback=lambda records: self._publish_records(records, identifier),
                on_error=lambda error: self.editor.feedback.setText(error), owner=self.editor,
                suppress_expected_cancellation=True)
            return
        database = self.editor.database
        records = (metadata.list_tags(database) if self.kind == "tag" else
                   metadata.list_entities(database, entity_type=self.entity_type.currentText()))
        self._publish_records(records, identifier)

    def _publish_records(self, records, identifier):
        identifier = getattr(self, "_desired_id", None) or identifier
        self._desired_id = None
        self.records = records
        assigned = {record[self.id_field] for record in
                    self.editor.asset_metadata["tags" if self.kind == "tag" else "entities"]}
        self.list.blockSignals(True)
        self.list.clear()
        selected_row = -1
        for row, record in enumerate(self.records):
            label = record["name"] + (" · assigned" if record[self.id_field] in assigned else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, record[self.id_field])
            self.list.addItem(item)
            if record[self.id_field] == identifier:
                selected_row = row
        if self.records:
            self.list.setCurrentRow(max(0, selected_row))
        self.list.blockSignals(False)
        self._selected()

    def _selected(self, *_args):
        record = self.selected_record()
        self.name.setText(record["name"] if record else "")
        self.aliases.clear()
        if record:
            self.aliases.addItems(record["aliases"])
        if self.kind == "tag":
            self.parent_box.clear()
            self.parent_box.addItem("No parent", None)
            for candidate in self.records:
                if record is None or candidate["tag_id"] != record["tag_id"]:
                    self.parent_box.addItem(candidate["name"], candidate["tag_id"])
            if record:
                index = self.parent_box.findData(record["parent_id"])
                self.parent_box.setCurrentIndex(max(0, index))
        self._update_buttons()

    def _update_buttons(self, *_args):
        selected = self.selected_record() is not None
        self.rename_button.setEnabled(selected)
        self.add_alias_button.setEnabled(selected)
        self.remove_alias_button.setEnabled(selected and self.aliases.currentItem() is not None)
        if self.kind == "tag":
            self.parent_button.setEnabled(selected)
        enabled = selected and self.editor.asset_id is not None
        self.assign_button.setEnabled(enabled)
        self.unassign_button.setEnabled(enabled)

    def _write(self, function, *args, after=None):
        if self.editor.catalog_window is not None:
            window = self.editor.catalog_window
            focus = window._capture_metadata_focus()
            def received(reply):
                # The gallery owns the write even when this editor closes.
                window._metadata_focus_after_write(focus, reply)
                if not self.editor.isVisible():
                    return
                if reply.status not in ("ok", "completed_no_payload"):
                    self.editor.feedback.setText(reply.message or reply.status)
                    return
                self.editor.refresh()
                self.editor.changed.emit()
                self.editor.feedback.setText("Catalog metadata saved.")
                if after is not None and reply.status == "ok":
                    after(reply.value)
            window._mutate_catalog(function.__name__, args, callback=received)
            return None
        try:
            result = function(self.editor.database, *args)
            self.editor.refresh()
            self.editor.changed.emit()
            self.editor.feedback.setText("Catalog metadata saved.")
            return result
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.editor.feedback.setText(str(exc))
            return None

    def create_record(self):
        if self.kind == "tag":
            result = self._write(metadata.create_tag, self.name.text(),
                                 after=lambda record: self.select_id(record[self.id_field]))
        else:
            result = self._write(metadata.create_entity, self.entity_type.currentText(), self.name.text(),
                                 after=lambda record: self.select_id(record[self.id_field]))
        if result:
            self.select_id(result[self.id_field])

    def select_id(self, identifier: str):
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                self.list.setCurrentRow(row)
                return
        self._desired_id = identifier

    def rename_record(self):
        record = self.selected_record()
        if record:
            self._write(getattr(metadata, f"rename_{self.kind}"), record[self.id_field], self.name.text())

    def add_alias(self):
        record = self.selected_record()
        if record:
            if self._write(getattr(metadata, f"add_{self.kind}_alias"), record[self.id_field], self.alias.text()):
                self.alias.clear()

    def remove_alias(self):
        record, alias = self.selected_record(), self.aliases.currentItem()
        if record and alias:
            self._write(getattr(metadata, f"remove_{self.kind}_alias"), record[self.id_field], alias.text())

    def set_parent(self):
        record = self.selected_record()
        if record:
            self._write(metadata.set_tag_parent, record["tag_id"], self.parent_box.currentData())

    def set_assignment(self, assigned: bool):
        record = self.selected_record()
        if self.editor.asset_id is not None and record:
            operation = "assign" if assigned else "unassign"
            self._write(getattr(metadata, f"{operation}_{self.kind}"),
                        self.editor.asset_id, record[self.id_field])


class MetadataEditor(QDialog):
    """The edit target is captured once; selection changes cannot retarget writes."""

    changed = Signal()

    def __init__(self, database: Path, asset_id: str | None = None,
                 asset_label: str | None = None, parent=None, *, catalog_window=None):
        super().__init__(parent)
        self.database = Path(database)
        self.catalog_window = catalog_window
        self._catalog_closed = False
        self.asset_id = asset_id
        self.asset_metadata = {"asset_id": asset_id, "tags": [], "entities": []}
        self.setWindowTitle("Tags and entities")
        self.resize(620, 660)
        self.target = QLabel(f"Assignment target: {asset_label or asset_id}\nID: {asset_id}" if asset_id else
                             "No asset selected. Create and edit taxonomy here; select an asset to assign it.")
        self.target.setWordWrap(True)
        self.target.setAccessibleName("Captured metadata assignment target")
        self.assigned = QLabel()
        self.assigned.setWordWrap(True)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setAccessibleName("Metadata edit result")
        self.tags = MetadataTaxonomyPanel(self, "tag")
        self.entities = MetadataTaxonomyPanel(self, "entity")
        tabs = QTabWidget()
        tabs.addTab(self.tags, "Tags")
        tabs.addTab(self.entities, "Entities")
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.target)
        layout.addWidget(self.assigned)
        layout.addWidget(tabs, 1)
        layout.addWidget(self.feedback)
        layout.addWidget(close)
        self.refresh()

    def refresh(self):
        if self.catalog_window is not None and self.asset_id is not None:
            self.catalog_window._legacy(
                f"metadata-asset:{id(self)}", "get_asset_metadata", (self.asset_id,),
                callback=self._publish_asset_metadata,
                on_error=lambda error: self.feedback.setText(error), owner=self,
                suppress_expected_cancellation=True)
            return
        self.asset_metadata = (metadata.get_asset_metadata(self.database, self.asset_id)
                               if self.asset_id is not None else
                               {"asset_id": None, "tags": [], "entities": []})
        self._publish_asset_metadata(self.asset_metadata)

    def _publish_asset_metadata(self, value):
        self.asset_metadata = value
        tags = ", ".join(record["name"] for record in self.asset_metadata["tags"]) or "None"
        entities = ", ".join(f"{record['entity_type']}: {record['name']}"
                             for record in self.asset_metadata["entities"]) or "None"
        self.assigned.setText(f"Assigned tags: {tags}\nAssigned entities: {entities}")
        self.tags.refresh()
        self.entities.refresh()

    def closeEvent(self, event):
        self._catalog_closed = True
        super().closeEvent(event)


class CurationFilterBox(QComboBox):
    """Qt opaque Python objects need value comparison for typed filter lookup."""

    def findData(self, data, role=Qt.ItemDataRole.UserRole,
                 flags=Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive):
        for index in range(self.count()):
            if self.itemData(index, role) == data:
                return index
        return -1


class CurationDialog(QDialog):
    """A captured UUID and revision remain fixed until an explicit reload/save."""

    saved = Signal(str)

    def __init__(self, database: Path, asset_id: str, asset_label: str | None = None,
                 parent=None, *, catalog_window=None):
        super().__init__(parent)
        self.database = Path(database)
        self.catalog_window = catalog_window
        self._catalog_closed = False
        self._asset_id = asset_id
        self.state = {}
        self._reload_serial = 0
        self._focus_continuation = None
        self.setWindowTitle("Rating and favorite")
        self.resize(480, 360)
        self.target = QLabel(f"Editing: {asset_label or asset_id}\nID: {asset_id}")
        self.target.setWordWrap(True)
        self.target.setAccessibleName("Captured rating and favorite target")
        self.current = QLabel()
        self.current.setWordWrap(True)
        self.current.setAccessibleName("Current rating and favorite")
        self.rating_box = QComboBox()
        self.rating_box.setObjectName("curationRating")
        self.rating_box.setAccessibleName("Asset star rating")
        self.rating_box.addItem("Unrated", None)
        for stars in range(1, 6):
            self.rating_box.addItem(f"{stars} star{'s' if stars != 1 else ''}", stars)
        self.favorite_box = QCheckBox("Favorite")
        self.favorite_box.setObjectName("curationFavorite")
        self.favorite_box.setAccessibleName("Asset favorite independent of rating")
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setAccessibleName("Rating and favorite edit result")
        self.save_button = QPushButton("Save rating and favorite")
        self.save_button.setObjectName("curationSave")
        self.save_button.clicked.connect(self.save)
        self.undo_button = QPushButton("Undo latest rating/favorite edit")
        self.undo_button.setObjectName("curationUndo")
        self.undo_button.clicked.connect(self.undo)
        self.reload_button = QPushButton("Reload current values")
        self.reload_button.setObjectName("curationReload")
        self.reload_button.clicked.connect(self.reload)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        for widget in (self.target, self.current, QLabel("Rating"), self.rating_box,
                       self.favorite_box, self.save_button, self.undo_button,
                       self.reload_button, self.feedback, close):
            layout.addWidget(widget)
        self.reload()
        self.rating_box.setFocus()

    @property
    def asset_id(self):
        return self._asset_id

    def reload(self, *, outcome=None):
        if self.catalog_window is not None:
            self._reload_serial += 1
            serial = self._reload_serial
            self.save_button.setEnabled(False)
            self.undo_button.setEnabled(False)
            self.feedback.setText(outcome or "Loading current catalog values…")
            self.catalog_window._legacy(f"curation-values:{id(self)}", "get_curation",
                (self.asset_id,), callback=lambda state: self._load_edits(state, serial, outcome),
                on_error=lambda error: self._reload_error(error, serial, outcome), owner=self)
            return False
        try:
            self.state = curation.get_curation(self.database, self.asset_id)
            edits = curation.list_curation_edits(self.database, self.asset_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Current values could not be loaded: {exc}")
            self.save_button.setEnabled(False)
            self.undo_button.setEnabled(False)
            return False
        return self._publish_curation(self.state, edits)

    def _load_edits(self, state, serial, outcome):
        if serial != self._reload_serial:
            return
        self.catalog_window._legacy(f"curation-edits:{id(self)}", "list_curation_edits",
            (self.asset_id,), callback=lambda edits: self._publish_curation(state, edits, serial, outcome),
            on_error=lambda error: self._reload_error(error, serial, outcome), owner=self)

    def _reload_error(self, error, serial=None, outcome=None):
        if serial is not None and serial != self._reload_serial:
            return
        self.feedback.setText((f"{outcome} " if outcome else "") +
                              f"Current values could not be loaded: {error}")
        self.save_button.setEnabled(False)
        self.undo_button.setEnabled(False)

    def _publish_curation(self, state, edits, serial=None, outcome=None):
        if serial is not None and serial != self._reload_serial:
            return False
        self.state = state
        self.rating_box.setCurrentIndex(self.rating_box.findData(self.state["rating"]))
        self.favorite_box.setChecked(self.state["favorite"])
        rating = f"{self.state['rating']} stars" if self.state["rating"] is not None else "Unrated"
        favorite = "Favorite" if self.state["favorite"] else "Not favorite"
        self.current.setText(f"Current: {rating} · {favorite}\nRating and favorite are managed in this catalog; scans do not set them.")
        latest = next((edit for edit in edits if not edit["undone"]), None)
        self.undo_edit_id = latest["edit_id"] if latest else None
        eligible = bool(latest and latest["expected_revision"] == self.state["revision"] and
                        (latest["after_rating"], bool(latest["after_favorite"])) ==
                        (self.state["rating"], self.state["favorite"]))
        self.undo_button.setEnabled(eligible)
        self.undo_button.setToolTip("Undo the latest unchanged catalog edit" if eligible else
                                   "No edit remains safe to undo at the current asset revision")
        if latest and not eligible:
            self.current.setText(self.current.text() + "\nUndo unavailable: catalog changes intervened.")
        self.save_button.setEnabled(True)
        self.feedback.setText(outcome or "Current catalog values loaded.")
        return True

    def save(self):
        if self.catalog_window is not None:
            if "revision" not in self.state:
                self.feedback.setText("Current values are still loading.")
                return
            self.save_button.setEnabled(False)
            self._focus_continuation = self.catalog_window._capture_curation_focus()
            def received(reply):
                if not self.isVisible():
                    return
                if reply.status == "refused":
                    self.save_button.setEnabled(True)
                    self.feedback.setText(reply.message)
                    return
                if reply.status != "ok":
                    if reply.status in ("catalog_replaced", "catalog_unavailable"):
                        self.feedback.setText(f"Rating and favorite were not saved: {reply.message or reply.status}")
                        return
                    self.reload(outcome=f"Rating and favorite outcome unknown; reload required: "
                                        f"{reply.message or reply.status}")
                    return
                self.reload(outcome="Rating and favorite saved to catalog." if reply.value["changed"] else
                                    "No changes to save.")
                if reply.value["changed"]:
                    self.saved.emit(self.asset_id)
            self.catalog_window._mutate_catalog("set_curation", (self.asset_id,),
                kwargs={"rating": self.rating_box.currentData(),
                        "favorite": self.favorite_box.isChecked(),
                        "expected_revision": self.state["revision"]}, callback=received)
            return
        try:
            result = curation.set_curation(self.database, self.asset_id,
                rating=self.rating_box.currentData(), favorite=self.favorite_box.isChecked(),
                expected_revision=self.state["revision"])
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Rating and favorite were not saved: {exc}")
            return
        self.reload()
        self.feedback.setText("Rating and favorite saved to catalog." if result["changed"] else
                              "No changes to save.")
        if result["changed"]:
            self.saved.emit(self.asset_id)

    def undo(self):
        if self.undo_edit_id is None:
            return
        if self.catalog_window is not None:
            edit_id = self.undo_edit_id
            self.undo_button.setEnabled(False)
            self._focus_continuation = self.catalog_window._capture_curation_focus()
            def received(reply):
                if not self.isVisible():
                    return
                if reply.status == "refused":
                    self.undo_button.setEnabled(True)
                    self.feedback.setText(reply.message)
                    return
                if reply.status in ("catalog_replaced", "catalog_unavailable"):
                    self.feedback.setText(f"Catalog undo was not applied: {reply.message or reply.status}")
                    return
                self.reload(outcome="Latest rating/favorite edit undone in catalog." if reply.status == "ok"
                                    else f"Catalog undo outcome unknown; reload required: {reply.message or reply.status}")
                if reply.status == "ok":
                    self.saved.emit(self.asset_id)
            self.catalog_window._mutate_catalog("undo_curation", (edit_id,), callback=received)
            return
        try:
            curation.undo_curation(self.database, self.undo_edit_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Catalog undo was not applied: {exc}")
            return
        self.reload()
        self.feedback.setText("Latest rating/favorite edit undone in catalog.")
        self.saved.emit(self.asset_id)

    def closeEvent(self, event):
        self._catalog_closed = True
        super().closeEvent(event)


class BulkCurationDialog(QDialog):
    """Frozen selected identities; explicit preview/apply and separately targeted group undo."""

    saved = Signal(str)

    def __init__(self, database: Path, targets: tuple, parent=None, *, history_only=False,
                 catalog_window=None):
        super().__init__(parent)
        if not history_only:
            curation._targets(targets)
        self.database = Path(database)
        self.catalog_window = catalog_window
        self._catalog_closed = False
        self._targets = targets
        self.history_only = history_only
        self.plan = None
        self.undo_batch_id = None
        self.setWindowTitle("Bulk group history and undo" if history_only else "Bulk rating and favorite")
        self.resize(740, 760)
        self.target = QLabel()
        self.target.setWordWrap(True)
        self.target.setAccessibleName("Captured bulk targets and revisions")
        self.target_list = QPlainTextEdit()
        self.target_list.setReadOnly(True)
        self.target_list.setMaximumHeight(90)
        self.target_list.setAccessibleName("Scrollable captured asset IDs and revisions")
        self.rating_box = QComboBox()
        self.rating_box.setObjectName("bulkCurationRating")
        self.rating_box.setAccessibleName("Bulk rating change")
        self.rating_box.addItem("Keep each rating", curation.KEEP)
        self.rating_box.addItem("Set Unrated", None)
        for stars in range(1, 6):
            self.rating_box.addItem(f"Set {stars} stars", stars)
        self.favorite_box = QComboBox()
        self.favorite_box.setObjectName("bulkCurationFavorite")
        self.favorite_box.setAccessibleName("Bulk favorite change")
        for label, value in (("Keep each favorite", curation.KEEP), ("Set Favorite", True),
                             ("Set Not favorite", False)):
            self.favorite_box.addItem(label, value)
        self.preview_button = QPushButton("Preview effects on captured targets")
        self.preview_button.setObjectName("bulkCurationPreview")
        self.preview_button.clicked.connect(self.preview)
        self.apply_button = QPushButton("Apply preview to entire captured group")
        self.apply_button.setObjectName("bulkCurationApply")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        self.reload_button = QPushButton("Reload same captured IDs")
        self.reload_button.setObjectName("bulkCurationReload")
        self.reload_button.clicked.connect(self.reload)
        self.effects = QPlainTextEdit()
        self.effects.setReadOnly(True)
        self.effects.setAccessibleName("Bulk effects preview before and after values")
        self.feedback = QLabel("Choose changes, then preview the captured targets.")
        self.feedback.setWordWrap(True)
        self.feedback.setAccessibleName("Bulk rating and favorite result")
        self.group_box = QComboBox()
        self.group_box.setObjectName("bulkCurationHistory")
        self.group_box.setAccessibleName("Recent durable catalog groups independent of selection")
        self._group_choice_epoch = 0
        self.group_box.currentIndexChanged.connect(self._group_selected)
        self.group_effects = QPlainTextEdit()
        self.group_effects.setReadOnly(True)
        self.group_effects.setAccessibleName("Selected whole group undo effects")
        self.undo_button = QPushButton("Undo entire displayed group")
        self.undo_button.setObjectName("bulkCurationUndo")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_group)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        for widget in (self.target, self.target_list, QLabel("Rating change"), self.rating_box,
                       QLabel("Favorite change"), self.favorite_box, self.preview_button,
                       self.effects, self.apply_button, self.reload_button, self.feedback,
                       QLabel("Recent groups (up to 50; may include other assets)"), self.group_box,
                       self.group_effects, self.undo_button, close):
            layout.addWidget(widget)
        self.rating_box.currentIndexChanged.connect(self.invalidate_preview)
        self.favorite_box.currentIndexChanged.connect(self.invalidate_preview)
        if history_only:
            for widget in (self.rating_box, self.favorite_box, self.preview_button, self.apply_button,
                           self.reload_button, self.effects, self.target_list):
                widget.setVisible(False)
            self.feedback.setText("Choose one recorded group, inspect all its members, then undo the entire group.")
        self._show_targets()
        self.refresh_history()
        (self.group_box if history_only else self.rating_box).setFocus()

    @property
    def targets(self):
        return self._targets

    def _show_targets(self):
        self.target.setText("Inspect one exact recorded group. Undo affects its whole membership." if self.history_only else
                            f"{len(self.targets)} captured assets. Selection changes do not change these targets.")
        self.target_list.setPlainText("\n".join(f"{target.asset_id} (revision {target.revision})" for target in self.targets))

    @staticmethod
    def _values(rating, favorite):
        return f"{'Unrated' if rating is None else str(rating) + ' stars'}, {'Favorite' if favorite else 'Not favorite'}"

    def invalidate_preview(self, *_args):
        self.plan = None
        self.apply_button.setEnabled(False)
        self.effects.clear()
        self.feedback.setText("Preview required for the current choices and captured revisions.")

    def preview(self):
        self.invalidate_preview()
        if self.catalog_window is not None:
            changes = curation.CurationChanges(self.rating_box.currentData(),
                                               self.favorite_box.currentData())
            self.catalog_window._legacy(f"bulk-preview:{id(self)}", "preview_curation_batch",
                (self.targets, changes), callback=self._publish_plan,
                on_error=lambda error: self.feedback.setText(f"Preview refused: {error}"), owner=self)
            return
        try:
            self.plan = curation.preview_curation_batch(self.database, self.targets,
                curation.CurationChanges(self.rating_box.currentData(), self.favorite_box.currentData()))
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Preview refused: {exc}")
            return
        self._publish_plan(self.plan)

    def _publish_plan(self, plan):
        self.plan = plan
        lines = [f"{len(self.targets)} targets: {self.plan.changed_count} changed, "
                 f"{len(self.targets) - self.plan.changed_count} unchanged. Catalog only."]
        for effect in self.plan.effects:
            lines.append(f"{Path(effect.captured_path).name} | ID: {effect.target.asset_id} | revision {effect.target.revision}\n"
                         f"  {self._values(effect.before_rating, effect.before_favorite)} → "
                         f"{self._values(effect.after_rating, effect.after_favorite)}"
                         + (" [unchanged]" if not effect.changed else ""))
        self.effects.setPlainText("\n".join(lines))
        self.apply_button.setEnabled(True)
        self.feedback.setText("Preview ready. Apply rechecks every captured member before any edit.")

    def apply(self):
        if self.plan is None:
            return
        if self.catalog_window is not None:
            plan = self.plan
            self.apply_button.setEnabled(False)
            def received(reply):
                if not self.isVisible():
                    return
                if reply.status == "refused":
                    self.apply_button.setEnabled(True)
                    self.feedback.setText(reply.message)
                    return
                if reply.status != "ok":
                    self.invalidate_preview()
                    self.feedback.setText(f"Entire group outcome requires reload: {reply.message or reply.status}")
                    return
                self._publish_apply(reply.value)
            self.catalog_window._mutate_catalog("apply_curation_batch", (plan,), callback=received)
            return
        try:
            result = curation.apply_curation_batch(self.database, self.plan)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.invalidate_preview()
            self.feedback.setText(f"Entire group was not applied: {exc}")
            return
        self._publish_apply(result)

    def _publish_apply(self, result):
        self.plan = None
        self.apply_button.setEnabled(False)
        self.effects.setPlainText(("Applied preview:\n" if result["changed"] else "Completed without changes:\n")
                                 + self.effects.toPlainText())
        self.refresh_history(result["batch_id"])
        self.feedback.setText(f"Group saved to catalog: {result['changed_count']} changed, "
                              f"{result['target_count'] - result['changed_count']} unchanged."
                              if result["changed"] else "No changes; no group journal or revisions created.")
        if result["changed"]:
            self.saved.emit(result["batch_id"])

    def reload(self):
        self.invalidate_preview()
        if self.catalog_window is not None:
            ids = tuple(target.asset_id for target in self.targets)
            self.catalog_window._legacy(f"bulk-capture:{id(self)}", "capture_curation", (ids,),
                callback=self._publish_targets,
                on_error=lambda error: self.feedback.setText(f"Same captured targets could not be reloaded: {error}"),
                owner=self)
            return
        try:
            self._targets = curation.capture_curation(self.database, tuple(target.asset_id for target in self.targets))
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Same captured targets could not be reloaded: {exc}")
            return
        self._publish_targets(self._targets)

    def _publish_targets(self, targets):
        self._targets = targets
        self._show_targets()
        self.refresh_history()
        self.feedback.setText("Same captured IDs reloaded. Preview again before applying.")

    def refresh_history(self, selected_id=None):
        selected_id = selected_id or self.group_box.currentData()
        choice_epoch = self._group_choice_epoch
        if self.catalog_window is not None:
            self.catalog_window._legacy(f"bulk-history:{id(self)}", "list_curation_batches",
                callback=lambda groups: self._publish_history(groups, selected_id, choice_epoch),
                on_error=lambda error: self.feedback.setText(f"Group history could not be loaded: {error}"),
                owner=self)
            return
        try:
            groups = curation.list_curation_batches(self.database)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Group history could not be loaded: {exc}")
            return
        self._publish_history(groups, selected_id, choice_epoch)

    def _publish_history(self, groups, selected_id, choice_epoch):
        if choice_epoch != self._group_choice_epoch:
            selected_id = self.group_box.currentData()
        self.group_box.blockSignals(True)
        self.group_box.clear()
        self.group_box.addItem("Choose one exact group to inspect", None)
        for group in groups:
            self.group_box.addItem(f"{group['recorded_at']} · {group['changed_count']}/{group['target_count']} changed · "
                                   f"{'undone' if group['undone'] else 'recorded'} · {group['batch_id']}", group["batch_id"])
        self.group_box.setCurrentIndex(max(0, self.group_box.findData(selected_id)))
        self.group_box.blockSignals(False)
        self.load_group()

    def _group_selected(self, *_args):
        self._group_choice_epoch += 1
        self.load_group()

    def load_group(self, *_args):
        self.undo_batch_id = None
        self.undo_button.setEnabled(False)
        self.group_effects.clear()
        batch_id = self.group_box.currentData()
        if batch_id is None:
            return
        if self.catalog_window is not None:
            self.catalog_window._legacy(f"bulk-group:{id(self)}", "get_curation_batch", (batch_id,),
                callback=lambda group: self._publish_group(batch_id, group),
                on_error=lambda error: self.group_effects.setPlainText(f"Group could not be loaded: {error}"),
                owner=self)
            return
        try:
            group = curation.get_curation_batch(self.database, batch_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.group_effects.setPlainText(f"Group could not be loaded: {exc}")
            return
        self._publish_group(batch_id, group)

    def _publish_group(self, batch_id, group):
        if batch_id != self.group_box.currentData():
            return
        self.undo_batch_id = batch_id
        lines = [f"Entire group ID: {batch_id}\n{group['target_count']} captured members; "
                 f"{group['changed_count']} would be restored.",
                 "Undo available." if group["eligible"] else "Undo unavailable: already undone or catalog changes intervened."]
        for member in group["members"]:
            lines.append(f"{Path(member['captured_path']).name} | ID: {member['asset_id']}\n"
                         f"  {self._values(member['after_rating'], member['after_favorite'])} → "
                         f"{self._values(member['before_rating'], member['before_favorite'])}")
        self.group_effects.setPlainText("\n".join(lines))
        self.undo_button.setEnabled(group["eligible"])

    def undo_group(self):
        if self.undo_batch_id is None:
            return
        batch_id = self.undo_batch_id
        if self.catalog_window is not None:
            self.undo_button.setEnabled(False)
            def received(reply):
                if not self.isVisible():
                    return
                if reply.status == "refused":
                    self.undo_button.setEnabled(True)
                    self.feedback.setText(reply.message)
                    return
                self.invalidate_preview()
                self.refresh_history(batch_id)
                self.feedback.setText("Entire displayed group undone in catalog." if reply.status == "ok"
                                      else f"Entire group undo outcome requires reload: {reply.message or reply.status}")
                if reply.status == "ok":
                    self.saved.emit(batch_id)
            self.catalog_window._mutate_catalog("undo_curation_batch", (batch_id,), callback=received)
            return
        try:
            curation.undo_curation_batch(self.database, batch_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.feedback.setText(f"Entire group undo was not applied: {exc}")
            return
        self.invalidate_preview()
        self.refresh_history(batch_id)
        self.feedback.setText("Entire displayed group undone in catalog.")
        self.saved.emit(batch_id)

    def closeEvent(self, event):
        self._catalog_closed = True
        super().closeEvent(event)


class ThumbnailWorker(QThread):
    """One bounded queue and cache child; raw image delivery keeps decode off GUI."""
    updated = Signal(str)
    finished_item = Signal(int, object, QImage, object)

    def __init__(self, database: Path, cache_root: Path, parent=None):
        super().__init__(parent)
        self.database, self.cache_root = Path(database), Path(cache_root)
        self.requests = queue.Queue(maxsize=32)
        self.pending = set()
        self.pixmaps = OrderedDict()
        self.errors = {}
        self.results = OrderedDict()
        self.bindings = {}
        self._wanted = {}
        self._stop = threading.Event()
        self._active_cancel = None
        self._active_lock = threading.Lock()
        self._delivery = threading.Event()
        self._delivery.set()
        self.cleanup_failed = False
        self.generation = 0
        self.finished_item.connect(self._received)

    @staticmethod
    def key(asset, edge):
        return (asset["asset_id"], asset["sha256"], asset["byte_size"], edge)

    @staticmethod
    def binding(asset):
        return (capture_target(asset), availability_text(asset), generation_refusal(asset))

    def invalidate_pending(self):
        """Cancel old requests; captured inspectors remain independent."""
        self.generation += 1
        self.pending.clear()
        self._wanted.clear()
        with self._active_lock:
            if self._active_cancel is not None:
                self._active_cancel.set()
        while True:
            try:
                self.requests.get_nowait()
            except queue.Empty:
                break

    def lookup(self, asset: dict, edge: int):
        if type(edge) is not int or not 32 <= edge <= 256:
            return None, "Gallery cache edge must be from 32 through 256"
        try:
            binding = self.binding(asset)
            key = self.key(asset, edge)
        except (ValueError, KeyError, TypeError) as exc:
            return None, f"Cached preview refused: invalid indexed identity: {exc}"
        if self.cleanup_failed:
            return None, "Cache worker cleanup failed; replacement refused"
        if self.bindings.get(key) != binding:
            self.pixmaps.pop(key, None)
            self.errors.pop(key, None)
            self.results.pop(key, None)
            self.bindings.pop(key, None)
        if key in self.pixmaps:
            self.pixmaps.move_to_end(key)
            return self.pixmaps[key], None
        if key in self.errors:
            return None, self.errors[key]
        pending_key = (key, binding)
        if pending_key not in self.pending and not self._stop.is_set():
            try:
                self.requests.put_nowait((self.generation, dict(asset), edge))
            except queue.Full:
                pass
            else:
                self.pending.add(pending_key)
                self._wanted[key] = (self.generation, binding)
        return None, None

    def description(self, asset, edge):
        try:
            key = self.key(asset, edge)
            result = self.results.get(key) if self.bindings.get(key) == self.binding(asset) else None
        except (ValueError, KeyError, TypeError):
            return "Cached preview refused: invalid indexed identity"
        return preview_text(result, asset) if result is not None else availability_text(asset)

    def _received(self, generation, asset, image, result):
        try:
            if not result.cleanup_complete:
                self.cleanup_failed = True
            if self._stop.is_set() or generation != self.generation:
                return
            key = self.key(asset, result.requested_edge)
            binding = self.binding(asset)
            if result.target != binding[0]:
                return
            self.pending.discard((key, binding))
            if self._wanted.get(key) != (generation, binding):
                return
            self._wanted.pop(key, None)
            self.bindings[key] = binding
            self.results[key] = replace(result, pixels=b"")
            self.results.move_to_end(key)
            while len(self.results) > 256:
                evicted, _ = self.results.popitem(last=False)
                self.pixmaps.pop(evicted, None)
                self.errors.pop(evicted, None)
                self.bindings.pop(evicted, None)
            if result.status != "ready" or image.isNull():
                self.errors[key] = preview_text(result, asset)
                if len(self.errors) > 256:
                    self.errors.pop(next(iter(self.errors)))
            else:
                self.pixmaps[key] = QPixmap.fromImage(image)
                self.pixmaps.move_to_end(key)
                while len(self.pixmaps) > 256:
                    self.pixmaps.popitem(last=False)
            self.updated.emit(result.target.asset_id)
        finally:
            # Even stale/refused deliveries release the one outstanding image.
            self._delivery.set()

    def run(self):
        cache_root = self.cache_root
        while not self._stop.is_set() and not self.cleanup_failed:
            try:
                generation, asset, edge = self.requests.get(timeout=.1)
            except queue.Empty:
                continue
            cancel = threading.Event()
            with self._active_lock:
                self._active_cancel = cancel
                if generation != self.generation or self._stop.is_set():
                    cancel.set()
            target = capture_target(asset)
            try:
                result = read_cached_preview(self.database, target, cache_root, edge, cancel_event=cancel)
                if result.status == "no_cache" and not cancel.is_set():
                    # This is the actual cache miss-to-generator boundary. Admission
                    # cannot upgrade an unavailable request after a catalog change.
                    reason = fresh_generation_refusal(self.database, target, asset)
                    if reason:
                        result = CachedResult("no_cache", "No cached preview; " + reason, target,
                                              requested_edge=edge)
                    elif not cancel.is_set():
                        thumbnail_for(self.database, target.asset_id, cache_root, max_edge=edge,
                                      limits=ThumbnailLimits(timeout_seconds=6), cancel_event=cancel)
                        result = read_cached_preview(self.database, target, cache_root, edge,
                                                     cancel_event=cancel)
                image = result_image(result)
                if not image.isNull() and max(image.width(), image.height()) > edge:
                    image = image.scaled(edge, edge, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
            except ThumbnailCancelled:
                result = CachedResult("cancelled", "Thumbnail work canceled", target, requested_edge=edge)
                image = QImage()
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                result = CachedResult("refused", f"{type(exc).__name__}: {exc}", target, requested_edge=edge)
                image = QImage()
            finally:
                with self._active_lock:
                    self._active_cancel = None
            if not result.cleanup_complete:
                self.cleanup_failed = True
            metadata_result = replace(result, pixels=b"")
            del result
            self._delivery.clear()
            self.finished_item.emit(generation, asset, image, metadata_result)
            del image
            # Do not accumulate Qt queued images while the GUI is busy. Close
            # remains bounded even when no GUI acknowledgement can be delivered.
            while not self._delivery.wait(.05):
                if self._stop.is_set():
                    break

    def stop(self):
        self._stop.set()
        self.invalidate_pending()
        return self.wait(2500) and not self.cleanup_failed


class AssetDelegate(QStyledItemDelegate):
    COLORS = {
        "image/png": QColor("#577590"),
        "image/jpeg": QColor("#43aa8b"),
        "image/webp": QColor("#f9c74f"),
        "video/mp4": QColor("#f3722c"),
    }

    def __init__(self, cell_size=144, parent=None, thumbnails: ThumbnailWorker | None = None):
        super().__init__(parent)
        self.cell_size = cell_size
        self.thumbnails = thumbnails

    def set_cell_size(self, value: int):
        self.cell_size = value
        self.sizeHintChanged.emit(QModelIndex())

    def sizeHint(self, option, index):  # noqa: N802 - Qt API
        return QSize(self.cell_size, self.cell_size + 42)

    def paint(self, painter: QPainter, option, index):
        asset = index.data(AssetModel.AssetRole)
        if not asset:
            return
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        margin = 8
        thumb = QRect(
            option.rect.left() + margin,
            option.rect.top() + margin,
            option.rect.width() - margin * 2,
            max(24, option.rect.height() - 50),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.COLORS.get(asset["media_type"], QColor("#6c757d")))
        painter.drawRoundedRect(thumb, 8, 8)
        status = asset["media_type"]
        edge = min(256, max(32, self.cell_size))
        if not asset["media_type"].startswith("image/"):
            status = "Unsupported preview"
        elif self.thumbnails is not None:
            pixmap, error = self.thumbnails.lookup(asset, edge)
            if pixmap is not None:
                fitted = pixmap.size().scaled(thumb.size(), Qt.AspectRatioMode.KeepAspectRatio)
                destination = QRect(thumb.x() + (thumb.width() - fitted.width()) // 2,
                                    thumb.y() + (thumb.height() - fitted.height()) // 2,
                                    fitted.width(), fitted.height())
                painter.drawPixmap(destination, pixmap, pixmap.rect())
                status = ""
            elif error:
                status = "No cached preview" if "No cached preview" in error else "Cache refused"
            else:
                status = "Loading cached preview"
        painter.setPen(QColor("#ffffff"))
        if status:
            painter.drawText(thumb, Qt.AlignmentFlag.AlignCenter, status)
        painter.setPen(option.palette.text().color())
        label = Path(asset["current_path"]).name
        text_rect = QRect(
            option.rect.left() + margin,
            thumb.bottom() + 5,
            option.rect.width() - margin * 2,
            38,
        )
        label = option.fontMetrics.elidedText(
            label, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        detail = ("Cached · " if self.thumbnails and self.thumbnails.lookup(asset, edge)[0] is not None else "") + availability_text(asset) if asset["media_type"].startswith("image/") else asset["media_type"]
        detail = option.fontMetrics.elidedText(detail, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, label + "\n" + detail)
        painter.restore()


class GallerySelectionModel(QItemSelectionModel):
    """Expose an explicit Clear intent even when Qt has no change to signal."""

    clearRequested = Signal()

    def clear(self):
        self.clearRequested.emit()
        super().clear()


class GalleryView(QListView):
    reviewRequested = Signal(str)
    inspectRequested = Signal()
    filesPreviewed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(128)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setAccessibleName("Asset gallery")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.inspectRequested.emit()
            event.accept()
            return
        if event.text() and event.text() in "123456":
            self.reviewRequested.emit(REVIEW_STATES[int(event.text()) - 1])
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.filesPreviewed.emit(paths)
        event.acceptProposedAction()


class BackgroundWorker(QThread):
    progressChanged = Signal(int)
    canceled = Signal()

    def __init__(self, units=400, parent=None):
        super().__init__(parent)
        self.units = units
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        for unit in range(self.units):
            if self._cancel.is_set():
                self.canceled.emit()
                return
            # Deterministic CPU work plus a short yield models bounded media work.
            value = unit
            for _ in range(2_000):
                value = (value * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
            if unit % 4 == 0:
                self.progressChanged.emit(int((unit + 1) * 100 / self.units))
            self.msleep(1)
        self.progressChanged.emit(100)


class ScanWorker(QThread):
    progressChanged = Signal(dict)
    resultReady = Signal(dict)
    failed = Signal(str)

    page_size = 2_048

    def __init__(self, database: Path, source_id: str, quiet_seconds: float = 2.0,
                 parent=None):
        super().__init__(parent)
        self.database = Path(database)
        self.source_id = source_id
        self.quiet_seconds = quiet_seconds
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            first = self._scan_pass(None)
            result = first
            if (first["complete"] and not first["canceled"]
                    and first["sources"] and first["sources"][0]["health"] == "paused"
                    and first["totals"]["pending"]):
                self.progressChanged.emit({"phase": "quiet_interval", "source_id": self.source_id,
                                           "seconds": self.quiet_seconds})
                if not self.cancel_event.wait(self.quiet_seconds + .05):
                    result = self._scan_pass(None)
                    result["totals"] = {
                        key: (result["totals"][key] if key in
                              ("pending", "ignored_existing", "unchanged") else
                              first["totals"][key] + result["totals"][key])
                        for key in first["totals"]
                    }
                else:
                    result = dict(first, canceled=True)
            self.resultReady.emit(result)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _scan_pass(self, cursor: str | None) -> dict:
        cumulative = None
        inventory_cache = {}
        while True:
            result = scan_sources(
                self.database, source_id=self.source_id, quiet_seconds=self.quiet_seconds,
                cancel_event=self.cancel_event, progress=self.progressChanged.emit,
                max_candidates=self.page_size, resume_after=cursor,
                inventory_cache=inventory_cache,
            )
            if cumulative is None:
                cumulative = dict(result["totals"])
            else:
                for key in cumulative:
                    cumulative[key] += result["totals"][key]
            if result["canceled"] or result["complete"] or not result["sources"]:
                result["totals"] = cumulative
                return result
            if result["sources"][0]["health"] != "paused":
                result["totals"] = cumulative
                return result
            next_cursor = result["resume_after"]
            if next_cursor is None or next_cursor == cursor:
                raise RuntimeError("Scan page made no progress")
            cursor = next_cursor


class GalleryFilterPicker(QWidget):
    """One bounded catalog lookup page; typed text is never a selected ID."""

    changed = Signal()
    applyRequested = Signal()
    catalogInvalidated = Signal(str, str)

    def __init__(self, client: GalleryCatalogClient, kind: str, parent=None):
        super().__init__(parent)
        if kind not in ("tag", "entity", "source"):
            raise ValueError("Unknown gallery picker")
        self.client, self.kind = client, kind
        self.selected_id = None
        self.selected_label = ""
        self._epoch = 0
        self._cursor = None
        self._loading = False
        self.text = QLineEdit()
        self.text.setObjectName(f"gallery{kind.title()}Text")
        self.text.setAccessibleName(f"Gallery {kind} canonical lookup")
        self.text.setPlaceholderText(f"Find one {kind}…")
        self.text.textChanged.connect(self._edited)
        self.text.returnPressed.connect(self._return_pressed)
        self.text.installEventFilter(self)
        self.results = QListWidget()
        self.results.setObjectName(f"gallery{kind.title()}Results")
        self.results.setAccessibleName(f"Gallery {kind} bounded suggestions")
        self.results.setMaximumHeight(128)
        self.results.hide()
        self.results.itemActivated.connect(self._choose)
        self.results.itemClicked.connect(self._choose)
        self.results.installEventFilter(self)
        self.browse = QPushButton("Browse")
        self.browse.clicked.connect(self._first_page)
        self.more = QPushButton("More")
        self.more.setEnabled(False)
        self.more.clicked.connect(self._next_page)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_choice)
        self.feedback = QLabel("All")
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.feedback.setAccessibleName(f"Gallery {kind} lookup status")
        row = QHBoxLayout()
        row.addWidget(self.text, 2)
        row.addWidget(self.browse)
        row.addWidget(self.more)
        row.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.results)
        layout.addWidget(self.feedback)

    def eventFilter(self, watched, event):
        if watched in (self.text, self.results) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                if self.results.isVisible():
                    self.results.hide()
                elif self.selected_id is None and self.text.text():
                    self.clear_choice()
                else:
                    return False
                event.accept()
                return True
            if watched is self.results and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._return_pressed()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _edited(self, value):
        self.selected_id = None
        self.selected_label = ""
        self._epoch += 1
        self._cursor = None
        self.more.setEnabled(False)
        self.results.clear()
        self.results.hide()
        self.changed.emit()
        if value:
            self.feedback.setText("Resolve a canonical choice before Apply.")
            self._request(None)
        else:
            self._loading = False
            self.feedback.setText("All")

    def clear_choice(self):
        self._epoch += 1
        self.selected_id = None
        self.selected_label = ""
        self._cursor = None
        self._loading = False
        self.text.blockSignals(True)
        self.text.clear()
        self.text.blockSignals(False)
        self.results.clear()
        self.results.hide()
        self.more.setEnabled(False)
        self.feedback.setText("All")
        self.changed.emit()

    def set_choice(self, identifier, label):
        self._epoch += 1
        self.selected_id = identifier
        self.selected_label = label
        self._cursor = None
        self._loading = False
        self.text.blockSignals(True)
        self.text.setText(label)
        self.text.blockSignals(False)
        self.results.hide()
        self.more.setEnabled(False)
        self.feedback.setText(f"Selected {label}" if identifier is not None else "All")
        self.changed.emit()

    def _first_page(self):
        self._request(None)

    def _next_page(self):
        if self._cursor is not None:
            self._request(self._cursor)

    def _request(self, cursor):
        raw = self.text.text()
        try:
            if self.kind == "source":
                if len(raw) > 128 or any(unicodedata.category(char) == "Cc" for char in raw):
                    raise ValueError("Source lookup text must be at most 128 code points without controls")
                prefix = raw.strip()
            else:
                prefix = normalize_lookup_text(raw)
        except ValueError as exc:
            self._loading = False
            self.results.hide()
            self.more.setEnabled(False)
            self.feedback.setText(str(exc))
            return
        self._epoch += 1
        epoch = self._epoch
        self._loading = True
        self.more.setEnabled(False)
        self.feedback.setText("Loading bounded suggestions…")
        if self.kind == "source":
            category, operation, args = RequestClass.SOURCE, "sources", (prefix, cursor)
        else:
            category, operation = RequestClass.TAXONOMY, "taxonomy"
            args = (LookupKind.TAG if self.kind == "tag" else LookupKind.ENTITY,
                    prefix, cursor, None)

        def received(reply):
            if not qt_is_valid(self) or epoch != self._epoch:
                return
            self._loading = False
            if reply.status != "ok":
                self.results.clear()
                self.results.hide()
                self._cursor = None
                self.more.setEnabled(False)
                self.feedback.setText(reply.message or reply.status)
                if reply.status in ("catalog_replaced", "catalog_unavailable"):
                    self.catalogInvalidated.emit(reply.status, reply.message or reply.status)
                return
            page = reply.value
            self.results.clear()
            for record in page.rows:
                label = record["name"] or "[unavailable: missing catalog label]"
                if self.kind == "entity":
                    label += f" · {record['entity_type'] or '[unavailable category]'}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, (record["id"], label))
                item.setToolTip(f"Canonical ID: {record['id']}")
                item.setFlags(item.flags() if record["selectable"] else
                              item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                self.results.addItem(item)
            self.results.setVisible(bool(page.rows))
            self.results.setCurrentRow(0 if page.rows else -1)
            self._cursor = page.next_cursor
            self.more.setEnabled(self._cursor is not None)
            if page.incomplete and self._cursor is None:
                self.feedback.setText("Some labels or continuation are unavailable; refine the prefix.")
            elif page.incomplete:
                self.feedback.setText("Some labels are unavailable; refine the prefix if needed.")
            elif page.rows:
                self.feedback.setText(f"{len(page.rows)} canonical suggestions on this page")
            else:
                self.feedback.setText("No matching canonical records")

        _, reason = self.client.submit(category, operation, args,
                                       generation=epoch, callback=received)
        if reason:
            self._loading = False
            self.feedback.setText(reason)

    def _choose(self, item):
        if item is None or not bool(item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        identifier, label = item.data(Qt.ItemDataRole.UserRole)
        self.set_choice(identifier, label)
        self.text.setFocus()

    def _return_pressed(self):
        if self.results.isVisible() and self.results.currentItem() is not None:
            self._choose(self.results.currentItem())
        else:
            self.applyRequested.emit()


_FAILED_STARTUP_WINDOWS = []


class GalleryWindow(ExternalActionsMixin, QMainWindow):
    def __init__(self, database: Path, *, enable_thumbnails: bool = False,
                 cache_root: Path | None = None, private_root: Path | None = None,
                 external_settings_path: Path | None = None,
                 external_settings: external_actions.ExternalSettings | None = None):
        super().__init__()
        self._closing = False
        self._thumbnail_close_pending = False
        self._gateway_close_pending = False
        self._recovery_close_pending = False
        self._background_close_pending = False
        self._startup_validated = False
        self.database = Path(database).resolve(strict=True)
        self._admission_owner = current_session(self.database)
        self._restore_pending = True  # conservative until gateway reads the marker
        self._recovery_state_epoch = 0
        self._recovery_catalog_identity = None
        library_key = hashlib.sha256(str(self.database).encode()).hexdigest()[:16]
        app_data = default_private_root().parent
        self.cache_root = Path(cache_root or app_data / "thumbnails" / library_key)
        self.private_root = Path(private_root or default_private_root())
        if enable_thumbnails:
            assert_outside_git(self.database)
            assert_outside_git(self.cache_root)
        self.catalog_client = GalleryCatalogClient(self.database, self)
        self.catalog_client.failed.connect(self._catalog_failed)
        self.catalog_client.submit(RequestClass.LEGACY, "legacy",
            ("validate_source_roots", self.cache_root, self.private_root),
            context="startup-roots", callback=self._source_roots_checked)
        self._source_records = []
        self._legacy_epoch = {}
        self._mutation_pending = False
        self._selection_epoch = 0
        self._source_choice_epoch = 0
        self._clearing_gallery_selection = False
        self._model_reset_in_progress = False
        self._collection_choice_epoch = 0
        self._pending_restore = None
        self._metadata_focus_intent = None
        self._pending_bulk_restore = None
        self._bulk_restore_intent = None
        self._bulk_restore_dispose = None
        self._detail_ready_key = None
        self._draft_epoch = 0
        self._draft_duplicate_digest = None
        self._duplicate_draft_touched = False
        self._pending_filter = None
        self._last_filter_refusal = None
        self.setWindowTitle("DefiantMaple Gallery")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.model = AssetModel(self.database, self, read_mode="async",
                                catalog_client=self.catalog_client)
        self.model.loadFailed.connect(self._catalog_failed)
        self.model.loadFailed.connect(self._filter_load_failed)
        self.model.generationPublished.connect(self._gallery_published)
        self.model.actionabilityChanged.connect(self._update_action_controls)
        self.model.filterRestored.connect(self._filter_restored)
        self.thumbnails = (ThumbnailWorker(self.database, self.cache_root, self)
                           if enable_thumbnails else None)
        self.delegate = AssetDelegate(parent=self, thumbnails=self.thumbnails)
        if self.thumbnails is not None:
            self.model.preview_provider = lambda asset: self.thumbnails.description(asset, min(256, max(32, self.delegate.cell_size)))
        self.gallery = GalleryView(self)
        self.gallery.setModel(self.model)
        selection_model = GallerySelectionModel(self.model, self.gallery)
        self.gallery.setSelectionModel(selection_model)
        selection_model.clearRequested.connect(self._explicit_gallery_clear)
        self.gallery.setItemDelegate(self.delegate)
        self.gallery.selectionModel().currentChanged.connect(self._show_detail)
        self.gallery.reviewRequested.connect(self.set_selected_state)
        self.gallery.inspectRequested.connect(self.inspect_selected)
        self.gallery.doubleClicked.connect(lambda _index: self.inspect_selected())
        self.gallery.filesPreviewed.connect(self._preview_files)
        self.inspect_dialog: FullImageDialog | None = None
        self.comparison_dialog: ComparisonDialog | None = None
        self.cached_dialog: CachedPreviewDialog | None = None
        self.recovery_dialog: RecoveryDialog | None = None
        self.worker: BackgroundWorker | None = None
        self.scan_worker: ScanWorker | None = None
        if self.thumbnails is not None:
            self.thumbnails.updated.connect(lambda _asset_id: self.gallery.viewport().update())
            self.gallery.verticalScrollBar().valueChanged.connect(self._invalidate_thumbnails)
            self.gallery.horizontalScrollBar().valueChanged.connect(self._invalidate_thumbnails)
            self.model.modelReset.connect(self._invalidate_thumbnails)
            # Start only after the worker validates all registered source roots.

        self.source_box = QComboBox()
        self.source_box.setAccessibleName("Scan target source and health")
        self.source_box.currentIndexChanged.connect(self._source_choice_changed)
        self.add_source_button = QPushButton("Add folder…")
        self.add_source_button.clicked.connect(self._add_source_dialog)
        self.scan_button = QPushButton("Scan source")
        self.scan_button.clicked.connect(self.start_source_scan)
        self.cancel_scan_button = QPushButton("Cancel scan")
        self.cancel_scan_button.clicked.connect(self.cancel_source_scan)
        self.recovery_button = QPushButton("Metadata recovery…")
        self.recovery_button.setEnabled(False)
        self.recovery_button.clicked.connect(self.open_recovery)
        self.cancel_scan_button.setEnabled(False)
        self.scan_status = QLabel("Choose a source to scan. Scans are one-shot, not watchers.")
        self.scan_status.setAccessibleName("Source scan status")

        self.filter_box = QComboBox()
        self.filter_box.addItem("All states", "all")
        for state in REVIEW_STATES:
            self.filter_box.addItem(state.replace("_", " ").title(), state)
        self.filter_box.currentIndexChanged.connect(self._draft_edited)
        self.filter_box.setAccessibleName("Review state filter")
        self.type_box = QComboBox()
        self.type_box.addItem("All media", None)
        for label, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"),
                            ("GIF", "image/gif"), ("WebP", "image/webp")):
            self.type_box.addItem(label, mime)
        self.type_box.currentIndexChanged.connect(self._draft_edited)
        self.type_box.setAccessibleName("Media type filter")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Literal path/filename text")
        self.search_box.returnPressed.connect(self._apply_gallery_filters)
        self.search_box.setAccessibleName("Literal path or filename filter")
        self.search_box.textChanged.connect(self._draft_edited)
        self.search_box.textChanged.connect(self._update_collection_controls)
        self.apply_filters_button = QPushButton("Apply filters")
        self.apply_filters_button.setObjectName("applyGalleryFilters")
        self.apply_filters_button.clicked.connect(self._apply_gallery_filters)
        self.clear_filters_button = QPushButton("Clear filters (keep collection)")
        self.clear_filters_button.setObjectName("clearGalleryFilters")
        self.clear_filters_button.clicked.connect(self._clear_gallery_filters)
        self.gallery_tag_picker = GalleryFilterPicker(self.catalog_client, "tag", self)
        self.gallery_entity_picker = GalleryFilterPicker(self.catalog_client, "entity", self)
        self.gallery_source_picker = GalleryFilterPicker(self.catalog_client, "source", self)
        for picker in (self.gallery_tag_picker, self.gallery_entity_picker,
                       self.gallery_source_picker):
            picker.changed.connect(self._draft_edited)
            picker.applyRequested.connect(self._apply_gallery_filters)
            picker.catalogInvalidated.connect(self._picker_catalog_invalidated)
        self.filter_feedback = QLabel("Edit filters, then Apply. The gallery source is separate from the scan target.")
        self.filter_feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.filter_feedback.setWordWrap(True)
        self.filter_feedback.setAccessibleName("Gallery filter draft and apply result")

        self.rating_filter_box = CurationFilterBox()
        self.rating_filter_box.setObjectName("ratingFilter")
        self.rating_filter_box.setAccessibleName("Gallery rating filter")
        self.rating_filter_box.addItem("All ratings", RatingFilter())
        self.rating_filter_box.addItem("Unrated", RatingFilter(RatingMode.UNRATED))
        for stars in range(1, 6):
            self.rating_filter_box.addItem(f"Exactly {stars} stars", RatingFilter(RatingMode.EXACT, stars))
            self.rating_filter_box.addItem(f"At least {stars} stars", RatingFilter(RatingMode.AT_LEAST, stars))
        self.favorite_filter_box = CurationFilterBox()
        self.favorite_filter_box.setObjectName("favoriteFilter")
        self.favorite_filter_box.setAccessibleName("Gallery favorite filter")
        for label, value in (("All favorites", FavoriteFilter.ALL), ("Favorites", FavoriteFilter.FAVORITES),
                             ("Not favorites", FavoriteFilter.NOT_FAVORITES)):
            self.favorite_filter_box.addItem(label, value)
        self.rating_filter_box.currentIndexChanged.connect(self._draft_edited)
        self.favorite_filter_box.currentIndexChanged.connect(self._draft_edited)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(96, 224)
        self.size_slider.setValue(144)
        self.size_slider.valueChanged.connect(self._resize_cells)
        self.size_slider.setAccessibleName("Gallery cell size")

        self.task_button = QPushButton("Start background task")
        self.task_button.clicked.connect(self.start_background_task)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_background_task)
        self.cancel_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName("Scan or benchmark progress")

        sources_row = QHBoxLayout()
        sources_row.addWidget(QLabel("Scan target"))
        sources_row.addWidget(self.source_box, 2)
        sources_row.addWidget(self.add_source_button)
        sources_row.addWidget(self.scan_button)
        sources_row.addWidget(self.cancel_scan_button)
        sources_row.addWidget(self.recovery_button)
        sources_row.addWidget(self.progress)
        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel("State"))
        filters_row.addWidget(self.filter_box)
        filters_row.addWidget(self.type_box)
        filters_row.addWidget(self.search_box, 2)
        filters_row.addWidget(QLabel("Thumbnail size"))
        filters_row.addWidget(self.size_slider)
        curation_filters_row = QHBoxLayout()
        curation_filters_row.addWidget(QLabel("Rating"))
        curation_filters_row.addWidget(self.rating_filter_box)
        curation_filters_row.addWidget(QLabel("Favorite"))
        curation_filters_row.addWidget(self.favorite_filter_box)
        curation_filters_row.addStretch()
        canonical_filters_row = QHBoxLayout()
        for label, picker in (("Gallery source", self.gallery_source_picker),
                              ("Assigned tag", self.gallery_tag_picker),
                              ("Assigned entity", self.gallery_entity_picker)):
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            column.addWidget(picker)
            canonical_filters_row.addLayout(column, 1)
        filter_actions_row = QHBoxLayout()
        filter_actions_row.addWidget(self.apply_filters_button)
        filter_actions_row.addWidget(self.clear_filters_button)
        filter_actions_row.addStretch()
        self.task_button.hide()
        self.cancel_button.hide()

        self.collection_box = QComboBox()
        self.collection_box.setAccessibleName("Browse manual collection")
        self.collection_box.currentIndexChanged.connect(self._collection_selected)
        self.create_collection_button = QPushButton("New collection…")
        self.create_collection_button.clicked.connect(self._create_collection)
        self.rename_collection_button = QPushButton("Rename…")
        self.rename_collection_button.clicked.connect(self._rename_collection)
        self.delete_collection_button = QPushButton("Delete…")
        self.delete_collection_button.clicked.connect(self._delete_collection)
        self.add_member_button = QPushButton("Add selected…")
        self.add_member_button.clicked.connect(self._add_collection_member)
        self.remove_member_button = QPushButton("Remove selected")
        self.remove_member_button.clicked.connect(self._remove_collection_member)
        self.move_up_button = QPushButton("Move up")
        self.move_up_button.clicked.connect(lambda: self._move_collection_member(-1))
        self.move_down_button = QPushButton("Move down")
        self.move_down_button.clicked.connect(lambda: self._move_collection_member(1))
        collection_row = QHBoxLayout()
        collection_row.addWidget(QLabel("Collection"))
        collection_row.addWidget(self.collection_box, 2)
        for button in (self.create_collection_button, self.rename_collection_button,
                       self.delete_collection_button, self.add_member_button,
                       self.remove_member_button, self.move_up_button, self.move_down_button):
            collection_row.addWidget(button)
        self.collection_feedback = QLabel("Manual collections keep an ordered selection of library assets.")
        self.collection_feedback.setWordWrap(True)
        self.collection_feedback.setAccessibleName("Collection result and reorder guidance")
        self.collection_records = []
        self.gallery.selectionModel().currentChanged.connect(self._update_collection_controls)
        self.model.modelReset.connect(self._update_collection_controls)
        self._update_collection_controls()

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Selected asset details")
        self.duplicates_list = QListWidget()
        self.duplicates_list.setAccessibleName("Exact duplicate groups")
        self.duplicates_list.itemClicked.connect(self._duplicate_selected)
        self.issues_list = QListWidget()
        self.issues_list.setAccessibleName("Source files needing attention")
        duplicate_button = QPushButton("Show exact duplicates")
        duplicate_button.clicked.connect(self.refresh_duplicates)
        clear_duplicates = QPushButton("Clear duplicate filter")
        clear_duplicates.clicked.connect(self._clear_duplicate_draft)
        self.curate_button = QPushButton("Add selected to private evaluation…")
        self.curate_button.clicked.connect(self._curate_selected)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(self.detail, 3)
        self.inspect_button = QPushButton("Inspect full image…")
        self.inspect_button.setAccessibleName("Inspect selected original image")
        self.inspect_button.clicked.connect(self.inspect_selected)
        side_layout.addWidget(self.inspect_button)
        self.cached_button = QPushButton("View cached preview…")
        self.cached_button.setObjectName("viewCachedPreview")
        self.cached_button.setAccessibleName("View selected cached indexed preview")
        self.cached_button.clicked.connect(self.view_cached_selected)
        self.cached_button.setEnabled(False)
        side_layout.addWidget(self.cached_button)
        self.compare_button = QPushButton("Compare two selected images…")
        self.compare_button.setObjectName("compareCapturedImages")
        self.compare_button.setAccessibleName("Compare exactly two selected images in view order")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self.compare_selected)
        side_layout.addWidget(self.compare_button)
        self.metadata_button = QPushButton("Tags and entities…")
        self.metadata_button.clicked.connect(self._edit_metadata)
        side_layout.addWidget(self.metadata_button)
        self._init_external_actions(side_layout, external_settings_path, external_settings)
        self.curation_button = QPushButton("Rating and favorite…")
        self.curation_button.setObjectName("editCuration")
        self.curation_button.setAccessibleName("Edit selected rating and favorite")
        self.curation_button.clicked.connect(self.edit_curation)
        self.curation_button.setEnabled(False)
        self.curation_dialog = None
        side_layout.addWidget(self.curation_button)
        self.selection_label = QLabel("0 selected. Single-asset actions use the focused asset.")
        self.selection_label.setWordWrap(True)
        self.selection_label.setAccessibleName("Gallery selection count and focused action target")
        side_layout.addWidget(self.selection_label)
        self.bulk_curation_button = QPushButton("Bulk rating and favorite…")
        self.bulk_curation_button.setObjectName("editBulkCuration")
        self.bulk_curation_button.setAccessibleName("Edit captured selected ratings and favorites")
        self.bulk_curation_button.clicked.connect(self.edit_bulk_curation)
        self.bulk_curation_button.setEnabled(False)
        self.bulk_curation_dialog = None
        side_layout.addWidget(self.bulk_curation_button)
        self.group_history_button = QPushButton("Recent bulk groups and undo…")
        self.group_history_button.setAccessibleName("Inspect durable bulk groups and undo an entire group")
        self.group_history_button.clicked.connect(self.open_curation_history)
        side_layout.addWidget(self.group_history_button)
        side_layout.addWidget(duplicate_button)
        side_layout.addWidget(clear_duplicates)
        side_layout.addWidget(self.duplicates_list, 1)
        side_layout.addWidget(QLabel("Source issues (first 100)"))
        side_layout.addWidget(self.issues_list, 1)
        side_layout.addWidget(self.curate_button)
        splitter = QSplitter()
        splitter.addWidget(self.gallery)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setAccessibleName("Scrollable focused asset actions and source issues")
        self.detail_scroll.setWidget(side)
        splitter.addWidget(self.detail_scroll)
        splitter.setSizes([950, 330])

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(str(self.database)))
        layout.addLayout(sources_row)
        layout.addWidget(self.scan_status)
        layout.addLayout(filters_row)
        layout.addLayout(curation_filters_row)
        layout.addLayout(canonical_filters_row)
        layout.addLayout(filter_actions_row)
        layout.addWidget(self.filter_feedback)
        layout.addLayout(collection_row)
        layout.addWidget(self.collection_feedback)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self.gallery.selectionModel().selectionChanged.connect(self._update_selection_controls)
        self.gallery.selectionModel().selectionChanged.connect(self._selection_changed)
        self.gallery.selectionModel().currentChanged.connect(self._update_selection_controls)
        self.gallery.selectionModel().currentChanged.connect(self._selection_changed)
        self.model.modelAboutToBeReset.connect(self._model_reset_started)
        self.model.modelAboutToBeReset.connect(self._clear_gallery_selection)
        self.model.modelReset.connect(self._model_reset_finished)
        self._focus_path_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._focus_path_shortcut.activated.connect(self.search_box.setFocus)
        filter_order = (self.filter_box, self.type_box, self.search_box,
                        self.rating_filter_box, self.favorite_filter_box,
                        self.gallery_source_picker.text, self.gallery_source_picker.browse,
                        self.gallery_source_picker.more, self.gallery_source_picker.clear_button,
                        self.gallery_tag_picker.text, self.gallery_tag_picker.browse,
                        self.gallery_tag_picker.more, self.gallery_tag_picker.clear_button,
                        self.gallery_entity_picker.text, self.gallery_entity_picker.browse,
                        self.gallery_entity_picker.more, self.gallery_entity_picker.clear_button,
                        self.apply_filters_button, self.clear_filters_button,
                        self.collection_box)
        for first, second in zip(filter_order, filter_order[1:]):
            QWidget.setTabOrder(first, second)
        self.statusBar().showMessage(f"{self.model.rowCount():,} assets")
        if self._admission_owner is not None:
            self._admission_owner.claim_coordinator()
        try:
            self.catalog_client.start()
        except BaseException:
            # Connect before requesting shutdown: a very short worker can
            # finish between isRunning() and a late signal connection.
            _FAILED_STARTUP_WINDOWS.append(self)
            def cleaned():
                self.model.close()
                if self._admission_owner is not None:
                    self._admission_owner.release_coordinator()
                    self._admission_owner = None
                if self in _FAILED_STARTUP_WINDOWS:
                    _FAILED_STARTUP_WINDOWS.remove(self)
            self.catalog_client.gateway.finished.connect(cleaned)
            self.catalog_client.gateway.request_close()
            if not self.catalog_client.gateway.isRunning():
                cleaned()
            raise

    def _update_action_controls(self, *_args):
        if not hasattr(self, "gallery") or self._closing:
            return
        ready = self.model._actionable and not self._mutation_pending
        if not ready:
            self._detail_ready_key = None
            if hasattr(self, "detail"):
                self.detail.setPlainText("Updating catalog view…")
            for name in ("inspect_button", "cached_button", "curation_button",
                         "compare_button", "bulk_curation_button", "metadata_button",
                         "curate_button", "group_history_button"):
                control = getattr(self, name, None)
                if control is not None:
                    control.setEnabled(False)
        else:
            if hasattr(self, "metadata_button"):
                self.metadata_button.setEnabled(not self.gallery.currentIndex().isValid())
            if hasattr(self, "group_history_button"):
                self.group_history_button.setEnabled(True)
            self._show_detail(self.gallery.currentIndex())
        if hasattr(self, "collection_box"):
            self._update_collection_controls()
        if hasattr(self, "selection_label"):
            self._update_selection_controls()
        if hasattr(self, "open_external_button"):
            self._update_external_controls()

    def _catalog_failed(self, message: str):
        if not self._closing:
            self.statusBar().showMessage(f"Catalog unavailable: {message}")
            self.detail.setPlainText(f"Catalog unavailable: {message}")

    def _gallery_published(self, generation: int):
        if self._closing:
            return
        if (self._bulk_restore_intent is not None and
                self._bulk_restore_intent[2] != generation):
            self._bulk_restore_intent = None
        self.statusBar().showMessage(
            self.model.last_filter_error or f"{self.model.rowCount():,} matching assets")
        self._update_selection_controls()
        pending_filter = self._pending_filter
        if pending_filter is not None and self.model._query == pending_filter[1]:
            self._pending_filter = None
            self._last_filter_refusal = None
            if self._draft_epoch != pending_filter[2]:
                self.filter_feedback.setText("Captured filter draft applied; newer edits remain unapplied.")
            elif self.model.rowCount() == 0 and self.model._query == GalleryQuery():
                self.filter_feedback.setText("Library is empty.")
            elif self.model.rowCount() == 0:
                self.filter_feedback.setText("Applied filters: 0 matching assets.")
            else:
                self.filter_feedback.setText(f"Applied: {self.model.rowCount():,} matching assets.")
        elif pending_filter is not None and self._last_filter_refusal is not None:
            self._pending_filter = None
            self.filter_feedback.setText(
                f"Filter refused: {self._last_filter_refusal}. Previous view refreshed; draft retained.")
        pending = self._pending_restore
        self._pending_restore = None
        if (pending is not None and pending[0] == generation and
                (pending[2] is None or pending[2] == self._selection_epoch)):
            self._restore_asset_selection(pending[1])
        bulk_pending = self._pending_bulk_restore
        self._pending_bulk_restore = None
        if bulk_pending is not None and bulk_pending[0] == generation:
            self._restore_bulk_selection(bulk_pending[1])

    def _filter_restored(self, _query):
        self._pending_filter = None
        self._last_filter_refusal = self.model.last_filter_error
        self.filter_feedback.setText(
            f"Filter refused: {self.model.last_filter_error}. Previous view refreshed; draft retained.")
        self._update_action_controls()

    def _filter_load_failed(self, reason):
        if hasattr(self, "filter_feedback") and self._pending_filter is not None:
            self._last_filter_refusal = reason
            self.filter_feedback.setText(f"Filter read failed: {reason}. Draft retained; prior view is reloading.")

    def _picker_catalog_invalidated(self, status, message):
        if not self._closing:
            self._metadata_focus_intent = None
            self.model._invalidate_changed_view(status, message)
            self.filter_feedback.setText(f"Catalog unavailable for picker: {message}")

    def _draft_edited(self, *_args):
        if not hasattr(self, "filter_feedback"):
            return
        self._draft_epoch += 1
        self.filter_feedback.setText("Draft changed. Apply filters to update the gallery.")

    def _candidate_from_draft(self):
        for label, picker in (("tag", self.gallery_tag_picker),
                              ("entity", self.gallery_entity_picker),
                              ("gallery source", self.gallery_source_picker)):
            if picker.text.text() and picker.selected_id is None:
                raise ValueError(f"Resolve or clear the {label} picker before Apply")
        collection_id = self.model._collection_id
        return GalleryQuery(
            state=None if self.filter_box.currentData() == "all" else self.filter_box.currentData(),
            source_id=self.gallery_source_picker.selected_id,
            media_type=self.type_box.currentData(),
            tag_id=self.gallery_tag_picker.selected_id,
            entity_id=self.gallery_entity_picker.selected_id,
            rating=self.rating_filter_box.currentData(),
            favorite=self.favorite_filter_box.currentData(),
            path_text=self.search_box.text(),
            duplicate_digest=(self._draft_duplicate_digest if self._duplicate_draft_touched
                              else self.model._query.duplicate_digest),
            collection_id=collection_id,
            order=(GalleryOrder.MANUAL_COLLECTION if collection_id is not None
                   else GalleryOrder.LIBRARY),
        )

    def _apply_gallery_filters(self):
        if self._closing or not self._startup_validated:
            return
        try:
            candidate = self._candidate_from_draft()
        except ValueError as exc:
            self.filter_feedback.setText(f"Filter not applied: {exc}")
            self.statusBar().showMessage(str(exc))
            return
        self._selection_epoch += 1
        self._pending_restore = None
        self._metadata_focus_intent = None
        self._pending_bulk_restore = None
        self._bulk_restore_intent = None
        if self._bulk_restore_dispose is not None:
            self._bulk_restore_dispose()
        self._detail_ready_key = None
        self._clear_gallery_selection()
        self.detail.clear()
        self._last_filter_refusal = None
        reason = self.model.apply_query(candidate, defer_until_write=self._mutation_pending)
        self._pending_filter = (self.model._generation, candidate, self._draft_epoch)
        self.filter_feedback.setText(
            f"Catalog busy: {reason}. Captured draft awaits a fresh view."
            if reason else "Applying captured filter draft…")
        self._update_action_controls()

    def _clear_gallery_filters(self):
        for box in (self.filter_box, self.type_box, self.rating_filter_box,
                    self.favorite_filter_box):
            box.setCurrentIndex(0)
        self.search_box.clear()
        for picker in (self.gallery_source_picker, self.gallery_tag_picker,
                       self.gallery_entity_picker):
            picker.clear_choice()
        self._draft_duplicate_digest = None
        self._duplicate_draft_touched = True
        self._apply_gallery_filters()

    def _selection_changed(self, *_args):
        if not self._clearing_gallery_selection and not self._model_reset_in_progress:
            self._selection_epoch += 1
            self._metadata_focus_intent = None
            self._bulk_restore_intent = None

    def _explicit_gallery_clear(self):
        if self._closing or self._clearing_gallery_selection or self._model_reset_in_progress:
            return
        self._selection_epoch += 1
        self._pending_restore = None
        self._metadata_focus_intent = None
        self._pending_bulk_restore = None
        self._bulk_restore_intent = None
        if self._bulk_restore_dispose is not None:
            self._bulk_restore_dispose()
        self._detail_ready_key = None

    def _model_reset_started(self):
        self._model_reset_in_progress = True

    def _model_reset_finished(self):
        self._model_reset_in_progress = False

    def _source_roots_checked(self, reply):
        if reply.status != "ok":
            self._catalog_failed(reply.message or reply.status)
            self.centralWidget().setEnabled(False)
            return
        # Root validation already read the authoritative source list.  Publish
        # that result before the initial high-priority Apply can supersede any
        # lower-priority legacy list request.
        self._publish_sources(reply.value, None)
        self._legacy("recovery-state", "recovery_state",
                     callback=lambda state, epoch=self._recovery_state_epoch:
                     self._startup_recovery_state(state, epoch),
                     on_error=self._recovery_startup_failed)

    def _startup_recovery_state(self, state, epoch):
        if self._closing or epoch != self._recovery_state_epoch:
            return
        self._startup_validated = True
        self._recovery_catalog_identity = tuple(state["identity"])
        self.recovery_button.setEnabled(True)
        self._set_recovery_state(state, epoch)
        self.model.refresh()
        self.refresh_collections()
        if self.thumbnails is not None and not self.thumbnails.isRunning():
            self.thumbnails.start()

    def _recovery_startup_failed(self, reason):
        self._catalog_failed(reason)
        self.centralWidget().setEnabled(False)

    def _legacy(self, key: str, name: str, args=(), *, kwargs=None, callback=None,
                on_error=None, owner=None, suppress_expected_cancellation=False):
        epoch = self._legacy_epoch.get(key, 0) + 1
        self._legacy_epoch[key] = epoch
        owner_ref = weakref.ref(owner) if owner is not None else None
        def received(reply):
            if self._closing:
                return
            if reply.status in ("catalog_replaced", "catalog_unavailable"):
                self._metadata_focus_intent = None
                self.model._invalidate_changed_view(reply.status, reply.message)
            if epoch != self._legacy_epoch.get(key):
                return
            if owner_ref is not None:
                target = owner_ref()
                if target is None or not qt_is_valid(target) or getattr(target, "_catalog_closed", False):
                    return
            if reply.status != "ok":
                # Metadata's background refresh has no disabled control to
                # restore.  A higher-priority Apply or captured write may
                # cancel its old read after a successful edit reports its
                # outcome; that internal cancellation must not replace it.
                if (suppress_expected_cancellation and
                        reply.status in ("cancelled", "superseded")):
                    return
                if on_error is not None:
                    on_error(reply.message or reply.status)
                elif reply.status not in ("superseded", "cancelled"):
                    self._catalog_failed(reply.message or reply.status)
            elif callback is not None:
                callback(reply.value)
        _, reason = self.catalog_client.submit(RequestClass.LEGACY, "legacy",
            (name, *args), kwargs=kwargs, context=key, callback=received)
        if reason:
            if on_error is not None:
                on_error(reason)
            else:
                self._catalog_failed(reason)

    def _mutate_catalog(self, name: str, args=(), *, kwargs=None, callback=None,
                        retain=(), refresh_after=True):
        if self._closing or not self._startup_validated or self._mutation_pending:
            reason = ("A catalog change is pending; retry after it finishes"
                      if self._mutation_pending else "Catalog is not ready for another change")
            if callback is not None:
                callback(CatalogReply(-1, RequestClass.MUTATION, self.model._generation,
                                      "refused", message=reason))
            return False
        bulk_mutation = name in ("apply_curation_batch", "undo_curation_batch")
        bulk_selection = self._capture_bulk_selection() if bulk_mutation else None
        if bulk_mutation and bulk_selection is None:
            intent = self._bulk_restore_intent
            if (intent is not None and intent[1] == self.model._query and
                    intent[2] == self.model._generation and
                    intent[3] == self._collection_choice_epoch and
                    intent[0][2] == self._selection_epoch):
                bulk_selection = intent[0]
        self._bulk_restore_intent = None
        self._pending_bulk_restore = None
        self._mutation_pending = True
        self.model.invalidate_for_mutation()
        mutation_generation = self.model._generation
        mutation_collection_epoch = self._collection_choice_epoch
        if bulk_selection is not None:
            self._bulk_restore_intent = (bulk_selection, self.model._query,
                                         mutation_generation, mutation_collection_epoch)
        self._update_action_controls()
        self.detail.clear()
        def received(reply):
            self._mutation_pending = False
            # Even a failed or uncertain opaque mutation requires a fresh view.
            if not self._closing:
                if reply.status in ("catalog_replaced", "catalog_unavailable"):
                    self._metadata_focus_intent = None
                if (refresh_after and
                        reply.status not in ("catalog_replaced", "catalog_unavailable")):
                    restore_bulk = (bulk_selection is not None and
                                    self.model._generation == mutation_generation and
                                    self._collection_choice_epoch == mutation_collection_epoch)
                    self.model.refresh()
                    if restore_bulk:
                        self._bulk_restore_intent = (bulk_selection, self.model._query,
                                                     self.model._generation,
                                                     mutation_collection_epoch)
                        self._pending_bulk_restore = (self.model._generation, bulk_selection)
                    else:
                        self._bulk_restore_intent = None
                elif bulk_mutation:
                    self._bulk_restore_intent = None
                if reply.status not in ("ok", "completed_no_payload"):
                    self._catalog_failed(reply.message or reply.status)
                if callback is not None:
                    callback(reply)
        request_id, reason = self.catalog_client.submit(
            RequestClass.MUTATION, "mutation", (name, *args), kwargs=kwargs,
            generation=self.model._generation, callback=received, retain=retain)
        if request_id is None:
            self._mutation_pending = False
            restore_bulk = (bulk_selection is not None and
                            self.model._generation == mutation_generation and
                            self._collection_choice_epoch == mutation_collection_epoch)
            self.model.refresh()
            if restore_bulk:
                self._bulk_restore_intent = (bulk_selection, self.model._query,
                                             self.model._generation, mutation_collection_epoch)
                self._pending_bulk_restore = (self.model._generation, bulk_selection)
            else:
                self._bulk_restore_intent = None
            self._catalog_failed(reason)
            if callback is not None:
                callback(CatalogReply(-1, RequestClass.MUTATION, self.model._generation,
                                      "refused", message=reason))
            return False
        return True

    def closeEvent(self, event):
        if not self._close_external_actions(event):
            return
        # Signals already queued by a finishing worker can arrive after waits.
        self._closing = True
        self._metadata_focus_intent = None
        if self._bulk_restore_dispose is not None:
            self._bulk_restore_dispose()
        self._pending_bulk_restore = None
        self._bulk_restore_intent = None
        if self.bulk_curation_dialog is not None:
            self.bulk_curation_dialog.close()
        if self.comparison_dialog is not None and not self.comparison_dialog.close():
            event.ignore()
            return
        if self.cached_dialog is not None and not self.cached_dialog.close():
            event.ignore()
            return
        if self.inspect_dialog is not None and not self.inspect_dialog.close():
            event.ignore()
            return
        if self.recovery_dialog is not None and not self.recovery_dialog.close():
            if not self._recovery_close_pending and self.recovery_dialog.worker is not None:
                self._recovery_close_pending = True
                self.recovery_dialog.worker.finished.connect(
                    lambda: QTimer.singleShot(0, self._retry_recovery_close))
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2_000)
            if self.worker.isRunning():
                if not self._background_close_pending:
                    self._background_close_pending = True
                    self.worker.finished.connect(lambda: QTimer.singleShot(0, self.close))
                event.ignore()
                return
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait()
        if self.thumbnails is not None:
            if not self.thumbnails.stop():
                if not self._thumbnail_close_pending:
                    self._thumbnail_close_pending = True
                    self.thumbnails.finished.connect(lambda: QTimer.singleShot(0, self.close))
                self.statusBar().showMessage("Cache worker cleanup failed; ownership retained" if self.thumbnails.cleanup_failed else "Stopping thumbnail work…")
                event.ignore()
                return
        self.catalog_client.gateway.request_close()
        if not self.catalog_client.gateway.close_complete:
            if not self._gateway_close_pending:
                self._gateway_close_pending = True
                self.catalog_client.gateway.finished.connect(lambda: QTimer.singleShot(0, self.close))
            QTimer.singleShot(100, self.close)
            self.statusBar().showMessage("Finishing catalog work before closing…")
            event.ignore()
            return
        if self._admission_owner is not None:
            try:
                remaining = self._admission_owner.reap_owned_processes()
            except (OSError, ValueError):
                remaining = 1
            if remaining:
                self.statusBar().showMessage("Owned helper cleanup is incomplete; library ownership retained.")
                QTimer.singleShot(100, self.close)
                event.ignore()
                return
        self.model.close()
        super().closeEvent(event)
        if event.isAccepted() and self._admission_owner is not None:
            self._admission_owner.release_coordinator()
            self._admission_owner = None

    def _retry_recovery_close(self):
        self._recovery_close_pending = False
        if self.recovery_dialog is not None and self.recovery_dialog._closing:
            self.close()
        else:
            self._closing = False
            self.statusBar().showMessage("Recovery outcome needs review before this gallery closes.")

    def _invalidate_thumbnails(self, *_args):
        if self.thumbnails is not None:
            self.thumbnails.invalidate_pending()
            self.gallery.viewport().update()

    def _resize_cells(self, value: int):
        self._invalidate_thumbnails()
        self.delegate.set_cell_size(value)
        self.gallery.setGridSize(QSize(value + 8, value + 50))
        self.gallery.doItemsLayout()
        self.gallery.viewport().update()

    def _show_detail(self, current, previous=None):
        if self._closing:
            return
        self._detail_ready_key = None
        if not current.isValid():
            self.detail.clear()
            self.inspect_button.setEnabled(False)
            self.cached_button.setEnabled(False)
            self.curation_button.setEnabled(False)
            self.metadata_button.setEnabled(self.model._actionable and not self._mutation_pending)
            return
        asset = self.model.loaded_asset_at(current.row())
        if asset is None or not asset.get("targetable", False):
            self.detail.setPlainText("Catalog row is loading or unavailable.")
            self.inspect_button.setEnabled(False)
            self.cached_button.setEnabled(False)
            self.curation_button.setEnabled(False)
            self.metadata_button.setEnabled(False)
            return
        for button in (self.inspect_button, self.cached_button, self.curation_button,
                       self.metadata_button, self.curate_button):
            button.setEnabled(False)
        self.detail.setPlainText("Loading captured catalog detail…")
        selected_id, revision, generation = asset["asset_id"], asset["revision"], self.model._generation
        token = self.model._token
        def received(value, error):
            if (self._closing or generation != self.model._generation or
                    token != self.model._token or not self.model._actionable):
                return
            selected = self._loaded_focused_asset()
            if selected is None or (selected["asset_id"], selected["revision"]) != (selected_id, revision):
                return
            if error or value is None or not value.value["asset"].get("targetable", False):
                self.detail.setPlainText(error or value.reason or "Catalog detail unavailable")
                self._detail_ready_key = None
                self._update_selection_controls()
                self._update_collection_controls()
                self._update_external_controls()
                return
            self._detail_ready_key = (generation, token, selected_id, revision)
            self.detail.setPlainText((value.reason + "\n" if value.incomplete else "") +
                                     json.dumps(value.value, indent=2))
            self.inspect_button.setEnabled(not self._restore_pending and
                                           generation_refusal(selected) is None and
                                           selected["media_type"].startswith("image/"))
            self.cached_button.setEnabled(selected["media_type"].startswith("image/"))
            self.curation_button.setEnabled(True)
            self.metadata_button.setEnabled(True)
            self._update_selection_controls()
            self._update_collection_controls()
            self._update_external_controls()
        self.model.request_detail(asset, received)

    def inspect_selected(self):
        if self._closing:
            return None
        if self._restore_pending:
            self.statusBar().showMessage("Restored catalog is browse-only; review roots before original inspection.")
            return None
        asset = self._selected_asset()
        if asset is None:
            return None
        reason = generation_refusal(asset)
        if reason:
            self.statusBar().showMessage(reason + "; use View cached preview")
            return None
        if not self._close_other_viewers("inspect_dialog"):
            return None
        if self.inspect_dialog is not None:
            if not self.inspect_dialog.close():
                return self.inspect_dialog
        self.inspect_dialog = FullImageDialog(asset, self, database=self.database)
        self.inspect_dialog.show()
        return self.inspect_dialog

    def open_recovery(self):
        if self._closing:
            return None
        if not self._startup_validated or self._recovery_catalog_identity is None:
            self.statusBar().showMessage("Library recovery state is still loading; retry when the gallery is ready.")
            return None
        if self.recovery_dialog is None or not qt_is_valid(self.recovery_dialog):
            # This gallery manages one thumbnail/cache root; capture it for the
            # Core placement check even when thumbnail generation is disabled.
            self.recovery_dialog = RecoveryDialog(self.database, (self.cache_root,), self,
                                                  catalog_identity=self._recovery_catalog_identity)
            self.recovery_dialog.catalogChanged.connect(self._recovery_catalog_changed)
        self.recovery_dialog.show()
        self.recovery_dialog.raise_()
        return self.recovery_dialog

    def _set_recovery_state(self, state, epoch):
        if epoch != self._recovery_state_epoch:
            return
        self._restore_pending = state["state"] != "active"
        self._source_selected()
        self._update_action_controls()

    def _recovery_catalog_changed(self, result):
        self._recovery_state_epoch += 1
        token = result.get("view_epoch")
        if token != (self._selection_epoch, self.model._generation) and not self._closing:
            self.statusBar().showMessage("Recovery completed after the gallery view changed; current selection kept.")
        self._restore_pending = result["result"].get("state") == "restore_pending"
        if self._closing:
            return
        self.refresh_sources()
        self._invalidate_thumbnails()
        self._update_action_controls()

    def _update_external_controls(self, *_args):
        super()._update_external_controls(*_args)
        try:
            asset = self._selected_asset()
            reason = generation_refusal(asset) if asset is not None else None
        except (ValueError, IndexError, sqlite3.Error):
            reason = "Selected asset is unavailable or unresolved"
        if reason or self._restore_pending:
            self.open_external_button.setEnabled(False)
            self.open_folder_button.setEnabled(False)
            if self.external_worker is None and not self._closing:
                self.external_feedback.setText(reason or "Restored catalog is browse-only until root review")

    def view_cached_selected(self):
        if self._closing:
            return None
        asset = self._selected_asset()
        if asset is None or not asset["media_type"].startswith("image/"):
            return None
        if not self._close_other_viewers("cached_dialog"):
            return None
        if self.cached_dialog is not None and not self.cached_dialog.close():
            return self.cached_dialog
        try:
            self.cached_dialog = CachedPreviewDialog(self.database, asset, self.cache_root, self)
        except (ValueError, KeyError, TypeError) as exc:
            self.statusBar().showMessage(f"Cached preview refused: invalid indexed identity: {exc}")
            return None
        self.cached_dialog.show()
        return self.cached_dialog

    def _close_other_viewers(self, except_name):
        for name in ("inspect_dialog", "cached_dialog", "comparison_dialog"):
            dialog = getattr(self, name)
            if name != except_name and dialog is not None and not dialog.close():
                self.statusBar().showMessage("Previous viewer still owns helper cleanup; wait or retry its Close action.")
                return False
        return True

    def compare_selected(self):
        if self._closing:
            return None
        # Count ranges first; never materialize an unbounded selectedIndexes list.
        if self._selection_count() != 2:
            self.statusBar().showMessage("Select exactly two distinct supported images to compare.")
            return None
        try:
            rows = sorted({index.row() for index in self.gallery.selectionModel().selectedIndexes()})
            assets = [dict(self.model.asset_at(row)) for row in rows]
            if len(assets) != 2 or len({asset["asset_id"] for asset in assets}) != 2:
                raise ValueError("Select exactly two distinct images")
            # Constructor validates all media before any helper starts.
            from prototypes.qt.preview import SUPPORTED_MEDIA
            if any(asset["media_type"] not in SUPPORTED_MEDIA for asset in assets):
                raise ValueError("Select two PNG, JPEG, GIF or WebP images")
            if not self._close_other_viewers("comparison_dialog"):
                return None
            if self.comparison_dialog is not None and not self.comparison_dialog.close():
                self.statusBar().showMessage("Comparison cleanup pending; captured panes retained. Retry Close before replacing.")
                return None
            self.comparison_dialog = ComparisonDialog(self.database, self.cache_root, assets, self,
                                                       originals_allowed=not self._restore_pending)
            self.comparison_dialog.show()
            return self.comparison_dialog
        except (ValueError, KeyError, TypeError, IndexError, sqlite3.Error) as exc:
            self.statusBar().showMessage(f"Comparison refused: {exc}; refresh and select two images.")
            return None

    def edit_curation(self):
        asset = self._selected_asset()
        if asset is None:
            return None
        try:
            if self.curation_dialog is not None:
                self.curation_dialog.close()
            editor = CurationDialog(self.database, asset["asset_id"], Path(asset["current_path"]).name,
                                    self, catalog_window=self)
            editor.saved.connect(lambda _asset_id: self._curation_focus_saved(editor._focus_continuation))
            self.curation_dialog = editor
            editor.show()
            return editor
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Rating and favorite not opened", str(exc))
            return None

    def _curation_saved(self, asset_id):
        if self._closing:
            return
        if self.model._actionable:
            self._restore_asset_selection(asset_id)
        else:
            self._restore_after_publish(asset_id)

    def _capture_curation_focus(self):
        asset = self._loaded_focused_asset()
        return (asset["asset_id"] if asset is not None else None, self._selection_epoch)

    def _capture_metadata_focus(self):
        """Keep the gallery's current UUID through rapid edits of another asset."""
        asset = self._loaded_focused_asset() if self.model._actionable else None
        if asset is not None:
            intent = (asset["asset_id"], self._selection_epoch,
                      self.model._query, self._collection_choice_epoch)
            self._metadata_focus_intent = intent
            return intent
        intent = self._metadata_focus_intent
        if (intent is not None and intent[1] == self._selection_epoch and
                intent[2] == self.model._query and
                intent[3] == self._collection_choice_epoch):
            return intent
        return None

    def _metadata_focus_after_write(self, intent, reply):
        if self._closing or intent is None or reply.status == "refused":
            return
        if reply.status in ("catalog_replaced", "catalog_unavailable"):
            self._metadata_focus_intent = None
            return
        if (intent != self._metadata_focus_intent or
                intent[1] != self._selection_epoch or
                intent[2] != self.model._query or
                intent[3] != self._collection_choice_epoch):
            return
        self._restore_after_publish(intent[0], expected_selection_epoch=intent[1])

    def _curation_focus_saved(self, continuation):
        if self._closing or continuation is None:
            return
        asset_id, epoch = continuation
        if epoch == self._selection_epoch:
            self._restore_after_publish(asset_id, expected_selection_epoch=epoch)

    def _selection_count(self):
        return sum(item.width() * item.height() for item in self.gallery.selectionModel().selection())

    def _capture_bulk_selection(self):
        count = self._selection_count()
        if not 1 <= count <= curation.MAX_BATCH_TARGETS or not self.model._actionable:
            return None
        indexes = sorted(self.gallery.selectionModel().selectedIndexes(), key=lambda index: index.row())
        if len(indexes) != count:
            return None
        assets = [self.model.loaded_asset_at(index.row()) for index in indexes]
        if any(asset is None or not asset.get("targetable", False) for asset in assets):
            return None
        focused = self._loaded_focused_asset()
        return (tuple((asset["asset_id"], asset["revision"]) for asset in assets),
                focused["asset_id"] if focused is not None else None,
                self._selection_epoch)

    def _restore_bulk_selection(self, continuation):
        captured, focused_id, epoch = continuation
        generation, token = self.model._generation, self.model._token
        rows = []

        def clear_intent():
            intent = self._bulk_restore_intent
            if intent is not None and intent[0] == continuation and intent[2] == generation:
                self._bulk_restore_intent = None

        disposed = False
        def dispose_restore():
            nonlocal disposed
            if disposed:
                return
            disposed = True
            try:
                self.model.actionabilityChanged.disconnect(actionability_changed)
            except RuntimeError:
                pass
            if self._bulk_restore_dispose is dispose_restore:
                self._bulk_restore_dispose = None

        def actionability_changed(actionable):
            if not actionable:
                clear_intent()
                dispose_restore()

        if self._bulk_restore_dispose is not None:
            self._bulk_restore_dispose()
        self._bulk_restore_dispose = dispose_restore
        self.model.actionabilityChanged.connect(actionability_changed)

        def current():
            return (not self._closing and self.model._actionable and
                    self.model._generation == generation and self.model._token == token and
                    self._selection_epoch == epoch)

        def refuse(message):
            if current():
                clear_intent()
                dispose_restore()
                self.selection_label.setText(f"Bulk selection could not be restored: {message}")

        def finish():
            if not current():
                clear_intent()
                dispose_restore()
                return
            clear_intent()
            dispose_restore()
            if not rows:
                return
            selection = self.gallery.selectionModel()
            self._clearing_gallery_selection = True
            try:
                selection.clearSelection()
                for _asset_id, row in rows:
                    selection.select(self.model.index(row), QItemSelectionModel.SelectionFlag.Select)
                focus_row = next((row for asset_id, row in rows if asset_id == focused_id), rows[0][1])
                selection.setCurrentIndex(self.model.index(focus_row),
                                          QItemSelectionModel.SelectionFlag.NoUpdate)
            finally:
                self._clearing_gallery_selection = False
            self._update_selection_controls()
            self.gallery.scrollTo(self.model.index(focus_row))

        def advance(position):
            if not current():
                clear_intent()
                dispose_restore()
                return
            if position == len(captured):
                finish()
                return
            asset_id, _old_revision = captured[position]

            def ranked(row, error):
                if not current():
                    clear_intent()
                    dispose_restore()
                    return
                if error:
                    refuse(error)
                    return
                if row is None:
                    advance(position + 1)
                    return
                page = row // self.model.page_size

                def loaded():
                    if not current():
                        return
                    asset = self.model.loaded_asset_at(row)
                    if asset is None or asset["asset_id"] != asset_id or not asset.get("targetable", False):
                        refuse("captured row changed while loading")
                        return
                    rows.append((asset_id, row))
                    advance(position + 1)

                if page in self.model._cache:
                    loaded()
                    return

                def page_done(reply_generation, reply_page):
                    if reply_generation == generation and reply_page == page:
                        dispose()
                        loaded()

                def page_failed(_message):
                    if not current() or page in self.model._failed_pages:
                        dispose()
                        if current():
                            refuse(self.model._failed_pages.get(page, "gallery view changed"))

                def actionability_changed(actionable):
                    if not actionable:
                        dispose()

                disposed = False
                def dispose():
                    nonlocal disposed
                    if disposed:
                        return
                    disposed = True
                    for signal, callback in ((self.model.pagePublished, page_done),
                                             (self.model.loadFailed, page_failed),
                                             (self.model.actionabilityChanged, actionability_changed)):
                        try:
                            signal.disconnect(callback)
                        except RuntimeError:
                            pass

                self.model.pagePublished.connect(page_done)
                self.model.loadFailed.connect(page_failed)
                self.model.actionabilityChanged.connect(actionability_changed)
                self.model.request_page(page)
                if page in self.model._failed_pages:
                    page_failed(self.model._failed_pages[page])
                def timed_out():
                    if not disposed:
                        dispose()
                        refuse("page load timed out")
                QTimer.singleShot(5000, timed_out)

            self.model.request_rank(asset_id, ranked)

        advance(0)

    def _clear_gallery_selection(self):
        self._clearing_gallery_selection = True
        try:
            self.gallery.selectionModel().clear()
        finally:
            self._clearing_gallery_selection = False

    def _update_selection_controls(self, *_args):
        if self._closing:
            return
        count = self._selection_count()
        focused = self._loaded_focused_asset()
        label = f"{count} selected. Single-asset actions use focused "
        label += f"{Path(focused['current_path']).name} (ID: {focused['asset_id']})." if focused else "asset: none."
        if count > curation.MAX_BATCH_TARGETS:
            label += f" Bulk operation limit: {curation.MAX_BATCH_TARGETS}; reduce selection."
        self.selection_label.setText(label)
        ready = self.model._actionable and not self._mutation_pending
        loaded_selection = (ready and 1 <= count <= curation.MAX_BATCH_TARGETS and
                            all((asset := self.model.loaded_asset_at(index.row())) is not None
                                and asset.get("targetable", False)
                                for index in self.gallery.selectionModel().selectedIndexes()))
        self.bulk_curation_button.setEnabled(bool(loaded_selection))
        self.compare_button.setEnabled(bool(loaded_selection and count == 2))
        self.curate_button.setEnabled(ready and self._selected_asset() is not None)

    def _open_bulk_dialog(self, targets, *, history_only=False):
        if self.bulk_curation_dialog is not None:
            self.bulk_curation_dialog.close()
        editor = BulkCurationDialog(self.database, targets, self, history_only=history_only,
                                    catalog_window=self)
        self.bulk_curation_dialog = editor
        editor.show()
        return editor

    def edit_bulk_curation(self):
        count = self._selection_count()
        if not 1 <= count <= curation.MAX_BATCH_TARGETS:
            self.selection_label.setText(f"Select between 1 and {curation.MAX_BATCH_TARGETS} assets for a bulk operation.")
            return None
        # Check ranges first; selectedIndexes can otherwise materialize the whole catalog.
        try:
            rows = sorted(self.gallery.selectionModel().selectedIndexes(), key=lambda index: index.row())
            targets = tuple(curation.CapturedTarget(asset["asset_id"], asset["revision"])
                            for index in rows for asset in (self.model.asset_at(index.row()),))
            return self._open_bulk_dialog(targets)
        except (ValueError, IndexError, OSError, sqlite3.Error) as exc:
            self.selection_label.setText(f"Bulk editor could not be opened: {exc}")
            return None

    def open_curation_history(self):
        # History has no new-edit target; it remains available with no selected assets.
        def received(groups):
            if not groups:
                self.selection_label.setText("No recorded bulk groups yet.")
                return
            editor = self._open_bulk_dialog((), history_only=True)
            editor.refresh_history(groups[0]["batch_id"])
        self._legacy("bulk-history-opening", "list_curation_batches", kwargs={"limit": 1}, callback=received)
        return None

    def _edit_metadata(self):
        asset = self._selected_asset()
        if self.gallery.currentIndex().isValid() and asset is None:
            self.statusBar().showMessage("Captured detail is not ready for metadata assignment")
            return
        asset_id = asset["asset_id"] if asset else None
        label = Path(asset["current_path"]).name if asset else None
        try:
            editor = MetadataEditor(self.database, asset_id, label, self,
                                    catalog_window=self)
            editor.changed.connect(lambda: self._show_detail(self.gallery.currentIndex()))
            editor.exec()
            self._show_detail(self.gallery.currentIndex())
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Metadata not opened", str(exc))

    def _loaded_focused_asset(self) -> dict | None:
        current = self.gallery.currentIndex()
        asset = (self.model.loaded_asset_at(current.row()) if current.isValid() and
                 0 <= current.row() < self.model.rowCount() else None)
        return asset if asset is not None and asset.get("targetable", False) else None

    def _selected_asset(self) -> dict | None:
        asset = self._loaded_focused_asset()
        if asset is None or self._mutation_pending:
            return None
        key = (self.model._generation, self.model._token,
               asset["asset_id"], asset["revision"])
        return asset if self._detail_ready_key == key else None

    def refresh_collections(self, *, preferred_id=None, prefer=False,
                            preferred_epoch=None, force_view=False,
                            restore_id=None, restore_epoch=None,
                            restore_choice_epoch=None):
        if self._closing:
            return
        selected = self.collection_box.currentData()
        choice_epoch = self._collection_choice_epoch
        self._legacy("collections", "list_collections",
                     callback=lambda records: self._publish_collections(
                         records, selected, choice_epoch, preferred_id, prefer,
                         preferred_epoch, force_view, restore_id, restore_epoch,
                         restore_choice_epoch),
                     on_error=lambda error: self._collection_list_failed(error, force_view))

    def _collection_list_failed(self, error, force_view):
        if self._closing:
            return
        self.collection_feedback.setText(f"Collections could not be loaded: {error}")
        if force_view:
            self.model.refresh()

    def _publish_collections(self, records, selected, choice_epoch,
                             preferred_id, prefer, preferred_epoch,
                             force_view, restore_id, restore_epoch,
                             restore_choice_epoch):
        if self._closing:
            return
        user_changed_choice = self._collection_choice_epoch != choice_epoch
        desired = self.collection_box.currentData() if user_changed_choice else selected
        if (prefer and not user_changed_choice and
                (preferred_epoch is None or preferred_epoch == self._collection_choice_epoch)):
            desired = preferred_id
        valid_ids = {record["collection_id"] for record in records}
        if desired is not None and desired not in valid_ids:
            desired = None
        self.collection_records = records
        self.collection_box.blockSignals(True)
        self.collection_box.clear()
        self.collection_box.addItem("All assets", None)
        for record in self.collection_records:
            self.collection_box.addItem(record["name"], record["collection_id"])
        self.collection_box.setCurrentIndex(max(0, self.collection_box.findData(desired)))
        self.collection_box.blockSignals(False)
        base_changed = self.model._collection_id != desired
        if base_changed:
            self.model.set_collection(desired)
        elif force_view:
            self.model.refresh()
        self._update_collection_controls()
        if (force_view and not user_changed_choice and
                (restore_choice_epoch is None or
                 restore_choice_epoch == self._collection_choice_epoch)):
            self._restore_after_publish(restore_id,
                                        expected_selection_epoch=restore_epoch)

    def _update_collection_controls(self, *unused):
        if not hasattr(self, "collection_box") or self._closing:
            return
        selected = self._loaded_focused_asset() is not None
        ready = self.model._actionable and not self._mutation_pending
        collection_id = self.collection_box.currentData()
        in_collection = collection_id is not None
        self.create_collection_button.setEnabled(ready)
        self.rename_collection_button.setEnabled(ready and in_collection)
        self.delete_collection_button.setEnabled(ready and in_collection)
        self.add_member_button.setEnabled(ready and selected and bool(self.collection_records))
        self.remove_member_button.setEnabled(ready and selected and in_collection)
        filtered = self.model.has_active_filters
        movable = ready and selected and in_collection and not filtered
        row = self.gallery.currentIndex().row()
        self.move_up_button.setEnabled(movable and row > 0)
        self.move_down_button.setEnabled(movable and row + 1 < self.model.rowCount())
        guidance = "Clear all filters to reorder the complete collection." if filtered else \
                   "Move the selected member one place in the collection."
        self.move_up_button.setToolTip(guidance)
        self.move_down_button.setToolTip(guidance)

    def _restore_asset_selection(self, asset_id: str | None):
        if self._closing:
            return
        if self.model.read_mode == "async":
            if asset_id is None:
                self.gallery.setCurrentIndex(QModelIndex())
                return
            generation = self.model._generation
            token = self.model._token
            selection_epoch = self._selection_epoch
            metadata_intent = self._metadata_focus_intent
            def finish_metadata_intent():
                # An old rank/page reply cannot erase a continuation carried
                # into a newer write or a different user choice.
                if (metadata_intent is not None and
                        self._metadata_focus_intent == metadata_intent and
                        metadata_intent[0] == asset_id and
                        self.model._generation == generation):
                    self._metadata_focus_intent = None
            def current():
                return (not self._closing and self.model._actionable and
                        self.model._generation == generation and self.model._token == token and
                        self._selection_epoch == selection_epoch)
            def ranked(row, error):
                if not current():
                    return
                if error or row is None:
                    finish_metadata_intent()
                    self.gallery.setCurrentIndex(QModelIndex())
                    return
                connected = False
                disposed = False
                def dispose():
                    nonlocal disposed
                    if disposed:
                        return
                    disposed = True
                    if connected:
                        for signal, callback in ((self.model.pagePublished, select_loaded),
                                                 (self.model.loadFailed, failed),
                                                 (self.model.actionabilityChanged, changed)):
                            try:
                                signal.disconnect(callback)
                            except RuntimeError:
                                pass
                def select_loaded(*_):
                    if disposed:
                        return
                    if not current():
                        dispose()
                        return
                    asset = self.model.loaded_asset_at(row)
                    if asset is None:
                        return
                    dispose()
                    if asset["asset_id"] != asset_id:
                        finish_metadata_intent()
                        self._catalog_failed("Captured selection changed while loading its page")
                        return
                    index = self.model.index(row)
                    self.gallery.setCurrentIndex(index)
                    self.gallery.scrollTo(index)
                    finish_metadata_intent()
                def failed(_message):
                    # loadFailed is model-wide. Another requested page may
                    # fail while this row's page is still due to succeed.
                    if row // self.model.page_size in self.model._failed_pages:
                        if current():
                            finish_metadata_intent()
                        dispose()
                def changed(actionable):
                    if not actionable:
                        if not self._mutation_pending and self.model._token is None:
                            # Typed unavailable/replaced invalidation has no
                            # fresh publication to finish this old restore.
                            if self._metadata_focus_intent == metadata_intent:
                                self._metadata_focus_intent = None
                        dispose()
                if self.model.loaded_asset_at(row) is None:
                    connected = True
                    self.model.pagePublished.connect(select_loaded)
                    self.model.loadFailed.connect(failed)
                    self.model.actionabilityChanged.connect(changed)
                    self.model.request_page(row // self.model.page_size)
                    def timed_out():
                        if not disposed:
                            if current():
                                finish_metadata_intent()
                            dispose()
                    QTimer.singleShot(2500, timed_out)
                else:
                    select_loaded()
            self.model.request_rank(asset_id, ranked)
            return
        row = self.model.row_for_asset(asset_id) if asset_id is not None else None
        stale = asset_id is not None and row is None
        if row is not None:
            try:
                stale = (row >= self.model.rowCount() or
                         self.model.asset_at(row)["asset_id"] != asset_id)
            except IndexError:
                # Membership can shrink after rank lookup, before lazy fetch.
                stale = True
        if stale:
            # Repair count/cache for later paints and never select a replacement
            # UUID at the old rank, including when its page is now shorter.
            self.model.refresh()
            row = None
        current = self.model.index(row) if row is not None else QModelIndex()
        self.gallery.setCurrentIndex(current)
        if row is not None:
            self.gallery.scrollTo(current)
        self._show_detail(current)
        self._update_collection_controls()

    def _collection_selected(self):
        if self._closing:
            return
        self._collection_choice_epoch += 1
        self._metadata_focus_intent = None
        asset = self._loaded_focused_asset()
        self.model.set_collection(self.collection_box.currentData())
        self._restore_after_publish(asset["asset_id"] if asset else None)
        self.statusBar().showMessage(f"{self.model.rowCount():,} matching assets")

    def _refresh_collection_view(self, asset_id: str | None = None):
        if self._closing:
            return
        asset = self._loaded_focused_asset()
        restore_id = asset_id if asset_id is not None else (asset["asset_id"] if asset else None)
        restore_epoch = self._selection_epoch
        choice_epoch = self._collection_choice_epoch
        self.model.invalidate_for_mutation()
        self.refresh_collections(force_view=True, restore_id=restore_id,
                                 restore_epoch=restore_epoch,
                                 restore_choice_epoch=choice_epoch)
        self.statusBar().showMessage("Refreshing collection view…")

    def _restore_after_publish(self, asset_id, *, expected_selection_epoch=None):
        if (expected_selection_epoch is not None and
                expected_selection_epoch != self._selection_epoch):
            return
        if self.model._actionable:
            self._restore_asset_selection(asset_id)
        else:
            self._pending_restore = (self.model._generation, asset_id, expected_selection_epoch)

    def _change_collection(self, name: str, *args, **kwargs):
        if self._closing:
            return False
        restore_id = self._loaded_focused_asset()
        restore_id = restore_id["asset_id"] if restore_id else None
        restore_epoch = self._selection_epoch
        choice_epoch = self._collection_choice_epoch
        def received(reply):
            if self._closing:
                return
            if reply.status == "refused":
                self.collection_feedback.setText(reply.message)
                return
            if reply.status in ("catalog_replaced", "catalog_unavailable"):
                self.collection_feedback.setText(reply.message or reply.status)
                return
            prefer = name == "create_collection" and reply.status == "ok"
            preferred_id = reply.value["collection_id"] if prefer else None
            self.refresh_collections(preferred_id=preferred_id, prefer=prefer,
                                     preferred_epoch=choice_epoch, force_view=True,
                                     restore_id=restore_id, restore_epoch=restore_epoch,
                                     restore_choice_epoch=choice_epoch)
            self.collection_feedback.setText("Collection saved." if reply.status == "ok" else
                                             reply.message or reply.status)
        return self._mutate_catalog(name, args, kwargs=kwargs, callback=received,
                                    refresh_after=False)

    def _create_collection(self):
        if self._closing:
            return
        name, accepted = QInputDialog.getText(self, "New collection", "Collection name:")
        if accepted:
            self._change_collection("create_collection", name)

    def _rename_collection(self):
        if self._closing:
            return
        collection_id = self.collection_box.currentData()
        if collection_id is None:
            return
        name = self.collection_box.currentText()
        replacement, accepted = QInputDialog.getText(self, "Rename collection", "Collection name:",
                                                     QLineEdit.EchoMode.Normal, name)
        if accepted:
            self._change_collection("rename_collection", collection_id, replacement)

    def _delete_collection(self):
        if self._closing:
            return
        collection_id = self.collection_box.currentData()
        if collection_id is None:
            return
        name = self.collection_box.currentText()
        answer = QMessageBox.question(self, "Delete collection", f'Delete “{name}”?\n'
                                     "Only this collection and its membership are removed. "
                                     "Library assets and original files are kept.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._change_collection("delete_collection", collection_id)

    def _add_collection_member(self):
        if self._closing:
            return
        asset = self._loaded_focused_asset()
        records = list(self.collection_records)
        if asset is None or not records:
            return
        names = [record["name"] for record in records]
        selected = self.collection_box.currentData()
        default = next((index for index, record in enumerate(records)
                        if record["collection_id"] == selected), 0)
        name, accepted = QInputDialog.getItem(self, "Add to collection",
            f'Add {Path(asset["current_path"]).name} to:', names, default, False)
        if accepted:
            target = records[names.index(name)]["collection_id"]
            self._change_collection("add_member", target, asset["asset_id"])

    def _remove_collection_member(self):
        if self._closing:
            return
        collection_id, asset = self.collection_box.currentData(), self._loaded_focused_asset()
        if collection_id is not None and asset is not None:
            self._change_collection("remove_member", collection_id, asset["asset_id"])

    def _move_collection_member(self, direction: int):
        if self._closing:
            return
        if self.model.has_active_filters:
            self.collection_feedback.setText("Clear all filters before moving collection members.")
            return
        collection_id, asset = self.collection_box.currentData(), self._loaded_focused_asset()
        row = self.gallery.currentIndex().row()
        neighbor_row = row + direction
        if collection_id is None or asset is None or not 0 <= neighbor_row < self.model.rowCount():
            return
        neighbor = self.model.loaded_asset_at(neighbor_row)
        if neighbor is None or not neighbor.get("targetable", False):
            self.collection_feedback.setText("Neighbor row is loading; retry when it appears.")
            return
        neighbor_id = neighbor["asset_id"]
        self._change_collection("move_member", collection_id, asset["asset_id"],
                                direction=direction, expected_neighbor_id=neighbor_id)

    def refresh_sources(self):
        selected = self.source_box.currentData()
        self._legacy("sources", "list_sources",
                     callback=lambda records: self._publish_sources(records, selected))

    def _publish_sources(self, records, selected, *, prefer_selected=False):
        if not prefer_selected and self.source_box.currentData() != selected:
            selected = self.source_box.currentData()
        self._source_records = list(records)
        self.source_box.blockSignals(True)
        self.source_box.clear()
        self.source_box.addItem("All sources", None)
        for source in records:
            label = (f"{source['name']} · {source['health']} · "
                     f"{source['existing_file_policy'].replace('_', ' ')}")
            self.source_box.addItem(label, source["source_id"])
            self.source_box.setItemData(self.source_box.count() - 1, source["root_path"],
                                        Qt.ItemDataRole.ToolTipRole)
        index = self.source_box.findData(selected)
        self.source_box.setCurrentIndex(max(0, index))
        self.source_box.blockSignals(False)
        self._source_selected()

    def _source_selected(self):
        source_id = self.source_box.currentData()
        source = next((item for item in self._source_records
                       if item["source_id"] == source_id), None)
        held = bool(source and source.get("health_detail") ==
                    "Restored root requires explicit review before enable")
        self.scan_button.setEnabled(source_id is not None and not self._restore_pending
                                    and not held and bool(source and source.get("enabled"))
                                    and not (self.scan_worker and self.scan_worker.isRunning()))
        self.refresh_source_issues()
        if source_id:
            if source:
                detail = ("Stored root awaits explicit review; original access and scans are disabled."
                          if held or self._restore_pending else
                          source["health_detail"] or "Ready for an explicit scan.")
                self.scan_status.setText(f"{source['health'].title()}: {detail}")
        self.gallery.viewport().update()

    def _source_choice_changed(self):
        self._source_choice_epoch += 1
        self._source_selected()

    def refresh_source_issues(self):
        self.issues_list.clear()
        source_id = self.source_box.currentData()
        if source_id is None:
            return
        self._legacy("source-issues", "source_issues", (source_id,),
                     callback=lambda rows: self._publish_source_issues(source_id, rows))

    def _publish_source_issues(self, source_id, rows):
        if source_id != self.source_box.currentData():
            return
        for row in rows:
            label = f"{row['disposition']}: {Path(row['current_path']).name}"
            if row["last_error"]:
                label += f" · {row['last_error']}"
            item = QListWidgetItem(label)
            item.setToolTip(row["current_path"])
            self.issues_list.addItem(item)

    def _apply_curation_filters(self):
        self._apply_gallery_filters()

    def _apply_metadata_filters(self):
        self._apply_gallery_filters()

    def _add_source_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose read-only artwork source")
        if not folder:
            return
        choices = ["Inbox", "Reviewed", "Ignore Until Modified"]
        choice, accepted = QInputDialog.getItem(
            self, "Existing files", "How should files already here enter the library?",
            choices, 0, False,
        )
        if not accepted:
            return
        policy = {"Inbox": "inbox", "Reviewed": "reviewed",
                  "Ignore Until Modified": "ignore_until_modified"}[choice]
        try:
            assert_library_locations(self.database, self.cache_root, Path(folder))
            assert_outside_sources(self.private_root, [Path(folder)])
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Source not added", str(exc))
            return
        selection_at_request = self.source_box.currentData()
        choice_epoch_at_request = self._source_choice_epoch
        def received(reply):
            if self._closing:
                return
            if reply.status != "ok":
                QMessageBox.warning(self, "Source not added", reply.message or reply.status)
                return
            source_id = reply.value["source_id"]
            self._legacy("sources", "list_sources", callback=lambda records:
                self._source_added(records, source_id, selection_at_request,
                                   choice_epoch_at_request))
        self._mutate_catalog("add_source", (Path(folder),),
                             kwargs={"existing_file_policy": policy}, callback=received)

    def _source_added(self, records, source_id, selection_at_request, choice_epoch_at_request):
        self._publish_sources(records, source_id,
                              prefer_selected=(self.source_box.currentData() == selection_at_request
                                               and self._source_choice_epoch == choice_epoch_at_request))
        self._source_selected()
        self.scan_status.setText("Source added. Scan observes stable files; it does not watch continuously.")

    def start_source_scan(self):
        if self._admission_owner is not None:
            try:
                self._admission_owner.validate()
            except ValueError as exc:
                self.statusBar().showMessage(str(exc))
                return
        source_id = self.source_box.currentData()
        if not source_id or (self.scan_worker and self.scan_worker.isRunning()):
            return
        self.scan_worker = ScanWorker(
            self.database, source_id, parent=self
        )
        self.scan_worker.progressChanged.connect(self._scan_progress)
        self.scan_worker.resultReady.connect(self._scan_result)
        self.scan_worker.failed.connect(self._scan_failed)
        self.scan_worker.finished.connect(self._scan_finished)
        self.scan_button.setEnabled(False)
        self.cancel_scan_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.scan_status.setText("Enumerating source…")
        self.scan_worker.start()

    def cancel_source_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_status.setText("Stopping after the current file; observations are retained.")

    def _scan_progress(self, state: dict):
        if self._closing:
            return
        phase = state["phase"]
        if phase == "enumerating":
            self.progress.setRange(0, 0)
            self.scan_status.setText(f"Enumerated {state['enumerated']:,} files…")
        elif phase == "processing":
            self.progress.setRange(0, max(1, state["total"]))
            self.progress.setValue(state["processed"])
            self.scan_status.setText(
                f"Processing {state['processed']:,} of {state['total']:,} files…"
            )
        elif phase == "quiet_interval":
            self.progress.setRange(0, 0)
            self.scan_status.setText("Waiting for files to remain stable before the second pass…")

    def _scan_result(self, result: dict):
        if self._closing:
            return
        self._refresh_collection_view()
        self.refresh_sources()
        self.refresh_source_issues()
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if not result["canceled"] else 0)
        totals = result["totals"]
        health = result["sources"][0]["health"] if result["sources"] else "paused"
        self.scan_status.setText(
            f"{health.title()}{' (canceled)' if result['canceled'] else ''}: "
            f"{totals['indexed']} indexed, {totals['pending']} pending, "
            f"{totals['ignored_existing']} skipped by policy, "
            f"{totals['overlap_skipped']} overlap skipped, "
            f"{totals['unsupported']} unsupported, {totals['errors']} errors. "
            f"{'Scan source again to resume' if result['canceled'] else 'Use Scan source to rescan'}; "
            "no continuous watcher is running."
        )
        self.statusBar().showMessage(f"{self.model.rowCount():,} matching assets")

    def _scan_failed(self, error: str):
        if self._closing:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.scan_status.setText(f"Scan error: {error}")
        self.refresh_sources()

    def _scan_finished(self):
        if self._closing:
            return
        self.cancel_scan_button.setEnabled(False)
        self.scan_button.setEnabled(self.source_box.currentData() is not None)

    def refresh_duplicates(self):
        self.duplicates_list.clear()
        self._legacy("duplicates", "duplicates", callback=self._publish_duplicates)

    def _publish_duplicates(self, groups):
        for group in groups:
            item = QListWidgetItem(f"{group['asset_count']} copies · SHA-256 {group['sha256'][:12]}…")
            item.setData(Qt.ItemDataRole.UserRole, group["sha256"])
            self.duplicates_list.addItem(item)
        self.statusBar().showMessage(f"{self.duplicates_list.count()} exact-duplicate groups")

    def _duplicate_selected(self, item: QListWidgetItem):
        self._draft_duplicate_digest = item.data(Qt.ItemDataRole.UserRole)
        self._duplicate_draft_touched = True
        self._draft_edited()
        self.filter_feedback.setText("Exact duplicate digest selected in draft. Apply to filter the gallery.")

    def _clear_duplicate_draft(self):
        self._draft_duplicate_digest = None
        self._duplicate_draft_touched = True
        self._draft_edited()

    def _curate_selected(self):
        index = self.gallery.currentIndex()
        if not index.isValid():
            QMessageBox.information(self, "Select an asset", "Select one image first.")
            return
        asset = self._selected_asset()
        if asset is None:
            return
        anonymous_id, accepted = QInputDialog.getText(
            self, "Private evaluation", "Anonymous character ID (for example character-001):"
        )
        if not accepted:
            return
        role, accepted = QInputDialog.getItem(
            self, "Private evaluation", "Role:",
            ["reference", "query", "near-lookalike-negative"], 0, False,
        )
        if not accepted:
            return
        rights, accepted = QInputDialog.getItem(
            self, "Private evaluation", "Rights status:",
            ["artist_owned", "permission_granted", "uncertain"], 2, False,
        )
        if not accepted:
            return
        notes, accepted = QInputDialog.getMultiLineText(
            self, "Private evaluation", "Optional private notes:"
        )
        if not accepted:
            return
        key = hashlib.sha256(str(self.database).encode()).hexdigest()[:16]
        def received(reply):
            if self._closing:
                return
            if reply.status != "ok":
                QMessageBox.warning(self, "Selection not saved", reply.message or reply.status)
            else:
                self.statusBar().showMessage("Private selection saved outside the artwork source.")
        self._mutate_catalog("private_select",
            (self.private_root / f"{key}.private.sqlite3", asset["asset_id"],
             anonymous_id, role, rights, notes), callback=received)

    def set_selected_state(self, state: str):
        asset = self._loaded_focused_asset()
        if asset is None:
            return
        asset_id = asset["asset_id"]
        def received(reply):
            if self._closing:
                return
            if reply.status == "ok":
                self._restore_after_publish(asset_id)
                self.statusBar().showMessage(f"Review state set to {state}", 2_000)
        self._mutate_catalog("review_state", (asset_id, asset["revision"], state),
                             callback=received)

    def _choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Preview files without importing")
        self._preview_files(paths)

    def _preview_files(self, paths: list[str]):
        if paths:
            self.statusBar().showMessage(
                f"Read-only preview request: {len(paths)} file(s); no files changed", 5_000
            )

    def start_background_task(self):
        if self.worker and self.worker.isRunning():
            return
        self.progress.setValue(0)
        self.worker = BackgroundWorker(parent=self)
        self.worker.progressChanged.connect(self.progress.setValue)
        self.worker.finished.connect(self._task_finished)
        self.task_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker.start()

    def cancel_background_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _task_finished(self):
        self.task_button.setEnabled(True)
        self.cancel_button.setEnabled(False)


class LibraryLauncher(QMainWindow):
    """Explicit library creation/opening keeps source work user initiated."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DefiantMaple — Open a library")
        self.setWindowIcon(app_icon())
        self.resize(520, 220)
        self.gallery_window: GalleryWindow | None = None
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("Libraries and thumbnails stay outside artwork folders."))
        create = QPushButton("Create new library…")
        create.clicked.connect(self.create_library)
        opening = QPushButton("Open existing library…")
        opening.clicked.connect(self.open_library)
        layout.addWidget(create)
        layout.addWidget(opening)
        self.setCentralWidget(container)

    def create_library(self):
        selected, _ = QFileDialog.getSaveFileName(
            self, "Create a library database outside artwork folders", "", "SQLite (*.sqlite3)"
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".sqlite3":
            path = path.with_suffix(".sqlite3")
        if path.exists():
            QMessageBox.warning(self, "Library exists", "Open this library instead.")
            return
        try:
            assert_outside_git(path)
            self._quiesce_gallery()
            path.parent.mkdir(parents=True, exist_ok=True)
            with admission_session(path, create=True) as owner:
                initialize(path)
                owner.ready()
                self._show_gallery(path)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Library not created", str(exc))

    def open_library(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open an existing library database", "", "SQLite (*.sqlite3)"
        )
        if not selected:
            return
        try:
            assert_outside_git(Path(selected))
            self._quiesce_gallery()
            with admission_session(Path(selected)):
                result = initialize(Path(selected), create=False)
                self._show_gallery(Path(selected))
            if result["migrated"]:
                QMessageBox.information(self.gallery_window, "Library upgraded",
                                        f"Library upgraded to schema {result['schema_version']}.\n"
                                        f"Verified backup: {result['backup_path']}")
        except (OSError, ValueError, sqlite3.Error) as exc:
            detail = str(exc)
            backup = getattr(exc, "backup_path", None)
            if backup:
                detail += f"\nPreserved verified backup: {backup}"
            QMessageBox.warning(self, "Library not opened", detail)

    def _quiesce_gallery(self):
        if self.gallery_window is not None:
            if not self.gallery_window.close():
                raise ValueError("The current library could not close. Stop its active work before opening another library.")
            self.gallery_window = None

    def _show_gallery(self, path: Path):
        self._quiesce_gallery()
        self.gallery_window = GalleryWindow(path, enable_thumbnails=True)
        self.gallery_window.show()
        self.hide()


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[position]


def _rss_bytes() -> int | None:
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(Counters),
            ctypes.c_ulong,
        )
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        process = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return None
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return int(completed.stdout.strip()) * 1024
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _processor_name() -> str:
    name = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "")
    if name or not sys.platform.startswith("linux"):
        return name
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.partition(":")[2].strip()
    except OSError:
        pass
    return ""


def _benchmark_wait(app: QApplication, predicate, label: str, *, seconds=10.0):
    """CLI benchmark completion wait; never used by interactive GUI callbacks."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise RuntimeError(f"Benchmark timed out waiting for {label}")


def _benchmark_select_id(app: QApplication, window: GalleryWindow, asset_id: str):
    result = []
    window.model.request_rank(asset_id, lambda row, error: result.append((row, error)))
    _benchmark_wait(app, lambda: bool(result), "captured rank")
    row, error = result[0]
    if error or row is None:
        raise RuntimeError(f"Benchmark captured target unavailable: {error or asset_id}")
    window.model.request_page(row // window.model.page_size)
    _benchmark_wait(app, lambda: window.model.loaded_asset_at(row) is not None,
                    "captured target page")
    selected = window.model.loaded_asset_at(row)
    if selected["asset_id"] != asset_id:
        raise RuntimeError("Benchmark rank selected a changed asset")
    window.gallery.setCurrentIndex(window.model.index(row))


def run_benchmark(app: QApplication, window: GalleryWindow, startup_ms: float) -> dict:
    app.processEvents()
    if not window.model._actionable:
        raise RuntimeError("Benchmark first count and page were not published")
    initial_rss = _rss_bytes()

    query_ms = []
    for index in range(50):
        started = time.perf_counter()
        window.model.set_filter("new" if index % 2 == 0 else None)
        expected = window.model._generation
        _benchmark_wait(app, lambda: window.model._actionable and
                        window.model._token.generation == expected, "query generation")
        query_ms.append((time.perf_counter() - started) * 1_000)
    window.model.set_filter(None)
    expected = window.model._generation
    _benchmark_wait(app, lambda: window.model._actionable and
                    window.model._token.generation == expected, "unfiltered generation")

    keyboard_ms = []
    state_ms = []
    if window.model.rowCount() == 0:
        raise RuntimeError("Benchmark catalog has no assets")
    benchmark_asset_id = window.model.asset_at(0)["asset_id"]
    _benchmark_select_id(app, window, benchmark_asset_id)
    window.gallery.setFocus()
    digit_keys = (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4)
    for operation in range(500):
        started = time.perf_counter()
        QApplication.sendEvent(window.gallery, QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.NoModifier,
        ))
        app.processEvents()
        keyboard_ms.append((time.perf_counter() - started) * 1_000)
        if operation % 10 == 0:
            shortcut = (operation // 10) % len(digit_keys)
            _benchmark_select_id(app, window, benchmark_asset_id)
            started = time.perf_counter()
            before = window.model._generation
            QApplication.sendEvent(window.gallery, QKeyEvent(
                QEvent.Type.KeyPress,
                digit_keys[shortcut],
                Qt.KeyboardModifier.NoModifier,
                str(shortcut + 1),
            ))
            _benchmark_wait(app, lambda: (window.model._generation > before
                                         and not window._mutation_pending
                                         and window.model._actionable),
                            "review write and refreshed generation")
            state_ms.append((time.perf_counter() - started) * 1_000)
            _benchmark_select_id(app, window, benchmark_asset_id)

    worker = BackgroundWorker(units=100_000)
    worker.start()
    deadline = time.perf_counter() + 2
    while not worker.isRunning() and time.perf_counter() < deadline:
        app.processEvents()

    scroll_ms = []
    upper = min(window.model.rowCount() - 1, 9_999)
    traversal_started = time.perf_counter()
    traversal_deadline = traversal_started + 60
    step = 0
    while time.perf_counter() < traversal_deadline:
        phase = step % 2_000
        ratio = phase / 999 if phase <= 999 else (1_999 - phase) / 1_000
        row = int(upper * ratio) if upper > 0 else 0
        started = time.perf_counter()
        window.gallery.scrollTo(
            window.model.index(row), QListView.ScrollHint.PositionAtCenter
        )
        window.gallery.viewport().repaint()
        app.processEvents()
        scroll_ms.append((time.perf_counter() - started) * 1_000)
        step += 1
    scroll_duration_seconds = time.perf_counter() - traversal_started

    cancel_started = time.perf_counter()
    worker.cancel()
    worker.wait(5_000)
    cancel_ms = (time.perf_counter() - cancel_started) * 1_000

    screen = window.screen()
    screen_size = screen.size() if screen else None
    return {
        "schema": "defiantmaple.desktop-benchmark.v1",
        "stack": "qt-pyside6",
        "framework_version": PYSIDE_VERSION,
        "qt_version": qVersion(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": _processor_name(),
        "cpu_count": os.cpu_count(),
        "ci_environment": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
        "display_backend": app.platformName(),
        "display_scale": screen.devicePixelRatio() if screen else None,
        "display_size_px": [screen_size.width(), screen_size.height()] if screen_size else None,
        "asset_count": window.model.rowCount(),
        "startup_ms": round(startup_ms, 3),
        "rss_first_grid_bytes": initial_rss,
        "rss_after_scroll_bytes": _rss_bytes(),
        "query_ms_median": round(statistics.median(query_ms), 3),
        "query_ms_p95": round(_percentile(query_ms, 0.95), 3),
        "keyboard_ms_median": round(statistics.median(keyboard_ms), 3),
        "keyboard_ms_p95": round(_percentile(keyboard_ms, 0.95), 3),
        "keyboard_ms_max": round(max(keyboard_ms), 3),
        "review_state_ms_median": round(statistics.median(state_ms), 3),
        "review_state_ms_p95": round(_percentile(state_ms, 0.95), 3),
        "review_state_ms_max": round(max(state_ms), 3),
        "scroll_step_ms_median": round(statistics.median(scroll_ms), 3),
        "scroll_step_ms_p95": round(_percentile(scroll_ms, 0.95), 3),
        "scroll_steps_over_16_7_ms": sum(value > 16.7 for value in scroll_ms),
        "scroll_steps": len(scroll_ms),
        "scroll_duration_seconds": round(scroll_duration_seconds, 3),
        "background_cancel_ms": round(cancel_ms, 3),
        "measurement_notes": [
            "Placeholder cells only; no image decode or disk thumbnail I/O.",
            "Offscreen/headless CI timing does not measure compositor presentation.",
            "Scroll timing measures synchronous scroll, repaint, and event processing per step.",
            "Query samples end after count and first page publication; review samples end after the captured write and fresh publication.",
            "Keyboard and scroll samples time GUI event/repaint handling, not later page completion.",
            "The background CPU task is active throughout the 60-second traversal.",
            "RSS is the current resident set on Unix and current working set on Windows.",
            "Startup is one release-artifact launch; filesystem and OS caches are not controlled.",
        ],
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--smoke-admission", action="store_true", help="Generated current-client exclusion probe")
    parser.add_argument("--smoke-admission-probe", action="store_true", help="Generated admission/release probe")
    parser.add_argument("--benchmark-json", type=Path)
    parser.add_argument("--smoke-thumbnail-id", help="Package self-check asset UUID")
    parser.add_argument("--smoke-worker-thumbnail-id", help="Package self-check gallery thumbnail worker")
    parser.add_argument("--smoke-external-probe-id", help="Read-only real external worker package probe; never dispatches")
    parser.add_argument("--smoke-cached-preview-id", help="Package self-check cache-only RGBA worker")
    parser.add_argument("--smoke-comparison-ids", nargs=2, help="Package self-check two captured comparison workers")
    parser.add_argument("--smoke-gallery-filters", action="store_true",
                        help="Package self-check bounded gateway and canonical filter controls")
    parser.add_argument("--smoke-source-root", type=Path, action="append",
                        help="Generated registered source root for gallery-filter I/O refusal")
    parser.add_argument("--smoke-recovery-package", type=Path,
                        help="Generated private package target for the spawned recovery smoke")
    parser.add_argument("--smoke-recovery-restored", type=Path,
                        help="Generated private new catalog target for the spawned recovery smoke")
    parser.add_argument("--smoke-cache-root", type=Path)
    parser.add_argument("--smoke-identity", action="store_true", help="Package self-check desktop identity")
    args = parser.parse_args(argv)

    if args.catalog is None:
        return _main_admitted(args, parser)
    try:
        with admission_session(args.catalog):
            return _main_admitted(args, parser)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))


def _main_admitted(args, parser):
    if args.smoke_admission or args.smoke_admission_probe:
        if args.catalog is None:
            parser.error("admission smoke requires --catalog")
        owner = current_session(args.catalog)
        if owner is None:
            parser.error("admission smoke has no native owner")
        owner.validate()
        if args.smoke_admission_probe:
            print(json.dumps({"admission_acquired": True}))
            return 0
        command = ([sys.argv[0]] if getattr(sys, "frozen", False) or "__compiled__" in globals()
                   else [sys.executable, "-m", "prototypes.qt.app"])
        result = subprocess.run(command + ["--catalog", str(args.catalog), "--smoke-admission-probe"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 2 or result.stdout.strip() or "already in use" not in result.stderr:
            parser.error("current-client admission smoke did not refuse its contender")
        owner.validate()
        print(json.dumps({"schema": "defiantmaple.admission-smoke.v1", "status": "passed",
                          "second_client_refused": True, "owner_still_valid": True}))
        return 0
    if args.smoke_thumbnail_id:
        if not args.catalog or not args.smoke_cache_root:
            parser.error("--smoke-thumbnail-id requires --catalog and --smoke-cache-root")
        result = thumbnail_for(args.catalog, args.smoke_thumbnail_id, args.smoke_cache_root)
        print(json.dumps({"cache_hit": result["cache_hit"], "width": result["width"],
                          "height": result["height"]}))
        return 0

    external_launch_ns = os.environ.get("DEFIANTMAPLE_LAUNCH_TIME_NS")
    started = time.perf_counter()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("DefiantMaple")
    app.setApplicationName("DefiantMaple")
    app.setApplicationDisplayName("DefiantMaple")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    if args.smoke_identity:
        print(json.dumps({"application_name": app.applicationName(),
                          "desktop_file_name": app.desktopFileName(),
                          "window_icon_available": not app.windowIcon().isNull()}))
        return 0
    if args.smoke_recovery_package or args.smoke_recovery_restored:
        if not (args.catalog and args.smoke_cache_root and args.smoke_recovery_package
                and args.smoke_recovery_restored):
            parser.error("recovery smoke requires --catalog, --smoke-cache-root, "
                         "--smoke-recovery-package and --smoke-recovery-restored")
        from prototypes.qt.recovery_smoke import run_recovery_smoke
        print(json.dumps(run_recovery_smoke(args.catalog, args.smoke_recovery_package,
                                            args.smoke_recovery_restored, args.smoke_cache_root),
                         sort_keys=True))
        return 0
    if args.smoke_gallery_filters:
        if not args.catalog or not args.smoke_cache_root or not args.smoke_source_root:
            parser.error("--smoke-gallery-filters requires --catalog, --smoke-cache-root and --smoke-source-root")
        from prototypes.qt.gallery_filter_smoke import run_gallery_filter_smoke
        print(json.dumps(run_gallery_filter_smoke(
            app, GalleryWindow, args.catalog, args.smoke_cache_root,
            args.smoke_source_root), sort_keys=True))
        return 0
    if args.smoke_comparison_ids:
        if not args.catalog or not args.smoke_cache_root:
            parser.error("--smoke-comparison-ids requires --catalog and --smoke-cache-root")
        model = AssetModel(args.catalog, read_mode="synchronous")
        try:
            assets = []
            for asset_id in args.smoke_comparison_ids:
                row = model.row_for_asset(asset_id)
                if row is None:
                    parser.error("unknown comparison smoke asset")
                assets.append(dict(model.asset_at(row)))
        finally:
            model.close()
        from prototypes.qt.comparison import comparison_smoke
        print(json.dumps(comparison_smoke(args.catalog, args.smoke_cache_root, assets, app)))
        return 0
    if args.smoke_external_probe_id:
        if not args.catalog:
            parser.error("--smoke-external-probe-id requires --catalog")
        with connect(args.catalog) as db:
            row = db.execute("SELECT * FROM assets WHERE asset_id=?", (args.smoke_external_probe_id,)).fetchone()
        if row is None:
            parser.error("unknown --smoke-external-probe-id")
        target = external_actions.capture_target(dict(row))
        worker = ExternalActionWorker(args.catalog, target, external_actions.OpenAction.FILE,
                                      external_actions.CommandSpec(), probe_only=True)
        worker.start()
        deadline = time.monotonic() + 8
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if worker.isRunning():
            worker.cancel()
            # Bounded cleanup occurs in the worker; no dispatch permit is possible.
            worker.wait(1500)
            if worker.isRunning():
                parser.error("external probe worker cleanup did not finish")
        result = worker.outcome
        if not isinstance(result, external_actions.ActionResult) or result.status != "probe_ready" or result.permit_sent or result.dispatched or not result.cleanup_complete:
            parser.error(f"external probe worker failed: {result}")
        print(json.dumps({"status": result.status, "permit_sent": result.permit_sent,
                          "dispatched": result.dispatched, "cleanup_complete": result.cleanup_complete}))
        return 0
    if args.smoke_cached_preview_id:
        if not args.catalog or not args.smoke_cache_root:
            parser.error("--smoke-cached-preview-id requires --catalog and --smoke-cache-root")
        with connect(args.catalog) as db:
            row = db.execute("SELECT * FROM assets WHERE asset_id=?", (args.smoke_cached_preview_id,)).fetchone()
        if row is None:
            parser.error("unknown --smoke-cached-preview-id")
        worker = CachedPreviewWorker(args.catalog, dict(row), args.smoke_cache_root, edge=256)
        deliveries = []
        worker.completed.connect(lambda image, result: deliveries.append((image, result)))
        worker.start()
        deadline = time.monotonic() + 8
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if worker.isRunning():
            worker.cancel()
            if not worker.wait(2500):
                parser.error("cache worker cleanup did not finish; ownership retained")
        app.processEvents()
        result = worker.outcome
        if (result is None or result.status != "ready" or not result.cleanup_complete
                or len(deliveries) != 1 or deliveries[0][0].isNull()):
            parser.error(f"cache-only worker failed: {result}")
        print(json.dumps({"status": result.status, "width": result.width, "height": result.height,
                          "requested_edge": result.requested_edge, "cache_edge": result.cache_edge,
                          "cleanup_complete": result.cleanup_complete,
                          "address_space_enforced": result.address_space_enforced,
                          "address_space_note": result.address_space_note,
                          "address_space_bytes": worker.limits.address_space_bytes,
                          "rgba_bytes": worker.rgba_bytes}))
        return 0
    if args.smoke_worker_thumbnail_id:
        if not args.catalog or not args.smoke_cache_root:
            parser.error("--smoke-worker-thumbnail-id requires --catalog and --smoke-cache-root")
        with connect(args.catalog) as db:
            row = db.execute("SELECT * FROM assets WHERE asset_id=?",
                             (args.smoke_worker_thumbnail_id,)).fetchone()
        if row is None:
            parser.error("unknown --smoke-worker-thumbnail-id")
        asset = dict(row)
        worker = ThumbnailWorker(args.catalog, args.smoke_cache_root)
        worker.start()
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                pixmap, error = worker.lookup(asset, 128)
                if pixmap is not None:
                    print(json.dumps({"width": pixmap.width(), "height": pixmap.height()}))
                    return 0
                if error:
                    parser.error(error)
                app.processEvents()
                time.sleep(.01)
            parser.error("thumbnail worker smoke timed out")
        finally:
            worker.stop()
    if args.benchmark_json and not args.catalog:
        parser.error("--benchmark-json requires --catalog")
    migration = None
    if args.catalog:
        try:
            migration = initialize(args.catalog, create=False)
        except (OSError, ValueError, sqlite3.Error) as exc:
            detail = str(exc)
            if getattr(exc, "backup_path", None):
                detail += f"; preserved verified backup: {exc.backup_path}"
            parser.error(detail)
        window = GalleryWindow(args.catalog, enable_thumbnails=not args.benchmark_json)
    else:
        window = LibraryLauncher()
    window.show()
    if migration and migration["migrated"] and not args.benchmark_json:
        QMessageBox.information(window, "Library upgraded",
                                f"Library upgraded to schema {migration['schema_version']}.\n"
                                f"Verified backup: {migration['backup_path']}")
    for _ in range(5):
        app.processEvents()
    if args.benchmark_json:
        _benchmark_wait(app, lambda: window.model._actionable and window.model._token is not None,
                        "initial count and first page")
    if external_launch_ns:
        startup_ms = (time.time_ns() - int(external_launch_ns)) / 1_000_000
    else:
        startup_ms = (time.perf_counter() - started) * 1_000
    if args.benchmark_json:
        result = run_benchmark(app, window, startup_ms)
        args.benchmark_json.parent.mkdir(parents=True, exist_ok=True)
        args.benchmark_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        window.close()
        _benchmark_wait(app, lambda: window.catalog_client.gateway.close_complete and
                        not window.isVisible(), "catalog gateway and window close", seconds=20)
        return 0
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
