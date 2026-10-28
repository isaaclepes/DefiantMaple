# Task 50 — scheduled local metadata snapshots

Status: design/brief stage; runtime work requires independent Task52 design
clearance. Base: merged PR24 `47effeeb5a5adf8b692023c49b67ee52a9025559`.
Implementation owner: Sol; acceptance/CI: Luna (Task51); independent review:
Task52. The next available task numbers are50–52.

## Objective and contract

Implement the bounded FR-RECOVERY-003 increment specified by
[the design](../scheduled-snapshots-design.md): explicitly enabled metadata-only
snapshots while the admitted Qt application is running, visible last-success
and current failure/status, configurable interval/destination/storage policy,
and separately enabled bounded retention. Never silently delete the last
verified recovery point or touch unrelated files. No OS service, background
daemon, media-inclusive backup, portable export, relink, or deployment is added.

Use existing SQLite-consistent backup/inspection and qualified local publication;
retain admission through actual worker cleanup. Preserve schema7, UUIDs/rows,
journal/synchronous policy, scanner/source/recovery holds, original media/cache,
existing manual Windows/macOS behavior and all15 deployed outputs. Unsupported
scheduled publication is a visible refusal, never an unlocked/silent fallback.

## Staged implementation targets

1. Obtain exact design clearance; resolve reviewer findings before runtime edits.
   Task51 prepares named acceptance oracles independently of implementation.
2. Add UI-independent validated schedule/state types, bounded atomic state I/O,
   physical catalog/destination binding, a durable private per-user locator for
   automatic unchanged-library reopen, and a clock-injected due-state machine.
   Use permanent bounded pending/committed transition records and per-key
   monotonic revisions to prevent interrupted destination changes from resuming
   an old matching enabled configuration. Lock locator, old managed schedule,
   then distinct new schedule; validate/retain old quiescence through commit.
   Test timing/restart, malformed state and identity refusal without live media.
3. Add one owned operation coordinator around real recovery backup/inspection,
   durable ledger/status transitions and retention with revalidation/journaling.
   Review destructive boundaries before enabling pruning in generated tests.
4. Integrate Qt settings/status and one timer plus cancellable worker; share the
   existing recovery operation exclusion. Close waits for actual worker exit.
   Preserve manual recovery behavior on every existing platform.
5. Run affected focused/full checks, generated native/frozen lifecycle evidence
   and actual current-head platform jobs as specified by Task51. Reconcile each
   claim and skip; independently review preservation/privacy before publishing a
   draft PR. Root owns branch publication, merge and any later deployment.

## Acceptance handoff

Name scenarios for opt-in/default-off, due/restart/clock behavior, one operation
at a time, actual backup-child retention, cancellation/late cleanup, publication
uncertainty and truthful last-success. Use the real previous package producer
or unchanged reviewed compatibility evidence where justified. Restore a
scheduled package into a new destination and verify rows/UUID/settings/holds.

Reopen must automatically load the unchanged library schedule/status through its
validated private locator; no manual directory reattachment is required. Test
interrupted locator/state revisions and copy/move/replacement suspension.
Phase-specific success records survive later pruning/cleanup warnings without
claiming overall completion before actual worker exit.

Retention is required under the documented cooperative private-directory
boundary; unverifiable invariants suspend operations, never remove the feature.
Retention tests must include last verified point, corrupt/missing/changed
candidates, foreign files/links, changed destination/catalog, interrupted delete
and state update, audit/state exhaustion, count/byte limits and an oversized
single recovery point. Preserve failed attempts; no fixture skip is a pass.
Freeze source inputs and all15 output records before each material helper run.
Use only disposable generated catalogs/media/private directories.

## Governing requirements and limits

SDD v0.2 §§16.3,21.1–21.2,22: FR-RECOVERY-003 primary;
FR-LIB-003/004, FR-RECOVERY-001/002/004/005 and
NFR-003/005/007/008/015 constrain implementation. FR-RECOVERY-007's full Phase2
mutation matrix is not claimed, but faults at this increment's own publication,
state and deletion boundaries are required. Preserve all129 tracker IDs; change
only evidence/status justified by this increment. Full FR-RECOVERY-003, recovery,
crossplatform desktop and release acceptance are not inferred from a draft.

## Mandatory package-reader lease gate

Retention requires real physical package-use leases across the original manual
inspection and restore read path, in addition to library admission and the
schedule operation slot. The qualified Linux adapter uses compatible shared
leases on the actual read-only package descriptors; pruning needs an exclusive
candidate lease and shared distinct-survivor lease through durable completion.
Observed hold lists and actor child cleanup are additional checks, not authority
to assume unrelated readers absent. Preserve current manual package format,
read-only permissions, concurrent readers and existing unsupported Windows/macOS
publication behavior. No user-profile lease registry or sidecar is needed.

Implement/review the nondeletion reader and reusable pinned-descriptor primitive
first. Evidence must prove actual independent manual inspection readers and a
restore reader block exclusive acquisition, typed bounded busy results,
exception/cancellation/crash release, unchanged source/package bytes, and no fork
or spawned-descriptor leak. Revalidate named identity after lease acquisition.
The exact source and generated helper require independent review before workers
run; native retention unlink and backup-cap integration remain a separate held
gate. The planned native executor must never inspect the candidate through a
shared child while holding its own exclusive candidate lease; final survivor
inspection remains compatible with the parent's shared survivor lease.


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


### Implementation checkpoint and next boundary

Draft PR25 contains the reviewed implementation. The owned initialization-thread
fix passed 52 focused checks, and the first original window/settings/native
fixture passed four bounded cases with independent audit. These do not qualify
actual manual-dialog, integrated Stop/restart, visible/frozen or full-platform
behavior. Next prepare exact original manual backup/restore/mapping/review/enable
and contention/close fixtures without bypassing startup, admission or holds.
Preserve all deployed outputs and reuse unchanged accepted lower-layer evidence.
