from pathlib import Path
import sqlite3
import tempfile
import unittest

from benchmarks.embedding_fixture import CHARACTERS, generate
from benchmarks.image_embeddings import STORE_SCHEMA, read_vectors, score_retrieval, write_vector
from defiantmaple.catalog import connect, index_file, initialize


META = {"name": "example/model", "revision": "a" * 40, "license": "Apache-2.0",
        "weights_sha256": "b" * 64, "method": "test", "preprocessing_version": "v1",
        "fixture_schema": "defiantmaple.embedding-fixture.v2"}


class EmbeddingBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_fixture_repeats_exactly_and_manifest_matches_files(self):
        first = generate(self.root / "first")
        second = generate(self.root / "second")
        self.assertEqual(first, second)
        self.assertEqual(len(first["items"]), len(CHARACTERS) * 4)
        self.assertEqual({item["role"] for item in first["items"]}, {"gallery", "query"})
        from hashlib import sha256
        for item in first["items"]:
            self.assertEqual(item["sha256"], sha256((self.root / "first" / item["file"]).read_bytes()).hexdigest())

    def test_vectors_are_versioned_and_catalog_assets_are_untouched(self):
        fixture = generate(self.root / "fixture")
        catalog = self.root / "catalog.sqlite3"
        initialize(catalog)
        asset_id = index_file(catalog, self.root / "fixture" / fixture["items"][0]["file"])
        with connect(catalog) as db:
            before = dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone())
        store = self.root / "vectors.sqlite3"
        with sqlite3.connect(store) as db:
            db.executescript(STORE_SCHEMA)
            write_vector(db, fixture["items"][0], META, [3, 4])
            other_version = {**META, "revision": "c" * 40}
            write_vector(db, fixture["items"][0], other_version, [4, 3])
            self.assertEqual(len(read_vectors(db, META)), 1)
            self.assertEqual(len(read_vectors(db, other_version)), 1)
            self.assertEqual(db.execute("SELECT COUNT(DISTINCT model_revision) FROM vectors").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT dimensions FROM vectors LIMIT 1").fetchone()[0], 2)
        with connect(catalog) as db:
            self.assertEqual(before, dict(db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()))

    def test_rejects_unpinned_and_invalid_vectors_and_detects_corruption(self):
        item = {"sha256": "d" * 64, "file": "a.png", "label": "a", "role": "gallery"}
        with sqlite3.connect(self.root / "vectors.sqlite3") as db:
            db.executescript(STORE_SCHEMA)
            for meta, values in [({**META, "revision": ""}, [1]),
                                 ({**META, "license": ""}, [1]),
                                 (META, [0]), (META, [float("nan")])]:
                with self.assertRaises(ValueError):
                    write_vector(db, item, meta, values)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 0)
            write_vector(db, item, META, [1, 2])
            db.execute("UPDATE vectors SET vector_f32=X'00'")
            with self.assertRaisesRegex(ValueError, "Damaged vector"):
                read_vectors(db, META)

    def test_rank_one_and_reciprocal_rank_are_measured(self):
        rows = [
            {"file": "a0", "label": "a", "role": "gallery", "vector": (1, 0)},
            {"file": "b0", "label": "b", "role": "gallery", "vector": (0, 1)},
            {"file": "a1", "label": "a", "role": "query", "vector": (.9, .1)},
            {"file": "b1", "label": "b", "role": "query", "vector": (.8, .2)},
        ]
        score = score_retrieval(rows)
        self.assertEqual(score["recall_at_1"], .5)
        self.assertEqual(score["mean_reciprocal_rank"], .75)
        self.assertIn("not calibrated", score["score_warning"])
        with self.assertRaisesRegex(ValueError, "different dimensions"):
            score_retrieval([*rows, {**rows[0], "vector": (1, 0, 0)}])


if __name__ == "__main__":
    unittest.main()
