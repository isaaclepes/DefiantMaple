# Viewing cached previews while originals are unavailable

Open the existing library normally. It uses the indexed catalog without requiring
a rescan. Metadata, ratings/favorites, review states and collections remain in
the catalog when a source becomes unavailable.

When a compatible cached image exists, the gallery can display it with a cached-
preview label and the last observed source state. Select a card and choose
**View cached preview** to inspect that cached image. The dialog reports its
actual pixel dimensions and whether the cache size differs from the requested
size. Fit, zoom, pan and checker/light/dark transparency backgrounds work on
those cached pixels; zoom does not restore detail from the original.

A cache matching the last indexed fingerprint is not proof that today's original
has unchanged content. The cache is checked for integrity, format and indexed
identity. It is not authenticated against someone replacing both the cache image
and its manifest. The current policy preserves EXIF orientation and RGB/RGBA
alpha; this feature does not add qualified ICC/color management.

**Inspect full image**, **Open in Editor** and **Open containing folder** require
the original and remain disabled when the catalog records it as unavailable or
unresolved. Cached inspection is a distinct operation and never sends the cache
to an editor. Paused source monitoring is a normal last observation, not an
offline status. Standalone indexed assets without a registered source report
availability as unchecked.

Returning a disconnected source or file does not silently clear its recorded
state. Choose the source and explicitly rescan when it is available. The scan
can reconcile observations; cache viewing does not change source health, mark
assets deleted, write metadata or scan source folders. An inspector remains
bound to the asset captured at opening even if gallery selection or filters
change. Content changes detected during loading refuse stale delivery; catalog
location/metadata changes are reported without switching the target.

If there is no compatible cache, the gallery/dialog says so. A corrupt, partial,
incompatible or over-limit preferred entry shows an error. The cache-only path
does not read an unavailable original to repair it or substitute an older content
revision. A different cached size can be used only within the same indexed
fingerprint and supported policy; its actual dimensions remain visible.

Cache reads use finite input, pixel, time and worker bounds. Timeout/cancellation
is visible; incomplete cleanup is reported rather than claimed successful. Close
the inspector to cancel its work. The five-second cache-read limit is separate
from the existing original decoder/generator limits. These are operational
refusal limits, not universal performance or process-memory guarantees.

On macOS, the worker attempts the default 512 MiB address-space ceiling. A
specific reviewed rejection can allow bounded cache reading while reporting that
this ceiling was not enforced in that child; the cause is not established. This
does not mean macOS lacks the control, and it provides no OS memory guarantee.
Other limit failures still refuse. Input, image, deadline and cleanup limits
remain active. Linux ceiling failures continue to refuse; Windows reports its
separate enforcement gap. Historical local Linux receipts keep their original
source hashes; revised-platform validation is recorded separately.

No new whole-cache disk budget, eviction, cache rebuild, comparison view,
backup/restore, automatic watching or media mutation is included. See the
[technical contract](cached-offline-design.md) and
[scoped acceptance record](cached-offline-acceptance.md) for supported bounds,
compatibility and evidence limitations.

The scoped native evidence uses generated missing originals to demonstrate
visible cached viewing, disabled original controls and explicit source-health
transitions. It does not instrument attempted original I/O. A separate Core
spawned-child guard test detects original open/stat/resolve/enumeration attempts;
the private native receipt retains that test log and digest as combined evidence.
Intentional failed/restored scans change source observations; original bytes,
asset metadata, edit journals and collection membership remain preserved.
