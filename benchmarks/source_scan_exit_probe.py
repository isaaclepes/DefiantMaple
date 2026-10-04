"""Exit-only, process-local attribution for the unchanged fictional scan soak.

The four fixed strata use SQLite's read-only state immediately before the
original context exit. No connection, statement, row or path enters a metric.
"""
from __future__ import annotations

from contextlib import ExitStack
import sqlite3
import sys
import time
import tracemalloc
from unittest.mock import patch

from benchmarks import source_scan_soak as soak

PHASES = ("observation", "indexing", "cancellation", "fresh_resume",
          "stable_followup", "offline", "online_recovery")
PAGED_PHASES = tuple(name for name in PHASES if name != "offline")
STRATA = ("transaction_normal", "transaction_exception",
          "no_transaction_normal", "no_transaction_exception")
# Half-open bins; the last one includes every larger duration. Fixed size.
BUCKET_UPPER_NS = (1_000, 10_000, 100_000, 1_000_000, 10_000_000,
                   100_000_000, 1_000_000_000)


def empty_metric():
    return {"count": 0, "total_ns": 0, "min_ns": None, "max_ns": None,
            "buckets": [0] * (len(BUCKET_UPPER_NS) + 1)}


class ExitProbe:
    _installed = False

    def __init__(self, clock=time.perf_counter_ns, *, instrumented=True):
        self.clock = clock
        self.instrumented = instrumented
        self.phase = None
        self.phases = {}
        self._page = 0
        self._patches = None

    def _record(self, transaction, exceptional, elapsed):
        if self.phase is None:
            return
        name = ("transaction" if transaction else "no_transaction") + (
            "_exception" if exceptional else "_normal")
        metric = self.phases[self.phase]["strata"][name]
        metric["count"] += 1
        metric["total_ns"] += elapsed
        metric["min_ns"] = elapsed if metric["min_ns"] is None else min(metric["min_ns"], elapsed)
        metric["max_ns"] = elapsed if metric["max_ns"] is None else max(metric["max_ns"], elapsed)
        for index, upper in enumerate(BUCKET_UPPER_NS):
            if elapsed < upper:
                metric["buckets"][index] += 1
                break
        else:
            metric["buckets"][-1] += 1

    def _phase_call(self, name, function, *args, **kwargs):
        if self.phase is not None or name in self.phases:
            raise RuntimeError("Exit probe phases cannot overlap or repeat")
        entry = {"elapsed_ns": 0, "strata": {key: empty_metric() for key in STRATA}}
        self.phases[name] = entry
        self.phase = name
        started = self.clock()
        try:
            return function(*args, **kwargs)
        finally:
            entry["elapsed_ns"] = self.clock() - started
            self.phase = None

    def __enter__(self):
        if ExitProbe._installed:
            raise RuntimeError("Only one exit probe may be installed")
        ExitProbe._installed = True
        patches = self._patches = ExitStack()
        original_connect = sqlite3.connect
        original_paged = soak._paged_pass
        original_scan = soak.scan_sources
        probe = self

        class Connection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                # State inspection and the timer bracket are the only changes
                # to the original context-exit behavior. Record even on raise.
                transaction = self.in_transaction
                started = probe.clock()
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    probe._record(transaction, exc_type is not None,
                                  probe.clock() - started)

        def connect(*args, **kwargs):
            if probe.phase is None:
                return original_connect(*args, **kwargs)
            # Preserve explicit custom-factory behavior exactly. The canonical
            # catalog uses the default factory; arbitrary factories cannot be
            # assumed to subclass sqlite3.Connection.
            if "factory" in kwargs or len(args) >= 6:
                return original_connect(*args, **kwargs)
            return original_connect(*args, **kwargs, factory=Connection)

        def paged(*args, **kwargs):
            name = PAGED_PHASES[probe._page]
            probe._page += 1
            return probe._phase_call(name, original_paged, *args, **kwargs)

        def scan(*args, **kwargs):
            if probe.phase is not None:
                return original_scan(*args, **kwargs)
            return probe._phase_call("offline", original_scan, *args, **kwargs)

        try:
            if self.instrumented:
                patches.enter_context(patch.object(sqlite3, "connect", connect))
            patches.enter_context(patch.object(soak, "_paged_pass", paged))
            patches.enter_context(patch.object(soak, "scan_sources", scan))
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
            ExitProbe._installed = False


def run_trial(count, page_size, variant):
    if variant not in ("baseline", "instrumented"):
        raise ValueError("Unknown exit-probe variant")
    if tracemalloc.is_tracing():
        raise RuntimeError("Run probe without an existing tracemalloc session")
    try:
        with ExitProbe(instrumented=variant == "instrumented") as probe:
            result = soak.run(count, page_size,
                              fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
        if set(probe.phases) != set(PHASES):
            raise AssertionError("Incomplete phase capture")
        return {"soak": result, "phases": probe.phases if variant == "instrumented" else {}}
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
