# Bulk ratings and favorites acceptance

## Scope and status

This record covers the captured-target bulk ratings/favorites increment in
[Task 26](tasks/26-bulk-curation-implementation.md). It does not claim
acceptance of broader metadata synchronization, full accessibility, source
mutation/undo, or a performance budget. The branch is based on merged PR 16
`6f850c3fa65097a48406b50a19bab8a859bb756c`; implementation, generated-fixture
acceptance, and hosted exact-head CI are separate evidence classes.

Sol's final local summaries report 225 Core tests and 50 Qt tests passing, plus
the Node grid check passing; those tool outputs were not retained as standalone
log files. Native attempt 1 passed on Nobara 44 KDE Wayland and its sanitized
derivative is reviewed below. Hosted Core, Qt, and Tauri checks on the eventual
published head remain pending.

## Acceptance coverage

The local generated-catalog tests cover frozen captured plans; Keep, Unrated,
and rating/favorite typing; empty, duplicate, missing, forged, and over-limit
targets; no-op behavior; revision-preserving unchanged batch members; atomic
apply and undo fault rollback; competing writers; content/path/metadata ABA;
exact-group history; eligible single-edit undo on an unchanged member; and
v5-to-v6 migration with old single-edit history, verified backup, and rollback
on injected migration failure. Relevant tests are in
[test_bulk_curation.py](../tests/test_bulk_curation.py) and
[test_catalog_migration.py](../tests/test_catalog_migration.py).

The Qt regression tests cover keyboard multi-selection, captured revisions,
control-change preview invalidation, filter/model-reset selection clearing,
same-ID reload, stale apply refusal, no-op and storage failures, durable group
history without gallery selection, exact group selection, keyboard/focus for
whole-group undo, the 256-target selection bound, and single/group history
coexistence. See
[test_bulk_curation_ui.py](../prototypes/qt/tests/test_bulk_curation_ui.py).

The reviewed native helper is
[bulk_curation_native_acceptance.py](../prototypes/qt/bulk_curation_native_acceptance.py).
Root runs it only after confirming the visible session is unlocked. It creates
an actual v5 catalog with generated sources and existing curation history,
migrates to v6, compares the old-row snapshot with both verified backup and
migrated catalog, then exercises keyboard multi-selection, preview/apply,
stale-target refusal and same-ID reload, no-op behavior, group undo after
reopening, and unchanged-member single-undo interaction. It records byte
manifests for generated media before and after and requires equality. It writes
only to that generated catalog; thumbnails are disabled. App-only captures,
host/runtime/display data, focus gates, SQLite integrity and foreign keys, and
cleanup are recorded.

### Native attempt 1

The helper passed once (exit 0; 2.613 seconds) on Nobara Linux 44 KDE Plasma
Wayland, x86-64, using Python 3.14.7, PySide6/Qt 6.11.2, the Wayland platform
plugin, and device-pixel ratio 1.0. Qt reported 2560×1080 and 1920×1080
displays. Root's preflight found the session unlocked. This was a source-Python
run, not frozen-package qualification.

The generated v5 catalog migrated to v6. Its legacy snapshot digest matched
both the verified backup and migrated catalog (`ec21cd83…fa8cff3`); the backup
and migrated catalog passed `integrity_check` with zero foreign-key violations.
The snapshot retained four asset rows, four provenance rows, four source-entry
rows, taxonomy and assignments, an ordered collection, and one existing
single-edit journal row. Collection order remained gamma, alpha, delta, beta.
The four generated-media SHA-256/size manifests matched before and after; all
ten recorded helper/source/test code digests still matched after cleanup. The
helper created the four fictional PNGs before the initial manifest; catalog
migration and curation did not write those media. SHA-256, sizes, and recorded
nanosecond mtimes matched after the run. The helper isolated XDG config/data/
cache and preserved the existing Wayland runtime directory.

Native keyboard events selected fictional alpha then beta with Ctrl+Right and
Ctrl+Space. The active dialog retained its two captured IDs when a filter reset
cleared gallery selection. Keep/Keep produced no group and no revision changes;
choice changes invalidated Apply. A stale alpha revision made Apply refuse the
entire group, leaving both members and group history unchanged. Reload kept the
same IDs, updated captured revisions, and required a new preview. The accepted
preview applied one changed and one unchanged member; the unchanged member's
revision did not advance. After closing and reopening the gallery, the exact
recorded group and both effects appeared in history, and keyboard focus reached
the explicit whole-group Undo. Undo restored the changed member and left the
unchanged member unchanged.

A second generated group checked coexistence with migrated single-edit history.
Its unchanged beta member retained an eligible explicit single undo; using that
single undo advanced beta's revision and invalidated the whole group, while
delta's change remained in place. Separate generated-catalog fault injection
proved all-member apply and undo rollback. Empty, duplicate, and over-limit
plans were refused. The final catalog passed integrity and foreign-key checks,
generated media were byte-identical, and the app closed with its model
connection closed. Thumbnail work was disabled; the run makes no performance,
human-accessibility, compositor-timing, frozen-binary, Windows, macOS, or
cross-distribution claim.

The private raw receipt remains outside the checkout at
`work/bulk-curation-native-attempt1/bulk-curation-native-acceptance.json`
(SHA-256 `3c9554278245da2b0ccf7cadf9b0fd5a8c704fe9d82417f976b5a0d6457ca4e7`);
the wrapper command log SHA-256 is
`604be3ebe09056a3cccb06bdc3081cb04cdb5f8b629957320eee74bcb92233f3`. The
reviewed privacy-filtered [attempt history](evidence/bulk-curation/attempt-history.json)
preserves this sole outcome (SHA-256 `5d14467834c3dded6016867299b8d9ffd2a4cf2926e0ed6cf5b8cfd836e5a624`). The [public receipt](evidence/bulk-curation/attempt1/acceptance.json)
SHA-256 is `9ef0008dcaa7985a59c5baae69831fc00690b30ba185ea90383fc2c2ae2467fd`.
The unchanged app-only [bulk preview capture](evidence/bulk-curation/attempt1/generated-bulk-preview-dialog.png)
and [reopened group-history capture](evidence/bulk-curation/attempt1/generated-bulk-group-history.png)
have SHA-256 `9dd727b13356c8c66431bede96564fbe2557e04903de77cca9c9eed547749f36`
and `28af8b2565717fadc9ce19dae2a467b0f80f84893beb69c54ff1fc26680dd180`.
The derivative omits the temporary root and raw per-run identifiers; images
show fictional names and a generated group identifier only. No failed native
attempt occurred for this task.

## Requirement mapping and limits

The [129-ID tracker](phase1-requirements-tracker.md) remains the canonical
traceability source and retains 104 FR, 15 NFR, and 10 SEC IDs exactly once.
FR-META-004 and the related FR-UX-003/010 and FR-TXN-007 rows remain Partial
because this increment accepts only bounded ratings/favorites group edits; it
does not accept richer taxonomy/metadata bulk operations, configurable
shortcuts, general assistive-technology behavior, or filesystem undo. Native
and hosted gates determine whether the scoped behavior is evidenced, not
whether those wider requirements are complete. FR-META-002/003 remain Partial
because this increment does not accept their wider metadata and synchronization
requirements. The 256-target bound is an explicit operation limit, not an
adopted responsiveness or memory budget.

Native source-run evidence from this host describes Nobara 44 KDE Wayland
only. It is distinct from offscreen Qt tests, hosted Windows/macOS CI, and frozen
package smoke tests. It cannot establish human assistive-technology coverage,
compositor presentation timing, Windows/macOS native qualification, or
cross-distribution release support. Source files must remain unchanged during
the probe, and generated-source before/after manifests must match exactly.

## Hosted CI

Exact-head Core push and PR results, Qt and Tauri results, actual Windows
unittest totals, and named skips remain pending. Treat cache messages separately
from final step/job conclusions and report skips separately from passes. Root
records final run links and receipts in the draft PR body so hosted results do
not require a documentation-only follow-up change.
