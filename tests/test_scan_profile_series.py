"""Fictional aggregate protocols; failures must never become benchmark evidence."""
from contextlib import contextmanager, redirect_stdout
import copy
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import source_scan_profile_series as series, source_scan_soak as soak
from scripts.check_public_artifacts import _check_json


@contextmanager
def local_environment():
    with patch.dict(os.environ):
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_ENVIRONMENT", "ImageOS", "ImageVersion"):
            os.environ.pop(key, None)
        yield


def fictional_trial(variant, count, page_size, identity, code, runtime, duration=10):
    sample = {"schema": series.TRIAL_SCHEMA, "status": "complete", "variant": variant,
              "identity": copy.deepcopy(identity), "code": copy.deepcopy(code), "runtime": dict(runtime),
              "configuration": {"count": count, "page_size": page_size}, "phases": {}}
    sample["soak"] = {"schema": "defiantmaple.source-scan-soak.v1", "platform": runtime["platform"],
        "python_version": runtime["python_version"], "fixture_kind": "generated-fictional-png",
        "file_count": count, "page_size": page_size, "observation_pages": (count + page_size - 1) // page_size,
        "index_pages": (count + page_size - 1) // page_size,
        "observation_seconds": round(duration / 1e9, 3), "index_seconds": round(duration / 1e9, 3),
        "fresh_resume_seconds": round(2 * duration / 1e9, 3),
        "timings_ns": {"observation": duration, "indexing": duration, "fresh_resume": 2 * duration},
        "catalog_schema_version": series.SCHEMA_VERSION, "fixture": soak.fixture_descriptor(count),
        "memory_scope": soak.MEMORY_SCOPE, "cache_scope": soak.CACHE_SCOPE, "python_peak_allocated_bytes": 100,
        "assets_after_recovery": count + 1, "interruption_resumed": True, "offline_retained_assets": True,
        "source_files_unchanged": True, "source_bytes_unchanged": True, "stable_identity_retained": True,
        "note": "Local generated fixture; no real network share or native watcher tested."}
    if variant == "instrumented":
        for phase in series.profile.PHASES:
            operations = {name: {"calls": 0, "failures": 0, "inclusive_ns": 0, "exclusive_ns": 0,
                                 "inclusive_seconds": 0.0, "exclusive_seconds": 0.0}
                          for name in series.profile.OPERATIONS}
            operations["scan_pass"].update(calls=1, inclusive_ns=duration, exclusive_ns=duration,
                                           inclusive_seconds=duration / 1e9, exclusive_seconds=duration / 1e9)
            operations["enumeration"]["calls"] = int(phase != "offline")
            operations["index_file"]["calls"] = count if phase == "indexing" else int(phase == "stable_followup")
            result = {"elapsed_ns": duration, "elapsed_seconds": duration / 1e9,
                      "operations": operations, "counts": {}}
            if phase == "indexing":
                result["counts"]["sha256_bytes"] = sample["soak"]["fixture"]["initial_bytes"]
            if phase != "offline":
                known = {"observation": {"pending": count}, "indexing": {"indexed": count},
                         "cancellation": {"unchanged": count // 3},
                         "fresh_resume": {"pending": 1, "unchanged": count},
                         "stable_followup": {"indexed": 1, "unchanged": count},
                         "online_recovery": {"unchanged": count + 1}}[phase]
                files = count if phase in ("observation", "indexing") else count + 1
                pages = (known["unchanged"] + page_size - 1) // page_size if phase == "cancellation" else (
                    files + page_size - 1) // page_size
                result.update(pages=pages,
                              totals={key: known.get(key, 0) for key in series.TOTALS})
            sample["phases"][phase] = result
    return sample


def fictional_pair(system, index, identity, code, runtime, *, count=64, page_size=16, pairs=4,
                   baseline=10, instrumented=20):
    runtime = dict(runtime, platform=system)
    order = list(series.ORDERS[index - 1])
    return {"schema": series.PAIR_SCHEMA, "status": "complete", "identity": copy.deepcopy(identity),
            "code": copy.deepcopy(code), "runtime": runtime,
            "configuration": {"count": count, "page_size": page_size, "pairs": pairs, "pair_index": index},
            "order": order, "samples": [{"position": position, "trial": fictional_trial(
                variant, count, page_size, identity, code, runtime,
                baseline if variant == "baseline" else instrumented)} for position, variant in enumerate(order, 1)],
            "wall_ns": 100, "cleanup": {"workers_reaped": True, "owned_storage_removed": True,
                                        "storage_retained": False}, "issues": []}


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.environment = local_environment()
        self.environment.__enter__()
        self.addCleanup(self.environment.__exit__, None, None, None)
        self.identity, self.code = series.actual_identity()
        self.runtime = series.runtime_metadata()

    def grid(self):
        return [fictional_pair(system, index, self.identity, self.code, self.runtime,
                               baseline=index * 10, instrumented=index * 20)
                for system in series.PLATFORMS for index in range(1, 5)]

    def aggregate(self, reports, **kwargs):
        return series.aggregate(reports, count=64, page_size=16, **kwargs)

    def test_full_grid_preserves_raw_samples_balances_order_and_exact_math(self):
        grid = list(reversed(self.grid()))
        result = self.aggregate(grid)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["pairs"]), 12)
        for system in series.PLATFORMS:
            summary = result["summaries"][system]["intervals"]["observation"]
            self.assertEqual(summary["variant_ns"]["baseline"], {"n": 4, "median": 25.0, "min": 10, "max": 40})
            self.assertEqual([item["ratio"] for item in summary["paired_ratios"]], [2.0] * 4)
            self.assertEqual(summary["order_groups"]["baseline-first"]["pairs"], 2)
            self.assertEqual(summary["order_groups"]["instrumented-first"]["pairs"], 2)
        self.assertEqual(result["pairs"][0], grid[-1])
        series.validate_public_report(result)

    def test_zero_duration_has_null_ratio_without_dropping_raw_trial(self):
        pair = fictional_pair("Linux", 1, self.identity, self.code, self.runtime, baseline=0)
        other = fictional_pair("Linux", 2, self.identity, self.code, self.runtime)
        for item in (pair, other):
            item["configuration"]["pairs"] = 2
        result = self.aggregate([pair, other], pairs=2, platforms=["Linux"])
        self.assertEqual(result["status"], "complete")
        summary = result["summaries"]["Linux"]["intervals"]["observation"]
        self.assertIsNone(summary["paired_ratios"][0]["ratio"])
        self.assertEqual(summary["variant_ns"]["baseline"]["n"], 2)
        self.assertEqual(summary["order_groups"]["baseline-first"]["ratios"]["n"], 0)

    def test_missing_duplicate_wrong_order_stale_identity_and_false_integrity_refuse(self):
        mutations = {
            "missing": lambda grid: grid.pop(),
            "duplicate": lambda grid: grid.append(copy.deepcopy(grid[0])),
            "order": lambda grid: grid[1].update(order=list(series.ORDERS[0])),
            "revision": lambda grid: grid[0]["code"].update(revision="f" * 40),
            "run": lambda grid: grid[0]["identity"].update(run_id="999"),
            "attempt": lambda grid: grid[0]["identity"].update(run_attempt=2),
            "digest": lambda grid: grid[0]["code"]["digests"].update({series.CODE_FILES[0]: "f" * 64}),
            "source-integrity": lambda grid: grid[0]["samples"][0]["trial"]["soak"].update(source_bytes_unchanged=False),
            "runtime": lambda grid: grid[1]["runtime"].update(cpu_logical_count=999),
            "malformed": lambda grid: grid[0].update(private_path="/fictional/private.png"),
            "negative-span": lambda grid: grid[0]["samples"][1]["trial"]["phases"]["indexing"]["operations"]["scan_pass"].update(exclusive_ns=-1),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                grid = self.grid()
                mutation(grid)
                result = self.aggregate(grid)
                self.assertEqual(result["status"], "incomplete")
                self.assertNotIn("summaries", result)
                series.validate_public_report(result)
                self.assertNotIn("private_path", json.dumps(result))

    def test_closed_reports_reject_private_free_text_nonfinite_and_ambiguous_json(self):
        pair = self.grid()[0]
        for change in (lambda value: value.update(status="private-host-name"),
                       lambda value: value["issues"].append({"code": "private SQL", "error_type": None}),
                       lambda value: value["runtime"].update(cpu_model="private workstation"),
                       lambda value: value["samples"][0]["trial"]["soak"].update(observation_seconds=float('nan'))):
            value = copy.deepcopy(pair)
            change(value)
            with self.assertRaises((ValueError, TypeError)):
                series.validate_public_report(value)
        for text in ('{"status":"incomplete","status":"complete"}', '{"value":NaN}', '{"value":Infinity}'):
            with self.assertRaises(ValueError):
                series.parse_report(text)

    def test_summary_tampering_is_rejected(self):
        result = self.aggregate(self.grid())
        result["summaries"]["Linux"]["intervals"]["observation"]["variant_ns"]["baseline"]["median"] = 1
        with self.assertRaises(ValueError):
            series.validate_public_report(result)

    def test_inconsistent_protocol_totals_and_pages_never_form_complete_summary(self):
        for phase, key in (("observation", "pending"), ("indexing", "indexed"),
                           ("fresh_resume", "unchanged"), ("stable_followup", "indexed"),
                           ("online_recovery", "unchanged")):
            for field in ("totals", "pages"):
                with self.subTest(phase=phase, field=field):
                    grid = self.grid()
                    measured = grid[0]["samples"][1]["trial"]["phases"][phase]
                    if field == "totals":
                        measured[field][key] = 0
                    else:
                        measured[field] += 1
                    result = self.aggregate(grid)
                    self.assertEqual(result["status"], "incomplete")
                    self.assertNotIn("summaries", result)

    def test_wrong_child_configuration_preserves_prior_sample_and_sanitized_partial(self):
        for count, page_size in ((128, 16), (64, 8)):
            with self.subTest(count=count, page_size=page_size):
                children = [(fictional_trial('baseline', 64, 16, self.identity, self.code, self.runtime), None, True),
                            (fictional_trial('instrumented', count, page_size, self.identity, self.code, self.runtime), None, True)]
                stdout = StringIO()
                with patch.object(series, '_run_child', side_effect=children), redirect_stdout(stdout):
                    status = series.main(['pair', '--count', '64', '--page-size', '16', '--pairs', '2', '--pair-index', '1'])
                self.assertEqual(status, 1)
                report = series.parse_report(stdout.getvalue())
                self.assertEqual(len(report['samples']), 1)
                self.assertEqual(report['samples'][0]['trial']['variant'], 'baseline')
                self.assertTrue(report['cleanup']['owned_storage_removed'])
                self.assertIn('identity_mismatch', [item['code'] for item in report['issues']])
                series.validate_public_report(report)

    def test_real_seed_cancellation_counts_must_fit_reported_page_prefix(self):
        # The first actual generated 2048/256 trial canceled after 703 unchanged
        # files in three pages. Preserve that aggregate without retaining media.
        pair = fictional_pair('Linux', 1, self.identity, self.code, self.runtime, count=2048, page_size=256)
        cancellation = pair['samples'][1]['trial']['phases']['cancellation']
        cancellation['totals']['unchanged'] = 703
        cancellation['pages'] = 3
        series.validate_public_report(pair)
        for pages in (1, 2, 4):
            with self.subTest(pages=pages):
                bad = copy.deepcopy(pair)
                bad['samples'][1]['trial']['phases']['cancellation']['pages'] = pages
                with self.assertRaises(ValueError):
                    series.validate_public_report(bad)
                other = fictional_pair('Linux', 2, self.identity, self.code, self.runtime, count=2048, page_size=256)
                for item in (bad, other):
                    item['configuration']['pairs'] = 2
                result = series.aggregate([bad, other], count=2048, page_size=256, pairs=2, platforms=['Linux'])
                self.assertEqual(result['status'], 'incomplete')
                self.assertNotIn('summaries', result)

    def test_hosted_identity_requires_full_experiment_even_for_declared_subset(self):
        with patch.dict(os.environ, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1'):
            for count, page_size, pairs, platforms in ((64, 16, 4, series.PLATFORMS),
                    (2048, 256, 2, series.PLATFORMS), (2048, 256, 4, ['Linux'])):
                with self.subTest(count=count, pairs=pairs, platforms=platforms), self.assertRaises(ValueError):
                    series.aggregate([], count=count, page_size=page_size, pairs=pairs,
                                     platforms=platforms, run_id='123')
        value = self.aggregate(self.grid())
        value['identity']['run_id'] = '123'
        with self.assertRaises(ValueError):
            series.validate_public_report(value)

    def test_actual_checkout_and_environment_refuse_forged_provenance(self):
        with self.assertRaises(ValueError):
            series.actual_identity("f" * 40)
        with self.assertRaises(ValueError):
            series.actual_identity(run_id="123")
        with patch.dict(os.environ, GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="2"):
            with self.assertRaises(ValueError):
                series.actual_identity(run_id="123", run_attempt=1)
            identity, code = series.actual_identity(run_id="123", run_attempt=2)
            self.assertEqual(identity, {"run_id": "123", "run_attempt": 2})
            self.assertEqual(set(code["digests"]), set(series.CODE_FILES))

    def test_pair_subprocess_isolation_order_cleanup_and_partial_failure(self):
        calls = []
        def child(command, environment, timeout):
            variant = command[command.index("--variant") + 1]
            calls.append((command, environment, timeout))
            return fictional_trial(variant, 64, 16, self.identity, self.code, self.runtime), None, True
        with patch.object(series, "_run_child", side_effect=child):
            pair = series.run_pair(64, 16, pairs=4, pair_index=2)
        self.assertEqual(pair["status"], "complete")
        self.assertEqual([item["trial"]["variant"] for item in pair["samples"]], ["instrumented", "baseline"])
        roots = [Path(item[1]["DEFIANTMAPLE_SCAN_TRIAL_ROOT"]) for item in calls]
        self.assertNotEqual(roots[0], roots[1])
        self.assertFalse(any(root.exists() for root in roots))
        for command, environment, timeout in calls:
            self.assertIn("error::ResourceWarning", command)
            self.assertEqual(environment["TMPDIR"], environment["TEMP"])
            self.assertLessEqual(timeout, 720)
        with patch.object(series, "_run_child", side_effect=[child(calls[0][0], calls[0][1], 1),
                       (None, series._issue("child_timeout", subprocess.TimeoutExpired("private", 1)), True)]):
            partial = series.run_pair(64, 16, pairs=2, pair_index=2)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(len(partial["samples"]), 1)
        self.assertTrue(partial["cleanup"]["owned_storage_removed"])
        self.assertNotIn("private", json.dumps(partial))

    def test_unreaped_worker_retains_owned_storage_and_stops_next_trial(self):
        roots = []
        def child(command, environment, timeout):
            roots.append(Path(environment["DEFIANTMAPLE_SCAN_TRIAL_ROOT"]).parent)
            return None, series._issue("child_timeout"), False
        with patch.object(series, "_run_child", side_effect=child) as runner:
            partial = series.run_pair(64, 16, pairs=2, pair_index=1)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["cleanup"], {"workers_reaped": False, "owned_storage_removed": False, "storage_retained": True})
        self.assertTrue(roots[0].is_dir())
        # The test used no actual process; explicitly remove its fictional storage.
        series.shutil.rmtree(roots[0])

    def test_reap_kills_only_after_terminate_timeout_and_requires_exit(self):
        class Worker:
            def __init__(self):
                self.actions = []
                self.dead = False
            def terminate(self):
                self.actions.append("terminate")
            def kill(self):
                self.actions.append("kill")
                self.dead = True
            def communicate(self, timeout):
                if not self.dead:
                    raise subprocess.TimeoutExpired("private path", timeout)
                return '', ''
            def poll(self):
                return 1 if self.dead else None
        worker = Worker()
        self.assertTrue(series._reap(worker))
        self.assertEqual(worker.actions, ["terminate", "kill"])
        worker = Worker()
        worker.kill = lambda: None
        self.assertFalse(series._reap(worker))

    def test_child_timeout_and_untrusted_output_are_sanitized_and_proven_reaped(self):
        class Worker:
            def __init__(self, timeout=False, output='', exit_code=0):
                self.timeout = timeout
                self.output = output
                self.returncode = exit_code
                self.dead = False
            def communicate(self, timeout):
                if self.timeout and not self.dead:
                    raise subprocess.TimeoutExpired('/fictional/private-worker', timeout)
                self.dead = True
                return self.output, 'SELECT private source value'
            def terminate(self):
                self.dead = True
            def kill(self):
                self.dead = True
            def poll(self):
                return self.returncode if self.dead else None
        for worker, expected in ((Worker(timeout=True), 'child_timeout'),
                                 (Worker(output='{"private_path":"/fictional/private.png"}'), 'invalid_report'),
                                 (Worker(output='private stdout', exit_code=1), 'child_failed')):
            with self.subTest(expected=expected), patch.object(series.subprocess, 'Popen', return_value=worker):
                value, issue, reaped = series._run_child(['fictional'], {}, 1)
            self.assertIsNone(value)
            self.assertTrue(reaped)
            self.assertEqual(issue['code'], expected)
            self.assertNotIn('private', json.dumps(issue))

    def test_live_worker_and_changed_owner_marker_prevent_cleanup_and_next_trial(self):
        roots = []
        def child(command, environment, timeout):
            roots.append(Path(environment['DEFIANTMAPLE_SCAN_TRIAL_ROOT']).parent)
            return fictional_trial('baseline', 64, 16, self.identity, self.code, self.runtime), None, False
        with patch.object(series, '_run_child', side_effect=child) as runner:
            report = series.run_pair(64, 16, pairs=2, pair_index=1)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(report['samples'], [])
        self.assertTrue(report['cleanup']['storage_retained'])
        series.shutil.rmtree(roots.pop())  # No actual worker was spawned.
        def changed_owner(command, environment, timeout):
            root = Path(environment['DEFIANTMAPLE_SCAN_TRIAL_ROOT']).parent
            roots.append(root)
            (root / '.owned-scan-pair').write_text('fictional changed owner')
            return None, series._issue('child_failed'), True
        with patch.object(series, '_run_child', side_effect=changed_owner):
            report = series.run_pair(64, 16, pairs=2, pair_index=1)
        self.assertTrue(report['cleanup']['workers_reaped'])
        self.assertTrue(report['cleanup']['storage_retained'])
        self.assertTrue(roots[0].exists())
        series.shutil.rmtree(roots[0])

    def test_changed_measured_code_and_incomparable_cohort_refuse_without_summary(self):
        changed = copy.deepcopy(self.code)
        changed['digests'][series.CODE_FILES[0]] = 'f' * 64
        with patch.object(series, 'actual_identity', side_effect=[(self.identity, self.code), (self.identity, changed)]), \
                patch.object(series.profile, 'run_trial', return_value={}):
            with self.assertRaisesRegex(ValueError, 'code_changed'):
                series.run_trial(64, 16, 'baseline')
        grid = self.grid()
        grid[1]['runtime']['cpu_logical_count'] = 999
        for sample in grid[1]['samples']:
            sample['trial']['runtime']['cpu_logical_count'] = 999
        result = self.aggregate(grid)
        self.assertEqual(result['status'], 'incomplete')
        self.assertNotIn('summaries', result)
        self.assertIn('incomparable', [item['code'] for item in result['issues']])

    def test_cli_write_failure_preserves_validated_samples_and_partial_privacy(self):
        pair = self.grid()[0]
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(stdout), \
                patch.object(series, 'run_pair', return_value=pair), \
                patch.object(series, 'write_report', side_effect=PermissionError('private output path')):
            self.assertEqual(series.main(['pair', '--count', '64', '--page-size', '16', '--pair-index', '1',
                                        '--metrics', str(Path(temporary) / 'metrics.json')]), 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(len(report['samples']), 2)
        self.assertNotIn('private output path', stdout.getvalue())
        series.validate_public_report(report)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'partial.json'
            path.write_text(json.dumps(report))
            errors = []
            _check_json(path, 'benchmarks/fictional-partial-report.json', errors)
            self.assertEqual(errors, [])

    def test_invalid_arguments_never_start_workers_and_cli_diagnostics_are_closed(self):
        with patch.object(series, "_run_child") as runner:
            for args in ((63, 16, 4, 1), (64, 0, 4, 1), (64, 16, 3, 1), (64, 16, 4, 5)):
                with self.assertRaises(ValueError):
                    series.run_pair(*args)
            runner.assert_not_called()
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(series.main(["pair", "--count", "/private/source", "--pair-index", "1"]), 1)
        value = json.loads(stdout.getvalue())
        series.validate_public_report(value)
        self.assertNotIn("/private/source", stdout.getvalue())

    def test_atomic_output_keeps_previous_report_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "metrics.json"
            target.write_text("previous fictional output")
            with patch.object(series.os, "replace", side_effect=PermissionError("private output")):
                with self.assertRaises(OSError):
                    series.write_report(target, self.grid()[0])
            self.assertEqual(target.read_text(), "previous fictional output")
            self.assertEqual(list(Path(temporary).iterdir()), [target])

    def test_tiny_real_balanced_series_integrity_private_checker_and_dirty_digests(self):
        # The single real series: four isolated 64-file children, two balanced pairs.
        system = self.runtime["platform"]
        pairs = [series.run_pair(64, 16, pairs=2, pair_index=index, trial_timeout=60, pair_timeout=120)
                 for index in (1, 2)]
        result = self.aggregate(pairs, pairs=2, platforms=[system])
        self.assertEqual(result["status"], "complete", result["issues"])
        for pair in pairs:
            self.assertEqual(pair["code"]["digests"], self.code["digests"])
            for sample in pair["samples"]:
                measured = sample["trial"]["soak"]
                self.assertEqual(measured["assets_after_recovery"], 65)
                self.assertTrue(measured["source_bytes_unchanged"])
                self.assertTrue(measured["stable_identity_retained"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metrics.json"
            series.write_report(path, result)
            errors = []
            _check_json(path, "benchmarks/fictional-series-report.json", errors)
            self.assertEqual(errors, [])
            tampered = copy.deepcopy(result)
            tampered["private_notes"] = "/fictional/private.png"
            path.write_text(json.dumps(tampered))
            _check_json(path, "benchmarks/fictional-series-report.json", errors)
            self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
