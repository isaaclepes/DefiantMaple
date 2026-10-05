# DefiantMaple Qt gallery

This is the first Phase 1 desktop workflow. It uses the existing catalog,
one-shot source scanner, bounded thumbnail decoder, and page-cached Qt grid.
Original media is read only. There is no continuous filesystem watcher and no
file organization or automatic character recognition.

## Install and launch on Linux

With Python 3.11+ installed, from the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r prototypes/qt/requirements.txt
python -m prototypes.qt.app
```

The unsigned Linux build is named `DefiantMapleQt.bin`. After obtaining it from
the Qt CI artifact or a local build, launch it with:

```sh
chmod +x DefiantMapleQt.bin
./DefiantMapleQt.bin
```

The application identifies itself as `io.github.isaaclepes.DefiantMaple` to
Wayland and uses the same name for its Linux desktop entry and icon. A Linux
package build places `DefiantMapleQt-linux-desktop/` beside the binary. To add
the launcher for the current user on Fedora/KDE, from the artifact directory:

```sh
install -Dm755 DefiantMapleQt.bin "$HOME/.local/bin/DefiantMapleQt.bin"
install -Dm644 DefiantMapleQt-linux-desktop/io.github.isaaclepes.DefiantMaple.png \
  "$HOME/.local/share/icons/hicolor/256x256/apps/io.github.isaaclepes.DefiantMaple.png"
mkdir -p "$HOME/.local/share/applications"
sed "s|^Exec=.*|Exec=$HOME/.local/bin/DefiantMapleQt.bin|" \
  DefiantMapleQt-linux-desktop/io.github.isaaclepes.DefiantMaple.desktop \
  > "$HOME/.local/share/applications/io.github.isaaclepes.DefiantMaple.desktop"
```

The desktop entry can be checked with `desktop-file-validate` where available.
The Python launch has the same in-app window title and icon; the desktop entry
above is for the packaged binary. These commands install only into the current
user's XDG directories and do not scan any media.

The binary is unsigned and may need the system Qt/XCB runtime libraries. On
Debian/Ubuntu, the CI build installs `libegl1`. If a distribution lacks other
Qt platform dependencies, use the Python launch above while resolving them.
No model weights are included. The first screen asks you to create or open a
library; it does not discover or scan personal folders automatically.

## Hands-on smoke test with fictional files

Run this from the repository root to create a disposable fixture outside Git:

```sh
python -m benchmarks.gallery_fixture /tmp/defiantmaple-fictional-gallery
```

1. Launch the application. Choose **Create new library**, saving a `.sqlite3`
   file outside the artwork folder and outside Git, for example in a separate
   temporary directory. Reopen it later with **Open existing library**.
2. Choose **Add folder**, select `/tmp/defiantmaple-fictional-gallery`, then
   choose **Inbox**. **Reviewed** and **Ignore Until Modified** are also
   available for sources added later.
3. Choose **Scan source**. The scan runs in the background, reports progress,
   and waits for unchanged file size and modification time before indexing.
   The generated gallery includes PNG, JPEG, GIF, WebP, transparency, EXIF
   orientation, one exact duplicate, malformed and oversized images, and an
   unsupported text file. Unsupported files appear under **Source issues**.
4. Browse the thumbnails, adjust the size slider, select a card, and inspect
   details and provenance. Double-click a card, press Enter, or choose **Inspect
   full image…** for the cataloged original. The viewer has fit, zoom, drag-pan,
   full-screen/F11, Escape to close, and checker/light/dark transparency
   backgrounds. A malformed, changed, missing, unsupported, or over-limit source
   reports an explicit inspect error. The gallery does not substitute a cached
   thumbnail for an original. A malformed or oversized image also gets a
   thumbnail-error placeholder rather than a full-resolution grid decode.
5. With a card selected, use keys `1` through `6` for New, Needs Review,
   Reviewed, Organized, Ignored, and Error. Use the state, media-type, source,
   and path filters to narrow the grid.
6. Choose **Show exact duplicates** and select the group to filter the grid.
   Use **Clear duplicate filter** to return to the other filters.
7. Choose **Scan source**, then **Cancel scan**. The scan stops after the current
   operation. Choose **Scan source** again to resume; completed observations and
   asset UUIDs remain. A new app session can explicitly rescan from the start
   without rehashing unchanged indexed assets.
8. Temporarily make the *fixture* folder unavailable, then choose **Scan
   source**. The source becomes **Offline** and indexed assets remain in the
   library. Restore the fixture and rescan. Only do this to the disposable
   fixture; never rename or unmount a personal artwork source for this test.

The scan is one-shot. If you change files after it completes, choose **Scan
source** again. The UI paginates processing in 2,048-file batches and can resume
from a canceled batch within the same app session. Each pass holds an in-memory
inventory while processing its pages; reopening the app starts a fresh
enumeration. Very large trees still need a future streaming inventory.

## Tags and entities

Choose **Tags and entities…** beside the inspector to create/rename tags and
Character, Artist, Project, Location, Client or Franchise entities. The manager
also opens with no selected asset for taxonomy setup; explicit assignment buttons
require a captured asset. Add/remove aliases and choose/change/clear a tag parent
in the same editor. Names, relationships and assignments persist in the local
catalog, with stable IDs across rename and path changes. Workflow states retain
their separate controls.

The displayed assignment target remains fixed while the editor is open. Reopen
it to target another card. Source images and sidecars remain read-only, and
parent changes do not automatically assign ancestors. See
[the metadata guide](../../docs/metadata-guide.md) for the focused controls and
normalization rules.

Opening a supported v1/v2/v3/v4/v5 library upgrades it to v6 before gallery workers/models
start, after a verified original-version backup. The launcher displays the backup
path after upgrade; failed migrations retain and display any verified backup.
Current galleries must close successfully before another open/create operation.
Missing, unknown, unversioned and future-version catalogs are refused.

## Ratings and favorites

Select a card and choose **Rating and favorite…**. Choose Unrated or 1–5 stars,
toggle Favorite independently, then save. The modeless editor shows its captured
filename/UUID and retains that target when gallery selection changes. Reload
current values explicitly after a stale-write conflict. Gallery Rating and
Favorite filters compose with the existing facets and preserve collection order.
The fields are user catalog overrides; scans and imported candidates do not replace
them. Source files and sidecars remain read-only.

The latest unchanged rating/favorite edit can be undone after reopening. Undo
refuses intervening catalog-observed content/path or metadata changes, including
ABA changes; reload disables stale history. This conservative single-edit undo
does not rebase older history, redo, undo file changes, or detect unscanned external
file edits. See the [ratings and favorites guide](../../docs/ratings-favorites-guide.md)
for revision coverage, keyboard controls and the generated-fixture tests.

## Manual collections

Choose **New collection…** to create an ordered selection of library assets.
Collection management also works in an empty library. Select a collection in
the **Collection** box to browse it; **All assets** restores the library view.
**Rename…** keeps its identity. **Delete…** asks for confirmation and removes
only that collection and its membership, keeping library assets and source files.

Select a card and choose **Add selected…**, then choose its destination collection.
The selected card stays the action's target while the chooser is open. This works
from **All assets** as well as from another collection. Duplicate adds keep the
existing order. **Remove selected** removes the card from the collection being
browsed; adding it again appends it to the end.

**Move up** and **Move down** swap a card with the adjacent member and keep that
card selected, including across gallery page boundaries. Clear source, state,
media, path-search and duplicate filters before reordering. Moves are disabled
while filtering so a hidden member cannot be moved accidentally. If another
writer changes the captured neighbor, the move is refused and the view refreshes.
Collection views otherwise retain those filters and the existing paged gallery.
Order survives refresh and library reopen. A selected card removed or hidden by
a change clears selection rather than selecting a different card at its old row.

An indexed card remains a member when its source is offline or its file is
missing. Collections reference asset IDs; they do not find replacements by path
or content hash. Removing a catalog asset also removes its membership, while
retaining the relative order of remaining members. Collection edits preserve
tags, entities, workflow state, original media and sidecars. Saved searches,
nesting, bulk file operations and collection export/import are outside this
manual increment. See [the collection contract](../../docs/collections-design.md).

## Private artwork and evaluation

For a personal collection, create a private library outside both Git and the
artwork tree, then use **Add folder** to select that collection yourself. Choose
the existing-file policy deliberately and start the scan manually. The app puts
thumbnails under its application data directory, not beside source files. Do
not put library databases, caches, or private evaluation data inside an artwork
source. Symlinks are skipped; an unavailable source is Offline, never a deletion
request. The app does not copy, rename, remove, rewrite, or sidecar source art.

The **Add selected to private evaluation** action records one selected asset at
a time in a separate local SQLite manifest. It asks for an anonymous ID such as
`character-001`, a reference/query/near-lookalike-negative role, a rights
status, and optional private notes. `uncertain` rights are excluded by default.
It does not infer identity or rights and does not change catalog metadata.

Optional offline inference is a separate command and requires a pinned model
snapshot to be downloaded from its official repository first. It is never run
by opening a library or scanning a source:

```sh
python -m benchmarks.private_image_eval \
  --catalog /path/to/private-data/library.sqlite3 \
  --selections /path/to/private-data/selections.private.sqlite3 \
  --vectors /path/to/private-data/vectors.private.sqlite3 \
  --summary /path/to/private-data/evaluation-private-report.json \
  --model dinov2-small
```

The command validates the pinned revision and weights SHA-256 and uses only
rights-cleared selected images. Its local vector rows carry model, revision,
license, weights hash, preprocessing version, source hash, and dimensions. The
aggregate summary omits paths, names, hashes, vectors, IDs, and per-image scores.
Keep even that summary private until reviewing it for disclosure. Embeddings
must not be assumed non-reversible. The synthetic benchmark recommendation in
[`docs/embedding-model-benchmark.md`](../../docs/embedding-model-benchmark.md)
remains provisional; this app offers no recognition suggestions or automatic
tags.

## Local data and limits

The library database goes exactly where you choose in the file dialog.
Thumbnails are in `DefiantMaple/thumbnails/<library-key>` under
`$XDG_DATA_HOME` or `~/.local/share` on Linux, `~/Library/Application Support`
on macOS, and `%LOCALAPPDATA%` on Windows. Private selections are in a sibling
`DefiantMaple/private-evaluations` directory. Temporary decoder files and locks
are inside the thumbnail cache. Optional model downloads use the configured
Hugging Face cache; optional vectors and summaries go to explicit CLI paths.
None of these belong inside an artwork source or Git.

Image support is PNG, JPEG, GIF, and WebP. Video entries can be indexed but
have a safe unsupported-preview placeholder. Animated images use the first
frame. Full-image inspection validates the catalog fingerprint and is capped at
512 MiB source bytes, 32,768 pixels per dimension, 40 million pixels, and a
12-second decoder timeout; larger sources report an explicit limit error.
Decoder limits prevent excessively large sources and dimensions, but the
worker process is not an OS security sandbox. Cancellation cannot interrupt an
individual file hash or decoder call; it takes effect at the next file boundary.
Progress totals can change if the source changes during enumeration. Native
watchers, cross-volume rename guarantees, automatic organization, and
cross-platform CPU-only model packaging remain future work.

For the existing 100,000-row synthetic grid benchmark and unsigned package:

```sh
python -m benchmarks.generate_catalog /tmp/benchmark.sqlite3
QT_QPA_PLATFORM=offscreen python -m prototypes.qt.app \
  --catalog /tmp/benchmark.sqlite3 --benchmark-json /tmp/qt-source-metrics.json
python -m prototypes.qt.package \
  --catalog /tmp/benchmark.sqlite3 --metrics /tmp/qt-metrics.json
```

The benchmark disables thumbnail loading and mutates review state only in the
generated catalog. CI runs core and Qt tests on Linux, macOS, and Windows,
benchmarks this catalog, and uploads unsigned artifacts. The Tauri workflow
remains a separate regression check.

## Captured bulk curation

Ctrl/Shift selection and Ctrl+Space select multiple cards. The gallery shows the
selection count and focused single-action target. **Bulk rating and favorite…**
captures up to 256 displayed IDs/revisions; Keep/clear/set choices require an
effects preview before atomic apply. Selection/filter changes never retarget it.
Recent group history persists across reopening and exposes explicit whole-group
undo with all-member revision checks. See the [bulk curation guide](../../docs/bulk-curation-guide.md)
for reload, unchanged-member single undo, source preservation and evidence limits.

Explicit external file/folder actions capture the focused asset and run bounded
checks before a literal-argument or local-file URL handoff. Machine-local tool
settings, refusal states and reconciliation are described in the
[external actions guide](../../docs/external-actions-guide.md). The packaging
gate now includes a read-only real spawned external-worker probe; it withholds
the dispatch permit and qualifies worker validation only.
