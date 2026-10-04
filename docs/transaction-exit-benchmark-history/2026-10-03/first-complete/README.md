# First complete Windows transaction-exit diagnostic: inconclusive attribution

This first complete cohort is retained separately from the future canonical
result. The [unchanged raw closed series](windows-series-run-37140259168-attempt-1.json) contains
four complete matched pairs and eight fresh child trials from one hosted
Windows job. Every recorded soak integrity and cleanup check passed. The
predeclared attribution verdict is **inconclusive**: pair 1's instrumented to
baseline (I/B) indexing ratio is **0.769**, below the 0.80 lower screen.
The same `transaction_normal` exit stratum occupies more than 90% of full
instrumented indexing elapsed time in every pair, but that consistency does
not override the ratio breach or establish a cause.

## Raw identity and scope

The source PR head is `cf483d06d15828d18f14501687a96a570e8622de`;
the measured PR merge is `c1193a38165483d6f738ea31d701541d411ad857`.
The merge has ordered parents `80887a2196fea3c3c6568fc11e7d1b7b78054f91`
and that PR head, with tree
`54f4c16baa926f3d899ad740b6f4e04d14227fe7`.
[GitHub run 37140259168, attempt 1](https://github.com/isaaclepes/DefiantMaple/actions/runs/37140259168)
used logical job `windows-series` and
[job 111253079928](https://github.com/isaaclepes/DefiantMaple/actions/runs/37140259168/job/111253079928).
The job ran from 17:23:59 to 19:16:04 UTC on 2026-10-03.
All four pairs bind the same run, attempt, job, merge, PR head, public runtime,
fixture descriptor and ephemeral session token. The local raw copy is 103,399
bytes with SHA-256
`f9420182d43737f6a47eddbddeffd61bc1553523e0a28d4aca9571b979dbceaa`.
The decoded job log has 213,379 bytes and SHA-256
`7203e843bc3f091046d28e5ec911c486cbe70a21c252a6951b59eded4335cf44`.
Independently checked artifact `11282622095` is a 5,861-byte ZIP with
SHA-256 `fa1757dd0de5d06ebb41c9b5793d041b965948b3a9f6ecbd5ad3ed1fa88e1a5e`.
Its 106,445-byte Windows CRLF JSON member has SHA-256
`b4e48cd784480ebffca2d87469e258016c76e46801657d6189d974c984cea0c9`.
Converting only CRLF to LF yields the retained 103,399-byte report exactly;
the independently authenticated log's JSON also matches those LF bytes.

The canonical fictional recipe has 2,048 initial 32×32 RGBA PNG files,
eight encoded contents, 220,672 initial bytes, page size 256 and catalog
schema version 4. The BI/IB/IB/BI schedule and new process/fixture for each
trial are recorded in the report. The original cancellation, fresh restart,
Offline/online recovery, stable asset identities, source bytes and owned
storage cleanup checks passed in all eight trials. The accepted 2026-10-02
and 2026-10-03 source-scan cohorts and the earlier zero-sample failed
transaction-exit attempt remain separate from this diagnostic cohort.

## Predeclared screen and raw variability

All elapsed values below are seconds. `transaction_normal` means the
read-only pre-exit `in_transaction` state was true and no exception was passed
to the delegated SQLite context exit. Its share uses the **full** I indexing
interval as denominator.

| Pair | Order | B indexing | I indexing | I/B | `transaction_normal` exits | Exit elapsed | Share of I indexing | Pair wall |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | BI | 409.244 | 314.824 | 0.769 | 4,112 | 288.333 | 91.585% | 1,846.568 |
| 2 | IB | 256.846 | 274.484 | 1.069 | 4,112 | 249.670 | 90.960% | 1,521.183 |
| 3 | IB | 365.997 | 305.737 | 0.835 | 4,112 | 280.386 | 91.708% | 1,712.128 |
| 4 | BI | 344.489 | 323.068 | 0.938 | 4,112 | 293.584 | 90.874% | 1,641.850 |

Each I indexing phase also records 25 `no_transaction_normal` exits totaling
only 0.000069–0.000080 seconds. Both exception strata have zero indexing
exits in these successful trials. This does not replace the separate
commit/rollback and exceptional-delegation tests. In every I indexing phase,
the `transaction_normal` histogram has 4,112 exits: 3,213–3,502 in
[10 ms, 100 ms) and 610–899 in [100 ms, 1 s), with none in other bins.
Observed per-exit minima range from 17.136 to 17.835 ms and maxima from
0.695 to 0.946 s. Fixed bucket counts do not yield exact percentiles.

The four B indexing values range 256.846–409.244 s (median 355.243 s);
I values range 274.484–323.068 s (median 310.280 s). Paired ratios range
0.769–1.069 (median 0.887). The two BI ratios are 0.769 and 0.938; the two
IB ratios are 1.069 and 0.835. These small order groups and uncontrolled
cache/runner load do not support an order-effect claim. Observation spans
105.251–159.342 s in B and 127.502–172.000 s in I; fresh-resume spans
216.968–235.261 s in B and 189.325–227.893 s in I. Pair wall durations
remain below the 3,000 s cap, and the parent stopped after the fourth pair.

The result meets the four-complete-pair and consistent-majority-stratum
conditions, but **fails the 0.80–1.25 perturbation screen in pair 1**. The
verdict is therefore `inconclusive`, as recomputed by the closed report
validator. The high share locates an API span for further investigation; it
does not prove that commits, SQLite, storage or the wrapper caused the total
indexing time, and it does not authorize a production optimization.

## Environment, memory and next experiment

The report identifies a GitHub-hosted Windows `AMD64` runner, Windows release
`2025`, CPython 3.13.15, SQLite 3.50.4, Pillow 12.3.0, PNG zlib-ng 1.3.1,
four logical CPUs, and runner image `win25-vs2026` version `20260925.250.1`.
CPU model, total RAM, filesystem, storage, power policy and antivirus fields
are `null`, so those conditions were not measured. This hosted session is not
a defined physical reference desktop. The generated local fixture cannot
establish controlled cold-cache behavior, varied/large-media indexing,
100k gallery responsiveness or real SMB/NFS interruption behavior.

The recorded `tracemalloc` peaks are 7,594,045 bytes for each B trial and
7,605,017–7,605,073 bytes for I. Tracing starts after fixture creation and
includes Python allocations during the scan protocol, including verification
and retained asset-identity/UUID sets. It excludes native allocations,
whole-process RSS, whole-machine memory and the known-byte source checks after
tracing stops. These peaks are not total-memory budgets.

The smallest useful next experiment is a **separately declared, one-page
256-file/256-page balanced BI/IB/IB/BI diagnostic** on one identified Windows
runner. Keep B unwrapped and I exit-only; use identical phase hooks and tracing
in both variants, and
pre-read each generated source fixture before the timed scan so both variants
have an explicit, identical source-cache preparation. Record the per-pair B/I
indexing ratios and exit-stratum shares again, without pooling with this run.
This tests whether the perturbation screen and the large B variation persist
under a smaller, stated cache preparation; it cannot validate 2,048-file
performance or prove what the exit span does internally. A durability or
transaction-boundary change would need a separate design and tests.

The raw file retains the measured Windows checkout digests. Its six frozen
measured-source digests match the Git blobs byte-for-byte. The two new probe
module digests match the exact LF-to-CRLF transformation of their Git blobs,
reflecting Windows checkout bytes. The original publication gate compared all
eight digests directly with LF Git blobs. A narrow gate-only repair now accepts
that exact transformation for the two named new modules while keeping the six
frozen digests exact. The gate itself is a protected input changed after this
measurement, so its conservative closure requires a **fresh complete Windows
cohort** for publication. This first raw report is not rewritten, pooled or
used to skip that run.
