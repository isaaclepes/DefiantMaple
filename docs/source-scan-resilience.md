# Phase 1 source-scan resilience evidence

The scanner is still an explicit one-shot reader. This gate tests how it behaves
under a sustained generated workload and when a source becomes unavailable. It
does not introduce a filesystem watcher or any source-media mutation.

## Reproducible run

From the repository root, with `requirements.txt` installed:

```sh
python -m benchmarks.source_scan_soak --count 2048 --page-size 256 \
  --metrics /tmp/defiantmaple-source-scan-metrics.json
```

The script creates fictional PNGs and a separate catalog in a temporary local
directory. It performs a paged first observation, a stable second pass, a
cancellation partway through a later pass, and a fresh restart. The restart must
index an image whose name sorts before the canceled cursor. It then makes the
generated source path temporarily unavailable, verifies that catalog assets
and observations survive, restores the path, and verifies recovery. It checks
that source file sizes and modification times were unchanged. The JSON report
contains only aggregate counts, durations, platform, Python version, and peak
Python allocation; it contains no paths or per-image records.

Core CI runs this on current GitHub-hosted Linux, macOS, and Windows using
Python 3.13 and uploads each aggregate report. Fault-injection tests on the same
OS matrix cover a disappearing child directory, a network-style read error,
and a source-root replacement immediately before missing-file reconciliation.

## Local evidence

One Linux run on Python 3.14.7 completed with 2,048 generated files in eight
pages per pass. Observation took 2.307 seconds, stable indexing 4.563 seconds,
and the fresh restart plus stable follow-up 6.198 seconds. Peak traced Python
allocation was 7,173,697 bytes. All 2,049 final assets were retained through
the simulated Offline interval, and generated source files were unchanged.
An additional 8,192-file run in 32 pages per pass took 23.862 seconds for
observation, 37.331 seconds for stable indexing, and 62.191 seconds for fresh
resume plus its stable follow-up. Peak traced Python allocation was 26,429,307
bytes; all 8,193 final assets were retained. The larger run is local Linux
evidence, not part of the cross-platform CI gate.
These times include local filesystem, SQLite, and Python work; OS caches and
disk state were not controlled. They are diagnostic measurements, not latency
guarantees for a network share.

## Safety rule and remaining gate

A missing root or child directory, changed root identity, or network-style
timeout/disconnect/I/O error makes the pass incomplete. Incomplete passes never
reconcile absent paths as missing. A later healthy full enumeration can do so.
Automatic rename reconciliation stays within one source. An asset belonging
to an Offline or inaccessible source is not moved to another source merely
because an identical file appears there.
Within a pass, pagination uses one in-memory inventory. A cursor from a canceled
pass is not reused with a new inventory, because files added before that cursor
could otherwise be skipped; the next Scan source action repeats enumeration but
retains completed observations and asset UUIDs.

This is **simulated source loss**, not proof of SMB/NFS behavior. The next
experiment requires a dedicated writable scratch share containing only generated
fictional files on each target OS. Start a scan, disconnect the mount during
enumeration and again during indexing, reconnect it, and verify source health,
catalog asset UUIDs, and a subsequent complete scan. Keep the library and cache
on local storage. Do not use the private artwork tree for this experiment. Native
watcher design remains gated on that real-mounted-share evidence. The current
inventory is held in memory, and no durable page cursor or crash-resume journal
exists; large trees need further performance and memory characterization.
