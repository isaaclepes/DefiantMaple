# Task 30: External-actions acceptance and CI

Baseline: merged PR17/main `00432238d7c1e7918fb505364de382dcaa1e3425`.
Branch: `codex/phase1a-external-actions`. Task29 and SDD v0.2 define scope.

Luna owns this brief, the acceptance record, requirement tracker and reviewed
public derivatives. Implementation Sol owns production/tests/product guide and
complex native helper. Independent Sol owns Task31. Root alone runs visible
native interactions and publishes. No agent commits, pushes, switches, PR
operations, global associations changes or user-media launches.

## Acceptance contract

Verify immutable focused ID/revision/path/fingerprint targeting through
selection, filters, refresh and configuration dialogs. Revalidation must refuse
catalog drift and stale/unavailable/nonregular originals without retargeting.
Prove literal executable argv and local-file URL association handling;
adversarial media names must not become executable commands. User configuration
is trusted machine-local state, never portable catalog data. Missing executable,
permission/launch failure, finite timeout, late results and shutdown have
truthful outcomes and bounded cleanup. Successful handoff does not establish
opening/saving or automatic reconciliation.

Check source states are last observed. Paused is a normal successful explicit-
scan state, not offline; unavailable states require explicit rescan. Record
scanning/error handling and final check-to-launch races. External editing is
user-controlled; the generated read-only handler is what proves immutability.
First-use settings load must stay off the GUI thread and share the single
in-flight admission slot. Its absolute five-second operation deadline gates
permit admission; bounded cleanup and an OS request already admitted may finish
afterward. Connection-local foreign-key setup and reading `user_version` are
allowed, but no persistent pragma, schema, or catalog-row changes are accepted.

Map FR-EXT-001, scoped external portion of FR-UX-008 and relevant FR-UX-006/007/
010. Keep all 104 FR, 15 NFR and 10 SEC IDs exactly once. Comparison and cached-
offline display remain unaccepted; broad accessibility/platform/release gates
remain explicit. Retain previous evidence chronology and report no new user
feedback rather than inventing it.

## Current status

The external-action design is approved and implementation is in progress on
`codex/phase1a-external-actions`. Bounded Core/source-native behavior and the
reviewed privacy derivative have passed locally. Local verification: 237 Core
tests passed on Python 3.14.7; 58 broad Qt tests passed before the feedback
label plain-text fix, followed by all 9 focused external-action Qt UI tests
after that fix; the Node test passed 1/1. Public-artifact privacy and explicit
`_check_json` passed. Root's generated native attempt 1 is complete; see the
evidence block below and [attempt history](../evidence/external-actions/attempt-history.json).
Exact-head Core/Qt/Tauri CI, actual Windows totals/skips, and the frozen-package
smoke remain gates. Keep source/native behavior distinct from hosted checks
and package validation. The Task 27 PR17 CI evidence is complete: its reviewed
head passed all 30 exact-head checks before merging; this does not pre-accept
external actions.

## Native and privacy protocol

Use generated sources/catalogs/temporary executable/configuration/logs and
isolated XDG state. Record exact host/backend/displays/DPR, Python/Qt, source
and frozen helper hashes, actual keyboard/focus gates and dispatch/refusals.
Use a temporary read-only handler to record literal argv, including fictional
adversarial names, and assert no shell-marker side effect. Default associations
are mocked unless independently evidenced. No global handler installation.

Establish source byte/size/mtime and catalog/journal snapshots before actions;
record deliberate generated mutation/refusal setup separately. Check SQLite
integrity and foreign keys. Record cleanup, timeouts and process ownership.
Preserve raw complete and failed attempts privately. Public receipts use only
reviewed fictional labels/digests/counts and unchanged app-only captures;
exclude private absolute paths/asset UUIDs/raw catalog or argv logs. Run public
artifact checks plus explicit _check_json for newly created JSON and manual
path/ID privacy audit. Native Nobara44 KDE Wayland source evidence, offscreen
tests and hosted/frozen package smokes have distinct limits. Adopt no numeric
performance budget or untested native Windows/macOS/assistive-tech claim.

### Native attempt 1

Root ran the frozen helper
`ed42a150a450b63d3734e362c46f3809c7a25641521fba4484e3647c29693a11` after an
unlocked preflight. The raw receipt is complete (SHA-256
`53f24b5a89f1b2b25dcb313204ad851d0950ecb913cc3ddfb1eccbc7ac555c60`); all ten
source/document digests embedded in it matched the checkout after the run. On
Nobara Linux 44 KDE Plasma/Wayland with Python 3.14.7 and Qt/PySide 6.11.2, one
generated source/two-asset fixture exercised a configured read-only handler,
settings save/reload, focused file/folder handoffs, unavailable-state/ABA/tool
refusals, pre-permit startup and catalog-lock timeouts, cleanup and preservation.
There were three handler requests; the original source manifest and catalog
snapshot were unchanged, integrity was `ok`, and foreign-key violations were
zero. The lock-timeout capture shows refusal and visible controls, not a
successful handoff. The two public PNGs are byte-identical app-only copies.
The configured stub proves literal dispatch only; default associations were
not invoked, and this does not establish a real editor launch, frozen-worker
qualification, Windows/macOS behavior, broad accessibility, or real-share
interruption safety. The public JSON derivative has no absolute paths or UUID
values; the unchanged captures show only generated fixture locations/IDs. Raw
JSON/catalog/argv remain in private wrapper work.

## Completion

Record relevant local commands/counts. Audit exact published-head Core push
and PR, Qt and Tauri jobs, actual Windows unittest totals/named skips and
schema/frozen package smokes/artifacts. Do not rerun completed checks/cohorts
without changed code, failure or unresolved concern. Final CI receipt belongs
in draft PR body/private records to avoid docs-only workflow churn. Finish with
explicit accepted behaviors and limitations, independent review and draft PR;
merge and deployed outputs remain separate.
