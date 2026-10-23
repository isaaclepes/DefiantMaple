# Independent scheduled metadata snapshot review

Status: exact Task50 design and Task51 acceptance contracts independently
cleared below, before material runtime changes. Root may authorize the staged
implementation. No implementation acceptance, retention deletion or private
native/frozen helper execution clearance is implied.
Baseline: merged PR24 `47effeeb5a5adf8b692023c49b67ee52a9025559`.
Independent reviewer: Task52.

## Goal and SDD fit

SDD v0.2 §16.3 FR-RECOVERY-003 requires scheduled local metadata snapshots,
visible last-success status, configurable retention/storage policy, and no
silent deletion of the last verified recovery point. FR-RECOVERY-001/002/004/005
and NFR-005 retain consistency, verification, isolated restore, omissions,
stable identities/relationships, safe source holds and migration rules.
FR-LIB-003 requires participating application ownership through real worker
cleanup; FR-LIB-004 does not certify writable catalogs or backup publication on
network/synchronized/removable storage. SDD §21.2 requires fault, job and
preservation evidence, not only a timer demonstration.

The bounded goal is opt-in scheduling while the application is running. It
must say that closed applications do not create snapshots. It adds explicit
configuration and status plus a reviewed retention/storage policy; it does not
install a background service. Existing Linux/macOS/Windows application writers
and manual recovery behavior must remain intact. Existing Linux local backup
publication qualification cannot silently become general scheduling storage
qualification, and unsupported platforms must not be made writable by bypassing
the established native publication policy.

## Mandatory exact design decisions

1. **Ownership and execution.** Name every launcher, window, Core API, CLI or
   other surface that enables/disables/configures scheduling or dispatches work.
   Define one scheduler per admitted physical catalog and use existing backup
   child/publication verification rather than copying a live SQLite main file.
   Define overlap with manual backup, migration, restore, scan work and shutdown.
   Disabling/cancellation must retain ownership through proven child cleanup;
   late callbacks cannot publish stale success or restart disabled work.

2. **Physical identity.** A logical UUID does not distinguish copies/restores.
   Specify how configuration identifies the admitted physical catalog and how
   copied, moved, replaced, hardlinked or temporarily missing catalogs behave.
   Do not automatically enable an unrelated copy because its UUID matches.
   Revalidate before execution and before accepting a result. Define explicit
   user recovery/rebinding when stable identity cannot be established, without
   opening or mutating a personal catalog to discover policy.

3. **External durable state.** Keep configuration/status outside the catalog;
   preserve schema7 and UUID/durability. Specify versioned validation, atomic
   update and durability/failure handling, concurrency, ownership, permissions,
   corrupted/unknown state, and stable association with the physical catalog.
   Persisted status is evidence about a verified operation, not authority to
   delete a path. Separate user intent from active process/worker state.

4. **Clocks and restart truth.** Specify monotonic cadence while running and
   wall-clock timestamps for displayed/audited history. Handle wall jumps,
   suspend/resume, process restart, missed intervals, invalid persisted clocks
   and long-running work without catch-up storms or invented successes. Define
   whether overdue startup performs one attempt and when next due is computed.
   Last attempted, last verified success, next due, running/canceling, skipped,
   unavailable, failed and uncertain publication must be distinguishable.
   Do not overwrite the last verified-success timestamp on failure or merely
   trust an old persisted timestamp as proof a recovery point still exists.

5. **Destination and trust boundary.** Choose a visible explicit local storage
   policy and existing supported adapter; authenticate the pinned directory and
   its identity through publication/retention. Cover symlink/reparse/hardlink,
   directory replacement, case/Unicode naming, unexpected entries, mount loss,
   permission changes and unsupported/unknown backing. Never enumerate a user
   directory and infer every package belongs to this scheduler from extension,
   filename, UUID or a self-described manifest alone.

6. **Index and recovery-point ownership.** Define the scheduler-owned namespace,
   package identifiers and durable index/provenance linking an exact verified
   package to this scheduler/catalog. Authenticate candidate identity/content
   at use time; reject tampered, substituted, unindexed or untrusted packages
   for deletion. Define index loss/corruption, orphan publication, duplicate
   entries and ambiguous ownership conservatively. Retain evidence and require
   reconciliation rather than adopt and delete unrelated files.

7. **Retention/storage and last recovery point.** Specify configurable validated
   count/age/byte budget semantics, disabled cleanup, defaults, units, policy
   changes, and a visible audit of decisions. Retention may select only owned
   verified points after a newly published point is durably verified and
   recoverable. Protect the last verified recovery point even if it exceeds
   budget; show over-budget/storage failure instead of silently removing it.
   Before each deletion, recheck directory binding, exact candidate identity,
   ownership and the protected verified-point invariant. Define how failure of
   verification of the nominal newest point affects selection. Unsupported
   race-free deletion semantics must fail closed for retention rather than
   expand a claim from path checks alone.

8. **Fault ordering and uncertainty.** Enumerate create/stage/fsync/verify,
   publish/bind, index/status persistence, retention selection/unlink and
   directory durability boundaries. Inject interruption/failure at each relevant
   durable step, including disk full before/after publication, missing/changed
   destination and cleanup failure. A published-but-unindexed point is not an
   excuse to delete an older verified point; a failed status write is not a
   successful recorded schedule. Preserve the last verified point and explicit
   uncertain state when rollback cannot be guaranteed.

9. **Compatibility and holds.** New scheduled packages use the existing verified
   metadata-only format and omission reporting, preserve required rows/UUIDs,
   and restore through the existing isolated destination workflow. Do not
   activate, clear or discard pending/source/standalone holds. Define whether
   unsupported source states refuse scheduling or produce a verified snapshot
   under the existing recovery contract. Preserve prior-package and manual
   backup/restore behavior on every currently supported platform boundary.

10. **UI and auditability.** Opt-in, destination, interval and retention/storage
    effects must be clear before enabling; deletion consequences need a
    documented explicit enabled policy. Report disabled/unavailable/overdue/
    failure and truthful last-success status. Keep full private paths/catalog
    data out of public evidence. Do not claim work happened while closed or
    silently classify a failed or interrupted operation as a completed point.

## Acceptance and review gates

Task51 must map every decision above to concrete generated-fixture oracles.
Use named readiness/barrier boundaries with real adapters/workers where their
support is claimed. Inject clocks for deterministic schedule logic but retain
real process/SQLite publication and cleanup evidence. Check immediate disable,
restart during active work, pending shutdown, stale callbacks, busy admission,
status/index corruption and retention races. Enumerate and hash catalog rows,
identity/settings, media/cache and all15 deployed outputs before/after; operation
effects must be explicit. Demonstrate restoration from the produced package and
last-point survival through failures. A harmless unrelated package/sentinel in
the same destination must survive every cleanup scenario.

Review design and acceptance by exact hash before material runtime changes.
Then review incremental implementation and focused tests before affected full
checks; review exact private native/frozen helpers before execution. Preserve
failed/interrupted/rejected attempts and direct exits. Platform claims require
actual platform logs and named skips; no injected Windows response is Windows
execution. Final source freeze, independent evidence/privacy review and actual
current-head hosted CI precede milestone completion. Root owns draft PR
publication; no merge or deployed output replacement is included.

## Current review record

- Baseline SDD and requirement tracker read. FR-RECOVERY-003 is Not Started;
  existing recovery rows remain Partial and NFR-005 retains its existing scoped
  status. No tracker status is changed by establishing this gate.
- Task50 exact design and Task51 exact acceptance handoffs are pending. The
  points above are required design decisions, not findings against unseen
  documents. No runtime clearance until explicit exact-file review.

### Initial exact design review

Reviewed Task50 design SHA256
`9be07c72e62134bcc52a174e75a4d60f75660ce5eb1f6608316d1f61ec7ca19a`
and brief SHA256
`eb66c323c360d7dd497224d93f5521cf3253615a752e90733916afc5333f7070`.
No runtime clearance.

**Blocking: ordinary reopen does not resume an enabled schedule.** Requiring a
user to select the managed directory again each session leaves durable enabled
configuration dormant after ordinary application restart. The requested
persistent schedule/restart contract requires a reviewed external per-user
locator: reopening the unchanged admitted physical catalog automatically loads
and revalidates its exact state/directory binding. Never match logical UUID
alone or search disks. Copied/moved/replaced catalogs and missing/corrupt locator
or schedule state must suspend visibly and require explicit repair, without
silently creating or enabling replacement state. Specify atomic locator
persistence, concurrent updates, failure ordering and restoration semantics;
Task51 must cover these exact boundaries. Root independently identified the
same blocker and requested amendment.

The proposed retention mechanism is defensible within its stated cooperative
private-directory boundary, subject to exact implementation and fault review.
Real candidate/survivor inspection, ledger identity/digest, exclusive lock,
pinned-directory checks, delete intent and directory durability support that
bounded contract. They do not make unlink atomic with a prior identity check
against hostile same-user code racing afterward. This limitation must remain
explicit, while retention remains a required implemented feature. Acceptance
must inject candidate/survivor/directory changes at observable boundaries,
preserve unrelated files and the verified survivor, and stop after uncertain
deletion. No fallback that drops required retention or restart behavior is
cleared by this review.

### Initial exact acceptance review

Reviewed protocol SHA256
`520a4c0086dcbbe188cab20166ad693e4a6e9bc44aabf7c26bdabc12f2853d99`
and Task51 brief SHA256
`eae7f99c18348d7490df8dc63b8c459500772f27ac83b5df5cca7e55230e3686`.
The new ordinary-reopen locator and cooperative retention race cases address
the required review topics, but exact protocol clearance remains pending.

**Blocking: cancellation/failure status oracle ignores durable effects.** The
shared rule that every failed/canceled attempt leaves last-success unchanged,
combined with cancellation at every boundary, conflicts with a verified package
whose success was already durably recorded before cancellation or pruning/
cleanup failure. Require phase-specific outcomes: no advancement before verified
durable registration; published-but-unrecorded uncertainty stays distinct;
durably registered verified success survives later cleanup failure with a
separate latest outcome. Do not assert rollback of completed durable effects.

Clarify that unsupported scheduling storage/identity refuses before new
scheduler source access, not before ordinary admitted application opening or
existing manual writer operations. Correct the Task50 task link. Align SS-09
with approved count/byte policy rather than adding age retention implicitly;
SS-12 must name actual reviewed limits rather than invent catalog/package caps
not specified by the design. These requests were sent to Task51 and Root.

### Revised design disposition

Task50 design SHA256
`95ac3db53a0a836d429a48d503639b4aa26db6c54a8f416a8c7ef9e768498836`
and brief SHA256
`2e24602fa75a5800cba7ef6920480a7795cb8f662e65072e3bb8ca764d764586`
are independently cleared as a design contract. This is not runtime or helper
execution clearance; Root's implementation go also requires the final exact
Task51 protocol disposition.

The locator amendment resolves ordinary-reopen continuity: exact canonical-key
lookup after real admission/authenticated identity, private bounded state,
native catalog/parent/destination bindings, fixed locator-then-schedule lock
order, and matching configuration revisions across the two durable documents
before enabling work. Two-file persistence is explicitly non-atomic; mismatch
or uncertain writes suspend instead of falling back to older policy. Copies
and moves with no matching key are visibly unconfigured; replacement/corruption
does not inherit or silently repair a schedule. No disk search or UUID-only
discovery is added.

Cooperative retention remains required with last-point and unrelated-file
protection, real verification and directory/index/delete-intent fault review.
The exact native deletion code and generated boundary helpers still require
independent review before destructive execution. Phase-specific status now
preserves durably registered verified success across later pruning/cleanup
failure and keeps publication/registration uncertainty separate.

Revised Task51 protocol SHA256
`0b3f2c29a1d9fcb3648f42719cbae8087e1178e031d4510361e114cba5b33900`
and brief SHA256
`29965d89083a2a4652d915e4844be4308652166176695615a5cf9ec71a31f675`
resolve the phase-specific status, ordinary-open/manual-recovery and policy
findings. Two controlled documentation corrections remain: SS-12 must distinguish
the existing16 GiB snapshot bound from the larger package bound including
header/manifest overhead, and the brief must describe the manual-reattach
finding as historical rather than current revised design behavior. Exact final
protocol clearance follows the corrected hashes.

### Final exact design and protocol clearance

The following exact contracts are independently cleared for Root's staged
implementation decision:

| Contract | SHA256 |
| --- | --- |
| Task50 brief | `2e24602fa75a5800cba7ef6920480a7795cb8f662e65072e3bb8ca764d764586` |
| Scheduled snapshots design | `95ac3db53a0a836d429a48d503639b4aa26db6c54a8f416a8c7ef9e768498836` |
| Task51 brief | `bcc5fe80ac940df9a5f3235cdb0d596b14225f1286935dc101c174a01d8b0ea8` |
| Scheduled snapshots acceptance | `426c6fdae739d26f2bc14031dc64e6f81f92ba3186b7a426672b69ab587fadf4` |

All initial design/protocol findings above are resolved in these exact
versions. SS-12 now distinguishes the existing16 GiB payload bound from the
package bound including header and bounded manifest. The Task51 brief correctly
identifies manual reattachment as the superseded initial design. The16 named
cases preserve automatic ordinary reopen, durable success/cleanup distinctions,
actual admitted worker ownership, conservative copy/move/replacement behavior,
required cooperative retention and observable-boundary fault tests, last
verified-point and unrelated-file preservation, and real platform/capability
limits. Existing manual application/recovery behavior is explicitly preserved.

This is a design/acceptance gate clearance, not permission to skip retained
checks or evidence of runtime success. Incremental implementation and meaningful
tests require review; exact destructive retention code and generated native/
frozen helpers require independent review before execution. Final preservation,
current-head CI, evidence/privacy and Root draft-publication review remain
completion gates. No source/runtime tests, settings changes, merge or output
deployment were performed for this review.

### Stage2 foundations review — held for corrections

Reviewed source SHA256
`5b4256c9f178dc6575c1b19302217725e82ebed6c69b1c422a7ba12fa4374516`
and test SHA256
`e67df3dadbdc5711ab29b06e66d08282b4a88e46a96a1fd7274b4d726d538c42`.
Focused receipt SHA256
`e2afcc775587802da64b11217e2d156873d54df25570c2102a25a39c666a1a46`
and both raw log hashes match;16 tests passed, with source and all15 output
records unchanged. No app imports, timer, backup or pruning entrypoint is
enabled. These tests do not resolve the following source findings.

1. **Persisted incomplete cleanup can resume automatically.** Constructor
   suspension omits `cleanup_warning`, although live completion suspends that
   outcome. Also `finish(..., cleanup_complete=False)` accepts `verified`,
   `failed` and `canceled` outcomes without persisting cleanup-pending facts;
   restarting loses the live active/suspended flags. Persist an explicit
   suspended cleanup state or reject inconsistent completion combinations.
   Restart tests must cover every accepted incomplete-cleanup outcome and
   preserve verified success while preventing new work before reconciliation.

2. **Locked-directory trust facts are not revalidated.** Later validation checks
   directory/lock identity only. Observed directory permission/ownership changes
   or lock permission/link-count/empty-file changes can leave operations running
   in an unsafe store. Recheck pinned and named trust facts before I/O and
   publication, including relevant ancestor redirect/permission checks; refuse
   rather than repair. Add actual generated chmod/hardlink boundary regressions.

3. **Cleanup can mask published-state uncertainty.** After initial link
   publication, failure removing the stage produces `StateUncertainError`, but
   a second stage-unlink failure in `finally` replaces it with ordinary
   `OSError`. Preserve uncertain publication classification and cleanup detail
   through all cleanup paths; inject successful link followed by failed unlink.

4. **Final publication postcondition accepts disappearance/substitution.**
   Returning the final `read` version does not prove the name still identifies
   this operation's exact staged identity/content; absence returns `None`, and
   an externally substituted valid document returns its version as success.
   Verify expected staged identity and exact encoded bytes/hash after durable
   publication. Observed removal/substitution must remain uncertain and stop
   automatic work. Exercise real generated namespace changes at the final
   directory-fsync boundary, without replacing native publication calls.

Strict JSON fields, bounded typed policies, explicit physical binding, native
nonblocking locks, pre-publication CAS and file/directory fsync ordering are
otherwise meaningful foundations. Current tests cover their success/basic
failure cases but miss the restart and publication/trust regressions above.
No next-stage clearance until exact corrected files and focused evidence are
reviewed. No source edits or reruns performed by this reviewer.

### Corrected Stage2 disposition

Independently cleared the bounded state-foundation source SHA256
`40979e11bf878870a769b890813ef59557d1191dc5d32aeb26b0a92f241258e2`
and tests SHA256
`77c36e361414fed8eb6a8380065eb2256e58695666bcfeffa8cef169493ff3de`.
Fresh focused receipt SHA256
`740eb02c7386a8b7a7c99409cfcd7a3a1144724185c91ab86ed70b779d2b6e79`
and both raw log hashes match:21 tests passed in0.689 seconds reported by
unittest. The two source hashes and all15 full output records match before/
after. No rerun was needed for this independent review.

All four grouped Stage2 findings are resolved. A typed persisted
`cleanup_pending` flag and explicit `cleanup_warning` startup suspension survive
restart for every accepted completion outcome; explicit reconciliation clears
that state without losing prior success. Directory validation rechecks pinned/
named ownership/permissions, lexical ancestors/native local policy, and permanent
lock mode/link-count/emptiness. Post-publication uncertainty retains leftover
stage evidence instead of retrying cleanup that masks the classification.
The final durable read must match this operation's exact staged native identity,
document and bytes hash; disappearance and even identical-byte replacement
raise uncertainty.

New regressions exercise actual generated chmod/hardlink/content mutations,
permission change after real file fsync, successful native link followed by
stage-unlink failure, and removal/valid substitution after real directory fsync.
The native publication operations run unchanged around these controlled hooks.
These are meaningful fixes within the existing cooperative boundary; no hostile
post-final-check universal guarantee is inferred.

This clearance covers strict state/locator/binding types, locked durable I/O,
CAS and injected-clock foundations only. No timer, backup coordinator, application
integration, managed pruning or destructive helper is enabled or accepted.
Root's next-stage decision remains separate; subsequent exact code/helper and
real-worker/retention evidence gates remain mandatory.

### Stage3a configuration/ledger review — held for corrections

Reviewed scheduled-state source SHA256
`2be621eaa51fac0336cffc651f677e5999f45f8cfd388735086718895086c2b5`,
configuration source SHA256
`3547426d13b7582184ef5a1b3fab8bb9cabacd3f453df30de12ccd76cbcfca04`,
and configuration tests SHA256
`aa7c71415acc5cddace0ce1bc774154014106206a0301d99b20ea890f47f337c`.
Earlier foundation tests retain SHA256
`77c36e361414fed8eb6a8380065eb2256e58695666bcfeffa8cef169493ff3de`.
Focused receipt SHA256
`826be0939f1a63e31751884bde0d191f9d0ea5af125462dd5d5ab655228b05f7`
and raw hashes match:30 tests passed in1.608 seconds reported by unittest;
input/output maps remain unchanged. No GUI, timer, backup or pruning is enabled.

1. **Destination-change interruption can restore old enabled policy.** Writing
   a new directory's state then failing before locator publication leaves the
   old locator and old state mutually consistent and enabled. Discovery returns
   the old configuration, rather than the required suspended transition. Add a
   durable per-key transition/intent or equivalent conservative invalidation
   before abandoning the old binding. Fault tests must cover destination change,
   not only edits to the same directory, and preserve both package sets.

2. **Destination-change revision ABA accepts stale edits.** New schedules reset
   locator revision to1. Switching from old revision1 to a new destination's
   revision1 allows an old `expected_revision=1` command to edit the new binding.
   Use monotonic per-locator-key revision or captured schedule UUID plus revision
   CAS. A stale pre-switch configuration request must refuse after the switch.

3. **Catalog-family destination collisions remain accepted.** Placement rejects
   the catalog itself/ancestors but not absent `-journal`, `-wal` or `-shm`
   family leaves. Creating a managed directory there can break unchanged SQLite
   writers. Reuse the existing catalog-family guard before creating any
   configuration directory/lock; test each suffix with no unexpected files and
   a continuing legitimate catalog writer.

4. **Userdata is queried before schema/identity authentication.** `_placement`
   calls `_source_roots` after physical admission validation only. A future or
   malformed catalog under an explicit session is queried before later binding
   authentication, and absent-locator discovery never reaches that guard.
   Authenticate using the existing read-only current-catalog/backup guard before
   source-root queries, preserving legitimate recovery holds and native SQLite
   contention semantics. Test malformed identity/future schema before a
   source-query sentinel and before configuration filesystem effects.

Ledger/audit cardinality, ordered sequence and schedule identity checks, exact
last-success package references, strict nested decode, lock order, and matching
same-directory revision checks are useful within this stage. Current tests
cover those normal/error paths but not the transaction, ABA and placement/
authentication cases above. No next-stage clearance; reviewer changed no source
and reran no tests.

### Corrected Stage3a review — prior findings resolved; lifecycle hold

Reviewed scheduled-state SHA256
`2d84347482cd865ea4c7f01a61645aafc56e217a01a07784d00a6658706479a4`,
configuration SHA256
`92e96e9f6a1c7239da10f256bf9132a0ff5e14c4dde310ddc2a8aacbb3e3c827`,
and tests SHA256
`09ede06aee5f29d86528ca28a5112d432a65c472c5f5ebfb2e4730549d432224`.
Receipt SHA256
`c7088f087de61f4a35a0607a98c6d277c678688b0f6377b78909784e52b5012d`
and raw hashes match:34 tests passed in2.376 seconds reported by unittest,
with unchanged input and15 output maps. No independent rerun.

The four original findings are resolved. A bounded128 KiB typed permanent
configuration-transition document records pending before state/locator changes
and committed only after matching verified reads; discovery suspends pending
or mismatched transitions. Locator-key revisions increase across destination
changes. The existing catalog-family guard precedes configuration creation,
and existing read-only schema/identity authentication precedes source-root
queries while preserving native contention exceptions. Regression tests cover
matching old-pair fallback after interrupted destination switch, stale edits,
sidecar refusal with a continuing real writer, and authentication ordering.
The additional transition document is a reviewed safety refinement of the
non-atomic configuration transaction; final design/evidence must describe it.

**Remaining lifecycle blocker:** a different managed destination bypasses the
old schedule's lock and cleanup-state checks. Same-directory edits refuse
`cleanup_pending`, in-progress, uncertain and cleanup-warning states, but
`reuse=False` never reads the old managed state. It can acknowledge a new
schedule while the prior operation still owns its old schedule lock or needs
cleanup/reconciliation. Validate/serialize the previous schedule before a
same-catalog destination switch, retain quiescence through the transition, and
specify safe ordering if both managed locks are required. Real old-lock
contention and persisted incomplete-cleanup regressions must refuse a new
acknowledged binding and preserve prior packages/state. Do not defer this
configuration-to-worker exclusion until after enabling real operations.

No Stage3a/next-stage clearance yet. No runtime edits or reruns by reviewer.

### Stage3a final configuration/ledger clearance

Independently cleared configuration source SHA256
`848355bc4d1a0cc79e8b81847b787bce85ae7972219db43893a6baa20c7b8064`
and configuration tests SHA256
`399ebdb822dab3b7d0ef11d1a98b3d3710d40d0e9375422f05534d6c4e1a952f`,
with scheduled-state SHA256
`2d84347482cd865ea4c7f01a61645aafc56e217a01a07784d00a6658706479a4`
and earlier foundation tests SHA256
`77c36e361414fed8eb6a8380065eb2256e58695666bcfeffa8cef169493ff3de`
unchanged from the preceding review.

The corresponding amended Task50 brief SHA256
`6688c349ced4548c961c2aabbb2248bfffa79486619f4382b75774a4643f5dc4`
and design SHA256
`4f523f98080b8e32b615796e7801d5ae696444233c1f957c5bc921b8e0a9b1b9`
are independently cleared. They explicitly specify the permanent bounded
transition marker, per-key monotonic revisions and locator/old-managed/new-
managed lock order rather than leaving that refinement implicit. The16-case
acceptance contract previously cleared remains applicable.

The remaining old-schedule lifecycle finding is resolved: under the locator
lock, configuration locks/validates the old managed identity and exact state,
refuses pending/in-progress/uncertain/warning cleanup before creating a new
destination, holds its lock through the complete transition and acknowledgment,
and rechecks its unchanged state before publishing the pointer. Distinct old/
new destinations cannot be ancestors/descendants or existing schedules. The
cooperative lock order has no managed-to-locator acquisition edge.

New regressions cover all persisted blocked outcomes, real old-lock contention
before new-directory creation and real lock retention at locator publication.
They verify unchanged prior state, no premature new directory and the incremented
new revision. The fresh receipt SHA256
`2af4a07a08c33a7bd2a9a6df9372f2037207eabdd51350fd6d29b07d0124e41c`
and both raw hashes match:36 tests passed in2.913 seconds reported by unittest;
input and15 full output maps remain unchanged. No independent rerun.

All Stage3a findings are resolved within the reviewed cooperative boundary.
This is configuration/discovery/ledger foundation clearance only: discovered
configuration still requires real package reconciliation before any operation.
No GUI, timer, snapshot child, package pruning or destructive helper is enabled
or cleared. Root's next-stage implementation decision and exact subsequent
code/helper/evidence reviews remain separate.

### Stage3b1 operation/helper plan review

The proposed isolated operation/reconciliation module and generated helper cases
A–D are suitable for source preparation: explicit configured empty reconciliation
and real snapshot/reopen; actual isolated restore of that scheduled package;
real registered child/cancellation/contender lifecycle; and phase-specific
publication/state/inspection/cleanup faults. No GUI, timer or pruning belongs
to this stage. This is plan feedback only; exact code and helper hashes remain
required before any new real-worker execution.

Required exact-review checks:

- Keep locator-before-managed native lock order and a nonblocking per-owner
  operation slot. Retain the actual admitted session reference through backup
  and inspection worker cleanup, including uncertain/unreaped outcomes. Validate
  committed transition/configuration, physical binding, enabled policy and
  package reconciliation before source backup; no alternate manual trigger may
  bypass those checks.
- Verify exact ledger package identity/type/no-follow/link-count/size/streamed
  whole digest before and after real inspection, plus metadata-only manifest,
  schema and library UUID. Bound directory enumeration and reads. Missing,
  corrupt, unknown/unrecorded packages or interrupted state must not be adopted,
  removed or silently converted to success. Leave unrelated files untouched.
- Persist attempt/audit before a real child; separately classify prepublication
  failure, published-unregistered uncertainty and durably registered verified
  success followed by cleanup warning. Reconciliation distinguishes historical
  saved success from currently verified availability without inventing a new
  success time.
- Track cleanup facts for this operation and its real children. Existing global
  recovery reaper totals alone do not identify this operation's child or prove
  its termination. No containment/reaping of unrelated processes. A timeout or
  delivered result is not exit proof.
- Cancellation helper C must record a real verified-boundary child still alive
  and retained, request cancellation while it remains alive, and obtain another
  current CLI refusal before releasing the harness barrier. Then use original
  worker/result/cancellation/reap behavior and prove actual child stop and
  ownership release/reacquisition. Merely releasing a barrier does not prove
  cooperative cancellation.
- Preserve exact catalog rows/UUID/settings, expected restore holds and original
  package, generated media/cache and all15 full output records around each
  independently executed helper; freeze exact source and retain failed attempts.

Root may authorize non-destructive source preparation separately. No operation,
restore-helper, child execution, retention deletion or acceptance clearance has
been granted by this plan review.

### Stage3b1 early recovery API boundary feedback

Read-only review of the in-progress optional private `_process_started` observer
and `_only_process` reaper proposal finds the API shape acceptable in principle.
Observing the actual started Process inside the original recovery cleanup try,
before source retention can fail, supplies ownership evidence without replacing
native workers/results or introducing an authority token. Inspection may then
retain that actual read-only child explicitly. Exact-identity filtered reaping
can keep the scheduler from joining/cleaning unrelated recovery operations;
default manual callers must retain their existing semantics and bounded8-record
behavior. Merely examining prior unreaped state without cleaning unrelated
records is acceptable if it fails visibly rather than silently bypassing active
staging ownership.

Exact review must still verify callback/retention exceptions use original
kill/join/stage cleanup, filtered live/dead/stage-error paths never touch other
records, default manual backup/inspect/restore remain unchanged, and per-operation
strong ownership/native locks/slot persist until actual child/stage cleanup is
proven. Existing global totals are not a substitute for exact child facts.
This preliminary API feedback grants no exact-source, real-worker/helper,
retention deletion or acceptance clearance; code and helper hashes are pending.

### Stage3b1 exact source/unit/helper review — real execution held

Reviewed recovery source SHA256
`53bec3fcc82a650b7acbaea7a440d3733cca9e3fecee09dbc402db29d7498748`,
operation source SHA256
`8088eb644d22690846b54013696873082b2d838ca8190edbc48d753a46775644`,
unit tests SHA256
`5c2724b02a0f0ddde367f253b62a40ae5996645b1a0030e4634c7baa34fe884a`,
and proposed private helper SHA256
`f61b232ba5a53e60afbbf2216b93db9fb462bca0fba75329f680191187035ce0`.
No execution by reviewer.

The optional actual-Process callback is inside the existing recovery cleanup
try before retention; its exceptions retain original kill/join/cleanup behavior.
Default recovery callers retain their original path. Exact-identity filtered
reaping avoids joining/cleaning other records and preserves the default8-record
bound. The scoped unit tests mock all recovery children and are suitable for
one focused unit-only run, not real-worker qualification. Typed phase tests and
observer/inspection-retention failure tests are meaningful within that scope.

**Blocking for real operation execution:** coordinator cleanup calls the
pathname-only `_cleanup_stages` again after original recovery cleanup (and
possibly filtered reaping) already handled those names. The recorded Process
binds stage path strings, not a created/pinned native file identity. An unknown
sentinel or replacement appearing at a previously cleaned stage path can be
silently unlinked by this redundant cleanup. Do not automatically delete such
content. Use actual original-run cleanup facts and exact native-identity-bound
ownership for any retry, or conservatively retain/suspend unexpected leftovers.
Add a real generated regression that places an unrelated sentinel at an already
cleaned stage name before coordinator cleanup and requires preservation plus
truthful uncertainty.

The helper's A/B/C real backup/reopen/isolated restore/cancellation structure
is otherwise meaningful: controlled child acknowledgment follows real snapshot
verification, cancellation is requested with the actual retained PID alive,
CLI refusal precedes parent-barrier release, and the original child's cancel
Event must be observed before original reaping/reacquisition. Phase-D injected
faults currently live in mocked unit evidence, not this real helper; results
must not claim an unexecuted real fault matrix. Exact revised code/helper review
is still required before real-worker execution. No GUI/pruning clearance.

### Resumed Stage3b1 fixture-isolation contract

Generated-registry injection is acceptable bounded acceptance instrumentation:
the parent uses the existing explicit `_registry_path` fixture parameter, and
a fresh contender bootstrap may replace only `admission.registry_path` with the
same generated directory before invoking real `__main__.main`. Native resource
identity, key construction, nonblocking kernel locks, real CLI admission and
actual typed refusal must execute unchanged. This proves generated-registry
native admission behavior, not production OS-account registry namespace
selection. No product environment override or serialized ownership bypass is
introduced.

All namespace users must be accounted for. A parent monkeypatch does not
propagate under multiprocessing spawn: the actual isolated restore child also
needs a narrowly scoped validated helper bootstrap that chooses the generated
registry before original worker execution. It must not silently create locks in
the real account profile. Existing unchanged production-namespace evidence can
be reused only within its prior recorded scope; it does not turn injected
namespace tests into production namespace acceptance.

Before imports, directory creation or child launch, validate/pin the intended
checkout, workspace, private baseline, fresh attempt and registry paths. Reject
arbitrary/protected/cross-root arguments and existing attempt directories; do
not overwrite earlier evidence. Keep configuration, temporary state and all
recovery destinations inside the generated root. Exact helper review must
check this actual isolation, not only a docstring claim.

The cancellation fixture must preserve a real retained PID through contender
refusal using explicit barriers; cancellation timing cannot race the claimed
alive/refusal observation. Record actual child cancel acknowledgment and then
exit/reaping. Compare the prior verified package and durable success facts before/
after cancellation, not just source bytes. Capture main/WAL/SHM/journal family
membership and bytes plus allowed operation effects. These requirements address
Task51's independent helper findings; no revised helper has been cleared or
executed yet. The stage-cleanup ownership finding remains pending exact source
and regression review even though the author reports a correction in progress.

### Corrected Stage3b1 source/unit/helper execution disposition

Exact source/API and scoped unit-execution clearance:

| File | SHA256 |
| --- | --- |
| recovery source | `53bec3fcc82a650b7acbaea7a440d3733cca9e3fecee09dbc402db29d7498748` |
| snapshot operations source | `c8422b1116cff0b077c80952d396e31557007905a872764e808631b21e3099a6` |
| snapshot operations unit tests | `5337c79a9482ce5edf6487ed3e1bb141426e232aae534e4dead397750db3b4a4` |

The redundant cleanup finding is resolved. Original recovery cleanup or its
one deferred exact-process reaper owns stage cleanup; the coordinator now only
checks for absence. A leftover/recreated name is preserved, reported and keeps
ownership/locks/slot pending. The new generated unit regression recreates a
sentinel after original cleanup and checks bytes/native identity survive repeated
cleanup attempts until explicit test-fixture disposal. Callback/default/filter
behavior retains the earlier reviewed API boundary. This is static clearance
for the scoped unit run, not a test result.

Exact private real-helper execution clearance is granted for SHA256
`fb1676f3210ccb5ae9c0a6a8aad2eb314795d5bd46a8a753b7ab5490d0b57682`,
subject to Root's execution go and frozen source checks. Its fixed checkout,
workspace, baseline hash and fresh attempt-parent/name checks reject arbitrary
or symlinked/protected paths before directory creation. Parent/actual CLI and
all spawned recovery targets use the same generated registry with real native
adapters; the spawn wrapper injects only namespace before invoking the original
worker, including restore. Child proof files record that isolation. The claim
explicitly excludes production namespace acceptance.

Controlled correction after initial helper review: the generated CLI bootstrap
now propagates `main()` via `SystemExit`, preserving actual refusal direct exits.
The preceding helper hash with a discarded return value was not executed.

The helper verifies a real prior package/success remains unchanged through
cancellation, captures full source main/WAL/SHM/journal membership/bytes/stat,
and proves a real retained PID and CLI refusal before requesting cancellation.
Original child cancellation Event acknowledgment, actual exit and owner release
remain required. An actual original-run cleaned-stage recreation regression
checks sentinel identity/content and preserved verified success while ownership
stays pending; only the fixture's exact sentinel is explicitly disposed after
its preservation assertion. The helper does not implement retention deletion.
Catalog/package/restore holds, media/cache and15 full deployed-output records
are compared; previous attempt directories cannot be overwritten.

No execution has occurred in this review. Clearance permits only these scoped
unit and generated real-worker attempts with direct-exit/cleanup/preservation
receipts; source changes require a new exact review. Phase-D broader faults
remain unit evidence rather than an invented real matrix. No GUI, timer,
retention, full acceptance or deployment clearance follows.

### Final Stage3b1 helper receipt hardening

Re-reviewed only the three controlled hardening changes and cleared exact
private helper SHA256
`fd8ad7f6a696a4867886ba0f8937099b052d3e7b5622267a32613768dae53a27`
for Root's scoped generated execution go. Source/API/unit hashes remain as
cleared above. No helper has been executed by this reviewer.

Actual original Process factory records now bind the expected namespace proof
set to exact PID/target/cardinality; the wrapper permits only original recovery
workers or the reviewed controlled cancellation target. Every proof must use the
same generated registry. An original native private-local-parent probe records
adapter hash/platform/mount/backing and parent identity/ownership/mode without
creating its probe leaf. Fixture sentinel disposal now requires regular singly
linked exact identity, no-follow opened content/pinned identity and a final
named identity check before unlink. These strengthen evidence and fixture
containment without changing product behavior, worker results or acceptance
scope. Earlier helper variants remain unexecuted proposals, not failed runs.


### Completed Stage3b1 evidence audit

Independently accepted the completed bounded attempts without rerunning tests or
workers. Focused receipt SHA256
`5cabd933d540078e54163071375950c718951ca3a87417bc148b20bf1db1c64b`
records seven passing tests, no skips, direct exit zero. Real wrapper receipt
`b77c3cf082e020b633a322eb9766ad145ed8ecd52ad1d5a54b7bae44aea25ee7`
and inner receipt
`2eb8169ae7956473786450f342adf37b345b656d23a9d43d384d61cc3bf9e193`
bind the reviewed `fd8ad7f6a696a4867886ba0f8937099b052d3e7b5622267a32613768dae53a27`
helper to an actual direct-zero execution. Raw log hashes/bytes match receipts.
The outer freeze contains 326 inputs; the inner fixture freeze contains 320.
Both comparisons are unchanged, and current files match the outer freeze.

Actual evidence covers native qualified local backup, fresh inspection/reopen,
restore with exact metadata rows/UUID/durability and paused source holds, and
live-child cancellation with CLI refusal before barrier release, original Event
acknowledgment, actual exit and ownership release. All ten actual child
PID/target proofs match the factory records and isolated generated registry.
All four operation actors are inactive and reaped. Prior verified success and
package survive cancellation. The recreated-stage sentinel remains intact while
cleanup is pending; its later disposal uses the reviewed fixture-only guard.
The final registered success remains with `cleanup_warning`, rather than a
claim that an ordinary automatic reconciliation already cleared that warning.

Rechecked five CLI log pairs and their direct exits, final package ledger hashes,
size/native identities, original/restored table evidence, source catalog family,
media/cache preservation and phase snapshots. All fifteen protected outputs
still exactly match baseline hash, bytes, mode and mtime. This is generated
namespace evidence using the actual native adapter and original workers; it is
not production namespace, GUI, timer, pruning, full fault-matrix or cross-platform
acceptance. No remaining blocker was found within this Stage3b1 scope.

### Additional unchanged recovery-suite runner

Reviewed exact private runner SHA256
`54c698bc4bfdce6038eccefa8d4af127c6d978f59ab99166c61f89077e6373eb`.
It reuses the exact reviewed helper and fixed fresh-attempt validation, injects
only generated registry paths in parent/original spawned recovery workers, and
runs existing test bodies/assertions unchanged. Child PID/target/namespace
cardinality and no-live-child assertions are required; unittest failures retain
a nonzero direct exit. Cleared for Root's scoped execution with the proposed
outer input/output freeze, raw logs, bounded execution and cleanup receipt.
No production registry/CLI acceptance follows, and no execution of this runner
has occurred in this review.


### Recovery-suite instrumentation correction

The first unchanged recovery-suite attempt was a harness failure: its shared
multiprocessing interception rejected the original thumbnail decoder reached by
an existing recovery test (24 tests, 23 passing and one failure). That attempt
is retained as failure evidence and does not establish a passing suite.

Reviewed exact amended private runner SHA256
`f77798a6d11b0bbbaf7fad09e2f312cc2607894a004b6f57ece9122752ad1570`.
Cleared its controlled delta for Root execution: fresh attempt3, explicit identity
allowance for original `thumbnail._decode_worker`, unchanged target/arguments
passed to actual original Process, separate decoder PID/exit/dead inventory, and
combined no-live-child assertion. Recovery namespace injection/proof checks
remain unchanged. This does not change product/test assertions or claim decoder
admission namespace coverage. No retry has been executed by this reviewer.


### Passing unchanged recovery retry and retention preparation

Accepted the fresh passing retry after exact runner correction: inner receipt
`05df74e43937be6b9970080a4810a9bae4b740d9e6e231c05a6fd6b736fab0e5`
and wrapper
`3ec9738fd86aea47ad184f4ad082383ad15cf42b3ee1a890c2ab4cbacc662112`
match their hashes. Actual raw unittest log reports 24 tests in 5.011 seconds,
OK, no skips; direct exit zero. Twenty-one original recovery children have exact
namespace proofs, plus one separately recorded original decoder. All twenty-two
are dead with zero exits. Raw log hashes and wrapper pre/post equality verify
326 frozen inputs and fifteen protected outputs unchanged. Failed earlier
instrumentation attempt remains preserved. No test rerun by this reviewer.

The proposed next retention stage may prepare pure selection and durable
intent/reconciliation code; deletion execution remains held for exact review.
Intent must bind committed configuration revision and both candidate and distinct
verified survivor identity/digest/size/sequence. Each unlink must revalidate the
survivor and honor actual package holds. Unsatisfiable caps cannot authorize
last-point deletion. Open-intent recovery must distinguish exact present
candidate, absent candidate after unlink, and changed/recreated leaf; no pathname
replay may delete the changed leaf. Preserve historical success and durable
stop/uncertainty audit, including cancellation after deletion. State/directory
flush uncertainty and observable cooperative replacement boundaries need exact
fault oracles; native check-then-unlink is not an atomic hostile-writer guarantee.
No retention implementation or deletion helper was reviewed or executed here.


### Stage3b2a pure retention slice

Cleared exact source `snapshot_retention.py` SHA256
`b3dfa4e16369ffd63c4c2127c0928100ae41f4ec8d99711516a455a1282b875b`
and tests SHA256
`77554b4d59785d85e3ffc6af7ea9c11cd4319ac9ed1e66a273c6cb9afa6fdea8`
for their isolated non-deletion scope. Strict existing bounded state/audit types
bind candidate, newer physically distinct survivor and current revision. Pending
intent rejects overlap, stale revision and mismatched completion; inspection
observations never grant replay permission or remove ledger/history. Selection
protects newest/minimum one, count/byte caps and caller-supplied holds; disabled
retention/unsatisfiable caps yield visible stop warnings preserving success.
Actual filesystem inspection, native holds and unlink execution are explicitly
future obligations, not established by these supplied dataclass facts.

Verified receipt
`c60aa7a046f1586a7a490f2c8ddfa4bbd98704d18e4afdd05bd69cd28f896343`,
raw log hashes and seven passing non-deletion tests with no skips/direct zero;
receipt pre/post inputs and fifteen outputs compare unchanged. Tests exercise
durable intent roundtrip, policy selection, supplied holds, protected singleton,
status gating, exact/absent/changed/cancel classifications and malformed intents.
No blocker found in this pure slice. Executor code/helper needs separate exact
review; this disposition grants no deletion execution or native-hold acceptance.


### Package reader lease contract amendment

Cleared the design-only private plan SHA256
`4015b8692fbe4d93a5ca50b28e90481fe7bb368f51eafecd737224fed6e71bc1`
for source preparation, not execution. Actual original manual inspect/restore
must hold a shared advisory lease on the exact nofollow package descriptor from
before first byte through extraction/verification close. After its own inspections
are reaped, retention pins exclusive candidate and shared distinct survivor
leases through durable intent/unlink/flush/completion. All acquisition is
nonblocking with partial release on failure; candidate is rehashed on its own
exclusive descriptor, preventing self-contention. Final survivor inspection
uses a compatible shared child lease, followed by actual child cleanup proof.

Reader named identity is revalidated after acquisition; no orphan/substituted
package may be read following a lost path race. This closes the cooperative
reader gap without registry/sidecars/package writes and retains existing native
storage qualification before Linux-specific lease acquisition. Unsupported
platform guard paths remain unchanged. Cross-platform or hostile-writer lease
protection is not claimed. Kernel flock semantics were cross-checked against
[the Linux manual](https://man7.org/linux/man-pages/man2/flock.2.html).

Required exact implementation/helper review remains: descriptor lifetime on all
exceptions/cancellation/crash, no inheritable duplicate lease leak, typed busy
failure and partial-acquisition cleanup, real concurrent original readers/restore,
post-lease name substitution, candidate exclusive/read conflict, survivor shared
compatibility and unchanged manual recovery regressions. Public design and
acceptance contracts must capture this required lease boundary before executor
clearance. No native deletion or lease helper execution is cleared here.


### Exact package lease acceptance amendment

Reviewed Task51 brief SHA256
`78598cfd0b47479d0a9e68cdacaa70293508621198b46c48449bbe0830dc861d`
and protocol
`77ba19ad47aa3bb3800ca17cf82a4ee3c2f6e775f71fc5fa27c2e7fb1739c1a7`.
Cleared the SS-17/SS-18 contract amendment: actual original manual inspect and
restore readers, both contention directions, before-first-byte refusal,
post-acquisition path identity, compatible survivor shared reads, actual child
cancel/crash/close lifetime and non-destructive completion barrier. Supplied
hold facts grant no authority. Lease-only evidence cannot close SS-09/SS-16
unlink/ledger requirements. Existing cooperative Linux scope and unsupported
platform behavior remain explicit; all unrun mandatory cases stay open.
No execution or executor clearance follows; exact design amendment is pending.


### First exact lease source/helper review: execution held

Reviewed recovery `eb0c306c3843f643f74aabe744cd7293debaa646c20b0dc1d86123af77a77a56`
and storage `1076a6f45aed68bc9eba84fdd6c628ae49fe70cde4062cd70585800994eed9c3`:
original native guard precedes shared lease, descriptor/name checks precede first
read, release/close covers exceptions, and fork handlers close inherited leases
without unlocking the parent's description. No immediate source correctness
blocker found. Exact amended design `c118d3fb4ae28a2f6bbf45a78f7c64b9db43ce8310d04eda8d161d611bd896df`
and Task50 `3d61905b5e223a50b6eb20f776cebf1f7833fceb12bf1967eea88fa3e9150eb7`
are contract-cleared for this mandatory cooperative lease boundary.

Execution remains held on test/helper corrections. New tests `d9584bd1...`
unconditionally enter the Linux native adapter in setUp without unsupported-host
qualification skip: standard Windows/macOS discovery would error all five tests.
Use honest existing native qualification skips and keep unsupported guard behavior.
Private helper `624539ac...` does not prove cancel-acknowledged-but-still-live
reader refusal because its child immediately raises after acknowledgment. Add a
lease-retaining acknowledgment/release barrier and actual live PID/exclusive-busy
check. It also lacks distinct survivor shared-reader/completion-lifetime proof
and actual descriptor/native-identity fields in control evidence. Do not close
SS-17/SS-18 with those observations absent. No execution occurred in this review.


### Corrected exact nondeletion lease execution clearance

Cleared corrected tests SHA256
`68df6417773291969e435406df224771f2fca99fe5bfa7b0e37c44426a62c719`,
private helper
`8f0fd16f87ae11d02f2ff3bb7355e1fd476df56b97687082d437e65b487fd36e`
and outer wrapper
`84babdaf23d2e56bc8c67d173eaaf5fd76715a6137b59f1e63678fb8c21cad75`
for Root's scoped nondeletion execution. Recovery/storage source and design
hashes remain as reviewed above. Native test skips now match only exact original
unsupported-platform/backing refusals; separate platform-neutral guards assert
refusal before opening. Unknown native failures remain errors.

Helper actual descriptor identity/path/size/mtime readiness is checked against
original package facts. Cancellation acknowledgment retains the live original
child behind explicit release, while parent join is held and exclusive contention
is asserted; actual cancellation exit and crash signal are checked. A distinct
real survivor supports shared child inspection under retained parent shared lease,
with exclusive refusal after child exit at a clearly labeled nondeletion
completion checkpoint. Source/candidate/survivor hashes are checked per interrupt.
The replacement drill first observes actual exclusive contention on the original
FD, then performs a test-only retry of original native acquisition after fixture
replacement; original named-identity validation refuses with zero package reads.
This exercises that production check without introducing a product retry.

Outer pins fresh paths/helper/baseline, freezes source/docs/helper bytes and all
fifteen protected output records, records raw logs/direct exit and bounds its
new private process group. No helper/test was executed by this reviewer. This
permits only the reviewed lease proof; no unlink, durable deletion completion,
retention integration or production namespace acceptance is authorized.


### Completed nondeletion lease evidence

Independently accepted focused receipt
`6b0b4e1b0b903abec6ee5e30d9059ddcbf08f769f72e3b23595601c676d6fd17`
(six passing tests, no skips/direct zero), outer receipt
`e91b716dac1d9f4f6db266fcd1f3bbafaa91b1252215671dd9bcf0bd7cf79abf`
and inner receipt
`771b3dbb254e8860f575373cc80102f27d80831f3f31cad5c555663b556627b1`.
Exact hashes, raw log hashes/bytes and outer pre/post equality match: 329 inputs,
fifteen outputs and helper/wrapper bytes unchanged. Native helper logs are empty;
its concrete event receipt carries the evidence, not invented log content.

Eight actual reader children are dead, seven exiting zero and the intentional
crash exiting SIGKILL; no threads remain. Receipt identities bind two concurrent
shared inspectors and restore cancellation to the original package, with a
physically distinct survivor. Actual reverse inspect/restore busy refusals and
contended-path replacement report zero package reads. Survivor shared child
compatibility and retained parent shared/exclusive lifetime are explicitly a
nondeletion checkpoint. The exact reviewed helper's actual cancel-ack/live-PID/
exclusive-busy assertions passed before release, with source/package/survivor
preservation checks at interruption boundaries. No execution was repeated by
this reviewer. Changed lease-source manual regressions remain required; no
executor, unlink, full SS-17/SS-18 completion or production namespace claim follows.


Cleared affected manual-regression runner `1189830d2cfdfc50ad2634f32a0d04093c96c96483e1c13d02b0fe7d151932ab` for Root execution: byte comparison proves the only difference from reviewed `f77798a6...` is fresh generated OUT attempt3 to attempt5. Prior isolation/assertions remain exact. Require outer freeze/raw logs/direct exit/cleanup receipt; no execution by reviewer.


### Affected manual recovery regression after lease source change

Accepted exact outer receipt
`8802b3018ead6f853888e024ff0330551d14fde3ed243faab4a4c0b98c00df76`
and inner
`fce019f155726dbfb953e9f0d8d624d7ef9afbc4e7f9483d4582f53e179e2039`.
Actual unchanged suite passes all24 tests with no skips/errors/failures/direct
zero. Raw logs match recorded bytes/hashes; 21 exact recovery namespace proofs
plus the original decoder account for22 dead zero-exit children. Outer329 input
and15 protected-output pre/post freeze is unchanged. No tests rerun by reviewer.
This clears the affected Linux manual-regression gate after lease changes, not
crossplatform hosted CI or production namespace acceptance.

Executor source/helper preparation may resume with mandatory actual candidate
exclusive and survivor shared descriptor leases retained through directory fsync
and durable ledger completion. Every fault/cancel/restart branch must preserve
last verified success, stop pathname replay and report cleanup/publication
uncertainty truthfully. Exact executor/helper review is required before any
native deletion; none is authorized by this evidence disposition.


### First native pruning executor/helper review: held

Reviewed proposed operations `77c143dda641e28b07097f8e03b7249bce70d8d6fa55190bb95c00d1e18bccba`,
pruning `d56773421140aec757e3dbeb789e352f64a31199f5fb5d6ce59f21013f4709c4`,
private helper `e148c1e60588a29be35e29f75451d967b1d1506c7cc6dc11d18576fa27a7ab4f`
and outer `92e17c77ca778235bc52fa193fb319882e66477862c3681385ca2b55380d0c18`.
No immediate destructive source-boundary correctness defect found: original
same-backup registration, owner/slot/config CAS checks, actual inspector cleanup,
sorted candidate EX/survivor SH leases, pinned hashes/named identity and retained
leases through directory flush/completion are explicit. Pending restart uses
read-only actual inspection and never replays deletion. Cooperative race scope
remains essential; this is not atomic hostile-user unlink-by-identity.

Execution held on concrete helper correction: reader_holds_candidate requires
`PackageInUseError` text in OperationResult.error although direct native busy
exception is stringified without its class name. Assert actual native typed
exception or stable busy outcome without modifying runtime prose for this test.
Restart cases require expected actual exact/absent/changed classifications, not
merely suspended with unchanged inventory; otherwise unrelated refusal passes
vacuously. Add current-vs-historical verification assertions for substituted
survivor/directory versus preserved survivor. Pre-unlink cancellation, locator/
transition changes and actual retained-lease probes at unlink/flush/completion
are missing from these23 cases and remain required distinct acceptance gates.
No source/helper/test was executed; no deletion clearance is granted.


### Corrected exact native pruning proposal

Cleared proposed operations `77c143dda641e28b07097f8e03b7249bce70d8d6fa55190bb95c00d1e18bccba`,
pruning `7de44333d726dfaae80bcd0d4db4ec8fecbce0f42e2edca8c39f623494079ec3`,
private helper `eb1b617a4957fce51a0956dfb8609f46c3de89e0ae8373b0cd4442a20f70eaeb`
and outer `f1959af9b63f76acdc8c89e93678e1b60ec55acc0f4645a47a5ee6a2fa79c986`
for Root's separately authorized generated native execution. Exact hashes match.
No execution occurred in this review.

Final validation now checks all bounded ledger facts, with absence permitted only
for the exact pending unlinked candidate. The29-case helper addresses earlier
oracle findings: native typed busy capture, actual restore shared-reader exclusion,
changed middle ledger entry, pre-unlink cancel/config/transition boundaries,
exact healthy retained sequence set and expected per-case unlink, preserved
quarantined original identity/hash/mode/mtime and whole old-directory inventory,
explicit current-vs-historical success and actual pending restart classifications.

Independent native probes assert candidate shared refusal and survivor shared
compatibility/exclusive refusal at unlink, directory flush and ledger completion.
Post-unlink candidate access via the parent's actual pinned FD is explicitly a
native lifetime probe, not a manual pathname authority API. Actual durable
completion acknowledgment loss checks disk completion and actual reopen without
candidate deletion replay. Helper controls touch only fresh generated fixtures;
its outer pins dependencies, full input/output freeze, raw logs and direct exit.

Clearance is bounded to cooperative private-directory mutation before supported
checks. A hostile/nonparticipating replacement between final named check and
unlink remains outside the contract; an extra last check cannot eliminate that
race. No GUI/timer, production namespace, full release or deployment clearance
follows. Actual executed receipts and preserved fault outcomes remain required.


### Native fixture CAS correction

Attempt6 failed in setup before pruning because existing policy configure omitted
required expected_revision; preserve it as a harness failure, not a deletion run.
Cleared exact helper `7dad1a77996789254282b928952e0e0893f3e7a0d1f358437d70a19023d43786`
and outer `70a2724d0ab656e58e4a526154f84ce2bef009afd24196f414fec8ef3b1e20a0`
for separately authorized fresh attempt7/outer2. Mechanical reverse substitution
reproduces prior exact hashes: sole logic change is actual discover, configured
locator assertion and passing its actual revision to existing configure CAS;
initial absent configure remains unchanged. Other changes are fresh attempt names
and helper pin. No product/assertion changes or execution by reviewer.


### Attempt7 inventory failure investigation

Attempt7 failed healthy before intent/unlink; it supplies no native deletion
acceptance. Read-only source analysis identifies shared directory-stream offset
as the leading cause: `_reconcile` and repeated pruning `_validate` enumerate
`os.scandir(actor.managed.fd)` on the same retained directory descriptor. A dup
used by fdopendir can share its open-description offset, leaving later scans at
EOF despite unchanged physical names. Fresh-descriptor inspection matching the
five allowed names is consistent with that hypothesis. This is not yet an
executed diagnostic result. A bounded nondeletion generated probe should record
original offset and seen/allowed sets across scans. A fix should enumerate an
independent pinned-directory open description and verify its native identity,
not rely on shared dup offsets or uncontrolled pathname reopening. No fix,
diagnostic helper or retry was executed/cleared by this reviewer here.


Subsequent Root-authorized stdlib-only diagnostic (receipt
`a40ff2295e2ed7f294d9292209084e1bee2a2264a9e3eb9eaad31c8f57d23154`)
falsifies the simple EOF hypothesis on the actual Python runtime: closed scandir
iterations reset the shared FD offset and repeated names remain stable. No fix
should be based on that hypothesis. Next appropriate scope is a fresh single-
healthy nondeletion trace preserving original lazy iterator behavior and recording
actual seen/allowed/absent/offset/identity/calling phase, with independent
before-delete-intent and package-unlink vetoes. Exact diagnostic review pending.


### Exact guarded native inventory diagnostic clearance

Cleared private diagnostic `06b7b97795fd8bcd9f4de19e68e9f6191f266cf6aef25a6fb2a5a012671a7d0b`
and outer `3e5344613c3bd6484c8e08dcfbff30ddc5b71ec7872f9a6786b7c377743dbf4f`
for Root-authorized single healthy nondeletion trace only. The original native
fixture is hash-pinned, fresh attempt8 and healthy-only. Scandir proxy observes
original lazy entries/context closure without preconsumption; original validator
receives unchanged arguments, with offsets/native identity/allowed/state recorded.
Class save guard rejects any delete_intent before persistence; independent global
package-unlink guard remains in the original unlink chain. Generated backup and
inspection are permitted; retention intent/unlink cannot proceed. Outer captures
full freeze/dependencies/fifteen outputs/raw logs and bounds its own process group.
Expected diagnostic nonzero is not a passing native matrix outcome. No execution
or source fix by this reviewer.


### Narrow exception-only diagnostic clearance

Cleared exact private diagnostic
`6435805406d342f51b40045c52b0ce7413f34c4e9d8371f58df0bb97d1f77de7`
and outer `0753f2d2b6ac687c43453b3107f7237ad831d3b9f1867ac79454c43723791512`
for fresh single-healthy attempt9 nondeletion execution. Original validator runs
before instrumentation; only its actual exception traceback frame supplies
seen/allowed/absent and line/phase. No scan proxy/lseek/fstat/prevalidation queries
remain. Independent before-delete-intent and all-package-unlink vetoes remain
exact. Outer differs solely in fresh path/helper pin from prior reviewed wrapper.
Preserve nonreproduction and expected guard nonzero as diagnostic outcomes, not
passing native retention evidence. No source change or execution by reviewer.


### Actual inventory omission reproduced

Verified exact exception-only diagnostic trace
`7a69b9290ad9a7340d2f82f555be33db4dc52aa95c0716b4380a1519a7fc88dc`.
Its first actual validator frame sees lock plus two older packages, while allowed
also contains replaced schedule.json and newly published third package; absent
is empty. This is actual stale enumeration/omission evidence, not proof of a
specific kernel cause. No durable intent/package unlink occurred. Independent
open-description enumeration is now justified for source preparation: open dot
relative to pinned directory with DIRECTORY/NOFOLLOW, validate native/private
identity before/after, close independent scan FD; no dup/path fallback. Exact
source and real publication/replacement/unknown-file regression review remains
required before execution. No source patch or test execution by reviewer.


### Exact fresh-inventory fix and guarded comparison clearance

Cleared source scheduled_snapshots `d8a43bbe251c486694a41410578759d44580c5230219ba64406c006e2250d715`,
operations `3f3d651b37eb3200fd6dc7e81fddee165d0e509e499f8094a099bac0d90a73ad`,
pruning `b48feb9ec8e7b3db5660ebcf1b993487b7aaf67e2d88e866c40e4e64cf101619`
and tests `f63843f5f470d16b20d1c13dd06a49d9b9bdfabb91a0825285d76e28fc71ae70`
for focused nondeletion tests. names opens dot relative to retained pin as an
independent nofollow directory description, authenticates both descriptions/private
facts before and after, revalidates named store and closes its own FD. Both prior
inventory sites use it; bounds remain unchanged. Regressions cover retained pin
with real state CAS replacement/new generated leaf, post-reconcile unknown leaf
refusal/preservation and private-directory fact change after open.

Also cleared guarded comparison helper
`89ffd26142106c41f2b22c8cea847b69e99a851f5c40bdf0ca1fff6ee5a748da`
and outer `9eebac1b673125292ed88b193c616049fc27925fc94984ddc18224d817e796b5`.
Fresh names are recorded only after original method returns; actual original
validator/backup/inspect and independent before-intent/package-unlink guards
remain. This permits fresh attempt10 comparison only, expected guarded nonzero,
not29-case native deletion retry. No execution by reviewer; receipts required.


### Fresh inventory fix evidence accepted

Verified focused receipt `fdd92fccc75b97c7c9ca57c3d5d337fd0da382b75048b987ebdad6a69b80c647`
(three passing tests/no skips/direct zero), guarded wrapper
`5511c7a52f0a65660c133b2ce2a159981fa4dc6602a25d9a9e782c226210fb7c`,
inner `95421525cea0d32d4475918a9d327b7a52414b403ba3288b120535bebd08e9d4`
and actual trace `3bdda6342e760821627c819d8758829f7e7ecc044a500d3791f6d6845d037d21`.
All three original validators return successfully; six real fresh inventories
contain2,3,4,5,5,5names, including final state plus all three packages. Guarded
attempt10 exits one intentionally before delete_intent, not as a native29 pass.
Twelve actual children are dead/zero with actors reaped/no external threads.
Raw logs match;331input/fifteen-output pre/post freezes are unchanged. This
supports the bounded stale-enumeration correction against actual failing9;
no specific kernel cause is inferred. No tests repeated by reviewer. A fresh
native29 runner still needs its exact controlled path/hash review before deletion.


### Exact fresh native29 retry clearance

Cleared private helper `a542ca0630904c560322a484c7928ce43cd9d3cd83c30f67a212400996f8d8a5`
and outer `b3c3715918ac36a44424bc471ed48779c2ae25995c7f7cea047e045933b866e9`
for Root's separately authorized generated native29 attempt11. Mechanical reverse
substitution reproduces cleared7dad/70a272hashes exactly: only fresh real7→11,
outer2→3 and helper pin changed. Execution source is the reviewed fresh-inventory
set d8a43/3f3d/b48f, with focused/guarded proof above. All original native29
assertions, generated isolation, bounded cooperative guarantee and preservation
requirements remain. No execution or full acceptance by this reviewer; preserve
prior failed/guarded attempts and audit actual retry outcome before acceptance.


### Native29 actual evidence accepted (20 October resume)

Independently audited exact outer receipt
`c8c3696219fa6a8a2893bf48da8ace3895232f8e3f182d2c58ed68347a7f77ba`
and inner `76b6124a4e05985a85a527c228c5a1967db9462247be5e7ed54958c89a34b7ff`.
Reviewed helper a542/outer b3c371 ran direct zero in67.382seconds against reviewed
d8a43/3f3d/b48f source. Raw stdout/stderr are actually empty and hash correctly;
case receipt and preserved fixture files carry the evidence. All29 cases passed,
349 distinct child PIDs are dead/zero,99 actor cleanup outcomes reaped and no
external threads remain. Eighteen independent native pair-lease probes satisfy
candidate shared refusal/survivor shared compatibility/exclusive refusal.

Recomputed all29 final fixture inventories against receipt hash/size/mode/mtime,
all original source main/WAL/SHM/journal membership and identity facts, preserved
quarantined originals, healthy exact retained sequences2,3, actual pending restart
classifications, and durable completion-ack-loss disk completion/reopen outcome.
Current runtime/test hashes still match wrapper freeze. All15 protected outputs
still match exact hash/bytes/mode/mtime. Outer331inputs/helpers/output pre/post
freeze is unchanged. Prior failed6/7 and diagnostic8/9/10 remain distinct history;
none was relabeled passing deletion evidence. No tests/workers rerun by reviewer.

This accepts bounded generated qualified-Linux cooperative retention/fault evidence,
including actual inspect/restore-reader exclusion, survivor leases, configuration
and mutation gates, last-point protection, uncertainty/restart/no-replay and
publication acknowledgment loss. It does not establish GUI/timer scheduling,
production namespace, hosted crossplatform regression, or full milestone/release
completion. Next Qt integration plan needs review before source go: actual admitted
owner/slot lifecycle, off-thread worker/cancel/close cleanup, durable discovery,
truthful clocks/missed-run/no-overlap status and settings/retention disclosure,
manual recovery coordination and exact generated acceptance helpers.


### Desktop backend GateA plan review

Reviewed exact plan `b6e84f7350f1488ba820e76b404335e604eb3eca806d601069f39a292dc28b8f`.
Separate strict durable control overlay is an appropriate way to stop scheduling
without revising/discarding pending intent. Missing/corrupt/mismatched control
must veto; existing development records require explicit same-discovered-directory
Enable/configuration preserving history, never automatic adoption or reattachment.
A stop writer takes control lock only, last in global order, retains actual owner
through durable readback and cannot wait upstream. Read-only reconciliation/manual
recovery remain available without clearing veto or manufacturing recovery.

Required plan clarification before source go: Enable must capture expected-control
version and explicit user request epoch before waiting for configuration locks,
then reject a newer stop, rather than treating that newer stop as its new baseline.
Control lock is retained through durable readback, not a GUI acknowledgment wait.
Manual actor retains each actual child unless original_run retains this same owner;
restore with absent/different live_catalog cannot assume original retention.
All slot/owner references remain until actual cleanup plus thread finish.

Same-live-session stopped acknowledgment requires exact stop request UUID/version,
authenticated binding, no queued work and actual child/stage cleanup, with CAS
failure preserving requested state. Restart stop_requested stays durable veto and
cleanup unknown; admission acquisition/PID absence is not authority to promote.
This conservative status can remain review-required without inventing repair or
silently resolving intent. Tests must cover stop persistence/readback/ack loss,
Enable-Disable races and stale results, interrupted exact/absent/changed intents,
thread/callback/start failure and manual/scheduled slot exclusion. GateB remains
separate, including timer-contract alignment. No runtime/source/test edits here.


### Revised desktop contracts cleared for staged source preparation

Cleared GateA plan `3fe8fa2e141b2370ebd7b45b2ab8ea509e0f9d17024e3ff3d1d41bb4f51518c4`
and GateB plan `c76ab0eb253524246aa5ea2029a58c015b187ca0816eb4890d2b8826cda39092`.
Previous plan findings are resolved: explicit Enable captures expected-control CAS
before waiting, newer stop wins, control lock releases after durable readback
before signals, manual child retention covers absent/different original owner,
and missing-control explicit configuration preserves discovered directory/history.
Same-live-session off acknowledgment requires exact request/binding/CAS plus
thread finish and actual cleanup; restart request remains veto/cleanup UNKNOWN.
Named lost-ack/CAS/race and interrupted-intent tests are required, not deferred.

GateB specifies off-UI persistence/hash/inspection, retained actual owner and
worker/actor lifetime, generation fences, at-most-minute bounded schedule wake
plus events, separate active-cleanup reap and no missed-run burst/overlap. Managed
Snapshot now shares enabled policy/retention; unmanaged manual backup cannot alter
scheduled success/deadline. Settings disclosure, automatic exact-locator reopen,
truthful historical/current/stop status, unsupported scheduling isolation and
native/source/frozen evidence boundaries are explicit. No GUI-thread filesystem
work or manual directory reattachment is introduced by the plan.

This grants GateA scoped source preparation only, followed by exact source/tests/
helper review before execution. GateB is contract-cleared but its source stage
remains behind GateA code review and Root go. No runtime edits/tests/workers by
reviewer, no blanket acceptance or deployment clearance.


### Desktop acceptance SS-19 through SS-21 review

Verified protocol `a9b71c9d08c5b21409bd11e4b2157427e64bb0c316b9cc18469ea93f5ecfcb5d`
and Task51 `4ebaa1cf04713108b368ce4462e21545bb0244a62e6e4c8e74a90c16452c1acb`.
Required actual stop durability/CAS/lost acknowledgment/restart UNKNOWN, shared
manual/scheduled slot and child lifetime, source/controller epochs and close/timer
oracles align cleared GateA/B. No desktop execution/acceptance is claimed.
One wording correction is required before exact clearance: SS-19's final blanket
configuration-revision preservation conflicts with included explicit Enable
configuration-commit faults. Stop/ack paths must preserve configuration and
pending intent; Enable may legitimately advance revision at a committed boundary,
then remain vetoed if run-control acknowledgment fails. Require exact pre/post
committed revision outcomes and no unintended rollback/rewrite, not unchanged
revision across successful Enable commit. Author/Root notified; revised hashes
pending. No runtime edit or execution by reviewer.


### Final desktop acceptance contract and first manual actor source review

Cleared final protocol `a8dcabd62ba1c2cd02885b6a2d8a783e3e32a488a0a25b3e99aa6e00dc361542`
and Task51 `1d65ebcfb3221e08b0660f841da2695b64083503e227f9c641cc27c4ebda5530`.
SS-19 now distinguishes uncommitted/missing/uncertain control from exact durable
run authorized by explicit Enable with lost UI/readback acknowledgment. Reopen
may reconcile actual committed run without duplicate Enable/rollback; newer Stop
wins CAS. SS-20/21 retain required ownership/epoch/close/timer oracles. Contract
clearance is not execution or desktop acceptance.

Reviewed manual actor `fbfd3a5dcc9753199c9d7054c0413c4da40b083a3587ce0ab12ca7c30d19e7e2`,
recovery `d8b5c8a342027477c7bc48571732d8440a658077ece001c3c60751f6c46a924e`
and tests `752be82754d86fc109e17393a05d6ef9d3ca4f075ec3cb4736e008dd32f3bc8b`.
Restore optional callback forwards default None without changing original args;
child recording precedes retention failure, actual same-owner routing avoids
redundant retain, cleanup defers slot/owner release until thread finish and exact
process/stage proof without repeated deletion.

Execution held on per-actor overlap: begin acquires shared slot once, while
backup/inspect/restore only check active and can concurrently invoke original
recovery from the same actor. The callback lock protects records, not method
entry. Add nonblocking invocation/single-action guard and a barrier test proving
second call refuses before original API/process start. Also define backup source
affinity: arbitrary other-owner database cannot bypass that owner's shared slot
merely because this GUI owner is retained. No tests/real workers executed here.


### Corrected manual ownership slice: focused execution clearance

Cleared manual actor `9b2433aed8126ffd2585f53cee549d6f8ddc98869cf0e2ebaf09442ea8676dc1`,
tests `c2d674b3ad833ae40806fe05e3d572fca9ae9c92f21cf39e0d760a09ac4a9663`
and unchanged restore callback source `d8b5c8a342027477c7bc48571732d8440a658077ece001c3c60751f6c46a924e`
for focused nine injected/non-native-worker tests under Root's frozen receipt.
Invocation lock now spans complete original API call; concurrent call refuses
before API and finish_thread cannot release active invocation. Exact owner-path
backup affinity plus physical owner validation prevents wrong-source slot bypass.
Bounded thread barrier tests reject second call/early finish and wrong source.
Prior actual child/deferred cleanup claims remain unqualified until separately
reviewed real manual-actor helper. No execution by reviewer or Qt wiring clearance.


Accepted ownership focused receipt
`c40ab90b7ef2a62e9a4bd8db85e1a1b0846cf506b9cce99d1a0985417c2a07ee`:
actual nine passing/no-skip tests and direct zero, raw log hashes/bytes valid,
335-input/fifteen-output pre/post freeze unchanged. This is mock ownership and
bounded real-thread barrier evidence only, not actual recovery-child retention
or Qt lifecycle acceptance. No tests rerun by reviewer.


### Lowest control persistence/live-stop slice: execution held

Reviewed exact control `f214757e8dca3ed3cd6fd92719fdce30bc6662e269ba212a3aee2d3cdc9dcc8c`
and tests `dbd12402e671893072b98f8fb0afbb3b337c4ac79ff2ec424a4eff82f82e40c3`.
Strict bounded codec, native private CAS/readback, exact published inode check,
control-only request and upstream→control-last acknowledgment preserve intended
separation. Enable/config/veto/Qt/real-worker integration are explicitly absent.

Two findings hold focused execution clearance. LiveStopSession._validate connects
to SQLite and queries identity before owner.validate/native captured-binding
checks; source replacement could therefore be queried before admission physical
authentication. Require native guard before connection and after identity query,
with failed-owner validation preventing any SQLite/identity call. Also saved
request mapping and observed actor list grow strong references indefinitely:
superseded request UUIDs cannot ever acknowledge and completed actors are never
removed. Retain only latest acknowledgeable request/outstanding actors, or enforce
an explicit bounded fail-closed limit; never prune active or unproven cleanup.
Add targeted supersession/lifecycle regressions. No execution by reviewer.


### Corrected lowest control slice: focused nonworker clearance

Cleared control `ec3285ba620e4ca94d409c125b007d72595ed12598d4de737369a89e13a2993c`
and tests `a1fb5364cba661a5130e874a8041abdee7659359fac35d876fd1d49011e5dcfd`
for12 focused nonworker tests under Root's full frozen receipt. Native actual
owner/captured physical path/parent/file checks now precede placement/SQLite;
original current-catalog read-only identity guard and native revalidation follow.
Real generated rename/copy substitution refuses before any connection or identity
query. Only latest saved request authority is retained; superseded ack is refused.
Observed actors cap at64 fail-closed, deduplicate same object and never drop
unproven cleanup. This interim cap is explicit, not proof-backed deregistration;
long-lived Qt actor lifecycle remains a later integration requirement.

No Enable/config transaction, automatic operation/pruning veto, actual stop-during-
child helper or Qt evidence is inferred. Twelve authored tests have not been run
by reviewer. Exact executed receipt remains required before accepting this slice.


Accepted exact control focused receipt
`dc4b7b49e7408798e6dc1471814eed46f68ebcb859e8f627820ae2d66bc35e02`:
12actual passing/no-skip tests/direct zero, raw log hashes/bytes match,335inputs
and15protected-output pre/post freeze unchanged. This covers codec/generated
control storage/live-stop authority only, no actual recovery workers, Enable
coordinator or automatic veto. No rerun by reviewer. Actor64 cap remains bounded
outstanding/unproven tracking, not an accepted lifetime job limit for Qt.


### Cross-module control integration plan review

Reviewed plan `b850bfcb76f7ff5dd4907a3ce6edd395a96505d7f7d5491fa051bfc1964a5310`.
Captured one-shot action CAS before waiting, optional original configure context
hook, control-last through exact run readback and mandatory operation/pruning
veto are appropriate. Bare configure cannot acknowledge controlled readiness;
old exact-source receipts stay historical. Stop-session outstanding-only scope
avoids lifetime64-job exhaustion without discarding unproven cleanup.

Two details require clarification before cross-module go. Actual package
reconciliation must use explicitly borrowed authenticated old/new stores/state
within original configure locks; calling actor._begin/reconcile while those locks
are held, or recursively configure while actor owns them, would self-contend on
independent flock descriptions. Retain owner/slot through inspections and cleanup
before taking control-last. Define hook API/lifetime to prevent that inversion.
Transient control checks before unlink establish a checkpoint, not a linearizable
promise that nothing unlinks after stop persistence: a stop may commit after that
check while the in-flight irreversible action completes. Either document this
in-flight boundary while saved stop waits cleanup, or explicitly change locking
semantics. No additional last check eliminates that race. No runtime edits or
execution by reviewer; revised plan/source handoff pending.


### Amended control integration contracts cleared

Cleared exact private plan `bfd6f9aea36d26f341853280572303b4e2cf3934c6b0a78c6b077f505bef3bd6`,
Task50 `90c8250d0f53e05cd99b65f115bb3364a98f7f36d44d660bb8448e756d9913dc`
and design `7dd840e50a0db01ce1f59e932ed299a692a731e40bbf1e51e035f4dc02976d55`
for scoped integration source preparation. Both prior findings are resolved:
immutable context borrows same configure-owned locked stores only within original
ExitStack lifetime; actual inspectors/cleanup occur before control-last, without
recursive actor begin/configure/flock acquisition. Wrapper retains owner/slot and
actual records through unresolved child cleanup even after store lifetime ends.
Stop's saved veto applies to next checkpoint/future work; already-passed bounded
unlink may finish while saved-stop status awaits cleanup, without false
linearizable promise. No control lock spans child wait or unlink/flush/completion.
Exact source/tests/helpers remain required before execution; no Qt go or native
rerun is granted by this contract review. No runtime changes by reviewer.


### First actual manual lifecycle helper review: held

Reviewed the supplied manual helper proposal a2c3/outer5af7 content; files began
changing during review, so no frozen exact execution clearance is issued.
Execution findings: actor callback records contain no control pipe, but wait_record
returns them and barrier cases access control; lookup pipe through exact actual
Process identity in factory inventory instead. Helper/outer failed receipts need
failed direct-exit propagation via status return/SystemExit. Distinct-owner
callback wait uses AND instead of OR and can race the second retain. Cancellation
event drain must handle EOF. Callback-retention failure may kill child before
namespace bootstrap; prove readiness before injection or distinguish prebootstrap
abort honestly. Final cleanup must reject active actors/pending records/live
threads, not merely live Process objects. Outer should pin exact reviewed helper
hash, not only freeze whichever bytes exist. Root/author notified; revised frozen
handoff required before clearance. No workers executed by reviewer.


### Exact controlled-config focused and actual manual helper clearances

Cleared controlled_configuration `6288238fd41b7f73329af294bdf8e044d2a76622530add4a5c074c78b290f401`,
configuration `8179ff64c2a9d7e721c56a1949827c9fad1bfbc0cee0a8b7341e5bc0c4fc7508`
and tests `9cc44fcda91bebf9df1c72fca6926e7965d18b59d27696d02b808f219dd1ee13`
for five focused nonworker tests. Borrowed original stores/ExitStack lifetime,
actual shared owner/slot through finish, inspector cleanup before control-last,
captured CAS before publication and run after committed readback are coherent.
Default None preserves original configure path. Existing configure regressions
remain required before integration acceptance. EnableRequest is presently typed
capture data; consumption is per-operation instance, so later UI must fence
reconstructed/duplicate action instances rather than claim backend controller
identity authority not yet implemented.

Cleared exact actual manual helper
`597a8f45ceafaed87de656d09652a65e9776cb54821004cdf753f051d25d1597`
and outer `f98ccaad7e97f144831d39221df01c787636078e91e37730a05666d450fc1a2c`
for Root's separately authorized generated execution. Previous mechanical findings
are corrected: exact Process-to-control lookup, both-owner wait, EOF-safe drains,
actual callback readiness proof atomically published, exactly one selected-mode
callback boundary, failed receipt/direct-exit propagation, helper hash pin and
full actor/thread/process/stage cleanup refusal. Original worker/actual owner and
native adapter remain, with generated registry isolation and closed fresh paths.
No runtime execution by reviewer; actual receipts required. This is manual actor
lifecycle scope only, no control-veto, Qt or production namespace acceptance.


### Actual manual lifecycle evidence and failed wrapper aggregation

Accepted actual generated manual attempt3 receipt
`be7069aa4dc19ff6253ee90a6a171e0399c4c93867f93aee56e4fca7d310de9d`
through a separate independent evidence binding. Original wrapper receipt
`79e0df778396981733f6e35037ed77cdcf6cca8e3a4e413e1fb5d9cf83cb4500`
remains FAILED: its hardcoded inner reference erroneously reads failed attempt2.
It actually launches reviewed fc7 helper (fixed OUT3) and records child exit zero;
its own process exits one due aggregation. No original receipt is rewritten or
relabeled, and no actual-worker repeat is required merely to repair that link.

Verified correct inner3 and all namespace-proof mtimes within the same wrapper
UTC interval, pinned helper/wrapper hashes and341input/15output pre/post equality.
Eight exact cases passed; six actual children are dead (five zero exits and
intentional callback-retention kill), eight actors inactive with stages absent and
no cleanup errors. Actual PID/proof sets, callback readiness, both source-owner
retention, slot contention, original start/callback faults, live cancel/close and
CLI busy/busy/acquire logs match. Recomputed source families and all15 protected
output SHA/bytes/mode/mtime. Raw native logs are actually empty. Supplementary
private attestation preserves the defective wrapper linkage and bounded acceptance.

Setup failure1 and pre-callback failure2 remain separate failures; original error
in2 was not captured, so spawn serialization is source-supported diagnosis, not
invented observed traceback. Final reviewed class-start instrumentation and EOF
fix produced actual successful fixture3. No tests/workers rerun by reviewer.
This accepts manual actor lifecycle only, not Qt, control-veto integration,
production namespace or full milestone. Previously audited controlled-config
five-test receipt0e380d remains accepted in its nonworker scope.


### Mandatory control veto: exact focused clearance

Cleared control `1bd24c677019209be679170e5ad94e89b619280aeffd21f6f6cb6dc3cb114376`,
operations `7e10cc9d4dc671b49dfc6ac316d43b112f9478e913de05941c66d653b0260fc0`,
pruning `2a307aa0d6a3753e19fc78907d2bc49f20d57a1505f9da20764457350823ba79`
and tests `00fba6ee77ce1f4f6f544c47cf09a665d6bd205a03b4bc58297741c906c69180`
for14 focused nonworker tests. Required run is checked at backup entry, after
reconciliation, before original backup API and native pruning validation; no
production false-default bypass exists. Control authenticates same pinned locator
root and actual source owner before/after reading exact run binding. Locks are
transient and do not span workers/unlink. Read-only reconciliation preserves stop.

Earlier source-after-control-read gap is fixed and covered with real rename/copy
substitution refusing API/shared final checkpoint. Missing/mismatched/malformed/
actually contended control, stop-after-attempt-save, saved stop/read-only reconcile
and injected ledger prune checkpoint have explicit nondeletion oracles. This is
not actual native package/retention evidence; affected fixtures require reviewed
legitimate ControlledEnable setup and fresh execution before current-source
qualification. No tests/workers executed by reviewer. Review edits close for the
focused material freeze after this entry.


Accepted mandatory-veto focused receipt
`12941b7f4717e71a74b740523e405a6ee8d37d7d78c74ac55cc9765dc24257be`:
14pass/no skips/direct zero, raw logs verified,341inputs/fifteen outputs unchanged.
No real worker/retention acceptance follows from that focused receipt.

### Current-control native29 fixture migration clearance

Cleared exact helper `0d43ccb066fbd55f225935f812a06cb8b04fcae19ae313db7ed46468dc8be644`
and outer `d2ec869e530536192a197cc1a84043d79126303955c343e9a187159e7541987e`
for Root's separately authorized generated native29 fresh attempt12/outer4.
Verified archived precontrol a542/b3c hashes and complete delta: setup now uses
actual ControlledEnableOperation, first explicit absence and later discovered
revision/current exact run CAS captured before configuration lock waiting; no
control-held discovery or default bypass. Actual borrowed inspectors use original
workers and retain shared owner/slot through explicit finish/cleanup. Every Enable
run/CAS/child proof and cleanup is recorded. Existing29fault/oracle bodies remain
unchanged, including config/transition substitution reaching original validators.
Outer changes only fresh path/helper pin. Source is the reviewed mandatory-control
set; old exact receipts remain historical, not current-source claims. No execution
by reviewer; actual receipt audit required. Review edits close for material freeze.


### Current controlled backend native29 evidence accepted

Accepted exact outer receipt
`3cb842c5d65fdf6da7701950ded417f4bafe03be565fed2e83de0c915179a07b`
and inner `11de79e152b2991d82aacbea8e13994771bd57af1deff28be21f619dc8b36a35`.
Reviewed hardened helper07bd7/outera85e1 executed direct zero in83.170seconds;
all29case oracles passed. All405distinct actual children are dead/zero, with no
finalizer intervention (the hardened finalizer fails if it needs kill/join).
All99snapshot actors and58legitimate ControlledEnable operations are inactive/
reaped; no external threads or cleanup errors. Eighteen native pair-lease probes
meet candidate exclusion/survivor compatibility boundaries. Actual Enable revision,
captured CAS/run readback and original inspection cleanup records are present.

Recomputed all29full fixture inventories/source families and preserved quarantined
originals, all337current frozen inputs and all15protected outputs including full
hash/bytes/mode/mtime. Raw stdout/stderr are genuinely empty and hash correctly.
337versus prior focused341 excludes only four untracked Qt build artifacts
(desktop entry/icon, prototype binary and deployment spec); no tracked source,
runtime/test or documentation input is omitted. Those four are not retrospectively
claimed covered. Previous precontrol29receipts remain exact historical evidence.
No tests/workers rerun by this reviewer.

GateA reviewed code and bounded backend evidence are sufficient for GateB Qt
SOURCE PREPARATION under Root go. GateA acceptance is not wholly complete: actual
stop publication during a live child/held upstream locks, next real pruning
checkpoint veto without new intent/unlink, delayed actual cleanup/thread-finish
off acknowledgment and stop/run lost-ack/race lifecycle require further original
worker/Qt evidence. These may be combined in a separately reviewed B3 generated
helper; existing29 tests do not substitute for them. UI/controller one-shot epoch,
automatic reopen, clocks, settings/retention disclosure and native/frozen lifecycle
remain their explicit gates. No full desktop, requirement or release acceptance.


### First isolated Qt foundations review

Reviewed module `efa8cce3937a4a9b57ba6bfeb3e9b228b7eb83c2c4aba08385138706a9f63437`
and tests `61b47939cc5c8420031f915218012fc78975d41b088af375ade2a1278546d575`.
Cleared four pure platform-neutral Qt guard tests only: exact object/controller/
epoch single use, latest capture invalidation, minute-bounded pending-only timer
without worker dispatch, and close disarming/refusing new work. No actual worker,
configuration query or native child is authorized by that test scope.

Actual check/dispatch path remains held for cancellation correction: assigning
job.cancel_event to actor.cancel followed by actor._begin currently clears the
same event, losing cancellation requested before begin. Prefer optional external
sticky per-job event: preserve default internally owned reusable cancellation,
never clear external event, reject pre-canceled job before discovery/native work
and before actor/API dispatch. Do not clear/reapply after begin. Deterministic
prestart/during-begin barriers and separate actual QThread/child cleanup evidence
are required. Prestart owner retain, live thread kept after start acknowledgment
error and release on actual queued finished are sound architecture but unproven
by these four guards. No existing window wiring, stop lanes, settings, automatic
backup dispatch, A3 or native/frozen desktop acceptance is claimed. No execution
by reviewer; review edits close for focused material freeze.


### Sticky per-job cancellation source and focused evidence accepted

Reviewed operations `df792756f076867fadd4d9c832d6e6045189121e52d5ef7e6bff3e6be75025e9`,
Qt module `87bfb8084775ec6ae1181fb7cf55cd06fbb4bf0a64d7c611122373456e572d99`,
operation tests `2e7b50e6743b421349a2454e7bc5f1fc6b35d05281a03fe9a735c614d58e55d2`
and Qt tests `7b7dde726b7c91961b297e992e378e414257c9b0fe45fdc78d4c024b5a0a3d5f`.
The pre-begin cancellation-loss blocker is closed: optional external Event is
never cleared, preset refusal precedes slot/placement/native entry, checkpoints
cover begin/inspection/backup dispatch, while internally owned reusable actors
retain their original reset behavior. Qt job refuses pre-run and post-owner-check
cancellation before callback; actual actor shares the event at construction,
covering cancel before actor assignment. Existing owner/slot cleanup on refusal
remains balanced.

Task50 `38224974f4c8e8cc8316a6103fb2327921a296bd2fc16c217f7592963cdf9766`
and design `eb05ad93198d83fd27878e6792d0ff08dbe23487f237b5ad85fe4229e1fee1ee`
correctly distinguish observed checkpoint cancellation from an impossible atomic
cancel-versus-spawn guarantee: already-passed bounded action stays owned until
actual cleanup/thread completion.

Verified exact receipt `d9c484e310787dc1e6140dabba4aff65365edf589bc6f04f89f044a88c84f7ca`:
24actual focused tests/no skips/direct zero, raw logs match,343inputs and15outputs
pre/post unchanged. Deterministic real-thread begin barrier rejects post-placement
cancel before native-store/API entry; pre-slot/preassignment/pre-run and internal
reuse oracles are meaningful. Qt job.run is called synchronously; no QThread.start
or recovery Process is exercised. No reruns by reviewer. Source-level cancellation
fix is accepted for further staged work; actual QThread/child lifecycle, dispatch,
stop lanes/settings/window wiring and native/frozen acceptance still require their
separate exact helpers/results. No blanket actual-dispatch execution clearance.


### Actual Qt/native ordering checkpoint accepted; window acceptance remains open

Independent review accepted controller source
`360f86fd5eb47a4df5891394ce7947a4bcb477aa8ba65d0283b5a91ed779c640`
and tests `37b9d488ba0d2851f131481078d070233e0cd9103865c514ca6569a3ea355bde`.
The held-stop-ack refresh exclusion, completed stop-session retirement and fresh
post-ack durable-state observation findings are closed. Focused evidence ran
20 tests without skips, including actual QThreads with mocked backend and an
existing recovery QWidget compatibility case; it did not run recovery children.

The separately reviewed B3 generated fixture then exercised a real offscreen
QApplication/controller and original native backend in two ordering cases. Exact
outer receipt `8e6597942f70dd6150ab9413847d7d86039f1009ef015c0c521ed7f578b2f181`
and inner receipt `de1220fa6c90ac8d6a4e7fd05eb83831c26381aec172e14ab38d93a7ebcba492`
passed with direct exit zero. External wrapper pin, exact source/helper freeze,
raw logs and linked receipt were independently checked. All 408 repository inputs,
13 private dependencies and 15 protected outputs matched before and after the
run; current frozen source matched the run at review. No protected artifact was
replaced or deployed.

In the first case, the original inspection child exited normally before Stop;
original verified registration resumed after the saved stop. Actual actor cleanup
completed while its genuine QThread remained running and retained. Acknowledgment
waited for genuine finished delivery. The newly registered third snapshot and
retained cleanup warning appeared in the fresh stopped view. This case does not
claim Stop during a live child. In the second case, genuine QThread completion
preceded actual child/actor cleanup. Exact process kill-refusal instrumentation
kept the original cleanup path pending; acknowledgment waited for actual filtered
cleanup and its genuine cleanup-thread completion. The historical two snapshots
and warning remained visible. Original stopped-state observation ran in both
cases, and final views matched actual durable state and package inventories.

All 15 actual children exited: 14 normally and one with the specifically declared
original cancellation-result BrokenPipeError/EPIPE after its receiver had closed.
That exception, original send frame, exact process refusal and exit one were
preserved and verified; it was not suppressed or described as normal completion.
All 19 genuine Qt jobs finished, stages were absent and no containment cleanup
intervention or live probe thread remained. No new deletion intent or managed
package unlink occurred. Current package hash verification and recovery-review
warnings are independent of the stopped control state.

This checkpoint accepts only those two offscreen controller/native orderings.
It is not visible GalleryWindow input/display, settings/manual-dialog wiring,
restart, installed/frozen application or full desktop acceptance. Prior accepted
backend/retention evidence retains its original exact-source scope; no unchanged
experiment was rerun by the reviewer.

The isolated W1 registry/settings source and 16 focused mocked-actor/widget tests
are reviewed within their scope. The native-versus-stat identity mismatch was
corrected. Before window acceptance, implementation and evidence must still cover
controller-derived next-due/deadline, clock and deferred-work status; synchronous
manual reservations in stop/idle decisions; real manual thread plus child/stage
cleanup; default manual behavior on all platforms; startup binding and close
refusal/reconciliation; actual window/native and private frozen integration.
Metadata omissions, application-running scheduling and explicit managed-retention
deletion consent must remain visible. Missing platform/storage qualification must
not disable unrelated manual recovery or ordinary writers. These gates remain
open; FR-RECOVERY-003 is not declared fully accepted.

### W1 timing, manual hooks and startup normalization checkpoint

Independent review clears the bounded W1 source and focused evidence below.
The amended timing suite passed 29 tests, direct exit zero, with 343 inputs and
15 protected outputs unchanged: receipt
`2608d75509d1e3dcfd87579608661292b748876be79e2de8e3b2b411cce1e8c0`.
The earlier 28-test receipt remains historical; the amendment adds a
sampled-duration oracle. Manual reservation/stop/cleanup hooks passed 41 tests,
direct exit zero, with 343 inputs and 15 outputs unchanged: receipt
`52347261a4c3b01b79a1c1edbdbb440e907d7dc204e15eea06b26eedd478ec12`.
The preceding failed hooks receipt
`16794bacca9c87d011bb58a41c3aab9793f3ead68ad98ee504642e95d11a4a73`
remains preserved: direct exit one with an observed test-oracle IndexError before
actor creation. The author attributed the earlier refusal to duplicate
unqualified ManualCall module imports; that cause is inferred from the import
correction, not the raw traceback. It is not passing evidence.

The prior application wiring suite passed 46 tests, direct exit zero, with 344
inputs and 15 outputs unchanged: receipt
`eae49795424babe353c1d994b75c1b5188fbb9d2fcec88b8d53949c385a90ae9`.
Its application source
`c13b2b7a0f5ca6b9521aacb525b9f0b7cb4636bc49b4e55858aee0395216903e`
and fully mocked configuration constructor did not prove startup normalization
was off GUI. Independent review subsequently found original configuration
construction reached filesystem-backed cache canonicalization on GUI. The
prior failed-import and pre-initialization-fix evidence remains historical;
none is replaced or promoted to current-source acceptance.

The startup blocker is closed for current application source
`30a1a921dbc089d33bdb77802df54aafa1e8c3931906015e56657e14b958a867`
and window tests
`b2f0ff8c944fabbb005b60fa0d9b4a39a7ca51be748c080f9cfd2284a2e059ba`.
A window-owned QThread runs the original SnapshotConfiguration constructor and
cache normalizer. Prestart retained ownership survives live-after-start errors
until genuine queued finished delivery; proven never-started failures release
it. Failure restores manual admission, close cancels and waits, and closing or
stale-epoch results cannot create a controller. GUI controller construction
follows current-epoch completion. Existing admission retain validation is not
claimed filesystem-free.

Verified receipt
`d3045aa594b8f0551914772827db3dd36fb3cd7f14de3f53fcd37778a977f6ce`:
52 tests passed, direct exit zero, 346 inputs and all 15 protected-output
hash/size/mode/mtime records unchanged; exact source pins and raw-log hashes
match. This includes an actual original constructor/cache-normalization
non-GUI assertion, bounded initialization-finished waits, start failures,
retention, close and stale-result cases. Scheduling actors remain mocked; no
actual recovery Process or native window integration is claimed by these suites.
Current controller is
`918eb10d06215b03bf70c68b294c44ef2401521c9595f00bf888bf6dec84b0b6`,
manual registry
`5c36fb3ce1837215f6f2835821ca389e30fed594ae4c06e54b558053f87aad7e`.

W2 actual admitted window/settings/manual-dialog/native integration remains
open and requires separate exact helper review and Root execution clearance.
Reuse unchanged native retention/A3/B3 evidence within its original scope;
integrated prune Stop and restart/fault cuts remain separate gates. W3 visible,
frozen and platform evidence and full FR-RECOVERY-003 acceptance remain open.
No reviewer execution, publication or deployment clearance follows.
