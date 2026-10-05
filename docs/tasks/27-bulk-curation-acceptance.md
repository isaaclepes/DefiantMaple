# Task 27: Bulk ratings/favorites acceptance and CI

Baseline: merged PR16/main `6f850c3fa65097a48406b50a19bab8a859bb756c`.
Branch: `codex/phase1a-bulk-curation`. Design: SDD v0.2 and Task26.

Luna owns this brief, the scoped acceptance record, requirement tracker and
generated acceptance derivatives. Sol owns implementation and finalized the
native helper; Luna owns the acceptance/tracker record and privacy derivative.
Independent Sol reviewed the frozen helper and public derivatives. Root alone
ran the visible native helper after an unlocked-session preflight. Do not edit
production implementation, old evidence or Task26/28. No commits, pushes,
switches, PR operations, or visible desktop probes by the acceptance agent.

## Acceptance contract

Verify stable-ID/revision multi-selection; exact effects preview; Keep versus
Unrated/False; changed/unchanged counts; selection/filter/control drift;
same-ID reload invalidating preview; 256-target bound; atomic apply and all-no-op
behavior; durable group selection/effects/undo after reopening; any-target
stale/ABA/content/path/metadata refusal; atomic fault rollback; and truthful
single/group history interaction. Never describe an unchanged member's later
single edit as partial group undo. Verify unchanged source files except
explicitly documented generated mutation/refusal scenarios.

Exercise genuine v5-to-v6 verified-backup migration retaining original rows,
IDs, metadata, collections/order and single-edit history. Test schema/refusal/
rollback independently; source integrity and SQLite integrity/foreign keys
are separate gates. Keep historical v4/v5 reports readable and live producers
strictly current-version; no completed cohort is rerun.

Map FR-META-004, FR-UX-003/010, scoped FR-TXN-007 and relevant FR-META-002/003
evidence without inventing acceptance of broader requirements. Retain all
104 FR, 15 NFR and 10 SEC IDs exactly once. Keep prior native/CI evidence and
failure records historical; no new user feedback has been supplied.

## Native and privacy evidence

Prepare generated-only temporary sources/catalog/backup/cache/XDG data and
record their actual isolation. Record source/helper hashes, precise host,
Python/Qt, display/backend/DPR, controls and keyboard focus, exact IDs internally,
expected/observed effects and refusals, integrity and cleanup. This host is
Nobara44 KDE Wayland, not plain Fedora or native Windows/macOS qualification.
Thumbnail work may be disabled for this metadata probe; do not claim throughput,
memory/performance budgets, compositor grouping or full assistive-technology
qualification from it. Root must verify unlocked session before owned visible
interaction; never weaken activation/focus gates or bypass the lock.

Preserve raw attempts/logs privately and create reviewed public derivatives
with hashes, fictional labels and app-only captures. Establish byte/hash
manifests before a preservation comparison; do not claim an unrecorded
before/after proof. Disclose failed attempts separately. Run public artifact
checks and explicit _check_json on new JSON, with manual path/ID/privacy audit.

## Completion

Report relevant commands/counts and actual current-head Core push+PR, Qt and
Tauri job results. Inspect actual Windows unittest totals and named skips,
distinguishing a cache message from a failed test/step/job. Inspect schema and
frozen package smokes/artifacts. No automatic diagnostic labels or cohorts.
Repeat passed tests/measurements only after changes or concrete failures.

Root publishes reviewed code/evidence as a draft PR. Final exact-head CI
receipts belong in its body to avoid documentation-only workflow churn. End
with explicit acceptance findings and limitations; merge remains separate.
