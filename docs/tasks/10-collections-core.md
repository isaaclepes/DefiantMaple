# Task 10: Manual collections catalog and migrations

Owner: Sol (catalog). Status: implementation frozen; focused checks passed;
independent acceptance/review and platform CI pending on codex/phase1-collections.
Baseline main: 5d67640; PRs 10 and 11 merged with exact-head green CI.
Read Task 05, metadata-design.md and catalog.py. Root coordinates schema v4.

Implement a focused collections API and catalog schema using stable UUIDs for
collections and existing asset IDs for members. Names use the existing Unicode,
case and whitespace normalization contract in a separate collection namespace;
reject empty names and normalized duplicate collection names. Renaming preserves
ID. Deleting a collection removes only its membership records. Membership is
ordered and unique per collection; duplicate add is idempotent without moving
the member, remove is idempotent, and re-add appends. Reordering requires an
exact permutation, validated atomically, with no lost concurrent writes.
Define a single-member move API if it keeps UI operations bounded and clear.

Reject unknown collection/asset IDs explicitly. Referencing an indexed asset
whose source is unavailable remains valid. Actual catalog-asset deletion must
not leave dangling references; choose/document cascade semantics and ordering
after a deletion. Do not substitute path/hash identity or silently add unknown
records. Membership writes must preserve asset rows, state, tags and entities.

Advance to schema v4 with authenticated prior v1/v2/v3 shapes. Preserve original
verified-backup and reserved-writer sequencing, all-steps atomic upgrades and
rollback, retained backups, and Qt existing-only opening semantics. Include all
columns via table_xinfo and refuse generated/hidden/noncanonical declarations.
Preserve metadata and legacy rows exactly, including aliases, parents and
assignments. Document v4 APIs, normalization, ordering and failure contracts.

Own catalog.py, a focused collections module, relevant Core/migration tests,
collection design/guide documents and this record. Coordinate API before UI
implementation. Do not edit Qt, Rust, another agent's docs or root's orchestration
record. No commits, pushes, branch changes, external messages or extra agents.
Use fictional temporary catalogs only; never mutate source media or sidecars.

Acceptance: create/rename/delete, duplicate/remove/re-add, ordering and reconnect,
missing IDs vs unavailable source, exact reorder refusal without partial writes,
UUID/path changes, metadata preservation, empty/populated v1/v2/v3 migrations,
backup restoration and injected whole-upgrade rollback. Run focused meaningful
checks, then report ready for one independent full-suite acceptance run.

## Agreed preparation contract

Collection records are `{collection_id, name, member_count}`. Provide
create/get/rename/list/delete_collection, ordered list_members, idempotent
add_member/remove_member and exact reorder_members. Validate optional pagination
bounds before SQL. Collection/member IDs are catalog UUID references.
Positions are unique nonnegative integers within a collection. Remove/cascade
may leave gaps; re-add appends and full reorder compacts, preserving sequence.
Adjacent move_member takes direction -1/+1 and expected_neighbor_id, verifies
the captured neighbor under the writer lock, and atomically swaps those two
members. Define/document boundary and stale-neighbor behavior explicitly.
An asset deletion can still be forbidden by existing provenance/source FKs;
this increment adds no asset deletion API.

## Implementation and focused evidence (2026-09-28)

- Added schema v4 `collections` and `collection_members`, canonical retained
  `SCHEMA_V3`, normalized independent names, stable collection UUIDs, unique
  nonnegative integer positions, membership uniqueness and cascade delete actions.
  Schema authentication retains full `table_xinfo` and declaration checks.
- Added `defiantmaple.collections` with the agreed lifecycle/member API, validated
  pagination, idempotent append/remove, exact full permutations and captured-
  neighbor adjacent moves. Each write reserves the SQLite writer before reading
  or validating membership. Sparse positions preserve survivor order; re-add
  appends. Neighbor swaps replace only two rows atomically and refuse stale or
  boundary captures. Unknown IDs never create records implicitly.
- Preserved one original-version verified backup before any mutation. All
  required v1/v2/v3-to-v4 steps share the original reserved transaction. V3
  metadata is retained without recreating its tables. Full v4 failure injection
  proves earlier steps, DDL/data and the version marker roll back together; a
  verified backup remains and retries create a different backup.
- Added [the API/schema contract](../collections-design.md) and
  [the gallery guide](../collections-guide.md). Updated metadata migration/current-
  version guidance while retaining Task 04's historical validation evidence.

Environment: Linux x86_64, Python 3.14.7, SQLite 3.51.2, Pillow 12.3.0, using
`/tmp/defiantmaple-scan-venv/bin/python`. All checks used fictional temporary
catalogs/media/sidecars. No real source library, mount or private media was used.

| Command after `python -W error::ResourceWarning -m unittest discover -s tests -p` | Result |
| --- | --- |
| `test_collections.py -v` | 16 passed; 0.190 s |
| `test_catalog_migration.py -v` | 18 passed; 0.481 s |
| `test_metadata.py -v` | 11 passed; 0.187 s |
| `test_core.py -v` | 16 passed; 0.070 s |
| `test_sources.py -v` | 9 passed; 0.189 s |

Coverage includes exact reorder rejection without writes, partial-insert rollback
for full reorder and two-row swap, simultaneous captured-neighbor refusal,
reserved-writer/concurrent-add preservation, ordering across sparse positions and
row 255/256, empty/populated v1/v2/v3 migrations, aliases/parents/assignments,
backup restore/retention/WAL sequencing, forged v4 declarations, actual deletion
versus unavailable media, and unchanged asset/state/metadata/media/sidecar rows
or bytes/mtimes as applicable. Existing legacy migration refusal tests remain.

Independent full Core/Qt acceptance, read-only review and desktop release/platform
CI are the integration gate. The schema/API increment adds no file operations,
saved searches, nested collections, export/import or asset-deletion API. No
large-collection throughput or power-loss durability claim is made.
