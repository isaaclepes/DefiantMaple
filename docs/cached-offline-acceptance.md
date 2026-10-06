# Cached-offline gallery acceptance protocol

This document defines the generated-fixture acceptance gate and records the
scoped attempt 1 result for Task 33. The approved implementation and policy were
reviewed before Root ran the visible native helper. The attempt passed its
bounded Linux source-build checks; Task 33 remains open for exact-head hosted CI,
final staged-publication privacy validation, and review of broader requirement
gates.

## Scope and evidence classes

The gate is limited to a schema-v6 catalog and a disposable generated image
source. It must show cached previews and catalog metadata while that source is
unavailable, preserve ordinary catalog curation, guard operations requiring the
original, and require an explicit scan after source restoration. A cache display
never changes source health or proves the original is current. A cached image is
a derived preview, not a substitute original or an external-editor target.

Keep these evidence classes separate:

- Core and Qt offscreen regressions establish deterministic cache-policy,
  migration/metadata, corruption, cancellation, and GUI-state behavior.
- Native source-build evidence records the visible generated-fixture behavior on
  one named Linux host, including labels, focus, cancellation, cleanup, and
  source/catalog snapshots.
- Hosted Core, Qt, and Tauri checks establish the exact PR head's platform test,
  reader, privacy, and package outcomes; they do not establish native display or
  editor behavior.
- Frozen-package smoke evidence establishes only the named CLI/worker behaviors
  exercised on each built artifact. It does not automatically qualify a visible
  native application.
- The user's separate Gwenview, Krita v5.3.4 AppImage, and Dolphin reports are
  human-observed external-open happy paths associated with the prior PR18 test
  context. They do not identify the user's running process or demonstrate
  cached-offline behavior.

## Cleared design values — scoped implementation and native gates passed

Sol's private design proposal version SHA256
`4d8b0fb2129ea92668e2b0353143cdb4577b40f7b59180dfebed4edddd870e1a` has been
cleared by independent Task 34 review and Root, including the bounded legacy
cache-reader and fifth frozen-smoke exceptions. The values below are the cleared
contract for implementation. The Linux frozen build applied the 512 MiB child
address-space limit in the fifth smoke; this records address-space enforcement
on that runtime only, not RSS or cross-platform behavior. The initial hosted
PR19 attempt exposed a macOS enforcement gap described below. Further
implementation deviations must be reviewed before the affected evidence is
accepted. Do not infer defaults
from the SDD's candidate performance values or proposed 5 GiB cache default.

- Immutable `CachedTarget` captures asset UUID, indexed SHA-256/bytes, media
  type, catalog revision, path and source identity. Cache content identity is
  UUID plus indexed fingerprint/size and policy; a rating edit alone does not
  invalidate an image cache. Capture is lexical and must perform no source/cache
  I/O.
- Retain cache schema 1 and current Pillow-version identity. Existing accepted
  output policy is EXIF-oriented first-frame PNG, RGB/RGBA, with source maximum
  512 MiB, source dimension maximum 32,768 and pixel maximum 80,000,000. No ICC
  conversion or color-fidelity claim is made. Unknown schema, decoder,
  fingerprint, size, media type, or output policy refuses.
- The cleared size fallback scans at most 512 total entries in one captured
  UUID/fingerprint directory. Candidate edges are the current gallery sizes
  96–224 plus 32/64/128/256/512/1024/2048, with duplicates removed; only fixed
  recognized basenames for the known policy qualify. Count unrecognized debris;
  overflow refuses. Select exact size if present; a corrupt/incompatible exact
  entry refuses. If exact is absent, choose the smallest recognized larger edge,
  else the largest smaller edge; a corrupt/incompatible preferred alternate
  refuses instead of falling through to another candidate. The result labels
  requested edge, actual edge and decoded dimensions. A 2048 inspection can use
  the largest smaller recognized entry.
- Cleared manifest ceiling is 16 KiB; cache PNG input ceiling is 20 MiB; image
  dimensions are at most 2048 each and 4,194,304 pixels. Decode output is at
  most 16 MiB tightly packed RGBA and must match manifest dimensions/declared
  edge. The manifest is bounded UTF-8 JSON with known scalar fields, unique keys
  and finite values. Digest is checked on the opened bytes.
- Only the derived known basename is allowed. Never resolve/stat/exists/open or
  enumerate the original path/source root, even to compare a captured path.
  Compare captured path/source/revision lexically and return catalog drift if
  they change while content identity remains stable. For cache containment,
  reject escaping roots, symlink/reparse/nonregular components and identity drift.
  POSIX uses a no-follow directory-fd walk from filesystem root and leaf opens
  relative to a pinned fingerprint-directory handle; Windows rejects reparse
  components and pins directory handles during bounded reads. If these primitives
  are unavailable, refuse with explicit unsupported-containment status. This is
  containment/integrity checking, not a complete defense against privileged
  same-user replacement races.
- Cache-only `read_cached_preview` may not access original media, enumerate the
  source, generate, create cache directories, lock/repair/delete cache entries,
  or write catalog/source health. A supervised child performs bounded catalog
  and candidate reads plus decode, then rechecks content identity. No-cache is
  side-effect free. A final race after requery remains possible and is disclosed.
  The new five-second lookup/decode bound excludes legacy available-source
  generation. The approved exception allows only a narrow existing-cache reader
  change in `thumbnail.py`: 16 KiB max+1 bounded manifest/lock/lease JSON reads
  and 20 MiB bounded chunked cached-output checksum reads, without altering
  original hashes,
  generated decoder output verification, lock behavior, or publication. Test
  those overflow cases separately; do not describe all legacy generation as a
  five-second operation.
- Cleared lookup/decode deadline is 5 seconds including helper startup, lookup
  and decode; cancellation polling is at most 50 ms, followed by up to 1 second
  terminate and 1 second kill/reap. Catalog read waits within the same deadline. A
  kernel-blocked filesystem call is not claimed forcibly interruptible on every
  host. The local Linux frozen smoke applied the 512 MiB address-space ceiling;
  it is address space, not RSS. It does not establish enforcement on other
  runtimes.
- Cleared limits allow one gallery cache child from the existing bounded
  thumbnail queue, one explicit cached-inspector child, at most 32 queued
  thumbnail requests and 256 in-memory entries. No new unbounded per-card queue
  is permitted. Keep existing cache publication/generation behavior and atomic
  PNG/manifest publication unchanged.
- Cleared UI names the action **View cached preview** and labels
  “Cached preview of last indexed content · W × H pixels · original availability
  [last observed state]”. It is not titled full resolution/original. Original
  full-image inspection and external actions are guarded when the source is
  unavailable; cached viewing, settings and ordinary catalog curation remain
  available. In-flight preview remains attached to its captured request; content
  drift refuses delivery, while unrelated gallery selection does not retarget an
  open cached inspector.
- The cleared minimal frozen exception adds `--smoke-cached-preview-id` while
  retaining the four PR18 frozen smokes/metrics. It reuses generated fixture
  data, primes a verified cache, removes original access in helper-owned scratch
  state, and tests the actual QThread→spawned helper→bounded RGBA handoff with no
  catalog/source mutation and cleanup. It grants no association permit. This
  remains a worker smoke only, separate from visible offline-desktop acceptance.

The implementation API names and limits must match the cleared design. If any
changed value is proposed, hold native acceptance and request review rather than
inferring a safe fallback or resource bound.

## Fixture and before-state

Use only generated images and a new disposable schema-v6 library. Record the
generated source-image manifest (relative fixture path, bytes, size, mtime,
digest, and purpose), generated cache manifest/entry identity, exact requested
preview sizes, and cache-root policy. Include generated samples that distinguish
orientation, alpha, aspect ratio, and a supported ordinary image. No user art,
network share, personal catalog, global association, or user original source
path may be involved; the generated original source path is required for the
warm-cache setup.

Warm the cache through the normal supported workflow while the generated source
is healthy. Close the app cleanly and capture both byte-level and logical
before-state: source file digests/sizes/mtimes; cache entries; catalog file/WAL
state and catalog-row snapshot for identity, path, fingerprint, metadata,
collections, and source health; SQLite integrity and foreign-key results. Preserve
raw snapshots privately. The fixture must include a fresh or reopened catalog
state, not only an already-open model.

Make only the generated source unavailable by moving or renaming its fixture
root to a second location reserved for the test. Do not delete it or alter its
image bytes. Before the failed scan, record the existing last-observed state
(often paused or unchecked); moving the directory alone does not establish
Offline. Then explicitly scan the missing generated root and record its separate
catalog/source-health state change to Offline. Record the scan result and verify
the fixture bytes remain unchanged.

## Source-state matrix

Every state is derived from catalog rows. Cache lookup never probes a source root,
changes source health, or converts the result into an original-file action.

| Catalog/source condition | Cache read | Original generation after cache miss | Expected visible meaning |
| --- | --- | --- | --- |
| Paused/watching with one matching indexed entry/source/path | Allowed | Existing generation may remain eligible under current rules | Last explicit observation; paused is not Offline; original actions still revalidate |
| Offline, permission denied, error, or scanning | Allowed | Forbidden | Cached only; disable original-only controls; cache hit does not clear state |
| Missing, pending/ignored, nonindexed, unsupported/error entry, absent or inconsistent source relation | Allowed only when asset content identity is valid | Forbidden | Unavailable/unresolved last observation; no inferred deletion |
| Standalone asset with null source ID | Allowed | Existing explicit/ordinary bounded decoder may try; cache read does not establish availability | Last indexed/unchecked; do not invent source health |

A source-row/state change during the request may be reported as catalog drift, but
cannot make that request cross from cache-only into original generation. A new
request or explicit scan may establish a different eligible state.

## Native interaction sequence

Root runs the independently reviewed helper once after confirming the desktop is
unlocked and the actual app window is active. The helper must use normal visible
controls and Qt input events. A `setFocus()` call alone is not user interaction;
if focus is programmatically established, record that fact and separately
confirm the control is visible, active, exposed, and receives the actual key or
button event. Capture only the generated application window.

1. After the explicit missing-root scan has recorded Offline, close and reopen
   the disposable library with the fixture still unavailable. Verify its prior
   catalog metadata, the explicit Offline observation, collection membership,
   and supported curation controls remain usable. Do not silently refresh source
   health from cache access.
2. Request the already-warmed preview. Confirm displayed pixels correspond to
   the fixture's known orientation/alpha/aspect expectations and that labels
   identify it as cached derived content, with the actual cache resolution and
   source/freshness limitation. Do not claim the preview represents a presently
   unchanged original.
3. Exercise captured-target safety: begin a request for a known asset, then
   change selection/filter/refresh or otherwise induce the reviewed drift case.
   The result must stay bound to the captured identity or cancel/refuse visibly;
   it must never show another asset under the original request.
4. Attempt each agreed original-only action while unavailable, including
   full-resolution inspection and external handoff. The control must be disabled
   or the service must refuse before dispatch. Never pass the cached preview to
   an editor as though it were the original.
5. Demonstrate cache-only operation independently of the original tree. Use the
   reviewed instrumentation/guard to prove no original open, enumeration, stat,
   hash, or decode occurs on cache hit. Cache access must validate the entry
   against captured asset ID/fingerprint/size, schema, decoder/color/output
   policy and containment rules.
6. Exercise exact-size, absent exact-size, corrupt exact candidate and corrupt
   preferred alternate. Use the final reviewed fallback policy: if exact exists
   but is corrupt/incompatible, refuse; if exact is absent and fallback is
   enabled, accept only the single preferred recognized alternate and label its
   actual edge/dimensions. If that alternate is corrupt/incompatible, refuse
   rather than searching another. Never claim requested or native pixel
   resolution for a smaller fallback; disclose actual source pixels and any
   enlargement used to fit/zoom it. A missing exact and fallback candidate is a
   visible placeholder/error.
7. In a disposable cache copy, test representative missing, truncated/corrupt,
   stale-identity/fingerprint, unsupported-schema/Pillow/policy, malformed or
   duplicate-key manifest, oversized manifest/lock/lease/PNG, dimensions/pixels,
   and unsafe path/type/symlink/reparse entries from the reviewed design. Check
   the 512-entry cap (or final reviewed value), count debris, and confirm
   overflow refusal. Each must fail visibly; while offline no case may regenerate
   from the original. Cleanup must stay inside the reviewed disposable cache
   root and preserve unrelated entries.
8. Confirm viewing itself does not alter catalog metadata, source records,
   ratings/favorites, collection membership/order, original bytes, or source
   health. Run SQLite integrity and foreign-key checks. If ordinary curation is
   part of the interaction, capture its separate explicit user action and verify
   only the expected catalog field changes.
9. Restore the same generated source root without rescanning. Health must remain
   at its last explicit observation and cached data must not trigger hidden
   reconciliation. Perform an explicit scan, then verify the source is
   reconciled and preview state follows the reviewed identity/version policy.
10. Exercise cancellation, close, late-result, and cleanup behavior with the
    reviewed bounded worker. Record acknowledgment, stop/reap/cleanup evidence;
    never report success if a helper remains active or owned storage is retained.

## Attempt 1 — scoped native result

Root ran the reviewed helper once on Nobara 44 with KDE Wayland, Python 3.14.7,
and Qt 6.11.2. The generated schema-v6 fixture contained three images and one
two-member collection. After warming six cache entries, the source was renamed;
an explicit failed scan established `offline`, reopening preserved that last
observed state, and restoring the source without scanning left it `offline`.
The explicit restored-root scan ended `paused` with zero pending work and errors.
Across five before/after catalog snapshots, SQLite integrity passed and foreign
key checks were empty; assets, collection membership/order, and curation data
were unchanged. Only source-health/entry observation fields changed during the
explicit scans. The source bytes and cache manifest matched their before-state
manifests after restoration and before fixture cleanup.

The grid requested edge 144 and used a cached edge-128 preview decoded at
64×128 pixels. The native grid capture is withheld because it exposes generated
fixture paths, UUIDs, and catalog details; only one selected card had loaded
while the other two were still loading. The published inspector capture is
byte-identical to the app-only raw inspector image. Its request for edge 2048
used cached edge 128 and displayed a 64×128 result labeled as cached content
from the last indexed state. The helper also verified alpha against the dark
background and an EXIF-orientation-6 JPEG using numeric quadrant markers. It
does not establish ICC/color fidelity, broad media coverage, or high-DPI behavior.

While offline, original-only controls were disabled; three QtTest key attempts
produced no click signals, inspector launch, or external worker dispatch. Cached
viewing remained available. The captured target stayed fixed after gallery
selection changed. The helper established focus programmatically and then sent
18 real QtTest key actions; this is not human keyboard-only or general
accessibility qualification. Window/model/worker shutdown, fixture removal, and
database integrity checks passed.

The raw receipt contains the contradictory field
`native_no_attempted_io_instrumentation: false` alongside prose saying the
native helper did not instrument attempted original I/O. The public derivative
omits that ambiguous boolean. Attempted-original-I/O instrumentation is
supported only by the separate Core child-spy test/log; the native result shows
the functional missing-root cached-view behavior, not an I/O spy.

The separate local frozen Linux package smoke returned a 48×40 RGBA preview
(7,680 bytes) from an exact cache hit at requested edge 256 after the original
was moved away. It reported cleanup success and applied a 512 MiB child
`RLIMIT_AS`. This is a narrow exact-hit worker check and address-space limit;
it does not measure RSS, process-tree peak memory, performance, or other
platforms. See the sanitized [attempt 1 result](evidence/cached-offline/attempt1/acceptance.json)
and [app-only inspector capture](evidence/cached-offline/attempt1/cached-inspector.png).

## Initial hosted attempt — macOS resource-limit gap

The first PR19 head `452fffa179bbd33cd97754f701880abd5eafd36c` exposed a
macOS-specific gap. Core macOS Python 3.11 job
[112151035612](https://github.com/isaaclepes/DefiantMaple/actions/runs/37427708198/job/112151035612)
and Python 3.13 job
[112151128938](https://github.com/isaaclepes/DefiantMaple/actions/runs/37427737452/job/112151128938)
each ran 258 tests and failed seven cached-preview tests. The returned child
error was `Required address-space ceiling could not be applied: ValueError`.
The Qt macOS job
[112151128629](https://github.com/isaaclepes/DefiantMaple/actions/runs/37427737426/job/112151128629)
failed its prerequisite Core step with the same seven failures; Qt tests,
packaging and artifact upload were skipped. Core Windows jobs were cancelled
by matrix fail-fast, so those jobs yielded no Windows test results. These logs
establish an attempted-but-unapplied limit and the refusal that followed; they
do not establish why `setrlimit` raised `ValueError`.

The reviewed policy treats only a Darwin request whose requested and effective
limit are both the default 512 MiB (536870912 bytes), and whose `setrlimit`
raises `ValueError`, as an explicit enforcement gap. The result must report
`address_space_enforced=false`, the limit as attempted but not applied, and no
address-space protection. The logs do not establish the cause of `ValueError`.
Other limit-query/application errors, malformed limits, intentionally
tightened requested caps, and application failures outside that exact case
still refuse. A successfully applied cap is reported enforced, including a
stricter inherited hard ceiling when the requested cap can be applied.
Linux retains its existing fail-closed behavior. This narrow exception does
not measure RSS or generalize to other errors or operating systems.

The historical Linux native attempt used helper digest
`4deaca23bca5f7c4e7f5bb75546e9ff153a7be59c378b7e1e56dd87abb3c6fc4` from a
reviewed working-tree snapshot while checkout HEAD was
`fe97dea460c64d514a9995cc01cdd67523d3b467`; the helper was not the HEAD blob.
The separate local
frozen Linux artifact SHA256 is
`d97478c33c36f162937cb57d9c2f7a7b4ff1de1516ef3e63b84c79368f7a339b`; it came
from a verified working-file export, not a published commit. Neither historical
receipt proves the amended macOS behavior. The narrow implementation correction
passed the focused 37-test Core/legacy slice. Fresh exact-head hosted checks,
including real-child and frozen fifth-smoke verification on the affected
runtime, remain required before acceptance.

## Required evidence and privacy

Keep original helper output, detailed paths, generated IDs, command logs, and
full snapshots private. The public acceptance derivative may contain only
fictional generated content and sanitized values. It must not include home or
source paths, raw catalog contents, executable arguments, UUIDs from private
libraries, model prompts, or unredacted filesystem logs. Include a SHA256 and
size for each raw/public JSON and capture, and verify captures are app-only and
byte-identical to the reviewed raw images. Run the project's public-artifact
checker and manually inspect paths/IDs and image pixels before publication.

Record the actual host, OS/display backend, geometry/scale, Python/Qt/decoder
versions, cache/source preparation, manifest and snapshot hashes, requested and
returned preview sizes, each action/result, measured limits versus declared
limits, `integrity_check`, foreign-key result, source/catalog before/after
comparisons, cleanup, capture hashes, and helper/source hashes. Preserve every
failed attempt and mark partial/setup failures accurately. Do not convert an
incomplete probe into a pass.

## Requirement scope and deferred claims

Task 33 maps FR-UX-007 and FR-MEDIA-004 directly; it exercises only the relevant
offline guards in FR-UX-002/FR-EXT-001 and bounded focus/job behavior from
FR-UX-006/010 and FR-JOB-001/003/004. It records only the applicable orientation,
alpha/aspect, parser-safety, cache/job-resource and public-privacy portions of
FR-MEDIA-001/003, SEC-PARSE-001/002, NFR-004/010/014. Broader rows remain
Partial until their own complete SDD gates pass. FR-UX-008 side-by-side
comparison, ICC/color fidelity, general accessibility, full supported-media
coverage, cache eviction policy, adopted performance budgets, actual editor
save/reconciliation, Windows/macOS native behavior, clean-install/upgrade/release
qualification, backup/restore/export, and real network-share failure are not
accepted by this generated Linux fixture gate.
