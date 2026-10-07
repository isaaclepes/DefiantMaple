"""Root-only captured comparison acceptance on isolated fictional local media.

Full captures and receipts are private. Public images are separate direct canvas
captures, excluding identity/path rows; no screenshot is edited. --selfcheck
only creates/checks generated fixtures and does not open a native window.
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
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageOps, __version__ as PILLOW_VERSION
from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QPoint, QItemSelectionModel, Qt, qVersion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import cached_preview, catalog, collections, external_actions
from defiantmaple.private_eval import assert_outside_git
from defiantmaple.sources import add_source, list_sources, scan_sources
from defiantmaple.thumbnail import thumbnail_for
from prototypes.qt.app import GalleryWindow
from prototypes.qt.comparison import ComparisonDialog
from prototypes.qt.identity import APP_ID, app_icon
from prototypes.qt.preview import _FULL_IMAGE_OWNERS
from prototypes.qt import external_actions_native_acceptance as native

SOURCE_FILES = (
    "defiantmaple/catalog.py", "defiantmaple/cached_preview.py", "defiantmaple/thumbnail.py",
    "defiantmaple/sources.py", "defiantmaple/collections.py", "defiantmaple/external_actions.py",
    "prototypes/qt/app.py", "prototypes/qt/comparison.py", "prototypes/qt/preview.py",
    "prototypes/qt/cached_preview.py", "prototypes/qt/external_actions.py", "prototypes/qt/identity.py",
    "prototypes/qt/package.py", "prototypes/qt/tests/test_comparison_ui.py",
    "prototypes/qt/tests/test_gallery_usability.py", "prototypes/qt/tests/test_gallery_workflow.py",
    "prototypes/qt/tests/test_cached_preview_ui.py", "tests/test_cached_preview.py",
    "docs/comparison-design.md", "docs/comparison-guide.md", "prototypes/qt/README.md",
    "prototypes/qt/external_actions_native_acceptance.py",
    "prototypes/qt/comparison_native_acceptance.py",
)
_ROOT = _WINDOW = _RECEIPT = _PATH = None


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stage(name, **values):
    _RECEIPT["stages"].append({"stage": name, **values})
    native._write(_PATH, _RECEIPT)


def _manifest(root):
    return {str(path.relative_to(root)): {"sha256": _sha(path), "bytes": path.stat().st_size,
                                         "mtime_ns": path.stat().st_mtime_ns}
            for path in sorted(root.rglob("*")) if path.is_file()}


def _snapshot(database, label):
    """Retain full raw rows and physical files for independent recomputation."""
    folder = _PATH.parent / ("private-catalog-" + label)
    folder.mkdir()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {table: [dict(row) for row in db.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid')]
                for table in tables}
        logical = {"rows": rows, "sql_dump": list(db.iterdump())}
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    logical_file = folder / "logical-rows-and-sql.json"
    native._write(logical_file, logical)
    physical = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(str(database) + suffix)
        if not path.exists():
            physical[suffix or "main"] = {"present": False}
            continue
        digest = _sha(path)
        copy = folder / ("catalog.sqlite3" + suffix)
        shutil.copy2(path, copy)
        assert digest == _sha(path) == _sha(copy)
        physical[suffix or "main"] = {"present": True, "sha256": digest, "bytes": path.stat().st_size,
                                      "file": str(copy.relative_to(_PATH.parent))}
    receipt = {"label": label, "logical_file": str(logical_file.relative_to(_PATH.parent)),
               "logical_sha256": _sha(logical_file), "physical": physical,
               "integrity": "ok", "foreign_key_violations": []}
    _RECEIPT.setdefault("catalog_snapshots", []).append(receipt)
    native._write(_PATH, _RECEIPT)
    return {"rows": rows, "physical": physical, "logical_sha256": receipt["logical_sha256"]}


def _view_preserved(before, after):
    assert before["rows"] == after["rows"]
    def facts(value):
        return {suffix: {key: item for key, item in entry.items() if key != "file"}
                for suffix, entry in value.items()}
    assert facts(before["physical"]) == facts(after["physical"])


def _scan_delta(before, after, source_id, expected_health):
    changed = {table for table in before["rows"] if before["rows"][table] != after["rows"][table]}
    assert changed <= {"sources", "source_entries"}, changed
    assert next(row["health"] for row in after["rows"]["sources"] if row["source_id"] == source_id) == expected_health
    allowed = {"sources": {"health", "health_detail", "last_scan_at", "initial_scan_completed"},
               "source_entries": {"observed_at_ns"}}
    fields = {}
    for table in changed:
        old, new = before["rows"][table], after["rows"][table]
        assert len(old) == len(new)
        fields[table] = sorted({key for a, b in zip(old, new) for key in a if a[key] != b[key]})
        assert set(fields[table]) <= allowed[table], fields
    return {"changed_tables": sorted(changed), "changed_fields": fields,
            "expected_health": expected_health, "asset_metadata_and_collections_preserved": True}


def _collection_drift(database, fixture, before):
    """Declare the two membership-trigger revisions and exact new position."""
    collection_id, identifier = fixture["collection"]["collection_id"], fixture["ids"]["C"]
    collections.remove_member(database, collection_id, identifier)
    collections.add_member(database, collection_id, identifier)
    after = _snapshot(database, "after-declared-collection-drift")
    expected = json.loads(json.dumps(before["rows"]))
    row = next(row for row in expected["assets"] if row["asset_id"] == identifier)
    old_revision = row["revision"]
    row["revision"] += 2
    member = next(row for row in expected["collection_members"] if row["asset_id"] == identifier and row["collection_id"] == collection_id)
    previous_position = member["position"]
    member["position"] = max(row["position"] for row in expected["collection_members"] if row["collection_id"] == collection_id) + 1
    for table, rows in expected.items():
        if table == "collection_members":
            assert sorted(rows, key=lambda row: (row["collection_id"], row["asset_id"])) == sorted(
                after["rows"][table], key=lambda row: (row["collection_id"], row["asset_id"]))
        else:
            assert rows == after["rows"][table], table
    return after, {"asset_id_private": identifier, "revision_before": old_revision, "revision_after": old_revision + 2,
                   "membership_preserved": True, "position_before": previous_position, "position_after": member["position"],
                   "all_other_asset_fields_rows_tables_preserved": True, "operations": "remove C then add C at end through collection API"}


def _seed(root):
    fixture = root / "fixture"
    fixture.mkdir()
    scratch = root / "runtime-scratch"
    scratch.mkdir()
    media = fixture / "sources"
    media.mkdir()
    available, unavailable = media / "available", media / "unavailable"
    available.mkdir()
    unavailable.mkdir()
    names = {"A": "alpha $(`literal`) ; ' café %.png", "B": "beta-oriented.jpg",
             "C": "gamma-unavailable.png", "D": "delta-corrupt.png"}
    with Image.new("RGBA", (600, 300)) as image:
        draw = ImageDraw.Draw(image)
        for rectangle, color in (((0, 0, 299, 149), (80, 170, 220, 64)), ((300, 0, 599, 149), (230, 20, 30, 128)),
                                 ((0, 150, 299, 299), (230, 220, 20, 192)), ((300, 150, 599, 299), (20, 220, 30, 100))):
            draw.rectangle(rectangle, fill=color)
        image.save(available / names["A"])
    with Image.new("RGB", (288, 144)) as image:
        draw = ImageDraw.Draw(image)
        for rectangle, color in (((0, 0, 143, 71), (230, 20, 30)), ((144, 0, 287, 71), (20, 220, 30)),
                                 ((0, 72, 143, 143), (20, 30, 230)), ((144, 72, 287, 143), (230, 220, 20))):
            draw.rectangle(rectangle, fill=color)
        exif = Image.Exif()
        exif[274] = 6
        image.save(available / names["B"], exif=exif, quality=100, subsampling=0)
    with Image.new("RGBA", (160, 72), (90, 150, 90, 61)) as image:
        image.save(unavailable / names["C"])
        image.save(available / names["D"])
    database = fixture / "fictional-library.sqlite3"
    catalog.initialize(database)
    source_ids = {}
    for label, folder in (("available", available), ("unavailable", unavailable)):
        source = add_source(database, folder, name="Fictional " + label, existing_file_policy="inbox")
        source_ids[label] = source["source_id"]
        for _ in range(2):
            assert scan_sources(database, source_id=source["source_id"], quiet_seconds=0)["complete"]
        assert next(row["health"] for row in list_sources(database) if row["source_id"] == source["source_id"]) == "paused"
    with catalog.connect(database) as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM assets")]
    ids = {key: next(row["asset_id"] for row in rows if Path(row["current_path"]).name == name) for key, name in names.items()}
    collection = collections.create_collection(database, "Fictional comparison review")
    for key in ("A", "B", "C", "D"):
        collections.add_member(database, collection["collection_id"], ids[key])
    cache = fixture / "cache"
    cache_paths = {key: Path(thumbnail_for(database, ids[key], cache, max_edge=256)["path"])
                   for key in ("A", "B", "C", "D")}
    for path in media.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    return {"database": database, "cache": cache, "media": media, "available": available,
            "unavailable": unavailable, "scratch": scratch, "source_ids": source_ids,
            "ids": ids, "names": names, "collection": collection, "cache_paths": cache_paths}


def _select(window, ids):
    selection = window.gallery.selectionModel()
    selection.clearSelection()
    for identifier in ids:
        row = window.model.row_for_asset(identifier)
        assert row is not None
        selection.select(window.model.index(row), QItemSelectionModel.SelectionFlag.Select)
    native._APP.processEvents()
    rows = sorted({index.row() for index in selection.selectedIndexes()})
    actual = [window.model.asset_at(row)["asset_id"] for row in rows]
    assert set(actual) == set(ids) and len(actual) == len(ids)
    _RECEIPT.setdefault("selection_setup", []).append({"method": "programmatic stable-ID selection; subsequent command uses guarded keyboard",
                                                     "view_order_ids_private": actual})
    return actual


def _ready(dialog):
    native._wait(lambda: dialog.active is None and not dialog.queue and dialog.worker is not None and not dialog.worker.isRunning(), 18)
    assert dialog.worker.cleanup_complete
    assert all(pane.result is not None for pane in dialog.panes.values())


def _load_original(dialog, pane):
    """Observe real supervisor scratch creation; delegate unchanged allocation."""
    allocator = tempfile.TemporaryDirectory
    observed = []
    def allocate(*args, **kwargs):
        temporary = allocator(*args, **kwargs)
        if kwargs.get("prefix") == "defiantmaple-comparison-original-":
            path = Path(temporary.name).resolve(strict=True)
            assert path.parent == (_ROOT / "runtime-scratch")
            observed.append(path)
        return temporary
    with patch("prototypes.qt.comparison.tempfile.TemporaryDirectory", side_effect=allocate):
        native._key(dialog, pane.original_button, Qt.Key.Key_Space)
        _ready(dialog)
    if pane.result.status == "ready":
        assert observed
    assert all(not path.exists() for path in observed)
    _RECEIPT.setdefault("actual_supervisor_scratch_private", []).append({
        "paths": [str(path) for path in observed], "confirmed_removed": True,
        "instrumentation": "allocation wrapper delegates actual TemporaryDirectory; no filesystem behavior or original I/O changed"})


def _open(window, ids):
    order = _select(window, ids)
    window.gallery.setFocus()
    native._activate(window)
    native._key(window, window.compare_button, Qt.Key.Key_Space)
    dialog = window.comparison_dialog
    assert dialog is not None
    dialog.panes["left"].canvas.setFocus()
    native._activate(dialog)
    _ready(dialog)
    assert [target.asset_id for target in dialog.targets] == order
    assert all(pane.result.mode == "cache" for pane in dialog.panes.values())
    return dialog


def _close_dialog(dialog):
    if dialog.isVisible():
        native._key(dialog, dialog.close_button, Qt.Key.Key_Space)
        native._wait(lambda: not dialog.isVisible(), 8)
    assert dialog.worker is None or (not dialog.worker.isRunning() and dialog.worker.cleanup_complete)
    assert all(pane.canvas._item is None for pane in dialog.panes.values())
    assert not _FULL_IMAGE_OWNERS and not cached_preview._ORPHANS


def _close_window(window):
    dialog = window.comparison_dialog
    if dialog is not None and dialog.isVisible():
        _close_dialog(dialog)
    result = native._close(window)
    assert not window.thumbnails.isRunning()
    assert window.scan_worker is None or not window.scan_worker.isRunning()
    assert not _FULL_IMAGE_OWNERS and not cached_preview._ORPHANS
    return {**result, "comparison_clean": True, "thumbnail_stopped": True, "source_scan_stopped": True}


def _pixel_samples(width, height, pixel, key, mode):
    """Mode-scaled quarter markers distinguish alpha, aspect and orientation."""
    assert mode in ("cache", "original")
    size = [width, height]
    positions = [(width // 4, height // 4), (3 * width // 4, height // 4),
                 (width // 4, 3 * height // 4), (3 * width // 4, 3 * height // 4)]
    samples = [list(pixel(x, y)) for x, y in positions]
    if key == "A":
        assert size == ([256, 128] if mode == "cache" else [600, 300])
        expected = [(80, 170, 220, 64), (230, 20, 30, 128), (230, 220, 20, 192), (20, 220, 30, 100)]
        # Qt's premultiplied pixmap representation can round RGB at low alpha.
        tolerances = [3, 3, 3, 1]
    elif key == "B":
        assert size == ([128, 256] if mode == "cache" else [144, 288])
        expected = [(20, 30, 230, 255), (230, 20, 30, 255), (230, 220, 20, 255), (20, 220, 30, 255)]
        tolerances = [20, 20, 20, 1]
    else:
        assert size == [160, 72]
        expected = [(90, 150, 90, 61)] * 4
        tolerances = [3, 3, 3, 1]
    assert all(abs(a - b) <= tolerance for sample, match in zip(samples, expected)
               for a, b, tolerance in zip(sample, match, tolerances)), samples
    return {"actual_size": size, "quarter_positions": positions, "rgba_samples": samples,
            "expected_rgba": expected, "channel_tolerances": tolerances, "mode": mode}


def _fixture_properties(fixture):
    """Fixture-only proof before native interaction; no product worker involved."""
    evidence = {}
    for key in ("A", "B"):
        evidence[key] = {}
        for mode, path in (("original", fixture["available"] / fixture["names"][key]),
                           ("cache", fixture["cache_paths"][key])):
            with Image.open(path) as source:
                with ImageOps.exif_transpose(source) as oriented:
                    with oriented.convert("RGBA") as image:
                        evidence[key][mode] = _pixel_samples(*image.size, lambda x, y: image.getpixel((x, y)), key, mode)
        cached_size, original_size = evidence[key]["cache"]["actual_size"], evidence[key]["original"]["actual_size"]
        assert all(a < b for a, b in zip(cached_size, original_size))
        assert cached_size[0] * original_size[1] == cached_size[1] * original_size[0]
    a, b = evidence["A"]["original"]["actual_size"], evidence["B"]["original"]["actual_size"]
    assert a[0] * b[1] != a[1] * b[0] and a[0] > a[1] and b[0] < b[1]
    return {"images": evidence, "aspect_ratios_distinct": True, "cache_smaller_than_original": True,
            "scope": "fixture-only Pillow validation, separate from actual native worker/pixmap evidence"}


def _pixels(pane, key):
    image = pane.canvas._item.pixmap().toImage()
    evidence = _pixel_samples(image.width(), image.height(), lambda x, y: image.pixelColor(x, y).getRgb(), key, pane.result.mode)
    assert [pane.result.width, pane.result.height] == evidence["actual_size"]
    return {**evidence,
            "status_text": pane.status.text(), "target_private": pane.target.asset_id}


def _capture(dialog, label, public_canvases=False):
    assert all(native._focus(dialog)[key] for key in ("visible", "active", "exposed", "focus_inside"))
    path = _PATH.parent / ("private-" + label + ".png")
    assert dialog.grab().save(str(path))
    _RECEIPT["captures"].append({"file": path.name, "sha256": _sha(path), "scope": "private full unedited app widget; may contain UUIDs/paths"})
    if public_canvases:
        for side, pane in dialog.panes.items():
            public = _PATH.parent / ("public-" + label + "-" + side + "-canvas.png")
            assert pane.canvas.grab().save(str(public))
            _RECEIPT["captures"].append({"file": public.name, "sha256": _sha(public),
                "scope": "separate direct canvas-widget capture excludes identity/path/status rows; generated pixels only; unedited"})
    native._write(_PATH, _RECEIPT)


def _transforms(dialog):
    left, right = dialog.panes["left"], dialog.panes["right"]
    actions = []
    for side, pane, other in (("left", left, right), ("right", right, left)):
        other_scale = other.canvas.transform().m11()
        native._key(dialog, pane.canvas, Qt.Key.Key_Plus)
        assert not pane.canvas._fit and other.canvas.transform().m11() == other_scale
        native._key(dialog, pane.canvas, Qt.Key.Key_F)
        assert pane.canvas._fit and other.canvas.transform().m11() == other_scale
        # Zoom beyond the viewport then deliver an actual mouse drag, not a
        # scrollbar/state mutation. The other pane must retain its transform.
        for _ in range(12):
            native._key(dialog, pane.zoom_in_button, Qt.Key.Key_Space)
        viewport = pane.canvas.viewport()
        start = viewport.rect().center()
        before = (pane.canvas.horizontalScrollBar().value(), pane.canvas.verticalScrollBar().value())
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(viewport, start + QPoint(40, 30), 30)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + QPoint(40, 30))
        native._APP.processEvents()
        after = (pane.canvas.horizontalScrollBar().value(), pane.canvas.verticalScrollBar().value())
        assert before != after and other.canvas.transform().m11() == other_scale
        actions.append({"pane": side, "mouse_drag": [40, 30], "scroll_before": before, "scroll_after": after,
                        "other_transform_preserved": True})
        native._key(dialog, pane.fit_button, Qt.Key.Key_Space)
    other_background = right.background_box.currentText()
    native._key(dialog, left.background_box, Qt.Key.Key_Down)
    assert left.background_box.currentText() == "Light" and right.background_box.currentText() == other_background
    native._key(dialog, left.canvas, Qt.Key.Key_Tab)
    assert native._APP.focusWidget() is left.original_button
    native._key(dialog, right.canvas, Qt.Key.Key_F11)
    native._wait(dialog.isFullScreen)
    native._key(dialog, right.canvas, Qt.Key.Key_Escape)
    native._wait(lambda: not dialog.isFullScreen())
    assert dialog.isVisible()
    return actions


def _host(window):
    screen = window.screen()
    return {"platform": platform.platform(), "os_release": platform.freedesktop_os_release(),
            "python": platform.python_version(), "qt": qVersion(), "pyside": PYSIDE_VERSION,
            "pillow": PILLOW_VERSION, "qt_platform": native._APP.platformName(),
            "screen_name_private": screen.name(), "screen_geometry": screen.geometry().getRect(),
            "available_geometry": screen.availableGeometry().getRect(), "device_pixel_ratio": window.devicePixelRatio(),
            "display_environment_private": {key: os.environ.get(key) for key in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "DISPLAY", "WAYLAND_DISPLAY")},
            "rss_measurement": None, "pixel_buffer_accounting_mib": 256.5, "rss_budget_claim": False}


def _unlocked():
    # Linux/KDE native evidence only. A missing/ambiguous session check refuses.
    session = os.environ.get("XDG_SESSION_ID")
    if not session:
        raise ValueError("Native run needs a known local session")
    completed = subprocess.run(["loginctl", "show-session", session, "-p", "Active", "-p", "Remote", "-p", "LockedHint"],
                               check=True, capture_output=True, text=True, timeout=3)
    values = dict(line.split("=", 1) for line in completed.stdout.splitlines())
    assert values.get("Active") == "yes" and values.get("Remote") == "no" and values.get("LockedHint") == "no"
    screensaver = subprocess.run(["busctl", "--user", "call", "org.freedesktop.ScreenSaver", "/ScreenSaver",
                                  "org.freedesktop.ScreenSaver", "GetActive"],
                                 check=True, capture_output=True, text=True, timeout=3)
    assert screensaver.stdout.strip() == "b false"
    return {**values, "ScreenSaver_GetActive": False}


def _run(args):
    global _ROOT, _WINDOW, _RECEIPT, _PATH
    repository = Path(__file__).resolve().parents[2]
    assert _sha(__file__) == args.expected_helper_sha
    output = args.output_root.expanduser().resolve(strict=False)
    assert_outside_git(output)
    assert not output.exists() or not any(output.iterdir())
    output.mkdir(parents=True, exist_ok=True)
    _PATH = output / "comparison-native-raw.json"
    _RECEIPT = {"schema": "defiantmaple.comparison-native.v1", "status": "running", "complete": False,
                "stages": [], "captures": [], "keyboard_actions": [],
                "focus_method": "programmatic selection/focus plus guarded real QtTest keys and mouse events; not human keyboard-only/AT qualification"}
    native._RECEIPT, native._RECEIPT_PATH = _RECEIPT, _PATH
    source_hashes = {name: _sha(repository / name) for name in SOURCE_FILES}
    assert _sha(args.focused_log) == args.expected_focused_log_sha
    log = args.focused_log.read_text()
    assert "Ran 53 tests" in log and log.rstrip().endswith("OK")
    shutil.copy2(args.focused_log, output / "private-focused-worker-log.txt")
    _ROOT = Path(tempfile.mkdtemp(prefix="DefiantMaple-Fictional-Comparison-", dir="/tmp")).resolve(strict=True)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    isolated = {f"XDG_{key}_HOME": str(_ROOT / "local-data" / key.lower()) for key in ("CONFIG", "DATA", "CACHE")}
    os.environ.update(isolated)
    fixture = _seed(_ROOT)
    previous_tmpdir = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = str(fixture["scratch"])
    database, cache, ids = fixture["database"], fixture["cache"], fixture["ids"]
    originals, cached = _manifest(fixture["media"]), _manifest(cache)
    initial = _snapshot(database, "initial")
    fixture_properties = _fixture_properties(fixture)
    _stage("generated", source_hashes=source_hashes, fixture_properties=fixture_properties,
           checked_out_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
           fixture_private=str(_ROOT), originals_private=originals, cache_private=cached,
           isolated_xdg=isolated, isolated_xdg_verified=all(os.environ[key] == value for key, value in isolated.items()),
           supervised_original_scratch_base_private=str(fixture["scratch"]),
           tmpdir_override="current helper process and spawned children only", previous_tmpdir_private=previous_tmpdir,
           wayland_runtime_preserved=os.environ.get("XDG_RUNTIME_DIR") == runtime,
           actual_vs_injected_evidence="Native actual loaders/transforms/cleanup; separate focused log contains injected setup/allocation/reap/transport/late-delivery/backpressure cases",
           native_attempted_original_io_instrumentation=False)
    if args.selfcheck:
        _view_preserved(initial, _snapshot(database, "selfcheck-final"))
        _, mutation = _collection_drift(database, fixture, initial)
        _stage("selfcheck_declared_collection_mutation", **mutation)
        assert _manifest(fixture["media"]) == originals and _manifest(cache) == cached
        shutil.rmtree(_ROOT)
        _RECEIPT.update(status="selfcheck_passed", complete=True, native_executed=False, fixture_cleanup_complete=True)
        _stage("complete")
        return {"status": "selfcheck_passed", "native_executed": False}
    assert os.environ.get("QT_QPA_PLATFORM", "").lower() not in ("offscreen", "minimal", "vnc")
    _stage("native_preflight", session=_unlocked())
    native._APP = QApplication.instance() or QApplication([])
    app = native._APP
    app.setOrganizationName("DefiantMaple")
    app.setApplicationName("DefiantMaple")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    assert app.platformName().lower() not in ("offscreen", "minimal", "vnc")
    def open_window():
        global _WINDOW
        _WINDOW = GalleryWindow(database, enable_thumbnails=True, cache_root=cache, private_root=_ROOT / "private",
                                external_settings=external_actions.ExternalSettings(), external_settings_path=_ROOT / "local-tools.json")
        _WINDOW.resize(1280, 800)
        _WINDOW.show()
        _WINDOW.gallery.setFocus()
        native._activate(_WINDOW)
        return _WINDOW
    window = open_window()
    host = _host(window)
    refusals = []
    for selection in ((), (ids["A"],), (ids["A"], ids["B"], ids["C"])):
        _select(window, selection)
        assert window.compare_selected() is None and window.comparison_dialog is None
        refusals.append({"count": len(selection), "message": window.statusBar().currentMessage(), "method": "direct admission API from real gallery selection"})
    rows = [dict(window.model.asset_at(window.model.row_for_asset(ids[key]))) for key in ("A", "A")]
    try:
        ComparisonDialog(database, cache, rows)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate target admitted")
    rows = [dict(window.model.asset_at(window.model.row_for_asset(ids[key]))) for key in ("A", "B")]
    rows[1]["media_type"] = "application/octet-stream"
    try:
        ComparisonDialog(database, cache, rows)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported captured-row admission succeeded")
    dialog = _open(window, (ids["A"], ids["B"]))
    assert all(pane.result.status == "ready" for pane in dialog.panes.values())
    evidence = {side: _pixels(pane, "A" if pane.target.asset_id == ids["A"] else "B") for side, pane in dialog.panes.items()}
    left_size, right_size = evidence["left"]["actual_size"], evidence["right"]["actual_size"]
    assert left_size[0] * right_size[1] != left_size[1] * right_size[0]
    transforms = _transforms(dialog)
    _capture(dialog, "cache-first", True)
    captured = dialog.targets
    # Parent-view drift is deliberately programmatic; target retention is checked.
    _select(window, (ids["C"],))
    window.model.set_metadata_filters(search="gamma")
    window.model.refresh()
    window.model.set_metadata_filters()
    window.model.set_collection(fixture["collection"]["collection_id"])
    window.model.set_collection(None)
    before_drift, collection_delta = _collection_drift(database, fixture, initial)
    assert dialog.targets == captured
    _stage("admission_cache_transforms", admission_refusals=refusals, duplicate_api_refused=True,
           unsupported_api_refused=True, unsupported_fixture_method="copied captured row only; no catalog or unsupported index mutation",
           pixels=evidence, transform_mouse_events=transforms, captured_targets_preserved=True,
           declared_collection_delta=collection_delta)
    original_evidence = {}
    for side, pane in dialog.panes.items():
        other = dialog.panes["right" if side == "left" else "left"]
        other_target = other.target
        _load_original(dialog, pane)
        assert pane.result.status == "ready" and pane.result.mode == "original" and other.target == other_target
        original_evidence[side] = _pixels(pane, "A" if pane.target.asset_id == ids["A"] else "B")
        assert all(cached < original for cached, original in zip(
            evidence[side]["actual_size"], original_evidence[side]["actual_size"]))
    _stage("verified_original_dimensions", pixels=original_evidence,
           actual_cached_dimensions={side: value["actual_size"] for side, value in evidence.items()},
           caches_strictly_smaller_than_originals=True, actual_pane_aspect_ratios_distinct=True)
    _capture(dialog, "verified-originals", True)
    _close_dialog(dialog)
    _view_preserved(before_drift, _snapshot(database, "after-read-only-originals"))
    dialog = _open(window, (ids["A"], ids["B"]))
    pane = next(pane for pane in dialog.panes.values() if pane.target.asset_id == ids["A"])
    revision = pane.target.revision
    with catalog.connect(database) as db:
        db.execute("UPDATE assets SET rating=4 WHERE asset_id=?", (ids["A"],))
    _snapshot(database, "after-declared-rating-edit")
    _load_original(dialog, pane)
    assert pane.result.status == "ready" and pane.result.metadata_drift and pane.result.observed_revision > revision
    assert pane.target.revision == revision
    reported_revision = pane.result.observed_revision
    # Replace fixture bytes outside the application, restoring exact bytes later.
    path = fixture["available"] / fixture["names"]["A"]
    saved, original_stat = path.read_bytes(), path.stat()
    path.chmod(0o644)
    path.write_bytes(saved + b"fictional explicit stale-content mutation")
    _load_original(dialog, pane)
    assert pane.result.status == "refused" and pane.displayed_result.mode == "original"
    assert "still showing previous" in pane.status.text()
    path.write_bytes(saved)
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    path.chmod(0o444)
    catalog_drift_refusals = []
    for column, replacement in (("current_path", str(path.with_name("fictional-relocated.png"))), ("source_id", None)):
        with catalog.connect(database) as db:
            previous = db.execute("SELECT " + column + " FROM assets WHERE asset_id=?", (ids["A"],)).fetchone()[0]
            db.execute("UPDATE assets SET " + column + "=? WHERE asset_id=?", (replacement, ids["A"]))
        _load_original(dialog, pane)
        assert pane.result.status == "refused" and pane.target == captured[0 if captured[0].asset_id == ids["A"] else 1]
        catalog_drift_refusals.append({"field": column, "message": pane.status.text(), "captured_target_preserved": True})
        with catalog.connect(database) as db:
            db.execute("UPDATE assets SET " + column + "=? WHERE asset_id=?", (previous, ids["A"]))
    revision_snapshot = _snapshot(database, "after-declared-restored-catalog-drift")
    _stage("revision_and_content_drift", captured_revision=revision, metadata_drift_reported=True,
           reported_revision=reported_revision, content_refused=True, catalog_drift_refusals=catalog_drift_refusals,
           retained_previous_label=pane.status.text(), originals_restored=True,
           expected_catalog_delta="rating A=4; path/source restored exactly; revision advances for declared fixture writes")
    _close_dialog(dialog)
    _view_preserved(revision_snapshot, _snapshot(database, "after-read-only-drift-view"))
    parked = fixture["media"] / "unavailable-parked"
    fixture["unavailable"].rename(parked)
    source_id = fixture["source_ids"]["unavailable"]
    failed_scan = scan_sources(database, source_id=source_id, quiet_seconds=0)
    assert not failed_scan["complete"]
    offline = _snapshot(database, "after-explicit-failed-scan")
    scan_delta = _scan_delta(revision_snapshot, offline, source_id, "offline")
    _close_window(window)
    window = open_window()
    dialog = _open(window, (ids["A"], ids["C"]))
    unavailable = next(pane for pane in dialog.panes.values() if pane.target.asset_id == ids["C"])
    available = next(pane for pane in dialog.panes.values() if pane.target.asset_id == ids["A"])
    assert unavailable.result.status == "ready" and not unavailable.original_button.isEnabled()
    active_worker = dialog.worker
    clicks = []
    unavailable.original_button.clicked.connect(lambda: clicks.append(True))
    native._key(dialog, unavailable.canvas, Qt.Key.Key_F)
    QTest.keyClick(unavailable.original_button, Qt.Key.Key_Space)
    app.processEvents()
    assert not clicks and dialog.worker is active_worker and not dialog.request(unavailable.side, "original")
    _load_original(dialog, available)
    assert available.result.status == "ready" and available.result.mode == "original"
    _capture(dialog, "mixed-offline", True)
    _stage("offline_reopen_mixed", failed_scan=failed_scan, scan_delta=scan_delta,
           disabled_original_key_event=True, clicked_count=0, disabled_original_no_new_worker=True,
           original_cannot_be_successfully_read=True, native_attempted_original_io_instrumentation=False,
           cache_success_while_captured_path_absent=True)
    _close_dialog(dialog)
    parked.rename(fixture["unavailable"])
    assert next(row["health"] for row in list_sources(database) if row["source_id"] == source_id) == "offline"
    _view_preserved(offline, _snapshot(database, "restored-root-before-rescan"))
    rescanned = scan_sources(database, source_id=source_id, quiet_seconds=0)
    assert rescanned["complete"]
    restored = _snapshot(database, "after-explicit-restoration-rescan")
    restoration_delta = _scan_delta(offline, restored, source_id, "paused")
    window.model.refresh()
    _stage("restore_requires_rescan", implicit_health_update=False, result=rescanned, scan_delta=restoration_delta)
    # A real cache refusal does not repair the published derivative.
    png = fixture["cache_paths"]["D"]
    corrupt_before, corrupt_stat = png.read_bytes(), png.stat()
    png.write_bytes(b"fictional corrupt cache, not a PNG")
    corrupted = _sha(png)
    dialog = _open(window, (ids["A"], ids["D"]))
    failed = next(pane for pane in dialog.panes.values() if pane.target.asset_id == ids["D"])
    healthy = next(pane for pane in dialog.panes.values() if pane.target.asset_id == ids["A"])
    assert failed.result.status == "refused" and healthy.result.status == "ready" and _sha(png) == corrupted
    native._key(dialog, healthy.canvas, Qt.Key.Key_Plus)
    _capture(dialog, "isolated-cache-failure")
    _stage("cache_failure_isolated", error=failed.status.text(), healthy_id_private=healthy.target.asset_id,
           corrupt_cache_not_repaired=True)
    _close_dialog(dialog)
    png.write_bytes(corrupt_before)
    os.utime(png, ns=(corrupt_stat.st_atime_ns, corrupt_stat.st_mtime_ns))
    # Start a real cache load then immediately close: no injected helper/timing.
    dialog = _open(window, (ids["A"], ids["B"]))
    native._key(dialog, dialog.panes["left"].cache_button, Qt.Key.Key_Space)
    native._key(dialog, dialog.close_button, Qt.Key.Key_Space)
    native._wait(lambda: not dialog.isVisible(), 8)
    _close_dialog(dialog)
    dialog = _open(window, (ids["A"], ids["B"]))
    _close_dialog(dialog)
    cleanup = _close_window(window)
    _WINDOW = None
    final = _snapshot(database, "final-after-all-worker-cleanup")
    _view_preserved(restored, final)
    assert _manifest(fixture["media"]) == originals and _manifest(cache) == cached
    assert {name: _sha(repository / name) for name in SOURCE_FILES} == source_hashes
    assert os.environ.get("XDG_RUNTIME_DIR") == runtime
    assert not any(fixture["scratch"].iterdir())
    _RECEIPT.update(host_private=host, cleanup=cleanup, source_hashes_preserved=True,
                    source_and_cache_manifest_preserved=True, helper_external_action_invocations=0,
                    external_evidence_scope="helper action ledger invokes no external-open controls; no global process/dispatch spy",
                    status="passed", complete=True, native_executed=True)
    shutil.rmtree(_ROOT)
    _RECEIPT["fixture_cleanup_complete"] = not _ROOT.exists()
    _stage("complete", fixture_removed=True)
    return {"status": "passed", "complete": True, "stages": len(_RECEIPT["stages"]), "captures": len(_RECEIPT["captures"])}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-helper-sha", required=True)
    parser.add_argument("--focused-log", required=True, type=Path)
    parser.add_argument("--expected-focused-log-sha", required=True)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(_run(args)))
        return 0
    except Exception as exc:
        if _RECEIPT is not None:
            _RECEIPT.update(status="failed", complete=False, error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            try:
                if _WINDOW is not None:
                    _RECEIPT["failure_cleanup"] = _close_window(_WINDOW)
            except Exception as cleanup:
                _RECEIPT["failure_cleanup_error"] = f"{type(cleanup).__name__}: {cleanup}"
            try:
                database = _ROOT / "fixture" / "fictional-library.sqlite3" if _ROOT else None
                if database is not None and database.exists():
                    _snapshot(database, "failure-retained")
            except Exception as snapshot:
                _RECEIPT["failure_snapshot_error"] = f"{type(snapshot).__name__}: {snapshot}"
            _RECEIPT["failed_fixture_retained"] = bool(_ROOT and _ROOT.exists())
            native._write(_PATH, _RECEIPT)
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
