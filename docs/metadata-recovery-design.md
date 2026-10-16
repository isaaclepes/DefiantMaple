# Metadata-only backup, inspection, and isolated restore design

Status: reviewed design amended for the Core implementation, 13 October 2026;
the amendment requires repeat independent review. No acceptance is implied.
[Task 41](tasks/41-metadata-recovery-implementation.md)
owns the bounded implementation; [Task 42](tasks/42-metadata-recovery-acceptance.md)
owns evidence. This first slice covers explicit schema-6 backup, package
inspection, and restore to a **new** local catalog. It preserves the existing
schema, journal mode, synchronous policy, originals, caches, and live catalog.

## User contract and limits

The user selects an existing local library and a new backup package path.
Backup takes one SQLite-consistent metadata snapshot, verifies the closed
snapshot, and publishes one metadata-only package. Inspection reports package
and catalog versions, digest/integrity result, omissions, and unverified source
roots without restoring or opening media. Restore requires a verified package
and a new, nonexistent catalog path on eligible local storage; it creates a
separate catalog and leaves it in a durable browse-only state. The user must
explicitly open that catalog. No operation implicitly scans, relinks, opens,
moves, or writes originals.

The package contains the entire schema-6 SQLite catalog, including original
absolute paths, metadata, taxonomy, aliases, asset IDs/revisions, provenance,
source entries, collections and order, and curation history. It does not
contain original media or derived previews/cache. Current schema 6 has no
stable `library_id`, stored rule set, or executable bindings; none is invented.
Out-of-catalog credentials/settings are not packaged, but freeform catalog
fields and paths may themselves contain sensitive text. This is a private
metadata backup, **not** a redacted or portable export and not an authenticated
package: SHA-256 detects accidental/tampered bytes only when the expected hash
comes from a trusted channel. The UI states these limits before writing or
restoring. Restored paths are reported as unverified even if they happen to
exist on this machine.

Scheduled retention, media-inclusive backup, portable export/import, sidecars,
general cross-instance writer coordination, a stable library ID, and automatic
relinking remain separate milestones. Thus FR-LIB-005 and FR-RECOVERY-001/002/
004/005 gain only bounded partial evidence; FR-RECOVERY-003/006 remain open.

## Package format and untrusted inspection

One `.dmbackup` regular file avoids archive extraction and directory entries.
Version 1 is exactly: eight-byte magic `DMETA1\0\0`, unsigned big-endian
32-bit manifest byte length, unsigned big-endian 64-bit snapshot byte length,
canonical UTF-8 JSON manifest, then the raw closed SQLite snapshot, with no
trailing bytes. The manifest is at most 64 KiB; the snapshot at most 16 GiB;
the file length must equal the sum before allocation or SQLite opening.
Canonical JSON has unique fixed keys: `kind=metadata-only`, `package_version=1`,
`catalog_schema=6`, `snapshot_bytes`, `snapshot_sha256`, `created_utc`, and
fixed omission declarations for media/cache/out-of-catalog settings plus
`source_paths_unverified=true`. It contains no arbitrary filename or extraction
path. Unknown fields, duplicate keys, invalid UTF-8, noncanonical encoding,
invalid value types, unsupported versions, digest mismatch, or extra bytes
cause refusal. The manifest records verification facts, not a signature or a
claim that catalog freeform data was scrubbed.

Inspection opens the selected regular package through a platform-specific
no-follow handle; it rejects symlinks, Windows reparse points, nonregular
files, changing file identity/length, and oversize input. It hashes bounded
chunks into a private temporary regular file, closes and verifies the digest,
then opens only that immutable closed copy with SQLite read-only settings in
an owned worker process. It authenticates supported schema declarations and
version, runs `integrity_check`, `foreign_key_check`, required relationship/
orphan checks, and bounded identity probes. The worker has a finite wall-time
and memory/size budget; the parent can terminate and reap it. The package is
never mounted or executed and SQLite extension loading is disabled. A
successful manifest hash does not make an untrusted SQLite file trusted; all
validation stays inside the bounded worker. If a platform cannot enforce its
handle, containment, or process limits, inspection refuses there.

## Consistent snapshot and worker lifetime

The backup worker obtains a read-only source connection and a private staging
destination, and uses SQLite's online backup API. It does **not** copy a live
main database file. Use finite pages per step (initially 256), finite SQLite
busy timeout (initially 100 ms), a monotonic cooperative deadline (initially
120 s), and a finite restart/no-progress budget (initially eight detected
restarts). The worker rejects an initial
`page_count * page_size` above 16 GiB before creating the staging database,
rechecks each progress callback's reported total against the same bound, and
keeps the final closed-byte size check. Another connection may commit while
backup runs: a step holds a source read lock only for that step, and writes
from another connection between
steps can restart the backup. The completed backup is one consistent state;
continuous writes may otherwise prevent completion. Progress can regress on
restart and must be shown as indeterminate until verification completes.

The worker checks cancellation/deadline at progress callbacks and phase
boundaries, closes both SQLite connections in `finally`, and reports success
only after the closed snapshot passes the same schema/integrity/relationship
checks and its bytes are hashed. A blocked filesystem operation is not
interruptible by a Python callback; the parent requests cancellation, then
kills and attempts bounded reaping of its owned process at the deadline. A
kernel-blocked process that remains alive after kill is retained for later
bounded reaping and staging cleanup, with an uncertain outcome reported; the
UI cannot claim it was reaped or that all descriptors closed. A killed or
crashed worker never returns a published success. Clean up bounded staging
files on ordinary failure; surface cleanup failure explicitly. App/window
close cancels and attempts bounded join/reap, then retains exceptional live
worker ownership and reports the unresolved state instead of blocking the UI
indefinitely. If source files
change after completion, the package still represents its completed snapshot,
not a promised later live state.

## Local paths and no-overwrite publication

Live catalogs and restored catalogs must be in a private local directory
outside media roots and the caller's complete captured cache-root set. Backup
and restore require that set explicitly; an empty set asserts there are no
protected cache roots for this library. The APIs cannot discover arbitrary
caches made by other programs, so the Qt caller captures every cache root it
manages and discloses this placement limit. The initial package destination is also a
private local directory on a filesystem supporting same-directory hard links;
remote/offline archive copies are a later operation on a **closed verified**
package. The platform storage adapter checks the resolved destination and
every parent against symlink/reparse/junction redirection, verifies a trusted
private parent and that the final leaf does not exist, then checks local
filesystem eligibility: fixed local NTFS on Windows, APFS/HFS+ with the local
mount flag on macOS, and a verified local mount and backing filesystem on
Linux. UNC/network mounts, active sync locations when identified, unknown
mount types or indeterminate backing, source roots, cache roots, and the live
catalog file and SQLite sidecar names are refused. A package leaf must end in
`.dmbackup`; a restored catalog leaf must end in `.sqlite3`. Restore accepts a
captured current-live-catalog path or explicit `None` when there is no live
catalog; the worker rechecks that captured file/sidecar family before writing.
Restore also refuses any pre-existing sidecar name for its new target, both
before staging and immediately before publication; it never removes those
entries.
Distinct new files may share the same trusted private parent. Source-root
containment checks may resolve directory aliases to compare placements; they
do not enumerate or open original media files. Active sync software cannot be detected
reliably on every platform, so the UI asks the user to choose a private local
directory and discloses that limitation; it never treats an unknown mount as
local by assumption. A test-only storage adapter may certify disposable CI
locations without weakening production checks.

The first Core checkpoint implements only a Linux adapter for a private
owner-only parent on a verified NVMe controller with `transport=pcie`; other
block buses and indeterminate backing refuse. macOS and
Windows refuse until their native adapters are implemented and reviewed;
the cross-platform acceptance item remains open.

Stage the complete package or restored SQLite catalog under an unpredictable
name in the same trusted parent. Flush the regular staging file (`fsync`/
`FlushFileBuffers`), close it, and verify its length, hash, and identity.
Publish with a same-directory hard link from stage to the absent final leaf:
link creation is atomic create-if-absent, unlike replace/rename on POSIX.
Refuse when hard links or a secure parent-handle operation are unavailable;
never fall back to a copying/overwriting publication. The POSIX adapter uses
directory file descriptors and no-follow operations. The Windows adapter uses
reparse-safe handles, private directory ACLs, and an atomic NTFS hard-link
create; it rechecks parent and file identity. A platform without that adapter
does not claim support. After link creation, verify final identity and content,
remove staging, and flush the parent directory where the platform/filesystem
supports it. POSIX success requires file and directory sync. Windows file
flush plus readback is reported accurately; directory-entry power-loss
durability is not promised without an evidenced supported primitive.

If a crash occurs before the link, only staging remains; after the link, the
final file is already complete and staging may remain. Recovery never deletes
an existing final path solely because a late flush/readback failed. Report an
uncertain publication and require inspection. This prevents overwriting a
prior recovery point and avoids a partly written final path. The trusted
private-parent boundary excludes a hostile process with write access to that
directory; if ownership/permissions or path identity cannot be established,
refuse. For restore, close the SQLite database and ensure no live WAL/journal
sidecar is required before stage verification and publication.

## Restored-catalog safety and explicit path review

Schema 6 has no durable recovery-state table. Use SQLite's persistent 32-bit
`PRAGMA application_id` header as a **state marker**, not as a library identity:
historical/current active catalogs have `0`; reserve `0x444D5250` (`DMRP`)
for `RESTORE_PENDING`; any other nonzero value fails closed. The restore worker
sets `RESTORE_PENDING` and sets every restored source to `enabled=0,
health='paused'` with a reserved `health_detail` review hold derived from its
source ID and exact stored root in the staged catalog before verification and
publication. Its exact value is the ASCII prefix
`defiantmaple:restored-root-review:v1:` followed by lowercase hex SHA-256 of
`UTF8(source_id) || 0x00 || UTF8(root_path)` using the stored strings without
path normalization. This allows an independent oracle to compare the intended
source-row delta. The hold persists after the catalog marker clears; ordinary
source enable refuses it, and ordinary health updates preserve it. Only the
captured per-source root review clears that source's hold. The display shows a
readable review message instead of the reserved token. The
package snapshot is never modified. This preserves asset IDs/revisions,
provenance, paths, metadata, and collection order. It does not create a schema
version 7 or change `user_version`. A backup of a pending catalog retains its
marker; restoring any package always produces pending state.

Current-build Core admission reads the marker from the actual opened catalog
before original-media reads/actions. The marker check precedes even source
path resolution, `stat`, directory enumeration, or a decoder open: current
`index_file` resolves and stats its input before `connect`, so its operation
order must change. Pending and unknown states refuse source
scans (`scan_sources`, including its CLI path), direct `index_file` (including
its CLI path, before opening its input), fresh cached-preview generation,
direct `thumbnail_for` (including CLI/smoke callers), full-original inspector
and comparison loads, external open/action dispatch, and any other original
path consumer. `prototypes/qt/preview.py::_decode_original` currently receives
only an asset and opens its path inside a child process; its worker protocol
must carry the captured catalog path/identity and asset ID/revision, open that
catalog read-only in the child, requery the asset, and run the shared Core
admission check **immediately before** decoding. A button-state check or a
parent-only `generation_refusal` check is insufficient. The same child-time
check applies to any comparison worker that opens originals. The Core guard
must requery source enabled/state and target identity from the same connection;
do not trust UI row projections. Keep catalog metadata and already verified
cache-only previews browsable. Each Core original consumer checks that a
captured path is outside every held root and inside its approved source root;
an approved parent-source scan refuses overlap with a held descendant before
enumeration. Directory alias resolution may read path metadata but a refused
operation never opens original media bytes. Add a source-enabled check to
original-media admission after pending clears:
restored unapproved sources remain blocked, including when their health is
`paused`. Ordinary active catalogs with enabled paused sources retain their
existing behavior. Both the UI worker and Core recheck the durable marker at
the point of use; stale UI state cannot bypass it. The guard applies even to
`assets.source_id IS NULL` while the catalog is pending. Unknown application
IDs refuse catalog opening rather than being interpreted as legacy active.
Legacy builds predate this marker and may ignore it; users must not open a
pending restored catalog in an older build. This is a current-runtime safety
contract, not a cross-version security boundary.

Catalog opening must check supported `application_id` values before returning
data or starting workers. Audit raw `sqlite3.connect` use in the product:
`GalleryWindow`/gateway, gallery query, cached-preview and comparison helpers
currently bypass `catalog.connect`. Route those through a shared read-only
catalog opener or give each an immediate marker/version check; unknown IDs
must fail closed there too. Pending is permitted for metadata/cache-only
queries, while the shared original-media admission function refuses original
paths. Do not treat a launch-time check as sufficient for child or long-lived
workers, and do not break generated fixture setup connections in tests.

The narrow review/activation flow displays a bounded, complete list of source
IDs, stored roots, current root availability and access status. It captures
the catalog identity, full source mapping and exact stored paths before
review, with no automatic scan. The user explicitly confirms that every
stored root was reviewed, including unavailable roots that will remain
disabled. Core re-reads marker and rows under one `BEGIN IMMEDIATE` transaction
and refuses if the captured mapping changed or if any standalone asset exists.
It clears the pending marker only after these preconditions; all sources stay
disabled with their per-source review holds. SQLite's header update participates in the transaction, so failure
rolls the marker back. The UI then refreshes by catalog identity/epoch; late
worker replies cannot retarget the prior gallery. A separate explicit
per-source enable action captures ID/path, rechecks current mapping and
directory read/search access without reading media, then enables only that
source and clears its hold. No source scan or
original open is part of either action. A source that is later enabled through
the normal path still requires an explicit action; restored roots are never
automatically enabled by opening the catalog.
While any per-source hold remains, direct standalone `index_file` refuses
before resolving an input path. Direct indexing with an explicit approved
source refuses known held roots before path resolution, then checks the
resolved path is inside its approved root and outside every held root before
stat/open. This conservative standalone limit preserves ordinary standalone
indexing in active catalogs without restored holds.

Schema 6 permits standalone assets with `source_id IS NULL`. They have no
durable per-asset review flag. Activation therefore **refuses to clear** the
pending marker if even one standalone asset is present. The UI gives the
count and a browse-only/relink-needed result; it does not offer a warning-only
override or silently rewrite provenance. This is a real first-slice limit:
standalone metadata/caches can be browsed in the restored catalog, but its
original-media actions remain unavailable until a later explicit identity/
relink feature can review them durably. A linked-only catalog can activate
after the stated root review. Pending-state editing of source/asset mappings
is refused outside this review flow, so it cannot be used to evade the check.

## Acceptance and evidence boundary

Use generated fictional catalogs. Show a writer-before/during/after backup
produces one coherent snapshot; induce writer starvation, busy, cancellation,
worker crash, corrupt/oversize/unknown package, destination collision,
permission loss, disk-full and late publication failures. Check exact stable
IDs/revisions and relationship order; compare live catalog, originals and
caches before/after. Test pending source-backed **and standalone** original
refusal through Core and Qt, cache-only browsing, linked-source explicit
review/activation, standalone activation refusal, and existing enabled-paused
behavior. Exercise worker close/reap and stale target/selection replies.
Require focused tests, coordinated full discovery, actual native Linux and
hosted Windows/macOS/Linux exact-head results, named skips, privacy checks,
and independent review before any acceptance claim. Public evidence contains
no real catalog paths or raw logs. See [the acceptance protocol](metadata-recovery-acceptance.md).

## Technical sources

- [SQLite online backup](https://www.sqlite.org/backup.html) and
  [backup-step locking/restart behavior](https://www.sqlite.org/c3ref/backup_finish.html).
- [Python `sqlite3.Connection.backup`](https://docs.python.org/3/library/sqlite3.html).
- [SQLite database header and `application_id`](https://www.sqlite.org/fileformat2.html)
  and [SQLite PRAGMA reference](https://www.sqlite.org/pragma.html).
- [Python `os.link`, `os.rename`, and `os.fsync`](https://docs.python.org/3/library/os.html),
  [POSIX link no-overwrite behavior](https://man7.org/linux/man-pages/man2/link.2.html),
  and [Windows hard-link support](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw).
