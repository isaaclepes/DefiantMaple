"""Native KDE/Wayland acceptance on generated fictional gallery fixtures only."""
from __future__ import annotations

from argparse import ArgumentParser
from configparser import ConfigParser
import atexit
from pathlib import Path
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import sys
import time
import shutil
import subprocess
import signal
import tempfile

from PIL import Image, ImageDraw
from PySide6.QtCore import QEventLoop, QPoint, QTimer, Qt, qVersion
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from defiantmaple.catalog import initialize
from defiantmaple.sources import add_source, scan_sources
from defiantmaple.thumbnail import ThumbnailLimits
from prototypes.qt.app import GalleryWindow
from prototypes.qt.identity import APP_ID, ICON_PATH, app_icon
from prototypes.qt.preview import FullImageDialog, PreviewLimits


_ACTIVE_PARTIAL_RECEIPT: dict | None = None
_ACTIVE_PARTIAL_PATH: Path | None = None


def _flush_partial_receipt(error: BaseException | None = None):
    if _ACTIVE_PARTIAL_RECEIPT is None or _ACTIVE_PARTIAL_PATH is None:
        return
    if _ACTIVE_PARTIAL_RECEIPT.get("completed"):
        return
    if error is not None:
        _ACTIVE_PARTIAL_RECEIPT["attempt_status"] = "failed"
        _ACTIVE_PARTIAL_RECEIPT["exception"] = {
            "type": type(error).__name__, "message": str(error),
        }
    temporary = _ACTIVE_PARTIAL_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(_ACTIVE_PARTIAL_RECEIPT, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, _ACTIVE_PARTIAL_PATH)


def _focus_report(app: QApplication, dialog: FullImageDialog) -> dict:
    focus = app.focusWidget()
    active = app.activeWindow()
    focus_window = app.focusWindow()
    return {
        "focus_widget_class": type(focus).__name__ if focus is not None else None,
        "focus_widget_object_name": focus.objectName() if focus is not None else None,
        "focus_widget_accessible_name": (focus.accessibleName() if focus is not None else None),
        "focus_widget_inside_dialog": bool(
            focus is not None and (focus is dialog or dialog.isAncestorOf(focus))
        ),
        "active_window_class": type(active).__name__ if active is not None else None,
        "active_window_title": active.windowTitle() if active is not None else None,
        "focus_window_title": focus_window.title() if focus_window is not None else None,
        "dialog_active": dialog.isActiveWindow(),
        "canvas_has_focus": dialog.canvas.hasFocus(),
    }


def _canvas_report(dialog: FullImageDialog) -> dict:
    canvas = dialog.canvas
    item = canvas._item
    mapped = (canvas.mapFromScene(item.boundingRect()).boundingRect()
              if item is not None else None)

    def scrollbar(bar):
        return {"minimum": bar.minimum(), "maximum": bar.maximum(),
                "value": bar.value(), "page_step": bar.pageStep()}

    return {
        "dialog_geometry": [dialog.x(), dialog.y(), dialog.width(), dialog.height()],
        "dialog_visible": dialog.isVisible(),
        "dialog_active": dialog.isActiveWindow(),
        "dialog_fullscreen": dialog.isFullScreen(),
        "dialog_window_state": int(dialog.windowState().value),
        "dialog_exposed": bool(dialog.windowHandle() and dialog.windowHandle().isExposed()),
        "window_handle_visibility": (dialog.windowHandle().visibility().name
                                     if dialog.windowHandle() else None),
        "viewport_size": [canvas.viewport().width(), canvas.viewport().height()],
        "scene_rect": [canvas.sceneRect().x(), canvas.sceneRect().y(),
                       canvas.sceneRect().width(), canvas.sceneRect().height()],
        "image_bounds_in_view": ([mapped.x(), mapped.y(), mapped.width(), mapped.height()]
                                  if mapped is not None else None),
        "transform_scale": canvas.transform().m11(),
        "canvas_scale": canvas._scale,
        "horizontal_scroll": scrollbar(canvas.horizontalScrollBar()),
        "vertical_scroll": scrollbar(canvas.verticalScrollBar()),
        "drag_mode": canvas.dragMode().name,
    }


def _wait_fullscreen_state(app: QApplication, dialog: FullImageDialog, *, fullscreen: bool,
                           normal_size: tuple[int, int] | None = None,
                           timeout: float = 4.0, stable_seconds: float = 0.25) -> dict:
    started = time.perf_counter()
    deadline = started + timeout
    stable_since = None
    matched = False
    while time.perf_counter() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        handle = dialog.windowHandle()
        exposed = bool(handle and handle.isExposed())
        in_fullscreen = dialog.isFullScreen()
        size_matches = (normal_size is None or
                        (dialog.width(), dialog.height()) == normal_size)
        matched = (in_fullscreen == fullscreen and exposed and size_matches)
        if matched:
            if stable_since is None:
                stable_since = time.perf_counter()
            elif time.perf_counter() - stable_since >= stable_seconds:
                break
        else:
            stable_since = None
        time.sleep(0.005)
    final = _canvas_report(dialog)
    return {"requested_fullscreen": fullscreen,
            "matched_stable_state": bool(matched and stable_since is not None and
                                         time.perf_counter() - stable_since >= stable_seconds),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "stable_seconds_required": stable_seconds,
            "timeout_seconds": timeout,
            "final_state": final}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _draw_fixture(path: Path, size: tuple[int, int], color: str, alpha=False):
    image = Image.new("RGBA", size, (0, 0, 0, 0) if alpha else "#f5f1e8")
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((width // 10, height // 8, width * 9 // 10, height * 7 // 8),
                   fill=color)
    draw.ellipse((width // 3, height // 3, width * 2 // 3, height * 2 // 3),
                 fill="#f2c14e")
    image.save(path)
    image.close()


def _generate(root: Path) -> dict:
    root.mkdir(parents=True)
    _draw_fixture(root / "fictional-landscape.png", (420, 180), "#267a9b")
    _draw_fixture(root / "fictional-portrait.png", (180, 420), "#9b4967")
    _draw_fixture(root / "fictional-square.png", (240, 240), "#588157")
    _draw_fixture(root / "fictional-alpha.png", (220, 140), "#8041a0", alpha=True)
    oriented = Image.new("RGB", (320, 180), "#d5a84f")
    ImageDraw.Draw(oriented).rectangle((0, 0, 70, 179), fill="#267a9b")
    exif = Image.Exif()
    exif[274] = 6
    oriented.save(root / "fictional-exif-6.jpg", exif=exif)
    oriented.close()
    for index in range(58):
        color = f"#{(index * 37 + 41) % 256:02x}{(index * 71 + 83) % 256:02x}{(index * 19 + 127) % 256:02x}"
        _draw_fixture(root / f"fictional-batch-{index:03d}.png",
                      (176 + index % 5 * 13, 128 + index % 7 * 11), color)
    large = Image.new("RGB", (1920, 1200), "#f5f1e8")
    draw = ImageDraw.Draw(large)
    for y in range(0, 1200, 80):
        draw.rectangle((0, y, 1919, y + 39), fill="#267a9b" if (y // 80) % 2 else "#9b4967")
    draw.ellipse((640, 240, 1280, 880), fill="#f2c14e", outline="#263238", width=12)
    large.save(root / "fictional-large-original.png", optimize=False)
    large.close()
    return {path.name: _sha256(path) for path in sorted(root.iterdir())}


def _wait(app: QApplication, predicate, timeout=15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    return bool(predicate())


def _asset_rows(window: GalleryWindow) -> list[dict]:
    return [window.model.asset_at(row) for row in range(window.model.rowCount())]


def _catalog_snapshot(database: Path) -> dict:
    with sqlite3.connect(database) as db:
        assets = db.execute(
            "SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state "
            "FROM assets ORDER BY asset_id"
        ).fetchall()
        tags = db.execute("SELECT asset_id,tag_id FROM asset_tags ORDER BY asset_id,tag_id").fetchall()
        entities = db.execute(
            "SELECT asset_id,entity_id FROM asset_entities ORDER BY asset_id,entity_id"
        ).fetchall()
    values = {"assets": assets, "asset_tags": tags, "asset_entities": entities}
    serialized = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return {"sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "asset_count": len(assets), "tag_assignment_count": len(tags),
            "entity_assignment_count": len(entities)}


def _os_release() -> dict:
    values = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"ID", "ID_LIKE", "PRETTY_NAME", "VERSION_ID"}:
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def _process_tree_rss_bytes() -> int | None:
    try:
        import psutil
        process = psutil.Process()
        processes = [process, *process.children(recursive=True)]
        return sum(item.memory_info().rss for item in processes if item.is_running())
    except Exception:
        return None


def _physical_memory_bytes() -> int | None:
    try:
        values = Path("/proc/meminfo").read_text(encoding="ascii")
        match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", values, re.MULTILINE)
        return int(match.group(1)) * 1024 if match else None
    except OSError:
        return None


def _source_provenance(repo: Path) -> dict:
    relative = (
        "prototypes/qt/app.py", "prototypes/qt/preview.py",
        "prototypes/qt/identity.py", "prototypes/qt/native_acceptance.py",
        "prototypes/qt/assets/io.github.isaaclepes.DefiantMaple.desktop",
        "prototypes/qt/assets/io.github.isaaclepes.DefiantMaple.png",
        "defiantmaple/thumbnail.py", "defiantmaple/catalog.py",
        "defiantmaple/sources.py", "defiantmaple/media.py",
    )
    hashes = {name: _sha256(repo / name) for name in relative}
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                            check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            cwd=repo, check=True, capture_output=True, text=True).stdout
    return {"baseline_commit": "b0d1755fd344f7cb033c83d66413dff04997bfd4",
            "checkout_head": commit,
            "working_tree_dirty": bool(status.strip()),
            "working_tree_status_paths": [line[3:] for line in status.splitlines()],
            "source_sha256": hashes}


def _kwin_identity(output: Path, target_pid: int, progress=None) -> dict:
    busctl = shutil.which("busctl")
    if not busctl:
        raise RuntimeError("busctl is required for scoped KWin compositor identity evidence")
    with tempfile.TemporaryDirectory(prefix="defiantmaple-kwin-", dir=output) as temp_name:
        temporary = Path(temp_name)
        receiver_path = temporary / "receiver.py"
        result_path = temporary / "kwin-result.json"
        receiver_source = '''
import json, os, sys
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
target_pid = int(sys.argv[1])
result_path = sys.argv[2]
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
kwin_owner = bus.get_name_owner("org.kde.KWin")
service_name = "org.defiantmaple.GalleryProbe.p%d" % target_pid
interface = "org.defiantmaple.GalleryProbe"
loop = GLib.MainLoop()
windows = []
class Receiver(dbus.service.Object):
    def __init__(self):
        super().__init__(bus, "/Probe")
    @dbus.service.method(interface, in_signature="isss", out_signature="",
                          sender_keyword="sender_keyword")
    def Report(self, pid, internal_id, desktop_file_name, resource_class, sender_keyword=None):
        if int(pid) != target_pid or sender_keyword != kwin_owner:
            return
        windows.append({"pid": int(pid), "internal_id": str(internal_id),
                        "desktop_file_name": str(desktop_file_name),
                        "resource_class": str(resource_class)})
    @dbus.service.method(interface, in_signature="", out_signature="",
                          sender_keyword="sender_keyword")
    def Finish(self, sender_keyword=None):
        if sender_keyword != kwin_owner or not windows:
            return
        value = {"windows": windows, "dbus_sender": sender_keyword}
        with open(result_path, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        loop.quit()
bus.request_name(service_name)
receiver = Receiver()
with open(result_path + ".ready", "w", encoding="ascii") as stream:
    stream.write("ready")
loop.run()
'''
        receiver_path.write_text(receiver_source, encoding="utf-8")
        receiver_path.chmod(0o600)
        process = subprocess.Popen([sys.executable, str(receiver_path), str(target_pid),
                                    str(result_path)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True)
        plugin_name = f"defiantmaple_gallery_probe_{target_pid}"
        loaded = False
        result = None
        unloaded = not loaded
        unload_error = None
        try:
            ready_path = Path(str(result_path) + ".ready")
            ready_deadline = time.monotonic() + 5
            while time.monotonic() < ready_deadline and not ready_path.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"KWin receiver exited: {process.stderr.read()}")
                time.sleep(0.02)
            if not ready_path.exists():
                raise TimeoutError("Temporary KWin receiver did not become ready")
            if progress:
                progress("kwin_receiver_ready", pid=target_pid)
            script_path = temporary / "probe.js"
            script_source = f'''const targetPid = {target_pid};
const service = "org.defiantmaple.GalleryProbe.p{target_pid}";
const matches = [];
for (const window of workspace.windowList()) {{
    if (window.pid === targetPid) {{
        matches.push(window);
    }}
}}
for (const window of matches) {{
        callDBus(service, "/Probe", "org.defiantmaple.GalleryProbe", "Report",
                 window.pid, String(window.internalId),
                 String(window.desktopFileName), String(window.resourceClass));
}}
callDBus(service, "/Probe", "org.defiantmaple.GalleryProbe", "Finish");
'''
            script_path.write_text(script_source, encoding="utf-8")
            script_path.chmod(0o600)
            call = [busctl, "--user", "call", "org.kde.KWin", "/Scripting",
                    "org.kde.kwin.Scripting", "loadScript", "ss",
                    str(script_path), plugin_name]
            loaded_result = subprocess.run(call, check=True, capture_output=True,
                                           text=True, timeout=5)
            loaded = True
            if progress:
                progress("kwin_script_loaded", plugin_name=plugin_name,
                         script_path=str(script_path))
            subprocess.run([busctl, "--user", "call", "org.kde.KWin", "/Scripting",
                            "org.kde.kwin.Scripting", "start"],
                           check=True, capture_output=True, text=True, timeout=5)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not result_path.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"KWin receiver exited: {process.stderr.read()}")
                time.sleep(0.02)
            if not result_path.exists():
                raise TimeoutError("KWin did not report the generated app windows by PID")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not result["windows"] or any(row["pid"] != target_pid for row in result["windows"]):
                raise AssertionError("KWin identity report was not scoped to the app PID")
            result["script_id_output"] = loaded_result.stdout.strip()
        finally:
            if loaded:
                try:
                    unload_result = subprocess.run(
                        [busctl, "--user", "call", "org.kde.KWin", "/Scripting",
                         "org.kde.kwin.Scripting", "unloadScript", "s", plugin_name],
                        capture_output=True, text=True, timeout=5, check=False
                    )
                    unloaded = (unload_result.returncode == 0 and
                                unload_result.stdout.strip() == "b true")
                    if not unloaded:
                        unload_error = unload_result.stderr.strip() or unload_result.stdout.strip()
                except Exception as exc:
                    unload_error = f"{type(exc).__name__}: {exc}"
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            except Exception as exc:
                if unload_error is None:
                    unload_error = f"receiver cleanup failed: {type(exc).__name__}: {exc}"
            if progress:
                progress("kwin_script_cleanup", script_unloaded=unloaded,
                         unload_error=unload_error,
                         receiver_returncode=process.returncode)
        if result is None:
            raise RuntimeError("KWin identity probe returned no app window")
        result["script_unloaded"] = unloaded
        if not unloaded:
            raise RuntimeError(f"Temporary KWin identity script could not be unloaded: {unload_error}")
        return result


def run(output: Path) -> dict:
    global _ACTIVE_PARTIAL_PATH, _ACTIVE_PARTIAL_RECEIPT
    output = output.expanduser().resolve(strict=False)
    repo = Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents:
        raise ValueError("Acceptance output must be outside the Git checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Acceptance output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    _ACTIVE_PARTIAL_PATH = output / "native-acceptance-partial.json"
    _ACTIVE_PARTIAL_RECEIPT = {
        "schema": "defiantmaple.gallery-native-acceptance-partial.v1",
        "output_directory": str(output),
        "attempt_status": "in_progress",
        "completed_stages": [],
        "stage_receipts": [],
    }
    atexit.register(_flush_partial_receipt)

    def checkpoint(stage: str, **evidence):
        _ACTIVE_PARTIAL_RECEIPT["completed_stages"].append(stage)
        _ACTIVE_PARTIAL_RECEIPT["stage_receipts"].append(
            {"stage": stage, **evidence}
        )
        _ACTIVE_PARTIAL_RECEIPT["last_completed_stage"] = stage
        _flush_partial_receipt()

    fixture = output / "fictional-fixture"
    provenance_before = _source_provenance(repo)
    checkpoint("source_provenance_captured", provenance=provenance_before)
    if provenance_before["checkout_head"] != provenance_before["baseline_commit"]:
        raise RuntimeError("Probe checkout HEAD differs from the declared merged-main baseline")
    source_digests_before = _generate(fixture)
    checkpoint("generated_fixture_created", fixture_file_sha256=source_digests_before)
    database = output / "fictional-catalog.sqlite3"
    cache = output / "cache"
    private = output / "private"
    xdg_data = output / "xdg-data"
    xdg_cache = output / "xdg-cache"
    for path in (cache, private, xdg_data, xdg_cache):
        path.mkdir()
    packaged_desktop_entry = Path(__file__).with_name("assets") / f"{APP_ID}.desktop"
    packaged_icon = Path(__file__).with_name("assets") / f"{APP_ID}.png"
    applications_dir = xdg_data / "applications"
    icons_dir = xdg_data / "icons" / "hicolor" / "256x256" / "apps"
    applications_dir.mkdir()
    icons_dir.mkdir(parents=True)
    staged_desktop_entry = applications_dir / packaged_desktop_entry.name
    staged_icon = icons_dir / packaged_icon.name
    shutil.copy2(packaged_desktop_entry, staged_desktop_entry)
    shutil.copy2(packaged_icon, staged_icon)
    checkpoint("isolated_desktop_assets_staged",
               desktop_entry_sha256=_sha256(staged_desktop_entry),
               icon_sha256=_sha256(staged_icon),
               desktop_entry_source_sha256=_sha256(packaged_desktop_entry),
               icon_source_sha256=_sha256(packaged_icon))
    desktop_config = ConfigParser(interpolation=None)
    desktop_config.read(staged_desktop_entry, encoding="utf-8")
    desktop = desktop_config["Desktop Entry"]
    if (desktop.get("Type") != "Application" or desktop.get("Name") != "DefiantMaple" or
            desktop.get("Icon") != APP_ID or not desktop.get("Exec")):
        raise AssertionError("Isolated .desktop entry is missing required application identity")
    os.environ["XDG_DATA_HOME"] = str(xdg_data)
    os.environ["XDG_CACHE_HOME"] = str(xdg_cache)
    initialize(database)
    source = add_source(database, fixture, name="Generated acceptance fixture")
    scan_passes = [scan_sources(database, source_id=source["source_id"], quiet_seconds=0)]
    checkpoint("generated_source_first_scan", source_id=source["source_id"],
               scan_pass=scan_passes[-1])
    # The first observation deliberately records new files as pending. A second
    # explicit pass confirms their fingerprints stayed stable and indexes them.
    while scan_passes[-1]["totals"]["pending"] and len(scan_passes) < 3:
        scan_passes.append(
            scan_sources(database, source_id=source["source_id"], quiet_seconds=0)
        )
        checkpoint(f"generated_source_scan_{len(scan_passes)}", source_id=source["source_id"],
                   scan_pass=scan_passes[-1])
    if (any(not result.get("sources") or not result["sources"][0].get("complete")
            for result in scan_passes) or
            scan_passes[-1]["totals"]["pending"] != 0 or
            scan_passes[-1]["totals"]["indexed"] + scan_passes[-1]["totals"]["updated"] != 64):
        raise RuntimeError(f"Generated fixture scan did not index all 64 stable files: {scan_passes}")
    with sqlite3.connect(database) as db:
        scanned_asset_count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if scanned_asset_count != 64:
        raise RuntimeError(f"Generated fixture scan indexed {scanned_asset_count}, expected 64")
    checkpoint("generated_catalog_ready", source_id=source["source_id"],
               scan_passes=scan_passes, asset_count=scanned_asset_count,
               catalog_snapshot=_catalog_snapshot(database))

    app = QApplication(["defiantmaple-native-acceptance"])
    app.setOrganizationName("DefiantMaple")
    app.setApplicationName("DefiantMaple")
    app.setApplicationDisplayName("DefiantMaple")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    thumbnail_limits = ThumbnailLimits(timeout_seconds=6)
    preview_limits = PreviewLimits()
    catalog_before = _catalog_snapshot(database)
    checkpoint("catalog_before_viewer", catalog_snapshot=catalog_before)
    window = GalleryWindow(database, enable_thumbnails=True, cache_root=cache,
                           private_root=private)
    timer = None
    def cleanup_visible_probe():
        if timer is not None:
            timer.stop()
        for top_level in QApplication.topLevelWidgets():
            if isinstance(top_level, FullImageDialog):
                top_level.close()
        window.close()
        deadline = time.monotonic() + 6
        while window.thumbnails is not None and window.thumbnails.isRunning() and \
                time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
            time.sleep(0.005)
        if window.thumbnails is not None and window.thumbnails.isFinished() and window.isVisible():
            window.close()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        checkpoint("failure_exit_cleanup", window_closed=not window.isVisible(),
                   thumbnail_worker_stopped=(window.thumbnails is None or
                                             window.thumbnails.isFinished()),
                   process_tree_rss_bytes=_process_tree_rss_bytes())

    atexit.register(cleanup_visible_probe)
    source_index = window.source_box.findData(source["source_id"])
    if source_index < 0:
        raise RuntimeError("Generated fixture source is absent from the gallery source selector")
    window.source_box.setCurrentIndex(source_index)
    app.processEvents()
    if (window.source_box.currentData() != source["source_id"] or
            window.model.rowCount() != 64):
        raise RuntimeError("Gallery source selector did not show all 64 generated assets")
    checkpoint("gallery_source_selected", source_id=source["source_id"],
               model_row_count=window.model.rowCount(),
               selected_source_id=window.source_box.currentData())
    if any(cache.rglob("*.png")):
        raise AssertionError("Cold thumbnail phase started with existing PNG cache entries")
    checkpoint("cold_cache_empty", png_entries=[])
    heartbeat = {"ticks": 0, "times": [], "rss_samples": []}
    phase_started = time.perf_counter()
    completions = {}
    window.thumbnails.updated.connect(
        lambda asset_id: completions.setdefault(asset_id, time.perf_counter())
    )
    timer = QTimer()
    timer.setInterval(5)
    def sample_heartbeat():
        heartbeat["ticks"] += 1
        heartbeat["times"].append(time.perf_counter())
        if heartbeat["ticks"] % 10 == 0:
            value = _process_tree_rss_bytes()
            if value is not None:
                heartbeat["rss_samples"].append(value)
    timer.timeout.connect(sample_heartbeat)
    timer.start()

    window.show()
    app.processEvents()
    if app.platformName().lower() != "wayland" or os.environ.get("XDG_SESSION_TYPE") != "wayland":
        raise RuntimeError("Native acceptance requires a Qt Wayland platform in a Wayland session")
    checkpoint("native_wayland_window_shown", platform_name=app.platformName(),
               session_type=os.environ.get("XDG_SESSION_TYPE"),
               qwindow_exposed=bool(window.windowHandle() and window.windowHandle().isExposed()),
               source_provenance=provenance_before)

    rows = _asset_rows(window)
    by_name = {Path(row["current_path"]).name: (index, row)
               for index, row in enumerate(rows)}
    required = {"fictional-landscape.png", "fictional-portrait.png",
                "fictional-square.png", "fictional-alpha.png", "fictional-exif-6.jpg",
                "fictional-large-original.png"}
    if not required.issubset(by_name):
        raise RuntimeError(f"Catalog omitted generated fixtures: {required - by_name.keys()}")
    if len(by_name) != 64:
        raise AssertionError(f"Expected 64 supported generated images, got {len(by_name)}")

    # Flood the bounded queue, cancel stale queued generations with a fast scroll,
    # then let each visible target settle before moving the viewport again.
    cold = {}
    edge = 144
    requests = {name: (asset["asset_id"], asset["sha256"], asset["byte_size"], edge)
                for name, (_row, asset) in by_name.items()}
    for name, (_row, asset) in by_name.items():
        window.thumbnails.lookup(asset, edge)
    queue_length_at_initial_flood = window.thumbnails.requests.qsize()
    pending_at_initial_flood = len(window.thumbnails.pending)
    checkpoint("thumbnail_queue_flooded", queue_length=queue_length_at_initial_flood,
               pending_count=pending_at_initial_flood,
               queue_capacity=window.thumbnails.requests.maxsize,
               cache_png_count=sum(1 for _ in cache.rglob("*.png")))
    if queue_length_at_initial_flood > window.thumbnails.requests.maxsize:
        checkpoint("thumbnail_queue_capacity_gate_failed",
                   queue_length=queue_length_at_initial_flood,
                   pending_count=pending_at_initial_flood,
                   queue_capacity=window.thumbnails.requests.maxsize)
        raise AssertionError("Thumbnail queue exceeded its configured bound")
    # Change the active target while queued decodes are outstanding.
    requested_name = "fictional-landscape.png"
    for name in ("fictional-portrait.png", "fictional-square.png", requested_name):
        index, _asset = by_name[name]
        window.gallery.setCurrentIndex(window.model.index(index, 0))
        app.processEvents()
    selection_during_load = Path(window._selected_asset()["current_path"]).name
    checkpoint("selection_changed_during_cold_load", selected_name=selection_during_load,
               requested_final_name=requested_name,
               queue_length=window.thumbnails.requests.qsize(),
               pending_count=len(window.thumbnails.pending))

    deadline = time.monotonic() + 90
    names = list(by_name)
    for name in names:
        index, _asset = by_name[name]
        window.gallery.scrollTo(window.model.index(index, 0),
                                window.gallery.ScrollHint.PositionAtCenter)
        window.gallery.viewport().repaint()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    scroll_burst_steps = len(names)
    for name in names:
        index, asset = by_name[name]
        key = requests[name]
        window.gallery.scrollTo(window.model.index(index, 0),
                                window.gallery.ScrollHint.PositionAtCenter)
        window.gallery.viewport().repaint()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        window.thumbnails.lookup(asset, edge)
        per_item_deadline = min(deadline, time.monotonic() + 8)
        while key not in window.thumbnails.pixmaps and key not in window.thumbnails.errors:
            if time.monotonic() >= per_item_deadline:
                checkpoint("cold_thumbnail_timeout", name=name,
                           elapsed_ms=(time.perf_counter() - phase_started) * 1000,
                           completed_items=cold, heartbeat_ticks=heartbeat["ticks"],
                           queue_length=window.thumbnails.requests.qsize(),
                           pending_count=len(window.thumbnails.pending),
                           source_provenance=provenance_before,
                           catalog_before=catalog_before)
                raise TimeoutError(f"Visible thumbnail exceeded its bounded wait: {name}")
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
            time.sleep(0.005)
        if key in window.thumbnails.errors:
            checkpoint("cold_thumbnail_decode_failed", name=name,
                       error=window.thumbnails.errors[key], completed_items=cold,
                       source_provenance=provenance_before,
                       catalog_before=catalog_before)
            raise RuntimeError(f"Cold thumbnail failed for {name}")
    for name, (_row, asset) in by_name.items():
        key = requests[name]
        pixmap = window.thumbnails.pixmaps[key]
        completed_at = completions.get(asset["asset_id"], time.perf_counter())
        cold[name] = {"completion_from_window_show_ms":
                          (completed_at - phase_started) * 1000,
                      "width": pixmap.width(), "height": pixmap.height(),
                      "alpha": pixmap.toImage().hasAlphaChannel()}
        source_image = Image.open(asset["current_path"])
        expected_size = source_image.size
        if source_image.getexif().get(274) in (5, 6, 7, 8):
            expected_size = expected_size[::-1]
        source_image.close()
        expected_ratio = expected_size[0] / expected_size[1]
        actual_ratio = pixmap.width() / pixmap.height()
        aspect_gate_passed = abs(actual_ratio - expected_ratio) <= 0.015
        checkpoint("cold_thumbnail_aspect_gate", name=name,
                   measurement=cold[name], expected_size=list(expected_size),
                   expected_ratio=expected_ratio, actual_ratio=actual_ratio,
                   passed=aspect_gate_passed, cold_count=len(cold),
                   cold_phase_elapsed_ms=(time.perf_counter() - phase_started) * 1000,
                   source_provenance=provenance_before, catalog_before=catalog_before)
        if not aspect_gate_passed:
            raise AssertionError(f"Thumbnail aspect changed for {name}: {actual_ratio} vs {expected_ratio}")
    cold_phase_ended = time.perf_counter()
    heartbeat_times = [timestamp for timestamp in heartbeat["times"]
                       if phase_started <= timestamp <= cold_phase_ended]
    heartbeat_gaps_ms = [(right - left) * 1000
                         for left, right in zip(heartbeat_times, heartbeat_times[1:])]
    warm_started = time.perf_counter()
    warm_hits = sum(window.thumbnails.lookup(asset, edge)[0] is not None
                    for _index, asset in by_name.values())
    warm_elapsed_ms = (time.perf_counter() - warm_started) * 1000
    checkpoint("cold_loading_metrics_complete", cold_phase_elapsed_ms=(cold_phase_ended - phase_started) * 1000,
               cold_item_count=len(cold), heartbeat_ticks=len(heartbeat_times),
               heartbeat_gaps_ms=heartbeat_gaps_ms,
               warm_cache_hits=warm_hits, warm_lookup_elapsed_ms=warm_elapsed_ms,
               process_tree_rss_samples_bytes=heartbeat["rss_samples"],
               source_provenance=provenance_before,
               catalog_before=_catalog_snapshot(database))

    # Completion from old queued requests must not retarget the final selection.
    final_asset = window._selected_asset()
    if final_asset is None or Path(final_asset["current_path"]).name != requested_name or \
            selection_during_load != requested_name:
        checkpoint("stale_selection_gate_failed", selection_during_load=selection_during_load,
                   final_selected_name=(Path(final_asset["current_path"]).name
                                        if final_asset else None),
                   requested_name=requested_name)
        raise AssertionError("Selection changed to a stale completion target")
    checkpoint("stale_selection_gate_passed", selection_during_load=selection_during_load,
               final_selected_name=Path(final_asset["current_path"]).name,
               requested_name=requested_name)

    # Revisit each shape anchor so the native gallery screenshots show actual
    # delegated thumbnail rendering rather than only the final batch viewport.
    gallery_anchor_captures = {}
    for name in ("fictional-landscape.png", "fictional-portrait.png",
                 "fictional-square.png", "fictional-exif-6.jpg",
                 "fictional-alpha.png"):
        index, asset = by_name[name]
        window.gallery.setCurrentIndex(window.model.index(index, 0))
        window.gallery.scrollTo(window.model.index(index, 0),
                                window.gallery.ScrollHint.PositionAtCenter)
        window.gallery.viewport().repaint()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        if requests[name] not in window.thumbnails.pixmaps:
            raise AssertionError(f"Native gallery did not finish the visible thumbnail: {name}")
        capture_name = f"generated-gallery-{Path(name).stem}.png"
        if not window.grab().save(str(output / capture_name)):
            raise RuntimeError(f"Could not save app-window-only evidence for {name}")
        gallery_anchor_captures[name] = capture_name
        checkpoint("gallery_anchor_captured", anchor=name, capture=capture_name,
                   thumbnail_key=list(requests[name]),
                   thumbnail_dimensions=[window.thumbnails.pixmaps[requests[name]].width(),
                                         window.thumbnails.pixmaps[requests[name]].height()],
                   selected_name=Path(window._selected_asset()["current_path"]).name)
    # Capture the app window only; this does not screenshot the desktop.
    if not window.grab().save(str(output / "generated-gallery-window.png")):
        raise RuntimeError("Could not save app-window-only evidence image")
    qwindow = window.windowHandle()
    qt_identity = {
        "application_name": app.applicationName(),
        "display_name": app.applicationDisplayName(),
        "desktop_file_name": app.desktopFileName(),
        "canonical_app_id": APP_ID,
        "window_title": window.windowTitle(),
        "window_icon_null": window.windowIcon().isNull(),
        "window_icon_path_exists": ICON_PATH.is_file(),
        "desktop_entry_path": str(staged_desktop_entry),
        "desktop_entry_sha256": _sha256(staged_desktop_entry),
        "desktop_entry_source_sha256": _sha256(packaged_desktop_entry),
        "desktop_icon_path": str(staged_icon),
        "desktop_icon_sha256": _sha256(staged_icon),
        "desktop_icon_source_sha256": _sha256(packaged_icon),
        "window_handle_class": type(qwindow).__name__ if qwindow else None,
        "window_handle_properties": [bytes(value).decode("utf-8", "replace")
                                     for value in qwindow.dynamicPropertyNames()] if qwindow else [],
    }
    checkpoint("qt_identity_captured", identity=qt_identity)

    # Inspect the original EXIF asset, then exercise fit, zoom, pan mode, alpha control.
    exif_index, exif_asset = by_name["fictional-exif-6.jpg"]
    window.gallery.setCurrentIndex(window.model.index(exif_index, 0))
    window.gallery.setFocus()
    QTest.keyClick(window.gallery, Qt.Key.Key_Return)
    dialog: FullImageDialog = window.inspect_dialog
    if dialog is None:
        checkpoint("exif_viewer_open_failed", selected_asset_id=exif_asset["asset_id"],
                   selected_name=Path(exif_asset["current_path"]).name)
        raise AssertionError("Enter did not open the selected full-image dialog")
    dialog.show()
    if not _wait(app, lambda: dialog.canvas._item is not None or
                 dialog.status.text().startswith(("ValueError:", "OSError:", "Decoder error"))):
        raise TimeoutError("Full-image dialog did not produce a terminal state")
    image_item = dialog.canvas._item
    if image_item is None:
        raise RuntimeError(f"Full-image decode failed: {dialog.status.text()}")
    original_size = image_item.pixmap().size()
    if (original_size.width(), original_size.height()) != (180, 320):
        checkpoint("exif_decode_gate_failed", actual_size=[original_size.width(), original_size.height()],
                   expected_size=[180, 320], dialog_status=dialog.status.text())
        raise AssertionError(f"EXIF orientation was not applied: {original_size}")
    checkpoint("exif_original_decoded", asset_id=exif_asset["asset_id"],
               dimensions=[original_size.width(), original_size.height()],
               dialog_status=dialog.status.text(), focus_on_open=_focus_report(app, dialog),
               canvas=_canvas_report(dialog))

    # Ask the native window to activate, then verify real Qt focus before using
    # keyboard shortcuts. Do not force a child focus if the dialog fails to get it.
    dialog.activateWindow()
    dialog.raise_()
    activation_focus_acquired = _wait(
        app, lambda: (_focus_report(app, dialog)["focus_widget_inside_dialog"] and
                      dialog.isActiveWindow()), timeout=3.0
    )
    focus_after_activation = _focus_report(app, dialog)
    checkpoint("dialog_activation_focus", activation_focus_acquired=activation_focus_acquired,
               focus=focus_after_activation, canvas=_canvas_report(dialog))

    before_zoom = dialog.canvas._scale
    dialog.zoom_in_button.click()
    zoomed = dialog.canvas._scale
    dialog.fit_button.click()
    fitted = dialog.canvas._scale
    dialog.background_box.setCurrentText("Dark")
    dialog.background_box.setCurrentText("Light")
    dialog.background_box.setCurrentText("Checker")
    pan_enabled = (dialog.canvas.dragMode().name == "ScrollHandDrag")
    fit_zoom_gate = {"zoom_increased_scale": zoomed > before_zoom,
                     "fit_scale_positive": fitted > 0,
                     "pan_mode_enabled": pan_enabled}
    checkpoint("fit_zoom_pan_mode_gate", gate=fit_zoom_gate,
               scale_before_zoom=before_zoom, scale_after_zoom=zoomed,
               scale_after_fit=fitted, canvas=_canvas_report(dialog))

    # Zoom until both axes have enough overflow for a measurable drag.
    pan_zoom_steps = 0
    while (dialog.canvas.horizontalScrollBar().maximum() -
           dialog.canvas.horizontalScrollBar().minimum() <= 70 or
           dialog.canvas.verticalScrollBar().maximum() -
           dialog.canvas.verticalScrollBar().minimum() <= 70) and pan_zoom_steps < 12:
        dialog.zoom_in_button.click()
        pan_zoom_steps += 1
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
    viewport = dialog.canvas.viewport()
    pan_start = viewport.rect().center()
    pan_end = pan_start + QPoint(-70, -70)
    horizontal = dialog.canvas.horizontalScrollBar()
    vertical = dialog.canvas.verticalScrollBar()
    enough_pan_overflow = (horizontal.maximum() - horizontal.minimum() > 70 and
                           vertical.maximum() - vertical.minimum() > 70)
    if enough_pan_overflow:
        horizontal.setValue((horizontal.minimum() + horizontal.maximum()) // 2)
        vertical.setValue((vertical.minimum() + vertical.maximum()) // 2)
    canvas_before_pan = _canvas_report(dialog)
    if enough_pan_overflow:
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=pan_start)
        QTest.mouseMove(viewport, pan_end, 50)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=pan_end)
        _wait(app, lambda: True, timeout=0.1)
    canvas_after_pan = _canvas_report(dialog)
    scroll_before_pan = (canvas_before_pan["horizontal_scroll"]["value"],
                         canvas_before_pan["vertical_scroll"]["value"])
    scroll_after_pan = (canvas_after_pan["horizontal_scroll"]["value"],
                        canvas_after_pan["vertical_scroll"]["value"])
    pan_moved_view = enough_pan_overflow and scroll_before_pan != scroll_after_pan
    focus_before_f11 = _focus_report(app, dialog)

    # Deliver F11/Escape to the actual focused descendant when it belongs to
    # the dialog, as a keyboard user would; retain all states on any failure.
    keyboard_target = app.focusWidget()
    if keyboard_target is None or not dialog.isAncestorOf(keyboard_target):
        keyboard_target = dialog
    normal_geometry = (dialog.width(), dialog.height())
    QTest.keyClick(keyboard_target, Qt.Key.Key_F11)
    fullscreen_enter_state = _wait_fullscreen_state(app, dialog, fullscreen=True)
    fullscreen_entered = fullscreen_enter_state["matched_stable_state"]
    checkpoint("f11_enter_transition", target_class=type(keyboard_target).__name__,
               focus=focus_before_f11, focus_after=_focus_report(app, dialog),
               state_wait=fullscreen_enter_state)
    QTest.keyClick(keyboard_target, Qt.Key.Key_F11)
    fullscreen_exit_state = _wait_fullscreen_state(
        app, dialog, fullscreen=False, normal_size=normal_geometry
    )
    fullscreen_exited = fullscreen_exit_state["matched_stable_state"]
    checkpoint("f11_exit_transition", target_class=type(keyboard_target).__name__,
               focus_after=_focus_report(app, dialog),
               state_wait=fullscreen_exit_state,
               expected_normal_geometry=list(normal_geometry))
    if not dialog.grab().save(str(output / "generated-full-image-window.png")):
        raise RuntimeError("Could not save app-only full-image window evidence")
    QTest.keyClick(keyboard_target, Qt.Key.Key_Escape)
    escape_immediate = {"visible": dialog.isVisible(),
                        "worker_running": dialog.worker.isRunning(),
                        "close_pending": dialog._close_pending}
    escape_close_waited = _wait(app, lambda: not dialog.isVisible(), timeout=3.0)
    escape_closed = escape_close_waited and not dialog.isVisible()
    escape_after_wait = {"visible": dialog.isVisible(),
                         "worker_running": dialog.worker.isRunning(),
                         "close_pending": dialog._close_pending}
    final_focus_report = _focus_report(app, dialog)
    final_canvas_report = _canvas_report(dialog)
    control_gate = {
        "fit_zoom_pan_mode_controls_passed": all(fit_zoom_gate.values()),
        "focus_inside_dialog_after_activation": activation_focus_acquired,
        "focus_inside_dialog_before_f11": focus_before_f11["focus_widget_inside_dialog"],
        "pan_overflow_on_both_axes": enough_pan_overflow,
        "pan_changed_scroll_position": pan_moved_view,
        "f11_enter_stable": fullscreen_entered,
        "f11_exit_stable_and_normal_geometry_restored": fullscreen_exited,
        "escape_closed_dialog": escape_closed,
    }
    checkpoint("full_image_control_gate", gate=control_gate,
               fit_zoom=fit_zoom_gate, pan_zoom_steps=pan_zoom_steps,
               canvas_before_pan=canvas_before_pan, canvas_after_pan=canvas_after_pan,
               focus_before_f11=focus_before_f11, focus_after_close=final_focus_report,
               fullscreen_enter_state=fullscreen_enter_state,
               fullscreen_exit_state=fullscreen_exit_state,
               escape_close_waited=escape_close_waited,
               escape_immediate=escape_immediate,
               escape_after_wait=escape_after_wait,
               dialog_after_escape=final_canvas_report)
    if not all(control_gate.values()):
        raise AssertionError(f"Full-image controls failed: {control_gate}")

    alpha_index, alpha_asset = by_name["fictional-alpha.png"]
    window.gallery.setCurrentIndex(window.model.index(alpha_index, 0))
    window.gallery.setFocus()
    QTest.keyClick(window.gallery, Qt.Key.Key_Return)
    alpha_dialog: FullImageDialog = window.inspect_dialog
    if alpha_dialog is None or not _wait(app, lambda: alpha_dialog.canvas._item is not None):
        raise TimeoutError("Alpha original full-image preview did not load")
    alpha_preview_has_channel = alpha_dialog.canvas._item.pixmap().toImage().hasAlphaChannel()
    alpha_dialog.background_box.setCurrentText("Checker")
    checker_brush = alpha_dialog.canvas.backgroundBrush()
    alpha_dialog.background_box.setCurrentText("Light")
    light_brush = alpha_dialog.canvas.backgroundBrush()
    alpha_dialog.background_box.setCurrentText("Dark")
    dark_color = alpha_dialog.canvas.backgroundBrush().color().name()
    alpha_control_gate = {
        "original_has_alpha_channel": alpha_preview_has_channel,
        "checker_differs_from_light": checker_brush.style() != light_brush.style(),
        "dark_background_color": dark_color == "#222222",
    }
    checkpoint("alpha_preview_control_gate", gate=alpha_control_gate,
               checker_style=checker_brush.style().name,
               light_style=light_brush.style().name, dark_color=dark_color,
               canvas=_canvas_report(alpha_dialog))
    if not all(alpha_control_gate.values()):
        raise AssertionError("Alpha preview or selectable checker/light/dark background failed")
    alpha_dialog.close()
    app.processEvents()

    large_index, large_asset = by_name["fictional-large-original.png"]
    window.gallery.setCurrentIndex(window.model.index(large_index, 0))
    window.gallery.setFocus()
    QTest.keyClick(window.gallery, Qt.Key.Key_Return)
    large_dialog: FullImageDialog = window.inspect_dialog
    if large_dialog is None:
        raise AssertionError("Enter did not open the large original image")
    if not _wait(app, lambda: large_dialog.canvas._item is not None or
                 large_dialog.status.text().startswith(("ValueError:", "OSError:", "Decoder error"))):
        raise TimeoutError("Large full-image decode did not complete")
    large_size = large_dialog.canvas._item.pixmap().size() if large_dialog.canvas._item else None
    if large_size is None or (large_size.width(), large_size.height()) != (1920, 1200):
        raise AssertionError(f"Full viewer did not use original large pixels: {large_size}")
    if not large_dialog.grab().save(str(output / "generated-large-original-window.png")):
        raise RuntimeError("Could not save app-only large-original window evidence")
    checkpoint("large_original_decoded_and_captured", asset_id=large_asset["asset_id"],
               dimensions=[large_size.width(), large_size.height()],
               capture="generated-large-original-window.png",
               dialog_status=large_dialog.status.text())
    compositor_identity = _kwin_identity(output, os.getpid(), progress=checkpoint)
    if any(row["desktop_file_name"] != APP_ID or
           row["resource_class"].casefold() != APP_ID.casefold()
           for row in compositor_identity["windows"]):
        raise AssertionError(f"KWin window identity does not match {APP_ID}: {compositor_identity}")
    (output / "kwin-compositor-identity.json").write_text(
        json.dumps(compositor_identity, indent=2) + "\n", encoding="utf-8"
    )
    large_dialog.close()
    app.processEvents()

    image = QImage(str(fixture / "fictional-alpha.png"))
    alpha_source = image.hasAlphaChannel()
    if not alpha_source:
        raise AssertionError("Generated alpha fixture unexpectedly has no alpha channel")
    image = QImage()

    source_digests_after = {path.name: _sha256(path) for path in sorted(fixture.iterdir())}
    if source_digests_before != source_digests_after:
        raise AssertionError("Generated source fixture changed during read-only acceptance")
    with sqlite3.connect(database) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        asset_count = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if integrity != "ok":
        raise AssertionError(f"Catalog integrity check failed: {integrity}")
    catalog_after = _catalog_snapshot(database)
    if catalog_before != catalog_after:
        checkpoint("catalog_unchanged_gate_failed", before=catalog_before,
                   after=catalog_after, integrity=integrity)
        raise AssertionError("Viewer interactions changed catalog asset or metadata state")
    checkpoint("catalog_unchanged_gate_passed", before=catalog_before,
               after=catalog_after, integrity=integrity)
    provenance_after = _source_provenance(repo)
    if provenance_before["source_sha256"] != provenance_after["source_sha256"]:
        checkpoint("source_provenance_unchanged_gate_failed",
                   before=provenance_before, after=provenance_after)
        raise AssertionError("Measured source files changed during native acceptance")
    checkpoint("source_provenance_unchanged_gate_passed", before=provenance_before,
               after=provenance_after)

    screen = window.screen()
    result = {
        "schema": "defiantmaple.gallery-native-acceptance.v1",
        "host": {"distribution": platform.platform(),
                 "os_release": _os_release(),
                 "machine": platform.machine(),
                 "logical_cpu_count": os.cpu_count(),
                 "physical_memory_bytes": _physical_memory_bytes(),
                 "python": platform.python_version(),
                 "qt": qVersion(),
                 "pyside": __import__("PySide6").__version__,
                 "display_backend": app.platformName(),
                 "session_type": os.environ.get("XDG_SESSION_TYPE"),
                 "wayland_display_present": bool(os.environ.get("WAYLAND_DISPLAY")),
                 "screen_size_px": ([screen.size().width(), screen.size().height()]
                                     if screen else None),
                 "device_pixel_ratio": screen.devicePixelRatio() if screen else None},
        "fixture": {"root": str(fixture), "file_sha256": source_digests_after,
                    "asset_count": asset_count, "source_id": source["source_id"],
                    "scan_passes": scan_passes},
        "source_provenance_before": provenance_before,
        "source_provenance_after": provenance_after,
        "catalog": {"path": str(database), "integrity_check": integrity},
        "catalog_snapshot_before": catalog_before,
        "catalog_snapshot_after": catalog_after,
        "thumbnails": {"edge": edge,
                       "cold_scope": "completion from window show, including queueing",
                       "cold_phase_elapsed_ms": (cold_phase_ended - phase_started) * 1000,
                       "queue_length_at_initial_flood": queue_length_at_initial_flood,
                       "pending_count_at_initial_flood": pending_at_initial_flood,
                       "scroll_burst_steps_while_work_queued": scroll_burst_steps,
                       "cold": cold,
                       "warm_cache_hits": warm_hits,
                       "warm_lookup_elapsed_ms": warm_elapsed_ms,
                       "heartbeat_ticks_during_cold_phase": len(heartbeat_times),
                       "heartbeat_gap_ms_sample_count": len(heartbeat_gaps_ms),
                       "heartbeat_gap_ms_p95_nearest_rank": sorted(heartbeat_gaps_ms)[
                           max(0, math.ceil(0.95 * len(heartbeat_gaps_ms)) - 1)]
                           if heartbeat_gaps_ms else None,
                       "heartbeat_gap_ms_max": max(heartbeat_gaps_ms)
                           if heartbeat_gaps_ms else None,
                       "sampled_process_tree_rss_bytes_peak": max(heartbeat["rss_samples"])
                           if heartbeat["rss_samples"] else None,
                       "worker_threads": 1,
                       "queue_capacity": window.thumbnails.requests.maxsize,
                       "decoder_max_source_bytes": thumbnail_limits.max_source_bytes,
                       "decoder_max_dimension": thumbnail_limits.max_dimension,
                       "decoder_max_pixels": thumbnail_limits.max_pixels,
                       "decoder_timeout_seconds": thumbnail_limits.timeout_seconds,
                       "per_visible_item_deadline_seconds": 8,
                       "overall_cold_phase_deadline_seconds": 90},
        "selection": {"requested_name": requested_name,
                      "selected_name_during_load": selection_during_load,
                      "selected_asset_id": final_asset["asset_id"],
                      "selected_name": Path(final_asset["current_path"]).name},
        "full_image": {"selected_asset_id": exif_asset["asset_id"],
                       "oriented_original_dimensions": [original_size.width(), original_size.height()],
                       "scale_before_zoom": before_zoom, "scale_after_zoom": zoomed,
                       "scale_after_fit": fitted, "pan_mode": pan_enabled,
                       "pan_changed_scroll_position": pan_moved_view,
                       "keyboard_focus_inside_dialog": control_gate[
                           "focus_inside_dialog_before_f11"],
                       "fullscreen_entered_with_f11": fullscreen_entered,
                       "fullscreen_exited_with_f11": fullscreen_exited,
                       "escape_closed_dialog": escape_closed,
                       "alpha_source_has_channel": alpha_source,
                       "alpha_preview_has_channel": alpha_preview_has_channel,
                       "alpha_dark_background": dark_color,
                       "dialog_status": dialog.status.text()},
        "large_full_image": {"asset_id": large_asset["asset_id"],
                             "original_dimensions": [large_size.width(), large_size.height()],
                             "limit_bytes": preview_limits.max_source_bytes,
                             "limit_dimension": preview_limits.max_dimension,
                             "limit_pixels": preview_limits.max_pixels,
                             "timeout_seconds": preview_limits.timeout_seconds},
        "qt_identity": qt_identity,
        "gallery_anchor_captures": gallery_anchor_captures,
        "kde_compositor_identity": compositor_identity,
        "privacy": {"capture": "generated GalleryWindow QWidget only",
                    "source_hashes_unchanged": source_digests_before == source_digests_after,
                    "cache_root": str(cache), "private_root": str(private)},
        "candidate_budget_note": "SDD §19.2 figures remain unadopted; observations are not pass/fail budgets.",
        "probe_cap_seconds": 120,
    }
    timer.stop()
    window.close()
    _wait(app, lambda: not window.isVisible(), timeout=5)
    if window.thumbnails is not None and not window.thumbnails.isFinished():
        checkpoint("thumbnail_worker_shutdown_gate_failed",
                   window_closed=not window.isVisible(),
                   thumbnail_worker_running=window.thumbnails.isRunning(),
                   source_provenance=provenance_before,
                   catalog_before=catalog_before)
        raise RuntimeError("Thumbnail worker did not stop cleanly")
    checkpoint("normal_cleanup_complete", window_closed=not window.isVisible(),
               thumbnail_worker_stopped=window.thumbnails.isFinished())
    result["cleanup"] = {"window_closed": not window.isVisible(),
                         "thumbnail_worker_stopped": window.thumbnails.isFinished()}
    (output / "native-acceptance.json").write_text(json.dumps(result, indent=2) + "\n",
                                                   encoding="utf-8")
    _ACTIVE_PARTIAL_RECEIPT["attempt_status"] = "complete"
    if _ACTIVE_PARTIAL_PATH is not None:
        stages_path = output / "native-acceptance-stages.json"
        stages_temporary = stages_path.with_suffix(".json.tmp")
        stages_temporary.write_text(
            json.dumps(_ACTIVE_PARTIAL_RECEIPT, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(stages_temporary, stages_path)
        if _ACTIVE_PARTIAL_PATH.exists():
            _ACTIVE_PARTIAL_PATH.unlink()
        _ACTIVE_PARTIAL_PATH = stages_path
    _ACTIVE_PARTIAL_RECEIPT["completed"] = True
    return result


def main(argv=None) -> int:
    def graceful_sigterm(_signum, _frame):
        raise KeyboardInterrupt("Native acceptance stopped by the 120-second external cap")

    signal.signal(signal.SIGTERM, graceful_sigterm)
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new or empty evidence directory outside Git")
    args = parser.parse_args(argv)
    try:
        result = run(args.output)
    except BaseException as exc:
        _flush_partial_receipt(exc)
        raise
    print(json.dumps({"evidence": str(args.output.resolve()),
                      "catalog_integrity": result["catalog"]["integrity_check"],
                      "selected": result["selection"]["selected_name"],
                      "app_id": result["qt_identity"]["desktop_file_name"],
                      "compositor": "recorded separately"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
