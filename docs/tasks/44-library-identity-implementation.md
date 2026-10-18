# Task 44 — stable library identity and compatible recovery

Status: design, Core/admission, Qt integration and diagnostic compatibility
independently cleared. Full Core 311 and offscreen Qt 188 tests passed with
direct exits zero and independent receipt review at the historical 154-input
freeze. The bounded integration correction supersedes two frozen inputs; the
other 152 runtime, test and build inputs remain unchanged. The isolated frozen
build passed all eight smokes and preserved the deployed outputs. The bounded
Tauri and Windows fixture corrections were independently cleared and published
at `a9e2be9fe5239e3fb3e1d743d3050e441813f553`. The private LI07 pre-held writer
experiment is independently cleared within its declared scope. All 30 hosted checks at that correction head passed.
Windows Qt logged Core311/21 skips and Qt188/6 skips, followed by successful
packaging. Final independent evidence/publication-head verification remain
integration gates. This is bounded implementation evidence, not a
full SDD or release claim.
Owner: Sol. Base: PR22 merge `d53d7d0675800ec8bd71536c1be0c6890ee4bd01`.

## Intended user behavior

A library has one immutable, validated UUID independent of its path and source
roots. New catalogs receive one identity. Supported existing catalogs upgrade
only after verified original-state backup; reopening or relocating a catalog
does not assign a different identity. Metadata backup, inspection and isolated
restore preserve an identity that was actually stored. Legacy schema-6 backups
remain inspectable, with explicit missing-identity reporting and documented
isolated-restore identity assignment rather than a false preservation claim.

## Design gate

Write `docs/library-identity-design.md` and a compatibility matrix before code.
Cover schema/version authentication, singleton UUID validation and ownership,
creation/migration/rollback, preservation of prior migration backups, legacy
catalogs and package versions, old-client refusal, pending restored catalogs,
standalone assets, cancellation/uncertain publication and worker cleanup.
Choose package-version and manifest changes deliberately; incrementing the
current schema constant alone must not invalidate deployed schema-6 packages.
Inspection never mutates a package or invents persistent identity. Repeated
restores of identity-less packages need honest semantics. Keep `application_id`
exclusively as the existing restore-state marker. Do not claim cross-instance
broker coordination; identify supported migration lock/concurrency limits.
Independent Sol review must clear the design before schema/runtime edits.

## Implementation ownership and limits

Own the design, Core/Qt implementation, necessary generated regression tests,
and minimal packaging integration. Coordinate test ownership with Task45.
Preserve existing row identities, metadata/taxonomy/provenance/order/history,
journal/synchronous settings, media/cache, scanner semantics, pending/global
and per-source holds, standalone browse-only limits, and deployed outputs.
No scheduling, retention deletion, portable import/export, relink, source-file
writes, broad performance experiments or output deployment. No commits,
branch switches, pushes or PR creation: Root integrates and publishes.

## Traceability and evidence

SDD v0.2 §§5.3, 6.1, 16.3, 21.2, 22.3, 25; FR-LIB-001/002,
FR-RECOVERY-001/002/004/005 and NFR-005. Keep broad requirement rows Partial.
Test new/reopen/relocate identity, old-schema upgrades and original backup,
failed migration rollback, malformed/missing/duplicate identity, package
compatibility and identity equality, exact metadata fingerprints and retained
source guards. Do not replace meaningful assertions with generic success.
Run focused checks at material changes, then relevant full suites after freeze.
Native/frozen acceptance and actual Windows CI remain Task45/46 gates.


## Current implementation stage

The reviewed [design](../library-identity-design.md) defines schema 7 identity,
v2/schema-7 manifests and exact deployed v1/schema-6 compatibility. Independent
Task46 review cleared the design and then the Core/admission stage. Core adds
immutable authenticated singleton UUIDs, verified migration and rollback,
legacy inspection without identity invention, isolated legacy assignment,
and modern identity-preserving restore. Bounded current-catalog admission
covers ordinary Core and Qt raw readers without an integrity scan per read.

Qt reports legacy absence, fresh assignment, or exact modern preservation;
restore confirmation discloses legacy assignment and defaults to No. Captured
inode and stale-worker guards remain in place. Generated regressions cover
these behaviors. Private Core focused receipts record 13 identity, 21 migration,
24 recovery, 10 curation, 10 bulk, 11 gallery-query and 21 cached-preview cases,
all passing. Initial failed invocations/assertions and the independent admission
finding remain recorded in private history. Handcrafted legacy unit packages
do not replace the required actual PR22 producer acceptance fixture.

Final source freeze, full Core/Qt suites, frozen/native evidence, actual Windows
CI, and final independent Task46 review remain gates owned with Root/Task45.

## Pause checkpoint — initial PR23 hosted Tauri failure

The initial PR23 head `d39fe8a72d4b7a3ccdd840e7c5090547442dbf52`
failed the Tauri benchmark/package job on Windows, macOS and Ubuntu. Actual
logs show successful Rust tests and release compilation followed by the built
application refusing the shared generated catalog with `unsupported catalog
schema 7`. The executable exits 2; the Python package wrapper exits 1. The
unchanged Rust reader accepts only schemas 2–6, while the current shared
generator correctly produces schema 7. The earlier cargo-cache probe is not
the terminal failure. This failed cohort is retained; no job was rerun.

The proposed next change is a bounded Rust schema-7 compatibility update with
meaningful identity-preservation regression coverage and continued future
schema refusal. Independent review must settle its precise admission scope
before implementation. Do not downgrade the shared fixture or weaken the
benchmark. Cargo is unavailable in the local session, so no local Rust pass
is claimed; a correction requires actual hosted validation. No Tauri or other
runtime source was changed before the pause. Root owns the separate genuine
Core/native acceptance receipts and their review. Existing GitHub jobs remain
running; resume requires the user's instruction.

## Resumed hosted integration correction

The Tauri correction is limited to its Rust catalog prototype. Schema 7 is
admitted only after bounded authentication of the identity table declaration,
all three immutable trigger declarations, and exactly one canonical RFC 4122
version-4 UUID row. Historical schemas 2–6 retain their existing behavior;
unknown schema 8 and future versions remain refused. Regression cases cover
schema-7 paging/filtering/workflow updates with unchanged UUID and malformed
identity/declaration refusal without catalog mutation. The shared generator
and benchmark remain unchanged. Independent review is pending.

The final SQL comparison preserves single-quoted literal case, whitespace and
doubled quote escapes. Authored Rust regressions reject altered quoted table
constraints and test normalization directly. A fresh Python mirror comparison
against an actual Core-generated schema-7 catalog confirms that the current
Rust table/trigger literals match the producer and leaves catalog bytes unchanged.
This is not Rust execution. Cargo and rustc remain unavailable locally; authored
Rust tests, compilation and the corrected actual package path require fresh
hosted evidence.

Initial Windows Core failures occurred before the identity guard because the
generated test target used POSIX `/generated.png`. The test now derives an
absolute path from its platform-native temporary root. The focused identity
suite passed all 13 tests in 7.983 seconds with direct exit zero; its retained
receipt and log match the current test hash. This local result does not establish
Windows success or a Windows Qt-suite outcome. Fresh hosted Windows execution
remains required.

Exactly two of the 154 frozen paths are superseded: Rust main at SHA-256
`cf50e3cd2a5a33c95df26e81eb91b8e6a496e48ca9ab595159b6893cc75a9c10`
and the identity test at
`a1e154471e47da6930fbc8f961ece24afdd80918d8f39ee7c8af4025f0c87655`.
All other 152 frozen input hashes still match. Core/Qt Python runtime is
unchanged, so previously reviewed Core311, Qt188, frozen8, genuine Core and
native evidence retains its historical scope. No redundant broad suite, native
or frozen build rerun was performed. Independent final correction review and
actual current-head hosted evidence remain gates; no completion or release
claim is made.
