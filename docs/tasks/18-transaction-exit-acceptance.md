# Task 18: transaction-exit acceptance and CI audit

Owner: Luna. Baseline `80887a2196fea3c3c6568fc11e7d1b7b78054f91`.
Status: local acceptance recorded; hosted PR and measurement audit pending.

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
