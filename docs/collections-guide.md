# Manual collections in the gallery

Use **New collection…** to create a named sequence of library assets, including
in an empty library. Names preserve display case and accents; whitespace and
Unicode/case equivalents identify the same name. Empty names and duplicate
collection names are refused with a message. Tags and entities may use the same
spelling because their namespaces are separate.

Choose a collection in the **Collection** selector to browse its members in
their saved order. **All assets** returns to the full library. Existing workflow,
source, media, search and duplicate filters still narrow the displayed assets.
A source becoming unavailable leaves its catalog members in the collection.

Select an asset and choose **Add selected…**, then choose its destination
collection. This chooser also works from **All assets** and can target another
collection without changing the browse view. Adding a member again leaves its
existing position unchanged. Choose **Remove selected** while browsing a
collection to remove only that membership. Adding it back later appends it to
the end. The asset, media and metadata remain in the library.

Use **Move up** or **Move down** to move the selected member one place. Clear all
filters first; movement is disabled in filtered views so hidden members cannot
be moved unexpectedly. Movement works across page boundaries. If another edit
changes the captured neighbor before the save, the move is refused and the view
refreshes. The selection follows the same asset ID after a successful refresh;
removing or filtering out that asset clears selection.

**Rename…** preserves the collection ID and membership. **Delete…** asks for
confirmation and removes only that collection and its memberships. It leaves
every asset, workflow state, tag, entity, original file and sidecar intact.
Collection order and membership persist when the library reopens, including
after an asset's path or content hash changes.

Opening an authentic v1/v2/v3 library upgrades its local catalog to v4 before
the gallery/model/workers open. The existing backup notice identifies the
verified original-version backup. A failed migration rolls back and retains
that verified backup. Current-v4 opening does not create another backup.
Backup catalogs contain private library data; retain them with the local library.
See [the catalog/API contract](collections-design.md) for exact ordering,
concurrency, missing-ID and migration behavior, and [metadata opening guidance](metadata-guide.md)
for worker quiescence and refusal behavior.

This increment provides manual sequences within one library. Saved searches,
nested collections, bulk file operations and export/import are separate work.
Collection browsing retains the gallery's existing thumbnail/cache behavior.
