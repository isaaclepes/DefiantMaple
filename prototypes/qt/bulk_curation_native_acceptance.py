"""Generated-fixture bulk ratings/favorites native acceptance probe.

Root runs this helper visibly on the authorized desktop session. It creates a
new v5 catalog and generated media under an empty output directory outside the
checkout, then exercises v5->v6 preservation and bounded Qt interaction. It
never opens or changes user-library files.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import closing
import atexit
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

from PIL import Image, ImageDraw
from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QEventLoop, QItemSelectionModel, Qt, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, curation
from prototypes.qt.app import GalleryWindow
from prototypes.qt.identity import APP_ID


ASSET_IDS = {name: f"fictional-asset-{name}" for name in ("alpha", "beta", "delta", "gamma")}
SOURCE_FILES = (
    "defiantmaple/catalog.py",
    "defiantmaple/curation.py",
    "prototypes/qt/app.py",
    "prototypes/qt/identity.py",
    "prototypes/qt/bulk_curation_native_acceptance.py",
    "tests/test_curation.py",
    "tests/test_bulk_curation.py",
    "prototypes/qt/tests/test_curation_ui.py",
    "prototypes/qt/tests/test_bulk_curation_ui.py",
    "prototypes/qt/tests/test_gallery_workflow.py",
)
_PARTIAL: dict | None = None
_PARTIAL_PATH: Path | None = None
_APP: QApplication | None = None
_WINDOW: GalleryWindow | None = None
_KEY_ACTIONS: list[dict] = []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _flush(error: BaseException | None = None) -> None:
    if _PARTIAL is None or _PARTIAL_PATH is None:
        return
    _PARTIAL["keyboard_actions"] = list(_KEY_ACTIONS)
    if error is not None:
        _PARTIAL["status"] = "failed"
        _PARTIAL["complete"] = False
        _PARTIAL["exception"] = {"type": type(error).__name__, "message": str(error)}
        _PARTIAL["traceback"] = traceback.format_exc()
    _write_json(_PARTIAL_PATH, _PARTIAL)


def _checkpoint(stage: str, **fields) -> None:
    assert _PARTIAL is not None
    _PARTIAL["stages"].append({"stage": stage, **fields})
    _PARTIAL["last_stage"] = stage
    _flush()


def _wait(app: QApplication, predicate, timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    return bool(predicate())


def _focus_report(app: QApplication, widget) -> dict:
    focus = app.focusWidget()
    active = app.activeWindow()
    handle = widget.windowHandle() if widget is not None else None
    return {
        "widget_class": type(widget).__name__ if widget is not None else None,
        "widget_visible": bool(widget is not None and widget.isVisible()),
        "widget_active": bool(widget is not None and widget.isActiveWindow()),
        "widget_exposed": bool(handle is not None and handle.isExposed()),
        "active_window_class": type(active).__name__ if active is not None else None,
        "focus_widget_class": type(focus).__name__ if focus is not None else None,
        "focus_widget_name": focus.objectName() if focus is not None else None,
        "focus_widget_accessible_name": focus.accessibleName() if focus is not None else None,
        "focus_inside_widget": bool(widget is not None and focus is not None and
                                     (focus is widget or widget.isAncestorOf(focus))),
    }


def _activate(app: QApplication, widget, timeout: float = 4.0) -> bool:
    widget.raise_()
    widget.activateWindow()
    handle = widget.windowHandle()
    if handle is not None:
        handle.requestActivate()
    return _wait(app, lambda: widget.isVisible() and widget.isActiveWindow() and
                 handle is not None and handle.isExposed() and
                 _focus_report(app, widget)["focus_inside_widget"], timeout)


def _key(app: QApplication, top, widget, key, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    """Inject only into the real focused widget of an active, exposed native window."""
    widget.setFocus()
    def ready():
        focus = app.focusWidget()
        report = _focus_report(app, top)
        return (report["widget_visible"] and report["widget_active"] and report["widget_exposed"] and
                report["focus_inside_widget"] and widget.isVisible() and widget.isEnabled() and
                focus is not None and (focus is widget or widget.isAncestorOf(focus)))
    if not _wait(app, ready, 2.0):
        raise RuntimeError(f"Keyboard target failed active/exposed/focus guard: {widget.objectName() or widget.accessibleName()}")
    focus = app.focusWidget()
    _KEY_ACTIONS.append({"window": top.windowTitle(), "target": widget.objectName() or widget.accessibleName() or type(widget).__name__,
                         "key": key.name, "modifiers": modifier.name, "focus": _focus_report(app, top)})
    QTest.keyClick(focus, key, modifier)
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)


def _tab_to(app: QApplication, top, target, *, maximum_steps=8) -> None:
    steps = 0
    while app.focusWidget() is not target and steps < maximum_steps:
        focus = app.focusWidget()
        if focus is None:
            raise RuntimeError("Tab traversal lost the focused widget")
        _key(app, top, focus, Qt.Key.Key_Tab)
        steps += 1
    if app.focusWidget() is not target:
        raise AssertionError(f"Bounded keyboard Tab traversal did not reach {target.objectName()}")


def _close_window(app: QApplication, window: GalleryWindow) -> dict:
    close_accepted = bool(window.close())
    hidden = _wait(app, lambda: not window.isVisible(), 2.0)
    try:
        window.model._db.execute("SELECT 1")
    except sqlite3.ProgrammingError as exc:
        model_closed = "closed" in str(exc).casefold()
    else:
        model_closed = False
    result = {"close_accepted": close_accepted, "window_hidden": hidden,
              "model_connection_closed": model_closed}
    if not all(result.values()):
        raise AssertionError(f"Gallery cleanup was incomplete: {result}")
    return result


def _draw(path: Path, color: str) -> None:
    image = Image.new("RGB", (96, 72), "#f5f1e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 8, 86, 64), fill=color)
    draw.ellipse((32, 20, 64, 52), fill="#f2c14e")
    image.save(path, format="PNG")
    image.close()


_OLD_TABLES = (
    "sources", "assets", "provenance", "source_entries", "tags", "tag_aliases",
    "entities", "entity_aliases", "asset_tags", "asset_entities", "collections",
    "collection_members", "curation_edits",
)
_OLD_COLUMNS = {
    "sources": "source_id,name,root_path,recursive,existing_file_policy,enabled,health,health_detail,initial_scan_completed,created_at,last_scan_at",
    "assets": "asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at,rating,favorite,revision",
    "provenance": "provenance_id,asset_id,source_kind,details_json,recorded_at",
    "source_entries": "current_path,source_id,byte_size,modified_ns,device,inode,stable_since_ns,observed_at_ns,preexisting,disposition,asset_id,last_error",
    "tags": "tag_id,name,normalized_name,parent_id",
    "tag_aliases": "normalized_alias,tag_id,alias",
    "entities": "entity_id,entity_type,name,normalized_name",
    "entity_aliases": "entity_type,normalized_alias,entity_id,alias",
    "asset_tags": "asset_id,tag_id",
    "asset_entities": "asset_id,entity_id",
    "collections": "collection_id,name,normalized_name",
    "collection_members": "collection_id,asset_id,position",
    "curation_edits": "edit_id,asset_id,before_rating,before_favorite,after_rating,after_favorite,expected_revision,undone,recorded_at",
}


def _legacy_snapshot(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as db:
        values = {}
        for table in _OLD_TABLES:
            rows = db.execute(f'SELECT {_OLD_COLUMNS[table]} FROM "{table}"').fetchall()
            values[table] = sorted((list(row) for row in rows),
                                   key=lambda row: json.dumps(row, sort_keys=True, default=str))
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return {"sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "row_counts": {name: len(rows) for name, rows in values.items()},
            "collection_member_order": [row[1] for row in sorted(
                values["collection_members"], key=lambda row: (row[2], row[1]))],
            "rows": values}


def _catalog_snapshot_digest(database: Path) -> str:
    with closing(sqlite3.connect(database)) as db:
        data = "\n".join(db.iterdump())
    return hashlib.sha256(data.encode()).hexdigest()


def _seed_v5(database: Path, root: Path, sources: dict[str, Path]) -> None:
    """Create genuine v5 tables and rows, then append the v5 curation schema."""
    with closing(sqlite3.connect(database)) as db:
        db.executescript(catalog.SCHEMA_V4)
        db.execute(
            "INSERT INTO sources(source_id,name,root_path,recursive,existing_file_policy,"
            "enabled,health,health_detail,initial_scan_completed,created_at,last_scan_at) "
            "VALUES('fixture-source','Generated bulk source',?,1,'inbox',1,'paused',NULL,1,?,?)",
            (str(root.resolve()), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))
        for name, path in sources.items():
            info = path.stat()
            digest = _sha256(path)
            asset_id = ASSET_IDS[name]
            db.execute(
                "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
                "workflow_state,source_id,discovered_at) VALUES(?,?, 'image/png', ?, ?, ?, ?, ?)",
                (asset_id, str(path.resolve()), digest, info.st_size,
                 "reviewed" if name in ("beta", "gamma") else "new", "fixture-source",
                 f"2026-01-01T00:00:{('0'+str(list(sources).index(name))) [-2:]}Z"))
            db.execute(
                "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json,recorded_at) "
                "VALUES(?,?, 'generated_fixture', ?, '2026-01-01T00:00:00Z')",
                (f"fixture-provenance-{name}", asset_id,
                 json.dumps({"fixture": True, "role": name}, sort_keys=True)))
            db.execute(
                "INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id,last_error) "
                "VALUES(?,?,?,?,?,?,?,?,1,'indexed',?,NULL)",
                (str(path.resolve()), "fixture-source", info.st_size, info.st_mtime_ns,
                 str(info.st_dev), str(info.st_ino), info.st_mtime_ns, info.st_mtime_ns, asset_id))
        db.execute("INSERT INTO tags VALUES('fixture-tag-parent','Generated','generated',NULL)")
        db.execute("INSERT INTO tags VALUES('fixture-tag-child','Color study','color-study','fixture-tag-parent')")
        db.execute("INSERT INTO tag_aliases VALUES('fixture-tag-alias','fixture-tag-child','Color Study')")
        db.execute("INSERT INTO entities VALUES('fixture-entity','Project','Generated set','generated-set')")
        db.execute("INSERT INTO entity_aliases VALUES('Project','fixture-entity-alias','fixture-entity','Generated Set')")
        for asset_id in ASSET_IDS.values():
            db.execute("INSERT INTO asset_tags VALUES(?, 'fixture-tag-child')", (asset_id,))
            db.execute("INSERT INTO asset_entities VALUES(?, 'fixture-entity')", (asset_id,))
        db.execute("INSERT INTO collections VALUES('fixture-collection','Ordered generated set','ordered-generated-set')")
        for pos, name in enumerate(("gamma", "alpha", "delta", "beta"), start=7):
            db.execute("INSERT INTO collection_members VALUES('fixture-collection',?,?)",
                       (ASSET_IDS[name], pos))
        db.executescript(catalog.CURATION_SCHEMA)
        db.execute("UPDATE assets SET rating=3,favorite=1 WHERE asset_id=?", (ASSET_IDS["beta"],))
        db.execute("INSERT INTO curation_edits(edit_id,asset_id,before_rating,before_favorite,"
                   "after_rating,after_favorite,expected_revision,undone,recorded_at) "
                   "VALUES('fixture-legacy-single-beta',?,NULL,0,3,1,1,0,'2026-01-01T00:01:00Z')",
                   (ASSET_IDS["beta"],))
        db.commit()


def _manifest(paths: dict[str, Path]) -> dict:
    return {name: {"sha256": _sha256(path), "bytes": path.stat().st_size,
                   "mtime_ns": path.stat().st_mtime_ns}
            for name, path in sorted(paths.items())}


def _integrity(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as db:
        return {"integrity_check": db.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_violations": [list(row) for row in db.execute("PRAGMA foreign_key_check")],
                "schema_version": db.execute("PRAGMA user_version").fetchone()[0]}


def _state(database: Path, name: str) -> dict:
    return curation.get_curation(database, ASSET_IDS[name])


def _selected_ids(window: GalleryWindow) -> list[str]:
    return [window.model.asset_at(index.row())["asset_id"]
            for index in sorted(window.gallery.selectionModel().selectedIndexes(), key=lambda i: i.row())]


def _select_ids_programmatically(window: GalleryWindow, names: tuple[str, ...]) -> None:
    selection = window.gallery.selectionModel()
    selection.clear()
    for name in names:
        row = window.model.row_for_asset(ASSET_IDS[name])
        if row is None:
            raise AssertionError(f"Generated asset {name} is not visible")
        selection.select(window.model.index(row, 0), QItemSelectionModel.SelectionFlag.Select)
    first = window.model.row_for_asset(ASSET_IDS[names[0]])
    selection.setCurrentIndex(window.model.index(first, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
    QApplication.processEvents()


def _host(app: QApplication, window: GalleryWindow) -> dict:
    screens = []
    for screen in QGuiApplication.screens():
        geometry = screen.geometry()
        screens.append({"name": screen.name(), "geometry_px": [geometry.x(), geometry.y(),
                        geometry.width(), geometry.height()], "device_pixel_ratio": screen.devicePixelRatio(),
                        "logical_dpi": [screen.logicalDotsPerInchX(), screen.logicalDotsPerInchY()]})
    release = {}
    try:
        release = dict(platform.freedesktop_os_release())
    except (AttributeError, OSError):
        pass
    return {"platform": platform.platform(), "os_release": release,
            "machine": platform.machine(), "python": platform.python_version(),
            "python_executable": sys.executable, "pyside6": PYSIDE_VERSION, "qt": qVersion(),
            "qt_platform_plugin": app.platformName(), "session_type": os.environ.get("XDG_SESSION_TYPE"),
            "wayland_display_set": bool(os.environ.get("WAYLAND_DISPLAY")),
            "logical_cpu_count": os.cpu_count(), "screens": screens,
            "application_id": APP_ID, "source_run": True,
            "window_device_pixel_ratio": window.devicePixelRatio()}


def _preflight_generated_api(database: Path, output: Path) -> dict:
    """Exercise refusal/rollback edges against a disposable copy of the fixture."""
    primary_before = _catalog_snapshot_digest(database)
    trial = output / "generated-atomicity-trial.sqlite3"
    shutil.copy2(database, trial)
    alpha, beta = ASSET_IDS["alpha"], ASSET_IDS["beta"]
    before = {"alpha": curation.get_curation(trial, alpha),
              "beta": curation.get_curation(trial, beta)}
    trial_initial = _catalog_snapshot_digest(trial)
    capture = curation.capture_curation(trial, (alpha, beta))
    plan = curation.preview_curation_batch(trial, capture,
              curation.CurationChanges(rating=5, favorite=True))
    with closing(sqlite3.connect(trial)) as db:
        db.execute("CREATE TRIGGER fail_bulk_member BEFORE INSERT ON curation_batch_items "
                   "WHEN NEW.position=1 BEGIN SELECT RAISE(ABORT,'generated fault injection'); END")
        db.commit()
    try:
        curation.apply_curation_batch(trial, plan)
    except ValueError as exc:
        apply_refusal = str(exc)
    else:
        raise AssertionError("Injected group-member failure did not abort batch apply")
    with closing(sqlite3.connect(trial)) as db:
        db.execute("DROP TRIGGER fail_bulk_member")
        db.commit()
        batch_count = db.execute("SELECT COUNT(*) FROM curation_batches").fetchone()[0]
    after_fault = {"alpha": curation.get_curation(trial, alpha),
                   "beta": curation.get_curation(trial, beta)}
    if before != after_fault or batch_count or _catalog_snapshot_digest(trial) != trial_initial:
        raise AssertionError("Apply fault left a partial member update or journal")

    batch_result = curation.apply_curation_batch(trial, plan)
    if not batch_result["changed"]:
        raise AssertionError("Fault-recovery trial failed to apply its valid batch")
    with closing(sqlite3.connect(trial)) as db:
        db.execute("CREATE TRIGGER fail_batch_undo BEFORE UPDATE OF undone ON curation_batches "
                   "WHEN NEW.undone=1 BEGIN SELECT RAISE(ABORT,'generated undo fault'); END")
        db.commit()
    post_apply = {"alpha": curation.get_curation(trial, alpha),
                  "beta": curation.get_curation(trial, beta)}
    # The injected trigger is excluded from the logical rollback comparison.
    with closing(sqlite3.connect(trial)) as db:
        db.execute("DROP TRIGGER fail_batch_undo")
        db.commit()
    trial_applied = _catalog_snapshot_digest(trial)
    with closing(sqlite3.connect(trial)) as db:
        db.execute("CREATE TRIGGER fail_batch_undo BEFORE UPDATE OF undone ON curation_batches "
                   "WHEN NEW.undone=1 BEGIN SELECT RAISE(ABORT,'generated undo fault'); END")
        db.commit()
    try:
        curation.undo_curation_batch(trial, batch_result["batch_id"])
    except ValueError as exc:
        undo_refusal = str(exc)
    else:
        raise AssertionError("Injected group-header failure did not abort undo")
    with closing(sqlite3.connect(trial)) as db:
        db.execute("DROP TRIGGER fail_batch_undo")
        db.commit()
    after_undo_fault = {"alpha": curation.get_curation(trial, alpha),
                        "beta": curation.get_curation(trial, beta)}
    if (post_apply != after_undo_fault or _catalog_snapshot_digest(trial) != trial_applied or
            not curation.get_curation_batch(trial, batch_result["batch_id"])["eligible"]):
        raise AssertionError("Undo fault partially restored members or consumed group eligibility")
    undone = curation.undo_curation_batch(trial, batch_result["batch_id"])
    after_valid_undo = {"alpha": curation.get_curation(trial, alpha),
                        "beta": curation.get_curation(trial, beta)}
    if (any((after_valid_undo[name]["rating"], after_valid_undo[name]["favorite"]) !=
            (before[name]["rating"], before[name]["favorite"]) for name in ("alpha", "beta")) or
            any(after_valid_undo[name]["revision"] <= before[name]["revision"]
                for name in ("alpha", "beta")) or not undone["changed"]):
        raise AssertionError("Valid group undo did not restore both generated members")
    trial_integrity = _integrity(trial)
    if trial_integrity["integrity_check"] != "ok" or trial_integrity["foreign_key_violations"]:
        raise AssertionError("Fault-injection trial catalog failed its final integrity checks")
    for invalid in ((), (curation.CapturedTarget(alpha, 0), curation.CapturedTarget(alpha, 0)),
                    tuple(curation.CapturedTarget(f"id-{n}", 0) for n in range(257))):
        try:
            curation.preview_curation_batch(trial, invalid, curation.CurationChanges())
        except ValueError:
            continue
        raise AssertionError("Empty, duplicate, or over-limit batch input was accepted")
    trial.unlink(missing_ok=True)
    if _catalog_snapshot_digest(database) != primary_before:
        raise AssertionError("Fault-injection trial mutated the primary generated catalog")
    return {"apply_atomic_fault_rollback": True, "apply_failure": apply_refusal,
            "undo_atomic_fault_rollback": True, "undo_failure": undo_refusal,
            "successful_group_undo": True, "invalid_target_sets_refused": 3,
            "trial_final_integrity": trial_integrity, "primary_catalog_unchanged": True,
            "successful_trial_removed": not trial.exists(), "full_catalog_rollback_verified": True}


def _run(output: Path) -> dict:
    global _PARTIAL, _PARTIAL_PATH, _APP, _WINDOW
    output = output.expanduser().resolve(strict=False)
    repo = Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents:
        raise ValueError("Evidence output must be outside the source checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence output must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    runtime_directory_before = os.environ.get("XDG_RUNTIME_DIR")
    for kind in ("config", "data", "cache"):
        root = output / "xdg" / kind
        root.mkdir(parents=True, exist_ok=True)
        os.environ[{"config": "XDG_CONFIG_HOME", "data": "XDG_DATA_HOME",
                    "cache": "XDG_CACHE_HOME"}[kind]] = str(root)
    _PARTIAL_PATH = output / "bulk-curation-native-partial.json"
    _PARTIAL = {"schema": "defiantmaple.bulk-curation-native-partial.v1",
                "status": "in_progress", "stages": []}
    atexit.register(_flush)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    source_before = {name: _sha256(repo / name) for name in SOURCE_FILES}
    _checkpoint("provenance_start", base_commit="6f850c3fa65097a48406b50a19bab8a859bb756c",
                checked_out_head=head, source_file_digests=source_before,
                working_tree_dirty=bool(subprocess.run(
                    ["git", "status", "--porcelain"], cwd=repo, check=True,
                    capture_output=True, text=True).stdout.strip()))

    source_root = output / "generated-source"
    source_root.mkdir()
    sources = {name: source_root / f"fictional-{name}.png" for name in ASSET_IDS}
    for name, color in (("alpha", "#267a9b"), ("beta", "#9b4967"),
                        ("delta", "#8041a0"), ("gamma", "#588157")):
        _draw(sources[name], color)
    source_before = _manifest(sources)
    database = output / "generated-catalog-v5.sqlite3"
    _seed_v5(database, source_root, sources)
    old_version = _integrity(database)["schema_version"]
    legacy_before = _legacy_snapshot(database)
    migration = catalog.initialize(database, create=False)
    backup = Path(migration["backup_path"])
    backup_snapshot = _legacy_snapshot(backup)
    migrated_snapshot = _legacy_snapshot(database)
    backup_integrity = _integrity(backup)
    migrated_integrity = _integrity(database)
    if (old_version != 5 or migrated_integrity["schema_version"] != 6 or
            not migration.get("migrated") or legacy_before["sha256"] != backup_snapshot["sha256"] or
            legacy_before["sha256"] != migrated_snapshot["sha256"] or
            backup_integrity["integrity_check"] != "ok" or backup_integrity["foreign_key_violations"] or
            migrated_integrity["integrity_check"] != "ok" or migrated_integrity["foreign_key_violations"]):
        raise AssertionError("Generated v5-to-v6 migration failed backup or legacy-row preservation")
    _checkpoint("v5_to_v6_verified_backup", old_schema=old_version,
                new_schema=migrated_integrity["schema_version"],
                backup_sha256=_sha256(backup), backup_integrity=backup_integrity,
                migrated_integrity=migrated_integrity,
                legacy_snapshot_sha256=legacy_before["sha256"],
                preserved_row_counts=legacy_before["row_counts"],
                preserved_collection_order=legacy_before["collection_member_order"])

    fault_checks = _preflight_generated_api(database, output)
    if _legacy_snapshot(database) != migrated_snapshot or _manifest(sources) != source_before:
        raise AssertionError("Disposable fault trial changed the primary catalog or generated source fixtures")
    _checkpoint("atomic_rollback_and_bound_checks", result=fault_checks)

    _APP = QApplication.instance() or QApplication([])
    if _APP.platformName() in ("offscreen", "minimal"):
        raise RuntimeError("Native acceptance requires a desktop Qt platform, not offscreen/minimal")
    _WINDOW = GalleryWindow(database, enable_thumbnails=False,
                            cache_root=output / "thumbnail-cache",
                            private_root=output / "private-state")
    window = _WINDOW
    window.show()
    if not _wait(_APP, lambda: window.isVisible() and window.windowHandle() and
                 window.windowHandle().isExposed()):
        raise TimeoutError("Generated gallery did not become exposed")
    gallery_activation = _activate(_APP, window)
    _checkpoint("gallery_activation_gate", passed=gallery_activation,
                focus=_focus_report(_APP, window))
    if not gallery_activation:
        raise RuntimeError("Visible gallery failed the active/exposed/focused-descendant gate")
    host_receipt = _host(_APP, window)
    _checkpoint("visible_native_host", host=host_receipt)

    alpha_row = window.model.row_for_asset(ASSET_IDS["alpha"])
    if alpha_row is None:
        raise AssertionError("Generated alpha is not visible in the native gallery")
    window.gallery.setFocus()
    if not _wait(_APP, lambda: _APP.focusWidget() is window.gallery, 2.0):
        raise RuntimeError("Gallery did not receive focus for generated-card selection")
    rect = window.gallery.visualRect(window.model.index(alpha_row, 0))
    beta_row = window.model.row_for_asset(ASSET_IDS["beta"])
    beta_rect = window.gallery.visualRect(window.model.index(beta_row, 0)) if beta_row is not None else None
    if not rect.isValid() or beta_rect is None or beta_rect.center().x() <= rect.center().x() or beta_rect.center().y() != rect.center().y():
        raise AssertionError("Generated alpha/beta are not adjacent left-to-right IconMode targets for the declared keyboard sequence")
    QTest.mouseClick(window.gallery.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    _key(_APP, window, window.gallery, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    _key(_APP, window, window.gallery, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    keyboard_selected = _selected_ids(window)
    if keyboard_selected != [ASSET_IDS["alpha"], ASSET_IDS["beta"]]:
        raise AssertionError(f"Ctrl+Right/Ctrl+Space multi-selection did not capture expected generated pair: {keyboard_selected}")
    _key(_APP, window, window.bulk_curation_button, Qt.Key.Key_Space)
    dialog = window.bulk_curation_dialog
    if dialog is None or tuple(target.asset_id for target in dialog.targets) != tuple(keyboard_selected):
        raise AssertionError("Bulk dialog did not capture the selected displayed asset identities")
    dialog_activation = _activate(_APP, dialog)
    _checkpoint("multi_selection_and_dialog_gate", passed=dialog_activation,
                selected_count=len(keyboard_selected), captured_count=len(dialog.targets),
                selection_keyboard="initial click on alpha, Ctrl+Right to beta, Ctrl+Space to toggle beta",
                dialog_focus=_focus_report(_APP, dialog))
    if not dialog_activation:
        raise RuntimeError("Bulk dialog failed the active/exposed/focused-descendant gate")

    captured_targets = [{"asset_id": target.asset_id, "revision": target.revision}
                        for target in dialog.targets]
    # A filter model reset clears the gallery selection; the open operation must retain
    # its original IDs and revisions and cannot be redirected by that change.
    window.model.set_curation_filters(rating=curation.RatingFilter(curation.RatingMode.EXACT, 5),
                                      favorite=curation.FavoriteFilter.FAVORITES)
    QApplication.processEvents()
    if _selected_ids(window) or [{"asset_id": t.asset_id, "revision": t.revision}
                                 for t in dialog.targets] != captured_targets:
        raise AssertionError("Filter/model reset redirected or failed to clear selection independently of captured targets")
    selection_drift = {"selection_cleared_after_filter_reset": True,
                       "dialog_targets_unchanged": True, "captured_targets": captured_targets}

    groups_before = len(curation.list_curation_batches(database))
    revisions_before = {name: _state(database, name)["revision"] for name in ASSET_IDS}
    _key(_APP, dialog, dialog.preview_button, Qt.Key.Key_Space)
    no_op_preview = {"changed_count": dialog.plan.changed_count if dialog.plan else None,
                     "apply_enabled": dialog.apply_button.isEnabled(),
                     "visible_text": dialog.effects.toPlainText()}
    if not dialog.plan or dialog.plan.changed_count != 0:
        raise AssertionError("Keep/Keep did not preview as a no-op")
    _key(_APP, dialog, dialog.favorite_box, Qt.Key.Key_Down)
    if dialog.favorite_box.currentData() is not True:
        raise AssertionError("No-op invalidation did not actually change Keep to Favorite by keyboard")
    _key(_APP, dialog, dialog.favorite_box, Qt.Key.Key_Home)
    if dialog.favorite_box.currentData() is not curation.KEEP:
        raise AssertionError("No-op invalidation did not restore Keep by keyboard")
    if dialog.apply_button.isEnabled() or dialog.plan is not None:
        raise AssertionError("Changing controls did not invalidate the no-op preview")
    _key(_APP, dialog, dialog.preview_button, Qt.Key.Key_Space)
    _key(_APP, dialog, dialog.apply_button, Qt.Key.Key_Space)
    no_op_result = {"feedback": dialog.feedback.text(),
                    "groups_after": len(curation.list_curation_batches(database)),
                    "revisions_after": {name: _state(database, name)["revision"] for name in ASSET_IDS}}
    if (no_op_result["groups_after"] != groups_before or
            no_op_result["revisions_after"] != revisions_before or
            "No changes" not in no_op_result["feedback"]):
        raise AssertionError("All-no-op operation created a group or advanced any revision")

    _key(_APP, dialog, dialog.favorite_box, Qt.Key.Key_Down)
    if dialog.favorite_box.currentData() is not True:
        raise AssertionError("Keyboard did not select the favorite choice")
    if dialog.apply_button.isEnabled():
        raise AssertionError("Changing bulk controls left Apply enabled for the previous preview")
    _key(_APP, dialog, dialog.preview_button, Qt.Key.Key_Space)
    preview = dialog.plan
    if preview is None or preview.changed_count != 1:
        raise AssertionError("Expected one changed and one unchanged preview member")
    alpha_before_stale = curation.get_curation(database, ASSET_IDS["alpha"])
    curation.set_curation(database, ASSET_IDS["alpha"], rating=2, favorite=False,
                          expected_revision=alpha_before_stale["revision"])
    before_stale_apply = {name: _state(database, name) for name in ("alpha", "beta")}
    group_count_before_stale_apply = len(curation.list_curation_batches(database))
    _key(_APP, dialog, dialog.apply_button, Qt.Key.Key_Space)
    stale_apply = {"feedback": dialog.feedback.text(),
                   "alpha": _state(database, "alpha"), "beta": _state(database, "beta"),
                   "group_count": len(curation.list_curation_batches(database)),
                   "preview_invalidated": dialog.plan is None and not dialog.apply_button.isEnabled()}
    if (not stale_apply["preview_invalidated"] or
            stale_apply["group_count"] != group_count_before_stale_apply or
            stale_apply["alpha"] != before_stale_apply["alpha"] or
            stale_apply["beta"] != before_stale_apply["beta"]):
        raise AssertionError("Stale one-member apply was not refused atomically")
    _key(_APP, dialog, dialog.reload_button, Qt.Key.Key_Space)
    same_id_reload = [{"asset_id": item.asset_id, "revision": item.revision} for item in dialog.targets]
    if [item["asset_id"] for item in same_id_reload] != [item["asset_id"] for item in captured_targets] or \
            same_id_reload[0]["revision"] <= captured_targets[0]["revision"] or dialog.apply_button.isEnabled():
        raise AssertionError("Reload changed target identities or failed to invalidate the previous preview")
    _key(_APP, dialog, dialog.preview_button, Qt.Key.Key_Space)
    if not dialog.plan or dialog.plan.changed_count != 1:
        raise AssertionError("Repreview after same-ID reload did not show one changed/one unchanged member")
    if not dialog.grab().save(str(output / "generated-bulk-preview-dialog.png")):
        raise RuntimeError("Could not save app-only generated bulk preview capture")
    _key(_APP, dialog, dialog.apply_button, Qt.Key.Key_Space)
    if "1 changed, 1 unchanged" not in dialog.feedback.text():
        raise AssertionError("Bulk apply did not report truthful changed/unchanged counts")
    first_batch_id = dialog.group_box.currentData()
    first_batch = curation.get_curation_batch(database, first_batch_id)
    after_first_apply = {name: _state(database, name) for name in ("alpha", "beta")}
    if (first_batch["target_count"], first_batch["changed_count"], first_batch["eligible"]) != (2, 1, True) or \
            (after_first_apply["alpha"]["rating"], after_first_apply["alpha"]["favorite"], after_first_apply["alpha"]["revision"]) != \
            (2, True, before_stale_apply["alpha"]["revision"] + 1) or \
            after_first_apply["beta"] != before_stale_apply["beta"]:
        raise AssertionError("Batch apply did not keep unchanged member revision and store one group")
    _checkpoint("bulk_preview_stale_noop_and_apply", selection_drift=selection_drift,
                no_op_preview=no_op_preview, no_op_result=no_op_result,
                stale_apply=stale_apply, same_id_reload=same_id_reload,
                batch_summary={"target_count": first_batch["target_count"],
                               "changed_count": first_batch["changed_count"],
                               "unchanged_count": first_batch["target_count"] - first_batch["changed_count"],
                               "eligible": first_batch["eligible"]})

    # Close and reopen the application before choosing this exact persisted group.
    dialog.close()
    first_cleanup = _close_window(_APP, window)
    _WINDOW = None
    _checkpoint("first_gallery_closed_before_reopen", cleanup=first_cleanup)
    window = GalleryWindow(database, enable_thumbnails=False,
                           cache_root=output / "thumbnail-cache", private_root=output / "private-state")
    _WINDOW = window
    window.show()
    if not _wait(_APP, lambda: window.isVisible() and window.windowHandle() and window.windowHandle().isExposed()):
        raise TimeoutError("Gallery did not reopen for durable group history")
    reopen_activation = _activate(_APP, window)
    _checkpoint("reopened_gallery_activation_gate", passed=reopen_activation, focus=_focus_report(_APP, window))
    if not reopen_activation:
        raise RuntimeError("Reopened gallery failed active/exposed/focus gate")
    _key(_APP, window, window.group_history_button, Qt.Key.Key_Space)
    history = window.bulk_curation_dialog
    if history is None or history.undo_batch_id != first_batch_id or not _activate(_APP, history):
        raise AssertionError("Reopened group history did not select the exact first batch")
    history_snapshot = curation.get_curation_batch(database, first_batch_id)
    _key(_APP, history, history.group_box, Qt.Key.Key_Home)
    if history.undo_batch_id is not None:
        raise AssertionError("History keyboard Home did not clear exact group choice")
    _key(_APP, history, history.group_box, Qt.Key.Key_End)
    if history.undo_batch_id != first_batch_id or _APP.focusWidget() is not history.group_box:
        raise AssertionError("History keyboard End did not choose exact persisted group with real combo focus")
    if not history.undo_button.isEnabled() or first_batch_id not in history.group_effects.toPlainText():
        raise AssertionError("Exact durable group effects or whole-group Undo was not presented")
    if not history.grab().save(str(output / "generated-bulk-group-history.png")):
        raise RuntimeError("Could not save app-only generated group history capture")
    _tab_to(_APP, history, history.undo_button)
    _key(_APP, history, history.undo_button, Qt.Key.Key_Space)
    after_group_undo = {name: _state(database, name) for name in ("alpha", "beta")}
    if (not curation.get_curation_batch(database, first_batch_id)["undone"] or
            after_group_undo["alpha"]["rating"] != 2 or after_group_undo["alpha"]["favorite"] or
            after_group_undo["alpha"]["revision"] != after_first_apply["alpha"]["revision"] + 1 or
            after_group_undo["beta"] != after_first_apply["beta"]):
        raise AssertionError("Whole-group undo after reopen did not restore all changed members only")

    # A second group includes beta unchanged. Its prior single edit remains an
    # explicit single-target action; undoing it advances beta's revision and
    # invalidates the entire group, leaving delta's changed value intact.
    history.close()
    if not _activate(_APP, window):
        raise RuntimeError("Gallery failed active/exposed/focus gate before second group")
    _select_ids_programmatically(window, ("beta", "delta"))
    _key(_APP, window, window.bulk_curation_button, Qt.Key.Key_Space)
    second = window.bulk_curation_dialog
    if second is None or {t.asset_id for t in second.targets} != {ASSET_IDS["beta"], ASSET_IDS["delta"]}:
        raise AssertionError("Second generated pair was not captured as expected")
    if not _activate(_APP, second):
        raise RuntimeError("Second bulk dialog failed active/exposed/focus gate")
    _key(_APP, second, second.favorite_box, Qt.Key.Key_Home)
    _key(_APP, second, second.favorite_box, Qt.Key.Key_Down)
    if second.favorite_box.currentData() is not True:
        raise AssertionError("Second bulk dialog keyboard favorite choice failed")
    _key(_APP, second, second.preview_button, Qt.Key.Key_Space)
    if second.plan is None or second.plan.changed_count != 1:
        raise AssertionError("Second group did not preview exactly one unchanged member")
    _key(_APP, second, second.apply_button, Qt.Key.Key_Space)
    second_batch_id = second.group_box.currentData()
    second_batch = curation.get_curation_batch(database, second_batch_id)
    if second_batch["changed_count"] != 1 or second_batch["target_count"] != 2:
        raise AssertionError("Second group history did not retain mixed changed/unchanged members")
    beta_before_single_undo = _state(database, "beta")
    delta_before_single_undo = _state(database, "delta")
    single_undo = curation.undo_curation(database, "fixture-legacy-single-beta")
    beta_after_single_undo = _state(database, "beta")
    delta_after_single_undo = _state(database, "delta")
    second_after_single_undo = curation.get_curation_batch(database, second_batch_id)
    second.refresh_history(second_batch_id)
    if (beta_before_single_undo["revision"] != beta_after_single_undo["revision"] - 1 or
            beta_after_single_undo["rating"] is not None or beta_after_single_undo["favorite"] or
            second_after_single_undo["eligible"] or second.undo_button.isEnabled() or
            delta_after_single_undo != delta_before_single_undo or delta_after_single_undo["favorite"] is not True):
        raise AssertionError("Explicit old single undo did not invalidate the whole group without partial group reversal")
    _checkpoint("reopen_group_undo_and_single_history_coexistence",
                exact_group_id_selected=True, group_effect_count=len(history_snapshot["members"]),
                first_group_undo_result={"undone": True, "unchanged_member_preserved": True},
                second_group_id=second_batch_id,
                single_edit_undo={"result": single_undo, "member_was_unchanged_in_group": True},
                group_ineligible_after_single_undo=not second_after_single_undo["eligible"],
                other_group_member_not_partially_reverted=delta_after_single_undo["favorite"] is True)

    second.close()
    final_cleanup = _close_window(_APP, window)
    _WINDOW = None
    if os.environ.get("XDG_RUNTIME_DIR") != runtime_directory_before:
        raise AssertionError("Acceptance helper changed the desktop runtime directory")
    source_after = _manifest(sources)
    if source_after != source_before:
        raise AssertionError("Generated source bytes changed during catalog-only bulk acceptance")
    final_integrity = _integrity(database)
    if final_integrity["integrity_check"] != "ok" or final_integrity["foreign_key_violations"]:
        raise AssertionError("Final generated catalog integrity/foreign key check failed")
    source_digests_after = {name: _sha256(repo / name) for name in SOURCE_FILES}
    if source_digests_after != _PARTIAL["stages"][0]["source_file_digests"]:
        raise AssertionError("Source code changed while the acceptance helper ran")
    _checkpoint("source_integrity_and_cleanup", source_manifest_before=source_before,
                source_manifest_after=source_after, fixture_bytes_unchanged=True,
                catalog_integrity=final_integrity, cleanup=final_cleanup,
                runtime_directory_preserved=True,
                source_file_digests_after=source_digests_after)

    result = {
        "schema": "defiantmaple.bulk-curation-native-acceptance.v1",
        "baseline_commit": "6f850c3fa65097a48406b50a19bab8a859bb756c",
        "checked_out_head": head,
        "source_file_digests": _PARTIAL["stages"][0]["source_file_digests"],
        "host": host_receipt,
        "fixture": {"source_count": 1, "asset_count": len(sources),
                    "fictional_names": sorted(sources), "source_byte_manifest_before": source_before,
                    "source_byte_manifest_after": source_after, "byte_manifests_equal": True},
        "migration": {"from_schema": old_version, "to_schema": 6,
                      "verified_backup_sha256": _sha256(backup),
                      "legacy_snapshot_sha256_before": legacy_before["sha256"],
                      "legacy_snapshot_sha256_backup": backup_snapshot["sha256"],
                      "legacy_snapshot_sha256_migrated": migrated_snapshot["sha256"],
                      "preserved_row_counts": legacy_before["row_counts"],
                      "collection_member_order": legacy_before["collection_member_order"],
                      "backup_integrity": backup_integrity,
                      "migrated_integrity_after_migration": migrated_integrity},
        "atomicity": fault_checks,
        "selection_and_preview": {"keyboard_multi_selection": "initial click alpha, Ctrl+Right to beta, Ctrl+Space toggles beta",
                                   "captured_targets": captured_targets,
                                   "filter_reset_drift": selection_drift,
                                   "no_op": no_op_result,
                                   "stale_apply_refusal": stale_apply,
                                   "same_id_reload": same_id_reload,
                                   "mixed_apply": {"target_count": 2, "changed_count": 1,
                                                   "unchanged_count": 1, "batch_id": first_batch_id}},
        "group_history": {"reopened_group_id": first_batch_id,
                          "effects_members": len(history_snapshot["members"]),
                          "whole_group_undo_after_reopen": True,
                          "single_history_coexistence": {"unchanged_beta_eligible_single_undo": True,
                              "single_undo_invalidated_second_group": True,
                              "delta_not_partially_reverted": True}},
        "integrity": final_integrity,
        "cleanup": {"before_reopen": first_cleanup, "final": final_cleanup},
        "captures": ["generated-bulk-preview-dialog.png", "generated-bulk-group-history.png"],
        "privacy": {"generated_media_only": True, "app_window_captures_only": True,
                    "whole_desktop_captured": False, "source_writes": False,
                    "temporary_root": str(output),
                    "runtime_directory_preserved": True,
                    "runtime_directory_set": bool(runtime_directory_before),
                    "isolated_xdg_roots": {name: str(output / "xdg" / name)
                                           for name in ("config", "data", "cache")}},
        "measurement_scope": {"thumbnail_workers_enabled": False,
                               "no_performance_budget_claim": True,
                               "native_keyboard_actions": _KEY_ACTIONS,
                               "focus_gate": "gallery and dialogs required visible, exposed, active, focused descendant",
                               "human_accessibility_or_cross_platform_qualification": False},
        "acceptance_boundary": "Generated-fixture metadata behavior only; broader FR/NFR/SEC requirements remain scoped as partial or deferred.",
    }
    result_path = output / "bulk-curation-native-acceptance.json"
    _write_json(result_path, result)
    _checkpoint("result_written", result_file=result_path.name, result_sha256=_sha256(result_path))
    _PARTIAL["status"] = "complete"
    _PARTIAL["result_file"] = "bulk-curation-native-acceptance.json"
    _PARTIAL["complete"] = True
    _flush()
    return result


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new or empty private evidence directory outside the checkout")
    args = parser.parse_args(argv)
    try:
        result = _run(args.output)
        print(json.dumps({"status": "complete", "assets": result["fixture"]["asset_count"],
                          "captured": result["selection_and_preview"]["mixed_apply"],
                          "captures": result["captures"]}, sort_keys=True))
        return 0
    except BaseException as exc:
        _flush(exc)
        try:
            cleanup = (_close_window(_APP, _WINDOW) if _WINDOW is not None and _APP is not None else
                       {"window_remaining": False})
            if _PARTIAL is not None:
                _checkpoint("failure_cleanup", result=cleanup,
                            fault_trial_retained=(args.output / "generated-atomicity-trial.sqlite3").exists())
        except Exception as cleanup_error:
            if _PARTIAL is not None:
                _checkpoint("failure_cleanup_incomplete", exception={"type": type(cleanup_error).__name__,
                                                                    "message": str(cleanup_error)})
        print(f"bulk curation native acceptance failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
