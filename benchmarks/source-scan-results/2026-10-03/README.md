# Additional accepted hosted source-scan series — 2026-10-03

The [fresh aggregate](hosted-series-run-37091008433-attempt-1.json) contains
one complete Linux, Intel macOS and Windows 2,048-file fictional scan series:
four balanced pairs per OS, 12 pairs and 24 trials from **run 37091008433,
attempt 1 only**. Its strict status is `complete`, with no issues and three
summaries. All 12 separate pair JSON reports are complete and exactly match
their embedded aggregate objects. Every child was reaped, owned storage was
removed, and cancellation, fresh restart, Offline retention, online recovery,
2,049 final assets, source bytes/size/mtime and stable asset identity checks
passed. The original [accepted 2026-10-02 attempt-3 series](../2026-10-02/README.md)
remains an independent cohort with its raw JSON unchanged.

## Identity, provenance and environment

| Field | Fresh accepted value |
| --- | --- |
| Workflow | [run 37091008433, attempt 1](https://github.com/isaaclepes/DefiantMaple/actions/runs/37091008433) |
| PR source head | `73ca65936f184e96087db889c2fbf5a96ea3a465` |
| Measured Actions merge revision | `6b02efffb78d5782eef3f377a20e32dbabe45ad0` |
| Measured Git tree | `5f768cbf13cb9ef035647e0cf1b3681d4a868833` (also the source-head tree) |
| Base parent | `317e9ebd713869e229166065b7fb990613905a6a` |
| Aggregate job and artifact | [job 111115363534](https://github.com/isaaclepes/DefiantMaple/actions/runs/37091008433/job/111115363534); [artifact 11263296198](https://github.com/isaaclepes/DefiantMaple/actions/runs/37091008433/artifacts/11263296198) |
| Archived JSON | 764,834 bytes; SHA-256 `36da9c4706fa3b5e838ba7f57eeaa7c13a91c2b573865d9f33ddd9b5262c9e1e` |
| Uploaded ZIP metadata | 62,975 bytes; reported SHA-256 `490b5f67da8842b897ffe5e246dd7c240dbe5da2b7499b8122d45ef6472052da` |
| Decoded aggregate job log | SHA-256 `da8c309aec972e81e38f7899005b6d9aa798ec7698ceba872ce0d8cbcf47ff5b` |

The archived JSON bytes were reconstructed from the authenticated decoded
aggregate job log and independently matched to that log block; the ZIP was not
materialized for member-byte verification. The ZIP digest identifies uploaded
artifact metadata, not these JSON member bytes. The 12 separately saved pair
reports match the aggregate's pair objects. Pair/trial records state
`code.dirty=false` and `checkout_dirty=false`; the aggregate records
`code.dirty=false` and `checkout_dirty=true`. Artifact downloads preceded
aggregation, but the recorded checkout-dirtiness change has no proved cause.
The six measured-file SHA-256 digests equal those listed for the [original accepted
series](../2026-10-02/README.md#identity-provenance-and-controls), and the
generated catalog schema is version 4. The diagnostic-only change at this PR
head was to the protected tiny-series test's failure message (SHA-256
`78cb1b87428ca25b7babddaf053af4e902ccb58a755b7fe4c7c3c03cf0bb9478`);
the scanner, profiler drivers, fixture, transaction behavior and timeout caps
are unchanged.

Every trial created a fresh catalog and a cyclic corpus of 2,048 fictional
32×32 RGBA PNG files from eight pinned encoded payloads, totaling 220,672
initial bytes, plus a 105-byte newly appearing file. Files were grouped by 256
and page size was 256. The fixed pair order was BI, IB, IB, BI. Both variants
enabled Python allocation tracing; only I installed operation wrappers.

| Recorded runtime | Linux | Intel macOS | Windows |
| --- | --- | --- | --- |
| Platform / machine / OS release | Linux / x86_64 / 6.17.0 | Darwin / x86_64 / 25.6.0 | Windows / AMD64 / 2025 |
| Python / Pillow | CPython 3.13.15 / 12.3.0 | CPython 3.13.15 / 12.3.0 | CPython 3.13.15 / 12.3.0 |
| SQLite / PNG zlib | 3.45.1 / 1.3 | 3.50.4 / 1.3.1.zlib-ng | 3.50.4 / 1.3.1.zlib-ng |
| Hosted image / version | ubuntu24 / 20260927.320.1 | macos26 / 20260824.0517.1 | win25-vs2026 / 20260925.250.1 |
| Recorded logical CPUs | 4 | 4 | 4 |

Within each OS, all four runtime records match. These recorded fields also
match their counterparts in the original accepted cohort, but the two runs
used different jobs and merge revisions; matching labels do not establish
identical physical machines. CPU model, RAM total, filesystem, storage, power
policy and antivirus remain unverified (`null`). Fixture creation and initial
stat checks preceded timing, so OS cache is uncontrolled; this is neither a
cold-cache run nor a defined reference desktop.

## Fresh raw pairs and within-cohort summaries

Each cell below is `baseline seconds / instrumented seconds / I÷B` from raw
nanosecond fields. `Fresh+stable` combines fresh restart and its stable
follow-up. These are paired observations, not an isolated wrapper overhead
measurement.

| OS | Pair | Order | Observe B / I / ratio | Index B / I / ratio | Fresh+stable B / I / ratio |
| --- | --- | --- | --- | --- | --- |
| Linux | 1 | BI | 4.436 / 4.409 / 0.994 | 8.331 / 8.450 / 1.014 | 9.346 / 9.655 / 1.033 |
| Linux | 2 | IB | 5.117 / 5.817 / 1.137 | 9.822 / 11.147 / 1.135 | 11.939 / 12.779 / 1.070 |
| Linux | 3 | IB | 6.054 / 6.795 / 1.122 | 11.735 / 13.441 / 1.145 | 14.061 / 15.214 / 1.082 |
| Linux | 4 | BI | 6.259 / 6.301 / 1.007 | 12.768 / 12.757 / 0.999 | 13.706 / 14.267 / 1.041 |
| macOS | 1 | BI | 12.420 / 12.466 / 1.004 | 25.758 / 27.740 / 1.077 | 26.249 / 29.731 / 1.133 |
| macOS | 2 | IB | 11.966 / 14.634 / 1.223 | 24.523 / 31.883 / 1.300 | 29.838 / 29.056 / 0.974 |
| macOS | 3 | IB | 16.293 / 22.738 / 1.396 | 36.047 / 40.997 / 1.137 | 34.883 / 38.075 / 1.092 |
| macOS | 4 | BI | 12.720 / 13.248 / 1.042 | 26.429 / 28.532 / 1.080 | 27.258 / 29.319 / 1.076 |
| Windows | 1 | BI | 111.907 / 113.446 / 1.014 | 269.883 / 273.368 / 1.013 | 191.102 / 196.212 / 1.027 |
| Windows | 2 | IB | 49.929 / 53.766 / 1.077 | 160.416 / 131.621 / 0.821 | 87.491 / 100.610 / 1.150 |
| Windows | 3 | IB | 47.282 / 46.976 / 0.994 | 125.486 / 111.405 / 0.888 | 127.021 / 85.179 / 0.671 |
| Windows | 4 | BI | 61.201 / 92.247 / 1.507 | 154.214 / 186.729 / 1.211 | 105.998 / 106.282 / 1.003 |

For each OS and interval, median `[min, max]` below uses **n=4 pairs** from
this run only. Ratio statistics summarize four individual paired ratios; they
are not ratios of the displayed medians.

| OS | Interval | Baseline s median [min, max] | Instrumented s median [min, max] | I/B median [min, max] |
| --- | --- | --- | --- | --- |
| Linux | Observe | 5.585 [4.436, 6.259] | 6.059 [4.409, 6.795] | 1.065 [0.994, 1.137] |
| Linux | Index | 10.778 [8.331, 12.768] | 11.952 [8.450, 13.441] | 1.075 [0.999, 1.145] |
| Linux | Fresh+stable | 12.823 [9.346, 14.061] | 13.523 [9.655, 15.214] | 1.056 [1.033, 1.082] |
| macOS | Observe | 12.570 [11.966, 16.293] | 13.941 [12.466, 22.738] | 1.132 [1.004, 1.396] |
| macOS | Index | 26.094 [24.523, 36.047] | 30.208 [27.740, 40.997] | 1.108 [1.077, 1.300] |
| macOS | Fresh+stable | 28.548 [26.249, 34.883] | 29.525 [29.056, 38.075] | 1.084 [0.974, 1.133] |
| Windows | Observe | 55.565 [47.282, 111.907] | 73.006 [46.976, 113.446] | 1.045 [0.994, 1.507] |
| Windows | Index | 157.315 [125.486, 269.883] | 159.175 [111.405, 273.368] | 0.950 [0.821, 1.211] |
| Windows | Fresh+stable | 116.510 [87.491, 191.102] | 103.446 [85.179, 196.212] | 1.015 [0.671, 1.150] |

The fixed order groups each have **n=2 pairs**. Their median `[min, max]`
paired ratios are descriptive; such small groups do not establish an order
effect or tail bound.

| OS | Interval | B-first I/B median [min, max] | I-first I/B median [min, max] |
| --- | --- | --- | --- |
| Linux | Observe | 1.000 [0.994, 1.007] | 1.130 [1.122, 1.137] |
| Linux | Index | 1.007 [0.999, 1.014] | 1.140 [1.135, 1.145] |
| Linux | Fresh+stable | 1.037 [1.033, 1.041] | 1.076 [1.070, 1.082] |
| macOS | Observe | 1.023 [1.004, 1.042] | 1.309 [1.223, 1.396] |
| macOS | Index | 1.078 [1.077, 1.080] | 1.219 [1.137, 1.300] |
| macOS | Fresh+stable | 1.104 [1.076, 1.133] | 1.033 [0.974, 1.092] |
| Windows | Observe | 1.261 [1.014, 1.507] | 1.035 [0.994, 1.077] |
| Windows | Index | 1.112 [1.013, 1.211] | 0.854 [0.821, 0.888] |
| Windows | Fresh+stable | 1.015 [1.003, 1.027] | 0.910 [0.671, 1.150] |

Instrumented operations below show selected indexing costs and the observation
transaction-exit span. Counts were identical across the four instrumented
trials for each listed OS/phase. Inclusive/exclusive seconds are separate
median `[min, max]` statistics, **n=4**. Inclusive `index_file` contains nested
catalog/SQLite/hash work; inclusive catalog teardown contains
`sqlite_transaction_exit`. Do not add overlapping inclusive spans. Exclusive
spans partition each individual phase, but separate medians need not sum to
the median whole phase. The raw JSON retains every phase and operation.

| OS | Phase | Operation | Calls | Inclusive s median [min, max] | Exclusive s median [min, max] |
| --- | --- | --- | --- | --- | --- |
| Linux | Observe | `sqlite_transaction_exit` | 2089 | 1.490 [1.322, 1.729] | 1.490 [1.322, 1.729] |
| Linux | Index | `scan_pass` | 1 | 11.952 [8.450, 13.441] | 2.537 [1.457, 2.697] |
| Linux | Index | `index_file` | 2048 | 5.316 [3.836, 6.058] | 1.507 [0.879, 1.661] |
| Linux | Index | `catalog_connection_setup` | 4137 | 1.978 [1.188, 2.175] | 1.417 [0.806, 1.543] |
| Linux | Index | `sqlite_statement_execute` | 16507 | 1.966 [1.373, 2.220] | 1.966 [1.373, 2.220] |
| Linux | Index | `sqlite_transaction_exit` | 4137 | 3.075 [2.660, 3.567] | 3.075 [2.660, 3.567] |
| macOS | Observe | `sqlite_transaction_exit` | 2089 | 4.205 [3.612, 6.286] | 4.205 [3.612, 6.286] |
| macOS | Index | `scan_pass` | 1 | 30.208 [27.740, 40.997] | 4.831 [4.123, 5.812] |
| macOS | Index | `index_file` | 2048 | 14.748 [13.807, 20.475] | 2.841 [2.680, 3.971] |
| macOS | Index | `catalog_connection_setup` | 4137 | 4.286 [4.042, 6.003] | 3.028 [2.842, 4.161] |
| macOS | Index | `sqlite_statement_execute` | 16507 | 4.408 [4.169, 5.986] | 4.408 [4.169, 5.986] |
| macOS | Index | `sqlite_transaction_exit` | 4137 | 11.411 [10.575, 15.751] | 11.411 [10.575, 15.751] |
| Windows | Observe | `sqlite_transaction_exit` | 2089 | 60.301 [37.456, 99.657] | 60.301 [37.456, 99.657] |
| Windows | Index | `scan_pass` | 1 | 159.175 [111.405, 273.368] | 2.981 [2.938, 3.012] |
| Windows | Index | `index_file` | 2048 | 93.102 [64.017, 159.308] | 2.669 [2.419, 2.923] |
| Windows | Index | `catalog_connection_setup` | 4137 | 3.352 [3.051, 3.394] | 2.118 [1.946, 2.136] |
| Windows | Index | `sqlite_statement_execute` | 16507 | 12.831 [10.144, 18.433] | 12.831 [10.144, 18.433] |
| Windows | Index | `sqlite_transaction_exit` | 4137 | 135.980 [91.704, 244.243] | 135.980 [91.704, 244.243] |

| OS | Variant | Traced Python peak bytes median [min, max], n=4 |
| --- | --- | --- |
| Linux | baseline | 8,833,109 [8,833,109, 8,837,207] |
| Linux | instrumented | 8,877,559 [8,877,521, 8,881,635] |
| macOS | baseline | 8,462,973 [8,462,973, 8,462,973] |
| macOS | instrumented | 8,507,537 [8,507,537, 8,507,545] |
| Windows | baseline | 7,617,173 [7,617,173, 7,617,173] |
| Windows | instrumented | 7,659,379 [7,659,377, 7,659,389] |

Peak values are traced Python allocations during the scan soak after fixture
setup. Both variants incur tracing overhead. They include verification/private
identity sets, exclude fixture creation and known-byte verification after
tracing, and exclude untraced native allocations, process RSS, thumbnails,
GUI and whole-machine memory.

## Separate-cohort reading and next experiment

The comparison below repeats each run's own **n=4** median paired I/B ratio
and observed range. It does not pool trials, form a larger sample, measure a
code improvement or compare identical hardware.

| OS | Interval | Original 36634086725/3 I/B median [min, max] | Fresh 37091008433/1 I/B median [min, max] |
| --- | --- | --- | --- |
| Linux | Observe | 1.093 [1.062, 1.735] | 1.065 [0.994, 1.137] |
| Linux | Index | 1.108 [1.085, 1.851] | 1.075 [0.999, 1.145] |
| Linux | Fresh+stable | 1.055 [1.003, 2.179] | 1.056 [1.033, 1.082] |
| macOS | Observe | 1.062 [1.004, 1.218] | 1.132 [1.004, 1.396] |
| macOS | Index | 1.108 [1.097, 1.192] | 1.108 [1.077, 1.300] |
| macOS | Fresh+stable | 1.025 [0.870, 1.269] | 1.084 [0.974, 1.133] |
| Windows | Observe | 0.967 [0.433, 1.142] | 1.045 [0.994, 1.507] |
| Windows | Index | 0.854 [0.604, 1.298] | 0.950 [0.821, 1.211] |
| Windows | Fresh+stable | 0.965 [0.945, 1.448] | 1.015 [0.671, 1.150] |

In the fresh Windows cohort, the instrumented indexing
`sqlite_transaction_exit` wrapper recorded 4,137 calls in each pair and
91.704–244.243 s exclusive (median 135.980 s). The original accepted cohort
recorded the same call count and 89.022–229.739 s (median 131.346 s). These
are original context-exit API spans; they do not identify which exits
committed, rolled back or did nothing, or isolate fsync, antivirus, filesystem
or storage delay. Windows indexing paired I/B ratios remain variable
(0.821–1.211 fresh; 0.604–1.298 original). Ratios below one are observed
variation; they do not establish a production speedup. Four separate hosted
jobs per OS give no throughput budget, percentile or tail-latency guarantee.

The **one** next experiment remains the bounded, benchmark-only Windows
transaction-exit attribution repeat described in the [original result's
protocol](../2026-10-02/README.md#one-bounded-next-attribution-experiment):
stratify exit timings by pre-exit transaction and exception state on one
identified machine, retain the BI/IB/IB/BI schedule and unwrapped comparison,
and use its predeclared 0.80–1.25 diagnostic perturbation screen. Stop at the
first timeout, cleanup or integrity failure; keep inconclusive results
inconclusive. No connection reuse, batching, lock scope, rollback, recovery,
PRAGMA or durability change is authorized by these reports.

At the published diagnostic-test head, [Qt Windows job 111111161707](https://github.com/isaaclepes/DefiantMaple/actions/runs/37091008435/job/111111161707)
ran 182 Core tests: 181 passed, zero failed or errored, and one known host-
capability skip. All 28 Qt tests passed.
The tiny real-series regression passed there. Its earlier failure on head
`9f8461dc2d0e4b607d01bc226d45c9ba73e6c4a2` did not log the two
incomplete pairs' underlying issue codes; the new pass cannot determine whether
the earlier cause was timeout, runner variation, Qt dependencies or something
else. The diagnostic-only assertion now exposes bounded pair issue data if a
future failure occurs.

Varied and large media, 10k/100k/500k indexing, 100k gallery responsiveness,
concurrent thumbnails/UI, controlled cold cache, a reference desktop and real
SMB/NFS interruption remain separate Phase 1 validation gaps.
