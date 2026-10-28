# Task 51 — scheduled local metadata snapshots acceptance

Status: acceptance protocol drafted; broader execution and independent review pending. A bounded B3 offscreen controller/native ordering slice has been independently accepted; it does not complete Task 51 or FR-RECOVERY-003.
Owner: Luna. Implementation/design dependency: [Task 50](50-scheduled-snapshots-implementation.md) and its [design](../scheduled-snapshots-design.md).
Independent review: Task 52. Protocol: [scheduled snapshots acceptance](../scheduled-snapshots-acceptance.md).

This task defines generated-fixture acceptance for opt-in, app-running scheduled
metadata snapshots and managed retention. It does not implement runtime
behavior, change the phase tracker, or establish complete FR-RECOVERY-003
acceptance by itself. Preserve FR-RECOVERY-003's current status until reviewed
results justify a narrowly scoped transition. It does not authorize merging,
deployment, output replacement, or opening the user's actual catalog.

Acceptance is limited to the reviewed Task 50 contract. It must show truthful
last-success and failure status; scheduling under wall-clock jumps, process
restart, and concurrent app activity; native admission before access to the
source catalog; ownership and reaping of spawned snapshot workers; no overlap
between jobs; safe cancellation; coherent SQLite snapshots; real backup and
isolated restore/prior-package compatibility; and retention that cannot remove
the last verified point or an unrelated file. It must test corruption,
replacement, symlinks, destination loss, disk-full behavior, storage bounds,
and unsupported platforms without representing a refusal as a successful
snapshot.

The desktop durable-stop overlay, shared manual recovery actor, and Qt
orchestration add mandatory acceptance cases SS-19 through SS-21 in the public
protocol. B3 now provides a reviewed, bounded component slice for two actual
offscreen QApplication/controller/native-worker orderings. In one, the worker
cleans its actor before the real backup QThread finishes; in the other, the
QThread finishes while an actual child and actor remain pending, and stop
acknowledgment waits for real child/stage cleanup. The second case records the
actual original cancellation-result `BrokenPipeError` and nonzero child exit;
it does not normalize that declared fault into a successful child result. Both
cases verify durable stop readback, the original stopped-state observer,
post-operation state, and preservation. This is partial evidence relevant to
SS-19 and one scheduled-owner contention boundary; it is not window/settings/
manual-dialog integration, restart or lost-ack evidence, or complete SS-19,
SS-20, or SS-21 acceptance. Exact evidence identifiers are listed in the
public case protocol. The timer wake remains bounded to at most once per
minute. No broader desktop behavior is accepted by this evidence slice.

An earlier Task 50 draft required a user to reattach a managed directory after
reopening the app, which could leave a persistently enabled schedule dormant.
The revised Task 50 design now specifies a durable locator; Task 52 clearance
is still required before runtime execution. The acceptance contract must test
ordinary reopening of the same unchanged physical catalog without asking the
user to select the managed directory again. The locator must reattach only the exact
physical catalog and managed directory; corruption or missing/changed identity
must visibly suspend scheduling and retention. A moved, replaced, copied, or
same-UUID/different-physical catalog must never inherit or prune the old
schedule. No manual-reattach-only result may be described as automatic restart
continuity.

The public [case protocol](../scheduled-snapshots-acceptance.md) must be
reviewed before runtime execution. Build generated-only catalogs, media-free
source rows, snapshot destinations, clocks, scheduler events, child processes,
and failure adapters. Helpers that create fixtures or inject native/storage
failures require independent code review before execution. Capture exact
commands, direct exits, source/tree and environment digests, fixture/output
manifests, raw output hashes, worker lifecycle events, and cleanup. Keep
machine-specific paths, private fixture IDs, raw logs, and sensitive metadata
in private receipts. The public protocol and sanitized results contain no such
values.

Package-use leases are an additional required acceptance contract, using the
cleared private package-use lease plan as design input. The real
`_read_package` path must acquire a shared native
lease on its exact no-follow read-only package descriptor before the first
header byte, and hold it until that descriptor closes after extraction and
verification. Exercise both actual manual inspection and actual restore
children. Retention must fully inspect candidates before lease acquisition,
then acquire nonblocking exclusive lease on the exact candidate and shared
lease on the exact survivor, retain both through the reviewed completion
boundary, and stop on typed busy without durable deletion intent or unlink.
Caller-supplied facts are vetoes only and never authority for package identity,
ownership, digest, or deletion.

The lease race cases must run in both directions. Hold an actual manual
inspection or restore shared lease while a retention attempt requests candidate
exclusive access; prove typed busy, package and last-success preservation, and
absence of deletion intent/unlink. Then hold candidate exclusive and survivor
shared leases while actual inspection and restore try to open the candidate;
prove typed refusal before their first package byte. Verify actual descriptor
and native-identity revalidation after shared-lease acquisition so a name that
was replaced while contended is refused. Exercise cancellation and child crash
while each real lease holder is paused; a contender remains refused while the
actual descriptor-owning child is alive, can acquire only after confirmed
exit/close, and sees unchanged packages and managed state. Verify shared reads
of the leased survivor remain compatible. Prove the retention holder keeps
both candidate-exclusive and survivor-shared descriptors open through its
reviewed final completion boundary, then releases them only on completion or
confirmed child exit. Until a separately reviewed executor exists, use a
non-destructive generated completion barrier and do not infer ledger/unlink
integration from that lease-lifetime proof. These are generated lease and
non-deletion cases: the current package-use lease stage does not authorize or
prove native retention unlink/executor integration; SS-09/SS-16 deletion
boundaries remain open until separately reviewed and executed.

Locks are cooperative advisory OS semantics. Existing clients that do not
acquire the new shared package lease, already-open descriptors, and hostile or
noncooperative same-user mutation after the final check are outside the
guarantee. Do not expand or narrow the existing platform claim: native package
lease evidence is limited to the already qualified local Linux adapter, while
Windows/macOS retain their current unsupported native publication behavior.
Platform-neutral parsing/refusal behavior and ordinary manual backup/restore
availability remain separate oracles.

Before any runtime case, save a private source baseline for the merged base
`47effeeb5a5adf8b692023c49b67ee52a9025559`: hashes for all tracked source
inputs, exact hashes/byte lengths/modes/mtime_ns for all 15 deployed outputs,
and the 129 requirement IDs/statuses. Compare the output baseline against the
previous library-admission baseline, which must still match. The baseline is
evidence only; do not modify protected outputs. Reconcile only actually
triggered merged-main CI jobs at this base and fetch actual Windows totals and
named skips from job logs. Do not rerun PR #24 checks or infer results from an
old PR snapshot.

Before and after each independently executed generated fixture/helper, rehash
all 15 protected outputs (SHA-256, bytes, mode, mtime_ns), and compare the
generated catalog main/WAL/SHM, journal/synchronous settings, source/media and
cache inventories/bytes, restored-source holds, package set, and destination
state. No unexpected delta is acceptable. This is a generated-state comparison,
not proof that the application never read source media.

No fixture may refer to the user's real catalog, profile, media, backups,
settings, or recovery destinations. Do not create, delete, or alter real user
snapshots or settings. Do not create a baseline that opens, queries, or
otherwise touches the real catalog. No source/runtime changes, deployed
output changes, tracker edits, or Task 00 orchestration changes are in this
acceptance task. Root owns any later public runtime or tracker authorization.

## Desktop integration acceptance extension

The desktop extension is covered by the detailed generated cases in SS-19 to
SS-21 of the [case protocol](../scheduled-snapshots-acceptance.md). Keep their
evidence separate from the already accepted native retention cases:

- SS-19 covers the durable `stop_requested`/`stopped` transaction, request and
  enable write failures, crash/reopen with cleanup unknown, exact intent and
  last-success preservation, and competing Disable/Enable request-version CAS.
  Restart never promotes a saved request or infers cleanup from a missing PID,
  acquired lock, or idle thread. Only the originating live session may
  acknowledge `stopped` after exact worker and owned-child cleanup. Stop/ack
  faults preserve the existing configuration revision; Enable faults are
  checked against the exact pre/post commit outcome. A committed configuration
  is not rolled back merely because its final `run` control write or
  acknowledgment failed. Missing, mismatched, or uncertain `run` remains
  vetoed and suspended. If the exact valid `run` record committed durably but
  its UI/readback acknowledgment was lost, reopen may reconcile that exact
  committed state without rollback or duplicate Enable; a newer stop still
  wins by control CAS.
- SS-20 covers the actual shared per-owner recovery slot in both directions,
  real inspect/restore/backup child ownership, worker start/callback/cancel/
  timeout faults, and cleanup that outlives a dialog or result signal. Require
  exact filtered reaping and preserve the original worker's stage-deletion
  authority.
- SS-21 covers captured admitted-owner/physical-source identity, controller and
  request epochs, close/switch/reopen and stale replies, plus the bounded
  at-most-once-per-minute Qt wake. The GUI thread performs no catalog or
  filesystem work; offscreen, frozen, and native display evidence stay distinct.

These are acceptance requirements, not implementation authorization or proof
that the desktop feature works. Gate A/B contract review, reviewed generated
helpers, actual results, and Task 52 review remain necessary. The one-minute
bound applies to scheduling wakeups; any separate cleanup wake while an actual
actor remains owned must stay bounded, non-scheduling, and off-UI as specified
in the reviewed desktop contract.

## Evidence and disposition

The case matrix defines required behavior and per-case evidence. A test result
is valid only for the exact source revision, host, adapter, fixture, and
command recorded. Mock clocks, fake native results, synthetic disk-full
exceptions, or injected worker events are adapter/unit evidence only; they do
not establish live scheduler timing, actual platform identity, filesystem
durability, or packaged behavior. A skip is an uncovered case, not a pass.
Unsupported systems must refuse scheduled publication, scheduler-owned source
reads, and scheduled retention before those operations begin. This must not
disable ordinary admitted catalog opens or existing manual backup/restore.
A generic worker success is not allowed to bypass native admission.

The managed-directory locator remains a required independent-review gate, not
an invitation to relax SS-15 into a manual-reattach pass. Retention evidence must exercise
real generated/native serialization and each observable selection/verification/
unlink/state-commit boundary in SS-16. Do not blanket-defer these races as
outside scope; keep hostile same-user behavior within the explicitly reviewed
OS lock/handle limits.

Run reviewed fixture/helper static checks before executing the helper, and
capture helper source hashes in the execution receipt. On each failure retain
the first complete failure log and exact generated state, stop dependent
cases, and do not blindly retry or remove the evidence. Run no manual rerun of
unchanged hosted jobs. Preserve all historical outcomes separately from the
current exact-head census. Root controls any public source changes and later
publication; Task 52 reviews this protocol/evidence independently.

Status oracles are phase-specific: a failure before verified publication and
durable status recording cannot advance last-success; a later retention or
cleanup failure preserves an already durably recorded success and appears as a
separate latest outcome. Acceptance can recommend only bounded evidence-backed partial progress. It
must keep unresolved host-native behavior, storage/durability limits,
unexecuted failure boundaries, and retention-policy gaps explicit. FR-RECOVERY-
003 remains Not Started unless the existing tracker is later changed by its
authorized owner after Task 52 review; this document itself makes no status
transition.


### Current handoff after W2-A

The four actual offscreen window/settings/native-backup/reopen cases are accepted
within the [public derivative](../evidence/scheduled-snapshots/window-a-attempt1/acceptance.json)
and independent receipt audit. B/C/D and W3 remain open. Next exercise the real
participating manual dialog, then integrated Stop/restart and frozen/platform
boundaries; do not interpret same-process reopen as a restart or Snapshot now as
elapsed-clock evidence. Initial PR25 hosted CI found a method-local retention
persistence capability-probe omission; the reviewed targeted correction passed
7/7 locally. Audit actual new-head CI, including Windows logs, after publication.
