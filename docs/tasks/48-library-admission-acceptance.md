# Task 48 — library admission acceptance

Status: local named admission acceptance evidence is independently reviewed.
Exact publication-head platform CI and final evidence/privacy review are required
and recorded in the draft PR before goal completion. Owner: Luna.
Implementation: [Task47](47-library-admission-implementation.md).
Independent review: [Task49](49-library-admission-review.md).

Independently reviewed local evidence now includes the native Qt lifecycle
on Linux KDE Wayland through Qt xcb/XWayland, the offscreen production
GalleryWindow/ScanWorker cancellation and restart scenario, and actual
recovery compatibility from the prior PR23 producer with admitted backup, held-destination
refusal, directory-gate, migration-fault and SQLite limitation/busy bridges.
Native lifecycle covers an owned idle child; active writer cancellation is a
separate offscreen QThread case. Native Wayland protocol, host portal
registration and native Windows/macOS or Tauri GUI qualification are not claimed.

Earlier full Core 336, offscreen Qt 192 and nine frozen Linux smokes retain their
recorded input/component scope. The current implementation/test reference is
`806a42f65d8cab29311ff63e5801f8e063cf2046`, tree
`2bdbd9d462596c6e56975f4785bc2b2243c1b47b`, with 165 inputs and runtime ID
`3dbfd3456eda0983a584ac491c4a7cd447698bd18f0068cd3b32b104107a9c59`.
The implementation-head CI audit was incomplete at preparation. Actual
publication-head conclusions, totals and skip reasons are recorded in the draft
PR before goal completion; no unobserved check success is claimed. Preserve the earlier Windows replacement
and macOS alias-oracle failures and their reviewed test-only corrections.

The [results](../library-admission-results.md) and [case protocol](../library-admission-acceptance.md)
identify each tested reference and evidence class. Later documentation-head CI
is recorded in the draft PR after its checks complete; no document claims an
unobserved pass for its own future commit. No full requirement/release acceptance,
merge, deployment or output replacement is included.

Prepare `docs/library-admission-acceptance.md` with named cases and exact
oracles against the reviewed design. Use fictional private fixtures only.
Distinguish current cooperative clients, historical clients and external SQLite
writers. Explicitly retain the old-client and unsupported-storage limitations.

Cover two real processes competing, same-process nested services/threads,
normal release, owner crash, contender refusal without mutation, bounded
refusal timing, inherited/spawned worker cleanup, cancellation and restart.
Exercise alias/copy/UUID distinctions, missing target creation races and
replacement freshness. Use real platform adapters when claiming their support;
an injected Windows result on Linux is not Windows execution.

Verify migration ownership begins before mutation/backup, restoration publishes
only isolated destinations and leaves holds intact, and the live source owner
can complete legitimate spawned recovery without opening a bypass for another
application. Retain read-only inspection and prior package compatibility within
the documented contract. Verify no source/cache/output changes and unchanged
SQLite durability settings, UUIDs and catalog metadata.

Capture source freeze, environment, exact commands, direct exits and raw hashes.
Run relevant focused and full suites after material implementation changes;
reuse unchanged evidence within scope rather than repeat it indiscriminately.
Native desktop and frozen subprocess evidence require separate named claims,
reviewed generated-fixture helpers and real desktop availability. Do not launch
the app against the user's actual library for acceptance.

Audit all actually triggered current-head workflows and actual Windows test
totals and named skips. Preserve failed/interrupted attempts; never equate a
wrapper success or platform skip with supported behavior. Do not cancel/rerun
unchanged jobs. Keep private paths, IDs, catalogs and raw logs outside public
evidence. Publish a sanitized results MD/JSON only after Task49 review.

No output deployment, source-file mutation, commit, push or merge. Root owns
publication. Finish with bounded acceptance and an explicit remaining-limit
record, not full FR-LIB-003 or release acceptance without its evidence.
