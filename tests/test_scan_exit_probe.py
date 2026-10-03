"""Transaction semantics and bounded public evidence for the exit-only probe."""
from contextlib import redirect_stdout
import copy
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import source_scan_exit_probe as probe
from benchmarks import source_scan_exit_series as series


class ProbeTests(unittest.TestCase):
    def test_original_commit_rollback_and_custom_factory(self):
        original_connect = sqlite3.connect
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "test.sqlite3"
            db = sqlite3.connect(database)
            db.execute("CREATE TABLE t (n INTEGER)")
            db.close()

            class Custom(sqlite3.Connection):
                exits = 0

                def __exit__(self, *args):
                    type(self).exits += 1
                    return super().__exit__(*args)

            with probe.ExitProbe() as active:
                active.phase = "indexing"
                active.phases["indexing"] = {"elapsed_ns": 0,
                    "strata": {name: probe.empty_metric() for name in probe.STRATA}}
                connection = sqlite3.connect(database)
                with connection:
                    connection.execute("INSERT INTO t VALUES (1)")
                connection.close()
                with self.assertRaisesRegex(RuntimeError, "rollback"):
                    connection = sqlite3.connect(database)
                    with connection:
                        connection.execute("INSERT INTO t VALUES (2)")
                        raise RuntimeError("rollback")
                connection.close()
                custom = sqlite3.connect(database, factory=Custom)
                with custom:
                    self.assertIs(type(custom), Custom)
                custom.close()
                custom = sqlite3.connect(database, 5, 0, "DEFERRED", True, Custom)
                with custom:
                    self.assertIs(type(custom), Custom)
                custom.close()
                active.phase = None
            self.assertIs(sqlite3.connect, original_connect)
            self.assertEqual(Custom.exits, 2)
            counts = active.phases["indexing"]["strata"]
            self.assertEqual(counts["transaction_normal"]["count"], 1)
            self.assertEqual(counts["transaction_exception"]["count"], 1)
            self.assertEqual(sum(item["count"] for item in counts.values()), 2)
            connection = sqlite3.connect(database)
            with connection:
                self.assertEqual(connection.execute("SELECT n FROM t").fetchall(), [(1,)])
            connection.close()

    def test_patch_restored_after_body_exception_and_baseline_same_phase_hooks(self):
        original = (sqlite3.connect, probe.soak._paged_pass, probe.soak.scan_sources)
        with self.assertRaisesRegex(RuntimeError, "body"):
            with probe.ExitProbe():
                raise RuntimeError("body")
        self.assertEqual((sqlite3.connect, probe.soak._paged_pass, probe.soak.scan_sources), original)
        with probe.ExitProbe(instrumented=False):
            # Baseline installs the same phase hooks but leaves sqlite.connect
            # untouched. It still follows the unchanged soak's tracing policy.
            self.assertIs(sqlite3.connect, original[0])
            self.assertIsNot(probe.soak._paged_pass, original[1])
            self.assertIsNot(probe.soak.scan_sources, original[2])
        self.assertEqual((sqlite3.connect, probe.soak._paged_pass, probe.soak.scan_sources), original)

    def test_original_exit_exception_propagates_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "deferred.sqlite3"
            setup = sqlite3.connect(database)
            setup.execute("PRAGMA foreign_keys=ON")
            setup.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
            setup.execute("CREATE TABLE child(pid INTEGER REFERENCES parent(id) "
                          "DEFERRABLE INITIALLY DEFERRED)")
            setup.close()
            with probe.ExitProbe() as active:
                active.phase = "indexing"
                active.phases["indexing"] = {"elapsed_ns": 0,
                    "strata": {name: probe.empty_metric() for name in probe.STRATA}}
                connection = sqlite3.connect(database)
                connection.execute("PRAGMA foreign_keys=ON")
                with self.assertRaises(sqlite3.IntegrityError):
                    with connection:
                        connection.execute("INSERT INTO child VALUES (99)")
                connection.close()
                active.phase = None
            self.assertEqual(active.phases["indexing"]["strata"]["transaction_normal"]["count"], 1)
            check = sqlite3.connect(database)
            self.assertEqual(check.execute("SELECT COUNT(*) FROM child").fetchone()[0], 0)
            check.close()


class SeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ):
            for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB",
                        "RUNNER_ENVIRONMENT", "ImageOS", "ImageVersion"):
                os.environ.pop(key, None)
            first = series.run_pair(64, 16, pair_index=1,
                                    session_token="a" * 32)
            cls.report = {"schema": series.SERIES_SCHEMA, "status": "complete",
                          "identity": first["identity"], "code": first["code"],
                          "runtime": first["runtime"],
                          "configuration": {"count": 64, "page_size": 16, "pairs": 4},
                          "pairs": [], "issues": [], "note": series.NOTE}
            for index, order in enumerate(series.ORDERS, 1):
                pair = copy.deepcopy(first)
                pair["configuration"]["pair_index"] = index
                pair["order"] = list(order)
                pair["samples"] = [{"position": position,
                    "trial": copy.deepcopy(next(item["trial"] for item in first["samples"]
                        if item["trial"]["variant"] == variant))}
                    for position, variant in enumerate(order, 1)]
                cls.report["pairs"].append(pair)
            cls.report["attribution"] = series._attribution(cls.report["pairs"])

    def test_complete_series_raw_invariants_and_closed_schema(self):
        report = self.report
        self.assertEqual(report["status"], "complete")
        self.assertEqual([pair["order"] for pair in report["pairs"]],
                         [list(order) for order in series.ORDERS])
        self.assertEqual(len({pair["identity"]["session_token"] for pair in report["pairs"]}), 1)
        for pair in report["pairs"]:
            self.assertEqual(pair["cleanup"], {"workers_reaped": True,
                "owned_storage_removed": True, "storage_retained": False})
            for sample in pair["samples"]:
                trial = sample["trial"]
                self.assertTrue(trial["soak"]["source_bytes_unchanged"])
                self.assertTrue(trial["soak"]["stable_identity_retained"])
                self.assertEqual(trial["soak"]["fixture"]["recipe"],
                                 series.soak.CANONICAL_FIXTURE_RECIPE)
        series.validate_public_report(report)
        for mutation in (lambda x: x.update(private_path="/secret"),
                         lambda x: x["pairs"][1]["order"].reverse(),
                         lambda x: x["pairs"][2]["identity"].update(job_id="other"),
                         lambda x: x["pairs"][0]["samples"][0]["trial"]["code"]["digests"].update(
                             {series.CODE_FILES[0]: "0" * 64})):
            changed = copy.deepcopy(report)
            mutation(changed)
            with self.assertRaises((ValueError, KeyError)):
                series.validate_public_report(changed)

    def test_histogram_and_attribution_screen_reject_forgery(self):
        changed = copy.deepcopy(self.report)
        trial = next(s["trial"] for s in changed["pairs"][0]["samples"]
                     if s["trial"]["variant"] == "instrumented")
        trial["phases"]["indexing"]["strata"]["transaction_normal"]["buckets"].append(0)
        with self.assertRaises(ValueError):
            series.validate_series(changed)
        changed = copy.deepcopy(self.report)
        changed["attribution"]["verdict"] = (
            "attributed" if changed["attribution"]["verdict"] == "inconclusive"
            else "inconclusive")
        with self.assertRaises(ValueError):
            series.validate_series(changed)
        # A complete protocol with an out-of-screen ratio is valid evidence,
        # but its diagnostic result must be inconclusive.
        changed = copy.deepcopy(self.report)
        pair = changed["pairs"][0]
        baseline = next(s["trial"] for s in pair["samples"]
                        if s["trial"]["variant"] == "baseline")
        measured = next(s["trial"] for s in pair["samples"]
                        if s["trial"]["variant"] == "instrumented")
        # Directly exercise the pure predeclared screen without breaking the
        # soak's own elapsed/rounded-second checks.
        baseline["soak"]["timings_ns"]["indexing"] = max(1, measured["soak"]["timings_ns"]["indexing"] // 2)
        self.assertEqual(series._attribution(changed["pairs"])["verdict"], "inconclusive")
        impossible = {"count": 1, "total_ns": 0, "min_ns": 0, "max_ns": 9,
                      "buckets": [1] + [0] * len(probe.BUCKET_UPPER_NS)}
        with self.assertRaises(ValueError):
            series._metric(impossible)

    def test_dominance_uses_full_indexing_interval(self):
        pairs = copy.deepcopy(self.report["pairs"])
        for pair in pairs:
            trials = {item["trial"]["variant"]: item["trial"] for item in pair["samples"]}
            instrumented = trials["instrumented"]
            baseline = trials["baseline"]
            phase = instrumented["phases"]["indexing"]
            phase["elapsed_ns"] = 100
            instrumented["soak"]["timings_ns"]["indexing"] = 130
            baseline["soak"]["timings_ns"]["indexing"] = 130
            for metric in phase["strata"].values():
                metric["total_ns"] = 0
            phase["strata"]["transaction_normal"]["total_ns"] = 60
        self.assertEqual(series._attribution(pairs)["verdict"], "inconclusive")

    def test_deadline_stop_cleanup_and_duplicate_key_parse(self):
        with self.assertRaises(ValueError):
            series.old.parse_report('{"schema":1,"schema":2}')
        with patch.dict(os.environ):
            for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB"):
                os.environ.pop(key, None)
            with patch.object(series, "_run_child", return_value=(
                    None, series.issue("child_timeout"), True)) as child:
                failure = series.run_pair(64, 16, pair_index=1, trial_timeout=.001,
                                          pair_timeout=.01, session_token="a" * 32)
            self.assertEqual(child.call_count, 1)
            self.assertEqual(failure["status"], "incomplete")
            self.assertTrue(failure["cleanup"]["owned_storage_removed"])
            with patch.object(series, "run_pair", return_value=failure) as pair:
                report = series.run_series(64, 16, session_token="a" * 32)
            self.assertEqual(pair.call_count, 1)
            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(len(report["pairs"]), 1)

    def test_cleanup_time_counts_against_pair_deadline(self):
        first = self.report["pairs"][0]
        samples = {item["trial"]["variant"]: item["trial"] for item in first["samples"]}
        def fake_child(command, environment, timeout):
            variant = command[command.index("--variant") + 1]
            return copy.deepcopy(samples[variant]), None, True
        with patch.dict(os.environ):
            for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB"):
                os.environ.pop(key, None)
            with patch.object(series, "_run_child", side_effect=fake_child):
                with patch.object(series.time, "perf_counter_ns",
                                  side_effect=[0, 0, 0, 90_000_000, 110_000_000]):
                    pair = series.run_pair(64, 16, pair_timeout=.1,
                                           session_token="a" * 32)
        self.assertEqual(pair["status"], "incomplete")
        self.assertIn("pair_deadline", [item["code"] for item in pair["issues"]])
        self.assertTrue(pair["cleanup"]["owned_storage_removed"])


if __name__ == "__main__":
    unittest.main()
