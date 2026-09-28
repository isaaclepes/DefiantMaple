# Task 07: Qt metadata editing and Tauri catalog compatibility

Owner: Sol UI (`mounted_share`). Status: implementation complete; hosted validation
tracked in [PR #11 checks](https://github.com/isaaclepes/DefiantMaple/pull/11/checks).

Checkout: DefiantMaple-metadata; branch codex/phase1-metadata; baseline 0578dfb.
Read Task 04, Task 06 and docs/metadata-design.md once the backend publishes it.
Own prototypes/qt/app.py, focused Qt tests, prototypes/qt/README.md,
prototypes/tauri/src-tauri/src/main.rs and its focused tests, docs/metadata-guide.md,
and this task's results. Do not edit backend/Core tests, CI, Task 04 or audit.

Begin with current-code inspection and a concise UI/reader plan while the API is
being defined. Once coordinated, implement focused controls for tag/entity
creation and rename, explicit assignment/unassignment on the selected asset,
alias add/remove, and tag parent choose/change/clear. Support all six entity
types. Persist and refresh metadata after library reopen. Keep workflow states
separate. Taxonomy deletion, tag rules/groups, recognition/reference/canonical
emission, collections and query-language search remain deferred.

Capture a stable asset UUID before an editor opens; selection changes or model
resets must never redirect the edit. Disable assignment without an asset.
Use backend APIs and foreign-key-enabled writes rather than model raw SQL.
Avoid metadata joins that duplicate paginated gallery rows. Keep source artwork
and sidecars unchanged; normal existing thumbnail cache generation is allowed.
Upgrade a supported existing library before constructing its gallery/model or
workers. Refuse missing/unknown/future catalogs without creating or modifying
those files. Surface a concise useful backup location after a real upgrade.

Tauri remains the comparison prototype. Update its catalog reader to support
v2 and v3 while refusing unknown/future versions; add meaningful reader tests for
both versions and retained count/page/review behavior. Do not add Tauri metadata
product controls. Its release benchmark must open the actual Python-generated
v3 catalog in CI; a version constant change alone is insufficient evidence.

Qt tests must exercise all entity types, tag/entity rename and assignments,
aliases/parents, selection changes, reopen persistence, open-time migration and
refusal, plus unchanged generated source bytes and sidecars. Report local Qt and
Rust checks, any unavailable build dependencies, API integration issues and UX
limitations. Never invent platform test results.
No commits, pushes, branch changes, PRs, external messages or extra agents.

## Results (2026-09-28)

- Added a shared Qt metadata manager with canonical tag/entity create/rename,
  aliases, tag parent choose/change/clear, and explicit assign/unassign for all
  six entity types. It opens in an empty library; only assignment controls depend
  on an asset. The displayed target and writes retain the UUID captured before
  the editor opens, including gallery selection changes and model resets.
- Inspector metadata comes from backend APIs; paginated asset queries have no
  tag/entity joins. Metadata writes use FK-enabled backend connections, and the
  existing model workflow-write connection now enables foreign keys too.
- Launcher and direct --catalog opening call initialize(create=False) before
  constructing the gallery/model/workers. A close refusal aborts open/create
  without clearing the prior reference or initializing another file. A shutdown
  flag ignores queued scan callbacks after waits/model close. Real upgrades and
  failures with a preserved backup display the verified backup location.
- Tauri comparison reader accepts v2/v3, enables foreign keys, and has focused
  count/disjoint-page/filter/review tests for both, preserving IDs/paths/hashes,
  plus unknown/future and missing-file refusal. No Tauri product metadata UI.
- Added docs/metadata-guide.md and Qt README usage/upgrade notes. The offscreen
  editor was rendered with fictional labels/assets and visually inspected.

Local checks: focused Qt metadata tests (11) passed on Linux/Python 3.14.7 /
PySide6 6.11.2; full Qt suite (19) passed in 6.110 seconds after final shutdown/CLI
changes. A backend reference-connection ResourceWarning was reported to its owner.
py_compile and scoped whitespace checks passed. Rust tests were authored
but cannot execute locally because Cargo/toolchain is absent from PATH and the
known ~/.cargo/bin, /usr/bin and /usr/local/bin locations; none was installed.
Hosted Rust compilation/tests and release benchmarks on actual Python-generated
v3 catalogs remain required on all target platforms.

Tests exercise all entity types, tag/entity rename, alias editing, parents,
assignment/removal, separate same-hash asset UUIDs, empty-library taxonomy,
selection/model-reset capture, current library reopen, actual v1/v2 upgrade and
original-version backup integrity, unknown/unversioned/future/missing refusal,
preserved-backup messages, close refusal, and queued actual-QThread shutdown.
Generated image/sidecar bytes and mtimes are unchanged throughout the tests.

Limitations: one asset per editor session, synchronous full taxonomy lists,
modal manager, and no taxonomy deletion/batch edits/recognition/rules/collections.
Migration can wait for an already-blocking scan filesystem operation during
quiescence; it never runs against the still-active model. Hosted platform evidence
is recorded with PR #11; no private media or source/sidecar mutations were performed.
