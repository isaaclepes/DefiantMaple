# Library writer admission acceptance

Status: bounded protocol and implementation-gap map. Design:
[Task 47](tasks/47-library-admission-implementation.md) and exact design
revision `53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`
in `library-admission-design.md`. Independent review:
[Task 49](tasks/49-library-admission-review.md). Scope is bounded cooperative
ownership by participating current application entry points: Qt owns a
full-app session, CLI owns a command session, and Tauri owns a full-app
session. Each session is acquired before initialization and retained through
its writers and worker cleanup. Explicit Core admitted-session APIs are
covered when called through such a session. Direct Core API calls without an
admitted session are nonparticipating, like arbitrary SQLite tools; they are
not promised automatic refusal. This does not claim a blanket guard around
every Core API. Task49 cleared the updated Windows 128-bit file identity
design at exact revision `53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`.
Task49 also approved the harness-only timing proposal below, with clarifications.
This is not native or full acceptance evidence. Current stage 2 focused tests
are reported below with review/receipt still pending; no full suite, frozen
build or native-platform test was run for this turn. Prior stage 1 Linux output
reports 16 tests passing in 1.427 s (log SHA-256
`4c436c8feb795b676f0ab51325a45d7209151c90b1891972b0aa241c9b9879b0`). This
does not establish overall acceptance; direct exit, environment and frozen
source/tree receipts are absent from that log.

All cases use disposable generated catalogs and media in a private temporary
directory. Use fixed fictional UUIDs and record only sanitized fixture names,
never user paths, catalog contents, IDs, or private logs in published evidence.
For every case capture source commit/tree, fixture manifest hash, OS/runtime
and SQLite versions, exact command, direct process exit status, stdout/stderr
hashes, and cleanup state. Preserve failed and interrupted attempts. Before
and after the suite, hash the frozen source inventory and all 15 deployed
output files; query catalog UUID, schema, row identities/counts, metadata,
SQLite journal/synchronous settings, source/cache/output trees. No acceptance
command may open the user's actual library.

## Evidence classes and shared oracle

| Class | What it can establish | What it cannot establish |
| --- | --- | --- |
| Core/offscreen generated-fixture tests | Deterministic service and adapter behavior on the executing host | Native desktop lifecycle, frozen packaging, or another OS adapter |
| Real multiprocess tests | Contention and process lifetime behavior on the named OS/runtime | Native Qt integration or frozen executable behavior |
| Native desktop | The named installed/test desktop flow, including close and worker cleanup | Other desktop systems or absent OS semantics |
| Frozen subprocess | The named packaged executable and child startup/cleanup path | Native desktop behavior or another OS |
| Hosted CI | Only the jobs, platforms, test totals, and named skips actually present in raw run/job records | A platform behavior skipped by the suite or an untriggered workflow |

An injected adapter result is unit evidence only. A Windows, macOS, or Linux
claim requires execution on that platform through its real native adapter. A
skip is not a pass. Each claimed desktop platform must demonstrate that its
native lease actually acquires, contends, releases on crash, and handles the
covered identity cases. A platform with no functioning adapter does not pass
admission acceptance; it must refuse the participating app entry point rather
than silently run without ownership. Recovery package publication remains a
separate, narrower platform claim. Network, removable, synchronized, and
unknown storage remain outside the supported live-catalog boundary unless
separately designed and accepted.

For all mutation-refusal cases, the shared exact oracle is: the contender
returns the documented actionable refusal within the design's configured
bound; it does not initialize, migrate, start a writer/job, or change catalog
bytes or metadata. Compare the contender's attributable delta, or compare
after the legitimate owner is quiescent; do not fail a test because the active
owner made its own authorized write. The contender also must not alter the
owner token/lease, unlink or replace the reservation, or modify source/cache/
output trees. Compare before/after hashes and SQLite integrity/settings, not
only UI text. For successful acquisition, the oracle is one valid current
owner, and all required work and owned children are complete before the final
release. The design commits only to a nonblocking native lock attempt
(`LOCK_NB` on POSIX and `LOCKFILE_FAIL_IMMEDIATELY` on Windows), with no sleep,
wait, polling loop, or retry. Task49 approved the following proposed
test-harness bounds: **250 ms** from API entry to typed
busy refusal in a responsive local contender. Start that timer only after the
contender process reports readiness; include all admission API work and exclude
process launch/startup. The harness gives a generated refusing contender **2 s**
to report its response and applies **5 s** containment only to that disposable
acceptance process after recording a failure. These are test controls only: they
are not product performance guarantees, global NFR budgets, or OS real-time
claims. Measure monotonic and process CPU durations. If a documented scheduler
stall exceeds the proposed 250 ms interval, retain the raw timing and classify
the timing result as inconclusive, never as a synthesized pass; still verify
the native nonblocking flag and absence of retry/wait. A missing refusing
contender response by 2 s is a harness timeout, not evidence of a valid refusal.
This 2 s bound does not apply to actual owned-worker cleanup. The 5 s
containment applies only to the disposable acceptance process after recording
a test failure and must not kill legitimate product workers; their existing
named lifecycle budgets remain in force. Report direct exits and
elapsed times, not wrapper success alone. Do not freeze these proposed values
as product targets; Task49 approved them only as test-harness controls.

## Named case matrix

| ID | Case and setup | Exact pass oracle |
| --- | --- | --- |
| ADM-01 | First participating Qt, CLI, or Tauri entry point opens a valid existing catalog for writing. | The corresponding full-app or command session acquires native ownership before schema/catalog initialization or any write-capable service starts; exactly one owner is visible; UUID, schema 7, row IDs and SQLite durability settings match expected fixture state. |
| ADM-02 | Independent process B requests the same catalog while A owns it. Synchronize both at a barrier and repeat with reversed start order. | Exactly one acquisition succeeds; loser satisfies shared refusal oracle within the declared bound. Repeat enough barrier-controlled trials to exercise both scheduling orders; no timing-only sleep is used as synchronization. |
| ADM-03 | Same process invokes explicit Core admitted-session APIs, nested services, and concurrent threads under an active Qt/CLI/Tauri session. | Session-scoped Core operations borrow the active session; no self-deadlock; operations serialize according to design; no second independent owner or premature release occurs when a nested operation exits. An unwrapped Core API call is not used to infer blanket admission behavior. |
| ADM-04 | Owner performs normal shutdown while no children remain. | New contender acquires after release; old owner no longer writes; persistent reservation/lock identity remains safe for subsequent contenders (no unlink/split-brain interval). |
| ADM-05 | Kill owner process without orderly shutdown while contender waits/retries. | OS-backed ownership becomes acquirable after process death without deleting a stale pathname or trusting PID text; contender either acquires or returns bounded refusal according to documented retry policy. Catalog integrity and settings remain valid. |
| ADM-06 | One participating app session holds admission; a second participating Qt, CLI, or Tauri app entry point attempts create/open/migrate against the same physical catalog. | Each covered conflicting entry point refuses before its first mutation/backup or publication action; shared refusal oracle holds. Direct Core calls without a session are outside this case. Restore publication is checked separately by ADM-18/19. |
| ADM-07 | After contender process readiness, hold admission and time a refusing contender under an intentionally held lease. | The native attempt is immediate/nonblocking with no wait or retry. Measure the complete admission API call (excluding process launch) against the proposed 250 ms bound on a responsive local contender. The generated refusal event has a 2 s response/cleanup harness deadline; 5 s containment may kill only the disposable acceptance process after recording failure. These are harness controls, not product guarantees. A documented scheduler stall over 250 ms makes timing inconclusive, never a pass. |
| ADM-08 | Participating parent app holds its full-app/command session while its existing workers run; include a strict read-only recovery backup child. | Parent retains source ownership until all owned writers/workers are actually stopped and cleaned up. A read-only child needs no delegated source-writer authority and cannot mutate the live catalog. The recovery restore child instead acquires ownership of its new destination as in ADM-18. |
| ADM-09 | Exercise any supported fork/inherited-worker path under an admitted parent, plus the documented spawn path. | No child inherits reusable source-write authority. Parent remains the owner through writer cleanup; any child that must write a catalog acquires a new destination session under the reviewed contract. Unsupported start modes refuse explicitly. |
| ADM-10 | Child startup fails before readiness; then a child exits late after parent requests cancellation/shutdown. | Startup failure is reported, resources are joined/closed, and ownership remains until the late child is confirmed stopped. New contender can proceed only after cleanup completes. No detached child writes afterward. |
| ADM-11 | Cancel an admitted job during active work, then immediately restart the same operation. | Cancellation and restart follow the existing worker lifecycle budget; restart is refused/serialized until old work is quiescent. No overlapping writes, orphan process, or partial state presented as success. Harness containment may kill only its own generated subprocesses after a test failure; it must not impose a new 5 s product-worker deadline. |
| ADM-12 | Open identical catalog through canonical path, relative path, symlink, and hardlink aliases (where OS supports each). | Aliases to the same physical catalog contend as one resource and satisfy shared refusal oracle. Unsupported alias form is recorded as such; no unsupported alias is silently reported as covered. |
| ADM-13 | Copy catalog bytes to a separate physical file while retaining the same logical library UUID. Open original and copy concurrently. | Both distinct physical resources may acquire independently; UUID equality alone does not create a conflict. Neither catalog nor cache is rewritten by identity probing. |
| ADM-14 | Two processes race to create the same missing catalog destination. Also race a missing-path reservation against a third opener after creation. | At most one creation succeeds; loser gets actionable bounded refusal, and no partial/empty competing catalog, lost reservation, or clobber occurs. A missing `open-existing` request refuses without creating anything. |
| ADM-15 | While a handle is open, atomically replace catalog pathname with a different generated database; try both a compliant admitted replacement and an external replacement. | At each documented pre-operation path/fd freshness check, current owner detects the observed identity change and refuses before proceeding; a compliant replacement is accepted only via reviewed protocol and fresh ownership. External replacement after the last check is outside the guarantee: do not claim prevention of all orphan-handle writes or a race-free boundary against nonparticipating writers. |
| ADM-16 | Migration with valid legacy catalog; inject failures before backup, during backup, after backup and at each migration boundary. | Ownership begins before backup or mutation. Each failure leaves original logical state recoverable, verified backup retained where produced, and no contender can write during the interval. No migration begins if admission fails. |
| ADM-17 | Exercise documented read-only inspection paths while a participating app owns the source catalog. | Read-only paths do not initialize schema/cache or mutate the source. Any app-owned read path follows its documented session lifetime; a raw Core call without a session is a nonparticipating limitation probe, not an automatic-refusal expectation. Hashes, settings, UUID, and row identities remain unchanged. |
| ADM-18 | Restore/inspection worker receives source catalog and writes a new isolated destination. Probe source owner and a competing application simultaneously. | Source worker is read-only where specified; source owner's active lease remains intact; only isolated destination is published after verification and destination ownership; another app cannot use spawned-recovery authority as a bypass to write source. Failed restore leaves source, holds, backup, and partial destination unpublished/intact per design. |
| ADM-19 | Restore destination aliases source or collides with an existing held destination. | Operation refuses before changing either catalog; source and destination lease/reservation remain intact; no in-place restore or hold removal. |
| ADM-20 | Compare baseline fixture before/after successful open, contention, migration, read-only inspection, restore and cancellation. | Stable library/asset UUIDs, catalog row identities/metadata, schema version 7, scanner semantics, pending/source/standalone holds, original generated media, cache/output trees and journal/synchronous settings are unchanged except for exact, documented operation effects. No operation changes SQLite durability settings. |
| ADM-21 | Current client against a fixture created by the prior supported package/client. | Existing verified automatic migration is allowed and reported according to its supported contract; migration admission and backup ordering still pass ADM-16. Any migration that is unverified or unreported, downgrade, discard, or overwrite fails. |
| ADM-22 | Historical client, direct Core API call without an admitted session, or arbitrary SQLite process attempts a write while a participating current app owns the catalog. | Record as a nonparticipating limitation probe only: success or SQLite-level contention is not represented as prevented by cooperative admission. Do not claim automatic refusal or enforcement against these writers. |
| ADM-23 | A nonparticipating generated SQLite connection holds a transaction that conflicts with a current admitted client's transaction. | SQLite's own busy/lock result is reported within the documented timeout and does not corrupt state or release admission early. This isolates SQLite transaction behavior from the admission refusal; it does not imply the external connection acquired or respected the app lease. |
| ADM-24 | On each claimed Linux, macOS, and Windows desktop platform, run acquisition, two-process contention, crash release, and alias identity cases through that platform's real native adapter. On Windows, exercise `GetFileInformationByHandleEx(FileIdInfo=18)` and the declared `FILE_ID_INFO` ABI. Also probe explicitly unsupported/unknown storage categories. | Every claimed platform's real adapter passes its native lease cases; injected results do not count. Windows must report the 24-byte, 8-byte-aligned structure, volume serial and complete 128-bit file identifier with specified byte order/golden values; zero/unsupported identity refuses, and a 64-bit fallback is a failure. Unsupported/unknown storage refuses before write when identifiable, and otherwise remains unclaimed. A missing/failing native adapter cannot count as acceptance or permit an unlocked app session. No broad NAS/removable/sync-folder claim from local tests. |
| ADM-25 | Native desktop launch, open, contender refusal, close during active child work, and reopen using generated fixture. | UI reports bounded refusal and does not launch conflicting jobs; close waits/reports cleanup according to contract; a subsequent launch succeeds only after prior ownership is released. Receipt names exact OS/build and generated fixture. |
| ADM-26 | Frozen executable spawns a supported child under real package entry point, including child startup failure and shutdown cleanup. | Packaged parent/child protocol works without development-only imports or implicit bypass; direct exits and process-tree cleanup are recorded; no remaining owned child/lease. Claim applies only to tested OS/package artifact. |
| ADM-27 | Exercise the physical-parent directory gate on every acquisition route: ordinary existing open/migration, create, and restore. Hold it at each protocol boundary and request admission for a different existing catalog in that same directory; also verify a separate catalog session already open before the gate remains active. | Each acquisition takes the gate before path/file reservation. A competing new acquisition may receive immediate busy while the gate is held; already admitted session work continues. After the owner signals the gate-release boundary, the same independent catalog acquisition succeeds within the normal bound. Create holds through initialization; restore holds through publication/binding. No unrelated catalog is changed. This temporary same-directory refusal is intentional. |
| ADM-28 | From Python and Rust, query the production registry namespace while `HOME`, `XDG_STATE_HOME`, and `XDG_DATA_HOME` vary; run a Python owner against Rust contender and vice versa using same OS account. On POSIX, also test missing/nonabsolute account home lookup and real/effective UID mismatch refusal where a safe generated host fixture permits. On Windows, compare both language adapters against known-folder and native `FILE_ID_INFO` ABI/golden fixtures. | Both languages resolve the exact protocol-defined OS-account namespace, never an env-selected path, and their versioned golden key/hash vectors match. Python and Rust must agree on Windows structure size/alignment, volume serial, all 128 file-ID bits and byte order; no truncation or 64-bit fallback. Cross-language owner/contender exclusion succeeds on each claimed native platform. Unsafe/missing identity cases refuse before catalog or registry mutation. Do not synthesize Windows execution on POSIX. |

## Historical Stage 1 implementation-to-acceptance gap map

This is the initial implementation snapshot; its evidence rows are not the current status. See the exact-candidate checkpoint below.

The existing focused Python implementation suite is `tests/test_admission.py`.
The prior stage 1 Linux artifact at
`work/library-admission-local/stage1-fork-corrected-tests.log` records 16
passing tests in 1.427 seconds; its SHA-256 is
`4c436c8feb795b676f0ab51325a45d7209151c90b1891972b0aa241c9b9879b0`. The
earlier `stage1-native-tests.log` also records 16 passing tests in 1.332
seconds (SHA-256
`5c42397a6fcd64c4b95cdb06b823576e156f820c9057888bd74ddf4f7bfce768`). These
are prior owner/reviewer results, not reruns or fresh independent verification
here. The artifacts list test outcomes but do not establish exact source/tree
hashes, direct exit receipt, frozen executable behavior, or acceptance.
Task49 cleared the fork cleanup correction at source `d0f82dbb16` for
integration. ADM-09 still requires native/frozen process evidence and final
acceptance review even though the focused stage 1 log records a Linux pass.

| Cases | Existing test evidence | Remaining acceptance work |
| --- | --- | --- |
| ADM-01, ADM-06 | No app-entrypoint integration test in the 16-test stage 1 list. | Add generated-fixture Qt full-app, CLI command, and Tauri full-app admission-before-init cases. Verify actionable platform-specific errors and no startup worker before acquisition. Test explicit Core session opt-in separately; do not imply low-level Core calls are wrapped. |
| ADM-02, ADM-04 | `test_owner_refuses_real_child_and_preserves_catalog` proves one Linux Python owner/refusal, and reacquisition after orderly release. | Add synchronized two-direction starts; record API refusal latency and process exits. Add all app entry points and Python/Rust parity. Existing one-direction probe is not evidence for the proposed 250 ms harness bound. |
| ADM-03 | `test_nested_session_retains_until_last_reference`. | Integrate session around real Core multi-step operations and app scope; add thread overlap and validate no premature release during nested work. |
| ADM-05 | `test_child_crash_releases_kernel_locks_without_unlink`. | Retain direct exit/hashes and run on each claimed native OS. Verify reservation files persist and are reused without stale-file deletion. |
| ADM-07 | No elapsed-time oracle in stage 1. | Add monotonic and process-CPU measurement after process readiness; include the complete admission call but exclude launch. Apply the reviewer-approved proposed 250 ms responsive-host API bound, 2 s generated refusing-event response/cleanup deadline, and 5 s containment only to the disposable acceptance process after recorded failure. Scheduler stalls over 250 ms are inconclusive, never passes. These are harness controls, not product NFRs. Verify native nonblocking flags and no retry/wait path. |
| ADM-08, ADM-10, ADM-11 | `test_owned_late_child_retains_session_after_context_return`, `test_reaper_start_failure_stays_owned_until_explicit_exit_reap`, and `test_cleanup_reference_survives_invalidated_catalog` cover retained references, reaper startup failure, and invalidated owner cleanup. | Add recovery backup strict read-only proof, actual app writer cancellation and restart sequencing, child startup failure, late child exit, and parent process-tree cleanup. Keep parent lease until its owned writer children exit. |
| ADM-09 | `test_fork_closes_inherited_handles_without_unlocking_parent` is present and passed in the prior stage 1 log; Task49 cleared source `d0f82dbb16` for integration. | This focused clearance is not native/frozen acceptance. Confirm spawn behavior and frozen worker entrypoints on each claimed platform and retain exact source/test receipts. |
| ADM-12 | `test_hardlink_alias_is_same_physical_resource`. | Add symlinked parent/final alias, relative path, case/Unicode-equivalent names, and actual directory gate races on case-insensitive hosts. |
| ADM-13 | `test_copy_independent_even_with_identical_content`. | Use valid catalog fixtures with the same logical library UUID and prove distinct physical copies acquire independently with rows/settings preserved. |
| ADM-14, ADM-27 | `test_create_keeps_directory_gate_until_ready` shows a transient same-directory refusal while a create gate is held and acquisition after ready. | Add two independent processes racing to create the same missing name, failed initialization cleanup, parent-directory transient-gate case for restore, and proof that pre-existing independent sessions keep working. Exercise every acquisition path's parent gate. |
| ADM-15 | `test_replacement_is_observable_and_never_adopted`. | Test each documented pre-operation path/fd validation boundary in participating entry points. Keep post-check external replacement explicitly out of contract; do not claim universal orphan-handle prevention. |
| ADM-16 | No migration/session integration test in stage 1. | Inject failures before/during backup and migration. Prove participating app session starts before backup/mutation and preserves original plus verified backup. |
| ADM-17, ADM-22, ADM-23 | No explicit RO or legacy busy-transaction test in stage 1. | Verify only named read-only app/recovery paths remain read-only. Exercise unwrapped direct Core API as a nonparticipating limitation case and SQLite's own busy result separately; do not expect admission's automatic refusal there. |
| ADM-18, ADM-19 | `test_restore_stage_stays_owned_across_publication` is a synthetic stage/hardlink lease test. | Integrate the recovery restore child owning absent destination before staging, full parent gate through publication, final identity binding, source backup RO behavior, and collision/alias/source-preservation cases. Publication support claims remain limited to actual platform policy. |
| ADM-20, ADM-21 | `test_owner_refuses_real_child_and_preserves_catalog` compares fixture bytes; no prior-package verified migration test is in this suite. | Run full generated catalog/source/cache/output preservation oracle, including schema 7, UUID/row identities, scanner semantics, holds, journal/synchronous settings, all 15 deployed outputs, and prior-package compatibility/verified migration. |
| ADM-24 | Stage 1 Python tests execute on Linux only. The native cross-language probe exists in `prototypes/tauri/admission-probe/` but is not listed in stage 1's 16-test log. | Build/run actual Linux, macOS, and Windows native adapters. On Windows, validate actual `GetFileInformationByHandleEx(FileIdInfo=18)` output and `FILE_ID_INFO` 24-byte size, 8-byte alignment, volume serial, full 128-bit identifier/byte order and golden cases; reject any 64-bit fallback. Run Python/Rust mutual exclusion both directions with HOME/XDG variations and golden vectors. Native platform claims require raw job logs; no emulated OS result counts. |
| ADM-25, ADM-26 | No native desktop or frozen-app test in stage 1. | Review generated helper before execution; separately exercise real Qt desktop lifecycle and frozen Qt/CLI/Tauri child startup/refusal/cleanup on each claimed OS. |
| ADM-28 | `test_protocol_golden` and `test_home_and_xdg_do_not_select_registry` cover Python protocol vectors and env independence on POSIX. Rust has `protocol_golden_vectors`; `test_cross_language.py` covers mutual exclusion/aliases/crash when built. | Run the actual Rust test and cross-language probe per OS, including env variations in both directions, POSIX UID mismatch/missing-home refusal where safely available, and Windows known-folder namespace plus native Python/Rust ABI goldens for 128-bit `FILE_ID_INFO` values and byte order. Do not infer from source inspection or synthetic non-Windows vectors alone. |

## Current exact-candidate evidence status (2026-10-18)

The current run used the reviewed uncommitted runtime overlay on base commit
`99d4e471d2dd207a3f44b1408eb6eb3197bca55d`, runtime ID
`597b1fbac1186a70af0e86370413b9c1d6bb82c2544f423fb3f4dee218fc913e`, and
freeze-manifest SHA-256
`23241cc013755bec0d8eef65120c38e623671c9c2b50bdd1ca0d1750d7cdaf9d`. It is
not a claim of equivalence to Git HEAD. Of 164 runtime/test/build inputs, 161
were retained and three changed relative to the first failed admission runtime
candidate `fdbeb370a94fa42632ad8d92a0a82e290dd44d2f629be294168c92278928638f`:
`defiantmaple/recovery.py`, `defiantmaple/thumbnail.py`, and
`tests/test_admission_recovery.py`. All 164 frozen inputs and all 15 deployed
outputs were unchanged pre/post the successful local sequence.

- Focused admission/recovery/thumbnail attempt 1: 43 tests, four failures and
  two errors, direct exit 1 while fixed-registry access was denied by the
  restricted sandbox. Preserve as a failed attempt.
- Focused attempt 2: 43 tests passed, direct exit 0.
- Full Core: 336 tests passed, direct exit 0; wrapper wall 118.287 s and
  unittest-reported 117.865 s. Public-artifact privacy check also passed.
- Full offscreen Qt: 192 tests passed, direct exit 0; wrapper wall 99.005 s and
  unittest-reported 97.339 s. This is offscreen evidence, not native desktop.
- Refreshed frozen package: the receipt records all nine named smokes passed,
  including recovery publication. Package direct exit 0; independent Task49
  validation of the receipt is pending. This remains package evidence, not a
  native desktop lifecycle claim.
- The first full Core run on the earlier candidate ran 335 tests and exited 1
  with one failure and one error. Preserve it as a real pre-fix failure. The
  earlier frozen package child exited -15 while its supervising helper exited
  1; neither is overwritten by the refreshed successful receipt.

The generated-fixture focused and full Core results provide bounded functional
evidence for the named cases. The offscreen Qt suite provides Qt service/UI
test evidence on the executing Linux host. It does not prove a mapped desktop
window or compositor lifecycle. The frozen package smoke does not prove native
GUI behavior. Unwrapped Core calls, old clients, external SQLite writers,
unsupported storage, and network/removable storage remain outside the
cooperative admission guarantee.

## Remaining execution and review gates

1. Independently review the sanitized results and frozen package receipt.
2. Review the exact generated-fixture native Qt helper source by hash before
   executing it. It must exercise the production launcher/window path, actual
   compositor visibility, a second CLI refusal, pending close with a registered
   generated idle child, and successful release/reopen only after actual child
   exit. This proves the named idle-child lifecycle case, not universal decoder
   or worker fault behavior.
3. Obtain the planned actual three-host Rust admission-probe and Tauri package
   CI evidence, recording actual job totals and skips. Windows/macOS adapter
   execution remains held until those records exist. No native Tauri GUI claim
   is planned.
4. Reconcile every ADM case with the resulting evidence, preserve named gaps,
   then complete Task49 privacy/evidence review before final sanitized results
   publication. Root owns publication and branch actions.

No new full Core or Qt rerun is requested by this checkpoint. Do not cancel or
rerun unchanged hosted jobs. No full FR-LIB-003 or release acceptance is
claimed.

## Preservation and compatibility checks

Run all preservation comparisons on generated fixtures. The comparison report
must enumerate checks and their hashes/counts; a single top-level success flag
is insufficient. Keep the migration/restore source, verified backup, pending
and standalone recovery holds, and original media untouched. Confirm all 15
deployed output records are byte-identical to the frozen baseline. Confirm
schema 7 and the exact SQLite `journal_mode` and `synchronous` values before
and after. Do not treat a successful integrity check by itself as proof of
preservation.

The cooperative protocol covers only participating current application
entrypoints and explicit Core calls made under their admitted session.
Historical application versions, direct Core API calls without a session,
arbitrary SQLite connections, hostile same-user code, and other external
writers are outside the lease's enforcement guarantee; SQLite may
independently serialize or reject some conflicting operations, but that is
not a product admission claim. The protocol is cooperative coordination, not
a security boundary. FR-LIB-003 is therefore bounded to the named entrypoints
and tested native adapters. This matrix does not establish full FR-LIB-003,
all of SDD v0.2, or release acceptance.

## Execution record and held evidence

Acceptance results belong in a separate sanitized results document and JSON
only after Task 49 review. Attach private raw logs and receipts by hash in a
private location; public artifacts contain no private paths, catalog data,
IDs, or raw logs. For hosted CI enumerate every actually triggered run and
job at the exact source head, including direct job conclusions, actual test
totals, named skips and their reasons. Preserve failures, cancellations and
incomplete runs as distinct states. Do not cancel or rerun unchanged jobs.

The previously pending merged-main CI audit at run `39096653218` was checked
against the actual run, job records, and Windows job logs. The run is for
merge commit `99d4e471d2dd207a3f44b1408eb6eb3197bca55d`, attempt 1, and
completed successfully with all 12 jobs green. Windows Python 3.11 and 3.13
each ran 311 tests successfully with 21 skips. Their named skips and raw-log
hashes are in the private receipt
`work/library-admission-ci/receipt.md`; 16 skips per run require the Linux
recovery publication adapter, with the remaining five covering POSIX FIFO,
resource-control, mount-rename, path-spelling, and effective-ID semantics.
These unchanged-main results are baseline evidence, not evidence for a future
implementation head. Native desktop, frozen subprocess, platform adapters,
and any missing/unsupported cases remain held until their own named evidence
exists.
