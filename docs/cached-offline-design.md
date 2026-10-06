# Cached-offline preview contract

Task32 delivers a read-only derived-preview path for the explicit-scan gallery.
Root and independent review cleared the initial design on 5 October 2026
(private proposal SHA256 `4d8b0fb2129ea92668e2b0353143cdb4577b40f7b59180dfebed4edddd870e1a`).
The baseline is PR18 merge `fe97dea460c64d514a9995cc01cdd67523d3b467`.
This contract adds no catalog schema, source reconciliation or cache eviction.

## Identity and freshness

`defiantmaple.cached_preview.CachedTarget` captures asset UUID, indexed SHA-256,
indexed byte size, media type, revision, absolute original path and optional
source ID. Capture is lexical; original paths and source roots are never
resolved, statted, enumerated, opened or hashed by cache-only inspection.

The spawned reader checks the local catalog's current UUID/content identity
before and after decode. Content drift refuses delivery. Rating/favorite
revision drift with unchanged content is not image invalidation. Path/source/
metadata drift is reported for the captured inspector rather than silently
rebasing it. Grid generations discard queued results from older selections,
filters, sizes or refreshes. A new asset at the same row/path is not a target.

A ready preview is **integrity/format checked and bound to the indexed key**.
The PNG digest agrees with its manifest; the manifest key agrees with the
catalog. It is not proof that today's original exists or has unchanged bytes.
A same-user actor replacing both PNG and matching manifest cannot be detected
offline without an independently trusted output digest. No new catalog-stored
digest or cryptographic authenticity claim is introduced.

## Compatibility and candidate selection

Existing cache schema 1 is retained. The accepted generation policy is the
current Pillow version, EXIF-oriented RGB/RGBA, first-frame PNG, with the
existing 512 MiB source/32768-dimension/80000000-pixel generation policy.
That source policy describes the existing generator; it is distinct from the
smaller cached-input limits below. Legacy schema1 inferred the output policy
from this fixed generator; it did not independently authenticate an explicit
output-policy field. An explicit different policy or unknown manifest field
is refused. ICC/color fidelity remains unqualified; no ICC transform is added.

Lookup examines only the captured UUID/current-fingerprint directory. It counts
every entry, including debris, and refuses after 512 entries. Recognized sizes
are 96–224 plus 32/64/128/256/512/1024/2048 and the exact requested supported
edge. The 135 unique usual sizes require 270 PNG/JSON partners, within the cap.

If exact is present, it is selected and must validate. If absent, choose the
smallest recognized larger edge, otherwise the largest recognized smaller
edge. A corrupt, partial or incompatible preferred entry refuses; a different
candidate does not hide it. Results report requested edge, actual cache edge
and decoded dimensions. Prior fingerprints, other UUIDs and arbitrary manifest
paths never serve as fallbacks. No compatible cache is an explicit no-cache
result, not permission to access an unavailable original.

## Containment and parsing

Cache locations are derived from UUID/fingerprint/fixed basename, never from a
manifest-provided path. On POSIX, each directory is opened relative to a pinned
parent with `O_DIRECTORY/O_NOFOLLOW`; regular-file leaves use non-following,
nonblocking opens, size bounds and descriptor/path identity checks. On Windows,
directory handles reject reparse points and withhold delete sharing while the
read is active; leaf handles do not follow reparse points. UNC cache storage or
unsupported containment primitives are refused rather than opened ordinarily.
Configured cache paths must be canonical. Only the supervisor's own private
temporary directory is canonicalized for standard OS temporary-path aliases.

JSON reads are bounded before parsing, duplicate keys/nonfinite/nested values
are refused, and only known scalar fields are accepted. The selected PNG must
match manifest bytes/digest and decode as a single-frame RGB/RGBA PNG with exact
declared dimensions. Descriptor/path changes during reading refuse it. This is
containment and integrity checking, not a sandbox; privileged/same-user races
outside these checks remain possible and must not be described as authenticity.

## Operational bounds and ownership

| Cache-only stage | Maximum |
| --- | --- |
| Manifest | 16 KiB |
| Compressed PNG | 20 MiB |
| Dimensions / pixels | 2048 per edge / 4,194,304 pixels |
| Normalized tightly packed RGBA | 16 MiB |
| Directory enumeration | 512 entries in one captured fingerprint directory |
| Admission/startup/catalog/read/decode/delivery | Five-second deadline |
| Supervisor polling | At most 50 ms per wait |
| Separate terminate / kill reap | One second each |
| Gallery queue / decoded in-memory entries | 32 requests / 256 entries |
| Proposed child address-space ceiling | 512 MiB where supported |

`CacheReadLimits` may tighten these ceilings; callers cannot silently expand
the deadline or address-space limit. Supported `RLIMIT_AS` failure refuses the
operation, apart from the explicitly reviewed Darwin default-ceiling rejection
below. Platforms lacking that control report the enforcement gap. Address
space/output bounds are not measured process-tree RSS acceptance. Source and
frozen-runtime compatibility of the proposed ceiling need separate evidence;
a necessary adjustment requires review, never silent removal.

The 6 October 2026 portability review permits one specific Darwin runtime gap:
after valid inherited/proposed limit checks, the child still attempts
`setrlimit(RLIMIT_AS, (536870912, inherited_hard))`. If that call raises
`ValueError` at the default/effective 512 MiB ceiling, cached reading may continue
with `address_space_enforced=False` and a note recording platform, attempted
bytes, exception and **cause not established**. Successful Darwin application
reports enforcement. Reading limits, `OSError`, malformed limits, tightened
caller ceilings and lower inherited-hard rejections remain refusals. Linux's
existing getrlimit/min/setrlimit and failure path are unchanged; Windows control
availability and cache containment are unchanged. All file, pixel, raw-output,
directory, deadline and child-cleanup limits still apply. This Darwin exception
provides no OS address-space or process/RSS memory guarantee.

Darwin does implement this control: [Apple XNU's resource handler](https://github.com/apple-oss-distributions/xnu/blob/xnu-11215.81.4/bsd/kern/kern_resource.c#L1345)
delegates it to Mach VM, which can reject a limit below the current map size.
The failed macOS26.6.2 arm64/Python3.11.9 CI child reported `ValueError` but did
not measure that map size; that mechanism is a possible explanation, not a
confirmed diagnosis or a claim that macOS lacks `RLIMIT_AS`.

One gallery worker owns its bounded queue and one cache child at a time; explicit
cached inspection has its own bounded child. The child produces normalized RGBA
into supervisor-owned private scratch. The QThread makes a copied QImage from
bounded raw bytes; the GUI makes QPixmap from QImage, never decodes a cache path.
Cancellation/timeout discards late results. Unreaped workers retain ownership
and scratch; replacement is refused until cleanup actually succeeds. Kernel-
blocked I/O is not universally interruptible. Cleanup is reported separately.

## Last-observed availability and original generation

Source health is the last explicit scan observation. Paused one-shot monitoring
is not offline; cache display never clears offline/error/missing/scanning facts.
Review state and catalog metadata remain independent.

| Catalog condition | Original generation after cache miss |
| --- | --- |
| Paused/watching source, exactly one indexed entry matching UUID/source ID/current path | Eligible only after a fresh off-GUI catalog requery |
| Offline/permission_denied/error/scanning source | Forbidden; cache-only |
| Missing/nonindexed/absent/inconsistent source entry | Forbidden; cache-only |
| Standalone null source ID and no linked entry | Existing bounded original decoder may try; availability remains unchecked until actual source work |

Admission is captured from the request row. A cache-only request cannot upgrade
to original generation because a later query appears eligible.
`fresh_generation_refusal` rechecks current content/path/source and exact entry
relation immediately before an eligible no-cache request uses the existing
generator. Refused/corrupt cache entries are not silently repaired. A restored
file alone changes no catalog health; explicit rescan performs reconciliation.
Original full inspection/external controls remain guarded, and the external
service retains its independent fresh checks and one-time dispatch permit.

Existing available-source generation retains its original decoder/cache-lock
deadlines; it is not globally a five-second operation. The narrow legacy-reader
exception caps manifest/lease JSON at 16 KiB and cached-output checksums at 20 MiB
in at most 1 MiB chunks. Nonregular/link/reparse inputs and unsafe ancestor lease
fallbacks refuse without following foreign files. Normal lease token/expiry,
original hashing, generation and atomic PNG/manifest publication stay unchanged.

## Product and acceptance boundary

**View cached preview** is explicit and separate from **Inspect full image**.
It labels actual cached dimensions, indexed-content freshness and last-observed
availability. Zoom/fit/pan/background controls do not recover original pixels.
No cached thumbnail is handed to an editor or labeled full resolution.
Known unavailable original-dependent actions are disabled; catalog curation,
collections and history keep their existing revision/conflict rules.

Task33 separates generated Core/offscreen tests, source-native desktop evidence,
frozen worker smokes, hosted CI and prior human external-tool feedback. The new
fifth package smoke exercises the actual Qt→spawn→RGBA cache path with a missing
generated original, preserving the existing four smokes and all metrics. It is
not native-display qualification or association dispatch.

The Darwin policy revision changes the service/source digest. Prior local Linux
native and frozen receipts retain their original source hashes and remain
historical evidence; they are not relabeled as executions of the revised file.
Exact revised-head hosted Linux and macOS real-child/frozen-worker checks are
required separately. Reusing scoped Linux visible behavior relies on independent
review that the Linux enforcement/read/decode path remains unchanged.

See [Task32](tasks/32-cached-offline-implementation.md),
[Task33](tasks/33-cached-offline-acceptance.md),
[independent review](tasks/34-cached-offline-review.md), and
[the user guide](cached-offline-guide.md). Comparison, whole-cache budget/eviction,
backup/restore/export, ICC fidelity, broad AT/platform/release qualification and
watching remain separate requirements, not completed by this contract.
