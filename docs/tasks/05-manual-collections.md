# Task 05: Add user-managed manual collections

Owner: unassigned. Status: ready, not started.

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
  and passes integrity checks; retain it on failure. Coordinate schema version
  and backup behavior with Task 04 rather than assuming a parallel migration
  number.
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

Own the collection catalog implementation, `prototypes/qt/app.py`, focused
tests, and this task file. Avoid unrelated tag/entity edits: request any
correction through the orchestrator. Do not add saved-query collections or file
operations. No commits, pushes, branch changes, external messages, or additional
agents. Report exact tests, migration/backup behavior, limitations, and files
changed in this task's results.
