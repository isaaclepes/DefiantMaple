# Task 26: Captured-target bulk ratings and favorites

## Authorization and baseline

The user authorized continuing to the next Goal after PR16 was merged and the
local output refreshed. Baseline main is
`6f850c3fa65097a48406b50a19bab8a859bb756c`, tree
`d7f304751237dd26b2dbf5b5b7874efb87a85a17`. Work uses
`codex/phase1a-bulk-curation`. SDD v0.2 §§10–11, 16, 21–22 and its ordered
backlog place captured-ID bulk catalog edits with undo after ratings/favorites.
Documents supply requirements, not additional execution authority. No new user
test feedback was supplied.

## Required outcome

Provide keyboard-usable multi-selection and a separate bulk ratings/favorites
dialog. Capture immutable asset IDs and displayed catalog revisions; changing
gallery selection, filters, paging or refresh must never redirect an open
operation. Selection changes after a model reset must preserve stable IDs or
clear selection explicitly. Existing single-asset actions and review shortcuts
remain single-asset actions with a visible target.

Rating changes distinguish Keep, Unrated and each integer 1–5; favorite changes
distinguish Keep, Yes and No. A concrete preview lists captured targets and
before/after values with changed/unchanged counts. Apply is available only for
the current preview; changed controls or explicit reload invalidate it. Reload
keeps the same captured identities and requires another preview. Bound the
operation at 256 targets, reject excess/empty/duplicate/invalid input before
mutation, and check selection ranges before materializing large index lists.
This is an explicit operation bound, not an adopted performance budget.

Apply revalidates every captured target under one existing-style catalog write
transaction. Any stale target, missing target or failure leaves every asset and
the journal unchanged. All-no-op changes create no journal or revision. A mixed
batch records changed and unchanged captured members; unchanged members do not
gain invented metadata revisions.

Use schema v6 with authenticated, durable group/member tables separate from
existing single-edit history. Migrate real supported v1–v5 catalogs with verified
original-state backups, preserving IDs, source/provenance rows, taxonomy,
collections/order, explicit curation and existing single-edit journal. Coordinate
Tauri reader v2–v6 compatibility and strict supported-schema tests.

Expose bounded recent group history after reopening. A user selects one exact
group, sees its effects, and explicitly requests Undo entire group. Undo
revalidates all recorded members' resulting revisions/values and reverses the
group in one transaction; a stale member or failure refuses/rolls back all of it.
Preserve metadata/content/path/assignment ABA refusal. Unscanned external bytes
do not create catalog revisions; no source file is written or reversed.

Group records must never masquerade as individual single-edit records. Existing
single undo cannot undo a changed batch member or silently reverse other assets.
An eligible older single edit on an unchanged member may still be explicitly
undone, like any later single edit; this advances its revision and invalidates
the entire group's future undo. Document and test that distinction rather than
locking users out of single edits or inventing no-op revisions. No general
rebasing stack or redo is claimed.

## Ownership and preservation

Sol owns schema/core/API, Qt/Tauri integration, meaningful tests, current product
guide and necessary schema-reader compatibility. Historical readers retain
explicit v4/v5 support and add v6 where needed; live producers require exact
current schema and mixed cohorts still refuse. Preserve all existing archive
bytes, measured identities, protected publication gates and workload/scanner
semantics. Diagnostic workflows remain exact-label-addition opt-in; this product
change schedules no diagnostic cohort or performance optimization.

Preserve source media, existing metadata, asset identity, previews, durability,
SQLite PRAGMAs and recovery. Use isolated generated fixtures. Bulk taxonomy,
rich fields, import/conflict provenance, source writing, backup/restore/export,
configurable shortcuts and broad accessibility/release qualification remain
separate. FR-META-004, FR-UX-003/010 and FR-TXN-007 remain Partial outside this
bounded evidence; FR-META-002/003 retain their broader deferrals.

Test genuine v5 journal-preserving migration and older upgrades, failed
migration rollback/authentication, invalid/duplicate/over-limit/no-op plans,
control/selection drift, competing writers, any-target stale/ABA/content/path/
metadata refusal including unchanged members, journal/apply/undo fault rollback,
reopen group undo, and coexistence of single/group history. Include keyboard
multi-selection, focus/preview/reload, refreshed filtering and exact group
targeting UI tests. Tests must verify outcomes, not mirror implementation.

Luna owns Task 27 acceptance, tracker and evidence derivatives. Implementation
Sol handles complex native-helper corrections within that acceptance contract;
independent Sol reviews the frozen helper and owns Task 28. Root
owns Task26, orchestration, branch integration and publication. Shared checkout:
no agent commits, pushes, switches or PR operations; coordinate file ownership.
Finish native generated-fixture evidence, privacy, green exact-head Core/Qt/
Tauri CI with actual Windows summaries, independent review and a draft PR.
Merging and updating the deployed outputs binary remain separate decisions.
