"""Root-only native cached viewing with warm fictional cache and explicit scans.

Raw receipts contain private absolute paths. Captures contain only safe generated
app content and are never edited. No association/editor or user source is opened.
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
import shutil
import sqlite3
import subprocess
import tempfile
import time
import traceback

from PIL import Image, ImageDraw
from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import Qt, qVersion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPlainTextEdit, QWidget

from defiantmaple import cached_preview as cache_api, catalog, collections, external_actions
from defiantmaple.private_eval import assert_outside_git
from defiantmaple.sources import add_source, list_sources, scan_sources
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import GalleryWindow
from prototypes.qt.identity import APP_ID, app_icon
# Reuse the already-reviewed active/exposed/focus/keyboard/scroll guards. These
# functions retain their real guards; no lock/activation bypass is introduced.
from prototypes.qt import external_actions_native_acceptance as native

SOURCE_FILES = (
    "defiantmaple/cached_preview.py", "defiantmaple/thumbnail.py", "defiantmaple/catalog.py",
    "defiantmaple/sources.py", "defiantmaple/collections.py", "defiantmaple/external_actions.py",
    "prototypes/qt/cached_preview.py", "prototypes/qt/app.py", "prototypes/qt/preview.py",
    "prototypes/qt/external_actions.py", "prototypes/qt/package.py", "prototypes/qt/identity.py",
    "tests/test_cached_preview.py", "tests/test_thumbnails.py",
    "prototypes/qt/tests/test_cached_preview_ui.py", "prototypes/qt/tests/test_gallery_workflow.py",
    "docs/cached-offline-design.md", "docs/cached-offline-guide.md", "prototypes/qt/README.md",
    "prototypes/qt/external_actions_native_acceptance.py",
    "prototypes/qt/cached_offline_native_acceptance.py",
)
_FIXTURE = None
_WINDOW = None
_RECEIPT = None
_PATH = None


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stage(name, **values):
    _RECEIPT["stages"].append({"stage": name, **values})
    native._write(_PATH, _RECEIPT)


def _snapshot(database):
    with closing(sqlite3.connect(database)) as db:
        dump = tuple(db.iterdump())
    return hashlib.sha256(json.dumps(dump).encode()).hexdigest()


def _preserve_snapshot(database, label):
    """Retain full private logical and physical evidence before fixture removal."""
    destination = _PATH.parent / ("private-catalog-" + label)
    destination.mkdir()
    with closing(sqlite3.connect(database)) as db:
        db.row_factory = sqlite3.Row
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {table: [dict(row) for row in db.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid')]
                for table in tables}
        dump = tuple(db.iterdump())
    logical = destination / "logical-rows-and-sql.json"
    native._write(logical, {"tables": rows, "sql_dump": dump})
    physical = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        source = Path(str(database) + suffix)
        if not source.exists():
            physical[suffix or "main"] = {"present": False}
            continue
        before = {"sha256": _sha(source), "bytes": source.stat().st_size}
        copied = destination / ("catalog.sqlite3" + suffix)
        shutil.copy2(source, copied)
        assert _sha(source) == before["sha256"] == _sha(copied)
        assert source.stat().st_size == before["bytes"] == copied.stat().st_size
        physical[suffix or "main"] = {"present": True, **before, "file": str(copied.relative_to(_PATH.parent))}
    receipt = {"label": label, "logical_file": str(logical.relative_to(_PATH.parent)),
               "logical_sha256": _sha(logical), "logical_bytes": logical.stat().st_size,
               "physical": physical, "tables": rows, "sql_digest": _snapshot(database)}
    _RECEIPT.setdefault("catalog_snapshots", []).append({key: value for key, value in receipt.items() if key != "tables"})
    native._write(_PATH, _RECEIPT)
    return receipt


def _scan_transition(before, after, expected_health):
    changed = [table for table in before["tables"] if before["tables"][table] != after["tables"][table]]
    assert set(changed) <= {"sources", "source_entries"}, changed
    assert after["tables"]["sources"][0]["health"] == expected_health
    fields = {}
    allowed_fields = {"sources": {"health", "health_detail", "last_scan_at", "initial_scan_completed"},
                      "source_entries": {"observed_at_ns"}}
    for table in changed:
        old, new = before["tables"][table], after["tables"][table]
        assert len(old) == len(new)
        fields[table] = sorted({key for previous, current in zip(old, new) for key in previous if previous[key] != current[key]})
        assert set(fields[table]) <= allowed_fields[table], fields
    return {"changed_tables": changed, "changed_fields": fields, "allowed_scan_tables": ["sources", "source_entries"],
            "asset_metadata_journals_collections_preserved": True, "expected_source_health": expected_health}


def _collection_rows(database):
    with catalog.connect(database) as db:
        return {table: [dict(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
                for table in ("collections", "collection_members")}


def _pixel_evidence(width, height, pixel, oriented=False):
    positions = [(width // 4, height // 4), (3 * width // 4, height // 4),
                 (width // 4, 3 * height // 4), (3 * width // 4, 3 * height // 4)]
    values = [list(pixel(x, y)) for x, y in positions]
    expected = [(20, 30, 230, 255), (230, 20, 30, 255), (230, 220, 20, 255), (20, 220, 30, 255)] if oriented else [(80, 170, 220, 100)] * 4
    tolerance = 35 if oriented else 1
    assert all(abs(actual - wanted) <= tolerance for value, match in zip(values, expected) for actual, wanted in zip(value, match)), values
    return {"quarter_positions": positions, "rgba_samples": values, "expected_rgba": expected,
            "channel_tolerance": tolerance, "orientation_marker_verified": oriented,
            "alpha_verified": not oriented}


def _dialog_pixels(dialog, oriented=False):
    image = dialog.canvas._item.pixmap().toImage()
    assert (image.width(), image.height()) == (64, 128)
    return _pixel_evidence(image.width(), image.height(), lambda x, y: image.pixelColor(x, y).getRgb(), oriented)


def _attempt_disabled_original_controls(window):
    attempts = []
    for control in (window.inspect_button, window.open_external_button, window.open_folder_button):
        native._reveal(window, control)
        native._key(window, window.gallery, Qt.Key.Key_Right)
        # Disabled controls cannot receive focus. Keep actual focus in the active
        # gallery, then deliver a real QtTest key event to the disabled receiver.
        assert all(native._focus(window)[key] for key in ("visible", "active", "exposed", "focus_inside"))
        assert control.isVisible() and not control.isEnabled() and native._reachable(window, control)
        assert window.inspect_dialog is None and window.external_worker is None
        clicked = []
        def observe_clicked(*_args):
            clicked.append(True)
        control.clicked.connect(observe_clicked)
        try:
            QTest.keyClick(control, Qt.Key.Key_Space)
            native._APP.processEvents()
            assert not clicked
            assert window.inspect_dialog is None and window.external_worker is None
        finally:
            control.clicked.disconnect(observe_clicked)
        attempts.append({"target": control.accessibleName() or control.text(), "key": "Key_Space",
                         "receiver_disabled": True, "focus": native._focus(window),
                         "delivery": "QtTest event to disabled receiver; gallery retains focus",
                         "clicked_signal_count": len(clicked), "new_inspector": False, "new_external_worker": False})
    return attempts


def _assets(database):
    with catalog.connect(database) as db:
        return [dict(row) for row in db.execute("SELECT * FROM assets ORDER BY asset_id")]


def _originals(folder, names):
    return {name: {"sha256": _sha(folder / name), "bytes": (folder / name).stat().st_size,
                   "mtime_ns": (folder / name).stat().st_mtime_ns} for name in names}


def _cache_manifest(root):
    return {str(path.relative_to(root)): {"sha256": _sha(path), "bytes": path.stat().st_size,
                                        "mtime_ns": path.stat().st_mtime_ns}
            for path in sorted(root.rglob("*")) if path.is_file()}


def _integrity(database):
    with catalog.connect(database) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    assert result == "ok" and not foreign
    return {"integrity": result, "foreign_key_violations": []}


def _health(database, source_id):
    return next(row["health"] for row in list_sources(database) if row["source_id"] == source_id)


def _capture(top, path):
    assert all(native._focus(top)[key] for key in ("visible", "active", "exposed", "focus_inside"))
    for widget in top.findChildren(QWidget):
        if not isinstance(widget, (QLabel, QLineEdit, QPlainTextEdit)) or not widget.isVisible():
            continue
        text = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()
        if str(Path.home()) in text:
            raise AssertionError("App-only capture would expose a private home path")
    assert top.grab().save(str(path))
    _RECEIPT["captures"].append({"file": path.name, "sha256": _sha(path), "bytes": path.stat().st_size,
                                  "unedited_app_only": True, "focus": native._focus(top)})
    native._write(_PATH, _RECEIPT)


def _host(window):
    screen = window.screen()
    rectangle = screen.geometry()
    available = screen.availableGeometry()
    return {"platform": platform.platform(), "os_release": platform.freedesktop_os_release(),
            "python": platform.python_version(), "pyside": PYSIDE_VERSION, "qt": qVersion(),
            "qt_platform": native._APP.platformName(), "display_environment": {
                name: os.environ.get(name) for name in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "WAYLAND_DISPLAY", "DISPLAY")},
            "screen_name_private": screen.name(), "screen_geometry": [rectangle.x(), rectangle.y(), rectangle.width(), rectangle.height()],
            "available_geometry": [available.x(), available.y(), available.width(), available.height()],
            "device_pixel_ratio": window.devicePixelRatio(), "logical_dpi": screen.logicalDotsPerInch(),
            "process_tree_rss": None, "rss_limit_claim": False}


def _close(window):
    cached = getattr(window, "cached_dialog", None)
    if cached is not None and cached.isVisible():
        cached.close()
        native._wait(lambda: not cached.isVisible(), 8)
    if cached is not None:
        assert not cached.worker.isRunning()
        assert cached.worker.outcome is None or cached.worker.outcome.cleanup_complete
    assert window.scan_worker is None or not window.scan_worker.isRunning()
    result = native._close(window)
    assert window.thumbnails is None or not window.thumbnails.isRunning()
    assert not cache_api._ORPHANS
    return {**result, "cached_worker_reaped": True, "thumbnail_thread_stopped": True,
            "source_scan_stopped": True}


def _seed(root):
    art = root / "fictional-originals"
    art.mkdir()
    names = ("alpha $(`literal`) ; ' café %.png", "beta-oriented.jpg", "gamma-wide.png")
    with Image.new("RGBA", (72, 144), (80, 170, 220, 100)) as image:
        image.save(art / names[0])
    with Image.new("RGB", (144, 72)) as image:
        draw = ImageDraw.Draw(image)
        for rectangle, color in (((0, 0, 71, 35), (230, 20, 30)), ((72, 0, 143, 35), (20, 220, 30)),
                                 ((0, 36, 71, 71), (20, 30, 230)), ((72, 36, 143, 71), (230, 220, 20))):
            draw.rectangle(rectangle, fill=color)
        exif = Image.Exif()
        exif[274] = 6
        image.save(art / names[1], exif=exif, quality=95, subsampling=0)
    with Image.new("RGB", (160, 72), (90, 150, 90)) as image:
        image.save(art / names[2])
    database = root / "fictional-library.sqlite3"
    catalog.initialize(database)
    source = add_source(database, art, name="Fictional cached originals", existing_file_policy="inbox")
    first = scan_sources(database, source_id=source["source_id"], quiet_seconds=0)
    second = scan_sources(database, source_id=source["source_id"], quiet_seconds=0)
    assert first["complete"] and second["complete"] and _health(database, source["source_id"]) == "paused"
    rows = _assets(database)
    assert len(rows) == 3
    identifiers = {Path(row["current_path"]).name: row["asset_id"] for row in rows}
    # Fixture-only metadata; subsequent viewing must preserve it and the journal.
    with catalog.connect(database) as db:
        db.execute("UPDATE assets SET rating=4,favorite=1 WHERE asset_id=?", (identifiers[names[0]],))
    collection = collections.create_collection(database, "Fictional offline review")
    for name in names[:2]:
        collections.add_member(database, collection["collection_id"], identifiers[name])
    for path in art.iterdir():
        path.chmod(0o444)
    cache = root / "cache"
    for identifier in identifiers.values():
        thumbnail_for(database, identifier, cache, max_edge=128)
    return database, source["source_id"], art, names, identifiers, cache


def _trial_cache_failures(database, target, root, cache):
    trial = root / "fictional-cache-refusal-trial"
    shutil.copytree(cache, trial)
    fingerprint = f"sha256-{target.sha256}-bytes-{target.byte_size}"
    folder = trial / target.asset_id[:2] / target.asset_id / fingerprint
    png = next(folder.glob("*.png"))
    png.write_bytes(b"fictional corruption")
    before = _snapshot(database)
    corrupt = cache_api.read_cached_preview(database, target, trial, 128)
    assert corrupt.status == "refused" and corrupt.cleanup_complete and _snapshot(database) == before
    for path in folder.iterdir():
        path.unlink()
    missing = cache_api.read_cached_preview(database, target, trial, 128)
    assert missing.status == "no_cache" and missing.cleanup_complete and _snapshot(database) == before
    return {"corrupt": corrupt.status, "no_cache": missing.status, "catalog_unchanged": True,
            "source_health_unchanged": True}


def _run(output, expected_sha, core_guard_log, expected_core_guard_log_sha):
    global _FIXTURE, _WINDOW, _RECEIPT, _PATH
    repository = Path(__file__).resolve().parents[2]
    if _sha(__file__) != expected_sha:
        raise ValueError("Native helper does not match its reviewed SHA")
    if os.environ.get("QT_QPA_PLATFORM", "").lower() in ("offscreen", "minimal", "vnc"):
        raise ValueError("Native helper requires a real visible desktop")
    output = output.expanduser().resolve(strict=False)
    assert_outside_git(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    _PATH = output / "cached-offline-native-raw.json"
    _RECEIPT = {"schema": "defiantmaple.cached-offline-native-acceptance.v1", "status": "running", "complete": False,
                "stages": [], "keyboard_actions": [], "captures": [],
                "scope": "Generated local source loss/restoration; cache-only viewing; no network/association/editor dispatch",
                "focus_method": "Programmatic focus/scrollbar establishment, guarded actual QtTest keys; scoped native navigation only"}
    native._RECEIPT, native._RECEIPT_PATH = _RECEIPT, _PATH
    source_digests = {name: _sha(repository / name) for name in SOURCE_FILES}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    guard_id = "test_real_child_never_accesses_original_and_preserves_catalog_pixels"
    assert _sha(core_guard_log) == expected_core_guard_log_sha
    guard_text = core_guard_log.read_text(encoding="utf-8")
    assert any(guard_id in line and line.rstrip().endswith("ok") for line in guard_text.splitlines())
    saved_guard = output / "private-core-guard-log.txt"
    shutil.copy2(core_guard_log, saved_guard)
    _RECEIPT["original_independence_evidence"] = {
        "native_scope": "Warm-cache success while captured originals are absent; no attempted-I/O instrumentation in native helper",
        "native_attempted_io_instrumentation": False,
        "separate_core_guard": "tests.test_cached_preview.CachedPreviewTests." + guard_id,
        "core_guard_log": saved_guard.name, "core_guard_log_sha256": _sha(saved_guard),
        "core_guard_spies": ["Path.open", "Path.stat", "Path.resolve", "os.open", "os.scandir"],
        "core_test_source_sha256": source_digests["tests/test_cached_preview.py"],
        "evidence_combination": "Core child spies establish no attempted original filesystem I/O; native run establishes visible missing-original behavior"}
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    _FIXTURE = Path(tempfile.mkdtemp(prefix="DefiantMaple-Fictional-Offline-", dir="/tmp")).resolve(strict=True)
    xdg = {f"XDG_{name}_HOME": str(_FIXTURE / "local-data" / name.lower()) for name in ("CONFIG", "DATA", "CACHE")}
    os.environ.update(xdg)
    database, source_id, art, names, identifiers, cache = _seed(_FIXTURE)
    source_before, metadata_before = _originals(art, names), _assets(database)
    cache_before = _cache_manifest(cache)
    collection_before = _collection_rows(database)
    initial_snapshot = _preserve_snapshot(database, "initial-warm-cache")
    _stage("generated_warm_cache", source_file_digests=source_digests, checked_out_head=head,
           fixture_root=str(_FIXTURE), source_id=source_id, initial_source_manifest=source_before,
           initial_cache_manifest=cache_before, asset_metadata=metadata_before, manual_collection=collection_before, isolated_xdg=xdg,
           isolated_xdg_verified=all(os.environ[name] == value for name, value in xdg.items()),
           wayland_runtime_preserved=os.environ.get("XDG_RUNTIME_DIR") == runtime)
    parked = _FIXTURE / "fictional-originals-unavailable"
    art.rename(parked)
    failed_scan = scan_sources(database, source_id=source_id, quiet_seconds=0)
    assert not failed_scan["complete"] and _health(database, source_id) == "offline"
    assert failed_scan["totals"]["missing"] == 0 and _assets(database) == metadata_before
    assert _originals(parked, names) == source_before and _cache_manifest(cache) == cache_before
    unavailable_catalog = _snapshot(database)
    offline_snapshot = _preserve_snapshot(database, "after-explicit-failed-scan")
    failure_transition = _scan_transition(initial_snapshot, offline_snapshot, "offline")
    assert _collection_rows(database) == collection_before
    first_id = identifiers[names[0]]
    with catalog.connect(database) as db:
        target = cache_api.capture_target(dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (first_id,)).fetchone()))
    trials = _trial_cache_failures(database, target, _FIXTURE, cache)
    refusal = external_actions.execute_external_action(database, external_actions.OpenTarget(
        target.asset_id, target.revision, target.path, target.sha256, target.byte_size, target.source_id),
        external_actions.OpenAction.FILE, external_actions.CommandSpec())
    assert refusal.status == "refused" and not refusal.permit_sent and not refusal.dispatched
    _stage("explicit_failure_scan", result=failed_scan, source_health="offline", entries_not_reconciled_missing=True,
           retained_ids_metadata=True, cache_trials=trials, external_status=refusal.status,
           external_permit_sent=False, catalog_digest=unavailable_catalog, scan_transition=failure_transition, **_integrity(database))
    native._APP = QApplication.instance() or QApplication([])
    app = native._APP
    app.setOrganizationName("DefiantMaple")
    app.setApplicationName("DefiantMaple")
    app.setApplicationDisplayName("DefiantMaple")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    assert app.platformName().lower() not in ("offscreen", "minimal", "vnc")
    def open_window():
        global _WINDOW
        window = GalleryWindow(database, enable_thumbnails=True, cache_root=cache, private_root=_FIXTURE / "private",
                               external_settings=external_actions.ExternalSettings(), external_settings_path=_FIXTURE / "local-tools.json")
        _WINDOW = window
        window.resize(1280, 800)
        window.show()
        native._select(window, first_id)
        window.gallery.setFocus()
        native._activate(window)
        return window
    window = open_window()
    selected = window._selected_asset()
    native._wait(lambda: window.thumbnails.lookup(selected, 144)[0] is not None)
    assert "Cached preview" in window.thumbnails.description(selected, 144)
    assert not window.inspect_button.isEnabled() and not window.open_external_button.isEnabled() and not window.open_folder_button.isEnabled()
    assert window.curation_button.isEnabled() and window.cached_button.isEnabled()
    disabled_attempts = _attempt_disabled_original_controls(window)
    native._select(window, first_id)
    selected = window._selected_asset()
    _capture(window, output / "fictional-offline-gallery.png")
    _stage("native_offline_grid", cache_description=window.thumbnails.description(selected, 144), source_health="offline",
           original_controls_disabled=True, disabled_control_key_attempts=disabled_attempts, cached_catalog_curation_enabled=True, catalog_unchanged=_snapshot(database) == unavailable_catalog)
    native._key(window, window.cached_button, Qt.Key.Key_Space)
    native._wait(lambda: window.cached_dialog is not None and window.cached_dialog.result is not None)
    dialog = window.cached_dialog
    dialog.canvas.setFocus()
    native._activate(dialog)
    assert dialog.result.status == "ready" and dialog.result.target.asset_id == first_id
    assert (dialog.result.width, dialog.result.height) == (64, 128)
    assert "Cached preview" in dialog.status.text() and "offline" in dialog.status.text() and "64 × 128" in dialog.status.text()
    captured_target = dialog.target
    native._select(window, identifiers[names[2]])
    assert dialog.target == captured_target and dialog.result.target == captured_target
    native._key(dialog, dialog.canvas, Qt.Key.Key_Plus)
    native._key(dialog, dialog.canvas, Qt.Key.Key_F)
    native._key(dialog, dialog.background_box, Qt.Key.Key_End)
    assert dialog.background_box.currentText() == "Dark"
    _capture(dialog, output / "fictional-offline-cached-inspector.png")
    _stage("native_cached_inspector", captured_asset_id=first_id, dimensions=[dialog.result.width, dialog.result.height],
           cache_edge=dialog.result.cache_edge, requested_edge=dialog.result.requested_edge,
           aspect_preserved=True, alpha_background="Dark", pixel_evidence=_dialog_pixels(dialog), captured_selection_drift=True,
           address_space_enforced=dialog.result.address_space_enforced, address_space_note=dialog.result.address_space_note,
           catalog_unchanged=_snapshot(database) == unavailable_catalog)
    native._key(dialog, dialog.close_button, Qt.Key.Key_Space)
    native._wait(lambda: not dialog.isVisible())
    native._select(window, identifiers[names[1]])
    window.gallery.setFocus()
    native._activate(window)
    native._key(window, window.cached_button, Qt.Key.Key_Space)
    native._wait(lambda: window.cached_dialog is not None and window.cached_dialog.result is not None)
    oriented_dialog = window.cached_dialog
    oriented_dialog.canvas.setFocus()
    native._activate(oriented_dialog)
    assert oriented_dialog.result.status == "ready"
    assert (oriented_dialog.result.width, oriented_dialog.result.height) == (64, 128)
    assert oriented_dialog.target.asset_id == identifiers[names[1]]
    _stage("native_oriented_cached_inspector", cached_dimensions=[64, 128], indexed_source_dimensions=[144, 72],
           indexed_exif_orientation=6, orientation_preserved=True, pixel_evidence=_dialog_pixels(oriented_dialog, True), catalog_unchanged=_snapshot(database) == unavailable_catalog)
    native._key(oriented_dialog, oriented_dialog.close_button, Qt.Key.Key_Space)
    native._wait(lambda: not oriented_dialog.isVisible())
    first_cleanup = _close(window)
    _WINDOW = None
    window = open_window()
    selected = window._selected_asset()
    native._wait(lambda: window.thumbnails.lookup(selected, 144)[0] is not None)
    assert _snapshot(database) == unavailable_catalog and _assets(database) == metadata_before
    reopened_snapshot = _preserve_snapshot(database, "after-offline-reopen")
    assert all(
        {k: v for k, v in reopened_snapshot["physical"][suffix].items() if k != "file"} == {k: v for k, v in value.items() if k != "file"}
        for suffix, value in offline_snapshot["physical"].items())
    assert _collection_rows(database) == collection_before
    _stage("native_reopen_offline", collection_membership_preserved=True, physical_catalog_bytes_preserved=True, cache_visible=True, stable_ids_metadata=True, first_cleanup=first_cleanup,
           source_health=_health(database, source_id), catalog_unchanged=True)
    parked.rename(art)
    assert _originals(art, names) == source_before
    assert _health(database, source_id) == "offline" and _snapshot(database) == unavailable_catalog
    assert not window.inspect_button.isEnabled() and not window.open_external_button.isEnabled()
    restored_snapshot = _preserve_snapshot(database, "restored-before-rescan")
    assert restored_snapshot["tables"] == offline_snapshot["tables"]
    _stage("restoration_without_implicit_reconciliation", restored_original_manifest=_originals(art, names),
           source_health="offline", original_controls_still_disabled=True, catalog_unchanged=True)
    # The real source chooser/scan button uses actual keys on the visible app.
    native._key(window, window.source_box, Qt.Key.Key_Home)
    native._key(window, window.source_box, Qt.Key.Key_Down)
    assert window.source_box.currentData() == source_id
    native._key(window, window.scan_button, Qt.Key.Key_Space)
    native._wait(lambda: window.scan_worker is not None and not window.scan_worker.isRunning()
                 and _health(database, source_id) == "paused", 15)
    app.processEvents()
    native._select(window, first_id)
    assert window.inspect_button.isEnabled() and window.open_external_button.isEnabled() and window.open_folder_button.isEnabled()
    assert _assets(database) == metadata_before and _originals(art, names) == source_before
    assert _cache_manifest(cache) == cache_before
    final_snapshot = _preserve_snapshot(database, "after-explicit-restored-rescan")
    restored_transition = _scan_transition(restored_snapshot, final_snapshot, "paused")
    assert _collection_rows(database) == collection_before
    _stage("explicit_restored_source_rescan", scan_transition=restored_transition, collection_membership_preserved=True, source_health="paused", original_controls_enabled=True,
           ids_metadata_unchanged=True, originals_cache_unchanged=True, scan_status=window.scan_status.text(),
           catalog_digest_after_explicit_scan=_snapshot(database), **_integrity(database))
    host = _host(window)  # Actual exposed window facts, before closing.
    final_cleanup = _close(window)
    _WINDOW = None
    assert {name: _sha(repository / name) for name in SOURCE_FILES} == source_digests
    assert os.environ.get("XDG_RUNTIME_DIR") == runtime
    _RECEIPT.update(host=host, cleanup=final_cleanup, source_hashes_preserved=True,
                    isolated_xdg=xdg, wayland_runtime_preserved=True,
                    unexpected_dispatch_count=0, status="passed", complete=True,
                    resource_evidence="Small source-native fixture only; frozen ceiling/whole-process RSS qualification separate")
    shutil.rmtree(_FIXTURE)
    _RECEIPT["fixture_cleanup_complete"] = not _FIXTURE.exists()
    assert _RECEIPT["fixture_cleanup_complete"]
    _stage("complete", source_and_metadata_preserved=True, fixture_removed=True)
    return {"status": "passed", "complete": True, "stages": len(_RECEIPT["stages"]),
            "captures": len(_RECEIPT["captures"]), "keyboard_actions": len(_RECEIPT["keyboard_actions"])}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-helper-sha", required=True)
    parser.add_argument("--core-guard-log", required=True, type=Path)
    parser.add_argument("--expected-core-guard-log-sha", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(_run(args.output_root, args.expected_helper_sha, args.core_guard_log, args.expected_core_guard_log_sha)))
        return 0
    except Exception as exc:
        if _RECEIPT is not None:
            _RECEIPT.update(status="failed", complete=False, error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            try:
                if _WINDOW is not None:
                    _RECEIPT["failure_cleanup"] = _close(_WINDOW)
            except Exception as cleanup:
                _RECEIPT["failure_cleanup_error"] = f"{type(cleanup).__name__}: {cleanup}"
            # Failed fixtures are retained for diagnosis; never falsely report removal.
            try:
                database = _FIXTURE / "fictional-library.sqlite3" if _FIXTURE else None
                if database is not None and database.exists():
                    _preserve_snapshot(database, "failure-retained")
            except Exception as snapshot:
                _RECEIPT["failure_snapshot_error"] = f"{type(snapshot).__name__}: {snapshot}"
            _RECEIPT["failed_fixture_retained"] = bool(_FIXTURE and _FIXTURE.exists())
            native._write(_PATH, _RECEIPT)
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
