# Task 02: Attribute scan costs before optimizing Windows

Owner: Sol. Status: profiling implementation, local validation and
cross-platform profile CI evidence complete. A Windows/Python 3.11 mounted-share
probe portability follow-up is tracked separately in Task 03.

Baseline evidence: docs/source-scan-resilience.md. Review sources.py, catalog.py,
and benchmarks/source_scan_soak.py. Build an opt-in profiling benchmark on the
same generated fixture that helps separate enumeration, SQLite connection and
transaction work, and indexing/hashing costs without changing production scanner
semantics. Explain inclusive/exclusive timings and instrumentation overhead;
never sum overlapping measurements or label unmeasured components as proven.
Capture only aggregate counts/timings/runtime metadata, no paths or SQL values.
Keep the original soak's recovery/source-integrity assertions.

Prefer benchmark-only wrappers/instrumentation. Do not change durability,
transaction boundaries, database pragmas, or scanner behavior in this task.
Create tests for meaningful profiler invariants/restoration/error handling.
Run a local sample and document exact invocation and limitations. Prepare a
Windows CI invocation for orchestrator integration; no unmeasured Windows claims.

Own `benchmarks/source_scan_profile.py`, `tests/test_scan_profile.py`,
`docs/source-scan-profiling.md`, and this task file's status/results. If a shared
file change is necessary, request it from the orchestrator before editing.
No git commits/pushes/branch changes, PRs, external messages, or extra agents.

## Results

- Added benchmark-only `source_scan_profile.py`, reusing the unchanged original
  soak twice with fresh fictional fixtures/catalogs. Reports contain aggregates
  only, fixed phase/operation names, inclusive/exclusive timings, runtime versions,
  and paired baseline/instrumented elapsed comparisons. SQLite context exits are
  distinguished from proof of fsync cost; overlapping inclusive spans are never
  summed. No production scanner/catalog or durability changes were made.
- Added eight profiler tests for timing partition, rollback/settings/results,
  error handling and restoration, privacy, generated recovery/source integrity,
  tracing cleanup, parameter validation, and sanitized CLI failure output.
  `python -m unittest discover -s tests -p 'test_scan*.py' -v` passed 21 tests
  in 1.216 s. `python -m scripts.check_public_artifacts` and `git diff --check`
  passed; the generated-report test also invokes the JSON privacy validator
  directly because local profiling outputs are outside tracked repository files.
- Local invocation: `python -m benchmarks.source_scan_profile --count 2048
  --page-size 256 --metrics /tmp/defiantmaple-source-scan-profile-2048.json`.
  Linux x86_64 / CPython 3.14.7 / SQLite 3.51.2 / installed Pillow 12.2.0.
  Baseline observation/index/fresh-restart-plus-follow-up: 2.247/4.381/5.809 s;
  instrumented: 2.709/5.030/6.334 s. Both retained 2,049 final assets and passed
  all original soak assertions. Baseline always ran first; paired differences
  include uncontrolled cache/storage/order variation as well as instrumentation.
- Documented exact component counts/timings, methodology, and limitations in
  [source-scan-profiling.md](../source-scan-profiling.md). Prepared the CI command
  `python -m benchmarks.source_scan_profile --count 256 --page-size 64 --metrics
  source-scan-profile.json` for orchestrator integration on all three OSes.
  The bounded CI sample does not replace the comparable 2,048-file Windows run.
- Core workflow run 36378460690 passed all three `scan-cost-profile` jobs. The
  256-file paired baseline/instrumented observation, indexing and fresh-resume
  figures plus instrumented phase components are recorded in the profiling
  report. Each OS had one pair; inclusive spans overlap, paired ratios include
  tracer/wrapper and run-order/cache variation, and Windows transaction-exit
  timing does not identify an fsync or other cause.
- At PR head `5859c7c65fa44896ae61b463177f4f0441320124`, Core run 36378460690
  had all three profile jobs and all three source-scan-soak jobs pass. Its
  Windows/Python 3.11 core suite failed
  `test_local_loss_recovery_checks_both_phases_and_stable_uuids` in the mounted
  share probe; Windows/Python 3.13 was cancelled after that failure. Other
  completed OS/Python core suites passed. This is historical evidence for that
  head; the mounted-share-probe portability follow-up is tracked in Task 03 and
  should be rechecked at its follow-up head.
- A comparable 2,048-file Windows profile run, repeated/cold-cache measurements,
  real mounted-share interruption behavior, large-media hashing, and
  disk-sync/antivirus attribution remain open. No Windows bottleneck or
  throughput claim is made.
