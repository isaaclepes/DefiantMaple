# Task 48 — library admission acceptance

Status: exact-candidate local Core, offscreen Qt, and nine frozen package smokes have passing receipts; independent validation, platform CI and native desktop gates remain open. Owner: Luna. Checkpoint: 2026-10-18.
Implementation: [Task47](47-library-admission-implementation.md).
Independent review: [Task49](49-library-admission-review.md).

Current sanitized evidence is in [the incomplete results draft](../library-admission-results.md) and [its JSON record](../evidence/library-admission/results.json). The tested runtime ID is `597b1fbac1186a70af0e86370413b9c1d6bb82c2544f423fb3f4dee218fc913e` on base `99d4e471d2dd207a3f44b1408eb6eb3197bca55d`; it identifies an uncommitted 164-input overlay and does not claim Git HEAD equivalence. Full Core passed 336 tests, the full offscreen Qt suite passed 192, and the frozen package receipt records nine named smoke passes. Source/output preservation matched. Task49 validation of the frozen receipt and results drafts remains pending. Native Qt helper planning is approved for implementation only; review the exact helper source before execution. Actual three-host Rust/Tauri CI, native Qt execution, and final acceptance remain held.

Prepare `docs/library-admission-acceptance.md` with named cases and exact
oracles against the reviewed design. Use fictional private fixtures only.
Distinguish current cooperative clients, historical clients and external SQLite
writers. Explicitly retain the old-client and unsupported-storage limitations.

Cover two real processes competing, same-process nested services/threads,
normal release, owner crash, contender refusal without mutation, bounded
refusal timing, inherited/spawned worker cleanup, cancellation and restart.
Exercise alias/copy/UUID distinctions, missing target creation races and
replacement freshness. Use real platform adapters when claiming their support;
an injected Windows result on Linux is not Windows execution.

Verify migration ownership begins before mutation/backup, restoration publishes
only isolated destinations and leaves holds intact, and the live source owner
can complete legitimate spawned recovery without opening a bypass for another
application. Retain read-only inspection and prior package compatibility within
the documented contract. Verify no source/cache/output changes and unchanged
SQLite durability settings, UUIDs and catalog metadata.

Capture source freeze, environment, exact commands, direct exits and raw hashes.
Run relevant focused and full suites after material implementation changes;
reuse unchanged evidence within scope rather than repeat it indiscriminately.
Native desktop and frozen subprocess evidence require separate named claims,
reviewed generated-fixture helpers and real desktop availability. Do not launch
the app against the user's actual library for acceptance.

Audit all actually triggered current-head workflows and actual Windows test
totals and named skips. Preserve failed/interrupted attempts; never equate a
wrapper success or platform skip with supported behavior. Do not cancel/rerun
unchanged jobs. Keep private paths, IDs, catalogs and raw logs outside public
evidence. Publish a sanitized results MD/JSON only after Task49 review.

No output deployment, source-file mutation, commit, push or merge. Root owns
publication. Finish with bounded acceptance and an explicit remaining-limit
record, not full FR-LIB-003 or release acceptance without its evidence.
