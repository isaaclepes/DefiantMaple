# Task 28: Independent bulk-curation integrity review

Baseline main: `6f850c3fa65097a48406b50a19bab8a859bb756c` (merged PR16).
Branch: `codex/phase1a-bulk-curation`. Task26 defines the authorized scope;
Task27 owns acceptance. Independent Sol is read-only for implementation and
acceptance files; record findings here and notify Root/owners. No commits,
pushes, switches, PR operations or visible probes.

Review authenticated schema-v6 migration/verified backup/rollback and retention
of v5 journal and old IDs/relationships. Audit frozen plans, Keep/clear typing,
duplicate/bounds/no-op checks, selection-range memory bounds, stable captured
IDs through model/filter/control drift and explicit same-ID reload/repreview.

Audit all-target preconditions under write serialization, fault-injected
apply/journal/undo rollback, durable group history and whole-group undo after
reopening. Review changed and unchanged members, metadata/source/content/path
ABA changes, later single edits and old eligible single undo. Batch entries must
not become single-asset undo records; no hidden multi-asset reversal or invented
no-op revisions. Check concurrency, immutable identities, truthful UI outcomes
and broader deferrals. Catalog undo does not revert files or detect unscanned
external bytes.

Check Tauri v2–v6 reader/schema compatibility, historical v4/v5 report support,
current-version producer/mixed-cohort refusal and unchanged archived evidence,
scanner/durability/publication gates. No new diagnostic cohort is authorized.

Independently verify raw native/public derivative correspondence, before/after
manifests, app-only generated PNG bytes, privacy and all129 tracker IDs. Keep
Nobara source-native, offscreen and hosted/frozen package evidence distinct.
Reproduce meaningful regression/failure cases; do not repeat broad passed
measurement suites without a change or unresolved concern.

Review exact published head, green relevant checks, actual Windows summaries,
current feedback and final PR description. Report explicit final verdict and
resolved findings. Finish with a reviewable draft PR; merge and deployed-output
replacement require a separate user decision.

## Initial independent design read — 2026-10-04

The first uncommitted core diff adds schema-v6 batch and item tables to the
catalog's declaration-authentication path and uses the existing verified backup
and writer-reserved migration sequence. Its batch API captures stable IDs and
revisions, recalculates every preview effect under the apply transaction,
records unchanged members without updating their revisions, and separates group
history from single-edit history. This is an initial code read, not an acceptance
verdict; implementation and tests are still in progress.

Focused review targets are the UI's pre-materialization selection bound and
selection-reset behavior; preview invalidation after control changes/reload;
all-member apply/undo refusal and rollback; older eligible single undo on an
unchanged member; schema-v6 Tauri support and historical-reader compatibility.
Native evidence and exact-head CI are pending. No frozen archive, scanner or
diagnostic experiment was rerun during this review.

## Provisional implementation review — before native acceptance

The stabilized source diff keeps batch history separate from single edits.
`apply_curation_batch` recalculates every captured effect under one reserved
writer transaction, including unchanged members; it updates only changed rows
and commits the header and ordered item records with those updates. Whole-group
undo loads the exact group, checks its complete membership plus resulting
revisions/values, and reverses changed rows with the undone marker in one
transaction. Missing/stale members, ABA catalog changes and injected journal or
undo faults therefore have refusal/rollback paths. Source-file changes not yet
observed by a scan remain outside the revision contract, as documented.

The reviewed UI checks selection ranges before calling `selectedIndexes`,
captures displayed IDs/revisions, clears selection on model reset, and restores
surviving IDs after curation refresh. Control changes/reload invalidate Apply;
the history-only dialog selects an exact group without requiring gallery
selection. A generated offscreen 256-target layout check showed the scrollable
target list and all action controls inside the 740×760 logical-pixel dialog;
this is not a native display or assistive-technology result. Initial concerns
about the long target label, stale preview on failed apply, keyboard history
focus and selection-capture exceptions were corrected in the source diff.

The schema v6 migration authenticates the new declarations and retains the
verified-backup/writer-reservation path. Focused tests cover a genuine v5
single-edit journal, failure rollback, and incomplete group refusal. The
comparison Tauri reader adds v6 to its explicit v2–v6 set while leaving old
rating defaults intact. The historical diagnostic reader adds v6 to its fixed
v4/v5 allowlist; live trial and pair producers still require the current
schema and mixed/unknown schemas refuse. These are compatibility reads, not
new measurements. Sol reported 225 Core and 50 Qt local tests passing;
independent review has not repeated those broad suites. Hosted exact-head CI
and native evidence remain publication gates.

## Native-helper static clearance — before Root's visible run

Independently reviewed the frozen generated-fixture helper at SHA-256
`c81d81628088134a8061da7595b119a227b7552b91bb501b1d9f4fee67943bc6`.
It seeds a genuine v5 catalog, compares all 13 legacy tables before migration,
in the verified backup, and after v6 migration, and separately checks SQLite
integrity and foreign keys. Disposable fault trials compare complete catalog
dump digests before and after injected apply and undo failures; the primary
catalog and generated source-byte manifest are checked independently. The
helper records source-code hashes at start and end, fixture bytes and mtimes,
and whether generated windows and their model connections close.

The visible path requires exposed, active windows and actual focused targets
for recorded QtTest keys. Its first selection is a click on fictional alpha,
Ctrl+Right to beta, and Ctrl+Space to select beta, guarded by actual card
geometry and exact selected IDs. It tests control-driven preview invalidation,
same-ID reload, stale apply refusal, no-op, mixed apply, reopen, exact history
choice and bounded Tab/Space whole-group undo. The second pair is selected
programmatically for the single-history coexistence test; the first pair alone
supports the keyboard multi-selection claim. Native host facts are captured
while the gallery is exposed. XDG config/data/cache are isolated under the
private output directory, while the Wayland runtime directory is preserved.
Generated app windows alone are captured; the helper contains no desktop
capture or user-media access. Success and failure stage receipts are written
atomically. `py_compile` and `git diff --check` passed. This is static
clearance for Root's run, not proof that the native interaction succeeds.

Against Root's baseline preservation manifest, SHA-256 still matches all 53
protected repository files and all 15 existing output files. Native raw
results, public derivatives, privacy and exact-head hosted CI remain to be
reviewed before a final verdict.

## Independent raw native review — before publication

Root's sole visible attempt returned 0 in 2.613 seconds after an unlocked
screen preflight. The command receipt's helper SHA matches the reviewed
`c81d816…43bc6` file, and its log SHA-256
`604be3ebe09056a3cccb06bdc3081cb04cdb5f8b629957320eee74bcb92233f3`
matches the retained command log. I independently recomputed the raw result
SHA-256 `3c9554278245da2b0ccf7cadf9b0fd5a8c704fe9d82417f976b5a0d6457ca4e7`
and complete 12-stage receipt SHA-256
`8ac278e8122d266eacf52937a366bd6b2bd5333eb812c725a073aa1b48306cfd`.
All 25 recorded QtTest key actions have visible, active, exposed windows and
focused descendants; the gallery and reopened gallery activation gates passed.

The v5 backup and migrated catalog retain the same 13-table legacy snapshot
digest and collection order. Independently reading the retained backup shows
schema 5, integrity `ok` and zero foreign-key violations; the final catalog
shows schema 6 with the same integrity results. The disposable apply/undo
fault trial records full-catalog rollback and is removed. The first mixed
group was undone after reopen; the second mixed group is now ineligible after
the older eligible beta single edit was explicitly undone, while delta's
changed value remains. The final SQLite rows agree. The four fictional PNG
sources retain their before/after SHA-256, length and mtime; all ten monitored
source-code hashes match both run receipts and the current checkout. Both
gallery closes were accepted and their model connections closed.

The raw captures are the generated bulk preview and exact group-history
dialogs. Visual inspection found their controls visible and no desktop or
personal content. The host receipt identifies Nobara Linux 44 KDE Plasma on
Wayland, PySide6/Qt 6.11.2 and DPR 1.0; this is a source-native metadata
check with thumbnails disabled, not a frozen-package, Windows/macOS, human
accessibility or performance qualification. Public evidence filtering and
exact-head CI remain publication/completion gates.

## Prepublication derivative and scope verdict

The reviewed [public receipt](../evidence/bulk-curation/attempt1/acceptance.json)
has SHA-256 `9ef0008dcaa7985a59c5baae69831fc00690b30ba185ea90383fc2c2ae2467fd`;
the [sole-attempt history](../evidence/bulk-curation/attempt-history.json) has
SHA-256 `5d14467834c3dded6016867299b8d9ffd2a4cf2926e0ed6cf5b8cfd836e5a624`.
Their raw, public, helper, command receipt, command log and capture hashes were
independently recomputed and cross-checked. The two public captures are
byte-identical to the generated app-only raw PNGs. The public JSON removes
temporary roots, private paths, executable paths, raw per-run UUIDs and screen
names/positions; a path/UUID scan found none. It distinguishes no user-source
writes from generated fixture creation and records that those fixtures were
unchanged after the initial manifest. Native outcomes, migration row counts
and collection order, fault/refusal facts, cleanup and platform qualifiers
match the raw receipt. The requirement tracker still has 129 unique IDs:
104 FR, 15 NFR and 10 SEC. Mapped rows remain Partial for their broader scope.

There is no blocking source, native or public-evidence finding for publishing
this reviewed tree as a **draft**. The verdict is deliberately time-scoped:
exact published-head Core/Qt/Tauri checks, actual Windows summaries, package
smokes and PR feedback still require review after publication. This record
does not authorize a merge or output-binary replacement.
