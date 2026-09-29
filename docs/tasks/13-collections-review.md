# Task 13: Independent manual collections integrity review

Owner: independent Sol reviewer. Status: local integrity review complete; hosted acceptance pending.
Read Tasks 05, 10-12 and final APIs/design. Review saved implementation separately
from owner tests; this record is the only writable review file.

Check stable IDs, namespace/canonical collision behavior, ordered unique members,
reserved-writer validation and atomic reorder/delete, exact permutation handling,
catalog deletion vs unavailable source, and no mutation of asset state/taxonomy.
Review original-version backup verification, lock ordering, supported-shape
authentication, all-steps rollback/restoration and v3 metadata preservation.
Exercise uncertain behavior with small independent fictional repros; use primary
documentation for uncertain SQLite semantics rather than guessing.

Review paged Qt collection queries, filters/count/order, target UUID capture,
reorder page/filter edges, deletion/view refresh and safe worker quiescence.
Review Tauri supported/unknown catalog handling and actual-v4 release evidence.
Report concrete findings to root/owners; verify fixes from saved source and
focused checks. Do not repeat full acceptance or expensive benchmarks without
a new failure or unresolved concern. No code edits, commits, pushes, branch
changes, PR mutations, external messages, private media/mounts or extra agents.

## Independent review results (2026-09-28)

Reviewed the saved collections implementation on `codex/phase1-collections`,
based on `5d676403eae6b281bae73bcfa706420696245f70`. The implementation was
uncommitted during review. Root froze the catalog implementation before the
independent reproductions; the UI owner froze the final selection-race fix
before its verification. This review changed only this record. All experiments
used fictional rows and temporary local catalogs, with no private media,
mounts, network shares or source-file operations.

### Finding and verified resolution

**Resolved P2: selection restoration could raise after a concurrent member
removal.** In a new three-member collection `a,b,c`, clear the model's page
cache, then wrap the real `row_for_asset('c')` to remove `c` through the real
collections API after computing rank 2. Calling
`_restore_asset_selection('c')` raised `IndexError: list index out of range`:
the model still counted three rows while its lazy page contained only `a,b`.
The existing UUID comparison dereferenced the missing row before it could
clear selection. The reproduction uses a real second database connection;
the wrapper merely chooses the precise rival-commit boundary.

The UI owner now treats an absent rank, mismatching UUID or lazy-fetch
`IndexError` as a stale view, refreshes the count/cache, and clears selection
and detail. It retains the single-statement target/rank snapshot and close
guard. The original independent reproduction now completes without exception,
reports count 2, has no selected row, and safely reads surviving UUIDs `a,b`.
The owner's new deterministic regression also covers removal of an earlier
member, where the old rank points to a different surviving UUID; both subcases
clear selection and repair the count/cache. No other concrete integrity
finding remains from this review.

### Catalog, names and ordering

- Collection creation uses a new UUID; rename preserves it. Membership uses
  existing asset IDs exclusively, with no path/hash substitution. The reused
  metadata name contract performs NFC, whitespace collapse and casefolding;
  empty/control-character names and normalized collisions are refused within
  a separate collection namespace. Historical asset IDs remain supported.
- The schema enforces unique `(collection_id,asset_id)` and
  `(collection_id,position)`, nonnegative integer positions, and both parent
  foreign keys with delete cascades. Collection operations write only the two
  collection tables. Workflow, taxonomy, provenance and source rows are not
  updated by these APIs.
- Mutations reserve the writer before dependent reads/validation. Duplicate
  add preserves position, repeated removal of a known nonmember is idempotent,
  re-add appends, and gaps preserve survivor order. Full reorder captures caller
  input, validates an exact current permutation under the writer lock, then
  replaces membership atomically. It cannot discard a rival add/remove.
- Adjacent moves validate direction, member and captured directional neighbor
  under the same writer lock and replace only the two rows with swapped
  positions. Sparse positions and boundaries are handled explicitly. The
  final concurrent-capture regression proves two identical captures cannot
  silently swap twice; stale full-order input after a rival addition is refused.
- Offline or missing-source observations remain valid catalog members.
  Actual catalog-asset deletion cascades membership and preserves survivor
  order, while existing provenance/source-entry foreign keys can still forbid
  that deletion. No asset-deletion or source-file operation API was introduced.

### Migration and backup evidence

Read the complete initialization path and declaration authentication. The
accepted legacy-v1 canonicalization policy is retained from the reviewed
metadata milestone. V2/v3/v4 authenticate table and trigger sets, all
`table_xinfo` columns, types/null/default declarations, primary/unique
comparison semantics, CHECKs and foreign-key actions; generated/hidden
columns are refused. V3-to-v4 creates collection structures without rebuilding
the metadata tables. Existing-only missing/unknown/future opening refuses
before gallery construction, and launcher quiescence retains close-refusal
handling.

An independently authored experiment exercised **six cases: DELETE and WAL
each with original v1, v2 and v3**. Each had a legacy asset ID, original workflow
state and provenance; v3 also had parent/child tags, tag/entity aliases and
assignments. At the final migration step, the experiment verified exactly one
readable original-version backup matching the complete original `iterdump`
and `user_version`, and confirmed that a rival `BEGIN IMMEDIATE` was refused.
It then completed the v4 DDL, changed an asset state, and raised an injected
failure. Every case restored the exact original dump/version, retained the
verified backup, and supported restoration by copying that backup. A normal
retry produced a distinct backup, preserved old values and passed integrity
and foreign-key checks. All six cases passed under the final frozen backend.

Primary SQLite documentation was checked directly:

- [Transactions](https://sqlite.org/lang_transaction.html) establishes the
  single writer and IMMEDIATE transaction behavior, plus snapshot lifetime.
- [Online backup API](https://sqlite.org/c3ref/backup_finish.html) specifies
  distinct source/destination handles and the source-write restriction.
- [PRAGMA table_xinfo](https://sqlite.org/pragma.html#pragma_table_xinfo)
  documents inclusion of generated and hidden columns.

These checks establish implementation sequencing and rollback behavior in the
tested runtime; power-loss or network-storage durability remains unverified.

### Qt and reader review

Count and page queries share the collection join and every source, workflow,
media, search and duplicate predicate. Membership uniqueness and the existing
unique source-entry asset index prevent joined row multiplication; pages select
asset columns and order by stored position then asset ID. Rank lookup and
target lookup use one SQL statement/read snapshot. The repaired post-lookup
check safely clears a changed or absent target and repairs stale caches.

Create/rename/delete/add dialogs capture collection and asset IDs before nested
dialog responses; destination collection records are snapshotted for the add
chooser. Changed selection/model resets cannot retarget the operation. Empty
libraries can manage collections. Delete confirmation clearly limits deletion
to the collection and memberships; deletion refresh falls back to All assets
when the selected collection disappears. Collection callbacks and late dialog
responses guard `_closing` before accessing a closed model or writing.

Movement is disabled and refused while any applied filter or pending search
text is active. The selected and adjacent UUIDs are captured across the existing
256-row page boundary and revalidated by the backend. The final 514-member
sparse-position boundary regression passed independently, including selection
following its UUID and no unbounded member-list fetch.

Independently inspected the owner's fictional 1280x800 offscreen preview at
`work/collections-ui-preview.png` in the parent workspace. Collection controls,
gallery selection and inspector fit without visible clipping. No minimum width
is specified in the saved app/docs or supplied SDD text. Narrower widths and
platform-specific layouts remain unverified; this preview uses placeholders.

Tauri remains a comparison reader with retained v2/v3 and current v4 support.
Saved Rust tests exercise paging/count/filter/review behavior, invalid bounds,
unknown versions 0/1/5/999 without mutation, and missing catalogs without
creation. Its unit fixtures are intentionally minimal reader fixtures. The
hosted release workflow instead invokes the Python catalog generator, then
benchmarks that catalog with the actual unsigned release executable. The final
generator change reads `PRAGMA user_version` from the generated database and
reports `catalog_schema_version`; this supplies explicit schema evidence in
hosted logs. Cargo is unavailable locally, so this reviewer did not execute
Rust tests or a release package.

### Focused verification and limits

Environment: Linux x86_64; Python 3.11.16, SQLite 3.51.2, Pillow 12.3.0 and
PySide6 6.11.2 in `/tmp/defiantmaple-metadata-verify-venv`. Python commands used
`-W error::ResourceWarning`; Qt used `QT_QPA_PLATFORM=offscreen`.

- Independent original race reproduction: confirmed before the fix; passed
  after the fix with count/cache repair and cleared selection.
- Independent migration/rollback/restoration experiment: all six cases passed.
- `python -W error::ResourceWarning -m unittest
  tests.test_collections.CollectionsTests.test_concurrent_captured_neighbor_moves_do_not_swap_twice
  tests.test_collections.CollectionsTests.test_reorder_reserves_writer_before_reading_and_refuses_concurrent_add -v`:
  **2 passed**, 0.023 s.
- `QT_QPA_PLATFORM=offscreen python -W error::ResourceWarning -m unittest
  prototypes.qt.tests.test_collections_ui.CollectionUITests.test_rival_removal_between_rank_and_page_load_repairs_view_without_retargeting
  prototypes.qt.tests.test_collections_ui.CollectionUITests.test_paging_moves_across_boundary_without_full_member_fetch
  prototypes.qt.tests.test_collections_ui.CollectionUITests.test_collection_callbacks_after_close_and_dialog_close_do_not_access_model -v`:
  **3 passed**, 0.181 s, including the two rival-removal subcases.
- One initially mistyped test selector caused a unittest loader error; the
  corrected saved test name is recorded above and passed.
- `git diff --check` and `git diff --no-index --check /dev/null
  docs/tasks/13-collections-review.md` passed, including the untracked review
  record. Final implementation hashes remained unchanged during verification.

Final reviewed source SHA-256 identifiers:

| File | SHA-256 |
| --- | --- |
| `defiantmaple/catalog.py` | `18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad` |
| `defiantmaple/collections.py` | `c027d404b0f43e009fd8f9a4e1fc774bf92a46a11ea0e6acd0ee35c9d7cbf6ae` |
| `prototypes/qt/app.py` | `10ede8956ddf96e349a995e82c488b3be18f2d713d3ff50ccb007715dec9b6db` |
| `prototypes/qt/tests/test_collections_ui.py` | `95e0d63bd08cdf0f179aa44d175b400f822664887fa6660f76a62cab4476ed76` |
| `prototypes/tauri/src-tauri/src/main.rs` | `4f51cd227fa69fb60e2a6bb3690d311e71bfbf04c34f0f04d55046fc751fc71d` |
| `benchmarks/generate_catalog.py` | `c2a346b645db6df7c927710a6847b30c05b4b8759946e3a28e670ba59f579e36` |

No full suites or expensive benchmarks were repeated by this reviewer.
Independent full-suite/privacy acceptance belongs to Task 12. Exact-head
hosted Linux/macOS/Windows checks, Rust execution and actual schema-v4 release
benchmark/thumbnail evidence remain pending publication; local review does
not satisfy those acceptance gates. Root was informed of the finding, verified
resolution, backend checks and remaining hosted evidence.

## Required v4 index follow-up review (2026-09-28)

The automated P2 on PR 12, thread `PRRT_kwDOPnNRA86m6OyE`, arrived after the
original independent review above. The follow-up baseline was
`9b4fd049c132a6df0593821056b78b0b874f1fbf`. The original catalog SHA-256 was
`a6d7f5699f1d4c6812b27fea9249482ebf403f4fdf2da18da11f0768c8e77a74`;
the six-source table now contains the newly reviewed catalog hash. Original
findings, experiment counts and limits above retain their historical meaning.
The other five sources in that table have unchanged hashes.

**Resolved P2: required collection asset lookup was not authenticated.** An
independent immutable-baseline module accepted seven populated fictional v4
catalogs: missing `collection_members_asset`, its canonical name on the wrong
table, wrong key, partial predicate, DESC direction, NOCASE collation, and an
expression key. Every opening reported current v4 without changing bytes.
The original signature skipped all non-unique indexes, so both absent and
malformed lookup declarations escaped authentication.

The owner explicitly froze the saved catalog, regression tests, design and
Task 10 before dependent verification. Read the complete saved diff: the
signature now collects the named index through `index_list(collection_members)`
and compares its uniqueness, partialness and ordered `index_xinfo` key semantics
against the canonical SQLite-created reference schema. Its name must occur on
the actual membership table, with exactly one plain `asset_id` key, BINARY
collation, ascending direction, non-unique and non-partial. Key identity/order
and expression semantics are checked through SQLite introspection, independent
of SQL formatting. An index with the right name on `assets(asset_id)` fails.

The policy is bounded to the new v4 membership lookup. Retained v1/v2/v3 tables
keep their historical non-unique-index acceptance policy, including after
upgrade; unrelated extra non-unique indexes remain allowed. The existing
distinct-extra-unique refusal policy and accepted v1 constraint canonicalization
are preserved. The saved design states this scope, canonical-name requirement,
accepted equivalent quoting/BINARY/ASC formatting and refusal without repair.
No backup/migration sequencing, collection API, Qt or Rust implementation changed.

Primary SQLite documentation was checked directly for this follow-up:

- [PRAGMA index_list](https://sqlite.org/pragma.html#pragma_index_list) reports
  association with the queried table, uniqueness and partialness.
- [PRAGMA index_xinfo](https://sqlite.org/pragma.html#pragma_index_xinfo) reports
  ordered keys, expression identity, direction, collation and auxiliary columns.
  Auxiliary row locator columns do not become declared keys.

### Independent frozen-source verification

An independently authored `/tmp/collections-index-independent-review.py` used
Python 3.11.16 and SQLite 3.51.2 in
`/tmp/defiantmaple-metadata-verify-venv`, with `-W error::ResourceWarning`.
All catalogs, rows and paths were fictional and temporary. The final fixture
also included offline/missing source metadata and v3 parent/child tags, aliases,
entities and assignments. It passed **47 cases**:

| Independent probe | Exact result |
| --- | --- |
| Fifteen malformed index declarations, each under DELETE and active WAL | 30 refusals |
| Canonical v4, quoted explicit BINARY/ASC, parenthesized plain key, extra partial expression index, missing historical non-unique indexes | 5 accepted current-v4 openings |
| V1/v2/v3 with absent historical non-unique indexes plus an extra partial expression index; v1 also uses its accepted NOCASE path policy | 3 successful upgrades |
| Distinct extra unique index on retained assets in v2/v3/v4 | 3 refusals |
| Final-step failure, original backup/restoration and successful retry for v1/v2/v3 under DELETE and WAL | 6 atomic migration cases |

The fifteen malformed shapes were missing, renamed equivalent, right name on
the wrong table with the same key name, wrong column, unique, partial `WHERE 0`,
partial `WHERE 1`, extra key after/before `asset_id`, repeated key, DESC, NOCASE,
RTRIM, function expression and unary expression. Every refusal preserved the
complete schema, `user_version`, dump and catalog bytes; active WAL bytes also
remained unchanged. Instrumentation forbade backup creation, all three migration
steps and schema execution, and none ran. No backup output appeared.

Current-v4 acceptance cases returned the exact unchanged-current result and
preserved bytes/schema/version/rows without a backup. Historical policy cases
made exact original-version dump/schema backups and preserved old row values;
v1 added its canonical source column without changing original fields. Each
upgrade passed v4 authentication, integrity and foreign-key checks.

For each atomic case, the final-step hook found exactly one readable backup of
the complete original schema/version/dump and confirmed that a rival
`BEGIN IMMEDIATE` was refused. It then created v4, changed workflow state,
inserted a collection and raised. Original schema/version/rows returned exactly,
the verified backup remained readable and copying it restored the original.
A normal retry made a distinct backup, preserved the old backup and every
original asset/provenance/source/metadata value, and passed v4 authentication,
integrity and foreign-key checks. The catalog hash stayed frozen throughout.

Additional frozen follow-up file hashes:

| File | SHA-256 |
| --- | --- |
| `tests/test_catalog_migration.py` | `41539c95ede927da4687b5408a5b53fa771f33d9dd985d87d2b82206cf9e8f86` |
| `docs/collections-design.md` | `7481c06d09c3c09b1e68d6383d75a89f6c985e1db72ac836547252025988ba66` |
| `docs/tasks/10-collections-core.md` | `a6f757634faf5172991c2fccf5daf5e613577f54ad57af9922a0259434fdb261` |

`git diff --check` passed after saving this record. All four frozen follow-up
file hashes above were verified again and remained unchanged.

No concrete integrity finding remains from this follow-up. The owner-run
regressions and full Core result are recorded in Task 10; this reviewer did
not repeat full suites or expensive benchmarks. This review changed only Task
13 in the repository. Root owns publication, PR-thread resolution and fresh
affected hosted acceptance. The original platform, real-source/network-share
and power-loss limits remain applicable.
