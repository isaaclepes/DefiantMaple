# Task 15: Independent scan-characterization acceptance

Owner: Luna. Status: local frozen acceptance complete; published-head hosted CI pending.

Read [Task 14](14-scan-characterization.md), [Task 16](16-characterization-review.md),
the existing profiling/soak contracts and current-head source before verification.
Fixtures are generated and fictional; never accept source/catalog inputs or use
private artwork. Root owns workflow integration and publication.

## Before freeze

Inspect proposed reporting/workflow contracts and prepare checks. Audit merged
main `317e9ebd713869e229166065b7fb990613905a6a` post-merge Core CI once complete,
using full all-event/latest-attempt pagination. Older Task 03 OS-suite statements
are historical: PR 12 hosted portable tests passed; actual SMB/NFS remains untested.
Do not execute dependent suites or benchmarks against moving implementation.

## Local acceptance after freeze

- Run one warning-as-error full Core suite with the configured scan venv.
  Coordinate focused checks already run by Sol; do not repeat unchanged checks.
- Run the four balanced 2,048/256 local pairs using the final CLI, each variant
  fresh and isolated. Store metrics outside tracked source; report all samples,
  environment and uncontrolled cache/storage scope. Local results are Linux
  evidence, not Windows or reference-desktop measurements.
- Check raw/summary identity and math, original soak integrity/recovery, fixture
  sizes/bytes/counts, explicit memory scope and instrumentation restoration.
- Validate the actual complete/partial JSON through the public privacy checker,
  then tracked-artifact privacy and whitespace. Check changed Markdown links and
  reviewed hashes. No fixtures, databases or model weights may be tracked.

## Published-head evidence

Audit all current-head workflows/checks/jobs and attempts with complete pagination;
push and PR events stay distinct. Read actual test summaries, especially Windows
Core, rather than inferring a suite passed from a combined job. Existing Windows
physical-rename capability skip is disclosed; portable loss tests must pass.

The dedicated PR-only experiment needs all 12 OS/pair jobs and its aggregator,
actual 2,048/256 settings, BI/IB/IB/BI coverage, eight trial samples per OS, exact
code/dependency/fixture/schema identities and all uploaded aggregate artifacts.
Inspect aggregate stdout and metadata tied to the current head. Missing, timed
out or incomparable data cannot be a complete result. No automatic reruns.
Qt/Tauri checks triggered by existing broad filters must also pass; do not infer
their old-head results or repeat their unchanged local suites.

## Local frozen acceptance (final Task 14 digest)

The accepted source freeze is `/tmp/defiantmaple-task14-freeze.sha256`; all 14
manifest entries passed `sha256sum -c`. The checkout remained at actual `HEAD`
`317e9ebd713869e229166065b7fb990613905a6a`. Final measured series code SHA256
is `bd8366dbfbed523e5847952237b244bfc16ef74e0570535599f892c133a22aad`; the
series regression test SHA256 is
`2e76a4108a97532d2e50cb71fa5035e0487bfa86f5b72816ce06bd1f5d9583c1`.
The uncommitted code is intentionally recorded as dirty in every raw report;
all four reports share the same fixed measured-code digests. The earlier four
pair reports generated before the cancellation-page validator fix are retained
outside this accepted cohort and are not aggregated or cited as final results.

The full warning-as-error Core command passed once on the frozen final code:

```sh
/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
```

Result: 159 tests in 19.301 seconds; 159 passed, 0 failures, 0 errors, 0 skips.
No unchanged Qt, Rust or focused suites were repeated. The final 43-test focused
warning-as-error scan suite passed before this handoff in 7.556 seconds; the
independent integrity review recorded 46 focused probes passing.

Each local pair used the following final command shape, with `--pair-index` 1
through 4 and a distinct metrics path in the pair-only directory:

```sh
/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m benchmarks.source_scan_profile_series pair \
  --count 2048 --page-size 256 --pairs 4 --pair-index 1 \
  --trial-timeout 720 --pair-timeout 1800 \
  --revision 317e9ebd713869e229166065b7fb990613905a6a \
  --run-id local --run-attempt 1 \
  --metrics /tmp/defiantmaple-characterization/final/pairs/linux-pair-1.json
```

All four reports are complete and authenticate the requested pair index,
`baseline/instrumented`, `instrumented/baseline`, `instrumented/baseline`,
`baseline/instrumented` schedule, 2,048 count, page size 256, `local`/attempt 1
and actual revision. Every child was fresh and isolated; all four reports show
both workers reaped, owned temporary storage removed, no issues, and matching
series-module digest. Each of the eight trials reports catalog schema version
4; 2,048 initial files in eight observation and indexing pages; 2,049 assets
after the fresh recovery; successful interruption/resume and Offline retention;
stable identity and unchanged source file sizes, mtimes and bytes. The shared
fictional fixture is `tiny-rgba-png-eight-content.v1`, 32x32 RGBA, eight encoded
contents, directory group 256, 220,672 original bytes plus one 105-byte resume
file. All instrumented component failure counts are zero.

Local runtime: Linux x86_64, kernel release 7.2.3, CPython 3.14.7, SQLite
3.51.2, Pillow 12.3.0, PNG zlib 1.3.1.zlib-ng, 12 logical CPUs. Host kind,
runner image, CPU model, RAM, filesystem/storage, power policy and antivirus
were unverified and remain null. The cache scope is
`fixture-created-and-stat-checked-os-cache-uncontrolled`; fixture creation and
initial stat checks precede timing. Memory is only the explicitly reported
`python-tracemalloc-scan-protocol-after-fixture-setup` allocation peak, not RSS,
native allocations or whole-machine use.

Raw elapsed seconds, baseline/instrumented:

| Pair | Order | Observation B/I | Indexing B/I | Fresh resume B/I |
| ---: | --- | ---: | ---: | ---: |
| 1 | BI | 3.009281 / 3.254704 | 5.485618 / 6.327689 | 7.235474 / 7.525083 |
| 2 | IB | 2.947553 / 3.175038 | 5.556604 / 6.475378 | 7.147772 / 7.475412 |
| 3 | IB | 2.876311 / 3.226233 | 5.429817 / 6.473320 | 7.055986 / 7.508043 |
| 4 | BI | 2.866712 / 3.193277 | 5.642809 / 6.484562 | 7.267981 / 7.634918 |

The complete aggregate reports, for baseline then instrumented, median
(min–max) observation 2.911932 (2.866712–3.009281) / 3.209755
(3.175038–3.254704) s; indexing 5.521111 (5.429817–5.642809) / 6.474349
(6.327689–6.484562) s; fresh resume 7.191623 (7.055986–7.267981) / 7.516563
(7.475412–7.634918) s. Pairwise instrumented/baseline ratios, by pair 1–4,
are observation 1.081555, 1.077177, 1.121656, 1.113916; indexing 1.153505,
1.165348, 1.192180, 1.149173; fresh resume 1.040026, 1.045838, 1.064067,
1.050487. These are one Linux machine's four paired runner executions with
uncontrolled cache/storage/load. Tracemalloc affects both variants and wrapper
instrumentation affects instrumented timings. They do not establish a cold
cache result, hardware budget, Windows/macOS performance, a percentile, or a
cause such as fsync/antivirus/storage; no production optimization follows from
these timings.

The aggregate command wrote its summary outside the pair input directory:

```sh
/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m benchmarks.source_scan_profile_series aggregate \
  --input-dir /tmp/defiantmaple-characterization/final/pairs \
  --count 2048 --page-size 256 --pairs 4 --platforms Linux \
  --revision 317e9ebd713869e229166065b7fb990613905a6a \
  --run-id local --run-attempt 1 \
  --metrics /tmp/defiantmaple-characterization/final/series.json
```

The complete series is
`/tmp/defiantmaple-characterization/final/series.json`, preserved byte-for-byte
as the repository's [local Linux raw series](../../benchmarks/source-scan-results/2026-09-29/linux-local-series.json)
(SHA256
`edd64c49fd4c69d359c20f67aada965f4390b89c4427af846a8f6d14343c12d6`). Pair
JSON SHA256 values are: pair 1 `ef13e372ab641941b5bfa2f95863509d71d672c65fd4d29cef7d2ea948713671`,
pair 2 `716815c75c6ae3d3c6c075d174c620b07bc88321f73aaab4693308b3938e1190`,
pair 3 `362f4df0433ec70311f0de0d27f62cf8c45fdafc68330eaa7b768ae7086f02d4`,
pair 4 `434c599352bd0506f21cff8dcd33cde8a7416b09f007b15d2a338400d501a26c`.
An authentic incomplete series generated from the first three verified reports
has `missing_pair`, no summaries, and is stored at
`/tmp/defiantmaple-characterization/final/incomplete-missing-pair.json`
(SHA256 `2599a459f729efa22cce8db64a689b02db9a41b0971e5b7d04322773cb05906d`).

The actual shared `validate_public_report` path in `scripts/check_public_artifacts.py`
accepted each of the four complete pair reports, the complete series and this
sanitized missing-pair incomplete report. The tracked-artifact privacy check
passed, as did `git diff --check`. Reports and generated fixtures remain only
under `/tmp`, outside tracked source. Hosted current-head 12-pair experiment
and any triggered Qt/Tauri checks remain pending publication; Linux results do
not close those platform gates or the separate real SMB/NFS and reference-
desktop validation.

## Ownership

Append evidence/status only to this file after local handoff; after publication,
record full hosted IDs/log proof in sibling `work/scan-characterization-ci-audit.md`
and report to root. Preserve handoff history; root's PR body records final current
head outcomes without another documentation-only CI loop. No implementation,
workflow, branch, commit, PR, source-media or mount mutations; no extra agents.
