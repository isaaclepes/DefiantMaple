"""Generated real-child cache outcomes; no user media or desktop dispatch."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from defiantmaple import cached_preview as api, catalog
from defiantmaple.thumbnail import thumbnail_for


def _guarded_helper(*args):
    """Child-side spies: spawn cannot inherit parent monkeypatches."""
    target = args[1]
    original_root = str(Path(target.path).parent)
    def guard(function):
        def wrapped(path, *a, **kw):
            if not isinstance(path, int) and (str(path) == original_root or str(path).startswith(original_root + os.sep)):
                raise AssertionError("Original/source filesystem access from cache-only reader")
            return function(path, *a, **kw)
        return wrapped
    guarded_open = guard(os.open)
    with patch.object(Path, "open", guard(Path.open)), patch.object(Path, "stat", guard(Path.stat)), \
         patch.object(Path, "resolve", guard(Path.resolve)), patch.object(os, "open", guarded_open), \
         patch.object(os, "supports_dir_fd", os.supports_dir_fd | {guarded_open}), \
         patch.object(os, "scandir", guard(os.scandir)):
        api._cache_helper(*args)


def _sleeping_helper(*args):
    time.sleep(10)


def _crashing_helper(*args):
    os._exit(3)


def _changing_helper(*args):
    original = api._asset_snapshot
    calls = 0
    def snapshot(database, target, deadline):
        nonlocal calls
        calls += 1
        if calls == 2:
            with catalog.connect(database) as db:
                db.execute("UPDATE assets SET sha256=?,revision=revision+1 WHERE asset_id=?", ("b" * 64, target.asset_id))
        return original(database, target, deadline)
    with patch.object(api, "_asset_snapshot", snapshot):
        api._cache_helper(*args)


class AddressSpacePolicyTests(unittest.TestCase):
    ceiling = 512 * 1024 * 1024

    def resource(self, limits=(-1, -1)):
        return SimpleNamespace(RLIMIT_AS=9, RLIM_INFINITY=-1,
                               getrlimit=Mock(return_value=limits), setrlimit=Mock())

    def apply(self, platform, resource, ceiling=None):
        with patch.object(api.sys, "platform", platform), patch.dict("sys.modules", {"resource": resource}):
            return api._address_space_limit(self.ceiling if ceiling is None else ceiling)

    def test_darwin_default_rejection_is_attempted_and_explicitly_unenforced(self):
        resource = self.resource()
        resource.setrlimit.side_effect = ValueError("generated current limit rejection")
        enforced, note = self.apply("darwin", resource)
        self.assertFalse(enforced)
        self.assertIn("Darwin RLIMIT_AS requested/effective 536870912 bytes", note)
        self.assertIn("setrlimit rejected with ValueError", note)
        self.assertIn("address-space ceiling not enforced; cause not established", note)
        resource.getrlimit.assert_called_once_with(resource.RLIMIT_AS)
        resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (self.ceiling, -1))

    def test_darwin_success_preserves_requested_limit_and_enforced_report(self):
        for limits in ((-1, -1), (64 * 1024 * 1024, self.ceiling)):
            with self.subTest(limits=limits):
                resource = self.resource(limits)
                enforced, note = self.apply("darwin", resource)
                self.assertTrue(enforced)
                self.assertEqual(note, "RLIMIT_AS 536870912 bytes (address space, not RSS)")
                resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (self.ceiling, limits[1]))

    def test_darwin_other_failures_and_stricter_limits_remain_refusals(self):
        for stage, error, limits, ceiling in (
                ("getrlimit", ValueError("read rejected"), (-1, -1), self.ceiling),
                ("getrlimit", OSError("read failed"), (-1, -1), self.ceiling),
                ("setrlimit", OSError("write failed"), (-1, -1), self.ceiling),
                ("setrlimit", ValueError("tightened failed"), (-1, -1), self.ceiling // 2),
                ("setrlimit", ValueError("inherited hard failed"), (self.ceiling // 4, self.ceiling // 2), self.ceiling)):
            with self.subTest(stage=stage, error=type(error).__name__, limits=limits, ceiling=ceiling):
                resource = self.resource(limits)
                getattr(resource, stage).side_effect = error
                with self.assertRaises(api.CacheRefusal):
                    self.apply("darwin", resource, ceiling)
                if stage == "getrlimit":
                    resource.setrlimit.assert_not_called()
                else:
                    resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (min(ceiling, limits[1]) if limits[1] != -1 else ceiling, limits[1]))
        for limits in ((1, 0), (-1, self.ceiling), (0, -2), (False, -1), (1.5, -1), (0,)):
            with self.subTest(malformed_limits=limits):
                resource = self.resource(limits)
                with self.assertRaises(api.CacheRefusal):
                    self.apply("darwin", resource)
                resource.setrlimit.assert_not_called()

    def test_linux_failure_and_success_keep_original_resource_path(self):
        for stage in ("getrlimit", "setrlimit"):
            for error in (ValueError("generated rejected"), OSError("generated failed")):
                with self.subTest(stage=stage, error=type(error).__name__):
                    resource = self.resource()
                    getattr(resource, stage).side_effect = error
                    with self.assertRaises(api.CacheRefusal):
                        self.apply("linux", resource)
        resource = self.resource((self.ceiling // 4, self.ceiling // 2))
        self.assertEqual(self.apply("linux", resource), (True, "RLIMIT_AS 268435456 bytes (address space, not RSS)"))
        resource.getrlimit.assert_called_once_with(resource.RLIMIT_AS)
        resource.setrlimit.assert_called_once_with(resource.RLIMIT_AS, (self.ceiling // 2, self.ceiling // 2))

    def test_missing_resource_control_still_reports_an_unavailable_gap(self):
        for resource in (None, SimpleNamespace()):
            with self.subTest(resource=resource):
                enforced, note = self.apply("win32", resource)
                self.assertFalse(enforced)
                self.assertEqual(note, "Address-space enforcement unavailable on this platform")


class CachedPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Match catalog canonicalization on /var aliases and Windows short names.
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.art = self.root / "generated-art"
        self.art.mkdir()
        self.media = self.art / "literal $(`x`) ; café %.png"
        Image.new("RGBA", (96, 48), (20, 80, 190, 91)).save(self.media)
        self.db = self.root / "generated.sqlite3"
        catalog.initialize(self.db)
        self.asset_id = catalog.index_file(self.db, self.media)
        self.cache = self.root / "cache"
        self.entry = thumbnail_for(self.db, self.asset_id, self.cache, max_edge=128)
        self.png = Path(self.entry["path"])
        self.manifest = self.png.with_suffix(".json")
        with catalog.connect(self.db) as db:
            self.row = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (self.asset_id,)).fetchone())
        self.target = api.capture_target(self.row)

    def read(self, edge=128, **kw):
        return api.read_cached_preview(self.db, self.target, self.cache, edge, **kw)

    def snapshot(self):
        with catalog.connect(self.db) as db:
            return list(db.iterdump()), self.media.read_bytes(), self.media.stat().st_mtime_ns

    def write_manifest(self, **changes):
        value = json.loads(self.manifest.read_text())
        value.update(changes)
        self.manifest.write_text(json.dumps(value))

    def test_lexical_capture_immutable_and_policy_limits(self):
        with patch.object(Path, "stat", side_effect=AssertionError("capture stat")), \
             patch.object(Path, "resolve", side_effect=AssertionError("capture resolve")), \
             patch.object(Path, "open", side_effect=AssertionError("capture open")):
            self.assertEqual(api.capture_target(self.row), self.target)
        with self.assertRaises(FrozenInstanceError):
            self.target.path = "replacement"
        for values in ({"png_bytes": 21 * 1024 * 1024}, {"timeout_seconds": float("inf")}, {"directory_entries": True},
                       {"address_space_bytes": 513 * 1024 * 1024}, {"timeout_seconds": 6}):
            with self.assertRaises(ValueError):
                api.CacheReadLimits(**values)

    def test_real_child_never_accesses_original_and_preserves_catalog_pixels(self):
        before = self.snapshot()
        with patch.object(api, "_cache_helper", _guarded_helper):
            result = self.read()
        self.assertEqual(result.status, "ready", result.message)
        self.assertEqual((result.width, result.height), (96, 48))
        self.assertEqual(result.pixels[:4], bytes((20, 80, 190, 91)))
        self.assertTrue(result.cleanup_complete)
        if api.sys.platform == "darwin" and not result.address_space_enforced:
            self.assertIn("Darwin RLIMIT_AS requested/effective 536870912 bytes", result.address_space_note)
            self.assertIn("setrlimit rejected with ValueError", result.address_space_note)
            self.assertIn("cause not established", result.address_space_note)
        self.assertEqual(self.snapshot(), before)
        self.media.rename(self.art / "temporarily-unavailable.png")
        self.assertEqual(self.read().status, "ready")

    def test_size_fallback_exact_corrupt_and_preferred_corrupt_are_truthful(self):
        thumbnail_for(self.db, self.asset_id, self.cache, max_edge=192)
        for requested, actual in ((128, 128), (144, 192), (256, 192), (96, 128)):
            result = self.read(requested)
            self.assertEqual((result.status, result.requested_edge, result.cache_edge), ("ready", requested, actual))
        self.png.write_bytes(b"corrupt exact")
        self.assertEqual(self.read(128).status, "refused")
        # Exact absent chooses the preferred128 alternative; a valid192 must not hide corruption.
        self.assertEqual(self.read(96).status, "refused")

    def test_no_cache_wrong_uuid_and_old_fingerprint_never_generate_or_repair(self):
        before = self.snapshot()
        self.png.unlink()
        self.manifest.unlink()
        result = self.read()
        self.assertEqual(result.status, "no_cache")
        self.assertEqual(list(self.cache.rglob("*.png")), [])
        self.assertEqual(self.snapshot(), before)
        with catalog.connect(self.db) as db:
            db.execute("UPDATE assets SET sha256=? WHERE asset_id=?", ("a" * 64, self.asset_id))
        self.assertEqual(self.read().status, "refused")
        nonexistent = replace(self.target, asset_id="00000000-0000-4000-8000-000000000001")
        self.assertEqual(api.read_cached_preview(self.db, nonexistent, self.cache).status, "refused")

    def test_incompatible_identity_decoder_policy_and_declared_dimensions_refuse(self):
        original = self.manifest.read_bytes()
        for changes in ({"asset_id": "00000000-0000-4000-8000-000000000001"},
                        {"decoder_version": "fictional-old"}, {"cache_schema": 2},
                        {"max_pixels": 1}, {"width": 2049}, {"height": True},
                        {"output_sha256": "0" * 64}, {"source_bytes": self.target.byte_size + 1},
                        {"output_policy": "different"}, {"unknown_field": "different"}):
            with self.subTest(changes=changes):
                self.manifest.write_bytes(original)
                self.write_manifest(**changes)
                self.assertEqual(self.read().status, "refused")

    def test_manifest_bounds_duplicate_nested_nonfinite_and_png_bounds_refuse(self):
        original = self.manifest.read_bytes()
        for value in (b"x" * 16385, b'{"a":1,"a":2}', b'{"nested":{"a":1}}', b'{"x":NaN}'):
            self.manifest.write_bytes(value)
            self.assertEqual(self.read().status, "refused")
        self.manifest.write_bytes(original)
        with self.png.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
        self.assertEqual(self.read().status, "refused")

    def test_matching_digest_is_not_authentication_and_png_decode_still_refuses_malformed(self):
        corrupt = b"not a PNG despite matching manifest"
        self.png.write_bytes(corrupt)
        self.write_manifest(output_bytes=len(corrupt), output_sha256=hashlib.sha256(corrupt).hexdigest())
        self.assertEqual(self.read().status, "refused")
        # Coherent same-user image+manifest replacement is deliberately not authenticated offline.
        Image.new("RGBA", (96, 48), (91, 92, 93, 94)).save(self.png)
        data = self.png.read_bytes()
        self.write_manifest(output_bytes=len(data), output_sha256=hashlib.sha256(data).hexdigest())
        result = self.read()
        self.assertEqual(result.status, "ready", result.message)
        self.assertEqual(result.pixels[:4], bytes((91, 92, 93, 94)))

    def test_cache_leaf_and_ancestor_symlink_refusal(self):
        outside = self.root / "outside-copy.png"
        outside.write_bytes(self.png.read_bytes())
        self.png.unlink()
        try:
            self.png.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Generated symlink creation unavailable: {exc}")
        self.assertEqual(self.read().status, "refused")
        self.png.unlink()
        outside.replace(self.png)
        moved = self.root / "cache-moved"
        self.cache.rename(moved)
        self.cache.symlink_to(moved, target_is_directory=True)
        self.assertEqual(self.read().status, "refused")

    def test_supervisor_owned_scratch_alias_is_canonicalized_without_relaxing_cache_containment(self):
        scratch = self.root / "private-scratch"
        scratch.mkdir()
        alias = self.root / "scratch-alias"
        try:
            alias.symlink_to(scratch, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Generated scratch alias unavailable: {exc}")
        with patch.object(tempfile, "tempdir", str(alias)):
            result = self.read()
        self.assertEqual(result.status, "ready", result.message)
        self.assertEqual(list(scratch.iterdir()), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is POSIX-only")
    def test_nonregular_manifest_fifo_refuses_without_open_block(self):
        self.manifest.unlink()
        os.mkfifo(self.manifest)
        result = self.read(limits=api.CacheReadLimits(timeout_seconds=2))
        self.assertEqual(result.status, "refused", result.message)
        self.assertNotEqual(result.status, "timeout")
        self.assertTrue(result.cleanup_complete)

    def test_finite_directory_count_includes_debris_and_normal_slider_pairs_fit(self):
        # Valid manifest/PNG partners for all supported slider sizes fit the selected cap.
        for edge in range(96, 225):
            base = api._basename(edge)
            for suffix in (".png", ".json"):
                path = self.png.parent / (base + suffix)
                if not path.exists():
                    path.write_bytes(b"unused")
        result = self.read(128)
        self.assertEqual(result.status, "ready", result.message)
        self.assertEqual(result.entries_examined, 258)
        for number in range(255):
            (self.png.parent / f"unrecognized-{number}").write_bytes(b"")
        result = self.read()
        self.assertEqual(result.status, "refused")
        self.assertEqual(result.entries_examined, 513)

    def test_metadata_path_source_drift_warns_but_content_drift_refuses(self):
        with catalog.connect(self.db) as db:
            db.execute("UPDATE assets SET rating=4,revision=revision+1,current_path=? WHERE asset_id=?",
                       (str(self.art / "changed-location.png"), self.asset_id))
        result = self.read()
        self.assertEqual(result.status, "ready", result.message)
        self.assertTrue(result.catalog_drift)
        self.assertEqual(result.target.path, str(self.media))
        with patch.object(api, "_cache_helper", _changing_helper):
            self.assertEqual(self.read().status, "refused")

    def test_observed_state_eligibility_does_not_probe_or_clear_scan_facts(self):
        standalone = dict(self.row)
        self.assertIsNone(api.generation_refusal(standalone))
        self.assertIsNotNone(api.generation_refusal({**standalone, "linked_entry_count": 1}))
        self.assertIn("unchecked", api.availability_text(standalone))
        source_row = {**self.row, "source_id": "generated", "entry_source_id": "generated",
                      "entry_path": self.row["current_path"], "entry_disposition": "indexed", "source_relation_count": 1}
        with patch.object(Path, "stat", side_effect=AssertionError("state probe")):
            for health in ("paused", "watching"):
                self.assertIsNone(api.generation_refusal({**source_row, "source_health": health}))
            for health in ("offline", "permission_denied", "error", "scanning", None):
                self.assertIsNotNone(api.generation_refusal({**source_row, "source_health": health}))
            for disposition in ("missing", "pending", "ignored_existing", "unsupported", "error", None):
                self.assertIsNotNone(api.generation_refusal({**source_row, "source_health": "paused", "entry_disposition": disposition}))
            self.assertIsNotNone(api.generation_refusal({**source_row, "source_health": "paused", "source_relation_count": 0}))
            self.assertIsNotNone(api.generation_refusal({**source_row, "source_health": "paused", "entry_source_id": "different"}))
            self.assertIsNotNone(api.generation_refusal({**source_row, "source_health": "paused", "entry_path": "different"}))

    def test_fresh_generation_relation_recheck_and_cache_only_admission_never_upgrade(self):
        source_id = "00000000-0000-4000-8000-000000000002"
        with catalog.connect(self.db) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) VALUES(?,?,?,'inbox')",
                       (source_id, "Generated source", str(self.art)))
            db.execute("INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,inode,"
                       "stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
                       "VALUES(?,?,?,0,'0','0',0,0,1,'indexed',?)",
                       (self.target.path, source_id, self.target.byte_size, self.asset_id))
        # A standalone asset with a stray linked entry cannot generate originals.
        self.assertIsNotNone(api.fresh_generation_refusal(self.db, self.target, self.row))
        with catalog.connect(self.db) as db:
            db.execute("UPDATE assets SET source_id=? WHERE asset_id=?", (source_id, self.asset_id))
        target = replace(self.target, source_id=source_id)
        admitted = {**self.row, "source_id": source_id, "source_health": "paused", "entry_disposition": "indexed",
                    "entry_source_id": source_id, "entry_path": target.path, "source_relation_count": 1}
        self.assertIsNone(api.fresh_generation_refusal(self.db, target, admitted))
        with catalog.connect(self.db) as db:
            db.execute("UPDATE sources SET health='offline' WHERE source_id=?", (source_id,))
        self.assertIsNotNone(api.fresh_generation_refusal(self.db, target, admitted))
        with catalog.connect(self.db) as db:
            db.execute("UPDATE sources SET health='paused' WHERE source_id=?", (source_id,))
        self.assertIsNotNone(api.fresh_generation_refusal(self.db, target, {**admitted, "source_health": "offline"}))
        with catalog.connect(self.db) as db:
            db.execute("UPDATE source_entries SET current_path=? WHERE asset_id=?", (str(self.art / "other.png"), self.asset_id))
        self.assertIsNotNone(api.fresh_generation_refusal(self.db, target, admitted))

    @unittest.skipIf(os.name == "nt", "POSIX resource controls are unavailable on Windows")
    def test_supported_address_space_failure_refuses_instead_of_silent_waiver(self):
        import resource
        if not hasattr(resource, "RLIMIT_AS"):
            self.skipTest("RLIMIT_AS unavailable")
        with patch.object(resource, "setrlimit", side_effect=OSError("generated limit failure")):
            with self.assertRaises(api.CacheRefusal):
                api._address_space_limit(512 * 1024 * 1024)

    def test_timeout_cancellation_worker_crash_and_reaping_are_bounded(self):
        before = {child.pid for child in multiprocessing.active_children()}
        with patch.object(api, "_cache_helper", _sleeping_helper):
            result = self.read(limits=api.CacheReadLimits(timeout_seconds=.3))
            self.assertEqual(result.status, "timeout")
            canceled = threading.Event()
            timer = threading.Timer(.2, canceled.set)
            timer.start()
            try:
                result = self.read(cancel_event=canceled)
                self.assertEqual(result.status, "cancelled")
            finally:
                timer.join()
        with patch.object(api, "_cache_helper", _crashing_helper):
            result = self.read()
            self.assertEqual(result.status, "refused")
        self.assertTrue(result.cleanup_complete)
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)


if __name__ == "__main__":
    unittest.main()
