# Task 05: Add user-managed manual collections

Owner: orchestrator, Sol catalog/Qt and Luna acceptance. Status: implemented,
independently reviewed and accepted locally; current-head hosted acceptance is
recorded in the publication PR before it becomes ready for review.
Baseline main: `5d67640`; branch `codex/phase1-collections`. PRs 10 and 11 are
reviewed and merged; each final PR head passed all 30 hosted checks. The merged
baseline equals the independently tested 114-Core / 19-Qt metadata tree.

Execution briefs: [catalog/migrations](10-collections-core.md),
[Qt/reader](11-collections-ui.md), [acceptance](12-collections-validation.md)
and [independent review](13-collections-review.md). Schema v4 is coordinated
for this bounded milestone; agents have separate file ownership.

Dependency: Task 04 tags/entities and durable asset UUID assignments must be
reviewed and integrated into the shared branch before this task starts. This task
may use the stable catalog identity model from Task 04; it must not duplicate or
redefine its tag/entity schema. Scan profiling and mounted-share validation are
independent and do not block manual collections.

Read SDD §§6, 11, 18 and 21; review the catalog migration and Qt workflow
delivered by Task 04. Add a bounded user-curated collection increment:

- Store manual collections with stable collection IDs and member references to
  asset UUIDs. Persist member ordering so a curated sequence survives refresh and
  library reopen. Define and test what happens when a referenced catalog asset
  is missing; do not substitute a path or hash identity.
- Add Qt controls to create, rename and delete a collection; add/remove the
  selected asset; choose a collection and browse its members. Collection
  membership must not alter workflow state, tags, entities or source files.
- Keep this increment manual. Defer saved searches/dynamic collections, query
  language, nested collections, cross-library membership, bulk file operations
  and export/import.
- Source media and sidecars remain read-only; existing thumbnail and cache
  behavior remains unchanged, and routine cache generation is allowed.
- Add a versioned, transactional, backup-aware migration following the
  repository's established policy. Verify the pre-migration backup is readable
  and passes integrity checks before any schema/data mutation; retain it on
  failure. Preserve Task 04's atomic supported-version upgrade paths and Qt
  open-time migration before gallery construction. Coordinate schema version
  and backup behavior with Task 04 rather than assuming a parallel migration
  number; quiesce existing workers/connections during upgrade.
- When the catalog version advances, coordinate/update the Tauri benchmark
  reader's supported versions and focused tests so the Python-generated catalog
  remains usable by its release benchmark. Preserve existing comparison behavior
  and unknown-future refusal; do not add Tauri collection or other product UI.
- Use generated fictional catalog rows and temporary local databases only.
  Do not alter source media or sidecars.

Acceptance criteria:

1. Migration tests cover empty and populated prior-version catalogs, preserve
   Task 04 tag/entity data and all existing asset UUIDs/provenance, validate the
   backup, and prove an injected migration failure leaves the original database
   usable.
2. Core tests cover create/rename/delete, ordered membership, duplicate-add
   behavior, remove/re-add behavior, persistence after reconnect, and explicit
   missing-asset handling.
3. Qt tests create a collection, add and remove assets, reorder its members,
   switch views and reopen the library; verify collection membership is intact
   while source-file bytes and sidecars remain unchanged.
4. Existing catalog and gallery tests plus Task 04 tests pass. No mount, network
   share, private artwork, or real media library is needed.
5. Focused Tauri reader tests cover the advanced catalog version, retained
   supported versions and unknown-future refusal. Tauri release benchmark CI
   successfully opens the Python-generated catalog at the advanced version.

Own the collection catalog implementation, `prototypes/qt/app.py`, focused
tests, and this task file. Also own necessary catalog-reader compatibility and
focused tests in `prototypes/tauri/src-tauri/src/main.rs`; coordinate release CI
validation with the orchestrator. Tauri product features remain out of scope.
Avoid unrelated tag/entity edits: request any
correction through the orchestrator. Do not add saved-query collections or file
operations. No commits, pushes, branch changes, external messages, or additional
agents. Report exact tests, migration/backup behavior, limitations, and files
changed in this task's results.

## Results (2026-09-28)

Schema v4 stores collection UUIDs and unique ordered asset UUID memberships.
Names use a separate normalized namespace. Duplicate adds retain position,
remove/re-add appends, and full reorder requires an exact current permutation.
Adjacent moves reserve the writer and verify the captured directional neighbor.
Unknown IDs and stale captures refuse atomically. Offline/missing source records
retain membership; allowed catalog-asset deletion cascades membership, while
existing provenance/source foreign keys can still prohibit deletion. No new
asset-deletion or media-operation API exists.

Qt adds lifecycle controls, selected-asset membership editing and paged collection
browsing. Filtering preserves counts/order and disables reordering until all
filters are clear. Captured UUIDs survive nested dialogs. Independent review
reproduced and corrected a race between selection-rank lookup and lazy page
loading: a concurrent removal now refreshes count/cache and clears selection
instead of raising or selecting another UUID. A deterministic two-case regression
and an independent reproduction verify the repair.

Supported v1/v2/v3 upgrades authenticate their accepted declarations, reserve the
writer and verify one original-version backup before any migration statement.
All steps through v4 share one transaction. Tests preserve asset/source/provenance
rows and deep v3 aliases, parents and assignments; failure after v4 DDL and data
writes restores the original state and retains its verified backup. The
[design](../collections-design.md) and [guide](../collections-guide.md) define
the API, ordering, missing-ID and migration boundaries.

Independent local acceptance passed **133 Core** and **28 Qt** tests with
`ResourceWarning` treated as an error, no failures/errors/skips, plus privacy and
whitespace checks ([Task 12](12-collections-validation.md)). Independent Sol
review verified migration failure/backup/writer behavior across six DELETE/WAL
and v1/v2/v3 cases, concurrency regressions and the selection-race repair
([Task 13](13-collections-review.md)). A fictional 1280x800 offscreen layout was
inspected; narrower layouts are unverified.

Tauri accepts retained v2/v3 and current v4 without adding collection UI. Its
focused reader matrix retains missing/future refusal. Cargo is unavailable
locally; hosted Rust and unsigned-release checks on Linux/macOS/Windows remain
the publication gate. The actual Python-generated 100k benchmark catalog now
reports its read-back `catalog_schema_version`, separately from fixture/metrics
format versions. The publication PR body records final exact-head CI outcomes.

Saved/dynamic queries, nested/cross-library collections, bulk membership editing,
export/import and file mutations are deferred. No large-collection throughput,
real network-share behavior, power-loss durability or signed distribution claim
is established by this increment.
