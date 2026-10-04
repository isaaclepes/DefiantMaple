# Completed diagnostic experiments and future opt-in

The accepted scan-characterization and transaction-exit cohorts are historical
evidence for their recorded source hashes, fixture, protocol and environment.
SDD v0.2 §§19.4/22.3 closes each finite experiment after its documented finding.
Changing the catalog for a product feature does not authorize another cohort
or extend the original performance conclusions to that new code.

The two diagnostic workflows now subscribe only to the `pull_request` **labeled**
activity, retaining their exact measured-file path filters. The gate job also
requires that the label added in that event is exactly its own opt-in label:

| Workflow | Label-addition event |
| --- | --- |
| Repeated scan characterization | `experiment:scan-characterization` |
| Windows transaction-exit attribution | `experiment:transaction-exit` |

An existing label, a normal open/reopen/synchronize event, or adding another
label cannot start a fresh measurement. GitHub's [activity filters](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
and [job conditions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idif)
provide this boundary. Ordinary Core, Qt and Tauri tests/packages remain active.
These diagnostic jobs are optional experiment evidence, not required product
merge checks. Do not configure a path/activity-filtered workflow as a required
merge check: [filtered workflows can leave checks pending](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore).

Before adding either label, record a concrete unresolved product decision,
hypothesis, exact reviewed PR head, protocol compatibility, bounded run budget,
fixture/platform/cache limitations and acceptance/stop rule. Review that record
independently. Immediately before adding the label, recheck the current PR head
against that reviewed record; a push in between requires another review of the
changed inputs. Adding the relevant label then opts into **one complete** cohort
at the label event's PR head and synthetic merge. The unchanged conservative publication gate treats a labeled
event as a measurement event; it cannot reuse a mixed or incomplete report.
Do not reuse historical hashes for changed code or combine attempts/platform
fragments. Repeating an experiment requires another explicit decision and a
full run, never failed-jobs-only aggregation. Removing/readding a label is a new
opt-in and must not be used as an automatic retry loop.

Archived report bytes and their protocol/code identities are preserved. The v5
product migration requires an explicit compatibility change in the two series
readers: they accept archived v4 descriptors while current producers/aggregates
require the exact live schema, and mixed-version pairs/cohorts remain invalid.
Protected-byte publication gates, scanner/workload and profiling/attribution
runtime are unchanged. These current reader changes have new code digests and
do not extend historical findings to the new code. Workflow changes are current
scheduling policy; historic workflow digests identify their original runs.
A future protocol must be rechecked against schema/runtime changes before
scheduling and use its own current measured-code hashes. No label is added and
no cohort is authorized by the ratings/favorites increment.
