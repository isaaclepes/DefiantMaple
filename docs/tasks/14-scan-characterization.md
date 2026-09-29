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
