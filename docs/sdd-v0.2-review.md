# SDD v0.2 review against the Phase 1 attribution work

Review basis: the supplied 1,045-line
[*Artist Gallery and Asset Management Platform, Software Design Document v0.2*](sdd-v0.2.md)
(3 October 2026), read in full;
repository baseline `1d4dc92c5a9aa4bd043daaf191581ef19937e611`.
This is a requirements delta, not a fresh code/CI audit or approval to run
software on user media. The SDD's own document control calls the commit a
read-only evidence baseline and separates design targets from acceptance.

## Effect on the current PR

The draft PR's [Task 17 exit-only diagnostic](tasks/17-transaction-exit-probe.md)
still uses the contract in the
[accepted characterization](../benchmarks/source-scan-results/2026-10-02/README.md#one-bounded-next-attribution-experiment):
four BI/IB/IB/BI pairs with 2,048 files and page size 256.
SDD v0.2 [§19.4](sdd-v0.2.md#194-benchmark-governance),
[§21.3](sdd-v0.2.md#213-performance-acceptance) and
[§22.3](sdd-v0.2.md#223-recommended-sequencing) strengthen the stopping rule: authenticate the
separate gate-repair cohort, apply its original screen once,
preserve complete or incomplete raw evidence, and report either a supported
diagnostic span or `inconclusive`. Do not retry an inconclusive result for a
preferred verdict, combine attempts, or continue a chain of microbenchmarks
without a concrete product or engineering decision. The
[first complete cohort](transaction-exit-benchmark-history/2026-10-03/first-complete/README.md)
already remains separate and inconclusive. The fresh cohort was justified by
a protected publication-gate repair before v0.2 arrived; it is not a retry
chosen to turn that verdict into acceptance. The SDD's read-only §22.2
snapshot did not review that later cohort; its authenticated
[canonical report](transaction-exit-benchmark-results/2026-10-03/README.md)
now passes the original diagnostic screen and identifies an API span only.
That result does not change the finite stopping rule.

The eight-core/16 GiB/local-SSD reference profile and §19.2 interaction
numbers are **candidate design targets**. They are not adopted budgets, and
none replaces Task 17's diagnostic 0.80–1.25 perturbation screen or >50%
same-stratum rule. A GitHub-hosted Windows job is one runner session, not a
defined physical reference desktop; Python `tracemalloc` is not process-tree
RSS. The [experiment guide](transaction-exit-attribution.md) and
[first-cohort report](transaction-exit-benchmark-history/2026-10-03/first-complete/README.md)
already keep these scopes distinct. The 100k-row virtual-grid evidence does
not measure 100k media indexing or native preview I/O
([Phase 1 audit](phase1-requirements-audit.md),
[desktop benchmark](../benchmarks/results/2026-09-25/README.md)).
No production transaction, SQLite journal/PRAGMA, durability, batching or
locking change follows from an exit span. §19.3 and §16 require correctness,
concurrency and recovery evidence before such a design is proposed. §20.3's
fixed-SQLite-WAL runtime requirement applies if WAL is adopted; the SDD does
not direct a current journal-mode change.

## Material v0.2 delta for Phase 1

| SDD v0.2 boundary | Current checked-in evidence | Remaining implication |
| --- | --- | --- |
| §22 separates **1a explicit-scan gallery** from **1b watching/reconciliation**; network watching is claim-scoped (§§7, 21). | Sources scan on demand and preserve assets through synthetic Offline/recovery; [scan design](source-scanning-prototype.md), [Phase 1 audit](phase1-requirements-audit.md). | Finish truthful explicit-scan UX and local reliability independently. Native watcher claims need event/overflow evidence; remote watcher claims additionally need scratch-only real SMB/NFS loss/reconnect. Synthetic loss is not real-share acceptance. |
| §§6–7 make content revisions, replacement ambiguity, relinking and four independent state dimensions explicit. | UUID assets, supported rename identity and six review states exist; [source design](source-scanning-prototype.md), [Phase 1 audit](phase1-requirements-audit.md). | Preserve uncertain prior records; add revision invalidation, relink preflight and user reconciliation before claiming full 1a/1b identity behavior. Do not treat a matching path or hash as identity proof. |
| §§10–11, 15 and 22 move usable daily curation into 1a: ratings/favorites, bulk catalog edits, basic typed filters, correct supported-image display, full preview, external-open, offline cache and accessibility. | Qt grid/detail, PNG thumbnails, review shortcuts, tags/entities and ordered manual collections are present; [metadata guide](metadata-guide.md), [collection guide](collections-guide.md), [Qt prototype](../prototypes/qt/README.md). | These are partial, scoped flows. Color/orientation/alpha, unsupported formats, real keyboard/screen-reader behavior, editor integration and richer curation need separate implementation and native acceptance. |
| §§5, 16 and 22 require verified **user-facing** backup/restore/export and writer coordination in 1a. | Supported v1–v3 migrations verify an original-version backup before schema-v4 upgrade; [migration guide](metadata-guide.md), [Phase 1 audit](phase1-requirements-audit.md). | A migration backup is not restore, portable export, retention policy or rebuild. Add isolated restore drills and explicit omitted-media/unresolved-root reports; keep live catalogs on supported local storage. |
| §§18–21 add resource scheduling, full process-tree memory, named reference media/hardware, accessibility and clean-machine release gates. | Generated source characterization and Qt virtual-grid fixtures answer narrower questions; [characterization](../benchmarks/source-scan-results/2026-10-02/README.md), [Phase 1 audit](phase1-requirements-audit.md). | Adopt profile, corpus, budgets and stop rules before pass/fail claims. Measure actual thumbnail I/O and native display separately from hosted CI; report unknown CPU/RAM/cache and native-memory fields honestly. 500k indexing is extended scale evidence, not an automatic gate for every small 1a increment. |
| §21.1 requires requirement-to-evidence status and explicit deferrals; §22.2 preserves historical scoped acceptance. | [Phase 1 audit](phase1-requirements-audit.md) and [Task 00](tasks/00-phase1-orchestration.md) record earlier scoped status. | Add new v0.2 IDs, phase, owner, design, test/manual gate, evidence and Not Started/Partial/Implemented/Accepted state to the tracker. Do not retroactively mark expanded Must requirements accepted because earlier tests passed. |

The v0.1 archive/import, naming/rules, similarity, video and plugin scope is
retained, with clearer safety gates. Phase 2's journal/recovery boundary still
precedes source-writing organization and sidecars; Phase 3 extraction commits
depend on that boundary. Optional recognition remains advisory and cannot
mutate asset metadata from a score (§13). These later scopes do not expand
the current attribution PR.

## Ordered follow-up backlog after the bounded PR

1. **Close the current evidence task once.** The fresh Windows report has
   four complete pairs and passes its predeclared diagnostic screen; root and
   independent acceptance/review retain its code/merge/job provenance, raw
   bytes, variability and limits. Stop here. Keep both transaction-exit
   cohorts and the two accepted source-scan cohorts separate. A possible next
   experiment is conditional on the concrete Phase 1a budget/prioritization
   decision stated in the canonical report (§19.4).
2. **Update the requirement tracker for v0.2.** Map each new or clarified ID
   to 1a/1b/later phase, owner, design, evidence and status; retain reasons and
   replacement milestones for deferrals (§21.1). Review earlier scoped
   acceptance without rewriting its historical claim.
3. **Deliver daily 1a catalog curation and viewing.** Prioritize supported
   image orientation/color/alpha and full preview, ratings/favorites, captured-ID
   bulk edits with undo, useful basic filters, external-open, offline cached
   states, and keyboard/assistive-technology acceptance (§§10–11, 15, 22).
   Existing tags/entities and manual collections are foundations, not the
   whole 1a exit gate.
4. **Make catalog information recoverable.** Specify one-writer behavior,
   verified metadata backup/restore into a new location, portable export,
   rebuild of disposable caches, and explicit omission/conflict reports
   (§§5, 16, 22). Exercise failure paths before claiming release readiness.
5. **Resolve identity and source truth before watching.** Add content-revision
   invalidation, ambiguous replacement/relink UI, conservative missing-file
   rules and bounded job states. Then qualify local native watcher overflow and
   reconciliation for 1b. Qualify each remote share/backend separately with
   generated scratch media (§§6–7, 21–22).
6. **Adopt and test performance/release profiles only when product decisions
   need them.** Choose actual supported hardware/display/storage, representative
   media, cache preparation, job limits and candidate budgets; then measure
   native interaction, real preview I/O, full process-tree RSS and media
   throughput. Keep 10k/100k/500k indexing distinct from 100k catalog browsing
   (§§18–21). A new attribution microbenchmark is not the default next task.
7. **Keep source-writing work behind the later safety gate.** Phase 2 mutation
   journal, fault injection, safe undo/refusal and metadata authority precede
   rename/move/delete, sidecar writes and Phase 3 archive commits (§§9–10, 16,
   22). Optional retrieval, media expansion and plugins retain their separate
   phase and evidence gates.

This ordering is a review recommendation, not authorization to change media,
mounts, services, catalogs, production durability or the published benchmark.
