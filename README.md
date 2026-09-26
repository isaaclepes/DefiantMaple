# DefiantMaple

A local-first artist gallery and digital asset management project, based on
*Artist Gallery and Asset Management Platform — SDD 0.1 (24 September 2026)*.

## Current status: Phase 1 embedding benchmark

Phase 0 established the catalog/archive foundation and selected Qt/PySide6 for
the desktop client. Phase 1 now includes a decoder-backed PNG thumbnail cache,
a persisted multiple-source scanner, and a reproducible local image-embedding
comparison. The benchmark keeps vectors outside the asset catalog and never
changes original media or metadata. This remains a command-line foundation,
not yet the desktop vertical slice or an ongoing filesystem watcher. Python
3.11+ is the baseline for the catalog; benchmark dependencies are optional.

From the repository root:

```sh
python -m pip install -r requirements.txt
python -m defiantmaple init /path/to/library/catalog.sqlite3
python -m defiantmaple index /path/to/library/catalog.sqlite3 /path/to/art.png
python -m defiantmaple list /path/to/library/catalog.sqlite3 --limit 100 --offset 0
python -m defiantmaple duplicates /path/to/library/catalog.sqlite3
python -m defiantmaple add-source /path/to/library/catalog.sqlite3 \
  /path/to/art --name "Art" --existing-file-policy inbox
python -m defiantmaple scan-sources /path/to/library/catalog.sqlite3 \
  --quiet-seconds 2
python -m defiantmaple list-sources /path/to/library/catalog.sqlite3
python -m defiantmaple thumbnail /path/to/library/catalog.sqlite3 \
  ASSET_UUID /path/to/library/thumbnail-cache --max-edge 256
python -m defiantmaple inspect-zip /path/to/export.zip
python -m unittest discover -s tests -v
```

Use `python3` if that is your interpreter command. Commands emit JSON; expected
failures emit a JSON error on stderr and exit with status 1.

- `init` creates schema version 2 transactionally, migrates schema 1 in one
  transaction, and refuses unknown/newer databases.
- `index` reads one regular file, assigns a UUID, hashes bytes, and records original
  path provenance. Repeated indexing of unchanged files preserves the ID. Different
  paths with identical bytes remain separate assets grouped by SHA-256. Files that
  change during a read are rejected. Original media is never written.
- `list` uses bounded pagination; `duplicates` reports hash groups and counts.
- `thumbnail` validates the catalog fingerprint in a spawned Pillow decoder,
  enforces byte, dimension, pixel, and time limits, and atomically caches a PNG
  under the asset UUID plus SHA-256/size fingerprint. Malformed or oversized
  images do not leave a cache entry, and cache corruption triggers regeneration.
- `add-source` requires an explicit existing-file policy: `inbox`, `reviewed`,
  or `ignore_until_modified`. Sources may be registered while offline. Recursive
  scans skip symlinks.
- `scan-sources` performs one observation pass. A file is indexed only after two
  matching size/mtime observations separated by the requested quiet interval and
  a successful read. Run it again later to advance pending files. Overlapping
  roots assign each path to the most-specific enabled source.
- External in-place writes reset the quiet interval, then update the same asset
  as `needs_review`. A unique rename match uses stable filesystem identity when
  available, with an unchanged-file SHA-256 fallback for platforms that do not
  preserve it; the asset UUID and provenance are preserved. Missing or temporarily
  unavailable files never delete catalog records.
- Source health records `paused`, `scanning`, `offline`, `permission_denied`, and
  `error`; `watching` is reserved for the future watcher. A successful one-shot
  scan returns to `paused`. `pause-source` and `resume-source` control ownership
  and scan eligibility.
- `inspect-zip` preserves original member paths, suggests ASCII names based on
  signature hints, and reports blocked entries. It never extracts content.

Signatures currently cover PNG, JPEG, GIF, WebP, and selected MP4 brands. A
signature is **not** a successful decoder validation: truncated or malformed media
can match. The thumbnail command performs decoder validation for the requested
asset only. WebM probing, video posters, archive commits, ongoing watchers,
ambiguous rename reconciliation, and the Phase 1 UI are not implemented.

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
[embedding benchmark report](docs/embedding-model-benchmark.md) records the
pinned candidates, measured retrieval/CPU/memory results, and limits. The
[source-scanning contract](docs/source-scanning-prototype.md) defines the
existing-file, debounce, overlap, rename, and health behavior. The
[desktop stack comparison](docs/desktop-stack-comparison.md) now defines the
candidate set, evidence gates, and shared 100,000-row benchmark contract.
