"""Explicit captured-asset handoffs. No source or catalog rows are written.

Blocking filesystem/launch calls live in one spawned helper. A READY probe needs
a separate, timely permit; probe-only smokes never grant that permit. External
applications own their behavior after handoff and are not catalog transactions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time
import uuid

from .catalog import connect


class OpenAction(Enum):
    FILE = "file"
    FOLDER = "folder"


class DispatchRejected(OSError):
    """The adapter confirmed it did not accept the handoff."""


@dataclass(frozen=True)
class OpenTarget:
    asset_id: str
    revision: int
    path: str
    sha256: str
    byte_size: int
    source_id: str | None = None

    def __post_init__(self):
        if type(self.asset_id) is not str or not self.asset_id:
            raise ValueError("Asset ID must be a nonempty string")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("Revision must be a nonnegative integer")
        _absolute_path(self.path, "Asset path")
        if type(self.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("Catalog fingerprint must be a SHA-256 digest")
        if type(self.byte_size) is not int or self.byte_size < 0:
            raise ValueError("Catalog byte size must be a nonnegative integer")
        if self.source_id is not None and (type(self.source_id) is not str or not self.source_id):
            raise ValueError("Source ID must be absent or a nonempty string")


def _absolute_path(value, label):
    # Lexical only: no resolve/stat/network access on the GUI thread.
    if type(value) is not str or not value or "\0" in value or not Path(value).is_absolute():
        raise ValueError(f"{label} must be an absolute filesystem path")


def capture_target(asset: dict) -> OpenTarget:
    return OpenTarget(asset["asset_id"], asset["revision"], asset["current_path"],
                      asset["sha256"], asset["byte_size"], asset.get("source_id"))


def observed_unavailable(asset: dict) -> str | None:
    """Last scan facts only; paused monitoring is ordinary last-observed availability."""
    if asset.get("source_id") is None:
        return None
    health = asset.get("source_health")
    if health not in ("paused", "watching"):
        return f"Source last observed {health or 'unavailable'}. Complete an explicit scan before external opening."
    if asset.get("entry_disposition") != "indexed":
        return f"Asset last observed {asset.get('entry_disposition') or 'without matching source entry'}. Run an explicit scan before external opening."
    return None


@dataclass(frozen=True)
class CommandSpec:
    executable: str | None = None
    fixed_args: tuple[str, ...] = ()

    def __post_init__(self):
        if self.executable is not None:
            _absolute_path(self.executable, "Trusted executable")
            if Path(self.executable).suffix.casefold() in (".bat", ".cmd"):
                raise ValueError("Windows shell batch wrappers are not supported")
        if type(self.fixed_args) is not tuple or len(self.fixed_args) > 32:
            raise ValueError("Fixed arguments must be a tuple of at most 32 values")
        if any(type(value) is not str or len(value) > 4096 or any(char in value for char in "\0\r\n")
               for value in self.fixed_args):
            raise ValueError("Each fixed argument must be a literal string of at most 4096 characters without NUL/newlines")
        if self.executable is None and self.fixed_args:
            raise ValueError("OS associations do not accept configured arguments")


@dataclass(frozen=True)
class ExternalSettings:
    file: CommandSpec = CommandSpec()
    folder: CommandSpec = CommandSpec()

    def __post_init__(self):
        if type(self.file) is not CommandSpec or type(self.folder) is not CommandSpec:
            raise ValueError("External settings require typed file and folder commands")


@dataclass(frozen=True)
class ActionLimits:
    timeout_seconds: float = 5.0
    max_source_bytes: int = 512 * 1024 * 1024

    def __post_init__(self):
        if (type(self.timeout_seconds) not in (float, int) or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= 30):
            raise ValueError("External operation timeout must be finite and between 0 and 30 seconds")
        if type(self.max_source_bytes) is not int or not 0 < self.max_source_bytes <= 512 * 1024 * 1024:
            raise ValueError("External source byte bound must be between 1 and 512 MiB")


@dataclass(frozen=True)
class ActionResult:
    status: str
    message: str
    target: OpenTarget
    action: OpenAction
    permit_sent: bool = False
    dispatched: bool = False
    cleanup_complete: bool = True
    process_id: int | None = None


def _check_deadline(deadline, cancelled):
    if cancelled.is_set():
        raise InterruptedError("External request cancelled before dispatch")
    if time.monotonic() >= deadline:
        raise TimeoutError("External check exceeded its operation deadline; no handoff requested")


def _catalog_target(db, target):
    row = db.execute("SELECT asset_id,revision,current_path,sha256,byte_size,source_id "
                     "FROM assets WHERE asset_id=?", (target.asset_id,)).fetchone()
    if row is None or capture_target(dict(row)) != target:
        raise ValueError("Captured asset changed. Reload the same asset before requesting an external handoff.")
    entries = db.execute("SELECT current_path,source_id,disposition FROM source_entries WHERE asset_id=? LIMIT 2",
                         (target.asset_id,)).fetchall()
    if target.source_id is None:
        if entries:
            raise ValueError("Standalone asset has inconsistent source linkage; explicit reconciliation required")
        return
    health = db.execute("SELECT health FROM sources WHERE source_id=?", (target.source_id,)).fetchone()
    if (len(entries) != 1 or entries[0]["current_path"] != target.path or
            entries[0]["source_id"] != target.source_id):
        raise ValueError("Source-backed asset has no exact matching entry; run an explicit scan")
    unavailable = observed_unavailable({"source_id": target.source_id,
        "source_health": health[0] if health else None, "entry_disposition": entries[0]["disposition"]})
    if unavailable:
        raise ValueError(unavailable)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _source_probe(target, action, limits, deadline, cancelled):
    _check_deadline(deadline, cancelled)
    path = Path(target.path)
    if path.resolve(strict=True) != path or path.is_symlink():
        raise ValueError("Captured source path now contains a symlink; explicit reconciliation required")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Captured source is not a regular file")
    if info.st_size != target.byte_size:
        raise ValueError("Source size differs from captured fingerprint. Run an explicit scan.")
    if info.st_size > limits.max_source_bytes:
        raise ValueError("Source exceeds the external-open verification byte bound (512 MiB maximum)")
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if _identity(before) != _identity(info) or not stat.S_ISREG(before.st_mode):
            raise ValueError("Source changed while opening it")
        while block := stream.read(1024 * 1024):
            _check_deadline(deadline, cancelled)
            digest.update(block)
        if digest.hexdigest() != target.sha256:
            raise ValueError("Source content differs from captured fingerprint. Run an explicit scan.")
        if _identity(os.fstat(stream.fileno())) != _identity(before) or _identity(path.stat()) != _identity(before):
            raise ValueError("Source changed during verification")
        if path.resolve(strict=True) != path or path.is_symlink():
            raise ValueError("Source path became a symlink during verification")
    destination = target.path if action is OpenAction.FILE else str(path.parent)
    folder_identity = None
    if action is OpenAction.FOLDER:
        folder = path.parent.stat()
        if not stat.S_ISDIR(folder.st_mode) or not os.access(path.parent, os.R_OK | os.X_OK):
            raise PermissionError("Containing folder is unavailable or cannot be traversed")
        folder_identity = (folder.st_dev, folder.st_ino)
    _check_deadline(deadline, cancelled)
    return destination, _identity(before), folder_identity


def _command_available(command):
    if command.executable is None:
        return
    info = Path(command.executable).stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(command.executable, os.X_OK):
        raise PermissionError("Trusted executable is missing or not executable")


def _default_association(destination):
    # Runs only in the isolated helper, never the gallery thread. No URL parsing
    # or global handler registration: punctuation in a filename remains local.
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices, QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    url = QUrl.fromLocalFile(destination)
    if not url.isLocalFile() or url.scheme() != "file":
        raise ValueError("External association requires a local-file URL")
    requested = bool(QDesktopServices.openUrl(url))
    app.processEvents()
    if not requested:
        raise DispatchRejected("Operating system declined the local-file handoff")
    return None


def _dispatch(command, destination):
    if command.executable is None:
        return _default_association(destination)
    try:
        process = subprocess.Popen([command.executable, *command.fixed_args, destination],
            shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, start_new_session=True)
    except OSError as exc:
        raise DispatchRejected(f"Trusted executable did not accept the handoff: {exc}") from exc
    return process.pid


def _external_helper(database, target, action, command, limits, deadline, cancelled, channel):
    dispatched = False
    try:
        _check_deadline(deadline, cancelled)
        with connect(database) as db:
            _catalog_target(db, target)
        destination, source_identity, folder_identity = _source_probe(target, action, limits, deadline, cancelled)
        _command_available(command)
        _check_deadline(deadline, cancelled)
        channel.send({"kind": "ready"})
        while not channel.poll(.02):
            _check_deadline(deadline, cancelled)
        permit = channel.recv()
        if permit != {"permit": True}:
            channel.send({"kind": "result", "status": "probe_ready", "message": "Captured source verified; dispatch permit withheld.", "dispatched": False})
            return
        _check_deadline(deadline, cancelled)
        # Slow content read has finished. Reserve the catalog writer briefly for
        # the final identity/availability check and handoff; no rows are written.
        with connect(database) as db:
            db.execute("BEGIN IMMEDIATE")
            _catalog_target(db, target)
            path = Path(target.path)
            if path.resolve(strict=True) != path or path.is_symlink():
                raise ValueError("Source path became a symlink after verification")
            if _identity(Path(target.path).stat()) != source_identity:
                raise ValueError("Source changed after verification; handoff refused")
            if folder_identity is not None:
                info = Path(destination).stat()
                if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != folder_identity:
                    raise ValueError("Containing folder changed after verification")
            _command_available(command)
            _check_deadline(deadline, cancelled)
            dispatched = True  # Once OS dispatch starts, lost acknowledgement is uncertain.
            process_id = _dispatch(command, destination)
        channel.send({"kind": "result", "status": "requested", "message": "External handoff requested. Opening, saving and reconciliation are not confirmed.",
                      "dispatched": True, "process_id": process_id})
    except (OSError, ValueError, sqlite3.Error, RuntimeError, EOFError) as exc:
        status = "refused" if isinstance(exc, DispatchRejected) else "uncertain" if dispatched else ("timeout" if isinstance(exc, TimeoutError) else
                 "cancelled" if isinstance(exc, InterruptedError) else "refused")
        try:
            channel.send({"kind": "result", "status": status, "message": str(exc), "dispatched": dispatched and not isinstance(exc, DispatchRejected)})
        except (OSError, EOFError, BrokenPipeError):
            pass
    finally:
        channel.close()


def execute_external_action(database: Path, target: OpenTarget, action: OpenAction,
                            command: CommandSpec = CommandSpec(), limits: ActionLimits = ActionLimits(),
                            *, cancel_event=None, probe_only=False, process_factory=None) -> ActionResult:
    """Synchronous supervisor for an off-GUI worker; at most one helper per call.

    The Qt controller admits only one call at a time. A cleanup failure retains
    its process reference on the factory/controller and must block replacements.
    """
    if type(target) is not OpenTarget or type(action) is not OpenAction or type(command) is not CommandSpec or type(limits) is not ActionLimits:
        raise ValueError("External action requires typed target, action, command and limits")
    if type(probe_only) is not bool:
        raise ValueError("probe_only must be boolean")
    context = multiprocessing.get_context("spawn")
    stopped = context.Event()
    parent, child = context.Pipe(duplex=True)
    deadline = time.monotonic() + limits.timeout_seconds
    process = (process_factory or context.Process)(target=_external_helper,
        args=(Path(database), target, action, command, limits, deadline, stopped, child))
    permit_sent = False
    payload = None
    ready_received = False
    try:
        if cancel_event is not None and cancel_event.is_set():
            return ActionResult("cancelled", "External request cancelled before probe startup.", target, action)
        process.start()
        child.close()
        while payload is None:
            cancelled = cancel_event is not None and cancel_event.is_set()
            expired = time.monotonic() >= deadline
            if cancelled or expired:
                stopped.set()
                status = "uncertain" if permit_sent else "cancelled" if cancelled else "timeout"
                message = ("Handoff outcome uncertain after dispatch permit; do not automatically retry." if permit_sent else
                           "Request cancelled; no dispatch permit issued." if cancelled else
                           "Verification timed out; no dispatch permit issued. Explicitly retry after checking availability.")
                payload = {"status": status, "message": message, "dispatched": False}
                break
            if parent.poll(.02):
                response = parent.recv()
                if response.get("kind") == "ready":
                    if ready_received:
                        raise ValueError("External helper requested more than one dispatch permit")
                    ready_received = True
                    if cancel_event is not None and cancel_event.is_set() or time.monotonic() >= deadline:
                        continue
                    parent.send({"permit": not probe_only})
                    permit_sent = not probe_only
                elif response.get("kind") == "result":
                    payload = response
                else:
                    raise ValueError("External helper returned an invalid message")
            elif not process.is_alive():
                payload = {"status": "uncertain" if permit_sent else "refused", "message": "External helper exited without a handoff acknowledgement.", "dispatched": False}
        return ActionResult(payload["status"], payload["message"], target, action, permit_sent,
                            payload.get("dispatched", False), True, payload.get("process_id"))
    except (OSError, EOFError, RuntimeError, ValueError) as exc:
        return ActionResult("uncertain" if permit_sent else "refused", str(exc), target, action, permit_sent)
    finally:
        stopped.set()
        if process.pid is not None:
            process.join(.1)
            if process.is_alive():
                process.terminate()
                process.join(.5)
            if process.is_alive():
                process.kill()
                process.join(.5)
            if process.is_alive():
                # A factory/controller must retain this reference. Raising keeps
                # the caller from reporting a clean result or starting another.
                error = RuntimeError("External helper cleanup incomplete; further dispatch disabled")
                error.process = process
                parent.close()
                child.close()
                raise error
            process.close()
        parent.close()
        child.close()


def _settings_path(database, settings_path):
    path = Path(settings_path).expanduser().resolve(strict=False)
    if path == Path(database).resolve(strict=False):
        raise ValueError("External settings must be separate from the catalog")
    with connect(database) as db:
        roots = [Path(row[0]).resolve(strict=False) for row in db.execute("SELECT root_path FROM sources")]
    if any(path == root or root in path.parents for root in roots):
        raise ValueError("External settings must be outside artwork sources")
    return path


def load_external_settings(database: Path, settings_path: Path) -> ExternalSettings:
    path = _settings_path(database, settings_path)
    try:
        if path.stat().st_size > 512 * 1024:
            raise ValueError("External settings file exceeds its size bound")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ExternalSettings()
    if type(value) is not dict or set(value) != {"schema", "file", "folder"} or value["schema"] != "defiantmaple.external-settings.v1":
        raise ValueError("Unsupported external settings document")
    commands = []
    for name in ("file", "folder"):
        command = value[name]
        if type(command) is not dict or set(command) != {"executable", "fixed_args"} or type(command["fixed_args"]) is not list:
            raise ValueError("Invalid external command settings")
        commands.append(CommandSpec(command["executable"], tuple(command["fixed_args"])))
    return ExternalSettings(*commands)


def save_external_settings(database: Path, settings_path: Path, settings: ExternalSettings,
                           *, deadline=None, cancelled=None) -> None:
    if type(settings) is not ExternalSettings:
        raise ValueError("Settings must be ExternalSettings")
    path = _settings_path(database, settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump({"schema": "defiantmaple.external-settings.v1", **asdict(settings)}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if deadline is not None:
            _check_deadline(deadline, cancelled)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _settings_helper(database, settings_path, settings, deadline, cancelled, channel):
    try:
        _check_deadline(deadline, cancelled)
        if settings is None:
            result = load_external_settings(database, settings_path)
        else:
            save_external_settings(database, settings_path, settings, deadline=deadline, cancelled=cancelled)
            result = settings
        _check_deadline(deadline, cancelled)
        channel.send((result, ""))
    except (OSError, ValueError, sqlite3.Error) as exc:
        channel.send((None, str(exc)))
    finally:
        channel.close()


def execute_settings_task(database: Path, settings_path: Path, settings=None, *, timeout_seconds=5.0, cancel_event=None):
    """Bounded settings I/O for the UI, including source-root location checks."""
    if settings is not None and type(settings) is not ExternalSettings:
        raise ValueError("Settings must be typed")
    limits = ActionLimits(timeout_seconds)
    context = multiprocessing.get_context("spawn")
    cancelled = context.Event()
    parent, child = context.Pipe(duplex=False)
    deadline = time.monotonic() + limits.timeout_seconds
    process = context.Process(target=_settings_helper,
        args=(Path(database), Path(settings_path), settings, deadline, cancelled, child))
    try:
        process.start()
        child.close()
        while not parent.poll(.02):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Settings request cancelled")
            if time.monotonic() >= deadline:
                raise TimeoutError("Local settings I/O timed out; inspect local state before retrying")
            if not process.is_alive():
                raise OSError("Local settings helper exited unexpectedly")
        result, error = parent.recv()
        if error:
            raise ValueError(error)
        return result
    finally:
        cancelled.set()
        if process.pid is not None:
            process.join(.1)
            if process.is_alive():
                process.terminate()
                process.join(.5)
            if process.is_alive():
                process.kill()
                process.join(.5)
            if process.is_alive():
                error = RuntimeError("Settings helper cleanup incomplete; further operations disabled")
                error.process = process
                parent.close()
                child.close()
                raise error
            process.close()
        parent.close()
        child.close()
