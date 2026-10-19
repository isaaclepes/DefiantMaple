# Task 49 — independent library admission review

Status: exact design, executable/recovery integration, runtime corrections,
platform test-oracle fixes and named local/frozen/native evidence have review
records. Independent review accepted native Linux xcb/XWayland lifecycle,
offscreen active ScanWorker cancellation/restart and actual prior-producer/
admitted-recovery, gate, migration-fault and SQLite limitation/busy bridges.
Exact implementation/publication-head CI and final sanitized evidence/privacy
review are required and recorded with the final head in the draft PR before goal
completion; the implementation-head audit was incomplete at preparation. No full FR-LIB-003, other-OS GUI, portal,
unsupported-storage or release qualification is implied.
Owner: independent Sol.
Implementation: [Task47](47-library-admission-implementation.md).
Acceptance: [Task48](48-library-admission-acceptance.md).

Review the design before material lock/admission changes. Independently trace
all live-writer entry points and direct SQLite bypasses, including the Rust
comparison prototype and spawned workers. Check physical-resource identity,
aliases/copies, path replacement, missing-target reservation, lock lifetime,
crash cleanup, same-process nesting and child delegation. Do not accept UUID or
PID-only ownership, unsafe stale-lock deletion, implicit platform assumptions,
or a cooperative protocol presented as protection from old/external clients.

Review platform adapter semantics using primary documentation where needed.
Separate live-catalog placement from the narrow Linux backup-publication
adapter. Specify a defensible supported/refused boundary and document any gap
before implementation. Review effects on SQLite locking and durability without
changing journal/synchronous settings.

Review incremental implementation and meaningful tests, scoped native/frozen
helper proposals before execution, and resulting raw receipts and databases.
Independently validate source freeze and all 15 deployed outputs. Confirm
preserved UUIDs/rows, schema 7, scanner/recovery/source holds, read-only paths,
late worker cleanup and prior recovery-package compatibility.

Record design clearance, concrete findings/resolution and final exact-file
evidence/privacy clearance in `docs/library-admission-review.md`. Public status
must match actual tests and platform execution; missing tests remain held.
Verify actual current-head CI and Windows summaries with Task48. Root owns
commits and draft PR publication. No output writes, source/media mutation,
merge or deployment; no full SDD/release acceptance implied.
