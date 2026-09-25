"""Scoped Qt/PySide6 gallery prototype for the DefiantMaple stack spike."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
import ctypes
import json
import os
import platform
import sqlite3
import statistics
import sys
import threading
import time

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    Signal,
    qVersion,
)
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)


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
        uri = database.as_uri() + "?mode=rw"
        self._db = sqlite3.connect(uri, uri=True)
        self._db.row_factory = sqlite3.Row
        self._filter: str | None = None
        self._cache: OrderedDict[int, list[dict]] = OrderedDict()
        self._count = self._query_count()

    @property
    def active_filter(self) -> str | None:
        return self._filter

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
        if self._filter:
            return " WHERE workflow_state=?", (self._filter,)
        return "", ()

    def _query_count(self) -> int:
        where, params = self._where()
        return self._db.execute(
            "SELECT COUNT(*) FROM assets" + where, params
        ).fetchone()[0]

    def _load_page(self, page: int) -> list[dict]:
        cached = self._cache.get(page)
        if cached is not None:
            self._cache.move_to_end(page)
            return cached
        where, params = self._where()
        rows = [dict(row) for row in self._db.execute(
            "SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at "
            "FROM assets" + where +
            " ORDER BY discovered_at,asset_id LIMIT ? OFFSET ?",
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
        self.beginResetModel()
        self._filter = state
        self._cache.clear()
        self._count = self._query_count()
        self.endResetModel()

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


class AssetDelegate(QStyledItemDelegate):
    COLORS = {
        "image/png": QColor("#577590"),
        "image/jpeg": QColor("#43aa8b"),
        "image/webp": QColor("#f9c74f"),
        "video/mp4": QColor("#f3722c"),
    }

    def __init__(self, cell_size=144, parent=None):
        super().__init__(parent)
        self.cell_size = cell_size

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
        painter.setPen(QColor("#ffffff"))
        painter.drawText(thumb, Qt.AlignmentFlag.AlignCenter, asset["media_type"])
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
        if event.text() in "123456":
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


class GalleryWindow(QMainWindow):
    def __init__(self, database: Path):
        super().__init__()
        self.setWindowTitle("DefiantMaple Qt Gallery Prototype")
        self.resize(1280, 800)
        self.model = AssetModel(database, self)
        self.delegate = AssetDelegate(parent=self)
        self.gallery = GalleryView(self)
        self.gallery.setModel(self.model)
        self.gallery.setItemDelegate(self.delegate)
        self.gallery.selectionModel().currentChanged.connect(self._show_detail)
        self.gallery.reviewRequested.connect(self.set_selected_state)
        self.gallery.filesPreviewed.connect(self._preview_files)
        self.worker: BackgroundWorker | None = None

        self.filter_box = QComboBox()
        self.filter_box.addItem("All states", "all")
        for state in REVIEW_STATES:
            self.filter_box.addItem(state.replace("_", " ").title(), state)
        self.filter_box.currentIndexChanged.connect(
            lambda: self.model.set_filter(self.filter_box.currentData())
        )
        self.filter_box.setAccessibleName("Review state filter")

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(96, 224)
        self.size_slider.setValue(144)
        self.size_slider.valueChanged.connect(self._resize_cells)
        self.size_slider.setAccessibleName("Gallery cell size")

        choose = QPushButton("Choose files (read-only)")
        choose.clicked.connect(self._choose_files)
        choose.setAccessibleName("Choose files for read-only preview")
        self.task_button = QPushButton("Start background task")
        self.task_button.clicked.connect(self.start_background_task)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_background_task)
        self.cancel_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName("Background task progress")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter"))
        controls.addWidget(self.filter_box)
        controls.addWidget(QLabel("Cell size"))
        controls.addWidget(self.size_slider)
        controls.addWidget(choose)
        controls.addWidget(self.task_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.progress)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Selected asset details")
        splitter = QSplitter()
        splitter.addWidget(self.gallery)
        splitter.addWidget(self.detail)
        splitter.setSizes([950, 330])

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addLayout(controls)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self.statusBar().showMessage(f"{self.model.rowCount():,} assets")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2_000)
        self.model.close()
        super().closeEvent(event)

    def _resize_cells(self, value: int):
        self.delegate.set_cell_size(value)
        self.gallery.setGridSize(QSize(value + 8, value + 50))
        self.gallery.doItemsLayout()

    def _show_detail(self, current, previous=None):
        if not current.isValid():
            self.detail.clear()
            return
        asset = self.model.asset_at(current.row())
        self.detail.setPlainText(json.dumps(asset, indent=2))

    def set_selected_state(self, state: str):
        current = self.gallery.currentIndex()
        if current.isValid():
            self.model.update_state(current.row(), state)
            if current.row() < self.model.rowCount():
                self.gallery.setCurrentIndex(self.model.index(current.row()))
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
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            return int(counters.WorkingSetSize)
        return None
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if sys.platform == "darwin" else rss * 1024)


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
    for operation in range(500):
        row = operation % max(1, min(window.model.rowCount(), 10_000))
        started = time.perf_counter()
        current = window.model.index(row)
        window.gallery.setCurrentIndex(current)
        app.processEvents()
        keyboard_ms.append((time.perf_counter() - started) * 1_000)
        if operation % 10 == 0:
            started = time.perf_counter()
            window.model.update_state(row, REVIEW_STATES[(operation // 10) % 4])
            app.processEvents()
            state_ms.append((time.perf_counter() - started) * 1_000)

    scroll_ms = []
    upper = min(window.model.rowCount() - 1, 9_999)
    for step in range(1_000):
        row = int(upper * step / 999) if upper > 0 else 0
        started = time.perf_counter()
        window.gallery.scrollTo(
            window.model.index(row), QListView.ScrollHint.PositionAtCenter
        )
        window.gallery.viewport().repaint()
        app.processEvents()
        scroll_ms.append((time.perf_counter() - started) * 1_000)

    worker = BackgroundWorker(units=4_000)
    worker.start()
    deadline = time.perf_counter() + 2
    while not worker.isRunning() and time.perf_counter() < deadline:
        app.processEvents()
    time.sleep(0.02)
    cancel_started = time.perf_counter()
    worker.cancel()
    worker.wait(5_000)
    cancel_ms = (time.perf_counter() - cancel_started) * 1_000

    return {
        "schema": "defiantmaple.desktop-benchmark.v1",
        "stack": "qt-pyside6",
        "framework_version": PYSIDE_VERSION,
        "qt_version": qVersion(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "asset_count": window.model.rowCount(),
        "startup_ms": round(startup_ms, 3),
        "rss_first_grid_bytes": initial_rss,
        "rss_after_scroll_bytes": _rss_bytes(),
        "query_ms_median": round(statistics.median(query_ms), 3),
        "query_ms_p95": round(_percentile(query_ms, 0.95), 3),
        "keyboard_ms_median": round(statistics.median(keyboard_ms), 3),
        "keyboard_ms_p95": round(_percentile(keyboard_ms, 0.95), 3),
        "review_state_ms_median": round(statistics.median(state_ms), 3),
        "review_state_ms_p95": round(_percentile(state_ms, 0.95), 3),
        "scroll_step_ms_median": round(statistics.median(scroll_ms), 3),
        "scroll_step_ms_p95": round(_percentile(scroll_ms, 0.95), 3),
        "scroll_steps_over_16_7_ms": sum(value > 16.7 for value in scroll_ms),
        "background_cancel_ms": round(cancel_ms, 3),
        "measurement_notes": [
            "Placeholder cells only; no image decode or disk thumbnail I/O.",
            "Offscreen/headless CI timing does not measure compositor presentation.",
            "Scroll timing measures synchronous scroll, repaint, and event processing per step.",
            "RSS is peak RSS on Unix and current working set on Windows.",
        ],
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--benchmark-json", type=Path)
    args = parser.parse_args(argv)

    external_launch_ns = os.environ.get("DEFIANTMAPLE_LAUNCH_TIME_NS")
    started = time.perf_counter()
    app = QApplication(sys.argv[:1])
    window = GalleryWindow(args.catalog)
    window.show()
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
    raise SystemExit(main())
