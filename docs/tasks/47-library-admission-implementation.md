# Task 47 — cooperative library writer admission

Status: design revision `53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`
and executable/recovery integration are independently cleared. The two saved
full-Core failures were corrected and reviewed; focused43, full Core336 and
offscreen Qt192 checks passed. Fresh164-input runtime identity is
`597b1fbac1186a70af0e86370413b9c1d6bb82c2544f423fb3f4dee218fc913e`.
All nine frozen smokes passed within their generated/offscreen scope, including
qualified local recovery publication and actual executable refusal/reopen. Native
GUI acceptance, actual three-platform Python/Rust evidence and current-head
hosted CI remain held. This is incomplete milestone evidence.
Owner: Sol. Base: merged PR23 `99d4e471d2dd207a3f44b1408eb6eb3197bca55d`.

## User behavior and scope

A current application must acquire documented ownership before it initializes,
migrates or starts conflicting work against a live library. A second current
client receives an actionable bounded refusal; it must not silently start its
own writers. Ownership lasts through owned worker and subprocess cleanup.
Reuse within the admitted application must not deadlock against its own work.

The bounded enforcement surface is current Qt/CLI/Tauri executable entry
points and an explicit UI-independent admitted Core session API. Ordinary raw
Core/SQLite calls made without that session are nonparticipating callers, not
automatically protected application clients. Do not add a blanket connection
guard that makes legitimate children contend with their parent. Preserve
existing child handoff transactions and keep participating ownership alive
through cleanup. All three platforms retain their existing supported writer
functionality; disabling Windows/macOS writes or weakening existing tests is
not an acceptable shortcut to admission.

SDD v0.2 §§5.3, 16.3, 21.2 and 22.3 make FR-LIB-003 the primary requirement.
FR-LIB-001/002/004, FR-RECOVERY-001/002/005 and NFR-005 constrain the boundary.
This is a dependency before scheduled snapshots, not scheduling implementation.

## Design gate

Write `docs/library-admission-design.md` before material runtime edits. Inventory
Qt launcher/window/model/gateway, CLI/Core services, scanner, cache/external
workers, spawned recovery and the Rust comparison prototype. Specify which
entry points acquire, retain, delegate, validate and release ownership; identify
every intentional read-only path and any excluded writer explicitly.

Explain physical catalog identity versus logical UUID: moved/copy/restored
catalogs can share a UUID without being the same physical writable resource.
Cover relative paths, symlinks, hardlinks, missing paths, creation races,
catalog replacement while open and lock-file lifetime. PID text alone is not
ownership. Do not unlink a lock path on release if that can split contenders.
Review interactions with SQLite locks, transactions and existing inode/epoch
freshness guards. Preserve journal/synchronous settings and schema 7.

Specify thread/process lifetime, crash release, cancellation, child startup
failure, late child cleanup, fork/spawn and frozen executable behavior. A child
must not compete with its owning parent or accept an unvalidated bypass token.
An OS lease is cooperative coordination, not a security sandbox or protection
from old clients, arbitrary SQLite tools, hostile same-user code or network
filesystems. Local-storage support and unsupported/unknown platform behavior
must be explicit; no broad storage certification is implied by Linux recovery
publication qualification.

Task49 independently clears the design and adapter strategy before runtime
changes. Resolve findings before implementation. If an unsafe boundary cannot
be bounded, document the smallest defensible slice rather than weaken refusal.

## Preservation and delivery

Preserve stable UUIDs, every catalog row identity, recovery compatibility and
pending/source/standalone holds, scanner semantics, durability, original media,
cache and all 15 deployed output files. No automatic stale-lock deletion,
source-writing operation, scheduling/retention, export/relink, broker or
multi-user claim. Do not replace the deployed binary in this goal.

Implement meaningful generated multiprocess/adversarial tests after design
review. Coordinate focused and full checks with Task48; retain failures and
direct exits. Obtain scoped native and frozen evidence for changed admission
and cleanup paths. Root owns commits, draft publication and branch management.
No merge or deployment. Independent final review and exact-head CI, including
actual Windows summaries, precede completion.
