"""Root-only visible native checks with fictional /tmp originals and a read-only handler.

No installed association is exercised or changed. Raw path-bearing receipts are
private. PNGs capture only this app's safe generated UI, without image editing.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import closing
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

from PIL import Image
from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QEventLoop, QItemSelectionModel, Qt, QTimer, qVersion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, external_actions as api
from defiantmaple.private_eval import assert_outside_git
from prototypes.qt.app import GalleryWindow
from prototypes.qt.identity import APP_ID, app_icon

SOURCE_FILES = (
    "defiantmaple/external_actions.py", "prototypes/qt/external_actions.py",
    "prototypes/qt/app.py", "prototypes/qt/package.py", "prototypes/qt/identity.py",
    "tests/test_external_actions.py", "prototypes/qt/tests/test_external_actions_ui.py",
    "docs/external-actions-design.md", "docs/external-actions-guide.md",
    "prototypes/qt/external_actions_native_acceptance.py",
)
_RECEIPT = None
_RECEIPT_PATH = None
_APP = None
_WINDOW = None


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _stage(name, **values):
    _RECEIPT["stages"].append({"stage": name, **values})
    _write(_RECEIPT_PATH, _RECEIPT)


def _wait(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        _APP.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        time.sleep(.01)
    _APP.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    if not predicate():
        raise AssertionError("Bounded native wait failed")


def _focus(top):
    handle = top.windowHandle()
    focused = _APP.focusWidget()
    return {"visible": top.isVisible(), "active": top.isActiveWindow(),
            "exposed": bool(handle and handle.isExposed()),
            "focus_inside": bool(focused and (focused is top or top.isAncestorOf(focused))),
            "focused_class": type(focused).__name__ if focused else None,
            "focused_name": focused.objectName() if focused else None,
            "focused_accessible_name": focused.accessibleName() if focused else None}


def _activate(top):
    top.raise_()
    top.activateWindow()
    handle = top.windowHandle()
    if handle:
        handle.requestActivate()
    _wait(lambda: all(_focus(top)[key] for key in ("visible", "active", "exposed", "focus_inside")), 4)


def _reachable(top, widget):
    scroll = getattr(top, "detail_scroll", None)
    if scroll is None or not scroll.widget().isAncestorOf(widget):
        return True
    viewport = scroll.viewport()
    rectangle = widget.rect().translated(widget.mapTo(viewport, widget.rect().topLeft()))
    return viewport.rect().contains(rectangle)


def _reveal(top, widget):
    scroll = getattr(top, "detail_scroll", None)
    if scroll is None or not scroll.widget().isAncestorOf(widget):
        return
    bar = scroll.verticalScrollBar()
    for _ in range(80):
        if _reachable(top, widget):
            return
        y = widget.mapTo(scroll.viewport(), widget.rect().topLeft()).y()
        _key(top, bar, Qt.Key.Key_Up if y < 0 else Qt.Key.Key_Down)
    raise AssertionError("Bounded keyboard scrolling did not expose the control")


def _key(top, widget, key, modifier=Qt.KeyboardModifier.NoModifier):
    _reveal(top, widget)
    widget.setFocus()
    def ready():
        report = _focus(top)
        focus = _APP.focusWidget()
        return (all(report[key] for key in ("visible", "active", "exposed", "focus_inside")) and
                widget.isVisible() and widget.isEnabled() and _reachable(top, widget) and
                focus is not None and (focus is widget or widget.isAncestorOf(focus)))
    _wait(ready, 2)
    _RECEIPT["keyboard_actions"].append({"window": top.windowTitle(),
        "target": widget.objectName() or widget.accessibleName() or type(widget).__name__,
        "key": key.name, "modifiers": modifier.name, "focus": _focus(top)})
    QTest.keyClick(_APP.focusWidget(), key, modifier)
    _APP.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)


def _text(top, widget, text):
    if not text.isascii() or "\n" in text:
        raise ValueError("Native typed fixture values must be one ASCII line")
    _key(top, widget, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(_APP.focusWidget(), text)
    _RECEIPT["keyboard_actions"].append({"target": widget.accessibleName(), "typed_fixture_characters": len(text), "focus": _focus(top)})
    _APP.processEvents()


def _tab_to(top, target, maximum=12):
    for _ in range(maximum):
        if _APP.focusWidget() is target:
            return
        focus = _APP.focusWidget()
        if focus is None:
            raise AssertionError("Keyboard Tab traversal lost focus")
        _key(top, focus, Qt.Key.Key_Tab)
    if _APP.focusWidget() is not target:
        raise AssertionError("Bounded Tab traversal did not reach the requested control")


def _snapshot(database):
    with closing(sqlite3.connect(database)) as db:
        rows = tuple(db.iterdump())
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def _manifest(files):
    return {path.name: {"sha256": _sha(path), "byte_size": path.stat().st_size,
                        "mtime_ns": path.stat().st_mtime_ns} for path in files}


def _logs(path):
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _select(window, identifier):
    row = window.model.row_for_asset(identifier)
    if row is None:
        raise AssertionError("Fictional stable ID is no longer visible")
    window.gallery.selectionModel().setCurrentIndex(window.model.index(row),
        QItemSelectionModel.SelectionFlag.ClearAndSelect)
    _APP.processEvents()


def _finished(window):
    _wait(lambda: window.external_worker is None or window.external_cleanup_failed)
    if window.external_cleanup_failed:
        raise AssertionError("External helper ownership remains unreaped")


def _close(window):
    if window.isVisible():
        accepted = bool(window.close())
        _wait(lambda: not window.isVisible())
    else:
        accepted = None
    try:
        window.model._db.execute("SELECT 1")
    except sqlite3.ProgrammingError as exc:
        closed = "closed" in str(exc).lower()
    else:
        closed = False
    if not closed or window.external_worker is not None or window.external_cleanup_failed:
        raise AssertionError("Native gallery/model/helper cleanup incomplete")
    return {"initial_close_accepted": accepted, "window_hidden": True,
            "model_connection_closed": True, "helper_reaped": True}


def _seed(root):
    art = root / "fictional-originals"
    art.mkdir()
    files, identifiers = [], []
    database = root / "fictional-library.sqlite3"
    catalog.initialize(database)
    for number, name in enumerate(("alpha $(`literal`) ; ' café %.png", "beta.png")):
        path = art / name
        image = Image.new("RGB", (96, 72), (70 + number * 80, 120, 160))
        image.save(path, "PNG")
        image.close()
        path.chmod(0o444)
        files.append(path)
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, "defiantmaple-fictional-external-" + str(number)))
        identifiers.append(identifier)
        info = path.stat()
        with catalog.connect(database) as db:
            if number == 0:
                db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health,initial_scan_completed) "
                           "VALUES('fictional-source','Fictional paused originals',?,'inbox','paused',1)", (str(art),))
            db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,source_id,discovered_at) "
                       "VALUES(?,?,'image/png',?,?,'fictional-source',?)", (identifier, str(path), _sha(path), info.st_size,
                         f"2026-01-01T00:00:0{number}.000Z"))
            db.execute("INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
                       "VALUES(?,'fictional-source',?,?,?,?,?,?,1,'indexed',?)", (str(path), info.st_size,
                        info.st_mtime_ns, str(info.st_dev), str(info.st_ino), info.st_mtime_ns, info.st_mtime_ns, identifier))
    stub = root / "fictional_read_only_handler.py"
    stub.write_text("import json,os,sys\nwith open(sys.argv[1],'a',encoding='utf-8') as out:\n out.write(json.dumps(sys.argv[2:])+'\\n'); out.flush(); os.fsync(out.fileno())\n", encoding="utf-8")
    stub.chmod(0o444)
    return database, files, identifiers, stub


def _trial_refusals(database, root, command):
    import shutil
    trial = root / "fictional-refusal-trial.sqlite3"
    shutil.copy2(database, trial)
    with catalog.connect(trial) as db:
        asset = dict(db.execute("SELECT * FROM assets ORDER BY discovered_at LIMIT 1").fetchone())
    target = api.capture_target(asset)
    outcomes = []
    for health in ("scanning", "offline", "permission_denied", "error"):
        with catalog.connect(trial) as db:
            db.execute("UPDATE sources SET health=?", (health,))
        before = _snapshot(trial)
        result = api.execute_external_action(trial, target, api.OpenAction.FILE, command)
        assert result.status == "refused" and not result.dispatched and not result.permit_sent
        assert _snapshot(trial) == before
        outcomes.append({"last_observed_health": health, "status": result.status, "permit_sent": result.permit_sent})
    with catalog.connect(trial) as db:
        db.execute("UPDATE sources SET health='paused'")
        db.execute("UPDATE assets SET rating=5 WHERE asset_id=?", (target.asset_id,))
        db.execute("UPDATE assets SET rating=NULL WHERE asset_id=?", (target.asset_id,))
    before = _snapshot(trial)
    stale = api.execute_external_action(trial, target, api.OpenAction.FILE, command)
    assert stale.status == "refused" and not stale.permit_sent and _snapshot(trial) == before
    with catalog.connect(trial) as db:
        fresh = api.capture_target(dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (target.asset_id,)).fetchone()))
    missing = api.execute_external_action(trial, fresh, api.OpenAction.FILE, api.CommandSpec(str(root / "missing-tool")))
    assert missing.status == "refused" and not missing.permit_sent and _snapshot(trial) == before
    limited = api.execute_external_action(trial, fresh, api.OpenAction.FILE, command, api.ActionLimits(.001))
    assert limited.status == "timeout" and not limited.permit_sent and _snapshot(trial) == before
    with catalog.connect(trial) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
    assert integrity == "ok" and not foreign_keys
    return {"source_states": outcomes, "catalog_aba_refused": True, "missing_tool_refused": True,
            "startup_deadline_no_permit": True, "catalog_integrity": integrity, "foreign_key_violations": [],
            "deliberate_changes": "Disposable trial source health and rating ABA only; no original writes."}


def _run(output, expected_sha):
    global _RECEIPT, _RECEIPT_PATH, _APP, _WINDOW
    repository = Path(__file__).resolve().parents[2]
    if _sha(Path(__file__)) != expected_sha:
        raise ValueError("Helper does not match its independently reviewed SHA")
    output = output.expanduser().resolve(strict=False)
    assert_outside_git(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Native evidence directory must be new or empty")
    if os.environ.get("QT_QPA_PLATFORM", "").lower() in ("offscreen", "minimal", "vnc"):
        raise ValueError("Native acceptance requires a real visible desktop platform")
    output.mkdir(parents=True, exist_ok=True)
    _RECEIPT_PATH = output / "external-actions-native-partial.json"
    _RECEIPT = {"schema": "defiantmaple.external-actions-native-acceptance.v1", "status": "running",
                "complete": False, "stages": [], "keyboard_actions": [], "captures": [],
                "scope": "Generated read-only handler only; default associations mocked elsewhere."}
    digests = {name: _sha(repository / name) for name in SOURCE_FILES}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    fixture = Path(tempfile.mkdtemp(prefix="defiantmaple-fictional-external-", dir="/tmp"))
    # Preserve the real Wayland runtime. Only local application data roots move.
    isolated_xdg = {f"XDG_{name}_HOME": str(fixture / "local-data" / name.lower()) for name in ("CONFIG", "DATA", "CACHE")}
    for variable, value in isolated_xdg.items():
        os.environ[variable] = value
    database, files, ids, stub = _seed(fixture)
    handler_log = fixture / "fictional-handler-argv.jsonl"
    # The handler needs only stdlib. Use a trusted system interpreter whose
    # visible path cannot disclose a private task environment/home directory.
    candidates = (Path("/usr/bin/python3"), Path("/usr/local/bin/python3"))
    handler_python = next((path.resolve(strict=True) for path in candidates
                           if path.is_file() and os.access(path, os.X_OK)), None)
    if handler_python is None or Path.home() in handler_python.parents:
        raise ValueError("No trusted system Python outside the home directory for the native stub")
    command = api.CommandSpec(str(handler_python), (str(stub), str(handler_log), "fixed $(`literal`) ; ' %"))
    baseline_source, baseline_catalog = _manifest(files), _snapshot(database)
    _stage("generated_fixture", source_file_digests=digests, checked_out_head=head,
           fixture_root=str(fixture), original_manifest=baseline_source, catalog_digest=baseline_catalog)
    trial = _trial_refusals(database, fixture, command)
    assert not _logs(handler_log)
    assert _manifest(files) == baseline_source and _snapshot(database) == baseline_catalog
    _stage("generated_api_refusals", results=trial, unexpected_dispatch_count=0)
    _APP = QApplication.instance() or QApplication([])
    _APP.setOrganizationName("DefiantMaple")
    _APP.setApplicationName("DefiantMaple")
    _APP.setApplicationDisplayName("DefiantMaple")
    _APP.setDesktopFileName(APP_ID)
    _APP.setWindowIcon(app_icon())
    if _APP.platformName().lower() in ("offscreen", "minimal", "vnc"):
        raise ValueError("Qt did not initialize a native display backend")
    settings_path = fixture / "local-data" / "external-tools.json"
    window = GalleryWindow(database, external_settings_path=settings_path,
                           cache_root=fixture / "cache", private_root=fixture / "private")
    _WINDOW = window
    window.show()
    _select(window, ids[0])
    window.gallery.setFocus()
    _activate(window)
    _key(window, window.external_settings_button, Qt.Key.Key_Space)
    _finished(window)
    _wait(lambda: window.external_settings_dialog is not None and window.external_settings_dialog.isVisible())
    dialog = window.external_settings_dialog
    dialog.fields[api.OpenAction.FILE][0].setFocus()
    _activate(dialog)
    for action in (api.OpenAction.FILE, api.OpenAction.FOLDER):
        association, executable, arguments = dialog.fields[action]
        assert association.isChecked()
        _key(dialog, association, Qt.Key.Key_Space)
        _text(dialog, executable, command.executable)
        _text(dialog, arguments, command.fixed_args[0])
        for value in command.fixed_args[1:]:
            _key(dialog, arguments, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
            _key(dialog, arguments, Qt.Key.Key_Return)
            QTest.keyClicks(_APP.focusWidget(), value)
    # Source path is fictional /tmp; no private wrapper paths appear in this app capture.
    if str(Path.home()) in dialog.fields[api.OpenAction.FILE][1].text():
        raise AssertionError("Trusted executable path would expose a private home path in the capture")
    assert dialog.grab().save(str(output / "fictional-external-settings.png"))
    _RECEIPT["captures"].append("fictional-external-settings.png")
    _tab_to(dialog, dialog.save_button)
    _key(dialog, dialog.save_button, Qt.Key.Key_Space)
    _finished(window)
    assert not dialog.isVisible() and window.external_settings == api.ExternalSettings(command, command)
    assert settings_path.exists()
    _stage("native_settings_keyboard", settings_persisted=True, command_argv_literal=True,
           model_catalog_unchanged=_snapshot(database) == baseline_catalog)
    window.gallery.setFocus()
    _activate(window)
    _key(window, window.open_external_button, Qt.Key.Key_Space)
    worker = window.external_worker
    assert worker and worker.target.asset_id == ids[0]
    # IconMode horizontal movement: change focus to beta while alpha is in flight.
    _key(window, window.gallery, Qt.Key.Key_Right)
    assert window._selected_asset()["asset_id"] == ids[1]
    assert not window.open_folder_button.isEnabled()
    _finished(window)
    _wait(lambda: len(_logs(handler_log)) == 1)
    assert _logs(handler_log)[0] == [command.fixed_args[-1], str(files[0])]
    assert worker.outcome.status == "requested" and worker.outcome.dispatched
    assert worker.outcome.target.asset_id == ids[0]
    assert ids[0] in window.external_feedback.text()
    assert _snapshot(database) == baseline_catalog and _manifest(files) == baseline_source
    _stage("native_file_captured_keyboard_drift", result=worker.outcome.__dict__ | {"target": worker.outcome.target.__dict__, "action": worker.outcome.action.value},
           handler_argv=_logs(handler_log)[0], original_catalog_preserved=True)
    _key(window, window.open_folder_button, Qt.Key.Key_Space)
    folder_worker = window.external_worker
    assert folder_worker.target.asset_id == ids[1]
    _finished(window)
    _wait(lambda: len(_logs(handler_log)) == 2)
    assert _logs(handler_log)[1] == [command.fixed_args[-1], str(files[1].parent)]
    assert folder_worker.outcome.status == "requested"
    _stage("native_containing_folder_keyboard", handler_argv=_logs(handler_log)[1], promises_highlight=False)
    # Demonstrate catalog-lock timeout with a ticking native GUI, no dispatch.
    blocker = sqlite3.connect(database)
    blocker.execute("BEGIN EXCLUSIVE")
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(20)
    try:
        _key(window, window.open_external_button, Qt.Key.Key_Space)
        timeout_worker = window.external_worker
        _key(window, window.gallery, Qt.Key.Key_Tab)
        _finished(window)
    finally:
        blocker.rollback()
        blocker.close()
    timer.stop()
    assert len(ticks) > 10
    assert timeout_worker.outcome.status == "timeout" and not timeout_worker.outcome.permit_sent
    assert len(_logs(handler_log)) == 2
    assert window._selected_asset()["asset_id"] == ids[1]
    _stage("native_catalog_lock_timeout", status=timeout_worker.outcome.status,
           no_permit=True, no_extra_handler_request=True, keyboard_focus_traversal_responsive=True, native_gui_timer_ticks=len(ticks))
    # Safe app-only target/result capture; catalog and visible targets are fictional /tmp.
    _reveal(window, window.external_feedback)
    # Existing curation controls remain reachable in the same scrollable pane.
    _key(window, window.curation_button, Qt.Key.Key_Tab)
    _key(window, window.bulk_curation_button, Qt.Key.Key_Tab)
    _reveal(window, window.external_feedback)
    _APP.processEvents()
    assert window.grab().save(str(output / "fictional-external-handoff.png"))
    _RECEIPT["captures"].append("fictional-external-handoff.png")
    try:
        os_release = platform.freedesktop_os_release()
    except (AttributeError, OSError):
        os_release = {}
    host = {"os_release": os_release, "screens": [{"name": screen.name(),
        "geometry_px": [screen.geometry().x(), screen.geometry().y(), screen.geometry().width(), screen.geometry().height()],
        "device_pixel_ratio": screen.devicePixelRatio()} for screen in _APP.screens()],
        "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "pyside6": PYSIDE_VERSION, "qt": qVersion(), "qt_platform_plugin": _APP.platformName(),
            "session_type": os.environ.get("XDG_SESSION_TYPE"), "application_id": APP_ID,
            "device_pixel_ratio": window.devicePixelRatio(), "visible_focus": _focus(window), "source_run": True}
    _stage("native_host_while_visible", host=host)
    first_cleanup = _close(window)
    _WINDOW = None
    # Reopen uses persisted local settings through the same explicit-load worker.
    window = GalleryWindow(database, external_settings_path=settings_path,
                           cache_root=fixture / "cache", private_root=fixture / "private")
    _WINDOW = window
    window.show()
    _select(window, ids[0])
    window.gallery.setFocus()
    _activate(window)
    _key(window, window.open_external_button, Qt.Key.Key_Space)
    _finished(window)
    _wait(lambda: len(_logs(handler_log)) == 3)
    assert _logs(handler_log)[2] == [command.fixed_args[-1], str(files[0])]
    assert window.external_settings == api.ExternalSettings(command, command)
    _stage("native_reopen_local_settings", settings_reloaded=True, handler_argv=_logs(handler_log)[2])
    # Closing a helper waiting on a catalog lock must remain asynchronous and reap.
    blocker = sqlite3.connect(database)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        _key(window, window.open_external_button, Qt.Key.Key_Space)
        cancel_worker = window.external_worker
        close_accepted = bool(window.close())
        assert not close_accepted and window.isVisible()
        _finished(window)
        _wait(lambda: not window.isVisible())
    finally:
        blocker.rollback()
        blocker.close()
    assert cancel_worker.outcome.status == "cancelled" and not cancel_worker.outcome.permit_sent
    final_cleanup = _close(window)
    _WINDOW = None
    assert len(_logs(handler_log)) == 3
    source_after, catalog_after = _manifest(files), _snapshot(database)
    assert source_after == baseline_source and catalog_after == baseline_catalog
    with catalog.connect(database) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
    assert integrity == "ok" and not foreign_keys and os.environ.get("XDG_RUNTIME_DIR") == runtime
    assert all(os.environ.get(variable) == value for variable, value in isolated_xdg.items())
    assert {name: _sha(repository / name) for name in SOURCE_FILES} == digests
    _stage("native_shutdown_and_preservation", cancelled_before_permit=True, final_cleanup=final_cleanup,
           first_cleanup=first_cleanup, original_manifest_after=source_after,
           catalog_digest_after=catalog_after, integrity=integrity, foreign_key_violations=[], runtime_directory_preserved=True,
           handler_request_count=3)
    _RECEIPT.update({"status": "complete", "complete": True, "host": host,
                     "fixture_source_count": 1, "fixture_asset_count": 2,
                     "handler_request_count": 3, "source_catalog_unchanged": True,
                     "privacy": {"generated_media_only": True, "app_only_captures": True,
                                 "runtime_directory_preserved": True, "fixture_root": str(fixture),
                                 "raw_path_receipts_private": True, "pngs_unedited": True,
                                 "isolated_xdg_roots": isolated_xdg},
                     "qualification": {"configured_stub_dispatch": True, "native_default_associations": False,
                                       "keyboard_scope": "Programmatic focus establishment followed by real QtTest keys into active exposed focused controls; bounded keyboard scrolling and Tab traversal.",
                                       "native_windows_macos": False, "broad_accessibility": False,
                                       "frozen_worker": False, "real_share_interruption": False}})
    _write(output / "external-actions-native-acceptance.json", _RECEIPT)
    _write(_RECEIPT_PATH, _RECEIPT)
    return _RECEIPT


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-helper-sha", required=True)
    args = parser.parse_args(argv)
    try:
        result = _run(args.output, args.expected_helper_sha)
        print(json.dumps({"status": result["status"], "assets": result["fixture_asset_count"],
                          "handler_request_count": result["handler_request_count"], "captures": result["captures"]}))
        return 0
    except BaseException as exc:
        if _RECEIPT is not None:
            _RECEIPT.update({"status": "failed", "complete": False,
                            "exception": {"type": type(exc).__name__, "message": str(exc)},
                            "traceback": traceback.format_exc()})
            _write(_RECEIPT_PATH, _RECEIPT)
        try:
            if _WINDOW is not None:
                _stage("failure_cleanup", result=_close(_WINDOW))
        except BaseException as cleanup_error:
            if _RECEIPT is not None:
                _stage("failure_cleanup_incomplete", error=str(cleanup_error))
        print(f"External native acceptance failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
