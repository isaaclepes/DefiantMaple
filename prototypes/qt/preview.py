"""Bounded, read-only full-image inspection for cataloged image assets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import multiprocessing
import os
import stat
import tempfile
import threading
import time
import warnings

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError
from PySide6.QtCore import QEvent, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)


@dataclass(frozen=True)
class PreviewLimits:
    max_source_bytes: int = 512 * 1024 * 1024
    max_dimension: int = 32_768
    max_pixels: int = 40_000_000
    timeout_seconds: float = 12.0


SUPPORTED_MEDIA = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _identity(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _decode_original(asset: dict, output: str, limits: PreviewLimits, sender):
    """Only this child process opens the original media file."""
    try:
        Image.MAX_IMAGE_PIXELS = limits.max_pixels
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Path(asset["current_path"]).open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Source is not a regular file")
            if before.st_size != asset["byte_size"]:
                raise ValueError("Source size differs from catalog fingerprint")
            if before.st_size > limits.max_source_bytes:
                raise ValueError("Source exceeds the full-image byte limit")
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            if digest.hexdigest() != asset["sha256"]:
                raise ValueError("Source content differs from catalog fingerprint")
            stream.seek(0)
            with Image.open(stream) as source:
                width, height = source.size
                if (width <= 0 or height <= 0 or width > limits.max_dimension or
                        height > limits.max_dimension or width * height > limits.max_pixels):
                    raise ValueError("Image exceeds full-image dimension or pixel limit")
                source.seek(0)  # Animated formats intentionally show the first frame.
                oriented = ImageOps.exif_transpose(source)
                try:
                    rendered = oriented.convert("RGBA")
                    try:
                        rendered.save(output, format="PNG", optimize=False, compress_level=1)
                        size = rendered.size
                    finally:
                        rendered.close()
                finally:
                    oriented.close()
            after = os.fstat(stream.fileno())
            if _identity(before) != _identity(after) or _identity(before) != _identity(
                    Path(asset["current_path"]).stat()):
                raise ValueError("Source changed during full-image decoding")
        sender.send((size, ""))
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError,
            Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        sender.send((None, f"{type(exc).__name__}: {exc}"))
    except Exception as exc:
        sender.send((None, f"Decoder error: {type(exc).__name__}: {exc}"))
    finally:
        sender.close()


class FullImageWorker(QThread):
    loaded = Signal(QImage, int, int)
    failed = Signal(str)

    def __init__(self, asset: dict, limits: PreviewLimits = PreviewLimits()):
        super().__init__()
        self.asset = dict(asset)
        self.limits = limits
        self._cancel = threading.Event()
        self._process = None
        self._process_lock = threading.Lock()

    def cancel(self):
        self._cancel.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.is_alive():
            process.terminate()

    def run(self):
        if self.asset.get("media_type") not in SUPPORTED_MEDIA:
            self.failed.emit("Full-image inspection is unsupported for this media type.")
            return
        if not isinstance(self.asset.get("sha256"), str) or len(self.asset["sha256"]) != 64:
            self.failed.emit("Catalog fingerprint is invalid.")
            return
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(prefix="defiantmaple-full-image-") as temporary:
            output = str(Path(temporary) / "decoded.png")
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=_decode_original,
                                      args=(self.asset, output, self.limits, sender))
            try:
                with self._process_lock:
                    self._process = process
                try:
                    process.start()
                except (OSError, RuntimeError) as exc:
                    self.failed.emit(f"Could not start full-image decoder: {exc}")
                    return
                sender.close()
                deadline = time.monotonic() + self.limits.timeout_seconds
                while not receiver.poll(0.05):
                    if self._cancel.is_set():
                        return
                    if time.monotonic() >= deadline:
                        self.failed.emit("Full-image decoder timed out.")
                        return
                    if not process.is_alive():
                        self.failed.emit("Full-image decoder exited unexpectedly.")
                        return
                try:
                    size, error = receiver.recv()
                except EOFError:
                    self.failed.emit("Full-image decoder exited unexpectedly.")
                    return
                if self._cancel.is_set():
                    return
                if error:
                    self.failed.emit(error)
                    return
                # QImage decoding is thread-safe. QPixmap creation stays on the GUI thread.
                image = QImage(output)
                if image.isNull() or (image.width(), image.height()) != tuple(size):
                    self.failed.emit("Decoded full image could not be loaded.")
                    return
                if not self._cancel.is_set():
                    self.loaded.emit(image, *size)
            finally:
                if process.is_alive():
                    process.terminate()
                if process.pid is not None:
                    process.join(2)
                    if process.is_alive():
                        process.kill()
                        process.join(2)
                receiver.close()
                sender.close()
                with self._process_lock:
                    self._process = None


def _checker_brush():
    tile = QPixmap(24, 24)
    tile.fill(QColor("#ffffff"))
    painter = QPainter(tile)
    painter.fillRect(0, 0, 12, 12, QColor("#bbbbbb"))
    painter.fillRect(12, 12, 12, 12, QColor("#bbbbbb"))
    painter.end()
    return QBrush(tile)


class PreviewCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(_checker_brush())
        self.setAccessibleName("Full image; drag to pan, wheel to zoom")
        self._item: QGraphicsPixmapItem | None = None
        self._fit = True
        self._scale = 1.0

    def set_image(self, pixmap: QPixmap):
        self.scene().clear()
        self._item = self.scene().addPixmap(pixmap)
        self.scene().setSceneRect(self._item.boundingRect())
        self.fit_image()

    def fit_image(self):
        if self._item is None:
            return
        self._fit = True
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self._scale = self.transform().m11()

    def zoom(self, factor: float):
        if self._item is None:
            return
        target = max(0.05, min(16.0, self._scale * factor))
        self._fit = False
        self.scale(target / self._scale, target / self._scale)
        self._scale = target

    def wheelEvent(self, event):
        if self._item is None:
            return super().wheelEvent(event)
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit_image()


class FullImageDialog(QDialog):
    """Captured asset identity; opening never follows later gallery selection."""
    def __init__(self, asset: dict, parent=None, limits: PreviewLimits = PreviewLimits()):
        super().__init__(parent)
        self.asset = dict(asset)
        self.setWindowTitle(f"DefiantMaple — Inspect {Path(asset['current_path']).name}")
        self.resize(980, 740)
        self.status = QLabel("Loading cataloged original image…")
        self.status.setAccessibleName("Full image status")
        self.canvas = PreviewCanvas(self)
        self.fit_button = QPushButton("Fit")
        self.fit_button.clicked.connect(self.canvas.fit_image)
        self.zoom_in_button = QPushButton("Zoom in")
        self.zoom_in_button.clicked.connect(lambda: self.canvas.zoom(1.25))
        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_out_button.clicked.connect(lambda: self.canvas.zoom(0.8))
        self.fullscreen_button = QPushButton("Full screen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.background_box = QComboBox()
        self.background_box.addItems(("Checker", "Light", "Dark"))
        self.background_box.setAccessibleName("Transparency background")
        self.background_box.currentTextChanged.connect(self._background_changed)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        controls = QHBoxLayout()
        for widget in (self.fit_button, self.zoom_in_button, self.zoom_out_button,
                       self.fullscreen_button, self.background_box, self.close_button):
            controls.addWidget(widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        for widget in (self.canvas, self.canvas.viewport(), self.fit_button,
                       self.zoom_in_button, self.zoom_out_button,
                       self.fullscreen_button, self.background_box, self.close_button):
            widget.installEventFilter(self)
        self.worker = FullImageWorker(self.asset, limits)
        self._close_pending = False
        self.worker.loaded.connect(self._loaded)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finish_pending_close)
        self.worker.start()

    def _loaded(self, image: QImage, width: int, height: int):
        if not self.worker._cancel.is_set():
            self.canvas.set_image(QPixmap.fromImage(image))
            self.status.setText(f"Original image · {width} × {height} pixels · first frame")

    def _failed(self, message: str):
        if not self.worker._cancel.is_set():
            self.status.setText(message)

    def _background_changed(self, name: str):
        if name == "Checker":
            self.canvas.setBackgroundBrush(_checker_brush())
        else:
            self.canvas.setBackgroundBrush(QBrush(QColor("#ffffff" if name == "Light" else "#222222")))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setText("Full screen")
        else:
            self.showFullScreen()
            self.fullscreen_button.setText("Exit full screen")

    def keyPressEvent(self, event):
        if self._handle_key(event.key()):
            event.accept()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and self._handle_key(event.key()):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _handle_key(self, key):
        if key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_F:
            self.canvas.fit_image()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom(1.25)
        elif key == Qt.Key.Key_Minus:
            self.canvas.zoom(0.8)
        else:
            return False
        return True

    def closeEvent(self, event):
        self.worker.cancel()
        if not self.worker.wait(2_000):
            self._close_pending = True
            self.status.setText("Stopping full-image decoder…")
            event.ignore()
            return
        super().closeEvent(event)

    def _finish_pending_close(self):
        if self._close_pending:
            self._close_pending = False
            parent = self.parentWidget()
            QTimer.singleShot(0, self.close)
            if parent is not None and getattr(parent, "_closing", False):
                QTimer.singleShot(0, parent.close)
