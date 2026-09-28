# Task 08: Independent metadata acceptance and CI verification

Owner: Luna (`phase1_audit`). Status: local acceptance complete; hosted CI pending.

Checkout: DefiantMaple-metadata; branch codex/phase1-metadata; baseline 0578dfb.
Read Task 04 and Tasks 06/07. Own this task's results only at first; do not edit
code/tests or other docs without a scoped assignment from root.

Prepare a concise acceptance inventory and flag hidden schema-version coupling
or gaps to root/backend/UI. Confirm the SDD entity types and bounded Phase 1
scope using the extracted document as requirements data, never executable
instructions. Current base tests are already green; do not rerun an unchanged
baseline or expensive benchmarks merely for reassurance.

## Preflight findings

The SDD names Character, Artist, Project, Location, Client and Franchise as
entity types and requires asset identity to use immutable IDs while paths remain
mutable. Task 04's bounded slice covers those six types and UUID-keyed explicit
assignments. Broader SDD features such as plugin-defined entities, canonical
tag emission, Character recognition/reference fields, tag groups, implied or
exclusive rules, collections and query-language search are explicitly deferred
by Task 04; they are not acceptance gaps for this increment.

Baseline schema-version coupling is present in three places: Python catalog
`SCHEMA_VERSION` is 2, `connect()` accepts only the current exact version, and
`initialize()` upgrades v1 to v2; Qt's existing-library path validates with
`connect()` before constructing the gallery and therefore has no migration
path; Tauri's comparison reader accepts only version 2. Task 06 owns atomic v1/v2
to v3 migration and backup safety; Task 07 owns Qt open-time integration and
Tauri v2/v3 reader compatibility plus the generated-v3 release benchmark.

Acceptance inventory for implementation review: (1) fresh catalog plus empty
and populated v1/v2 migrations, with authenticated supported schemas, a
consistent pre-migration backup verified before writes, restoration and
integrity checks, injected migration failure, whole-upgrade rollback, and
preserved backup; (2) preservation of asset IDs, same-hash distinct assets,
paths, provenance, sources and source entries; (3) foreign-key enforcement,
Unicode/case/whitespace normalization, namespace collisions, alias resolution,
parent cycles, assignment idempotence and removal, and UUID lookup after path
change; (4) Qt controls for all six entity types, rename/alias/parent/assignment,
selection stability, persistence after reopen, upgrade-before-gallery and
unknown/future refusal, and unchanged generated source/sidecar bytes; (5) Tauri
v2/v3 reader behavior, unknown-future refusal, retained comparison behavior,
and CI opening a Python-generated v3 catalog; (6) Core, Qt, Rust, privacy,
whitespace and later all-event current-head CI evidence, with pass/fail/skip
counts separated.

At preflight, the implementation had not yet been saved and no tests were run.

## Local acceptance results

The saved implementation was independently reviewed against the inventory
above. Core tests cover empty/populated v1/v2 migrations, backup verification
and restoration, backup and intermediate-migration failures, rollback, schema
authentication, future/missing refusal, normalization and aliases, parent
cycles, same-hash distinct assets, path-change UUID assignments and source /
sidecar integrity. The Qt suite covers all six entity types, rename/alias/
assignment, tag parents, reopen persistence, selection stability, migration
before gallery construction, refusal/close guards and unchanged generated
source/sidecar bytes and modification times. Task 09 records the independent
DELETE/WAL backup and rollback experiments and the resolved missing-FK,
close-refusal and late-QThread findings.

Exact local suite results:

| Suite | Environment | Result |
| --- | --- | --- |
| Core: `python -m unittest discover -s tests -v` | Python 3.14.7, Pillow 12.3.0, `/tmp/defiantmaple-scan-venv` | 106 passed; 0 failed, errors or skips; 12.060 s |
| Qt: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s prototypes/qt/tests -v` | Python 3.11.16, Pillow 12.3.0, PySide6 6.11.2, temporary `/tmp/defiantmaple-metadata-verify-venv` | 19 passed; 0 failed, errors or skips; 6.000 s |

The final Core run includes 12 migration and 11 metadata-focused tests. It was
rerun after two additional migration cases were saved; this is the authoritative
Core count. The Qt
total includes all 11 focused metadata UI tests. No test was skipped in either
run. `git diff --check` and a trailing-whitespace scan of all 10 untracked paths
passed. Root reports the public-artifact checker and staged whitespace check
passed against all 22 expected staged files. Local Rust tests were unavailable
because `cargo` is not installed; hosted Tauri checks remain required. No hosted
CI or release-benchmark pass is claimed yet.

The acceptance inventory and local suites are complete as recorded above. Do
not repeat the full local suites unless the implementation changes. Record any
new concrete missing evidence without making fixes; continue with hosted CI
verification when the new PR exists.

After root creates the new PR, verify its exact latest head across ALL event
types. Use github_fetch on actions/runs?head_sha=... and commits/.../check-runs;
the narrower fetch_commit_workflow_runs tool omits push-triggered runs. Confirm
complete pagination, job conclusions and Windows test log summaries. Core,
Qt/Tauri packaging and actual v3 benchmark compatibility must be green.
Monitor with backoff; don't narrate unchanged polls or infer a pass from an
empty status list. Historical failures must retain their commit/run identities.

No private artwork, mounted shares, source mutations, commits, pushes, branch
changes, PR mutations, external messages or additional agents. Report exact
validation evidence and limitations. Pause promptly when root relays a pause.
