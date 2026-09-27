# DefiantMaple Qt gallery

This is the first Phase 1 desktop workflow. It uses the existing catalog,
one-shot source scanner, bounded thumbnail decoder, and page-cached Qt grid.
Original media is read only. There is no continuous filesystem watcher and no
file organization or automatic character recognition.

## Install and launch on Linux

With Python 3.11+ in a virtual environment, from the repository root:

```sh
python -m pip install -r requirements.txt -r prototypes/qt/requirements.txt
python -m prototypes.qt.app
```

The unsigned Linux build is named `DefiantMapleQt.bin`. After obtaining it from
the Qt CI artifact or a local build, launch it with:

```sh
chmod +x DefiantMapleQt.bin
./DefiantMapleQt.bin
```

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
   details and provenance. A malformed or oversized image gets a thumbnail-error
   placeholder rather than a full-resolution grid decode.
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
frame. Decoder limits prevent excessively large sources and dimensions, but the
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
