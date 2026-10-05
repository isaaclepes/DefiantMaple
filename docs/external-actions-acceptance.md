# Safe external-action protocol and acceptance

Status: bounded local and source-native evidence passed; exact-head hosted CI
remains pending. This document defines the bounded behavior and its evidence.
It is not evidence that an external program opened, saved, or reconciled a
file.

## User-visible actions

The focused item may be sent to **Open in Editor** or **Open containing
folder**. The folder action opens its directory; it does not promise to select
or highlight the image. The action uses either the operating-system association
or a trusted executable selected by the user in machine-local settings. The
command configuration is frozen when the action starts; later settings edits
do not retarget it. A configured executable receives fixed literal arguments
plus the target as a separate argument. Use an absolute executable path; do not
search `PATH`, expand templates, or invoke a shell. At most 32 fixed arguments
are allowed, each no longer than 4096 characters and without NUL/newline
separators. Windows `.bat` and `.cmd` wrappers are refused. OS associations
take no configured arguments and use a local-file URL. No global OS association
is installed or changed. Media names are never interpolated into a shell
command.

Trusted command settings live in versioned machine-local JSON outside the
portable catalog and registered artwork roots. They are never restored from
catalog data. On first use, settings load off the GUI thread under the same
one-operation admission rule; the absolute operation deadline includes that
load and the remaining probe/permit flow. A load timeout before permit cannot
launch. Saving settings does not change the system's global file associations.

The external application is user-controlled. A successful dispatch result
means only that DefiantMaple requested a handoff. It does not confirm that an
editor appeared, opened the intended document, saved changes, or updated the
catalog. After editing a source, the user explicitly rescans to refresh
catalog/source observations.

## Captured-target checks

At action start, capture the displayed asset UUID, catalog revision, absolute
path, indexed content fingerprint and size, plus source ID when present.
Selection changes, filtering, refresh, or opening settings cannot replace this
captured target. Before a handoff, requery the same catalog identity and source
relation, check that the original is an available regular file, and hash its
contents through a file descriptor. Compare device, inode, size and modification
time while validating that descriptor and path. Requery catalog/source state
again after hashing while holding a short `BEGIN IMMEDIATE` writer reservation
that ends with the final check and dispatch. Repeat source path and
parent-directory identity checks there; do not write catalog rows, persistent
pragmas or schema. Connection-local `PRAGMA foreign_keys=ON` and a `user_version`
read are allowed. Refuse any revision, path, identity, source membership,
availability or fingerprint drift instead of silently rebasing the request.

Source health is a last-observed scan fact. The current enum is `watching`,
`scanning`, `paused`, `offline`, `permission_denied`, or `error`. `paused` is a
normal successful explicit-scan state, not an unavailable source. `watching`
and `paused` may proceed after the fresh checks. `scanning`, `offline`,
`permission_denied`, `error`, and pending/ignored/unsupported/error/missing
entries are refused. A source-backed asset must have exactly one indexed entry
matching its asset ID, source ID and current path. A valid standalone indexed
asset may have a null source ID and no source-entry row; it still requires the
captured identity and fresh-file checks. A GUI probe does not clear an
unavailable last-observed status; explicit rescan/reconciliation is required.

The design bounds permit admission to a 5-second operation deadline and hashes
no more than 512 MiB of source bytes. These are operational refusal limits: a
larger or slow valid file may be refused. The deadline does not guarantee a
result is visible within five seconds; bounded cleanup may add time, and an OS
request admitted before the deadline may finish or acknowledge afterward.
These are not supported-media limits, latency budgets, or a promise about
launch time.

## Dispatch and timeout outcomes

Potentially blocking catalog/filesystem work runs off the GUI thread. One
operation is admitted at a time; there is no waiting queue, and another worker
is not started while cleanup remains incomplete. On completion, timeout or
cancellation, cleanup makes bounded 0.1/0.5/0.5-second wait/terminate/reap
attempts. If a process remains uninterruptible, report cleanup incomplete,
retain its reference and disable replacement actions. The helper first reports
`READY`; it can receive exactly one dispatch permit only while uncancelled and
before the absolute deadline. Probe-only execution never grants that permit.
A timeout or cancellation before permit guarantees no dispatch and no late
launch. Once a permit is issued and an operating-system request begins, a
timeout, cancellation, or lost acknowledgement may mean the handoff occurred.
Show that outcome as uncertain, never claim that it did not open, and never
automatically retry. Do not terminate an acknowledged user-owned editor.

The final path check and operating-system launch cannot be made race-free as a
single operation. Acceptance must document this remaining check-to-launch
window. DefiantMaple neither writes source files nor changes asset metadata as
a consequence of an external process.

## Acceptance evidence

Native attempt 1 completed on Nobara Linux 44 KDE Plasma/Wayland with Python
3.14.7, PySide6/Qt 6.11.2 and DPR 1.0. On one generated source with two assets,
a configured read-only handler received three literal requests for a file and
its containing folder; settings saved and reloaded. Generated API checks
refused scanning/offline/permission-denied/error source states, a catalog ABA,
a missing tool and a pre-permit startup timeout. A catalog-lock timeout sent no
permit or extra handler request while GUI timer/key handling remained
responsive. The original media manifest and catalog snapshot matched after the
run; SQLite integrity was `ok`, foreign-key violations were zero, and the
helper was reaped and gallery model connection closed. Thirty-eight QtTest key
actions used programmatically established focus followed by real keys into
visible, active, exposed controls; this is bounded control evidence, not a
human keyboard-only or broad accessibility evaluation. The read-only stub does
not qualify real editor opening or the OS default association.

The reviewed fictional-only receipt is
[`attempt-history.json`](evidence/external-actions/attempt-history.json), with
unchanged app-only captures of the settings dialog and timeout/controls state.
The capture called timeout/controls depicts refusal after the catalog-lock
timeout, not a successful handoff. Raw receipt, paths, argv, and catalog remain
private.

Local verification on Python 3.14.7 passed 237 Core tests; 58 broad Qt tests
passed before a subsequent feedback-label plain-text regression fix, followed
by all 9 focused external-action Qt UI tests after that fix. The Node test
passed (1/1), and the public-artifact privacy checker and explicit `_check_json`
for the new derivative passed. Exact-head hosted Core/Qt/Tauri CI, actual
Windows summaries and the frozen-package smoke remain pending.

Acceptance uses generated fictional sources, a generated catalog and isolated
machine-local settings. Test safe literal argv with adversarial filenames and a
temporary read-only handler; verify a shell-marker file is not created. Mock
default-association behavior unless it is separately and safely evidenced.
Cover focused-target drift, ABA/revision/path/content changes, nonregular or
unavailable originals, source health and entry consistency, absent executables,
permission and launch failures, deadline/cancellation before permit, late
results, uncertain acknowledgement after permit, bounded cleanup, and
shutdown. Verify the action does not modify source bytes or catalog rows. A
frozen `--smoke-external-probe-id` verifies packaged helper validation through
the `READY` gate without granting a dispatch permit; it is not evidence of a
real editor or OS-association launch.

Record exact host/backend/display and runtime facts, focused control/keyboard
results, fixture and helper hashes, source byte/size/mtime and catalog/journal
snapshots, integrity/foreign-key status, process ownership, timeouts and
cleanup. Preserve raw failures. Public JSON must pass the repository privacy
checker and explicit `_check_json`; manually inspect paths and IDs. Public
captures must be unchanged app-only copies with fictional content. Exclude
private absolute paths, asset UUIDs, raw catalogs and raw argv logs.

Offscreen tests, hosted Windows/macOS jobs, a source-native Nobara KDE run, and
frozen-package smoke tests are separate evidence classes. A temporary handler
proves structured dispatch only, not the native default association. No Linux
source run qualifies native Windows/macOS behavior, human assistive-technology
coverage, or release support. Comparison, cached-offline display, broad
accessibility and platform/release qualification remain outside this scoped
acceptance.
