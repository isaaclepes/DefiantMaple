# Captured two-image comparison design

This is the design gate for Tasks 35–37 at merged PR19 commit
`0f7082a2e01afccfdf4b81ec2145dc8a6572287e`. It proposes FR-UX-008's viewing
slice with FR-UX-002/003/006/007, FR-MEDIA-001/002/003 and
NFR-003/007/009/010/014/015. Source implementation awaits Root and independent
review clearance. No schema, scanner, catalog writes, original writes, cache
publication, association dispatch or persisted comparison workspace is added.

## Targets and presentation

The command counts selection ranges before materializing indexes. Exactly two
distinct supported image assets must be selected; otherwise it refuses the
entire command. PNG, JPEG, GIF and WebP use the existing supported-image set.
Targets are captured in ascending current view-row order, not focused-item
order. Each immutable target contains UUID, SHA-256, byte size, media type,
catalog revision, indexed absolute path and source ID, together with a copied
admission row recording exact source relation and last-observed health.
Filters, sort, collections, selection, refresh and catalog changes cannot
replace either captured target. A request token also identifies dialog, pane,
mode and request generation; canceled, mismatched or late delivery is discarded.

One dialog has Left and Right panes. Each has a plain-text captured name/ID,
mode, actual pixel dimensions, cache requested/actual edge, freshness and
last-observed availability. Elided names have a literal full-text tooltip.
Each canvas independently preserves aspect ratio and supports fit, zoom, pan
and checker/light/dark background. Controls have pane-specific accessible
names and a defined Tab order. F, + and - act on the focused pane when focus
is in its canvas; editable/combo controls keep their own keys. F11 makes the
whole two-pane dialog fullscreen; Escape first leaves fullscreen, then closes
the dialog. Focus remains in the same pane after fullscreen changes.

Initial loads are cache-only at requested edge 2048 through the unchanged
reviewed Core service. Exact-cache corruption refuses; absent exact size uses
its existing deterministic fallback and reports actual dimensions. A miss or
refusal never generates or reads an original. One pane's failure leaves the
other usable. A failed explicit replacement may retain that pane's previous
validated image, with an explicit message naming the failed action and the
still-displayed mode/dimensions; it never presents retained cached pixels as
an original.

## Explicit originals and drift

Each pane has an explicit Load original action. Admission uses the captured
row's `generation_refusal`: paused/watching source plus exactly indexed matching
entry is eligible; offline, denied, error, scanning, missing/nonindexed or
inconsistent relation is refused. Standalone assets require no linked entry
and remain availability-unchecked until their bytes are actually validated.
A cache-only admission never upgrades because of a later rescan; close/reopen
captures a new admission instead. No original/source stat, resolve, open,
enumeration, hash or decode occurs on the cache path.

Immediately before original I/O, the off-GUI loader calls
`fresh_generation_refusal` against the captured target and admission row. It
repeats this query after decode and before delivery. UUID/content/type/path/
source drift or fresh ineligibility refuses delivery. Revision-only metadata
drift with the same content/location is allowed but visibly reported; neither
pane is rebased. The comparison worker also makes a separate bounded read-only
catalog query for the captured UUID/revision at admission and final validation,
with the same 250 ms maximum SQLite wait inside the operation deadline. Its
pixel-free result records captured revision, observed revision and
`metadata_drift`; `fresh_generation_refusal` supplies eligibility, not this
annotation. A later revision changes only the warning, never captured metadata
or target identity. Cache content identity remains distinct from metadata freshness.

The new original helper lives in `comparison.py`; it does not invoke the legacy
`_decode_original`. A new `_OriginalFile` context explicitly reuses the unchanged
Core `_DirectoryTree` parent-handle containment and, on Windows, its
`_windows_handle` primitive. It does not call the cache checksum helper whose
contract remains cached-output hashing. These private primitives are named here
so their reuse and platform assumptions can be reviewed, rather than inferred
from the old preview decoder's ordinary `Path.open`.

On POSIX, each parent component is opened relative to the preceding directory
fd with O_DIRECTORY/O_NOFOLLOW/O_NONBLOCK. The leaf is first observed without
following links, then opened relative to the pinned parent with
O_NOFOLLOW/O_NONBLOCK; fstat must identify the same regular file. On Windows,
each component is a no-reparse CreateFileW directory handle held without
FILE_SHARE_DELETE, and the leaf is a no-reparse regular-file handle held without
write/delete sharing and transferred to a Python fd. Nonregular, linked,
reparse, UNC or unsupported-safe-containment inputs refuse this explicit
original action only; the cache path stays usable. No original path is resolved
to evade these refusals.

The child retains parent and file handles through decoding. It checks expected
size, reads at most 64 MiB plus a detection byte and hashes the captured input;
frame zero is decoded from those verified bytes, EXIF-transposed and converted
to RGBA without resampling or a new ICC policy. After decode, it rewinds the
held fd for a second checksum in at most 1 MiB chunks, checking size and
device/inode/mode/size/mtime identity before and after. A fresh no-follow parent
walk and leaf fd must still identify the held file at the captured pathname.
Fresh catalog/source validation follows before delivery. A replacement,
fingerprint mismatch or unsafe path refuses; a coherent same-byte replacement
is not a provenance/authentication claim.

The child writes raw RGBA, not a PNG, to a canonical supervisor-owned scratch
path: exactly width × height × 4, at most 32 MiB. Width/height/length are checked
before writing and again by the supervisor's bounded no-follow read; extra or
short bytes refuse. QImage construction and detached copy occur off GUI.
The twelve-second monotonic deadline covers spawn through final delivery;
the child checks it before/after input, decode, final checks and output, while
the supervisor enforces timeout even when a read/decoder does not return.

The original child first applies its resource policy and fresh eligibility,
then classifies the configured temporary base and every registered source,
cache, captured-parent and catalog-parent namespace. Canonical known directory
prefixes are checked; denied/unclassifiable prefixes refuse, and missing tails
are allowed only after an unambiguous existing prefix. A small bounded typed
JSON `safe_temp_base` reply identifies the live request and canonical base.
The supervisor validates stage/request/path/type/length and cancel/deadline
before creating its owned TemporaryDirectory there, then supplies a separately
tagged output plan. The same child rechecks actual scratch isolation before
any original read or output. No second child or fallback temp location is used.
`decoded` replies have a separate stage tag; malformed, EOF or late replies
refuse and retain ownership through cleanup, even when no scratch yet exists.

One bounded in-process watchdog accompanies the one original child. It checks
cancel/deadline independently of a QThread blocked in framed receipt, closes
the supervisor's duplicate child endpoint, and performs terminate/join then
kill/join within the same shared two-second cleanup budget. The QThread waits
for that supervisor before ordinary owned cleanup; there is no concurrent
reaping or new watchdog on cleanup-only retry. Partial-frame and blocked first/
second-stage failures are tested separately from actual decoder success.
If process startup before PID ownership, transport, signal or filesystem cleanup
is stuck in uninterruptible host I/O, the retained worker cannot promise a
universal wall-clock exit: GUI close/replacement remains refused and no false
cleanup success is reported. Concurrent same-user namespace moves between
classification and use remain an explicit race, not a provenance guarantee.

## Finite budgets and ownership

There is at most one comparison dialog, one running pane load and one queued
pane load: two admitted loads total, at most one pending request per pane.
Initial requests run Left then Right. Each later action is explicit; requests
are not silently superseded or queued without limit. The next load starts
only after the previous image has been consumed/discarded on the GUI thread
and its worker has finished with confirmed cleanup. Results retained by worker
and dialog contain metadata only, not a second raw-pixel cache.

Cache limits stay unchanged: 16 KiB manifest, 20 MiB encoded PNG, 512 entries,
2048 dimensions, 4,194,304 pixels/16 MiB RGBA, five seconds including startup
and delivery, and the reviewed 512 MiB address-space policy. Explicit comparison
originals tighten the legacy original limits to 64 MiB encoded input, 8192 per
dimension, 8,388,608 decoded pixels/32 MiB RGBA and twelve seconds covering
startup, admission, input/hash/decode, final checks, normalized output and
off-GUI QImage copy. Larger originals refuse actionably; comparison does not
quietly downsample an original. Both modes decode and create the detached
QImage off GUI; only bounded QPixmap conversion/presentation is on GUI.

Two retained pane pixmaps contain at most 16,777,216 pixels/64 MiB. At a
replacement boundary, the old two pixmaps (64 MiB), incoming raw bytes
(32 MiB), detached QImage (32 MiB), and incoming pixmap (32 MiB) give a
conservative 160 MiB explicit comparison pixel-buffer ceiling. Gallery's
existing 256 by 256 thumbnail LRU adds at most 64 MiB. Gallery's in-flight
raw cache pixels and detached full QImage add 32 MiB, with at most 0.5 MiB
for reduced 256-edge QImage/delivery/pixmap overlap: 256.5 MiB of these
explicit parent pixel buffers. The gallery worker admits only one outstanding
scaled-image delivery and waits for GUI acknowledgement before reading the
next item; acknowledgement occurs even for stale/refused deliveries, and stop
breaks the finite polling wait. Prior raw/result/image references are dropped
before the next read. Root and independent review approved this app.py-only
ownership correction; cache parsing, generation and source semantics are unchanged.
This is not an RSS bound: Qt, Python, Pillow,
graphics drivers and allocator overhead are separate. The original child
allows two encoded-input representations (128 MiB), three bounded decoded
representations (96 MiB) and normalized output (32 MiB): at most 256 MiB of
these explicit buffers. The existing 512 MiB child address-space ceiling may
refuse otherwise dimension-eligible inputs. Linux supported enforcement stays
fail-closed; the reviewed Darwin child-specific default-limit ValueError and
Windows unavailable-resource gaps are reported honestly, never called RSS
limits. Source and frozen startup/decode compatibility require evidence.

The comparison contributes at most one decoder child. An existing gallery
thumbnail helper may coexist under its existing limits; a separate external
probe may coexist under its existing limits but produces no image. Scanner
work is unchanged. Single original/cached inspectors and comparison are
mutually exclusive: opening either waits for the former viewer to close,
clear pixels and confirm cleanup, otherwise the action refuses. This avoids
stacking the legacy 40-million-pixel inspector on the comparison budget.

Cancellation is event-only on GUI; supervision and process termination happen
off GUI. Operation deadlines are monotonic and start before process startup.
After deadline/cancel, terminate/join up to one second, then kill/join up to
one second; this cleanup grace is distinct from the operation deadline.
Close disables actions and retains the dialog/worker while cleanup is pending,
without a GUI-thread blocking wait. No worker or temporary output is forgotten
because a close event occurred. An unreaped child keeps a strong process,
scratch and owner reference and blocks replacement/new pane admission.
Explicit cleanup retry is off GUI and bounded; original retry cannot decode
again, and cache retry passes an already-set cancellation event through the
existing service's orphan-reap-first admission, returning without a new helper.
No claim is made that blocked kernel I/O can always be killed. Accepted close
clears both canvases and returns the parent to its normal state.

## Narrow shared-preview exception requested

`prototypes/qt/preview.py` needs a lifecycle-only exception before implementation.
Its current worker emits loaded before cleanup, unconditionally forgets the
process and exits TemporaryDirectory even after failed reap; its dialog waits
on GUI during close and retains a canvas after accepted close. Comparison
cannot establish safe mutual exclusion against an unowned prior decoder.
Proposed correction retains process/scratch until confirmed reap, exposes
cleanup outcome, emits successful image only after cleanup, makes GUI cancel
event-only, uses bounded off-GUI cleanup/retry, refuses replacement while
cleanup is incomplete, and clears pixels on accepted asynchronous close.
The concrete shared lifecycle states are idle, running, canceling,
cleanup-pending, clean and cleanup-failed. TemporaryDirectory is held as an
owned object, not a `with` block that can delete output while a child is alive.
The worker and dialog retain strong process/scratch/worker references after
failed reap, report `cleanup_complete=False`, discard decoded pixels and emit
no loaded signal. Accepted close, replacement inspector and comparison admission
remain refused until an off-GUI bounded cleanup-only retry confirms the process
has exited, joins it and removes its scratch. No retry reruns decode or source
I/O; only one supervisor/cleanup thread can own that process at a time. GUI
cancel only sets an event, and the monotonic operation deadline begins before
spawn. Clean success is signaled only after confirmed reap/scratch cleanup;
accepted asynchronous dialog close clears its canvas. The original child
decoder, fingerprint algorithm, format/orientation/color policy,
40-million-pixel limits and original source access remain unchanged. New
comparison tests cover this ownership interaction; no protected existing
preview test is edited. This is an explicit additional source exception,
not authorization to redesign shared preview behavior.

## Files and evidence gate

Owned new files: `prototypes/qt/comparison.py`,
`prototypes/qt/tests/test_comparison_ui.py`,
`prototypes/qt/comparison_native_acceptance.py`, `docs/comparison-design.md`
and `docs/comparison-guide.md`. Existing owned integrations:
`prototypes/qt/app.py`, `prototypes/qt/package.py`, `prototypes/qt/README.md`.
The shared `preview.py` exception above requires separate Root/reviewer
clearance. Core cached service, scanner/catalog/schema, external actions,
workflows, archived evidence and all deployed outputs stay unchanged.

Meaningful generated tests exercise real spawned cache/original success and
refusal, exact two-target capture, metadata/content drift, fresh eligibility,
orientation/alpha/aspect, independent transforms/keys/focus/fullscreen,
corruption, no cache-to-original fallback, start/deadline/cancel/late delivery,
bounded queue and cleanup/replacement. Private temporary roots are canonicalized
only after creation. All workers register cleanup before start. Failure tests
retain receipts and exercise cleanup failures without forgetting ownership.

A sixth package smoke uses the actual frozen comparison worker path with two
generated small images, cache-first delivery and an explicit eligible original,
plus unavailable-original refusal; it checks pixels/labels and cleanup without
association dispatch. The prior five smokes remain intact. Root alone runs
frozen/native gates after exact source/helper review. The native helper owns
generated source/cache/catalog/snapshot/capture fixtures, records actual focus
and keyboard events, independent pane transforms and original refusal, then
closes/reopens and confirms worker/helper cleanup. Full logical and physical
catalog/source/cache/collection snapshots and failed-stage receipts are private;
safe app-only captures and sanitized digests/counts are public. Native successful
cache viewing with an unavailable source is combined with separately instrumented
child-side tests for the no-attempted-original-I/O claim. Historical PR19 evidence
is reused only for unchanged bytes; new comparison/lifecycle evidence is distinct.
