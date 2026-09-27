from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from PIL import Image

from benchmarks.private_image_eval import _aggregate
from defiantmaple.catalog import index_file, initialize
from defiantmaple.private_eval import (PrivateSelectionStore, assert_outside_git,
                                       assert_outside_sources, sanitize_public_summary)
from defiantmaple.sources import add_source
from scripts.check_public_artifacts import _check_json, validate


class PrivateEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.art = self.root / "fictional-art"
        self.art.mkdir()
        self.database = self.root / "library.sqlite3"
        initialize(self.database)
        self.source = add_source(self.database, self.art, existing_file_policy="inbox")
        self.asset_ids = []
        for index in range(3):
            path = self.art / f"fictional-{index}.png"
            Image.new("RGB", (48, 48), (index * 50, 80, 120)).save(path)
            self.asset_ids.append(index_file(self.database, path,
                                             source_id=self.source["source_id"]))

    def test_selection_rights_validation_and_no_asset_mutation(self):
        store_path = self.root / "outside" / "selections.private.sqlite3"
        store = PrivateSelectionStore(store_path, self.database)
        with self.assertRaisesRegex(ValueError, "anonymous"):
            store.select(self.asset_ids[0], "real-character-name", "reference", "artist_owned")
        with self.assertRaisesRegex(ValueError, "role"):
            store.select(self.asset_ids[0], "character-001", "prediction", "artist_owned")
        store.select(self.asset_ids[0], "character-001", "reference", "artist_owned", "local note")
        store.select(self.asset_ids[1], "character-001", "query", "permission_granted")
        store.select(self.asset_ids[2], "character-002", "near-lookalike-negative", "uncertain")
        self.assertEqual(len(store.entries()), 2)
        self.assertEqual(len(store.entries(include_uncertain=True)), 3)
        self.assertEqual(next(row["private_notes"] for row in store.entries()
                              if row["role"] == "reference"), "local note")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM provenance").fetchone()[0], 3)

    def test_private_destinations_reject_artwork_and_git(self):
        with self.assertRaisesRegex(ValueError, "outside every artwork"):
            assert_outside_sources(self.art / "vectors.sqlite3", [self.art])
        with self.assertRaisesRegex(ValueError, "outside every artwork"):
            PrivateSelectionStore(self.art / "manifest.sqlite3", self.database)
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        with self.assertRaisesRegex(ValueError, "outside Git"):
            assert_outside_git(repo / "vectors.sqlite3")

    def test_summary_contains_only_aggregate_anonymized_metrics(self):
        rows = [
            {"anonymous_id": "character-001", "role": "reference", "vector": (1, 0)},
            {"anonymous_id": "character-002", "role": "reference", "vector": (0, 1)},
            {"anonymous_id": "character-001", "role": "query", "vector": (.9, .1)},
            {"anonymous_id": "character-002", "role": "query", "vector": (.8, .2)},
            {"anonymous_id": "character-001", "role": "near-lookalike-negative",
             "vector": (.7, .3)},
        ]
        report = _aggregate(rows, [20.0, 30.0], 500.0, 1)
        self.assertEqual(report["recall_at_1"], .5)
        self.assertAlmostEqual(report["mean_reciprocal_rank"], 2 / 3)
        self.assertEqual(report["dataset_counts"]["excluded_uncertain"], 1)
        self.assertEqual(report["false_match_categories"]["other"], 1)
        encoded = json.dumps(report)
        self.assertNotIn("character-001", encoded)
        self.assertNotIn("anonymous_id", encoded)
        with self.assertRaisesRegex(ValueError, "unknown"):
            sanitize_public_summary({**report, "per_image": rows})
        with self.assertRaisesRegex(ValueError, "identifying"):
            sanitize_public_summary({**report, "false_match_categories": {"character-001": 1}})
        lookalike = _aggregate([
            {"anonymous_id": "character-001", "role": "reference", "vector": (1, 0)},
            {"anonymous_id": "character-002", "role": "near-lookalike-negative",
             "vector": (0, 1)},
            {"anonymous_id": "character-001", "role": "query", "vector": (.2, .9)},
        ], [15.0], 100.0, 0)
        self.assertEqual(lookalike["false_match_categories"]["lookalike"], 1)
        self.assertEqual(lookalike["recall_at_1"], 0)

    def test_repository_checker_rejects_private_files_and_paths(self):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        private = repo / "private-eval"
        private.mkdir()
        (private / "manifest.json").write_text("{}", encoding="utf-8")
        subprocess.run(["git", "add", "private-eval/manifest.json"], cwd=repo, check=True)
        self.assertTrue(any("private artifact" in error for error in validate(repo)))
        public = repo / "benchmarks" / "other-report.json"
        public.parent.mkdir()
        public.write_text(json.dumps({"path": "/home/person/NAS/art.png"}), encoding="utf-8")
        errors = []
        _check_json(public, "benchmarks/other-report.json", errors)
        self.assertTrue(any("absolute private filesystem path" in error for error in errors))
        public.write_text(json.dumps({"label": "fictional-but-unreviewed"}), encoding="utf-8")
        errors = []
        _check_json(public, "benchmarks/other-report.json", errors)
        self.assertTrue(any("private per-image fields" in error for error in errors))
        legacy = repo / "benchmarks/results/2026-09-25/qt-linux-x64.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(json.dumps({
            "package_path": "/home/runner/work/DefiantMaple/DefiantMaple/prototypes/qt/DefiantMapleQt.bin",
            "other_path": "/home/artist/private.png",
        }), encoding="utf-8")
        errors = []
        _check_json(legacy, "benchmarks/results/2026-09-25/qt-linux-x64.json", errors)
        self.assertTrue(any("absolute private filesystem path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
