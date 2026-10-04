# Tags and entities in the Qt gallery

Open a library and choose **Tags and entities…** beside the selected-asset details.
The manager is available in an empty library too, so you can create labels before
indexing artwork. Assignment buttons become available when the manager opens
with an asset selected. Its target filename and stable asset ID remain fixed
for that editor session; selecting another card or resetting the grid does not
redirect an assignment. Close and reopen the manager to choose another target.

## Edit the taxonomy

In **Tags**, type a canonical name and choose **Create**. Select an existing tag,
edit the name, and choose **Rename selected** to keep its ID and assignments.
Choose a parent or **No parent**, then **Set or clear parent**. A tag can have
one parent; self/descendant cycles are rejected with an inline message. Changing
parents does not assign ancestors to artwork.

The **Entities** tab has a type selector for Character, Artist, Project,
Location, Client, and Franchise. Each type has its own canonical-name/alias
namespace. Creation and rename work the same way as tags; a record's type stays
fixed. The same name can be used for a Character and an Artist.

For either taxonomy, select a record, enter an alias, and choose **Add alias**.
Select an existing alias to enable **Remove selected alias**. The canonical name
and aliases identify the same record. Renaming does not create an alias from the
old name. Names and aliases are normalized by the catalog: Unicode NFC,
collapsed/trimmed whitespace, and casefolded lookup keys while preserving display
case and accents. Collisions and invalid names appear inline without committing
the invalid edit.

## Assign explicitly

Select a tag/entity and choose **Assign selected tag/entity**. The list marks it
as assigned, and the summary above the tabs shows the target's persisted labels.
Use **Unassign selected tag/entity** to remove that relationship. Repeated
assignment/removal is safe. Labels remain on the same asset ID after a source
path changes, and identical-content assets retain separate assignments.

The gallery inspector includes persisted metadata when an asset is selected.
Reopening the library reloads labels, aliases, parents, and assignments from the
catalog. Workflow-state controls remain separate from these artistic labels.
All metadata edits use the catalog API; source files and sidecars are unchanged.
The existing thumbnail/cache behavior remains available.

## Open an older library

The launcher and direct `--catalog` path open supported existing catalogs in
existing-only mode. Valid v1/v2/v3/v4 libraries are upgraded to v5 before a gallery,
model, or scanner/thumbnail worker is constructed. Missing, unversioned, unknown,
and future-version catalogs are refused without being created or rewritten.
An existing gallery must close successfully first; a refused close aborts the
open/create operation and retains that gallery reference.

Normal gallery close cancels and waits for scan/thumbnail work before closing
its model connection. Queued scan callbacks are ignored after shutdown begins.
A blocking filesystem operation can delay this close; migration proceeds only
after quiescence succeeds. The backend reserves the SQLite writer and verifies
a consistent original-version backup before mutation, then upgrades atomically.
After a real upgrade, the UI shows the verified backup's exact local path. If
an upgrade fails after backup, the failure message also shows the retained
backup. Current v5 opening does not create a new backup. Backup catalogs contain
private library records; keep them with the local library. Full migration and
normalization contracts are in [metadata-design.md](metadata-design.md).
Metadata was introduced in v3; the v4 upgrade preserves it and adds separate
[manual collections](collections-guide.md). The v5 upgrade adds explicit
[ratings/favorites and scoped catalog undo](ratings-favorites-guide.md), with
revision triggers covering existing metadata edits as well.

## Current scope and validation

This editor supports one captured asset at a time and loads the taxonomy lists
synchronously. Large taxonomy browsing, batch metadata editing, taxonomy deletion,
groups/rules, automatic ancestor assignment, canonical-tag emission, Character
reference/recognition fields, query-language search, and sidecar
synchronization are outside this increment.
Manual collections use separate gallery controls described in the
[collection guide](collections-guide.md).

Tauri remains the comparison reader. Its current reader contract covers v2/v3/v4/v5 catalogs and retains its
asset count/page/review behavior, and refuses unknown/future versions and missing
files. It does not provide metadata editing controls or migrate catalogs.

Task 04's historical local verification used fictional images, a fictional sidecar, and temporary
catalogs. Focused Qt tests cover all six entity types, canonical rename,
alias add/remove, parent choose/change/clear, assignment/unassignment, empty
library use, UUID capture across selection/model resets, library reopen,
v1/v2 migration before construction, refusal and backup messages, close refusal,
queued worker shutdown, and unchanged source bytes/mtime. Run:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s prototypes/qt/tests -v
```

[Task 11](tasks/11-collections-ui.md) records the historical v2/v3/v4 reader
fixtures and release verification: disjoint pages, filters and review updates
preserved ID/path/hash, with missing/future refusal. The current Python initializer
produces a full v5 catalog for the hosted Tauri release fixture. The v5 reader
change belongs to [Task 23](tasks/23-ratings-favorites-implementation.md), with
verification tracked by [Task 24](tasks/24-ratings-favorites-acceptance.md) and the
[current acceptance record](ratings-favorites-acceptance.md); the historical
Task 11 evidence does not establish its hosted result. Task 04's local Rust execution lacked a
Cargo/toolchain; its hosted compilation, tests and packaged reader evidence
covered v3, before the collections increment. See
[PR #11 checks](https://github.com/isaaclepes/DefiantMaple/pull/11/checks) for
that metadata increment's platform evidence.
