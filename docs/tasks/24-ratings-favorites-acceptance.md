# Task 24: Ratings/favorites acceptance and CI

Baseline: `60ebf881e6bb85316042100e3ed8beb119acf400` (merged PR #15).
Branch: `codex/phase1a-ratings-favorites`. Design: SDD v0.2, Task 23.

Luna owns this brief's evidence updates, the 129-ID requirement tracker,
[the acceptance record](../ratings-favorites-acceptance.md), and the generated-
fixture native helper `prototypes/qt/ratings_favorites_native_acceptance.py`
with evidence under `docs/evidence/ratings-favorites/`. The filename and output
directory are coordinated with Root. Do not edit implementation or old
gallery/benchmark evidence. No commits, pushes, switches, PR creation or
messages to external users.

## Acceptance protocol

Record unrated/1–5 and favorite semantics, explicit user authority, captured-ID
editing, composed filter membership, no-op/invalid-value behavior, persistence,
revision-checked undo after reopen and conflict/ABA refusal. Exercise generated
old-schema migration with retained verified backup and preservation of UUIDs,
tags/entities, source rows and collection order. Check existing media digests
before/after; use isolated fictional sources, catalogs and caches only.

Native interaction evidence must name host/runtime/display, fixture, cache and
memory limits, controls/keyboard/focus and failure states actually exercised.
This host is Nobara 44 KDE Wayland; that is not plain Fedora or cross-platform
release qualification. Root runs visible native probes serially. Keep raw logs
and attempts locally, derive privacy-checked public evidence without hiding
failed attempts, and record original hashes. Do not repeat passed measurements
without changes/failures that justify repetition. Offscreen tests and hosted
packages are distinct from native desktop evidence.

Refresh only supported tracker claims: FR-META-002, FR-META-003, FR-UX-003,
FR-UX-005 and FR-TXN-007 remain partial where broader requirements are deferred.
Retain all 104 FR, 15 NFR and 10 SEC IDs exactly once and preserve earlier
historical acceptance. Do not invent further user feedback.

## Current evidence record

Local implementation tests report 215 Core tests and 42 Qt tests passing. They are offscreen/regression evidence, separate from visible native acceptance. Native attempt 3 passed on Nobara 44 KDE Plasma Wayland after the desktop session was unlocked. It used Python 3.14.7, Qt 6.11.2, a 2560×1080 display at DPR 1.0, four generated fictional assets, two generated sources, an isolated catalog/cache/XDG root, and a v4-to-v5 catalog migration. The backup and migrated catalog both passed integrity checks with zero foreign-key violations. The seeded rows, collection order, explicit rating/favorite values across four completed scans, and three composed-filter result sets were verified.

The active dialog reached native QtTest keyboard/focus gates for the 5-star and Unrated endpoints, tab navigation, favorite Space toggles, and Save. Changing gallery selection after opening did not redirect the captured-asset edit. The probe refused a stale external write, then saved after reload; it also verified no-op behavior and refusal of four invalid inputs. After reopening, durable catalog undo restored the prior values. Metadata ABA (revision 2→4), content change, and rename each made an older undo unavailable/refused. The application window closed and catalog integrity remained `ok`. This is automated Qt event evidence from one Nobara 44 host; no KDE compositor identity, human accessibility, cross-distribution, or thumbnail-performance claim is made.

Attempt 1 timed out before native editor activation could be established. Attempt 2 observed a Qt-visible dialog without native exposure or an active/focused application window. Root's read-only session-state check found the desktop locked at that time. These two failures remain in the record and are not reclassified as passes or product defects. Attempt 3 completed after the session became unlocked.

The filtered public evidence is [the attempt history](../evidence/ratings-favorites/attempt-history.json), [the attempt 3 receipt](../evidence/ratings-favorites/attempt3/acceptance.json), and two unchanged app-only generated-fixture captures in the same attempt directory. The first two history entries and original capture digests are preserved. The attempt 3 JSON omits absolute paths, raw per-run asset/edit identifiers, tracebacks, and process IDs; the PNGs visibly retain synthetic fixture names and the temporary catalog path. Raw JSON and runner logs remain outside the repository. All eight implementation-file digests in the attempt 3 receipt match the published BEDA-measured implementation, including helper `d29ffe8b2285bc9d62d6b990a2efafb48b5d7eb042d03ce62da1b54f17744201`.

On initial PR #16 head `beda3c560155f924efa01230273872ab279dcafb`, Core push macOS/Python 3.11, Core PR macOS/Python 3.13, and Qt macOS/Windows each exposed the same two fixture-portability failures in `test_diagnostic_schema_compatibility.py`: nested synthetic reports assumed Linux runtime metadata on Darwin/Windows. The Windows Qt Core discovery also recorded the known root-rename skip; Qt tests and package build were not reached in the two failed Qt jobs. A tests-only fixture correction is staged for the next exact-head CI run. Tauri passed on all three platforms and Qt Linux passed Core/Qt tests and package smokes. Do not treat the local suite count or those partial hosted successes as a green full matrix.

All five mapped tracker rows remain Partial: the bounded native ratings/favorites scope now passes, while broader metadata, accessibility, search, and filesystem-undo requirements remain deferred. The PR's corrected-head Core push+PR, Qt, and Tauri runs still need to complete before hosted CI acceptance is recorded.

## CI and privacy

Audit exact published-head Core, Qt and Tauri checks and actual Windows unittest
summaries, distinguishing named skips from failures. Inspect package/schema
compatibility and relevant artifact receipts. Audit merged-main baseline once
if useful; do not confuse those checks with new-head acceptance. Completed
scan/exit cohorts must not run for this product increment absent a concrete
experiment decision. Check tracked public artifacts and explicitly inspect new
evidence JSON even if its filename is outside automatic checker patterns.

Report exact commands, counts, findings, limitations and blockers. Root publishes
reviewed implementation as a draft PR and records hosted receipts in its body,
avoiding documentation-only reruns solely to update CI evidence.
