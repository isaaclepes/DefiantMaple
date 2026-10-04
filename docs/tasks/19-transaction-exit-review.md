# Task 19: independent transaction-exit integrity review

Owner: independent Sol. Baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`.
Status: both hosted cohorts independently reviewed; first inconclusive, separate gate-repair cohort meets the predeclared attribution screen. Final publication documents/current-head CI review pending.

Own this task record. Independently review Task 17, the frozen soak/profile
drivers, new implementation/tests and root's workflow. Read production as needed
but do not modify it. Send early protocol/design findings to root and implementer.

Review exit-only semantics, original delegation/return/exception/custom-factory
behavior, readonly state timing, per-phase attribution and restoration of patches.
Bound counts/timing distributions, reject malformed/duplicate/extra fields and
identity mismatches, preserve source/metadata/durability/recovery. Ensure one
Windows job/session cannot masquerade as a physical reference desktop. Check
caps, four fresh BI/IB/IB/BI pairs and stop-on-first-failure. No retries/pooling.

Predeclared attribution screen is every indexing I/B ratio in 0.80–1.25 and
the same stratum exceeding 50% of indexing elapsed in every I trial. Incomplete
or screen-failing results are inconclusive, not grounds to relax the screen or
change production. Review privacy, environment/cache/memory limits, raw provenance
and the evidence-backed smallest next experiment. Accepted raw archives and six
measured sources remain byte-identical. Review current-head CI interpretation,
especially real Windows test summaries and capability skips.

Reproduce concrete findings with focused checks. Track severity, exact location,
resolution and final reviewed hashes. Independently review final raw results and
documentation before root publishes the final draft PR evidence.

Agents must not commit, push, switch branches, create PRs or edit another owner's
files. Root owns shared documents, workflow and publication. No merge authorized
for the next PR.

## Design review baseline

At baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`,
`defiantmaple.catalog.connect` opens a SQLite connection, enters `with db`,
then closes it in `finally`. The probe needs to time the delegated connection
`__exit__` itself, after reading `in_transaction` immediately before
delegation. The frozen soak gives all seven scan phases through `_paged_pass`
and its one direct offline `scan_sources` call. Both B and I need the same
phase hooks and tracing policy. Existing broad `ScanProfiler` interception is
not the exit-only instrument.

The six frozen measured-source SHA-256 values, in `source_scan_profile.py`,
`source_scan_soak.py`, `source_scan_profile_series.py`, `catalog.py`,
`sources.py`, `media.py` order, are:

```text
9e819cc3001912d40d6ba42c167fdcbde5f09e8acfcbae63e2d7db2982ac45ce
203dbb277fb4f2d0602ed008031ef75f42e1e7e8ff209002213ebd3fbe8190e7
4f55246ab68bc668a881290b0d6cce9941264940efa2660ac7d21fbd0d75d635
18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad
8e1c19d05920b8d537bd54a8ab1a5de5bc823727c5ccfa9b8275f0f5858cf87b
e14d21c7186a3c041a8efbd39f4b19179f7c89cd76b75a8f619802a8e256a116
```

The two accepted hosted raw archives currently hash to
`980360da60a12d6f0437ca0d227e5bb65cc7103b53a01da49cbc87a1725fc9b2`
(2026-10-02) and
`36da9c4706fa3b5e838ba7f57eeaa7c13a91c2b573865d9f33ddd9b5262c9e1e`
(2026-10-03). Final review must compare these bytes again.

An independent focused SQLite smoke on the preliminary probe exercised actual
commit and exceptional rollback. The first insert persisted, the second did
not; the corresponding instrumented strata each counted one exit. Keyword and
positional custom factories returned the exact custom connection class,
executed its own exit, and were left unmeasured. The full probe/series tests,
workflow identity, hosted raw report and final hashes remain to review.

## Resolved implementation findings

| Severity | Location | Finding and evidence | Verified resolution |
| --- | --- | --- | --- |
| High | `benchmarks/source_scan_exit_series.py::_attribution` | The initial version compared a stratum with half the inner phase elapsed instead of half the trial's outer `soak.timings_ns.indexing`. A focused constructed four-pair case with 45 ns of exits, 80 ns phase and 100 ns soak indexing incorrectly returned `attributed`. | It now uses outer indexing. The focused 60/100/130 ns boundary test returns `inconclusive`. |
| Medium | `benchmarks/source_scan_exit_series.py::run_pair` | The deadline check ran before cleanup while `wall_ns` was recorded after cleanup, permitting a complete report beyond the 3,000 s pair cap. | Final wall time is rechecked after cleanup; focused test makes cleanup cross a 0.1 s cap and gets an incomplete pair with `pair_deadline`. |
| Medium | `benchmarks/source_scan_exit_series.py::_metric` | A one-count histogram with 1,000,000,000 ns min/max/total in the first `<1,000 ns` bucket passed validation. A follow-up found that bin bounds alone allowed one sample to claim different minimum and maximum. | The validator now locates extrema in occupied bins and reserves their exact durations in the feasible sum. Focused impossible one-count cases are rejected. |

These findings were sent to the implementer and root before the hosted run.
The focused suite passed eight tests with `-W error::ResourceWarning`, including
an exit-raised SQLite `IntegrityError` that propagated while rollback held; full
workflow and hosted evidence remain pending.

## Resolved publication-gate findings

The first `scripts/transaction_exit_gate.py` draft could skip on a second or
later workflow attempt because it did not check the current attempt number. It
also checked merge-commit parents without checking that this commit was the
actual checkout `HEAD`. Both fail-closed checks and a fixed `windows-series`
job key now appear in the gate. The workflow uses the gate's environment-backed
CLI defaults; its series command binds the PR source head to the measured merge.

One gate provenance finding was reproduced: the initial graph test supplied the
*new* docs-only synthetic merge as `report.code.revision` while claiming the
old measured source head, yet the gate skipped. The gate now rejects the
current merge as the earlier measurement and checks the archived revision's
parents against its source head when the old synthetic merge object remains
available. The corrected graph test constructs a separate measured merge and
rejects a new-merge substitution and wrong old-merge parents. Three focused
gate tests pass under `-W error::ResourceWarning`. Old synthetic merge objects
may be unavailable after a shallow fetch; in that case the archived run/log
origin still needs the independent provenance review required by Task 18.

## Initial reviewed implementation hashes

The staged pre-measurement implementation and integration bytes reviewed here
have these SHA-256 values. Documentation and Task 19 may change when actual
hosted evidence is added; final review will verify the resulting head again.

| File | SHA-256 |
| --- | --- |
| `benchmarks/source_scan_exit_probe.py` | `21a23ab540ab3f1b86aaab3334d08c6afaaf0243a751b4f3939d946b7d76c0b8` |
| `benchmarks/source_scan_exit_series.py` | `4331c60f95627566ef8f16c42a42bcdcd7c3ee1d5d6dcac2d34dcda6c3657f0f` |
| `tests/test_scan_exit_probe.py` | `64607fea34e055403ca9975d13992f578599e506a0d01dd6e10423e3de65651d` |
| `scripts/transaction_exit_gate.py` | `29155d1596d0302ac00d7a85d90fecc083a2fe4537201e9bada2382d3e11f60e` |
| `tests/test_transaction_exit_gate.py` | `09f33c35bd7efc3ca239a379bb9f3d3837047a61f3d324535d27bb604121d46f` |
| `.github/workflows/transaction-exit-attribution.yml` | `2e306930569097ca45ad0752a2d8dd4a98eaacc1f7a8f767e0edfc9d97c930b6` |
| `scripts/check_public_artifacts.py` | `3faa2a934d9de3a67def42dccb7d8a418ae3a610e83a343245c2b11bab42fdbc` |

## Hosted CI fixture finding and repair

PR #14 initial head `ef71028c401a066e3d27d3b0015c98fe2b19cf6e`
exposed one Core unittest failure in the Ubuntu Qt benchmark-package job of
run `37139254907`, job `111250088892`: `test_cleanup_time_counts_against_pair_deadline`
expected `pair_deadline` but received `identity_mismatch`. I reproduced this
with GitHub-style `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`,
`RUNNER_ENVIRONMENT`, `ImageOS` and `ImageVersion` variables. The test's
`setUpClass` generated a local fake-child report with all six variables absent,
then the deadline test cleared only the first three before `run_pair` compared
the fake child's runtime metadata. Production identity rejection behaved as
designed; the fixture environment was inconsistent.

The narrow test-only repair defines `LOCAL_ENV_KEYS` once and clears the same
six keys in fixture setup and both local-fixture tests. The exact hosted-style
reproduction then passed all eight exit-probe tests with
`-W error::ResourceWarning` in 1.87 seconds. The repaired
`tests/test_scan_exit_probe.py` SHA-256 is
`675dfb4947cdb7b0a1e7c7e843f171df8eb72a6d914e4e66522e2b678edd8d13`.
No production or frozen measured source changed. This is a source-head test
repair; the failed initial CI event remains a failed event and any new
measurement has its own run/attempt identity.

## Failed initial Windows measurement and checkout repair

The initial PR #14 Windows attribution job was run `37139254911`, attempt 1,
job `111250132237`, measured merge
`ba4cab4c4b3afa27acc8329c59895659237ebd0d`. Its checkout log explicitly
shows `fetch-depth: 1`; the `series` command exited 1 with a bounded minimal
`defiantmaple.source-scan-exit-series.v1` report, `status=incomplete`, no
samples, and one `identity_mismatch`/`ValueError` issue. Artifact
`11279836821` was uploaded; GitHub reports a 313-byte ZIP and its ZIP digest
`bd77a91715ef870417c992e4232a5484a22e568402ef515b0552cc9c77f677a9`.
The decoded job log independently confirms the JSON fields, but the artifact
download initially returned 403. A fresh connector reference was then
materialized and independently verified by Task 18: the 313-byte ZIP SHA-256
matches the GitHub digest, and its 211-byte CRLF JSON member SHA-256 is
`5461353fe287b392c47ce5acb4ff77c96427e7b9be3c85682a87d19e6f8f6e03`.
Converting only CRLF to LF yields the retained 200-byte report exactly; I
independently recomputed the retained hash and the stated CRLF form's hash
from the retained bytes. Task 18 confirms that the actual ZIP member matches
that CRLF form. No pair completed and this attempt supplies no attribution
timing.

The hosted `series.actual_identity` must verify that the measured synthetic
merge has the reported PR head as its second parent. A shallow depth-one
checkout hides its parents from `git show --format=%P`, making the original
identity refusal correct. I reproduced that Git behavior with a temporary
two-parent merge: a depth-one clone returned no parent hashes, while depth two
returned both. The workflow-only repair sets `fetch-depth: 2` on the
`windows-series` checkout; the gate retains depth 128. No identity check or
production code was weakened. The repaired workflow SHA-256 is
`15e267ad12f3ea673135e22be8fb44b3daa64f08ff6d19a9914259ee80281edd`.
This failure remains a separate incomplete run; the next source head needs a
fresh full measurement, never a failed-only retry or pooled pair.

The failure-history JSON reconstructed from the decoded job log parses as the
same four-field minimal incomplete report (`schema`, `status`, `samples`,
`issues`) and passes the closed series and
public privacy validators. Its SHA-256 is
`0bfda5a4f8877f4ccc791afa54b7338beacdb30788a0c520a908003bf98977aa`.
The `docs/transaction-exit-benchmark-history/` prefix is outside the gate's
sole canonical complete-evidence prefix
`docs/transaction-exit-benchmark-results/`.

## Additional initial-head Windows Core finding

Read-only job-log inspection found that the initial `test-benchmark-package
(windows-latest)` job `111250089046` in run `37139254907` did run a Core
unittest summary: 193 tests, two failures, one capability skip. Besides the
exit-probe test fixture failure above,
`test_transaction_exit_gate.GateTests.test_only_proven_attempt_one_docs_delta_skips`
failed at line 77: expected a verified docs-only skip but got
`changed_inputs`. The temporary Git fixture wrote text with a newline; on
Windows, working-tree CRLF can differ from the committed blob while the gate
correctly requires exact protected bytes. I reproduced `changed_inputs` by
changing only the temporary protected working file to CRLF. The test fixture
now uses explicit LF bytes, disables autocrlf in its temporary repository,
and asserts that the post-checkout protected bytes remain LF. The production
gate's strict check is unchanged. Three gate tests pass with and without a
simulated global autocrlf=true setting under `-W error::ResourceWarning`.
The repaired `tests/test_transaction_exit_gate.py` SHA-256 is
`40f8ba1921bb5953779fecb9ab77dc9326a3bf3d01fd1b8fb30b588891b49065`.
The history README now separately identifies the failed Windows
benchmark-package 193-test summary and the cancelled Core-matrix jobs with no
test summaries. Task 18 retains the independent CI audit.

The artifact-verified history README now hashes to
`341e2a92d93f8bfaf1d3bd0f007637f527a50a7378c1bcb12b8dea419c8951f5`.
After staging the history JSON, the tracked public-artifact privacy check
passed and the report passed the closed series validator. The reviewed repair
set is limited to the two test fixtures, Windows checkout depth, Task 18/19
records and the separate immutable failure-history files. Root reports its
full Core suite passed 193 tests after the first fixture repair; the later newline
fixture fix passed three focused gate tests under normal and simulated global
autocrlf=true settings. The repaired head subsequently produced a complete
Windows series, reviewed below; final source-head evidence remains pending.

The guide-only correction quotes the actual folded workflow command, defines
the eight disjoint latency bins accurately, and narrows memory claims to the
`tracemalloc` Python-allocation scope after fixture creation. I checked its
interval boundaries against `BUCKET_UPPER_NS` and its tracing scope against
the frozen soak. Its null runtime fields are correctly described as
unavailable. These documentation edits do not change the probe or measured
source bytes. The guide SHA-256 at this review is
`2d5f4bd68eced0c8fcd777d52a2edcd61502bfcc2fb6eb8bf7c414daeb4cd0c1`.

## Completed Windows series: independent raw review

Run `37140259168`, attempt 1, Windows job `111253079928`, PR head
`cf483d06d15828d18f14501687a96a570e8622de` produced one complete
four-pair series at measured merge
`c1193a38165483d6f738ea31d701541d411ad857`. GitHub reports both the
gate and Windows-series jobs successful and artifact `11282622095` bound to
that run/head. Its 5,861-byte ZIP SHA-256 is
`fa1757dd0de5d06ebb41c9b5793d041b965948b3a9f6ecbd5ad3ed1fa88e1a5e`;
the sole 106,445-byte CRLF member SHA-256 is
`b4e48cd784480ebffca2d87469e258016c76e46801657d6189d974c984cea0c9`.
CRLF-to-LF normalization exactly matches the 103,399-byte canonical raw JSON
at `docs/transaction-exit-benchmark-history/2026-10-03/first-complete/`, SHA-256
`f9420182d43737f6a47eddbddeffd61bc1553523e0a28d4aca9571b979dbceaa`.
The closed series validator and public privacy checker accept that JSON.

All four fresh pairs have the BI/IB/IB/BI order, two trials each, one run,
attempt, job, session token, revision, runtime and canonical fixture. Each
child preserved eight observation and indexing pages, 2,049 recovered assets,
all five soak integrity booleans, and full reaping/owned-storage cleanup.
There are no pair or series issues. The eight Python-traced peaks are about
7.24–7.25 MiB; total process or machine memory, cold-cache state and physical
reference hardware remain unavailable.

| Pair | Indexing I/B | `transaction_normal` share of full I indexing |
| --- | ---: | ---: |
| 1 | 0.769282 | 91.585% |
| 2 | 1.068671 | 90.960% |
| 3 | 0.835355 | 91.708% |
| 4 | 0.937818 | 90.874% |

I recomputed the ratios and shares from raw nanoseconds. Pair 1 breaches the
predeclared 0.80 lower perturbation bound. The complete experiment's
attribution verdict is therefore **inconclusive** despite the same exit
stratum exceeding 50% in every I trial. The reported exit span is an API
interval to inspect; these numbers do not prove why it is long or authorize
production transaction, locking or durability changes. No pair may be
replaced or pooled with either accepted source-scan cohort.

The six frozen code hashes in this report match the baseline bytes exactly.
The two new probe/series code hashes instead match the Windows CRLF checkout
bytes: converting the current LF Git blobs to CRLF reproduces both reported
digests exactly. The original new publication gate compared those raw hashes
against LF Git blobs and would conservatively schedule a fresh measurement on
a docs-only evidence update. The raw digests remain untouched. The reviewed
gate repair authenticates exactly the LF-to-CRLF checkout transformation for
those two named files; that repair itself changes protected inputs and
requires one fresh full run.
The first complete run remains a distinct inconclusive cohort in the history
prefix; no retry to clear the screen or cross-run pooling is allowed.

## Narrow Windows checkout digest proof review

The repair in `scripts/transaction_exit_gate.py` names only
`benchmarks/source_scan_exit_probe.py` and
`benchmarks/source_scan_exit_series.py`. For those two files it rejects Git
blobs already containing CR or lacking LF, then compares the raw digest with
the SHA-256 of the blob's exact LF-to-CRLF transformation. The six older
measured files still require the untransformed Git-blob digest. The public
report validator still requires the exact eight-code-file schema, a complete
hosted Windows four-pair report, and the canonical configuration. The gate
retains attempt-one, synchronize, ancestry, current synthetic-merge parent,
docs-only delta and protected-byte closure checks. The protected set includes
the gate, its tests, workflow, privacy checker and all measured sources; its
blobs must agree across archived source head, prior head, current merge and
current checkout. A gate-only repair after the archived run therefore forces
measurement rather than reusing that old report.

Five focused temporary-Git graph tests pass with
`-W error::ResourceWarning`, both under normal Git settings and a temporary
global `core.autocrlf=true`. They cover the positive two-file CRLF proof and
fail-closed frozen-file CRLF, new-file LF/mixed representation, altered digest,
extra digest, wrong platform and changed protected gate input. The unchanged
gate path requires another full measurement for an unproven identity, attempt,
merge parent or non-doc delta. I found no blocking defect in this bounded
repair. Reviewed local SHA-256 values: gate
`1f2c826637639a32f5c7e0f919afcaf83bde69e948b8c9ddac23c187f1e96802`;
gate tests
`cc128f06be8f89150fd809979d901ffecc4bc10aa3bc95606e316e0a7eaac844`.
These are pre-publication file hashes; final source-head and raw evidence
checks remain pending.

## First-cohort record and shared-document review

The separately retained first-complete raw has the same 103,399 bytes and
SHA-256 `f9420182d43737f6a47eddbddeffd61bc1553523e0a28d4aca9571b979dbceaa`
as the independently reviewed LF report. It passes the closed series and
public privacy checks. I checked all eight reported code digests against the
current source bytes: the six frozen files match exactly, and only the two
named new modules match an LF-to-CRLF conversion. The four pair timings,
ratios, counts, fixed-bin ranges, 2,048-file fixture and traced-memory scope
in the first-complete README agree with the raw fields. The README now states
the verified artifact ZIP/member/log linkage and correct next-experiment
contrast: B unwrapped, I exit-only, with shared hooks and tracing. Its SHA-256
is `8cb4167572aff3dcc9004542773b6f142eb32fb1329c819858234e4d4bd0a158`.

I reviewed the linked Task 00/17/18 updates, attribution guide and initial
failure-history correction for consistent separate cohorts and the inconclusive
screen. The failure record retains its four-field, zero-sample status and
now correctly states that the historical artifact download was later
resolved. Reviewed SHA-256 values: Task 00
`4fbf0ec6e39f73d9bbfd5e11b3d600027b375e7fafa97a354ef2faaf57d89b80`,
Task 17 `489d10ad7d83a3b8315ee33f60c40e5255f2bed9a39b52fc68bda1fe07724a7e`,
Task 18 `ed7209027ea757cbca1754042258c8114dc568226858cc8fb47adb7eedfa13da`,
guide `834eea80e43da067c527e0721fb562382df449fb1006bb5034d0a2dfe553daa9`,
and initial-failure history README
`341e2a92d93f8bfaf1d3bd0f007637f527a50a7378c1bcb12b8dea419c8951f5`.
The next protected source head, current-head CI and its new complete Windows
raw remain for a separate final review.

## SDD v0.2 impact review after task resumption

I reviewed the supplied 1,045-line revised specification at
`output/Artist_Gallery_Asset_Management_SDD_v0.2.md`, SHA-256
`cc89c06088b894163cd8e477da7407be4e6b93a39a25e71b423083ea4d43a157`,
against the frozen transaction-exit protocol and this PR's evidence. The
document marks its baseline as source head `1d4dc92c5a9aa4bd043daaf191581ef19937e611`;
its implementation snapshot explicitly does not certify later CI or the
gate-repair cohort. Product targets in §19 are candidates: the proposed
eight-logical-core/16 GiB/local-SSD reference profile and interaction,
cancel, cache and full-process RSS budgets become acceptance thresholds only
after a named machine and workload are adopted before measuring. This hosted
four-pair scanner report measures neither a physical reference desktop nor
those gallery UI and whole-process budgets. Its 2,048 tiny generated files
also do not establish the §21 representative 10k/100k/500k media workloads.

Section 19.4 requires predefined fixture, code, pairing, caps and stop
conditions; retains every failed/inconclusive attempt separately; forbids
assembling a balanced cohort from failed-only reruns and forbids retrying for a
preferred verdict. Those rules agree with retaining the first complete
`inconclusive` cohort and reviewing the already triggered fresh run as the
required protected-gate-source cohort. They do not replace the original
0.80–1.25 indexing-ratio and common >50%-stratum screen or permit weakening
durability from exit-span timings. Any later one-page/cache-preparation
diagnostic requires its own decision and declaration, not automatic work in
this PR.

Sections 7 and 22 make Phase 1a a useful explicit-scan gallery and Phase 1b
the separately accepted watching/reconciliation increment. Generated
synthetic source loss remains useful scanner evidence but is not real SMB/NFS
or watcher acceptance; that does not invalidate the current bounded probe.
The broader v0.2 identity, curation, backup, display, accessibility and
resource requirements are forward-looking product scope, not retroactive
claims that this diagnostic or existing CI satisfies Phase 1a release gates.
I found no contradiction that requires changing this PR's frozen runtime
sources, production transaction settings or predeclared measurement protocol.

## Fresh gate-repair Windows cohort: independent raw review

The protected gate-repair source is
`1d4dc92c5a9aa4bd043daaf191581ef19937e611`, tree
`bf513104f50d87fe662f3f53e5085c8b9263ab2b`. GitHub's Git-data commit
API independently confirms the measured synthetic merge
`92a9fce9bcd4d53f8be630010e7986832c35324e` has that tree and ordered
parents baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`, then
the protected source head. GitHub's Actions API reports run `37148420816`,
attempt 1, pull-request event, successful `windows-series` job
`111277186186`, and artifact `11284681263` tied to that run/head. The job
ran from 19:36:33 to 20:44:10 UTC on 2026-10-03. Its sole artifact ZIP is
5,758 bytes, SHA-256
`31d38f8b026b26ccb7c7e42e0e44d9193cc3af55c74378005d4c983eb330be37`,
matching GitHub's artifact digest. The ZIP's only member is a 106,366-byte
Windows CRLF `transaction-exit-series.json`, SHA-256
`1db84da5de41240ad6d572be8a7a8b17ce30e5cdae36ff8d65a5a6d30c2732a3`.
Replacing CRLF with LF reproduces the exact 103,320-byte canonical report at
`docs/transaction-exit-benchmark-results/2026-10-03/windows-series-run-37148420816-attempt-1.json`,
SHA-256 `38653a2d770db33d4ebdc41617a53bc66beb02eb35a323988e439582678ba94d`.
That file also equals the independently retained LF JSON reconstructed from
the 213,299-byte decoded runner log, SHA-256
`2be0f87daf033d41e3e56b9c3728629476f605c04cfcc479e599247a4598de3a`.

The closed series validator and public privacy checker both pass. One run,
attempt, logical job, source head, measured merge, ephemeral session token,
runtime and canonical fixture cover all four complete BI/IB/IB/BI pairs.
Each B/I child used a fresh process/fixture and completed eight observation
and eight indexing pages, 2,049 recovered assets, all five soak integrity
checks and full worker/owned-storage cleanup. All pairs and the series have
no issues; pair wall times are 1,096.472, 996.711, 971.584 and 972.197 s,
below the 3,000 s cap. The eight `tracemalloc` peaks are 7,594,045 bytes in
B and 7,604,902–7,604,957 bytes in I; these are Python allocation peaks,
not whole-process RSS. CPU model, RAM, filesystem/storage, power policy,
antivirus and controlled cache state remain unavailable. The hosted job is
one runner session, not a physical reference desktop.

| Pair | B indexing (s) | I indexing (s) | I/B | `transaction_normal` share of full I indexing |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 221.213 | 197.741 | 0.893890 | 90.734% |
| 2 | 184.767 | 192.446 | 1.041559 | 91.322% |
| 3 | 178.150 | 191.386 | 1.074297 | 90.426% |
| 4 | 184.559 | 187.652 | 1.016758 | 90.486% |

I recomputed each ratio from the raw outer soak indexing nanoseconds, and
each share from the `transaction_normal` exit-total nanoseconds divided by
the full I indexing elapsed. The same stratum counts 4,112 indexing exits
in every I trial. Every ratio is in the predeclared inclusive 0.80–1.25
range, and that same stratum exceeds 50% of I indexing in every pair. The
fresh cohort therefore supports the **attributed exit API span** verdict
under the declared diagnostic screen. It does not establish why that span is
long, the cost of commit/locking/storage, a production optimization, a
durability change, a representative-media indexing budget, or any §19 SDD
reference-desktop target. The earlier complete cohort remains separately
`inconclusive` because its first ratio failed; neither cohort is rewritten,
pooled or replaced.

All six frozen measured-source digests in the fresh report still match LF Git
blobs byte-for-byte. The two new probe/series digests match only the exact
LF-to-CRLF transformation authenticated by the repaired gate. I exercised
that gate against this *actual* fresh report using a temporary isolated Git
clone at the measured source head, a docs-only descendant commit and a new
synthetic merge with the proper base/head parents. The decision was
`(False, "verified_docs_only_evidence")`; changing only the simulated
GitHub attempt to 2 returned `(True, "measurement_event")`. This did not
alter the real checkout or schedule a hosted measurement. Final publication
must still validate its exact docs-only branch delta and current-head CI.

## Publication-document and source-head CI review

I checked the canonical result README against the raw nanoseconds, counts,
histogram bins, extrema, medians, observation/resume ranges, memory scope and
artifact identities. Its span-only interpretation is supported. Its
conditional next experiment depends on first adopting a reference profile,
representative media and a product budget; its two balanced idle/indexing
pairs provide a control for foreground responsiveness and predeclare a
decision difference, invalid-run rule and one-hour stop. It does not schedule
another microbenchmark or transform this hosted result into a release NFR claim.
The guide, Task 00/17/18 updates and SDD v0.2 review keep the first complete
inconclusive report, the separate fresh attributed report and both accepted
scan-characterization cohorts distinct. The copied SDD v0.2 is byte-identical
to the supplied 93,686-byte source. The new/updated Markdown files had no
broken local links or matches for the public checker’s private NAS-artwork
path pattern; the canonical JSON passed the closed privacy check.

GitHub's read-only check-run API returned all 46 checks at exact measured
source head `1d4dc92c5a9aa4bd043daaf191581ef19937e611`, each completed
successfully. Task 18 independently inspected the actual Windows Core/Qt
test summaries and one documented filesystem-capability skip; success icons
alone are not the basis for that assertion. These are the measured-source
checks. The documentation-only publication head and this record-correction
descendant need exact-head CI and gate results reviewed before this task is
closed.

Reviewed publication SHA-256 values: canonical result README
`e078420992c6e6ec0a7acda7605ff041205b1877c0d2a3011fd6d4035bc50f05`,
Task 00 `28cff3429ae34a7c73595f46bd02732e7ec79769f82cae3c30ff6637d2cf151c`,
Task 17 `1dc2ba564423d9663a31825c2c7d62d5956559cb547fb1e9e248a700372c58f0`,
Task 18 `7b88276cf983ded7e9de999ffd13bd7664d625d4287ac98e573e96f928b0e40d`,
guide `7845411c8c9d831a675daedc593b3baae8859f1a5ed0a5384c443361bf02bab1`,
and SDD v0.2 review
`5f74296e5a2f394f1a9c1be5a9d44e4580ea7217f14062c1aba46123111f44d4`.
