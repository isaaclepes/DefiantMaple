# Gallery filters — acceptance protocol

Status: staged acceptance for Task 38. Checkpoint 1 cleared the frozen design
`2d8d25c2c9206608422cc5c48419dffb1ee57d1eeee2d38b57e8f8802a24b518` on
8 October 2026. The reviewed Phase A, B1, B2a and B2b source/test pairs passed
their bounded gates. B1's helper was dormant during its focused gate and is
now consumed by the reviewed B2b GalleryWindow integration. Phase C's reviewed
control tests passed 48/48, and the local full Qt discovery passed 170/170.
The Core discovery passed 274/274 using the repository workflow's warning
mode. A separate stricter local Core run with warnings promoted to errors had
one existing `sqlite3.connect()` deprecation-warning error; both results and
their exact modes are recorded in Task 39. The native generated-fixture run
passed 20/20 on the unlocked local Wayland desktop with zero source-path I/O
and unchanged catalog/source/cache snapshots. The visible-gallery capture stays
private because its captions include generated filenames. Root reviewed the
five path-free controls; the closed-schema result candidate awaits the final
publication privacy check. A local Linux one-file build and its frozen smoke
checks passed; hosted cross-platform CI and completion of the filter slice
remain pending.

## Frozen local build observation

The reviewed Linux x86_64 one-file build completed in 305.534 seconds and
produced a 50,933,248-byte artifact. Its offscreen benchmark used 100,000
placeholder catalog rows, reported 1,030 ms startup, 140 MB first-grid RSS,
149 MB RSS after scroll, and 35/59 ms median/p95 query publication. All seven
frozen package smokes passed, including the gallery-filter and gallery-worker
smokes. This is a single local observation: placeholders avoid image decode and
disk thumbnail I/O, and offscreen timing does not measure compositor
presentation. It does not qualify the SDD's real-preview performance budgets,
other platforms, or hosted CI. The binary and full metrics receipt remain in
private work evidence.

Keep all mapped requirements Partial and recovery requirements Not Started.
This protocol does not authorize user-media access, a production-catalog
query, a backup/restore drill, a new query language, or a release claim. PR20
comparison evidence is historical and does not exercise tag/entity filtering.

## Reviewed generated evidence

The local native attempt produced path-free controls for the source, tag and
entity pickers and the Apply/Clear actions, plus a closed-schema JSON result.
Root reviewed the controls. The gallery widget capture remains private because
its generated filename captions are test data. The public evidence copies are
[source picker](evidence/gallery-filters/source-picker.png),
[tag picker](evidence/gallery-filters/tag-picker.png),
[entity picker](evidence/gallery-filters/entity-picker.png), [Apply](evidence/gallery-filters/apply.png),
[Clear](evidence/gallery-filters/clear.png), and
[the native result candidate](evidence/gallery-filters/native-linux.json).
They show generated placeholders and the 20 declared cases only. They do not
measure memory, performance or thumbnail behavior, or qualify another OS.

## Requirement scope

This increment adds one optional canonical assigned tag and one optional
canonical assigned entity to the existing literal path/state/source/media/
rating/favorite filters. All selected facets compose with AND semantics.
Taxonomy aliases resolve to the same canonical ID; entity category
disambiguates identical names. A selected taxonomy record that exists but has
no assignments is a valid zero-result query. A deleted/unresolvable selected
ID is a visible stale-filter refusal and must not broaden the query. There are
no implied descendants, multi-value OR/NOT, fuzzy search, implicit taxonomy
creation, schema migration, or Phase 2 query grammar.

Keep the current deterministic ordering: collection position then asset ID in
a collection, otherwise discovery order then asset ID. Applying a successful
new view clears current index, multi-selection, detail and action targets; it
does not select row zero. Previously captured dialogs retain their captured
asset identity and existing stale/refusal behavior. Filtering is catalog-only:
it does not scan, stat, resolve, open or mutate source media, and it does not
write catalog rows, taxonomy, collection membership, source state, published
cache entries or deployed outputs.

Scope maps directly to `FR-UX-005` and bounded parts of `FR-UX-003`,
`FR-UX-006`, `FR-UX-010`, `FR-META-002/003`, and `NFR-002/007/009/015`.
The SDD basic-search list also mentions broader text/path behavior; this
increment keeps the existing literal current-path/filename search and does
not claim title/description search. Configurable shortcuts, full
keyboard-only use, AT/screen-reader qualification, scaling, HiDPI, all sort
fields, other desktop platforms, and complete Phase 1a acceptance remain
outside scope. Keep `FR-UX-003/005/006/010` and linked NFR rows Partial.
`FR-RECOVERY-001`–`005` remain Not Started.

## Generated fixture

Create a new disposable schema-6 catalog and generated-only media paths. Do
not scan any directory. Insert a small fixed set of assets with distinct
stable IDs and distinct expected query sets, including:

- two registered sources, one standalone/null-source asset, and catalog
  entries whose last-observed source states include paused/offline/missing;
- all six supported entity categories, two equal entity names in different
  categories, at least two canonical tags, one alias, and a parent/child tag
  pair demonstrating that no descendant is implicitly included;
- single and combined tag/entity assignments, plus assets with no assignment
  to a selected existing taxonomy ID;
- rated values across 1–5, a NULL/unrated row, favorite and non-favorite
  rows, supported/other media MIME values, and duplicate digests;
- one manual collection with a nontrivial member order, including rows hidden
  by different facets;
- literal paths containing generated percent, underscore, backslash, Unicode
  and HTML-like characters, plus an indexed row with explicit missing/offline
  disposition.

Use generated opaque IDs in private raw receipts only. Public values should be
stable fixture labels such as `asset-alpha`; no private catalog rows, absolute
host paths, user IDs, or user media may appear in public derivatives.

## Staged gateway and GUI acceptance

The historical cleared Phase A pair added only the dormant serial gateway and
its focused tests. Its exact attempt 13 result was 17/17 in 0.702 seconds under
Python 3.14.7 and PySide6 6.11.2; hashes and private manifest/log are recorded
in [Task 39](tasks/39-gallery-filters-acceptance.md). Later gateway changes
require their own evidence. This historical test exercised gateway
infrastructure, not the app. It does not activate the UI or establish filter
acceptance.

The Phase A gate tested real SQLite rollback-journal contention on a generated
on-disk schema-6 catalog:
hold an established gateway SHARED read, dispatch a Qt review-key action and
representative existing service writes, and confirm a Qt event-loop heartbeat
continues while those commands are pending. A mutation intent must invalidate
old row/action targets before dispatch; verify old targets remain
non-actionable while the writer is pending or later refuses. Confirm the
gateway releases its read transaction before invoking the existing Core
service connection. Exercise close while a service write is dispatched: close
must retain gateway ownership until the opaque call actually returns, then
close the worker-owned read connection and finish. Do not claim an active
opaque Core write is cancelable, capped by a two-second deadline, or size
bounded. Existing Core service lock/wait behavior remains a separately
qualified legacy limitation. The lock path uses a
generated rollback-journal catalog, a gateway read held while a
`curation.set_curation` write queues, and a Qt heartbeat; a separate direct-SQL
external-writer test checks the rollback lock and next-snapshot change. Tests
also cover queued-read invalidation and ownership through dispatched-write
completion. They do not exercise GalleryWindow or real GUI target disabling,
and do not cover metadata, collection or source service APIs. See [Task 39](tasks/39-gallery-filters-acceptance.md)
for the bounded audit; the manifest and logs remain in the private wrapper.
No broad-suite or native result is implied.

Phase B1's reviewed dormant Core query module and focused PySide-free tests
passed attempt 7: 11/11 in 1.988 seconds under Python 3.14.7. The query/test
hashes are `d776645435d468e9972ac046ebbfe7384519c0541b31ea4a97b58882b0e29b58`
and `fff9e53e1fae259b53f4950196124084de7acb42d52859cb9c6e7e17c2d50909`; the
log SHA-256 is `7a0a7abfb2ee58f03d3b713596c9f758824e6a341778c06b803eac9ea2245159`.
This covers focused query semantics, coherent Core snapshots and bounded
projections, not GUI integration or performance. Earlier attempts remain
diagnostic; actual A `ReadContext` integration is deferred to B2 Qt tests so
Core tests do not depend on PySide6.

**B2a is released only for two gateway fixes and actual Qt integration tests.**
A's prior 8,192-node reply cap cannot carry a B1 page: 19 fields per row across
256 rows needs at least 9,984 mapping/key/value nodes. Test a real 256-row B1
reply while preserving byte, depth, shape and oversize refusal limits. A
persistent SQLite reader can also remain on the old file after atomic catalog
replacement while path stats see the replacement; compare the live path with
the connection's original file identity and refuse/reopen with a new reader
incarnation. B2a's new focused test file is
`prototypes/qt/tests/test_gallery_query_gateway.py`; exercise B1 with A's actual
`ReadContext`, a real full-page reply, overflow refusal, and atomic-replacement
identity refusal there. Existing `app.py` and GalleryWindow remain unchanged;
B2a does not wire the query path or activate controls.

B2b's released integration scope is the closed module-level registry
`prototypes/qt/gallery_operations.py`, the full inventoried GalleryWindow
catalog read/write migration in `prototypes/qt/app.py`, focused tests in
`prototypes/qt/tests/test_gallery_filters_ui.py`, and optional bounded waits in
`prototypes/qt/tests/gallery_wait.py`. New query/read generations invalidate
older page/rank/detail replies; mutation intent marks current action targets
stale and disables them before write dispatch. B2b's generated fixtures must
exercise the exact facet, snapshot, page/rank/detail, pending-row, stable-target
and Apply/Clear assertions below. Include both WAL and rollback-journal
fixtures for coherent reads and changed-view detection. Under rollback-journal
contention, verify the heartbeat while representative review and service writes
are pending; verify mutation-intent invalidation, exact existing service
success/refusal, a fresh gallery generation, and worker-owned close completion.
Do not infer a whole-application responsiveness guarantee from the heartbeat.
The B2b code/test gate is cleared for its scoped integration. Phase C filter
controls passed their reviewed 48/48 focused suite, and the generated native
Wayland attempt passed 20 declared cases with source-path access blocked after
startup settled. The gallery capture remains private; the path-free controls
and closed result candidate are linked above. Keep legacy source-management
and taxonomy-editing service limits separate from new gallery-read bounds.


### Existing Qt-suite compatibility diagnostics

Attempts 7 and 8 of the four-file named-wait migration are immutable private
diagnostics, not passing acceptance. Attempt 8 ran 28 tests (21 pass, 7 fail)
on a stable app/UI pair; its exact hashes, raw log, module counts and
individual pending compatibility fixes are recorded in [Task 39](tasks/39-gallery-filters-acceptance.md).
The outstanding curation, history-choice, bulk-selection, empty-collection
and paged-neighbor boundaries retain their original identity/order/database
assertions. A later coordinated run requires Sol's frozen runtime plus root
and reviewer release. Do not treat focused module results as full Qt/Core,
native, package or filter acceptance.


Attempt 9 on the replacement freeze ran the same 28 focused tests: 24 passed,
3 failed and 1 errored. Curation (6/6) and QtPrototype (5/5) passed; remaining
bulk selection/reopened-history and collection page-boundary observations are
recorded with immutable private hashes in [Task 39](tasks/39-gallery-filters-acceptance.md).
The run is diagnostic only; no substantive assertion was relaxed, and the
bounded filter slice remains Partial pending reviewed fixes and a new frozen
acceptance run.


Attempt 10 on the replacement freeze passed 27/28 tests. The lone remaining
history assertion preserves an explicit-clear contract; review traced the
failure to a pending bulk-restore racing a no-op clear after the model reset.
Root has released a narrow runtime fix and held-rank regression. The original
test clear and refusal assertion remain intact; the bounded filter slice is
still Partial pending the new frozen pair and focused acceptance run.


Attempt 11, the final released same-28 checkpoint, passed 27/28 with one
post-undo gamma selection/detail restoration error in the history test. The
immutable run and source/test hashes are recorded in [Task 39](tasks/39-gallery-filters-acceptance.md).
The original identity assertion remains; no further retry or broader gate was
released under the user's pause. B2b and the filter slice remain pending and
Partial.


Attempt 12 is the one released same-28 checkpoint after adding the named
post-undo gamma wait. It passed 27/28; the sole error moved to the same history
test's immediate alpha editor open before selected detail became actionable.
Immutable private receipts are cited in [Task 39](tasks/39-gallery-filters-acceptance.md).
No repeat or further edit was released. B2b and the filter slice remain
pending/Partial.


Attempt 13 passed the reviewed same-28 focused quartet (curation 6/6, bulk
8/8, collections 9/9, QtPrototype 5/5) on the frozen attempt 23 app/UI pair.
The immutable private receipt is listed in [Task 39](tasks/39-gallery-filters-acceptance.md).
This is scoped timing compatibility evidence only; the other six legacy Qt
modules, full Qt/Core suites, visible/native/package gates, and full filter
acceptance remain pending. Keep mapped requirements Partial.

On 12 October, the then-frozen filter-control focused suite separately passed
40/40 in 6.300 seconds (attempt 7). This result covers that exact historical
app/UI pair and does not qualify the current Phase C source. A subsequent
seven-module legacy timing checkpoint (attempt 8) failed 79 tests with 6
failures, 7 errors and one callback traceback; its shell pipeline did not
capture Python's actual exit status. The bounded five-module retry (Phase C
attempt 9) failed 59 tests with 3 failures and 2 errors, exit 1, with stable
before/after hashes. Remaining findings concern legacy source-list readiness,
async metadata panel publication, and two post-close probes that need completed
ownership assertions without issuing a new read. Three intentional detached-
handoff ResourceWarnings were preserved. A separately authorized single
metadata case also timed out after the Core entity and selected panel record
were present, because panel feedback read `Legacy catalog task canceled`;
the narrow feedback fix made that success condition pass. The next bounded
wait then showed the original later gallery selection was lost after the async
metadata writes. This is retained as a runtime focus finding; the final
selection/detail assertion remains unchanged. Keep current Phase C
compatibility, full Qt/Core, native/package evidence and the bounded filter
slice pending; the mapped requirements remain Partial. See [Task 39](tasks/39-gallery-filters-acceptance.md)
for immutable attempt provenance and private-log hashes.

## Automated acceptance

After the source and tests are frozen, run the targeted Core/query and Qt
filter/UI tests, the one coordinated full Core and full offscreen Qt suite,
the Node virtual-grid test only if its inputs changed, and the public-artifact
privacy checker. Do not duplicate the active implementation agent's focused
checks or repeat a green broad suite without a code/test change or unresolved
failure. Archive exact command, runtime, input hashes, exit, full logs and
test totals privately.

Required assertions:

1. Each existing facet and each new canonical tag/entity facet returns the
   exact expected stable IDs. Alias selection yields its canonical ID;
   equal entity names stay disambiguated by category. `EXISTS` membership
   checks produce no duplicate asset rows. Parent/child tags do not imply
   descendants.
2. Exact useful conjunctions return the expected IDs in stable order. Apply
   publishes one complete generation only after validating all draft fields.
   Clear removes the field and duplicate predicates but retains the selected
   manual collection and its order. The explicit duplicate filter is retained
   by ordinary Apply and removed by Clear.
3. A valid zero-result query for an existing unassigned taxonomy record is
   distinct from an empty library, a stale/deleted filter ID, malformed or
   unresolved picker text, read failure, and a missing/offline source row.
   Failures retain the prior applied state and visible feedback; they never
   silently turn into All or a successful empty result.
4. Literal path matching preserves the existing case/wildcard behavior and
   escapes `%`, `_` and backslash. Reject control/nontext and path strings
   longer than the declared 512 Unicode code points before changing the
   applied state; never silently truncate. SQL-looking and HTML-like values
   remain data and render literally.
5. Count, initial page, subsequent pages, stable-ID rank and detail use the
   same immutable predicate and ordering. Exercise a generated 100k-row
   catalog for bounded paging/ownership, not as an adopted SDD latency or
   decoded-media performance target. Test a coherent snapshot across count
   and page, stale generation replies, row placeholders, replacement refusal,
   cancellation of active reads, close, locked catalog and actionable read
   failure. A dispatched Core service write is allowed to run to completion;
   gateway ownership must survive close until actual worker completion.
6. A filtered ordered collection retains identical membership and order.
   Successful Apply/Clear clears current selection/detail/action identity and
   never retargets by old row number. Previously captured viewers/commands
   retain the original stable ID or refuse; they do not rebind to a new row.
7. Distinguish keyboard text editing from gallery review actions: `Ctrl+F`
   focuses literal path input; Return and Apply submit the same draft; Escape
   first dismisses an unresolved picker without changing the applied view;
   Tab/Shift+Tab reach controls in logical order. Digits typed into search or
   picker text remain text and do not mutate review state. With gallery focus,
   arrows and `Ctrl+Space` change only intended selection; review digits are
   enabled only in the gallery. If acceptance explicitly tests a digit review
   action, bracket it as a deliberate generated-catalog mutation and verify
   only the captured row changes. Do not count it as read-only filter
   preservation.
8. Verify accessible names/roles/states for the controls used, visible
   focus, and non-color-only pending/invalid/empty/missing feedback. QtTest
   events do not establish human keyboard-only usability or AT semantics.


## B2b integration instrumentation and privacy gates

Predeclare these checks for the focused UI integration tests and later visible
helper; they add evidence gates without broadening the product requirements:

9. Instrument the complete design §56 GalleryWindow catalog read/write
   inventory. Treat startup separately: instrument startup catalog SQL and
   confirm it runs off the GUI thread. The unchanged startup
   `assert_outside_sources` containment validation legitimately resolves
   configured roots; keep it protected as a separate legacy operation. Once
   startup containment and legacy source-list/health work have settled,
   instrument count/first-page, page, rank, detail, picker, selection, refresh,
   review-key and captured metadata/collection action paths. Assert each
   catalog request dispatches through its fixed closed-registry operation and
   record the worker thread that executes it. Attach SQLite trace/authorizer
   observers to opened catalog connections and a GUI-thread connection guard;
   assert no catalog SQL or synchronous wait/fallback occurs on the GUI thread.
   Assert every returned model/widget mutation occurs on the GUI thread. Do
   not omit an inventory entry just because its result is cached or a failure
   path is taken.
10. Prove bounded gallery/query operations and the new source picker do not
    touch source media or invoke scan-target/source-health enumeration. After
    startup containment and legacy source-list/health work have settled, use
    unique generated placeholder source paths and scoped traps for
    open/stat/resolve/list/scandir operations on those paths, with call
    counters; require zero accesses in this bounded-operation window. Guard
    scanner and source-management entry points against invocation by the
    bounded picker/filter path. Do not weaken or count the protected startup
    containment validation as a gallery query. Bracket generated fixture
    setup and intentional thumbnail/viewer I/O separately, and snapshot media
    bytes plus source/catalog rows around the bounded read-only scenarios.
11. Keep fixtures synthetic and generated. Preserve opaque IDs, raw database
    rows, absolute paths, full logs and host details in private receipts only.
    Directly parse every new public JSON, run the repository privacy checker
    against the final staged set, and confirm the published derivative has no
    raw IDs or machine paths. The native helper may capture only the intended
    app canvas/controls through reviewed direct capture calls; do not use full
    window or desktop captures as public evidence. Include direct before/after
    catalog and generated-media snapshots and verify worker cleanup.
12. Record the visible helper's exact source/runtime/fixture hashes, focus
    establishment, key/modifier sequence, and completion generation. Wait for
    actual count plus first-page publication before measuring initial load;
    after a review write, wait for the reported result and refreshed generation
    before timing or checking rows. Keep timing observations bounded to the
    measured operation and do not imply whole-app latency or human/AT use.

The cleared design's candidate bounds are not product performance claims: 256-row
pages, 24 cached pages, picker pages of 64, one active request plus one latest
pending filter generation, 50 ms SQLite busy timeout, cooperative two-second
bounded read refusal and 512-code-point literal text limit. These apply to
the new gateway read path only where the cleared design specifies them. They
do not bound or cancel active opaque Core writes or retrofit separate legacy
service calls. The two-second value is not a universal wall-clock guarantee
against kernel-blocked I/O. Do not claim RSS or media-scan performance from
row-count/page tests.

## Visible generated acceptance

Root alone executes the visible helper after B2b and filter-control code/test
reviews, independent helper/privacy review, and an unlocked-desktop preflight.
Run only on the generated catalog and generated fixture paths. Record exact
helper, source, runtime and fixture
hashes, host/desktop/backend, display geometry, and before/after state. The
native stages are:

1. Establish the initial generated gallery and expected ordered IDs; show
   filter controls are exposed, named and reachable. Record any programmatic
   focus setup separately from actual key events.
2. Use the filter control through the declared keyboard path: focus literal
   text with `Ctrl+F`, enter a generated filename/path term, apply with Return,
   then clear with the explicit Clear control. Apply an alias-resolved tag
   choice and a category-qualified entity choice and verify the visible
   result states and expected stable IDs.
3. Apply a multi-facet conjunction and a valid zero-result filter. Show the
   empty-library, stale-filter and missing/offline states separately if the
   fixture provides them. A valid zero-result count must not be described as
   source loss. Check Escape on unresolved picker text preserves the prior
   applied view.
4. Traverse Tab/Shift+Tab through filter, Apply/Clear, status and gallery.
   Use gallery arrows and `Ctrl+Space`; verify focus and no asynchronous
   result steals it. Type digits into a focused text editor and verify no
   review mutation. If a focused-gallery review digit is used, record its
   intentional one-row catalog delta as a separate stage.
5. Capture selection or a viewer target, change filters/refresh, then verify
   the captured stable ID remains or a stale action refuses. No action may
   target the item now occupying an old row number.
6. Close the generated app and confirm only its owned workers/windows finish.
   Preserve raw logs/captures; use direct app-only generated captures for
   public evidence. No real editor, shell, source scan, external association,
   user-media path or personal library is involved.

Before and after read-only stages, compare source-media byte manifests,
catalog physical/logical snapshot, source rows/health, taxonomy assignments,
collection membership/order and relevant cache manifests. Setup and any
explicit generated review-key mutation are bracketed outside the filter
actions. The expected read-only filter result is unchanged catalog/source/
cache state. Recheck after app close; do not claim that an idle scan was run.

Keep private raw paths, UUIDs, full rows, desktop details and full captures in
private wrapper evidence. Public JSON must contain generated labels and
minimal scoped facts only; screenshots must be byte-identical direct reviewed
app-only captures and must not expose catalog paths, source paths or raw
records. Directly parse and privacy-check new public JSON, inspect each image,
then run `python -m scripts.check_public_artifacts` over the final staged set.
Record checker coverage limits rather than treating it as universal.

## PR20 comparison closure and CI expectations

PR20 was independently cleared with 27/27 exact-head automatic checks at
`966c9a46e43ed249436b76148457091aed517c6d` / tree
`e872140902d6a78ea856763c3948b7b5835da716`: Core push 12/12, Core PR 12/12,
and Qt PR 3/3. All five Windows Core invocations ran 263 tests (260 pass,
three named capability skips: POSIX FIFO creation, Windows-unavailable
POSIX resource controls, and Windows open-handle source-root rename). The
Windows Qt job also ran 263 Core tests with those skips and 101 Qt tests (100
pass, one POSIX partial-frame-injection skip). The six-smoke Qt package and
artifacts passed on Linux/macOS/Windows. No fresh PR20 Tauri run occurred:
the path-filtered workflow did not match its paths; exact unchanged prior
Tauri evidence is labeled by original PR19 run, not a PR20 pass.

PR20 merged at `0af8ba5108af4727679e76bc60e6a71918ef5994` with the same tree
and ordered parents main `0f7082a2e01afccfdf4b81ec2145dc8a6572287e` then PR20
head `966c9a46e43ed249436b76148457091aed517c6d`. Its automatic main Core push
run [37697431239](https://github.com/isaaclepes/DefiantMaple/actions/runs/37697431239)
is now audited: 12/12 jobs succeeded (six OS/Python test jobs, three soak,
three scan-cost-profile). Windows Python 3.11 and 3.13 each ran 263 tests with
three named platform/host skips; the public-artifact privacy checker passed
on both. Exact skip reasons, per-log hashes and private decoded/structured
receipts are retained outside the repository. See the public
[Actions run](https://github.com/isaaclepes/DefiantMaple/actions/runs/37697431239)
and [Task 39](tasks/39-gallery-filters-acceptance.md) for the audit summary.
This closes only the merge-main Core audit; it is not gallery-filter, Qt, or
fresh Tauri acceptance evidence.

For the future filter PR, derive expected current-head workflows from the
actual changed paths. Core tests in `tests.yml` trigger on push and PR
unconditionally (12 jobs per event: OS/Python test matrix, plus soak and
profile matrices); Qt runs three OS jobs on a PR if `prototypes/qt/**`,
`tests/**`, `defiantmaple/**`, `benchmarks/**`, or the Qt workflow changes.
The Tauri PR workflow runs three OS jobs if a changed path matches
`prototypes/tauri/**`, `benchmarks/**`, `defiantmaple/**`, or its workflow.
Because Task38 may require a new `defiantmaple/gallery_query.py`, a fresh
Tauri workflow is expected if that file is in the published diff. If runtime
design safely keeps the implementation Qt-only, Tauri may be filtered out;
then record only exact-byte prior Tauri/Node evidence as reuse, not a
current-head pass. Do not alter unrelated files to manufacture a workflow
run. Inspect Actions runs by exact `head_sha` for both push and PR, then
inspect actual Windows test logs, named skips, final job conclusions, frozen
package gates and artifacts.

## Adjacent recovery boundary

`FR-RECOVERY-001`–`005` cover consistent backup, isolated restore with
failure preservation, scheduled snapshots/retention, media omission reports,
and restoration of IDs/relationships/configuration. The v1–v3 migration
backup is not user-facing restore. Keep backup/restore out of filter tests and
native stages; it needs its own generated backup/source fixtures, corruption
and restore-failure scenarios, verification before activation, privacy review
and tracker task.

## Acceptance status

This protocol is staged. Phase A gateway evidence does not complete the
bounded filter slice. Passing Phase A and Phase B implementation reviews,
tests, generated visible evidence, preservation/privacy, final current-head
CI and scoped independent review are all required before the bounded slice is
recorded. Any successful bounded result leaves the broader FR/NFR rows Partial.
