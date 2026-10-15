# Task 41: verified metadata recovery implementation

Status: amended design and Core draft under independent review; Qt and
acceptance remain held. Owner: Sol (Core and Qt implementation). Separate Sol reviewer:
Task 43. Luna owns Task 42 acceptance. Root owns orchestration, requirement
tracker, integration, and publication decisions. Baseline: PR21 merge
`a42b213ec600db5cab2a55281533dd21ac53a584`, schema 6.

## Bounded objective

Implement the contract in [the recovery design](../metadata-recovery-design.md):
explicit metadata-only SQLite snapshot into a versioned, bounded single-file
package; read-only package inspection; restore to a new, isolated eligible
local catalog; current-runtime browse-only marker until explicit source-root
review. Preserve live catalog, stable asset IDs/revisions, metadata,
provenance, ordered collections, originals, caches, schema 6, and current
journal/durability settings. No auto-open, scan, source mutation, replacement
of existing destinations, portable export, scheduled retention, or media
inclusive mode. Source paths are unverified after restore. Schema 6 has no
stable library ID or durable standalone-asset review state; neither may be
claimed solved.

## Implementation sequence and review holds

1. **Freeze this design.** Independent Task 43 review must clear state-marker
   semantics, all original-media admission paths, storage policy, package
   bounds, publication/crash behavior, worker shutdown, and Qt target capture
   before runtime edits. Record any required design corrections here first.
2. **Core snapshot/package.** Add a recovery module with fixed format/limits,
   no-follow package inspection, SQLite online backup in an owned worker,
   cooperative progress/deadline and hard parent worker-lifetime bound,
   verified closed staging, and no-overwrite publication. Reuse existing
   catalog declaration/integrity checks rather than duplicating weaker
   validation. Do not conflate migration backup with a user backup.
3. **Core restore/admission.** Verify untrusted package in a bounded worker;
   restore to private staging, set `application_id=RESTORE_PENDING`, disable
   sources with durable ID/root-derived `health_detail` holds, verify, close,
   publish to a new local leaf. Encode each hold with the exact versioned
   UTF-8/SHA-256 formula in the design. Make current-build catalog/Core
   original-media admission fail closed for pending/unknown
   marker and disabled restored sources, covering scanner, direct indexing,
   cached-preview regeneration, direct thumbnails, external actions, Qt
   original inspector/comparison, and standalone `source_id NULL` assets.
   The full-image child decoder must receive a captured catalog identity and
   requery Core admission immediately before opening the original; button
   state or parent-only refusal is insufficient. Include CLI callers.
   Move `index_file` admission ahead of source `resolve`/`stat`; instrument
   a refused path to prove it is not probed. Audit product raw SQLite openers
   (gallery gateway/query, cached preview, comparison) so unknown markers
   fail closed at open and pending reads remain cache/metadata-only.
   Cache-only metadata browsing remains available; ordinary active enabled
   paused sources keep existing behavior. Add captured complete source-root
   review and catalog activation for linked-only catalogs, leaving every
   source disabled with its review hold; ordinary enable refuses the hold and
   per-source enable is a separate explicit captured action.
   Direct standalone indexing waits until all restored source holds clear;
   explicit source indexing checks held-root and approved-root containment
   before original access, including after path resolution.
   Refuse activation with standalone assets and report their count; never
   offer an override.
   Require `.dmbackup` and `.sqlite3` output leaves and protect the captured
   active catalog plus its SQLite sidecar names; separate new leaves can share
   one trusted private parent. The first Linux storage adapter certifies only
   local PCIe NVMe backing and refuses other/unknown devices.
4. **Qt workflow.** Provide explicit Backup, Inspect, Restore-to-new-location,
   and Review restored roots actions. Display metadata-only omissions,
   private-path sensitivity, uncertain publication, pending/browse-only state,
   unverified paths and standalone limit. Capture database/package/target
   identities and view epoch for every worker request/reply. Bound progress,
   cancel, and window close; attempt bounded join/reap, retain ownership of
   an exceptional kernel-blocked worker, and report pending cleanup. No reply
   may switch the active library, gallery selection, or target path.
5. **Generated evidence.** Implement meaningful Core and Qt tests at the
   actual failure boundaries, then hand frozen inputs to Task 42. Task 43
   independently reviews implementation, tests, raw-to-sanitized evidence,
   and final diff. Root alone advances tracker/PR/output state.

Core implementation began after the initial Task 43 design clearance. The
per-source hold and explicit captured cache-root set amend that design; repeat
Task 43 review is required before Core or Qt clearance.

## Acceptance checklist

- A controlled concurrent writer cannot produce a mixed snapshot; sustained
  writes/busy state terminate with no success package. Closed snapshot schema,
  integrity, relationships, size and SHA-256 match manifest.
- Inspection refuses malformed/truncated/oversize/changed/symlink/reparse
  packages, unknown versions, invalid schema and relationships. Failure,
  cancel, worker crash, disk-full and target collision never overwrite a
  source, backup or existing catalog; uncertain post-link outcomes are named.
- Restore preserves generated IDs, revisions, metadata, taxonomy/aliases,
  provenance, source entries, curation history and ordered collections except
  documented source enabled/health/health_detail guard fields and application marker.
- Pending linked and standalone assets refuse every Core/Qt original-media
  path while metadata/verified cache reads work. Explicit root review can
  activate a linked-only catalog with captured mapping checks and no scan.
  Standalone-bearing catalogs remain pending with an actionable count.
  Existing active enabled-paused behavior is unchanged.
- Eligibility refuses remote/unknown storage and unsafe containment. Package
  and restore publication are create-if-absent on supported Linux, macOS and
  Windows, with durability claims matching proven platform primitives.
- Event loop remains responsive; close/cancel owns worker exit; stale results
  cannot retarget a gallery or overwrite user selection. Actual platform
  skips and limits are reported, never folded into a pass claim.
- No real private paths/raw logs enter public fixtures or docs. Generated
  acceptance follows [Task 42](42-metadata-recovery-acceptance.md) and the
  [protocol](../metadata-recovery-acceptance.md). The 15 deployed outputs and
  prior source baseline remain byte/mode/time unchanged unless Root separately
  authorizes replacement.

## Deferrals and honest status

This task does not complete FR-RECOVERY-003 scheduled local snapshots,
FR-RECOVERY-006 portable reconstruction, FR-LIB-003 general broker, or
FR-LIB-007 rebuild. It cannot claim the stable-library-ID part of
FR-RECOVERY-005. A pending catalog containing standalone assets intentionally
remains browse-only until a later durable per-asset identity/relink design.
The current-runtime marker is not enforced by old application builds. Full
Phase 1a recovery/release acceptance stays open until separately evidenced.
