# Task 40 — independent gallery filter review

Active Goal, 7 October 2026. Owner: separate Sol reviewer.
Read [Task38](38-gallery-filters-implementation.md),
[Task39](39-gallery-filters-acceptance.md), SDD v0.2 and scoped tracker rows.
The private planning review cleared the bounded product direction; it did
not clear runtime architecture or implementation.

## Review checkpoints

1. Independently review `docs/gallery-filters-design.md` before runtime
   changes. Verify shared count/page/rank/detail predicates, ordering and
   coherent snapshot/change detection; Qt pending rows; stable identities;
   canonical bounded alias lookup; typed validation; one active/latest
   pending ownership; cancellation/deadline/busy limits and actual close
   completion. Reject GUI-thread query fallbacks or all-row materialization.
   If broader refactoring is needed, require a separately reviewed source
   slice within this Goal. Technical gates are not extra user approvals.
2. Review actual code and meaningful tests after Root settles exact scope.
   Check selection/current-index clearing, no row-zero retarget, failure
   retention, source-filter/scan separation, duplicate Apply/Clear semantics,
   collection order, existing captured dialogs and protected behavior.
3. Review generated native helper/protocol before Root runs it. Match actual
   fixture/keypress/focus/visual assertions to the claim; inspect raw output,
   owned cleanup and preservation after execution. Distinguish focused
   QtTest/native evidence from human/AT qualification.
4. Review privacy, staged/public files, exact local/frozen/runtime identities,
   current-head CI and actual Windows summaries. Preserve diagnostic attempts
   and truthful resource/cache/native limits. Review final draft PR wording
   and tracker statuses; no evidence inflation or full Phase1a exit claim.

Report concrete blockers and clearance per checkpoint in this task/private
review receipts. Reviewer does not edit implementation, run broad duplicate
tests, commit/push, switch branches, publish, run visible UI or update outputs.
Preserve all media/metadata/schema/scanner/durability/recovery/cache/external
scope. Merging the new draft PR and binary replacement are separate decisions.

## Brief preflight — runtime design pending

I reviewed Tasks 38–40 against SDD §11 and the existing Qt model. The bounded
one-tag/one-entity direct-assignment AND semantics, explicit Apply/Clear,
collection retention, duplicate-digest behavior, source-filter/scan-target
separation and Partial status boundaries are coherent. This clears the briefs
as implementation planning only; it does not clear the off-GUI runtime design.

The existing `AssetModel` synchronously reads the catalog for count, page,
stable-ID rank and detail, including calls from `data()` during Qt painting.
Moving only the Apply count into a worker would leave GUI-thread reads. The
design must show how count and first page share one snapshot, how later
page/rank/detail reads detect intervening catalog changes without holding a
read transaction across user input, and how pending/old-page rows cannot
become action targets. The new gallery source-filter picker and Apply must
remain bounded and off-GUI without invoking the existing scan-target
issue/status enumeration. Existing source-management reads remain a separate
documented synchronous limitation unless a separately reviewed prerequisite
requires changing them. These are design gates, not another user permission
decision.

## Design checkpoint — runtime clearance held (8 October 2026)

I reviewed `docs/gallery-filters-design.md` at SHA-256
`ee47eab3bfa492a382cd00f86f59922e7d6f1b5ddb9059a690183d88a59c112f`.
The immutable predicate/order, count plus first-page snapshot, versioned
later-page/rank/detail replies, non-targetable Qt placeholders, bounded
picker/source lookup and actual-finish worker close form a coherent proposed
read architecture. This is not runtime implementation clearance yet.

The blocker is concurrent GUI writing under the catalog's default SQLite
rollback journal. A two-second worker read transaction can hold a shared lock
while `AssetModel.update_state()` commits through a GUI-owned writer with its
own busy wait. The worker's 50 ms timeout does not bound that GUI wait.
Specify nonblocking write/read coordination or stage a separately reviewed
writer prerequisite, then test a forced overlapping read and GUI mutation.
Do not change catalog durability or journal mode merely to bypass the gate.
The private `work/gallery-filter-design-review-2026-10-08.md` receipt records
the remaining snapshot, bounded-output, action-target and source/test checks.

## Design re-review — checkpoint 1 cleared (8 October 2026)

The revised `docs/gallery-filters-design.md` at SHA-256
`2d8d25c2c9206608422cc5c48419dffb1ee57d1eeee2d38b57e8f8802a24b518`
resolves the blocker above. A single serial off-GUI gateway ends its reader
transaction before executing captured GalleryWindow catalog writes, routes
overlapping GUI catalog reads off the GUI, invalidates row actions at write
intent, and uses captured ID/revision refusal for delayed review keys. It
keeps scanner/Core service ownership and schema/durability unchanged. The
design now bounds the legacy request queue, tests rollback-journal contention,
and keeps prerequisite A dormant as isolated gateway transport and lock tests.
Prerequisite B adds the frozen typed query and activates the complete GUI
read/write migration only after snapshot, generation, placeholder,
action-target and close guards pass, before filter controls. **This clears
the design and exact A/B review scope only**; code/tests, generated native helper, preservation,
privacy, current-head CI and final draft PR still require independent review.

## Phase A dormant gateway source review — cleared (8 October 2026)

The new `prototypes/qt/gallery_filters.py` at SHA-256
`abf8392d427611c2629f5b53a995df82d196b0c39f126072823802152497845c`
and `prototypes/qt/tests/test_catalog_gateway.py` at SHA-256
`51cd4940ee6a49df8c1fc752f6a1f2bbda322c3a63c7b0a54f21ad08cba5e784`
are independently cleared as **dormant Phase A infrastructure only**. The
final focused generated rollback-journal run passed 17/17 tests at those
hashes; earlier attempts remain private diagnostics. The gateway has fixed
queue slots, no GUI object transport, reader release before service writes,
truthful uncertain write results, distinct unbounded legacy service reads,
and actual-finish close/resource acknowledgement. No existing app path is
wired to it. The private `work/gallery-filter-phase-A-independent-review-2026-10-08.md`
receipt records the exact log hash, findings and B review gates. Phase B is
not cleared by this checkpoint; Root settles its exact source scope first.

## Phase B1 dormant query source review — cleared (9 October 2026)

The new `defiantmaple/gallery_query.py` at SHA-256
`d776645435d468e9972ac046ebbfe7384519c0541b31ea4a97b58882b0e29b58`
and `tests/test_gallery_query.py` at SHA-256
`fff9e53e1fae259b53f4950196124084de7acb42d52859cb9c6e7e17c2d50909`
are independently cleared as **dormant B1 only**. The final focused Core run
passed 11/11 tests at those exact hashes. The bounded helper preserves typed
AND predicates, direct canonical tag/entity membership, literal path escaping,
existing order, collection/digest semantics, caller-owned count/first-page
snapshot, and versioned later page/rank/detail refusal. It projects oversized
catalog text through SQL guards and uses bounded canonical/source lookup. The
Core test remains free of Qt dependencies; actual gateway-context integration
is deferred to B2 Qt tests. The private
`work/gallery-filter-phase-B1-independent-review-2026-10-09.md` receipt records
the log hash, review evidence, and limits.

**B2 is not cleared.** A's current 8,192-node reply cap rejects a legitimate
full 256-row B1 page, and A's persistent reader can mislabel old rows after an
atomic catalog-file replacement that happens before a request. B2 needs narrow
reviewed gateway corrections with actual full-page and replacement regressions,
plus pending/stale-row, captured-action, GUI read/write migration and close
tests before any GalleryWindow activation or filter controls.

## Phase B2a gateway correction review — cleared (9 October 2026)

The corrected `prototypes/qt/gallery_filters.py` at SHA-256
`87fe023f2210ed7ca164bb7f0a3c386ce8fd166ceb7a41df706a57358582116a`
and new `prototypes/qt/tests/test_gallery_query_gateway.py` at SHA-256
`01bd254107eb2c1b6c34dd99db4ed2cd5a3bcbe89e91216115cb48d61d687ac6`
clear the two B1 gateway integration blockers **in dormant B2a scope only**.
The affected A plus new Qt gateway suite passed 20/20 tests at those exact
hashes. A full 256-row B1 reply now fits the bounded read-reply node budget,
while request/write bounds remain and true byte/node oversize replies still
refuse. The persistent reader refuses path identity changes relative to its
opened catalog, including after an actual on-disk replacement; a fresh gateway
reads the replacement. The private
`work/gallery-filter-phase-B2a-independent-review-2026-10-09.md` receipt records
the exact log/manifest and integration limits.

GalleryWindow remains unwired. A fixed module-level operation registry is a
justified B2b source addition under A's handler contract, provided it exposes
only trusted B1/Core calls with copied arguments. B2b must independently clear
the full GUI read/write inventory, pending/stale action guards, captured-ID
continuations, no GUI wait, actual close, and existing-test timing changes
before gateway activation. This B2a review does not clear filter controls,
native acceptance, preservation, CI or release.

## Phase B2b focused integration review — held at pause (10 October 2026)

I reviewed the activated `prototypes/qt/app.py` SHA-256
`df867657b8c0a29894388c0eab5d8186873cb0ca1b09fc82d88f01128448ea0e`,
the typed-status/identity-guard gateway SHA-256
`76469ba37bd85f834ddf8d8e9e5d56135229474be805e8302ca0751cd1021295`,
closed worker operations SHA-256
`bfeea3154b97948086ed9b181ee71c95e2fc9d475cd6b8dbc249877891d7a1e1`,
and focused UI/gateway-query tests SHA-256
`3fd36fe644d7119111256f50804c0ba564914762e44efdf7de9fa1f8b7847780` /
`f21920b3cce639505e330812d21de95d4f5b6a94b22ad0ba7e3994608aaa6b3d`.
The unchanged A gateway suite passed 17/17 and actual gateway/query suite 4/4
at the same gateway hash; the final new UI suite passed 15/15 at all final
B2b hashes with warnings as errors and clean callback capture. The prior
existing Qt prototype module passed 5/5 at an **earlier** app hash, before a
closed collection operation-label fix, so it is not a final-hash suite claim.

The source review found no further blocker in the focused gateway/GUI paths:
count plus page zero publish together after off-GUI root validation; page,
rank and detail use typed stale-view replies; pending/error/stale rows and
detail-dependent single actions cannot target old rows; selected IDs and
revisions are captured for worker mutations. External commit, file
replacement before read/legacy/write dispatch, failed candidate, 24-page LRU
revisit, old page reply, malformed page, delayed focus, closed dialog,
actual Core curation failure and rival collection neighbor refusal have
meaningful generated regressions. The gateway's pre-dispatch file-identity
check is not an atomic filesystem race guarantee. Existing prewindow CLI
`initialize()` remains synchronous outside the activated GalleryWindow read
path; no whole-app startup or performance claim is made.

**B2b acceptance and next-stage clearance remain held at the user's pause.**
Existing `test_curation_ui.py`, `test_bulk_curation_ui.py` and
`test_collections_ui.py` have preserved failing diagnostics because their
GalleryWindow helpers still assume synchronous `row_for_asset()` or immediate
publication. Resume with bounded named waits while retaining their exact
ID/order/revision/neighbor assertions, then rerun affected tests at a frozen
head. The private
`work/gallery-filter-phase-B2b-independent-review-2026-10-10.md` receipt
records exact manifests, log hashes, findings and all remaining gates.
Filter controls, native tests, preservation, CI/Windows, publication and Goal
completion are not cleared by this checkpoint.

## Phase B2b bulk continuation review — narrow source clearance (11 October 2026)

I independently reviewed frozen `prototypes/qt/app.py` SHA-256
`8419a5b3c309ecf300fff56c0bc613f49e9b52ed2fa477ca465e286d417001ce`
and `prototypes/qt/tests/test_gallery_filters_ui.py` SHA-256
`b07af2bfa45b4c658e093a30c72c9a207c80b8654af6562170a626bbfe05f0cf`.
Immutable attempt 20 passed 23/23 focused Qt UI tests with warnings as errors,
source-stable receipt SHA-256
`f4a03e73caacaa193f4865de24c2af752e4bd1fb5acc67772a806eac1df8a298`
and clean log SHA-256
`1fc3e9446d6ad5265d1fa182226ccb598fb0031a4c4e991f2508bb5a065f2d3f`.

The previously identified explicit-Apply race is resolved for this scope:
mutation completion refreshes the latest predicate, but restores captured bulk
selection only when the model generation and collection-choice epoch still
match write intent. The generated delayed Core-write regression proves that a
later reviewed filter wins and leaves selection, current row, detail and
actions clear while the single captured write completes. Fresh rank/page
lookups select only matching stable IDs from the new token and targetable rows;
captured old revisions are not used to issue commands. User selection changes,
generation changes, file replacement/unavailability and close prevent stale
restoration. Rank has the gateway's cooperative read deadline and no GUI wait;
the page continuation has a bounded timer and disconnects its listeners on
completion or refusal. A separate rank timer is not required for this narrow
source clearance.

The delayed history-list regression preserves a later chosen group and proves
that undo changes only that group's captured ID. The history choice epoch and
latest-key group read prevent a stale list or detail callback from retargeting
the user. This clears the **bulk restoration/history-choice source finding
only**. Release the affected curation, bulk, collection and Qt prototype test
run on these frozen hashes, preserving original substantive assertions. Prior
old-suite failures remain diagnostics until that run passes. This is not B2b,
Phase C, native, CI/Windows, preservation, release or Goal clearance; see the
private `work/gallery-filter-phase-B2b-independent-review-2026-10-11.md`
receipt.

### Affected legacy Qt run: rapid-chain blocker (11 October 2026)

The separately owned attempt 9 ran the four affected Qt modules against app
SHA-256 `8419a5b3c309ecf300fff56c0bc613f49e9b52ed2fa477ca465e286d417001ce`:
24/28 passed, with three failures and one error. Curation 6/6 and Qt prototype
5/5 passed. Gamma detail and the reopened history ID were asserted before
their async continuations completed; a collection move-up wait incorrectly
required a success message to change although both moves report the same
message. Preserve their exact identity, history, order and DB assertions when
correcting these named waits.

The bulk no-op/failure/retry chain reveals a **new runtime source blocker**.
After a write ACK, another valid bulk write can begin before fresh rank/page
selection restoration finishes. `_capture_bulk_selection()` then sees no
actionable selected rows; `_mutate_catalog` clears `_pending_bulk_restore`,
losing the prior stable-ID continuation even though query and user choice did
not change. A final test wait would conceal this valid rapid interaction.
Retain the bounded continuation across compatible writes or visibly refuse a
new write until restoration completes, with a focused rapid-chain regression.
The narrow attempt20 explicit-Apply/history finding above remains cleared,
but **B2b acceptance and Phase C release remain held**. Private receipt:
`work/gallery-filter-phase-B2b-independent-review-2026-10-11.md`.

### Rapid-chain source correction — cleared for affected tests (11 October 2026)

The subsequent frozen app SHA-256
`59fe7689f17a9b9922ada0d64f0d3f33928506ae008e97da76b50d0d9f26e4ca`
and focused UI test SHA-256
`9b941299739ce0a6ce75683196006e151d27286679785ffccecd491bf87b307c`
resolve the rapid-chain source blocker above. Attempt 22's immutable receipt
SHA-256 `60693c25a46787bd36db2ba039cd95015924f939483dd927e3289c0557c9d530`
records 25/25 clean, source-stable generated UI tests; log SHA-256
`639dcb1c9756f23ce72b1b61ac472815dfcc6177b67a86448cb2f2aebbf5aebc`.
The bounded stable-ID intent passes across compatible own bulk writes while
query, generation, collection choice and user-selection epoch match. It is
discarded on explicit Apply, new user choice, stale view or close. An
actionability listener now clears the matching active intent on typed catalog
replacement/unavailability and disconnects on completion/refusal. Held old rank
callbacks cannot republish selection. The focused regression proves no-op and
failed writes leave revisions unchanged, followed by one successful write,
one group journal and current-revision A/B selection. This clears the **narrow
source finding for release of the affected 28-test quartet only**. Existing
suite results, B2b acceptance and Phase C remain pending separate review.

### Explicit blank clear — pause checkpoint (11 October 2026)

The first affected-suite run on the rapid-chain fix passed 27/28. Its sole
history failure followed `selectionModel().clear()` while an automatic bulk
rank restoration was still pending. A standalone PySide6 6.11.2 check confirmed
that Qt's `clear()` clears both current index and selected rows when present;
an extra `setCurrentIndex()` would have hidden the blank-clear race. The
subsequent frozen app SHA-256
`8831de0699846534c85b7f18a2cac222869bfd091614f94238459b84aff6f83c`
and generated UI test SHA-256
`e75a603b55a4a23ab52f2803799be1db4eaf789af46546328b9adfad2a61db6b`
add a view-owned explicit-clear signal guarded from model-owned resets. It
advances the user-selection epoch and disposes pending restoration even when
Qt selection and current index are already blank. Attempt 23's source-stable
receipt SHA-256 `ed4c67feebbee05820a9760671dfbfa18d6dc8164262978b961fd0c028128154`
and clean log SHA-256
`dac21f39a87b667f0ec221b01ab46e636403cf94c9587613bae0e9e793866824`
record 26/26 focused generated tests, including a held-rank blank-clear
regression. This is a narrow direct-`clear()` source clearance. The affected
28-test quartet needs one frozen-hash checkpoint; B2b, other gestures, Phase C,
native and final acceptance remain held at the user's pause.

## Phase B2b prerequisite review — cleared for Phase C development (12 October 2026)

The frozen app SHA-256
`8831de0699846534c85b7f18a2cac222869bfd091614f94238459b84aff6f83c`
and new UI test SHA-256
`e75a603b55a4a23ab52f2803799be1db4eaf789af46546328b9adfad2a61db6b`
remain unchanged. Generated attempt 23 passed 26/26 at those hashes. The
reviewed timing migration in the four affected existing Qt modules passed
28/28 at unchanged runtime/UI hashes in Luna's immutable attempt 13, receipt
SHA-256 `7607c6162bcb8a2a622d710cd6d0a3cd166e955f65befbd238aa668da616ec64`,
clean log SHA-256
`a8cc9d213a178855f4c041b1d2ac0a9c8799abdd70faa0f5cf345671ac305abc`.
The final bulk test SHA-256
`98ef536f16e3aac1c75d1260a610443b8a9075de8538c936a29072792399e61f`
awaits exact post-undo gamma and alpha detail and serial curation-history
publication before preserving its original target, disabled Undo and Core
edits assertions. Earlier 27/28 diagnostics remain recorded, not green
evidence.

**Decision:** the focused B2b gateway/GUI source and these affected-test gates
have no remaining review blocker for **starting Phase C controls development**.
This does not clear full B2b, filter behavior or final acceptance. Root may
release only `prototypes/qt/app.py` and existing new
`prototypes/qt/tests/test_gallery_filters_ui.py` for Phase C; no Core query,
gateway, registry, schema or old-test changes are justified by the reviewed
proposal. Keep a mutable draft separate from the published immutable query
and latest requested Apply; mutations refresh the latest valid user intent,
never unsaved widget text. Candidate failure leaves the dirty draft visible
and republishes the prior predicate only under a fresh valid token. Picker
edits unset canonical IDs; unresolved text and deleted IDs visibly refuse
Apply. The shared taxonomy slot needs per-picker epoch/loading/cancel handling.
An unsafe 64-row lookup cursor with `next_cursor=None` and `incomplete=True`
must show refine-prefix refusal, not a false exhausted list. Clear removes
all facets plus duplicate digest while retaining collection/order. Source
lookup uses bounded catalog rows and stays independent of legacy source issues
and scan target. Return/Escape respect picker selection before ordinary Apply
or gallery actions. The private
`work/gallery-filter-phase-B2b-independent-review-2026-10-11.md` receipt
records exact evidence and limits. Six other Qt timing modules, full Core/Qt,
native, package, privacy/preservation, hosted CI/Windows, PR and release remain
separate gates at final source freeze.

## Phase C controls checkpoint — held (12 October 2026)

The mutable controls candidate reached app SHA-256
`9e382139b2a8a538751ded08b486942bb254603b10981b6cd93477e07955a2e8`
and generated UI test SHA-256
`56ed43ee990f6456e89dcfbecd454a6113b5fd5bdaf29df9f14b1e794f9e193f`.
Attempt 4 passed 36/36 focused offscreen checks at source-stable hashes, with
warnings as errors and no uncaught Qt callback traceback. This is not Phase C
clearance. Independent source review found that a failed candidate awaiting
prior-view restoration may be superseded by a captured-dialog mutation while
its internal filter fields still contain the failed candidate; mutation
completion can then refresh that rejected query with no old token available to
restore. A held-restore mutation regression and correction are required.
A permitted 256-character selected name also expands the picker to over 3,000
pixels in a read-only offscreen probe; a bounded-layout correction/regression
is pending. The existing curation UI widget test expects auto-apply and needs
an explicit Apply timing migration without losing its substantive assertions.
Exact evidence and limits are in the private
`work/gallery-filter-phase-C-independent-review-2026-10-12.md` receipt.

The separate private native fixture builder at SHA-256
`aa923ecf3ef04f59cdd0860ceefac2e4c2d7b411fb70339cc3d2283a62a8fa95`
has source-only clearance for one new disposable private output root. It uses
schema-6/Core metadata and collection APIs plus generated catalog SQL, no
scan or media creation, and records logical integrity and physical database/
placeholder snapshots. Its execution, exact fixture matrix, UI capture and
privacy checks are independent evidence gates; see private
`work/gallery-filter-native-fixture-source-review-2026-10-12.md`.

Attempt 6 at app SHA-256
`3ebc7cf55b1e0e40c0b2a8e012a71b4626718cef4b556fd4b8e0a948e2888c4e`
and new UI test SHA-256
`05aaa004c365fe335bc3a114ac23d3ea88766e1ef0958b3bf5521d39eef5175a`
passed 39/39 focused tests. It corrects the preceding held-restore race
and long-label expansion, with generated regressions. Phase C remains held:
when an invalid picker ID is Applied during an active catalog write, the
deferred first-page failure occurs after mutation invalidated `_token`;
`_candidate_failed` resets to the prior predicate but currently submits no
fresh count/page, leaving the gallery non-actionable. The private Phase C
receipt records the distinct required regression. Existing explicit-Apply
legacy test migration and broader acceptance remain separate.

Attempt 7 at app SHA-256
`2446ce66f64b44db6f68b854fe37c6271d47fcfcb78a544ccdc500683096a3e1`
and new UI test SHA-256
`1dd414c501f163eb446623e26353aa772acae927ec857aa395e98f3bc7f42e01`
passed 40/40 focused generated offscreen tests at source-stable hashes,
warnings as errors and no uncaught Qt traceback. Independent review confirms
the deferred invalid-ID Apply after an active captured write now freshens the
prior published query, retains the dirty draft and leaves no stale action
target. The amended seven existing Qt test modules retain original Core,
identity, ordering and captured-target assertions; cached preview, comparison
and external actions preserve direct model filter calls. Workflow and curation
use explicit Apply for GUI draft controls. The exact seven test hashes and
receipt are in private
`work/gallery-filter-phase-C-independent-review-2026-10-12.md`.
**Decision:** clear this frozen source and scoped test-only diff for one focused
seven-module affected run. The run, full Core/Qt acceptance, native UI,
package, privacy/preservation, hosted CI/Windows and PR remain pending.

The first affected legacy run, attempt 8, failed: 79 tests with six failures
and seven errors; its shell pipeline lost the Python exit status because
`tee` ran without `pipefail`. The raw log also contains a Qt callback traceback
and an ignored `Popen.__del__` ResourceWarning. Independent read-only triage
found missing asynchronous source-list/add-source, selected-detail, metadata
modal visibility/write, comparison-close and actual gateway-close readiness
preconditions in the affected tests; no app defect is established from those
failures alone. Preserve exact Core/captured-target assertions and retry only
the five failing modules after bounded test-only corrections. Cached preview
and curation passed unchanged; neither broad acceptance nor a clean affected
run is claimed. The private Phase C receipt records the exact attempt-8 log
hash and per-case classification.

Attempt 9 used a direct subprocess harness with actual Python exit 1 and
source-stable hashes. Its five-module retry ran 59 tests with three failures
and two errors (raw log SHA-256
`ffdea64571645f2e4a2c5a36995570099f790a385a8ebb9eda433453f8449968`).
Independent review identifies a real startup race: the first gallery Apply
cancels an active legacy source-list request and leaves source controls empty.
The two close errors used the old model's SQLite handle, which is now
intentionally absent after owned async close. Amended external and metadata
tests preserve close/callback/no-reopen assertions with gateway ownership
checks; the metadata timeout now records private terminal Core/panel state
only on failure. The source-list correction and focused generated regression,
then a narrow affected retry, are pending. Three detached-editor `Popen`
ResourceWarnings are qualified legacy handoff diagnostics, not gallery
QThread cleanup evidence. See the private Phase C receipt for exact test
hashes and remaining acceptance gates.

Attempt 10 at app SHA-256
`1459fba57f2fb8d0ae7f8865ac2f7c231883c7fe0b278a68f1b05923f46ecb8c`
and new UI test SHA-256
`9bce4bc137cd097f4e25da6b76b2a55938ce343a69368da9605a5432e5f292a4`
passed 41/41 focused source-stable checks, including held startup validation
and source/collection option publication before the first Apply. Independent
review clears that narrow source fix for the affected retry. Separate static
review clears the seventh packaged smoke source and private native helper for
their first staged executions after three package/smoke evidence and two
native-helper gaps were corrected. No affected retry, package build or native
UI outcome is claimed; full acceptance remains open. Exact hashes and scope
are in the private Phase C receipt.

At the user's pause, the narrow metadata feedback correction passed 42/42
generated focused checks at app SHA-256
`ba13570ec5c86e85b60f34688baa9a98ef68d2cc7c3693513e60044990f9ef50`
and new UI test SHA-256
`0cc5dbc46185deddfda2c98359351d1b65048c744e9ce05b0cfe5cdd988c2fe5`.
The isolated old metadata test then established another runtime issue:
captured-A writes complete, but a later user B selection/detail is lost across
generic mutation reset. Its original final B identity assertion remains;
the bounded matching-detail wait timed out with an actionable two-row model.
A narrow metadata focus continuation is WIP and has no independent clearance.
The staged affected retry, native UI, package smoke, broad tests and hosted CI
remain pending. See the private Phase C receipt for exact checkpoint scope.

## Resumed final local checkpoint — 12 October 2026

The metadata focus continuation is now cleared at app SHA-256
`d4c09ab5e9bd615c7188f1009a0c7e6f563a72cdc4b63d569f446522a4281881`
and generated UI-test SHA-256
`d280a4218062a3c292f6c084796864dbf21b45e30ce3990b9d6e3cebc322ae2b`.
It carries a later selected B through rapid writes captured on A only while
query, collection choice and user-selection epochs still match; fresh
rank/page/token checks prevent an old revision or late reply from retargeting
commands. Explicit Apply, user change/blank clear, close, replacement and
targeted rank/page failure dispose the continuation. The source-stable focused
suite passed 48/48; the isolated old metadata case also passed with its
original captured-A Core assignment and final B identity assertions.

The full local Qt discovery passed 170/170 offscreen under Python 3.14.7 and
PySide6 6.11.2, with no uncaught Qt callback traceback. Three ignored
`Popen.__del__` ResourceWarnings belong to the existing detached synthetic
external-editor handoff, not gallery worker cleanup. The full Core discovery
passed 274/274 in the repository workflow warning mode. A separate local
`-W error` run passed 273 and errored once on the unchanged Python 3.14
`sqlite3.connect()` positional-argument DeprecationWarning. The command modes
and raw logs remain distinct in Task39 and the private review receipt.

I independently reviewed native visible Linux Wayland attempt 2: 20/20
declared generated cases passed in 5.183 seconds against frozen runtime
hashes. The public JSON has only `runtime_hashes` and `cases`; each case has
only `case`, `expected` and `observed`. All expected/observed arrays match
and contain only generated alpha–hotel labels. The gateway reached actual
close completion; catalog logical/physical state, source placeholders and
owned cache match the private before/after snapshot. The launcher records
stable inputs and no timeout. Attempt 1 remains a failed private diagnostic:
its helper expected `Parent` when the fixture's canonical name is `parent`.
The exact two-literal private helper correction was reviewed before attempt
2; product source did not change. The gallery viewport grab contains generated
filename/path captions and remains private. Only the closed JSON and five
inspected path-free source/tag/entity/Apply/Clear control grabs are copied to
`docs/evidence/gallery-filters/`. Final staged privacy validation is a
separate gate. The observation does not qualify human keyboard-only use,
assistive technology, other platforms or performance.

The isolated task-private Linux shadow build passed with real
`pyside6-deploy`/Nuitka and all seven frozen smokes, including gallery filters.
Its one-file artifact is 50,933,248 bytes, SHA-256
`6eaa457dfbd4463fafc31698c9e05b7e3633097a108f527936e8634d3166a1c5`.
Private receipt SHA-256
`e8cd2793038037aced1f64605afe806fe3e32cd681690c06dd5b5d82102920a8`
records 28 copied runtime allowlist files and all 15 protected deployed
outputs unchanged in bytes, modes and timestamps. The 100,000-row offscreen
placeholder benchmark is one local launch with count/first-page and review
write/fresh-publication timing; it excludes real image decode, disk thumbnails
and compositor presentation. Root's separate post-build protected-source audit
found 250 tracked records, zero unexpected tracked changes, zero protected
record changes and zero changes among 15 deployed outputs (private receipt
SHA-256 `77ceab907bc3e0e27177c1c2e86849b4b8e3576a9168d09753ed846c370ebfe9`).

**Review disposition:** local frozen source, generated Core/Qt tests, bounded
native behavior and isolated seven-smoke package gate are cleared for draft
PR preparation. Final staged-set privacy, current-head hosted CI including
Windows summaries, and final PR diff review
remain open. Keep mapped filter requirements Partial and recovery rows Not
Started. This record does not authorize a PR merge or deployed-binary
replacement.
