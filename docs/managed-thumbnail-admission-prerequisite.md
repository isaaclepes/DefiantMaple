# Managed thumbnail admission: internal A2 protocol

The selected policy remains **5 GiB per library, no automatic deletion**. This
increment implements a finite internal protocol using the [A1 primitives](managed-thumbnail-budget-prerequisite.md).
**No production caller uses it.** It does not activate a quota, prepare unseen
thumbnails, change the decoder, or select an account-global authority location.

## Exact scope

`managed_thumbnail_admission` takes two explicit existing private roots and a
read-only captured library association. It verifies catalog UUID, canonical
catalog path and physical identity, and binds those to captured root identities.
Matching UUID alone does not permit copies, moves, restores or root changes.
New enrollment requires an empty owned managed namespace; no legacy adoption,
permission changes, root creation or relocation is performed.

Both roots use permanent empty kernel-gate files with one common basename.
Locks follow physical-file-identity total order; aliasing/nesting, identical
locks and nested guard reuse refuse. The authority gate serializes its domains
in this first adapter. Gate waits are bounded/cancellable; filesystem syscalls
are not preempted. POSIX is the only native adapter. Unsupported platforms refuse.

Strict exclusive JSON controls are bounded at16 KiB, reject duplicate/unknown
fields and invalid numeric types, and are synced before child dispatch. Admission
counts all managed regular-file pathnames (including unknown/control/staging and
hard-link aliases) plus64 KiB/four-file/four-entry conservative outside control
allowance. It reserves41 MiB/eight-file/16-entry prospective overlap using the
reviewed conservative arithmetic. This is cooperating admission, not physical
filesystem/global-account quota or a claim about older/external writers.

One pending operation is persisted before at most one child may start. Unknown
prior pending, ambiguous startup, live child, changed association/control or
incomplete/over-ceiling inventory holds admission. PID/age does not reclaim it.
Actual decoder output limits and publication are not wired in this increment.
Callers must use reviewed non-delegating child targets: a descendant-spawning
process cannot establish whole-tree exit merely by its parent's exit code.

`finish()` and `rollback_known()` require all registered children to have concrete
terminal results, exact control ownership and retained metadata/digest identity (same-content
replacement still refuses), fresh association, complete bounded
inventory, and observed managed usage including pending **plus outside control
allowance at/below every ceiling**. They release only that operation's owned
pending control. A known pre-dispatch refusal or joined decoder failure can
therefore release without permanently blocking future work. A still-live guard
can roll back exclusively created interrupted-enrollment controls under the
same ownership/inventory proof. No image, manifest, unrelated or substituted
file is deleted. Context exit alone never silently reclaims pending.

Unknown prior-owner loss remains **recovery-held**, even after a possible orphan
exits. Cross-process recovery eligibility is deliberately unresolved here; no
PID disappearance, timeout or apparently empty directory substitutes for proof.
A3 must settle this before production use. Terminal unlink is a visible process
outcome, not a power-loss-durable removal guarantee; a replayed pending fails
closed. Required metadata sync occurs before the terminal unlink so there is no
post-unlink sync failure falsely described as retained ownership.

## Descriptor and fork lifetime

The protocol owns its pinned/gate/control fds. A process-local mutex covers exact
open/register and unregister/close boundaries, including finite root pinning;
these syscalls may block. It never covers lock retries, inventory or child
startup. A fork before-hook waits for that boundary. Its child hook closes exact
inherited fds **without LOCK_UN**, clears copied handle state and prevents copied
guard use through owner-PID checks. CLOEXEC alone is not treated as fork safety.
Fork from inside this critical section or an interrupting signal handler is
unsupported; ordinary concurrent fork is covered by a deterministic event-barrier
regression. This is not a general claim that arbitrary multithreaded Python/Qt
fork is safe. The production decoder continues to require spawn.

## Evidence and next gate

Generated tests cover two-process contention/progress; pending-before-child;
known enrollment/partial-write/start-precondition/child-failure rollback;
ambiguous start held; canceled dispatch; changed catalog/root/copy/custom root;
strict controls and substitution; prospective/terminal usage including outside
controls; same-process alias/nesting; fork close without releasing parent locks;
open/register concurrent-fork barrier; and lost owner with a live bounded child.
Linux pidfd observes/signals that orphan exactly; that test explicitly skips on
platforms without this facility. No real account registry or user library/media/catalog,
native UI or large performance probe is used.

A3 still needs one unique production authority decision, known-safe interrupted
owner recovery, supported native adapters, supervised filesystem lifetime,
mandatory integration of every writer, bounded owned staging, no-clobber PNG and
manifest publication, and legacy-read routing. Only after these pass review may
visible-first background disk preparation use the existing bounded worker/queue
with a finite nonstarvation rule. No extra pipeline, pruning, source-health or
asset-metadata mutation is authorized by this internal increment.
