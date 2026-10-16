# Task 44 — stable library identity and compatible recovery

Status: design, Core/admission, Qt integration and diagnostic compatibility
independently cleared. Full Core 311 and offscreen Qt 188 tests passed with
direct exits zero and independent receipt review; all 154 frozen runtime,
test and build inputs remain unchanged. An isolated exact-source frozen build
is running. Genuine legacy, frozen/native, hosted CI and final acceptance
remain pending. No acceptance or release claim.
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
