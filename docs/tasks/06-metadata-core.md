# Task 06: Metadata catalog and safe migration

Owner: Sol backend (`scan_profile`). Status: completed locally; integration CI pending.

Checkout: DefiantMaple-metadata; branch codex/phase1-metadata; baseline 0578dfb.
Parent acceptance contract: Task 04. Current catalog schema v2 advances to v3.
PR 10 is an open dependency; do not change its branch or merge it.

Own defiantmaple/catalog.py, defiantmaple/metadata.py (or a focused equivalent),
Core metadata/migration tests, necessary existing Core test expectation updates,
and the parent-authorized `defiantmaple/__main__.py` init-result integration,
docs/metadata-design.md, and this task's results. Do not edit Qt, Rust, CI,
Task 04, the audit, or another agent's files.

Deliver normalized tags, aliases and acyclic parent tags; six typed entities
(Character, Artist, Project, Location, Client, Franchise), aliases, and explicit
asset assignments keyed by stable UUIDs. Preserve same-hash distinct assets.
Names and aliases need defined Unicode/case/whitespace normalization and shared
collision rules; entity namespaces may be scoped by type. Aliases reference a
canonical ID directly. Renames do not silently create aliases; parent changes
never propagate asset assignments. Include idempotent assign/unassign and
persistence across asset path changes. No recognition or source/sidecar writes.

First publish docs/metadata-design.md with the exact public API and returned
record shapes for the UI agent: create/rename/list tags/entities, alias editing,
parent changes, assign/unassign, and selected-asset metadata lookup. Also publish
the existing-catalog open/migration API and backup result. Notify root promptly
before implementing the full body so the UI can proceed against a stable contract.

Fresh catalogs use v3. Existing valid v1/v2 upgrades must be atomic across all
intermediate steps. Verify a consistent original-version backup before any
schema/data mutation, retain it on failure, and preserve all assets, provenance,
sources and source entries. Refuse future/unknown catalogs and provide a mode
for opening an existing library that cannot create a missing or unversioned file.
Check authenticity of supported-version schema before mutation. Define safe
locking and connection sequencing for backup versus migration; verify subtle
SQLite/Python transaction behavior against primary documentation. Do not rely
on executescript preserving an outer transaction or back up through a writing
connection. Avoid weakening catalog durability settings. Backups are private
local catalog files; never publish paths, UUIDs or user records in repo evidence.

Tests must cover fresh and empty/populated v1/v2 catalogs, original backup
readability/integrity/restoration, failed backup, failed intermediate DDL/data
step, complete rollback, unknown/future refusal, preserved IDs/provenance/source
state, namespace collisions, cycles, alias behavior, stable UUID assignment and
source/sidecar integrity. Use generated fictional fixtures only. Report exact
checks, API contract, changed files, backup lifecycle and remaining limitations.
No commits, pushes, branch changes, PRs, external messages or extra agents.

## Outcome (2026-09-28)

Implemented catalog v3 and the exact metadata API/record contract in
[metadata-design](../metadata-design.md). Tags, aliases, acyclic parents, six
typed entity namespaces and explicit stable-ID assignments are persisted without
source/sidecar or workflow/provenance changes. Write transactions reserve the
writer before collision/hierarchy validation; selected-record reads use one
snapshot.

`initialize(create=False)` refuses missing/unversioned catalogs and upgrades
supported v1/v2 before application connections open. A separately read backup
is verified before any DDL/data change and retained on success or later failure.
All intermediate steps and version changes roll back together. Supported-schema
authentication includes FK declarations and complete namespace/cycle trigger
bodies. Accepted legacy v1 tables are rebuilt canonically inside that transaction,
with original row values preserved. The old canonical ALTER-based v2 layout is
covered. CLI `init` now reports the initialization/migration fields and local
verified backup path; its focused test reads and verifies that output.

Changed owned files: `defiantmaple/catalog.py`, `defiantmaple/metadata.py`,
`defiantmaple/__main__.py`, `tests/test_catalog_migration.py`,
`tests/test_metadata.py`, necessary version expectations in `tests/test_core.py`
and `tests/test_sources.py`, `docs/metadata-design.md`, and this result brief.
No commits, pushes, branch changes or PRs were made by this owner.

Focused local checks: migration 12 passed (0.170 s), metadata 11 passed (0.151 s),
existing Core 16 passed (0.063 s), sources 9 passed (0.164 s), all with
`ResourceWarning` treated as an error. Environment: Python 3.14.7, SQLite 3.51.2,
pinned Pillow 12.3.0. Independent integration owner reported Core 106 and Qt 19
passed without failures/errors/skips. `git diff --check` passed.

Remaining limits: exclusive/quiesced application use during migration; locks do
not protect against external catalog-file substitution; backup duration has no
independent deadline; no product restore UI; no power-loss/hardware fault test.
Current-v3 launch checks schema declarations rather than scanning all rows.
Cross-platform CI remains the parent integration gate. No expensive benchmark or
real/private library was used for this task.
