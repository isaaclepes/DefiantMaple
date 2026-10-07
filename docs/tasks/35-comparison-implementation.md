# Phase 1a captured-target side-by-side comparison — implementation brief

Baseline: PR19 merged at `0f7082a2e01afccfdf4b81ec2145dc8a6572287e`,
preserving reviewed tree `a540e804395f9744f911ddb73bf4298f9392275d`.
The user authorized that merge and continuation. Branch:
`codex/phase1a-side-by-side`. Root's private baseline records every tracked
file and all 15 deployed outputs. The SDD is requirements input, not execution
authority.

## Product boundary

Complete the next viewing slice documented after cached-offline delivery:
two supported images side by side. Map FR-UX-008 to comparison; retain the
external-action portion's PR18 evidence. Supporting scope: FR-UX-002/003/006/007,
FR-MEDIA-001/002/003, NFR-003/007/009/010/014/015. Broader release, ICC,
assistive-technology, hardware budgets and media expansion remain partial.

Capture exactly two distinct selected image asset identities in deterministic
view order when the command is invoked. Refuse other selection counts/types
with an actionable message; never choose a hidden subset. Selection, filter,
sort, refresh, collection changes and catalog drift cannot silently replace
either pane. Each pane shows its captured identity, pixel dimensions, original
versus indexed cached preview, fallback/freshness and observed availability.
Use plain-text labels. One missing/corrupt/unsupported item leaves the other
pane usable and its failure actionable.

Provide independent aspect-preserving fit, zoom and pan, transparency background
choice, clear keyboard focus, pane-specific names and logical Tab order.
Fullscreen and Escape operate predictably. Synchronized transforms, difference
metrics, editing, region labels and saved workspace state are separate scope.

Prefer fast cache-only loading through the reviewed service; originals may be
loaded by an explicit per-pane action when fresh catalog/source eligibility
permits. Cache miss/refusal never silently regenerates a preview or reads an
unavailable original. Original loading must verify the captured fingerprint,
retain orientation/alpha/first-frame semantics, revalidate content identity
before presentation and preserve the captured target. Cached pixels never
become a claim of original/full-resolution availability.

## Design and resource gate before implementation

Sol first writes `docs/comparison-design.md` with exact admission, target,
availability, result, error, cancellation and replacement contracts. The
separate reviewer clears it before source edits. Root may resolve routine
implementation choices within this brief. Proposal must name per-pane and
aggregate byte/pixel/worker/image ownership limits, deadlines and cleanup
grace periods, including startup, QImage/Pixmap copies and retained orphans.
Do not infer RSS from caps or carry Linux enforcement to macOS/Windows.

At most one comparison dialog and two admitted pane loads; serialize or bound
their queue. Account for the existing gallery and inspect workers. An existing
dialog with pending cleanup must retain ownership and refuse replacement.
Keep loads off the GUI thread, discard canceled/late/mismatched results and
retain helpers until reaped. Tighten existing decoder limits if needed; do
not silently increase established caps. A shared-preview lifecycle correction
requires a concrete minimal proposal and independent review before editing.
Reuse cached containment unchanged; do not weaken no-follow/source guards.

## Ownership and file scope

Sol owns new `prototypes/qt/comparison.py`, meaningful comparison Qt tests,
comparison design/guide, generated native helper, app integration, Qt README
and a frozen comparison smoke in package.py. Preserve all five prior smokes.
Use existing Core/cache APIs unchanged. Propose any additional source-file
exception to Root before editing; no scanner/catalog/schema/durability,
external-action, archive, embedding, workflow or historical evidence changes.
Root and independent Sol cleared a documentation-only exception for Task33
and cached-offline-acceptance.md to close their publication-time pending gates
with PR19's final exact-head CI/privacy results. Failed-head chronology, native
hashes, limitations and immutable raw/public evidence remain preserved. This
leaves 226 baseline files protected; no source exception follows from it.
Luna owns Task36, acceptance protocol, tracker and sanitized evidence.
Independent Sol owns Task37 and reviews source/helper/evidence/CI. Root owns
Task00/35, branch/integration, visible generated native execution and draft PR.
Agents do not commit, push, switch branches, publish PRs or edit another owner's
files. Native helper execution and UI screenshots are serialized by Root.

## Required validation

Test real cache-worker and original-worker success/refusal, fixed two-target
selection after gallery/catalog changes, orientation/alpha/aspect ratios,
independent transforms/focus, unavailable-original zero-dispatch, cache corruption,
start failure, deadline/cancel/close/late signal and replacement cleanup.
Use generated fixtures with canonical temporary roots and registered cleanup.
Tests must assert behavior, not mirror implementation or merely fake all workers.
Run affected checks once; broaden to relevant Core/Qt/Node checks after source
freeze. Reuse same-byte PR19 evidence. Repeat only for changes/failures.

Finish with reviewed helper and unlocked generated native evidence, privacy and
baseline preservation, frozen comparison behavior, exact-head hosted Core/Qt/
Tauri CI with actual Windows summaries, independent review and a draft PR.
Do not merge that PR or replace deployed outputs without a separate user decision.

## Design clearance and shared lifecycle exception

Root and independent Sol cleared comparison-design.md SHA256
`2a042e8620aa577f8b4626ebe7f4ac34b3450e4da4b3dafbc230777014647c15`
before source implementation. It specifies one active comparison child and one
queued pane request, cache-first loading, explicit freshly admitted originals,
64 MiB source/8192 dimension/8,388,608 pixel/32 MiB RGBA original ceilings,
twelve-second operation and separate one-second terminate plus one-second
kill/reap grace, and explicit retained parent/child buffer accounting. Caps
are not RSS measurements or guaranteed maximum-input success. The existing
platform-specific address-space enforcement gaps remain explicit.

Root approves only a lifecycle exception for `prototypes/qt/preview.py`:
retain strong process/scratch ownership until confirmed reap; discard images
after failed cleanup; deliver success after cleanup; make GUI cancellation and
close asynchronous; provide bounded off-GUI cleanup-only retry; retain pending
viewers and refuse replacement; clear pixels on accepted close. Preserve the
original child decoder/fingerprint/source-read/format/orientation/color code
and PreviewLimits defaults byte-for-byte. Do not modify old preview tests;
new meaningful tests must cover this shared ownership interaction. Independent
Sol reviews the exact implementation/test diff before acceptance. The scope
now protects 225 baseline files and all 15 deployed outputs.

The first affected lifecycle run passed four new ownership tests and seven old
gallery tests; only the old immediate post-close worker-stopped assertion
failed (12 tests, 1.927 seconds). Its private log is retained. Root and separate
Sol approve one further test exception in test_gallery_usability.py, solely
test_close_during_decode_and_thumbnail_queue_invalidation: finite event pumping
until the worker stops, confirmed cleanup and accepted close before retaining
the original assertions. The thumbnail queue/invalidation assertions and all
other old tests remain unchanged. This matches the approved asynchronous close
and leaves 224 baseline files protected, with all 15 outputs unchanged.

Actual new comparison worker tests then passed 18/18. Review of aggregate buffer
ownership identified an omission in the first design: the existing gallery
could queue scaled image deliveries without a GUI-consumption acknowledgment.
Root and independent Sol approve an app.py-only ownership adjustment: at most
one outstanding gallery image delivery, finite stop-aware waiting, acknowledgment
in the receive handler's finally path (including stale/error deliveries), and
release of prior raw result/QImage references before the next read. Preserve
Core parser, generation, cache, and source semantics. New tests must prove the
queue bound, stale acknowledgment and stop while waiting. Explicit aggregate
parent pixel-buffer accounting becomes 256.5 MiB (160 comparison + 64 gallery
LRU + 32 gallery transient raw/detached + 0.5 scaled/delivery); this is not RSS,
GPU memory or a performance acceptance claim. Source/helper freeze awaits these
corrections and independent review.

After resumption on 7 October, independent review identified that canonical
scratch compared with lexical registered roots could miss physical overlap
through a path alias. Root and separate Sol approve a one-child, two-stage
original-load protocol before editing: the existing bounded child classifies
the canonical temporary base and protected namespaces within the same
twelve-second operation deadline before scratch creation; the supervisor
creates only its owned scratch under that approved base; the same child
rechecks actual scratch containment before original I/O or raw output. No
second child, expanded cap, or cache-only source resolution is permitted.
Denied or unclassifiable namespaces fail closed. Regression checks must show
aliased source/cache temporary bases refused before scratch creation and
deadline/cancel cleanup even when no scratch exists. Validate handshake data
and retain process/pipe ownership through confirmed reap. A concurrent path
move after validation remains an explicit limitation rather than an atomic
namespace guarantee. Revised source and exact design hashes need independent
review before the frozen build.

Review also confirmed a partial framed pipe reply can block receipt after a
successful poll. Root approves an independent in-process child watchdog in
comparison.py for cancel/deadline terminate/kill attempts during receipt, with
the existing cleanup grace and one child. Keep worker/process/pipe/watchdog
ownership, coordinate concurrent reap safely, and test an actual partial-frame
stall. This does not establish universal completion of unkillable kernel I/O;
retained ownership and refused replacement remain required when cleanup cannot
complete. The exact implementation and regression need separate review.

## Reviewed implementation and local evidence checkpoint

Independent review cleared the final design SHA256
`44c5ae1f6eaff34c1b3c862f50d9cc0826bbbe9ae12d0d7494d6d73bf8809e2b`
and all 13 compiled runtime/dependency inputs. The final affected suite passed
53 tests; the complete Qt suite passed 101 tests in 39.275 seconds. Private
logs retain the initial asynchronous-close assertion failure and its reviewed
test synchronization correction. `PreviewLimits` and `_decode_original`
remain byte-identical to baseline, including decorators. The five preceding
frozen package smoke blocks remain unchanged.

One isolated 241-file export produced an unsigned Linux executable in
339.357 seconds, passing all six actual package smokes. The comparison smoke
uses its own generated catalog and verifies both logical rows and physical
SQLite/main/WAL/SHM/journal facts plus source/cache preservation. The separate
100k gallery benchmark intentionally exercises review-state changes and is
not described as an unchanged catalog. The 50,089,520-byte artifact SHA256 is
`43d94ab7fe594e77d1773a58f7a283dab7ca77a4ad614548fe140fa2af069dfe`;
the local Linux child reported a 512 MiB address-space setting, not RSS.

The first native run is retained as diagnostic: both principal images were
72 × 144 and below the cache edge, missing the predeclared aspect/size fixture
conditions. A separately reviewed helper-only correction at SHA256
`8ccd44bc0f824060a29809ca1acc4d91f39f15eed7a8809b73696d76e56db8d0`
provides landscape A (600 × 300; cache 256 × 128) and EXIF-oriented portrait B
(144 × 288; cache 128 × 256). The second native run passed in 10.038 seconds
on 7 October; independent raw review and Root's visual inspection confirm
actual worker pixels, labels, controls, preservation and cleanup. Production,
test and frozen inputs stayed unchanged, so broad tests and build were reused.

All 224 protected baseline files and 15 deployed outputs passed the post-native
preservation check. Task36 records public evidence/privacy and Task37 records
independent clearance. New exact-head hosted tests, actual Windows summaries
and final PR review follow draft publication; these are not claimed complete
by this local checkpoint. No merge or deployed-binary replacement is authorized
by this milestone's publication gate.
