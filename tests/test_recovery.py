"""Generated, private Core recovery cases; no personal catalog/media paths."""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from defiantmaple import catalog
from defiantmaple.catalog import RESTORE_PENDING_APPLICATION_ID, SCHEMA_VERSION, restored_root_review_detail
from defiantmaple.cached_preview import capture_target, fresh_generation_refusal
from defiantmaple.recovery import (RecoveryError, _backup_worker,
                                   OMISSIONS, _canonical_json, _check_snapshot_page_budget,
                                   _manifest, _read_package, _worker_main,
                                   backup_metadata, enable_reviewed_source,
                                   inspect_package, reap_recovery_workers,
                                   restore_metadata, review_restored_sources)
from defiantmaple.recovery_storage import (PublicationUncertain, _local_backing,
                                           _mount_type, private_local_parent, publish)
from defiantmaple.sources import add_source, scan_sources, set_source_enabled
from defiantmaple.thumbnail import ThumbnailLimits, _decode_worker, thumbnail_for


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        # A user-owned 0700 directory on the checked-out local filesystem.
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "live.sqlite3"
        self.package = self.root / "point.dmbackup"
        self.restored = self.root / "restored.sqlite3"
        (self.root / "media").mkdir(mode=0o700)
        self.media = self.root / "media" / "fictional.png"
        Image.new("RGB", (2, 2), "purple").save(self.media)
        catalog.initialize(self.database)

    def _backup(self, **kwargs):
        return backup_metadata(self.database, self.package,
                               cache_roots=(self.root / "cache",), **kwargs)

    def _restore(self):
        return restore_metadata(self.package, self.restored,
                                cache_roots=(self.root / "cache",), live_catalog=self.database)

    def _mark_restore_pending(self):
        """Build generated pending state for platform-neutral guard/UI tests."""
        with closing(sqlite3.connect(self.database)) as source_db, \
                closing(sqlite3.connect(self.restored)) as restored_db:
            source_db.backup(restored_db)
            restored_db.execute(f"PRAGMA application_id={RESTORE_PENDING_APPLICATION_ID}")
            rows = restored_db.execute("SELECT source_id,root_path FROM sources").fetchall()
            for source_id, root_path in rows:
                restored_db.execute("UPDATE sources SET enabled=0,health='paused',health_detail=? WHERE source_id=?",
                                    (restored_root_review_detail(source_id, root_path), source_id))
            restored_db.commit()

    def _require_native_publication(self):
        """Skip only for the production adapter's declared platform/filesystem boundary."""
        try:
            with private_local_parent(self.root / ".native-capability-probe"):
                pass
        except ValueError as exc:
            detail = str(exc)
            if detail == "Recovery publication has no reviewed native adapter on this platform":
                self.skipTest(f"Native package publication requires the reviewed Linux PCIe NVMe adapter; {detail}")
            if detail == "Recovery requires a verified durable local filesystem":
                self.skipTest(f"Native package publication requires reviewed PCIe NVMe backing; {detail}")
            raise

    def _require_posix_root_enable(self):
        if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
            self.skipTest("Restored-root enable proof requires POSIX effective-ID and O_DIRECTORY semantics")

    def _linked(self):
        source = add_source(self.database, self.media.parent, existing_file_policy="inbox")
        asset_id = catalog.index_file(self.database, self.media, source_id=source["source_id"])
        return source, asset_id

    def _snapshot(self, path):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            return {name: db.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
                    for name in ("assets", "provenance", "tags", "collections", "collection_members")}

    def test_backup_inspect_restore_preserves_rows_and_guards_linked_original(self):
        self._require_native_publication()
        source, asset_id = self._linked()
        before_rows = self._snapshot(self.database)
        before_media = hashlib.sha256(self.media.read_bytes()).hexdigest()
        before_stat = self.media.stat()
        backed = self._backup()
        inspected = inspect_package(self.package)
        self.assertEqual(backed["manifest"], inspected["manifest"])
        self.assertEqual(inspected["catalog"]["assets"], 1)
        result = self._restore()
        self.assertEqual(result["restored"]["state"], "restore_pending")
        self.assertEqual(self._snapshot(self.restored), before_rows)
        with catalog.connect(self.restored) as db:
            self.assertEqual(catalog.catalog_state(db), "restore_pending")
            self.assertEqual(tuple(db.execute("SELECT enabled,health FROM sources").fetchone()), (0, "paused"))
            row = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
        with self.assertRaisesRegex(ValueError, "browse-only"):
            thumbnail_for(self.restored, asset_id, self.root / "cache")
        with self.assertRaisesRegex(ValueError, "browse-only"):
            scan_sources(self.restored)
        original_resolve = Path.resolve

        def guarded_resolve(path, *args, **kwargs):
            if path == self.media:
                self.fail("Pending index probed original media path")
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", guarded_resolve):
            with self.assertRaisesRegex(ValueError, "browse-only"):
                catalog.index_file(self.restored, self.media)
        admitted = {**row, "source_health": "paused", "entry_disposition": "indexed",
                    "source_relation_count": 1, "entry_path": row["current_path"],
                    "entry_source_id": row["source_id"]}
        self.assertIn("browse-only", fresh_generation_refusal(self.restored, capture_target(row), admitted))
        self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(), before_media)
        self.assertEqual((self.media.stat().st_mode, self.media.stat().st_mtime_ns),
                         (before_stat.st_mode, before_stat.st_mtime_ns))
        reviewed = review_restored_sources(self.restored, [(source["source_id"], source["root_path"])])
        self.assertEqual(reviewed["sources_enabled"], 0)
        with self.assertRaisesRegex(ValueError, "captured root review"):
            set_source_enabled(self.restored, source["source_id"], True)
        with self.assertRaisesRegex(ValueError, "disabled"):
            thumbnail_for(self.restored, asset_id, self.root / "cache")
        enable_reviewed_source(self.restored, source["source_id"], source["root_path"])
        with catalog.connect(self.restored) as db:
            self.assertEqual(catalog.catalog_state(db), "active")
            self.assertEqual(db.execute("SELECT enabled FROM sources").fetchone()[0], 1)
        self.assertFalse(thumbnail_for(self.restored, asset_id, self.root / "cache")["cache_hit"])

    def test_pending_source_mapping_cannot_be_rewritten_before_review(self):
        source, _ = self._linked()
        self._mark_restore_pending()
        with self.assertRaisesRegex(ValueError, "explicit review"):
            add_source(self.restored, self.media.parent / "other")
        with self.assertRaisesRegex(ValueError, "explicit review"):
            set_source_enabled(self.restored, source["source_id"], True)
        with catalog.connect(self.restored) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 1)

    def test_direct_index_cannot_probe_unreviewed_root_after_catalog_activation(self):
        reviewed_source, _ = self._linked()
        held_root = self.root / "held-media"
        held_root.mkdir(mode=0o700)
        held_file = held_root / "held.png"
        Image.new("RGB", (2, 2), "blue").save(held_file)
        held_source = add_source(self.database, held_root)
        catalog.index_file(self.database, held_file, source_id=held_source["source_id"])
        self._mark_restore_pending()
        # Model the post-review active catalog directly so pre-stat admission
        # remains portable; the POSIX root-enable check is tested separately.
        with catalog.connect(self.restored) as db:
            db.execute("PRAGMA application_id=0")
            db.execute("UPDATE sources SET enabled=1,health='paused',health_detail=NULL WHERE source_id=?",
                        (reviewed_source["source_id"],))
        original_resolve = Path.resolve
        def guarded_resolve(path, *args, **kwargs):
            if path == held_file:
                self.fail("Direct index probed an unreviewed original path")
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", guarded_resolve):
            with self.assertRaisesRegex(ValueError, "Standalone indexing waits"):
                catalog.index_file(self.restored, held_file)
            with self.assertRaisesRegex(ValueError, "unreviewed restored source root"):
                catalog.index_file(self.restored, held_file, source_id=reviewed_source["source_id"])
        with catalog.connect(self.restored) as db:
            held_asset = db.execute("SELECT asset_id FROM assets WHERE current_path=?",
                                    (str(held_file),)).fetchone()[0]
            db.execute("UPDATE assets SET source_id=? WHERE asset_id=?",
                       (reviewed_source["source_id"], held_asset))
        with self.assertRaisesRegex(ValueError, "unreviewed restored source root"):
            thumbnail_for(self.restored, held_asset, self.root / "cache")

    def test_thumbnail_child_refuses_pending_before_opening_original(self):
        _, asset_id = self._linked()
        self._mark_restore_pending()
        with catalog.connect(self.restored) as db:
            asset = db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        class Sender:
            result = None
            def send(self, value):
                self.result = value
            def close(self):
                pass
        sender = Sender()
        catalog_info = self.restored.stat()
        payload = {"database": str(self.restored), "asset_id": asset_id,
                   "catalog_identity": (catalog_info.st_dev, catalog_info.st_ino),
                   "revision": asset["revision"],
                   "source_id": asset["source_id"], "source": asset["current_path"],
                   "source_sha256": asset["sha256"], "source_bytes": asset["byte_size"],
                   "output": str(self.root / "should-not-exist.png"), "max_edge": 64,
                   "limits": asdict(ThumbnailLimits())}
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if path == self.media:
                self.fail("Thumbnail child opened original while restore was pending")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open):
            _decode_worker(payload, sender)
        self.assertFalse(sender.result["ok"])
        self.assertIn("browse-only", sender.result["error"])

    def test_reviewed_root_requires_read_and_search_access(self):
        self._require_posix_root_enable()
        source, _ = self._linked()
        self._mark_restore_pending()
        review_restored_sources(self.restored, [(source["source_id"], source["root_path"])])
        old_mode = self.media.parent.stat().st_mode & 0o777
        self.media.parent.chmod(0o400)
        try:
            with self.assertRaisesRegex(RecoveryError, "read/search"):
                enable_reviewed_source(self.restored, source["source_id"], source["root_path"])
        finally:
            self.media.parent.chmod(old_mode)

    def test_standalone_restore_stays_pending_and_guarded(self):
        asset_id = catalog.index_file(self.database, self.media)
        self._mark_restore_pending()
        with self.assertRaisesRegex(RecoveryError, "standalone assets"):
            review_restored_sources(self.restored, [])
        with self.assertRaisesRegex(ValueError, "browse-only"):
            thumbnail_for(self.restored, asset_id, self.root / "cache")
        with catalog.connect(self.restored) as db:
            self.assertEqual(catalog.catalog_state(db), "restore_pending")

    def test_digest_and_existing_destination_refuse_without_overwrite(self):
        self._require_native_publication()
        self._linked()
        self._backup()
        original = self.package.read_bytes()
        self.package.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaisesRegex(RecoveryError, "digest"):
            inspect_package(self.package)
        self.assertFalse(self.restored.exists())
        self.package.write_bytes(original)
        self.restored.write_bytes(b"preexisting")
        with self.assertRaisesRegex(RecoveryError, "already exists"):
            self._restore()
        self.assertEqual(self.restored.read_bytes(), b"preexisting")
        with self.assertRaisesRegex(RecoveryError, "already exists"):
            self._backup()
        self.assertEqual(self.package.read_bytes(), original)

    def test_unknown_application_id_fails_closed(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("PRAGMA application_id=1234567")
        with self.assertRaisesRegex(ValueError, "Unsupported catalog application_id"):
            with catalog.connect(self.database):
                pass

    def test_backup_refuses_unknown_application_id_before_publication(self):
        self._require_native_publication()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("PRAGMA application_id=1234567")
        with self.assertRaisesRegex(RecoveryError, "Unsupported catalog application_id"):
            self._backup()
        self.assertFalse(self.package.exists())

    def test_cache_and_source_containment_refuse_before_publication(self):
        self._require_native_publication()
        self._linked()
        (self.root / "cache").mkdir(mode=0o700)
        with self.assertRaisesRegex(RecoveryError, "cache root"):
            backup_metadata(self.database, self.root / "cache" / "point.dmbackup",
                            cache_roots=(self.root / "cache",))
        with self.assertRaisesRegex(RecoveryError, "media source"):
            backup_metadata(self.database, self.media.parent / "point.dmbackup",
                            cache_roots=(self.root / "cache",))
        self._backup()
        with self.assertRaisesRegex(RecoveryError, "media source"):
            restore_metadata(self.package, self.media.parent / "restored.sqlite3",
                             cache_roots=(self.root / "cache",), live_catalog=self.database)
        self.assertFalse((self.media.parent / "restored.sqlite3").exists())

    def test_resolved_source_alias_cannot_hide_output_containment(self):
        self._require_native_publication()
        source, _ = self._linked()
        alias = self.root / "alias"
        alias.symlink_to(self.root)
        with catalog.connect(self.database) as db:
            db.execute("UPDATE sources SET root_path=? WHERE source_id=?",
                       (str(alias), source["source_id"]))
        with self.assertRaisesRegex(RecoveryError, "media source"):
            self._backup()
        self.assertFalse(self.package.exists())

    def test_symlink_and_truncated_package_refuse(self):
        self._require_native_publication()
        self._linked()
        self._backup()
        alias = self.root / "alias.dmbackup"
        alias.symlink_to(self.package)
        with self.assertRaisesRegex(RecoveryError, "Too many levels|symbolic link|Symlink"):
            inspect_package(alias)
        contents = self.package.read_bytes()
        self.package.write_bytes(contents[:-1])
        with self.assertRaisesRegex(RecoveryError, "framing"):
            inspect_package(self.package)
        self.assertFalse(self.restored.exists())

    def test_live_catalog_sidecar_names_are_reserved(self):
        self._linked()
        sidecar = Path(str(self.database) + "-wal")
        with self.assertRaisesRegex(RecoveryError, "sidecar name"):
            backup_metadata(self.database, sidecar, cache_roots=(self.root / "cache",))
        with self.assertRaisesRegex(RecoveryError, "sidecar name"):
            restore_metadata(self.root / "missing.dmbackup", sidecar, cache_roots=(self.root / "cache",),
                             live_catalog=self.database)
        self.assertFalse(sidecar.exists())

    def test_restore_sidecar_refusal_with_valid_package(self):
        self._require_native_publication()
        self._linked()
        self._backup()
        sidecar = Path(str(self.database) + "-wal")
        with self.assertRaisesRegex(RecoveryError, "sidecar name"):
            restore_metadata(self.package, sidecar, cache_roots=(self.root / "cache",),
                             live_catalog=self.database)
        self.assertFalse(sidecar.exists())

    def test_manifest_format_validation_is_platform_neutral(self):
        with self.assertRaisesRegex(RecoveryError, "manifest is malformed"):
            _manifest(b"{", 1)
        with self.assertRaisesRegex(RecoveryError, "canonical or has unsupported fields"):
            _manifest(b"{}", 1)
        manifest = {"kind": "metadata-only", "package_version": 1,
                    "catalog_schema": SCHEMA_VERSION, "snapshot_bytes": 1,
                    "snapshot_sha256": "a" * 64, "created_utc": "2026-10-13T00:00:00+00:00",
                    "omissions": OMISSIONS, "source_paths_unverified": True}
        raw = _canonical_json(manifest)
        self.assertEqual(_manifest(raw, 1), manifest)
        manifest["snapshot_sha256"] = "g" * 64
        with self.assertRaisesRegex(RecoveryError, "declarations are unsupported"):
            _manifest(_canonical_json(manifest), 1)

    def test_escaped_network_mount_is_not_misclassified_as_local(self):
        if os.name == "nt":
            self.skipTest("Synthetic /proc/self/mountinfo parser case uses POSIX path spelling; Windows is outside scope")
        for encoded, actual in ((r"private\012remote", "private\nremote"),
                                (r"private\134remote", "private\\remote")):
            mountinfo = ("1 0 0:1 / / rw - btrfs /dev/nvme0n1p4 rw\n"
                         f"2 1 0:2 / /safe/{encoded} rw - nfs4 server:/share rw\n")
            with self.subTest(encoded=encoded), patch.object(Path, "read_text", return_value=mountinfo):
                kind, source = _mount_type(Path("/safe") / actual / "point.dmbackup")
                self.assertEqual((kind, source), ("nfs4", "server:/share"))
                self.assertFalse(_local_backing(kind, source))

    def test_new_restore_target_refuses_preexisting_sidecar(self):
        self._require_native_publication()
        self._linked()
        self._backup()
        sidecar = Path(str(self.restored) + "-wal")
        sidecar.write_bytes(b"older-sidecar")
        with self.assertRaisesRegex(RecoveryError, "already exists"):
            self._restore()
        self.assertFalse(self.restored.exists())
        self.assertEqual(sidecar.read_bytes(), b"older-sidecar")

    def test_post_link_failure_is_explicitly_uncertain_and_keeps_final(self):
        self._require_native_publication()
        stage = self.root / ".stage"
        final = self.root / "published.dmbackup"
        stage.write_bytes(b"verified")
        digest = hashlib.sha256(b"verified").hexdigest()
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with patch("defiantmaple.recovery_storage.os.fsync", side_effect=OSError("late flush")):
                with self.assertRaisesRegex(PublicationUncertain, "inspect it before retry"):
                    publish(stage, final, parent, 8, digest)
            self.assertEqual(final.read_bytes(), b"verified")
        finally:
            os.close(parent)

    def test_closed_package_reinspection_prevents_corrupt_stage_publication(self):
        self._require_native_publication()
        self._linked()
        stage = self.root / ".corrupt-stage"
        snapshot = self.root / ".snapshot"
        def corrupt_then_inspect(package, copied, cancel):
            raw = package.read_bytes()
            package.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            return _read_package(package, copied, cancel)
        with patch("defiantmaple.recovery._read_package", side_effect=corrupt_then_inspect):
            with self.assertRaisesRegex(RecoveryError, "digest"):
                _backup_worker(self.database, self.package, snapshot, stage,
                               (self.root / "cache",), threading.Event(), 10)
        self.assertFalse(self.package.exists())

    def test_precanceled_backup_has_bounded_exit_and_no_final(self):
        self._require_native_publication()
        self._linked()
        canceled = threading.Event()
        canceled.set()
        start = time.monotonic()
        with self.assertRaisesRegex(RecoveryError, "canceled"):
            self._backup(cancel_event=canceled, timeout_seconds=5)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(self.package.exists())
        self.assertFalse(list(self.root.glob(".recovery-*")))
        self.assertEqual(reap_recovery_workers()["remaining_workers"], 0)

    def test_page_budget_refuses_growth_before_writing_oversize_snapshot(self):
        _check_snapshot_page_budget((16 * 1024**3) // 4096, 4096)
        with self.assertRaisesRegex(RecoveryError, "16 GiB"):
            _check_snapshot_page_budget((16 * 1024**3) // 4096 + 1, 4096)

    def test_unsupported_posix_worker_reaches_native_adapter_before_package_open(self):
        class Capture:
            value = None
            closed = False

            def send(self, value):
                self.value = value

            def close(self):
                self.closed = True

        captured = Capture()
        stage = self.root / ".recovery-unsupported.inspect"
        with patch("defiantmaple.recovery.sys.platform", "darwin"), \
                patch("defiantmaple.recovery.regular_existing") as package_open:
            _worker_main("inspect", (self.package, stage), captured, threading.Event())
        self.assertEqual(captured.value, (
            False, "ValueError: Recovery publication has no reviewed native adapter on this platform"))
        self.assertTrue(captured.closed)
        package_open.assert_not_called()
        self.assertFalse(self.package.exists())
        self.assertFalse(stage.exists())

    def test_linux_worker_retains_bounded_address_space_setup(self):
        class Capture:
            value = None

            def send(self, value):
                self.value = value

            def close(self):
                pass

        calls = []
        fake_resource = SimpleNamespace(
            RLIMIT_AS=9, RLIM_INFINITY=-1,
            getrlimit=lambda key: (2 * 1024**3, 3 * 1024**3),
            setrlimit=lambda key, limits: calls.append((key, limits)))
        captured = Capture()
        with patch("defiantmaple.recovery.sys.platform", "linux"), \
                patch.dict(sys.modules, {"resource": fake_resource}), \
                patch("defiantmaple.recovery._inspect_worker",
                      side_effect=RecoveryError("bounded worker reached inspection")):
            _worker_main("inspect", (self.package, self.root / ".unused"),
                         captured, threading.Event())
        self.assertEqual(calls, [(9, (1024**3, 3 * 1024**3))])
        self.assertEqual(captured.value, (False, "RecoveryError: bounded worker reached inspection"))

    def test_concurrent_writer_snapshot_is_consistent_or_bounded_refusal(self):
        self._require_native_publication()
        self._linked()
        media_before = self.media.read_bytes()
        media_stat_before = self.media.stat()
        stop = threading.Event()
        started = threading.Event()

        def writer():
            with closing(sqlite3.connect(self.database, timeout=.1)) as db:
                started.set()
                for number in range(500):
                    if stop.is_set():
                        break
                    with db:
                        db.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                                   (f"tag-{number}", f"Tag {number}", f"tag {number}"))
                        db.execute("INSERT INTO entities(entity_id,entity_type,name,normalized_name) "
                                   "VALUES(?,?,?,?)", (f"ent-{number}", "Artist", f"Person {number}", f"person {number}"))
                    time.sleep(.002)

        thread = threading.Thread(target=writer)
        start = time.monotonic()
        thread.start()
        self.assertTrue(started.wait(2), "generated writer did not become ready")
        try:
            self._backup(timeout_seconds=10)
        except RecoveryError as exc:
            self.assertIn(str(exc), {
                "Recovery backup starved by concurrent writes",
                "OperationalError: database is locked",
            })
            self.assertFalse(self.package.exists())
            self.assertFalse(list(self.root.glob(".recovery-*")))
        else:
            inspected = inspect_package(self.package)
            self.assertEqual(inspected["catalog"]["state"], "active")
            self._restore()
            with closing(sqlite3.connect(self.restored)) as db:
                tags = db.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
                entities = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            self.assertEqual(tags, entities)
        finally:
            stop.set()
            thread.join(2)
        elapsed = time.monotonic() - start
        self.assertFalse(thread.is_alive(), "generated writer was not reaped")
        self.assertLess(elapsed, 12, "concurrent backup exceeded its bounded exit")
        self.assertEqual(reap_recovery_workers()["remaining_workers"], 0)
        self.assertFalse(list(self.root.glob(".recovery-*")))
        self.assertEqual(self.media.read_bytes(), media_before)
        media_stat_after = self.media.stat()
        self.assertEqual(
            (media_stat_after.st_mode, media_stat_after.st_size, media_stat_after.st_mtime_ns,
             media_stat_after.st_ino),
            (media_stat_before.st_mode, media_stat_before.st_size, media_stat_before.st_mtime_ns,
             media_stat_before.st_ino),
        )


if __name__ == "__main__":
    unittest.main()
