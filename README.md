# DefiantMaple

A local-first artist gallery and digital asset management project, based on
*Artist Gallery and Asset Management Platform — SDD 0.1 (24 September 2026)*.

## Current status: Phase 1 desktop gallery

Phase 0 established the catalog/archive foundation and selected Qt/PySide6 for
the desktop client. Phase 1 now includes a decoder-backed PNG thumbnail cache,
a persisted multiple-source scanner, and a reproducible local image-embedding
comparison. The first Qt/PySide6 desktop workflow now creates or opens a library,
registers local sources with an explicit existing-file policy, scans in the
background, browses cached thumbnails, supports review and filtering, and shows
details, source issues, and exact duplicates. Catalog metadata now includes tags,
aliases, parent tags and six typed entity categories, with explicit assignment
to stable asset UUIDs through the Qt editor. Manual collections keep ordered
asset UUID memberships, with create, rename, delete, add, remove and adjacent
move controls in the gallery. It is a one-shot scanner rather
than an ongoing filesystem watcher. Optional embedding vectors remain outside
the asset catalog and never change original media or metadata. Python 3.11+
is the baseline for the catalog; model dependencies are optional. See the
[gallery launch and hands-on guide](prototypes/qt/README.md).

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

- `init` creates schema version 4 transactionally and upgrades supported v1/v2/v3
  catalogs in one transaction. Upgrades verify a SQLite-consistent backup beside
  the catalog before changing schema/data; the JSON result includes its path.
  Missing existing libraries and unknown/newer schemas are refused when opening
  through Qt. See the [metadata and migration guide](docs/metadata-guide.md).
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
ambiguous rename reconciliation, and native long-running watchers are not
implemented. The gallery does not write, move, or delete source media.

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

The [source-scan resilience gate](docs/source-scan-resilience.md) now uses
generated files to exercise sustained scans, interruption, fresh resume, and
simulated Offline recovery across the desktop CI platforms. Real mounted-share
disconnect testing remains the next gate before native watching. Phase 2's
journal and recovery foundation remains the prerequisite for any organizing
file mutations.

The [current task briefs](docs/tasks/00-phase1-orchestration.md) assign the
Phase 1 coverage audit, scan-cost profiling, and mounted scratch-share validation
work, plus the catalog metadata and manual collection milestones, with explicit
ownership, acceptance criteria, and evidence limits. The
[manual collections guide](docs/collections-guide.md) describes ordering,
unavailable assets and migration boundaries. Saved queries, tag rules, character
recognition fields, sidecars and file mutations remain outside this increment.
