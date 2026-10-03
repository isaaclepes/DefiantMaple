# Repeated source-scan characterization

This benchmark characterizes the existing scan protocol before any production
optimization. It preserves the fictional workload of the
[paired profiler](source-scan-profiling.md): 2,048 initial 32x32 RGBA PNGs, eight
contents, directory groups of 256 and page size 256. The series uses pinned PNG
bytes with a new recipe identity so every OS scans identical encoded contents.
The [accepted hosted attempt-3 results](../benchmarks/source-scan-results/2026-10-02/README.md)
contain the complete three-OS/four-pair cohort, its raw archive, provenance and
bounded next attribution experiment.
Each trial creates
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
256-file Core smoke retain their legacy runtime-encoded fixture by default.
New timing fields are additive there. The series explicitly selects the
canonical fixture through benchmark-only keyword arguments; neither CLI
accepts arbitrary media or fixture paths.
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

Archive validation never recompresses PNGs on the reader's machine. Historical
`tiny-rgba-png-eight-content.v1` records retain fixed recipe/geometry/count checks,
conservative encoded-size guards, eight-content cycle/prefix arithmetic and
recorded hash-byte totals. The known first payload's length comes from the added
resume file. Authentic historical archives remain readable even when the reader
uses a different encoder; they are not current-code measurements.

Current series trials use `tiny-rgba-png-eight-content-canonical.v1`. Eight own
generated payloads are embedded in the already-hashed soak module, in the
original solid-color order. Their lengths are 105, 108, 108, 108, 109, 108, 108,
108 bytes. The 2,048-file fixture is exactly 220,672 bytes and the resume addition
is 105 bytes. Before storage or tracing, setup authenticates pinned sizes,
per-payload hashes and the ordered corpus hash. All eight valid PNGs decode to
the original 32x32 RGBA colors; creation uses the embedded bytes rather than a
runtime encoder. Payload verification and decoding tests remain outside scan
timing. The runtime PNG codec field still describes actual decoder capabilities.

The canonical descriptor has an exact cyclic/prefix byte contract, alongside
the existing closed geometry/count fields. Its immutable recipe and the recorded
soak-file digest identify the corpus without adding per-media hashes to reports.
The child producer, parent before sample append, and current aggregator require
this exact canonical descriptor. Both variants and the complete cohort must have
identical recorded fixtures. Legacy/canonical mixtures and genuine encoded-byte
differences remain incomparable; archive acceptance cannot authorize a current
producer to use historical bytes.

The earlier hosted run demonstrated separate fixture and checkout differences:
Linux recorded 220,672/105 bytes while macOS recorded 229,120/110. All six measured
Windows source hashes exactly matched LF-to-CRLF conversion of the same committed
files. Scoped `text eol=lf` attributes now retain identical raw source bytes on
all platforms. Code authentication still hashes actual raw checkout bytes. Those
earlier reports retain their original recipe, revision, runtime and hashes;
neither equal Linux byte totals nor a new validator relabels them as canonical
measurements. Earlier reports did not record per-payload hashes, so their totals
alone cannot prove byte-exact identity to the new corpus. New comparable evidence
requires a fresh complete hosted grid.

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

The [dedicated workflow](../.github/workflows/scan-characterization.yml) runs for
every eligible pull request, including docs updates, on the default opened,
synchronize and reopened events. It begins with a visible publication gate. When
measurement is required, its Linux/macOS/Windows by four-ordinal matrix has
12 independent pair jobs with the following operational bounds:

| Platform | Child limit | Pair parent limit | CI job limit |
| --- | ---: | ---: | ---: |
| Linux/macOS | 720 seconds | 1,800 seconds | 35 minutes |
| Windows | 1,440 seconds | 3,000 seconds | 55 minutes |

The API/CLI defaults remain 720/1,800 seconds. Separate validated maximums are
1,800 seconds per child and 3,600 seconds per parent; the second child receives
at most the parent's remaining allowance. The Windows limit changed after a
first baseline child was censored at 720 seconds with no phase sample, while
earlier Windows pairs completed in 732–1,097 seconds. This is a fixed bounded
completion allowance; the other three canonical Windows pairs completed in
907–1,242 seconds. It is not a tail bound, phase diagnosis or promise of completion.
The censored report remains incomplete with its original identity and cleanup
record; it cannot supply a phase duration or an accepted performance sample.
One pair per job bounds total work. These caps are not performance targets.
Attempt-specific
artifacts keep the raw pairs separate. The aggregator requires the exact
12-pair grid and uploads a complete or incomplete series report. Hard runner,
setup or job termination can prevent any pair JSON; normal bounded failures
produce sanitized incomplete reports. The five-minute job margin reduces that
risk but cannot guarantee artifact delivery. Missing artifacts fail coverage.
Existing Qt/Tauri workflow filters remain in effect.

## Guarded evidence publication

The dedicated Mac jobs select `macos-26-intel`, a standard Intel configuration
listed with four CPUs in GitHub's
[runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
The earlier arm64 run used the same image/version but recorded three logical
CPUs for pair 3 and five for pairs 1/2/4, which strict runtime equality correctly
refused. Those samples remain separate. The new cohort measures Intel macOS;
it does not establish arm64 performance or identical physical hardware. Actual
runtime equality remains required; the label is not a guarantee against future
runner-image or capacity changes. Core/Qt/Tauri runner choices are unchanged.

The cheap gate may skip this dedicated pair matrix and its aggregator only on
an attempt-one `pull_request/synchronize` with a proven documentation/evidence
update. It authenticates `after` against the PR head, actual checkout against
`GITHUB_SHA` and the base/head merge parents, and an available `before` ancestor.
It reads the full before-to-after endpoint tree delta with NUL-delimited names
and rename detection disabled. Every changed path must be under `docs/` or
`benchmarks/source-scan-results/`; README and all other paths request measurement.
It also compares raw protected files in the predecessor, current merge and
working checkout: six measured files, attributes, requirements, dedicated
workflow/helper and their acceptance tests. Base drift cannot hide behind a
documentation-only PR head delta. The gate checkout fetches at most 128 history
levels; unavailable endpoints conservatively request measurement.

Skipping also requires tracked, unchanged JSON containing a strictly parsed
COMPLETE hosted canonical series: exact three-OS/four-pair/2,048/256 grid, all
24 trials, matching current six raw source digests, measured `dirty=false`, valid
phase/math/cohort records and GitHub-hosted runtime identity. `checkout_dirty`
may be true after artifact downloads. Legacy/local/incomplete archives cannot
authorize skipping. Duplicate keys, nonfinite numbers, malformed or unreadable
archives and proof errors request measurements. Input/report sizes, path counts,
candidate count and Git command durations are bounded.

Intrinsic archive validation is not cryptographic proof that a hosted run took
place. Root and independent review authenticate its original artifact/log origin
before publication. The gate preserves that archive's measured revision,
run/attempt and raw bytes; it identifies the accepted earlier evidence in the
current job summary. It never invokes the live aggregator on old reports,
rewrites identity or creates new performance samples. Both costly jobs require
the same successful gate decision. The aggregator still runs after failures of
a requested pair grid; gate/output failure remains visible and cannot appear as
an accepted experiment. Open/reopen events, reruns, force-push ambiguity,
unavailable refs, missing evidence and any other input change measure.

Adding/changing this gate, operational controls or its tests requests a fresh
cohort. Later validated result/documentation publication can retain that cohort
without a second dedicated matrix. Existing Core/Qt/Tauri workflows are unchanged
and may still run their own timed jobs or checks on a later evidence commit.

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
checker integration. At implementation freeze, local 2,048-file acceptance,
one full Core suite, independent review and current-head hosted measurements
were pending under [Task 15](tasks/15-characterization-acceptance.md) and
[Task 16](tasks/16-characterization-review.md). The accepted hosted results are
now recorded below; that historical freeze did not itself claim new timings.
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

The first revised-control hosted attempt at PR head
`d99ebecc8a222ff03dbc28e778c91c3f4aa0007f` was
[run 36634086725, attempt 1](https://github.com/isaaclepes/DefiantMaple/actions/runs/36634086725),
measuring Actions merge revision `0112155e6f4b53f2447bde074c9c7d6c1da07017`.
All 12 pairs completed with two trials, the canonical fixture, matching measured
code digests and proven child reaping and owned-storage cleanup. The aggregate
retained all 24 trials but correctly returned `incomplete`, two `incomparable`
issues and no summaries. Linux and Intel macOS each recorded one runtime.
Windows pairs 1, 2 and 4 recorded `win25-vs2026` image version
`20260922.246.2`; pair 3 recorded `20260925.250.1`. The version is the sole
difference among the recorded Windows runtime objects, so the two reported
comparability failures correspond to the transition into pair 3 and back at
pair 4. This is an inference from the raw records and strict cohort key; the
public issue records themselves do not include a cause string. The
[preserved incomplete aggregate](../benchmarks/source-scan-results/2026-09-29/incomplete/aggregate-head-d99ebecc-run-36634086725-attempt-1.json)
is 587,645 extracted JSON bytes, SHA-256
`701584cfa3f92c64b9243b3a5663f49d62f1a8a535fe680238e65842068760d1`.
That digest identifies the JSON extracted from its authenticated job log; it
does not identify the uploaded ZIP or prove byte identity of a ZIP member.
The incomplete attempt and earlier local/hosted reports retain their original
code, run and fixture identities. They are not pooled with a new attempt.

The only justified next measurement from that incomplete attempt was a full
12-pair rerun for the unchanged source head after the Windows image rollout.
Its new run attempt and artifacts must meet the original complete-grid and
within-OS runtime criteria. A failed-jobs-only rerun of the aggregate or
splicing pairs from different attempts cannot repair the cohort. No source-cost
attribution follows from the incomplete attempt.

The full rerun became run `36634086725`, attempt 2, for the same measured merge
revision. All 12 pair jobs produced complete two-trial JSON reports with
matching recorded runtimes within each OS, including Windows image version
`20260925.250.1` in all four Windows pairs. The
[macOS pair-3 job](https://github.com/isaaclepes/DefiantMaple/actions/runs/36634086725/job/110922831958)'s artifact
upload failed after its pair report was logged. The aggregate could download
only 11 pair artifacts and correctly returned `incomplete`, one `missing_pair`
issue and no summaries. The
[preserved incomplete aggregate](../benchmarks/source-scan-results/2026-10-02/incomplete/aggregate-head-d99ebecc-run-36634086725-attempt-2.json)
is 538,594 extracted JSON bytes, SHA-256
`d83e771c5cdc07d542c1393b122f206a9823154a7c80c66b75fdee7e69af4a13`;
the separately
[preserved decoded macOS pair-3 JSON](../benchmarks/source-scan-results/2026-10-02/incomplete/macos-pair-3-run-36634086725-attempt-2.json)
is 44,052 bytes, SHA-256
`db53d7b99cb9d6f3636c83eeefde38117873485e28be6fc202df458ed415c65b`.
Those digests identify log-extracted JSON, not an uploaded ZIP member. The
logged pair demonstrates completed local measurement and cleanup, but cannot
replace its missing attempt-specific uploaded artifact or make the aggregate
complete. Attempt 2 remains a separate operational diagnostic; a complete
12-pair workflow attempt was still necessary and was supplied by attempt 3 below.

Use all accepted samples to identify repeated measured categories and their
variability before proposing one bounded optimization or attribution probe.
Connection reuse or batching would require explicit recovery, rollback and
locking analysis; long transaction exits alone do not justify changing
durability. If the category is not repeatable, collect narrower evidence first.
10k/100k/500k cold indexing, varied/large media, thumbnails/concurrent UI,
reference desktop and numeric budgets, controlled cold-cache runs and actual
SMB/NFS interruption remain separate experiments. This increment does not
establish the SDD's 100k responsive-gallery or background-work acceptance.

The existing run's **attempt 3** met that complete-grid requirement. At source
head `d99ebecc8a222ff03dbc28e778c91c3f4aa0007f`, the same measured merge
revision `0112155e6f4b53f2447bde074c9c7d6c1da07017` and tree
`bf273ba83c64b48947be0a760efd28cd243cc7ca`, all 12 jobs supplied pair
artifacts from one attempt. The aggregate is `complete`: 12 pairs, 24 valid
trials, no issues and one matching runtime/fixture/code cohort per OS. Its
[exact archived JSON](../benchmarks/source-scan-results/2026-10-02/hosted-series-run-36634086725-attempt-3.json)
is 764,855 bytes, SHA-256
`980360da60a12d6f0437ca0d227e5bb65cc7103b53a01da49cbc87a1725fc9b2`.
It was reconstructed from the authenticated decoded aggregate job log; the
uploaded ZIP's member-byte identity was not independently proved. The
[results ledger](../benchmarks/source-scan-results/2026-10-02/README.md)
records artifact metadata, all pairs, n=4 medians/ranges, n=2 order strata,
operation inclusive/exclusive spans and traced-memory scope. Earlier attempts
and the local series remain separate.

On Windows, instrumented indexing's `sqlite_transaction_exit` wrapper totaled
89.022–229.739 s exclusive across four pairs (median 131.346 s) with 4,137
calls in each. The observed span includes original context-exit behavior and
does not distinguish commit, rollback, no-op exit or storage causes. Linux pair
3 and Windows show substantial variation, so these data provide no speedup,
tail bound or reference-hardware budget. The one bounded next experiment is a
same-machine Windows attribution repeat that stratifies exit timings by
transaction and exception state while preserving the scan protocol, cleanup,
rollback, locking and durability behavior; its success/stop criteria are in
the results ledger. No production optimization is part of this increment.
