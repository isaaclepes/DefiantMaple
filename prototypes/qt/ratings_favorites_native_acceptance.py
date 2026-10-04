"""Bounded native ratings/favorites acceptance using generated media only.

Run from the repository root with a PySide6/Pillow-capable Python and a new,
empty --output directory outside the checkout. The helper intentionally refuses
to run unless HEAD is the declared merged-main baseline; evidence therefore
describes the source-file hashes recorded in its receipt, not a later commit.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import closing
import atexit
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time
import traceback

from PIL import Image, ImageDraw
from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple import catalog, collections, curation, metadata
from defiantmaple.catalog import connect
from defiantmaple.curation import FavoriteFilter, RatingFilter, RatingMode
from defiantmaple.sources import scan_sources
from prototypes.qt.app import GalleryWindow
from prototypes.qt.identity import APP_ID, app_icon


BASELINE = "60ebf881e6bb85316042100e3ed8beb119acf400"
CODE_FILES = (
    "defiantmaple/catalog.py", "defiantmaple/curation.py",
    "defiantmaple/sources.py", "defiantmaple/metadata.py",
    "defiantmaple/collections.py", "prototypes/qt/app.py",
    "prototypes/qt/identity.py", "prototypes/qt/ratings_favorites_native_acceptance.py",
)
_PARTIAL: dict | None = None
_PARTIAL_PATH: Path | None = None
_WINDOW: GalleryWindow | None = None
_APP: QApplication | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _flush(error: BaseException | None = None) -> None:
    if _PARTIAL is None or _PARTIAL_PATH is None or _PARTIAL.get("complete"):
        return
    if error is not None:
        _PARTIAL["status"] = "failed"
        _PARTIAL["exception"] = {"type": type(error).__name__, "message": str(error)}
        _PARTIAL["traceback"] = traceback.format_exc()
    temporary = _PARTIAL_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(_PARTIAL, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, _PARTIAL_PATH)


def _checkpoint(stage: str, **fields) -> None:
    assert _PARTIAL is not None
    _PARTIAL["stages"].append({"stage": stage, **fields})
    _PARTIAL["last_stage"] = stage
    _flush()


def _wait(app: QApplication, predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    return bool(predicate())


def _window_focus_report(app: QApplication, widget) -> dict:
    focus = app.focusWidget()
    active = app.activeWindow()
    focus_window = app.focusWindow()
    handle = widget.windowHandle() if widget is not None else None
    return {
        "widget_exists": widget is not None,
        "widget_class": type(widget).__name__ if widget is not None else None,
        "widget_title": widget.windowTitle() if widget is not None else None,
        "widget_visible": bool(widget is not None and widget.isVisible()),
        "widget_active": bool(widget is not None and widget.isActiveWindow()),
        "widget_exposed": bool(handle is not None and handle.isExposed()),
        "active_window_class": type(active).__name__ if active is not None else None,
        "active_window_title": active.windowTitle() if active is not None else None,
        "focus_widget_class": type(focus).__name__ if focus is not None else None,
        "focus_widget_object_name": focus.objectName() if focus is not None else None,
        "focus_widget_accessible_name": focus.accessibleName() if focus is not None else None,
        "focus_inside_widget": bool(widget is not None and focus is not None and
                                     (focus is widget or widget.isAncestorOf(focus))),
        "focus_window_title": focus_window.title() if focus_window is not None else None,
    }


def _request_activation(app: QApplication, widget, timeout: float = 4.0) -> bool:
    widget.raise_()
    widget.activateWindow()
    handle = widget.windowHandle()
    if handle is not None:
        handle.requestActivate()
    return _wait(app, lambda: widget.isVisible() and widget.isActiveWindow() and
                 handle is not None and handle.isExposed() and
                 _window_focus_report(app, widget)["focus_inside_widget"], timeout=timeout)


def _draw(path: Path, size: tuple[int, int], color: str) -> None:
    image = Image.new("RGB", size, "#f5f1e8")
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((width // 8, height // 8, width * 7 // 8, height * 7 // 8), fill=color)
    draw.ellipse((width // 3, height // 3, width * 2 // 3, height * 2 // 3), fill="#f2c14e")
    image.save(path)
    image.close()


def _seed_v4(database: Path, roots: dict[str, Path], paths: dict[str, Path]) -> None:
    with closing(sqlite3.connect(database)) as db:
        db.executescript(catalog.SCHEMA_V4)
        source_ids = {"one": "fixture-source-one", "two": "fixture-source-two"}
        for key, root in roots.items():
            db.execute(
                "INSERT INTO sources(source_id,name,root_path,recursive,existing_file_policy,"
                "health,initial_scan_completed,created_at,last_scan_at) "
                "VALUES(?,?,?,1,'inbox','paused',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                (source_ids[key], f"Generated source {key}", str(root.resolve())),
            )
        media = {
            "alpha": ("one", "new"), "beta": ("one", "reviewed"),
            "gamma": ("two", "reviewed"), "delta": ("two", "new"),
        }
        for key, (source_key, state) in media.items():
            path = paths[key].resolve()
            stat = path.stat()
            digest = _sha256(path)
            asset_id = f"fictional-asset-{key}"
            db.execute(
                "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
                "workflow_state,source_id,discovered_at) VALUES(?,?, 'image/png', ?, ?, ?, ?, ?)",
                (asset_id, str(path), digest, stat.st_size, state, source_ids[source_key],
                 "2026-01-01T00:00:00Z"),
            )
            db.execute(
                "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json,recorded_at) "
                "VALUES(?,?, 'generated_fixture', ?, '2026-01-01T00:00:00Z')",
                (f"fixture-provenance-{key}", asset_id,
                 json.dumps({"fixture": True, "role": key}, sort_keys=True)),
            )
            db.execute(
                "INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id,last_error) "
                "VALUES(?,?,?,?,?,?,?,?,1,'indexed',?,NULL)",
                (str(path), source_ids[source_key], stat.st_size, stat.st_mtime_ns,
                 str(stat.st_dev), str(stat.st_ino), stat.st_mtime_ns, stat.st_mtime_ns, asset_id),
            )
        db.execute("INSERT INTO tags VALUES('fixture-tag-parent','Generated','generated',NULL)")
        db.execute("INSERT INTO tags VALUES('fixture-tag-child','Color study','color-study','fixture-tag-parent')")
        db.execute("INSERT INTO tag_aliases VALUES('fixture-tag-alias','fixture-tag-child','Color Study')")
        db.execute("INSERT INTO entities VALUES('fixture-entity','Project','Generated set','generated-set')")
        db.execute("INSERT INTO entity_aliases VALUES('Project','fixture-entity-alias','fixture-entity','Generated Set')")
        for key in media:
            asset_id = f"fictional-asset-{key}"
            db.execute("INSERT INTO asset_tags VALUES(?, 'fixture-tag-child')", (asset_id,))
            db.execute("INSERT INTO asset_entities VALUES(?, 'fixture-entity')", (asset_id,))
        db.execute("INSERT INTO collections VALUES('fixture-collection','Ordered generated set','ordered-generated-set')")
        for position, key in enumerate(("gamma", "alpha", "delta", "beta"), start=7):
            db.execute("INSERT INTO collection_members VALUES('fixture-collection',?,?)",
                       (f"fictional-asset-{key}", position))
        db.commit()


_OLD_TABLES = (
    "sources", "assets", "provenance", "source_entries", "tags", "tag_aliases",
    "entities", "entity_aliases", "asset_tags", "asset_entities", "collections",
    "collection_members",
)
_OLD_COLUMNS = {
    "sources": "source_id,name,root_path,recursive,existing_file_policy,enabled,health,health_detail,initial_scan_completed,created_at,last_scan_at",
    "assets": "asset_id,current_path,media_type,sha256,byte_size,workflow_state,source_id,discovered_at",
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
}


def _v4_snapshot(database: Path) -> dict:
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
            "old_table_rows": values}


def _visible_names(window: GalleryWindow) -> list[str]:
    return sorted(Path(window.model.asset_at(row)["current_path"]).name
                  for row in range(window.model.rowCount()))


def _select_source(window: GalleryWindow, source_id: str | None) -> None:
    index = window.source_box.findData(source_id)
    if index < 0:
        raise AssertionError(f"Generated source was not selectable: {source_id}")
    window.source_box.setCurrentIndex(index)
    QApplication.processEvents()


def _select_filter(box, wanted) -> None:
    index = box.findData(wanted)
    if index < 0:
        raise AssertionError(f"Expected typed filter is absent: {wanted}")
    box.setCurrentIndex(index)
    QApplication.processEvents()


def _source_digest_map(paths: dict[str, Path]) -> dict[str, str]:
    return {key: _sha256(path) for key, path in sorted(paths.items()) if path.exists()}


def _asset_facts(database: Path, asset_id: str) -> dict:
    with connect(database) as db:
        row = db.execute("SELECT sha256,current_path,byte_size,workflow_state,source_id "
                         "FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
    if row is None:
        raise AssertionError(f"Generated fixture asset disappeared: {asset_id}")
    return dict(row)


def _os_release() -> dict:
    result = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"ID", "ID_LIKE", "PRETTY_NAME", "VERSION_ID"}:
                result[key] = value.strip().strip('"')
    except OSError:
        pass
    return result


def _run(output: Path) -> dict:
    global _PARTIAL, _PARTIAL_PATH, _WINDOW, _APP
    output = output.expanduser().resolve(strict=False)
    repo = Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents:
        raise ValueError("Acceptance output must be outside the Git checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Acceptance output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    _PARTIAL_PATH = output / "ratings-favorites-partial.json"
    _PARTIAL = {"schema": "defiantmaple.ratings-favorites-native-partial.v1",
                "status": "in_progress", "stages": []}
    atexit.register(_flush)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    source_before = {name: _sha256(repo / name) for name in CODE_FILES}
    if head != BASELINE:
        raise RuntimeError("Probe requires merged-main baseline HEAD " + BASELINE)
    _checkpoint("provenance_start", baseline=head, code_file_digests=source_before,
                working_tree_dirty=bool(subprocess.run(
                    ["git", "status", "--porcelain"], cwd=repo, check=True,
                    capture_output=True, text=True).stdout.strip()))

    roots = {"one": output / "generated-source-one", "two": output / "generated-source-two"}
    for root in roots.values():
        root.mkdir()
    paths = {
        "alpha": roots["one"] / "fictional-alpha.png",
        "beta": roots["one"] / "fictional-beta.png",
        "gamma": roots["two"] / "fictional-gamma.png",
        "delta": roots["two"] / "fictional-delta.png",
    }
    specs = {"alpha": ((640, 360), "#267a9b"), "beta": ((360, 640), "#9b4967"),
             "gamma": ((500, 400), "#588157"), "delta": ((420, 420), "#8041a0")}
    for key, path in paths.items():
        _draw(path, *specs[key])
    digests_start = _source_digest_map(paths)
    _checkpoint("generated_fixture_ready", source_file_digests=digests_start,
                fixture_asset_count=len(paths))

    database = output / "generated-catalog.sqlite3"
    _seed_v4(database, roots, paths)
    before = _v4_snapshot(database)
    with closing(sqlite3.connect(database)) as db:
        old_version = db.execute("PRAGMA user_version").fetchone()[0]
    migration = catalog.initialize(database, create=False)
    backup = Path(migration["backup_path"])
    backup_snapshot = _v4_snapshot(backup)
    with closing(sqlite3.connect(backup)) as db:
        backup_integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        backup_foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
    with closing(sqlite3.connect(database)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        new_version = db.execute("PRAGMA user_version").fetchone()[0]
    if (old_version != 4 or new_version != 5 or not migration["migrated"] or
            integrity != "ok" or foreign_keys or backup_integrity != "ok" or
            backup_foreign_keys or before["sha256"] != backup_snapshot["sha256"]):
        raise AssertionError("Generated v4 migration/verified backup preservation gate failed")
    with closing(sqlite3.connect(database)) as db:
        migrated_snapshot_values = {}
        for table in _OLD_TABLES:
            migrated_snapshot_values[table] = sorted(
                (list(row) for row in db.execute(
                    f'SELECT {_OLD_COLUMNS[table]} FROM "{table}"').fetchall()),
                key=lambda row: json.dumps(row, sort_keys=True, default=str))
    if before["sha256"] != hashlib.sha256(json.dumps(
            migrated_snapshot_values, sort_keys=True, separators=(",", ":"),
            default=str).encode()).hexdigest():
        raise AssertionError("Legacy v4 rows changed during migration")
    _checkpoint("migration_and_backup_passed", schema_before=old_version,
                schema_after=new_version, backup_sha256=_sha256(backup),
                migrated_catalog_integrity=integrity, backup_integrity=backup_integrity,
                migrated_foreign_key_violations=foreign_keys,
                backup_foreign_key_violations=backup_foreign_keys,
                preserved_v4_snapshot_sha256=before["sha256"],
                preserved_row_counts=before["row_counts"],
                preserved_collection_member_order=before["collection_member_order"])

    for key, rating, favorite in (("alpha", None, False), ("beta", 1, True),
                                  ("gamma", 4, False), ("delta", 4, True)):
        initial = curation.get_curation(database, f"fictional-asset-{key}")
        curation.set_curation(database, f"fictional-asset-{key}", rating=rating,
                              favorite=favorite, expected_revision=initial["revision"])
    scan_passes = []
    for source_id in ("fixture-source-one", "fixture-source-two"):
        for _ in range(2):
            scan_passes.append(scan_sources(database, source_id=source_id, quiet_seconds=0))
    with connect(database) as db:
        after_scan = {row[0]: (row[1], bool(row[2])) for row in db.execute(
            "SELECT asset_id,rating,favorite FROM assets ORDER BY asset_id")}
    expected_authority = {f"fictional-asset-{key}": (rating, favorite)
                          for key, rating, favorite in (("alpha", None, False),
                                                       ("beta", 1, True),
                                                       ("gamma", 4, False),
                                                       ("delta", 4, True))}
    if after_scan != expected_authority:
        raise AssertionError("Explicit curation values changed after source scans")
    _checkpoint("scan_authority_passed", scan_passes=scan_passes,
                curation_after_scan=after_scan)

    xdg_roots = {"data": output / "xdg-data", "cache": output / "xdg-cache",
                 "config": output / "xdg-config"}
    for path in xdg_roots.values():
        path.mkdir()
    os.environ["XDG_DATA_HOME"] = str(xdg_roots["data"])
    os.environ["XDG_CACHE_HOME"] = str(xdg_roots["cache"])
    os.environ["XDG_CONFIG_HOME"] = str(xdg_roots["config"])
    _checkpoint("xdg_state_isolated", paths={key: str(value) for key, value in xdg_roots.items()})
    app = QApplication(["ratings-favorites-native-acceptance"])
    _APP = app
    app.setOrganizationName("DefiantMaple")
    app.setApplicationName("DefiantMaple")
    app.setApplicationDisplayName("DefiantMaple")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    (output / "cache").mkdir()
    (output / "private").mkdir()
    window = GalleryWindow(database, enable_thumbnails=False,
                           cache_root=output / "cache", private_root=output / "private")
    _WINDOW = window
    window.show()
    if not _wait(app, lambda: window.isVisible() and window.windowHandle() is not None and
                 window.windowHandle().isExposed()):
        raise TimeoutError("Generated gallery window did not become exposed")
    if app.platformName().lower() != "wayland" or os.environ.get("XDG_SESSION_TYPE") != "wayland":
        raise RuntimeError("Native acceptance requires Qt Wayland inside a Wayland session")
    _checkpoint("native_window_exposed", platform_name=app.platformName(),
                session_type=os.environ.get("XDG_SESSION_TYPE"), app_id=APP_ID,
                window_title=window.windowTitle(),
                screen_px=[window.screen().size().width(), window.screen().size().height()],
                device_pixel_ratio=window.devicePixelRatio())
    gallery_activation_requested = _request_activation(app, window)
    gallery_activation_report = _window_focus_report(app, window)
    _checkpoint("gallery_activation_request", activation_requested=True,
                activation_passed=gallery_activation_requested,
                focus=gallery_activation_report)

    # Verify concrete typed filters against the real Qt-backed database model.
    _select_source(window, "fixture-source-one")
    _select_filter(window.filter_box, "new")
    _select_filter(window.rating_filter_box, RatingFilter(RatingMode.UNRATED))
    _select_filter(window.favorite_filter_box, FavoriteFilter.ALL)
    filter_results = [{"query": "source one AND state new AND unrated",
                       "expected": ["fictional-alpha.png"], "observed": _visible_names(window)}]
    _select_source(window, "fixture-source-two")
    _select_filter(window.filter_box, "reviewed")
    _select_filter(window.rating_filter_box, RatingFilter(RatingMode.AT_LEAST, 4))
    _select_filter(window.favorite_filter_box, FavoriteFilter.NOT_FAVORITES)
    filter_results.append({"query": "source two AND state reviewed AND at least 4 AND not favorite",
                           "expected": ["fictional-gamma.png"], "observed": _visible_names(window)})
    _select_filter(window.filter_box, "new")
    _select_filter(window.rating_filter_box, RatingFilter(RatingMode.EXACT, 4))
    _select_filter(window.favorite_filter_box, FavoriteFilter.FAVORITES)
    window.search_box.setText("fictional-delta")
    window._apply_metadata_filters()
    filter_results.append({"query": "source two AND state new AND exactly 4 AND favorite AND filename search",
                           "expected": ["fictional-delta.png"], "observed": _visible_names(window)})
    if any(row["expected"] != row["observed"] for row in filter_results):
        raise AssertionError(f"Typed composed filters returned unexpected fixture membership: {filter_results}")
    window.search_box.clear()
    window._apply_metadata_filters()
    _select_source(window, "fixture-source-one")
    _select_filter(window.filter_box, "new")
    _select_filter(window.rating_filter_box, RatingFilter(RatingMode.UNRATED))
    _select_filter(window.favorite_filter_box, FavoriteFilter.ALL)
    alpha_row = window.model.row_for_asset("fictional-asset-alpha")
    window.gallery.setCurrentIndex(window.model.index(alpha_row, 0))
    window.gallery.setFocus()
    app.processEvents()
    if not window.grab().save(str(output / "generated-gallery-window.png")):
        raise RuntimeError("Could not save generated-only app-window capture")
    _checkpoint("typed_filters_and_gallery_capture", filter_results=filter_results,
                capture="generated-gallery-window.png", row_count=window.model.rowCount())

    window.curation_button.click()
    editor = window.curation_dialog
    editor_after_show = _window_focus_report(app, editor)
    _checkpoint("curation_editor_after_button", activation_requested=False,
                parent_focus=_window_focus_report(app, window), editor_focus=editor_after_show)
    if editor is None:
        raise AssertionError("Gallery button did not create a curation dialog")
    editor_activation_requested = _request_activation(app, editor)
    editor_after_activation = _window_focus_report(app, editor)
    _checkpoint("curation_editor_activation_gate", activation_requested=True,
                activation_passed=editor_activation_requested,
                parent_focus=_window_focus_report(app, window), editor_focus=editor_after_activation)
    if not editor_activation_requested:
        raise AssertionError("Curation dialog failed visible/exposed/active/focused-descendant gate")
    editor.rating_box.setFocus()
    rating_initial_focus = _window_focus_report(app, editor)
    rating_control_has_focus = app.focusWidget() is editor.rating_box
    _checkpoint("rating_control_focus_gate", rating_control_has_focus=rating_control_has_focus,
                focus=rating_initial_focus)
    if not rating_control_has_focus:
        raise AssertionError("Rating combo did not receive actual Qt focus before keyboard input")
    QTest.keyClick(editor.rating_box, Qt.Key.Key_End)
    rating_end_selects_five = editor.rating_box.currentData() == 5
    QTest.keyClick(editor.rating_box, Qt.Key.Key_Home)
    rating_home_selects_unrated = editor.rating_box.currentData() is None
    QTest.keyClick(editor.rating_box, Qt.Key.Key_Tab)
    app.processEvents()
    focus_after_rating_tab = app.focusWidget()
    tab_reaches_favorite = focus_after_rating_tab is editor.favorite_box
    QTest.keyClick(editor.favorite_box, Qt.Key.Key_Space)
    favorite_space_checks = editor.favorite_box.isChecked()
    QTest.keyClick(editor.favorite_box, Qt.Key.Key_Space)
    favorite_space_unchecks = not editor.favorite_box.isChecked()
    QTest.keyClick(editor.favorite_box, Qt.Key.Key_Tab)
    app.processEvents()
    focus_after_favorite_tab = app.focusWidget()
    tab_reaches_save = focus_after_favorite_tab is editor.save_button
    if not (rating_end_selects_five and rating_home_selects_unrated and
            tab_reaches_favorite and favorite_space_checks and favorite_space_unchecks and
            tab_reaches_save):
        raise AssertionError("Keyboard rating/favorite controls or focus traversal failed")
    focus_widget = app.focusWidget()
    focus_report = {"widget_class": type(focus_widget).__name__ if focus_widget else None,
                    "object_name": focus_widget.objectName() if focus_widget else None,
                    "inside_dialog": bool(focus_widget and
                        (focus_widget is editor or editor.isAncestorOf(focus_widget))),
                    "dialog_active": editor.isActiveWindow(),
                    "rating_end_selects_five": rating_end_selects_five,
                    "rating_home_selects_unrated": rating_home_selects_unrated,
                    "tab_reaches_favorite": tab_reaches_favorite,
                    "favorite_space_checks": favorite_space_checks,
                    "favorite_space_unchecks": favorite_space_unchecks,
                    "tab_reaches_save": tab_reaches_save}
    if not focus_report["inside_dialog"]:
        raise AssertionError(f"Keyboard Tab focus left the active curation dialog: {focus_report}")
    if not editor.grab().save(str(output / "generated-curation-dialog.png")):
        raise RuntimeError("Could not save generated-only curation dialog capture")
    editor.rating_box.setCurrentIndex(editor.rating_box.findData(None))
    editor.favorite_box.setChecked(False)
    QTest.keyClick(editor.save_button, Qt.Key.Key_Space)
    no_op = {"feedback": editor.feedback.text(),
             "state": curation.get_curation(database, "fictional-asset-alpha"),
             "edit_count": len(curation.list_curation_edits(database, "fictional-asset-alpha"))}
    if "No changes" not in no_op["feedback"] or no_op["edit_count"] != 0:
        raise AssertionError(f"No-op edit created a misleading change: {no_op}")
    alpha_before_invalid = curation.get_curation(database, "fictional-asset-alpha")
    invalid_results = []
    for rating, favorite in ((0, True), (True, True), (6, False), (None, 1)):
        try:
            curation.set_curation(database, "fictional-asset-alpha", rating=rating,
                                  favorite=favorite,
                                  expected_revision=alpha_before_invalid["revision"])
        except ValueError as exc:
            invalid_results.append({"rating_type": type(rating).__name__,
                                    "favorite_type": type(favorite).__name__,
                                    "refused": True, "message": str(exc)})
        else:
            invalid_results.append({"rating_type": type(rating).__name__,
                                    "favorite_type": type(favorite).__name__, "refused": False})
    if not all(row["refused"] for row in invalid_results) or \
            curation.get_curation(database, "fictional-asset-alpha") != alpha_before_invalid:
        raise AssertionError("Invalid rating/favorite input was not rejected atomically")

    # The modeless editor holds alpha's immutable asset ID while gallery selection moves.
    _select_source(window, None)
    _select_filter(window.filter_box, "all")
    _select_filter(window.rating_filter_box, RatingFilter())
    _select_filter(window.favorite_filter_box, FavoriteFilter.ALL)
    beta_row = window.model.row_for_asset("fictional-asset-beta")
    window.gallery.setCurrentIndex(window.model.index(beta_row, 0))
    external = curation.set_curation(database, "fictional-asset-alpha", rating=2,
                                     favorite=False,
                                     expected_revision=alpha_before_invalid["revision"])
    editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
    editor.favorite_box.setChecked(True)
    editor.save_button.setFocus()
    QTest.keyClick(editor.save_button, Qt.Key.Key_Space)
    stale_feedback = editor.feedback.text()
    beta_after_stale = curation.get_curation(database, "fictional-asset-beta")
    beta_unchanged = (beta_after_stale["rating"], beta_after_stale["favorite"]) == \
        expected_authority["fictional-asset-beta"]
    alpha_after_stale = curation.get_curation(database, "fictional-asset-alpha")
    if ("not saved" not in stale_feedback.lower() or editor.asset_id != "fictional-asset-alpha" or
            not beta_unchanged or (alpha_after_stale["rating"], alpha_after_stale["favorite"]) != (2, False)):
        raise AssertionError("Captured-ID stale-write gate failed")
    editor.reload()
    editor.rating_box.setCurrentIndex(editor.rating_box.findData(5))
    editor.favorite_box.setChecked(True)
    editor.save_button.setFocus()
    QTest.keyClick(editor.save_button, Qt.Key.Key_Space)
    alpha_saved = curation.get_curation(database, "fictional-asset-alpha")
    if (alpha_saved["rating"], alpha_saved["favorite"]) != (5, True):
        raise AssertionError("Explicit reload and save did not persist captured asset values")
    captured_id_result = {"captured_asset": "fictional-asset-alpha",
                          "gallery_selection_after_open": "fictional-asset-beta",
                          "external_writer_result": external,
                          "stale_feedback": stale_feedback,
                          "reloaded_save_state": alpha_saved,
                          "beta_state_unchanged": beta_unchanged,
                          "keyboard_tab_focus": focus_report,
                          "invalid_inputs": invalid_results, "no_op": no_op}
    _checkpoint("captured_identity_validation_and_save", result=captured_id_result)

    # Open a candidate that is initially undoable; make metadata ABA externally,
    # refuse the stale click, then prove explicit reload disables that candidate.
    beta_state = curation.get_curation(database, "fictional-asset-beta")
    beta_edit = curation.set_curation(database, "fictional-asset-beta", rating=2,
                                      favorite=True, expected_revision=beta_state["revision"])
    window._restore_asset_selection("fictional-asset-beta")
    if not _request_activation(app, window):
        _checkpoint("beta_parent_activation_failed", focus=_window_focus_report(app, window))
        raise AssertionError("Gallery lost native activation before opening beta undo dialog")
    window.curation_button.click()
    beta_dialog = window.curation_dialog
    beta_after_show = _window_focus_report(app, beta_dialog)
    _checkpoint("beta_dialog_after_button", activation_requested=False,
                parent_focus=_window_focus_report(app, window), dialog_focus=beta_after_show)
    if beta_dialog is None:
        raise AssertionError("Gallery button did not create beta curation dialog")
    beta_activation_requested = _request_activation(app, beta_dialog)
    beta_after_activation = _window_focus_report(app, beta_dialog)
    _checkpoint("beta_dialog_activation_gate", activation_requested=True,
                activation_passed=beta_activation_requested,
                parent_focus=_window_focus_report(app, window), dialog_focus=beta_after_activation)
    if not beta_activation_requested:
        raise AssertionError("Beta undo dialog failed visible/exposed/active/focused-descendant gate")
    if not beta_dialog.undo_button.isEnabled():
        raise AssertionError("Latest beta edit was not presented as undoable before intervening changes")
    with connect(database) as db:
        db.execute("DELETE FROM asset_tags WHERE asset_id=? AND tag_id=?",
                   ("fictional-asset-beta", "fixture-tag-child"))
        db.execute("INSERT INTO asset_tags(asset_id,tag_id) VALUES(?,?)",
                   ("fictional-asset-beta", "fixture-tag-child"))
    beta_after_aba = curation.get_curation(database, "fictional-asset-beta")
    beta_dialog.undo_button.click()
    stale_undo_feedback = beta_dialog.feedback.text()
    undo_state_after_stale_click = curation.get_curation(database, "fictional-asset-beta")
    if (beta_after_aba["revision"] <= beta_edit["revision"] or
            "not applied" not in stale_undo_feedback.lower() or
            undo_state_after_stale_click != beta_after_aba):
        raise AssertionError("Metadata ABA did not safely refuse the stale visible undo")
    beta_dialog.reload()
    undo_disabled_after_reload = not beta_dialog.undo_button.isEnabled()
    try:
        curation.undo_curation(database, beta_edit["edit_id"])
    except curation.CurationConflict as exc:
        aba_api_refusal = str(exc)
    else:
        raise AssertionError("Metadata ABA undo was accepted after explicit reload")
    aba_result = {"revision_before": beta_edit["revision"],
                  "revision_after_aba": beta_after_aba["revision"],
                  "rating_favorite_unchanged": (beta_after_aba["rating"], beta_after_aba["favorite"]) == (2, True),
                  "visible_stale_undo_feedback": stale_undo_feedback,
                  "disabled_after_reload": undo_disabled_after_reload,
                  "api_refusal": aba_api_refusal}
    if not undo_disabled_after_reload or not aba_result["rating_favorite_unchanged"]:
        raise AssertionError("Stale undo candidate remained available after reload")
    _checkpoint("metadata_aba_undo_refused", result=aba_result)
    beta_dialog.close()
    editor.close()
    window.close()
    if not _wait(app, lambda: not window.isVisible()):
        raise TimeoutError("Gallery failed to close before durable reopen test")

    # Reopening the catalog preserves values/history; only the latest safe edit
    # is undone. This does not claim a general history stack or redo.
    alpha_edits_before_reopen = curation.list_curation_edits(database, "fictional-asset-alpha")
    if not alpha_edits_before_reopen or not alpha_edits_before_reopen[0]["edit_id"]:
        raise AssertionError("Alpha edit history did not persist across close")
    alpha_history_id = alpha_edits_before_reopen[0]["edit_id"]
    window = GalleryWindow(database, enable_thumbnails=False,
                           cache_root=output / "cache", private_root=output / "private")
    _WINDOW = window
    window.show()
    if not _wait(app, lambda: window.isVisible() and window.windowHandle() and
                 window.windowHandle().isExposed()):
        raise TimeoutError("Gallery did not reopen")
    alpha_before_undo = curation.get_curation(database, "fictional-asset-alpha")
    undone = curation.undo_curation(database, alpha_history_id)
    alpha_after_undo = curation.get_curation(database, "fictional-asset-alpha")
    if ((alpha_before_undo["rating"], alpha_before_undo["favorite"]) != (5, True) or
            (alpha_after_undo["rating"], alpha_after_undo["favorite"]) != (2, False) or
            not curation.list_curation_edits(database, "fictional-asset-alpha")[0]["undone"]):
        raise AssertionError("Durable single-edit undo did not restore the prior user values")
    _checkpoint("durable_reopen_undo", state_before=alpha_before_undo,
                undo_result=undone, state_after=alpha_after_undo,
                older_history_unavailable_reason="Conservative single-edit undo; no stack/redo")

    # Content and path changes are deliberately made only to generated originals.
    gamma_before = {**curation.get_curation(database, "fictional-asset-gamma"),
                    **_asset_facts(database, "fictional-asset-gamma")}
    gamma_edit = curation.set_curation(database, "fictional-asset-gamma", rating=3,
                                       favorite=True, expected_revision=gamma_before["revision"])
    gamma_path = paths["gamma"]
    _draw(gamma_path, (500, 400), "#c75b39")
    content_scans = [scan_sources(database, source_id="fixture-source-two", quiet_seconds=60),
                     scan_sources(database, source_id="fixture-source-two", quiet_seconds=0)]
    gamma_after_content = {**curation.get_curation(database, "fictional-asset-gamma"),
                           **_asset_facts(database, "fictional-asset-gamma")}
    try:
        curation.undo_curation(database, gamma_edit["edit_id"])
    except curation.CurationConflict as exc:
        content_undo_refusal = str(exc)
    else:
        raise AssertionError("Undo after generated content revision was accepted")
    if (gamma_after_content["sha256"] == gamma_before["sha256"] or
            gamma_after_content["revision"] <= gamma_edit["revision"] or
            (gamma_after_content["rating"], gamma_after_content["favorite"]) != (3, True)):
        raise AssertionError("Generated content rescan did not advance revision while preserving overrides")
    _checkpoint("content_revision_undo_refused", scan_summaries=content_scans,
                state_before=gamma_before, edit=gamma_edit,
                state_after=gamma_after_content, refusal=content_undo_refusal)

    delta_before = {**curation.get_curation(database, "fictional-asset-delta"),
                    **_asset_facts(database, "fictional-asset-delta")}
    delta_edit = curation.set_curation(database, "fictional-asset-delta", rating=3,
                                       favorite=False, expected_revision=delta_before["revision"])
    old_delta_path = paths["delta"]
    new_delta_path = old_delta_path.with_name("fictional-delta-renamed.png")
    old_delta_path.rename(new_delta_path)
    rename_scan = scan_sources(database, source_id="fixture-source-two", quiet_seconds=0)
    paths["delta"] = new_delta_path
    delta_after_rename = {**curation.get_curation(database, "fictional-asset-delta"),
                          **_asset_facts(database, "fictional-asset-delta")}
    try:
        curation.undo_curation(database, delta_edit["edit_id"])
    except curation.CurationConflict as exc:
        path_undo_refusal = str(exc)
    else:
        raise AssertionError("Undo after generated path revision was accepted")
    if (Path(delta_after_rename["current_path"]) != new_delta_path.resolve() or
            delta_after_rename["revision"] <= delta_edit["revision"]):
        raise AssertionError("Generated path rename did not advance the catalog revision")
    _checkpoint("path_revision_undo_refused", scan_summary=rename_scan,
                state_before=delta_before, edit=delta_edit,
                state_after=delta_after_rename, refusal=path_undo_refusal)

    with closing(sqlite3.connect(database)) as db:
        integrity_after = db.execute("PRAGMA integrity_check").fetchone()[0]
        fk_after = db.execute("PRAGMA foreign_key_check").fetchall()
        asset_count_after = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    digest_after = _source_digest_map(paths)
    if integrity_after != "ok" or fk_after or asset_count_after != 4:
        raise AssertionError("Catalog integrity/count failed at end of generated probe")
    if digest_after.get("alpha") != digests_start["alpha"] or \
            digest_after.get("beta") != digests_start["beta"] or \
            digest_after.get("delta") != digests_start["delta"] or \
            digest_after.get("gamma") == digests_start["gamma"]:
        raise AssertionError("Expected generated-only content mutation/hash preservation matrix failed")
    source_after = {name: _sha256(repo / name) for name in CODE_FILES}
    if source_before != source_after:
        raise AssertionError("Acceptance helper or implementation source changed during the run")
    _checkpoint("integrity_source_and_cleanup_gates", integrity=integrity_after,
                foreign_key_violations=fk_after, asset_count=asset_count_after,
                source_file_digests_before=digests_start, source_file_digests_after=digest_after,
                code_file_digests_before=source_before, code_file_digests_after=source_after)

    result = {
        "schema": "defiantmaple.ratings-favorites-native-acceptance.v1",
        "baseline_commit": head,
        "working_tree_dirty": _PARTIAL["stages"][0]["working_tree_dirty"],
        "code_file_digests": source_before,
        "host": {"platform": platform.platform(), "os_release": _os_release(),
                 "machine": platform.machine(), "python": platform.python_version(),
                 "qt": __import__("PySide6").__version__, "display_backend": app.platformName(),
                 "session_type": os.environ.get("XDG_SESSION_TYPE"),
                 "logical_cpu_count": os.cpu_count(),
                 "screen_px": [window.screen().size().width(), window.screen().size().height()],
                 "device_pixel_ratio": window.devicePixelRatio()},
        "fixture": {"source_file_digests_before": digests_start,
                    "source_file_digests_after": digest_after,
                    "source_count": 2, "asset_count": asset_count_after,
                    "fixture_names": sorted(path.name for path in paths.values())},
        "migration": {"schema_before": old_version, "schema_after": new_version,
                      "backup_sha256": _sha256(backup), "backup_integrity": backup_integrity,
                      "backup_foreign_key_violations": backup_foreign_keys,
                      "migrated_catalog_integrity": integrity,
                      "migrated_foreign_key_violations": foreign_keys,
                      "preserved_v4_snapshot_sha256": before["sha256"],
                      "preserved_row_counts": before["row_counts"],
                      "collection_member_order": before["collection_member_order"]},
        "source_scan_authority": {"passes": scan_passes,
                                  "curation_after_scan": after_scan},
        "filters": filter_results,
        "editing": captured_id_result,
        "metadata_aba": aba_result,
        "durable_undo": {"before": alpha_before_undo, "result": undone,
                         "after": alpha_after_undo,
                         "history_after": curation.list_curation_edits(database, "fictional-asset-alpha")},
        "content_undo_refusal": {"scans": content_scans, "state": gamma_after_content,
                                 "message": content_undo_refusal},
        "path_undo_refusal": {"scan": rename_scan, "state": delta_after_rename,
                              "message": path_undo_refusal},
        "integrity": {"check": integrity_after, "foreign_key_violations": fk_after},
        "captures": ["generated-gallery-window.png", "generated-curation-dialog.png"],
        "privacy": {"media_generated_only": True, "capture_scope": "Qt app windows only",
                    "whole_desktop_capture": False, "fixture_isolation": str(output),
                    "isolated_xdg_roots": {key: str(value) for key, value in xdg_roots.items()}},
        "measurement_scope": {"thumbnail_workers_enabled": False,
                              "thumbnail_performance_not_measured": True,
                              "focus_scope": "Automated QtTest native events: End/Home rating selection, two Tab transitions, Space checkbox toggles and Save activation; no human or full accessibility claim"},
        "acceptance_boundary": "Scoped generated-fixture evidence; broader SDD rows remain partial.",
    }
    app_id = APP_ID
    window.close()
    if not _wait(app, lambda: not window.isVisible()):
        raise TimeoutError("Gallery did not close during normal cleanup")
    result["cleanup"] = {"window_closed": not window.isVisible(),
                         "application_id_reported_by_qt": app_id}
    source_after_cleanup = {name: _sha256(repo / name) for name in CODE_FILES}
    if source_after_cleanup != source_before:
        raise AssertionError("Source hashes changed during cleanup")
    result["code_file_digests_after_cleanup"] = source_after_cleanup
    (output / "ratings-favorites-native-acceptance.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _PARTIAL["status"] = "complete"
    _PARTIAL["result_file"] = "ratings-favorites-native-acceptance.json"
    _flush()
    _PARTIAL["complete"] = True
    return result


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new or empty evidence directory outside the repository")
    args = parser.parse_args(argv)
    try:
        result = _run(args.output)
        print(json.dumps({"status": "complete", "assets": result["fixture"]["asset_count"],
                          "filters": len(result["filters"]),
                          "captures": result["captures"]}, sort_keys=True))
        return 0
    except BaseException as exc:
        _flush(exc)
        # Best effort cleanup is constrained to this generated probe's own Qt window.
        try:
            if _WINDOW is not None:
                _WINDOW.close()
            if _APP is not None:
                _APP.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        except Exception:
            pass
        print(f"ratings/favorites native acceptance failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
