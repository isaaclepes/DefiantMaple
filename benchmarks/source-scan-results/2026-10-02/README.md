# Accepted hosted source-scan series — 2026-10-02

The [accepted aggregate](hosted-series-run-36634086725-attempt-3.json) is the
complete Linux, Intel macOS and Windows four-pair characterization of the
existing 2,048-file fictional scan protocol. It contains all 12 pairs and 24
baseline/instrumented trials from **one** GitHub Actions attempt. The strict
aggregate status is `complete`, with no issues and a summary for each OS. The
12 pair jobs and aggregate job succeeded; the aggregate's embedded pairs match
the 12 separately preserved pair reports. No earlier attempt, local series or
diagnostic was added to these summaries.
An [additional accepted 2026-10-03 cohort](../2026-10-03/README.md) has its own
run, attempt, revision, raw archive and summaries. The two cohorts are not
pooled; this archive remains unchanged.

## Identity, provenance and controls

| Field | Accepted value |
| --- | --- |
| Workflow | [run 36634086725, attempt 3](https://github.com/isaaclepes/DefiantMaple/actions/runs/36634086725) |
| PR source head | `d99ebecc8a222ff03dbc28e778c91c3f4aa0007f` |
| Measured Actions merge revision | `0112155e6f4b53f2447bde074c9c7d6c1da07017` |
| Authenticated measured Git tree | `bf273ba83c64b48947be0a760efd28cd243cc7ca` (also the source-head tree) |
| Base parent | `317e9ebd713869e229166065b7fb990613905a6a` |
| Aggregate job and artifact | [job 110939112402](https://github.com/isaaclepes/DefiantMaple/actions/runs/36634086725/job/110939112402); [artifact 11240287693](https://github.com/isaaclepes/DefiantMaple/actions/runs/36634086725/artifacts/11240287693) |
| Archived JSON | 764,855 bytes; SHA-256 `980360da60a12d6f0437ca0d227e5bb65cc7103b53a01da49cbc87a1725fc9b2` |
| Uploaded ZIP metadata | 62,909 bytes; reported SHA-256 `aa81b6f38f030e33f5c5f0074da00843f868e2a0db2d203d01dbd66b51aa6fad` |
| Decoded aggregate job log | SHA-256 `dc23a21577889420a2ad27f629b7b2c8725cd3e0d98a44513e536e353d15fdaa` |

The JSON archive was reconstructed from the authenticated, decoded aggregate
job log's report block; its byte count and digest identify those exact extracted
JSON bytes. The uploaded ZIP could not be materialized for a member-byte check.
Its artifact ID, size and ZIP digest authenticate artifact metadata but **do
not prove** that this extracted JSON equals the uploaded member. The 12 pair
objects embedded in the aggregate were compared with the independently saved
attempt-3 pair JSON reports. Pair code records state `dirty=false` and
`checkout_dirty=false`; the aggregate states `dirty=false` and
`checkout_dirty=true` after artifact downloads. Measured code identity stayed
constant. The aggregate's six SHA-256 measured-file digests are:

| Measured file | SHA-256 |
| --- | --- |
| `benchmarks/source_scan_profile.py` | `9e819cc3001912d40d6ba42c167fdcbde5f09e8acfcbae63e2d7db2982ac45ce` |
| `benchmarks/source_scan_soak.py` | `203dbb277fb4f2d0602ed008031ef75f42e1e7e8ff209002213ebd3fbe8190e7` |
| `benchmarks/source_scan_profile_series.py` | `4f55246ab68bc668a881290b0d6cce9941264940efa2660ac7d21fbd0d75d635` |
| `defiantmaple/catalog.py` | `18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad` |
| `defiantmaple/sources.py` | `8e1c19d05920b8d537bd54a8ab1a5de5bc823727c5ccfa9b8275f0f5858cf87b` |
| `defiantmaple/media.py` | `e14d21c7186a3c041a8efbd39f4b19179f7c89cd76b75a8f619802a8e256a116` |

The fixed BI, IB, IB, BI order means baseline first in pairs 1/4 and
instrumentation first in 2/3. Each trial created a fresh catalog and its own
2,048 generated, 32×32 RGBA PNG files in groups of 256. The 2,048-file cyclic
corpus from eight canonical encoded payloads totals 220,672 initial bytes; the
earlier newly appearing file adds 105 bytes. Page size is 256. All trials
completed cancellation, fresh restart and stable follow-up, simulated Offline
retention and online recovery,
with 2,049 final assets, source size/mtime/known bytes intact and stable asset
identity retained. Children were reaped and owned storage removed in every pair.
The generated catalog schema is version 4. These are protocol integrity checks,
not timings for real network shares.

| Runtime field | Linux | Intel macOS | Windows |
| --- | --- | --- | --- |
| Platform / machine / OS release | Linux / x86_64 / 6.17.0 | Darwin / x86_64 / 25.6.0 | Windows / AMD64 / 2025 |
| Python / Pillow | CPython 3.13.15 / 12.3.0 | CPython 3.13.15 / 12.3.0 | CPython 3.13.15 / 12.3.0 |
| SQLite / PNG zlib | 3.45.1 / 1.3 | 3.50.4 / 1.3.1.zlib-ng | 3.50.4 / 1.3.1.zlib-ng |
| Hosted image / version | ubuntu24 / 20260927.320.1 | macos26 / 20260824.0517.1 | win25-vs2026 / 20260925.250.1 |
| Recorded logical CPUs | 4 | 4 | 4 |

Within each OS, all four runtime records match exactly. CPU model, total RAM,
filesystem, storage, power policy and antivirus are unverified (`null`) in the
report. Each ordinal ran in a separate GitHub-hosted job, so matching runtime
fields do not prove identical physical hardware. The fixture was created and
stat checked before timing; OS cache remained uncontrolled. These figures do
not represent a reference desktop or a cold-cache budget.

## Raw paired intervals

All values are seconds from the archive's nanosecond fields. Each cell is
`baseline / instrumented / I÷B`; `Fresh+stable` is the fresh restart **plus**
stable follow-up interval. Ratios compare trials within a pair, not two
instrumented operations. They include process, cache and runner variation and
must not be interpreted as isolated wrapper cost or production speedup.

| OS | Pair | Order | Observe B / I / ratio | Index B / I / ratio | Fresh+stable B / I / ratio |
| --- | --- | --- | --- | --- | --- |
| Linux | 1 | BI | 6.276 / 6.725 / 1.071 | 12.031 / 13.051 / 1.085 | 14.003 / 14.042 / 1.003 |
| Linux | 2 | IB | 5.593 / 6.231 / 1.114 | 11.078 / 12.391 / 1.119 | 13.454 / 14.154 / 1.052 |
| Linux | 3 | IB | 10.063 / 17.464 / 1.735 | 27.319 / 50.581 / 1.851 | 19.763 / 43.059 / 2.179 |
| Linux | 4 | BI | 6.022 / 6.393 / 1.062 | 11.626 / 12.769 / 1.098 | 13.880 / 14.693 / 1.059 |
| macOS | 1 | BI | 10.661 / 10.716 / 1.005 | 22.484 / 24.938 / 1.109 | 22.333 / 23.801 / 1.066 |
| macOS | 2 | IB | 12.545 / 15.285 / 1.218 | 25.996 / 28.526 / 1.097 | 34.113 / 29.674 / 0.870 |
| macOS | 3 | IB | 9.969 / 11.161 / 1.120 | 21.572 / 23.866 / 1.106 | 21.981 / 27.898 / 1.269 |
| macOS | 4 | BI | 13.291 / 13.348 / 1.004 | 27.834 / 33.188 / 1.192 | 28.465 / 28.028 / 0.985 |
| Windows | 1 | BI | 180.281 / 78.080 / 0.433 | 199.256 / 176.374 / 0.885 | 145.532 / 139.760 / 0.960 |
| Windows | 2 | IB | 76.342 / 87.146 / 1.142 | 196.392 / 255.003 / 1.298 | 147.747 / 143.347 / 0.970 |
| Windows | 3 | IB | 52.778 / 55.205 / 1.046 | 205.515 / 124.041 / 0.604 | 100.346 / 94.834 / 0.945 |
| Windows | 4 | BI | 50.839 / 45.163 / 0.888 | 130.909 / 107.751 / 0.823 | 85.650 / 124.010 / 1.448 |

For each OS and interval, the following median `[min, max]` uses **n=4 pairs**.
The ratio column summarizes four individual paired ratios; it is not a ratio
of the two displayed medians.

| OS | Interval | Baseline s median [min, max] | Instrumented s median [min, max] | I/B median [min, max] |
| --- | --- | --- | --- | --- |
| Linux | Observe | 6.149 [5.593, 10.063] | 6.559 [6.231, 17.464] | 1.093 [1.062, 1.735] |
| Linux | Index | 11.828 [11.078, 27.319] | 12.910 [12.391, 50.581] | 1.108 [1.085, 1.851] |
| Linux | Fresh+stable | 13.942 [13.454, 19.763] | 14.424 [14.042, 43.059] | 1.055 [1.003, 2.179] |
| macOS | Observe | 11.603 [9.969, 13.291] | 12.255 [10.716, 15.285] | 1.062 [1.004, 1.218] |
| macOS | Index | 24.240 [21.572, 27.834] | 26.732 [23.866, 33.188] | 1.108 [1.097, 1.192] |
| macOS | Fresh+stable | 25.399 [21.981, 34.113] | 27.963 [23.801, 29.674] | 1.025 [0.870, 1.269] |
| Windows | Observe | 64.560 [50.839, 180.281] | 66.643 [45.163, 87.146] | 0.967 [0.433, 1.142] |
| Windows | Index | 197.824 [130.909, 205.515] | 150.208 [107.751, 255.003] | 0.854 [0.604, 1.298] |
| Windows | Fresh+stable | 122.939 [85.650, 147.747] | 131.885 [94.834, 143.347] | 0.965 [0.945, 1.448] |

Order strata each contain **n=2 pairs**. Their median `[min, max]` paired
ratios expose order sensitivity, but two observations per stratum cannot
separate order from runner variation.

| OS | Interval | B-first I/B median [min, max] | I-first I/B median [min, max] |
| --- | --- | --- | --- |
| Linux | Observe | 1.066 [1.062, 1.071] | 1.425 [1.114, 1.735] |
| Linux | Index | 1.092 [1.085, 1.098] | 1.485 [1.119, 1.851] |
| Linux | Fresh+stable | 1.031 [1.003, 1.059] | 1.615 [1.052, 2.179] |
| macOS | Observe | 1.005 [1.004, 1.005] | 1.169 [1.120, 1.218] |
| macOS | Index | 1.151 [1.109, 1.192] | 1.102 [1.097, 1.106] |
| macOS | Fresh+stable | 1.025 [0.985, 1.066] | 1.070 [0.870, 1.269] |
| Windows | Observe | 0.661 [0.433, 0.888] | 1.094 [1.046, 1.142] |
| Windows | Index | 0.854 [0.823, 0.885] | 0.951 [0.604, 1.298] |
| Windows | Fresh+stable | 1.204 [0.960, 1.448] | 0.958 [0.945, 0.970] |

Linux pair 3 is much slower than its other three pairs (indexing ratio 1.851;
fresh interval ratio 2.179). Windows indexing ratios range from 0.604 to
1.298 and its baseline indexing intervals range from 130.909 to 205.515 s.
Ratios below one are observed variation, not evidence that wrappers improve
production speed. No percentile, tail-latency, throughput or compliance target
can be inferred from four hosted jobs per OS.

## Instrumented operation spans and traced memory

The next table gives the selected operation totals most useful for attribution.
Each call count is the median of four instrumented trials; all listed counts
are identical across the four trials for that OS/phase. Inclusive and exclusive
seconds are each median `[min, max]` over **n=4**. `scan_pass` inclusive is the
whole phase. `index_file` inclusive contains nested catalog and hash calls;
`catalog_connection_setup` inclusive contains SQLite connection work. Thus
inclusive entries overlap. Exclusive spans, including `scan_pass` exclusive,
partition each *individual* phase; separate medians need not add to the
median phase duration. Full calls and both span kinds for all seven phases
and all operations remain in the raw JSON.

| OS | Phase | Operation | Calls | Inclusive s median [min, max] | Exclusive s median [min, max] |
| --- | --- | --- | --- | --- | --- |
| Linux | Observe | `scan_pass` | 1 | 6.559 [6.231, 17.464] | 1.970 [1.592, 2.165] |
| Linux | Observe | `enumeration` | 1 | 0.560 [0.484, 0.628] | 0.560 [0.484, 0.628] |
| Linux | Observe | `catalog_connection_setup` | 2089 | 0.990 [0.841, 1.064] | 0.715 [0.598, 0.764] |
| Linux | Observe | `sqlite_statement_execute` | 6267 | 0.902 [0.765, 0.958] | 0.902 [0.765, 0.958] |
| Linux | Observe | `sqlite_transaction_exit` | 2089 | 1.891 [1.308, 13.602] | 1.891 [1.308, 13.602] |
| Linux | Index | `scan_pass` | 1 | 12.910 [12.391, 50.581] | 2.415 [1.961, 2.668] |
| Linux | Index | `enumeration` | 1 | 0.564 [0.489, 0.631] | 0.564 [0.489, 0.631] |
| Linux | Index | `catalog_connection_setup` | 4137 | 1.968 [1.680, 2.139] | 1.403 [1.183, 1.524] |
| Linux | Index | `sqlite_statement_execute` | 16507 | 2.037 [1.775, 2.211] | 2.037 [1.775, 2.211] |
| Linux | Index | `sqlite_transaction_exit` | 4137 | 3.907 [2.812, 43.000] | 3.907 [2.812, 43.000] |
| Linux | Index | `index_file` | 2048 | 5.862 [5.536, 28.124] | 1.490 [1.260, 1.613] |
| macOS | Observe | `scan_pass` | 1 | 12.255 [10.716, 15.285] | 3.417 [3.086, 4.272] |
| macOS | Observe | `enumeration` | 1 | 1.229 [1.089, 2.186] | 1.229 [1.089, 2.186] |
| macOS | Observe | `catalog_connection_setup` | 2089 | 1.937 [1.719, 2.147] | 1.379 [1.236, 1.533] |
| macOS | Observe | `sqlite_statement_execute` | 6267 | 1.714 [1.486, 1.963] | 1.714 [1.486, 1.963] |
| macOS | Observe | `sqlite_transaction_exit` | 2089 | 3.569 [2.992, 4.270] | 3.569 [2.992, 4.270] |
| macOS | Index | `scan_pass` | 1 | 26.732 [23.866, 33.188] | 4.114 [3.666, 4.598] |
| macOS | Index | `enumeration` | 1 | 1.156 [1.062, 1.477] | 1.156 [1.062, 1.477] |
| macOS | Index | `catalog_connection_setup` | 4137 | 3.789 [3.497, 4.792] | 2.691 [2.485, 3.344] |
| macOS | Index | `sqlite_statement_execute` | 16507 | 3.832 [3.546, 4.923] | 3.832 [3.546, 4.923] |
| macOS | Index | `sqlite_transaction_exit` | 4137 | 10.272 [8.950, 13.412] | 10.272 [8.950, 13.412] |
| macOS | Index | `index_file` | 2048 | 13.138 [11.689, 16.706] | 2.516 [2.323, 3.153] |
| Windows | Observe | `scan_pass` | 1 | 66.643 [45.163, 87.146] | 1.969 [1.437, 2.547] |
| Windows | Observe | `enumeration` | 1 | 0.363 [0.256, 0.507] | 0.363 [0.256, 0.507] |
| Windows | Observe | `catalog_connection_setup` | 2089 | 1.314 [0.999, 1.623] | 0.836 [0.628, 1.045] |
| Windows | Observe | `sqlite_statement_execute` | 6267 | 5.470 [4.255, 6.295] | 5.470 [4.255, 6.295] |
| Windows | Observe | `sqlite_transaction_exit` | 2089 | 57.226 [36.292, 77.608] | 57.226 [36.292, 77.608] |
| Windows | Index | `scan_pass` | 1 | 150.208 [107.751, 255.003] | 2.357 [1.653, 2.927] |
| Windows | Index | `enumeration` | 1 | 0.366 [0.244, 0.477] | 0.366 [0.244, 0.477] |
| Windows | Index | `catalog_connection_setup` | 4137 | 2.643 [1.738, 3.145] | 1.637 [1.077, 1.986] |
| Windows | Index | `sqlite_statement_execute` | 16507 | 11.007 [9.359, 17.666] | 11.007 [9.359, 17.666] |
| Windows | Index | `sqlite_transaction_exit` | 4137 | 131.346 [89.022, 229.739] | 131.346 [89.022, 229.739] |
| Windows | Index | `index_file` | 2048 | 87.413 [62.001, 152.276] | 2.369 [1.563, 2.777] |

The repeated observation and indexing calls show where measured time accrued,
without identifying SQLite internals or storage causes. On Windows,
`sqlite_transaction_exit` indexing exclusive totals span 89.022–229.739 s
across four trials with 4,137 exits each; its median is 131.346 s. This wrapper
times the original context exit. The report does not identify whether each
exit committed, rolled back or did nothing, and does not isolate fsync,
antivirus, filesystem or device delay. `catalog_connection_teardown` includes
that exit, so adding both would double count. Similarly, the Linux pair-3
indexing exit total reached 43.000 s while its median was 3.907 s. This
variability is part of the evidence, not a reason to drop a sample.

| OS | Variant | Traced Python peak bytes median [min, max], n=4 |
| --- | --- | --- |
| Linux | baseline | 8,835,158 [8,833,109, 8,837,207] |
| Linux | instrumented | 8,879,600 [8,877,557, 8,881,655] |
| macOS | baseline | 8,462,973 [8,462,973, 8,462,973] |
| macOS | instrumented | 8,507,525 [8,507,501, 8,507,537] |
| Windows | baseline | 7,617,173 [7,617,118, 7,617,173] |
| Windows | instrumented | 7,659,375 [7,659,357, 7,659,377] |

Peak bytes above are `tracemalloc` Python allocations during the scan soak
after fixture setup. Both variants paid tracing overhead. The scope includes
verification queries/private identity sets, excludes fixture creation and
known-byte checks after tracing, and excludes untraced native allocations,
process RSS, thumbnails, GUI and whole-machine memory.

## One bounded next attribution experiment

The next experiment should instrument **transaction-context exits only** on a
single identified Windows machine while repeating the same 2,048/256 fictional
protocol four times with the BI/IB/IB/BI schedule. A benchmark-only wrapper
would record per-phase, bounded aggregate exit counts and elapsed distributions
stratified by `in_transaction` immediately before exit and whether an exception
was passed to the context exit. It must delegate to the original exit, retain
the existing scanner/catalog transaction and PRAGMA behavior, publish no SQL,
paths or rows, and leave production code unchanged. A matching unwrapped child
per pair checks total-time perturbation. Give each child the existing 1,440 s
Windows cap, each pair 3,000 s, and stop after four pairs or at the first
timeout, cleanup or integrity failure. Never merge these diagnostic samples
into the accepted hosted cohort.

Python documents [`in_transaction` as a read-only state property](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.in_transaction),
and its [connection context manager guide](https://docs.python.org/3.13/library/sqlite3.html#how-to-use-the-connection-context-manager)
explains that exit may commit, roll back or do nothing without closing the
connection; this supports the proposed grouping only, not a claim about which
action occurred in the accepted trials.

Success for attribution is four complete pairs with unchanged
cancellation/restart/Offline/recovery, source integrity, asset identities,
rollback and cleanup checks, plus a consistent exit stratum contributing over
half of indexing elapsed time in every instrumented trial. Before running,
set a diagnostic perturbation screen: in each pair, the instrumented-to-
unwrapped **indexing** elapsed ratio must stay within 0.80–1.25. If any of
the four ratios falls outside that range, or the dominant exit stratum is
inconsistent, mark the diagnosis inconclusive. This range is an operational
screen for this probe, not a significance test, causal proof or performance
budget. Even a consistent result identifies an API span to investigate; it
does not authorize connection reuse, batching, lock scope changes, relaxed
durability or production optimization. Any later
implementation proposal must separately preserve transaction boundaries,
rollback on failures, concurrent locking, Offline recovery and on-disk
durability before change and test.

The present fixture says nothing about varied or large media, 10k/100k/500k
indexing, 100k gallery or concurrent thumbnail/UI responsiveness, a defined
reference desktop, controlled cold cache, or real SMB/NFS interruption. Those
remain distinct acceptance experiments.

## Retained historical and rejected evidence

The following immutable JSON archives keep each earlier identity and its
diagnostic value visible. Byte counts and SHA-256 refer to each archived JSON,
not an uploaded ZIP member. The [2026-09-29 local series](../2026-09-29/linux-local-series.json)
used a dirty, earlier fixture/driver and is not pooled with the canonical
hosted series. Earlier hosted attempts had missing or incomparable coverage.
The `8608256d` minimal reports lack enough identity/runtime fields to become
pair samples; the `68a8516f` Windows sidecars have different LF/CRLF measured
source hashes. Each report remains at its original path with no repair or
normalization. The later d99 attempt 1 was rejected for mixed Windows image
versions; attempt 2 lacked the macOS pair-3 uploaded artifact despite its
complete log-extracted diagnostic. The only accepted performance cohort here
is attempt 3 above.

| Archive | Run/attempt | Measured revision | JSON bytes | JSON SHA-256 | Reason retained |
| --- | --- | --- | --- | --- | --- |
| [windows-pair-1-BI-job-109312549748-identity-mismatch.json](../2026-09-29/diagnostics/head-68a8516f-run-36539898020-attempt-1/windows-pair-1-BI-job-109312549748-identity-mismatch.json) | 36539898020/1 | `c4122f309473ae3abd71b58222eee229c21710c7` | 44,991 | `27a9dd2f9e07136aba117b706b9ff3d1ec16087ac3b6eaf18acf775bd3ca343d` | Windows LF/CRLF identity diagnostic |
| [windows-pair-2-IB-job-109312549695-identity-mismatch.json](../2026-09-29/diagnostics/head-68a8516f-run-36539898020-attempt-1/windows-pair-2-IB-job-109312549695-identity-mismatch.json) | 36539898020/1 | `c4122f309473ae3abd71b58222eee229c21710c7` | 44,986 | `ce44431322ba79688ff578a3d5cce04f8ecc66ceb921f9f3ce31326507f762ba` | Windows LF/CRLF identity diagnostic |
| [windows-pair-3-IB-job-109312549713-identity-mismatch.json](../2026-09-29/diagnostics/head-68a8516f-run-36539898020-attempt-1/windows-pair-3-IB-job-109312549713-identity-mismatch.json) | 36539898020/1 | `c4122f309473ae3abd71b58222eee229c21710c7` | 45,021 | `31e9d56703b941aecff29957a0139eb79eb844dec65b252dc26106f11d369e28` | Windows LF/CRLF identity diagnostic |
| [windows-pair-4-BI-job-109312549712-identity-mismatch.json](../2026-09-29/diagnostics/head-68a8516f-run-36539898020-attempt-1/windows-pair-4-BI-job-109312549712-identity-mismatch.json) | 36539898020/1 | `c4122f309473ae3abd71b58222eee229c21710c7` | 44,998 | `36e6526382147baef1526024ae14eb6cdd2fac153c2dad22da53687826fe7ec4` | Windows LF/CRLF identity diagnostic |
| [macos-pair-1-job-109304814820-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/macos-pair-1-job-109304814820-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [macos-pair-2-job-109304814851-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/macos-pair-2-job-109304814851-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [macos-pair-3-job-109304814941-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/macos-pair-3-job-109304814941-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [macos-pair-4-job-109304814933-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/macos-pair-4-job-109304814933-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [windows-pair-1-job-109304814962-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/windows-pair-1-job-109304814962-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [windows-pair-2-job-109304814792-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/windows-pair-2-job-109304814792-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [windows-pair-3-job-109304814840-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/windows-pair-3-job-109304814840-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [windows-pair-4-job-109304814963-minimal-incomplete.json](../2026-09-29/diagnostics/head-8608256d-run-36537499696-attempt-1/windows-pair-4-job-109304814963-minimal-incomplete.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 198 | `8b5bc68345541c93da9303a9ee6769c38380c061671f151d95218bf19acf87a7` | minimal invalid diagnostic |
| [aggregate-head-425a5970-run-36548534031-attempt-1.json](../2026-09-29/incomplete/aggregate-head-425a5970-run-36548534031-attempt-1.json) | 36548534031/1 | `fa40b68ac1923afa8e410043091c61935f65e8d3` | 540,662 | `fcbd8ea50ea9e08bfe0165357400190c05b6482f5e68320e38daaefdb45f81e4` | incomplete; Windows timeout/Mac runtime mismatch |
| [aggregate-head-68a8516f-run-36539898020-attempt-1.json](../2026-09-29/incomplete/aggregate-head-68a8516f-run-36539898020-attempt-1.json) | 36539898020/1 | `c4122f309473ae3abd71b58222eee229c21710c7` | 392,913 | `10132df3e644e5ebe399a78307eb4f1abf7770df159a04ac0dd415174aca869b` | incomplete; Windows source-byte mismatch |
| [aggregate-head-8608256d-run-36537499696-attempt-1.json](../2026-09-29/incomplete/aggregate-head-8608256d-run-36537499696-attempt-1.json) | 36537499696/1 | `873cb5cc4ad5d7b44f4509b2b650b30d05fe134b` | 197,374 | `85d04465a15c0f800d41f6fa60fd071a63f24700e5065e39a403ac37e2f1ec8c` | incomplete; invalid/minimal pairs |
| [aggregate-head-d99ebecc-run-36634086725-attempt-1.json](../2026-09-29/incomplete/aggregate-head-d99ebecc-run-36634086725-attempt-1.json) | 36634086725/1 | `0112155e6f4b53f2447bde074c9c7d6c1da07017` | 587,645 | `701584cfa3f92c64b9243b3a5663f49d62f1a8a535fe680238e65842068760d1` | incomplete; mixed Windows image versions |
| [linux-local-series.json](../2026-09-29/linux-local-series.json) | local/1 | `317e9ebd713869e229166065b7fb990613905a6a` | 254,951 | `edd64c49fd4c69d359c20f67aada965f4390b89c4427af846a8f6d14343c12d6` | local; earlier fixture/dirty code |
| [aggregate-head-d99ebecc-run-36634086725-attempt-2.json](incomplete/aggregate-head-d99ebecc-run-36634086725-attempt-2.json) | 36634086725/2 | `0112155e6f4b53f2447bde074c9c7d6c1da07017` | 538,594 | `d83e771c5cdc07d542c1393b122f206a9823154a7c80c66b75fdee7e69af4a13` | incomplete; missing macOS pair-3 artifact |
| [macos-pair-3-run-36634086725-attempt-2.json](incomplete/macos-pair-3-run-36634086725-attempt-2.json) | 36634086725/2 | `0112155e6f4b53f2447bde074c9c7d6c1da07017` | 44,052 | `db53d7b99cb9d6f3636c83eeefde38117873485e28be6fc202df458ed415c65b` | complete logged pair; upload failed; diagnostic only |

The source extraction ledger and artifact metadata used during review are
preserved outside the published repository under
`work/scan-characterization-raw/archive-manifest.json` in the analysis
workspace. Historical decoded-log JSON digests authenticate reconstructed
JSON; their ZIP metadata does not prove member-byte identity. A missing pair
artifact cannot be supplied by a decoded log for strict aggregate acceptance.
