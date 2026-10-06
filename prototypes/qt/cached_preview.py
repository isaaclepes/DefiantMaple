"""Qt adapters for bounded, original-independent cached previews."""
from dataclasses import replace
from pathlib import Path
import threading

from PySide6.QtCore import QEvent, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from defiantmaple.cached_preview import (CacheReadLimits, CachedResult, availability_text,
                                        capture_target, read_cached_preview)
from prototypes.qt.preview import PreviewCanvas, _checker_brush


def result_image(result: CachedResult) -> QImage:
    """Runs in the QThread: only tightly bounded raw pixels, never a cache path."""
    if result.status != "ready" or not result.cleanup_complete:
        return QImage()
    if (not 0 < result.width <= 2048 or not 0 < result.height <= 2048
            or len(result.pixels) != result.width * result.height * 4
            or len(result.pixels) > 16 * 1024 * 1024):
        raise ValueError("Invalid bounded cache pixel delivery")
    return QImage(result.pixels, result.width, result.height, result.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


def preview_text(result: CachedResult, asset: dict) -> str:
    text = result.message
    if result.status == "ready":
        text = f"Cached preview of last indexed content · {result.width} × {result.height} pixels"
        if result.cache_edge != result.requested_edge:
            text += f" · size fallback {result.cache_edge} (requested {result.requested_edge})"
    text += " · at request: " + availability_text(asset)
    if result.catalog_drift:
        text += " · catalog metadata/location changed; captured indexed content retained"
    return text


class CachedPreviewWorker(QThread):
    completed = Signal(QImage, object)

    def __init__(self, database, asset, cache_root, edge=2048, limits=CacheReadLimits()):
        super().__init__()
        self.database = Path(database)
        self.asset = dict(asset)
        self.target = capture_target(self.asset)
        self.cache_root = Path(cache_root)
        self.edge, self.limits = edge, limits
        self._cancel = threading.Event()
        self.outcome = None
        self.rgba_bytes = 0

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            self.outcome = read_cached_preview(self.database, self.target, self.cache_root,
                                              self.edge, self.limits, self._cancel)
            image = result_image(self.outcome)
            self.rgba_bytes = len(self.outcome.pixels)
            self.outcome = replace(self.outcome, pixels=b"")
        except (ValueError, OSError, RuntimeError) as exc:
            self.outcome = CachedResult("refused", f"Cached preview refused: {exc}", self.target)
            image = QImage()
        if not self._cancel.is_set():
            self.completed.emit(image, self.outcome)


class CachedPreviewDialog(QDialog):
    """One immutable captured cache-only inspector and one owned worker."""
    def __init__(self, database, asset, cache_root, parent=None, limits=CacheReadLimits()):
        super().__init__(parent)
        self.asset = dict(asset)
        self.target = capture_target(self.asset)
        self.setWindowTitle(f"DefiantMaple — Cached preview {Path(self.target.path).name}")
        self.resize(980, 740)
        self.status = QLabel("Loading cached preview · at request: " + availability_text(self.asset))
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Cached preview dimensions and last observed availability")
        self.canvas = PreviewCanvas(self)
        self.canvas.setAccessibleName("Cached indexed preview; drag to pan, wheel to zoom")
        self.fit_button = QPushButton("Fit")
        self.fit_button.clicked.connect(self.canvas.fit_image)
        self.zoom_in_button = QPushButton("Zoom in")
        self.zoom_in_button.clicked.connect(lambda: self.canvas.zoom(1.25))
        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_out_button.clicked.connect(lambda: self.canvas.zoom(.8))
        self.background_box = QComboBox()
        self.background_box.addItems(("Checker", "Light", "Dark"))
        self.background_box.setAccessibleName("Cached preview transparency background")
        self.background_box.currentTextChanged.connect(self._background_changed)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        controls = QHBoxLayout()
        for widget in (self.fit_button, self.zoom_in_button, self.zoom_out_button,
                       self.background_box, self.close_button):
            controls.addWidget(widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        for widget in (self.canvas, self.canvas.viewport(), self.fit_button, self.zoom_in_button,
                       self.zoom_out_button, self.background_box, self.close_button):
            widget.installEventFilter(self)
        self._closing = False
        self._close_pending = False
        self.result = None
        self.worker = CachedPreviewWorker(database, self.asset, cache_root, limits=limits)
        self.worker.completed.connect(self._received)
        self.worker.finished.connect(self._finish_pending_close)
        self.worker.start()

    def _received(self, image, result):
        if self._closing or self.worker._cancel.is_set() or result.target != self.target:
            return
        self.result = result
        self.status.setText(preview_text(result, self.asset))
        if not image.isNull() and result.status == "ready" and result.cleanup_complete:
            self.canvas.set_image(QPixmap.fromImage(image))

    def _background_changed(self, name):
        self.canvas.setBackgroundBrush(_checker_brush() if name == "Checker" else
                                       QBrush(QColor("#ffffff" if name == "Light" else "#222222")))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and self._handle_key(event.key()):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if self._handle_key(event.key()):
            event.accept()
        else:
            super().keyPressEvent(event)

    def _handle_key(self, key):
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_F:
            self.canvas.fit_image()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom(1.25)
        elif key == Qt.Key.Key_Minus:
            self.canvas.zoom(.8)
        else:
            return False
        return True

    def closeEvent(self, event):
        self._closing = True
        self.worker.cancel()
        # Never destroy ownership after an incomplete helper reap.
        if not self.worker.wait(2500):
            self._close_pending = True
            self.status.setText("Stopping cached preview worker…")
            event.ignore()
            return
        if self.worker.outcome is not None and not self.worker.outcome.cleanup_complete:
            self.status.setText("Cache worker cleanup failed; ownership retained; replacement refused")
            event.ignore()
            return
        self.canvas.scene().clear()
        self.canvas._item = None
        super().closeEvent(event)

    def _finish_pending_close(self):
        if self._close_pending:
            self._close_pending = False
            QTimer.singleShot(0, self.close)
            parent = self.parentWidget()
            if parent is not None and getattr(parent, "_closing", False):
                QTimer.singleShot(0, parent.close)
