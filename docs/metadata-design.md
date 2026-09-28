# Catalog metadata contract (introduced in v3)

This is the implemented backend/UI contract for Task 04, introduced in schema v3.
Schema v4 adds [manual collections](collections-design.md) while preserving
this metadata API and its records. All APIs below
take a catalog `Path` as their first argument.
Metadata operations use the current schema and never migrate implicitly.

## Library initialization and migration

`defiantmaple.catalog.initialize(path, *, create=True) -> dict`

- `create=True` keeps the existing initialization use: create a fresh v4 catalog
  or upgrade an authentic supported catalog. An empty unversioned catalog may
  be initialized only in this mode; a nonempty unknown catalog is refused.
- `create=False` is the existing-library open mode for the Qt launcher. It
  refuses missing and unversioned files and never creates them. It upgrades
  supported v1/v2/v3 catalogs before the gallery/model/workers are constructed.
- Return fields: `schema_version: 4`, `previous_version: int`, `created: bool`,
  `migrated: bool`, `backup_path: str | None`. `previous_version` is 0 for fresh
  initialization. `created` means the v4 schema was initialized fresh. A current
  v4 catalog returns `migrated=False`, `created=False`, `backup_path=None`.
- `CatalogMigrationError` subclasses `ValueError` and exposes
  `backup_path: str | None`. A verified original-version backup is retained if
  migration fails. Backup failure prevents every schema/data mutation.
- Inspect supported-version structure before mutation; a version marker alone
  is insufficient. Refuse unknown/future versions. Preserve every existing
  asset ID, path, hash, workflow state, provenance row, source and observation.
- The existing `init` CLI returns these same fields beside `database` in its
  local JSON output, including the verified backup path after an upgrade.

Migration sequencing: quiesce application workers/connections first. Reserve
the source write lock on a migration connection, copy through a separate
read-only source connection using SQLite's backup API, close and verify the
backup read-only, then apply all required v1/v2/v3-to-v4 steps in the reserved
transaction. `BEGIN IMMEDIATE` reserves a writer before validation/backup; a
competing writer cannot change the copied state. This follows SQLite
[transaction semantics](https://www.sqlite.org/lang_transaction.html) and its
[online backup API](https://www.sqlite.org/c3ref/backup_finish.html).
Do not use `executescript()` inside that transaction, change
journaling/synchronous settings, or back up through the writing connection.
Python documents the [backup operation](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)
and [explicit transaction control](https://docs.python.org/3/library/sqlite3.html#transaction-control-via-the-isolation-level-attribute);
individual schema statements preserve the reserved transaction, while
`executescript()` can commit it first under legacy transaction control.
Backup files stay beside the local catalog with unique private names and are
never overwritten. Paths and user records are private API results, not public
benchmark evidence. Backup/lock failure is an error, not permission to proceed.

Supported-schema validation checks the exact user-table set, column types,
null/default declarations using `table_xinfo` (refusing generated/hidden columns),
primary/unique keys (including the partial source
index predicate), foreign-key columns/actions, CHECK expressions and complete
trigger bodies. It ignores column order and SQLite-generated index/FK IDs.
The published legacy v1 table/column/key shape permits historical missing
constraints. Its upgrade renames the old assets/provenance tables, creates the
complete v2 schema, copies every row value unchanged and drops the old tables,
all in the reserved transaction. Constraint-invalid legacy rows abort the whole
upgrade. Authentic v2 catalogs produced by the previous ALTER-based migration
remain supported. Schema v3 metadata tables, aliases, hierarchy and assignments
are preserved while the two collection tables are added. No source/media or
provenance value is rewritten.

The backup is exclusively created with a unique filename (0600 where POSIX
permissions apply), copied with SQLite rather than filesystem byte copying,
closed, then reopened read-only. Original version, schema, integrity and foreign
keys are checked before the first migration DDL/data write. An incomplete or
unverified output is removed; a verified backup survives both success and a
later failure. Retry creates another unique backup and never overwrites the
first. A failure rolls back DDL, row changes and `user_version` together.

## Metadata API

Module: `defiantmaple.metadata`.

`ENTITY_TYPES = ("Character", "Artist", "Project", "Location", "Client", "Franchise")`

Tag record: `{"tag_id": str, "name": str, "parent_id": str | None,
"aliases": list[str]}`.

Entity record: `{"entity_id": str, "entity_type": str, "name": str,
"aliases": list[str]}`.

Selected-asset metadata: `{"asset_id": str, "tags": list[Tag],
"entities": list[Entity]}`. Lists have deterministic normalized-name/ID order;
entities sort by type, then normalized name/ID. Aliases sort by normalized key.
No media paths or workflow-state changes are part of these metadata records.

| Function after the catalog argument | Return |
| --- | --- |
| `create_tag(name, *, parent_id=None)` | Tag |
| `get_tag(tag_id)` / `rename_tag(tag_id, name)` | Tag |
| `list_tags()` | list[Tag] |
| `set_tag_parent(tag_id, parent_id)` | Tag; `None` clears parent |
| `add_tag_alias(tag_id, alias)` / `remove_tag_alias(tag_id, alias)` | Tag |
| `create_entity(entity_type, name)` | Entity |
| `get_entity(entity_id)` / `rename_entity(entity_id, name)` | Entity |
| `list_entities(*, entity_type=None)` | list[Entity] |
| `add_entity_alias(entity_id, alias)` / `remove_entity_alias(entity_id, alias)` | Entity |
| `assign_tag(asset_id, tag_id)` / `unassign_tag(asset_id, tag_id)` | selected-asset metadata |
| `assign_entity(asset_id, entity_id)` / `unassign_entity(asset_id, entity_id)` | selected-asset metadata |
| `get_asset_metadata(asset_id)` | selected-asset metadata |
| `find_tag(name)` / `find_entity(entity_type, name)` | canonical Tag/Entity or `None`; names and aliases resolve alike |

Invalid names/types, unknown IDs, namespace collisions and hierarchy cycles raise
`ValueError`. SQLite/I/O failures may raise `sqlite3.Error`/`OSError` as existing
catalog APIs do. Repeating an assignment or removal is idempotent for existing
records. Repeating the same normalized alias on the same record is idempotent;
aliases already naming another record are rejected. Taxonomy deletion and entity
type changes are not exposed.

## Identity, names and relationships

- Display names/aliases use Unicode NFC with whitespace collapsed and trimmed.
  Lookup keys use NFC of the display name's `casefold()`. Non-string, empty, NUL
  and non-whitespace control-character names are rejected. Accents are retained;
  no transliteration is applied. Normalization uses NFC rather than NFKC;
  Unicode casefold itself can still fold characters such as ligatures.
- Tag canonical names and aliases share one library-wide namespace. Entity
  canonical names and aliases share a namespace within each entity type. A
  canonical name cannot also be an alias, including on its own record. The same
  spelling may identify a Character and an Artist; UI lists retain typed IDs.
- Tags/entities receive stable IDs; renames preserve IDs and aliases and never
  silently add the previous name as an alias. Case-only display renames work.
- Tags have at most one parent. Reject self-parenting and descendant cycles.
  Hierarchy edits never assign ancestor tags or change any asset assignment.
- Assignments are many-to-many, keyed by the existing `assets.asset_id`, with
  unique `(asset_id, tag_id)` / `(asset_id, entity_id)` pairs. Existing IDs are
  preserved without imposing a new UUID-format check on legacy catalog rows.
  Same-hash assets remain separate; changed/missing media paths do not remove
  metadata. New writes validate referenced IDs and enable foreign keys.
- The Qt editor captures the selected UUID before dialogs and submits that UUID,
  not a later row index. Refresh assignments/details after committed edits.
  Metadata lists belong in the inspector; avoid joining them into grid pages.

The metadata API includes no source/sidecar writes, workflow reinterpretation, canonical-tag emission,
Character reference/recognition fields, taxonomy deletion, rules, collections,
query language or tag/entity-specific media processing are included.

## Validation and limits

The following Task 04 checks are historical schema-v3 implementation evidence,
before the collections increment. Current-v4 focused checks are recorded in
[Task 10](tasks/10-collections-core.md). These earlier local focused checks used
Python 3.14.7, SQLite 3.51.2 and pinned Pillow 12.3.0.
All fixtures were temporary fictional catalogs/media; no private paths, IDs or
records are recorded here.

| Check | Result |
| --- | --- |
| `python -W error::ResourceWarning -m unittest discover -s tests -p test_catalog_migration.py -v` | 12 passed; 0.170 s |
| `python -W error::ResourceWarning -m unittest discover -s tests -p test_metadata.py -v` | 11 passed; 0.151 s |
| Existing `test_core.py` / `test_sources.py`, same warning setting | 16 / 9 passed; 0.063 / 0.164 s |
| Independent integration acceptance | Core 106 and Qt 19 passed; no failures, errors or skips |
| `git diff --check` | Passed |

Migration tests cover empty/populated v1/v2, the canonical legacy v1 and old
ALTER-based v2 layout, original backup integrity/restoration, real backup failure,
failed verification, intermediate DDL/data rollback, retained/distinct retry
backups, name-collision refusal, a reserved rival writer and committed WAL rows.
Forged FK, partial-index, CHECK, unique-key and trigger declarations are refused.
The existing CLI migration output locates the readable original-version backup.

Metadata tests cover all six types and their scoped namespaces, canonical/alias
collisions in both directions, NFC/casefold/whitespace rules, ID-preserving rename,
alias resolution/removal, self/descendant cycles, concurrent collision and opposite
parent edits, idempotent many-to-many assignments, same-hash distinct assets,
path/missing-observation persistence, and unchanged source/sidecar bytes/mtimes
plus assets/provenance/source/observation rows.

Quiesce workers and application connections before initializing/migrating.
SQLite locks govern cooperating connections, not external filesystem replacement
or hostile modification of the catalog file. The normal connection lock timeout
is five seconds; backup/readback duration scales with catalog size and has no
separate wall-clock deadline. Current-v4 open authenticates declarations without
running a full data-integrity scan on each launch; backup and completed upgrades
receive full checks. Backup restoration is verified in tests but has no product
restore command/dialog. Readback verification and unchanged SQLite durability
settings do not constitute power-loss or hardware/filesystem fault certification.
Cross-platform CI is the integration owner's next gate; these backend timing
results are local Linux evidence, not measured Windows/macOS results.
