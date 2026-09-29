# Manual collections and catalog v4

Schema v4 adds manual collections to the existing local catalog. Each collection
has a stable UUID; membership references the existing `assets.asset_id`. A path,
hash, workflow state or source-health change never substitutes another member.
Same-hash assets remain distinct. Collection operations open only the catalog
and preserve source media, sidecars, workflow state, tags, entities and provenance.
The [gallery guide](collections-guide.md) describes the controls.

## Schema and names

`collections` contains `collection_id TEXT NOT NULL PRIMARY KEY`, nonempty
display `name`, and nonempty unique `normalized_name`.

`collection_members` contains `collection_id`, `asset_id` and `position`. Its
primary key is `(collection_id,asset_id)`; `(collection_id,position)` is unique.
Positions are nonnegative SQLite integers, enforced with both `typeof` and a
range CHECK. Foreign keys cascade membership deletion when the collection or
an actually deleted catalog asset is removed. An asset lookup index supports
the asset-deletion cascade. Existing provenance/source-entry foreign keys can
still forbid asset deletion; no asset-deletion or file-operation API is added.

Collection names reuse the metadata normalization contract: display names use
Unicode NFC with whitespace trimmed/collapsed; lookup keys are NFC of the display
name's `casefold()`. Non-text, empty and non-whitespace control-character names
are refused. Accents remain significant and NFC does not apply NFKC width folding.
Collection names have an independent library-wide namespace, so a tag/entity can
use the same name. Create/rename reject normalized collisions. Rename preserves
the UUID and membership; it does not create aliases. Existing legacy asset IDs
remain supported without imposing new UUID-syntax checks on historical rows.

## API

Module: `defiantmaple.collections`. Every function takes a catalog `Path` first;
the following signatures show arguments after it. APIs require the current
schema and never migrate implicitly.

A Collection is exactly `{"collection_id": str, "name": str,
"member_count": int}`. Collection lists sort by normalized name then UUID.
Member lists contain ordered asset IDs, including assets with unavailable media.

| Function | Return and behavior |
| --- | --- |
| `create_collection(name)` | Collection with a new UUID |
| `get_collection(collection_id)` | Collection |
| `rename_collection(collection_id,name)` | Collection; same UUID |
| `list_collections()` | list[Collection] |
| `delete_collection(collection_id)` | `None`; removes only this collection and its memberships |
| `list_members(collection_id,*,limit=None,offset=0)` | ordered list[str] of asset IDs |
| `add_member(collection_id,asset_id)` | Collection; append if absent, leave existing position unchanged |
| `remove_member(collection_id,asset_id)` | Collection; absent membership is a no-op for existing IDs |
| `reorder_members(collection_id,asset_ids)` | Collection; exact current-member permutation, supplied as list/tuple |
| `move_member(collection_id,asset_id,*,direction,expected_neighbor_id)` | Collection; swap with the captured adjacent member |

Unknown collection/asset IDs and invalid names/order/pagination raise `ValueError`.
Removal is idempotent only while both referenced records still exist; an unknown
or actually deleted asset is explicitly refused. Collection deletion requires an
existing collection, so a second deletion is an unknown-ID error. SQLite/I/O
failures retain the existing `sqlite3.Error`/`OSError` behavior. Pagination requires
positive integer `limit` or `None`, and nonnegative integer `offset`, within the
SQLite signed-integer range. Booleans, fractional and oversized bounds are refused
before SQL; offset beyond the membership returns an empty list.

## Ordering and concurrent edits

All mutations acquire `BEGIN IMMEDIATE` before validation or membership reads.
Each read API uses one read transaction. No durability pragma or scanner behavior
changes. Duplicate add is idempotent and never moves the member. Remove preserves
the relative order of the survivors; re-add appends after `MAX(position)`.
Remove and catalog-asset cascades may leave gaps. Stored positions are internal
order keys, rather than row numbers; sorting by `position,asset_id` defines the
display sequence. At the signed-integer position ceiling, a new add is refused;
an exact reorder compacts positions and permits further appends.

Full reorder accepts every current member exactly once. Missing, additional,
unknown, duplicate or invalid IDs refuse the entire operation. Validation and
replacement share the reserved writer transaction, so a stale captured list
cannot discard a concurrently committed add/remove. A valid replacement writes
dense positions starting at zero. Delete/insert avoids transient unique-key
collisions during permutations; any failure rolls the whole replacement back.
Two valid concurrent full-order commands serialize; the later accepted command
sets the order.

Adjacent move requires integer direction `-1` (up) or `+1` (down), the selected
asset ID and the neighbor captured by the UI. Under the writer lock, the API
checks that the selected asset is a member and that its actual directional
neighbor matches `expected_neighbor_id`. A boundary, removed/reordered neighbor,
unknown ID or nonmember is an error with no movement. It atomically replaces only
those two membership rows with swapped positions; sparse positions and page
boundaries behave the same way. It does not load the whole member list. Returned
member counts still require a catalog count query. Two calls with the same stale
capture cannot silently move twice.

Qt counts/pages join membership by collection UUID and asset UUID, select asset
columns, and preserve the existing page cache and filters. The UI captures IDs
before dialogs and looks up selection by UUID after refresh. Up/Down is enabled
only for an unfiltered collection, so an adjacent displayed row cannot conceal
another member. A neighbor across the 256-row page boundary is captured normally
and checked again by the API. Catalog members whose source is offline or whose
observation is marked missing remain valid; source loss never deletes membership.

## Migration and backup guarantees

Fresh initialization creates schema v4. Existing-only `initialize(create=False)`
refuses missing, unversioned, unknown/future and noncanonical catalogs; it never
creates them. Canonical `SCHEMA_V2` and `SCHEMA_V3` remain available for retained
version fixtures. Supported declarations authenticate all `table_xinfo` columns,
including refusal of generated/hidden columns, plus exact table/trigger sets,
types, null/default declarations, primary/unique comparison semantics, CHECKs
and foreign-key actions. V4 also requires the canonical named
`collection_members_asset` index on `collection_members`: exactly the plain
`asset_id` key, ascending with BINARY collation, non-unique and non-partial.
Its table association and actual key semantics are compared with SQLite's
reference-schema introspection; name existence alone is insufficient. Equivalent
SQL formatting, identifier quoting and explicit BINARY/ASC are accepted. Missing,
renamed or incorrectly declared required indexes refuse opening without repair,
backup or migration. Extra non-unique indexes remain allowed. Historical
non-unique indexes on the retained v1/v2/v3 tables remain outside authentication,
including after upgrade; this v4 lookup requirement does not narrow those accepted
shapes. The accepted legacy-v1 constraint policy remains unchanged.

Before any model or worker opens, quiesce existing connections. The initializer
reserves the writer, authenticates the original version, makes one SQLite backup
of that original state through a separate read-only connection, and verifies it
read-only before schema/data mutation. It then runs every required step in the
same reserved transaction: v1 rebuild to v2, v2 metadata addition to v3, and v3
collection addition to v4. There is one original-version backup per attempt,
rather than intermediate-version backups. V3 upgrades never recreate metadata
tables; all aliases, parents and assignments are preserved exactly.

The completed schema and integrity/FKs are checked before commit. DDL, copied
rows, metadata changes and `user_version` roll back together on failure, leaving
the original usable and the verified original-version backup retained. Retry
creates a distinct backup. Backup failure prevents every migration statement.
Current-v4 opening authenticates declarations without creating a backup or
running a full integrity scan each time. SQLite lock and backup limitations
remain those in [the metadata contract](metadata-design.md); these checks do
not certify power-loss or network-storage durability.

## Focused validation and limits

Local checks used Linux x86_64, Python 3.14.7, SQLite 3.51.2 and Pillow 12.3.0,
with `ResourceWarning` treated as an error. All media/catalogs were fictional
temporary fixtures.

| Focused command, after `python -W error::ResourceWarning -m unittest discover -s tests -p` | Result |
| --- | --- |
| `test_collections.py -v` | 16 passed; 0.190 s |
| `test_catalog_migration.py -v` | 18 passed; 0.481 s |
| `test_metadata.py -v` | 11 passed; 0.187 s |
| `test_core.py -v` | 16 passed; 0.070 s |
| `test_sources.py -v` | 9 passed; 0.189 s |

Collection tests cover names/UUIDs, independent namespaces, same-hash identity,
duplicate/remove/re-add/reopen, pagination, exact-permutation refusal, sparse
and cross-page swaps, stale/boundary and simultaneous captures, partial-write
rollback, competing additions, unavailable versus actually deleted assets,
unchanged metadata/state, and source/sidecar bytes/mtimes. Migration tests include
empty/populated v1/v2/v3, preserved v3 metadata, backup restoration, all-step v4
failure rollback, retry backups, existing writer/WAL coverage, and forged v4
key/CHECK/delete-action/generated-column declarations. The v4 lookup follow-up
also covers missing/wrong-table/wrong-key/order/uniqueness/partial/collation/
direction/expression index declarations, unchanged bytes/schema/version/rows on
refusal, canonical equivalent SQL, extra indexes and retained historical index
variations ([Task 10](tasks/10-collections-core.md)).

Independent full-suite acceptance, review and platform/release CI belong to the
integration gate. There are no saved searches, nested/cross-library collections,
bulk operations, export/import or file mutations. Large-collection throughput
and concurrent full-order UI editing have no separate benchmark in this slice.
