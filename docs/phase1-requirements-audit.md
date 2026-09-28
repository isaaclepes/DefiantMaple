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
| Library creation/opening and local catalog (§§5–6; §22 Phase 1) | Partial | Qt launcher creates or opens a user-selected SQLite library; catalog supports UUID assets, paths, fingerprints, workflow state and provenance ([app.py](../prototypes/qt/app.py), [catalog.py](../defiantmaple/catalog.py), [test_gallery_workflow.py](../prototypes/qt/tests/test_gallery_workflow.py)). Migration v1→v2 is transactional, but backups, practical rollback and recovery remain open (NFR-005; [sdd-review.md](sdd-review.md)). Rich asset metadata, tags, entities, relationships, and library export are missing. |
| Indexing, stable identity, provenance and exact duplicates (§§6.1–6.2, 14) | Partial | One-shot indexing records UUIDs, SHA-256 and origin/path provenance; byte-identical files remain separate assets and can be grouped, without a merge or destructive action ([catalog.py](../defiantmaple/catalog.py), [test_core.py](../tests/test_core.py), [README.md](../README.md)). Ambiguous move/replacement reconciliation, perceptual duplicate families and relationship types are absent. ZIP member provenance is retained in preview only. |
| Multiple watched sources, independent controls and profiles (§7: FR-INBOX-001/002) | Partial | Multiple persistent sources, enabled/paused controls, rescans, recursive walking and deterministic overlap assignment exist ([sources.py](../defiantmaple/sources.py), [test_sources.py](../tests/test_sources.py)). Despite the SDD term “watched,” this is an explicit one-shot scanner: native/event-driven watching, include/exclude patterns, media filters, initial tags/metadata, project defaults, recognition settings and per-source pipelines are absent. |
| Existing-file policy and stable-file detection (§7: FR-INBOX-003/004) | Partial | Add-source requires Inbox, Reviewed, or Ignore Until Modified. The scanner waits for matching size/mtime observations across a quiet interval and verifies reads ([sources.py](../defiantmaple/sources.py), [test_sources.py](../tests/test_sources.py), [test_scan_cancellation.py](../tests/test_scan_cancellation.py)). This is a scan-time heuristic, not a watcher debounce or proof that a writer has finished. |
| Source health and workflow states (§7: FR-INBOX-005/006) | Partial | Catalog/UI represent all six workflow states; the UI supports state changes and filtering. Offline, permission-denied and error health are recorded, and unavailable roots do not delete catalog records ([app.py](../prototypes/qt/app.py), [test_gallery_workflow.py](../prototypes/qt/tests/test_gallery_workflow.py), [test_scan_resilience.py](../tests/test_scan_resilience.py)). `Watching` is reserved but not an operating state; no durable job journal, startup recovery, or watcher self-event suppression exists (FR-INBOX-007). |
| Metadata inspector (§22 Phase 1; §10) | Partial | The detail pane shows basic asset, source and provenance information; filename/path search plus state, media-type, source and duplicate filters exist ([app.py](../prototypes/qt/app.py), [test_gallery_workflow.py](../prototypes/qt/tests/test_gallery_workflow.py)). Editable rich metadata, ratings, artist/generation fields, EXIF/IPTC/XMP, sidecars and conflict policy are absent. Search is a path substring, not the SDD query language (§11). |
| Tags and entities (§10; §22 Phase 1) | Absent | No tag/entity catalog schema, editor, aliases/hierarchy, entity records, character references, assignment flow or tests were found. Embedding retrieval is a separate generated-fixture benchmark; it does not implement tags/entities or character truth (see [benchmark report](embedding-model-benchmark.md)). |
| Gallery browsing, search and review UX (§11; NFR-002) | Partial | Qt provides a page-cached, virtualized grid, adjustable thumbnails, detail pane, review-state keyboard shortcuts, basic filters/search and exact-duplicate view ([app.py](../prototypes/qt/app.py), [Qt workflow tests](../prototypes/qt/tests/test_gallery_workflow.py)). Search fields/boolean logic, saved searches, tag/entity browsers, ratings/favorites and richer sorting/grouping are absent. |
| Manual collections (§11; §22 Phase 1) | Absent | No manual collection model, membership controls or tests were found. Dynamic saved-search collections are also absent; saved queries belong to Phase 2 in §22. |
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
The source-scan report links a hosted CI run that passed on Linux, macOS and
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
it informs watcher design and does not block tags/entities. The next product
slice is [Task 04](tasks/04-tags-entities.md), followed by its dependent
[Task 05](tasks/05-manual-collections.md).

1. **Next product slice: tags, entities and editable metadata.** Define catalog tables and
   migration behavior first; add tag hierarchy/aliases/groups, structured entity
   records and asset assignments, then expose editing and confirmation in the
   inspector. Acceptance: migration preserves existing UUIDs, paths, hashes and
   provenance; CRUD/query tests cover aliases, hierarchy and entity assignment;
   Qt tests create/edit/reopen metadata without writing source media. Do not
   treat embedding results as assignments.
2. **Then add manual collections.** This is the dependent Task 05 slice and
   follows Task 04's catalog identity work. Add collection and ordered membership
   persistence plus create/remove/reorder UI. Acceptance: curated membership
   survives reopen and catalog refresh; duplicate adds, remove/re-add, and
   missing-asset handling have defined tests; source media remains unchanged.
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
