"""Fault-injection checks for incomplete scans of a disposable source tree."""
from __future__ import annotations

import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple.catalog import connect, initialize
from defiantmaple import sources


PNG = b"\x89PNG\r\n\x1a\nfictional fixture"


class ScanResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.db = self.base / "catalog.sqlite3"
        self.art = self.base / "fictional-art"
        self.art.mkdir()
        initialize(self.db)
        self.source_id = sources.add_source(self.db, self.art)["source_id"]

    def scan(self, now_ns: int, **kwargs):
        return sources.scan_sources(
            self.db, source_id=self.source_id, quiet_seconds=0,
            now_ns=now_ns, **kwargs,
        )

    def indexed_entry(self, path: Path) -> tuple[str, str]:
        with connect(self.db) as db:
            row = db.execute(
                "SELECT disposition,asset_id FROM source_entries WHERE current_path=?",
                (str(path),),
            ).fetchone()
        return row["disposition"], row["asset_id"]

    def test_disappearing_child_directory_never_marks_existing_art_missing(self):
        child = self.art / "child"
        child.mkdir()
        image = child / "a.png"
        image.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original = self.indexed_entry(image)
        self.assertEqual(original[0], "indexed")

        real_scandir = sources.os.scandir

        def disconnected(directory):
            if Path(directory) == child:
                raise FileNotFoundError(errno.ENOENT, "share child unavailable", str(child))
            return real_scandir(directory)

        with patch.object(sources.os, "scandir", side_effect=disconnected):
            result = self.scan(3_000_000_000)
        self.assertEqual(result["sources"][0]["health"], "offline")
        self.assertFalse(result["complete"])
        self.assertEqual(self.indexed_entry(image), original)

        recovered = self.scan(4_000_000_000)
        self.assertTrue(recovered["complete"])
        self.assertEqual(self.indexed_entry(image), original)

    def test_network_read_error_preserves_assets_until_healthy_reconciliation(self):
        old = self.art / "old.png"
        old.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original = self.indexed_entry(old)

        fresh = self.art / "fresh.png"
        fresh.write_bytes(PNG + b"different-size")
        self.scan(3_000_000_000)
        old.unlink()
        real_index = sources.index_file

        def disconnected(database, path, **kwargs):
            if path == fresh:
                raise OSError(getattr(errno, "ENOTCONN", errno.EIO),
                              "network share disconnected")
            return real_index(database, path, **kwargs)

        with patch.object(sources, "index_file", side_effect=disconnected):
            result = self.scan(4_000_000_000)
        self.assertEqual(result["sources"][0]["health"], "offline")
        self.assertIsNone(result["resume_after"])
        self.assertEqual(self.indexed_entry(old), original)

        recovered = self.scan(5_000_000_000)
        self.assertTrue(recovered["complete"])
        self.assertEqual(recovered["totals"]["missing"], 1)
        self.assertEqual(self.indexed_entry(fresh)[0], "indexed")
        self.assertEqual(self.indexed_entry(old)[0], "missing")

    def test_root_swap_after_processing_blocks_missing_reconciliation(self):
        old = self.art / "old.png"
        kept = self.art / "kept.png"
        old.write_bytes(PNG)
        kept.write_bytes(PNG + b"kept")
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original = self.indexed_entry(old)
        old.unlink()
        saved = self.base / "source-before-swap"
        swapped = False

        def progress(state):
            nonlocal swapped
            if (not swapped and state["phase"] == "processing"
                    and state["processed"] == state["total"]):
                self.art.rename(saved)
                self.art.mkdir()
                swapped = True

        result = self.scan(3_000_000_000, progress=progress)
        self.assertTrue(swapped)
        self.assertEqual(result["sources"][0]["health"], "offline")
        self.assertEqual(self.indexed_entry(old), original)

        self.art.rmdir()
        saved.rename(self.art)
        recovered = self.scan(4_000_000_000)
        self.assertTrue(recovered["complete"])
        self.assertEqual(self.indexed_entry(old)[0], "missing")

    def test_stale_handle_during_rename_preserves_asset_uuid(self):
        old = self.art / "old.png"
        new = self.art / "new.png"
        old.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original_id = self.indexed_entry(old)[1]
        old.rename(new)
        with patch.object(sources, "record_external_rename",
                          side_effect=OSError(getattr(errno, "ESTALE", errno.EIO),
                                              "stale network handle")):
            interrupted = self.scan(3_000_000_000)
        self.assertEqual(interrupted["sources"][0]["health"], "offline")
        self.assertEqual(self.indexed_entry(old), ("indexed", original_id))

        recovered = self.scan(4_000_000_000)
        self.assertTrue(recovered["complete"])
        self.assertEqual(self.indexed_entry(new), ("indexed", original_id))

    def test_offline_source_is_not_reconciled_as_a_cross_source_rename(self):
        old = self.art / "old.png"
        old.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original_id = self.indexed_entry(old)[1]

        saved = self.base / "disconnected-share"
        self.art.rename(saved)
        self.assertEqual(self.scan(3_000_000_000)["sources"][0]["health"], "offline")
        other = self.base / "other-source"
        other.mkdir()
        copy = other / "copy.png"
        copy.write_bytes(PNG)
        other_id = sources.add_source(self.db, other)["source_id"]
        first = sources.scan_sources(self.db, source_id=other_id,
                                     quiet_seconds=0, now_ns=4_000_000_000)
        self.assertEqual(first["totals"]["renamed"], 0)
        self.assertEqual(self.indexed_entry(old), ("indexed", original_id))
        sources.scan_sources(self.db, source_id=other_id,
                             quiet_seconds=0, now_ns=5_000_000_000)
        self.assertNotEqual(self.indexed_entry(copy)[1], original_id)

    def test_unreported_disconnection_is_not_a_cross_source_rename(self):
        old = self.art / "old.png"
        old.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original_id = self.indexed_entry(old)[1]
        self.art.rename(self.base / "disconnected-share")

        other = self.base / "other-source"
        other.mkdir()
        (other / "copy.png").write_bytes(PNG)
        other_id = sources.add_source(self.db, other)["source_id"]
        first = sources.scan_sources(self.db, source_id=other_id,
                                     quiet_seconds=0, now_ns=3_000_000_000)
        self.assertEqual(first["totals"]["renamed"], 0)
        self.assertEqual(self.indexed_entry(old), ("indexed", original_id))

    def test_identical_copy_in_healthy_other_source_is_a_distinct_asset(self):
        old = self.art / "old.png"
        old.write_bytes(PNG)
        self.scan(1_000_000_000)
        self.scan(2_000_000_000)
        original_id = self.indexed_entry(old)[1]
        other = self.base / "other-source"
        other.mkdir()
        copy = other / "copy.png"
        copy.write_bytes(PNG)
        other_id = sources.add_source(self.db, other)["source_id"]
        first = sources.scan_sources(self.db, source_id=other_id,
                                     quiet_seconds=0, now_ns=3_000_000_000)
        self.assertEqual(first["totals"]["renamed"], 0)
        sources.scan_sources(self.db, source_id=other_id,
                             quiet_seconds=0, now_ns=4_000_000_000)
        self.assertNotEqual(self.indexed_entry(copy)[1], original_id)
        self.assertEqual(self.indexed_entry(old), ("indexed", original_id))

    def test_page_cursor_requires_the_original_inventory(self):
        (self.art / "z.png").write_bytes(PNG)
        with self.assertRaisesRegex(ValueError, "shared inventory_cache"):
            self.scan(1_000_000_000, max_candidates=1)
        cache = {}
        self.scan(1_000_000_000, max_candidates=1, inventory_cache=cache)
        with self.assertRaisesRegex(ValueError, "original in-memory inventory"):
            self.scan(2_000_000_000, max_candidates=1,
                      resume_after=str(self.art / "z.png"), inventory_cache={})


if __name__ == "__main__":
    unittest.main()
