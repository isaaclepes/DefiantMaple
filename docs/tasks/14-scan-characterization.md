# Task 14: Repeated comparable scan-cost characterization

Owner: Sol. Status: implementation complete; frozen for independent acceptance
and review. Root owns publication and final current-head evidence.

Baseline: merged PR 12, main `317e9ebd713869e229166065b7fb990613905a6a`.
Branch: `codex/phase1-scan-characterization`. Read the existing profiler, soak,
tests, [profiling evidence](../source-scan-profiling.md), and SDD sections 18,
19 and 21.3 as requirements. Root's goal is a reviewed, reproducible evidence
increment, with green current-head checks and a reviewable PR.

## Experiment contract

- Preserve the comparable fictional fixture: 2,048 initial 32x32 RGBA PNG files,
  eight encoded contents, directory groups of 256, page size 256, and the
  existing cancellation/fresh restart/Offline/recovery protocol.
- Run four matched baseline/instrumented pairs per hosted OS. Fixed order:
  BI, IB, IB, BI. Each pair runs its two variants sequentially in fresh Python
  children with fresh generated trees and catalogs.
- Each OS/pair ordinal is a separate CI job. Call these hosted-runner-pool
  samples; different jobs do not establish same-hardware repetitions. No cold
  OS-cache claim: fixture creation and initial stat checks precede timing.
- Keep the existing paired v1 profiler API/CLI and 256-file CI smoke compatible.
  Prefer a benchmark-only trial helper plus a new series/pair aggregation module.
  Add precise durations and fixture/integrity reporting to the soak without
  changing scanner calls or protocol semantics.

## Reports and failure handling

Retain raw aggregate samples before summary: declared order/ordinal/variant,
exact phase intervals, counts/pages, traced peak Python allocation and measured
instrumented operations. Record actual generated catalog schema, code revision,
Python/SQLite/Pillow/PNG runtime, reviewed environment fields and public fixture
geometry/byte totals. Unknown hardware, storage, power and antivirus facts remain
unknown. Do not publish host/user names, paths, SQL, rows, UUIDs, per-file hashes
or exception messages. Validate actual complete and partial JSON with the privacy
checker. Memory is traced Python allocation, not RSS/native/UI/whole-machine use.

Summaries show raw paired ratios plus median/min/max and order groups; n=4 does
not justify tail latency or compliance claims. Exclusive spans partition their
own trial; inclusive spans overlap. Long transaction exits do not prove fsync,
antivirus or a storage cause. Ratios below one do not prove a speed improvement.

The aggregator must authenticate the exact three-OS/four-pair grid, both variants,
schedule, code/dependency/fixture/schema identity, uniqueness and completeness.
Reject missing, duplicate, forged, malformed or incomparable inputs without a
complete-success summary. Failed/timeout runs retain validated completed aggregate
samples, explicit incomplete status and a nonzero exit; no silent retries or
sample trimming. Write report files atomically.

Children use only new parent-owned temporary storage. Bound terminate/kill/reap;
cleanup only owned trees after worker exit. Retain an unreaped worker's storage
and mark the result incomplete instead of removing live data. Operational caps
start at 35 minutes per CI pair job, 30 minutes per pair parent and 12 minutes
per child. These contain work; they are not throughput budgets. Root reviews
actual incomplete evidence before any justified timeout change or retry.

## Invariants and validation

Retain original pending/indexed/page/count, cancellation, earlier-file fresh
restart, Offline record/UUID retention, healthy recovery and source size/mtime
assertions. Verify the known generated source bytes after the timed protocol.
Instrumentation must restore patches/tracing on every exit, preserve SQLite
settings/results/rollback, and refuse an existing tracer.

Test schedule/order, subprocess isolation, closed report validation, exact
aggregation/math, identities/coverage, failures/timeouts/reaping/owned cleanup,
atomic output and sanitized diagnostics. Use one tiny real generated series for
integration; no timing-threshold or implementation-mirror tests. Run focused scan
tests; Task 15 owns one full Core acceptance after freeze and the local 2,048
series. Do not repeat unchanged Qt/Rust locally.

## Ownership and handoff

Own `benchmarks/source_scan_profile.py`, `benchmarks/source_scan_soak.py`, new
`benchmarks/source_scan_profile_series.py`, `tests/test_scan_profile.py`, new
`tests/test_scan_profile_series.py`, `docs/source-scan-profiling.md`, new
`docs/source-scan-characterization.md`, and this task's status/results. Root owns
the new workflow, shared privacy checker, README/audit/orchestration and publication.
Provide the exact CLI/schema/artifact interface before workflow integration.
Declare FROZEN with hashes, changed files, checks and limitations.

No commits/pushes/branch switches, PR actions, external messages or extra agents.
No production scanner/catalog/metadata/UI edits, durability/transaction/pragma
changes, private media or real mount interruption. Recognition stays advisory.
10k/100k/500k cold media, varied media, thumbnails/concurrent UI, defined reference
desktop budgets and real SMB/NFS evidence remain separate experiments.

## Recommendation gate

Use all current-head samples to identify repeated measured categories and their
variability. Recommend one bounded next probe/reuse/batching experiment with
explicit recovery/rollback/locking consequences, or state what narrower evidence
is missing. No production optimization follows automatically from this report.

## Implementation handoff — 2026-09-28

Implemented the benchmark-only trial helper and balanced pair/series module,
with closed trial/pair/series v1 schemas. The original paired v1 API/CLI remains
compatible. Exact nanoseconds, actual generated schema readback, known fixture
byte totals, explicit memory/cache scopes, private stable-identity assertions
and post-tracing known-byte verification supplement the existing soak.

The series authenticates actual checkout/run/attempt, measured-code digests and
runtime before/after execution. Local dirty code is disclosed. Fixed BI/IB/IB/BI
children use isolated owned storage; bounded reaping precedes cleanup, with
retention/incomplete results for unreaped workers or changed ownership. Strict
aggregation preserves raw samples and requires the requested complete grid,
cohort identity and exact summary math. The guides document the CLI, reporting
scope, failure/artifact limits and separate larger-media/reference-budget gaps.

Focused verification:

```sh
python -W error::ResourceWarning -m unittest discover -s tests -p 'test_scan*.py' -v
python -W error::ResourceWarning -m scripts.check_public_artifacts
git diff --check
```

The configured scan venv passed **42 tests in 7.657 seconds**, with zero failures,
errors or skips. This includes one real tiny series of two balanced pairs/four
64-file children; existing cancellation/resilience and paired-v1 tests; closed
metadata/provenance/grid/math validation; patch/tracing restoration; generated
byte integrity; timeout/reaping/ownership/atomic-output failures; and complete,
partial and tampered reports through the shared public checker. Environment:
CPython 3.14.7, SQLite 3.51.2, Pillow 12.3.0, PNG codec 1.3.1.zlib-ng. No timing
thresholds were asserted. Development failures exposed the installed codec's
version suffix and a private-key substring in an assertion label; both were
fixed while retaining the original privacy assertions.

Before freeze, independent static review identified missing requested child
configuration validation and insufficient raw phase-count reconciliation.
Both were corrected with regressions: an invalid second child preserves the
first completed sample, and inconsistent known phase totals/pages cannot form
a complete summary. Hosted aggregate identities now require the full three-OS,
four-pair, 2,048/256 experiment; local declared subsets remain available.
Root separately corrected duplicate-key parsing in the shared public checker
and added `test_private_eval.py` regressions (six focused tests passed in
0.080 seconds, as reported by root). Those root-owned files are part of the
independent frozen review scope together with the new workflow. The public
artifact privacy checker and `git diff --check` both passed at this handoff;
changed guide/task Markdown links resolve to existing local files.

Task 15 owns one full Core suite and four comparable local 2,048/256 pairs after
freeze; Task 16 owns independent review. Neither full Core nor a new 2,048 run
was performed by this owner. Hosted measurements, source-cost attribution and
the recommendation gate remain pending. No production/source-media/transaction
change, commit, branch switch, publication or additional agent was performed.

### Narrow validation correction and refreeze

Independent review of the first actual local 2,048/256 cohort found that
cancellation's 703 unchanged files in three pages could be reported as one
page without refusal. Root authorized this narrow correction after all workers
were idle. Cancellation counts now fit the completed-page prefix and final
partial page; scanner calls, timing, tracing and benchmark protocol are unchanged.
The fictional report helper now supplies capacity-consistent pages, and a
regression retains the actual aggregate seed (703 files/three pages) while
refusing contradictory one-, two- and four-page reports without a summary.

The final focused warning-as-error scan suite passed **43 tests in 7.556
seconds**, with zero failures/errors/skips. Read-only validation accepted all
four original pair reports and refused 12 page-count mutations. Their original
provenance was preserved; this verifies shape compatibility, not final-code
measurement identity. Privacy, whitespace and changed Markdown-link checks
passed again at refreeze. The updated 14-file hash manifest replaces the initial
freeze manifest. No full Core or additional real benchmark was run by this owner.

Because the series-file digest changed, the initial local cohort is retained as
earlier evidence and cannot be relabelled as the corrected code. Root/Task 15
will run a fresh coherent final-code local cohort and its justified Core check.
Task 16 will verify the correction and continue independent review. Final
interpretation still awaits current-head complete hosted evidence.

### CI portability correction — 2026-09-29

At published head `8608256d30c10b5f10dec3d939d7bb8bf70ca420`, macOS Core unit
tests passed but the public checker rejected the archived Linux series. A
read-only reproduction preserved archive SHA-256
`edd64c49fd4c69d359c20f67aada965f4390b89c4427af846a8f6d14343c12d6`
and showed rejection caused solely by recomputing fixture bytes under a
fictional different reader encoder. Separately, dedicated macOS/Windows pairs
failed before child execution with minimal incomplete reports. The runtime
image allowlist refused official names such as `macos26` and `win25-vs2026`;
the Windows token is defined by GitHub's
[image build helper](https://github.com/actions/runner-images/blob/main/helpers/GenerateResourcesAndImage.ps1).
Observed image headers were macos-26-arm64/version 20260907.0351.1 and
windows-2025-vs2026/version 20260922.246.2. Numeric leading-zero version
components were already supported and are now covered by a regression.

Root authorized the narrow fix after local work was idle and all twelve hosted
pair jobs had finished. Intrinsic archive validation now checks closed fixed
recipe/geometry/counts, bounded encoded bytes, cycle/prefix arithmetic and
recorded phase hash-byte consistency without reader-runtime recompression.
Current production of a trial still validates against its own actual encoder.
Pair variants explicitly require the same recorded fixture, and cross-platform
aggregate fixture equality remains strict. Official image-name grammar was
extended narrowly; arbitrary suffixes/free text remain refused. Scanner calls,
fixture contents, codecs, timing, tracing, catalog and durability are unchanged.

The affected series suite passed **24 tests in 1.716 seconds**, with resource
warnings treated as errors and zero failures/errors/skips. The unchanged real
tiny-series test was deliberately excluded; no timed trial or full Core suite
was repeated by this owner. Checks cover the actual archived report under a
reader whose descriptor function raises, cycle prefixes including nonmultiples
of eight, malformed byte/recipe/geometry refusal, current-generation refusal,
byte/hash reconciliation, distinct within-pair/cohort fixtures, official image
names/version components and private metadata refusal. A first development
assertion treated changing only a recorded first-payload length as necessarily
inconsistent; that can be legitimate if other content lengths differ. The
regression instead supplies an impossible bounded first-payload contribution,
retaining both malformed-data refusal and legitimate encoder variation.

Public artifact privacy, whitespace and changed Markdown-link checks passed.
All prior report bytes/provenance and the five timed code hashes remain unchanged;
only the series driver/validator hash changes. Old local measurements are retained
as earlier-driver evidence, not relabelled. Independent frozen fix review and
current-head CI remain required before publication acceptance. Any actual
cross-platform encoded-byte difference must remain an incomplete cohort and
requires evidence before a separate fixture decision.

### Native-runtime mocked-test correction — 2026-09-29

At corrected head `68a8516f6d85a01fc6a17c0f241a39ed2aa292b1`, push Core
macOS Python 3.11 ran 164 tests in 23.377 seconds: 163 passed and the new
distinct-fixture refusal test failed its one-preserved-sample assertion. The
unchanged real tiny-series test passed. The failing mock selected the first
cross-platform grid entry, which always has a Linux runtime. On Darwin or
Windows, the real pair parent correctly refuses that first child before append;
this was a runtime-dependent test fixture assumption, not a partial-report defect.

A read-only platform-only reproduction passed on Linux and failed with zero
preserved samples on Darwin and Windows. The test now constructs its mock with
the native parent runtime. Its hash-byte, pair/cohort comparability and one-sample
preservation assertions are unchanged; the validator is unchanged. Isolated
mocked checks then passed under all three platform families with zero failures,
errors or skips. The affected series suite passed **24 tests in 1.401 seconds**
with resource warnings treated as errors; the unchanged real tiny-series test
was excluded. No local timed trial or full Core suite was repeated.

All six measured code files and all retained report bytes/provenance remain
byte-identical to the portability freeze. Only this test and this task record
change. Independent frozen verification and current-head CI remain required.

### Canonical fixture and checkout-byte correction — 2026-09-29

The corrected-head hosted reports exposed genuine fixture differences: Linux
recorded 220,672 initial bytes/105 resume bytes; macOS recorded 229,120/110.
Separately, all six code hashes in each of four complete Windows pairs exactly
matched LF-to-CRLF conversion of the committed LF files (24/24 matches), despite
`checkout_dirty=false`. These are distinct comparability failures. Strict
aggregation remained incomplete. All existing reports retain their original
bytes, recipes, runtime, revision and source hashes.

Root authorized implementation after independent written design review. The
series now selects `tiny-rgba-png-eight-content-canonical.v1`: eight compact own
generated PNG payloads embedded in the already-hashed soak module. Pinned sizes,
per-payload SHA-256 and an ordered length-prefixed corpus hash authenticate setup
before storage or tracing. The 862-byte corpus preserves the original 32x32 RGBA
colors/order, eight contents, and the observed Linux 2,048-file totals. Historical
reports did not record per-payload hashes, so matching totals do not establish
byte-exact identity to every earlier hosted bitstream.

Keyword-only recipe selection preserves the legacy soak and baseline-first
paired-v1 API/CLI defaults. Intrinsic archives accept the closed legacy recipe
with bounded cycle/prefix arithmetic, or the new recipe with an exact canonical
byte contract. Current series production, the parent before append, and the
aggregator explicitly require the canonical descriptor. Valid legacy reports
cannot become current samples even when byte totals match. Strict same-pair and
cross-platform fixture equality remains; no report/hash normalization occurs.

The focused warning-as-error scan suite passed **53 tests in 6.039 seconds**,
with zero failures/errors/skips. It includes pinned corpus/hash/size checks,
PNG framing/CRC verification and every RGBA pixel; encoder independence;
unknown recipe and corruption/reordering/pin refusal before storage/tracing;
exact descriptor/hash-byte reconciliation; untouched historical archive reading;
legacy/canonical producer, parent and aggregate refusal; patch/tracing restoration
in both variants; and the existing scanner cancellation/resilience checks.
The one real tiny balanced series ran four isolated 64-file canonical children,
with the legacy generator and PNG encoder forced to raise inside each child.
All recovery/source-byte/identity assertions passed. The existing paired-v1
64-file real run also retained its legacy recipe. No additional tiny run, local
2,048 cohort or full Core suite was performed by this owner.

Root separately added six scoped `text eol=lf` attributes and the dedicated
workflow path trigger. Root reports that an isolated generated Git checkout with
`core.autocrlf=true` retained all six committed LF byte hashes; no active or global
Git setting changed. Public artifact privacy, whitespace and changed local
Markdown-link checks passed at freeze. The manifest includes attributes,
workflow, checker and retained local archive alongside owner files.

Profile/soak/series code hashes change; all three production code hashes remain
unchanged. Clock windows, tracing scope, scanner calls, transactions/pragmas,
cancellation/restart/Offline/recovery behavior and source integrity assertions
are unchanged. Retained local measurements are earlier-recipe evidence. Task 15
owns one justified full Core acceptance; Task 16 owns frozen independent review.
Root will obtain a fresh current-head three-OS/four-pair hosted grid with the
existing operational caps. No extra local 2,048 run is required. Final performance
interpretation and the bounded next attribution probe await comparable evidence.

### Bounded Windows allowance, Mac cohort and evidence gate — 2026-09-29

Canonical run `36548534031`/attempt 1 measured merge revision
`fa40b68ac1923afa8e410043091c61935f65e8d3` for source PR head `425a5970`.
Windows pairs 1/2/3 completed in 1,241.763017, 1,176.7815846 and 906.6740555
seconds; pair 4's first baseline child was censored at 720 seconds, with no
trial sample and pair wall 722.4142137 seconds. Its worker was proven reaped
and owned storage removed. The earlier legacy cohort's pair walls ranged
731.8439335–1,097.0103987 seconds. Individual child wall was not recorded;
phase sums are lower bounds, and the censored report cannot identify a phase
latency or fsync/antivirus/storage cause. All original reports remain unchanged.

The same canonical aggregate correctly refused Darwin pair 3's three logical
CPUs against five in pairs 1/2/4; arm64/image/version and other runtime fields
matched. The aggregate is incomplete with three incomparable issues (Windows
timeout and the two CPU-count transitions). Root and independent review approved
the dedicated `macos-26-intel` standard label, listed with four CPUs in GitHub's
[runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
The fresh cohort will explicitly measure Intel macOS; old arm64 samples remain
separate, and runtime equality remains strict. The label does not establish
identical physical hardware or guarantee an unchanged future image.

Root authorized the fixed Windows child/parent/job allowance of 1,440/3,000
seconds/55 minutes. Linux/macOS retain 720/1,800 seconds/35 minutes. The driver
now validates separate maxima of 1,800 child and 3,600 parent seconds; API/CLI
defaults remain 720/1,800. This is an operational completion allowance, not a
tail bound or guarantee. Reaping, cleanup, deadline/remaining-child behavior,
sample preservation and failure reporting are unchanged. No automatic retry,
fixture/durability change or local 2,048-file repeat was introduced.

The reviewed dedicated-workflow gate is bundled with that necessary control
change. Every eligible PR receives a cheap visible job on the default opened,
synchronize and reopened events. Only a proven attempt-one
synchronization with a complete before-to-after docs/evidence endpoint delta,
matching current merge/predecessor/working raw inputs and a tracked complete
hosted canonical archive may skip the dedicated matrix and aggregator. Protected
inputs include the six measured files, attributes, requirements, workflow/helper
and their acceptance tests. Missing/invalid proofs, other paths/events, reruns,
nonancestor/mismatched refs, base drift and malformed archives measure.
Closed valid historical local/incomplete series and diagnostic pair records may
coexist with accepted current evidence. Archive origin still requires root/independent artifact/log
authentication; intrinsic JSON is not cryptographic execution proof. Original
revision/run/attempt/raw bytes are preserved; no live aggregation of old data
or relabelling occurs. Both costly jobs share the successful gate decision;
gate/output failure remains visible. Core/Qt/Tauri workflows are unchanged.

Affected warning-as-error verification passed **12 publication-gate tests in
3.804 seconds** and **28 mocked series tests in 1.236 seconds**, with zero
failures/errors/skips. Synthetic temporary Git/event/archive cases cover full
multi-commit endpoint deltas, sensitive rename/deletion, base/worktree drift,
event/merge/ancestor identity, reruns, archive shape/math/grid/recipe/digests,
measured dirtiness, tracked/raw-byte/symlink/size/duplicate-key refusal, valid
historical coexistence, no old-data aggregation, fixed outputs and visible
output failure. Duration probes cover unchanged defaults, independent upper
bounds, pre-storage refusal and timeout cleanup. The unchanged real tiny-series
test was excluded; no timed trial or full Core suite was repeated by this owner.
The gate grew from 10 to 12 cases during development to cover a malformed archive
after a valid one and valid historical/incomplete coexistence; final checks
retain those assertions.
The coexistence case was then extended to include a valid minimal failed pair
and a complete diagnostic pair beside the accepted series. Its targeted rerun
passed **one test in 0.263 seconds**, without repeating the unchanged cases.

PyYAML syntax/control, privacy, whitespace, local Markdown-link and unchanged
timed/production/archive hash checks pass at freeze. The manifest adds gate
helper/tests to all prior relevant files. Only the series driver among the six
measured hashes changes; five timed/protocol/production hashes remain identical.
Independent frozen review and affected acceptance precede publication. The
updated controls require a fresh complete hosted three-OS/four-pair cohort;
later verified docs/evidence publication can retain that cohort without another
dedicated matrix. Existing workflows may still run their own checks/timed jobs.
