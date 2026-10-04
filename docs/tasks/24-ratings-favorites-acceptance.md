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

The frozen implementation reports 215 passing Core tests and 42 passing Qt
tests. They are local unit/offscreen evidence, not native desktop acceptance.
Two serial native attempts ran on Nobara 44 KDE Plasma Wayland at 2560×1080,
DPR 1.0, using four generated assets, two generated sources, a v4→v5 catalog
migration, verified backup, and isolated catalog/cache/XDG state. Both attempts
reported `ok` migration and backup integrity, zero foreign-key violations,
preserved seeded row counts and ordered collection membership, unchanged
rating/favorite values after scans, and exact expected/observed membership for
all three tested composed filter cases. Both exposed the gallery and captured
only the generated app window. Thumbnail workers were disabled; no thumbnail
performance or worker bound was measured.

Attempt 1 stopped with a timeout after the editor did not activate; its receipt
did not separate editor creation from activation/focus facts. Attempt 2 recorded
the editor visible through Qt but not exposed or active, with no application
active window or focus widget after bounded activation requests. Its strict
native keyboard gate stopped before keyboard interaction. Root separately
confirmed a locked desktop session with a read-only session-state query. The
attempts are preserved separately in the [public filtered history](../evidence/ratings-favorites/attempt-history.json); neither is a native curation
pass or a product defect finding. The two unchanged app-only captures retain
fictional fixture identifiers and temporary generated paths by design. Raw
receipts and runner logs remain local and their SHA-256 values are recorded in
the derivative.

Native editor focus, rating/favorite keyboard editing, save/no-op/invalid-value
behavior, persistence after reopen, durable undo, and stale/ABA/content/path
undo refusal remain pending an unlocked native session. Exact published-head
Core/Qt/Tauri CI and Windows unittest summaries are tracked separately and are
not inferred from the local test counts. All five mapped requirement rows stay
Partial; the broader SDD scope remains deferred.

To reproduce the measured dirty tree after publication, use a detached
worktree at baseline `60ebf881e6bb85316042100e3ed8beb119acf400`, apply the exact
published PR diff without committing, keep `HEAD` at that baseline, and verify
the helper's public `code_file_digests` before running with an appropriate Qt
runtime and a new empty external evidence directory. The probe intentionally
rejects a different baseline commit.

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
