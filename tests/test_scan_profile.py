import hashlib
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from benchmarks import source_scan_profile as profile
from benchmarks import source_scan_soak as soak
from defiantmaple import catalog, sources
from scripts.check_public_artifacts import _check_json


class ScanProfileTests(unittest.TestCase):
    def patched_functions(self):
        return (
            catalog.connect, sources.connect, soak.connect,
            sources._iter_candidates, sources.index_file,
            sources._sha256_if_unchanged, sqlite3.connect, hashlib.sha256,
            soak._paged_pass, soak.scan_sources,
        )

    def test_nested_exclusive_timings_partition_pass(self):
        ticks = iter((0, 10, 30, 50, 60, 70, 100, 120))
        profiler = profile.ScanProfiler(clock=lambda: next(ticks))
        with profiler.phase("observation"):
            with profiler.measure("enumeration"):
                pass
            with profiler.measure("index_file"):
                with profiler.measure("sha256_update"):
                    pass
        metrics = profiler.phases["observation"]["operations"]
        self.assertEqual(metrics["scan_pass"]["inclusive_ns"], 120)
        self.assertEqual(metrics["scan_pass"]["exclusive_ns"], 50)
        self.assertEqual(metrics["index_file"]["inclusive_ns"], 50)
        self.assertEqual(metrics["index_file"]["exclusive_ns"], 40)
        self.assertEqual(sum(item["exclusive_ns"] for item in metrics.values()), 120)
        self.assertTrue(all(item["exclusive_ns"] >= 0 for item in metrics.values()))

    def test_exception_balances_spans_and_only_records_failure_count(self):
        profiler = profile.ScanProfiler()
        with self.assertRaisesRegex(OSError, "fictional sensitive detail"):
            with profiler.phase("observation"):
                with profiler.measure("enumeration"):
                    raise OSError("fictional sensitive detail")
        self.assertIsNone(profiler._phase)
        self.assertEqual(profiler._stack, [])
        report = profiler.report()
        self.assertEqual(report["observation"]["operations"]["enumeration"]["failures"], 1)
        self.assertNotIn("fictional sensitive detail", json.dumps(report))
        with profiler.phase("indexing"):
            pass
        with self.assertRaisesRegex(ValueError, "Unknown profiler"):
            with profiler.phase("fictional source path"):
                pass

    def test_patches_restore_after_body_and_partial_install_errors(self):
        original = self.patched_functions()
        with self.assertRaisesRegex(RuntimeError, "body failed"):
            with profile.ScanProfiler():
                self.assertNotEqual(self.patched_functions(), original)
                with self.assertRaisesRegex(RuntimeError, "Only one"):
                    with profile.ScanProfiler():
                        pass
                raise RuntimeError("body failed")
        self.assertEqual(self.patched_functions(), original)
        with patch.object(profile.ScanProfiler, "_wrap", side_effect=RuntimeError("install failed")):
            with self.assertRaisesRegex(RuntimeError, "install failed"):
                with profile.ScanProfiler():
                    pass
        self.assertEqual(self.patched_functions(), original)
        with profile.ScanProfiler():
            pass
        self.assertEqual(self.patched_functions(), original)

    def test_sqlite_results_settings_and_rollback_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="fictional-profile-test-") as temporary:
            database = Path(temporary) / "catalog.sqlite3"
            catalog.initialize(database)

            def settings():
                with catalog.connect(database) as db:
                    return tuple(db.execute(f"PRAGMA {name}").fetchone()[0]
                                 for name in ("foreign_keys", "journal_mode", "synchronous"))

            expected = settings()
            profiler = profile.ScanProfiler()
            with profiler:
                with profiler.phase("observation"):
                    self.assertEqual(settings(), expected)
                    with self.assertRaisesRegex(RuntimeError, "rollback this insert"):
                        with catalog.connect(database) as db:
                            db.execute("INSERT INTO sources(source_id,name,root_path,existing_file_policy) "
                                       "VALUES(?,?,?,?)", ("fictional-id", "fictional", "fictional", "inbox"))
                            self.assertEqual(db.execute("SELECT name FROM sources").fetchall()[0]["name"],
                                             "fictional")
                            raise RuntimeError("rollback this insert")
                with profiler.phase("indexing"):
                    with catalog.connect(database) as db:
                        self.assertEqual(list(db.execute("SELECT * FROM sources")), [])
            with catalog.connect(database) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 0)
            counts = profiler.report()["observation"]["counts"]
            self.assertEqual(counts["transaction_exits_with_transaction"], 1)
            self.assertEqual(counts["exceptional_transaction_exits"], 1)
            self.assertEqual(profiler.report()["indexing"]["operations"]
                             ["sqlite_result_fetch"]["failures"], 0)

    def test_run_error_restores_tracing_and_instrumentation(self):
        original = self.patched_functions()
        calls = 0

        def failed_soak(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {}
            tracemalloc.start()
            raise RuntimeError("fictional soak failure")

        with patch.object(soak, "run", side_effect=failed_soak):
            with self.assertRaisesRegex(RuntimeError, "fictional soak failure"):
                profile.run(64, 16)
        self.assertFalse(tracemalloc.is_tracing())
        self.assertEqual(self.patched_functions(), original)
        tracemalloc.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "existing tracemalloc"):
                profile.run(64, 16)
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

    def test_trial_failure_restores_every_binding_and_tracer_in_both_orders(self):
        original = self.patched_functions()
        def failure(*args, **kwargs):
            tracemalloc.start()
            raise OSError('fictional private detail')
        for recipe in (soak.FIXTURE_RECIPE, soak.CANONICAL_FIXTURE_RECIPE):
            for order in (("baseline", "instrumented"), ("instrumented", "baseline")):
                for variant in order:
                    with self.subTest(recipe=recipe, order=order, variant=variant), \
                            patch.object(soak, "run", side_effect=failure):
                        with self.assertRaises(OSError):
                            profile.run_trial(64, 16, variant, fixture_recipe=recipe)
                    self.assertFalse(tracemalloc.is_tracing())
                    self.assertEqual(self.patched_functions(), original)

    def test_canonical_payloads_have_pinned_hashes_valid_pixels_and_no_encoder(self):
        with patch.object(soak.Image.Image, 'save', side_effect=AssertionError('Unexpected encoding')), \
                patch.object(soak, '_fictional_pngs', side_effect=AssertionError('Unexpected generation')):
            payloads = soak._fixture_pngs(soak.CANONICAL_FIXTURE_RECIPE)
            for count in (*range(64, 73), 2047, 2048):
                descriptor = soak.fixture_descriptor(count, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
                self.assertEqual(descriptor['initial_bytes'], sum(len(payloads[index % 8]) for index in range(count)))
                self.assertEqual(descriptor['resume_added_bytes'], 105)
        self.assertEqual(tuple(map(len, payloads)), (105, 108, 108, 108, 109, 108, 108, 108))
        self.assertEqual(tuple(hashlib.sha256(value).hexdigest() for value in payloads), soak.CANONICAL_PNG_SHA256)
        self.assertEqual(hashlib.sha256(b''.join(len(value).to_bytes(4, 'big') + value
                                                for value in payloads)).hexdigest(),
                         '5b4ef21dad6cd972d9e3a128eb4075bb736bb0784627be7f336ae2f3ed0bffcb')
        self.assertEqual(len(set(payloads)), 8)
        self.assertFalse(tracemalloc.is_tracing())
        for index, payload in enumerate(payloads):
            with soak.Image.open(BytesIO(payload)) as image:
                image.verify()  # PNG framing and chunk CRCs.
            with soak.Image.open(BytesIO(payload)) as image:
                image.load()
                self.assertEqual(image.size, (32, 32))
                self.assertEqual(image.mode, 'RGBA')
                expected = ((index * 37) % 256, (index * 61) % 256, 160, 255)
                self.assertTrue(all(image.getpixel((x, y)) == expected
                                    for y in range(32) for x in range(32)))

    def test_unknown_recipe_and_corrupt_corpus_refuse_before_storage_tracing_and_scanning(self):
        hex_values = soak._CANONICAL_PNG_HEX
        variants = (('payload-byte', '_CANONICAL_PNG_HEX',
                     (hex_values[0][:-2] + '83', *hex_values[1:])),
                    ('order', '_CANONICAL_PNG_HEX', (hex_values[1], hex_values[0], *hex_values[2:])),
                    ('missing', '_CANONICAL_PNG_HEX', hex_values[:-1]),
                    ('digest', 'CANONICAL_PNG_SHA256', ('f' * 64,) * 8),
                    ('size', 'CANONICAL_PNG_SIZES', (106, *soak.CANONICAL_PNG_SIZES[1:])),
                    ('corpus', 'CANONICAL_CORPUS_SHA256', 'f' * 64))
        with patch.object(soak.tempfile, 'TemporaryDirectory') as storage, \
                patch.object(soak.tracemalloc, 'start') as tracing, \
                patch.object(soak, 'initialize') as initialize, \
                patch.object(soak, '_paged_pass') as scan:
            with self.assertRaises(ValueError):
                soak.run(64, 16, fixture_recipe='unknown-fictional-recipe')
            for label, name, value in variants:
                with self.subTest(label=label), patch.object(soak, name, value), self.assertRaises(ValueError):
                    soak.run(64, 16, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
        for function in (storage, tracing, initialize, scan):
            function.assert_not_called()

    def test_byte_verification_detects_same_size_mtime_corruption_after_tracing(self):
        calls = 0
        byte_check_tracing = []
        real_read = Path.read_bytes
        def page(database, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 6:
                target = Path(database).parent / 'fictional-source' / 'group-0000' / 'fictional-000000.png'
                original = target.stat()
                content = target.read_bytes()
                target.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
                os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
            return {"result": {"complete": True, "canceled": calls == 3},
                    "totals": {"pending": 64, "indexed": 64}, "pages": 1}
        def read(path):
            byte_check_tracing.append(tracemalloc.is_tracing())
            return real_read(path)
        with patch.object(soak, '_paged_pass', side_effect=page), \
                patch.object(soak, 'scan_sources', return_value={"sources": [{"health": "offline"}]}), \
                patch.object(soak, '_asset_count', side_effect=[64, 64, 65, 65, 65]), \
                patch.object(soak, '_missing_count', return_value=0), \
                patch.object(soak, '_asset_ids', side_effect=[set(range(64)), set(range(64)),
                                                           set(range(65)), set(range(65)), set(range(65))]), \
                patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(AssertionError, 'generated source bytes'):
                soak.run(64, 16)
        self.assertTrue(byte_check_tracing[0])  # Fault injection during the protocol.
        self.assertFalse(byte_check_tracing[-1])  # Actual source-byte verification after it.
        self.assertFalse(tracemalloc.is_tracing())

    def test_generated_run_retains_soak_assertions_and_private_data_stays_out(self):
        report = profile.run(64, 16)
        self.assertEqual(report["schema"], "defiantmaple.source-scan-profile.v1")
        for variant in ("baseline", "instrumented"):
            self.assertEqual(report[variant]["assets_after_recovery"], 65)
            for assertion in ("interruption_resumed", "offline_retained_assets", "source_files_unchanged"):
                self.assertTrue(report[variant][assertion])
            self.assertTrue(report[variant]["source_bytes_unchanged"])
            self.assertTrue(report[variant]["stable_identity_retained"])
            self.assertEqual(report[variant]['fixture']['recipe'], soak.FIXTURE_RECIPE)
            self.assertEqual(report[variant]["fixture"]["initial_bytes"], 8 * sum(map(len, soak._fictional_pngs())))
        self.assertEqual(set(report["phases"]), set(profile.PHASES))
        for name, phase in report["phases"].items():
            operations = phase["operations"]
            self.assertTrue(math.isclose(sum(item["exclusive_seconds"] for item in operations.values()),
                                         phase["elapsed_seconds"], rel_tol=1e-12, abs_tol=1e-12))
            self.assertTrue(all(0 <= item["exclusive_seconds"] <= item["inclusive_seconds"]
                                for item in operations.values()))
            self.assertEqual(operations["scan_pass"]["calls"], 1)
            self.assertEqual(operations["enumeration"]["calls"], int(name != "offline"))
            for operation in ("sqlite_connection_open", "sqlite_connection_close",
                              "sqlite_transaction_enter", "sqlite_transaction_exit"):
                self.assertEqual(operations[operation]["calls"],
                                 operations["catalog_connection_setup"]["calls"])
        indexing = report["phases"]["indexing"]
        self.assertEqual(indexing["operations"]["index_file"]["calls"], 64)
        self.assertEqual(indexing["operations"]["sha256_update"]["calls"], 64)
        self.assertEqual(indexing["counts"]["sha256_bytes"], 8 * sum(map(len, soak._fictional_pngs())))
        self.assertEqual(report["phases"]["observation"]["operations"]["index_file"]["calls"], 0)
        self.assertEqual(report["phases"]["stable_followup"]["operations"]["index_file"]["calls"], 1)
        with tempfile.TemporaryDirectory(prefix="fictional-profile-report-test-") as temporary:
            report_path = Path(temporary) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            errors = []
            _check_json(report_path, "benchmarks/fictional-profile-report.json", errors)
            self.assertEqual(errors, [])
        serialized = json.dumps(report)
        for identifying_value in ("fictional-source", "fictional-000", "SELECT ", "INSERT ",
                                  "root_path", "current_path", "source_id", "asset_id"):
            self.assertNotIn(identifying_value, serialized)

    def test_invalid_fixture_arguments_do_not_start_a_soak(self):
        with patch.object(soak, "run") as runner:
            for count, page_size in ((63, 16), (64, 0)):
                with self.assertRaises(ValueError):
                    profile.run(count, page_size)
            runner.assert_not_called()

    def test_cli_failure_emits_no_paths_sql_values_or_success_report(self):
        stdout, stderr = StringIO(), StringIO()
        with patch("sys.argv", ["source_scan_profile"]), \
                patch.object(profile, "run", side_effect=OSError("fictional sensitive SQL/path detail")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(profile.main(), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue()), {
            "schema": "defiantmaple.source-scan-profile.v1", "status": "failed", "error_type": "OSError",
        })
        self.assertNotIn("fictional sensitive", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
