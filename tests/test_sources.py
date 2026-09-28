import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple.__main__ import main
from defiantmaple.catalog import SCHEMA_VERSION, connect, initialize, list_assets
from defiantmaple.sources import (
    add_source,
    list_sources,
    scan_sources,
    set_source_enabled,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"source prototype fixture"
SECOND = 1_000_000_000


class SourcePrototypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "catalog.sqlite3"
        initialize(self.db)

    def source(self, name, policy="inbox"):
        root = self.root / name
        root.mkdir(parents=True)
        return root, add_source(
            self.db, root, name=name, existing_file_policy=policy
        )

    def test_existing_file_policies_and_stable_interval(self):
        inbox_root, inbox = self.source("inbox")
        inbox_file = inbox_root / "existing.png"
        inbox_file.write_bytes(PNG)
        first = scan_sources(self.db, source_id=inbox["source_id"],
                             quiet_seconds=2, now_ns=0)
        self.assertEqual(first["totals"]["pending"], 1)
        early = scan_sources(self.db, source_id=inbox["source_id"],
                             quiet_seconds=2, now_ns=SECOND)
        self.assertEqual(early["totals"]["pending"], 1)
        ready = scan_sources(self.db, source_id=inbox["source_id"],
                             quiet_seconds=2, now_ns=2 * SECOND)
        self.assertEqual(ready["totals"]["indexed"], 1)

        reviewed_root, reviewed = self.source("reviewed", "reviewed")
        (reviewed_root / "existing.png").write_bytes(PNG + b"reviewed")
        scan_sources(self.db, source_id=reviewed["source_id"], now_ns=3 * SECOND)
        scan_sources(self.db, source_id=reviewed["source_id"], now_ns=5 * SECOND)

        ignored_root, ignored = self.source("ignored", "ignore_until_modified")
        ignored_file = ignored_root / "existing.png"
        ignored_file.write_bytes(PNG + b"ignored")
        ignored_scan = scan_sources(
            self.db, source_id=ignored["source_id"], now_ns=6 * SECOND
        )
        self.assertEqual(ignored_scan["totals"]["ignored_existing"], 1)
        self.assertEqual(len(list_assets(self.db)), 2)
        ignored_file.write_bytes(PNG + b"modified after registration")
        changed = scan_sources(
            self.db, source_id=ignored["source_id"], now_ns=7 * SECOND
        )
        self.assertEqual(changed["totals"]["pending"], 1)
        scan_sources(self.db, source_id=ignored["source_id"], now_ns=9 * SECOND)

        assets = {Path(asset["current_path"]).parent.name: asset for asset in list_assets(self.db)}
        self.assertEqual(assets["inbox"]["workflow_state"], "new")
        self.assertEqual(assets["reviewed"]["workflow_state"], "reviewed")
        self.assertEqual(assets["ignored"]["workflow_state"], "new")

    def test_ignored_existing_file_survives_temporary_absence(self):
        root, source = self.source("temporarily-absent", "ignore_until_modified")
        path = root / "original.png"
        parked = self.root / "parked.png"
        path.write_bytes(PNG)
        scan_sources(self.db, source_id=source["source_id"], now_ns=0)
        path.rename(parked)
        scan_sources(self.db, source_id=source["source_id"], now_ns=SECOND)
        with connect(self.db) as db:
            entry = db.execute(
                "SELECT disposition FROM source_entries WHERE current_path=?",
                (str(path.resolve()),),
            ).fetchone()
        self.assertEqual(entry["disposition"], "missing")

        parked.rename(path)
        restored = scan_sources(self.db, source_id=source["source_id"],
                                now_ns=2 * SECOND)
        self.assertEqual(restored["totals"]["ignored_existing"], 1)
        self.assertEqual(list_assets(self.db), [])

        path.write_bytes(PNG + b"changed")
        scan_sources(self.db, source_id=source["source_id"], now_ns=3 * SECOND)
        changed = scan_sources(self.db, source_id=source["source_id"],
                               now_ns=5 * SECOND)
        self.assertEqual(changed["totals"]["indexed"], 1)
        self.assertEqual(list_assets(self.db)[0]["workflow_state"], "new")

    def test_unindexed_file_moved_to_another_source_is_discovered(self):
        first_root, first = self.source("original-source", "ignore_until_modified")
        second_root, second = self.source("destination-source", "inbox")
        original = first_root / "transfer.png"
        destination = second_root / "transfer.png"
        original.write_bytes(PNG)
        scan_sources(self.db, source_id=first["source_id"], now_ns=0)
        scan_sources(self.db, source_id=second["source_id"], now_ns=0)

        original.rename(destination)
        discovered = scan_sources(self.db, source_id=second["source_id"],
                                  now_ns=SECOND)
        self.assertEqual(discovered["totals"]["pending"], 1)
        self.assertEqual(discovered["totals"]["renamed"], 0)
        self.assertEqual(list_assets(self.db), [])

        indexed = scan_sources(self.db, source_id=second["source_id"],
                               now_ns=3 * SECOND)
        self.assertEqual(indexed["totals"]["indexed"], 1)
        asset = list_assets(self.db)[0]
        self.assertEqual(asset["source_id"], second["source_id"])
        self.assertEqual(asset["workflow_state"], "new")

    def test_write_resets_debounce_and_reconciles_after_quiet_interval(self):
        root, source = self.source("writes")
        path = root / "render.png"
        path.write_bytes(PNG)
        scan_sources(self.db, source_id=source["source_id"],
                     quiet_seconds=2, now_ns=0)
        path.write_bytes(PNG + b"still writing")
        reset = scan_sources(self.db, source_id=source["source_id"],
                             quiet_seconds=2, now_ns=2 * SECOND)
        self.assertEqual(reset["totals"]["pending"], 1)
        self.assertEqual(list_assets(self.db), [])
        indexed = scan_sources(self.db, source_id=source["source_id"],
                               quiet_seconds=2, now_ns=4 * SECOND)
        self.assertEqual(indexed["totals"]["indexed"], 1)
        asset = list_assets(self.db)[0]
        original_id = asset["asset_id"]

        path.write_bytes(PNG + b"external edit is complete")
        scan_sources(self.db, source_id=source["source_id"],
                     quiet_seconds=2, now_ns=5 * SECOND)
        updated = scan_sources(self.db, source_id=source["source_id"],
                               quiet_seconds=2, now_ns=7 * SECOND)
        self.assertEqual(updated["totals"]["updated"], 1)
        asset = list_assets(self.db)[0]
        self.assertEqual(asset["asset_id"], original_id)
        self.assertEqual(asset["workflow_state"], "needs_review")
        with connect(self.db) as db:
            kinds = [row[0] for row in db.execute(
                "SELECT source_kind FROM provenance ORDER BY recorded_at,provenance_id"
            )]
        self.assertIn("filesystem_change", kinds)

        path.write_bytes(b"external replacement is not recognized media")
        scan_sources(self.db, source_id=source["source_id"],
                     quiet_seconds=2, now_ns=8 * SECOND)
        failed = scan_sources(self.db, source_id=source["source_id"],
                              quiet_seconds=2, now_ns=10 * SECOND)
        self.assertEqual(failed["totals"]["errors"], 1)
        self.assertEqual(list_assets(self.db)[0]["workflow_state"], "error")

    def test_same_file_rename_preserves_identity_and_missing_never_deletes(self):
        root, source = self.source("renames")
        old = root / "before.png"
        new = root / "after.png"
        old.write_bytes(PNG)
        scan_sources(self.db, source_id=source["source_id"], now_ns=0)
        scan_sources(self.db, source_id=source["source_id"], now_ns=2 * SECOND)
        asset_id = list_assets(self.db)[0]["asset_id"]
        # Exercise the full-hash fallback used when a platform changes or omits
        # file identity across a rename.
        with connect(self.db) as db:
            db.execute(
                "UPDATE source_entries SET device='previous',inode='previous'"
            )

        old.rename(new)
        result = scan_sources(self.db, source_id=source["source_id"],
                              now_ns=3 * SECOND)
        self.assertEqual(result["totals"]["renamed"], 1, result)
        asset = list_assets(self.db)[0]
        self.assertEqual(asset["asset_id"], asset_id)
        self.assertEqual(asset["current_path"], str(new.resolve()))
        with connect(self.db) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM provenance WHERE source_kind='filesystem_rename'")
                .fetchone()[0], 1,
            )

        new.unlink()
        missing = scan_sources(self.db, source_id=source["source_id"],
                               now_ns=4 * SECOND)
        self.assertEqual(missing["totals"]["missing"], 1)
        self.assertEqual(len(list_assets(self.db)), 1)

    def test_overlapping_roots_use_the_most_specific_enabled_source(self):
        parent = self.root / "art"
        child = parent / "renders"
        child.mkdir(parents=True)
        parent_file = parent / "reference.png"
        child_file = child / "frame.png"
        parent_file.write_bytes(PNG)
        child_file.write_bytes(PNG + b"child")
        parent_source = add_source(
            self.db, parent, name="Art", existing_file_policy="inbox"
        )
        child_source = add_source(
            self.db, child, name="Renders", existing_file_policy="inbox"
        )

        parent_first = scan_sources(
            self.db, source_id=parent_source["source_id"], now_ns=0
        )
        self.assertEqual(parent_first["totals"]["overlap_skipped"], 1)
        scan_sources(self.db, source_id=child_source["source_id"], now_ns=0)
        scan_sources(self.db, source_id=parent_source["source_id"], now_ns=2 * SECOND)
        scan_sources(self.db, source_id=child_source["source_id"], now_ns=2 * SECOND)

        by_name = {Path(asset["current_path"]).name: asset for asset in list_assets(self.db)}
        self.assertEqual(by_name["reference.png"]["source_id"], parent_source["source_id"])
        self.assertEqual(by_name["frame.png"]["source_id"], child_source["source_id"])

        set_source_enabled(self.db, child_source["source_id"], False)
        self.assertFalse(
            next(source for source in list_sources(self.db)
                 if source["source_id"] == child_source["source_id"])["enabled"]
        )

    def test_offline_and_permission_denied_are_source_health_not_deletion(self):
        missing = add_source(
            self.db, self.root / "disconnected", name="NAS",
            existing_file_policy="inbox",
        )
        offline = scan_sources(self.db, source_id=missing["source_id"], now_ns=0)
        self.assertEqual(offline["sources"][0]["health"], "offline")

        root, restricted = self.source("restricted")
        (root / "private.png").write_bytes(PNG)
        with patch("defiantmaple.sources.os.scandir", side_effect=PermissionError("blocked")):
            denied = scan_sources(
                self.db, source_id=restricted["source_id"], now_ns=SECOND
            )
        self.assertEqual(denied["sources"][0]["health"], "permission_denied")
        health = {source["name"]: source["health"] for source in list_sources(self.db)}
        self.assertEqual(health["NAS"], "offline")
        self.assertEqual(health["restricted"], "permission_denied")

    def test_schema_one_migrates_without_losing_assets(self):
        old = self.root / "schema-one.sqlite3"
        with contextlib.closing(sqlite3.connect(old)) as db:
            db.executescript("""
                CREATE TABLE assets (
                    asset_id TEXT PRIMARY KEY,current_path TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL,sha256 TEXT NOT NULL,byte_size INTEGER NOT NULL,
                    workflow_state TEXT NOT NULL,discovered_at TEXT NOT NULL
                );
                CREATE TABLE provenance (
                    provenance_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL,details_json TEXT NOT NULL,recorded_at TEXT NOT NULL
                );
                INSERT INTO assets VALUES('asset','/old.png','image/png','hash',1,'new','now');
                PRAGMA user_version = 1;
            """)
        initialize(old)
        with connect(old) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(db.execute("SELECT asset_id FROM assets").fetchone()[0], "asset")
            self.assertIsNotNone(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sources'"
            ).fetchone())

    def test_cli_requires_policy_and_emits_source_json(self):
        root = self.root / "cli"
        root.mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([
                "add-source", str(self.db), str(root), "--name", "CLI",
                "--existing-file-policy", "inbox",
            ]), 0)
        created = json.loads(output.getvalue())
        self.assertEqual(created["name"], "CLI")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["list-sources", str(self.db)]), 0)
        self.assertEqual(json.loads(output.getvalue())[0]["source_id"], created["source_id"])


if __name__ == "__main__":
    unittest.main()
