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
  mutually exclusive rules, plugins, recognition suggestions and batch rules.
- Add focused Qt controls to create/rename tags and entities, assign/unassign
  them on the selected asset, and show persisted assignments after reopening the
  library. Keep the existing workflow-state control separate from artistic
  labels.
- Persist catalog metadata only. Source media and sidecars remain read-only;
  existing thumbnail and cache behavior remains unchanged, and routine cache
  generation is allowed. Do not add tag/entity-specific media processing. Use
  generated fictional records and temporary catalogs in tests.
- Add a versioned migration with a SQLite-consistent pre-migration backup.
  Verify the backup opens and passes integrity checks before migration; preserve
  it if migration fails. Apply schema/data changes transactionally, retain all
  existing asset UUIDs, paths, hashes, workflow states and provenance, and refuse
  unknown future schema versions. Do not infer a backup policy from a successful
  transaction alone.

Acceptance criteria:

1. Migration tests cover an empty catalog and a populated prior-version catalog,
   verify backup integrity/restorability, verify preserved asset identity and
   provenance, and inject a migration failure to prove the source database is
   unchanged and the backup remains usable.
2. Core tests cover normalized tag/entity creation, aliases, parent tags,
   uniqueness, assignment, idempotent repeated assignment, reassignment/removal,
   and lookup by stable asset UUID after the asset path changes.
3. Qt tests create and assign a tag and each supported entity type, reopen the
   library and verify the assignments, and confirm the selected source-file
   bytes and sidecars are unchanged.
4. Existing catalog, source, thumbnail and gallery tests pass. Tests use
   generated fictional records and temporary files only; no private media or
   mounted-share dependency is required.

Own `defiantmaple/catalog.py`, the focused metadata module if needed,
`prototypes/qt/app.py`, relevant tests, and this task file. Keep changes limited
to the catalog/UI increment above. Do not implement collections, query-language
search, sidecars, file operations, recognition, or watcher behavior. No commits,
pushes, branch changes, external messages, or additional agents. Report exact
tests, migration/backup behavior, limitations, and files changed in this task's
results.
