# Task 04: Add catalog tags, entities and assignments

Owner: unassigned. Status: ready, not started.

Dependency: Task 01 coverage audit is complete. Tasks 02 and 03 (scan profiling
and mounted-share evidence) may proceed in parallel; neither blocks this product
slice. Coordinate the catalog schema version with the orchestrator before
implementation so concurrent work does not conflict with another migration.

Read SDD §§6, 10–11, 13.1, 18 and 21; review `defiantmaple/catalog.py`, Qt
gallery/editor patterns and their tests. Implement one bounded local catalog/UI
increment for explicit user metadata:

- Add normalized tag, tag-alias, typed-entity, entity-alias and asset-assignment
  records. Assignment keys must reference stable `asset_id` UUIDs, never paths.
  Start with the SDD entity types Character, Artist, Project, Location, Client
  and Franchise. Support parent tags and aliases; defer tag groups, implied or
  mutually exclusive rules, plugins, recognition suggestions, batch rules,
  Character reference/recognition fields and canonical-tag emission. This narrow
  task scope takes precedence over the coverage audit's broader follow-up list.
- Add focused Qt controls to create/rename tags and entities, assign/unassign
  them on the selected asset, add/remove aliases on a chosen tag/entity, and
  choose/change/clear a tag's parent. Show persisted metadata and assignments
  after reopening the library. Keep the existing workflow-state control separate
  from artistic labels; taxonomy deletion and automatic label propagation are
  outside this slice.
- Persist catalog metadata only. Source media and sidecars remain read-only;
  existing thumbnail and cache behavior remains unchanged, and routine cache
  generation is allowed. Do not add tag/entity-specific media processing. Use
  generated fictional records and temporary catalogs in tests.
- Add a versioned migration with a SQLite-consistent pre-migration backup.
  Verify the backup opens and passes integrity checks before any schema/data
  mutation; preserve it if migration fails. Upgrade existing v1 and v2 catalogs
  to the coordinated new version atomically, including every intermediate step.
  Retain all existing asset UUIDs, paths, hashes, workflow states and provenance,
  and refuse unknown future schema versions. Do not infer a backup policy from a
  successful transaction alone.

## Implementation preflight

- `catalog.initialize()` currently supports only v1 to v2. Back up the original
  version once before the full upgrade, verify through raw read-only SQLite
  rather than a helper that would migrate the backup, and test restoration.
  Quiesce scan workers and catalog/model connections before upgrading. Use an
  explicit transaction/rollback discipline: do not assume `executescript()`
  preserves a transaction already opened by its caller or back up through a
  source connection with an active write transaction.
- `LibraryLauncher.open_library()` currently validates with `connect()` and
  rejects older catalogs. Initialize/migrate supported existing catalogs before
  constructing `GalleryWindow`, its model or workers; keep missing/unknown-file
  refusal intact. Fresh catalogs initialize directly to the current schema.
- Keep tag/entity IDs stable across renames and assignment keys tied to existing
  asset IDs. Capture the selected asset UUID before editor dialogs; selection
  changes or model resets must never redirect an edit to a different row. Define
  and test Unicode/case/whitespace normalization and canonical/alias collision
  namespaces. Aliases resolve directly to a canonical record; renames do not
  automatically retain the old name as an alias. Reject self/descendant parents;
  parent changes do not automatically assign ancestors to an asset.
- The Tauri comparison reader currently accepts only schema v2. Coordinate its
  supported versions and update its reader/tests when the schema advances,
  retaining existing comparison behavior and refusal of unknown future versions.
  This is catalog compatibility work only, not a Tauri metadata UI increment.

Acceptance criteria:

1. Migration tests cover fresh catalogs and empty/populated v1 and v2 catalogs,
   verify the original-version backup's integrity/restorability and preserved
   asset identity/provenance, and inject failure during the upgrade to prove all
   migration steps roll back and the backup remains usable. Qt opening tests
   exercise upgrade before gallery construction and future-version refusal.
2. Core tests cover normalized tag/entity creation, aliases, parent tags,
   uniqueness, assignment, idempotent repeated assignment, reassignment/removal,
   and lookup by stable asset UUID after the asset path changes.
3. Qt tests create/rename and assign/unassign a tag and each supported entity
   type, edit tag/entity aliases and tag parents, reopen the library and verify
   persistence, and cover selection changes without assigning to the wrong
   asset. Confirm selected source-file bytes and sidecars are unchanged.
4. Existing catalog, source, thumbnail and gallery tests pass. Tests use
   generated fictional records and temporary files only; no private media or
   mounted-share dependency is required.
5. Focused Tauri reader tests cover the advanced schema and existing supported
   versions plus unknown-future refusal. Its release benchmark CI opens the
   Python-generated catalog at the advanced version and passes. Do not treat a
   version-constant edit alone as compatibility evidence.

Own `defiantmaple/catalog.py`, the focused metadata module if needed,
`prototypes/qt/app.py`, relevant tests, and this task file. Also own necessary
catalog-reader compatibility and focused tests in
`prototypes/tauri/src-tauri/src/main.rs`; coordinate release CI validation with
the orchestrator. No Tauri product features are included. Keep changes limited
to the catalog/UI increment above. Do not implement collections, query-language
search, sidecars, file operations, recognition, or watcher behavior. No commits,
pushes, branch changes, external messages, or additional agents. Report exact
tests, migration/backup behavior, limitations, and files changed in this task's
results.
