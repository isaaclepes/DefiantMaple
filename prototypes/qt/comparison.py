"""Two immutable image targets; cache-only by default, explicit verified originals."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import html
import io
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
import warnings

from PIL import Image, ImageFile, ImageOps
from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from defiantmaple.cached_preview import (
    CachedTarget, _DirectoryTree, _address_space_limit, _identity, _unsafe,
    availability_text, capture_target, fresh_generation_refusal, generation_refusal,
    read_bounded_cache_file, read_cached_preview,
)
from prototypes.qt.cached_preview import result_image
from prototypes.qt.preview import (
    FullImageWorker, PreviewCanvas, SUPPORTED_MEDIA, _checker_brush,
    _FULL_IMAGE_OWNERS, _FULL_IMAGE_OWNERS_LOCK,
)


@dataclass(frozen=True)
class OriginalLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_dimension: int = 8192
    max_pixels: int = 8_388_608
    max_rgba_bytes: int = 32 * 1024 * 1024
    timeout_seconds: float = 12.0
    address_space_bytes: int = 512 * 1024 * 1024

    def __post_init__(self):
        for name, maximum in (("max_source_bytes", 64 * 1024 * 1024),
                              ("max_dimension", 8192), ("max_pixels", 8_388_608),
                              ("max_rgba_bytes", 32 * 1024 * 1024),
                              ("address_space_bytes", 512 * 1024 * 1024)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError(f"Invalid comparison original {name}")
        if (type(self.timeout_seconds) not in (int, float) or
                not 0 < self.timeout_seconds <= 12):
            raise ValueError("Invalid comparison original deadline")


@dataclass(frozen=True)
class ComparisonResult:
    target: CachedTarget
    token: tuple
    mode: str
    status: str
    message: str
    width: int = 0
    height: int = 0
    cache_edge: int = 0
    observed_revision: int = 0
    metadata_drift: bool = False
    cleanup_complete: bool = True
    address_space_enforced: bool = False
    address_space_note: str = ""


class _OriginalFile:
    """Explicit original-only file handle, pinned through final verification."""
    def __init__(self, path):
        self.path = Path(path)
        self.tree = _DirectoryTree(self.path.parent)
        self.stream = None
        try:
            if os.name == "nt":
                import msvcrt
                from defiantmaple.cached_preview import _windows_handle, _KERNEL
                before = self.path.lstat()
                if _unsafe(before) or not stat.S_ISREG(before.st_mode):
                    raise ValueError("Original is not a nonlinked regular file")
                handle = _windows_handle(self.path, False)
                try:
                    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
                except BaseException:
                    _KERNEL.CloseHandle(handle)
                    raise
            else:
                parent = self.tree.handles[-1]
                before = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
                if _unsafe(before) or not stat.S_ISREG(before.st_mode):
                    raise ValueError("Original is not a nonlinked regular file")
                fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW |
                             getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
            try:
                self.stream = os.fdopen(fd, "rb")
            except BaseException:
                os.close(fd)
                raise
            self.before = os.fstat(self.stream.fileno())
            if not stat.S_ISREG(self.before.st_mode) or _identity(before) != _identity(self.before):
                raise ValueError("Original changed while opening")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        stream, self.stream = self.stream, None
        try:
            if stream is not None:
                stream.close()
        finally:
            self.tree.close()

    def verify(self, expected, ceiling, check):
        self.stream.seek(0)
        digest = hashlib.sha256()
        length = 0
        while chunk := self.stream.read(min(1024 * 1024, ceiling - length + 1)):
            check()
            length += len(chunk)
            if length > ceiling:
                raise ValueError("Original exceeds comparison input limit")
            digest.update(chunk)
        if (length != expected.byte_size or digest.hexdigest() != expected.sha256 or
                _identity(self.before) != _identity(os.fstat(self.stream.fileno()))):
            raise ValueError("Original changed or differs from captured fingerprint")
        # Rewalk the pathname: pinned old parent handles must not hide replacement.
        with _OriginalFile(self.path) as current:
            if _identity(current.before) != _identity(self.before):
                raise ValueError("Original pathname changed during decoding")


def _revision(database, target, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Comparison original deadline expired")
    with closing(sqlite3.connect(Path(database).as_uri() + "?mode=ro", uri=True,
                               timeout=min(.25, remaining))) as db:
        row = db.execute("SELECT revision FROM assets WHERE asset_id=?", (target.asset_id,)).fetchone()
    if row is None:
        raise ValueError("Captured asset is no longer indexed")
    return row[0]


def _namespace_path(path):
    """Explicit-original only; absent tails need an unambiguous safe prefix."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Protected namespace requires an absolute path")
    canonical = path.resolve(strict=False)
    current = Path(canonical.anchor)
    for part in canonical.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("Protected namespace prefix cannot be safely classified")
    return canonical


def _scratch_isolation(database, scratch, cache_root, target, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Comparison original deadline expired")
    with closing(sqlite3.connect(Path(database).as_uri() + "?mode=ro", uri=True,
                               timeout=min(.25, remaining))) as db:
        roots = [Path(row[0]) for row in db.execute("SELECT root_path FROM sources")]
    roots.extend((Path(cache_root), Path(target.path).parent, Path(database).parent))
    canonical_roots = [_namespace_path(root) for root in roots]
    if any(scratch.is_relative_to(root) for root in canonical_roots):
        raise ValueError("Original scratch overlaps a registered source, captured source directory, catalog directory or published cache; load refused")


def _send_reply(connection, payload):
    value = json.dumps(payload, allow_nan=False).encode("utf-8")
    if len(value) > 16 * 1024:
        raise ValueError("Original reply exceeds bounded transport limit")
    connection.send_bytes(value)


def _read_reply(connection):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate original reply field")
            result[key] = value
        return result
    value = json.loads(connection.recv_bytes(16 * 1024).decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite reply")))
    if type(value) is not dict:
        raise ValueError("Malformed original reply")
    return value


def _comparison_original(database, asset, target, cache_root, limits, deadline, sender, request):
    enforcement = (False, "Original helper did not establish address-space enforcement")
    try:
        enforcement = _address_space_limit(limits.address_space_bytes)
        def check():
            if time.monotonic() >= deadline:
                raise TimeoutError("Comparison original deadline expired")
        def admission():
            check()
            reason = fresh_generation_refusal(Path(database), target, asset)
            if reason:
                raise ValueError(reason)
            return _revision(database, target, deadline)
        admission()
        # Do not call tempfile.gettempdir here: its directory selection can
        # create probe files before a registered source is classified.
        candidate = (os.environ.get("TMPDIR") or os.environ.get("TEMP") or os.environ.get("TMP")
                     or ("/tmp" if os.name != "nt" else ""))
        if not candidate:
            raise ValueError("No classifiable original scratch base")
        base = _namespace_path(candidate)
        with _DirectoryTree(base):
            pass
        _scratch_isolation(database, base, cache_root, target, deadline)
        check()
        _send_reply(sender, {"stage": "safe_temp_base", "request": request, "base": str(base),
                             "enforced": enforcement[0], "note": enforcement[1][:2048]})
        while not sender.poll(.025):
            check()
        plan = _read_reply(sender)
        if (plan.get("stage") != "output_path" or plan.get("request") != request
                or type(plan.get("output")) is not str or len(plan["output"]) > 4096):
            raise ValueError("Malformed original output plan")
        output = Path(plan["output"])
        if (not output.is_absolute() or ".." in output.parts or output.name != "pixels.rgba"
                or output.parent.parent != base or not output.parent.name.startswith("defiantmaple-comparison-original-")
                or output.parent.resolve(strict=True) != output.parent):
            raise ValueError("Original output plan escaped approved scratch base")
        _scratch_isolation(database, output.parent, cache_root, target, deadline)
        admission()
        Image.MAX_IMAGE_PIXELS = limits.max_pixels
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with _OriginalFile(target.path) as original:
            if original.before.st_size != target.byte_size or target.byte_size > limits.max_source_bytes:
                raise ValueError("Original size differs from fingerprint or exceeds comparison input limit")
            check()
            encoded = original.stream.read(limits.max_source_bytes + 1)
            if len(encoded) != target.byte_size or hashlib.sha256(encoded).hexdigest() != target.sha256:
                raise ValueError("Original differs from captured fingerprint")
            check()
            with Image.open(io.BytesIO(encoded)) as source:
                width, height = source.size
                if (not 0 < width <= limits.max_dimension or not 0 < height <= limits.max_dimension
                        or width * height > limits.max_pixels):
                    raise ValueError("Original exceeds comparison dimension/pixel limit; use a smaller image")
                source.seek(0)
                oriented = ImageOps.exif_transpose(source)
                try:
                    rendered = oriented.convert("RGBA")
                    try:
                        width, height = rendered.size
                        if width * height * 4 > limits.max_rgba_bytes:
                            raise ValueError("Original exceeds comparison RGBA limit")
                        pixels = rendered.tobytes()
                    finally:
                        rendered.close()
                finally:
                    oriented.close()
            del encoded
            check()
            original.verify(target, limits.max_source_bytes, check)
            revision = admission()
            if len(pixels) != width * height * 4:
                raise ValueError("Malformed original RGBA output")
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(pixels)
            check()
        _send_reply(sender, {"stage": "decoded", "request": request, "size": (width, height),
                            "revision": revision, "error": "", "enforced": enforcement[0],
                            "note": enforcement[1][:2048]})
    except Exception as exc:
        _send_reply(sender, {"stage": "refused", "request": request,
                            "error": f"Original refused: {type(exc).__name__}: {exc}"[:2048],
                            "enforced": enforcement[0], "note": enforcement[1][:2048]})
    finally:
        sender.close()


class ComparisonWorker(FullImageWorker):
    """One load; shared lifecycle retains any failed original reap owner."""
    delivered = Signal(object, QImage)

    def __init__(self, database, cache_root, asset, token, mode="cache", limits=OriginalLimits()):
        super().__init__(asset, limits)
        if mode not in ("cache", "original"):
            raise ValueError("Invalid comparison load mode")
        if asset.get("media_type") not in SUPPORTED_MEDIA or type(token) is not tuple:
            raise ValueError("Comparison requires a supported image and immutable request token")
        self.database = Path(database)
        self.cache_root = Path(cache_root)
        self.target = capture_target(dict(asset))
        self.token = token
        self.mode = mode
        self.outcome = None
        self._request = uuid.uuid4().hex
        self._watchdog_stop = threading.Event()
        self._watchdog = None
        self._supervision_lock = threading.Lock()
        self._budget_lock = threading.Lock()
        self._cleanup_deadline = None
        self.receipt_stage = None

    def _cleanup_budget(self):
        with self._budget_lock:
            if self._cleanup_deadline is None:
                self._cleanup_deadline = time.monotonic() + 2
            return self._cleanup_deadline

    def retry_cleanup(self):
        if self.isRunning() or self.cleanup_complete:
            return False
        with self._budget_lock:
            self._cleanup_deadline = None
        return super().retry_cleanup()

    def _watch(self, process, sender, deadline):
        while not self._watchdog_stop.wait(.01):
            if not self._cancel.is_set() and time.monotonic() < deadline:
                continue
            if process.pid is None:
                continue  # Startup still owns this worker; no replacement admitted.
            cleanup_deadline = self._cleanup_budget()
            with self._supervision_lock:
                try:
                    sender.close()  # EOF can unblock receipt once the child exits.
                    if process.is_alive():
                        process.terminate()
                    process.join(min(1, max(0, cleanup_deadline - time.monotonic())))
                    if process.is_alive():
                        process.kill()
                        process.join(min(1, max(0, cleanup_deadline - time.monotonic())))
                except OSError:
                    pass  # The supervising reap determines actual cleanup truth.
            return

    def _reap(self):
        """One two-second cleanup budget includes watchdog shutdown and joins."""
        cleanup_deadline = self._cleanup_budget()
        self.state = "cleanup-pending"
        self._watchdog_stop.set()
        try:
            if self._watchdog is not None:
                self._watchdog.join(max(0, cleanup_deadline - time.monotonic()))
                if self._watchdog.is_alive():
                    raise RuntimeError("Original watchdog still owns pending transport cleanup")
            if not self._supervision_lock.acquire(timeout=max(0, cleanup_deadline - time.monotonic())):
                raise RuntimeError("Original process supervision remains owned")
            try:
                process = self._process
                if process is not None and process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(min(1, max(0, cleanup_deadline - time.monotonic())))
                    if process.is_alive():
                        process.kill()
                        process.join(min(1, max(0, cleanup_deadline - time.monotonic())))
                    if process.is_alive():
                        raise RuntimeError("Original helper could not be reaped")
                if self._temporary is not None:
                    self._temporary.cleanup()
            finally:
                self._supervision_lock.release()
        except (OSError, RuntimeError) as exc:
            self.cleanup_complete = False
            self.state = "cleanup-failed"
            with _FULL_IMAGE_OWNERS_LOCK:
                _FULL_IMAGE_OWNERS.add(self)
            return str(exc)
        self._process = self._temporary = None
        self.cleanup_complete = True
        self.state = "clean"
        with _FULL_IMAGE_OWNERS_LOCK:
            _FULL_IMAGE_OWNERS.discard(self)
        return ""

    def _result(self, status, message, **fields):
        return ComparisonResult(self.target, self.token, self.mode, status, message, **fields)

    def run(self):
        if self._cleanup_only and self.mode == "original":
            error = self._reap()
            self.outcome = self._result("cleanup_failed" if error else "canceled", error,
                                        cleanup_complete=self.cleanup_complete)
            return
        if self.mode == "cache":
            try:
                # Core reaps its retained orphans before checking cancellation. A
                # cleanup-only retry must then return without spawning/decoding.
                if self._cleanup_only:
                    self._cancel.set()
                cached = read_cached_preview(self.database, self.target, self.cache_root,
                                             requested_edge=2048, cancel_event=self._cancel)
                self.cleanup_complete = cached.cleanup_complete
                image = result_image(cached) if cached.status == "ready" and not self._cleanup_only else QImage()
                if cached.status == "ready" and not self._cleanup_only and (
                        image.isNull() or (image.width(), image.height()) != (cached.width, cached.height)):
                    raise ValueError("Bounded cached image copy could not be created")
                self.outcome = self._result(cached.status, cached.message, width=cached.width,
                                            height=cached.height, cache_edge=cached.cache_edge,
                                            metadata_drift=cached.catalog_drift,
                                            cleanup_complete=cached.cleanup_complete,
                                            address_space_enforced=cached.address_space_enforced,
                                            address_space_note=cached.address_space_note)
                self.state = "clean" if cached.cleanup_complete else "cleanup-failed"
            except Exception as exc:
                image = QImage()
                self.outcome = self._result("refused", f"Cached preview refused: {type(exc).__name__}: {exc}",
                                            cleanup_complete=self.cleanup_complete)
            if not self._cancel.is_set() and not self._cleanup_only:
                self.delivered.emit(self.outcome, image)
            return
        deadline = time.monotonic() + self.limits.timeout_seconds
        image, error, payload = QImage(), "", {}
        receiver = sender = None
        try:
            with _FULL_IMAGE_OWNERS_LOCK:
                if _FULL_IMAGE_OWNERS:
                    raise ValueError("Previous original helper still owns cleanup; close/retry that viewer")
            reason = generation_refusal(self.asset)
            if reason:
                raise ValueError(reason)
            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=True)
            self._process = context.Process(target=_comparison_original,
                args=(self.database, self.asset, self.target, self.cache_root,
                      self.limits, deadline, sender, self._request))
            self.cleanup_complete = False
            self.state = "running"
            self._watchdog = threading.Thread(target=self._watch,
                args=(self._process, sender, deadline), name="comparison-child-watchdog", daemon=True)
            self._watchdog.start()
            self._process.start()
            sender.close()
            while not receiver.poll(.025):
                if self._cancel.is_set():
                    raise InterruptedError("Original load canceled")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Comparison original deadline expired")
                if not self._process.is_alive():
                    raise RuntimeError("Original helper exited without a result")
            self.receipt_stage = "safe_temp_base"
            payload = _read_reply(receiver)
            if payload.get("request") != self._request:
                raise ValueError("Mismatched original request reply")
            if payload.get("error"):
                if payload.get("stage") != "refused" or type(payload["error"]) is not str:
                    raise ValueError("Malformed original refusal reply")
                raise ValueError(payload["error"])
            base = payload.get("base")
            if (set(payload) != {"stage", "request", "base", "enforced", "note"}
                    or payload.get("stage") != "safe_temp_base" or type(base) is not str
                    or not 0 < len(base) <= 4096 or not Path(base).is_absolute()
                    or ".." in Path(base).parts or str(Path(base)) != base
                    or type(payload.get("enforced")) is not bool or type(payload.get("note")) is not str
                    or len(payload["note"]) > 2048):
                raise ValueError("Malformed original safe-temp-base reply")
            if self._cancel.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Original canceled/expired before scratch creation")
            self._temporary = tempfile.TemporaryDirectory(prefix="defiantmaple-comparison-original-", dir=base)
            scratch = Path(self._temporary.name).resolve(strict=True)
            output = scratch / "pixels.rgba"
            if self._cancel.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Original canceled/expired before output plan")
            _send_reply(receiver, {"stage": "output_path", "request": self._request, "output": str(output)})
            while not receiver.poll(.025):
                if self._cancel.is_set() or time.monotonic() >= deadline:
                    raise TimeoutError("Comparison original deadline expired or canceled")
                if not self._process.is_alive():
                    raise RuntimeError("Original helper exited without decode result")
            self.receipt_stage = "decoded"
            payload = _read_reply(receiver)
            if payload.get("request") != self._request:
                raise ValueError("Mismatched original decode reply")
            if payload.get("error"):
                if payload.get("stage") != "refused" or type(payload["error"]) is not str:
                    raise ValueError("Malformed original decode refusal")
                raise ValueError(payload["error"])
            if (set(payload) != {"stage", "request", "size", "revision", "error", "enforced", "note"}
                    or payload.get("stage") != "decoded" or type(payload.get("revision")) is not int
                    or payload["revision"] < 0 or type(payload.get("enforced")) is not bool
                    or type(payload.get("note")) is not str or len(payload["note"]) > 2048):
                raise ValueError("Malformed original decode stage")
            size = payload.get("size")
            if (not isinstance(size, (tuple, list)) or len(size) != 2 or
                    any(type(value) is not int or not 0 < value <= self.limits.max_dimension for value in size)
                    or size[0] * size[1] > self.limits.max_pixels):
                raise ValueError("Malformed original dimensions")
            pixels = read_bounded_cache_file(output, self.limits.max_rgba_bytes)
            if len(pixels) != size[0] * size[1] * 4:
                raise ValueError("Malformed original raw byte length")
            image = QImage(pixels, *size, size[0] * 4, QImage.Format.Format_RGBA8888).copy()
            del pixels
            if image.isNull() or (image.width(), image.height()) != tuple(size):
                raise ValueError("Bounded original image copy could not be created")
            reason = fresh_generation_refusal(self.database, self.target, self.asset)
            if reason:
                raise ValueError(reason)
            payload["revision"] = _revision(self.database, self.target, deadline)
        except Exception as exc:
            error = f"Original refused: {type(exc).__name__}: {exc}"
        finally:
            cleanup_error = self._reap()
            if receiver is not None:
                receiver.close()
            if sender is not None:
                sender.close()
        if cleanup_error:
            error = "Original cleanup incomplete; retry Close. " + cleanup_error
        elif self._cancel.is_set():
            error = "Original load canceled"
        elif time.monotonic() >= deadline:
            error = "Comparison original deadline expired"
        if error:
            image = QImage()
        revision = payload.get("revision", self.target.revision)
        self.outcome = self._result("ready" if not error else "refused", error or "Verified captured original",
            width=image.width(), height=image.height(), observed_revision=revision,
            metadata_drift=revision != self.target.revision, cleanup_complete=self.cleanup_complete,
            address_space_enforced=payload.get("enforced", False), address_space_note=payload.get("note", ""))
        if not self._cancel.is_set():
            self.delivered.emit(self.outcome, image)


class ComparisonPane(QWidget):
    def __init__(self, side, asset, parent):
        super().__init__(parent)
        self.side = side
        self.asset = dict(asset)
        self.target = capture_target(self.asset)
        self.result = None
        self.displayed_result = None
        name = Path(self.target.path).name
        self.identity = QLabel()
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.identity.setText(f"{side.title()}: {self.identity.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, 300)}"
                              f" · ID {self.target.asset_id} · revision {self.target.revision}")
        self.identity.setToolTip("<qt>" + html.escape(name, quote=True) + "</qt>")
        self.identity.setWordWrap(True)
        self.status = QLabel("Queued cache-only preview")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName(f"{side.title()} comparison status")
        self.canvas = PreviewCanvas(self)
        self.canvas.setAccessibleName(f"{side.title()} comparison image; drag to pan, wheel to zoom")
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.original_button = QPushButton("Load original")
        self.original_button.setObjectName(f"{side}Original")
        self.cache_button = QPushButton("Reload cached preview")
        self.cache_button.setObjectName(f"{side}Cache")
        self.original_button.clicked.connect(lambda: parent.request(side, "original"))
        self.cache_button.clicked.connect(lambda: parent.request(side, "cache"))
        self.fit_button = QPushButton("Fit")
        self.fit_button.clicked.connect(self.canvas.fit_image)
        self.zoom_in_button = QPushButton("Zoom in")
        self.zoom_in_button.clicked.connect(lambda: self.canvas.zoom(1.25))
        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_out_button.clicked.connect(lambda: self.canvas.zoom(.8))
        self.background_box = QComboBox()
        self.background_box.addItems(("Checker", "Light", "Dark"))
        self.background_box.currentTextChanged.connect(self._background)
        load_controls = QHBoxLayout()
        transform_controls = QHBoxLayout()
        for widget in (self.original_button, self.cache_button):
            load_controls.addWidget(widget)
        for widget in (self.fit_button, self.zoom_in_button, self.zoom_out_button, self.background_box):
            transform_controls.addWidget(widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self.identity)
        layout.addWidget(self.status)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(load_controls)
        layout.addLayout(transform_controls)
        for widget, label in ((self.original_button, "Load captured original"),
                              (self.cache_button, "Reload captured cached preview"),
                              (self.fit_button, "Fit image"), (self.zoom_in_button, "Zoom in"),
                              (self.zoom_out_button, "Zoom out"),
                              (self.background_box, "Transparency background")):
            widget.setAccessibleName(f"{side.title()} {label}")
        self.canvas.installEventFilter(parent)
        self.canvas.viewport().installEventFilter(parent)

    def _background(self, name):
        self.canvas.setBackgroundBrush(_checker_brush() if name == "Checker" else
            QBrush(QColor("#ffffff" if name == "Light" else "#222222")))

    def set_busy(self, busy):
        self.cache_button.setEnabled(not busy)
        reason = generation_refusal(self.asset)
        self.original_button.setEnabled(not busy and reason is None)
        self.original_button.setToolTip(reason or "Explicitly verify and load the captured original")

    def consume(self, result, image):
        self.result = result
        if result.status == "ready" and result.cleanup_complete and not image.isNull():
            self.canvas.set_image(QPixmap.fromImage(image))
            self.displayed_result = result
        text = result.message
        if result.status == "ready":
            text = ("Captured original · first frame" if result.mode == "original"
                    else "Cached preview of last indexed content")
            text += f" · {result.width} × {result.height} pixels"
            if result.mode == "cache" and result.cache_edge != 2048:
                text += f" · size fallback {result.cache_edge} (requested 2048)"
        elif self.displayed_result is not None:
            prior = self.displayed_result
            text += f" · still showing previous {prior.mode} image {prior.width} × {prior.height}"
        text += " · at capture: " + availability_text(self.asset)
        if result.metadata_drift:
            text += " · catalog metadata/location drift observed; target remains captured"
            if result.mode == "original":
                text += f" (observed revision {result.observed_revision})"
        self.status.setText(text)


class ComparisonDialog(QDialog):
    """Serial loaders, independent canvases, and no target rebasing."""
    def __init__(self, database, cache_root, assets, parent=None, limits=OriginalLimits()):
        if len(assets) != 2 or len({row["asset_id"] for row in assets}) != 2:
            raise ValueError("Select exactly two distinct images to compare")
        if any(row.get("media_type") not in SUPPORTED_MEDIA for row in assets):
            raise ValueError("Comparison supports two PNG, JPEG, GIF or WebP images")
        super().__init__(parent)
        self.database = Path(database)
        self.cache_root = Path(cache_root)
        self.limits = limits
        self.setWindowTitle("DefiantMaple — Compare captured images")
        self.resize(1120, 760)
        self.setObjectName("capturedComparison")
        self.panes = {side: ComparisonPane(side, asset, self)
                      for side, asset in zip(("left", "right"), assets)}
        self.targets = tuple(pane.target for pane in self.panes.values())
        self.worker = None
        self.active = None
        self.queue = []
        self._sequence = 0
        self._consumed = set()
        self._closing = False
        self._close_pending = False
        self.feedback = QLabel("Cache-only loading; originals require an explicit per-pane action.")
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setAccessibleName("Comparison operation status")
        self.fullscreen_button = QPushButton("Full screen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        columns = QHBoxLayout()
        for pane in self.panes.values():
            columns.addWidget(pane, 1)
        controls = QHBoxLayout()
        controls.addWidget(self.feedback, 1)
        controls.addWidget(self.fullscreen_button)
        controls.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addLayout(columns, 1)
        layout.addLayout(controls)
        tab_order = []
        for pane in self.panes.values():
            tab_order.extend((pane.canvas, pane.original_button, pane.cache_button,
                              pane.fit_button, pane.zoom_in_button, pane.zoom_out_button, pane.background_box))
        tab_order.extend((self.fullscreen_button, self.close_button))
        for first, second in zip(tab_order, tab_order[1:]):
            QWidget.setTabOrder(first, second)
        self.panes["left"].canvas.setFocus()
        self.request("left", "cache")
        self.request("right", "cache")

    def request(self, side, mode):
        if side not in self.panes or mode not in ("cache", "original"):
            raise ValueError("Invalid comparison action")
        if self._closing:
            return False
        if self.worker is not None and not self.worker.cleanup_complete:
            if self.active is None:
                self.feedback.setText("Previous helper cleanup incomplete; Close retries cleanup. No new load admitted.")
                return False
        if (self.active and self.active[0] == side) or any(item[0] == side for item in self.queue):
            self.feedback.setText(f"{side.title()} already has a pending load; wait or close.")
            return False
        if mode == "original" and generation_refusal(self.panes[side].asset):
            self.feedback.setText(f"{side.title()} original unavailable at capture; cache viewing remains available.")
            return False
        if len(self.queue) + bool(self.active) >= 2:
            self.feedback.setText("Two pane loads are already admitted; wait or close.")
            return False
        self.queue.append((side, mode))
        self.panes[side].set_busy(True)
        self._advance()
        return True

    def _advance(self):
        if self._closing or self.active is not None or not self.queue:
            return
        if self.worker is not None and (self.worker.isRunning() or not self.worker.cleanup_complete):
            return
        side, mode = self.queue.pop(0)
        self._consumed.clear()
        self._sequence += 1
        token = (id(self), side, self.panes[side].target, mode, self._sequence)
        self.active = (side, mode, token)
        self.worker = ComparisonWorker(self.database, self.cache_root, self.panes[side].asset,
                                       token, mode, self.limits)
        worker = self.worker
        worker.delivered.connect(self._delivered)
        worker._dialog_finish = lambda: self._finished(worker)
        worker.finished.connect(worker._dialog_finish)
        self.panes[side].status.setText(f"Loading {mode} for captured target…")
        worker.start()

    def _delivered(self, result, image):
        self._consumed.add(result.token)
        if self._closing or self.active is None or result.token != self.active[2]:
            return
        pane = self.panes[self.active[0]]
        if result.target != pane.target:
            self.feedback.setText("Mismatched delivery discarded; captured target retained.")
            return
        pane.consume(result, image)

    def _finished(self, worker):
        if worker is not self.worker:
            return
        if self.active is not None:
            self.panes[self.active[0]].set_busy(False)
        self.active = None
        if not worker.cleanup_complete:
            self.queue.clear()
            for pane in self.panes.values():
                pane.set_busy(True)
            self.feedback.setText("Helper cleanup incomplete. Close retries cleanup; no replacement/load admitted.")
            return
        # Break the finished-signal closure's self/worker cycle before replacing
        # this clean worker. A failed cleanup keeps connections for its retry.
        callback = getattr(worker, "_dialog_finish", None)
        if callback is not None:
            worker.finished.disconnect(callback)
            del worker._dialog_finish
        worker.delivered.disconnect(self._delivered)
        if self._closing:
            QTimer.singleShot(0, self.close)
            return
        # Queued image delivery is consumed before admission of the next load.
        if worker.outcome is None or worker.outcome.token not in self._consumed:
            self.queue.clear()
            self.feedback.setText("Load ended without a consumed result; reload explicitly.")
            for pane in self.panes.values():
                pane.set_busy(False)
            return
        QTimer.singleShot(0, self._advance)

    def toggle_fullscreen(self):
        focused = self.focusWidget()
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setText("Full screen")
        else:
            self.showFullScreen()
            self.fullscreen_button.setText("Exit full screen")
        if focused is not None:
            focused.setFocus()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            pane = next((pane for pane in self.panes.values()
                         if watched in (pane.canvas, pane.canvas.viewport())), None)
            if pane is not None and event.key() in (Qt.Key.Key_F, Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
                if event.key() == Qt.Key.Key_F:
                    pane.canvas.fit_image()
                else:
                    pane.canvas.zoom(.8 if event.key() == Qt.Key.Key_Minus else 1.25)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
            else:
                self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._closing = self._close_pending = True
        self.queue.clear()
        for pane in self.panes.values():
            pane.set_busy(True)
            for widget in (pane.canvas, pane.fit_button, pane.zoom_in_button,
                           pane.zoom_out_button, pane.background_box):
                widget.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        if self.worker is not None:
            self.worker.cancel()
            if self.worker.isRunning():
                self.feedback.setText("Stopping comparison helper; ownership retained…")
                event.ignore()
                return
            if not self.worker.cleanup_complete:
                self.feedback.setText("Retrying comparison cleanup; replacement unavailable…")
                self.worker.retry_cleanup()
                event.ignore()
                return
        for pane in self.panes.values():
            pane.canvas.scene().clear()
            pane.canvas._item = None
        event.accept()
        parent = self.parentWidget()
        if parent is not None and getattr(parent, "_closing", False):
            QTimer.singleShot(0, parent.close)


def comparison_smoke(database, cache_root, assets, application):
    """Actual UI workers without showing a native window or dispatching anything."""
    dialog = ComparisonDialog(database, cache_root, assets)
    deadline = time.monotonic() + 30
    def wait():
        while dialog.active or dialog.queue:
            application.processEvents()
            if time.monotonic() >= deadline:
                raise TimeoutError("Comparison package smoke timed out")
            time.sleep(.005)
        application.processEvents()
        if dialog.worker is not None and not dialog.worker.cleanup_complete:
            raise RuntimeError("Comparison package smoke cleanup incomplete")
    try:
        wait()
        if any(pane.result is None or pane.result.status != "ready" for pane in dialog.panes.values()):
            raise ValueError("Comparison package smoke cache load failed")
        cache_sizes = [[pane.result.width, pane.result.height] for pane in dialog.panes.values()]
        right = dialog.panes["right"]
        prior = dialog.worker
        if right.original_button.isEnabled() or dialog.request("right", "original") or dialog.worker is not prior:
            raise ValueError("Comparison package smoke unavailable original was admitted")
        if not dialog.request("left", "original"):
            raise ValueError("Comparison package smoke eligible original not admitted")
        wait()
        left = dialog.panes["left"]
        if left.result.status != "ready" or left.result.mode != "original":
            raise ValueError("Comparison package smoke original failed: " + left.status.text())
        image = left.canvas._item.pixmap().toImage()
        other = right.canvas._item.pixmap().toImage()
        receipt = {"status": "ready", "cache_sizes": cache_sizes,
                   "original_size": [left.result.width, left.result.height],
                   "original_top_rgba": image.pixelColor(5, 5).getRgb(),
                   "original_bottom_rgba": image.pixelColor(5, image.height() - 6).getRgb(),
                   "cached_right_alpha": other.pixelColor(0, 0).alpha(),
                   "unavailable_original_refused": True,
                   "address_space_enforced": left.result.address_space_enforced,
                   "address_space_note": left.result.address_space_note,
                   "address_space_bytes": dialog.limits.address_space_bytes}
    finally:
        dialog.close()
        cleanup_deadline = time.monotonic() + 3
        while dialog.worker is not None and dialog.worker.isRunning() and time.monotonic() < cleanup_deadline:
            application.processEvents()
            time.sleep(.005)
        application.processEvents()
        accepted = dialog.close()
        if not accepted or (dialog.worker is not None and not dialog.worker.cleanup_complete):
            raise RuntimeError("Comparison smoke retains incomplete helper cleanup")
    receipt["cleanup_complete"] = all(pane.canvas._item is None for pane in dialog.panes.values())
    return receipt
