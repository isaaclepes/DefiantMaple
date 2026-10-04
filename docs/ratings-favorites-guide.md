# Ratings and favorites

Select an asset and choose **Rating and favorite…**. The editor shows its captured
filename/UUID and current values. Choose **Unrated** or **1–5 stars** and toggle
**Favorite** independently, then save. The editor keeps that UUID even if gallery
selection changes. **Reload current values** explicitly refreshes a stale editor;
a conflict leaves unsaved choices visible until you reload. Tab/Shift+Tab move
through controls; arrow keys choose ratings and Space toggles Favorite or activates
a focused button. The gallery and accessible card text include current values.

These fields are explicit **user catalog overrides**. New and upgraded assets
start unrated and not favorite. The API `catalog_user_managed` authority marker describes this field
policy; it does not claim default values were authored by the user. Per-field
import provenance and conflict synchronization remain separate requirements. Recognition, embedded metadata and sidecars do
not supply or overwrite them. Rescans, content reconciliation and external rename
preserve their values and asset identity. Editing writes the local catalog only.

Gallery **Rating** choices are all, unrated, exact stars and minimum stars;
**Favorite** choices are all, favorites and not favorites. They compose with
review state, source, media type, filename/path search, duplicate hash and manual
collection browsing. Filtered collection members retain their original order;
clear active filters before reordering the complete collection.

## Scoped catalog undo

**Undo latest rating/favorite edit** restores both previous values as one catalog
operation, including after closing and reopening the library. No-op saves create
no edit. Each successful change records an edit UUID, asset UUID, before/after
values and resulting revision in a durable journal. Reads/writes use SQLite
transactions; editing requires the revision captured by the editor.

Undo requires that resulting revision and values still match. Actual intervening
rating/favorite, workflow, content/path, source-identity, tag/entity assignment,
assigned taxonomy/alias and collection changes invalidate it. Meaningful scanner
observations (including a changed fingerprint becoming pending or a missing file)
also invalidate it. Ordinary unchanged scan heartbeat observations do not.
Monotonic revisions detect ABA changes that return to earlier values. Stale writes
and refused undo leave the catalog untouched. Reload disables an undo candidate
whose preconditions no longer match and explains its unavailability.

This is conservative single-edit undo: undo advances the asset revision itself,
so it does not rebase earlier history into a general undo stack. There is no redo,
bulk undo, imported-field synchronization or filesystem undo. Revisions track
changes **observed in the catalog**; the one-shot scanner has no watcher, so an
unscanned external file change does not yet produce a revision. Offline source
health alone does not establish a content change. Catalog rating undo never
restores, hashes, writes or deletes a source file.

## Migration and reader support

Schema v5 adds constrained rating/favorite fields, a monotonic revision, journal
and revision triggers. The existing initializer atomically upgrades supported
v1–v4 libraries after verifying an original-version SQLite backup; failure rolls
back the complete upgrade. Asset UUIDs, source records, existing metadata and
collection positions are preserved. Current v5 opens need no migration backup.
The migration validator authenticates the new table, checks, foreign keys and
trigger bodies. Replacing an existing asset row or changing its UUID is refused;
a journaled asset cannot be deleted and reinserted to reset its history.

The Qt editor provides this workflow. Tauri remains a comparison reader: it reads
v2–v5, exposes rating/favorite on v5 and supplies unrated/not-favorite defaults for
older versions; it does not migrate libraries or provide curation editing/undo.
Python APIs are in `defiantmaple.curation`: `get_curation`, `set_curation` with
`expected_revision`, `list_curation_edits`, and `undo_curation`. Gallery queries
require typed `RatingFilter`/`RatingMode` and `FavoriteFilter` values.

Generated-fixture regression coverage is in `tests/test_curation.py` and
`prototypes/qt/tests/test_curation_ui.py`, with older migration, scanner, metadata,
collection and reader suites retained. Native acceptance and hosted platform
checks are separate evidence; automated tests alone do not establish their result.
