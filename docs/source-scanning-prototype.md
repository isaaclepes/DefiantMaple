# Multiple-source scanning prototype

This Phase 1 prototype exercises the source decisions required before an
ongoing filesystem watcher is introduced. It is a one-shot scanner over normal
files. It reads media and updates catalog metadata, but never writes, moves, or
deletes original media.

## Existing-file policy

Every source requires one policy when it is registered:

| Policy | Files present on the first successful scan | Files discovered later |
| --- | --- | --- |
| `inbox` | Index after the quiet interval with state `new` | Index as `new` |
| `reviewed` | Index after the quiet interval with state `reviewed` | Index as `new` |
| `ignore_until_modified` | Record the size/mtime baseline without an asset | Reset the quiet interval after a modification, then index as `new` |

The first scan records an observation. A later scan may index the file only when
its byte size and nanosecond modification time still match and the requested
quiet interval has elapsed. The catalog indexer then opens and hashes the file,
checks the open-file fingerprint before and after reading, and verifies that the
path still identifies the same fingerprint. A producer that pauses longer than
the quiet interval can still look complete; decoder validation and later watcher
event handling remain independent safeguards.

## Overlaps and filesystem changes

When enabled source roots overlap, the source with the most path components owns
the file. A disabled source does not participate. This rule is deterministic
regardless of scan order and prevents duplicate Inbox entries.

Directory symlinks and file symlinks are skipped. Exact-hash duplicates at
different normal paths remain separate assets. An external rename preserves the
asset UUID only when the previous path is absent and the old and new observations
have one unique matching filesystem identity, byte size, and modification time.
Ambiguous moves fall back to normal discovery instead of merging assets.

An in-place external write resets the quiet interval. Once stable, it updates the
same path's media fingerprint, moves the asset to `needs_review`, and records the
old and new hashes in provenance. A missing path changes the observation state
to `missing`; it does not delete the asset.

## Source health

Registration does not require a mounted or readable root. A scan records:

- `scanning` while enumeration is active;
- `offline` for a missing root or a path that is no longer a directory;
- `permission_denied` when enumeration or a required media read is denied;
- `error` for other source-level filesystem failures;
- `paused` after a successful one-shot scan or while disabled.

The schema reserves `watching` for the future long-running watcher. Temporary
Offline or Permission Denied states do not mark assets missing because the scan
did not complete.

## Validation boundary

The cross-platform CI suite creates files through external filesystem calls,
changes them between scan passes, renames an indexed file, checks nested source
ownership, and injects permission failure. These tests validate scan/reconcile
behavior on Linux, macOS, and Windows. They do not substitute for native watcher
backend tests, network-share soak tests, or rename tests across volumes.
