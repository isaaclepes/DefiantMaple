#!/usr/bin/env python3
"""Generate a deterministic catalog for desktop gallery comparisons."""
from argparse import ArgumentParser
from pathlib import Path, PurePosixPath
import hashlib
import json
import time

from defiantmaple.catalog import connect, initialize


MEDIA_TYPES = ("image/png", "image/jpeg", "image/webp", "video/mp4")
WORKFLOW_STATES = (
    "new", "needs_review", "reviewed", "organized", "ignored", "error"
)


def generate(database: Path, count: int, batch_size: int = 10_000) -> dict:
    if count < 1 or count > 1_000_000:
        raise ValueError("count must be between 1 and 1,000,000")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    started = time.perf_counter()
    initialize(database)
    with connect(database) as db:
        if db.execute("SELECT 1 FROM assets LIMIT 1").fetchone():
            raise ValueError("benchmark catalog must be empty")
        for first in range(0, count, batch_size):
            rows = []
            provenance = []
            for index in range(first, min(first + batch_size, count)):
                asset_id = f"00000000-0000-0000-0000-{index:012d}"
                # Every 100th pair shares a content hash so duplicate views have data.
                content_number = index - 1 if index % 100 == 1 else index
                checksum = hashlib.sha256(
                    f"synthetic-asset-{content_number}".encode("ascii")
                ).hexdigest()
                media_type = MEDIA_TYPES[index % len(MEDIA_TYPES)]
                extension = media_type.rsplit("/", 1)[1].replace("jpeg", "jpg")
                current_path = str(PurePosixPath(
                    "/synthetic/library", f"{index // 1000:04d}",
                    f"asset_{index:08d}.{extension}",
                ))
                rows.append((
                    asset_id, current_path, media_type, checksum,
                    32_768 + index % 4_000_000,
                    WORKFLOW_STATES[index % len(WORKFLOW_STATES)],
                ))
                provenance.append((
                    f"10000000-0000-0000-0000-{index:012d}", asset_id,
                    "benchmark_fixture", json.dumps({"fixture_index": index}),
                ))
            db.executemany(
                "INSERT INTO assets(asset_id,current_path,media_type,sha256,byte_size,workflow_state) "
                "VALUES(?,?,?,?,?,?)",
                rows,
            )
            db.executemany(
                "INSERT INTO provenance(provenance_id,asset_id,source_kind,details_json) "
                "VALUES(?,?,?,?)",
                provenance,
            )

    return {
        "database": str(database),
        "assets": count,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "fixture_version": 1,
    }


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args(argv)
    try:
        result = generate(args.database, args.count, args.batch_size)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
