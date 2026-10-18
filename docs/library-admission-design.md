# Cooperative application library admission

Task47 reviewed-design candidate. Base: merged PR23
`99d4e471d2dd207a3f44b1408eb6eb3197bca55d`. Runtime changes await Task49.

## Bounded user contract

Current Qt, CLI and Rust/Tauri executables acquire an explicit admission session
before initializing/migrating a library or starting work. Ownership lasts for
that application/command and all its owned workers. A second current executable
refuses promptly with an actionable plain-text Qt/Rust error or bounded CLI JSON
error: close the other application using this library and retry. Existing
Windows/macOS/Linux functionality is preserved; native adapters require actual
hosted execution before acceptance. Unknown adapters fail explicitly.

This is same-user cooperative application coordination. It is not a security
sandbox, multi-user broker, exclusion of earlier clients, or protection from
arbitrary SQLite tools, direct unadmitted Core API calls, hostile same-user code,
network/filesync semantics or externally replaced files. Generic Core
`connect`/`initialize` remain unchanged. A public `admission_session(path, ... )`
context lets Core callers opt into the exact executable agreement for a whole
operation; using low-level APIs without it is explicitly nonparticipating.
There is no claimed automatic Core enforcement and no caller-supplied bypass.

FR-LIB-003 receives this bounded current-application contract. FR-LIB-004 remains
an honest local-live-catalog support boundary: NAS/removable source media is
separate; writable SMB/NFS/active-sync catalogs remain unsupported. No automatic
active-sync detection or universal storage certification is claimed. Preserve
schema7, logical UUIDs, every row identity, SQLite journal/synchronous settings,
scanner semantics, recovery holds and all existing external-action guarantees.

## Fixed registry and native adapter

Lock only permanent regular files in one fixed per-user registry. POSIX uses
the OS account home from `pwd.getpwuid(os.getuid()).pw_dir` plus
`.defiantmaple/admission-v1`; refuse missing/nonabsolute home or differing real
and effective UIDs. Rust uses checked `getpwuid_r` for that same real UID,
including bounded buffer growth/error handling. `HOME`, XDG variables and
language convenience home functions never choose this registry. Windows uses native
`SHGetKnownFolderPath(FOLDERID_LocalAppData)` plus `DefiantMaple/admission-v1`;
never use a caller-selected environment registry or silent fallback. Both
languages resolve the identical fixed location. Different OS users are outside
this agreement. Tests may construct an internal
adapter with an isolated registry; executable flags never select it.

Registry files contain no catalog data, path, UUID or PID. Lock names are SHA256
of the versioned key bytes specified below, followed by `.lock`. Never unlink,
rename, truncate, replace or stale-delete these files. Existence is not
ownership: only an exclusive OS lock held by an open handle is ownership.
Create POSIX registry directories mode0700/files0600, check user ownership,
regular-file/directory type and final-component symlinks. Existing unsafe paths
refuse rather than repairing permissions. Windows opens directories/files with
native reparse-point inspection; rejects reparse files and nonregular lock files;
uses the current user's known-folder namespace and ordinary inherited ACLs.
This is not independently certified hostile-user/DACL protection. No stronger
Windows private-directory claim is made. Unexpected native errors refuse.

Linux/macOS use `fcntl.flock(LOCK_EX|LOCK_NB)` on registry descriptors. Rust uses
an equivalent native flock wrapper with identical semantics. Windows uses
`CreateFileW(OPEN_ALWAYS, GENERIC_READ|GENERIC_WRITE, FILE_SHARE_READ|
FILE_SHARE_WRITE)` for registry lock files (no delete sharing), then synchronous
`LockFileEx(EXCLUSIVE_LOCK|FAIL_IMMEDIATELY)` on offset0 length1. Retain the native
OVERLAPPED structure until explicit `UnlockFileEx` and handle close. Contention
is an immediate `LibraryInUseError`; no wait, retry loop or unlocked fallback.
Native structures use exact pointer-width/layout declarations and checked return
codes. No lock touches SQLite's own catalog byte ranges.

Catalog and parent identity handles use `CreateFileW(OPEN_EXISTING,
FILE_READ_ATTRIBUTES, FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE)`;
directories add FILE_FLAG_BACKUP_SEMANTICS. `GetFileInformationByHandle` is
used only for attributes/reparse/type checks. Identity uses
`GetFileInformationByHandleEx(FileIdInfo=18)` and native `FILE_ID_INFO` with a
64-bit VolumeSerialNumber and FILE_ID_128.Identifier[16]. Interpret those 16
identifier bytes as one unsigned little-endian integer; serialize its exact
unsigned decimal value (up to 2^128-1) in the existing id2 field. The native
FILE_ID_INFO layout is 8-byte volume followed by 16 identifier bytes, with
8-byte structure alignment. Refuse zero/unavailable volume or file IDs,
unsupported native calls and malformed results; FileIdInfo requires Windows8 /
Server2012 or later. Never fall back to the old
64-bit BY_HANDLE_FILE_INFORMATION file index (not guaranteed unique on ReFS).
Use the same native operation for every Windows comparison. POSIX uses
open descriptor fstat device/inode. Identity handles stay open through ownership,
preventing identifier recycling. Windows does not use Python stat numbering as
a substitute. Handle sharing preserves existing SQLite and freshness behavior.

Primary native semantics:
[flock](https://man7.org/linux/man-pages/man2/flock.2.html),
[LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex),
[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew),
[GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle),
[FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info),
[GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex).
Documentation does not replace native execution evidence.

## Shared key protocol and acquisition

All decimal numbers are unsigned ASCII without leading zeroes. A key is UTF8
ASCII prefix plus fields separated by newline, including final newline:
`dm-admission-v1\n<kind>\n<platform>\n<id1>\n<id2>\n<leaf-hex>\n`.
Platform is `posix` or `windows`. Kind is `directory`, `path` or `file`.
IDs are POSIX device/inode or Windows 64-bit volume/128-bit file identifier. Directory/path keys use
parent IDs; file keys use catalog IDs. Leaf-hex is empty except for path keys.
POSIX leaf-hex encodes exact filesystem basename bytes in lowercase hex; Windows
encodes exact basename UTF16LE bytes in lowercase hex. Golden protocol vectors
must match Python and Rust. UUID never appears: physical copies/restores may
legitimately share a UUID and remain independently writable.

Every acquisition first takes an exclusive nonblocking directory gate keyed by
the pinned physical parent identity. This gate prevents case-insensitive and
Unicode-normalization-equivalent missing-name creation races without guessing
filesystem normalization or sharing incompatible language Unicode tables.
Resolve relative paths and directory/final symlinks to the intended target
first, pin the existing parent, and recheck after native open. Missing parent
creation is handled explicitly by launcher/CLI setup before catalog admission;
never initialize or start workers while resolving it. Core session API refuses
missing parents. CLI init may create its requested parent directories as existing
behavior requires, then pins the resulting parent before any catalog creation.

While gated, acquire the exact pathname reservation, open/pin an existing regular
catalog, acquire its physical-file reservation, and recheck directory/path/file
identity. Release the transient directory gate only after these are established.
Keep pathname and physical reservations throughout the application lifetime.
All acquisitions use directory, pathname, physical order and are nonblocking;
partial failure releases in reverse order. No waiting deadlock is possible.

For an absent create, hold directory gate and pathname reservation before
exclusive file creation (`O_CREAT|O_EXCL` or CREATE_NEW), pin/acquire its physical
reservation, and initialize that file before releasing the directory gate.
If a name appeared unexpectedly, refuse/revalidate, never overwrite. A crash may
leave an empty catalog; unchanged initialization rules govern its subsequent
admission. For restore, hold the directory gate through isolated stage creation,
verified publication and final identity binding, then release it. This causes
bounded temporary refusal when another application tries to open/create even an
unrelated catalog in that directory during create/restore. Existing owners in
that directory continue normally. This conservative acquisition contention is
intentional and does not serialize ongoing independent catalog sessions.

Hardlinks across directories converge on physical identity. Case-insensitive or
canonical-equivalent existing names also converge on physical identity. Their
pathname hashes need not match, because the directory gate closes the missing
file/physical-pin gap. Distinct files with the same UUID remain independent.
No compliant workflow replaces an existing admitted catalog. External
rename/unlink/replacement is outside coordination; retain existing inode/epoch
freshness checks, and session validation detects changed pinned paths before
new executable-level jobs. A race after that check is not claimed prevented.

## Entry points and lifetime

`admission_session` is UI-independent, with a process-local synchronized manager,
strong owner references and explicit `validate()`/retain/release. Nested sessions
inside the same process borrow only an existing matching pinned pathname and
physical identity; PID mismatch or changed identity refuses. There is no
serialized authority token or `already_admitted` boolean. Acquisition and release
are reference-counted; last release follows actual owned work completion.

| Entry point | Contract |
| --- | --- |
| Qt launcher create/open and direct `app.main` catalog startup | Acquire before initialize, then transfer same-process owner reference to window without gap. |
| Qt model/gateway/metadata/curation/collections/scanner/cache work | Covered by retained application session; existing Core calls do not reacquire. Validate before new jobs and keep current inode/epoch guards. |
| Qt direct model SQLite connection | Preserve existing behavior unless a separately justified RO change is needed; session covers it. |
| CLI init/index/list/duplicates/add-source/list-sources/scan/pause/resume/thumbnail | Own one session around entire command dispatch, including multi-connect scans and spawned helpers. Non-catalog inspect-zip needs none. |
| Explicit Core caller | May wrap its whole multi-step operation in public session API; low-level unwrapped Core calls do not participate. |
| Rust/Tauri app and benchmark execution | Matching native RAII owner in AppState before opening catalog or spawning work, held for execution lifetime. Preserve update_asset_at functionality. Validate before commands. Same key/adapter protocol as Python. |
| Recovery backup | Parent active-library session remains; child source SQLite handles become validated mode=ro, no independent metadata writer. |
| Recovery inspection | Package/stage-only isolated operation, no live ownership. |
| Recovery restore | Child independently owns absent destination before staging; publication boundary below. |
| Recovery review/enable source | Runs under active Qt/CLI session or explicit participating Core session; durable holds unchanged. |
| Thumbnail decode and external/settings children | Owned helpers, no independent application acquisition. Existing hold checks and external final BEGIN IMMEDIATE remain. Parent retains owner until actual helper exit. |
| private_eval EvaluationStore | Separate store; reject physical samefile alias of supplied live catalog before executescript. Standalone unadmitted use otherwise outside agreement. |
| Fixture/benchmark raw SQLite generation | Developer-generated artifacts, not product coordination entrypoints. |

Window shutdown first rejects new jobs, cancels/drains workers, closes readers
and then releases the session. A timeout is not proof of worker exit. Strong
references survive `_UNREAPED_WORKERS`, thumbnail terminate/kill timeouts and
external helper late cleanup until actual process exit. Admission code must
provide a small owned-process retention/reaper facility if existing cleanup can
return with a live child; it must not release merely because a request returned.
External applications launched by an action are not catalog workers and do not
retain admission indefinitely after confirmed handoff.

At-fork cleanup clears process-local manager state and closes inherited native
descriptors without explicit LOCK_UN: flock's shared open-file description means
child unlock would release the parent lease. PID guards cover missed inheritance.
Spawn remains the recovery method. Frozen spawn entrypoints never start their
own application session before dispatching owned child work. Child startup
failure/cancellation/kill all retain references through proven process cleanup.

Parent crash releases its OS locks; surviving owned helpers can only read catalog
state/reserve SQLite briefly or finish private derived output. They must not
perform independent catalog row mutations. Original media remains read-only.
Recovery restore differs: its independently owned destination lease survives
for its full mutation/publication lifetime even if its parent crashes.

## Recovery publication

Restore child acquires destination directory gate/path reservation itself before
its first stage mutation; parent must not pre-own that key. Existing private-local
publication policy remains Linux-only. Child pins/acquires the stage physical
lease, then preserves it across hardlink publication to final. The final file is
identity-checked and the manager binds its pathname reservation to that same
physical lease before releasing the directory gate. There is no release/reacquire
gap. Keep all existing absent-family, schema/UUID/integrity, backup compatibility,
uncertain-publication and source/standalone/pending-hold checks. No restore
switches the active catalog, enables sources or starts scanning.

Backup parent's session remains retained through real child termination. Child
uses mode=ro for source checks and SQLite backup; no token/delegation is needed.
A parent crash can therefore leave only a read-only backup operation. Package
inspection has no live writer authority.

## Acceptance and holds

Task48 generated subprocess oracles cover one-winner races for existing open,
create, migration and restore; hardlink/symlink/relative/case/Unicode aliases;
Python/Rust parity vectors and mutual exclusion with varied HOME/XDG variables
and identical OS-account namespace; same-process borrowing; retained
worker shutdown/cancellation/late exit; crash reacquisition with stale registry
files; registry unsafe-path refusal; physical copies sharing UUID; observable
replacement invalidation; old SQLite busy behavior with explicit old-client
limits; and frozen spawn startup/refusal/cleanup. Contender preservation hashes
use a quiescent owner or attributable deltas. No timing-only readiness waits.

All current Windows/macOS/Linux tests remain intact. Actual hosted native
adapters must execute; fake platform names are insufficient. Root owns exact-head
CI, review, commits and draft publication. Preserve all 15 deployed outputs;
no deployment, scheduling/retention, export, relink or source-writing changes.
Full FR-LIB-003 acceptance remains bounded by this stated participating-client
contract, native evidence and independent review.
