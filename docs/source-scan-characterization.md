# Repeated source-scan characterization

This benchmark characterizes the existing scan protocol before any production
optimization. It repeats the same fictional local fixture as the
[paired profiler](source-scan-profiling.md): 2,048 initial 32x32 RGBA PNGs, eight
encoded contents, directory groups of 256 and page size 256. Each trial creates
new files and a new catalog. Cancellation, fresh enumeration after an earlier
file appears, simulated Offline retention and online recovery remain required.
There is no source or catalog input argument.

## Paired execution and provenance

`benchmarks.source_scan_profile_series` exposes `pair`, internal `trial`, and
`aggregate` commands. Four pairs use BI, IB, IB, BI, where B is baseline and I
is instrumented. A pair runs its two variants sequentially in fresh Python
children. Both variants retain the soak's allocation tracing; only I installs
the operation wrappers. Pair indices are one-based. Local test fixtures may use
64 through 2,048 files and two or four pairs; hosted run identities require the
2,048/256/four-pair experiment and all three OSes when aggregating.

From the repository root, with `requirements.txt` installed, run each ordinal
once, writing to a dedicated directory outside tracked source. For example:

```sh
mkdir -p /tmp/defiantmaple-characterization-local
python -W error::ResourceWarning -m benchmarks.source_scan_profile_series pair \
  --count 2048 --page-size 256 --pairs 4 --pair-index 1 \
  --trial-timeout 720 --pair-timeout 1800 \
  --run-id local --run-attempt 1 \
  --metrics /tmp/defiantmaple-characterization-local/pair-1.json
```

Repeat that command with indices 2, 3 and 4 and corresponding output names.
Aggregate only those four reports:

```sh
python -W error::ResourceWarning -m benchmarks.source_scan_profile_series aggregate \
  --input-dir /tmp/defiantmaple-characterization-local \
  --count 2048 --page-size 256 --pairs 4 --platforms Linux \
  --run-id local --run-attempt 1 \
  --metrics /tmp/defiantmaple-characterization-local-summary.json
```

Use `Darwin` or `Windows` for the actual local platform. Keep the summary outside
the input directory: aggregation reads every JSON report recursively from its
dedicated input directory. It accepts at most 24 files, each at most 4 MiB, and
refuses symbolic report files. A missing, duplicate, malformed or unexpected
report makes the series incomplete.

`--revision` is optional locally and otherwise must equal actual `git HEAD`.
It cannot assign provenance to different code. Each parent, child and aggregator
reads actual checkout identity. Under GitHub Actions, `--run-id` and
`--run-attempt` must match `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT`; without those
variables the accepted identity is `local`/1. CI also passes its actual checkout
revision. Identity changes before/after measurement prevent completion.

The public `code` record includes the actual revision, whether measured code is
dirty, separate checkout dirtiness, and SHA-256 digests of six fixed public code
files: the three scan benchmarks and `defiantmaple/catalog.py`, `sources.py` and
`media.py`. These are code digests, never media digests. An uncommitted local run
therefore discloses its measured file contents instead of treating the base
commit as a complete code identity. Pairs must match those digests and measured
code dirtiness. Unrelated output files may change checkout dirtiness without
changing measured code identity. Preserve reports before editing measured code:
aggregation authenticates against its current checkout too.

## Report contract

| Schema | Contents |
| --- | --- |
| `defiantmaple.source-scan-profile-trial.v1` | Variant, actual code/run/runtime identity, configuration, aggregate soak result and instrumented phase breakdown. Baseline has an empty phase breakdown. |
| `defiantmaple.source-scan-profile-pair.v1` | Declared ordinal/order, raw trial samples with their positions, pair wall interval, cleanup outcome and fixed issue codes. |
| `defiantmaple.source-scan-profile-series.v1` | Requested platform/ordinal grid, validated raw pair reports, fixed issues and summaries only for a complete grid. |

The existing `defiantmaple.source-scan-profile.v1` API/CLI and baseline-first
256-file Core smoke remain compatible. New timing fields are additive there.
Series consumers should use the nanosecond fields instead of rounded seconds.

Raw trials retain observation/indexing page counts, original-file count, final
count including the earlier new file, exact elapsed intervals, peak traced Python
allocation, operation counts and timings. `fresh_resume` in the soak includes
the fresh restart plus its stable follow-up; the instrumented phases separate
these passes. The actual generated catalog `PRAGMA user_version` is read back.
Public fixture details include recipe, geometry, encoded-content count,
directory grouping, original byte total and added-file byte total.

Runtime records contain reviewed platform/architecture, numeric OS release,
Python/SQLite/Pillow/PNG codec versions, logical CPU count and available runner
image identity. CPU model, RAM total, filesystem, storage, power policy and
antivirus remain null because this experiment does not verify them. Runner
metadata describes the environment, not a reference desktop. Within one OS,
all four pairs require matching runtime, fixture and schema records. Across
OSes, code, configuration, encoded fixture totals and Python/Pillow versions
must match; observed OS/SQLite/codec versions remain platform-specific.

Validators require exact keys, bounded numbers, known statuses/diagnostics and
consistent phase/count/integrity records. JSON parsing rejects duplicate keys,
NaN and infinity. Arbitrary metadata, error strings, SQL, rows, paths, host/user
names, asset UUIDs and per-file hashes are not accepted report fields. The
shared public artifact checker applies these schemas as well as its existing
path/private-field checks. Reports are written with atomic replacement.
Cancellation's unchanged-file count must fit its reported page prefix: prior
pages completed, and the final page may be partial or not yet processed. A
reported page count cannot contradict the amount of work in that phase.

Archive validation uses the recorded fixture rather than recompressing PNGs on
the reader's machine. It checks the fixed recipe/geometry/counts, conservative
encoded-size guards, eight-content cycle/prefix arithmetic and recorded hash-byte
totals. The known first payload's length comes from the added resume file.
Current trial production still authenticates its descriptor against its actual
encoder. Both variants in a pair and the complete cohort must have identical
recorded fixture descriptors; a genuine cross-platform byte difference remains
incomparable. No fixture bytes or codec settings are changed by this policy.

Reviewed runner-image names include `win25-vs2026`, `macos26` and
`macos26-arm64`, alongside the existing forms. Numeric image-version components
may have leading zeroes. Arbitrary host labels, paths and unreviewed suffixes
remain refused. These names describe actual image identity; they are not
hardware or performance guarantees.

## Scope and interpretation

The cache label is `fixture-created-and-stat-checked-os-cache-uncontrolled`.
Fixture generation and initial stat checks precede timing; neither fresh
processes nor fresh catalogs establish a cold OS cache. Separate hosted jobs
sample a runner pool and do not establish repetitions on identical hardware.
Balanced order controls the declared schedule; it does not remove cache,
filesystem, machine-load or runner variation.

The memory label is `python-tracemalloc-scan-protocol-after-fixture-setup`.
Peak bytes cover traced Python allocations during the soak protocol, including
its verification queries and private identity sets. They exclude fixture setup,
known-byte verification after tracing, and untraced/native allocations. They
are neither RSS nor whole-application, thumbnail, GUI or machine memory.
Both variants pay tracing overhead; instrumented trials add wrapper overhead.

For each OS, summaries show median/min/max of each variant's three elapsed
intervals, every paired I/B ratio, and ratios grouped by declared order. A zero
baseline interval retains its raw sample with a null ratio. Instrumented
operation summaries retain calls and inclusive/exclusive nanoseconds. Exclusive
spans partition each individual phase; inclusive spans overlap. Component
medians need not sum to a median whole-pass interval. Four pairs and two pairs
per order do not justify tail latency, a throughput budget or compliance.
Ratios below one do not establish a speed improvement. Long transaction exits
remain observations; they do not prove fsync, antivirus or a storage cause.

## Failure, integrity and hosted bounds

Children use parent-created temporary trees with ownership markers; each trial
has its own base. The parent bounds child waits, then termination and kill/reap
attempts. A signal request does not prove exit. Cleanup requires proven worker
exit and matching directory/marker ownership. An unreaped worker or changed
ownership retains storage and makes the pair incomplete. The next child does
not start after a failure. Public cleanup fields disclose retention without
publishing temporary paths.

A normal child/pair failure preserves earlier validated samples, emits a fixed
incomplete diagnostic/report and exits nonzero. Incomplete series reports have
no summaries. Failed output replacement preserves a prior report file and
retains validated samples in the incomplete stdout report. There are no silent
retries, discarded slow samples or automatic cap increases.

The [dedicated workflow](../.github/workflows/scan-characterization.yml) runs on
relevant pull requests only. Its Linux/macOS/Windows by four-ordinal matrix has
12 independent pair jobs, each capped at 35 minutes. Parent/child operational
caps start at 30/12 minutes. One pair per job bounds the Windows wall time;
these caps are operational limits, not performance targets. Attempt-specific
artifacts keep the raw pairs separate. The aggregator requires the exact
12-pair grid and uploads a complete or incomplete series report. Hard runner,
setup or job termination can prevent any pair JSON; normal bounded failures
produce sanitized incomplete reports. The five-minute job margin reduces that
risk but cannot guarantee artifact delivery. Missing artifacts fail coverage.
Existing Qt/Tauri workflow filters remain in effect.

Original generated bytes are checked against known payloads after timing and
tracing. Size/mtime, asset counts and privately compared stable UUID sets must
survive cancellation, fresh restart, simulated Offline and reconnection. Patch
bindings and tracing restore on success/failure; SQLite settings, result values
and rollback behavior remain guarded by the profiler tests. Production scanner
calls, transactions and pragmas are unchanged.

## Acceptance and next experiment

The implementation's focused warning-as-error scan suite includes one real
tiny balanced series (four fresh 64-file children), malformed report/provenance/
grid tests, failure/reaping/ownership tests, atomic output and actual public-
checker integration. This is implementation evidence. Local 2,048-file
acceptance, one full Core suite, independent review and current-head hosted
measurements belong to [Task 15](tasks/15-characterization-acceptance.md) and
[Task 16](tasks/16-characterization-review.md); they are pending at the
implementation freeze. No new 2,048 timings are claimed here.
During independent review, an initial local cohort exposed a cancellation
page-capacity validation gap. The validator and regression were corrected;
those reports retain their original code digests. Fresh final-code acceptance
is required rather than rewriting old report provenance.
After initial publication, CI exposed archive-reader encoder dependence and
startup rejection of official image names. Those validator-only corrections
retain all five timed code files byte-identically. Earlier-driver measurements
can remain archived with their original revision/digests; they are not relabelled
as the corrected driver. Current-head hosted acceptance and final interpretation
remain separate gates.

Use all accepted samples to identify repeated measured categories and their
variability before proposing one bounded optimization or attribution probe.
Connection reuse or batching would require explicit recovery, rollback and
locking analysis; long transaction exits alone do not justify changing
durability. If the category is not repeatable, collect narrower evidence first.
10k/100k/500k cold indexing, varied/large media, thumbnails/concurrent UI,
reference desktop and numeric budgets, controlled cold-cache runs and actual
SMB/NFS interruption remain separate experiments. This increment does not
establish the SDD's 100k responsive-gallery or background-work acceptance.
