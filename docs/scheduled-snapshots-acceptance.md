# Scheduled local metadata snapshots acceptance protocol

Status: protocol draft for Task 51; broader implementation and acceptance have
not been completed. One bounded B3 offscreen Qt/native ordering slice has been
independently accepted as component evidence only. Design owner: [Task 50](tasks/50-scheduled-snapshots-implementation.md)
and its [scheduled-snapshot design](scheduled-snapshots-design.md).
Acceptance owner: [Task 51](tasks/51-scheduled-snapshots-acceptance.md).
Independent review: Task 52. This protocol is subordinate to the reviewed
design and does not change it.

## Scope and safety boundary

Verify the opt-in scheduled local metadata snapshot path while the application
is running, and its visible truthful status and managed retention behavior.
Keep the feature within the metadata-only package and local-storage boundary
specified by Task 50 and the SDD. Include a real SQLite-consistent backup, an
isolated restore, and compatibility with previously supported backup package
versions. The snapshot must not become a media backup, portable export,
automatic restore, automatic relink, or acceptance of FR-RECOVERY-006/007.

Use only generated private fixtures with fictional paths, UUIDs, media-free
source metadata, disposable package directories, and isolated child processes.
The fixture must be outside the application user's normal profile and outside
all real library, settings, and snapshot locations. Do not read, open, query,
hash, enumerate, change, or use as a baseline the user's actual catalog or
snapshots. Do not create or delete user snapshots or alter application
settings. If a test cannot prove it targets only its generated root, stop
before execution.

Before runtime work, capture a private baseline at merged base
`47effeeb5a5adf8b692023c49b67ee52a9025559`: every tracked source file hash;
the full SHA-256, byte length, file mode, and nanosecond mtime for all 15
deployed outputs; and all 129 requirement IDs and their current statuses. The
15 output records must match the earlier library-admission baseline exactly.
Do not modify or replace any output. The baseline command must only inspect
repository inputs and deployed-output paths; it must never access a catalog.
After document preparation, execute the baseline before any runtime acceptance
work. Audit read-only only the CI jobs actually triggered on merged-main base
`47effeeb5a5adf8b692023c49b67ee52a9025559`. Save real job logs, Windows
summary counts, and named skips. PR #24's older results are not evidence for
this base; do not rerun PR #24 or any unchanged job.

## Shared evidence rules

For each case record the exact source commit/tree and file inventory, fixture
manifest and hash, generated path mapping, OS/filesystem/Python/SQLite/runtime
versions, native adapter and admission result, exact command, process exit,
stdout/stderr hashes, monotonic and wall-clock timestamps, scheduler/worker
events, package hashes, before/after catalog and destination inventories, and
cleanup result. Preserve raw logs and private paths in private receipts only.
Publish only sanitized case IDs, host/runtime labels, counts, direct outcomes,
and evidence hashes after independent review.

Capture SQLite `integrity_check`, `foreign_key_check`, schema version, stable
row keys and exact generated-row comparisons. Use SQLite's supported online
backup API (or the exact reviewed Task 50 procedure), never a casual copy of a
live main database file. Prove that the snapshot is one coherent point in
time while a controlled second connection commits around and during backup.
Inspect/restore only closed generated package bytes. Restore into a new
nonexistent generated destination; compare the source catalog and original
package before/after. Do not claim no source-media reads from only a hash or
directory comparison. Only test code paths that operate on generated source
metadata; keep originals absent or instrumented fixture files that are never
opened by the application.

For every generated fixture and operation, capture catalog main/WAL/SHM
membership and bytes, SQLite journal/synchronous settings, source-root and
media membership/bytes/stat, derived-cache membership/bytes/stat, restored
hold/paused fields, package set, and managed-directory state. Compare all
before/after values against the exact Task 50 allowance and explain every
intentional change, including generated package creation or retention deletion.
Rehash all 15 protected deployed outputs (full SHA-256, bytes, mode, and
mtime_ns) before and after each independently executed fixture/helper run; they
must remain identical to the private merged-base baseline. Any unexpected
delta stops dependent cases and remains a preserved failure.

All background work must acquire the real native library-admission lease
before initializing, querying, or writing the source catalog. A mocked lease
does not qualify native platform support. Record owner identity, child PID,
start/stop/reap events, and all live workers before cleanup. A second scheduled
tick or manual trigger while a snapshot is active must not create an
overlapping writer or child. Cancellation is cooperative at supported
checkpoints; the parent retains ownership until the owned child is reaped or
reports an explicit uncertain outcome. Never kill or reap an unrelated process.

The scheduler/status oracle uses a controlled injected clock only for unit
tests and the actual host clock for platform end-to-end evidence. Displayed
last-success time must identify a completed, verified publication, not a
scheduled time, child start, stale file, or package merely present on disk.
Set last-success only after a package is verified and its ledger/status is
durably recorded. If publication occurred but durable recording is uncertain,
retain the package, do not advance last-success from memory, and show an
uncertain outcome. Once a new last-success is durably recorded, a later
retention, cancellation, or cleanup failure must preserve that success and
appear separately as the latest attempt/cleanup outcome; it cannot roll back
or relabel the verified success. Failures, cancellations, refusals, stale
results, and unverified attempts before that durable-success boundary do not
advance last-success. Record timezone and UTC values; wall-clock changes must not
cause overlapping runs, erase a verified outcome, or fabricate a success.
After restart, status and next-run behavior must reconcile from persisted
state; monotonic intervals are reconstructed conservatively and never guessed
from a regressed wall clock.

Retention must select only validated, application-managed package files under
the generated managed root, using stable identity and no-follow checks. It
must never follow symlinks, treat replaced files as owned, delete unrelated
files, or delete the last verified recovery point. Inventory and verify the
remaining set after each retention operation. Storage policy must expose its
configured bounds, account for package size and required temporary space, and
fail visibly before claiming a new successful snapshot if capacity is
insufficient. Storage types outside Task 50's reviewed local-supported set
must refuse the scheduled operation clearly and without scheduled-worker
catalog reads or managed-destination mutation. This refusal must not disable
ordinary admitted catalog opens or existing manual backup/restore paths.

## Named case matrix

| ID | Setup | Exact pass oracle and evidence |
| --- | --- | --- |
| SS-01 | Opt-in is disabled; app runs and time advances past a schedule boundary. | No scheduled snapshot begins, no new child/package is created, and status remains truthful. Existing explicit backup controls retain their separately documented behavior. Record settings and all generated destination bytes unchanged. |
| SS-02 | Generated catalog and managed destination; opt-in enabled; scheduler reaches one due time while app is running. | The ordinary app open already holds real native admission, and the scheduled worker validates that same session before scheduled source-catalog access. Exactly one owned worker produces a closed, verified SQLite-consistent metadata-only package. UI/status reports success only after verification and durable publication. Capture process events, package hash/manifest, integrity checks, and exact generated catalog row equivalence. |
| SS-03 | Use a controlled second SQLite connection to commit rows before, during, and after the online backup operation. | Package is a single coherent database state. It includes all commits visible at its SQLite snapshot boundary and excludes later commits; it never mixes inconsistent tables. `integrity_check`, `foreign_key_check`, manifest size/digest, schema and row-oracle all pass. Preserve each commit timestamp/order and package bytes. |
| SS-04 | Clock jumps forward across several schedule intervals and backward before the last recorded success; restart app during the shifted interval. | No overlapping job or burst of catch-up workers occurs. Last-success remains the verified package timestamp; next-run display is deterministic and truthful under the approved Task 50 policy. UTC and local-zone records agree. A fake-clock result is labeled unit evidence; host-clock behavior is separately captured. |
| SS-05 | Snapshot worker is active; issue a second schedule tick and a manual snapshot request, then close/reopen application during a controlled child boundary. | At most one snapshot writer/owned child exists. Triggers are coalesced/refused as Task 50 defines. On restart, old child is either confirmed reaped or retained as explicitly uncertain; no new job races it. No stale status is presented as a fresh success. Record owner/child lifecycle and all files. |
| SS-06 | Cancel at each reviewed backup/publication/verification/state boundary; inject child errors before verification, after package publication, and after durable last-success recording; separately inject cancellation or failure during later retention/cleanup. | Before a verified package is durably recorded, last-success remains unchanged; if publication occurred but durable status recording is uncertain, preserve the package and report uncertainty without claiming it as a durably recorded success. After verified last-success is durably recorded, later cancellation, retention, or cleanup failure preserves that timestamp/package and is recorded as a separate latest outcome. Never delete a verified point to make a failure look clean. Incomplete stages follow reviewed cleanup rules. Parent keeps admission until child exit/reap. Capture each phase boundary separately; blocked filesystem calls are not called promptly cancellable. |
| SS-07 | Successful current-format snapshot; inspect and restore into isolated generated destination. | Real inspect verifies format, digest, schema, SQLite integrity/relationships, then restore creates only a new separate destination. Stable generated row IDs/metadata/relations match exact design allowances; source holds remain protected; original catalog and package remain byte-identical. Restored library is not activated or opened implicitly. |
| SS-08 | Previously supported metadata backup package from the existing compatibility fixture set. | It is recognized and processed according to the documented prior-format contract. If unsupported, refusal occurs before target creation and does not change source/package; do not overstate compatibility. Capture package fixture provenance/hash privately and exact result. |
| SS-09 | Multiple verified generated snapshots exist; configured keep-count and/or managed-byte budget would require pruning. | Only application-owned, verified snapshots matching the manager's captured identities are candidates. Retention preserves at least one last verified recovery point and reports deleted/retained counts truthfully. Verify every remaining package and all unrelated files. Do not add an age policy unless Task 50 design is explicitly revised and reviewed. |
| SS-10 | Managed destination contains a symlink, replaced pathname/identity, unrelated file, corrupt package, or file with a matching-looking name. | No-follow and identity checks reject unsafe candidates. No symlink target or replacement is deleted; unrelated content stays byte/stat-identical; corrupt/unverified data never counts as a verified restore point. Preserve each generated adversarial fixture. |
| SS-11 | Remove/rename managed destination during run; inject disk-full/short-write/fsync/publish failure at reviewed boundaries. | Before verified publication and durable status recording, last-success does not advance; if publication occurred but recording is uncertain, retain the package and report uncertainty. A failure after durable success preserves that last-success and package while reporting a separate latest retention/cleanup outcome. Existing verified point and unrelated content remain. Never delete the final path merely to make status appear clean. Capture filesystem and directory state before/after. |
| SS-12 | Exercise the reviewed bounds: snapshot payload at most 16 GiB; full package at most `HEADER.size + MAX_MANIFEST_BYTES + MAX_SNAPSHOT_BYTES` (header plus the bounded manifest plus payload); 4 MiB state document; 1,024 ledger entries; 4,096 audit records; retention keep-count 1–1,000 and byte budget 1 MiB–1 TiB. Include exact-boundary and just-over values with generated sparse/fault adapters where needed; separately inject actual ENOSPC at staging/publication boundaries. | Reject values beyond explicit design limits before unbounded allocation or catalog mutation; accept in-range values where the tested storage permits. Do not silently evict audit history when state capacity is reached. Retention over-budget/disabled outcomes follow Task 50 stop-before-run behavior and preserve the last verified point. Free-space estimates are advisory; do not invent a temporary-space or catalog-size cap. Report actual disk-full outcomes separately from mocked preflight tests. |
| SS-13 | Run on each claimed real supported native adapter and each unsupported storage/platform class. | Supported host acquires actual admission and completes named cases through its actual implementation. Unsupported host/storage refuses scheduled publication, scheduling reads and retention on the scheduler path; ordinary admitted catalog opens and existing manual backup/restore behavior remain available. Do not claim refusal before the normal app-open/ admission path has identified the catalog. Mocked Windows/macOS outcomes, generic POSIX behavior, and unrun hosted jobs are not native results. Preserve actual CI totals and named skips. |
| SS-14 | Exercise Task 50's user-visible controls and settings persistence through the actual app-running path. | Opt-in, schedule, retention, destination and last-result status match persisted settings after restart. Invalid/unavailable destination is explained, not silently redirected. No unrelated settings change; no profile-level user setting is created or altered during acceptance. |
| SS-15 | Open the same unchanged generated physical catalog through the ordinary app/admission flow after restart; do not select or reattach the managed schedule directory. Then repeat with a moved catalog, copied catalog sharing its UUID, replaced catalog identity, missing locator, corrupt locator, and changed managed-directory identity. | The enabled schedule for the exact unchanged physical catalog resumes through a durable external locator without a second folder-selection step. Locator/state is versioned, bounded, permission-checked, atomically persisted and durably reconciled. Any missing/corrupt/uncertain locator, moved/replaced catalog or directory, or same-UUID physical copy visibly suspends scheduled source reads, scheduled publication and retention. This must not refuse ordinary admitted catalog opens or existing manual backup/restore. The scheduler must not read the catalog or mutate the managed directory under an invalid locator/binding. Old packages and settings remain unchanged; no unrelated catalog may inherit this schedule. A design that requires manual reattachment after every restart does not pass automatic restart continuity and must remain an explicit design gap. |
| SS-16 | With two cooperative scheduler attempts/configuration processes, race retention at each observable boundary: before candidate enumeration, after enumeration, after exact identity/content verification, immediately before unlink, after unlink and before durable ledger/status update, and after directory-sync uncertainty. Concurrently replace a candidate, remove/replace the managed directory, corrupt the ledger, and exhaust bounded state capacity. | The real schedule lock and pinned native handles serialize supported cooperative operations. Before every deletion, revalidate directory binding, exact candidate physical identity, package digest/size, ledger ownership and the last-verified invariant. A changed or ambiguous candidate, corrupt/exhausted ledger, lost destination, failed fsync, or uncertain post-unlink state stops further pruning and reports the exact uncertainty. At least one verified recovery point and every unrelated file are preserved; any completed deletion is recorded truthfully. Capture deterministic barriers/faults at each boundary and actual native behavior on each claimed platform. Do not claim protection against hostile same-user code beyond the reviewed OS handle/lock semantics. |
| SS-17 | On the qualified generated Linux/native fixture, pause an actual original manual-inspection child and, separately, an actual original restore child after each has opened the exact package through `_read_package` and acquired its shared lease, before the first header byte and through descriptor close. While each lease is held, start a retention attempt requesting exclusive lease on that candidate. Also run a compatible shared read of the survivor. | Shared leases are held on the exact no-follow read-only package descriptor from before the first header byte until extraction/verification closes it. Retention's candidate exclusive request returns the reviewed typed-busy outcome without durable deletion intent, unlink, package/state change, or loss of last-success. Shared survivor readers remain compatible. Caller-provided hashes/identities cannot make the contender authoritative. Record original child target/PID, actual descriptor/native identity, read boundary, lock result, and full package/managed-state preservation. This is generated lease evidence only; it does not prove retention unlink/executor behavior. |
| SS-18 | Reverse SS-17: acquire the candidate exclusive lease and survivor shared lease in reviewed native-identity order. Attempt actual manual inspection and actual restore of the exclusively held candidate; vary its name/identity while a reader is contending. Repeat cancellation and child-crash cases with the real descriptor-owning child paused. Also pause a generated retention lease holder at its completion barrier. | Candidate readers receive typed refusal before the first package byte; a path replaced while waiting fails native-identity revalidation and is not read. A contender remains refused until the actual lock-owning child exits and closes its descriptor; cancellation requests or process-context return alone do not release ownership. The retention holder keeps candidate-exclusive and survivor-shared descriptors open through its reviewed final completion boundary and releases them only on completed close or confirmed child exit. Before executor integration exists, this is a non-destructive lease-lifetime barrier only, not proof of ledger/unlink integration. After confirmed close, acquisition can proceed and all package bytes, prior verified success, survivor and unrelated files remain unchanged. Preserve exact child/process and lock-release evidence. This cooperative advisory-lock guarantee excludes old/noncooperative clients and hostile same-user mutation. No native unlink is part of this case. |
| SS-19 | On a generated configured library, exercise the desktop durable-stop control while an actual admitted scheduled operation and child are live. Inject stop-request, durable readback, stop-acknowledgment, enable/run-commit and control-reopen failures before and after their persistence boundaries. Crash/reopen with `stop_requested`, and interleave two Disable requests plus an older operation completion and a queued Enable using captured request UUID/control version. | A committed `stop_requested` suppresses every automatic run and retention attempt after restart. Restart reports saved stop with prior cleanup UNKNOWN and never infers cleanup from PID absence, new admission, or an idle QThread; unresolved exact, absent, or changed managed-deletion intent remains unchanged and visible. Only the same live controller session may write `stopped`, after exact QThread completion and proven owned process/stage cleanup, using the same request UUID and expected control CAS/version. A newer stop remains the veto and cannot be overwritten by an older completion or stale Enable. Failed/uncommitted request persistence never reports saved/disabled; committed request with lost acknowledgment remains a veto; failed stop acknowledgment keeps the UI suspended; failed Enable leaves missing/mismatched/stopped control that vetoes work. Stop/request/ack fault cases preserve last-success, ledger, configuration revision, package bytes and intent. For Enable faults, verify the exact durable configuration before/after boundary: a pre-commit failure leaves the old revision/configuration intact. Missing, mismatched, or uncertain `run` state remains vetoed with the live session suspended. If the exact valid `run` record was durably committed by explicit Enable but its UI/readback acknowledgment was lost, reopen may reconcile that exact committed state without rollback or duplicate Enable; a newer stop still wins by control CAS. Preserve the exact committed revision/configuration and do not treat a mere result signal as commit evidence. |
| SS-20 | Attach actual scheduled and manual operations to the same generated admitted library owner and shared per-owner recovery slot. Exercise scheduled-vs-manual contention in both directions for backup, inspect, restore, mapping, review and Enable. Inject process-start failure, callback/retention exception, cancellation, timeout, late child exit and deferred cleanup while a dialog closes or its result/QThread completion arrives first. | The contender is refused before work starts while the shared slot is owned. Use original process targets and actual `Process` objects; no source-owner token is serialized to child arguments. Retain the actual owner and slot through the exact owned child/stage cleanup; a result signal, dialog visibility, API return or QThread completion alone cannot release them. Exact filtered reaping touches only owned children; the original worker remains the sole stage-deletion owner, and a recreated stage name remains preserved/uncertain. After confirmed cleanup, the slot releases and ordinary manual inspection/recovery remains available. Source catalog family, media/cache, packages, last-success and unrelated files match their allowed case-specific changes. |
| SS-21 | Exercise the Qt controller against generated real admitted owners while closing, reopening, switching libraries, or replacing/moving/copying the source between request and worker execution/result delivery. Advance injected clocks across jumps, busy periods, restart, and multiple timer wakes. | Workers retain and validate the exact captured admitted owner and physical catalog identity; they never redirect by selection, UUID alone, or a newer global session. Stale replies/stop acknowledgments are rejected by controller/request epoch and cannot update a later window. Library close prevents new work and retains the GUI admission claim until actual actor/process cleanup and QThread completion; hiding the settings dialog does not stop the saved app-running schedule. The next-deadline timer wake is bounded to at most once per minute, does no filesystem/catalog work on the GUI thread, and creates at most one due attempt with no overlap or catch-up burst. Same-path replacement and copied/moved catalogs suspend scheduling without disabling ordinary admitted opens or manual recovery. Label offscreen, frozen, and native display/input evidence separately. |

## B3 component evidence accepted within its limited scope

Independent review accepted two actual offscreen QApplication/controller/native
backend ordering cases. The first verified child/actor cleanup before genuine
backup QThread completion, then a durable stop acknowledgment after the real
finished event. It retained the newly verified third package and last-success
while exposing the later cleanup warning. The second verified a genuine backup
QThread finish while its actual child, actor, and upstream ownership remained
pending; it refused acknowledgment until the child exited and original stage
cleanup completed. The child exited nonzero because cancellation reporting
reached the original `_worker_main` result-send path after its receiver had
closed; the captured `BrokenPipeError`/EPIPE traceback and exit classification
are retained as a declared fault, not a successful child result. Both cases
verified durable stop readback, execution of the original stopped-state
observer, independently reread final state/control, and preservation. The
run froze 408 repository inputs, 13 private dependencies, and all 15 protected
outputs with matching pre/post records.

This accepted evidence is limited to those two offscreen controller/native
orderings. It supplies partial evidence for SS-19 and a single scheduled-owner
contention refusal relevant to SS-20; it does not establish visible
GalleryWindow/settings/manual-dialog behavior, a manual inspect/restore
lifecycle, restart or lost-ack reconciliation, other CAS/close/timer races,
full SS-19–21 acceptance, frozen behavior, or native display/input behavior.
The acceptance protocol remains open.

Private evidence identifiers (SHA-256): external launch proof
`bce92ee70fbc13e5bab1714721abed4abe01789c98e2ae01b32e13f38ff9ce74`; wrapper
receipt `8e6597942f70dd6150ab9413847d7d86039f1009ef015c0c521ed7f578b2f181`;
actual Qt/backend receipt
`de1220fa6c90ac8d6a4e7fd05eb83831c26381aec172e14ab38d93a7ebcba492`;
independent bounded acceptance review
`e9bfd96c50bf3d424f10da9236659f7a9b09b37cf1a98467349e437ff68b8530`; and
independent local audit `c2afb2f07a698e603b5070b187e614a69acadfc598984e6a6ea4bd413780d435`.
These hashes identify private receipts/reviews; their contents and generated
paths remain private.

## Completion and remaining limits

Every mandatory case must have a direct outcome and evidence class. Failed,
interrupted, unrun, or skipped cases remain explicitly open; do not fill gaps
with local mocks or inferred CI status. Preserve current requirement IDs and
statuses during preparation and execution. Do not claim full SDD or
FR-RECOVERY-003 acceptance unless all requirement language is independently
reviewed against actual evidence. This protocol is not permission to merge,
deploy, replace outputs, or modify the requirement tracker. Task 52 and Root
must review proposed results and any requested source/public-document changes.


## W2-A bounded native window checkpoint

The [reviewed public derivative](evidence/scheduled-snapshots/window-a-attempt1/acceptance.json)
records four passed offscreen cases: original admitted startup with no saved
schedule, real settings Enable/hide and original verified metadata backup,
unchanged physical-catalog reopen under a new admitted owner in the same process,
and ordinary unadmitted startup without scheduling construction/discovery.
The outer receipt digest is `ca5acb242b85eb677e6f87d503dba9cee445bd720c7a583874bc063481726b88`;
inner `0f48306ee0ceba729c85eb05a879524c2476cf082f7587f67cf7a04cbd9436fe`;
independent audit `22dd34aaff7bc70bdca5853afd0ca181b640ef02938ec33155780c7c791f543c`.
Seven original children exited zero; twelve genuine Qt threads and seven exact
stage-cleanup calls completed, owners closed with zero references, and all frozen
input/output facts matched. Generated source catalog/media/cache were preserved.
The 137.021-second whole-fixture duration includes setup, actions, workers and
reopen; it is not a backup latency benchmark.

This is partial evidence toward the existing acceptance IDs, not full SS-19–21 or
FR-RECOVERY-003 acceptance. Real manual-dialog success/exclusion/close, integrated
Stop checkpoints and durable restart/lost-delivery cuts, elapsed clocks, visible
and frozen UI, platform limits and current-head CI remain open. Reuse the accepted
29-case/A3/B3/manual-actor evidence; do not repeat unchanged lower-level suites.
Raw receipts/logs remain private; the derivative omits private paths, PIDs and
fixture/native identities. No deployed output was replaced.
