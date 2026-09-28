# Task 12: Independent collections acceptance and CI

Owner: Luna. Status: acceptance inventory prepared; implementation acceptance pending.
Baseline main: `5d67640`; working branch: `codex/phase1-collections`.
Source of scope: Tasks 05, 10 and 11 plus SDD §§6, 11, 18 and 21.

This file records what the independent acceptance pass must establish. It is
not evidence that implementation checks have passed. Wait for root's handoff
and a frozen tree before testing; do not run suites against the active edits or
repeat an unchanged baseline.

## Acceptance inventory

### Product boundary and preserved data

- [x] Collections are user-managed, static curation lists with stable collection
  UUIDs. Saved searches, query language, dynamic/nested collections,
  cross-library membership, import/export and bulk file operations remain out
  of scope for this increment.
- [x] Membership refers to the catalog's stable asset UUID. Rename, path change
  or identical content at another path does not retarget membership by path or
  hash. Collection rename preserves its collection UUID.
- [x] Create, rename, delete, add, remove and reorder change collection records
  only. Verify asset UUIDs, paths, workflow state, tags, entities, provenance,
  source files and sidecars remain intact. Compare source and sidecar bytes and
  mtimes before and after UI acceptance; routine thumbnail/cache generation is
  allowed.
- [x] A known catalog asset whose source is unavailable remains a valid member
  and can still be displayed from catalog state. Unknown collection or asset
  IDs fail explicitly. No dangling member remains if a catalog asset is
  deleted through an existing supported path; document the established FK
  behavior because this increment adds no asset-deletion API.

### Catalog API, ordering and concurrency

- [x] Create/get/list/rename/delete use the agreed `{collection_id, name,
  member_count}` record. Reject empty names and names that collide after the
  existing Unicode, case-fold and whitespace normalization, scoped to a
  separate collection namespace. Invalid pagination bounds fail before SQL.
- [x] Member lists preserve a total order with unique nonnegative positions.
  Duplicate add and repeated remove are idempotent; duplicate add does not
  move a member, while remove then re-add appends it. Reconnect preserves the
  order. Removal/cascade gaps and full-reorder compaction match the documented
  contract.
- [x] Exact reorder accepts only a complete permutation of current member IDs.
  Invalid, missing, duplicated or extra IDs are refused atomically with no
  partial position changes. Adjacent up/down moves require direction `-1` or
  `+1`, verify the captured expected-neighbor UUID while holding the writer
  lock, swap only that pair, and define boundary and stale-neighbor outcomes.
- [x] Concurrent membership/reorder attempts serialize without lost updates or
  duplicate positions. Membership writes do not alter asset or Task 04
  metadata rows.

### Schema v4 migration and refusal safety

- [x] Authenticate canonical v1, v2 and v3 layouts before migration, including
  all columns and generated/hidden columns. Refuse altered or noncanonical
  schemas instead of accepting them by `user_version` alone.
- [x] Test both empty and populated catalogs at each supported prior version.
  Preserve asset UUIDs, provenance, tags, entities, aliases, parent links,
  assignments and other existing metadata while creating the v4 collection
  structures.
- [x] Reserve the SQLite writer and verify a readable, integrity-checked
  original-version backup before any schema/data mutation. Backup failure must
  leave the original unchanged. Inject a failure during the complete upgrade;
  verify rollback leaves the original usable and retains the verified backup.
  Demonstrate restoration from a verified backup.
- [x] Opening missing, unknown, newer/future or invalid catalogs refuses
  without creating or changing a database. Qt migrates supported catalogs
  before gallery/model/worker construction and preserves existing open-only
  behavior.

### Qt lifecycle, browsing and target stability

- [x] Exercise create, rename, confirmed delete, add selected asset, remove
  member, collection selection and ordered browsing. Empty-library collection
  management works without a selected asset. Delete confirmation says only the
  collection and membership are removed.
- [x] Capture the target asset and collection UUIDs before dialogs or model
  changes. Selection changes, resets, refreshes or late callbacks cannot
  retarget an operation. Refresh restores the asset selection by UUID only if
  it remains visible; otherwise clear it.
- [x] All-assets and collection views preserve paged counts, existing
  source/workflow/search/duplicate filters, selection, metadata editor,
  thumbnails and reopen behavior. Shared count/page collection predicates do
  not duplicate gallery rows and select only asset columns. Unavailable-source
  members remain visible as catalog records.
- [x] Up/down reordering is enabled only when source, workflow, media, search
  and duplicate filters are clear. Filtered/hidden members are never moved by
  mistake. Verify neighbor capture across the 256-row cache boundary (rows
  255/256), plus backend stale-neighbor refusal.
- [x] Render one representative offscreen UI state and record the environment
  and any visual limitation.

### Tauri reader and actual v4 release evidence

- [ ] Tauri remains a comparison reader with no collections UI. Focused tests
  establish v2, v3 and v4 support, retained paging/count/filter/review behavior,
  and refusal of missing, unknown and future schemas without file creation or
  mutation.
- [ ] On Linux, macOS and Windows, release CI generates the Python catalog
  using the current catalog initializer, confirms its canonical `user_version`
  is 4, and runs the actual unsigned release benchmark against that same
  generated catalog. Generator JSON must report `catalog_schema_version` read
  from the generated database's `PRAGMA user_version`; the fixture acceptance
  test compares it with both the actual database value and `SCHEMA_VERSION`.
  Record the generator output, direct schema-version
  evidence (or equivalent package validation), asset count, package result,
  benchmark metrics and thumbnail smoke result. A desktop metrics-format
  version field is not evidence of the catalog version.

## Execution and report fields

After owners freeze the implementation and root hands off the tested tree:

- Run the focused migration, core collection, Qt collection and Tauri reader
  checks once; then run one independent full Core and one full offscreen Qt
  suite. Do not rerun an unchanged baseline. Record the exact commit/tree,
  command, Python/Pillow/Qt/Rust environment, and pass/fail/error/skip counts.
- Run the public-artifact privacy checker and `git diff --check`; capture exact
  outcomes and any test-generated workspace changes. Use only fictional rows
  and temporary local catalogs. Do not use private artwork, real media
  libraries, mounts or network shares.
- For current-head CI, fetch all-event `actions/runs?head_sha=...&per_page=100`
  and `commits/.../check-runs?per_page=100` through the generic GitHub REST
  fetcher. Match each `total_count` to returned rows and follow every next
  page. Check the exact current head, current base, latest attempt and every
  job. Review actual Windows logs for Core totals and capability-skip reasons,
  Qt test counts, Rust test counts, and v4 release benchmark evidence on all
  three operating systems. Empty legacy status arrays do not establish success.
- Keep PR runs separate from push runs, including the post-merge main push.
  Poll live work with backoff; do not restart or cancel a slow job solely
  because observation takes time.

Final report: exact tested head/tree and base; changed files; migration and
backup behavior; local command/environment/counts; privacy and whitespace
results; UI render result; current-head run/check/job counts and per-platform
Windows/Qt/Rust/v4 benchmark evidence; unresolved issues and limits.

## Scope and ownership

Own this acceptance inventory and acceptance evidence only. Do not edit
implementation or other agents' documents, commit, push, change branches,
mutate PRs, send external messages or create agents. Root owns publication,
thread resolution and merge sequencing.

## Local acceptance results (2026-09-28)

Tested working tree based on `5d676403eae6b281bae73bcfa706420696245f70`;
the working tree contains the frozen collections implementation plus this
acceptance-owned generator evidence change. All fixtures use fictional rows and
temporary local databases/media; no private artwork, real media library, mount
or network share was used.

- Updated `benchmarks/generate_catalog.py` to read the generated database's
  `PRAGMA user_version` and emit `catalog_schema_version`. Extended the existing
  `test_benchmark_fixture_populates_comparison_data_once` test to compare that
  field against both `SCHEMA_VERSION` and the database's actual pragma.
- Focused command:
  `/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest tests.test_core.CoreTests.test_benchmark_fixture_populates_comparison_data_once -v`;
  1 passed, 0 failures/errors/skips, 0.025 s.
- Full Core command:
  `/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v`;
  133 passed, 0 failures/errors/skips, 12.583 s. Environment: Python 3.14.7,
  SQLite 3.51.2, Pillow 12.3.0.
- Full Qt command:
  `QT_QPA_PLATFORM=offscreen /tmp/defiantmaple-metadata-verify-venv/bin/python -W error::ResourceWarning -m unittest discover -s prototypes/qt/tests -v`;
  28 passed, 0 failures/errors/skips, 6.375 s. Environment: Python 3.11.16,
  PySide6 6.11.2. The frozen repair covers a rival deletion between rank lookup
  and lazy page loading; its regression checks recovery without raising or
  retargeting the selection. The prior 27-test run predates that repair and is
  superseded by this final full-suite result.
- Privacy command:
  `PYTHONPATH=. /tmp/defiantmaple-scan-venv/bin/python scripts/check_public_artifacts.py`;
  passed. The checker examines tracked files only; untracked files were separately
  inventoried with `git status --short` and contain only the documented source,
  tests and docs. `git diff --check` passed. No test-generated workspace files
  were reported by `git status --short`.
- Representative fictional offscreen layout render and visual inspection are
  recorded under Task 11 at
  `/home/isaac/Documents/Codex/2026-09-24/github-plugin-github-openai-curated-remote/work/collections-ui-preview.png`;
  the final Qt suite passed after the race repair.

Hosted exact-head Actions/check-run pagination, per-platform Windows/Qt/Rust
counts, and actual schema-v4 release benchmark evidence remain a publication
gate. Root will record those outcomes in the publication PR body after it
publishes the reviewed frozen head; see the
[collections branch Actions](https://github.com/isaaclepes/DefiantMaple/actions?query=branch%3Acodex%2Fphase1-collections).
The PR body is the current-head CI record so a documentation-only update does
not create a publication loop.

## Backup-path portability correction (2026-09-28)

Hosted macOS Core jobs failed three subtests of
`test_v4_failure_rolls_back_every_prior_upgrade_step_and_metadata_write` at
the strict `_verified_backup` mock assertion. The backup call correctly uses
the canonical path because `catalog.initialize` resolves the input path before
opening it; macOS exposes temporary directories through both `/var` and
`/private/var`. The assertion now expects `self.path.resolve()` while still
requiring exactly one backup call for each original schema version and
preserving the existing rollback, original-row and verified-backup checks.

On the aligned implementation checkout, the focused migration suite passed
18/18 with `-W error::ResourceWarning`; the full Core suite passed 133/133
with the same warning policy. Hosted logs for the pre-fix head showed the
Windows Core 3.13 job emitted the same three migration-test subtest failures
before fail-fast cancellation, but cancellation truncated the detailed
traceback. In the Qt workflow, Linux Core (133/133) and Qt (28/28) passed. On
Windows, Core reported 3 failures and 1 skip among 133 tests, then Qt passed
28/28; the combined step still reported success because the later Qt command
masked the earlier nonzero Core result. macOS Core reported the same three
failures, so the Qt suite did not run there. The post-fix hosted Core/Qt jobs
must replace that evidence before acceptance is complete. Tauri/Rust and the
unsigned benchmark jobs passed on Linux, macOS and Windows on the pre-fix
head; this test-only correction leaves their runtime and generator inputs
unchanged.

Exact post-fix local commands and results (same Python environment as the
local acceptance run above):

- `/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest tests.test_catalog_migration -v` — 18 passed, 0 failures, 0 errors, 0 skipped, 0.464 s.
- `/tmp/defiantmaple-scan-venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v` — 133 passed, 0 failures, 0 errors, 0 skipped, 12.451 s.
