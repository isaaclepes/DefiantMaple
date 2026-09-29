"""Manual collection behavior on fictional temporary catalogs/media only."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from defiantmaple import catalog, collections as c, metadata as m


class CollectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="defiantmaple-collections-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "fictional.sqlite3"
        catalog.initialize(self.database)
        self.files, self.assets = [], []
        for number in range(3):
            path = self.root / f"fictional-{number}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nfictional shared-content fixture")
            self.files.append(path)
            self.assets.append(catalog.index_file(self.database, path))
        self.collection = c.create_collection(self.database, "Fictional collection")
        self.cid = self.collection["collection_id"]

    def members(self):
        return c.list_members(self.database, self.cid)

    def add_all(self):
        for asset in self.assets:
            c.add_member(self.database, self.cid, asset)

    def membership_rows(self):
        with catalog.connect(self.database) as db:
            return [tuple(row) for row in db.execute(
                "SELECT * FROM collection_members ORDER BY collection_id,position")]

    def preserved_rows(self):
        with catalog.connect(self.database) as db:
            return {table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in ("assets", "provenance", "sources", "source_entries", "tags",
                                  "tag_aliases", "entities", "entity_aliases", "asset_tags", "asset_entities")}

    def test_normalized_names_separate_namespace_and_stable_rename(self):
        record = c.create_collection(self.database, "  Cafe\u0301\t Fictional\nLabel  ")
        identifier = record["collection_id"]
        self.assertEqual(str(uuid.UUID(identifier)), identifier)
        self.assertEqual(record, {"collection_id": identifier, "name": "Café Fictional Label",
                                  "member_count": 0})
        m.create_tag(self.database, "CAFÉ fictional label")
        m.create_entity(self.database, "Project", "CAFÉ fictional label")
        with self.assertRaises(ValueError):
            c.create_collection(self.database, "CAFÉ  fictional label")
        renamed = c.rename_collection(self.database, identifier, "  Replacement  ")
        self.assertEqual(renamed["collection_id"], identifier)
        self.assertEqual(c.get_collection(self.database, identifier)["name"], "Replacement")
        c.rename_collection(self.database, identifier, "REPLACEMENT")
        with self.assertRaises(ValueError):
            c.rename_collection(self.database, identifier, "FICTIONAL COLLECTION")
        self.assertEqual(c.get_collection(self.database, identifier)["name"], "REPLACEMENT")
        self.assertEqual([record["name"] for record in c.list_collections(self.database)],
                         ["Fictional collection", "REPLACEMENT"])

    def test_unicode_casefold_nfc_and_invalid_names(self):
        c.create_collection(self.database, "Straße")
        with self.assertRaises(ValueError):
            c.create_collection(self.database, "STRASSE")
        c.create_collection(self.database, "A")
        c.create_collection(self.database, "Ａ")  # NFC does not width-fold.
        c.create_collection(self.database, "é")
        c.create_collection(self.database, "e")  # Accents remain significant.
        before = c.list_collections(self.database)
        for name in ("", " \t\n", "fictional\x00name", "fictional\x07name", None, 3):
            with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                c.create_collection(self.database, name)
            with self.subTest(rename=repr(name)), self.assertRaises(ValueError):
                c.rename_collection(self.database, self.cid, name)
        self.assertEqual(c.list_collections(self.database), before)

    def test_ordered_idempotent_add_remove_readd_and_reopen(self):
        self.add_all()
        once = c.get_collection(self.database, self.cid)
        self.assertEqual(once["member_count"], 3)
        self.assertEqual(c.add_member(self.database, self.cid, self.assets[0]), once)
        self.assertEqual(self.members(), self.assets)
        c.remove_member(self.database, self.cid, self.assets[1])
        twice = c.remove_member(self.database, self.cid, self.assets[1])
        self.assertEqual(twice["member_count"], 2)
        self.assertEqual(self.members(), [self.assets[0], self.assets[2]])
        c.add_member(self.database, self.cid, self.assets[1])
        self.assertEqual(self.members(), [self.assets[0], self.assets[2], self.assets[1]])
        self.assertFalse(catalog.initialize(self.database, create=False)["migrated"])
        self.assertEqual(self.members(), [self.assets[0], self.assets[2], self.assets[1]])
        other = c.create_collection(self.database, "Other")
        c.add_member(self.database, other["collection_id"], self.assets[1])
        self.assertEqual(c.get_collection(self.database, other["collection_id"])["member_count"], 1)

    def test_pagination_bounds_and_order(self):
        self.add_all()
        self.assertEqual(c.list_members(self.database, self.cid, limit=1, offset=1), self.assets[1:2])
        self.assertEqual(c.list_members(self.database, self.cid, offset=2), self.assets[2:])
        self.assertEqual(c.list_members(self.database, self.cid, offset=3), [])
        for arguments in ({"limit": 0}, {"limit": -1}, {"limit": True}, {"limit": 1.5},
                          {"limit": 1 << 63}, {"offset": -1}, {"offset": True},
                          {"offset": "0"}, {"offset": 1 << 63}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                c.list_members(self.database, self.cid, **arguments)

    def test_exact_reorder_refuses_partial_duplicate_extra_and_invalid_without_changes(self):
        c.add_member(self.database, self.cid, self.assets[0])
        c.add_member(self.database, self.cid, self.assets[1])
        before = self.membership_rows()
        for order in ([], [self.assets[0]], [self.assets[0], self.assets[0]], self.assets,
                      [self.assets[0], "unknown"], "invalid", None, [self.assets[0], None]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                c.reorder_members(self.database, self.cid, order)
            self.assertEqual(self.membership_rows(), before)
        c.reorder_members(self.database, self.cid, list(reversed(self.assets[:2])))
        self.assertEqual(self.members(), list(reversed(self.assets[:2])))
        self.assertEqual([row[2] for row in self.membership_rows()], [0, 1])
        empty = c.create_collection(self.database, "Empty")
        self.assertEqual(c.reorder_members(self.database, empty["collection_id"], [])["member_count"], 0)

    def test_adjacent_move_across_sparse_positions_and_stale_boundary_refusal(self):
        self.add_all()
        c.remove_member(self.database, self.cid, self.assets[1])
        c.move_member(self.database, self.cid, self.assets[2], direction=-1,
                      expected_neighbor_id=self.assets[0])
        self.assertEqual(self.members(), [self.assets[2], self.assets[0]])
        c.add_member(self.database, self.cid, self.assets[1])
        before = self.membership_rows()
        for asset, direction, neighbor in ((self.assets[2], -1, self.assets[0]),
                                           (self.assets[0], -1, self.assets[1]),
                                           (self.assets[1], 1, self.assets[0])):
            with self.assertRaisesRegex(ValueError, "boundary or stale"):
                c.move_member(self.database, self.cid, asset, direction=direction,
                              expected_neighbor_id=neighbor)
            self.assertEqual(self.membership_rows(), before)
        for direction in (0, 2, True, "1"):
            with self.assertRaises(ValueError):
                c.move_member(self.database, self.cid, self.assets[0], direction=direction,
                              expected_neighbor_id=self.assets[2])

    def test_removed_captured_neighbor_does_not_move_against_replacement(self):
        self.add_all()
        captured = self.assets[1]
        c.remove_member(self.database, self.cid, captured)
        before = self.membership_rows()
        with self.assertRaisesRegex(ValueError, "stale"):
            c.move_member(self.database, self.cid, self.assets[0], direction=1,
                          expected_neighbor_id=captured)
        self.assertEqual(self.membership_rows(), before)
        c.add_member(self.database, self.cid, captured)
        c.reorder_members(self.database, self.cid, [captured, self.assets[0], self.assets[2]])
        before = self.membership_rows()
        with self.assertRaisesRegex(ValueError, "stale"):
            c.move_member(self.database, self.cid, self.assets[0], direction=1,
                          expected_neighbor_id=captured)
        self.assertEqual(self.membership_rows(), before)

    def test_two_member_move_is_bounded_and_preserves_surrounding_order(self):
        # More than a UI page, using fictional rows rather than real files.
        identifiers = [f"fictional-member-{index:03}" for index in range(300)]
        with catalog.connect(self.database) as db:
            db.executemany("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                           "VALUES(?,?,'image/png','fictional-hash',1)",
                           [(identifier, f"/fictional/{identifier}.png") for identifier in identifiers])
            db.executemany("INSERT INTO collection_members VALUES(?,?,?)",
                           [(self.cid, identifier, index * 2) for index, identifier in enumerate(identifiers)])
        with patch.object(c, "_member_ids", side_effect=AssertionError("Unbounded member read")):
            c.move_member(self.database, self.cid, identifiers[256], direction=-1,
                          expected_neighbor_id=identifiers[255])
        expected = identifiers.copy()
        expected[255], expected[256] = expected[256], expected[255]
        self.assertEqual(self.members(), expected)

    def test_failed_reorder_and_swap_roll_back_deletion_and_partial_insert(self):
        self.add_all()
        before = self.membership_rows()
        real_connect = sqlite3.connect

        class FailingConnection(sqlite3.Connection):
            def executemany(self, sql, rows):
                if sql.startswith("INSERT INTO collection_members"):
                    super().executemany(sql, list(rows)[:1])
                    raise OSError("fictional insert failure")
                return super().executemany(sql, rows)

        def connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=FailingConnection)

        for action in (lambda: c.reorder_members(self.database, self.cid, list(reversed(self.assets))),
                       lambda: c.move_member(self.database, self.cid, self.assets[0], direction=1,
                                             expected_neighbor_id=self.assets[1])):
            with patch.object(catalog.sqlite3, "connect", side_effect=connect):
                with self.assertRaisesRegex(OSError, "fictional insert failure"):
                    action()
            self.assertEqual(self.membership_rows(), before)

    def test_unknown_ids_and_nonmembers_are_explicitly_refused(self):
        c.add_member(self.database, self.cid, self.assets[0])
        before = self.membership_rows()
        actions = [lambda: c.get_collection(self.database, "unknown"),
                   lambda: c.rename_collection(self.database, "unknown", "Name"),
                   lambda: c.delete_collection(self.database, "unknown"),
                   lambda: c.list_members(self.database, "unknown"),
                   lambda: c.add_member(self.database, "unknown", self.assets[0]),
                   lambda: c.remove_member(self.database, "unknown", self.assets[0]),
                   lambda: c.add_member(self.database, self.cid, "unknown"),
                   lambda: c.remove_member(self.database, self.cid, "unknown"),
                   lambda: c.reorder_members(self.database, "unknown", []),
                   lambda: c.move_member(self.database, self.cid, self.assets[1], direction=1,
                                         expected_neighbor_id=self.assets[0]),
                   lambda: c.move_member(self.database, self.cid, self.assets[0], direction=1,
                                         expected_neighbor_id="unknown")]
        for action in actions:
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.membership_rows(), before)

    def test_offline_missing_path_hash_changes_preserve_asset_uuid_membership(self):
        self.add_all()
        with catalog.connect(self.database) as db:
            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy,health) "
                       "VALUES('fictional-source','Fictional','/fictional','inbox','offline')")
            db.execute("UPDATE assets SET current_path='/fictional-renamed.png',source_id='fictional-source',"
                       "sha256='fictional-new-hash' WHERE asset_id=?", (self.assets[0],))
            db.execute("INSERT INTO source_entries VALUES('/fictional-renamed.png','fictional-source',"
                       "1,1,'fictional-device','fictional-inode',1,1,0,'missing',?,NULL)", (self.assets[0],))
        self.assertEqual(c.add_member(self.database, self.cid, self.assets[0])["member_count"], 3)
        self.assertEqual(self.members(), self.assets)
        offline = c.create_collection(self.database, "Offline remains available")
        c.add_member(self.database, offline["collection_id"], self.assets[0])
        self.assertEqual(c.list_members(self.database, offline["collection_id"]), self.assets[:1])

    def test_actual_asset_deletion_cascades_members_and_preserves_remaining_order(self):
        self.add_all()
        with self.assertRaises(sqlite3.IntegrityError), catalog.connect(self.database) as db:
            db.execute("DELETE FROM assets WHERE asset_id=?", (self.assets[1],))
        self.assertEqual(self.members(), self.assets)  # Existing provenance still protects this asset.
        with catalog.connect(self.database) as db:
            db.execute("DELETE FROM provenance WHERE asset_id=?", (self.assets[1],))
            db.execute("DELETE FROM assets WHERE asset_id=?", (self.assets[1],))
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.members(), [self.assets[0], self.assets[2]])
        self.assertEqual([row[2] for row in self.membership_rows()], [0, 2])
        with self.assertRaisesRegex(ValueError, "Unknown asset"):
            c.add_member(self.database, self.cid, self.assets[1])

    def test_membership_and_collection_deletion_preserve_media_sidecars_and_metadata(self):
        tag = m.create_tag(self.database, "Parent")
        child = m.create_tag(self.database, "Child", parent_id=tag["tag_id"])
        m.add_tag_alias(self.database, child["tag_id"], "Child alias")
        entity = m.create_entity(self.database, "Artist", "Fictional artist")
        m.add_entity_alias(self.database, entity["entity_id"], "Artist alias")
        m.assign_tag(self.database, self.assets[0], child["tag_id"])
        m.assign_entity(self.database, self.assets[0], entity["entity_id"])
        sidecar = self.root / "fictional-0.png.json"
        sidecar.write_bytes(b'{"fictional":"original sidecar"}')
        files = self.files + [sidecar]
        original = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                    for path in files}
        rows = self.preserved_rows()
        self.add_all()
        c.reorder_members(self.database, self.cid, list(reversed(self.assets)))
        c.move_member(self.database, self.cid, self.assets[0], direction=-1,
                      expected_neighbor_id=self.assets[1])
        c.remove_member(self.database, self.cid, self.assets[2])
        c.rename_collection(self.database, self.cid, "Renamed")
        c.delete_collection(self.database, self.cid)
        self.assertEqual(c.list_collections(self.database), [])
        self.assertEqual(self.membership_rows(), [])
        self.assertEqual(self.preserved_rows(), rows)
        self.assertEqual({path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                          for path in files}, original)

    def test_concurrent_normalized_collision_and_adds_do_not_lose_members(self):
        barrier = threading.Barrier(2)

        def create(name):
            barrier.wait(timeout=5)
            try:
                return c.create_collection(self.database, name)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ["Concurrent", "CONCURRENT"]))
        self.assertEqual(sum(record is not None for record in results), 1)
        for identifiers in ([self.assets[0], self.assets[0]], self.assets[1:]):
            barrier = threading.Barrier(2)

            def add(identifier):
                barrier.wait(timeout=5)
                return c.add_member(self.database, self.cid, identifier)

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(add, identifiers))
        self.assertEqual(set(self.members()), set(self.assets))
        self.assertEqual(c.get_collection(self.database, self.cid)["member_count"], 3)
        self.assertEqual(len({row[2] for row in self.membership_rows()}), 3)

    def test_reorder_reserves_writer_before_reading_and_refuses_concurrent_add(self):
        for asset in self.assets[:2]:
            c.add_member(self.database, self.cid, asset)
        real_members = c._member_ids

        def protected_read(db, collection_id):
            with contextlib.closing(sqlite3.connect(self.database, timeout=0)) as rival:
                with self.assertRaises(sqlite3.OperationalError):
                    rival.execute("BEGIN IMMEDIATE")
            return real_members(db, collection_id)

        with patch.object(c, "_member_ids", side_effect=protected_read):
            c.reorder_members(self.database, self.cid, self.assets[:2])
        # A caller captures two members, then a rival commits an add while the
        # caller is waiting for its writer lock. That stale reorder must refuse.
        with contextlib.closing(sqlite3.connect(self.database)) as rival:
            rival.execute("BEGIN IMMEDIATE")
            ready = threading.Event()

            def stale_reorder():
                ready.set()
                with self.assertRaisesRegex(ValueError, "exact permutation"):
                    c.reorder_members(self.database, self.cid, self.assets[1::-1])

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(stale_reorder)
                self.assertTrue(ready.wait(timeout=5))
                rival.execute("INSERT INTO collection_members VALUES(?,?,2)", (self.cid, self.assets[2]))
                rival.commit()
                future.result(timeout=5)
        self.assertEqual(self.members(), self.assets)

    def test_concurrent_captured_neighbor_moves_do_not_swap_twice(self):
        self.add_all()
        barrier = threading.Barrier(2)

        def move(_):
            barrier.wait(timeout=5)
            try:
                return c.move_member(self.database, self.cid, self.assets[0], direction=1,
                                     expected_neighbor_id=self.assets[1])
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(move, range(2)))
        self.assertEqual(sum(record is not None for record in results), 1)
        self.assertEqual(self.members(), [self.assets[1], self.assets[0], self.assets[2]])


if __name__ == "__main__":
    unittest.main()
