# Task 33: Cached-offline acceptance and requirement tracking

Baseline and authorization are in [Task 32](32-cached-offline-implementation.md).
Luna owns this task, [the requirement tracker](../phase1-requirements-tracker.md),
[the acceptance protocol](../cached-offline-acceptance.md), sanitized derivatives,
privacy checks, and actual hosted CI summaries. Independent Sol owns Task 34
source/helper/evidence review. Root owns Task32/orchestration, design and helper
clearance, branch/integration, serialized visible native acceptance, and draft
publication. Root alone launches the visible native helper after independent
review and an unlocked-session preflight.

## Acceptance objective

The cache compatibility, identity, fallback, containment, resource-bound design,
legacy cache-reader exception, and fifth smoke proposal are cleared by independent
Task 34 review and Root at proposal SHA256
`4d8b0fb2129ea92668e2b0353143cdb4577b40f7b59180dfebed4edddd870e1a`. Keep the
implementation aligned to that contract; further deviations must be reviewed
before the affected evidence is accepted. Scoped source-build native acceptance passed on one
Linux host, and the local frozen fifth smoke applied the 512 MiB child
address-space limit. The first PR19 head then showed a Darwin gap: Core
Python 3.11 and 3.13 each failed seven of 258 tests because applying the
default limit returned `ValueError`; the Qt macOS job stopped at its failed
Core prerequisite. The reviewed policy allows only a Darwin `setrlimit`
`ValueError` when both requested and effective limits are the default
536,870,912 bytes to be reported as attempted but unenforced
(`address_space_enforced=false`). The logs do not establish the exception's
cause. Other limit errors still refuse; Linux remains fail-closed. The
correction passed 37 focused Core/legacy tests locally. This is not RSS
evidence. Fresh exact-head Core/Qt/Tauri checks, especially the real child and
frozen fifth smoke on the affected runtime, remain required. Do not infer
defaults from the SDD's unaccepted performance budgets. The required matrix,
generated fixture limits, checks, snapshot evidence and privacy rules are in
[Cached-offline gallery acceptance](../cached-offline-acceptance.md).

The evidence chain must distinguish offscreen Core/Qt tests, generated visible
Linux source-build acceptance, each hosted exact-head workflow, each named frozen
worker/package smoke, and human-observed local external-open feedback. Local
checks passed (Core 258, Qt 73, Node 1); the broad tracked-baseline privacy check
passed before new evidence files were staged, so final staged-set validation is
still required. Exact-head hosted checks remain pending. Native attempt 1 is
recorded in the protocol and sanitized derivative. The user's
Gwenview default, Krita v5.3.4 AppImage cold/running, and Dolphin containing-folder
reports are recorded as human observations associated with PR18's build context;
that context does not identify the user's running application. These reports do
not establish cache/offline behavior, source/catalog preservation, editor save,
rescan, or failure/cleanup coverage.

## Requirement tracking

Map these 129 unique SDD IDs exactly once in the tracker. Preserve current
statuses and never upgrade a row without its explicit gate and independent
review. Downgrade a status when a scope audit finds it overstates cached-offline
behavior that remains unaccepted.

- Direct cache/offline contract: FR-UX-007, FR-MEDIA-004, NFR-004.
- Attempt 1 provides scoped native and local frozen-worker evidence for these
  rows; each stays Partial because broader corruption, compatibility, fallback,
  platform, and adopted performance gates are not all covered.
- Original-only control and immutable targeting scope: FR-UX-002 and FR-EXT-001,
  with relevant targeting/focus rows FR-UX-006 and FR-UX-010. PR18's user feedback
  supports only observed local open happy paths; FR-UX-008 remains Partial
  because side-by-side comparison is unaccepted.
- Relevant displayed image policies: FR-MEDIA-001 and FR-MEDIA-003. ICC/color
  fidelity and broader format coverage stay outside this task's accepted scope.
- Worker scheduling, bounds and safe cancellation: FR-JOB-001, FR-JOB-003,
  FR-JOB-004. Publish only caps defined by reviewed design and measurements
  actually collected.
- Untrusted cache parsing and privacy: SEC-PARSE-001, SEC-PARSE-002,
  SEC-PARSE-003, NFR-010, NFR-014. General accessibility, release qualification,
  backup/restore/export and broad-platform qualifications remain Partial or
  deferred according to their existing requirement gates.

## Execution and handoff

Do not implement production code or run native UI here. Review Sol's design and
helper before Root runs native; preserve raw attempts, failures, source/catalog
snapshots and generated fixture manifests. Do not access user artwork, NAS,
network shares, global application associations, or source/output binaries.

Audit the merged-main PR18 Core push run separately from the new PR's exact-head
Core push/PR, Qt and Tauri runs. Reuse existing same-head PR18 hosted evidence
where hashes and run IDs are unchanged. Inspect actual Windows summaries and
named capability skips; never count a skip as a pass or classify successful
jobs by noisy cache cleanup text. Run the public privacy validator and manually
inspect derivatives/captures. No broad characterization rerun, workflow change,
new cohort, docs-only post-publication commit, merge or output replacement is
part of this task.

Completion requires a reviewed generated native acceptance, exact-head relevant
CI green with Windows actual summaries, published privacy-reviewed derivative,
independent Task 34 clearance, and documented limits. Keep all other requirement
rows Partial where broader scopes remain incomplete. A merge or deployed-binary
replacement is a separate decision.
