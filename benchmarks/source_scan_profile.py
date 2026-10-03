"""Opt-in aggregate profiling of the unchanged fictional source-scan soak.

Instrumentation is process-local, single-threaded, and restored on every exit.
No arguments, source paths, SQL text/values, or exception messages are recorded.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from functools import wraps
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
import tracemalloc
from unittest.mock import patch

from PIL import __version__ as pillow_version

from benchmarks import source_scan_soak as soak
from defiantmaple import catalog, sources


OPERATIONS = (
    "scan_pass", "enumeration", "catalog_connection_setup",
    "catalog_connection_teardown", "sqlite_connection_open",
    "sqlite_statement_execute", "sqlite_result_fetch",
    "sqlite_transaction_enter", "sqlite_transaction_exit",
    "sqlite_connection_close", "index_file", "rename_hash_validation",
    "sha256_constructor", "sha256_update", "sha256_digest",
)
PAGED_PHASES = (
    "observation", "indexing", "cancellation", "fresh_resume",
    "stable_followup", "online_recovery",
)
PHASES = PAGED_PHASES + ("offline",)


@dataclass
class _Frame:
    started_ns: int
    children_ns: int = 0


def _empty_operations() -> dict:
    return {name: {"calls": 0, "failures": 0, "inclusive_ns": 0,
                   "exclusive_ns": 0} for name in OPERATIONS}


class _Cursor:
    """Delegate results unchanged; time consumption without retaining any row."""

    def __init__(self, cursor, profiler):
        self._cursor = cursor
        self._profiler = profiler

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def fetchone(self):
        with self._profiler.measure("sqlite_result_fetch"):
            return self._cursor.fetchone()

    def fetchall(self):
        with self._profiler.measure("sqlite_result_fetch"):
            return self._cursor.fetchall()

    def fetchmany(self, *args, **kwargs):
        with self._profiler.measure("sqlite_result_fetch"):
            return self._cursor.fetchmany(*args, **kwargs)

    def __iter__(self):
        return self

    def __next__(self):
        # End-of-iteration is normal consumption, not a failed SQLite call.
        with self._profiler.measure("sqlite_result_fetch", normal_stop=True):
            return next(self._cursor)


class _Digest:
    def __init__(self, digest, profiler):
        self._digest = digest
        self._profiler = profiler

    def __getattr__(self, name):
        return getattr(self._digest, name)

    def update(self, data):
        with self._profiler.measure("sha256_update"):
            result = self._digest.update(data)
        self._profiler.add_count("sha256_bytes", len(data))
        return result

    def digest(self):
        with self._profiler.measure("sha256_digest"):
            return self._digest.digest()

    def hexdigest(self):
        with self._profiler.measure("sha256_digest"):
            return self._digest.hexdigest()

    def copy(self):
        return _Digest(self._digest.copy(), self._profiler)


class ScanProfiler:
    """Aggregate nested spans only while a fixed, named scan phase is active."""

    _installed = False

    def __init__(self, clock=time.perf_counter_ns):
        self._clock = clock
        self._stack: list[_Frame] = []
        self._phase = None
        self._patches = None
        self._page_index = 0
        self.phases: dict[str, dict] = {}

    @contextmanager
    def measure(self, operation: str, *, normal_stop: bool = False):
        if operation not in OPERATIONS:
            raise ValueError("Unknown profiler operation")
        if self._phase is None:
            yield
            return
        frame = _Frame(self._clock())
        self._stack.append(frame)
        metric = self.phases[self._phase]["operations"][operation]
        metric["calls"] += 1
        try:
            yield
        except BaseException as exc:
            if not (normal_stop and isinstance(exc, StopIteration)):
                metric["failures"] += 1
            raise
        finally:
            duration = self._clock() - frame.started_ns
            self._stack.pop()
            metric["inclusive_ns"] += duration
            metric["exclusive_ns"] += duration - frame.children_ns
            if self._stack:
                self._stack[-1].children_ns += duration

    def add_count(self, name: str, amount: int = 1):
        if self._phase is not None:
            counts = self.phases[self._phase]["counts"]
            counts[name] = counts.get(name, 0) + amount

    @contextmanager
    def phase(self, name: str):
        if name not in PHASES:
            raise ValueError("Unknown profiler phase")
        if self._phase is not None or name in self.phases:
            raise RuntimeError("Profiler phases cannot overlap or repeat")
        self.phases[name] = {"operations": _empty_operations(), "counts": {}}
        self._phase = name
        try:
            with self.measure("scan_pass"):
                yield
        finally:
            self._phase = None

    def _wrap(self, operation, function):
        @wraps(function)
        def measured(*args, **kwargs):
            with self.measure(operation):
                return function(*args, **kwargs)
        return measured

    def _connection_context(self, original):
        @contextmanager
        def measured(*args, **kwargs):
            manager = original(*args, **kwargs)
            with self.measure("catalog_connection_setup"):
                connection = manager.__enter__()
            try:
                yield connection
            except BaseException:
                with self.measure("catalog_connection_teardown"):
                    suppressed = manager.__exit__(*sys.exc_info())
                if not suppressed:
                    raise
            else:
                with self.measure("catalog_connection_teardown"):
                    manager.__exit__(None, None, None)
        return measured

    def __enter__(self):
        if ScanProfiler._installed:
            raise RuntimeError("Only one single-threaded profiler may be installed")
        ScanProfiler._installed = True
        self._patches = ExitStack()
        original_connect = sqlite3.connect
        original_sha256 = catalog.hashlib.sha256
        original_page = soak._paged_pass
        original_scan = soak.scan_sources
        profiler = self

        class Connection(sqlite3.Connection):
            def execute(self, *args, **kwargs):
                with profiler.measure("sqlite_statement_execute"):
                    cursor = super().execute(*args, **kwargs)
                return _Cursor(cursor, profiler)

            def __enter__(self):
                with profiler.measure("sqlite_transaction_enter"):
                    return super().__enter__()

            def __exit__(self, exc_type, exc_value, traceback):
                # Connection.__exit__ commits/rolls back only if a transaction
                # exists. Count that condition; do not call every exit a commit.
                profiler.add_count("transaction_exits_with_transaction",
                                   int(self.in_transaction))
                profiler.add_count("exceptional_transaction_exits",
                                   int(exc_type is not None))
                with profiler.measure("sqlite_transaction_exit"):
                    return super().__exit__(exc_type, exc_value, traceback)

            def close(self):
                with profiler.measure("sqlite_connection_close"):
                    return super().close()

        def connect(*args, **kwargs):
            if profiler._phase is None:
                return original_connect(*args, **kwargs)
            # The production connect() supplies no custom factory. Preserve
            # all of its other arguments and SQLite's default settings.
            if "factory" in kwargs:
                raise ValueError("Profiler does not replace a custom SQLite factory")
            with profiler.measure("sqlite_connection_open"):
                return original_connect(*args, **kwargs, factory=Connection)

        def sha256(*args, **kwargs):
            if profiler._phase is None:
                return original_sha256(*args, **kwargs)
            with profiler.measure("sha256_constructor"):
                digest = original_sha256(*args, **kwargs)
            if args:
                profiler.add_count("sha256_bytes", len(args[0]))
            return _Digest(digest, profiler)

        def paged(*args, **kwargs):
            name = PAGED_PHASES[profiler._page_index]
            profiler._page_index += 1
            with profiler.phase(name):
                result = original_page(*args, **kwargs)
            # Retain counts, never the result's paths or source identifiers.
            profiler.phases[name]["pages"] = result["pages"]
            profiler.phases[name]["totals"] = dict(result["totals"])
            return result

        def scan(*args, **kwargs):
            if profiler._phase is not None:
                return original_scan(*args, **kwargs)
            with profiler.phase("offline"):
                return original_scan(*args, **kwargs)

        try:
            for module, attribute in ((catalog, "connect"), (sources, "connect"),
                                      (soak, "connect")):
                self._patches.enter_context(patch.object(
                    module, attribute, self._connection_context(getattr(module, attribute))))
            for attribute, operation in (("_iter_candidates", "enumeration"),
                                         ("index_file", "index_file"),
                                         ("_sha256_if_unchanged", "rename_hash_validation")):
                self._patches.enter_context(patch.object(
                    sources, attribute, self._wrap(operation, getattr(sources, attribute))))
            self._patches.enter_context(patch.object(sqlite3, "connect", connect))
            self._patches.enter_context(patch.object(catalog.hashlib, "sha256", sha256))
            self._patches.enter_context(patch.object(soak, "_paged_pass", paged))
            self._patches.enter_context(patch.object(soak, "scan_sources", scan))
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._patches is not None:
                self._patches.close()
        finally:
            self._patches = None
            ScanProfiler._installed = False

    def report(self) -> dict:
        if self._phase is not None:
            raise RuntimeError("Cannot report an active phase")
        result = {}
        for name, phase in self.phases.items():
            operations = {}
            for operation, metric in phase["operations"].items():
                operations[operation] = {
                    "calls": metric["calls"], "failures": metric["failures"],
                    "inclusive_ns": metric["inclusive_ns"], "exclusive_ns": metric["exclusive_ns"],
                    "inclusive_seconds": metric["inclusive_ns"] / 1e9,
                    "exclusive_seconds": metric["exclusive_ns"] / 1e9,
                }
            result[name] = {
                "elapsed_ns": phase["operations"]["scan_pass"]["inclusive_ns"],
                "elapsed_seconds": phase["operations"]["scan_pass"]["inclusive_ns"] / 1e9,
                "operations": operations, "counts": dict(phase["counts"]),
            }
            for key in ("pages", "totals"):
                if key in phase:
                    result[name][key] = phase[key]
        return result


def run_trial(count: int, page_size: int, variant: str, *,
              fixture_recipe: str = soak.FIXTURE_RECIPE) -> dict:
    if count < 64 or page_size < 1:
        raise ValueError("count must be at least 64 and page_size positive")
    if tracemalloc.is_tracing():
        raise RuntimeError("Run profiling without an existing tracemalloc session")
    if variant not in ("baseline", "instrumented"):
        raise ValueError("Unknown trial variant")
    # Keep the paired-v1 default call compatible; the series opts into a pinned
    # recipe. Soak authenticates that recipe before creating storage or tracing.
    fixture_options = {} if fixture_recipe == soak.FIXTURE_RECIPE else {"fixture_recipe": fixture_recipe}
    try:
        if variant == "baseline":
            return {"soak": soak.run(count, page_size, **fixture_options), "phases": {}}
        with ScanProfiler() as profiler:
            result = soak.run(count, page_size, **fixture_options)
        return {"soak": result, "phases": profiler.report()}
    finally:
        # The original soak stops tracing on success; also restore it on error.
        if tracemalloc.is_tracing():
            tracemalloc.stop()


def run(count: int = 2_048, page_size: int = 256) -> dict:
    baseline = run_trial(count, page_size, "baseline")["soak"]
    measured = run_trial(count, page_size, "instrumented")
    instrumented = measured["soak"]
    comparisons = {}
    for key in ("observation_seconds", "index_seconds", "fresh_resume_seconds"):
        comparisons[key] = {
            "baseline_seconds": baseline[key],
            "instrumented_seconds": instrumented[key],
            "instrumented_to_baseline_ratio": (
                instrumented[key] / baseline[key] if baseline[key] else None),
        }
    return {
        "schema": "defiantmaple.source-scan-profile.v1",
        "runtime": {"platform": platform.system(), "machine": platform.machine(),
                    "python_version": platform.python_version(),
                    "python_implementation": platform.python_implementation(),
                    "sqlite_version": sqlite3.sqlite_version,
                    "pillow_version": pillow_version},
        "baseline": baseline, "instrumented": instrumented,
        "phases": measured["phases"], "paired_elapsed_comparison": comparisons,
        "timing_note": "Inclusive spans overlap; exclusive spans partition each scan pass. "
                       "Unclassified scanner work remains in scan_pass exclusive time. "
                       "Both runs use tracemalloc. Paired ratios include wrapper overhead "
                       "and uncontrolled order/cache/filesystem variation.",
        "scope_note": "Generated tiny local PNGs, fresh catalogs, baseline first. "
                      "No SQL text/values, paths, or exception messages recorded. "
                      "No real mounted share or native watcher tested.",
    }


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=2_048)
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args()
    try:
        report = json.dumps(run(args.count, args.page_size), indent=2) + "\n"
        if args.metrics is not None:
            args.metrics.write_text(report, encoding="utf-8")
    except Exception as exc:
        # Error text and tracebacks can carry paths or SQL values. A failed
        # invocation emits only its status/type and never a success report.
        print(json.dumps({"schema": "defiantmaple.source-scan-profile.v1",
                          "status": "failed", "error_type": type(exc).__name__}),
              file=sys.stderr)
        return 1
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
