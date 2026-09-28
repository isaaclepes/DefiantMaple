# Task 09: Independent metadata data-integrity review

Owner: Sol (`metadata_review`). Status: review complete; final acceptance owned by Luna.

Read Task 04, Tasks 06/07 and docs/metadata-design.md. Code review is read-only;
this task file is the only writable review record. Use the metadata checkout and
report concrete findings to root before assuming another owner will act on them.

Review backup/lock sequencing, source version/schema validation after lock,
closed-backup verification, whole v1/v2 upgrade rollback, retained original
backup, and no durability changes. Verify uncertain SQLite/Python semantics
against primary documentation and focused temporary fictional-catalog repros.
Review namespace/alias/parent constraints, foreign keys, stable UUID assignment,
Qt selected-target capture and refresh, open-time quiescence/refusal, and Tauri
v2/v3 compatibility. Do not treat a capability skip as coverage for a real mount.

Preserve private data and original media. No code edits, commits, pushes, branch
changes, PR mutations, external messages, extra agents, redundant full suites or
expensive benchmarks. Record exact evidence, fixes requiring owner action, and
limits. Stop promptly when root relays a user pause.

## Review results

Final implementation review is complete. No private catalog, media, mount, or sidecar was
read or changed. All reproductions below use new temporary fictional catalogs.

### Independent sequencing experiment

On Linux, Python 3.14.7 / SQLite 3.51.2, exercised both DELETE and WAL journal
modes independently of the implementation: reserve `BEGIN IMMEDIATE`; back up
through a separate `mode=ro` source connection; close the destination and source;
verify the closed backup read-only for original user_version, integrity and rows;
attempt a competing write; then execute ALTER TABLE, CREATE TABLE and user_version
changes and roll back. Both modes completed backup, rejected the competing
writer, retained the original backup contents, and rolled back all DDL/version
changes. This establishes runtime sequencing behavior; it is not a substitute
for implementation migration/rollback tests.

Primary references:

- [SQLite transactions](https://sqlite.org/lang_transaction.html): IMMEDIATE
  reserves the single writer while readers can continue.
- [SQLite backup API](https://www.sqlite.org/c3ref/backup_finish.html): the source
  handle must not be writing during backup; source/destination must differ.
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html): executescript
  implicitly commits a pending legacy transaction before executing its script.

### Findings and verified resolutions

1. **Resolved and verified:** Qt `LibraryLauncher._quiesce_gallery` ignored `QWidget.close()` returning
   false and cleared the gallery reference before open-time initialization.
   An AST-isolated reproduction of the saved method with a refusing close
   retained active workers while discarding the gallery reference. Abort opening
   on refusal and keep the reference. The owner fixed both open and create paths;
   the focused launcher refusal regression passed (1 test). A separate real
   offscreen QWidget with an ignored closeEvent preserved its visible gallery
   and prevented both initialization and new-gallery construction. Normal
   Gallery close waits for scan/thumbnail workers and closes the model.
   [Qt close contract](https://doc.qt.io/qt-6/qwidget.html#close).
2. **Resolved and verified:** catalog schema authentication did not verify foreign-key declarations. A
   new fictional v2 catalog built from SCHEMA_V2 with only the assets/source FK
   removed and an orphan source ID was accepted and upgraded to v3. The resulting
   foreign_key_check was empty because the absent constraint is not checked.
   The fixed validator checks foreign-key groups, uniqueness and partial-index
   predicates, CHECKs, default/not-null declarations, and actual trigger bodies.
   Repeating the original missing-FK reproduction now refuses before backup;
   the original file bytes remain unchanged. Accepted legacy v1 shapes are
   rebuilt to canonical constraints within the same reserved transaction.
3. **Resolved and verified:** a scan result queued during Gallery.closeEvent's thread wait
   was delivered after AssetModel.close. A real offscreen QThread reproduction
   emitted resultReady while closing a new empty fictional catalog; after the
   thread stopped, processEvents delivered _scan_result and raised
   ProgrammingError("Cannot operate on a closed database."). No corruption was
   observed. The owner added shutdown guards before waiting and ignores late
   progress/result/failure/finished callbacks. The actual-QThread regression
   passed (1 test); it confirms no closed-model access or callback exception.

### Implementation backup/rollback experiment

The saved v2-to-v3 implementation passed targeted DELETE and WAL reproductions.
Injected a failure after its complete metadata DDL and an asset UPDATE. Both
source catalogs retained v2, original asset rows and no tags table; both verified
original-version backups remained readable and passed integrity checks. Retrying
without injection upgraded successfully and created a distinct backup while
preserving the first one. No public/private user records were used.

Independently exercised the expanded v1 rebuild with both a minimal legacy shape
and a canonical legacy shape containing declared provenance FK and indexes,
each under DELETE and WAL. Each fixture had two same-hash assets with distinct
stable IDs, paths and workflow states plus provenance. Failure injected after
the complete v1 rebuild and an asset UPDATE restored the exact original
sqlite_master rows, catalog rows and user_version. The original v1 backup stayed
verified/readable. Successful retry preserved every old value and both asset
identities, removed the temporary legacy tables, and authenticated on v3 reopen.

Focused implementation regression checks run by this reviewer, all passing:

- `MetadataUITests.test_launcher_abort_on_close_refusal_before_open_or_create_initialization`
- `MetadataUITests.test_queued_scan_callbacks_after_close_do_not_access_closed_model`
- `MetadataUITests.test_direct_catalog_launch_migrates_before_construction_and_refuses_missing`
- `MigrationTests.test_empty_and_populated_legacy_upgrade_backup_and_restore`

The last check copies and reopens verified original backups for empty/populated
v1 and v2 catalogs and upgrades the restored copies. Direct --catalog startup
uses existing-file initialization before constructing Gallery, surfaces a real
backup location after upgrade, and refuses missing catalogs without creation.

### Reviewed paths without a current finding

The saved initializer reads user_version and validates structure after acquiring
its writer guard, uses a separate read-only backup source, closes and verifies
the backup before statement-by-statement migration, and retains a returned
verified backup on migration failure. It does not change journal/synchronous
settings. The Qt editor captures asset_id before its dialog and writes through
the metadata API using that captured ID. It refreshes the inspector through the
current selection without retargeting the edit. Rust count/page/workflow paths
accept v2/v3 and refuse other versions; release compatibility evidence remains
the orchestration/acceptance owner's responsibility.

Metadata API mutations reserve the writer before validation; reads keep record
and alias lookup in one snapshot. UNIQUE constraints and namespace triggers
reject collisions, the parent trigger rejects cycles, and FK-enabled assignment
writes validate stable IDs with idempotent ON CONFLICT handling. No additional
API finding from the saved body.

No unresolved data-integrity, API, or Qt review findings remain. A minor
ResourceWarning was observed because the reference-signature in-memory SQLite
connection used a transaction context manager without explicit close; cleanup
was completed by its owner with an explicit closing context, verified in the
saved source. The owner's warning-as-error metadata run passed; this cleanup
does not affect the migration conclusions.
Luna may proceed with final acceptance verification. No full suite,
release benchmark, Windows run or macOS run was performed by this reviewer.

## PR 11 authentication follow-up (2026-09-28)

Reviewed the assigned clean head `5242a0f70ff400158a869d181d8e293a2eae3484`
against base `0578dfb9854ccf7838299d4968ceef08e3c78968`. The edits below are
limited to catalog authentication, migration regressions and this review record;
publication and final CI remain root's responsibility.

### Generated-column finding: fixed and verified locally

`PRAGMA table_info` omitted both VIRTUAL and STORED generated columns. New
populated fictional v2 catalogs with an extra generated assets column passed
authentication, received a backup and migrated to v3 while retaining that extra
column. Equivalent current-v3 catalogs also passed authentication, and `SELECT
*` exposed the unexpected value. The new refusal regression additionally
demonstrated acceptance of augmented legacy-v1 catalogs before the fix.

`_table_signature` now reads `PRAGMA table_xinfo` and refuses nonzero hidden
flags. All supported v1/v2/v3 tables have ordinary columns. Existing declaration,
FK, uniqueness, partial predicate, CHECK and trigger comparisons are retained.
SQLite documents the omitted columns and the complete information in
[table_xinfo](https://www.sqlite.org/pragma.html#pragma_table_xinfo).

The regression covers populated v1/v2/v3 catalogs with each generated-column
form: six subcases failed before the fix and pass afterward. It verifies the
generated value and `table_info` omission, then checks refusal before calling
backup or either migration step, unchanged catalog bytes, original version/schema/
rows and no backup output. Canonical legacy-v1 and previous ALTER-based v2
compatibility, rollback and verified-backup regressions also pass.

### Unique-index collation finding: fixed and verified locally

The previous signature read unique key names with `index_info` and omitted their
collations. A new fictional v2 catalog changing only assets.current_path from
`UNIQUE` to `UNIQUE COLLATE NOCASE` passed validation and migrated. The equivalent
v3 catalog passed current-schema authentication. Two distinct temporary Linux
files named `Fictional.png` and `fictional.png`, containing identical fictional
PNG bytes, then returned the same asset ID from `index_file` and retained one row.
The altered column equality merged distinct file identities. Root authorized
the bounded authentication fix using key-column collations from
[index_xinfo](https://www.sqlite.org/pragma.html#pragma_index_xinfo).

Unique-index signatures now compare each key column's name, sort direction and
collation with the existing reference schema. Auxiliary index columns are
excluded; SQLite-generated index names and table-column order remain immaterial.
Populated v2/v3 fixtures changing the path collation, partial unique-index
collation, or partial unique-index direction all refuse before backup or
migration, preserve original catalog bytes/version/schema/rows, and create no
backup. These six subcases failed before the fix and pass afterward. The v1
validator retains its historical whole-path uniqueness policy; a focused
NOCASE-v1 upgrade/backup test confirms its rebuild produces canonical comparison
semantics, preserving the original row and allowing distinct case-sensitive
paths afterward.

### Focused verification and limits

Locally passed with the installed Python 3.14.7 / SQLite 3.51.2 runtime:

- `/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest tests.test_catalog_migration tests.test_metadata -v`: 26 tests.
- `QT_QPA_PLATFORM=offscreen /tmp/defiantmaple-metadata-verify-venv/bin/python -W error::ResourceWarning -m unittest` selecting five integration tests: captured-target/model-reset behavior, v1/v2 launcher migration and backup display, close refusal, queued scan callbacks after close, and direct catalog launch/refusal: 5 tests.

The remaining metadata API/Qt diff preserves reserved writes, snapshot reads,
stable ID assignment and captured editor targets. Previously resolved FK,
close-refusal and late scan-signal findings remain covered. No additional Qt/API
finding was reproduced. Tauri version compatibility changes were inspected;
release/Windows/macOS checks remain acceptance-owned. No full suite or release
benchmark was rerun, and no private catalog, artwork, sidecar or real mount was
read or changed.

Both authentication findings are resolved locally. No additional concrete
blocker remains from this review; final publication and exact-head CI are pending
with root and the acceptance owner.
