# DefiantMaple

A local-first artist gallery and digital asset management project, based on
*Artist Gallery and Asset Management Platform — SDD 0.1 (24 September 2026)*.

## Current status: Phase 1 thumbnail-cache slice

Phase 0 established the catalog/archive foundation and selected Qt/PySide6 for
the desktop client. The first Phase 1 slice adds a decoder-backed PNG thumbnail
cache without changing original media. It remains a command-line foundation,
not yet the desktop vertical slice or a complete importer. Python 3.11+ is the
baseline.

From the repository root:

```sh
python -m pip install -r requirements.txt
python -m defiantmaple init /path/to/library/catalog.sqlite3
python -m defiantmaple index /path/to/library/catalog.sqlite3 /path/to/art.png
python -m defiantmaple list /path/to/library/catalog.sqlite3 --limit 100 --offset 0
python -m defiantmaple duplicates /path/to/library/catalog.sqlite3
python -m defiantmaple thumbnail /path/to/library/catalog.sqlite3 \
  ASSET_UUID /path/to/library/thumbnail-cache --max-edge 256
python -m defiantmaple inspect-zip /path/to/export.zip
python -m unittest discover -s tests -v
```

Use `python3` if that is your interpreter command. Commands emit JSON; expected
failures emit a JSON error on stderr and exit with status 1.

- `init` creates schema version 1 transactionally and refuses unknown/newer DBs.
- `index` reads one regular file, assigns a UUID, hashes bytes, and records original
  path provenance. Repeated indexing of unchanged files preserves the ID. Different
  paths with identical bytes remain separate assets grouped by SHA-256. Files that
  change during a read are rejected. Original media is never written.
- `list` uses bounded pagination; `duplicates` reports hash groups and counts.
- `thumbnail` validates the catalog fingerprint in a spawned Pillow decoder,
  enforces byte, dimension, pixel, and time limits, and atomically caches a PNG
  under the asset UUID plus SHA-256/size fingerprint. Malformed or oversized
  images do not leave a cache entry, and cache corruption triggers regeneration.
- `inspect-zip` preserves original member paths, suggests ASCII names based on
  signature hints, and reports blocked entries. It never extracts content.

Signatures currently cover PNG, JPEG, GIF, WebP, and selected MP4 brands. A
signature is **not** a successful decoder validation: truncated or malformed media
can match. The thumbnail command performs decoder validation for the requested
asset only. WebM probing, video posters, archive commits, watchers, automatic
reconciliation, and the Phase 1 UI are not implemented.

The decoder worker contains crashes, exceptions, decompression-bomb warnings,
and timeouts away from the caller. Pixel and source-byte limits reduce resource
exposure, but this process boundary is not an OS sandbox or a substitute for
future worker memory limits and decoder fuzzing.

ZIP preview defaults: 64 MiB archive, 10,000 members, 2 GiB declared total expanded
size, 256 MiB per member, 200:1 compression ratio, and 4 KiB probes. Limits are
configurable through the Python `Limits` API. Large archives may be rejected by
this conservative spike. Nested archives are listed without expansion. Full-member
CRC validation is not guaranteed by prefix reads.

See [the SDD review and delivery plan](docs/sdd-review.md) for design decisions,
requirements coverage, risks, and the next implementation milestone. The
[desktop stack comparison](docs/desktop-stack-comparison.md) now defines the
candidate set, evidence gates, and shared 100,000-row benchmark contract.
