"""Dormant, serial catalog gateway for a future bounded gallery model.

This module has no GalleryWindow wiring. A request names a registered module-level
operation and carries copied data, never a callback or QObject from the GUI.
Read operations share one worker-owned read-only connection; service writes use
their existing separate connections only after the read transaction has ended.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import inspect
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping

from PySide6.QtCore import QObject, QThread, Signal

from defiantmaple.catalog import SCHEMA_VERSION
from defiantmaple.gallery_query import StaleTarget, ViewChanged


class RequestClass(str, Enum):
    APPLY = "apply"
    PAGE = "page"
    RANK = "rank"
    DETAIL = "detail"
    TAXONOMY = "taxonomy"
    SOURCE = "source"
    LEGACY = "legacy"
    MUTATION = "mutation"


class RequestCancelled(Exception):
    """A queued or active read was superseded or closing began."""


class ReadDeadlineExceeded(Exception):
    """A cooperative gallery-read deadline expired."""


class CatalogReplaced(Exception):
    """The path no longer names the worker's original catalog file."""


class CatalogUnavailable(Exception):
    """The original catalog path cannot be checked before dispatch."""


@dataclass(frozen=True)
class OperationSpec:
    """Trusted module-level function: (connection_or_path, context, *args, **kwargs)."""

    write: bool
    handler: Callable[..., Any]


@dataclass(frozen=True)
class CatalogRequest:
    request_id: int
    category: RequestClass
    operation: str
    args: tuple[Any, ...] = ()
    kwargs: tuple[tuple[str, Any], ...] = ()
    context: str = ""
    generation: int = 0
    deadline_seconds: float = 2.0


@dataclass(frozen=True)
class Admission:
    accepted: bool
    reason: str = ""


@dataclass(frozen=True)
class Acknowledgement:
    accepted: bool
    resources: tuple[Any, ...] = ()


@dataclass(frozen=True)
class CatalogReply:
    request_id: int
    category: RequestClass
    generation: int
    status: str
    value: Any = None
    message: str = ""
    data_version: int | None = None
    file_identity: tuple[int, int] | None = None
    worker_thread_id: int | None = None


@dataclass(frozen=True)
class ReadContext:
    """Snapshot identity and cooperative stop state valid only during one read."""

    data_version: int
    file_identity: tuple[int, int]
    cancel_event: threading.Event
    deadline: float

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise RequestCancelled("Catalog read canceled")
        if time.monotonic() >= self.deadline:
            raise ReadDeadlineExceeded("Catalog read deadline exceeded")


@dataclass(frozen=True)
class LegacyContext:
    """Cooperative cancellation without a gallery snapshot or deadline claim."""

    cancel_event: threading.Event

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise RequestCancelled("Legacy catalog task canceled")


def _copied_data(value: Any, *, depth: int = 0, budget: list[int] | None = None,
                 bounded: bool = True, max_nodes: int = 8_192) -> Any:
    """Copy data without crossing GUI/code ownership; bound new gallery traffic."""
    if bounded and depth > 16:
        raise ValueError("Catalog request is too deeply nested")
    if budget is not None:
        budget[0] += 1
        budget[1] += (len(value.encode("utf-8")) if type(value) is str else
                      len(value) if type(value) is bytes else
                      len(str(value).encode("utf-8")) if isinstance(value, Path) else 32)
        if budget[0] > max_nodes or budget[1] > 2 * 1024 * 1024:
            raise ValueError("Catalog request payload exceeds its size bound")
    if value is None or type(value) in (bool, int, float, str, bytes):
        if bounded and type(value) in (str, bytes) and len(value) > 64 * 1024:
            raise ValueError("Catalog request field exceeds 64 KiB")
        return value
    if isinstance(value, QObject) or callable(value):
        raise TypeError("Catalog requests cannot carry QObjects or callbacks")
    if isinstance(value, Path):
        return value
    if isinstance(value, Enum):
        if type(value.value) not in (bool, int, float, str, bytes):
            raise TypeError("Catalog enum values must be immutable scalar data")
        return value
    if type(value) is tuple:
        if bounded and len(value) > 1_024:
            raise ValueError("Catalog request tuple is too large")
        return tuple(_copied_data(item, depth=depth + 1, budget=budget,
                                  bounded=bounded, max_nodes=max_nodes) for item in value)
    if type(value) is list:
        if bounded and len(value) > 1_024:
            raise ValueError("Catalog request list is too large")
        return [_copied_data(item, depth=depth + 1, budget=budget,
                             bounded=bounded, max_nodes=max_nodes) for item in value]
    if type(value) is dict:
        if bounded and len(value) > 1_024:
            raise ValueError("Catalog request mapping is too large")
        return {_copied_data(key, depth=depth + 1, budget=budget, bounded=bounded,
                             max_nodes=max_nodes):
                _copied_data(item, depth=depth + 1, budget=budget, bounded=bounded,
                             max_nodes=max_nodes)
                for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type) and value.__dataclass_params__.frozen:
        return type(value)(**{field.name: _copied_data(getattr(value, field.name),
                                                       depth=depth + 1, budget=budget,
                                                       bounded=bounded, max_nodes=max_nodes)
                              for field in fields(value)})
    raise TypeError(f"Unsupported catalog request value: {type(value).__name__}")


class CatalogGateway(QThread):
    """One worker, one active request, fixed pending slots, no GUI-thread waits."""

    completed = Signal(object)
    ready = Signal()
    failed = Signal(str)

    max_legacy_pending = 4
    max_pages_pending = 2

    def __init__(self, database: Path, operations: Mapping[str, OperationSpec], parent=None):
        super().__init__(parent)
        self.database = Path(database).resolve(strict=True)
        # Set on the worker after opening the persistent read connection. It
        # identifies that connection, not merely the current path at a request.
        self._reader_file_identity: tuple[int, int] | None = None
        if not operations:
            raise ValueError("Catalog gateway needs registered operations")
        self._operations = dict(operations)
        for name, spec in self._operations.items():
            if not isinstance(name, str) or not name or not isinstance(spec, OperationSpec):
                raise TypeError("Invalid catalog operation registration")
            function = spec.handler
            if (not inspect.isfunction(function) or function.__closure__ is not None
                    or "<locals>" in function.__qualname__):
                raise TypeError("Catalog handlers must be module-level functions")
        self._condition = threading.Condition()
        self._stopping = False
        self._ever_started = False
        self._finished = False
        self._active: CatalogRequest | None = None
        self._active_cancel: threading.Event | None = None
        self._active_write = False
        self._write_waiting_ack: int | None = None
        self._pending_write: CatalogRequest | None = None
        self._apply: CatalogRequest | None = None
        self._pages: OrderedDict[str, CatalogRequest] = OrderedDict()
        self._rank: CatalogRequest | None = None
        self._detail: CatalogRequest | None = None
        self._taxonomy: CatalogRequest | None = None
        self._source: CatalogRequest | None = None
        self._legacy: OrderedDict[str, CatalogRequest] = OrderedDict()
        self._ids: set[int] = set()
        self._last_request_id = -1
        # These references live only on the GUI-owned QThread object. The worker
        # never dereferences them; the caller must not clean them until ack.
        self._retained: dict[int, tuple[Any, ...]] = {}
        self._replied_ids: set[int] = set()

    @property
    def close_complete(self) -> bool:
        with self._condition:
            stopped = ((self._finished and not self.isRunning())
                       or (self._stopping and not self._ever_started))
            return stopped and not self._retained and self._write_waiting_ack is None

    @property
    def pending_count(self) -> int:
        with self._condition:
            return (int(self._pending_write is not None) + int(self._apply is not None)
                    + len(self._pages) + int(self._rank is not None)
                    + int(self._detail is not None) + int(self._taxonomy is not None)
                    + int(self._source is not None) + len(self._legacy))

    def start(self, priority=QThread.Priority.InheritPriority):
        self._require_owner_thread()
        with self._condition:
            if self._ever_started or self._stopping:
                raise RuntimeError("Catalog gateway cannot restart")
            self._ever_started = True
        super().start(priority)

    def _require_owner_thread(self) -> None:
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Catalog gateway control and resource ownership require its GUI thread")

    @staticmethod
    def _reply(request: CatalogRequest, status: str, message: str = "") -> CatalogReply:
        return CatalogReply(request.request_id, request.category, request.generation,
                            status, message=message)

    def submit(self, request: CatalogRequest, *, retain: tuple[Any, ...] = ()) -> Admission:
        """Transfer non-QObject resource ownership until its result is handled.

        Retained objects are never passed to a worker handler. The GUI caller
        must defer explicit cleanup of their paths/handles until it acknowledges
        the result; a refused submission leaves ownership with the caller.
        """
        self._require_owner_thread()
        if not isinstance(request, CatalogRequest):
            raise TypeError("Expected CatalogRequest")
        if type(retain) is not tuple or len(retain) > 16:
            raise ValueError("Catalog retained resources must be a small tuple")
        if any(isinstance(item, QObject) or callable(item) for item in retain):
            raise TypeError("Cannot retain QObjects or callbacks for catalog work")
        if type(request.request_id) is not int or request.request_id < 0:
            raise ValueError("Catalog request ID must be a nonnegative integer")
        if type(request.generation) is not int or request.generation < 0:
            raise ValueError("Catalog generation must be a nonnegative integer")
        if not isinstance(request.category, RequestClass):
            raise TypeError("Unknown catalog request class")
        if request.operation not in self._operations:
            raise ValueError("Unregistered catalog operation")
        spec = self._operations[request.operation]
        if spec.write != (request.category == RequestClass.MUTATION):
            raise ValueError("Catalog operation/request class mismatch")
        if type(request.context) is not str or len(request.context) > 256:
            raise ValueError("Catalog request context is invalid")
        if request.category in (RequestClass.PAGE, RequestClass.LEGACY) and not request.context:
            raise ValueError("Page and legacy requests require a context key")
        if (type(request.deadline_seconds) not in (int, float)
                or not 0 < request.deadline_seconds <= 30):
            raise ValueError("Catalog read deadline must be in (0,30] seconds")
        if type(request.args) is not tuple or type(request.kwargs) is not tuple:
            raise TypeError("Catalog request args/kwargs must be tuples")
        if len(request.kwargs) > 32 or any(type(key) is not str for key, _ in request.kwargs):
            raise ValueError("Catalog keyword arguments are invalid")
        if len({key for key, _ in request.kwargs}) != len(request.kwargs):
            raise ValueError("Duplicate catalog keyword")
        budget = [0, 0]
        copied = CatalogRequest(request.request_id, request.category, request.operation,
                                _copied_data(request.args, budget=budget),
                                _copied_data(request.kwargs, budget=budget),
                                request.context, request.generation, float(request.deadline_seconds))
        replaced: list[CatalogRequest] = []
        invalidated: list[CatalogRequest] = []
        with self._condition:
            if self._stopping or self._finished:
                return Admission(False, "Catalog gateway is closing")
            if copied.request_id <= self._last_request_id:
                return Admission(False, "Catalog request IDs must increase")
            if (copied.category != RequestClass.MUTATION
                    and (self._pending_write is not None or self._active_write
                         or self._write_waiting_ack is not None)):
                return Admission(False, "Catalog change pending; retry the read after its result")
            if copied.category == RequestClass.MUTATION:
                if (self._pending_write is not None or self._active_write
                        or self._write_waiting_ack is not None):
                    return Admission(False, "A catalog change is already pending")
                self._pending_write = copied
                for slot in ("_apply", "_rank", "_detail", "_taxonomy", "_source"):
                    pending = getattr(self, slot)
                    if pending is not None:
                        invalidated.append(pending)
                        setattr(self, slot, None)
                invalidated.extend(self._pages.values())
                self._pages.clear()
                if self._active_cancel is not None:
                    self._active_cancel.set()
            elif copied.category == RequestClass.APPLY:
                if self._apply is not None:
                    replaced.append(self._apply)
                self._apply = copied
                if self._active_cancel is not None and not self._active_write:
                    self._active_cancel.set()
            elif copied.category == RequestClass.PAGE:
                previous = self._pages.pop(copied.context, None)
                if previous is not None:
                    replaced.append(previous)
                elif len(self._pages) == self.max_pages_pending:
                    _, previous = self._pages.popitem(last=False)
                    replaced.append(previous)
                self._pages[copied.context] = copied
            elif copied.category == RequestClass.LEGACY:
                previous = self._legacy.pop(copied.context, None)
                if previous is not None:
                    replaced.append(previous)
                elif len(self._legacy) == self.max_legacy_pending:
                    return Admission(False, "Catalog busy; retry this read")
                self._legacy[copied.context] = copied
            else:
                attribute = "_" + copied.category.value
                previous = getattr(self, attribute)
                if previous is not None:
                    replaced.append(previous)
                setattr(self, attribute, copied)
            self._ids.add(copied.request_id)
            self._last_request_id = copied.request_id
            if retain:
                self._retained[copied.request_id] = retain
            for old in (*replaced, *invalidated):
                self._ids.remove(old.request_id)
                if old.request_id in self._retained:
                    self._replied_ids.add(old.request_id)
            self._condition.notify()
        for old in replaced:
            self.completed.emit(self._reply(old, "superseded", "Newer catalog request replaced it"))
        for old in invalidated:
            self.completed.emit(self._reply(old, "cancelled", "Catalog change invalidated queued read"))
        return Admission(True)

    def cancel_pending(self, request_id: int) -> bool:
        self._require_owner_thread()
        removed = None
        with self._condition:
            slots = ["_pending_write", "_apply", "_rank", "_detail", "_taxonomy", "_source"]
            for slot in slots:
                request = getattr(self, slot)
                if request is not None and request.request_id == request_id:
                    removed = request
                    setattr(self, slot, None)
                    break
            if removed is None:
                for pending in (self._pages, self._legacy):
                    for key, request in list(pending.items()):
                        if request.request_id == request_id:
                            removed = pending.pop(key)
                            break
                    if removed is not None:
                        break
            if removed is not None:
                self._ids.remove(request_id)
                if request_id in self._retained or removed.category == RequestClass.MUTATION:
                    self._replied_ids.add(request_id)
            elif (self._active is not None and self._active.request_id == request_id
                  and not self._active_write and self._active_cancel is not None):
                self._active_cancel.set()
                return True
            else:
                return False
        self.completed.emit(self._reply(removed, "cancelled", "Catalog request canceled before dispatch"))
        return True

    def acknowledge_result(self, request_id: int) -> Acknowledgement:
        """Return retained resources to the GUI after handling the result.

        The caller now owns explicit cleanup (for example TemporaryDirectory or
        a captured file handle) before it lets its window finish closing.
        """
        self._require_owner_thread()
        with self._condition:
            if request_id not in self._replied_ids:
                return Acknowledgement(False)
            self._replied_ids.remove(request_id)
            retained = self._retained.pop(request_id, ())
            if self._write_waiting_ack == request_id:
                self._write_waiting_ack = None
        return Acknowledgement(True, retained)

    def acknowledge_write(self, request_id: int) -> Acknowledgement:
        """Compatibility name for mutation completion acknowledgement."""
        return self.acknowledge_result(request_id)

    def request_close(self) -> None:
        self._require_owner_thread()
        cancelled: list[CatalogRequest] = []
        with self._condition:
            if self._stopping:
                return
            self._stopping = True
            for slot in ("_pending_write", "_apply", "_rank", "_detail", "_taxonomy", "_source"):
                request = getattr(self, slot)
                if request is not None:
                    cancelled.append(request)
                    setattr(self, slot, None)
            cancelled.extend(self._pages.values())
            cancelled.extend(self._legacy.values())
            self._pages.clear()
            self._legacy.clear()
            for request in cancelled:
                self._ids.remove(request.request_id)
                if request.request_id in self._retained or request.category == RequestClass.MUTATION:
                    self._replied_ids.add(request.request_id)
            if self._active_cancel is not None:
                self._active_cancel.set()
            self._condition.notify_all()
        for request in cancelled:
            self.completed.emit(self._reply(request, "cancelled", "Catalog gateway is closing"))

    def _next(self) -> CatalogRequest | None:
        with self._condition:
            while True:
                if self._pending_write is not None:
                    request = self._pending_write
                    self._pending_write = None
                    break
                if self._stopping:
                    return None
                request = None
                for slot in ("_apply", "_rank", "_detail", "_taxonomy", "_source"):
                    if slot == "_apply" and self._apply is not None:
                        request, self._apply = self._apply, None
                        break
                    if slot == "_rank" and self._pages:
                        _, request = self._pages.popitem(last=False)
                        break
                    value = getattr(self, slot)
                    if value is not None:
                        request = value
                        setattr(self, slot, None)
                        break
                if request is None and self._legacy:
                    _, request = self._legacy.popitem(last=False)
                if request is not None:
                    break
                self._condition.wait()
            self._active = request
            self._active_write = request.category == RequestClass.MUTATION
            self._active_cancel = None if self._active_write else threading.Event()
            return request

    def _read(self, db: sqlite3.Connection, request: CatalogRequest) -> CatalogReply:
        cancel = self._active_cancel
        assert cancel is not None
        deadline = time.monotonic() + request.deadline_seconds
        file_id = self._require_original_file()
        context = None
        try:
            def progress() -> int:
                return int(cancel.is_set() or time.monotonic() >= deadline)

            db.set_progress_handler(progress, 1_000)
            db.execute("BEGIN")
            db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
            version = db.execute("PRAGMA data_version").fetchone()[0]
            context = ReadContext(version, file_id, cancel, deadline)
            context.check()
            value = self._operations[request.operation].handler(db, context, *request.args,
                                                                 **dict(request.kwargs))
            if not db.in_transaction:
                raise RuntimeError("Catalog read handler ended its snapshot transaction")
            context.check()
            self._require_original_file()
            db.rollback()
            return CatalogReply(request.request_id, request.category, request.generation,
                                "ok", value=_copied_data(value, budget=[0, 0], max_nodes=16_384),
                                data_version=version,
                                file_identity=file_id, worker_thread_id=threading.get_ident())
        except sqlite3.OperationalError as exc:
            if cancel.is_set():
                raise RequestCancelled("Catalog read canceled") from exc
            if time.monotonic() >= deadline:
                raise ReadDeadlineExceeded("Catalog read deadline exceeded") from exc
            raise
        finally:
            if db.in_transaction:
                db.rollback()
            db.set_progress_handler(None, 0)

    def _legacy_read(self, request: CatalogRequest) -> CatalogReply:
        """Run unchanged service reads without prolonging their SQLite locks.

        The service may open its own connection using this path. There is no
        extra gateway BEGIN, snapshot token, output cap or duration promise.
        """
        cancel = self._active_cancel
        assert cancel is not None
        self._require_original_file()
        context = LegacyContext(cancel)
        context.check()
        value = self._operations[request.operation].handler(self.database, context,
                                                             *request.args,
                                                             **dict(request.kwargs))
        context.check()
        return CatalogReply(request.request_id, request.category, request.generation,
                            "ok", value=_copied_data(value, bounded=False),
                            worker_thread_id=threading.get_ident())

    def _write(self, request: CatalogRequest) -> CatalogReply:
        self._require_original_file()
        value = self._operations[request.operation].handler(self.database, None,
                                                             *request.args,
                                                             **dict(request.kwargs))
        try:
            copied = _copied_data(value, budget=[0, 0])
        except (TypeError, ValueError) as exc:
            # The backend call returned and may have committed. Never turn a
            # transfer refusal into a claim that the catalog edit failed.
            return CatalogReply(request.request_id, request.category, request.generation,
                                "completed_no_payload", message=f"Operation returned; result transfer refused: {exc}. Reload catalog state.",
                                worker_thread_id=threading.get_ident())
        return CatalogReply(request.request_id, request.category, request.generation,
                            "ok", value=copied,
                            worker_thread_id=threading.get_ident())

    def _path_identity(self) -> tuple[int, int]:
        stat = os.stat(self.database)
        return stat.st_dev, stat.st_ino

    def _require_original_file(self) -> tuple[int, int]:
        try:
            identity = self._path_identity()
        except OSError as exc:
            raise CatalogUnavailable("Catalog path unavailable; reopen library before another action") from exc
        if identity != self._reader_file_identity:
            raise CatalogReplaced("Catalog file changed since reader opened; reopen library before another action")
        return identity

    def run(self) -> None:
        db = None
        try:
            opened_identity = self._path_identity()
            uri = self.database.as_uri() + "?mode=ro"
            db = sqlite3.connect(uri, uri=True)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=50")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ValueError(f"Unsupported catalog schema {version}")
            if self._path_identity() != opened_identity:
                raise ValueError("Catalog file changed while opening reader; start a fresh gateway")
            self._reader_file_identity = opened_identity
            self.ready.emit()
            while True:
                request = self._next()
                if request is None:
                    break
                try:
                    if request.category == RequestClass.MUTATION:
                        reply = self._write(request)
                    elif request.category == RequestClass.LEGACY:
                        reply = self._legacy_read(request)
                    else:
                        reply = self._read(db, request)
                except RequestCancelled as exc:
                    if request.category == RequestClass.MUTATION:
                        reply = self._reply(request, "outcome_unknown",
                                            f"{type(exc).__name__}: {exc}; mutation outcome unknown; reload catalog state before another action")
                    else:
                        reply = self._reply(request, "cancelled", str(exc))
                except ReadDeadlineExceeded as exc:
                    if request.category == RequestClass.MUTATION:
                        reply = self._reply(request, "outcome_unknown",
                                            f"{type(exc).__name__}: {exc}; mutation outcome unknown; reload catalog state before another action")
                    else:
                        reply = self._reply(request, "deadline", str(exc))
                except ViewChanged as exc:
                    reply = self._reply(request, "view_changed", str(exc))
                except StaleTarget as exc:
                    reply = self._reply(request, "stale_target", str(exc))
                except (CatalogReplaced, CatalogUnavailable) as exc:
                    reply = self._reply(
                        request, "catalog_replaced" if isinstance(exc, CatalogReplaced)
                        else "catalog_unavailable", str(exc))
                except Exception as exc:
                    # An opaque service mutation may commit before raising. Its
                    # exception cannot establish rollback or authorize retry.
                    status = ("outcome_unknown" if request.category == RequestClass.MUTATION
                              else "error")
                    message = f"{type(exc).__name__}: {exc}"
                    if status == "outcome_unknown":
                        message += "; mutation outcome unknown; reload catalog state before another action"
                    reply = self._reply(request, status, message)
                with self._condition:
                    self._ids.discard(request.request_id)
                    self._active = None
                    self._active_cancel = None
                    self._active_write = False
                    if request.category == RequestClass.MUTATION:
                        self._write_waiting_ack = request.request_id
                    if request.category == RequestClass.MUTATION or request.request_id in self._retained:
                        self._replied_ids.add(request.request_id)
                self.completed.emit(reply)
        except Exception as exc:
            message = f"Catalog gateway startup failed: {type(exc).__name__}: {exc}"
            stranded: list[CatalogRequest] = []
            active_mutation_id = None
            with self._condition:
                if self._active is not None:
                    stranded.append(self._active)
                    if self._active_write:
                        active_mutation_id = self._active.request_id
                        self._write_waiting_ack = active_mutation_id
                    self._active = None
                for slot in ("_pending_write", "_apply", "_rank", "_detail", "_taxonomy", "_source"):
                    request = getattr(self, slot)
                    if request is not None:
                        stranded.append(request)
                        setattr(self, slot, None)
                stranded.extend(self._pages.values())
                stranded.extend(self._legacy.values())
                self._pages.clear()
                self._legacy.clear()
                self._ids.clear()
                self._stopping = True
                for request in stranded:
                    if request.category == RequestClass.MUTATION or request.request_id in self._retained:
                        self._replied_ids.add(request.request_id)
            for request in stranded:
                status = ("outcome_unknown" if request.request_id == active_mutation_id
                          else "error")
                detail = (message + "; mutation outcome unknown; reload catalog state before another action"
                          if status == "outcome_unknown" else message)
                self.completed.emit(self._reply(request, status, detail))
            self.failed.emit(message)
        finally:
            try:
                if db is not None:
                    db.close()
            finally:
                with self._condition:
                    self._finished = True
                    self._condition.notify_all()
