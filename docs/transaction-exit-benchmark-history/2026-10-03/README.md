# Initial transaction-exit attempt: no measurements

PR #14 source `ef71028c401a066e3d27d3b0015c98fe2b19cf6e` triggered
[Windows run 37139254911, attempt 1](https://github.com/isaaclepes/DefiantMaple/actions/runs/37139254911).
Job [111250132237](https://github.com/isaaclepes/DefiantMaple/actions/runs/37139254911/job/111250132237)
checked out synthetic merge `ba4cab4c4b3afa27acc8329c59895659237ebd0d`.
It failed identity authentication before any pair started. The retained
[bounded report](initial-run-37139254911-attempt-1.json) has no samples and
provides no timing or attribution evidence.

The workflow's depth-one checkout hid both merge parents from
`git show --format=%P`, although the merge commit's raw object contains them.
Both root and independent review reproduced this with a temporary two-parent
Git fixture. The measurement job now fetches depth two; the authentication
check remains unchanged. A fresh full four-pair attempt is required.

Separately, the initial Core/desktop unit tests failed a cleanup-deadline
fixture because its generated local trials and fake parent retained different
runner metadata. The narrow test repair clears the same six environment keys
for both sides; eight focused tests pass with GitHub-style metadata. The initial
failed check remains failed. Core matrix fail-fast automatically cancelled its
Windows jobs before unittest summaries; those cancelled jobs establish no test
result. The separate desktop-package Windows job
[111250089046](https://github.com/isaaclepes/DefiantMaple/actions/runs/37139254907/job/111250089046)
did run 193 Core tests: two failures and one filesystem-capability skip.
Besides the deadline fixture failure, its temporary Git gate fixture used
platform-dependent newline bytes and returned `changed_inputs` rather than a
valid reuse proof. The test now fixes its Git newline policy and writes exact
LF bytes; the gate's strict byte comparison remains unchanged. Corrected-head
Windows summaries remain required. No jobs were manually cancelled or rerun.

This JSON is reconstructed from the exact JSON emitted in the authenticated
decoded job log, not extracted from the artifact ZIP. Its retained bytes hash
to `0bfda5a4f8877f4ccc791afa54b7338beacdb30788a0c520a908003bf98977aa`.
The decoded log hashes to
`90b7972dd5d2e9c4944e2544865016d2f09f4bb60801a7b30644d12d5ba6bc87`.
GitHub's upload records artifact `11279836821`, 313 ZIP bytes and digest
`bd77a91715ef870417c992e4232a5484a22e568402ef515b0552cc9c77f677a9`.
The returned file reference could not be materialized locally (HTTP 403), so
ZIP member-byte equivalence is unverified. No samples from this attempt may
be pooled with a later result or either accepted source-scan cohort.
