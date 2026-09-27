"""Reproducible, fictional source-scan soak for the three desktop CI platforms.

All media, catalog, and measurements are created outside the repository. The
report contains aggregate counts and timing only, never fixture paths.
"""
from __future__ import annotations

from argparse import ArgumentParser
from io import BytesIO
import json
from pathlib import Path
import platform
import tempfile
import threading
import time
import tracemalloc

from PIL import Image

from defiantmaple.catalog import connect, initialize
from defiantmaple.sources import add_source, scan_sources


def _fictional_pngs() -> tuple[bytes, ...]:
    result = []
    for index in range(8):
        image = Image.new("RGBA", (32, 32),
                          ((index * 37) % 256, (index * 61) % 256, 160, 255))
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            result.append(stream.getvalue())
    return tuple(result)


def _asset_count(database: Path) -> int:
    with connect(database) as db:
        return db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]


def _missing_count(database: Path) -> int:
    with connect(database) as db:
        return db.execute(
            "SELECT COUNT(*) FROM source_entries WHERE disposition='missing'"
        ).fetchone()[0]


def _paged_pass(database: Path, source_id: str, now_ns: int, page_size: int,
                *, cancel_event=None, progress=None) -> dict:
    inventory = {}
    cursor = None
    pages = 0
    totals = None
    while True:
        result = scan_sources(
            database, source_id=source_id, quiet_seconds=2.0, now_ns=now_ns,
            max_candidates=page_size, resume_after=cursor,
            inventory_cache=inventory, cancel_event=cancel_event, progress=progress,
        )
        pages += 1
        if totals is None:
            totals = dict(result["totals"])
        else:
            for key in totals:
                totals[key] += result["totals"][key]
        if result["complete"] or result["canceled"]:
            return {"result": result, "totals": totals, "pages": pages}
        if not result["sources"] or result["sources"][0]["health"] != "paused":
            return {"result": result, "totals": totals, "pages": pages}
        next_cursor = result["resume_after"]
        if next_cursor is None or next_cursor == cursor:
            raise RuntimeError("Paged scan made no progress")
        cursor = next_cursor


def run(count: int = 2_048, page_size: int = 256) -> dict:
    if count < 64 or page_size < 1:
        raise ValueError("count must be at least 64 and page_size positive")
    with tempfile.TemporaryDirectory(prefix="defiantmaple-fictional-soak-") as temporary:
        base = Path(temporary).resolve()
        root = base / "fictional-source"
        root.mkdir()
        database = base / "catalog.sqlite3"
        initialize(database)
        source_id = add_source(database, root)["source_id"]
        pngs = _fictional_pngs()
        source_files = []
        for index in range(count):
            directory = root / f"group-{index // 256:04}"
            directory.mkdir(exist_ok=True)
            path = directory / f"fictional-{index:06}.png"
            path.write_bytes(pngs[index % len(pngs)])
            source_files.append(path)
        original_stats = [(path.stat().st_size, path.stat().st_mtime_ns)
                          for path in source_files]

        tracemalloc.start()
        started = time.perf_counter()
        observed = _paged_pass(database, source_id, 1_000_000_000, page_size)
        observe_seconds = time.perf_counter() - started
        if not observed["result"]["complete"] or observed["totals"]["pending"] != count:
            raise AssertionError("First observation was incomplete")

        started = time.perf_counter()
        indexed = _paged_pass(database, source_id, 4_000_000_000, page_size)
        index_seconds = time.perf_counter() - started
        if (not indexed["result"]["complete"] or indexed["totals"]["indexed"] != count
                or _asset_count(database) != count):
            raise AssertionError("Stable files were not all indexed")

        canceled = threading.Event()

        def cancel_after_progress(state):
            if (state["phase"] == "processing"
                    and state["processed"] >= count // 3):
                canceled.set()

        interrupted = _paged_pass(database, source_id, 5_000_000_000, page_size,
                                  cancel_event=canceled, progress=cancel_after_progress)
        if not interrupted["result"]["canceled"] or _asset_count(database) != count:
            raise AssertionError("Cancellation did not preserve indexed assets")

        # This new file sorts before the canceled cursor. A fresh enumeration
        # must see it; carrying the old cursor into a new inventory would skip it.
        early = root / "group-0000" / "fictional-000000-before.png"
        early.write_bytes(pngs[0])
        started = time.perf_counter()
        resumed = _paged_pass(database, source_id, 6_000_000_000, page_size)
        stable = _paged_pass(database, source_id, 9_000_000_000, page_size)
        recovery_seconds = time.perf_counter() - started
        if (not resumed["result"]["complete"] or not stable["result"]["complete"]
                or _asset_count(database) != count + 1):
            raise AssertionError("Fresh resume skipped an earlier new file")

        disconnected = base / "source-temporarily-unavailable"
        root.rename(disconnected)
        offline = scan_sources(database, source_id=source_id, now_ns=10_000_000_000)
        if (offline["sources"][0]["health"] != "offline"
                or _asset_count(database) != count + 1 or _missing_count(database)):
            raise AssertionError("Offline source changed catalog assets")
        disconnected.rename(root)
        online = _paged_pass(database, source_id, 11_000_000_000, page_size)
        if not online["result"]["complete"] or _asset_count(database) != count + 1:
            raise AssertionError("Source did not recover after reconnection")
        if any((path.stat().st_size, path.stat().st_mtime_ns) != original
               for path, original in zip(source_files, original_stats)):
            raise AssertionError("Scanner changed a fictional source file")
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    return {
        "schema": "defiantmaple.source-scan-soak.v1",
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "fixture_kind": "generated-fictional-png",
        "file_count": count,
        "page_size": page_size,
        "observation_pages": observed["pages"],
        "index_pages": indexed["pages"],
        "observation_seconds": round(observe_seconds, 3),
        "index_seconds": round(index_seconds, 3),
        "fresh_resume_seconds": round(recovery_seconds, 3),
        "python_peak_allocated_bytes": peak_bytes,
        "assets_after_recovery": count + 1,
        "interruption_resumed": True,
        "offline_retained_assets": True,
        "source_files_unchanged": True,
        "note": "Local generated fixture; no real network share or native watcher tested.",
    }


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=2_048)
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args()
    result = run(args.count, args.page_size)
    report = json.dumps(result, indent=2) + "\n"
    if args.metrics is not None:
        args.metrics.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
