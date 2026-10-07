# Phase 1a side-by-side comparison — acceptance brief

Luna owns acceptance planning, requirement tracking, public privacy and CI audit.
Baseline and product/source boundaries are in [Task35](35-comparison-implementation.md).
Independent Sol owns [Task37](37-comparison-review.md). Do not commit/push or
change production code. Preserve historical evidence and deployed outputs.

Before implementation, create `docs/comparison-acceptance.md`: predeclared
generated-fixture stages, pass/refusal criteria, preservation snapshots,
environment/runtime/input hashes, actual keyboard delivery and focus checks,
raw/public boundaries, cleanup and attempt history. Refresh only relevant
requirement rows, preserving IDs and reasons for Partial states. Add PR19's
merged/30-check closure without relabeling its historical native receipts.

Native stages must cover two oriented/alpha images with different aspect ratios;
explicit original and cached states; one unavailable/missing/corrupt pane while
the other remains usable; independent fit/zoom/pan/background and Tab focus;
selection/filter/refresh drift without retargeting; original admission refusal;
close/cancel/reopen cleanup. Snapshot source bytes, catalog logical and physical
state, cache entries and collection membership before/after. Do not exercise
real artwork, system associations, network mounts or deployed user catalogs.

The generated helper is reviewed before visible execution. Root verifies an
unlocked desktop and serializes the run. Locked/unavailable desktop is a native
gate, not permission to claim offscreen evidence as native. Preserve every raw
attempt; never overwrite failures or rerun merely to improve a screenshot.
Public evidence may contain only generated, path-free sanitized aggregates
and reviewed images. Private roots/UUIDs/paths/argv/catalog rows remain private.
JSON outside the normal privacy checker's path coverage needs direct validation.

After a stable reviewed source snapshot, record actual relevant local checks,
frozen comparison smoke and retained prior smokes. Audit fresh exact-head hosted
CI: automatic Core push/PR (12 jobs each) and Qt PR (3 jobs). The Tauri PR
workflow path filter does not match this change set. The current review
environment cannot dispatch it, so no Tauri run was performed; prior Tauri run
`37517755028` is baseline evidence only after verifying its relevant inputs
remain unchanged, not a current-head pass. Record actual Windows Core/Qt totals
and named skips, platform memory-enforcement flags, frozen checks and artifact
provenance.
Keep different heads/attempts separate. Placeholder-grid benchmarks are not
decoded-media responsiveness; caps are not RSS; hosted checks are not native
Windows/macOS release qualification. No unadopted §19 budget becomes a pass gate.

Deliver factual acceptance/limitations and an evidence-backed next boundary,
green checks, privacy/preservation and independent clearance for a draft PR.
Merge and deployed binary replacement remain separate decisions.

## Current gate status

The base comparison design was cleared by Root and independent review at SHA256
`2a042e8620aa577f8b4626ebe7f4ac34b3450e4da4b3dafbc230777014647c15`. The
amended design, including approved gallery backpressure, scratch/watchdog
handshake and revised explicit-buffer accounting, is cleared at SHA256
`44c5ae1f6eaff34c1b3c862f50d9cc0826bbbe9ae12d0d7494d6d73bf8809e2b`. The
predeclared limits and shared `preview.py` lifecycle-only exception are copied
into [the acceptance protocol](../comparison-acceptance.md). The full local Qt
suite and first isolated frozen build passed. Native attempt 2 now passes the
scoped generated-fixture visual gate after independent review; attempt 1
remains diagnostic for its fixture mismatch. Fresh exact-head hosted CI and
final staged-publication privacy checks remain pending. The first focused test
result is recorded below as chronology, not as an accepted gate.

The cleared design hash names the base design, whose parent buffer total was
224 MiB. The separately approved app.py backpressure adjustment below raises
the acceptance accounting to 256.5 MiB. Do not attribute the amendment to the
base design hash; the cleared amended design is
`44c5ae1f6eaff34c1b3c862f50d9cc0826bbbe9ae12d0d7494d6d73bf8809e2b`.

Root and independent Sol also approved one `app.py`-only gallery ownership
adjustment: permit at most one outstanding scaled image delivery, use a finite
stop-aware wait, acknowledge in the receive handler's `finally` path (including
stale/error results), and release previous full raw/QImage references before
the next read. Add acceptance assertions for queue bound, stale acknowledgement,
and stop while waiting. This changes explicit parent pixel-buffer accounting
from 224 MiB to 256.5 MiB: 160 MiB comparison buffers + 64 MiB gallery LRU +
32 MiB one full-gallery transient raw/detached image + 0.5 MiB for two scaled/
delivery buffers. This remains an explicit-buffer budget, not RSS or a
performance measurement.

Root and independent Sol also approved a one-child, two-stage scratch
canonicalization handshake for explicit-original loads within the same
12-second deadline: the child classifies the canonical temporary base and
protected namespaces before scratch creation; the parent creates scratch only
under an approved base; that same child rechecks the actual scratch before
original I/O/output. Alias source/cache temporary bases or denied/unclassifiable
roots refuse before scratch exists. Typed-stage replies are validated; malformed,
EOF, late, timeout, and cancel handshakes must clean up and retain process/pipe
ownership until reap even when no scratch exists. Include a regression where a
child writes only part of a framed reply and stalls after the parent starts
reading. An in-process watchdog must trigger terminate/kill on cancellation or
deadline without waiting for that frame read. Assert the reader unblocks, pipes
close, and owned process/worker state clears only after confirmed reap. No
alternate location, second child, or cache-only source resolution is allowed.
A concurrent path move after validation remains a residual race, not an atomic
namespace guarantee. The watchdog and bounded termination grace do not promise
a hard wall-clock bound if kernel or transport operations cannot complete.
Acceptance must verify these cases after source freeze without implying a new
native result.

The first affected focused run is preserved in the private wrapper work
directory (beside, not inside, the repository) at
`work/comparison-lifecycle-checks/focused.log`, SHA256
`012a65f29b90335021e634a737f6029896949cba4b4f474a578c4c21918e3e68`. It ran
12 tests: 11 passed and
`test_close_during_decode_and_thumbnail_queue_invalidation` failed at the
legacy immediate assertion `self.assertFalse(dialog.worker.isRunning())` after
close. The approved lifecycle changes make close asynchronous. Root and
independent review approved adding bounded synchronization around that
assertion without removing or weakening it. Keep this first result historical.
The approved synchronization landed in
`prototypes/qt/tests/test_gallery_usability.py` at SHA256
`9a1289ef005de5c1ad5a733f9dfe30c0466651c36b7f2e012dd12a50b2d81238`. The
only legacy-test edit is three bounded synchronization/cleanup/accepted-close
assertions in the existing close test; no prior assertion was removed or
weakened. The
corrected 12-test focused slice passed in 1.929 seconds; its private wrapper
log is
`work/comparison-lifecycle-checks/corrected.log`, SHA256
`4322eba55bae8047ad7b6bbec1a54dcb062809ff0c647775de00f0417f3ef28a`. This is
focused lifecycle validation only. The full offscreen Qt suite then passed
101/101 tests (exit 0; 39.687 seconds wall time) with a matching 40-file
implementation/test input manifest before and after. The private log is
`work/comparison-lifecycle-checks/full-qt-2026-10-07/full-qt.log`, SHA256
`9f84146d1aba0684164e661180eaf763bd46b26d6af219b22e5197cc17129f63`; the run
receipt and exact input manifests are recorded in the wrapper directory. Core
and Node were reused only after relevant bytes were verified against the
protected baseline. Full comparison acceptance, visible acceptance, and hosted
CI remain pending.

Root's isolated frozen build subsequently exited 0 after 339.357 seconds from a
241-file source export; all 13 readiness inputs matched checkout and export.
The unsigned local x86-64 ELF candidate is 50,089,520 bytes, mode 755, SHA256
`43d94ab7fe594e77d1773a58f7a283dab7ca77a4ad614548fe140fa2af069dfe`. All six
frozen CLI smokes passed, including two-pane comparison and unavailable-original
refusal. Linux cached-preview and comparison children reported `RLIMIT_AS`
536,870,912 bytes applied; this is address-space control, not RSS or
process-tree enforcement. The benchmark changed its disposable generated
100,000-row catalog with review-state key events; preservation is claimed only
for the separate comparison smoke, whose package assertions check its catalog
logical/physical state, source hashes/mtimes and cache hashes before and after
the action. The private audit is
`work/comparison-lifecycle-checks/frozen-build-audit-attempt1-final.json`,
SHA256 `46a0720ba71a28b43b75422ef5a311d0f7651d7d0aa8e4b5889b46094a06e4bd`.
The candidate remains private and is not native UI evidence or deployed output.
Its offscreen placeholder benchmark did not measure image decode, disk
thumbnails, or compositor presentation.

## Generated-fixture native result — attempt 2

Root ran the corrected, separately reviewed helper at SHA256
`8ccd44bc0f824060a29809ca1acc4d91f39f15eed7a8809b73696d76e56db8d0`. It
exited 0 in 10.038 seconds after an active, unlocked KDE Wayland preflight.
Independent review accepted the scoped visual gate. The raw receipt is SHA256
`1c29ebdfc459215daa89cc7fc9c03343b616a76a7c8d5caa11176d5d152f93fa`; the
sanitized [attempt 2 result](../evidence/comparison/attempt2/acceptance.json)
and [history](../evidence/comparison/attempt-history.json) retain public
hashes and limits.

Attempt 2 used a 600×300 RGBA landscape with 256×128 cache and an EXIF-6
portrait displayed 144×288 with 128×256 cache. Distinct 2:1 and 1:2 pane
ratios and both cache reductions were checked in actual original/cache
pixmaps. Attempt 1's raw evidence remains diagnostic because its two panes
both displayed 72×144 and its cache images were not smaller than their
originals. No earlier raw result was overwritten.

The native helper observed 60 guarded QtTest key actions after programmatic
focus setup, two mouse drags, selection-count and unsupported/duplicate
refusals, stale target protection, cached viewing with a generated source
missing, disabled original admission, explicit rescan behavior, isolated
corrupt-cache refusal, and close/reap/fixture cleanup. These results cover one
Nobara 44-derived KDE Wayland source launch only. A portal AppInfo registration
warning leaves installed desktop identity unqualified. The helper did not
instrument attempted original-file I/O; the separate child-spy suite supports
only its narrower test claim. The 256.5 MiB figure is explicit parent buffer
accounting, not RSS or a process-tree measurement. Human keyboard-only/AT,
Windows/macOS native, ICC/fidelity, general performance, and deployed-output
qualification remain open. Final staged privacy validation and exact-head
hosted CI remain pending.

The separately recorded focused Qt slice passed 53/53 in 21.731 seconds
(log SHA256
`b26d6f2c74f144be660e03005dc4a469a635e241939aade7cd21e7878cd32d58`); the
full local offscreen suite passed 101/101 at the source/test snapshot recorded
above. The isolated frozen build passed all six CLI smoke gates and remains a
private candidate, not deployed output. The [public attempt 2 JSON](../evidence/comparison/attempt2/acceptance.json)
and [attempt history](../evidence/comparison/attempt-history.json) were each
directly passed through `scripts.check_public_artifacts._check_json` with zero
errors and manually scanned for absolute paths, UUIDs, private identifiers,
command arguments and per-image vectors. All six public images are exact
byte copies of their private receipt's direct canvas-widget captures; they
contain generated pixels without path or UUID labels. The ordinary tracked-set
privacy checker still must be run after Root stages the final publication set.
