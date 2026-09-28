# Scratch mounted-share validation

`benchmarks.mounted_share_probe` makes a manual interruption experiment repeatable.
It creates a uniquely named, marked child under an explicitly supplied writable
scratch parent. It never scans the parent's existing contents. The catalog,
file fingerprints, asset UUIDs, paths, and operator evidence references stay in a
new local session directory outside the repository and scratch parent. Public
JSON contains only aggregate results, platform/version, timestamps, and an
optional evidence-file SHA-256. Do not publish `session.private.json`,
`manifest.private.jsonl`, the catalog, a worker lock, or the operator evidence
file.

This harness has been tested with generated **local synthetic loss**. No actual
SMB/NFS mount has been disconnected for this implementation. Linux, macOS, and
Windows mounted-share experiments remain external validation gates. A supplied
path or a successful local test never establishes a network protocol.

## Preconditions and operator evidence

Use a dedicated disposable mount whose interruption will affect only this
experiment, with permission to create generated fictional files. No private
artwork or production catalog belongs in this run. The scratch parent must
already exist, be writable, and use its canonical absolute path. The local
session parent must already exist on local storage; the session directory itself
must be new. The tool relies on the operator to choose local storage, and refuses
state under the scratch parent or repository. Do not use a share with concurrent
writers changing this owned child.

Before a real run, verify the actual mount/protocol using the operating system's
read-only mount inventory. Record the matching mount entry, verification command,
OS/Python and client/server versions, verification time, chosen interruption
method, and reconnect times in a **local private evidence file**. On Linux,
[`findmnt --target`](https://man7.org/linux/man-pages/man8/findmnt.8.html)
identifies the filesystem serving the supplied absolute scratch-parent path; check its filesystem type rather than infer from a directory name. On
macOS, inspect the matching entry in `mount`. On Windows SMB clients, inspect
[`Get-SmbMapping`](https://learn.microsoft.com/en-us/powershell/module/smbshare/get-smbmapping)
for mappings and
[`Get-SmbConnection`](https://learn.microsoft.com/en-us/powershell/module/smbshare/get-smbconnection)
for server/share connections; a directory or mapped drive name alone proves nothing. NFS or
other Windows clients require their own verified mount/client evidence.

`--environment-kind mounted_scratch --protocol smb|nfs|other` requires a local
`--mount-evidence` file. Its digest associates the public report with the private
record; it does **not** authenticate the record or prove the protocol. Every
named protocol is reported as `operator_attested`, and
`protocol_independently_verified_by_harness` is always false. Use `unknown` if
verification is unavailable. Protocol `unknown` reports evidence as `not_tested`
for both environment kinds, even when an optional evidence file was supplied;
the digest alone does not establish a protocol. `local_fixture` requires protocol
`unknown` and reports protocol evidence as `not_tested`.

## Linux and macOS commands

Run from the repository root with `requirements.txt` installed. Replace these
example paths with your dedicated scratch parent and a new local session. The
same Python commands work on Linux and macOS; use `python3` if that is the
interpreter containing the dependencies. This example assumes the operator has
verified SMB and saved a local evidence record.

```sh
python -m benchmarks.mounted_share_probe prepare \
  --scratch-share /absolute/dedicated-scratch-parent \
  --local-state /absolute/local-probe-records/session-01 \
  --environment-kind mounted_scratch --protocol smb \
  --mount-evidence /absolute/local-probe-records/mount.private.txt \
  --count 256 --timeout 120

python -m benchmarks.mounted_share_probe interrupt \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
```

The first `interrupt` stops at the 64th enumeration candidate, before enumeration
finishes. When it prints the observation gate, manually interrupt **only your
dedicated disposable mount**, using the method recorded in private evidence.
Press Enter once unavailable. The tool supplies no mount or shell hooks.
Leave the mount unavailable while running the Offline probe:

```sh
python -m benchmarks.mounted_share_probe offline \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
```

Reconnect that mount manually to the same source path. Confirm it is serving the
original generated child, then run recovery and the second interruption:

```sh
python -m benchmarks.mounted_share_probe recover \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
python -m benchmarks.mounted_share_probe interrupt \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
```

Before the second gate, the harness writes a separate generated indexing batch
and records its first observations. The gate occurs immediately before a second
`index_file` call, after one new file was successfully indexed. Disconnect only
the dedicated mount again, press Enter, and leave it unavailable for `offline`.
Reconnect before `recover`:

```sh
python -m benchmarks.mounted_share_probe offline \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
python -m benchmarks.mounted_share_probe recover \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
python -m benchmarks.mounted_share_probe report \
  --local-state /absolute/local-probe-records/session-01 \
  --metrics /absolute/local-probe-records/public-report.json
python -m benchmarks.mounted_share_probe cleanup \
  --local-state /absolute/local-probe-records/session-01 --timeout 120
```

The report file must be new and outside scratch storage. Cleanup needs the mount
online. It verifies the exact marker, member inventory, regular-file types,
SHA-256, sizes, and nanosecond modification times before unlinking only manifest
members and removing empty generated directories. Unexpected files, changes,
symlinks, missing markers, and substituted paths cause refusal. Cleanup retains
the local catalog/evidence directory and never recursively deletes the supplied
scratch parent. It rechecks canonical root/marker and directory redirects at
each destructive member operation. These checks do not provide an atomic
cross-platform defense against a concurrent actor swapping filesystem entries
between check and unlink; exclusive use of the generated child is required.

Generation appends each completed file's ownership fingerprint to the local
`manifest.private.jsonl`, flushes and syncs that record before the next share
write, and saves the full manifest once per batch. Total checkpoint data grows
linearly with the generated count, including the accepted 100,000-file limit.
Loading private state replays completed journal records, so interruption before
the next full snapshot retains the recorded fingerprints. An incomplete final
journal record establishes no ownership. If a write stopped before its complete
fingerprint was checkpointed, exact inventory refuses cleanup of that member;
manual review is required. Conflicting, foreign-session, or redirected journal
files are refused. A partial failed preparation is never reused automatically.
These checkpoints support process-interruption recovery; they do not establish
network-server or power-loss durability.

## Windows PowerShell commands

Use an installed Python with the repository requirements. A mapped drive or UNC
scratch parent must be dedicated to this experiment, and the local session must
be on a local disk. Verify its protocol separately before using this SMB example.
Paths with spaces remain quoted. Subsequent stages use the same commands and
operator disconnect/reconnect sequence described above.

```powershell
python -m benchmarks.mounted_share_probe prepare `
  --scratch-share 'Z:\DisposableScratch' `
  --local-state 'C:\ProbeRecords\session-01' `
  --environment-kind mounted_scratch --protocol smb `
  --mount-evidence 'C:\ProbeRecords\mount.private.txt' `
  --count 256 --timeout 120
python -m benchmarks.mounted_share_probe interrupt --local-state 'C:\ProbeRecords\session-01' --timeout 120
python -m benchmarks.mounted_share_probe offline --local-state 'C:\ProbeRecords\session-01' --timeout 120
# Reconnect the dedicated mount manually before recovery.
python -m benchmarks.mounted_share_probe recover --local-state 'C:\ProbeRecords\session-01' --timeout 120
python -m benchmarks.mounted_share_probe interrupt --local-state 'C:\ProbeRecords\session-01' --timeout 120
python -m benchmarks.mounted_share_probe offline --local-state 'C:\ProbeRecords\session-01' --timeout 120
# Reconnect the dedicated mount manually before recovery.
python -m benchmarks.mounted_share_probe recover --local-state 'C:\ProbeRecords\session-01' --timeout 120
python -m benchmarks.mounted_share_probe report --local-state 'C:\ProbeRecords\session-01' --metrics 'C:\ProbeRecords\public-report.json'
python -m benchmarks.mounted_share_probe cleanup --local-state 'C:\ProbeRecords\session-01' --timeout 120
```

## What the stages establish

The permitted order is `prepare → interrupt → offline → recover → interrupt →
offline → recover`. Recovery always begins fresh enumeration; the canceled or
interrupted inventory/cursor is not reused. `report` can inspect any session.

- The baseline has one UUID per generated image. The ownership marker is a
  deliberately unsupported catalog entry, accounted for separately.
- Interrupted and Offline scans must report incomplete and `offline`, retain
  existing asset UUID membership and the asset IDs attached to earlier paths,
  preserve observed paths, and report zero false missing reconciliations.
- Pending observations may become indexed assets. This allowed progression
  cannot change an already assigned UUID. Offline/recovery checks include UUIDs
  created before the interruption, not merely the baseline count.
- A healthy recovery performs two fresh passes, indexes every generated image,
  retains previous UUIDs/records, and verifies source hashes/sizes/mtimes.
- Fixture creation and the second batch are explicit writes by the harness.
  Scanner calls read source files and write only the local catalog. The scanner
  may update filesystem access times through ordinary reads; those are not part
  of the source-integrity assertion.

Both gates pause **between filesystem operations**. They do not prove cancellation
of an in-flight kernel read. Client caching can let a disconnected scan complete;
that trial becomes `inconclusive`, with no recovery-success claim. Empty local
mount directories or replacement roots can expose different behavior. Record
exact mount behavior and scanner health; do not treat a timeout, cached successful
pass, or synthetic directory rename as an observed SMB/NFS Offline result.

## Deadlines and blocked workers

`--timeout` is a finite per-action budget of up to 3,600 seconds, covering child
startup, source work, and operator confirmation. Confirmation must arrive within
that same budget. The controller asks the worker to terminate, then kill, using
bounded waits of two seconds each. A scanner cancellation flag cannot interrupt
a kernel filesystem call already blocked on network I/O.

The subprocess design avoids Python multiprocessing's implicit shutdown join.
If the OS cannot finish killing the worker, the controller returns an incomplete
report and retains `worker.private.lock`; further work and cleanup refuse that
lock. `report` also marks any locked session `worker_active_or_unreaped` and
`complete=false`, even if older private state says complete. No CLI can guarantee
that a kernel operation has stopped by its deadline. Reconnect the dedicated
mount as needed and verify the recorded worker process has exited before any
manual review or removal of this **local** lock. A timed-out/failed session stays
inconclusive; use a new session for a new trial. Never start another stage against
a still-running worker or use broad process-killing/mount commands.

## Evidence and remaining environments

The public report includes schema, platform/Python versions, configured count,
actual generated fixture count, measured baseline assets (null before a completed
baseline),
environment kind, protocol/evidence classification and optional digest, UTC timestamps,
per-phase aggregate scan health/totals, gate reach, UUID retention, record
retention, recovery completion, integrity checks, timeout actions, worker-lock
presence, and cleanup state. Private paths, UUID sets, per-file fingerprints,
and exception details remain local. Preserve both records privately for audit,
but upload only reviewed aggregate JSON.

Portable semantic verification uses real generated files/catalogs and test-only
I/O errors at observation, indexing, and unavailable-root boundaries. A separate
subprocess test attempts a local child-directory rename during each gate. Hosts
that deny rename while an enumeration handle is open explicitly skip that
physical-rename capability test after checking inconclusive status, retained
records, and source integrity; they still run the portable injected-loss test.
An operator-confirmation I/O error also cannot establish an Offline or recovery
result. This suite covers safe parent isolation,
marker/symlink/member guards, linear checkpoint data, replay after interrupted
baseline/indexing generation, cleanup refusal for uncheckpointed members,
unknown-protocol evidence labels, pending-to-indexed state progression, precise UUID
retention, Offline/recovery protocol order, public-report privacy, normal timeout
reaping, and a mocked worker that cannot be reaped. These are harness tests, not
real-share, latency, durability, native watcher, or network-server tests.

| Environment | Implementation evidence | Remaining validation |
| --- | --- | --- |
| Linux local filesystem | Focused unittest suite, subprocess rename protocol and portable injected loss/recovery | Actual dedicated SMB and NFS interruption/reconnect experiments |
| macOS | Portable command/runbook and Python implementation | Local suite and dedicated SMB/NFS experiment on macOS |
| Windows | Portable command/runbook and Python implementation | Local suite, timeout behavior, mapped-drive/UNC SMB and applicable NFS experiment |

Run the focused suite from the repository root:

```sh
python -m unittest discover -s tests -p test_mounted_share_probe.py -v
```
