# Task 03: Make real mounted-share validation reproducible

Owner: Sol. Status: implementation complete; real mounted-share evidence pending.

Read docs/source-scan-resilience.md and scanner tests. Build a reproducible manual
integration harness/protocol using ONLY a unique generated fictional fixture on
an explicitly supplied writable scratch share and a local temporary catalog.
A supplied existing directory must not be treated as permission to scan its
contents or delete it. Create an owned child fixture with a marker, refuse unsafe
reuse, and limit cleanup strictly to that owned fixture. Avoid generic shell hooks.

Support observation/indexing interruption and reconnect validation with stable
asset UUIDs, retained catalog records, no false missing reconciliation, and source
file integrity checks. Bound waits/timeouts and explain how a blocking filesystem
call affects cancellation. Distinguish fixture creation writes from scanner reads.
An honest manual runbook plus harness is preferable to fabricated automation.
Document Linux/macOS/Windows commands and evidence fields; report mounted protocol
only when verified and leave untested environments explicit. Add local generated-
fixture tests for guards and state/protocol validation. Do not disconnect actual
mounts, start network services, use private media, or change machine configuration.

Own `benchmarks/mounted_share_probe.py`, `tests/test_mounted_share_probe.py`,
`docs/mounted-share-validation.md`, and this task file's status/results. Request
shared changes through the orchestrator. No commits/pushes/branch switches, PRs,
external messages, or extra agents.

## Results (2026-09-27)

- Added `benchmarks/mounted_share_probe.py` with explicit prepare/interruption/
  Offline/recovery/report/cleanup stages. Every source operation runs in a fixed
  subprocess with a deadline, bounded terminate/kill waits, and an exclusive
  local worker lock retained if the OS cannot reap it. No mount/service control
  or configurable shell hooks exist.
- The fixture is a unique marked child; parent contents are never scanned.
  Cleanup validates marker, exact inventory, symlinks, SHA-256, size, and mtime,
  then removes only owned members and empty generated directories. Local private
  state/catalog stay outside source storage and the repository. Public event and
  nested scan fields are allowlisted aggregates.
- UUID sets and existing UUID/path associations are checked through interrupted,
  Offline, and healthy fresh scans; pending observations can become indexed.
  Source integrity is rechecked, and the unsupported marker entry is explicitly
  accounted for. Cached success, timeout, failed worker exit, and unreaped
  workers never qualify as completed validation.
- Added `docs/mounted-share-validation.md` with Linux/macOS and Windows commands,
  manual between-operation interruption gates, evidence fields, private/public
  handling, and cancellation/kernel-I/O limits.
- Validation: `python -m unittest discover -s tests -p
  test_mounted_share_probe.py -v` (16 tests, passing on local Linux); `python -m
  py_compile benchmarks/mounted_share_probe.py tests/test_mounted_share_probe.py`
  passed. The generated local subprocess test exercises both interruption and
  reconnect phases using only an owned child rename; it verifies 128 original
  UUIDs retained and 256 final indexed images, plus one unsupported marker.

Remaining external dependencies: dedicated disposable SMB/NFS mounts and
operator-recorded protocol/interruption/reconnect evidence on Linux, macOS, and
Windows; local tests/timeout behavior on macOS and Windows. No actual mount was
interrupted, no private artwork was used, and no machine configuration changed.
Protocol labels are operator attestation associated with a local evidence digest,
never protocol verification performed by this harness.
