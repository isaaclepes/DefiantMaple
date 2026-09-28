# Aggregate source-scan profiling

The opt-in profiler attributes measured costs before changing the production
scanner. It wraps the existing [fictional soak](source-scan-resilience.md) and
runs that exact protocol twice: first without instrumentation, then with
benchmark-only wrappers. Each run has fresh generated PNG files and a separate
temporary local catalog. No source path argument is accepted. Both runs retain
the soak's cancellation, earlier-file fresh restart, simulated Offline retention,
reconnection, final asset-count, and source size/mtime assertions.

## Reproduce

From the repository root, with `requirements.txt` installed:

```sh
python -m benchmarks.source_scan_profile --count 2048 --page-size 256 \
  --metrics /tmp/defiantmaple-source-scan-profile-2048.json
```

The minimum count is 64. Reports use schema
`defiantmaple.source-scan-profile.v1` and contain the two aggregate soak results,
runtime versions, paired elapsed comparisons, and per-phase operation counts and
timings. The phases are observation, indexing, cancellation, fresh resume, stable
follow-up, simulated Offline, and online recovery. Setup, fixture generation, and
post-pass assertion queries are outside the component timings. No paths, SQL
text/values, per-file identifiers, rows, or exception messages are retained. The
CLI emits only a failed status and exception type if execution fails; it exits
nonzero and does not emit a success report.

The local report is intentionally outside the repository. The Core workflow runs
the bounded sample below on hosted Windows, Linux, and macOS, then uploads
`source-scan-profile-metrics.json` as a platform-specific artifact:

```sh
python -m benchmarks.source_scan_profile --count 256 --page-size 64 \
  --metrics source-scan-profile-metrics.json
```

The bounded sample supplies a reproducible instrumentation gate. Its timings
cannot be compared directly with the prior 2,048-file Windows soak. Run the
2,048/256 invocation on Windows for that comparison. The CI figures below are
the first paired, 256-file cross-platform profile sample; they do not replace a
like-for-like 2,048-file Windows run.

## Timing interpretation

All spans use `time.perf_counter_ns()`. `inclusive_seconds` includes the measured
children of a call. `exclusive_seconds` subtracts those children's inclusive
intervals. Inclusive indexing contains SQLite setup, statements, result fetching,
transaction exits, connection closes, and SHA-256 operations. Adding those
inclusive measurements to indexing would count them twice.

Within each phase, summing **all operation-exclusive times**, including
`scan_pass` exclusive, reconciles to `scan_pass` inclusive / `elapsed_seconds`
within floating-point rounding. This partition is tested with a deterministic
clock and an actual generated run. It is a partition of instrumented elapsed
time, not an overhead-free estimate. Wrapper creation, clock calls, bookkeeping,
and return delegation are partly charged to their measured parent or operation.

| Operation | What is measured | Practical limit |
| --- | --- | --- |
| `scan_pass` | One complete paged pass, or the direct Offline scan | Exclusive time includes unclassified scanner work: ownership/paging, observation preparation, counters, callbacks, and wrapper overhead. It is not a proven filesystem or SQLite category. |
| `enumeration` | `_iter_candidates`: traversal, candidate stats/path resolution, sorting, and enumeration callbacks | The cached inventory is reused across pages, so one enumeration call per healthy pass is expected. Root identity checks elsewhere remain unclassified. |
| `catalog_connection_setup` | Original `connect` context entry, including URI preparation, SQLite open, PRAGMAs/schema check, and transaction context entry | Exclusive time includes Python context/setup work and wrappers; it does not isolate a single SQLite internal stage. |
| `sqlite_connection_open` | Original `sqlite3.connect`, with a timing subclass as the connection factory | Includes SQLite/Python connection construction. No database settings are changed. |
| `sqlite_statement_execute` | `Connection.execute`, including statement preparation/execution and its initial result work | Includes the original PRAGMA/schema statements. Counts are API calls, not SQL statement categories or logical transactions. |
| `sqlite_result_fetch` | `fetchone`, `fetchall`, `fetchmany`, and cursor iteration steps | Includes row materialization. Iteration's final `StopIteration` is a counted normal call. No row contents are retained. |
| `sqlite_transaction_enter` | Original SQLite connection context entry | Does not assert that a write transaction began. |
| `sqlite_transaction_exit` | Original SQLite connection context exit | May commit, roll back, or do nothing. `transaction_exits_with_transaction` counts exits with `in_transaction` true; `exceptional_transaction_exits` counts exits receiving an exception. Neither proves a particular fsync duration. |
| `sqlite_connection_close` | Original connection close | Close and context-exit timing do not isolate disk flushes, filesystem waits, antivirus, or SQLite internals. |
| `catalog_connection_teardown` | Original catalog context exit, containing the SQLite context exit and close | Its inclusive time overlaps those two operations. |
| `index_file` | Original indexing call: path/stability checks, media read/signature sniff, SHA-256, and persistence | Exclusive time still combines file reading, stats, sniffing, Python data/UUID work, and wrappers. Read I/O is not separately measured. |
| `sha256_constructor`, `sha256_update`, `sha256_digest` | Original digest construction, update, and digest/hexdigest calls | `sha256_bytes` counts bytes given to the digest. These intervals do not measure the file reads that supply those bytes. |
| `rename_hash_validation` | Original fallback rename hash validation | It includes nested digest calls when used. This fixture has no rename candidates, so the local zero-call result provides no rename-cost evidence. |

Instrumentation replaces only benchmark-process module bindings and delegates to
the original scanner/catalog code. The SQLite subclass preserves connection
arguments, default pragmas, row factory, original transaction entry/exit, and
close behavior; the cursor and digest wrappers delegate returned values. Context
patches restore on normal return, scan failure, and partial instrumentation setup
failure. The profiler supports a single installation and single-threaded scans;
it is not intended to be installed inside a running application. An existing
`tracemalloc` session is rejected so its state is not disrupted.

## Measured local sample

The 2,048/256 invocation above completed on 2026-09-27, on Linux x86_64 with
CPython 3.14.7, SQLite 3.51.2, and installed Pillow 12.2.0. The repository currently
pins Pillow 12.3.0; this local sample used the already-installed version recorded
in the report. Both variants observed and indexed the original fixture in eight
pages, retained 2,049 assets after recovery, resumed after cancellation, and
left original generated source sizes/mtimes unchanged.

| Soak elapsed interval | Baseline | Instrumented | Instrumented / baseline |
| --- | ---: | ---: | ---: |
| First observation | 2.247 s | 2.709 s | 1.206 |
| Stable indexing | 4.381 s | 5.030 s | 1.148 |
| Fresh restart plus stable follow-up | 5.809 s | 6.334 s | 1.090 |

Both runs enable the original soak's `tracemalloc`; peak traced allocation was
7,171,678 bytes for the baseline and 7,200,857 bytes for the instrumented run.
This is Python allocation tracking, not process RSS. Baseline is always first,
catalogs are fresh, and OS cache, storage state, and other load are uncontrolled.
The ratios show the observed paired difference, not isolated wrapper overhead
or a stable performance bound. No repetitions or cold-cache experiment were
performed.

| Instrumented component | Observation calls | Observation inclusive / exclusive | Indexing calls | Indexing inclusive / exclusive |
| --- | ---: | ---: | ---: | ---: |
| Whole pass | 1 | 2.708628 / 1.185300 s | 1 | 5.029699 / 1.357177 s |
| Enumeration | 1 | 0.266888 / 0.266888 s | 1 | 0.268063 / 0.268063 s |
| Catalog connection setup | 2,089 | 0.596482 / 0.382135 s | 4,137 | 1.080424 / 0.688229 s |
| SQLite connection open | 2,089 | 0.116233 / 0.116233 s | 4,137 | 0.213232 / 0.213232 s |
| SQLite statement execute | 6,267 | 0.475891 / 0.475891 s | 16,507 | 1.105208 / 1.105208 s |
| SQLite result fetch | 9,298 | 0.080057 / 0.080057 s | 22,610 | 0.175363 / 0.175363 s |
| SQLite transaction exit | 2,089 | 0.078626 / 0.078626 s | 4,137 | 0.169460 / 0.169460 s |
| SQLite connection close | 2,089 | 0.056932 / 0.056932 s | 4,137 | 0.109246 / 0.109246 s |
| Index file | 0 | 0 / 0 s | 2,048 | 2.113014 / 0.788673 s |
| SHA-256 update | 0 | 0 / 0 s | 2,048 | 0.008470 / 0.008470 s |

The full JSON also includes transaction entry, catalog teardown, digest
construction/finalization, and recovery phases. Exclusive sums across the full
operation set were 2.708628253 seconds for observation and 5.029698669 seconds
for indexing, matching their whole-pass intervals. Observation had 2,064 exits
with an active transaction; indexing had 4,112. Neither phase had exceptional
transaction exits. Indexing gave SHA-256 220,672 bytes across the 2,048 tiny PNGs.

These local measurements establish connection-call frequency and attribute the
instrumented intervals on this machine. They do not identify the cause of the
earlier Windows slowdown. Tiny, repeated 32x32 PNGs do not represent large media
hashing throughput; the fixture uses only eight distinct image contents. The
relatively small SHA-256 update interval is evidence only for this fixture.
No durability setting, transaction boundary, SQLite pragma, or production scan
behavior has changed. Any later optimization must retain the existing recovery
checks and obtain platform-specific before/after measurements.

## Hosted CI profile sample (256 generated files)

PR #10 head `5859c7c65fa44896ae61b463177f4f0441320124` ran the same paired
256-file, page-size-64 profile command on hosted Linux x86_64, macOS ARM64, and
Windows AMD64 with CPython 3.13.15 and Pillow 12.3.0. All three
`scan-cost-profile` jobs in [Core run 36378460690](https://github.com/isaaclepes/DefiantMaple/actions/runs/36378460690)
completed successfully. Each pair used fresh catalogs and generated fictional
PNGs, and passed the soak's interruption/resume, Offline retention, asset-count,
and source-integrity checks.

| Hosted OS | Baseline observation / indexing / fresh resume | Instrumented observation / indexing / fresh resume | Instrumented / baseline ratios |
| --- | ---: | ---: | ---: |
| Linux x86_64 | 0.615 / 1.327 / 1.387 s | 0.632 / 1.473 / 1.410 s | 1.028 / 1.110 / 1.017 |
| macOS ARM64 | 0.511 / 1.050 / 0.985 s | 0.635 / 1.274 / 1.186 s | 1.243 / 1.213 / 1.204 |
| Windows AMD64 | 6.637 / 15.419 / 13.908 s | 6.222 / 14.290 / 11.321 s | 0.937 / 0.927 / 0.814 |

The per-platform component times below are from the **instrumented** run. Values
are seconds; “index file” shows inclusive/exclusive. These fields overlap and
must not be summed. `scan_pass` exclusive is remaining unclassified work within
the pass. The notably long Windows transaction-exit intervals are observed
measurements, not proof of fsync, antivirus, storage, or any other cause.

| Hosted OS | Phase | Scan pass exclusive | Enumeration | Catalog setup exclusive | SQLite transaction exit | Index file inclusive / exclusive | SHA-256 constructor + update + digest |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Linux | Observation | 0.141 | 0.059 | 0.080 | 0.216 | 0 / 0 | 0 |
| Linux | Indexing | 0.174 | 0.060 | 0.157 | 0.582 | 0.759 / 0.185 | 0.004 |
| macOS | Observation | 0.104 | 0.075 | 0.105 | 0.201 | 0 / 0 | 0 |
| macOS | Indexing | 0.119 | 0.069 | 0.173 | 0.450 | 0.603 / 0.168 | 0.004 |
| Windows | Observation | 0.160 | 0.070 | 0.123 | 5.215 | 0 / 0 | 0 |
| Windows | Indexing | 0.195 | 0.068 | 0.247 | 12.076 | 7.937 / 0.302 | 0.007 |

Each instrumented scan phase reported zero operation failures. The aggregate
`fresh_resume_seconds` interval includes the fresh restart and the subsequent
stable follow-up; the instrumented phase breakdown reports `fresh_resume` and
`stable_followup` separately. Each timing comes from one run per variant per
hosted runner. Baseline always ran first. Paired ratios include instrumentation
and tracemalloc overhead plus uncontrolled run
order, filesystem, cache and hosted-runner variation; values below 1.0 are not
evidence that instrumentation makes scanning faster. The transaction-exit
intervals overlap higher-level SQLite and scan operations, and do not identify
a durability or platform bottleneck. SHA-256 component time is tiny for this
fixture's 256 small PNGs; it is not representative of large-media hashing.

The comparison explicitly leaves a full 2,048-file Windows run, repeated runs,
and controlled cold-cache measurements open. It cannot establish a Windows
throughput budget or predict real mounted-share performance. No real SMB/NFS
share or native watcher was involved.

## Validation

```sh
python -m unittest discover -s tests -p 'test_scan*.py' -v
python -m scripts.check_public_artifacts
```

The profiler tests cover nested timing reconciliation, exception accounting,
normal cursor iteration, SQLite settings/results and rollback, patch restoration
after body/setup errors, tracing cleanup, generated recovery/source integrity,
report privacy, invalid fixture parameters, and CLI failure sanitization. The
existing scan cancellation and resilience tests remain the behavior gate.
Simulated path loss stays distinct from real SMB/NFS interruption; native
watching, mounted-share validation, a comparable 2,048-file Windows run,
repeated/cold-cache measurements, and attribution of antivirus/disk-sync costs
remain separate work.
