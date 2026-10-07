# Phase 1a side-by-side comparison — independent review brief

Separate Sol reviews [Task35](35-comparison-implementation.md),
[Task36](36-comparison-acceptance.md), proposed design, exact source diff,
generated helper, local/frozen/native evidence, privacy and exact-head CI.
Review independently; do not author production code, commit/push or run visible
native actions. Record blockers and exact validation in this file.

Clear the design before implementation. Check exactly two immutable targets,
deterministic admission, truthful original/cache dimensions and availability,
per-pane failure isolation, safe content/catalog drift, no unavailable-original
dispatch, finite aggregate resources, cancellation/reaping/replacement ownership,
GUI-thread work, focus/keyboard/pane labels and unsupported/error reporting.
Preserve cached containment, source relation guards and all five existing frozen
smokes. No scanner/schema/catalog metadata/durability/external-service change is
implied; extra shared source edits require a reviewed exception.

Review meaningful actual-worker tests and every failure/correction. Verify
historical receipt reuse by exact hashes instead of relabeling old runs.
Independently inspect native raw stage inputs, preservation, actual QtTest
events/focus, pixels/aspect/orientation/alpha and cleanup before public derivatives.
Distinguish native observation, programmatic state, spies and inference.

Check direct JSON privacy coverage and images, original raw immutability,
baseline files/outputs, current-head checks and actual Windows summaries.
Memory/address-space flags and unsupported platform/runtime features remain
explicit; no clean-machine/ICC/AT/reference-profile acceptance is inferred.
Require a factual reviewable draft PR with limitations and no remaining blockers.
Root alone publishes; new PR merge and output replacement need a separate user
decision.

## Brief preflight — design pending

I read Tasks 35–37, SDD v0.2 §11 and the FR-UX-008 tracker row at merged
baseline `0f7082a2e01afccfdf4b81ec2145dc8a6572287e`. The SDD requires
side-by-side comparison; the external-open portion has separate prior evidence.
The private baseline lists 233 tracked files and 15 deployed outputs. The
comparison design has not yet been supplied or cleared; no source or native
acceptance is claimed here.

The current gallery supports range-counted multi-selection and a single focused
asset. Comparison admission must require exactly two selected, distinct,
supported image IDs, materialize selected indexes only after the count guard,
and capture immutable view-ordered rows rather than reuse the focused-item
action. Pane labels must distinguish requested/cache edge, displayed pixels,
original pixels, fallback and last observed source health. Neither a stale
selection nor a cache hit may relabel derived pixels as an available original.

The existing `FullImageWorker` verifies source size, SHA-256 and file identity,
but does not perform fresh catalog/source eligibility checks around decoding.
The design needs off-GUI pre-admission and post-decode content/source checks for
an explicit original load. Its 40-million-pixel per-worker ceiling also cannot
simply be doubled: account for two decoded outputs, QImage/Pixmap copies, cached
panes, existing gallery/inspect workers and workers retained during cleanup.
The design must state aggregate ownership and refuse replacement until both
old pane workers are reaped. Cached panes continue to use the reviewed
original-independent bounded service and no-follow containment unchanged.
One pane's error must not cancel or retarget the other. These are design review
questions, not findings against a comparison implementation that does not yet
exist.

## Design review — cleared for bounded implementation

I reviewed `docs/comparison-design.md` at SHA256
`15eea018efb5e18fc541898c749d9f8917e1f4bfe99c97da60755341b4fe64ba`.
It captures two view-ordered identities, distinguishes cache-only reads from
explicit originals, serializes two admitted pane loads, and sets a finite
pixel-buffer accounting model without claiming RSS. Initial review identified
three precise contracts sent to the implementation owner:

- Name the actual no-follow/pinned source-handle primitive for explicit
  originals on POSIX and Windows. The current full-image worker uses ordinary
  path open/stat, so the phrase “unchanged pinned no-follow bounded-reader
  primitives” does not identify an existing original reader. Specify bounded
  raw output, postdecode fingerprint/path checks, and refusal if safe source
  containment is unavailable. Cache-only viewing must remain unaffected.
- In the requested shared `preview.py` lifecycle exception, retain strong
  process, scratch, worker and dialog ownership after failed reap; never leave
  a `TemporaryDirectory` context while the child is live, emit success only
  after confirmed cleanup, and refuse close/replacement until an off-GUI retry
  confirms cleanup. Deadline begins before spawn and GUI cancel is event-only.
- State how revision-only metadata drift is observed and labeled. The existing
  `fresh_generation_refusal` returns only a refusal reason and intentionally
  does not reject same-content rating/metadata changes.

The owner revised the design to SHA256
`2a042e8620aa577f8b4626ebe7f4ac34b3450e4da4b3dafbc230777014647c15`.
It now specifies a new original-only `_OriginalFile` with pinned no-follow
parent and leaf handles, a 64 MiB plus one-byte input bound, second bounded
checksum after decode, fresh pathname and catalog/source checks, and a raw
RGBA handoff capped at 32 MiB. Unsupported safe containment refuses explicit
originals without disabling cache-only viewing. A separate bounded read-only
revision query supplies metadata-only warning without rebasing the target.
The shared preview exception now states strong process/scratch ownership,
`cleanup_complete` state, cleanup-only off-GUI retry, no delivered success or
accepted close/replacement while reap is incomplete, and a pre-spawn deadline.
The design is cleared for implementation; the `preview.py` exception remains
an exact source change to inspect and test before accepting implementation.
No original-reader or lifecycle behavior has been observed yet.

The corrected comparison acceptance protocol explicitly brackets generated
fixture mutation/restoration outside read-only comparison actions, separates
actual native worker observations from controlled signals/spies, and restores
corrupted cache bytes outside the reader. Historical PR19 Task33/protocol
closure wording remains scoped. The tracker still has 129 unique requirement
IDs. No comparison source, native, frozen, or hosted acceptance is claimed.

## Compiled-runtime checkpoint — isolated build cleared

The later design at SHA256
`44c5ae1f6eaff34c1b3c862f50d9cc0826bbbe9ae12d0d7494d6d73bf8809e2b`
adds the reviewed one-child, two-stage original scratch handshake. The child
classifies the temporary base and protected source, catalog and cache
namespaces before the parent creates owned scratch; it rechecks the supplied
output directory before source I/O. Typed, capped stage replies and an
independent terminate/join then kill/join watchdog cover a partial framed
reply that blocks the receiver. Cleanup retains process and scratch ownership
if reap fails. A moving namespace or unkillable kernel operation remains a
stated limit; the 12-second operation deadline is not a universal wall-clock
guarantee.

I reviewed the frozen six-file runtime/test slice and its direct dependencies.
The exact hashes and file sizes are in the private
`work/comparison-compiled-runtime-readiness.json` receipt (SHA256
`1c6aeb232911990f95c4bd32b1173328eba8ea74bebdb6dca3c55146aec17d1c`).
The affected comparison, gallery and cache Qt tests passed 53/53. The sixth
package smoke's exact fixture/preservation block also passed when directed to
the source app: generated cache and original checks, an unavailable-original
refusal, confirmed cleanup, Linux 512 MiB address-space limit application,
and unchanged logical plus physical SQLite and media/cache snapshots. This
was a source-only rehearsal, not a frozen executable run. The five preceding
package smoke source block is byte-identical to baseline; so are
`PreviewLimits` and `_decode_original` AST source segments. The accepted
shared-preview old-test adjustment waits for confirmed asynchronous cleanup
while retaining the original stopped-worker assertion.

I clear this exact code slice for one isolated frozen build. Actual frozen
startup and six smokes, helper review, native focus/pixel/cleanup evidence,
broader and hosted cross-platform tests, privacy and final source review
remain separate gates. The 256.5 MiB figure is a conservative explicit parent
pixel accounting, and RLIMIT_AS application is an address-space setting;
neither is an RSS or performance measurement.

## Frozen package and native-helper gates

I independently matched all 13 compiled readiness inputs against the isolated
241-file export manifest and exported bytes. The unsigned Linux x86-64 frozen
build exited zero in 339.357 seconds. Its raw metrics report all six smoke
gates passed, including actual frozen comparison cache/original workers,
orientation/alpha samples, unavailable-original refusal and complete cleanup.
The comparison child reported Linux `RLIMIT_AS` applied at 512 MiB; no RSS or
visible-native result follows. The 50,089,520-byte ELF has SHA256
`43d94ab7fe594e77d1773a58f7a283dab7ca77a4ad614548fe140fa2af069dfe`.
The private independent audit is
`work/comparison-frozen-independent-audit-2026-10-07.json`, SHA256
`f8b45207ff5c89161c1a40b02e90e6b875a800d1d3d2c6482bf7c124a828b9b5`.
Deployed outputs were not part of this build gate.

The Root-only native helper is statically cleared at SHA256
`66095067c4afedc8fe5919a69138caa92a94e5b79432cc2b9463e2e248875bf6`.
Its fixture-only selfcheck passed at the immediately preceding helper hash;
the sole subsequent change scopes an external-action count to the helper's
own action ledger. Review resolved two concrete fixture setup defects: an
opaque file could not pass catalog indexing, so unsupported admission uses a
copied-row API refusal; and collection remove/add increments the member's
asset revision twice, now explicitly checked in the same function used by
selfcheck and the visible flow. The helper confines child scratch to a
generated canonical temporary base and observes actual supervisor allocation
and removal. It retains full private catalog rows and main/WAL/SHM/journal
snapshots, source/cache manifests, guarded QtTest focus/key/mouse evidence,
private full-dialog captures and separate direct canvas captures that exclude
identity/path labels. The private static review receipt is
`work/comparison-native-helper-review-2026-10-07.json`, SHA256
`b68c964ceb95ee34a362cbc2cdaa4dacac18f7fafe032995addd2a2c94f6a91c`.
Fresh unlocked-session preflight, actual native execution, raw/public review,
hosted Windows/macOS results and final acceptance remain pending.

## Native generated-fixture review — attempt 1

Root ran the exact reviewed helper after fresh local active/unlocked-session
checks. Attempt 1 exited zero in 10.73 seconds at helper SHA256
`66095067c4afedc8fe5919a69138caa92a94e5b79432cc2b9463e2e248875bf6`.
The raw receipt SHA256 is
`4fe169e108647a23276913096a9c85782bcf35f65d6ce8c48dd6c323913f0c41`.
This is a Nobara 44-derived KDE Wayland source-launch observation at
2560 × 1080 and DPR 1, not generic Fedora, installed desktop integration, or
native Windows/macOS qualification. The source launcher emitted a nonfatal
portal Appinfo-not-found warning; it is retained in the private console log.

I independently recomputed hashes for all 10 captures and all 10 retained
logical/physical catalog snapshots, then compared four bracketed read-only
phase pairs after excluding only their stage-specific copy filenames. Their
catalog rows and physical hash/size/presence facts match. Generated collection
member C's revision increased by two as declared; rating, content,
path/source, failed scan, cache corruption and restoration mutations were
separately bracketed. The run logged 60 guarded QtTest keyboard actions with
visible, active, exposed and inside-focus state, plus two actual mouse-drag
observations. The disabled offline original control emitted no click and
admitted no new worker; the still-available pane loaded its original. Actual
source/cache manifest restoration, worker/model closure and fixture removal
were asserted. The temporary fixture is gone, so the raw initial manifests
and final asserted result, not a retained final source tree, support that
last comparison.

All six separate direct canvas-widget images visually contain only generated
pixels, without identity/path/status labels. Four full app-only dialog images
retain private UUIDs and labels. The helper does not instrument native
attempted original I/O; the separately retained child-spy tests establish
the narrower no-attempted-I/O behavior. The private independent receipt is
`work/comparison-native-independent-audit-2026-10-07.json`, SHA256
`4e3de47be2717dc11fb1c73e00e03a3926c61cb66c72b9fe7895afa947e1a402`.
This verifies the recorded controls and preservation observations but does
not clear the predeclared native fixture gate. Root's subsequent visual review
found both principal A/B images displayed at 72 × 144, so they did not prove
the required distinct aspect ratios. Both were also below the 256 cache edge,
so attempt 1 did not prove cached dimensions smaller than the original. The
immutable attempt-1 raw evidence is diagnostic for those two missing visual
claims; it is not relabeled as accepted native comparison evidence. A
helper-only regenerated fixture with asymmetric, differently proportioned
A/B images above the cache edge requires exact review and one justified fresh
native attempt. Production, the 101-test Qt result and six frozen smokes stay
at their prior reviewed hashes. Public derivative, privacy and requirement
wording, source publication, exact-head hosted CI and final acceptance remain
pending.

The corrected helper-only fixture is independently cleared for one Root-run
attempt 2 at SHA256
`8ccd44bc0f824060a29809ca1acc4d91f39f15eed7a8809b73696d76e56db8d0`.
Its nonvisible fixture selfcheck passed with A original 600 × 300 versus cache
256 × 128, and EXIF-oriented B original 144 × 288 versus cache 128 × 256.
The source images have distinct 2:1 and 1:2 aspect ratios, and asymmetric
quarter markers plus alpha are asserted independently for source and cache.
Actual native pixmap dimensions and samples are separately required during
attempt 2. The private review receipt is
`work/comparison-native-helper-attempt2-review-2026-10-07.json`, SHA256
`481714db4fac9a38256ff807901b7d6ed23026358c2759243576898523c4fe71`.
Attempt 1 remains immutable diagnostic history; no source runtime, frozen
build, or broad-test result is relabeled by this helper correction.

Root's separately retained attempt 2 passed at helper SHA256
`8ccd44bc0f824060a29809ca1acc4d91f39f15eed7a8809b73696d76e56db8d0`.
The raw SHA256 is
`1c29ebdfc459215daa89cc7fc9c03343b616a76a7c8d5caa11176d5d152f93fa`.
Actual Qt cache pixels were A 256 × 128 landscape and B 128 × 256 portrait;
explicit originals were A 600 × 300 and EXIF-oriented B 144 × 288. Quarter
RGBA/alpha markers matched for both modes, so this run covers the distinct
aspect and strictly smaller cache dimensions missing from attempt 1. I
recomputed all 10 capture hashes, 10 retained logical/physical catalog
snapshots and four no-write phase comparisons, confirmed 60 guarded focused
QtTest key actions, and visually inspected the direct canvas candidates and
private app-only status captures. Scratch, workers, model connection and the
generated fixture were confirmed cleaned; source/cache restoration assertions
passed. The private independent receipt is
`work/comparison-native-attempt2-independent-review-2026-10-07.json`, SHA256
`535084fc55e44b64e6d69198998e6dea5fa2ffe707747f848ac7e4238008adf8`.
This clears the scoped generated native visual gate on Nobara-derived KDE
Wayland. At that native checkpoint, public derivative/privacy, source publication
and exact-head hosted CI remained pending. The nonfatal source-launcher portal
registration warning
still prevents an installed desktop-identity claim.

## Publication-time public evidence review

I checked the sanitized attempt-2 result at SHA256
`9ff1995e0f880ec0f6431fe09cc3e03a6b4f619927ffbaf688a6bdf90c08d1e3`
and the attempt history at SHA256
`ac59d79f94e31b91aa7455e389fe654663f47750578c25c0f489a3201ffa065f`.
Both parse as JSON; the history names the exact result hash, retains attempt 1
as diagnostic and attributes the scoped pass only to attempt 2. The result
distinguishes the prepared 256-pixel cache edge from the 2048-pixel viewer
request. All six public PNGs have their declared hashes and byte sizes and
match the separate raw direct-canvas captures byte for byte. The reviewed
canvas regions contain generated pixels without path, UUID or status labels;
the private full-dialog captures and full raw snapshots remain outside the
public evidence. A text scan found no absolute private paths or UUIDs in the
two public JSON files.

The updated protocol and Task36 keep local Qt, frozen Linux, native KDE and
future hosted evidence separate. The tracker retains 129 distinct SDD IDs,
maps this bounded comparison evidence to Partial requirements, and leaves
editor/platform, ICC, assistive-technology, RSS and release qualification
open. Task00 and Task35 preserve the failed-fixture chronology and report the
224 protected baseline files and 15 deployed outputs unchanged after native
attempt 2. The proposed draft PR body describes the reviewed local results and
marks exact-head automatic Core/Qt, actual Windows and frozen checks pending.
The Tauri workflow's path filter does not match this Qt/doc change set, and
no manual dispatch was performed from the available review environment.
Verified unchanged-input prior Tauri evidence is baseline evidence only,
not a current-head pass. Root still
needs the final staged-set privacy check before
publication; no current-head hosted result or PR clearance is inferred here.
