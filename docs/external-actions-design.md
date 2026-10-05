# Captured external handoffs: Task 29 decision

Root approved this design against Tasks 29–31 and SDD v0.2 §§11/17/21.
Schema remains v6. The service writes no catalog rows or original media and does
not reconcile on external process exit. Machine-local configuration is separate
from portable catalog information. The two actions open a file or its containing
directory; the latter makes no file-selection/highlighting promise.

`OpenTarget` freezes the displayed UUID, revision, absolute path, SHA-256, byte
size and optional source ID. `OpenAction`, `CommandSpec`, `ExternalSettings` and
`ActionLimits` are typed immutable descriptors. Capturing a displayed target is
lexical and performs no source stat/resolve/read on the GUI thread. Selection,
filter and settings changes cannot replace a request's target or command.

Standalone indexed assets with no source ID and no source entry are supported.
Source-backed assets require one exact indexed entry matching ID/path/source ID.
Source health is last-observed scan information: paused/watching are eligible;
scanning requires scan completion; offline, permission_denied, error, missing,
pending or inconsistent linkage refuse until explicit scan/reconciliation.
Probing does not rewrite health or infer restored availability. Actual current
facts are checked again because health alone does not advance asset revision.

One gallery operation is admitted at a time. A QThread supervises one spawned
helper; all blocking catalog/source/executable/settings I/O stays off the GUI.
No waiting job queue or replacement worker is started while busy or after a
cleanup failure. File checks reject missing/denied/nonregular originals, bound
the read at 512 MiB, hash content and compare device/inode/size/mtime through an
open descriptor and path. Folder opening verifies the same original first, then
its parent directory. These are operational refusal bounds, not performance or
general format acceptance claims.

Settings are loaded lazily on explicit use; an action freezes its target before
loading and retains the same overall deadline through that first-use load.
The absolute five-second deadline includes helper startup, lock acquisition,
source validation and handoff. After probing, the helper emits READY and waits
for one permit. Probe-only smokes never grant it. The supervisor grants a permit
only before its deadline and while uncancelled. The helper checks deadline and
cancellation again before dispatch. A timed-out probe cannot later request a
handoff. Lost acknowledgement after a permit is **uncertain**, with no automatic
retry. An OS request already started cannot be made ACID/cancellable; opening a
window later does not mean DefiantMaple admitted a post-deadline request.

After slow content validation, a short `BEGIN IMMEDIATE` reservation covers the
final catalog identity/state recheck, path/parent identity recheck and dispatch.
No rows or PRAGMAs change. Failure/helper exit releases the reservation. The
filesystem can still change between final check and an external application's
own access; this is not a race-free filesystem transaction. Trusted executables
and fixed arguments are user choices, not a sandbox for an external application.

Configured dispatch uses `[absolute_executable, *literal_fixed_args,
absolute_target]`, `shell=False`, closed inherited descriptors and no stdio
pipes. There is no command-template expansion, PATH search or media-name shell
interpolation. Windows .bat/.cmd shell wrappers are refused. Fixed arguments
are bounded at 32 values/4096 characters, without NUL/newline separators. Native
fixtures use trusted Python plus a generated read-only handler and a receipt
path as fixed arguments; the original target is one separate literal argument.

Default dispatch constructs `QUrl.fromLocalFile` and calls `QDesktopServices`
in the isolated helper's private Qt application, never the gallery thread.
No handler/association is installed. Qt documents that true means an OS request
was accepted; external opening/saving may still fail without a callback.
[Qt 6.11 QDesktopServices](https://doc.qt.io/qt-6.11/qdesktopservices.html),
[local-file URLs](https://doc.qt.io/qt-6.11/qurl.html#fromLocalFile).
Default associations are mocked in this milestone's tests; native acceptance
demonstrates configured stub dispatch only.

An acknowledged external application is user-owned and may continue running;
DefiantMaple does not wait for its exit, infer a save or kill it on gallery close.
The probe/dispatch helper is terminated/reaped with bounded 0.1/0.5/0.5-second
waits on completion, timeout or cancellation. A kernel-blocked process may resist
reaping: retain its reference, report cleanup incomplete and disable replacements.
Uninterruptible real-share behavior remains unqualified. Gallery close requests
cancellation and remains asynchronous until the worker reports its outcome.

Settings use a versioned machine-local JSON document outside the catalog and
registered artwork roots. Load/save use a separately bounded helper under the
same gallery admission limit; writes use a unique temporary file and atomic
replacement. Saving does not import executable trust from catalog metadata or
alter global OS associations. The configured command is frozen before a request.

Current packaging is pyside6-deploy/Nuitka, with `freeze_support()` already at
the application entry point. New helpers are top-level importable functions.
The authorized minimal package addition runs `--smoke-external-probe-id` through
the same Qt worker/spawn/hash/READY path as the UI, explicitly withholds dispatch
and verifies reaping plus source/catalog preservation. Existing smokes, metrics,
workload and archives are retained. This smoke proves frozen worker validation,
not a native external-editor launch or new benchmark result.
