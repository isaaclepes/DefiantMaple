# Task 38 — composed gallery filters and bounded query loading

Active Goal, 7 October 2026. Owner: Sol implementation; Root integrates.
SDD v0.2 is requirement input, not independent execution authority. The user
authorized PR20 merge and the next Goal. PR20 merged as
`0af8ba5108af4727679e76bc60e6a71918ef5994`, preserving reviewed tree
`e872140902d6a78ea856763c3948b7b5835da716`. This branch begins there.

## Local completion checkpoint, 12 October 2026

The independently reviewed final candidate passed 48 focused filter tests,
170 full Qt tests, and 274 full Core tests using the hosted warning settings.
The stricter Python 3.14 warning diagnostic remains recorded separately.
Native Wayland acceptance passed 20 generated cases. The isolated Linux build
passed seven frozen smoke checks and its 100,000-row placeholder benchmark;
all protected source records and 15 deployed output files remain unchanged.
The separate local sample is available for hands-on testing. Final publication
privacy checks and current-head hosted CI remain required; merge and deployed
binary replacement remain separate decisions. See [Task39](39-gallery-filters-acceptance.md)
for evidence and the limits of these claims.

## Product contract

Add one optional canonical assigned tag and one optional canonical assigned
entity, AND-composed with literal path/filename text, review state, source,
media type, rating, favorite and an explicitly selected duplicate digest.
Use parameterized `EXISTS` predicates, without duplicate result rows. Alias
lookup resolves canonical identity; equal entity names show their category.
No implicit descendants, taxonomy mutation, multi-value grammar or schema
migration. Path search keeps current literal wildcard/case behavior and has
a declared 512-code-point refusal limit, without silent truncation.

One draft state and one applied immutable state drive Apply/Return. Validate
the entire draft before publishing a new generation. Existing-but-unassigned
taxonomy yields valid zero matches; missing/deleted selected IDs yield a
visible stale-filter refusal that retains the previous applied view. Plain
unresolved picker text cannot silently mean All. Clear removes field and
duplicate predicates while retaining the chosen manual collection/order;
ordinary Apply preserves an explicit duplicate digest. Separate gallery
source filtering from scan-target/source-health selection.

Successful apply clears current index, multi-selection and detail/action
targets, without selecting row zero. Pending/failed/placeholder rows cannot
become command targets. Captured dialogs retain their existing stable IDs
and drift/refusal checks. Distinguish pending, invalid, empty library, valid
zero matches, read failure and catalog-observed missing/offline states.

Keyboard minimum: Ctrl+F focuses path text, Return applies, Escape dismisses
an unresolved picker first, and Apply/Clear are reachable in logical Tab/
Shift+Tab order. Gallery arrows/Ctrl+Space/review digits operate only with
gallery focus. Async results do not steal focus. Fixed defaults here do not
qualify configurable shortcuts or assistive technology.

## Design before runtime changes

First write `docs/gallery-filters-design.md`. Independent Sol must clear the
immutable predicate/order contract and bounded off-GUI count/initial-page/
later-page/rank/detail ownership before code. Existing Qt reads are GUI
synchronous, including paint/detail paths; moving Apply count alone is
insufficient. Coherent snapshot/change detection must prevent stale count,
page and rank replies from exposing a different target under a row index.

Predeclare request/text/output bounds, cancellation/deadline checks, busy
timeout, latest-pending generation, pending model behavior and actual close
ownership. Retain 256-row pages/24 cached pages; taxonomy lookup pages are
64 canonical records. The proposed 50 ms busy timeout and two-second read
refusal are design choices, not guarantees against kernel-blocked I/O.
No all-taxonomy/result materialization, source I/O or unbounded threads.

Root will settle the exact runtime file scope after independent clearance.
If safe integration needs a broader model refactor, stage the read adapter
as its own reviewed source slice before filter controls. This internal design
gate does not require another user approval question.

## Preservation and finish

Checkpoint 1 independently cleared the revised design on 8 October at SHA256
`2d8d25c2c9206608422cc5c48419dffb1ee57d1eeee2d38b57e8f8802a24b518`.
Rollback-journal readers can delay existing GUI commits, so the design stages
a dormant serial catalog gateway first (A), then one coherent bounded-query
and GUI-callback integration (B), before new filter controls. A adds only
`prototypes/qt/gallery_filters.py` and its focused gateway tests; it does not
activate new catalog reads or writes in GalleryWindow. Root requires separate
A source/test review before B. B's GUI migration preserves Core services and
qualifies opaque legacy task limits separately from new gallery-read bounds.
This design clearance is not implementation, native, or completion evidence.

Dormant A subsequently passed independent source/test review and 17 focused
generated checks (attempt 13). Its legacy service tasks use their original
connections without an extra gateway SHARED transaction or new gallery-read
limits; bounded gallery tasks retain their snapshot/limit guards. Prior
diagnostic attempts remain private. Root now releases B1: only the new Core
bounded-query module and focused query tests, still dormant. B2 activates the
query/gateway and migrates the listed GUI callbacks only after B1 review.
No existing app/runtime/test file is changed by A or B1, and no tag/entity
gallery usability acceptance is inferred from those infrastructure checks.

B2 also needs a reviewed full-page transport correction. The dormant gateway's
8,192-node copying limit counts dictionary keys and values; 256 normal query
rows with 19 fields already require at least 9,984 nodes. This is an integration
finding, not a failed Phase A transport test. A narrowly bounded reply-budget
or representation change must preserve byte/depth/shape limits and genuine
overflow refusal, with a real 256-row gateway regression before activation.
Root will release that exact exception with B2 after B1 clearance.

Independent review also reproduced a persistent-reader replacement hazard:
after atomic catalog-path replacement, an existing SQLite connection can keep
reading the old file while both per-request path checks see the new identity.
B2 must compare against the connection's original identity, refusing or safely
reopening on replacement, and test the actual gateway path. A manually changed
Core query context does not qualify this lifecycle behavior.

On 9 October, B1 received independent source/test clearance at query SHA256
`d776645435d468e9972ac046ebbfe7384519c0541b31ea4a97b58882b0e29b58`
and PySide-free Core-test SHA256
`fff9e53e1fae259b53f4950196124084de7acb42d52859cb9c6e7e17c2d50909`.
Attempt 7 passed 11/11 focused generated checks; diagnostic attempts are
retained separately. This remains dormant query infrastructure.
Root releases B2a for the two narrow gateway corrections above and a new
`prototypes/qt/tests/test_gallery_query_gateway.py` actual integration suite.
It must pass affected gateway checks and independent review before B2b.
The app, filter controls and previously cleared Core pair remain unchanged.
B2b's trusted handler module and complete GUI callback migration are proposed
scope only until this gateway checkpoint clears.

B2a subsequently passed all 20 affected gateway/query checks and independent
review. Root releases B2b: a closed module-level handler registry in
`prototypes/qt/gallery_operations.py`, the complete inventoried model/window/
dialog catalog migration in `prototypes/qt/app.py`, and focused integration
tests in `prototypes/qt/tests/test_gallery_filters_ui.py`. New canonical filter
controls remain gated until B2b review. GalleryWindow must explicitly use the
async path; standalone model callers explicitly select synchronous mode.
Benchmark samples wait for actual count plus first-page publication and, for
review actions, the write and refreshed generation. The legacy task limits
remain distinct from bounded gallery reads.

The private timing inventory names ten potentially affected existing Qt test
files. Exceptions are conditional on demonstrated asynchronous observations:
add bounded named-completion waits or explicit standalone read mode, keeping
all substantive identity/order/revision/refusal assertions. A shared bounded
`gallery_wait.py` helper is allowed. Structural or product-semantic test
changes require Root to settle their concrete need before editing; no blanket
sleeps or weaker expectations. Run focused affected checks during integration;
the coordinated broad suites follow source freeze.

The 10 October integration review releases one narrow gateway extension:
trusted typed changed-view and catalog-replacement failures. A changed view
invalidates all row/action targets and requests a fresh generation; a replaced
file requires reopening rather than querying the old reader indefinitely.
Check the original catalog identity before legacy tasks and writes as well as
bounded reads. A replacement-before-mutation test must show that the Core
handler is never invoked and the replacement catalog remains unchanged. This
pre-dispatch guard does not claim atomic coordination with external processes.
The prior B2a hash remains historical evidence; affected checks must qualify
the extension. Core service APIs and schema remain unchanged.

Paging allows one in-flight request per generation/page. A successfully loaded
page may be fetched again after eviction from the 24-page LRU, with the same
token guards. Failed pages retain visible, non-targetable errors for that
generation instead of being retried by painting. Test eviction and revisiting,
late replies and explicit new generations. Luna owns the demonstrated
`test_qt_prototype.py` timing adjustment and wait helper; Sol owns runtime and
new integration tests, with brief fixed-source holds for evidence runs.

Single-asset opening actions require a matching captured detail result for
the current generation, asset ID and revision, both in button state and direct
entry points. A bounded incomplete result may permit opening when the row's
identity/path remains targetable and incompleteness is visible. Review digits
can use an already published targetable row and revision guard independently;
multi-target bulk/comparison commands capture loaded rows under one current
token and do not require a detail request for every selected item. Pending,
failed, stale or overflow rows remain unavailable for every command. Existing
captured dialogs retain their Core revalidation rather than rebinding to the
gallery's current selection.

Preserve schema6, scanner/durability/recovery, media and catalog metadata,
cache containment/parsing, prior viewing/external actions and all deployed
outputs. Core ownership is allowed only if justified by the reviewed design;
do not edit metadata mutators, scanner or workflows to force CI. A frozen
worker smoke is justified only for a changed packaged runtime; preserve the
six prior smokes. Root recorded a private baseline of 250 tracked files and
15 outputs before these documents.

Coordinate meaningful tests with [Task39](39-gallery-filters-acceptance.md).
Root alone executes reviewed generated native acceptance and publishes a
draft PR after privacy/preservation and [Task40](40-gallery-filters-review.md)
clearance. Finish with actual current-head relevant hosted checks and Windows
test summaries. PR merge and deployed-binary replacement remain separate.
Full query grammar, new sort controls, configurable keymap, title/description
fields, backup/restore, watching, ICC, AT, native other-platform and release/
performance qualification remain outside this bounded scope.

## Requested pause checkpoint — 10 October 2026

Sol completed the current focused B2b regressions and stopped. The final app
SHA256 is `df867657b8c0a29894388c0eab5d8186873cb0ca1b09fc82d88f01128448ea0e`;
the new UI test SHA256 is
`3fd36fe644d7119111256f50804c0ba564914762e44efdf7de9fa1f8b7847780`.
Attempt 14 passed 15/15 with stable source hashes and a clean log. Task40's
independent focused review found no remaining code finding, but holds B2b
acceptance and permission to begin controls. Passing gateway 17/17 and
integration 4/4 runs apply to unchanged inputs; the earlier Qt prototype
5/5 run predates the final collection-dispatch correction.

Resume first coordinates Luna ownership of the demonstrated bounded timing
updates in the existing curation, bulk-curation and collection tests. Keep
their substantive assertions and failed diagnostics, then run affected checks
against frozen source and seek B2b clearance. No timing migration, new controls,
broad suite, native/build/publication work or deployed-output replacement
starts during the pause. Existing prewindow CLI schema initialization remains
synchronous and outside the activated GalleryWindow off-GUI read claim.

## Resumed timing gate and proposed controls scope — 10 October 2026

The user resumed. Luna owns the demonstrated timing migrations in
`test_curation_ui.py`, `test_bulk_curation_ui.py`, `test_collections_ui.py`
and the shared bounded wait helper. Runtime remains frozen. Preserve original
identity/order/revision/refusal and media/catalog assertions, capture unexpected
Qt callback failures, and finish gateway ownership before fixture cleanup.
The collection close test must first reach its actual populated collection
and mocked dialog. Its rival-removal hook may move from synchronous rank to
the real async rank callback, with explicit test-only page eviction to preserve
the rank-before-later-page race. No runtime defect is inferred from an unmet
async test precondition. Affected frozen-source results and independent review
are required before Root releases controls.

The proposed next implementation scope is only `prototypes/qt/app.py` and
the new `test_gallery_filters_ui.py`; existing Core query, gateway and operation
registry APIs appear sufficient. Keep control draft distinct from published
query. Widget edits, including duplicate choice, never auto-apply. A separate
bounded gallery-source picker never changes scan target or enumerates source
issues. Atomic Apply validates the complete captured candidate; Clear removes
all facets and digest while preserving collection/order. A successful Apply
clears row selection, detail/action targets and old restore continuations,
without stealing keyboard focus. Failed candidates remain visibly editable,
including a deleted selected ID, while any restored prior view obtains a fresh
token; never silently turn an unresolved/stale picker into All.

Tag/entity/source pickers replace one bounded page at a time, use keyset More,
and retain epoch/cursor guards. The shared taxonomy slot can supersede the
other picker; canceled controls must leave loading truthfully and permit retry.
Show incomplete/oversized lookup refusal and refine-prefix guidance, including
an unsafe continuation boundary. Preserve oversized user input visibly and
refuse it rather than truncating through a widget maximum length. Return first
chooses a highlighted picker suggestion; ordinary filter Return applies.
Escape resolves picker state first; existing gallery/dialog shortcuts retain
their context. Cover canonical aliases/categories, all-facet AND, valid zero,
deleted IDs, collection/digest, late replies, focus and source-I/O separation
with generated tests. This is a reviewed planning boundary, not release to
edit controls or claim acceptance; any API gap or old-test interaction change
requires a separately recorded concrete need.

The first migrated curation runs preserved a substantive failure: after editing
captured asset A while the gallery selection moved to B, the async saved
continuation attempted to restore A. Root releases only the relevant captured
continuation in `app.py` and focused new UI regressions: preserve B by ID and
selection epoch through the fresh generation, or clear if it is no longer
eligible; never restore the older dialog target over later user input.
Async reload also overwrites terminal save/no-change/undo/error feedback with
the generic loaded message. Preserve the original terminal outcome alongside
refreshed values, distinguish uncertain write outcomes from read failures,
and retain manual reload and closed-dialog ownership. Do not replace the old
test's persistent feedback assertion with a transient saved-event assertion.
Luna may continue owned timing edits, but evidence runs require a coordinated
fixed-source hold. Controls, Core service edits and broad checks remain gated.

The subsequent affected run passed curation and the existing Qt prototype,
but retained failing bulk/collection diagnostics. Root permits the concrete
bulk test adaptations: await the async history dialog, preserve fixture-correct
changed counts, establish a fresh view after deliberate external test writes,
and expect conservative worker outcome/reload wording instead of asserting
that an opaque service exception proves rollback. Preserve exact unchanged
database, captured revision, stale-preview and no-success assertions; hold
Core monkeypatches through actual worker completion.

Collection source review additionally found that list publication blocks combo
signals without reconciling the displayed base with the model or refreshing
controls, and can restore an older requested choice over later user selection.
Root releases only the relevant collection publication/selection/continuation
callbacks in `app.py` and generated ordering regressions. Later user choice
must win; created/deleted/default choices must request one fresh base generation
when necessary, with current controls and no recursive list refresh. Captured
delete/move IDs and original database/order assertions remain mandatory.
These corrections do not release filter controls or unrelated Core changes.

The next affected run exposed lost bulk multi-selection after an uncertain
mutation outcome and explicit recovery refresh. Preserve the existing loaded
member selection contract: Root releases guarded restoration of captured loaded
IDs in `app.py`, with fresh-generation/token checks and a user-selection epoch
that prevents an older continuation replacing later choices. Add focused new
UI regressions without changing Core mutation semantics. Keep unknown outcomes
truthful and require refreshed rows before actions become available. Remaining
history and collection failures must be classified against actual worker
completion; bounded timing corrections retain original database, ordering and
selection assertions. Filter controls remain held until compatibility and
independent review pass.

Independent review identified a second bulk compatibility defect: a delayed
history-list reply reselects the group captured before a later user choice.
Root releases a narrow dialog choice-epoch/current-ID guard and a delayed-list
regression. Preserve later group choice and captured undo targets; do not
serialize the acceptance test to conceal the race.

The 11 October independent review of the 22-test checkpoint found an Apply
overlap gap: write completion can arm the older bulk selection after a later
explicit filter Apply. Guard restoration with the write-intent query/choice
epoch, keep the latest requested predicate and a fresh post-write snapshot,
and prove final selection/detail/action targets remain clear using a delayed
actual-worker regression. This narrow correction does not release controls.

Attempt 9 exposed a valid rapid-write overlap: the next bulk write can capture
an empty selection while the previous restoration is still loading. Root
releases bounded carry-forward of the original selection intent across own
writes under unchanged query/collection/user-selection epochs, with explicit
Apply, later choice, replacement and close invalidation. Preserve the old
rapid-write test and prove the overlap through an actual worker regression;
do not add intermediate waits that conceal it or automatically retry an
uncertain write. Final result waits may await exact restored rows and details.

Attempt 10 passed 27/28 and exposed explicit selection clearing while the
previous rank restoration remains pending. Qt emits no selection change when
an already empty model is cleared; the old continuation can then restore
focus. Root releases a narrow app-owned clear-intent observer, exempting
internal reset/clearing/atomic restore and invalidating older continuations.
Preserve the old history test clear timing and add a held-rank clear-on-blank
regression. Do not conceal this case with an extra clear or a wait that makes
the original action occur only after restoration finishes.

On 12 October, the frozen B2b app `8831de06…` and generated UI suite
passed 26/26; the reviewed affected legacy quartet passed 28/28 (Luna
attempt 13). Independent review clears this prerequisite for controls
development only. Root releases Phase C edits to `app.py` and the existing
new `test_gallery_filters_ui.py`: separate draft/published/latest candidate,
atomic Apply/Clear, bounded canonical tag/entity and independent gallery-source
pickers, explicit keyboard/focus handling and generated contract checks.
Current query/gateway/registry APIs remain unchanged unless a concrete gap
receives a separate scope decision. Existing test interaction changes require
a demonstrated Apply/source-picker need; no blanket rewrite is released.
Other six Qt suites, broad acceptance, native/package/privacy/current-head
CI and draft publication remain pending, and outputs remain unchanged.

Phase C independent review releases narrow canonical-feedback layout corrections
and candidate-failure restoration reconciliation when a captured dialog mutation
interrupts the queued restoration. Preserve newer valid Apply intent and prove
the held-restore race through actual-worker regressions. Luna may migrate the
six remaining legacy Qt suites using bounded readiness and actual cleanup, plus
the demonstrated curation/workflow explicit Apply interactions. Original ordered
IDs, revisions, cache and captured-target assertions remain mandatory. No suites
run while functional source is mutable; full acceptance remains held.

The bounded affected retry exposed a real startup ordering race: the initial
Apply can cancel a constructor-submitted legacy source-list read and leave
the scan-source control empty despite an actionable gallery. Root releases
startup sequencing in `app.py` and an actual-gateway generated regression.
Publish already validated source records, submit initial Apply, then request
initial collections; preserve explicit scan targets and terminal root refusal.
No Core/gateway API changes or longer-wait workaround is released. Seventh
packaged-smoke source and a private native helper are also in independent
review; neither source preparation establishes frozen/native acceptance.

Two targeted legacy metadata cases exposed presentation/continuation gaps while
retaining exact captured-asset assignments. First, a canceled old legacy read
overlaid terminal saved feedback; the reviewed metadata-only status guard and
real gateway regression passed in the 42-test focused receipt. Real read
errors and mutation outcomes stay visible. Next, captured-A writes reset the
later gallery focus on B without restoration. Root releases a metadata-owned
bounded focus continuation, fresh generation/token and choice guards, including
rapid own writes and explicit Apply/Clear/later-choice cancellation. Never
retarget the editor or reuse an old revision for a command. The old final B
detail identity assertion must pass, rather than being removed. Core/gateway
semantics and package/smoke helpers remain unchanged.
