# Bulk ratings and favorites

Select cards with Ctrl+click or Shift+click, or use Ctrl+arrow to move focus and
Ctrl+Space to add/remove the focused card. The gallery shows the selection count
and focused filename/ID. Existing inspection, review shortcuts, metadata and
single rating/favorite actions use that focused asset. **Bulk rating and
favorite…** is a separate action over the selected cards, bounded at 256 targets.
Reduce a larger selection before opening it. This operation bound is not a
measured performance budget.

The modeless bulk dialog captures asset IDs and the revisions displayed in the
gallery. Its scrollable target list shows those identities and revisions.
Changing selection, filters, collection, paging or refreshing the gallery never
changes an open dialog's targets. Model resets clear gallery selection explicitly;
after a curation save, surviving selections of up to 256 IDs and the focused ID
are restored by identity. A filtered-out ID is not replaced by its former row.

Choose **Keep each rating**, **Set Unrated**, or **Set 1–5 stars**. Choose
**Keep each favorite**, **Set Favorite**, or **Set Not favorite** independently.
Keep retains each member's own value; it does not copy the focused member.
**Preview effects on captured targets** lists every filename/ID and before/after
value, with changed and unchanged counts. It only reads the catalog. Apply is
available for that concrete preview; changing a choice clears the preview and
disables Apply. Tab/Shift+Tab navigate controls, arrows choose options, and Space
activates focused buttons.

**Apply preview to entire captured group** rechecks every captured member in one
catalog write transaction. Any missing/stale target or storage failure refuses
the whole operation without partial edits or partial journal records. Even an
unchanged member participates in that validation. A complete no-op creates no
group record and advances no revision. A mixed group records all captured members
and updates only the changed members.

After a conflict, **Reload same captured IDs** explicitly reads new revisions
for those same identities, keeps the chosen changes and requires another preview.
Reopen the dialog to target a new gallery selection. A successfully applied
preview is labeled applied and cannot be reapplied without reloading/previewing.
All edits write the catalog only; source images and sidecars are retained.

## Durable whole-group undo

**Recent bulk groups and undo…** works with no gallery selection and after
reopening the library. The bulk editor also contains the same bounded list of
the 50 most recent groups. Choose one exact recorded group, inspect its complete
members and reversal effects, then activate **Undo entire displayed group**.
The displayed group may contain assets outside the current gallery filter or
selection. Its group UUID and complete membership identify the operation.

Undo checks every member's resulting catalog revision and rating/favorite values
under one write transaction. Any changed content/path, metadata/assignments,
meaningful scanner observation, ABA change returning to old values, or storage
failure refuses/rolls back the entire reversal. Already undone groups remain
visible and cannot be undone again. Unchanged members are still checked but do
not acquire artificial revisions. Group undo restores only the changed members
and marks the whole group undone atomically.

Single-asset edit history and group history are separate. A changed group member
has no individual group edit to undo; older single edits are stale after that
change. If a member was unchanged by the group, an otherwise eligible older
single edit may still be explicitly undone. That later write advances its
revision and makes the entire group's subsequent undo unavailable. Any later
single edit or its undo can likewise invalidate group undo, even if values
return to the group's result. This conservative history does not rebase earlier
edits into a general undo stack and provides no redo.

Revisions reflect changes observed in the catalog. An external source-file
change not yet scanned does not advance them. Catalog undo never hashes, writes,
deletes or restores source files. Offline source health alone is not a content
revision. Bulk tags/entities, rich metadata, imported-field synchronization,
source mutations and filesystem undo remain later work.

## Schema and verification

Schema v6 adds authenticated group/member tables alongside the unchanged v5
single-edit journal and revision triggers. The existing initializer upgrades
supported v1–v5 catalogs only after verifying a consistent original-version
backup. Genuine v5 ratings/favorites, revisions and single-edit rows are retained;
asset IDs, sources/provenance, taxonomy and collection order are preserved.
Failure rolls back the complete upgrade and retains the verified backup. Current
v6 catalogs require no new migration backup. Backup catalogs contain private
library metadata and belong with the local library.

The Qt flow and Python API provide bulk editing/undo. Tauri remains the comparison
reader for v2–v6 and preserves its review/page behavior; it has no bulk editor or
migration command. Core APIs are `CapturedTarget`, `CurationChanges`, `KEEP`,
`capture_curation`, `preview_curation_batch`, `apply_curation_batch`,
`list_curation_batches`, `get_curation_batch` and `undo_curation_batch` in
`defiantmaple.curation`. `capture_curation` explicitly reloads the revisions for
fixed IDs; Qt's initial capture instead uses the displayed revisions.

Generated regression tests are in `tests/test_bulk_curation.py` and
`prototypes/qt/tests/test_bulk_curation_ui.py`, alongside prior scanner, migration,
metadata, curation and reader suites. Their offscreen results are separate from
visible native acceptance and hosted platform packaging evidence. This bounded
increment does not establish configurable shortcuts, general accessibility,
broader bulk metadata editing or a Phase 1a release qualification. Historical
diagnostic reports retain their bytes/identities; no diagnostic cohort or
performance change is authorized by this feature.
