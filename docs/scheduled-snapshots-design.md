# Scheduled local metadata snapshots

Design candidate for Task50, based on merged PR24
`47effeeb5a5adf8b692023c49b67ee52a9025559`. Independent Task52 clearance is
required before runtime changes. Task51 owns the separate acceptance protocol.
SDD v0.2 §16.3 FR-RECOVERY-003 is the primary requirement; §§21–22 determine
evidence and scope. This document specifies an application feature, not a Codex
automation or installed OS task.

## User contract

Scheduling is off by default. An admitted Qt library window can explicitly
enable metadata-only snapshots, choose a supported destination and interval,
and see last verified success, latest attempt/failure and next due state.
The UI states that snapshots run only while this application/library is open:
closing, sleeping or powering off the machine does not run a background task.
The package includes private catalog metadata/absolute paths and omits original
media, derived caches/previews and out-of-catalog settings/credentials, exactly
as manual recovery does. It is neither portable export nor a scrubbed package.

Default interval is24 hours, configurable from15 minutes to30 days. Enabling a
new schedule makes one immediate attempt after configuration is durably saved;
the UI previews that first attempt before Enable. A due schedule runs at the
next idle recovery slot; it never starts multiple catch-up runs. A manual
"Snapshot now" uses the same coordinator and managed package/verification
pipeline. Existing manual backup/inspect/restore remain available and retain
their current behavior; unmanaged manual packages are never retention targets.

Retention deletion is separately off by default. Users may enable a policy
with keep-count1–1000 and/or managed-byte budget1 MiB–1 TiB. The UI describes
that only this schedule's verified managed packages may be removed, oldest
publication sequence first, while at least one currently verified package is
preserved. With deletion off, count/byte limits are stop-before-next-run caps;
no automatic cleanup is performed. A disabled schedule runs nothing and deletes
nothing; disabling retention prevents future pruning, including after restart.
Cancellation/disable during an operation is cooperative: cleanup must finish,
and already durable publication/deletion is reported rather than rolled back
or mislabeled as canceled-without-effects.

## Supported storage and unchanged behavior

Reuse the existing recovery `private_local_parent` adapter and its exact
qualified Linux durable-local backing policy. Configure a new, private,
dedicated managed directory beneath a user-selected eligible parent; creation
is explicit through Enable, never by a timer discovering a missing directory.
Use0700 directories/0600 state files and validate existing ownership/type/mode.
Reject symlink components, reparse/nonregular paths, unsupported backing, source
or cache containment, catalog family collisions and unsafe inherited paths;
do not repair permissions silently. The dedicated directory cannot contain
another schedule's state or be shared by two schedules.

On Windows/macOS the current publication adapter refuses scheduled enable/run
with its actionable unsupported explanation. Do not disable existing catalog
writes or alter existing manual recovery paths to make scheduling appear
crossplatform. Do not infer removable/network/sync safety merely because a path
looks local; retain the existing qualified backing boundary and no universal
active-sync detection claim. No HOME/XDG override changes admission registry
selection. Other native adapters require a separate reviewed extension.

## Managed identity and process coordination

The managed directory contains one versioned `schedule.json`, one permanent
`schedule.lock`, generated packages and this operation's private stages. A
random schedule UUID identifies this directory/ledger; it is not writer
authority. Configuration binds the canonical catalog pathname, library UUID,
native physical file identity and physical parent identity using the admission
adapter; directory binding includes its native physical identity. The state is
private local data, not catalog metadata and is not included in backup packages.
No catalog schema, application_id, SQLite journal or synchronous setting changes.

The window must already own the catalog admission session. The UI-independent
API accepts the actual in-process session, validates it before each operation,
and retains an explicit reference until its real worker and cleanup complete.
No serialized owner token, boolean bypass or independent source-writing child
is introduced. `backup_metadata` retains its real source backup child through
the existing ownership/reaper path. Timer, manual Snapshot now and manual
recovery controls share one operation coordinator; they queue at most one due
intent. Recovery restore still owns its own absent destination as before.

Take a nonblocking exclusive native lock on the permanent schedule.lock before
reading or mutating schedule state/packages. Use the reviewed admission lock
primitive with a distinct schedule namespace, no stale deletion and no wait
loop. Retain directory/file handles and revalidate the pinned directory before
each state/publication/deletion boundary. Lock acquisition failure is visible
busy; do not run an unlocked schedule. A second current application is already
refused by catalog admission; the schedule lock also prevents two configuration
coordinators/explicit Core schedule operations from splitting the managed set.
Unknown adapters/errors refuse. Do not hold a transient catalog directory gate
for the schedule lifetime; normal admission semantics remain unchanged.

Aliases resolve to the existing owner/binding; a physical copy sharing the UUID
does not inherit its schedule. A different path, replacement, moved catalog,
changed parent or changed managed directory suspends scheduling before backup
or pruning. The user may explicitly create a new schedule for the newly opened
catalog, leaving old packages/state intact. This increment does not rebind or
auto-discover moved/copied schedules. A restored browse-only catalog may have
its metadata backed up without clearing its holds; it never inherits automatic
scheduling from the package. Scheduler reads never scan originals or enable
restored sources/rules.

## State, bounded persistence and discovery

One bounded, strict versioned JSON state document contains schedule identity,
catalog/directory bindings, configuration revision, enabled flags, interval,
policy limits, monotonically increasing publication sequence, last verified
success record, latest attempt/outcome, package ledger and ordered audit events.
State values use typed finite integers, UTC timestamps, exact safe generated
leaf names and bounded error codes/messages. Reject unknown versions/fields,
duplicate keys, invalid types/lengths, out-of-range numbers and inconsistent
identities before any package mutation. Maximum state4 MiB,1024 ledger entries
and4096 audit records are design limits; do not silently evict history to fit.
If exhausted, suspend new scheduling/pruning with an actionable explanation;
manual recovery outside the managed directory remains available. Audit export/
reset/compaction is a future explicit operation, not hidden automatic deletion.

Persist state through a newly created same-directory0600 stage, bounded write,
file fsync, atomic replacement of the checked state entry and directory fsync.
Initial creation is absent-only; existing state identity/version/config revision
is rechecked under the schedule lock before replacement. A partial stage never
becomes authoritative state. Never blindly sweep unknown stage/package files;
cleanup applies only to exact files created/pinned by the current operation.
Failures after replacement but before confirmed directory fsync are uncertain:
suspend automatic work and require state re-read/reconciliation on reopen.

An unchanged eligible library automatically resumes its configured schedule and
status on application reopen. Persist a bounded private per-user locator under
the application's existing application-data root (`default_private_root().parent`),
in a dedicated `scheduled-snapshots-v1` directory. This reuses the application's
private settings location, not its evaluation database. Dependency-injected
private roots support generated tests; they never select an admission registry.
Validate containment outside catalog/source/cache trees and reject symlinks,
unsafe ownership/type/permissions and failed native persistence checks. Create
the dedicated directory0700 and locator/stage files0600. No disk search,
UUID-only matching or catalog mutation is used for discovery.

Each locator filename is SHA256 of a versioned prefix plus the canonical catalog
pathname bytes (POSIX filesystem bytes; Windows UTF16LE), followed by `.json`.
Do not guess filesystem case/Unicode equivalence. Its strict versioned document
is at most64 KiB and records canonical path, native catalog parent/file identities,
library UUID, managed-directory path/physical identity, schedule UUID and config
revision. It is a private settings pointer, never ownership authority or a
serialized admission bypass. Backup packages omit it. Copies sharing a logical
UUID cannot inherit the original schedule through this locator.

Explicit Enable/configure persists schedule state and locator with matching
configuration revisions before a timer can start. Configuration revisions are
monotonic per locator key, including destination changes that create a new
schedule UUID; a stale UI revision cannot become valid again after such a change.
Use a permanent nonblocking native lock per locator key, then the old managed
schedule lock if configured, then the new managed schedule lock if distinct.
Discovery takes locator then its current managed lock. No managed-held operation
acquires the locator lock. A new destination must be absent, separate from the
old directory and not its ancestor/descendant; it cannot adopt another schedule.
Before creating or acknowledging a new destination, read/validate the old managed
directory identity and exact state/locator under its lock, refuse in-progress,
cleanup-pending, uncertain or warning states, and retain old quiescence through
the complete commit. Recheck the unchanged old state before pointer publication.
Persist each document through a new bounded same-directory stage, file fsync,
atomic checked-target replacement and parent fsync. Initial creation is absent-
only. Never silently repair/truncate invalid documents. Two directories do not
form an atomic transaction. Maintain a permanent strict typed transition record
per locator key (`<locator leaf>.transition`), at most128 KiB, containing the
prospective complete locator, operation UUID and `pending`/`committed` phase.
Under the locks, durably publish its pending intent before new schedule state,
then persist state, matching locator and exact pair readback, then durably mark
the transition committed and verify it before acknowledging configuration.
Do not delete or silently discard the transition record. Discovery checks it
even if the normal locator is absent: pending or mismatched completion suspends
automatic work. This prevents destination-change failure from resuming an old
enabled locator/state pair that still matches. A committed record must match
the exact current locator. Interrupted/mismatched revisions suspend work with
actionable recovery, never an older-policy fallback. Changing destination creates a new
explicitly selected managed schedule and updates the locator; old packages/state
remain intact and are not pruned.

On library startup, after actual admission and authenticated UUID read, perform
the single exact-key locator lookup off the GUI thread. Validate its full binding
and matching managed-state revision under the locks, load enabled settings/status
and reconcile package facts before scheduling. An unchanged original library
needs no directory reselection or repeated Enable. Changed catalog/parent/
destination identity, path mismatch, replaced file or invalid state suspends the
configured schedule before backup/pruning; show the reason and offer explicit
new configuration. A copy/move opened under a new canonical pathname has no
matching locator and remains unconfigured, with explicit "No schedule configured
for this library location" status; do not search another locator or follow its
UUID. Reconfiguring it cannot mutate the original schedule's packages. Failed
locator reads are distinguishable from absence and cannot silently become "off"
or erase a saved success record.

Authenticate the current supported schema/application state/library identity on
the read-only source connection before querying source-root rows, including an
absent-locator lookup. Preserve recovery's native SQLite busy/locked errors and
restored-source holds. Reject the live catalog and all `-journal`/`-wal`/`-shm`
family paths, including descendants, as configuration targets before any mkdir
or lock creation; scheduler storage must not obstruct existing SQLite writers.

Audit records contain a sequence, operation ID, config revision, UTC time,
event/outcome code, package leaf/digest/size/physical identity when applicable
and bounded error details. They never assert deletion/publication succeeded
before that boundary is verified. This ledger records application actions,
not a tamper-proof security audit against hostile same-user code.

## Due state and clocks

Expose a UI-independent state machine with injected UTC/monotonic clocks and
explicit poll/enable/disable/start/cancel/completion events. QTimer is a wakeup
source only; blocking backup/inspection/state/pruning work runs off the GUI
thread. In a running process, use monotonic time to schedule the interval after
the latest completed attempt, preventing wall-clock adjustments from triggering
duplicate work. No tight polling: wake at most once per minute plus explicit
UI/job events. At most one operation is active and one due intent is pending.

On validated automatic reopen/restart, compare saved last completed attempt UTC to now. If
the interval elapsed, perform at most one due attempt after recovery becomes
idle. If the wall clock is earlier than the recorded attempt, show clock-change
status and wait one complete interval on the new monotonic clock; do not invent
a past/future success or replay runs. A crash with a saved in-progress attempt
is shown as interrupted, not success; reconcile managed files first and then
allow one fresh attempt. Sleep/resume yields one overdue attempt, not a backlog.
Failures use the configured interval before automatic retry; Snapshot now can
retry explicitly. Disabling/reconfiguring clears pending intent; interval edits
schedule relative to the latest completion and do not create concurrent work.

## Backup, verification and truthful status

1. Acquire coordinator/schedule lock, validate live admission/bindings and state.
   Persist attempt-start audit/state before source backup begins. If that fails,
   do not start a child or prune. Check stop caps, state capacity and destination
   eligibility. Free-space estimates are advisory; real I/O failures are handled.
2. Allocate an absent generated package leaf from schedule ID, publication
   sequence and random operation nonce; no timestamp-only collisions. Invoke
   real `backup_metadata` with cancellation/deadline policy unchanged. Its child
   reads the source through the existing validated read-only backup path.
3. Require actual child termination/cleanup, closed published package and real
   `inspect_package` verification; compare expected manifest/library UUID/schema
   and returned snapshot facts. Record current physical identity, complete
   package digest/size and verified UTC. No casual main-file copy is used.
4. Durably record the verified package ledger entry/publication sequence and
   last-success timestamp before any retention deletion. If state recording
   fails after publication, report "package published; status uncertain" and
   suspend automatic work. Do not delete the package or advance displayed durable
   last-success based solely on an in-memory success result.
5. If explicitly enabled and still current, run retention below; persist final
   attempt outcome. Track publication, package verification, durable success
   registration, pruning and worker cleanup as separate phase outcomes. A
   durably registered verified backup followed by pruning or cleanup failure
   retains its verified-success record with a distinct warning and suspended
   automatic work until actual cleanup/reconciliation completes. Never replace
   that success with a false "no backup created" outcome, or claim overall
   attempt/cleanup success while a child remains alive. Publication without
   confirmed verification/registration stays uncertain, not a durable success.
   Keep last-success visible
   alongside latest failure/uncertainty; never present a stale saved timestamp
   as proof that its package is currently available/verified.

On reopen, verify a recorded last-success package through the real inspector
before labeling it a currently verified recovery point. Missing/changed/corrupt
packages remain visible as unavailable/invalid; historical last-success time is
retained with that qualification. Scan only bounded exact ledger entries.
Unknown packages, unrecorded publication or unfinished deletion intents suspend
pruning and are displayed for explicit review; do not automatically adopt,
overwrite or remove them. Manual inspection/recovery remains available.

## Retention and storage safety

Retention runs only after durable registration of a new verified package, under
the same lock and current explicitly enabled configuration revision. No pruning
occurs merely on launch, during failure/cancellation, or to make room before a
new successful backup. Limits count this schedule's present recorded packages;
foreign files contribute to filesystem pressure but are never deletion targets.
If deletion is disabled or cannot safely meet limits, show storage-limit status
and suspend automatic runs instead of growing without bound. A single package
may exceed the configured byte budget: keep it as the last verified point,
report the exception and stop automatic runs pending policy/user action.

Before deleting anything, revalidate state/directory/catalog bindings and
configuration, and inspect both the candidate and a distinct survivor using
the actual package pipeline. Require ledger-matching schedule-generated leaf,
native file identity, regular/non-symlink type, link count1, size and digest.
Verify survivor UUID/schema/integrity and ensure it remains available before
each deletion. A candidate must be in this exact ledger and older than the
survivor's publication sequence; never select by glob, mtime or UUID alone.
One corrupt/missing/mismatched ledger entry suspends pruning; it is not silently
discarded from accounting. Unrelated files remain untouched even if named like
a package, and manual packages cannot become candidates through directory scan.

Actual package readers require native physical-file leases, independently of
catalog admission. On the currently qualified Linux local-storage adapter,
`_read_package` takes a nonblocking shared `flock` on its exact nofollow read-only
package descriptor before reading the header; it holds that lease through
snapshot extraction, digest/schema verification and the descriptor's existing
close. Both original manual inspection and original restore use this path.
Concurrent readers remain compatible. Busy is a typed bounded refusal, not a
wait or permission to bypass retention. No registry, sidecar, package write access
or package-format change is introduced. The adapter's existing platform refusal
runs first, so current Windows/macOS unsupported publication behavior and
platform-neutral validation paths remain unchanged. A future native publication
adapter must also qualify equivalent package leases before enabling retention.

Before deletion, reap the exact candidate/survivor inspection children, then hold
an exclusive native lease on the candidate's pinned descriptor and a shared lease
on the distinct survivor's descriptor. Acquire in deterministic native-identity
order without waiting; an incompatible reader makes pruning stop. Caller-supplied
hold observations can only veto work and never replace real native leases.
Candidate verification precedes its exclusive lease; rehash its pinned descriptor
after acquisition. Do not launch a candidate shared reader while its exclusive
lease is held. Reinspect the survivor through the actual shared-reader pipeline
while its compatible shared lease is held, then prove that child exited and its
stages are clean. Keep both pinned leases through final identity/digest checks,
unlink, directory fsync and durable ledger completion. Readers revalidate their
named identity after acquiring their lease and refuse a name removed/replaced
before their read. Fork-child inherited lease descriptors close without unlocking
the parent's shared open description; spawned workers open their own descriptors.
Exceptions, cancellation and actual child exit must release descriptors/leases,
with no assumption that a UI timeout means release. This is a cooperative native
lease boundary, not protection against nonparticipating raw file mutation.

Persist a delete-intent audit record naming candidate/survivor facts before
unlink. Immediately recheck the pinned directory and candidate/survivor path
identities/metadata under the lock, unlink only the exact candidate leaf through
the pinned dirfd, then fsync the directory. Finally persist delete-completed and
ledger removal. Interrupted intent or post-unlink fsync/state failure suspends
further deletions; reopening distinguishes exact candidate still present,
absent, or changed, displays uncertainty and preserves the survivor. Never
silently retry an uncertain deletion or delete the survivor to reconcile state.

This is same-user cooperative management of a private dedicated local directory.
The protocol detects observed replacement before its last check; it does not
provide atomic unlink-by-file-identity or protect against hostile/nonparticipating
same-user code racing after that check. Do not claim universal protection against
such races. Under this explicit cooperative boundary, separately enabled
retention is a required implemented feature, not deferred in favor of scheduling
alone. An unverifiable invariant suspends that operation with its reason; never
bypass checks or delete a recovery point to satisfy a budget. The exact native
deletion implementation requires independent review and fault tests at every
observable replacement, intent, unlink, fsync and ledger-completion boundary
before execution clearance.

## Shutdown, cancellation and resource ownership

The scheduler stops accepting due/manual requests when closing/disabling;
requests cancellation and keeps the application session/coordinator until real
backup/inspection workers and retention I/O finish. A UI timeout is not proof
of exit. Reuse recovery's bounded cancellation/reaping and admission's strong
process references, including startup/retention failure and late child exit.
Do not release on delivery of a result signal alone. Retention checks cancellation
before durable delete-intent; after intent, resolve/report its single boundary
before stopping. No new product5-second cleanup deadline is introduced.

## Review and acceptance handoff

Task51 must name exact generated oracles for default-off/explicit enable,
interval/clock/restart and automatic unchanged-library reopen, interrupted
locator/state revisions, copy/move/replacement suspension, no overlap with manual
recovery, actual
source-child retention and close/cancel/restart, verification/status persistence,
managed copy/move/replacement refusal, policy consent/stop caps, foreign files,
last-point protection, package corruption, interrupted intents and state limits.
Inject faults before/after publication, state replacement/fsync and each deletion
boundary; compare original catalog/package/media/cache and expected ledger/audit
deltas. Restore an actual scheduled package into a new qualified destination and
verify schema7, library/asset IDs, all rows and paused restored-source holds.

Freeze runtime/test/build inputs and15 deployed outputs around helpers; preserve
failed attempts and direct exits. Separate unit/real-process/offscreen/native/
frozen/hosted evidence, actual platform skips and capability refusals. No existing
Windows/macOS behavior is disabled. Reuse unchanged reviewed component evidence
with exact hashes; do not automatically rerun unrelated CI or experiments.
Root publishes the reviewed draft; no merge/output deployment follows from this
design. Full Phase1a/recovery/platform/storage acceptance remains separate.


## Cleared desktop integration contract: durable control and ownership

Desktop wiring follows two review gates. Gate A adds an independent private
per-locator control document and permanent control lock, plus a shared admitted
manual-recovery actor. Gate B connects asynchronous discovery, status/settings,
and bounded next-deadline wakeups (at most once per minute plus explicit UI/job
events). Active-child cleanup polling is separate from schedule triggering.

A saved stop vetoes future scheduled work without changing configuration revision,
managed deletion intent, ledger or historic success. The stop writer takes only
the independent control lock; configuration/operation ordering is locator, old
managed directory, new managed directory, package leases, then control last.
Explicit Enable captures its expected control CAS at the human action before
waiting for locks. A newer stop cannot be overwritten by a queued older Enable
or older cleanup acknowledgment. Missing/malformed/mismatched configured control
suspends rather than falling back to an enabled policy. Existing development
records require explicit same-directory configuration preserving their history.

Only the originating live controller session may promote its exact saved request
UUID/version to stopped, with unchanged catalog/configuration, no queued work,
actual worker-thread completion and proven cleanup of its actual children/stages.
The stop writer retains the admitted owner through durable readback and releases
its control lock before UI acknowledgment. After restart, a saved stop request
remains a veto with prior cleanup UNKNOWN: no PID-absence inference, automatic
Enable or implied repair engine. Saved-stop and cleanup-review status are distinct.

If an explicit Enable durably publishes an exact valid run record but loses its
UI/readback acknowledgment, the live session may remain uncertain. Reopening may
validate and reconcile that actual committed run; no extra two-phase run record,
false rollback or duplicate Enable is required. Prepublication, missing or
mismatched control remains a veto, and a later stop still wins its CAS ordering.

The manual actor uses the same per-owner operation slot as scheduled recovery
and holds admission until actual worker completion and exact process/stage
cleanup. Inspect always needs source-owner retention; restore also needs it when
its live catalog is absent or belongs to another owner. Default standalone manual
behavior remains unchanged. Original recovery cleanup alone deletes its stages;
recreated names suspend and are never removed by a second cleanup pass.

Required evidence includes Enable/Disable races, newer stop versus older cleanup
acknowledgment, lost acknowledgments, restart uncertainty, callback/start failure,
and actual child lifetime under shared manual/scheduled exclusion. Qt/native/
frozen and cross-platform qualification remain separate acceptance gates.


Controlled Enable borrows the original configure transaction's authenticated old
and new stores/state under the same retained admitted owner and shared operation
slot. Actual package inspection and exact child cleanup precede control-last
acquisition; it never recursively opens SnapshotOperations or reacquires those
native locator/managed locks. Borrowed stores expire with their original
ExitStack and cannot be retained, closed or reused by the hook. Unreaped children
keep actual owner/slot references until their own cleanup is proven.

A saved stop vetoes the next validation checkpoint and future scheduled work. A
bounded unlink that already passed its final checkpoint may complete while the
saved-stop status awaits actual cleanup. There is no promise of linearizable
absence of unlink after stop-save, and no control lock spans worker waits, unlink,
directory fsync or ledger completion. Request saved and stopped are separate
acknowledgments; stopped requires the exact live-session cleanup proof above.


A scheduled Qt job supplies a fresh external `threading.Event` to its one-job
`SnapshotOperations` actor before assigning that actor to the controller. Core
never clears this external event and refuses a pre-set request before native
store/SQLite work. The default internally owned event retains the original
reusable-actor reset behavior. A job canceled before `QThread.run` performs no
discovery or dispatch; cancellation during startup is rechecked before original
recovery APIs. An action already past its final cancellation check may start
bounded child work, which remains owned until actual cancellation/cleanup and
thread completion; no atomic cancel-versus-spawn guarantee is implied.
