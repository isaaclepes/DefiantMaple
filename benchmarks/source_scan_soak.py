"""Reproducible, fictional source-scan soak for the three desktop CI platforms.

All media, catalog, and measurements are created outside the repository. The
report contains aggregate counts and timing only, never fixture paths.
"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
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

FIXTURE_RECIPE = "tiny-rgba-png-eight-content.v1"
CANONICAL_FIXTURE_RECIPE = "tiny-rgba-png-eight-content-canonical.v1"
MEMORY_SCOPE = "python-tracemalloc-scan-protocol-after-fixture-setup"
CACHE_SCOPE = "fixture-created-and-stat-checked-os-cache-uncontrolled"

# Own generated 32x32 RGBA solid-color PNGs in the legacy recipe's order.
# Pin the encoded corpus instead of using a platform-dependent runtime encoder.
# Keep these bytes and this recipe immutable; a changed corpus needs a new recipe.
_CANONICAL_PNG_HEX = (
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003049444154789cedce310100200cc0b0827f11730a32f6a4069a53f35aec6ece010000000000000000000000000000aa3e33c801df20b638840000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce4101003008c4b0635e26635e713a64f0490d34755fff2c7636e700000000000000000000000000000049325fc30241037ddc090000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce4101003008c4b063f226696a703a64f0490d34755fff2c7636e700000000000000000000000000000049328bbe02a3680abfd80000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce4101003008c4b0638667692e903764f0490d3475fbfd2c7636e70000000000000000000000000000004932b7b90305c134503b0000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003449444154789cedce3101003008c4c0a7fec70aa848f62283e5622057b7dfcf6267730e0000000000000000000000000000902403e3b40367c67548670000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce4101003008c4b0638ee67836503764f0490d34d5f7fd2c7636e70000000000000000000000000000004932f0bf02c9bb56e6d80000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce4101003008c4b06382a769cab03264f0490d34d5f7fd2c7636e700000000000000000000000000000049321cc9032b37c2d5720000000049454e44ae426082",
    "89504e470d0a1a0a0000000d4948445200000020000000200806000000737a7af40000003349444154789cedce3101003008c4c0a7f5efa13b228b0c968b815cdd7e3f8b9dcd39000000000000000000000000000040920c28d4028db55e6a2d0000000049454e44ae426082",
)
CANONICAL_PNG_SIZES = (105, 108, 108, 108, 109, 108, 108, 108)
CANONICAL_PNG_SHA256 = (
    "6142a7cf653a09ca214fafa7a633425bb8b228efd4b3e1cce5f4dcd879ba23de",
    "2f286e0e3ab33afa708740b7404fac5b309948b87ba0b97cfcbd97bc6189a1fb",
    "a679206f56eb93e1eb09c345cdddbe21fafbe147268f2d311be0398afc691373",
    "7bded924b30468b04b1be84a9f774c1b68872bfba5c6b50fd593854c24690e40",
    "05d954f85a0f6aeb65b5dc3ea3229cfe82a67359d49c4f53046ff613633aa23e",
    "ed765fded8c41b52b9a962fa5204ab0ba6685857bd009d6439a64a0d3fb91dc7",
    "5570afba56dc5f24fd8253d704f9c6f1e3d9a980329a53cfb59a092bcb1b0b66",
    "1e808b806c1514287c1f1153bfce519415bacf4bc359e332810b2973c6f954d1",
)
CANONICAL_CORPUS_SHA256 = "5b4ef21dad6cd972d9e3a128eb4075bb736bb0784627be7f336ae2f3ed0bffcb"


def _fictional_pngs() -> tuple[bytes, ...]:
    result = []
    for index in range(8):
        image = Image.new("RGBA", (32, 32),
                          ((index * 37) % 256, (index * 61) % 256, 160, 255))
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            result.append(stream.getvalue())
    return tuple(result)


def _fixture_pngs(fixture_recipe: str) -> tuple[bytes, ...]:
    if fixture_recipe == FIXTURE_RECIPE:
        return _fictional_pngs()
    if fixture_recipe != CANONICAL_FIXTURE_RECIPE:
        raise ValueError("Unknown fictional fixture recipe")
    payloads = tuple(bytes.fromhex(value) for value in _CANONICAL_PNG_HEX)
    if (tuple(map(len, payloads)) != CANONICAL_PNG_SIZES or
            tuple(hashlib.sha256(value).hexdigest() for value in payloads) != CANONICAL_PNG_SHA256 or
            hashlib.sha256(b"".join(len(value).to_bytes(4, "big") + value
                                    for value in payloads)).hexdigest() != CANONICAL_CORPUS_SHA256):
        raise ValueError("Canonical fictional fixture corpus changed")
    return payloads


def _asset_count(database: Path) -> int:
    with connect(database) as db:
        return db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]


def _missing_count(database: Path) -> int:
    with connect(database) as db:
        return db.execute(
            "SELECT COUNT(*) FROM source_entries WHERE disposition='missing'"
        ).fetchone()[0]


def _asset_ids(database: Path) -> set:
    # Private verification state only; never include identifiers in a report.
    with connect(database) as db:
        return {row[0] for row in db.execute("SELECT asset_id FROM assets")}


def fixture_descriptor(count: int, *, fixture_recipe: str = FIXTURE_RECIPE) -> dict:
    payloads = _fixture_pngs(fixture_recipe)
    return {"recipe": fixture_recipe, "width": 32, "height": 32, "mode": "RGBA",
            "encoded_contents": len(set(payloads)), "directory_group_size": 256,
            "initial_files": count, "initial_bytes": sum(len(payloads[i % 8]) for i in range(count)),
            "resume_added_files": 1, "resume_added_bytes": len(payloads[0])}


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


def run(count: int = 2_048, page_size: int = 256, *, fixture_recipe: str = FIXTURE_RECIPE) -> dict:
    if count < 64 or page_size < 1:
        raise ValueError("count must be at least 64 and page_size positive")
    if tracemalloc.is_tracing():
        raise RuntimeError("Run soak without an existing tracemalloc session")
    # Authenticate canonical bytes or reject unknown recipes before owned storage.
    pngs = _fixture_pngs(fixture_recipe)
    with tempfile.TemporaryDirectory(prefix="defiantmaple-fictional-soak-") as temporary:
        base = Path(temporary).resolve()
        root = base / "fictional-source"
        root.mkdir()
        database = base / "catalog.sqlite3"
        initialize(database)
        with connect(database) as db:
            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        source_id = add_source(database, root)["source_id"]
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
        try:
            started = time.perf_counter_ns()
            observed = _paged_pass(database, source_id, 1_000_000_000, page_size)
            observe_ns = time.perf_counter_ns() - started
            if not observed["result"]["complete"] or observed["totals"]["pending"] != count:
                raise AssertionError("First observation was incomplete")

            started = time.perf_counter_ns()
            indexed = _paged_pass(database, source_id, 4_000_000_000, page_size)
            index_ns = time.perf_counter_ns() - started
            if (not indexed["result"]["complete"] or indexed["totals"]["indexed"] != count
                    or _asset_count(database) != count):
                raise AssertionError("Stable files were not all indexed")

            original_ids = _asset_ids(database)
            canceled = threading.Event()

            def cancel_after_progress(state):
                if (state["phase"] == "processing"
                        and state["processed"] >= count // 3):
                    canceled.set()

            interrupted = _paged_pass(database, source_id, 5_000_000_000, page_size,
                                      cancel_event=canceled, progress=cancel_after_progress)
            if not interrupted["result"]["canceled"] or _asset_count(database) != count:
                raise AssertionError("Cancellation did not preserve indexed assets")

            if _asset_ids(database) != original_ids:
                raise AssertionError("Cancellation changed original asset identities")

            # This new file sorts before the canceled cursor. A fresh enumeration
            # must see it; carrying the old cursor into a new inventory would skip it.
            early = root / "group-0000" / "fictional-000000-before.png"
            early.write_bytes(pngs[0])
            early_stat = (early.stat().st_size, early.stat().st_mtime_ns)
            started = time.perf_counter_ns()
            resumed = _paged_pass(database, source_id, 6_000_000_000, page_size)
            stable = _paged_pass(database, source_id, 9_000_000_000, page_size)
            recovery_ns = time.perf_counter_ns() - started
            if (not resumed["result"]["complete"] or not stable["result"]["complete"]
                    or _asset_count(database) != count + 1):
                raise AssertionError("Fresh resume skipped an earlier new file")

            recovered_ids = _asset_ids(database)
            if not original_ids <= recovered_ids:
                raise AssertionError("Fresh resume changed original asset identities")

            disconnected = base / "source-temporarily-unavailable"
            root.rename(disconnected)
            offline = scan_sources(database, source_id=source_id, now_ns=10_000_000_000)
            if (offline["sources"][0]["health"] != "offline"
                    or _asset_count(database) != count + 1 or _missing_count(database)):
                raise AssertionError("Offline source changed catalog assets")
            if _asset_ids(database) != recovered_ids:
                raise AssertionError("Offline source changed asset identities")
            disconnected.rename(root)
            online = _paged_pass(database, source_id, 11_000_000_000, page_size)
            if not online["result"]["complete"] or _asset_count(database) != count + 1:
                raise AssertionError("Source did not recover after reconnection")
            if _asset_ids(database) != recovered_ids:
                raise AssertionError("Online recovery changed asset identities")
            if (early.stat().st_size, early.stat().st_mtime_ns) != early_stat:
                raise AssertionError("Scanner changed the resume fixture")
            if any((path.stat().st_size, path.stat().st_mtime_ns) != original
                   for path, original in zip(source_files, original_stats)):
                raise AssertionError("Scanner changed a fictional source file")
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        # Byte verification stays outside both phase timing and allocation tracing.
        if any(path.read_bytes() != pngs[index % 8]
               for index, path in enumerate(source_files)) or early.read_bytes() != pngs[0]:
            raise AssertionError("Scanner changed generated source bytes")

    return {
        "schema": "defiantmaple.source-scan-soak.v1",
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "fixture_kind": "generated-fictional-png",
        "file_count": count,
        "page_size": page_size,
        "observation_pages": observed["pages"],
        "index_pages": indexed["pages"],
        "observation_seconds": round(observe_ns / 1e9, 3),
        "index_seconds": round(index_ns / 1e9, 3),
        "fresh_resume_seconds": round(recovery_ns / 1e9, 3),
        "timings_ns": {"observation": observe_ns, "indexing": index_ns,
                       "fresh_resume": recovery_ns},
        "catalog_schema_version": schema_version,
        "fixture": fixture_descriptor(count, fixture_recipe=fixture_recipe),
        "memory_scope": MEMORY_SCOPE, "cache_scope": CACHE_SCOPE,
        "python_peak_allocated_bytes": peak_bytes,
        "assets_after_recovery": count + 1,
        "interruption_resumed": True,
        "offline_retained_assets": True,
        "source_files_unchanged": True,
        "source_bytes_unchanged": True, "stable_identity_retained": True,
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
