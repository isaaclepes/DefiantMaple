# Bounded state and evidence index

Recorded **26 October 2026**. Source baseline:
`47effeeb5a5adf8b692023c49b67ee52a9025559`, the locally observed `origin/main`
merge of library-admission PR #24. This index describes that committed baseline;
it does not certify remote freshness, deployment, or the latest running task.
The local `main` branch is older, so its name alone must not select a base.

## Baseline and concurrent work

At this baseline the catalog uses schema 7. Qt/PySide6 is the selected desktop
client. The repository includes metadata, manual collections, ratings/favorites,
bulk curation, cached offline browsing, backup/recovery, library identity, and
cooperative admission. Each feature's design and bounded acceptance records
below define its actual guarantees and exclusions; this list is not full SDD
or release acceptance.

A separate scheduled-snapshots task was still active when inspected for this
index. Its local branch was observed at
`177b209658da4ec4a6b7bc000a231264f58c58ea`; this is an observation, not this
index's implementation baseline or an acceptance claim. Its completed local
checkpoint also retains unfinished qualification gates. No private receipt,
local path, or evolving task narrative is copied here. Reconcile a completed,
reviewed checkpoint and exact source before updating this baseline or deciding
what scheduled-snapshot work remains. Do not infer completion from an active
thread, a package build, or green CI.

## Reading order and evidence

| Purpose | Canonical entry / bounded record |
| --- | --- |
| Contributor commands and safety boundaries | [Root guidance](../AGENTS.md) |
| Forward requirements; implementation separate | [SDD v0.2](sdd-v0.2.md), especially §§21–22 |
| Desktop decision and hands-on behavior | [ADR 0001](adr-0001-desktop-stack.md), [Qt guide](../prototypes/qt/README.md) |
| Metadata and collections | [Metadata guide](metadata-guide.md), [collections guide](collections-guide.md) |
| Curation and cached browsing | [Bulk curation acceptance](bulk-curation-acceptance.md), [cached offline acceptance](cached-offline-acceptance.md) |
| Backup and recovery | [Recovery results](metadata-recovery-results.md) |
| Library identity | [Results](library-identity-results.md), [review](library-identity-review.md) |
| Cooperative library admission | [Design](library-admission-design.md), [acceptance](library-admission-acceptance.md), [results](library-admission-results.md), [review](library-admission-review.md) |
| Sanitized supporting evidence | [Evidence directories](evidence/) |
| Historical plans and experiments | [Task briefs](tasks/00-phase1-orchestration.md), [experiment policy](diagnostic-experiment-policy.md) |

Result ledgers retain earlier candidates, failures, and superseded findings.
Read each claim with its recorded source, manifest, platform, fixture, scope,
and review. Statements such as “current candidate” inside an older ledger are
relative to that ledger's checkpoint, not a live instruction. No audit history
has been deleted or promoted into contributor instructions.

## Next handoff gate

Before changing the state claim: identify the completed checkpoint, current
branch/HEAD and dirty files; reconcile accepted versus open rows; retain exact
source and runtime/output inventories; privacy-review any public derivative.
Record tests and CI independently from frozen/native acceptance, and retain
unrun or failed gates explicitly. This maintenance pass changes guidance, a
permission-sensitive test fixture, and a Qt workflow trigger only. It does not
qualify a new runtime or authorize deployment or publication.
