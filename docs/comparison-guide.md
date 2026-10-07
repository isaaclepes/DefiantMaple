# Compare two captured images

Select exactly two PNG, JPEG, GIF or WebP assets in the gallery, then choose
**Compare two selected images…**. The left pane is the earlier selected row in
the current view; the right pane is the later row. Other selection counts or
media types refuse the whole action. The dialog records each UUID, indexed
fingerprint, revision and path. Changing the gallery selection, filters, sort
or collection cannot replace those captured panes.

Both panes initially request a cached preview. A label identifies last indexed
content, actual dimensions, any size fallback and the source's last observation.
A cached preview does not establish that its original is available or current.
A miss, incompatible/corrupt cache or unavailable source is an actionable
pane-local result; comparison never silently regenerates a cache or opens an
original. The other pane remains usable.

**Load original** explicitly verifies that pane's captured original. A
paused/watching source needs exactly its indexed matching relation; offline,
permission-denied, error, scanning, missing and unresolved sources cannot
cross that boundary. A standalone asset has availability unchecked until its
bytes are actually verified. Returning a drive or file does not implicitly
change these observations. Rescan explicitly, then reopen comparison to
capture new eligibility. Source health is separate from workflow state.

The original worker checks fresh catalog/source facts before reading and after
decoding, SHA-256 and byte size, nonlinked regular-file/path identity and
first-frame orientation/alpha. Changed content, path or source relation refuses
delivery. A rating/favorite revision change alone may leave the same pixels
eligible; a warning reports the observed revision while keeping the captured
target. If an explicit replacement fails, an earlier validated image may stay
visible, but its label states exactly which previous cached/original image is
still being shown.

Each pane independently offers Fit, Zoom in/out, wheel zoom, drag to pan, and
Checker/Light/Dark transparency background. Focus has Left/Right names and a
logical Tab order. With focus in a canvas, F fits, +/− zoom, and changes affect
only that pane. F11 toggles the two-pane window's fullscreen state. Escape first
leaves fullscreen, then closes it. Editing, synchronized transforms, difference
metrics and saved comparison workspace are separate features.

Only one comparison exists at a time; its two requests run serially. Comparison
and single-image inspectors close and clear their pixels before replacing one
another. A helper that has not finished cleanup keeps its owner and blocks
replacement. Close requests cancellation without blocking the GUI. If cleanup
fails, the dialog remains present and Close performs a bounded cleanup-only
retry. It never retries decoding an original automatically or deletes published
cache/source files. No guarantee is made that blocked kernel I/O can always be
killed.

Comparison originals have operational limits of 64 MiB encoded input, 8192
pixels per dimension, 8,388,608 decoded pixels/32 MiB RGBA and twelve seconds
including startup and checks. Cache reads retain their reviewed five-second,
2048-edge/16 MiB RGBA and finite manifest/file/entry caps. Oversized originals
refuse explicitly rather than becoming a silently reduced original. Source
links/reparse points and paths lacking safe containment, including UNC in the
current original handle strategy, refuse only explicit original loading;
cached viewing remains available.

The conservative explicit parent pixel-buffer accounting is 256.5 MiB,
including two panes, replacement copies, gallery LRU and one acknowledged
gallery delivery. This is **not RSS, a hardware recommendation or a performance
measurement**. Helpers request a 512 MiB address-space ceiling: supported Linux
application failure refuses; the reviewed Darwin default-ceiling ValueError
reports a child-specific unenforced gap without guessing its cause; Windows
reports resource enforcement unavailable. All finite input/output/pixel/time
and cleanup limits still apply. Qt/Pillow/runtime overhead can cause a
dimension-eligible image to refuse; frozen-runtime acceptance is separate.

Original scratch planning/classification runs in the same bounded child before
the supervisor creates transient storage. Canonical source/cache, catalog
directory and captured source-directory namespaces are checked again before
original I/O or output. Typed replies are limited to 16 KiB. An independent
watchdog can attempt terminate/kill while a framed reply is incomplete; confirmed
reap uses one shared two-second cleanup grace. Blocked kernel/transport cleanup
is reported and retains ownership rather than claiming a universal wall-clock
guarantee. Unclassifiable protection
boundaries refuse. Concurrent same-user namespace changes can race such
observations; this is not a cryptographic authenticity or universal hostile
filesystem guarantee. Cache integrity remains format/digest/key compatibility
with indexed content, not proof against coherent same-user replacement.

Tests with actual spawned workers are distinct from injected startup/reap/
allocation/late-delivery faults and child-side I/O guards. Native generated
fixtures demonstrate the visible path and observed-unavailable source flow;
separate instrumentation establishes no attempted original I/O on cache paths.
Private full captures retain identity, paths and catalog snapshots. Public
images are separately declared direct canvas/widget captures that exclude
identity/path rows; they are not edited versions of private raw captures.
The sixth package smoke exercises actual frozen cache/original comparison
workers with generated media and unavailable-original refusal, without showing
a native window or launching an external association. Source-only smoke success
does not establish frozen packaging or platform acceptance.
