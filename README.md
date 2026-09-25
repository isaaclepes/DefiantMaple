# DefiantMaple

A local-first artist gallery and digital asset management project, based on
*Artist Gallery and Asset Management Platform — SDD 0.1 (24 September 2026)*.

## Current status: Phase 0 technical spike

This first slice implements a per-library SQLite catalog and read-only generic
ZIP inspection. It is a command-line foundation, not yet a desktop gallery or a
complete importer. No account, telemetry, network service, or external Python
package is required at runtime. Python 3.11+ is the spike baseline.

From the repository root:

```sh
python -m defiantmaple init /path/to/library/catalog.sqlite3
python -m defiantmaple index /path/to/library/catalog.sqlite3 /path/to/art.png
python -m defiantmaple list /path/to/library/catalog.sqlite3 --limit 100 --offset 0
python -m defiantmaple duplicates /path/to/library/catalog.sqlite3
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
- `inspect-zip` preserves original member paths, suggests ASCII names based on
  signature hints, and reports blocked entries. It never extracts content.

Signatures currently cover PNG, JPEG, GIF, WebP, and selected MP4 brands. A
signature is **not** a successful decoder validation: truncated or malformed media
can match. JSON records this limitation explicitly. WebM probing, thumbnails,
archive commits, watchers, automatic reconciliation, and UI are not implemented.

ZIP preview defaults: 64 MiB archive, 10,000 members, 2 GiB declared total expanded
size, 256 MiB per member, 200:1 compression ratio, and 4 KiB probes. Limits are
configurable through the Python `Limits` API. Large archives may be rejected by
this conservative spike. Nested archives are listed without expansion. Full-member
CRC validation is not guaranteed by prefix reads.

See [the SDD review and delivery plan](docs/sdd-review.md) for design decisions,
requirements coverage, risks, and the next implementation milestone. The
[desktop stack comparison](docs/desktop-stack-comparison.md) now defines the
candidate set, evidence gates, and shared 100,000-row benchmark contract.
