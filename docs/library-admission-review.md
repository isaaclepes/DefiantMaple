# Independent library admission review

Task49. Design cleared for implementation at the exact revision recorded below.
Implementation and acceptance remain independently held.
Reviewed base: merged PR23 `99d4e471d2dd207a3f44b1408eb6eb3197bca55d`.
Initial design SHA256: `f4207126a0aa2f5abe0980057c8caf55d56249770da16d9506c596a7fa435f48`.
First amended design: `558b37fc1f5b468716f6fc16d2fff0aae5ba5900579940c947ed4bdc60dfc584`.

## Independent trace and findings

The permanent per-user registry, native nonblocking locks, physical file keys,
and separate pathname reservations form a defensible cooperative approach.
Logical UUIDs must remain independent. Different users, old clients, external
SQLite tools, active sync folders and network filesystem guarantees remain
excluded. SQLite transactions and durability settings retain their own roles.

1. **Open: platform and missing-name equivalence.** Exact macOS leaf spelling
   does not reserve equivalent missing names on a case-insensitive filesystem.
   `O_EXCL` prevents clobber but does not establish creator ownership before an
   alias opener races physical-lock acquisition. Specify a qualified native
   normalization or refuse this creation boundary. Windows owner/DACL, file ID
   and handle-sharing details need a concrete adapter or explicit fail-closed
   platform boundary before clearance.
2. **Open: operation-wide ownership.** Per-connection ownership alone leaves
   direct Core jobs unowned between connections. `scan_sources` and
   `thumbnail_for` must retain an operation owner across their full work and
   owned cleanup, as must direct backup and settings jobs where applicable.
3. **Open: spawned catalog readers.** `thumbnail._decode_worker` uses
   `catalog.connect` to check captured assets and durable source holds.
   `external_actions._settings_helper` reaches `catalog.connect` through
   `_settings_path`. Wrapping that connection without converting these children
   to validated read-only contexts would cause self-contention. Preserve their
   identity, schema, hold and freshness checks. The backup child has the same
   explicitly documented read-only resolution.
4. **Open: late child retention.** Thumbnail `_stop_process` can return after
   bounded terminate/kill joins without proving termination. A surviving cache
   writer needs retained ownership and a reaping path. Recovery's existing
   `_UNREAPED_WORKERS` must likewise retain ownership until actual exit.
5. **Amended, implementation pending: fork release.** A fork child closes its
   inherited native descriptors without `LOCK_UN`, resets the process manager,
   and cannot reuse serialized/PID-mismatched ownership. Explicit unlock of a
   shared Linux open-file description would release the parent's lock.
6. **Amended, implementation pending: private evaluation alias.**
   `EvaluationStore` checks pathname inequality before its separate SQLite
   `executescript`; a hardlink can still mutate the catalog. Reject physical
   aliases before separate-store mutation. Other independent stores remain
   outside the catalog agreement only under their documented boundary.
7. **Required: Rust bypass.** Rust `open_catalog` feeds real updates. Its
   mutating commands must either join the identical qualified protocol or
   explicitly refuse; read queries use a real read-only SQLite open.
8. **Required: restore transition.** The child retains final pathname ownership
   and the stage's physical ownership across hardlink publication, validates
   final identity, and closes all connections before releasing. Parent/child
   cannot compete for the same destination reservation or accept a bypass token.

## Primary adapter evidence

[Linux flock documentation](https://man7.org/linux/man-pages/man2/flock.2.html)
specifies open-file-description ownership, separate-open self-contention,
fork/dup sharing and release after all duplicate descriptors close. Its
network filesystem semantics differ, reinforcing the excluded storage scope.
[Microsoft LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex)
documents immediate-failure mode and handle/process termination behavior;
native execution is still required for any supported Windows claim.

## Acceptance protocol review

The 25 named cases are useful with these required clarifications before freeze:
ADM-08 permits a strictly read-only child instead of requiring a delegation
token; ADM-15 tests the observable path/fd freshness check and explicitly
excludes an external replacement after the check; ADM-21 retains existing
verified automatic migration policy. Refusal hash oracles require a quiescent
owner or contender-attributable changes, since an active owner may legitimately
change its own catalog/cache. No full SDD or release acceptance follows.

Implementation, native/frozen helper review, exact source/output preservation,
current-head CI/Windows totals, and sanitized public artifact clearance remain
pending. No runtime, output, source-media, commit or deployment changes were
performed by this reviewer.

## Agreed bounded revision, awaiting exact design

Root and Task47 agreed to scope automatic admission to the executable current
clients and an explicit public Core admission-session API. Generic Core
functions called without that session are nonparticipating; the implementation
must not advertise automatic coordination for those callers. This is a
defensible bounded application contract and removes the need to modify child
`connect` calls or add authorizer/token exceptions. Existing external-action
`BEGIN IMMEDIATE` handoff checks remain intact. Owned child cleanup still
retains the application/session owner until actual termination.

Task47 adopted a permanent per-parent-directory acquisition-gate key. Every
acquisition obtains this native exclusive nonblocking gate before reserving a
pathname and physical file. Existing opens release the gate only after both
identities are pinned and rechecked; creation holds through initialization,
restore through publication and final binding. This resolves missing-name
case/Unicode equivalence without guessing filesystem normalization. Temporary
refusal of another acquisition in that directory is an explicit tradeoff;
existing already-admitted sessions continue normally. Final pathname and
physical leases remain held for the full session.

Windows qualification may be bounded to a fixed native per-user LocalAppData
registry with no sensitive catalog data and no hostile-user security/DACL
certification claim. Native consistent file IDs and nonblocking LockFileEx
remain required. Windows/macOS current executable writer workflows must
continue through their qualified native adapter, with real platform execution
required before platform evidence is claimed. Exact revised design clearance
is still pending.

The exact candidate `10b7f38362528c0d412b4b67f51f9609f64027391722dc1f75f4519c42e761bc`
resolved the scope, child, native protocol and directory-gate findings above.
A clearance message was immediately withdrawn when Root identified the remaining
fixed-namespace defect: POSIX `Path.home()` follows caller-controlled `HOME`.
The final design must derive the POSIX account home from real-UID account lookup
in both languages, define real/effective-UID mismatch refusal, and test differing
HOME/XDG environments against the same registry. No runtime clearance is active
until the corrected exact design is independently rechecked.

## Exact design clearance

Cleared design SHA256:
`8ca4e334cb60241970a7de3ac97dcb386900f7c43f96842fbfe045ec1a4458d9`.
The on-disk hash was independently verified. This revision replaces
environment-derived POSIX home lookup with real-UID OS-account lookup in both
languages, refuses missing/nonabsolute home and real/effective UID mismatch,
and requires HOME/XDG variation interoperability evidence. The earlier namespace
blocker is resolved at design level. At clearance, tracked changes were docs
only; runtime implementation had not begun.

Runtime implementation may proceed under this exact bounded contract. The
initial broad-Core and child-self-contention findings are resolved by the
explicit executable/opt-in-session boundary, rather than by weakening existing
external handoff checks. Directory-gate acquisition resolves creation alias
equivalence. Private-evaluation physical aliases and late-child retention remain
explicit implementation requirements. Windows/macOS/Linux native behavior,
Python/Rust parity, all preservation checks and exact-file public/privacy
clearance remain evidence gates, not consequences of this design clearance.

## Incremental native adapter review

Stage1 is cleared for executable/recovery integration at Python source
`d0f82dbb9d073d307e98e4ed818f98d2e8d27d5621cd302647d001aee5ea6382`
and test source
`f539bd18ddb16e852ca7627e056187307db15523e64ac47701c747d4a9fd1cfb`.
The implementer records 16 Linux tests passing directly at this revision in
`stage1-fork-corrected-tests.log`, hash
`4c436c8feb795b676f0ab51325a45d7209151c90b1891972b0aa241c9b9879b0`.
The reviewer independently ran the same 16 tests successfully against preceding
source `05fd49a2edec76868b6b7ceadf6b43ebd4f32de6cd9c27a672c4a9bc84554a1a`;
that run establishes its named scope only. Final integrated evidence remains held.

Incremental findings resolved before integration:

- Owned-process waits now duplicate the exit sentinel instead of racing the
  caller's Process join/close. Separate waiter and recovery handles permit
  bounded explicit reaping. Failed thread startup retains uncertain ownership;
  stale catalog validation cannot discard cleanup ownership of existing children.
- Before-fork acquisition of the manager lock excludes descriptor open/close
  and restore binding transitions. Parent releases that lock; child closes
  inherited handles without explicit unlock and resets the manager. Inherited
  sentinel cleanup tolerates already-closed handles without abandoning leases.
- Nonblocking POSIX identity opens reject FIFO substitutions before waiting.
  Windows checks ordinary disk type, nonzero volume/file ID and absolute native
  known-folder namespace. Platform execution remains required.
- Rust pinned identity Files now outlive the lease fields by declaration order.
  Polling and cancellation remain available after stale-path detection. Native
  adapters are limited to the named Linux/macOS/Windows targets.

Rust adapter source reviewed at
`e844586a71cd77d813d50d4001a1867def54fa4600da485625bbf222f4bf9491`.
The independent golden vectors match its POSIX and Windows protocol hashes.
The standalone probe and three-host workflow exercise real native bidirectional
Python/Rust exclusion, readiness acknowledgments and crash reacquisition, and
preserve generated dependency locks/metadata. They are reviewed proposals;
neither local Rust compilation nor Windows/macOS execution has been observed.

## Windows filesystem identity qualification

An additional primary-document audit found that
[BY_HANDLE_FILE_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information)
does not guarantee a unique 64-bit file ID on ReFS, and identifies filesystem
specific stability differences. It documents NTFS identity stability until file
deletion. [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)
provides the separate 128-bit identity mechanism. The present versioned protocol
must therefore qualify its 64-bit native identity claim to tested NTFS profiles;
ReFS, FAT and unknown identity profiles cannot inherit a universal Windows claim.
Native filesystem-name qualification/refusal was recommended to both adapter
owners. This remains an implementation/evidence gate; no new filesystem support
or broad local-storage certification follows from a hosted Windows pass.

Root selected the native 128-bit identity correction instead of narrowing the
adapter to NTFS. The exact revised design
`53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`
was independently read/hashed and cleared before Windows source edits. It uses
`GetFileInformationByHandleEx(FileIdInfo=18)` with FILE_ID_INFO volume64 and
Identifier[16], interpreting the identifier reversibly as unsigned little-endian
u128 and serializing full decimal precision. Windows8/Server2012 minimum and
failure without a 64-bit fallback are explicit. The existing POSIX protocol
and clearance remain unchanged. Independent max-u128 and byte-order-sensitive
golden vectors were supplied to both adapter owners. Actual native layout,
alias/copy/replacement behavior and cross-language exclusion remain held for
execution; this correction creates no general ReFS or network support claim.

## Incremental executable integration review

The initial Stage2 candidate was held. Reviewed integration covers full CLI dispatch and
direct Qt startup/launcher transitions, application worker supervision, the
independently owned recovery destination, same-process GUI coordinator exclusion,
private-evaluation hardlink refusal, and the generated executable smoke/package
hook. The existing external final BEGIN IMMEDIATE handoff remains intact.

The reviewer identified and the implementation addressed recovery retention
failure after process start escaping normal cleanup; GUI preflight/startup
failure leaking a coordinator claim; and a generic background-worker close
timeout proceeding before actual completion. Same-process GUI claims remain
exclusive while explicit nested Core sessions can borrow normally. The new
executable smoke checks contender refusal, subsequent release/reopen and generated
catalog preservation. It does not by itself establish native GUI or frozen owned
multiprocessing cleanup; those need their separate execution receipts.

The proposed 14-file candidate manifest
`a6784e05dd1c88a6e9fd05a08ee3b396cac8f14dc85449194057c9adbda753cc`
was independently read/hashed, but source comparison found admission.py had
already changed. That manifest cannot establish the final source freeze.
Root additionally required restoration of the original schema/UUID admission
guard before the backup child's first source-root query after converting it to
read-only SQLite. Later snapshot verification cannot substitute for that guard.
Updated exact hashes and focused receipts are required before integration
clearance. An independent 19-test native suite passed during review, but source
drift prevents treating it as final exact-candidate evidence.

All 15 deployed outputs were independently compared to the private prechange
baseline: SHA256, size, mode and mtime_ns matched for all 15, with no differences.
This read-only check is interim preservation evidence; final freeze and output
comparison remain required.

The corrected integration candidate is cleared to proceed to full/native/frozen
acceptance at exact private manifest hash
`772c03535023df3650d8af31e2688b6b0615f5d966194e7577ed7892d37a1219`.
All 14 source/test hashes independently matched. The reviewed raw Core/CLI log
`28660f54c593a249510cda451cea34aa70ecf2c70f6a877f642dff087ce82aec`
reports 24 passing tests; the reviewed offscreen Qt log
`1864617decff07a8c13ea456aa3741f50f7096e502d57362ce141f5f274f3cae`
reports 4 passing tests, both with recorded direct exit0. These are focused
Linux receipts, not Windows, macOS, native desktop or frozen evidence.

Both backup read-only handles now authenticate schema/current UUID before
userdata reads. A generated malformed-identity/future-schema oracle verifies
the first source-root query is not reached and the source/output family remains
unchanged. Finished owned-process records are pruned after safe exit/handle
cleanup, while active and failed-reaper records remain retained. The generated
admission smoke and package hook are cleared for execution alongside the
existing smoke suite. No final runtime/platform/preservation/privacy clearance
is implied by this incremental acceptance-stage clearance.

## First full-suite hold

The first full Core discovery at runtime candidate
`fdbeb370a94fa42632ad8d92a0a82e290dd44d2f629be294168c92278928638f`
ran 335 tests and exited1 with one failure and one error. Task48 stopped before
Qt/artifact commands and did not rerun unchanged tests. Its raw stderr hash is
`cb435c2e6bd45990f59e9e3100aa8058f819d3970154868986d663cb5eaa08b1`.
Runtime input/output pre/post checks remained unchanged. Initial draft-publication
and final acceptance gates are held pending review and a new exact source freeze.

The thumbnail cancellation oracle patches the decoder and intentionally passes
an empty payload; the new unconditional database-key lookup raises before the
child starts. Participating-owner lookup must preserve that existing helper
contract. The concurrent-writer backup oracle encountered SQLite busy during
the restored UUID/schema guard, which library_identity wraps as an identity
ValueError. Do not accept generic identity errors as valid contention or remove
the guard; preserve typed bounded busy behavior while retaining refusal of
malformed identity/version before userdata queries. Any frozen attempt using the
prior snapshot remains evidence only for that old snapshot after source changes.

## Resumed bounded correction review

The two full-suite regressions are corrected at independently checked SHA256s:
thumbnail source `74dc5a6939ff23ee6ba2fdfeaf01862bb081eefc77ea5f912b204182a86af185`,
recovery source `29422c1141042145f656a3595ad64915716c66e770ffd9bb49b542b71e5843a8`,
and recovery admission tests
`28fa766ee42c6cd22f0df4f54c6e056b8d69e2d2f4f3e45d178ad6f8a13c912e`.
Thumbnail owner lookup is optional for the generic empty-payload cancellation
helper. Both read-only backup handles retain current-schema/UUID authentication
before userdata. A helper unwraps only a direct sqlite3.Error cause with a
native BUSY/LOCKED base code; other identity errors retain their original type.
Connection timeouts and schema guards are unchanged.

The independently read focused correction receipt records 43 tests passing,
direct exit0, unchanged source, and stderr SHA256
`6cc12b0328243354629119c6401c9e2c2872bc79906ac4ce921a1d23c7ada869`.
This includes the existing real concurrent-writer and empty-payload cancellation
oracles, malformed UUID/future schema refusal before source-root queries, and
native/extended BUSY/LOCKED versus non-contention exact-exception oracles.
The preceding restricted attempt remains retained: 43 tests, four failures and
two errors from fixed-registry write refusal; it is not replaced by the later
authorized successful attempt. This correction is cleared for a fresh exact
freeze and full suites, not final acceptance or platform support.

Initial publication review permits an explicitly INCOMPLETE draft to collect
actual Rust/Windows/macOS CI only after the new full suites pass. Exact public
file selection and staged-byte review remain required: private work receipts,
catalogs, logs and build trees are outside the public allowlist. The existing
public checker scans tracked files and cannot alone clear new/untracked files.
No hosted platform pass, native/frozen pass, final output comparison or final
independent acceptance is implied by this conditional publication strategy.

The second candidate freeze was independently checked at SHA256
`23241cc013755bec0d8eef65120c38e623671c9c2b50bdd1ca0d1750d7cdaf9d`:
all 164 runtime/test/build files match the working-tree bytes, with exactly the
three corrected files above changed and 161 retained from the first freeze.
Runtime candidate identity is
`597b1fbac1186a70af0e86370413b9c1d6bb82c2544f423fb3f4dee218fc913e`.
Its public-file map is an archival documentation snapshot, not final publication
clearance. The second private frozen-build helper was independently diffed and
hashed at `e37a86ff961350ba7fb1c9e49f149edaa934f4bc27766ecd324306e5f4b8ad51`;
only freeze filename, freeze hash and runtime identity differ from the reviewed
first helper. Its generated 100k catalog, nine frozen smokes, provenance,
process cleanup, 164-input and 15-output preservation checks are cleared for
execution. This is helper review, not a successful build or smoke receipt.

## Corrected full local suite review

Task48's second full local receipt was independently read and hashed at
`5d6ad6d180e238dcca0cfc1b82c010bd5aaad6b8320ca4020334484926431172`.
All six stdout/stderr hashes and the pre/post snapshot hashes match. Sequential
Core discovery ran 336 tests in 117.865 seconds; offscreen Qt discovery ran 192
tests in 97.339 seconds. Both report OK and direct exit0, as does the intervening
tracked public-artifact checker. The commands use the reviewed working tree,
Python 3.14.7, PySide6 6.11.2 and Linux; only Qt adds the offscreen override.
These are real local full-suite receipts, not hosted or native desktop evidence.

All 164 runtime hashes match freeze2, and their hashes/size/mode remain unchanged
across the suites. All 15 outputs match the baseline in SHA256/size/mode and
remain unchanged; this receipt does not record mtime_ns. Final preservation
must retain its separate complete metadata comparison. The tracked privacy
checker passed within its documented limited scope; final staged-file review
still gates initial publication. Fresh frozen/native evidence, actual current-head
Rust/Windows/macOS CI and final independent review remain held.

## Fresh frozen Linux evidence review

The reviewed second private frozen build completed successfully. The independent
review verified receipt SHA256
`749e3861ab1c5b5be77c6bce56d7bb366fe5dfe3810b689de05ebd2533db35c8`,
all four raw command-log hashes, metrics SHA256
`843ab63096f2719b64ce9788446b742dfc5682a74d5ff90ff70e2801f30c283a`,
and package-log SHA256
`7c882053dabc95de7cba2d4743efd7c496c6c6534feb55acefb8a825d4baf60e`.
All commands exited0 without timeout and were reaped. The private binary is
51,297,792 bytes, mode755, SHA256
`c712019fd83ef6a4fb54d3c4333891facad600e7c79d02b929acad5c18f8aab4`.

All nine frozen smokes passed, including qualified local recovery publication.
The admission smoke reports contender refusal, valid continuing ownership,
release/reopen and unchanged catalog. Recovery reports real spawned backup,
inspection/refusal and restore, preserved tables/source cache, one source hold
and reaped worker. The generated benchmark catalog was independently opened
read-only immutable: integrity OK, schema7 and 100,000 assets. Temporary smoke
catalogs were cleaned by their helpers; their preserved metrics and reviewed
oracles establish the named smoke assertions rather than retained databases.

All 164 current repository and private build inputs independently match freeze2
and the recorded pre/post maps. All 15 deployed outputs independently match the
baseline in SHA256, size, mode and mtime_ns. The receipt records no remaining
private workers. This is bounded Linux frozen evidence for this exact artifact;
native Qt desktop, actual current-head Rust/Windows/macOS CI, exact staged public
privacy review and final independent acceptance remain required. No output was
replaced and no broader platform or release acceptance follows.
