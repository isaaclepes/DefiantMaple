# Task 39 — gallery filter acceptance and traceability

Active Goal, 12 October 2026. Owner: Luna; Root releases the visible native
gate and reviews publication evidence.
Read [Task38](38-gallery-filters-implementation.md), SDD §§11, 18–22 and the
129-row tracker. Task38 proposes one canonical assigned tag and one canonical
assigned entity, composed with existing basic facets. Checkpoint 1 cleared the
frozen query/read design on 8 October 2026 at SHA256
`2d8d25c2c9206608422cc5c48419dffb1ee57d1eeee2d38b57e8f8802a24b518`.
Dormant Phase A gateway implementation and its tests received independent
source/test clearance and passed attempt 13, a bounded 17/17 generated-test
run in 0.702 seconds. This is infrastructure evidence only; no filter behavior,
GUI activation or native acceptance is claimed.

The B2b integration checkpoint is now cleared for its scoped stage: the frozen
generated GalleryWindow test pair passed 26/26, and the reviewed existing-Qt
timing quartet passed 28/28 in attempt 13. The generated-test receipt is
attempt 23 (app SHA-256
`8831de0699846534c85b7f18a2cac222869bfd091614f94238459b84aff6f83c`, UI test
SHA-256 `e75a603b55a4a23ab52f2803799be1db4eaf789af46546328b9adfad2a61db6b`);
the exact receipts are preserved later in this task. This clears the reviewed
B2b integration gate only. Phase C controls passed their reviewed 48/48
focused gate and the local full Qt/Core discoveries are recorded below. The
generated-fixture/native helper passed 20/20 on local Linux Wayland and is
recorded below. Root reviewed the five path-free control captures. The reviewed local Linux
one-file build and its frozen smoke checks have now passed; final publication
privacy checks, hosted cross-platform CI and complete filter-slice acceptance
remain pending.

Current Phase C checkpoint, 12 October 2026: the reviewed control-focused
suite passed 48/48 in attempt 17 (7.481 seconds; app SHA-256
`d4c09ab5e9bd615c7188f1009a0c7e6f563a72cdc4b63d569f446522a4281881`, generated
UI test SHA-256 `d280a4218062a3c292f6c084796864dbf21b45e30ce3990b9d6e3cebc322ae2b`,
log SHA-256 `a13da345fd1877551ae8d12aceaf3dc63b1472888e58cd63fb70ee1698050153`).
The same frozen pair passed the one-case metadata compatibility check, and the
full local Qt discovery then passed 170/170 tests in 40.321 seconds under
Python 3.14.7/PySide6 6.11.2, offscreen, with local warnings-as-errors. Its
log SHA-256 is `9b7777032a6e3753611ed1d363043c5fed6dba5688989a9ec517c3d31326d7e3`;
three ignored `Popen.__del__` ResourceWarnings came from the intentional
external-editor handoff probes. No uncaught Qt callback traceback occurred.

The full Core discovery was run twice against the same stable 86 declared
source/test inputs. Attempt 16 used local `-W error`: 273 tests passed, while
`test_scan_exit_probe.ProbeTests.test_original_commit_rollback_and_custom_factory`
raised a `DeprecationWarning` promoted to an error because Python 3.14 warns
when `sqlite3.connect()` receives more than one positional argument. Its exit
was 1; log SHA-256 is
`d5bef5b97288fc768866543ddbe19b60153f33f008d054130213e692e3ee62d7`, receipt
SHA-256 `7ed856ba73fd82a1b95931fdf5872cdf4bc4452df49359a0ca4b0f44f1019e1a`.
Attempt 17 used the repository workflow warning mode, with no warning override,
and passed all 274 Core tests in 52.890 seconds, exit 0, no skips or errors;
log SHA-256 is `a85083b4d7032d7f1841cde2d1538a355d1d642eb3c7fb92d7014f3bf7ce5fb6`,
receipt SHA-256 `9af8b32fad891c0ec2a287d62dda0029a63ba3c8d0a95f10cadda5d6ab3b270f`.
The workflow-mode receipt covers 87 declared inputs, including both harness
versions; all before/after hashes remained stable. The hosted workflow's Core
command omits `-W error`, so attempt 17 is the matching local command mode.
The focused and full-suite results establish test coverage on this local
Python/Linux environment only. The generated native attempt below adds one
Linux Wayland GUI observation, not another-platform qualification. The frozen local Linux package build passed; hosted Windows/macOS CI and full
filter-slice acceptance remain pending. Keep mapped requirement rows Partial
and `FR-RECOVERY-001`–`005` Not Started. Raw logs and receipts remain outside
the repository in the private wrapper.

The frozen package/build attempt 1 completed on Linux x86_64 with Python
3.14.7 and Qt 6.11.2. The one-file artifact was 50,933,248 bytes; build time
was 305.534 seconds. Seven frozen smokes passed, including gallery-filter and
gallery-worker coverage. The offscreen 100,000-row placeholder benchmark
reported 1,030 ms startup, 140 MB first-grid RSS, 149 MB after-scroll RSS,
35 ms median and 59 ms p95 query publication, and zero of 48,133 scroll steps
over 16.7 ms during the 60-second traversal with a background CPU task active.
These are single local measurements: placeholder cells avoid image decode and
disk thumbnail I/O; offscreen runs do not measure compositor presentation;
startup caches were uncontrolled. This evidence does not establish the SDD's
real-preview performance budgets, memory guarantees, other-platform behavior,
or hosted CI. The private metrics receipt and binary are not included in public
evidence.

The first released visible generated-fixture attempt ran on the unlocked local
Wayland desktop against the prepared generated catalog. It stopped during the
first alias-picker step before recording a case or saving captures: the helper
expected the label `Parent`, but the generated fixture's canonical tag is
named lowercase `parent` and `Night Study` is its alias. The tag picker displays
the canonical name, so this is a helper expectation mismatch rather than a
filter result. Runtime, helper, fixture database and fixture receipt hashes
were stable; the catalog was not changed. The immutable private run log SHA-256
is `e863b57e7771d2a911777aaa4d9b61a8bd9bfbad77c230372fb37745e4c445ea`; the
private execution receipt SHA-256 is
`5ef2c11921a353431cb05f4bd741f77a00c970e6fe25a20e4568a3468b418cc6`. This
attempt gives no visible native acceptance; retain it as a diagnostic.

Native attempt 2 passed all 20 declared generated GUI cases after correcting
only those two helper label expectations. It ran on local Linux Wayland, exited
0 in 5.183 seconds, and reported no source-path I/O during bounded gallery,
query or picker operations. Catalog logical/physical state, source placeholders
and cache matched before and after; integrity was `ok`, foreign-key check was
empty, and the gateway finished closing. Nine declared runtime/fixture inputs
were hash-stable. The private log SHA-256 is
`74ca46bacdff0e5676a1b84d05013cc32c616f18ce42de18cd4e13a6a87d4659`, the
private execution receipt SHA-256 is
`f7bd55255f752f2c8a0dcffa2b0922d8b55e9c81c95d7cbb7fb06f8d8d781857`, and the
closed public candidate SHA-256 is
`0bd5d29a225d69e3c55fb3bd3806c2776a8ece2cef1ffc3c308614c29e24f8c1`. The
helper's direct JSON and repository privacy checks passed. Root reviewed the
five path-free controls; the gallery widget capture remains private because it
contains generated filename/path captions. The path-free controls and result
candidate are available at [source picker](../evidence/gallery-filters/source-picker.png),
[tag picker](../evidence/gallery-filters/tag-picker.png),
[entity picker](../evidence/gallery-filters/entity-picker.png), [Apply](../evidence/gallery-filters/apply.png),
[Clear](../evidence/gallery-filters/clear.png), and
[native result JSON](../evidence/gallery-filters/native-linux.json). Final
publication privacy validation remains pending. The attempt does not measure
memory, performance or thumbnail behavior, and makes no other-OS claim.
Historical Phase A attempt 13 used Python 3.14.7 and PySide6 6.11.2. Its
gateway SHA-256 is
`abf8392d427611c2629f5b53a995df82d196b0c39f126072823802152497845c`, its test
SHA-256 is `51cd4940ee6a49df8c1fc752f6a1f2bbda322c3a63c7b0a54f21ad08cba5e784`,
and its log SHA-256 is
`aafa600aa1fdaa9e07d4a820d527dbcccb5420ced23b56b1af31abdc928a209d`.

## Owned files and evidence stages

Own this task, [`docs/gallery-filters-acceptance.md`](../gallery-filters-acceptance.md),
and [`docs/phase1-requirements-tracker.md`](../phase1-requirements-tracker.md).
The acceptance protocol is staged; preserve every existing
requirement ID and status; the bounded gate does not complete FR-UX-003/005/
006/010, linked NFRs, or Phase 1a. Keep `FR-RECOVERY-001`–`005` Not Started.

Root owns implementation and stage transitions. The cleared Phase A pair
remains the dormant serial gateway in `prototypes/qt/gallery_filters.py` plus
focused tests; its 17/17 pass is evidence for that exact historical pair, not
for later gateway revisions or GUI behavior. B1's dormant Core query module
and focused PySide-free tests are now independently cleared and passed the
bounded attempt 7 run: 11/11 in 1.988 seconds under Python 3.14.7. The frozen
query/test hashes are `d776645435d468e9972ac046ebbfe7384519c0541b31ea4a97b58882b0e29b58`
and `fff9e53e1fae259b53f4950196124084de7acb42d52859cb9c6e7e17c2d50909`;
the log SHA-256 is `7a0a7abfb2ee58f03d3b713596c9f758824e6a341778c06b803eac9ea2245159`.
This is bounded query correctness/output evidence only. The helper was dormant
at this B1 checkpoint; B2b later integrated it into GalleryWindow. Earlier
attempts remain diagnostic; attempt
6's Qt context import was removed to keep Core tests PySide-free. The private
mechanical audit is in the wrapper; raw logs remain outside the repository.

The independently reviewed B2a gateway pair passed 20/20 focused checks in
0.992 seconds (1.166 seconds wall) under Python 3.14.7. Its gateway SHA-256 is
`87fe023f2210ed7ca164bb7f0a3c386ce8fd166ceb7a41df706a57358582116a`; the new
actual-context integration test SHA-256 is
`01bd254107eb2c1b6c34dd99db4ed2cd5a3bcbe89e91216115cb48d61d687ac6`, and the
log SHA-256 is `f924d105e14b476f28e0c6129c81d828e573106d2f39e0bdaba03e7895ceca23`.
The bounded pass covers actual 256-row reply transport, cap refusals, atomic
replacement identity refusal/reopen, portable identity refusal and affected
gateway regressions; it does not accept GUI integration. The app stayed
unchanged and unwired. The private mechanical audit and raw log remain in the
wrapper, outside the repository.

Root released and independently cleared B2b integration scope: closed operation registry
`prototypes/qt/gallery_operations.py`, complete inventoried GalleryWindow
catalog read/write migration in `prototypes/qt/app.py`, focused test
`prototypes/qt/tests/test_gallery_filters_ui.py`, and optional bounded-wait
helper `prototypes/qt/tests/gallery_wait.py`. Its scoped gates passed 26/26
generated tests and the separately reviewed 28/28 existing-Qt timing quartet
(attempt 13). Phase C tag/entity/source draft controls passed their reviewed
48/48 focused suite; the full Qt/Core local suites and generated native attempt
are recorded above. Final publication privacy validation, hosted cross-platform
CI and complete filter-slice acceptance remain pending; the local package build
and its frozen smokes passed as recorded above. The ten
existing Qt test files in the private timing inventory are
conditional exceptions only: change a test only where a demonstrated
asynchronous observation needs bounded named-generation completion or an
explicit synchronous mode, preserving its exact substantive assertions. Root
owns implementation reviews and filter implementation. This task owns the
generated acceptance gates and records staged evidence, not a claim that the
complete filter requirements are implemented.

The predeclared B2b gates instrument every design §56 GalleryWindow catalog
operation and its worker/GUI-thread boundary. Startup catalog SQL is checked
separately for off-GUI execution. The existing startup
`assert_outside_sources` validation legitimately resolves configured roots
and remains protected as a separate legacy operation. Zero source-path
open/stat/resolve/list/scandir counters apply only to bounded gallery/query
and new picker operations after startup containment and legacy source-list/
health work settle; fixture setup and intentional thumbnail/viewer I/O are
bracketed separately. Focused tests and the later helper use synthetic
fixtures, preserve raw IDs/paths privately, parse new public JSON directly,
run the repository privacy checker, and keep native captures to reviewed
app-only canvas/control captures. Record actual count, first-page and
refreshed-generation completion before timing. These gates do not claim broad
responsiveness or keyboard-only/AT acceptance. See the B2b instrumentation
section of the protocol for the exact checks.

Use a generated schema-6 catalog and generated placeholder paths/media only.
Assert exact stable-ID results, alias-to-canonical resolution, entity category
disambiguation, AND composition, no implicit descendants, no duplicate rows,
literal escaped path behavior, and valid empty versus stale/invalid/error/
missing states. Preserve deterministic collection order and clear selection
without row-zero retargeting. Checkpoint 1 design clearance allowed Phase A;
its bounded pass does not clear B2b GUI integration or filter behavior. Row
count, page, stable-ID rank and detail must share the cleared design's coherent
predicate/snapshot. Do not query by scanning/statting source media.

Attempt 13 exercised the Phase A infrastructure on a generated on-disk
rollback-journal catalog: a gateway SHARED read held while a
`curation.set_curation` write queued, with a Qt event-loop heartbeat advancing;
a separate direct-SQL external writer checked the rollback lock and
next-snapshot change. The tests also cover queued gallery-read invalidation,
mutation priority, and gateway ownership through dispatched-write completion.
This does not exercise GalleryWindow target disabling or the metadata,
collection and source service APIs. Active opaque Core writes are not
cancelable, bounded by the cooperative two-second read deadline, or
size-bounded. Existing Core service lock/wait behavior remains a separately
qualified legacy limitation. B1's query helper is accepted only for its
focused reviewed scope; B2b's separately cleared GUI integration repeats
contention coverage against the integrated app, verifies the exact Core
operation result/refusal, fresh generation and actual owned shutdown, and show
that new query/read generations invalidate older page/rank/detail replies and
mutation intent stales targets before dispatch. A heartbeat alone proves only
event-loop progress, not whole-app responsiveness.

The visible protocol uses real filter controls and declared Qt key actions on
the generated fixture. Record which focus was established programmatically;
this is not human keyboard-only or AT qualification. Snapshot catalog logical
and physical state, generated source-media bytes, source rows, taxonomy,
collection order and relevant cache entries before/after read-only stages.
Bracket any deliberate generated review-key mutation as its own expected
catalog delta. Root releases the reviewed helper for Luna's bounded native run
after independent review.

Keep private raw rows/UUIDs/paths/full captures out of public derivatives.
Use direct reviewed app-only generated captures, directly validate every new
public JSON and run the repository checker over the final staged publication
set. Retain failed attempts as diagnostics; do not overwrite or rerun a green
attempt to improve its appearance.


## B2b existing-Qt timing diagnostics (attempts 7 and 8)

Two immutable focused runs covered the four existing Qt modules whose
synchronous observations were migrated to named bounded waits. Both are
historical diagnostics; neither is a B2b acceptance pass. Their logs and
manifests are private wrapper evidence, not public artifacts.

- Luna attempt 7 ran the four modules under Python 3.14.7/PySide6 6.11.2,
offscreen, warnings-as-errors. It ran 28 tests in 26.264 seconds and failed
11. The immutable log SHA-256 is
`11e838a287732a8cfc01fca5a18edf780ed8acad86db54bd9e1841db7c79fa04`. It
exposed asynchronous curation/collection readiness and collection
rank-to-page race-test issues. It predates the subsequent test corrections
and collection/runtime changes; do not interpret the failures as current
runtime results.
- Luna attempt 8 ran the same four modules with the exact command and
source-stability receipt recorded in the private manifest. It ran 28 tests in
30.334 seconds: 21 passed and 7 failed (curation 5/6, bulk curation 4/8,
collections 7/9, Qt prototype 5/5). Runtime was Python 3.14.7, PySide6 6.11.2,
offscreen, warnings-as-errors. The app SHA-256 was
`5e58d626a3dc2329dc288e81e6de7491d1a46bddae91bd62d7154d8c1f5eeea8`; the
generated UI test was `f78115f0c9f16a9ea6892349bd2432f510d4184e6158aee8ec95f8aca906fc12`.
The private manifest SHA-256 is
`b3dbb163c4c3c419789bd5eadfa2795e4f091342b87994d9b5f0cada3ed1bb7a`; the
raw log SHA-256 is
`acd7786f5df8d9284548b656f6651c0c9e32de70c16ad1940a6c4f5fd82bb26c`.

Attempt 8's seven failed tests were:

1. Curation typed-facet/collection-order composition observed a collection
   created directly in Core after the window's initial list snapshot; the
   test needs an explicit collection-list refresh/readiness precondition.
2. Bulk displayed-revision apply timed out at completion. The fixture's
   successful terminal feedback is `Group saved to catalog`; the test must
   observe that completion while retaining the preview effect, DB, revision,
   focus and exact identity assertions.
3. Bulk unchanged-member history did not publish the expected second group;
   the pending-history-list versus later user selection boundary remains a
   runtime compatibility fix. Preserve the user's newer group choice and
   whole-group undo assertions.
4. Bulk storage-failure recovery did not preserve the expected loaded
   multi-selection. The narrow runtime restoration fix and its generated
   regression remain required; preserve exact selected IDs and DB refusal
   assertions.
5. Bulk reopened history did not reach the expected whole-group member
   details. Keep exact group/member identity and eligibility assertions; do
   not infer success from the opener returning synchronously.
6. Empty-collection deletion did not finish publishing the expected cleared
   view. Await list/generation/control readiness and keep the original delete
   confirmation and DB/list assertions.
7. Paged collection move did not reach the expected Core result. The
   generated test must establish the uncached neighbor page and keep the
   unbounded-fetch guard active through completion; retain exact ordered IDs,
   row boundary and DB assertions.

These outcomes include asynchronous test precondition/completion gaps and
runtime compatibility issues; attempt 8 alone does not distinguish every
remaining timeout. No assertion was waived. The current retry is held until
Sol supplies a frozen runtime and root/reviewer releases the coordinated run.
Retain attempts 7 and 8 as-is, then save each later attempt under a unique
name with pre/post source hashes, exact command/runtime, result totals and
full log hash. No broad-suite, native, package, privacy-publication or
filter-control acceptance is implied. Keep the full filter slice Partial.


### Attempt 9 — same four focused modules on replacement freeze

Root released the same 28-test retry against Sol's replacement source freeze.
All runtime and four test-file hashes were verified unchanged before/after.
The exact command, Python 3.14.7/PySide6/Qt 6.11.2, offscreen environment,
11.738-second unittest duration, 12.172-second shell wall time, source hashes,
and individual outcomes are preserved in the private manifest
`luna-attempt9-four-qt-modules.json` (SHA-256
`7910d75613ee102aa29ec3bcbdc9eb9b744d728cb5bcac853cb7ab34210eec4f`) and raw
log `luna-attempt9-four-qt-modules.log` (SHA-256
`094de74807c54e2f1c79a470c74b143cdaf339b3fb569b7090e0864cd104211e`).
The run exited 1: 24 passed, 3 failed, 1 errored. Curation passed 6/6 and
QtPrototype passed 5/5. Bulk curation passed 5/8, with two failures and one
error; collections passed 8/9.

The remaining diagnostics are exact and preserve original requirements:

- `test_displayed_revision_is_captured_and_explicit_reload_keeps_ids_choices`
  errored because `_selected_asset()` was `None` where the test expects the
  still-visible `gamma` identity after explicit reload.
- `test_noop_and_storage_failure_are_truthful_preserve_controls_and_stable_selection`
  failed because the expected loaded `alpha`/`beta` selection was empty after
  storage failure handling.
- `test_reopen_history_without_selection_exact_group_undo_and_single_dialog_exclusion`
  failed to publish the reopened whole-group member details/control within its
  bounded wait (generation 3, three gallery rows, current asset alpha).
- `test_paging_moves_across_boundary_without_full_member_fetch`
  failed to observe the expected move-up Core result and refreshed generation
  within the bounded wait (generation 6, 514 gallery rows, selected row 255).

No selection/history/order/database assertion was weakened. These results do
not establish whether each remaining failure is a runtime defect or a test
observation gap; retain them as diagnostics for review. Do not retry until a
specific correction is reviewed and a new frozen source/test set is released.
Attempt 9 does not qualify B2b, broad Qt/Core, native, package, privacy
publication or tag/entity filter acceptance. Keep all mapped filter rows
Partial.


Attempt 10 used the same four modules on the source-stable attempt 22 freeze:
27/28 passed (curation 6/6, bulk 7/8, collections 9/9, QtPrototype 5/5),
with one history-test failure and no errors. The private manifest SHA-256 is
`4c60a18d97cddef31decfc82eeda88bce3763acebe3eb7dfabc7543ceab2b2bb`; raw
log SHA-256 is `754a2ea03e331a18956395a5632cbdf7986ff285bf9ae0fabae38ae60cfb0358`.
The failure occurs at the original assertion that a single-asset editor is
refused after explicit gallery selection clear. A standalone PySide6 6.11.2
check confirmed `selectionModel().clear()` clears current index when one is
present. Review traced this failing sequence to a pending bulk selection restore
that may run after the bulk mutation has already reset the model; when clear
then sees an already blank model, it emits no selection change and cannot
advance the user-selection epoch. Root released a narrow app-owned explicit
clear-intent fix and held-rank regression. The test's original clear timing and
assertion remain unchanged. This is still diagnostic, not acceptance; retry is
held until the replacement source pair and tests are frozen and reviewed.


### Attempt 11 — final released same-28 checkpoint

Root released one same-command focused checkpoint on the source-stable attempt
23 runtime/UI pair after reviewer clearance. The immutable private manifest
SHA-256 is
`3904a4f78fb8b3201d96394f566235f1b28f28d56be5195254157181ac1f2247`; raw
log SHA-256 is `49a7ac5330e07c6412a85f1c383130e21862a94d7fa8ce21f6a4ce200e905979`.
The run used Python 3.14.7/PySide6 6.11.2/Qt 6.11.2, offscreen and
warnings-as-errors; it completed 28 tests in 1.772 seconds (2.190 seconds
shell wall), exit 1. Curation passed 6/6, bulk curation 7/8, collections 9/9,
and QtPrototype 5/5: 27 passed and one errored. The exact command and all
before/after source/helper/four-test hashes are in the manifest.

The only error is the existing history test's post-undo assertion: after
selecting gamma and receiving the successful whole-group undo feedback,
`_selected_asset()` was still `None` when the test immediately asserted gamma's
identity. This checkpoint did not wait for the fresh generation and selected
asset/detail restoration after undo. The assertion remains intact. No further
fix or retry was released under the user's requested pause. This limited
checkpoint does not accept B2b, the native/package gates, other six timing
modules, broad Core/Qt suites, or tag/entity filter behavior. Keep every mapped
filter requirement Partial and recovery rows Not Started.


### Attempt 12 — one released checkpoint after gamma readiness correction

On the reviewed, source-stable attempt 23 pair, the one authorized same-28
run exited 1: 27 passed and one error in 1.961 seconds (2.487 seconds shell
wall). Curation passed 6/6, bulk curation 7/8, collections 9/9 and QtPrototype
5/5. Python was 3.14.7 with PySide6/Qt 6.11.2, offscreen and
warnings-as-errors. Exact command, all before/after source/helper/test hashes,
and result are in the private manifest (SHA-256
`b080f9c19c833e43d2e44da8d194d14f743d0512d5ed2ece2db3d60c53eac392`); raw log
SHA-256 is `ef7f8c3330aa86d8a18f8236c1a491fba992e165c5fb6da3bb3b55de89c164ee`.

The added bounded post-undo generation and gamma selected-detail wait
resolved the prior immediate gamma assertion. The same history test then
selected alpha and immediately called `edit_curation()`; it returned None
before alpha detail became actionable, so its existing `single.undo_button`
assertion raised AttributeError. This is the only remaining attempt-12 error;
no callback exception or other module failure was observed. The approved
checkpoint permits no repeat or further edit. Record this as diagnostic, keep
history readiness pending, and do not infer B2b/native/package/full-suite or
tag/entity filter acceptance. All filter requirements remain Partial;
recovery remains Not Started.


### Attempt 13 — focused existing-Qt quartet passed

After the final alpha detail/history wait was independently reviewed, Root
released one same-28 run on the unchanged attempt 23 app/UI pair. All 28
tests passed: curation 6/6, bulk curation 8/8, collections 9/9 and QtPrototype
5/5. Runtime was Python 3.14.7 with PySide6/Qt 6.11.2, offscreen and
warnings-as-errors; unittest duration was 1.873 seconds (tool wall 2.344
seconds), exit 0. The immutable private manifest SHA-256 is
`7607c6162bcb8a2a622d710cd6d0a3cd166e955f65befbd238aa668da616ec64`;
raw log SHA-256 is
`a8cc9d213a178855f4c041b1d2ac0a9c8799abdd70faa0f5cf345671ac305abc`.
The manifest contains exact command, environment, all before/after runtime,
helper and four test hashes, and outcome. No standalone Qt callback exception
appeared in the captured log.

This closes only the one focused four-module timing checkpoint plus the
separately recorded generated B2b UI focused gate. It does not run the other
six legacy Qt timing modules or the full Qt/Core suites, and does not establish
visible filter-control/native/package/privacy/current-head-CI acceptance or
full tag/entity filter behavior. No unchanged rerun is authorized. Preserve
all broader requirements as Partial and recovery requirements as Not Started.

## Prior comparison increment closure

PR20's reviewed head was `966c9a46e43ed249436b76148457091aed517c6d` with tree
`e872140902d6a78ea856763c3948b7b5835da716`. It passed 27/27 pre-merge checks
(Core push 12, Core PR 12, Qt PR 3). It merged as
`0af8ba5108af4727679e76bc60e6a71918ef5994` with the same tree and parents
`0f7082a2e01afccfdf4b81ec2145dc8a6572287e` then the reviewed PR20 head.
Attempt 2 comparison-native evidence is accepted for its bounded generated
flow; attempt 1 remains diagnostic for the fixture geometry/resolution gap.
The PR20 Tauri workflow was filtered out, so prior PR19 Tauri evidence is
baseline reuse only, never described as a PR20 Tauri pass.

The merge-main Core push run
[37697431239](https://github.com/isaaclepes/DefiantMaple/actions/runs/37697431239)
has now been audited: all 12 jobs succeeded. Windows Python 3.11 and 3.13
each ran 263 tests with three named platform/host skips, and each public
artifact privacy check passed. The private receipt records each skip reason,
log hash, and the raw structured plus decoded logs; those logs remain outside
the repository. See the public
[Actions run](https://github.com/isaaclepes/DefiantMaple/actions/runs/37697431239)
for the run record and this task for the audit summary.
This closes the historical Core audit only; it supplies no gallery-filter,
Qt, or fresh Tauri acceptance evidence.

## Local and hosted checks for this increment

### Focused legacy-Qt prerequisite and Phase C status (12 October 2026)

The reviewed same-28 compatibility quartet passed once on the frozen attempt-23
app/UI pair: curation 6/6, bulk curation 8/8, collections 9/9 and Qt prototype
5/5 (28/28 total, exit 0, Python 3.14.7/PySide6 6.11.2, offscreen,
warnings-as-errors). The immutable private receipt is the Luna attempt-13
four-module record; the raw log SHA-256 is
`a8cc9d213a178855f4c041b1d2ac0a9c8799abdd70faa0f5cf345671ac305abc`.
This clears only that focused legacy-timing prerequisite. It is not evidence
for the current Phase C control revision, the remaining six legacy Qt modules,
full Qt/Core suites, native operation, package checks, or complete filter
behavior. The historical Phase C focused-control run passed 40/40 on its exact
earlier app/UI pair (attempt 7; 6.300 seconds), but the subsequent seven-module
legacy migration attempt 8 failed 79 tests (6 failures, 7 errors, one callback
traceback), with the shell pipeline's Python exit status unavailable. The
reviewed five-module retry, Phase C attempt 9, used a bounded direct-Python
harness and finished 59 tests with exit 1 (3 failures, 2 errors, 35.550 seconds)
and stable before/after hashes. It exposed source-list readiness in workflow
and usability, an async metadata panel publication timeout, and two test probes
that tried to use model._db after the model was closed. Three ignored
ResourceWarnings from intentional detached external handoffs were preserved;
the test log had no uncaught Qt callback traceback. Exact attempt 9 receipt and
log hashes are recorded in the current-status summary above. Keep the failed
attempt immutable; no repeated broad run is implied.

Phase C attempt 10 then ran only
`test_selection_change_and_model_reset_cannot_retarget_editor` on the frozen
startup-fix pair (app SHA-256
`1459fba57f2fb8d0ae7f8865ac2f7c231883c7fe0b278a68f1b05923f46ecb8c`, generated
UI test SHA-256
`9bce4bc137cd097f4e25da6b76b2a55938ce343a69368da9605a5432e5f292a4`). It
failed after 5.003 seconds with exit 1. The initial timeout diagnostic captured
`Legacy catalog task canceled`, the selected synthetic entity name and ID,
record count 1, no pending mutation, and gateway pending count 0; the gateway
was still running. Its private Core-row branch was skipped by a singular/plural
panel-kind typo. The immutable receipt SHA-256 is
`617f03364a571a140ee2f7b0149586abb0a6db1d2408724b8d2aa3d07a79a1c6`; raw log
SHA-256 is
`1462cc9ae471a8bafbb5c585b200f2fd79d171b121e4acbd730bb16b0d9476a6`.

After correcting only that diagnostic condition, Phase C attempt 11 repeated
the same one test and frozen app/UI pair. It again failed, in 5.278 seconds,
exit 1. The read-only Core listing now showed the desired entity row, matching
the panel's selected name, selected ID and single published record. The panel
feedback nevertheless read `Legacy catalog task canceled`; mutation-pending
was false and gateway pending count was 0 while the gateway was still running.
This isolates a likely asynchronous panel-feedback/read ordering issue after a
successful Core create, but does not qualify the original terminal-success
assertion. The raw generated ID and Core row remain only in the private log.
Attempt 11 receipt SHA-256 is
`fb9e020e4ae64ce84f9a1705ec52a452a1ea3871a35b696ae67b9474bdb4cdc5`; raw log
SHA-256 is
`71ae449d98e9a49934d58e3a73884921880c8e66e29fa1b2f9a1cb8dbc5969a0`.
No runtime fix or further retry is inferred here.

Root then released a narrow metadata-read feedback fix and generated regression.
Phase C attempt 12 reran only the same metadata case on app SHA-256
`ba13570ec5c86e85b60f34688baa9a98ef68d2cc7c3693513e60044990f9ef50` and
generated UI test SHA-256
`0cc5dbc46185deddfda2c98359351d1b65048c744e9ce05b0cfe5cdd988c2fe5`. The
saved-feedback condition passed, but the final original selection assertion
read the detail pane before its async refresh; the approved bounded
`wait_for_selected_asset(window, other_id)` was added before that unchanged
assertion. Attempt 12 receipt SHA-256 is
`28dca0da6cdbe9e4f9fc637a297040f5f71643ed0c3fec30728a3e9c9d69c13c`; log
SHA-256 is
`ac953b873780cf7b032bf313f97a43174cfef23a992ab8dd5c2e4c90960291f1`.

Phase C attempt 13 then reran that one case with the approved named detail
wait. It still failed after 5.457 seconds, exit 1: the original later user
selection was absent after the async metadata writes (generation 10, two rows,
actionable model and cached page zero, but no current row/asset or detail).
This is a selection-preservation runtime finding, not a readiness-only gap;
keep the original captured-editor identity, backend assignment and later
selection assertions. App/UI and test hashes were stable (`ba13570e…f9ef50`,
`0cc5dbc4…88c2fe5`, metadata test `44283ee2…72f81f`). Receipt SHA-256 is
`b430046f91d14a42f3276f057e7faf0567ec05cd29e418a1a9b1685e7dd56ec5`; log
SHA-256 is
`6a17a7499dddff9808e4d057726fd857a872902e69f4c1886c003e0cf757a30f`. Root
has held the four-module retry until a narrow runtime disposition; no further
test or UI suite is implied.

Phase C controls remain in implementation/review; the smoke app freeze and
generated fixture-helper review are separate. The generated fixture-builder
proposal is private and awaiting independent code inspection. No native fixture
has been created or exercised. Keep FR-UX-003/005/006/010, linked NFRs, and the
filter slice Partial; keep FR-RECOVERY-001–005 Not Started.

The private builder is constrained to a fresh schema-6 database, generated
rows/opaque IDs and placeholder paths, unchanged Core setup APIs where they
exist, and a small generated-only SQL insertion for asset/source-entry rows
because `index_file` requires opening media. It must not create media files,
scan roots, or claim Windows portability for the plan's literal backslash
path. Its eventual fixture-setup I/O and physical/logical snapshots are
separate from the later zero-source-I/O window for bounded queries and pickers;
startup containment and catalog setup remain separately instrumented.

After source/test freeze, run the meaningful targeted tests and one coordinated
full Core and Qt suite. Reuse unchanged Node/Tauri evidence only under its
original commit/run, and do not duplicate active implementation checks.
Check the actual changed paths before predicting hosted runs:

- Core `tests.yml` runs on push and PR without path filters; its six OS/Python
  Core test jobs plus three soak and three profile jobs make 12 jobs per
  event.
- Qt `qt-prototype.yml` runs on PR for `prototypes/qt/**`, `tests/**`,
  `defiantmaple/**`, `benchmarks/**`, or its workflow; it has three OS jobs,
  each including Core/Qt tests, generated 100k catalog, frozen build/benchmark
  and artifact upload.
- Tauri `tauri-prototype.yml` runs on PR for `prototypes/tauri/**`,
  `benchmarks/**`, `defiantmaple/**`, or its workflow. If the reviewed shared
  query adapter lands in `defiantmaple/`, a fresh Tauri matrix is expected;
  for a Qt-only diff it may be filtered out and only exact-byte baseline
  evidence can be reused.

At publication, enumerate actual exact-head push and PR runs rather than using
a PR-only wrapper as the run inventory. Read the actual Windows Core/Qt logs
for test totals and named skip reasons, record every job conclusion, package
smoke, artifact and privacy check, and distinguish skips/cancellations from
failures. Any frozen filter-worker smoke must be a justified addition with
preserved previous package smokes and platform-specific enforcement truth.

The generated read-only filter stages do not test backup/restore. Keep the
documented user-facing recovery boundary, source/backup failure-preservation
and restore verification in a separate milestone.
