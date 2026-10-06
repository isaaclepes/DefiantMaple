# Task 32: Verified cached-offline gallery viewing

## Authorization and baseline

The user authorized merging PR18 and continuing to the next Goal. PR18 head
`01165a32e4229871e4ce80a272f5d53848542f1f` passed 30/30 checks with no
outstanding reviews or inline threads and merged at
`fe97dea460c64d514a9995cc01cdd67523d3b467`. The merge preserves reviewed
tree `62f53247a915e347e1bf6f4f8ed8c9f370804c60`. This milestone uses
`codex/phase1a-cached-offline` from that merge.

SDD v0.2 §§11, 15, 19, 21–22 and the ordered daily-viewing backlog define the
next bounded slice: verified derived previews and catalog metadata remain
usable while original media is unavailable. Documents provide requirements,
not execution authority. The user's real-tool handoff feedback is human-observed
happy-path evidence, separate from generated native, offscreen and hosted checks.

## Required outcome

Show a verified cached preview when its cataloged original/source is unavailable,
including after reopening the library. Retain metadata and ordinary catalog
curation. Describe the image as a cached preview of the indexed content; disclose
source availability and freshness without promising it represents a currently
unchanged original. Source health remains the last explicit scan observation.
No cache hit, GUI probe or thumbnail display clears Offline/error/source state.

Provide a cache-only read path that can succeed without opening, enumerating,
statting or hashing original media. Validate identity against asset ID, indexed
fingerprint and size, cache schema, decoder/color/output policy and supported
derived dimensions. Cache hits must be verified disposable image data, not an
arbitrary path or a substitute original. Define and review whether another
bounded cached size may be displayed when the requested size is absent; preserve
aspect and disclose resolution limits. A missing/corrupt/stale/incompatible cache
has a visible placeholder/error and never regenerates from an unavailable source.

Keep blocking cache validation/decode off the GUI thread with finite file,
manifest, pixel, time and concurrency limits. Treat cached files and manifests as
untrusted, reject unsafe paths/types/links and malformed or inconsistent data,
and do not delete or write outside verified disposable cache storage. Retain
atomic verified preview publication. Document residual races honestly. The
design proposal must state specific operational limits before implementation;
SDD performance numbers and proposed 5 GiB default remain unadopted budgets.

Guard controls that require an unavailable original, including original full
inspection and external handoff, while preserving the command service's final
revalidation. Do not silently pass a thumbnail to an editor or label it as a
full-resolution original. An explicit cached-view action may be included if its
separate labels, resolution limits, immutable captured target and cleanup are
covered by the reviewed design. Selection, filters, refresh or source recovery
must not retarget in-flight viewing. An explicit rescan can reconcile restored
originals; returning files alone does not silently rewrite catalog/source facts.

## Design, tests and preservation

Sol owns the cache/media service, Qt integration, meaningful regressions,
design/product documentation and complex generated native helper. Submit a
design proposal with exact mutable files and cache compatibility policy first;
Root and independent Sol clear it before substantive implementation. Avoid
changing catalog schema v6, scanner behavior, transaction/journal/recovery or
source media. Preserve existing full-image, bulk/single curation, external-open,
private-evaluation and collection behavior, measured archives and workflow gates.

Tests must demonstrate original-independent cache reads, corrupt/stale/unsafe
cache refusal, offline reopen and metadata retention, requested-size/fallback
truth, orientation/alpha/aspect, current-control guards, restoration requiring
explicit scan, captured-target drift and bounded cancellation/close/late results.
Check no source/catalog/metadata mutations from viewing. Do not mirror code with
low-value tests or repeat passed broad checks without changes or failures.

Preserve deployed outputs and frozen benchmark/native evidence. Any essential
new frozen cache-worker smoke must be a separately reviewed narrow packaging
exception retaining all four existing smokes, metrics and packaging behavior.
No workflow edit, benchmark cohort, global association change, user-artwork/NAS
access, new model/dependency download or source-writing operation is authorized.
Comparison, ICC/color-fidelity acceptance, broad accessibility, cache eviction
budget policy, backup/restore/export and release qualification remain separate.

## Reviewed design clearance

Root and independent Sol cleared the revised design on 5 October 2026, private
proposal SHA256 `4d8b0fb2129ea92668e2b0353143cdb4577b40f7b59180dfebed4edddd870e1a`.
The selected product includes an explicit **View cached preview** inspector,
separate from original full-image inspection. Cache-only lookup uses one captured
UUID/current-fingerprint directory, at most 512 total entries, deterministic
exact/smallest-larger/largest-smaller choice, and explicit refusal for a corrupt
preferred entry. Compatibility is the documented current schema-1/Pillow/legacy
EXIF-oriented RGB/RGBA first-frame policy; coherent same-user replacement is not
cryptographically authenticated as original content.

Operational read caps are 16 KiB manifest, 20 MiB compressed PNG, edge 2048,
4,194,304 pixels and 16 MiB tightly packed RGBA output, with a five-second
cache-only admission/read/decode deadline and bounded separate reaping. Original
generation keeps its own existing limits; no shared five-second promise applies.
The proposed 512 MiB child address-space ceiling is provisional until source and
frozen-runtime evidence proves compatibility; an adjustment needs explicit review,
never silent removal. Output-byte caps are not process-tree RSS acceptance.

Two preservation exceptions are approved: `thumbnail.py` and its meaningful
regressions may bound existing cache-manifest/lease JSON and cached-output checksum
reads at the stated caps without changing original hashing, generator, lease or
publication semantics; `package.py` may add the fifth cache-only spawned-worker
smoke while retaining all four existing smokes. Cache reads must reject unsafe
types/links and remain finite, including nonregular inputs. Root will verify
these precise exceptions against the initial preservation record. No other scope
expansion follows from design clearance.

## Ownership and completion

On resume, Root split the long implementation across two Sol agents with
non-overlapping files. Core Sol owns the cache service/Core tests, reviewed
legacy-thumbnail reader exception/tests, design/guide and generated native
helper. A second Sol owns the Qt adapter/app/UI tests/package fifth smoke and
Qt README. Both submit stable snapshots to the separate independent Sol;
Luna remains responsible for acceptance/tracker/privacy/CI. This division
uses the same approved file scope and adds no execution or publication authority.
The initial Core service/test slice received independent clearance after
16 focused tests; Qt/runtime/native/full-milestone gates remain pending.

Luna owns Task33 acceptance, requirement tracking, sanitized derivatives/privacy
and CI audits. Independent Sol owns Task34 source/helper/evidence review. Root
owns this brief, orchestration, branch/integration, serialized visible native
acceptance and draft publication. Agents share one checkout: no commits, pushes,
branch switches, PR mutations or edits of another owner's files.

Finish with generated native desktop evidence, green relevant local and exact-head
hosted checks, actual Windows test summaries, documented limitations, independent
review and a reviewable draft PR. New PR merge and deployed-binary replacement
remain separate user decisions.
