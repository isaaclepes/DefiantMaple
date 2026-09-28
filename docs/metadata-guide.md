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
existing-only mode. Valid v1/v2 libraries are upgraded to v3 before a gallery,
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
backup. Current v3 opening does not create a new backup. Backup catalogs contain
private library records; keep them with the local library. Full migration and
normalization contracts are in [metadata-design.md](metadata-design.md).

## Current scope and validation

This editor supports one captured asset at a time and loads the taxonomy lists
synchronously. Large taxonomy browsing, batch metadata editing, taxonomy deletion,
groups/rules, automatic ancestor assignment, canonical-tag emission, Character
reference/recognition fields, collections, query-language search, and sidecar
synchronization are outside this increment.

Tauri remains the comparison reader. It accepts v2 and v3 catalogs, retains its
asset count/page/review behavior, and refuses unknown/future versions and missing
files. It does not provide metadata editing controls or migrate catalogs.

Local verification uses fictional images, a fictional sidecar, and temporary
catalogs. Focused Qt tests cover all six entity types, canonical rename,
alias add/remove, parent choose/change/clear, assignment/unassignment, empty
library use, UUID capture across selection/model resets, library reopen,
v1/v2 migration before construction, refusal and backup messages, close refusal,
queued worker shutdown, and unchanged source bytes/mtime. Run:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s prototypes/qt/tests -v
```

Rust reader fixtures exercise both supported versions through disjoint pages,
filters and review updates while preserving ID/path/hash, plus missing/future
refusal. The hosted Tauri release workflow generates its benchmark through the
current Python initializer, providing a full v3 catalog for its actual release
reader. Local Rust execution is unavailable on the implementation host because
no Cargo/toolchain was found; hosted compilation, tests and packaged reader
runs on Linux, macOS and Windows remain the release evidence gate. See
[PR #11 checks](https://github.com/isaaclepes/DefiantMaple/pull/11/checks) for
current-head platform evidence.
