# Windows transaction-exit diagnostic: supported API span

The [canonical raw series](windows-series-run-37148420816-attempt-1.json)
contains four complete BI/IB/IB/BI pairs and eight fresh process/fixture
trials from one hosted Windows job. All four predeclared indexing I/B ratios
are within **0.80–1.25**, and the same `transaction_normal` stratum accounts
for **more than 50% of the full instrumented indexing interval** in every I
trial. The closed report's verdict is `attributed`: it identifies the delegated
SQLite connection context-exit **API span** as the repeated large measured
span. It does not isolate commit, filesystem synchronization, locking,
Python overhead or any other cause, nor authorize a production optimization.

## Identity and evidence boundary

The source PR head is `1d4dc92c5a9aa4bd043daaf191581ef19937e611`;
the measured PR merge is `92a9fce9bcd4d53f8be630010e7986832c35324e`,
with ordered parents `80887a2196fea3c3c6568fc11e7d1b7b78054f91` and
that PR head, and tree `bf513104f50d87fe662f3f53e5085c8b9263ab2b`.
[GitHub run 37148420816, attempt 1](https://github.com/isaaclepes/DefiantMaple/actions/runs/37148420816)
used logical job `windows-series` and
[job 111277186186](https://github.com/isaaclepes/DefiantMaple/actions/runs/37148420816/job/111277186186).
The four-pair step ran 19:36:47–20:44:07 UTC on 2026-10-03. Every pair and
trial binds that run/attempt/job, source and merge, public runtime, canonical
fixture, code digests and one parent-created session token.

The retained LF JSON has 103,320 bytes and SHA-256
`38653a2d770db33d4ebdc41617a53bc66beb02eb35a323988e439582678ba94d`.
The authenticated job log has 213,299 bytes and SHA-256
`2be0f87daf033d41e3e56b9c3728629476f605c04cfcc479e599247a4598de3a`.
Artifact `11284681263` is a 5,758-byte ZIP with SHA-256
`31d38f8b026b26ccb7c7e42e0e44d9193cc3af55c74378005d4c983eb330be37`;
its 106,366-byte Windows CRLF JSON member has SHA-256
`1db84da5de41240ad6d572be8a7a8b17ce30e5cdae36ff8d65a5a6d30c2732a3`.
Converting only CRLF to LF reproduces the retained raw JSON byte-for-byte;
the log's JSON agrees. The six frozen measured-code hashes match Git blobs
exactly. The two new probe-module hashes match the exact LF-to-CRLF checkout
transformation authenticated by the narrow publication gate. No raw digest
was rewritten.

The fixed fictional fixture uses 2,048 initial 32×32 RGBA PNG files, eight
encoded contents, 220,672 initial bytes, page size 256 and catalog schema
version 4. All eight trials pass the original cancellation, fresh restart,
Offline/reconnection, stable identity and source-byte checks. Every pair
reports reaped workers and removed owned storage, with no retained storage or
issue. The 1,440-second child and 3,000-second pair caps held. The source
head's 46 hosted checks across six runs were green; actual Windows Core
reported 194 passes and one documented capability skip, and Qt reported 28
passes. Those regression checks are separate from the timing screen.

## Predeclared screen and variability

Elapsed values are seconds. `transaction_normal` means the read-only
pre-exit `in_transaction` state was true and no exception was passed to the
original SQLite `Connection.__exit__`. Its percentage uses the **full** I
indexing elapsed interval as denominator.

| Pair | Order | B indexing | I indexing | I/B | `transaction_normal` exits | Exit elapsed | Share of I indexing | Pair wall |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | BI | 221.213 | 197.741 | 0.894 | 4,112 | 179.418 | 90.734% | 1,096.472 |
| 2 | IB | 184.767 | 192.446 | 1.042 | 4,112 | 175.744 | 91.322% | 996.711 |
| 3 | IB | 178.150 | 191.386 | 1.074 | 4,112 | 173.063 | 90.426% | 971.584 |
| 4 | BI | 184.559 | 187.652 | 1.017 | 4,112 | 169.799 | 90.486% | 972.197 |

Each I indexing phase also records 25 `no_transaction_normal` exits totaling
0.000041–0.000064 seconds. Both exception strata contain zero indexing exits
in these successful trials; separate tests, rather than this workload, cover
commit failure and rollback delegation. For `transaction_normal`, each pair's
4,112 exits fall only in [10 ms, 100 ms) and [100 ms, 1 s): respectively
4,023/89, 4,049/63, 4,068/44 and 4,059/53. Observed per-exit minima range
22.092–22.714 ms and maxima 0.271–0.487 s. The eight fixed, disjoint
histogram bins do not establish exact percentiles.

B indexing spans 178.150–221.213 s (median 184.663 s); I spans
187.652–197.741 s (median 191.916 s). Paired ratios span 0.894–1.074
(median 1.029). The two BI ratios are 0.894 and 1.017, and the two IB ratios
are 1.042 and 1.074. Four observations and uncontrolled runner/cache state
do not establish an order effect. Observation spans 77.047–79.201 s in B and
77.622–85.088 s in I. Fresh resume spans 126.050–150.737 s in B and
129.997–137.407 s in I. Pair wall durations span 971.584–1,096.472 s,
below the cap; the parent stopped after the fourth pair.

All four pairs complete; every ratio lies inside 0.80–1.25; and
`transaction_normal` contributes 90.426–91.322% of full I indexing in all
four pairs. The predeclared diagnostic screen therefore passes. This is a
span attribution only. It is not a statistical causal test, indexing budget,
durability guarantee or basis for changing transaction boundaries, connection
reuse, PRAGMAs, batching or lock scope.

## Environment, memory and stopping rule

The report identifies a GitHub-hosted Windows `AMD64` runner, Windows release
`2025`, CPython 3.13.15, SQLite 3.50.4, Pillow 12.3.0, PNG zlib-ng 1.3.1,
four logical CPUs, and image `win25-vs2026` version `20260925.250.1`.
CPU model, total RAM, filesystem, storage, power policy and antivirus are
`null`: they were unavailable, not zero. The hosted job is one runner
session, not a named physical reference desktop. The fixture does not
control cold/warm OS cache, cover varied or large media, measure concurrent
gallery/thumbnail responsiveness, or validate real SMB/NFS loss.

The `tracemalloc` peaks are 7,594,045 bytes in every B trial and
7,604,902–7,604,957 bytes in I. Tracing begins after fixture creation and
includes Python allocations during the scan protocol, including verification
and retained asset-identity/UUID sets. It excludes untraced native
allocations, process-tree RSS, whole-machine memory and known-byte source
checks performed after tracing stops. These values are not full-memory
budgets. The proposed reference profile and interaction numbers in
[SDD v0.2 §§19–21](../../sdd-v0.2.md#19-performance-and-resource-governance)
remain unadopted release-design targets; this hosted diagnostic cannot claim
NFR compliance.

The earlier [first complete cohort](../../transaction-exit-benchmark-history/2026-10-03/first-complete/README.md)
remains **inconclusive** because its pair 1 ratio fell below 0.80. Its raw
bytes, source head and run identity are preserved; no samples from it or the
two accepted source-scan characterization cohorts are pooled here. This
fresh cohort was required after a protected publication-gate repair, not
chosen to rescue the earlier verdict. Under [SDD v0.2 §19.4](../../sdd-v0.2.md#194-benchmark-governance),
the diagnostic ends with this supported API span. No further microbenchmark
or production change follows automatically.

The smallest decision-led next experiment is **conditional**. The product
question is: *does explicit source indexing make visible gallery work miss an
adopted Phase 1a responsiveness budget, such that scan scheduling deserves
priority over other daily-gallery work?* If owners first adopt a named Windows
reference desktop, representative authorized 2,048-image manifest, cache
preparation, visible-preview/indexing budgets, and comparison rules, run two
balanced idle/indexing pairs there: idle then explicit scan, followed by
explicit scan then idle. Keep the same 100k-record catalog, viewport actions,
thumbnail I/O, and cache preparation in all four runs; the scanner remains
unwrapped. Predeclare the response and frame thresholds, the minimum
within-pair difference that would change the scheduling decision, and how
invalid runs are handled before starting. Cap each run, including cleanup, at
15 minutes and the entire sequence at one hour; stop on the first integrity,
cleanup or timeout failure and retain all attempts. Record indexing throughput,
user-visible response/frame timing, and full process-tree RSS while the
viewport is used. This bounded matched comparison tests whether explicit
indexing plausibly affects the adopted product budget; it does not rerun the
first cohort's failed perturbation screen or prove the exit mechanism. If no
budget is adopted, if the stop condition fires, or if the two paired
comparisons do not meet the predeclared decision rule, report that limit and
do not optimize. The default next work is the Phase 1a
backlog in the [SDD v0.2 review](../../sdd-v0.2-review.md). Even a missed
budget would require a separate durability-preserving design and correctness
tests before a transaction change.
