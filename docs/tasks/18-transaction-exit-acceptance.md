# Task 18: transaction-exit acceptance and CI audit

Owner: Luna. Baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`.
Status: exact-head CI and the fresh hosted four-pair cohort at `1d4dc92c5a9aa4bd043daaf191581ef19937e611` completed successfully; its predeclared attribution screen passes. The earlier complete cohort remains separately inconclusive. PR #14 remains a draft and unmerged; this diagnostic does not qualify product NFRs or reference-hardware performance.

Own this task record and independent acceptance records. Read Task 17 and the
2026-10-02 predeclared next experiment. Audit post-merge main CI, then the new
PR's exact current head and actual Windows unittest summaries. Distinguish all
events and conclusions, failed tests, capability skips and measurement jobs.
Do not treat a check's green icon as proof of a particular test count.

Validate frozen six measured hashes and both accepted raw archive byte hashes.
Independently run relevant tests and public-artifact privacy checks when ready;
repeat only for changes/failures. The experiment is four sequential 2,048/256
BI/IB/IB/BI pairs in one Windows job/session, child/pair caps 1,440/3,000 s, stop
at first timeout/cleanup/integrity failure. Never replace failed pairs or pool
cohorts. Validate exact code, revision, fixture, runtime, order, run/attempt/job
identity, cleanup, recovery, source bytes and asset identities.

Independently recompute every indexing I/B ratio and each exit stratum share.
All four ratios must be 0.80–1.25 and the same stratum must exceed 50% in every
I trial for attribution acceptance. Otherwise retain the report as inconclusive.
Separate protocol completeness from attribution acceptance. Check bounded raw
fields contain no paths, SQL, rows, private labels, machine/user identifiers or
fabricated values. Document unavailable CPU/RAM/filesystem/RSS/cache facts.

Communicate actionable failures with exact evidence. Keep a wrapper record with
run/job links, source head, measured merge, artifact provenance and raw hashes.
Root owns Task 00/workflow/PR. Agents must not commit, push, switch branches,
create PRs or edit another owner's files. Leave the next PR unmerged.

## Initial acceptance record (2026-10-03)

The merged baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91` has 12 completed
check-runs on workflow 37120430261; all 12 succeeded. The actual Windows Core
logs show Python 3.11 job 111195308226 ran 182 tests in 507.018 s and Python
3.13 job 111195308154 ran 182 tests in 416.151 s. Each had 181 passes, zero
failures/errors, and one host-capability skip:
`test_local_loss_recovery_checks_both_phases_and_stable_uuids`, because the host
denies generated-root rename with an open scan handle. The portable injected-loss
protocol is tested separately. Both public-artifact privacy checks passed. The
exact decoded logs and check-run snapshot are preserved under
`work/transaction-exit-raw/`.

Both previously accepted raw archives match their frozen SHA-256 values: Oct 2
run 36634086725 attempt 3, `980360da60a12d6f0437ca0d227e5bb65cc7103b53a01da49cbc87a1725fc9b2`,
and Oct 3 run 37091008433 attempt 1,
`36da9c4706fa3b5e838ba7f57eeaa7c13a91c2b573865d9f33ddd9b5262c9e1e`. All six
measured source-code hashes in the Oct 3 accepted report matched the local file
bytes exactly.

Independent focused validation passed: 7 exit-probe tests in 1.866 s. An
independent privacy-negative check accepted a valid generated 64-file/four-pair
report and rejected duplicate JSON keys, extra schema fields, a forged host
identity, private labels, SQL-like query data, and an absolute path. The staged
tracked-artifact privacy check passed. The root-owned full Core integration
suite passed 193 tests in 25.410 s with `-W error::ResourceWarning`, zero
failures/errors/skips; the independent reviewer separately passed 8 probe and
3 gate tests. No local 2,048-file measurement was run.

The protocol uses one Windows job and one series parent/session, with a
220-minute workflow job cap, 3,000-second pair cap, and 1,440-second child cap.
The earlier characterization experiment's 55-minute per-pair job setting does
not apply. Exact-head GitHub CI, actual Windows summaries for the new PR,
privacy CI, and the four-pair hosted artifact still require independent audit.
No hosted probe result or attribution conclusion is claimed here.

## Initial hosted attempt and repairs

The first PR #14 source head `ef71028c401a066e3d27d3b0015c98fe2b19cf6e` exposed
two separate failures. First, the Windows transaction-exit job used a
depth-one checkout, which hid the merge ancestry required for the series
identity check. It emitted an incomplete report with zero samples and
`identity_mismatch` before any pair began. The runner uploaded artifact
11279836821 (313 bytes; ZIP SHA-256
`bd77a91715ef870417c992e4232a5484a22e568402ef515b0552cc9c77f677a9`). The
connector download returned HTTP 403, so the JSON saved in the history
directory was initially reconstructed from the exact JSON text emitted in the
preserved job log. A later retry through the GitHub artifact-download connector
and `curl --fail --location` materialized the ZIP and member. The 211-byte CRLF
member SHA-256 is `5461353fe287b392c47ce5acb4ff77c96427e7b9be3c85682a87d19e6f8f6e03`;
normalizing CRLF to LF gives byte-for-byte equality with the 200-byte emitted
log reconstruction and published history JSON, SHA-256
`0bfda5a4f8877f4ccc791afa54b7338beacdb30788a0c520a908003bf98977aa`. The ZIP
SHA-256 `bd77a91715ef870417c992e4232a5484a22e568402ef515b0552cc9c77f677a9`
matches GitHub's artifact digest. Thus the historical initial failure is now
cross-checked against the actual member; the first 403 remains part of the
transport history. See
[`initial-run-37139254911-attempt-1.json`](../transaction-exit-benchmark-history/2026-10-03/initial-run-37139254911-attempt-1.json)
and its adjacent README.

Second, `test_cleanup_time_counts_against_pair_deadline` failed on Ubuntu
Python 3.11, Ubuntu Python 3.13, and macOS benchmark-package runs because the
test's synthetic child identity lacked hosted environment fields, so it
returned `identity_mismatch` before the deadline assertion. The separate Core
matrix Windows jobs 111250089130 (3.11) and 111250088949 (3.13) were
automatically canceled after the Ubuntu 3.11 failure triggered default
fail-fast; neither has a unittest summary. The Windows benchmark-package job
111250089046 did complete unittest discovery: 193 tests in 359.314 s, with
190 passes, two failures, and one capability skip. It failed the same deadline
fixture test and `test_only_proven_attempt_one_docs_delta_skips` at line 77,
where Windows returned `(True, 'changed_inputs')` instead of
`(False, 'verified_docs_only_evidence')`. The latter came from CRLF conversion
in the temporary Git fixture; the strict publication gate itself was not
weakened. The Windows job stopped at the failing test step, so its public
artifact privacy step did not run. Root fixed the deadline test's local GitHub
metadata, made the gate fixture byte-stable across Windows line endings, and
changed the measurement workflow checkout depth to two. Root's repaired local
Core run passed 193 tests in 26.873 s with `-W error::ResourceWarning`, zero
failures/errors/skips. A fresh tracked-artifact privacy run after adding the
history record passed. These are local repaired checks; the corrected source
head's Windows CI, current-head Windows unittest summaries and full four-pair
hosted measurement remain pending.

## Corrected-head CI and first hosted cohort (2026-10-03)

The corrected PR source head is `cf483d06d15828d18f14501687a96a570e8622de`,
tree `54f4c16baa926f3d899ad740b6f4e04d14227fe7`, on top of baseline
`80887a2196fea3c3c6568fc11e7d1b7b78054f91`. GitHub REST
`check-runs?per_page=100` returned all 46 checks at this exact head; all 46
completed successfully. This includes Core push and PR, Qt, Tauri, the legacy
12-pair characterization event, and the new exit workflow. The snapshot is
retained as `work/transaction-exit-raw/pr14-cf483d0-check-runs-per-page-100.json`.

Actual corrected-head Windows Core summaries:

- Core push Python 3.13, job 111253035889: 193 tests in 546.594 s, 192 passed,
  zero failures/errors, one capability skip; public-artifact privacy passed.
- Core push Python 3.11, job 111253035827: 193 tests in 759.912 s, 192 passed,
  zero failures/errors, the same skip; privacy passed.
- Core PR Python 3.11, job 111253043375: 193 tests in 574.484 s, 192 passed,
  zero failures/errors, the same skip; privacy passed.
- Core PR Python 3.13, job 111253043459: 193 tests in 904.862 s, 192 passed,
  zero failures/errors, the same skip; privacy passed.

The only skip remained
`test_local_loss_recovery_checks_both_phases_and_stable_uuids`: the host denies
renaming the generated root with an open scan handle, while the portable
injected-loss protocol is covered separately. The Windows Qt package job
111253043243 ran 193 Core tests in 663.107 s with zero failures/errors and this
same skip, then 28 Qt tests in 17.602 s with no failures/errors/skips. It built
the unsigned package (32,472,064 bytes), passed frozen-thumbnail smoke, and
uploaded its artifact. That workflow did not run a public-artifact privacy
step. The Windows Tauri job 111253043417 passed 2 Node tests and 4 Rust tests
and completed packaging. The separate legacy characterization run 37140259227
and its aggregate succeeded with all 12 pairs complete; that archive is kept
separate and none of its timings are pooled with this cohort.

The new Windows transaction-exit run was GitHub Actions run 37140259168,
attempt 1, pull-request event, job 111253079928 (`windows-series`). REST
confirms source head `cf483d0...`, base `80887a2...`, run start 17:22:21Z, job
start 17:23:35Z, and completion 19:16:08Z. The four-pair step ran
17:23:59Z–19:16:04Z and succeeded. The measured merge checkout was
`c1193a38165483d6f738ea31d701541d411ad857`, tree
`54f4c16baa926f3d899ad740b6f4e04d14227fe7`, with parents exactly the baseline
and PR source head, confirmed by GitHub's commit API and the runner checkout
log. The report identifies one Windows Server 2025 hosted runner session,
CPython 3.13.15, 2,048 files, page size 256, and four complete pairs in
BI/IB/IB/BI order. All pairs have no issues; cleanup reaped workers, removed
owned storage, and retained no storage. The soak report records interruption
and resume, offline asset retention, stable identities, unchanged source
files/bytes, and 2,049 assets after recovery.

The canonical LF report is preserved unmodified at
[`first-complete/windows-series-run-37140259168-attempt-1.json`](../transaction-exit-benchmark-history/2026-10-03/first-complete/windows-series-run-37140259168-attempt-1.json).
The raw Windows artifact, actual CRLF member, decoded runner log, and emitted
LF reconstruction are preserved separately under `work/transaction-exit-raw/`.
Artifact
11282622095 has ZIP SHA-256
`fa1757dd0de5d06ebb41c9b5793d041b965948b3a9f6ecbd5ad3ed1fa88e1a5e` (5,861
bytes). Its 106,445-byte CRLF JSON member has SHA-256
`b4e48cd784480ebffca2d87469e258016c76e46801657d6189d974c984cea0c9`. It parses
identically to the exact 103,399-byte LF JSON block reconstructed from the
Windows log, SHA-256
`f9420182d43737f6a47eddbddeffd61bc1553523e0a28d4aca9571b979dbceaa`; converting
CRLF to LF makes the member byte-for-byte identical to the emitted block. The
full 213,379-byte decoded Windows log SHA-256 is
`7203e843bc3f091046d28e5ec911c486cbe70a21c252a6951b59eded4335cf44`. The
report passed the closed public-report validator and independent public-artifact
`_check_json` screen with no errors.

All eight code digests from the Windows report were checked. The six
pre-existing measured files match their LF checkout bytes exactly:
`benchmarks/source_scan_profile.py`
`9e819cc3001912d40d6ba42c167fdcbde5f09e8acfcbae63e2d7db2982ac45ce`;
`benchmarks/source_scan_soak.py`
`203dbb277fb4f2d0602ed008031ef75f42e1e7e8ff209002213ebd3fbe8190e7`;
`benchmarks/source_scan_profile_series.py`
`4f55246ab68bc668a881290b0d6cce9941264940efa2660ac7d21fbd0d75d635`;
`defiantmaple/catalog.py`
`18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad`;
`defiantmaple/sources.py`
`8e1c19d05920b8d537bd54a8ab1a5de5bc823727c5ccfa9b8275f0f5858cf87b`; and
`defiantmaple/media.py`
`e14d21c7186a3c041a8efbd39f4b19179f7c89cd76b75a8f619802a8e256a116`. The
two new benchmark files are not pinned to LF by `.gitattributes`; Windows Git
checkout produced CRLF working bytes. Converting the local LF files to CRLF
reproduces the report hashes for `benchmarks/source_scan_exit_probe.py`
`6485053514e1035f653a2d412acfb361fdb0f3b0d4fbb6fff27b4a6aff9b06b7` and
`benchmarks/source_scan_exit_series.py`
`7cb1282a885d5f3c526229e90ef08c4563f6628ee762e972f1fa1084eb5f83dd`. These are
the exact reported Windows-checkout byte hashes. CPU model, total RAM,
filesystem, storage, power policy and antivirus are null, meaning unavailable.

I independently recomputed the predeclared screen using each trial's outer
`soak.timings_ns.indexing` as the elapsed denominator. I/B indexing ratios for
pairs 1–4 were 0.769282182544, 1.068670841812, 0.835354825991 and
0.937817873644. Pair 1 falls below the inclusive 0.80–1.25 range. The same
stratum, `transaction_normal`, contributed 91.585454708%, 90.959727575%,
91.708279337% and 90.873770045% of full instrumented indexing elapsed in pairs
1–4, respectively. The protocol is complete and the stratum threshold is met,
but the screen is **inconclusive** because one ratio is outside range. No
results were pooled with either accepted legacy cohort.

The report's two new-file CRLF hashes do not match the corresponding LF Git
blob digests used by the conservative reuse gate. The narrow gate repair keeps
the protected-file closure and delta checks intact, and intentionally requires
one fresh complete hosted measurement after publication. Preserve this first
complete but inconclusive cohort separately; do not rewrite its hashes, retry a
pair, or use it as the replacement measurement. Canonical publication is held
at that stage pending the gate repair and a fresh cohort; the later cohort is
recorded separately below.

## Gate-repair head CI and second hosted cohort (2026-10-03)

The reviewed gate repair is source head
`1d4dc92c5a9aa4bd043daaf191581ef19937e611`, tree
`bf513104f50d87fe662f3f53e5085c8b9263ab2b`, based on `cf483d0...`. The PR
remains open and draft. GitHub REST returned 46 current-head check-runs and six
workflow runs for this exact SHA; every workflow run completed successfully.
The check-run and all-event workflow snapshots are retained as
`work/transaction-exit-raw/pr14-1d4dc92-check-runs-final-per-page-100.json` and
`work/transaction-exit-raw/pr14-1d4dc92-workflow-runs-final-all-events.json`.
The events included Core push and PR, Qt and Tauri package checks, the legacy
12-pair characterization, and the new Windows four-pair transaction-exit run.

Actual Windows Core logs were inspected rather than inferred from check icons.
The two push and two PR Python 3.11/3.13 jobs each ran 195 tests with zero
failures or errors: 194 passed and one host-capability test was skipped. Each
Core log recorded that public-artifact privacy passed. The only skip remained
`test_local_loss_recovery_checks_both_phases_and_stable_uuids`, because the host
denies renaming the generated root while a scan handle is open; portable
injected-loss coverage remains separate. Windows durations were 432.220 s
(push 3.11), 973.996 s (push 3.13), 509.817 s (PR 3.11), and 591.864 s (PR
3.13). The Windows Qt package log ran 195 Core tests in 462.999 s with the same
single capability skip, then 28 Qt tests in 13.496 s with no failures, errors,
or skips; the package built and frozen-thumbnail smoke passed. That package
workflow did not run the public-artifact privacy step. The Windows Tauri job
also completed its 2 Node and 4 Rust tests and packaging. The legacy
characterization completed all 12 pairs in its separate run; its timings were
not mixed with either exit cohort.

The new [Windows run 37148420816](https://github.com/isaaclepes/DefiantMaple/actions/runs/37148420816),
attempt 1, pull-request event; its `windows-series` job is `111277186186`
(19:36:33Z–20:44:10Z), with the four-pair
step succeeding from 19:36:47Z to 20:44:07Z. It used one Windows Server 2025
hosted job/session and CPython 3.13.15 for four sequential 2,048-file, page-size
256 pairs in BI/IB/IB/BI order. Each pair completed below the 3,000-second cap
(1,096.472, 996.711, 971.584, and 972.197 seconds). Cleanup reaped workers,
removed owned storage, and retained none; all report issues are empty. Recovery
and source/identity invariants passed, including 2,049 assets after resume.

Artifact 11284681263 has ZIP size 5,758 bytes and SHA-256
`31d38f8b026b26ccb7c7e42e0e44d9193cc3af55c74378005d4c983eb330be37`. Its
actual 106,366-byte CRLF JSON member has SHA-256
`1db84da5de41240ad6d572be8a7a8b17ce30e5cdae36ff8d65a5a6d30c2732a3`. It
parses identically to the 103,320-byte LF JSON reconstructed from the exact
emitted Windows log, SHA-256
`38653a2d770db33d4ebdc41617a53bc66beb02eb35a323988e439582678ba94d`; replacing
CRLF with LF makes the member byte-for-byte identical to that reconstruction.
The full 213,299-byte decoded Windows log SHA-256 is
`2be0f87daf033d41e3e56b9c3728629476f605c04cfcc479e599247a4598de3a`. ZIP,
member, log, and reconstruction are retained in `work/transaction-exit-raw/`.
The report passed the closed public-report validator, independent public
artifact privacy checker, finite-number scan, and independent checks of pair
order, identity, cleanup, recovery, and invariants.

The exact 103,320-byte LF report is now preserved at
[`windows-series-run-37148420816-attempt-1.json`](../transaction-exit-benchmark-results/2026-10-03/windows-series-run-37148420816-attempt-1.json).
It hashes to the same `38653a2d...ba94d` as the emitted-log reconstruction.
The report states Windows Server 2025 hosted (`win25-vs2026`, image
`20260925.250.1`), AMD64, CPython 3.13.15, SQLite 3.50.4, Pillow 12.3.0,
zlib-ng 1.3.1, and four logical CPUs. CPU model, RAM total, filesystem,
storage, power policy, and antivirus are unavailable/null. The current report
was rechecked after canonical copy with zero public-artifact privacy errors;
all numeric values are finite. The Oct 2 and Oct 3 previously accepted report
files were also rehashed in the current checkout and still match their frozen
values, respectively `980360da60a12d6f0437ca0d227e5bb65cc7103b53a01da49cbc87a1725fc9b2`
and `36da9c4706fa3b5e838ba7f57eeaa7c13a91c2b573865d9f33ddd9b5262c9e1e`.

The reported measured merge is `92a9fce9bcd4d53f8be630010e7986832c35324e`,
with tree `bf513104f50d87fe662f3f53e5085c8b9263ab2b` and ordered parents
`80887a2...` then `1d4dc92...`, confirmed through GitHub's commit API. All eight
reported code digests were checked. The six frozen pre-existing code hashes
match their source bytes; the new `source_scan_exit_probe.py` and
`source_scan_exit_series.py` hashes also match the exact CRLF working bytes
produced by Windows checkout (the local files are LF and these paths are not
pinned by `.gitattributes`). CPU model, RAM total, filesystem, storage, power
policy, and antivirus remain unavailable/null.

I independently recomputed the screen from the outer
`soak.timings_ns.indexing` duration. I/B indexing ratios for pairs 1–4 are
0.893890490212, 1.041558636391, 1.074297354952, and 1.016758438589, all within
the predeclared 0.80–1.25 interval. `transaction_normal` is the dominant
instrumented stratum in every I trial, comprising 90.734%, 91.322%, 90.426%,
and 90.486% of the full indexing interval. The report's `attributed` screen is
therefore independently reproduced.

This is a second, separately identified cohort after the concrete
cross-platform hash-comparison defect in the publication gate was repaired; it
does not replace, pool with, or alter the first cohort's inconclusive verdict.
The first cohort remains archived in `first-complete/` history. The v0.2 SDD
§19.4 requires retaining attempts and prohibits repeating an inconclusive
diagnostic merely to obtain a preferred verdict; its §21.3 says not to claim
NFR compliance until a reference profile is set, and §22.2 records the first
cohort as inconclusive while stating that the later gate-repair cohort was not
reviewed for that document snapshot. This CI diagnostic is separate evidence
and does not establish the SDD's 100,000-asset, desktop-resource, display, or
release targets. No further exit cohort is justified by the current report.
The detailed hash, log, runtime, source-digest, and acceptance record is
retained in the private wrapper
`work/transaction-exit-raw/pr14-1d4dc92-run37148420816-attempt1-acceptance.md`.
