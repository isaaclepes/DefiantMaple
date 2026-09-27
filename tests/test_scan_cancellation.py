from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from defiantmaple.catalog import connect, initialize
from defiantmaple.sources import add_source, scan_sources
from defiantmaple import sources


PNG = b"\x89PNG\r\n\x1a\nfictional fixture"


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS exposes /var through /private/var; scanner paths are canonical.
        self.root = Path(self.temp.name).resolve()
        self.db = self.root / "catalog.sqlite3"
        self.art = self.root / "art"
        self.art.mkdir()
        initialize(self.db)
        self.source = add_source(self.db, self.art, existing_file_policy="inbox")

    def test_cancel_keeps_missing_asset_and_explicit_rescan_reconciles(self):
        old = self.art / "old.png"
        old.write_bytes(PNG)
        source_id = self.source["source_id"]
        scan_sources(self.db, source_id=source_id, quiet_seconds=1, now_ns=1_000_000_000)
        indexed = scan_sources(self.db, source_id=source_id, quiet_seconds=1,
                               now_ns=3_000_000_000)
        self.assertEqual(indexed["totals"]["indexed"], 1)
        old.unlink()
        (self.art / "new.png").write_bytes(PNG + b"different")
        canceled = threading.Event()
        seen = []

        def progress(state):
            seen.append(state["phase"])
            if state["phase"] == "processing":
                canceled.set()

        result = scan_sources(self.db, source_id=source_id, quiet_seconds=1,
                              now_ns=4_000_000_000, cancel_event=canceled,
                              progress=progress)
        self.assertTrue(result["canceled"])
        self.assertIn("processing", seen)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT disposition FROM source_entries "
                                        "WHERE current_path=?", (str(old),)).fetchone()[0],
                             "indexed")
        rescan = scan_sources(self.db, source_id=source_id, quiet_seconds=1,
                              now_ns=5_000_000_000)
        self.assertFalse(rescan["canceled"])
        self.assertEqual(rescan["totals"]["missing"], 1)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 1)

    def test_cancel_during_enumeration_does_not_mark_anything_missing(self):
        for index in range(70):
            (self.art / f"image-{index:03}.png").write_bytes(PNG + bytes([index]))
        canceled = threading.Event()

        def progress(state):
            if state["phase"] == "enumerating" and state["enumerated"] >= 64:
                canceled.set()

        result = scan_sources(self.db, source_id=self.source["source_id"],
                              quiet_seconds=0, cancel_event=canceled,
                              progress=progress)
        self.assertTrue(result["canceled"])
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM source_entries").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT health FROM sources").fetchone()[0], "paused")

    def test_paged_resume_defers_missing_reconciliation_until_complete(self):
        source_id = self.source["source_id"]
        for name in ("a.png", "b.png", "c.png"):
            (self.art / name).write_bytes(PNG + name.encode())
        first = scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                             now_ns=1_000_000_000, max_candidates=1)
        self.assertFalse(first["complete"])
        self.assertEqual(first["resume_after"], str(self.art / "a.png"))
        cursor = first["resume_after"]
        for _ in range(2):
            page = scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                                now_ns=1_000_000_000, max_candidates=1,
                                resume_after=cursor)
            cursor = page["resume_after"]
        self.assertTrue(page["complete"])
        self.assertIsNone(cursor)
        self.assertTrue(self.source["initial_scan_completed"] is False)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT initial_scan_completed FROM sources").fetchone()[0], 1)

        # The second pass indexes each stable observation. A later page must
        # leave a disappeared asset untouched until the entire source is seen.
        cursor = None
        for _ in range(3):
            page = scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                                now_ns=2_000_000_000, max_candidates=1,
                                resume_after=cursor)
            cursor = page["resume_after"]
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 3)
        (self.art / "a.png").unlink()
        partial = scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                               now_ns=3_000_000_000, max_candidates=1)
        self.assertFalse(partial["complete"])
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT disposition FROM source_entries "
                                        "WHERE current_path=?", (str(self.art / "a.png"),))
                             .fetchone()[0], "indexed")
        final = scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                             now_ns=3_000_000_000, max_candidates=1,
                             resume_after=partial["resume_after"])
        self.assertTrue(final["complete"])
        self.assertEqual(final["totals"]["missing"], 1)

    def test_page_inventory_is_reused_and_root_replacement_is_offline(self):
        for name in ("a.png", "b.png"):
            (self.art / name).write_bytes(PNG + name.encode())
        cache = {}
        with patch.object(sources, "_iter_candidates", wraps=sources._iter_candidates) as inventory:
            first = scan_sources(self.db, source_id=self.source["source_id"],
                                 quiet_seconds=0, max_candidates=1,
                                 inventory_cache=cache)
            final = scan_sources(self.db, source_id=self.source["source_id"],
                                 quiet_seconds=0, max_candidates=1,
                                 resume_after=first["resume_after"],
                                 inventory_cache=cache)
        self.assertTrue(final["complete"])
        self.assertEqual(inventory.call_count, 1)

        replacement = self.root / "replacement"
        replacement.mkdir()
        original = self.root / "original"
        self.art.rename(original)
        replacement.rename(self.art)
        changed = scan_sources(self.db, source_id=self.source["source_id"],
                               quiet_seconds=0, max_candidates=1,
                               inventory_cache=cache)
        self.assertEqual(changed["sources"][0]["health"], "offline")
        self.assertFalse(changed["complete"])
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM source_entries "
                                        "WHERE disposition='missing'").fetchone()[0], 0)

    def test_permission_failure_resumes_at_the_failing_file(self):
        from defiantmaple.catalog import index_file

        for name in ("a.png", "b.png", "c.png"):
            (self.art / name).write_bytes(PNG + name.encode())
        source_id = self.source["source_id"]
        scan_sources(self.db, source_id=source_id, quiet_seconds=0,
                     now_ns=1_000_000_000)

        def index_unless_denied(database, path, **kwargs):
            if path.name == "b.png":
                raise PermissionError("fictional denied file")
            return index_file(database, path, **kwargs)

        with patch.object(sources, "index_file", side_effect=index_unless_denied):
            stopped = scan_sources(self.db, source_id=source_id,
                                   quiet_seconds=0, now_ns=2_000_000_000,
                                   max_candidates=3)
        self.assertEqual(stopped["sources"][0]["health"], "permission_denied")
        self.assertEqual(stopped["resume_after"], str(self.art / "a.png"))
        resumed = scan_sources(self.db, source_id=source_id,
                               quiet_seconds=0, now_ns=3_000_000_000,
                               max_candidates=3, resume_after=stopped["resume_after"])
        self.assertTrue(resumed["complete"])
        self.assertEqual(resumed["totals"]["indexed"], 2)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
