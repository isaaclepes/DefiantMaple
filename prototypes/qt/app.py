"""Scoped Qt/PySide6 gallery prototype for the DefiantMaple stack spike."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
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

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    Signal,
    qVersion,
)
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
    QSplitter,
    QStyle,
    QTabWidget,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from defiantmaple.catalog import connect, duplicates, initialize
from defiantmaple import collections as collection_api, metadata
from defiantmaple.private_eval import (PrivateSelectionStore, assert_library_locations,
                                       assert_outside_git, assert_outside_sources,
                                       default_private_root)
from defiantmaple.sources import add_source, list_sources, scan_sources
from defiantmaple.thumbnail import ThumbnailLimits, thumbnail_for


REVIEW_STATES = (
    "new",
    "needs_review",
    "reviewed",
    "organized",
    "ignored",
    "error",
)


class AssetModel(QAbstractListModel):
    """SQLite-backed, page-cached model; rows are fetched only when requested."""

    AssetRole = Qt.ItemDataRole.UserRole + 1
    page_size = 256
    max_cached_pages = 24

    def __init__(self, database: Path, parent=None):
        super().__init__(parent)
        database = Path(database).resolve(strict=True)
        self.database = database
        uri = database.as_uri() + "?mode=rw"
        self._db = sqlite3.connect(uri, uri=True)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._filter: str | None = None
        self._source_filter: str | None = None
        self._type_filter: str | None = None
        self._search: str = ""
        self._duplicate_hash: str | None = None
        self._collection_id: str | None = None
        self._cache: OrderedDict[int, list[dict]] = OrderedDict()
        self._count = self._query_count()

    @property
    def active_filter(self) -> str | None:
        return self._filter

    @property
    def has_active_filters(self) -> bool:
        return bool(self._filter or self._source_filter or self._type_filter
                    or self._search or self._duplicate_hash)

    def _asset_tables(self) -> str:
        return ("assets JOIN collection_members AS members ON members.asset_id=assets.asset_id"
                if self._collection_id is not None else "assets")

    def _order_fields(self) -> tuple[str, str]:
        return ("members.position" if self._collection_id is not None else
                "assets.discovered_at", "assets.asset_id")

    def close(self):
        self._db.close()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else self._count

    def roleNames(self):  # noqa: N802 - Qt API
        return {self.AssetRole: b"asset"}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self._count:
            return None
        asset = self.asset_at(index.row())
        if role == self.AssetRole:
            return asset
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{Path(asset['current_path']).name}\n{asset['workflow_state']}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return asset["current_path"]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                f"{Path(asset['current_path']).name}, {asset['media_type']}, "
                f"state {asset['workflow_state']}"
            )
        return None

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
        where, params = self._where()
        return self._db.execute(
            "SELECT COUNT(*) FROM " + self._asset_tables() + where, params
        ).fetchone()[0]

    def _load_page(self, page: int) -> list[dict]:
        cached = self._cache.get(page)
        if cached is not None:
            self._cache.move_to_end(page)
            return cached
        where, params = self._where()
        rows = [dict(row) for row in self._db.execute(
            "SELECT assets.asset_id,assets.current_path,assets.media_type,assets.sha256,"
            "assets.byte_size,assets.workflow_state,assets.discovered_at,assets.source_id,"
            "source_entries.disposition AS entry_disposition,"
            "sources.health AS source_health FROM " + self._asset_tables() + " "
            "LEFT JOIN source_entries ON source_entries.asset_id=assets.asset_id "
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
        self._source_filter = source_id
        self._type_filter = media_type
        self._search = search.strip()
        self._duplicate_hash = None
        self.refresh()

    def set_duplicate_hash(self, digest: str | None):
        self._duplicate_hash = digest
        self.refresh()

    def set_collection(self, collection_id: str | None):
        if collection_id != self._collection_id:
            self._collection_id = collection_id
            self.refresh()

    def row_for_asset(self, asset_id: str) -> int | None:
        """Find a visible UUID's row without fetching all preceding assets."""
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
        self.beginResetModel()
        self._cache.clear()
        self._count = self._query_count()
        self.endResetModel()

    def details_for(self, asset_id: str) -> dict:
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

    def update_state(self, row: int, state: str):
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
        database = self.editor.database
        self.records = (metadata.list_tags(database) if self.kind == "tag" else
                        metadata.list_entities(database, entity_type=self.entity_type.currentText()))
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

    def _write(self, function, *args):
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
            result = self._write(metadata.create_tag, self.name.text())
        else:
            result = self._write(metadata.create_entity, self.entity_type.currentText(), self.name.text())
        if result:
            self.select_id(result[self.id_field])

    def select_id(self, identifier: str):
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                self.list.setCurrentRow(row)
                return

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
                 asset_label: str | None = None, parent=None):
        super().__init__(parent)
        self.database = Path(database)
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
        self.asset_metadata = (metadata.get_asset_metadata(self.database, self.asset_id)
                               if self.asset_id is not None else
                               {"asset_id": None, "tags": [], "entities": []})
        tags = ", ".join(record["name"] for record in self.asset_metadata["tags"]) or "None"
        entities = ", ".join(f"{record['entity_type']}: {record['name']}"
                             for record in self.asset_metadata["entities"]) or "None"
        self.assigned.setText(f"Assigned tags: {tags}\nAssigned entities: {entities}")
        self.tags.refresh()
        self.entities.refresh()


class ThumbnailWorker(QThread):
    """One bounded queue; only decoded cache PNGs reach the UI thread."""

    updated = Signal(str)

    def __init__(self, database: Path, cache_root: Path, parent=None):
        super().__init__(parent)
        self.database = Path(database)
        self.cache_root = Path(cache_root)
        self.requests: queue.Queue[tuple[str, str, int]] = queue.Queue(maxsize=32)
        self.pending: set[tuple[str, str, int]] = set()
        self.pixmaps: OrderedDict[tuple[str, str, int], QPixmap] = OrderedDict()
        self.errors: dict[tuple[str, str, int], str] = {}
        self._stop = threading.Event()
        self.finished_item.connect(self._received)

    finished_item = Signal(str, str, int, str, str)

    def lookup(self, asset: dict, edge: int) -> tuple[QPixmap | None, str | None]:
        key = (asset["asset_id"], asset["sha256"], edge)
        pixmap = self.pixmaps.get(key)
        if pixmap is not None:
            self.pixmaps.move_to_end(key)
            return pixmap, None
        if key in self.errors:
            return None, self.errors[key]
        if key not in self.pending:
            try:
                self.requests.put_nowait(key)
            except queue.Full:
                pass  # A later repaint retries after the bounded queue drains.
            else:
                self.pending.add(key)
        return None, None

    def _received(self, asset_id: str, digest: str, edge: int, path: str, error: str):
        key = (asset_id, digest, edge)
        self.pending.discard(key)
        if error:
            self.errors[key] = error
        else:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self.errors[key] = "Thumbnail cache error"
            else:
                self.pixmaps[key] = pixmap
                self.pixmaps.move_to_end(key)
                while len(self.pixmaps) > 256:
                    self.pixmaps.popitem(last=False)
        self.updated.emit(asset_id)

    def run(self):
        while not self._stop.is_set():
            try:
                asset_id, digest, edge = self.requests.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                result = thumbnail_for(
                    self.database, asset_id, self.cache_root, max_edge=edge,
                    limits=ThumbnailLimits(timeout_seconds=6),
                )
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.finished_item.emit(asset_id, digest, edge, "", type(exc).__name__)
            else:
                self.finished_item.emit(asset_id, digest, edge, result["path"], "")

    def stop(self):
        self._stop.set()
        self.wait()


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
        if asset.get("source_health") == "offline":
            status = "Offline"
        elif asset.get("source_health") == "permission_denied":
            status = "Permission denied"
        elif asset.get("entry_disposition") == "missing":
            status = "Missing"
        elif not asset["media_type"].startswith("image/"):
            status = "Unsupported preview"
        elif self.thumbnails is not None:
            pixmap, error = self.thumbnails.lookup(asset, min(256, max(32, self.cell_size)))
            if pixmap is not None:
                painter.drawPixmap(thumb, pixmap, pixmap.rect())
                status = ""
            elif error:
                status = "Thumbnail error"
            else:
                status = "Loading thumbnail"
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
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, label)
        painter.restore()


class GalleryView(QListView):
    reviewRequested = Signal(str)
    filesPreviewed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(128)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setAccessibleName("Asset gallery")

    def keyPressEvent(self, event: QKeyEvent):
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


class GalleryWindow(QMainWindow):
    def __init__(self, database: Path, *, enable_thumbnails: bool = False,
                 cache_root: Path | None = None, private_root: Path | None = None):
        super().__init__()
        self._closing = False
        self.database = Path(database).resolve(strict=True)
        library_key = hashlib.sha256(str(self.database).encode()).hexdigest()[:16]
        app_data = default_private_root().parent
        self.cache_root = Path(cache_root or app_data / "thumbnails" / library_key)
        self.private_root = Path(private_root or default_private_root())
        if enable_thumbnails:
            assert_outside_git(self.database)
            assert_outside_git(self.cache_root)
        for source in list_sources(self.database):
            assert_outside = [source["root_path"]]
            assert_outside_sources(self.database, assert_outside)
            assert_outside_sources(self.cache_root, assert_outside)
            assert_outside_sources(self.private_root, assert_outside)
        self.setWindowTitle("DefiantMaple Gallery")
        self.resize(1280, 800)
        self.model = AssetModel(self.database, self)
        self.thumbnails = (ThumbnailWorker(self.database, self.cache_root, self)
                           if enable_thumbnails else None)
        self.delegate = AssetDelegate(parent=self)
        self.gallery = GalleryView(self)
        self.gallery.setModel(self.model)
        self.gallery.setItemDelegate(self.delegate)
        self.gallery.selectionModel().currentChanged.connect(self._show_detail)
        self.gallery.reviewRequested.connect(self.set_selected_state)
        self.gallery.filesPreviewed.connect(self._preview_files)
        self.worker: BackgroundWorker | None = None
        self.scan_worker: ScanWorker | None = None
        if self.thumbnails is not None:
            self.thumbnails.updated.connect(lambda _asset_id: self.gallery.viewport().update())
            self.thumbnails.start()

        self.source_box = QComboBox()
        self.source_box.setAccessibleName("Source and health")
        self.source_box.currentIndexChanged.connect(self._source_selected)
        self.add_source_button = QPushButton("Add folder…")
        self.add_source_button.clicked.connect(self._add_source_dialog)
        self.scan_button = QPushButton("Scan source")
        self.scan_button.clicked.connect(self.start_source_scan)
        self.cancel_scan_button = QPushButton("Cancel scan")
        self.cancel_scan_button.clicked.connect(self.cancel_source_scan)
        self.cancel_scan_button.setEnabled(False)
        self.scan_status = QLabel("Choose a source to scan. Scans are one-shot, not watchers.")
        self.scan_status.setAccessibleName("Source scan status")
        self.refresh_sources()

        self.filter_box = QComboBox()
        self.filter_box.addItem("All states", "all")
        for state in REVIEW_STATES:
            self.filter_box.addItem(state.replace("_", " ").title(), state)
        self.filter_box.currentIndexChanged.connect(
            lambda: self.model.set_filter(self.filter_box.currentData())
        )
        self.filter_box.setAccessibleName("Review state filter")
        self.type_box = QComboBox()
        self.type_box.addItem("All media", None)
        for label, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"),
                            ("GIF", "image/gif"), ("WebP", "image/webp")):
            self.type_box.addItem(label, mime)
        self.type_box.currentIndexChanged.connect(self._apply_metadata_filters)
        self.type_box.setAccessibleName("Media type filter")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search path or filename")
        self.search_box.returnPressed.connect(self._apply_metadata_filters)
        self.search_box.setAccessibleName("Asset path search")
        self.search_box.textChanged.connect(self._update_collection_controls)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._apply_metadata_filters)

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
        sources_row.addWidget(QLabel("Source"))
        sources_row.addWidget(self.source_box, 2)
        sources_row.addWidget(self.add_source_button)
        sources_row.addWidget(self.scan_button)
        sources_row.addWidget(self.cancel_scan_button)
        sources_row.addWidget(self.progress)
        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel("State"))
        filters_row.addWidget(self.filter_box)
        filters_row.addWidget(self.type_box)
        filters_row.addWidget(self.search_box, 2)
        filters_row.addWidget(search_button)
        filters_row.addWidget(QLabel("Thumbnail size"))
        filters_row.addWidget(self.size_slider)
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
        self.refresh_collections()
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
        clear_duplicates.clicked.connect(lambda: self.model.set_duplicate_hash(None))
        curate_button = QPushButton("Add selected to private evaluation…")
        curate_button.clicked.connect(self._curate_selected)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(self.detail, 3)
        self.metadata_button = QPushButton("Tags and entities…")
        self.metadata_button.clicked.connect(self._edit_metadata)
        side_layout.addWidget(self.metadata_button)
        side_layout.addWidget(duplicate_button)
        side_layout.addWidget(clear_duplicates)
        side_layout.addWidget(self.duplicates_list, 1)
        side_layout.addWidget(QLabel("Source issues (first 100)"))
        side_layout.addWidget(self.issues_list, 1)
        side_layout.addWidget(curate_button)
        splitter = QSplitter()
        splitter.addWidget(self.gallery)
        splitter.addWidget(side)
        splitter.setSizes([950, 330])

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(str(self.database)))
        layout.addLayout(sources_row)
        layout.addWidget(self.scan_status)
        layout.addLayout(filters_row)
        layout.addLayout(collection_row)
        layout.addWidget(self.collection_feedback)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self.statusBar().showMessage(f"{self.model.rowCount():,} assets")

    def closeEvent(self, event):
        # Signals already queued by a finishing worker can arrive after waits.
        self._closing = True
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2_000)
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait()
        if self.thumbnails is not None:
            self.thumbnails.stop()
        self.model.close()
        super().closeEvent(event)

    def _resize_cells(self, value: int):
        self.delegate.set_cell_size(value)
        self.gallery.setGridSize(QSize(value + 8, value + 50))
        self.gallery.doItemsLayout()
        self.gallery.viewport().update()

    def _show_detail(self, current, previous=None):
        if self._closing:
            return
        if not current.isValid():
            self.detail.clear()
            return
        asset = self.model.asset_at(current.row())
        self.detail.setPlainText(json.dumps(self.model.details_for(asset["asset_id"]), indent=2))

    def _edit_metadata(self):
        current = self.gallery.currentIndex()
        asset = self.model.asset_at(current.row()) if current.isValid() else None
        asset_id = asset["asset_id"] if asset else None
        label = Path(asset["current_path"]).name if asset else None
        try:
            editor = MetadataEditor(self.database, asset_id, label, self)
            editor.changed.connect(lambda: self._show_detail(self.gallery.currentIndex()))
            editor.exec()
            self._show_detail(self.gallery.currentIndex())
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Metadata not opened", str(exc))

    def _selected_asset(self) -> dict | None:
        current = self.gallery.currentIndex()
        return (self.model.asset_at(current.row()) if current.isValid() and
                0 <= current.row() < self.model.rowCount() else None)

    def refresh_collections(self):
        if self._closing:
            return
        selected = self.collection_box.currentData()
        self.collection_records = collection_api.list_collections(self.database)
        self.collection_box.blockSignals(True)
        self.collection_box.clear()
        self.collection_box.addItem("All assets", None)
        for record in self.collection_records:
            self.collection_box.addItem(record["name"], record["collection_id"])
        self.collection_box.setCurrentIndex(max(0, self.collection_box.findData(selected)))
        self.collection_box.blockSignals(False)

    def _update_collection_controls(self, *unused):
        if not hasattr(self, "collection_box") or self._closing:
            return
        selected = self._selected_asset() is not None
        collection_id = self.collection_box.currentData()
        in_collection = collection_id is not None
        self.rename_collection_button.setEnabled(in_collection)
        self.delete_collection_button.setEnabled(in_collection)
        self.add_member_button.setEnabled(selected and bool(self.collection_records))
        self.remove_member_button.setEnabled(selected and in_collection)
        filtered = self.model.has_active_filters or bool(self.search_box.text().strip())
        movable = selected and in_collection and not filtered
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
        asset = self._selected_asset()
        self.model.set_collection(self.collection_box.currentData())
        self._restore_asset_selection(asset["asset_id"] if asset else None)
        self.statusBar().showMessage(f"{self.model.rowCount():,} matching assets")

    def _refresh_collection_view(self, asset_id: str | None = None):
        if self._closing:
            return
        asset = self._selected_asset()
        restore_id = asset_id if asset_id is not None else (asset["asset_id"] if asset else None)
        self.refresh_collections()
        if self.model._collection_id != self.collection_box.currentData():
            self.model.set_collection(self.collection_box.currentData())
        else:
            self.model.refresh()
        self._restore_asset_selection(restore_id)
        self.statusBar().showMessage(f"{self.model.rowCount():,} matching assets")

    def _change_collection(self, operation, *args, **kwargs):
        if self._closing:
            return False, None
        try:
            result = operation(self.database, *args, **kwargs)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.collection_feedback.setText(str(exc))
            self._refresh_collection_view()
            return False, None
        self._refresh_collection_view()
        self.collection_feedback.setText("Collection saved.")
        return True, result

    def _create_collection(self):
        if self._closing:
            return
        name, accepted = QInputDialog.getText(self, "New collection", "Collection name:")
        if accepted:
            saved, record = self._change_collection(collection_api.create_collection, name)
            if saved:
                self.collection_box.setCurrentIndex(self.collection_box.findData(record["collection_id"]))

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
            self._change_collection(collection_api.rename_collection, collection_id, replacement)

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
            self._change_collection(collection_api.delete_collection, collection_id)

    def _add_collection_member(self):
        if self._closing:
            return
        asset = self._selected_asset()
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
            self._change_collection(collection_api.add_member, target, asset["asset_id"])

    def _remove_collection_member(self):
        if self._closing:
            return
        collection_id, asset = self.collection_box.currentData(), self._selected_asset()
        if collection_id is not None and asset is not None:
            self._change_collection(collection_api.remove_member, collection_id, asset["asset_id"])

    def _move_collection_member(self, direction: int):
        if self._closing:
            return
        if self.model.has_active_filters or self.search_box.text().strip():
            self.collection_feedback.setText("Clear all filters before moving collection members.")
            return
        collection_id, asset = self.collection_box.currentData(), self._selected_asset()
        row = self.gallery.currentIndex().row()
        neighbor_row = row + direction
        if collection_id is None or asset is None or not 0 <= neighbor_row < self.model.rowCount():
            return
        neighbor_id = self.model.asset_at(neighbor_row)["asset_id"]
        self._change_collection(collection_api.move_member, collection_id, asset["asset_id"],
                                direction=direction, expected_neighbor_id=neighbor_id)

    def refresh_sources(self):
        selected = self.source_box.currentData()
        self.source_box.blockSignals(True)
        self.source_box.clear()
        self.source_box.addItem("All sources", None)
        for source in list_sources(self.database):
            label = (f"{source['name']} · {source['health']} · "
                     f"{source['existing_file_policy'].replace('_', ' ')}")
            self.source_box.addItem(label, source["source_id"])
            self.source_box.setItemData(self.source_box.count() - 1, source["root_path"],
                                        Qt.ItemDataRole.ToolTipRole)
        index = self.source_box.findData(selected)
        self.source_box.setCurrentIndex(max(0, index))
        self.source_box.blockSignals(False)
        self.scan_button.setEnabled(self.source_box.currentData() is not None)

    def _source_selected(self):
        source_id = self.source_box.currentData()
        self.scan_button.setEnabled(source_id is not None and
                                    not (self.scan_worker and self.scan_worker.isRunning()))
        self.delegate.thumbnails = self.thumbnails if source_id else None
        self._apply_metadata_filters()
        self.refresh_source_issues()
        if source_id:
            source = next((item for item in list_sources(self.database)
                           if item["source_id"] == source_id), None)
            if source:
                detail = source["health_detail"] or "Ready for an explicit scan."
                self.scan_status.setText(f"{source['health'].title()}: {detail}")
        self.gallery.viewport().update()

    def refresh_source_issues(self):
        self.issues_list.clear()
        source_id = self.source_box.currentData()
        if source_id is None:
            return
        with connect(self.database) as db:
            rows = db.execute(
                "SELECT current_path,disposition,last_error FROM source_entries "
                "WHERE source_id=? AND disposition IN ('error','unsupported','missing') "
                "ORDER BY disposition,current_path LIMIT 100", (source_id,),
            ).fetchall()
        for row in rows:
            label = f"{row['disposition']}: {Path(row['current_path']).name}"
            if row["last_error"]:
                label += f" · {row['last_error']}"
            item = QListWidgetItem(label)
            item.setToolTip(row["current_path"])
            self.issues_list.addItem(item)

    def _apply_metadata_filters(self):
        self.model.set_metadata_filters(
            source_id=self.source_box.currentData(), media_type=self.type_box.currentData(),
            search=self.search_box.text(),
        )
        self.statusBar().showMessage(f"{self.model.rowCount():,} matching assets")

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
            source = add_source(self.database, Path(folder), existing_file_policy=policy)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Source not added", str(exc))
            return
        self.refresh_sources()
        self.source_box.setCurrentIndex(self.source_box.findData(source["source_id"]))
        self.scan_status.setText("Source added. Scan observes stable files; it does not watch continuously.")

    def start_source_scan(self):
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
        for group in duplicates(self.database):
            item = QListWidgetItem(f"{group['asset_count']} copies · SHA-256 {group['sha256'][:12]}…")
            item.setData(Qt.ItemDataRole.UserRole, group["sha256"])
            self.duplicates_list.addItem(item)
        self.statusBar().showMessage(f"{self.duplicates_list.count()} exact-duplicate groups")

    def _duplicate_selected(self, item: QListWidgetItem):
        self.model.set_duplicate_hash(item.data(Qt.ItemDataRole.UserRole))
        self.statusBar().showMessage(f"{self.model.rowCount()} assets in duplicate group")

    def _curate_selected(self):
        index = self.gallery.currentIndex()
        if not index.isValid():
            QMessageBox.information(self, "Select an asset", "Select one image first.")
            return
        asset = self.model.asset_at(index.row())
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
        try:
            store = PrivateSelectionStore(self.private_root / f"{key}.private.sqlite3",
                                          self.database)
            store.select(asset["asset_id"], anonymous_id, role, rights, notes)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Selection not saved", str(exc))
            return
        self.statusBar().showMessage("Private selection saved outside the artwork source.")

    def set_selected_state(self, state: str):
        current = self.gallery.currentIndex()
        if current.isValid():
            row = current.row()
            self.model.update_state(row, state)
            if row < self.model.rowCount() and (
                not self.model.active_filter or self.model.active_filter == state
            ):
                updated = self.model.index(row)
                self.gallery.setCurrentIndex(updated)
                self._show_detail(updated)
            else:
                self.detail.clear()
            self.statusBar().showMessage(f"Review state set to {state}", 2_000)

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
            initialize(path)
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


def run_benchmark(app: QApplication, window: GalleryWindow, startup_ms: float) -> dict:
    app.processEvents()
    initial_rss = _rss_bytes()

    query_ms = []
    for index in range(50):
        started = time.perf_counter()
        window.model.set_filter("new" if index % 2 == 0 else None)
        app.processEvents()
        query_ms.append((time.perf_counter() - started) * 1_000)
    window.model.set_filter(None)

    keyboard_ms = []
    state_ms = []
    window.gallery.setCurrentIndex(window.model.index(0))
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
            started = time.perf_counter()
            QApplication.sendEvent(window.gallery, QKeyEvent(
                QEvent.Type.KeyPress,
                digit_keys[shortcut],
                Qt.KeyboardModifier.NoModifier,
                str(shortcut + 1),
            ))
            app.processEvents()
            state_ms.append((time.perf_counter() - started) * 1_000)

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
            "The background CPU task is active throughout the 60-second traversal.",
            "RSS is the current resident set on Unix and current working set on Windows.",
            "Startup is one release-artifact launch; filesystem and OS caches are not controlled.",
        ],
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--benchmark-json", type=Path)
    parser.add_argument("--smoke-thumbnail-id", help="Package self-check asset UUID")
    parser.add_argument("--smoke-cache-root", type=Path)
    args = parser.parse_args(argv)

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
    if external_launch_ns:
        startup_ms = (time.time_ns() - int(external_launch_ns)) / 1_000_000
    else:
        startup_ms = (time.perf_counter() - started) * 1_000
    if args.benchmark_json:
        result = run_benchmark(app, window, startup_ms)
        args.benchmark_json.parent.mkdir(parents=True, exist_ok=True)
        args.benchmark_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
