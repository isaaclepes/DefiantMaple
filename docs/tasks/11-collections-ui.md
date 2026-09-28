# Task 11: Qt manual collections and reader compatibility

Owner: Sol (Qt/reader). Status: implementation complete locally; independent acceptance pending.
Baseline main: 5d67640; PRs 10 and 11 merged with exact-head green CI.
Read Task 05 and Task 10; agree on stable collections APIs with the backend owner.

Add Qt create/rename/delete and explicit selected-asset add/remove controls,
collection selection/browsing, and persistent member reordering. Capture target
asset/collection UUIDs before dialogs and preserve them through model resets or
selection changes. Empty-library collection management works without an asset.
Deletion confirmation explains that only the collection is removed.

Keep gallery browsing paged; collection membership orders results without
duplicating rows or breaking counts, existing source/workflow/search filters,
thumbnail handling, selection or reopen behavior. Clearly define reordering with
filters and page boundaries: never move an unintended hidden member. A bounded
up/down interaction is sufficient. Preserve metadata editor behavior and safe
quiescence/open-time migration before models or workers. Source-unavailable
members remain visible as existing catalog records, with no file operations.

Tauri remains a comparison reader. Accept supported v2/v3/v4 and retain count,
page/filter/review behavior; reject missing/unknown/future catalogs without
creating or modifying them. Update focused Rust tests and use actual generated
schema-v4 release benchmark evidence, not just a version constant.

Own prototypes/qt/app.py, focused Qt collection tests, Qt README, Rust reader
and tests, and this record. No catalog edits, commits, pushes, branch changes,
external messages or extra agents. Use fictional temporary fixtures only.

Acceptance covers collection lifecycle, ordered members, selection stability,
views/filters/paging, remove/re-add, reopen persistence, unchanged source/sidecar
bytes/mtimes and unchanged tags/entities/state; existing metadata tests still
pass. Verify one representative offscreen UI render; document limitations.

## Agreed preparation contract

Use an All assets/collection selector, lifecycle controls, a captured-asset
Add selected chooser independent of the browse selector, Remove from current
collection, and Up/Down. Enable moves only when all source/state/media/search/
duplicate filters are clear. Capture adjacent IDs across row 255/256 under the
256-row cache; backend checks expected_neighbor_id again before writing.
Share collection joins/predicates between count/page queries and select only
asset columns. Refresh restores selection by asset UUID or clears a now-hidden
or removed selection. Preserve the existing metadata editor and close guards.

## Implemented results (2026-09-28)

Qt now provides an All assets/collection selector, collection create/rename/delete,
captured selected-asset destination chooser, remove, and adjacent Up/Down moves.
Empty libraries can manage collection names without an asset. Delete confirmation
explains that library assets and original files remain. Collection and asset IDs
are captured before nested dialogs; destination records are snapshotted before
the chooser opens. Changed gallery selection or collection selection cannot
retarget an operation.

The collection join and predicates are shared by count and page queries; member
position and asset UUID determine collection order. The existing 256-row page
cache and source/state/media/search/duplicate filters remain. The UI does not
fetch the full member list for browsing or moving. Up/Down captures only the
selected member and adjacent UUID, including rows 255/256. Moves are disabled
while any filter is active and the slot also refuses filtered moves. Backend
directional adjacency validation rejects a changed neighbor before swapping.

View refresh restores the selected UUID using target lookup and rank in one
SQLite statement/read snapshot, then verifies the row still names that UUID.
A removed or hidden target clears selection. Scan-result refresh uses the same
selection-preserving path. New selector, refresh and mutation callbacks guard
`_closing`, including dialog responses after the gallery has closed. Existing
metadata editing, shutdown/quiescence and thumbnail behavior are retained.

Tauri's reader and focused test matrix accept retained v2/v3 and current v4,
retain paging/filter/review behavior, and refuse 0/1/5/999 and missing catalogs
without creating or modifying them. No Tauri collection UI was added. Rust unit
fixtures remain deliberately minimal reader fixtures; the existing hosted
release workflow generates the actual catalog through Python `initialize`, now
schema v4, before benchmarking its unsigned release executable. Actual v4
release CI evidence remains acceptance-owned and pending publication.

## Focused checks and evidence limits

- `QT_QPA_PLATFORM=offscreen /tmp/defiantmaple-metadata-verify-venv/bin/python -W error::ResourceWarning -m unittest prototypes.qt.tests.test_collections_ui prototypes.qt.tests.test_metadata_ui prototypes.qt.tests.test_gallery_workflow prototypes.qt.tests.test_qt_prototype -v`: **27 tests passed** (8 collection, 11 metadata, 3 workflow, 5 prototype).
- After the final rank-read snapshot change, the collection and metadata modules
  were rerun with the same warning policy: **19 tests passed**. Existing metadata
  migration-opening coverage now includes canonical v3 alongside v1/v2 and checks
  the current schema before constructing the gallery.
- The collection regressions cover empty lifecycle and delete refusal/confirmation;
  add/remove/re-add, idempotent duplicate add and reopen order; forced selection
  and collection changes during dialogs; each filter's count/order and refused
  reorder; offline/missing members; stale-neighbor refusal; late callbacks/dialog
  close; and sparse-position moves across a 514-member fixture's page boundary.
  Source/sidecar bytes and mtimes plus existing asset/provenance/source/tag/entity/
  assignment rows are unchanged in all ordinary collection-control fixtures.
- `git diff --check` passed. Syntax compilation of the saved Qt app passed.
- Rendered and visually inspected a fictional selected four-member collection at
  1280x800: `/home/isaac/Documents/Codex/2026-09-24/github-plugin-github-openai-curated-remote/work/collections-ui-preview.png`.
  All collection controls fit, selected-card feedback and inspector remain
  visible, and the layout has no clipping. This offscreen layout preview uses
  placeholders; the existing real thumbnail workflow regression passed.
- Cargo is unavailable locally, so the changed Rust tests and release executable
  were not run here. Full independent suites, hosted Linux/macOS/Windows evidence
  and actual schema-v4 release benchmarks remain the acceptance owner's gate.

Owned files changed: `prototypes/qt/app.py`, new
`prototypes/qt/tests/test_collections_ui.py`, current-schema/retained-v3 adaptations
in `prototypes/qt/tests/test_metadata_ui.py`, `prototypes/qt/README.md`,
`prototypes/tauri/src-tauri/src/main.rs`, and this record. No catalog/core edits,
commits, pushes, branch changes, publication, private artwork or real mount use.
Implementation handed off frozen for independent review and acceptance.

## Independent-review selection-race correction

The reviewer reproduced a concurrent removal after `row_for_asset` read rank 2
but before its uncached page fetch: the selected last member disappeared,
`_count` remained 3, the page contained 2 rows, and `asset_at(2)` raised
`IndexError`. A UUID mismatch check alone did not handle a shorter page or repair
the stale count/cache.

`_restore_asset_selection` now treats an absent target, mismatching UUID or
`IndexError` from the lazy fetch as a stale view. It refreshes count and page
cache, then clears selection and detail without selecting a different UUID at
the old row. The single-statement rank snapshot and `_closing` guard remain.

The deterministic regression wraps the real rank lookup, then commits a real
rival `remove_member` before lazy page loading. It covers both deletion of the
selected last member and removal of an earlier member that makes the old row
name another UUID. Before the fix, the first subcase raised `IndexError` and the
second retained stale count 3; afterward both clear selection, report count 2,
retain the correct members and allow safe subsequent model reads.

Focused post-fix command with the same offscreen/runtime/warning policy:
`python -W error::ResourceWarning -m unittest prototypes.qt.tests.test_collections_ui prototypes.qt.tests.test_metadata_ui -v`:
**20 tests passed** (9 collection and 11 metadata). `git diff --check` passed.
Only the Qt app, collection regression tests and this record changed for the
correction; owned implementation is frozen again for reviewer recheck and full
independent acceptance.
