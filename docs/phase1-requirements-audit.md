# Phase 1 requirements audit

Audit basis: Artist Gallery and Asset Management Platform SDD 0.1 (24 September
2026), especially §§6–7, 10–11, 14, 18–22; current repository code, tests,
README and [SDD implementation review](sdd-review.md). Status describes
observable repository evidence, not a claim that the complete product scope is
finished. **Implemented** means the scoped behavior exists with repository
evidence; **partial** means only part of the requirement is present; **absent**
means no implementation was found.

## Coverage

| Phase 1 capability / SDD requirement | Status | Evidence and boundary |
| --- | --- | --- |
| Cross-platform UI/runtime selection (§22 Phase 0; NFR-001) | Implemented for the Phase 1 prototype | Qt/PySide6 is selected in [ADR 0001](adr-0001-desktop-stack.md). Release-artifact UI measurements and CI evidence cover hosted Windows, macOS, and Linux in [benchmark results](../benchmarks/results/2026-09-25/README.md). This establishes prototype evidence, not supported OS-version or signed-release commitments. |
| Library creation/opening and local catalog (§§5–6; §22 Phase 1) | Partial | Qt creates/opens a local catalog with UUID assets, paths, fingerprints, workflow state and provenance. Supported v1/v2/v3 upgrades to v4 verify an original-version SQLite backup before schema/data writes and roll back the full upgrade on failure; opening paths migrate before constructing the gallery ([catalog.py](../defiantmaple/catalog.py), [collection design](collections-design.md), [migration tests](../tests/test_catalog_migration.py)). Tags, entities and manual collections are present; richer metadata, relationships, library export, automatic restore and general crash recovery remain open. |
| Indexing, stable identity, provenance and exact duplicates (§§6.1–6.2, 14) | Partial | One-shot indexing records UUIDs, SHA-256 and origin/path provenance; byte-identical files remain separate assets and can be grouped, without a merge or destructive action ([catalog.py](../defiantmaple/catalog.py), [test_core.py](../tests/test_core.py), [README.md](../README.md)). Ambiguous move/replacement reconciliation, perceptual duplicate families and relationship types are absent. ZIP member provenance is retained in preview only. |
| Multiple watched sources, independent controls and profiles (§7: FR-INBOX-001/002) | Partial | Multiple persistent sources, enabled/paused controls, rescans, recursive walking and deterministic overlap assignment exist ([sources.py](../defiantmaple/sources.py), [test_sources.py](../tests/test_sources.py)). Despite the SDD term “watched,” this is an explicit one-shot scanner: native/event-driven watching, include/exclude patterns, media filters, initial tags/metadata, project defaults, recognition settings and per-source pipelines are absent. |
| Existing-file policy and stable-file detection (§7: FR-INBOX-003/004) | Partial | Add-source requires Inbox, Reviewed, or Ignore Until Modified. The scanner waits for matching size/mtime observations across a quiet interval and verifies reads ([sources.py](../defiantmaple/sources.py), [test_sources.py](../tests/test_sources.py), [test_scan_cancellation.py](../tests/test_scan_cancellation.py)). This is a scan-time heuristic, not a watcher debounce or proof that a writer has finished. |
| Source health and workflow states (§7: FR-INBOX-005/006) | Partial | Catalog/UI represent all six workflow states; the UI supports state changes and filtering. Offline, permission-denied and error health are recorded, and unavailable roots do not delete catalog records ([app.py](../prototypes/qt/app.py), [test_gallery_workflow.py](../prototypes/qt/tests/test_gallery_workflow.py), [test_scan_resilience.py](../tests/test_scan_resilience.py)). `Watching` is reserved but not an operating state; no durable job journal, startup recovery, or watcher self-event suppression exists (FR-INBOX-007). |
| Metadata inspector (§22 Phase 1; §10) | Partial | The detail pane shows asset, source, provenance and persisted tag/entity assignments. Qt provides a metadata manager for explicit taxonomy edits and captured-UUID assignments ([app.py](../prototypes/qt/app.py), [Qt metadata tests](../prototypes/qt/tests/test_metadata_ui.py)). Ratings, generation fields, EXIF/IPTC/XMP, sidecars and conflict policy remain absent. Search is a path substring, not the SDD query language (§11). |
| Tags and entities (§10; §22 Phase 1) | Partial | Introduced in schema v3 and preserved in v4, the Qt editor and catalog support normalized tags, aliases, acyclic parent tags, Character/Artist/Project/Location/Client/Franchise entities and explicit stable-UUID assignments ([metadata API](../defiantmaple/metadata.py), [metadata guide](metadata-guide.md), [Task 04](tasks/04-tags-entities.md)). Tag groups, rules, taxonomy deletion and richer Character reference/recognition fields are deferred. Embedding retrieval remains a separate benchmark and never supplies automatic assignments or character truth. |
| Gallery browsing, search and review UX (§11; NFR-002) | Partial | Qt provides a page-cached, virtualized grid, adjustable thumbnails, detail pane, review-state keyboard shortcuts, basic filters/search and exact-duplicate view ([app.py](../prototypes/qt/app.py), [Qt workflow tests](../prototypes/qt/tests/test_gallery_workflow.py)). Search fields/boolean logic, saved searches, tag/entity browsers, ratings/favorites and richer sorting/grouping are absent. |
| Manual collections (§11; §22 Phase 1) | Implemented, scoped | Schema v4 stores stable collection IDs and ordered asset UUID memberships. Qt supports create/rename/delete, adding/removing the selected asset, paged collection browsing and adjacent moves with captured-neighbor validation ([collection API](../defiantmaple/collections.py), [guide](collections-guide.md), [API tests](../tests/test_collections.py), [Qt tests](../prototypes/qt/tests/test_collections_ui.py)). Unavailable source files retain membership; deleting a collection leaves its assets and metadata intact. Dynamic saved-search collections, nested collections and bulk membership editing remain absent; saved queries belong to Phase 2 in §22. |
| Exact duplicate groups (§14; §22 Phase 1) | Implemented, scoped | Exact SHA-256 groups and a UI filter are present; same-byte files remain distinct and are not merged ([catalog.py](../defiantmaple/catalog.py), [test_gallery_workflow.py](../prototypes/qt/tests/test_gallery_workflow.py)). Perceptual/embedding similarity and keep/skip/link/replace decisions are not implemented. |
| Background work, cancellation and item isolation (NFR-003/007) | Partial | Scans and thumbnail decoding run off the UI thread; scan cancellation takes effect at operation boundaries, and corrupt/oversized images are isolated ([app.py](../prototypes/qt/app.py), [thumbnail.py](../defiantmaple/thumbnail.py), [test_thumbnails.py](../tests/test_thumbnails.py), [test_scan_cancellation.py](../tests/test_scan_cancellation.py)). A single-file hash/decode call is not interruptible; configurable worker limits and gallery-wide bounded scheduling are incomplete. ZIP inspection is a separate CLI preview, not a background gallery job. |
| Fast startup from cached index (NFR-004) | Partial | Opening a library uses its existing SQLite catalog without an automatic full scan; source scanning is user-started ([prototypes/qt/README.md](../prototypes/qt/README.md)). Startup/reconciliation latency and crash-recovery behavior have not been measured or implemented as a durable background reconciliation job. |
| Local-first behavior (NFR-006) | Implemented for current flows | Catalog, scan, thumbnail and prototype retrieval data are local; optional model inference is explicit and provenance-bearing, while the app offers no recognition action. The prototype does not require network access for gallery use ([prototypes/qt/README.md](../prototypes/qt/README.md)). |
| 100k gallery browsing and actual media indexing performance (NFR-002/003; §§19, 21.3) | Partial; evidence scopes differ | The Qt/Tauri comparison uses a generated **100,000-row SQLite catalog** and measures virtual-grid interactions, with thumbnail loading disabled ([benchmark result README](../benchmarks/results/2026-09-25/README.md), [ADR 0001](adr-0001-desktop-stack.md)). It is evidence for catalog browsing responsiveness, not cold media hashing/indexing, thumbnail generation, or 100k source-tree processing. Source profiling has generated 2,048-file hosted CI runs and a local 8,192-file run; Windows was substantially slower, with cause unresolved ([source-scan resilience report](source-scan-resilience.md)). NFR-002's “typical desktop” and latency/memory budgets remain undefined. |
| Simulated source loss versus real network shares (FR-INBOX-005; §§20–21.2) | Partial | Tests and the resilience report inject missing roots/directories and network-style errors; the hosted OS matrix passed for generated fixtures. These simulate loss and recovery; no mounted SMB/NFS disconnect/reconnect was demonstrated. Real scratch-share testing remains an external validation gate ([source-scan resilience report](source-scan-resilience.md)). |
| Phase boundary: safe file mutations and archive extraction (§§8–9, 16, 22) | Absent by design | ZIP inspection is read-only. No extraction, organization, rename, move, or delete API is exposed. Phase 2 must first add planned mutations, validation, journal, undo and interruption recovery (§16); only then may Phase 3 add staged archive commit and rollback (SEC-ARC-005). Keep this ordering. |

## Evidence and uncertainty

Repository test coverage includes catalog/archive core behavior, source policies
and health, scan cancellation/resilience, thumbnails, the Qt workflow, private
evaluation handling, and generated embedding retrieval. The audit inspected
these tests and the checked-in evidence reports; it did not rerun the test suite.
The metadata and collection milestones add generated-fixture migration
preservation, backup/rollback, explicit Qt editing and persisted ordering checks;
their task results record current validation separately from this original
audit ([collection acceptance](tasks/12-collections-validation.md),
[independent review](tasks/13-collections-review.md)). The source-scan report links a hosted CI run that passed on Linux, macOS and
Windows for its generated fixture. That is not evidence of real share behavior.

Embedding scores come from 18 queries over six programmatically drawn fictional
identities with generated transformations. Both models ranked all fixture
queries first, but this smoke test has a severe gap from varied artist references
and lookalikes. It cannot establish character identity, quality on real
references, calibrated confidence, or permission to auto-tag. Vectors preserve
model/version and input provenance and remain outside the asset catalog.

The desktop benchmark and source scan answer different performance questions.
Do not cite the 100k-row grid run as a media-indexing benchmark. Do not cite
simulated Offline recovery as SMB/NFS validation. Hosted-runner results are
evidence samples, not hardware budgets or distribution support commitments.

## Ordered follow-up slices

The profiling work in [Task 02](tasks/02-scan-profiling.md) and generated
scratch-share harness/runbook in [Task 03](tasks/03-mounted-share-validation.md)
are current evidence tasks that proceed in parallel with product work. A real
mounted-share run is a later manual gate when a dedicated share is available;
it informs watcher design and does not block tags/entities or collections.
The bounded [Task 04](tasks/04-tags-entities.md) is integrated; its dependent
[Task 05](tasks/05-manual-collections.md) records the manual collection slice,
reviewed and merged in [PR #12](https://github.com/isaaclepes/DefiantMaple/pull/12).
The next [Task 14](tasks/14-scan-characterization.md) closes the specific repeated,
comparable 2,048-file profiling gap with balanced paired hosted-pool samples;
[Tasks 15](tasks/15-characterization-acceptance.md) and
[16](tasks/16-characterization-review.md) own its acceptance and integrity gates.
This experiment keeps larger-scale cold media and reference-hardware budgets
open; it does not change production scanner/durability or establish real shares.

1. **Integrated product slice: tags, entities and explicit assignments.** Task 04
   added aliases, parent tags, six typed entity categories and Qt editing, with
   verified backup and atomic migration. Its focused execution/validation briefs
   define acceptance. Tag groups/rules, rich entity/reference fields and taxonomy
   deletion are deferred; this does not complete every §10 requirement. Metadata
   edits do not write source media or reinterpret embedding results as labels.
2. **Manual collection slice: Task 05.** This follows Task 04's catalog identity
   work and adds collection and ordered membership persistence plus Qt controls.
   Its acceptance record covers reopen and catalog refresh, duplicate adds,
   remove/re-add, stale adjacent moves, unavailable assets and unchanged source
   media and metadata. Validation and independent review are recorded in
   Tasks 12 and 13.
   Query-language search and saved-search collections are separate follow-up
   scope; saved queries are explicitly Phase 2 in §22.

3. **Run performance characterization in parallel with product slices.** Keep separate budgets
   for 100k-row browsing and 10k/100k/500k generated media indexing per §21.3.
   Add reference-hardware, cold/warm, memory, thumbnail and concurrent-work
   measurements; profile the Windows scan phases before optimizing. Acceptance:
   publish reproducible environment and raw aggregate metrics with stated
   budgets; report browse latency and indexing throughput separately, and never
   infer an unexplained bottleneck from the current totals.
4. **Complete mounted-share evidence in parallel; gate only watcher/profile design on it.** When a
   dedicated generated-file SMB/NFS share is available, run the explicit
   scratch-only protocol from Task 03 across target OSes. Then specify
   include/exclude and media-type
   profile behavior, native watcher backends, pause/rescan semantics, self-event
   suppression and periodic reconciliation. Acceptance: disconnect during
   enumeration and indexing; reconnect and complete a healthy scan; compare
   UUIDs, health and source bytes; verify inaccessible data is retained. The
   evidence task does not block tags/entities or collections. Watcher rollout
   remains gated on real-share evidence and Windows characterization.
5. **Add Phase 2 mutation journal and recovery before archive commits.** Design
   immutable plans, precondition checks, per-item journal boundaries, crash
   recovery, undo validation, and audit records. Acceptance: fault injection at
   each commit boundary yields a deterministic resume/rollback/reconcile result
   with no untracked partial mutation. Only after this gate, start Phase 3 staged
   archive extraction with path/decompression limits, validation and rollback;
   preview alone never authorizes commit.

No unmeasured result or real-share test is implied by these follow-up criteria.
