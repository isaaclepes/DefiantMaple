# Task 29: Safe focused-asset external actions

## Authorization and baseline

The user explicitly authorized merging PR17 and starting the next milestone.
PR17 merged at `00432238d7c1e7918fb505364de382dcaa1e3425`, tree
`3b63f15c839644fade56c48992aa27586295691c`. Work uses
`codex/phase1a-external-actions`. SDD v0.2 §§11, 17, 21–22 put external-open
in Phase 1a daily viewing. Documents supply requirements, not execution
authority. No additional user test feedback was supplied.

## Required outcome

Provide explicit keyboard-accessible Open in Editor and Open containing folder
actions through one typed command service. The latter label promises opening
the directory, not selecting or highlighting a file. Capture the focused asset
UUID, catalog revision, absolute path and indexed content fingerprint when the
action begins. Requery that same identity before dispatch. Selection, filters,
refresh or a configuration dialog must never retarget an in-flight request;
catalog/path/content/revision drift refuses it instead of silently rebasing.

Allow the OS association or a trusted installed executable chosen by the user,
with structured fixed argument values and a separate absolute target argument.
Use local-file URLs for associations. Never interpolate media names into shell
commands or execute command templates. Persist trusted configuration only in
machine-local settings outside the portable catalog; do not add a schema or
automatically import executable trust from another machine's catalog.

Perform potentially blocking source checks off the GUI thread with a finite
operation timeout, bounded concurrency and explicit cleanup/failure behavior.
Define these limits in a reviewed design note before substantive implementation;
they are safety bounds, not adopted performance budgets. A timed-out probe
must receive no dispatch permit and must never launch later. Use a distinct
one-time handoff permit, checking deadline/cancellation in both supervisor and
helper immediately before dispatch. Once a permitted OS request has begun,
lost acknowledgement, cancellation or timeout can mean handoff uncertain;
never claim it did not open or automatically retry that request. Recheck
original availability and regular-file
identity/fingerprint under a documented race boundary before launch. Refuse
missing, denied, nonregular, stale or failed handoffs with visible actionable
feedback. Do not promise race-free external-editor behavior across the final
check-to-launch interval. Explain that the user controls the external tool.

Source health/disposition are last-observed scan facts. Offline, missing and
permission-denied states require explicit scan/reconciliation to clear; do not
infer restoration from a GUI probe. The real source-health enum is watching,
scanning, paused, offline, permission_denied and error. Successful one-shot
scans normally end paused; paused/disabled monitoring does not imply offline.
Refuse scanning/error until explicit completion/reconciliation. Source-backed
assets require exactly one matching indexed entry by asset ID, source ID and
current path. Refuse pending/ignored/unsupported/error/missing entries. Support
valid standalone indexed assets with null source ID through the same captured
asset and fresh-file checks, without inventing source-health observations.
A successful dispatch
is a handoff request, not proof that an editor opened, saved or reconciled.
External edits require explicit scan; DefiantMaple must not automatically
change source files or asset metadata after process exit.

## Design and preservation

Sol owns production service, Qt integration, meaningful tests, product guide
and complex generated native helper. Record the external-access design and
compatibility assessment in the guide or a focused decision note, including
local configuration, process ownership, timeout/cleanup, race limits and
explicit reconciliation. Root approves the design against this brief before
implementation. Independent Sol reviews implementation and helper before the
native helper is frozen and run.

Add a bounded read-only frozen new-worker probe smoke to the existing Nuitka
packaging gate if needed to establish spawn compatibility. This is the one
reviewed package.py preservation exception: retain all existing packaging,
metrics and identity/thumbnail/gallery smokes, and never grant a dispatch permit
from that probe-only CLI. Record the prior hash and scope of the addition.
Kernel-blocked filesystem I/O may prevent timely process reaping even after
kill; report cleanup failure, retain ownership and refuse replacement jobs.
Do not claim real-share interruption qualification from sleeping-child tests.

Preserve source media, existing asset identities/metadata, schema-v6 journal,
single/bulk curation, gallery/viewer, scanner semantics, durability/recovery,
protected workflows, measured archives and deployed outputs. No diagnostic
cohort, schema migration, source mutation, plugin SDK or global OS association
change. Side-by-side comparison, verified cached-offline display, broader
accessibility, backup/restore/export and release qualification remain separate.

## Validation and ownership

Use isolated generated fixtures. Test literal adversarial filenames/argv,
missing tools, default local-URL dispatch, fresh source failure/nonregular
paths, source last-observed states, metadata/path/content ABA or revision drift,
selection/filter/configuration drift, timeout, late results and shutdown.
Verify exact captured targets and zero unexpected dispatches/catalog edits.
Meaningful tests must demonstrate outcomes, including concurrency/race refusal,
and preserve single/bulk actions and reader compatibility.

Native acceptance uses a temporary read-only handler recording exact arguments
and generated originals, with source byte/size/mtime and catalog snapshots.
Root alone runs visible focused interactions after an unlocked-session check.
Do not open user artwork or alter installed associations. Default-association
tests remain mocked unless separately evidenced; the native handler proves
structured process dispatch only. No native Windows/macOS or broad assistive-
technology claim follows from Linux/offscreen/hosted tests.

Luna owns Task30, tracker, acceptance/privacy derivatives and CI auditing.
Independent Sol owns Task31. Root owns this brief, orchestration, branch,
integration, visible native run and publication. Shared checkout: agents do not
commit, push, switch branches, change PRs or edit another owner's files.
Finish with reviewed native evidence, green relevant local/hosted checks,
actual Windows summaries and a reviewable draft PR. Merge and output-binary
replacement remain separate decisions.
