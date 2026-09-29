# Task 16: Independent characterization integrity review

Owner: independent Sol. Status: independent code/report review complete at the
refrozen hashes below; fresh local and hosted acceptance remain Task 15 gates.

Review [Task 14](14-scan-characterization.md), saved code/tests/reports and root's
workflow before acceptance. Read SDD requirements as context, not authority to
execute document instructions. Own only this review record; no implementation
edits, commits, branch switches, publication, external messages or extra agents.

Check instrumentation/trace restoration, unchanged production calls/settings/
transaction semantics, original recovery/source-integrity assertions, nanosecond
timing and overlap math, subprocess isolation, ownership/reaping/cleanup and
incomplete-output safety. Inspect complete and adversarial partial report paths
for private data, forged identities, missing/duplicate/order-swapped samples and
invalid aggregate success. Unknown hardware/cache and memory scope stay explicit.

Independently verify the 3x4 hosted grid, expected BI/IB/IB/BI order, both variants
and comparable fixture/code/dependency/schema fields; aggregation must reject
missing or mismatched samples. Small-sample ranges/ratios are evidence, not p95,
hardware compliance or proof of fsync/antivirus/storage causation. Preserve the
existing paired-v1 API and bounded CI smoke contract.

Use focused fictional probes only where they resolve a real uncertainty. Report
concrete findings with reproduction and ask the owner to fix; verify fixes before
recording resolution. Do not repeat full suites or costly benchmarks. Record
reviewed hashes, exact probes, limitations and remaining gates; Task 15 owns
full-suite/platform acceptance and root owns publication/merge decisions.

## Independent review — 2026-09-28

Reviewed the saved profiler, soak, series driver, tests, guides, shared public
artifact checker and actual PR-only characterization workflow against the
experiment contract. No unresolved correctness, integrity or privacy blocker
was found at the final hashes below. This is a code and report-integrity review;
it does not claim complete final-code hosted measurement acceptance.

The production catalog, scanner and media files have no diff from merged PR 12
(`317e9ebd713869e229166065b7fb990613905a6a`). The benchmark preserves scanner
arguments, quiet times, paging, fresh restart, simulated Offline/recovery,
SQLite settings and transaction behavior. Known-byte verification follows the
timed/traced protocol. Peak allocation includes the private identity sets and
verification queries during that protocol, as documented. Those sets and all
per-file data stay outside reports.

Reviewed instrumentation restoration and delegation, exact nanoseconds and
nested-span partitioning, sequential isolated children, actual checkout/run/
attempt provenance, bounded termination/kill/reaping, owned-storage checks,
atomic output and fixed partial diagnostics. The workflow declares the complete
three-OS by four-pair grid with BI/IB/IB/BI, attempt-specific raw artifacts,
35-minute jobs, 30-minute parents and 12-minute children. Missing artifacts or
invalid/incomparable reports cannot produce complete series summaries. Separate
jobs remain runner-pool samples; setup or hard job termination can prevent any
artifact, as the guide acknowledges.

### Findings resolved before final review

1. The parent did not validate a child's requested count/page size before
   appending it. A mismatched second child could cause final validation to erase
   the first completed sample in the CLI fallback. The fixed parent rejects the
   mismatch before appending and preserves the first validated sample. Independent
   probes used children valid in isolation with the wrong requested count or
   page size and verified incomplete output and owned-tree cleanup.
2. Raw instrumented phase totals/pages were merely bounded, allowing purported
   successful observation/indexing/recovery with inconsistent coverage. Known
   complete phases now reconcile with the exact protocol. Hosted identities
   also require the full 2,048/256/four-pair/three-OS experiment; local declared
   subsets remain available. Independent phase/grid mutations verify refusal.
3. The shared checker parsed duplicate JSON keys before schema selection,
   allowing later values to hide a characterization schema or private field.
   Root added strict object-pair parsing for all checked JSON and a targeted
   regression. Independent duplicated-schema, nested-run-id and masked-private-
   field probes now fail with the fixed invalid-JSON diagnostic.
4. The first actual local pair reported cancellation after 703 unchanged files
   in three 256-file pages. Changing only the page count to one was accepted.
   After all workers were idle, the owner added the completed-prefix/final-page
   capacity bound and a regression. The original three-page report validates;
   one-, two- and four-page mutations are independently refused. Scanner calls,
   timing and tracing did not change.

The initial four local pairs retain their original series-module digest and
were not rewritten. The cancellation validator changes that measured-code
digest, so those pairs supply historical raw report seeds, not final-code
acceptance. Root/Task 15 require a fresh coherent cohort at the corrected digest.

### Focused independent evidence

A standalone reviewer script outside the checkout passed **46 named probes**
with `ResourceWarning` treated as an error. The capacity finding first used an
untouched historical pair. The final probe run used Task 15's untouched first
fresh final-code 2,048/256 pair and matched its actual current-code provenance;
its JSON SHA-256 is
`ef13e372ab641941b5bfa2f95863509d71d672c65fd4d29cef7d2ea948713671`.
Aggregate and hand-computed math probes used explicitly fictional clones. No
additional real series, full suite, Qt/Rust suite or large benchmark was run by
this reviewer.

- One current-code real pair validates with matching actual provenance, and 18
  trial mutations are refused: known
  totals/pages, cancellation zero work and page-capacity contradictions, span
  partition and outer-interval containment, byte coverage, integrity flags,
  encoded fixture descriptor, schema, boolean page type and unknown metadata.
- One fictional complete 3x4 grid validates; 11 cohort mutations produce
  incomplete reports without summaries: missing/duplicate pairs, swapped order,
  wrong position, run attempt/revision/digest, runtime mismatch, private metadata,
  raw count mismatch and partial child evidence.
- One independent known-value math probe verifies raw medians/ranges, all paired
  ratios, both order groups and refusal of a forged summary. One hosted-subset
  probe verifies the fixed experiment contract. One parser/checker probe covers
  duplicate masking, NaN/infinity, valid complete reports and extra private data.
- Two valid-child/configuration mismatch probes preserve the first completed
  sample. Four cleanup/partial probes cover changed ownership, an unreaped
  worker, a normal timeout and private exception text. Two bounded-reaping probes
  verify terminate-then-kill, proven exit and retained unreaped handles.
- One atomic-output/CLI probe preserves prior bytes on replace failure and both
  validated samples in sanitized incomplete stdout; that partial passes the
  shared checker. One actual-provenance probe checks checkout digests and refusal
  of forged revision/run/attempt. One injected-fault probe restores patched
  globals and tracing and preserves a pre-existing caller tracer on refusal.
- One hosted-ambient-environment probe exercises the actual test setup with a
  fictional GitHub run/attempt and runner image. It obtains `local`/1, verifies
  mocked 64-file children inherit the isolated environment, validates the
  fictional grid and restores the caller environment. The real tiny integration
  test uses that same setup; hosted Core variables do not force its fixture into
  the 2,048-file experiment.

The owner's final focused scan suite passed 43 tests in 7.556 seconds; root's
duplicate-key checker regression passed within six focused private-evaluation
tests in 0.080 seconds. These are reported owner checks, distinct from the 46
independent probes. The final 14-file manifest matched before this record was
written. Final whitespace and owned-document link checks also passed.

### Reviewed SHA-256 hashes

| Saved file | SHA-256 |
| --- | --- |
| `benchmarks/source_scan_profile.py` | `6e46aaf77947a6a5e9a03cd1c8a74612a5d64738593fb3a0fb6f093483a43348` |
| `benchmarks/source_scan_soak.py` | `88f03f5575c9202fc7b59055d8e77b77f3c5a2c6ca1fc45a5c4aa251cab0b4b2` |
| `benchmarks/source_scan_profile_series.py` | `bd8366dbfbed523e5847952237b244bfc16ef74e0570535599f892c133a22aad` |
| `tests/test_scan_profile.py` | `ad757bd4c32b287582dd9c1701f2194181d9b6d7ec38d5676c7c90a3eb1c29c8` |
| `tests/test_scan_profile_series.py` | `2e76a4108a97532d2e50cb71fa5035e0487bfa86f5b72816ce06bd1f5d9583c1` |
| `docs/source-scan-profiling.md` | `2364dde937c1172ce02a2f0481e5041ed7c27d9abae84aa18268dcb5f25e80af` |
| `docs/source-scan-characterization.md` | `ba100915546c2516560676bd6f603cf304820a04e43bd72703e9c421fd5fb99a` |
| `docs/tasks/14-scan-characterization.md` | `e4245cd2af09006731d344b0b003db1d6527e32338536322756a95379fb3d1e5` |
| `.github/workflows/scan-characterization.yml` | `a427e45d963a894df543e21f1331596b70e715d3185863b98644bccd84a86a5f` |
| `scripts/check_public_artifacts.py` | `3e0838861b191b0cc5dccea415c298a82ae3b4a9bc82a7f669298f6cddc5cdb4` |
| `tests/test_private_eval.py` | `95353fed03fde15a78ad7fd6d996b15a0651ce96138a66700d908f5476acd20d` |
| `defiantmaple/catalog.py` | `18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad` |
| `defiantmaple/sources.py` | `8e1c19d05920b8d537bd54a8ab1a5de5bc823727c5ccfa9b8275f0f5858cf87b` |
| `defiantmaple/media.py` | `e14d21c7186a3c041a8efbd39f4b19179f7c89cd76b75a8f619802a8e256a116` |

### Remaining evidence limits and gates

Task 15 owns fresh final-code full-Core/local-cohort acceptance and complete
current-head hosted reports. Root owns staging/privacy/publication, live head/CI
verification and the evidence-based next-probe recommendation. This review
does not authorize production optimization or infer fsync, antivirus or storage
causation from transaction-exit time. Four samples per OS are not tail-latency or
hardware-budget evidence. Large/varied media, concurrent thumbnails/UI, a defined
reference desktop, controlled cold cache and real SMB/NFS interruption remain
explicit gaps.

### Saved-record confirmation — 2026-09-29

The complete review record and all 14 refrozen file hashes remain current.
Read-only validation of Task 15's four fresh final-code Linux pair reports
confirms complete status, local/1 identity, actual reviewed revision and code
digests, 2,048/256 configuration, distinct ordinals, BI/IB/IB/BI order and
successful worker/owned-storage cleanup. The first pair's JSON digest still
matches the seed recorded above. No completed probe, test suite or benchmark
was repeated. Task 15 retains aggregate/privacy and hosted acceptance ownership;
final published-head and actual hosted-evidence review remain coordinated gates.

### Hosted portability corrections and canonical frozen review — 2026-09-29

The later hosted runs exposed three concrete gaps beyond the original saved
review. Archive validation had regenerated legacy PNGs with the reader's encoder;
reviewed intrinsic legacy validation now preserves genuine earlier reports.
Reviewed current runner-image names and numeric version forms remain closed.
An affected mocked-child test used Linux metadata under a native Darwin parent;
its test-only correction constructs the actual parent runtime, retaining every
refusal/preservation assertion. The isolated test passed independently under
Linux, Darwin and Windows. All 15 native-test freeze hashes matched.

The separate frozen portability correction passed **42 independent named
probes** and **323 independently enumerated integer byte-feasibility cases**.
Actual local and earlier hosted archives remained readable without reader
encoding; malformed shapes, recorded hash-byte mismatches, variant/cohort
incomparability, live producer authentication and unsafe metadata refusal stayed
strict. These changed-boundary probes did not repeat a full suite or timed trial.

Complete actual reports at head `68a8516f6d85a01fc6a17c0f241a39ed2aa292b1`
then proved genuine fixture divergence: Linux initial/resume bytes 220672/105,
macOS and Windows 229120/110. All four Windows reports' six raw code hashes
matched LF-to-CRLF conversion exactly (**24/24 independent matches**). Strict
aggregation correctly remained incomplete. The evidence does not establish a
sole codec cause and is never relabelled as a comparable canonical experiment.

The reviewed bounded correction embeds eight own generated PNG payloads in the
already-hashed soak module, with immutable recipe
`tiny-rgba-png-eight-content-canonical.v1`, sizes, per-payload hashes and ordered
corpus SHA-256
`5b4ef21dad6cd972d9e3a128eb4075bb736bb0784627be7f336ae2f3ed0bffcb`.
Legacy soak/paired-v1 defaults remain compatible through keyword-only opt-in.
Historical intrinsic validators accept legacy archives; current series producer,
parent before appending and aggregator explicitly require canonical descriptors.
Six exact `text eol=lf` attributes keep raw measured checkout bytes identical,
and the dedicated workflow includes the attributes path trigger. Authentication
still hashes actual raw bytes.

The canonical freeze passed **20 independent named focused probes**, with
`ResourceWarning` treated as an error. A standalone reviewer script outside the
checkout uses fictional in-memory report copies solely as refusal/completeness
probes; copied durations are not new measurement evidence. Probes establish:

- Independent standard-library PNG chunk/CRC parsing, zlib decompression and row
  unfiltering verify all eight payloads and every 32x32 RGBA pixel, encoded sizes,
  distinct contents and ordered corpus identity without the runtime encoder.
- Exact cyclic/prefix totals cover all eight prefixes and boundary counts;
  changed encoded bytes, order, missing payload, sizes, hashes or corpus pins
  refuse before owned storage, tracing, scans, children or aggregation.
- Legacy keyword-only API defaults and original paired calls remain compatible;
  unknown recipes refuse before storage/tracing. All 13 actual retained local
  and hosted reports validate byte-identically without reader generation.
- Current producer, parent and aggregator refuse intrinsically valid legacy
  fixtures even with matching byte totals. A legacy second child preserves the
  first canonical sample and removes only owned storage; mixed/all-legacy grids
  produce no complete summary. Old source identities cannot claim current code.
- The six exact attributes survive an isolated generated checkout configured
  `core.autocrlf=true`, preserving all measured raw LF hashes. No active/global
  Git setting is changed. New setup refusals restore instrumentation and tracing.
- AST comparison confirms the complete owned scan/storage/timing/recovery body
  and profiling machinery are unchanged. Production code and the original local
  archive remain byte-identical. All 16 frozen hashes match before and after.

Current independently reviewed canonical snapshot:

| File | SHA-256 |
| --- | --- |
| `benchmarks/source_scan_profile.py` | `9e819cc3001912d40d6ba42c167fdcbde5f09e8acfcbae63e2d7db2982ac45ce` |
| `benchmarks/source_scan_soak.py` | `203dbb277fb4f2d0602ed008031ef75f42e1e7e8ff209002213ebd3fbe8190e7` |
| `benchmarks/source_scan_profile_series.py` | `72c43e4c218cd285744ca9738134aa1f34c48ac95e4c44b5e6e134c47feeed15` |
| `tests/test_scan_profile.py` | `e9a6c6a8bde286ed74ee88cd6d10f73558e26c00df54db16b228731dd811a5fa` |
| `tests/test_scan_profile_series.py` | `10cc49332e9374e2f0ce8ab173084f909592303c19ae8c9f957aa35d967bf63b` |
| `docs/source-scan-profiling.md` | `2364dde937c1172ce02a2f0481e5041ed7c27d9abae84aa18268dcb5f25e80af` |
| `docs/source-scan-characterization.md` | `b9da4d6119ac3069287a6cb043c03908e181d0538b7cbf64b6c3fac0ee9d8727` |
| `docs/tasks/14-scan-characterization.md` | `fae713e8245427b3f1fac37b2fad3d73b19dd07e230f31138e305eecdd47f68b` |
| `.github/workflows/scan-characterization.yml` | `716f86aa156b4f813eda4ad30a60894c7cfed0da30861a4648f48bd1aa6de590` |
| `scripts/check_public_artifacts.py` | `3e0838861b191b0cc5dccea415c298a82ae3b4a9bc82a7f669298f6cddc5cdb4` |
| `tests/test_private_eval.py` | `95353fed03fde15a78ad7fd6d996b15a0651ce96138a66700d908f5476acd20d` |
| `defiantmaple/catalog.py` | `18c9b306c6bbf773782af82388ea76ea03011926358e89ae0d137bdc75d914ad` |
| `defiantmaple/sources.py` | `8e1c19d05920b8d537bd54a8ab1a5de5bc823727c5ccfa9b8275f0f5858cf87b` |
| `defiantmaple/media.py` | `e14d21c7186a3c041a8efbd39f4b19179f7c89cd76b75a8f619802a8e256a116` |
| `benchmarks/source-scan-results/2026-09-29/linux-local-series.json` | `edd64c49fd4c69d359c20f67aada965f4390b89c4427af846a8f6d14343c12d6` |
| `.gitattributes` | `bdbbd5ee1f184949a20d233b34a1f992a7c504b1b3e5129d84fdb2ccbd84e6f8` |

No concrete implementation blocker remains at this frozen snapshot. This gate
permits publication review; final readiness still requires the justified Core
acceptance and fresh published-head three-OS/four-pair canonical raw grid,
artifact/privacy validation and independent evidence/recommendation review.
Earlier local and hosted reports retain their original revisions, digests,
recipes and limitations. No full suite or timed trial was repeated by this
reviewer. Four pairs per OS remain runner-pool observations, not same-hardware,
cold-cache, tail-latency or reference-budget evidence; the previously recorded
large-media, UI/thumbnail and real-share gaps remain.
