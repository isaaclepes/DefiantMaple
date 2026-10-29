# Linux background preview preparation

This local feature integrates the managed thumbnail admission prerequisites with
Linux thumbnail generation and the Qt gallery. It is work in progress, not a
release or native-runtime qualification. Earlier prerequisite documents describe
their own historical scope; their statements that no caller is wired do not
describe this integration.

## Behavior

The gallery prepares previews for its current query, including rows not currently
visible, through one bounded page of at most 256 rows at a time. Preparation
uses the existing worker and isolated decoder. Foreground requests take priority,
with one background item allowed after four foreground items to avoid starvation.
An already running item is subject to cancellation and cleanup; priority is not
a promise of immediate preemption or a latency deadline.

The preparation control pauses/resumes work. Query invalidation cancels the old
epoch; stale page replies and results cannot advance the new preparation pass.
Unavailable or refused assets are reported without changing their source health.
Quota, ownership and cleanup uncertainty hold preparation and retain a truthful
status instead of treating the pass as complete.

## Managed writes and reads

The selected policy is **5 GiB per library, no automatic deletion**. Admission
counts logical bytes and bounded file/entry/depth inventories, including unknown
cache files and conservative control/reservation allowances. This is cooperating
write admission, not a physical filesystem quota or a guarantee about external
writers. A reservation can refuse new work before observed bytes reach 5 GiB.

A newly created private managed namespace may enroll; an existing namespace must
already have its permanent gate and matching catalog/root binding. An unknown
existing namespace, including an empty one, is not adopted or modified. Catalog
copies, changed identities, unknown pending ownership, ambiguous child startup,
and uncertain cleanup hold new writes. PID disappearance or age does not grant
recovery authority. No user data, old previews or unrelated residue is deleted
to clear a hold. Only positively owned protocol controls are released after
terminal verification.

Validated cached reads remain available while new generation is held, subject
to their own content, identity, policy and bounded-decode validation. A cache
hold does not authorize source probing, cache repair or original-file mutation.
Publication requires the captured output directory identity and a validated
PNG/manifest pair; uncommitted residue is preserved and charged.

## Limits

- Linux alone uses this preparation/write adapter; behavior on other platforms
  remains unchanged. This work makes no Windows quota or preparation claim.
- Lexical placement and captured directory identities reject supported unsafe
  placements and substitutions. Bind-mount aliases are not fully detected or
  qualified; this is not a general filesystem-alias containment guarantee.
- Retry/decode waits are bounded where implemented. Filesystem calls themselves
  can block and are not preempted by those deadlines.
- The 20 MiB encoded-output bound limits PNG payload size. It is not an RSS
  bound, total-memory bound or guarantee against kernel/filesystem delays.
- Recovery of ownership lost across processes remains unresolved and fails
  closed. There is no automatic eviction or uncertain-owner reclamation.

## Evidence status

Focused generated-fixture checks in the existing isolated Python environment
passed during this correction: 11 Linux writer integration tests, 22 managed
admission tests, and 21 cached-preview tests. These cover existing empty/unknown
namespace preservation, immediate ambiguous-start/cleanup holds, recognized
cache reuse, publication substitution refusal, retained reads and bounded
multi-size discovery. The multi-size case counts one Linux operation entry plus
258 child entries once; overflow still refuses at entry 513. Test authority and
admission registries are isolated from the real account. These counts describe
those focused runs; they do not certify all later edits or the full suite.

An earlier generated 260-image Qt acceptance passed at its recorded source:
260 original decodes, 260 cached second-pass reads, no original decodes during a
memory-cold revisit, bounded queues/pages, and foreground overtaking waiting
background work. Its source-manifest SHA-256 was
`ff5cfb2d7229afde0baa5be531fcd827a94f61052f8d55b02cc73fb951e50777`.
That source predates the ownership, hold-classification, discovery-accounting
and query/cancellation corrections. The 260-image run is historical evidence,
not acceptance of the changed tree. Its pause/resume occurred between complete
passes, so it does not establish active cancellation.

A fresh generated 260-image offscreen Qt run on 29 October 2026 passed in
166.087 seconds (164.278 measured functional seconds). Its captured 372-file
source manifest was identical before and after the run:
`e5c32b97383654b12ad7108850547ac2561757c102d9bccdd50993e5bd21b8d8`.
The test-log SHA-256 was
`1cda9696db065256deb321d8c8916e2912708be235c73dec8c27e9e76bfea3ce`.
It reported 260 original decodes and 260 cached second-pass reads, sampled
foreground queue maximum 0, background page maximum 251 and visible pixmap
maximum 1. Its assertions also covered persistent revisit and cleanup. This
run establishes its named generated scenario against that captured source;
it does not establish native UI or whole-product acceptance.

After that run, the native recovery regression exposed directory handles opened
before gate creation returning an empty enumeration view even though the gates
existed. Control-name and budget inventories now reopen `.` relative to the
pinned directory, verify the captured inode, and enumerate that fresh handle.
This preserves fail-closed ownership and avoids omitting newly created controls.
The production changes after the fresh 260 run are limited to
`managed_thumbnail_admission.py` and `thumbnail_budget.py`, with a regression
added in `test_thumbnail_budget.py`; the exact-source caveat remains. The
260-image test was not repeated after this correction. Focused verification
passed all 57 recovery/admission/Linux integration tests and all 24 budget tests,
including the previously failing native recovery test, unchanged, and the new
fresh-enumeration regression. Those focused runs support the correction; they
do not turn the earlier 260 result into an exact-final-source run.

Broad regressions, Qt correction tests, privacy checks, hosted CI, independent
review, native/frozen builds and cross-platform qualification are separate
gates. Record their results against the actual tested source. No unrecorded
pass, final CI/native qualification, publication, deployment or binary
replacement is claimed here.
