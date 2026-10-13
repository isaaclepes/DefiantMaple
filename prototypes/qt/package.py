"""Build and measure the unsigned Qt prototype artifact."""
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from prototypes.qt.identity import APP_ID


def find_artifact(*roots: Path) -> Path:
    bundle_candidates = []
    file_candidates = []
    for root in roots:
        bundle_candidates.extend(path for path in root.rglob("DefiantMapleQt.app") if path.is_dir())
        file_candidates.extend(
            path for path in root.rglob("DefiantMapleQt*")
            if path.is_file() and not any(parent.suffix == ".app" for parent in path.parents)
        )
    candidates = bundle_candidates or file_candidates
    if not candidates:
        raise FileNotFoundError("pyside6-deploy produced no DefiantMapleQt artifact")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def bundle_launchable(bundle: Path) -> Path:
    executable_dir = bundle / "Contents" / "MacOS"
    preferred = executable_dir / bundle.stem
    if preferred.is_file():
        return preferred
    executables = [
        path for path in executable_dir.iterdir()
        if path.is_file() and os.access(path, os.X_OK)
    ]
    if len(executables) != 1:
        raise FileNotFoundError(f"could not identify application executable in {executable_dir}")
    return executables[0]


def add_nuitka_download_consent(spec: Path) -> None:
    config = ConfigParser()
    config.read(spec, encoding="utf-8")
    extra_args = config.get("nuitka", "extra_args", fallback="")
    config.set("nuitka", "extra_args", f"{extra_args} --assume-yes-for-downloads".strip())
    with spec.open("w", encoding="utf-8") as stream:
        config.write(stream)


def stage_linux_desktop_files(artifact: Path) -> Path:
    """Keep the desktop entry and icon beside the Linux build for local install."""
    source = Path(__file__).with_name("assets")
    target = artifact.parent / "DefiantMapleQt-linux-desktop"
    target.mkdir(parents=True, exist_ok=True)
    for suffix in ("desktop", "png"):
        shutil.copy2(source / f"{APP_ID}.{suffix}", target / f"{APP_ID}.{suffix}")
    return target


def frozen_gallery_filter_smoke(launchable: Path, environment: dict[str, str]) -> None:
    """Run one isolated, read-only filter smoke against the built executable."""
    import hashlib
    import sqlite3
    import uuid
    from contextlib import closing

    from defiantmaple.catalog import connect, initialize

    fixture = Path(tempfile.mkdtemp(prefix="defiantmaple-gallery-filter-smoke-"))
    verified_cleanup = False
    try:
        catalog = fixture / "generated.sqlite3"
        amber = fixture / "generated-sources" / "amber"
        cobalt = fixture / "generated-sources" / "cobalt"
        scratch = fixture / "owned"
        for directory in (amber, cobalt, scratch / "cache", scratch / "private"):
            directory.mkdir(parents=True)
        paths = (amber / "alpha.png", cobalt / "bravo.jpg", amber / "charlie.png")
        for number, path in enumerate(paths):
            path.write_bytes(b"fictional gallery filter source " + bytes([number]))
        initialize(catalog)
        ids = {name: str(uuid.uuid4()) for name in
               ("amber", "cobalt", "parent", "child", "unassigned",
                "character", "artist", "alpha", "bravo", "charlie")}
        with connect(catalog) as db:
            for name, root in (("Amber", amber), ("Cobalt", cobalt)):
                db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                           "VALUES(?,?,?,'inbox','paused')",
                           (ids[name.lower()], name, str(root)))
            for name in ("Parent", "Child", "Unassigned"):
                db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                           (ids[name.lower()], name, name.casefold()))
            for number in range(65):
                name = f"Topic {number:03}"
                db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                           (str(uuid.uuid4()), name, name.casefold()))
            db.execute("INSERT INTO tag_aliases(tag_id,alias,normalized_alias) VALUES(?,'Night Study','night study')",
                       (ids["parent"],))
            for category, key in (("Character", "character"), ("Artist", "artist")):
                db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) "
                           "VALUES(?,?,'Phoenix','phoenix')", (ids[key], category))
            for number, (name, path, source, state, favorite) in enumerate((
                ("alpha", paths[0], "amber", "reviewed", 1),
                ("bravo", paths[1], "cobalt", "needs_review", 0),
                ("charlie", paths[2], "amber", "reviewed", 1),
            )):
                info = path.stat()
                db.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
                           "workflow_state,source_id,discovered_at,rating,favorite) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (ids[name], str(path), "image/jpeg" if name == "bravo" else "image/png",
                            f"generated-digest-{number}", info.st_size, state, ids[source],
                            f"2026-01-01T00:00:0{number + 1}Z", number + 1, favorite))
                db.execute("INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                           "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
                           "VALUES(?,?,?,?,?,?,?,?,0,'indexed',?)",
                           (str(path), ids[source], info.st_size, info.st_mtime_ns,
                            str(info.st_dev), str(info.st_ino), info.st_mtime_ns,
                            info.st_mtime_ns, ids[name]))
                db.execute("INSERT INTO asset_tags(asset_id,tag_id) VALUES(?,?)",
                           (ids[name], ids["child" if name == "charlie" else "parent"]))
                db.execute("INSERT INTO asset_entities(asset_id,entity_id) VALUES(?,?)",
                           (ids[name], ids["artist" if name == "bravo" else "character"]))

        def snapshot():
            with closing(sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)) as db:
                logical = tuple(db.iterdump())
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Gallery smoke catalog integrity failed")
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Gallery smoke foreign keys failed")
            physical = {}
            for suffix in ("", "-wal", "-shm", "-journal"):
                path = Path(str(catalog) + suffix)
                physical[suffix or "main"] = (
                    (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size,
                     path.stat().st_mtime_ns) if path.is_file() else None)
            owned = {}
            for root in (amber, cobalt, scratch):
                owned[str(root.relative_to(fixture))] = tuple(
                    (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest(),
                     path.stat().st_size, path.stat().st_mtime_ns)
                    for path in sorted(root.rglob("*")) if path.is_file())
            return logical, physical, owned

        before = snapshot()
        smoke_environment = environment.copy()
        smoke_environment.pop("PYTHONPATH", None)
        smoke_environment.pop("PYTHONHOME", None)
        smoke_environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        command = [
            str(launchable), "--catalog", str(catalog),
            "--smoke-gallery-filters", "--smoke-cache-root", str(scratch),
            "--smoke-source-root", str(amber),
            "--smoke-source-root", str(cobalt),
        ]

        def retain_failure(reason, stdout, stderr, exit_code, *, timed_out=False):
            # This private sibling is outside the before/after scratch snapshot.
            # Preserve exact child streams and the fixture if the smoke fails.
            diagnostic = fixture / "private-smoke-diagnostic"
            diagnostic.mkdir(exist_ok=True)
            (diagnostic / "stdout.bin").write_bytes(stdout or b"")
            (diagnostic / "stderr.bin").write_bytes(stderr or b"")
            try:
                after_failure = snapshot()
                snapshot_error = None
            except Exception as exc:
                after_failure = None
                snapshot_error = repr(exc)
            source_files = (Path(__file__), Path(__file__).with_name("app.py"),
                            Path(__file__).with_name("gallery_filter_smoke.py"))
            receipt = {
                "reason": reason, "command": command, "cwd": str(fixture),
                "exit_code": exit_code, "timed_out": timed_out,
                "child_reaped": True,
                "stdout_sha256": hashlib.sha256(stdout or b"").hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr or b"").hexdigest(),
                "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in source_files},
                "before_snapshot": before, "after_snapshot": after_failure,
                "snapshot_error": snapshot_error,
            }
            (diagnostic / "receipt.json").write_text(
                json.dumps(receipt, indent=2, default=str), encoding="utf-8")

        try:
            completed = subprocess.run(command, cwd=fixture, env=smoke_environment,
                                       capture_output=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            # subprocess.run kills and waits for the child before raising.
            retain_failure("timeout", exc.stdout, exc.stderr, None, timed_out=True)
            raise ValueError("Frozen gallery filter smoke timed out; generated fixture retained") from exc
        if completed.returncode != 0:
            retain_failure("nonzero exit", completed.stdout, completed.stderr,
                           completed.returncode)
            raise ValueError("Frozen gallery filter smoke failed; generated fixture retained")
        expected = {"schema": "defiantmaple.gallery-filter-smoke.v1", "status": "passed",
                    "bounded_first_page": 64, "bounded_more_page": 4,
                    "composed_matches": 1, "clear_matches": 3, "prior_matches": 2,
                    "stale_refused": True, "source_io_calls": 0, "close_complete": True}
        # Qt may write platform diagnostics to stderr; stdout is a single,
        # strictly checked JSON object. Failed streams stay in the private receipt.
        try:
            actual = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            actual = None
        if actual != expected or b"Traceback" in completed.stderr:
            retain_failure("output mismatch", completed.stdout, completed.stderr,
                           completed.returncode)
            raise ValueError("Frozen gallery filter smoke output differed; generated fixture retained")
        if snapshot() != before:
            retain_failure("read-only snapshot mismatch", completed.stdout,
                           completed.stderr, completed.returncode)
            raise ValueError("Frozen gallery filter smoke changed generated catalog, media or cache")
        verified_cleanup = True
    finally:
        # subprocess.run has reaped the child, including on timeout.  A failed
        # smoke retains its private fixture for diagnosis and ownership review.
        if verified_cleanup:
            shutil.rmtree(fixture)


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    args = parser.parse_args(argv)
    executable = "pyside6-deploy.exe" if sys.platform == "win32" else "pyside6-deploy"
    environment_deploy = Path(sys.executable).parent / executable
    deploy = str(environment_deploy) if environment_deploy.exists() else shutil.which(executable)
    if not deploy:
        parser.error("pyside6-deploy is not installed")
    entry = Path(__file__).with_name("app.py")
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    # pyside6-deploy runs Nuitka from prototypes/qt, outside the package root.
    # Keep the gallery's catalog/scanner/decoder modules discoverable for the
    # standalone binary on every target OS.
    environment["PYTHONPATH"] = (str(entry.parents[2]) + os.pathsep
                                 + environment.get("PYTHONPATH", ""))
    cache_root = Path(tempfile.gettempdir()) / "defiantmaple-nuitka-cache"
    shutil.rmtree(cache_root, ignore_errors=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    environment["XDG_CACHE_HOME"] = str(cache_root)
    for root in {Path.cwd().resolve(), entry.parent.resolve()}:
        for name in ("DefiantMapleQt", "DefiantMapleQt.bin", "DefiantMapleQt.exe", "DefiantMapleQt.app"):
            stale = root / name
            if stale.is_dir():
                shutil.rmtree(stale)
            elif stale.exists():
                stale.unlink()
    spec = entry.parent / "pysidedeploy.spec"
    if spec.exists():
        spec.unlink()
    deploy_command = [
        deploy, str(entry), "-f", "--name", "DefiantMapleQt",
        "--nuitka-version", "4.2.2",
        "--extra-ignore-dirs", "tests,__pycache__",
    ]
    if sys.platform == "win32":
        subprocess.run(
            [*deploy_command, "--init"],
            cwd=entry.parent,
            check=True,
            env=environment,
        )
        add_nuitka_download_consent(spec)
        deploy_command = [
            deploy, "-c", str(spec), "-f", "--nuitka-version", "4.2.2",
        ]
    started = time.perf_counter()
    subprocess.run(deploy_command, cwd=entry.parent, check=True, env=environment)
    build_seconds = time.perf_counter() - started

    artifact = find_artifact(Path.cwd(), entry.parent)
    if artifact.is_dir():
        artifact_bytes = sum(path.stat().st_size for path in artifact.rglob("*") if path.is_file())
        launchable = bundle_launchable(artifact)
    else:
        artifact_bytes = artifact.stat().st_size
        launchable = artifact
    desktop_files = stage_linux_desktop_files(artifact) if sys.platform.startswith("linux") else None
    benchmark_environment = environment.copy()
    benchmark_environment.pop("PYTHONPATH", None)
    benchmark_environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    identity_output = subprocess.run(
        [str(launchable), "--smoke-identity"], check=True,
        env=benchmark_environment, capture_output=True, text=True,
    )
    identity = json.loads(identity_output.stdout)
    if identity != {"application_name": "DefiantMaple",
                    "desktop_file_name": APP_ID,
                    "window_icon_available": True}:
        raise ValueError(f"Frozen desktop identity smoke failed: {identity}")
    # Verify that the frozen binary includes our package and that Pillow's
    # spawned decoder works, not only the placeholder-only 100k grid.
    from PIL import Image
    from defiantmaple.catalog import index_file, initialize
    with tempfile.TemporaryDirectory(prefix="defiantmaple-package-smoke-") as temporary:
        smoke = Path(temporary).resolve(strict=True)
        media = smoke / "fictional.png"
        Image.new("RGBA", (48, 40), (90, 140, 180, 100)).save(media)
        smoke_catalog = smoke / "library.sqlite3"
        initialize(smoke_catalog)
        smoke_asset_id = index_file(smoke_catalog, media)
        completed = subprocess.run([
            str(launchable), "--catalog", str(smoke_catalog),
            "--smoke-thumbnail-id", smoke_asset_id,
            "--smoke-cache-root", str(smoke / "cache"),
        ], check=True, env=benchmark_environment, capture_output=True, text=True)
        smoke_result = json.loads(completed.stdout)
        if smoke_result["width"] <= 0 or smoke_result["height"] <= 0:
            raise ValueError("Frozen thumbnail decoder returned invalid dimensions")
        worker_completed = subprocess.run([
            str(launchable), "--catalog", str(smoke_catalog),
            "--smoke-worker-thumbnail-id", smoke_asset_id,
            "--smoke-cache-root", str(smoke / "worker-cache"),
        ], check=True, env=benchmark_environment, capture_output=True, text=True)
        worker_result = json.loads(worker_completed.stdout)
        if worker_result["width"] <= 0 or worker_result["height"] <= 0:
            raise ValueError("Frozen gallery thumbnail worker returned invalid dimensions")
        # Exercise the actual spawned external UI worker through final READY,
        # withholding its one-time permit. This never launches an association.
        import hashlib
        before_probe = (hashlib.sha256(media.read_bytes()).hexdigest(), media.stat().st_mtime_ns,
                        hashlib.sha256(smoke_catalog.read_bytes()).hexdigest())
        probe_completed = subprocess.run([
            str(launchable), "--catalog", str(smoke_catalog),
            "--smoke-external-probe-id", smoke_asset_id,
        ], check=True, env=benchmark_environment, capture_output=True, text=True, timeout=15)
        probe_result = json.loads(probe_completed.stdout)
        if probe_result != {"status": "probe_ready", "permit_sent": False,
                            "dispatched": False, "cleanup_complete": True}:
            raise ValueError("Frozen external worker did not complete its read-only no-permit probe")
        after_probe = (hashlib.sha256(media.read_bytes()).hexdigest(), media.stat().st_mtime_ns,
                       hashlib.sha256(smoke_catalog.read_bytes()).hexdigest())
        if after_probe != before_probe:
            raise ValueError("Frozen external worker probe changed its generated source or catalog")
        # Fifth smoke uses the actual cache-only QThread -> spawned service ->
        # owned RGBA QImage delivery. Captured original path absent in scratch.
        moved_media = smoke / "fictional-unavailable.png"
        media.rename(moved_media)
        before_cached = (hashlib.sha256(moved_media.read_bytes()).hexdigest(),
                         moved_media.stat().st_mtime_ns,
                         hashlib.sha256(smoke_catalog.read_bytes()).hexdigest())
        cache_before = {str(path.relative_to(smoke / "cache")): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (smoke / "cache").rglob("*") if path.is_file()}
        cached_completed = subprocess.run([
            str(launchable), "--catalog", str(smoke_catalog),
            "--smoke-cached-preview-id", smoke_asset_id,
            "--smoke-cache-root", str(smoke / "cache"),
        ], check=True, env=benchmark_environment, capture_output=True, text=True, timeout=15)
        cached_result = json.loads(cached_completed.stdout)
        if (cached_result["status"] != "ready" or
                (cached_result["width"], cached_result["height"]) != (48, 40)
                or cached_result["rgba_bytes"] != 48 * 40 * 4
                or not cached_result["cleanup_complete"]
                or cached_result["address_space_bytes"] != 512 * 1024 * 1024
                or (sys.platform.startswith("linux") and not cached_result["address_space_enforced"])):
            raise ValueError(f"Frozen cache-only worker failed bounded RGBA delivery: {cached_result}")
        after_cached = (hashlib.sha256(moved_media.read_bytes()).hexdigest(),
                        moved_media.stat().st_mtime_ns,
                        hashlib.sha256(smoke_catalog.read_bytes()).hexdigest())
        cache_after = {str(path.relative_to(smoke / "cache")): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (smoke / "cache").rglob("*") if path.is_file()}
        if media.exists() or before_cached != after_cached or cache_before != cache_after:
            raise ValueError("Frozen cache-only worker changed source, catalog or cache")
        # Sixth smoke: actual two-pane cache workers and explicit verified
        # original worker, with an observed-unavailable right source. No native
        # window or external association is opened by this CLI branch.
        import uuid
        from defiantmaple.catalog import connect
        from defiantmaple.thumbnail import thumbnail_for
        left_root = smoke / "comparison-left"
        right_root = smoke / "comparison-right"
        left_root.mkdir()
        right_root.mkdir()
        left_media = left_root / "fictional-oriented.jpg"
        right_media = right_root / "fictional-alpha.png"
        oriented = Image.new("RGB", (60, 20), (220, 30, 40))
        oriented.paste((20, 30, 230), (0, 0, 30, 20))
        exif = Image.Exif()
        exif[274] = 6
        oriented.save(left_media, exif=exif, quality=100, subsampling=0)
        oriented.close()
        Image.new("RGBA", (80, 40), (20, 150, 230, 61)).save(right_media)
        comparison_catalog = smoke / "comparison.sqlite3"
        comparison_cache = smoke / "comparison-cache"
        initialize(comparison_catalog)
        left_id = index_file(comparison_catalog, left_media)
        right_id = index_file(comparison_catalog, right_media)
        for asset_id in (left_id, right_id):
            thumbnail_for(comparison_catalog, asset_id, comparison_cache, max_edge=256)
        source_id = str(uuid.uuid4())
        info = right_media.stat()
        with connect(comparison_catalog) as db:
            path = db.execute("SELECT current_path FROM assets WHERE asset_id=?", (right_id,)).fetchone()[0]
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                       "VALUES(?,'Generated comparison source',?,'inbox','offline')", (source_id, str(right_root)))
            db.execute("UPDATE assets SET source_id=? WHERE asset_id=?", (source_id, right_id))
            db.execute("INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                       "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
                       "VALUES(?,?,?,?,?,?,?,?,1,'missing',?)", (path, source_id, info.st_size,
                       info.st_mtime_ns, str(info.st_dev), str(info.st_ino), info.st_mtime_ns,
                       info.st_mtime_ns, right_id))
        moved_right = smoke / "fictional-comparison-right-unavailable.png"
        right_media.rename(moved_right)
        def comparison_snapshot():
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(comparison_catalog.as_uri() + "?mode=ro", uri=True)) as db:
                logical = list(db.iterdump())
                integrity = db.execute("PRAGMA integrity_check").fetchall()
                foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
            physical = {}
            for suffix in ("", "-wal", "-shm", "-journal"):
                path = Path(str(comparison_catalog) + suffix)
                physical[suffix or "main"] = ({"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                               "bytes": path.stat().st_size} if path.is_file() else None)
            if integrity != [("ok",)] or foreign_keys:
                raise ValueError("Generated comparison smoke catalog integrity failed")
            return (logical, physical,
                    [(hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                     for path in (left_media, moved_right)],
                    {str(path.relative_to(comparison_cache)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in comparison_cache.rglob("*") if path.is_file()})
        before_comparison = comparison_snapshot()
        comparison_completed = subprocess.run([
            str(launchable), "--catalog", str(comparison_catalog),
            "--smoke-comparison-ids", left_id, right_id,
            "--smoke-cache-root", str(comparison_cache),
        ], check=True, env=benchmark_environment, capture_output=True, text=True, timeout=40)
        comparison_result = json.loads(comparison_completed.stdout)
        if (comparison_result["status"] != "ready" or
                comparison_result["cache_sizes"] != [[20, 60], [80, 40]] or
                comparison_result["original_size"] != [20, 60] or
                comparison_result["original_top_rgba"][2] < 200 or
                comparison_result["original_bottom_rgba"][0] < 200 or
                comparison_result["cached_right_alpha"] != 61 or
                not comparison_result["unavailable_original_refused"] or
                not comparison_result["cleanup_complete"] or
                comparison_result["address_space_bytes"] != 512 * 1024 * 1024 or
                (sys.platform.startswith("linux") and not comparison_result["address_space_enforced"])):
            raise ValueError(f"Frozen comparison worker failed: {comparison_result}")
        if right_media.exists() or comparison_snapshot() != before_comparison:
            raise ValueError("Frozen comparison worker changed generated catalog, sources or published cache")
    frozen_gallery_filter_smoke(launchable, benchmark_environment)
    benchmark_environment["DEFIANTMAPLE_LAUNCH_TIME_NS"] = str(time.time_ns())
    subprocess.run([
        str(launchable), "--catalog", str(args.catalog),
        "--benchmark-json", str(args.metrics),
    ], check=True, env=benchmark_environment)
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    metrics.update({
        "package_tool": "pyside6-deploy/Nuitka",
        "package_mode": "onefile" if artifact.is_file() else "application_bundle",
        "package_path": str(artifact),
        "package_bytes": artifact_bytes,
        "desktop_integration_path": str(desktop_files) if desktop_files else None,
        "release_build_seconds": round(build_seconds, 3),
        "frozen_thumbnail_smoke": "passed",
        "frozen_gallery_worker_smoke": "passed",
        "frozen_desktop_identity_smoke": "passed",
        "frozen_external_probe_smoke": "passed",
        "frozen_cached_preview_smoke": "passed",
        "frozen_cached_preview_result": cached_result,
        "frozen_comparison_smoke": "passed",
        "frozen_comparison_result": comparison_result,
        "frozen_gallery_filter_smoke": "passed",
        "signed": False,
    })
    args.metrics.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
