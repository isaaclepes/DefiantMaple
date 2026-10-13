"""Generated schema-6 tests for the dormant bounded gallery query executor."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from defiantmaple.catalog import initialize
from defiantmaple.curation import FavoriteFilter, RatingFilter, RatingMode
from defiantmaple.gallery_query import (
    GalleryOrder, GalleryQuery, LookupKind, StaleFilter, StaleTarget, ViewChanged,
    PAGE_SIZE, OVERFLOW_TEXT, compile_query, count_first_page, detail_for_asset,
    later_page, lookup_sources, lookup_taxonomy, normalize_lookup_text,
    rank_for_asset,
)


@dataclass(frozen=True)
class SnapshotContext:
    data_version: int
    file_identity: tuple[int, int]
    cancel: threading.Event
    deadline: float

    def check(self):
        if self.cancel.is_set():
            raise RuntimeError("generated cancellation")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("generated read deadline")


@contextmanager
def snapshot(db, path, *, seconds=2):
    # Match the gateway: BEGIN alone is deferred. The first catalog SELECT
    # establishes the snapshot before data_version is sampled.
    db.execute("BEGIN")
    db.execute("SELECT 1 FROM assets LIMIT 1").fetchone()
    stat = os.stat(path)
    context = SnapshotContext(db.execute("PRAGMA data_version").fetchone()[0],
                              (stat.st_dev, stat.st_ino), threading.Event(),
                              time.monotonic() + seconds)
    try:
        yield context
    finally:
        db.rollback()


class GalleryQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gallery-query-generated-")
        self.path = Path(self.temp.name) / "catalog.sqlite3"
        initialize(self.path)
        self.writer = sqlite3.connect(self.path)
        self.writer.execute("PRAGMA foreign_keys=ON")
        self.writer.row_factory = sqlite3.Row
        self.reader = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        self.reader.row_factory = sqlite3.Row
        self.reader.execute("PRAGMA busy_timeout=50")
        self.incarnation = "generated-reader-1"
        self._fixture()

    def tearDown(self):
        self.reader.close()
        self.writer.close()
        self.temp.cleanup()

    def _fixture(self):
        self.writer.executemany(
            "INSERT INTO sources(source_id,name,root_path,existing_file_policy) VALUES(?,?,?,?)",
            (("source-1", "Primary", "/generated/primary", "inbox"),
             ("source-2", "Secondary", "/generated/secondary", "reviewed")))
        assets = (
            ("asset-0", "/gallery/literal%_\\thing.png", "image/png", "shared-digest", 10,
             "new", "source-1", "2026-01-01", 5, 1),
            ("asset-1", "/gallery/literalAXthing.png", "image/png", "shared-digest", 11,
             "new", "source-1", "2026-01-01", 5, 1),
            ("asset-2", "/gallery/second.jpg", "image/jpeg", "other-digest", 12,
             "reviewed", "source-2", "2026-01-02", None, 0),
            ("asset-3", "/gallery/third.png", "image/png", "shared-digest", 13,
             "new", "source-1", "2026-01-03", 4, 1),
        )
        self.writer.executemany(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,"
            "workflow_state,source_id,discovered_at,rating,favorite) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)", assets)
        self.writer.executemany(
            "INSERT INTO tags(tag_id,name,normalized_name,parent_id) VALUES(?,?,?,?)",
            (("tag-root", "Sky", "sky", None),
             ("tag-child", "Cloud", "cloud", "tag-root"),
             ("tag-empty", "Empty", "empty", None)))
        self.writer.executemany(
            "INSERT INTO tag_aliases(tag_id,alias,normalized_alias) VALUES(?,?,?)",
            (("tag-root", "Blue Sky", "blue sky"),
             ("tag-root", "Azure", "azure")))
        self.writer.executemany(
            "INSERT INTO entities(entity_id,entity_type,name,normalized_name) VALUES(?,?,?,?)",
            (("entity-character", "Character", "Robin", "robin"),
             ("entity-artist", "Artist", "Robin", "robin"),
             ("entity-empty", "Project", "Vacant", "vacant")))
        self.writer.execute(
            "INSERT INTO entity_aliases(entity_id,entity_type,alias,normalized_alias) "
            "VALUES('entity-character','Character','Bird','bird')")
        self.writer.executemany("INSERT INTO asset_tags(asset_id,tag_id) VALUES(?,?)",
                                (("asset-0", "tag-root"), ("asset-1", "tag-root"),
                                 ("asset-2", "tag-child")))
        self.writer.executemany("INSERT INTO asset_entities(asset_id,entity_id) VALUES(?,?)",
                                (("asset-0", "entity-character"),
                                 ("asset-1", "entity-artist"),
                                 ("asset-2", "entity-character")))
        self.writer.execute("INSERT INTO collections(collection_id,name,normalized_name) "
                            "VALUES('collection-1','Favorites','favorites')")
        self.writer.executemany(
            "INSERT INTO collection_members(collection_id,asset_id,position) VALUES(?,?,?)",
            (("collection-1", "asset-2", 0), ("collection-1", "asset-0", 1)))
        self.writer.execute(
            "INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,device,"
            "inode,stable_since_ns,observed_at_ns,preexisting,disposition,asset_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (assets[0][1], "source-1", 10, 0, "device", "inode", 0, 0, 0, "indexed", "asset-0"))
        self.writer.commit()

    def _first(self, query=GalleryQuery(), generation=1):
        with snapshot(self.reader, self.path) as context:
            return count_first_page(self.reader, context, query, generation, self.incarnation)

    def test_closed_query_and_literal_input_validation(self):
        for kwargs in ({"state": "all"}, {"media_type": "image/tiff"},
                       {"source_id": ""}, {"tag_id": "x" * 257},
                       {"path_text": "x" * 513}, {"path_text": "bad\x00path"},
                       {"duplicate_digest": "x" * 257},
                       {"rating": "five"}, {"favorite": "favorites"},
                       {"collection_id": "collection-1"},
                       {"order": GalleryOrder.MANUAL_COLLECTION}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GalleryQuery(**kwargs)
        query = GalleryQuery(path_text="  literal%_\\  ",
                             duplicate_digest="not-hex")
        self.assertEqual(query.path_text, "literal%_\\")
        self.assertEqual(query.with_facets(path_text="").duplicate_digest, "not-hex")
        self.assertIsNone(query.clear_filters().duplicate_digest)
        self.assertIn("ESCAPE '\\'", compile_query(query).where_sql)

    def test_exact_full_conjunction_direct_assignments_and_no_join_duplicates(self):
        query = GalleryQuery(
            state="new", source_id="source-1", media_type="image/png",
            tag_id="tag-root", entity_id="entity-character",
            rating=RatingFilter(RatingMode.EXACT, 5),
            favorite=FavoriteFilter.FAVORITES,
            path_text="literal%_\\", duplicate_digest="shared-digest")
        first = self._first(query)
        self.assertEqual(first.token.count, 1)
        self.assertEqual([row["asset_id"] for row in first.rows], ["asset-0"])
        self.assertEqual(first.rows[0]["entry_disposition"], "indexed")
        self.assertEqual(first.rows[0]["source_relation_count"], 1)
        self.assertTrue(first.rows[0]["targetable"])
        self.assertEqual(self._first(GalleryQuery(tag_id="tag-root")).token.count, 2)
        self.assertEqual(self._first(GalleryQuery(tag_id="tag-child")).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(entity_id="entity-artist")).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(path_text="literal%_")).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(path_text="LITERAL%_")).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(path_text="literalAX")).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(rating=RatingFilter(RatingMode.UNRATED))).token.count, 1)
        self.assertEqual(self._first(GalleryQuery(rating=RatingFilter(RatingMode.AT_LEAST, 4))).token.count, 3)
        self.assertEqual(self._first(GalleryQuery(favorite=FavoriteFilter.NOT_FAVORITES)).token.count, 1)

    def test_valid_zero_missing_selected_id_and_collection_clear(self):
        zero = self._first(GalleryQuery(tag_id="tag-empty", entity_id="entity-empty"))
        self.assertEqual((zero.token.count, zero.rows), (0, ()))
        for kwargs in ({"tag_id": "deleted"}, {"entity_id": "deleted"},
                       {"source_id": "deleted"},
                       {"collection_id": "deleted", "order": GalleryOrder.MANUAL_COLLECTION}):
            with self.subTest(kwargs=kwargs), self.assertRaises(StaleFilter):
                self._first(GalleryQuery(**kwargs))
        query = GalleryQuery(collection_id="collection-1",
                             order=GalleryOrder.MANUAL_COLLECTION,
                             duplicate_digest="shared-digest", state="new")
        cleared = query.clear_filters()
        self.assertEqual((cleared.collection_id, cleared.order, cleared.duplicate_digest),
                         ("collection-1", GalleryOrder.MANUAL_COLLECTION, None))
        first = self._first(cleared)
        self.assertEqual([row["asset_id"] for row in first.rows], ["asset-2", "asset-0"])

    def test_rank_detail_revision_and_stable_order(self):
        query = GalleryQuery()
        first = self._first(query)
        self.assertEqual([row["asset_id"] for row in first.rows],
                         ["asset-0", "asset-1", "asset-2", "asset-3"])
        with snapshot(self.reader, self.path) as context:
            rank = rank_for_asset(self.reader, context, query, first.token,
                                  self.incarnation, 1, "asset-2")
            missing = rank_for_asset(self.reader, context, query, first.token,
                                     self.incarnation, 1, "no-such-asset")
            detail = detail_for_asset(self.reader, context, query, first.token,
                                      self.incarnation, 1, "asset-0", first.rows[0]["revision"])
            with self.assertRaises(StaleTarget):
                detail_for_asset(self.reader, context, query, first.token,
                                 self.incarnation, 1, "asset-0", 9_999)
        self.assertEqual(rank.row, 2)
        self.assertIsNone(missing.row)
        self.assertEqual(detail.value["metadata"]["tags"][0]["aliases"], ["Azure", "Blue Sky"])
        self.assertEqual(detail.value["source"]["name"], "Primary")
        self.assertFalse(detail.incomplete)
        filtered = GalleryQuery(tag_id="tag-root", entity_id="entity-character")
        filtered_first = self._first(filtered)
        with snapshot(self.reader, self.path) as context:
            filtered_detail = detail_for_asset(
                self.reader, context, filtered, filtered_first.token,
                self.incarnation, 1, "asset-0", filtered_first.rows[0]["revision"])
        self.assertEqual(filtered_detail.value["asset"]["asset_id"], "asset-0")
        manual = GalleryQuery(collection_id="collection-1", order=GalleryOrder.MANUAL_COLLECTION)
        manual_first = self._first(manual)
        with snapshot(self.reader, self.path) as context:
            manual_rank = rank_for_asset(self.reader, context, manual, manual_first.token,
                                         self.incarnation, 1, "asset-0")
        self.assertEqual(manual_rank.row, 1)

    def test_read_context_contract_keeps_transaction_with_caller(self):
        with snapshot(self.reader, self.path) as context:
            first = count_first_page(self.reader, context, GalleryQuery(), 1,
                                     self.incarnation)
            self.assertEqual(first.token.count, 4)
            self.assertTrue(self.reader.in_transaction)
        self.assertFalse(self.reader.in_transaction)

    def test_snapshot_version_generation_and_file_identity(self):
        first = self._first()
        with snapshot(self.reader, self.path) as context:
            with self.assertRaises(ViewChanged):
                rank_for_asset(self.reader, context, GalleryQuery(), first.token,
                               "other-reader", 1, "asset-0")
            with self.assertRaises(ViewChanged):
                later_page(self.reader, context, GalleryQuery(state="new"), first.token,
                           self.incarnation, 1, 1)
            with self.assertRaises(ViewChanged):
                rank_for_asset(self.reader, context, GalleryQuery(), first.token,
                               self.incarnation, 2, "asset-0")
        self.writer.execute("UPDATE assets SET favorite=0 WHERE asset_id='asset-0'")
        self.writer.commit()
        with snapshot(self.reader, self.path) as context:
            self.assertGreater(context.data_version, first.token.data_version)
            with self.assertRaises(ViewChanged):
                rank_for_asset(self.reader, context, GalleryQuery(), first.token,
                               self.incarnation, 1, "asset-0")
        replacement = Path(self.temp.name) / "replacement.sqlite3"
        initialize(replacement)
        os.replace(replacement, self.path)
        with snapshot(self.reader, self.path) as context:
            self.assertNotEqual(context.file_identity, first.token.file_identity)
            with self.assertRaises(ViewChanged):
                rank_for_asset(self.reader, context, GalleryQuery(), first.token,
                               self.incarnation, 1, "asset-0")

    def test_oversized_stored_text_and_detail_are_non_targetable(self):
        huge = "/gallery/" + "x" * 500_000
        self.writer.execute(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
            "VALUES(?,?,?,?,?)", ("huge-path", huge, "image/png", "huge-digest", 0))
        self.writer.execute(
            "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json) "
            "VALUES(?,?,?,?)", ("huge-prov", "asset-0", "generated", "x" * 500_000))
        self.writer.execute(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
            "VALUES(?,?,?,?,?)", ("nul-path", "/gallery/a\x00b.png", "image/png", "nul-digest", 0))
        self.writer.commit()
        first = self._first()
        overflow_rows = [row for row in first.rows if row["overflow"]]
        self.assertEqual(len(overflow_rows), 2)
        self.assertTrue(all(row["current_path"] == OVERFLOW_TEXT and not row["targetable"]
                            for row in overflow_rows))
        self.assertLess(len(str(first.rows).encode("utf-8")), 2 * 1024 * 1024)
        with snapshot(self.reader, self.path) as context:
            detail = detail_for_asset(self.reader, context, GalleryQuery(), first.token,
                                      self.incarnation, 1, "asset-0", first.rows[0]["revision"])
        self.assertTrue(detail.incomplete)
        self.assertEqual(detail.value["provenance"][0]["details_json"], OVERFLOW_TEXT)
        self.assertLess(len(str(detail.value).encode("utf-8")), 65_536)

    def test_alias_canonical_keyset_entity_category_and_source_only(self):
        self.writer.execute(
            "INSERT INTO tag_aliases(tag_id,alias,normalized_alias) VALUES(?,?,?)",
            ("tag-root", "Amazing Sky", "amazing sky"))
        self.writer.commit()
        with snapshot(self.reader, self.path) as context:
            alias = lookup_taxonomy(self.reader, context, LookupKind.TAG, "  BLUE   sky  ")
            two_aliases = lookup_taxonomy(self.reader, context, LookupKind.TAG, "A")
            same_name = lookup_taxonomy(self.reader, context, LookupKind.ENTITY, "Rob")
            bird = lookup_taxonomy(self.reader, context, LookupKind.ENTITY, "Bird",
                                   entity_type="Character")
        self.assertEqual([row["id"] for row in alias.rows], ["tag-root"])
        self.assertEqual([row["id"] for row in two_aliases.rows], ["tag-root"])
        self.assertEqual({(row["id"], row["entity_type"]) for row in same_name.rows},
                         {("entity-character", "Character"), ("entity-artist", "Artist")})
        self.assertEqual([row["id"] for row in bird.rows], ["entity-character"])
        self.writer.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                            ("marker-tag", OVERFLOW_TEXT, OVERFLOW_TEXT.casefold()))
        self.writer.commit()
        with snapshot(self.reader, self.path) as context:
            marker = lookup_taxonomy(self.reader, context, LookupKind.TAG,
                                     "[unavailable")
        self.assertEqual([row["id"] for row in marker.rows], ["marker-tag"])
        self.assertTrue(marker.rows[0]["selectable"])
        self.assertEqual(normalize_lookup_text("  RO\tBIN  "), "ro bin")
        with self.assertRaises(ValueError):
            normalize_lookup_text("x" * 129)
        with self.assertRaises(ValueError):
            normalize_lookup_text("bad\x00name")
        for number in range(70):
            self.writer.execute("INSERT INTO tags(tag_id,name,normalized_name) VALUES(?,?,?)",
                                (f"bulk-{number:03d}", f"Bulk {number:03d}",
                                 f"bulk {number:03d}"))
        self.writer.commit()
        with snapshot(self.reader, self.path) as context:
            page1 = lookup_taxonomy(self.reader, context, LookupKind.TAG, "Bulk")
            page2 = lookup_taxonomy(self.reader, context, LookupKind.TAG, "Bulk",
                                    cursor=page1.next_cursor)
        self.assertEqual((len(page1.rows), len(page2.rows)), (64, 6))
        self.assertEqual(len({row["id"] for row in (*page1.rows, *page2.rows)}), 70)
        def deny_source_entries(action, arg1, _arg2, _database, _trigger):
            if action == sqlite3.SQLITE_READ and arg1 == "source_entries":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.reader.set_authorizer(deny_source_entries)
        try:
            with snapshot(self.reader, self.path) as context:
                sources = lookup_sources(self.reader, context, "Pri")
        finally:
            self.reader.set_authorizer(None)
        self.assertEqual([row["id"] for row in sources.rows], ["source-1"])

    def test_context_cancel_and_deadline_refuse(self):
        with snapshot(self.reader, self.path) as context:
            context.cancel.set()
            with self.assertRaisesRegex(RuntimeError, "cancellation"):
                count_first_page(self.reader, context, GalleryQuery(), 1, self.incarnation)
        with snapshot(self.reader, self.path, seconds=.000001) as context:
            with self.assertRaises(TimeoutError):
                count_first_page(self.reader, context, GalleryQuery(), 1, self.incarnation)

    def test_hundred_thousand_rows_only_project_requested_page(self):
        rows = ((f"mass-{number:06d}", f"/mass/{number:06d}.png", "image/png",
                 "mass-digest", 0, "2026-01-04") for number in range(100_000))
        self.writer.executemany(
            "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,discovered_at) "
            "VALUES(?,?,?,?,?,?)", rows)
        self.writer.commit()
        # This fixture checks deep-page correctness, not a two-second latency budget.
        # The separate deadline test keeps the bounded-read refusal contract.
        with snapshot(self.reader, self.path, seconds=20) as context:
            first = count_first_page(self.reader, context, GalleryQuery(),
                                     1, self.incarnation)
        self.assertEqual(first.token.count, 100_004)
        self.assertEqual(len(first.rows), PAGE_SIZE)
        self.assertEqual(first.rows[0]["asset_id"], "asset-0")
        with snapshot(self.reader, self.path, seconds=20) as context:
            page = later_page(self.reader, context, GalleryQuery(), first.token,
                              self.incarnation, 1, 390)
        self.assertEqual(len(page.rows), 164)
        self.assertEqual(page.rows[0]["asset_id"], "mass-099836")


class JournalSnapshotTests(unittest.TestCase):
    def test_wal_and_rollback_snapshots_keep_count_and_first_page_together(self):
        for mode in ("delete", "wal"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="gallery-journal-generated-") as directory:
                path = Path(directory) / "catalog.sqlite3"
                initialize(path)
                writer = sqlite3.connect(path, check_same_thread=False)
                reader = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                reader.row_factory = sqlite3.Row
                try:
                    self.assertEqual(writer.execute(f"PRAGMA journal_mode={mode}").fetchone()[0], mode)
                    writer.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                                   "VALUES('before','/before.png','image/png','digest',0)")
                    writer.commit()
                    with snapshot(reader, path) as context:
                        completed = threading.Event()
                        def append_asset():
                            writer.execute("INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size) "
                                           "VALUES('after','/after.png','image/png','digest',0)")
                            writer.commit()
                            completed.set()
                        thread = threading.Thread(target=append_asset)
                        thread.start()
                        if mode == "wal":
                            self.assertTrue(completed.wait(1))
                        else:
                            self.assertFalse(completed.wait(.05))
                        first = count_first_page(reader, context, GalleryQuery(), 1, "reader-1")
                        self.assertEqual(first.token.count, 1)
                        self.assertEqual([row["asset_id"] for row in first.rows], ["before"])
                    thread.join(timeout=2)
                    self.assertFalse(thread.is_alive())
                    with snapshot(reader, path) as context:
                        self.assertGreater(context.data_version, first.token.data_version)
                        with self.assertRaises(ViewChanged):
                            rank_for_asset(reader, context, GalleryQuery(), first.token,
                                           "reader-1", 1, "before")
                finally:
                    reader.close()
                    writer.close()


if __name__ == "__main__":
    unittest.main()
