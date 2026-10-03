# Task 19: independent transaction-exit integrity review

Owner: independent Sol. Baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`.
Status: initial implementation and repair reviewed; fresh hosted evidence review pending.

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
member bytes were not available through the local download (403), so this is
not a member-byte hash or acceptance of a raw measurement. No pair completed
and this attempt supplies no attribution timing.

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
same five-field minimal incomplete report and passes the closed series and
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

The repaired history README hashes to
`34de184b7e3810d0b0ac1064f5196582df67e969175fff61b7a94c8d062182f1`.
After staging the history JSON, the tracked public-artifact privacy check
passed and the report passed the closed series validator. The reviewed repair
set is limited to the two test fixtures, Windows checkout depth, Task 18/19
records and the separate immutable failure-history files. Root reports its
full Core suite passed 193 tests after the first fixture repair; the later newline
fixture fix passed three focused gate tests under normal and simulated global
autocrlf=true settings. Fresh current-head hosted Windows summaries and a
complete four-pair raw report remain required before final Task 19 acceptance.
