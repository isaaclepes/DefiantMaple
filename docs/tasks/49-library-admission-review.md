# Task 49 — independent library admission review

Status: exact design and focused integration cleared; full-suite correction,
native/frozen evidence, publication privacy and final review remain held.
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
