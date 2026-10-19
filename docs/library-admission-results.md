# Library admission results

**Status: bounded local acceptance is qualified; exact publication-head CI is required and recorded in PR #24.**
This is a sanitized evidence ledger, not release or full SDD acceptance. The
reviewed design is the exact SHA-256
`53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`.
Implementation scope remains cooperative admission for current participating
Qt, CLI, and Rust/Tauri entry points plus explicit Core admitted sessions.
Unwrapped Core calls, old clients, arbitrary SQLite writers, and unsupported
storage are outside that guarantee.

## Current exact source candidate

PR #24 source head `806a42f65d8cab29311ff63e5801f8e063cf2046`, tree
`2bdbd9d462596c6e56975f4785bc2b2243c1b47b`, was verified against the reviewed
freeze-5 manifest. The frozen runtime candidate is
`3dbfd3456eda0983a584ac491c4a7cd447698bd18f0068cd3b32b104107a9c59`; manifest
SHA-256 `6ca943e2d973bf83e2b48672d110569f85f6643eda17fcebc559d7fd52d841ae`.
All 165 runtime/test/build input hashes match this source head. The only
freeze-5 delta from its predecessor is the reviewed alias-oracle correction in
`tests/test_admission_adversarial.py`; executable runtime and build inputs are
unchanged. The exact source is draft PR content, not a merged or deployed
release.

The focused Linux adversarial suite for the alias correction ran 12 tests:
10 passed and 2 were skipped, with direct exit 0. The unittest time was
5.579 s and wrapper wall time was 5.694 s. This host does not support the case- and
Unicode-equivalent filesystem cases, so those cases were skipped locally and
were run on macOS hosted CI. The earlier macOS failures on the preceding test
head remain recorded below; they are not overwritten by the correction.

Active-writer cancel/restart attempt 2 passed on the frozen candidate as
bounded offscreen Qt evidence. It preserved one fully committed asset and its
provenance through cancellation, kept the same worker active after an
immediate restart attempt, then completed three assets with three provenance
rows. Five CLI contenders were refused during protected periods and a CLI
acquired after cleanup. Both workers finished, the owner closed, the gateway
stopped, and all 165 inputs and 15 deployed outputs remained unchanged. The
private receipt is referenced by SHA-256
`ec788687d187fddf596bd0bca255d1ce57a298299b20e77876567d7959485aaa`. This is
offscreen worker evidence, not another native desktop run.

Compatibility/bridge attempt 3 passed on generated Linux fixtures after the
exact helper was independently reviewed and its real-registry execution
explicitly approved. It verified prior-version producer compatibility and
restore holds, refusals while actual inspect/backup children were verifying,
real existing-open and restore directory-gate routes, three admitted
migration-fault bridge tests, and the distinction between a nonparticipating
raw SQLite writer and SQLite's own `SQLITE_BUSY` result. The helper and receipt
SHA-256 values are
`f08920fff3d7e35912d7b4abd87c7469fa185edd3b173feca251883fe3307d93` and
`846f6d587c5d20a67ec5ae867337de941660a576b8f542439f96b16c70366f08`.
All 165 frozen inputs and 15 outputs matched before and after, both owned
children exited successfully, and final worker cleanup was clean. This is
bounded generated-fixture evidence; it does not cover every migration
statement or establish full FR-LIB-003 acceptance.

## Historical full local suite and frozen package

This earlier full local suite used a reviewed, uncommitted runtime overlay on base commit
`99d4e471d2dd207a3f44b1408eb6eb3197bca55d`. This identifies the tested inputs;
it does not claim equivalence to Git HEAD or a committed tree. The runtime
candidate ID is
`597b1fbac1186a70af0e86370413b9c1d6bb82c2544f423fb3f4dee218fc913e`; the
freeze-manifest file SHA-256 is
`23241cc013755bec0d8eef65120c38e623671c9c2b50bdd1ca0d1750d7cdaf9d`.

The frozen manifest contains 164 runtime/test/build inputs. Compared with the
first failed admission runtime candidate
`fdbeb370a94fa42632ad8d92a0a82e290dd44d2f629be294168c92278928638f`, 161
inputs were retained and three changed: `defiantmaple/recovery.py`,
`defiantmaple/thumbnail.py`, and `tests/test_admission_recovery.py`. This is a
comparison to that failed runtime candidate, not to base commit `99d4e47`. The
pre/post comparison found no hash delta across the current 164 frozen inputs. All 15 deployed output files matched their
baseline hashes before and after the run. The commands used generated test
fixtures. The local runtime was Python 3.14.7, PySide 6.11.2, SQLite 3.51.2 on
Linux; Qt tests used the offscreen platform.

## Historical local run record

The sequence stopped on any nonzero command. Core, the public-artifact privacy
check, and Qt each exited directly with status 0. The privacy check ran before
these two review-draft files were created, so it does not certify their contents:

| Scope | Result and test-runner time | Wrapper wall time | Raw stderr SHA-256 |
| --- | --- | ---: | --- |
| Full Core: `python -m unittest discover -s tests -v` | 336 tests passed; 117.865 s reported by unittest | 118.287 s | `c6d5f2dbaa862781fbeaddffe41ae1556a76b0c300533469288e28d4c34fa7bb` |
| Public-artifact privacy check | Passed | 1.193 s | Empty stderr (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`); stdout SHA-256 `5bb4495d293c8ea075c051bbb45b1ac0dc37e9c019f8e9055f130f042d01f207` |
| Full offscreen Qt: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s prototypes/qt/tests -v` | 192 tests passed; 97.339 s reported by unittest | 99.005 s | `7a0e1c5984367d6f9cb5ea4d053c568839329dbbf6d0843793e95195767b09d9` |

The private full-run receipt SHA-256 is
`5d6ad6d180e238dcca0cfc1b82c010bd5aaad6b8320ca4020334484926431172`.
The full-run receipt preserves direct exits, elapsed times, child-process CPU
measurements, command log hashes, and pre/post input/output inventories. The
source and output comparisons were clean. Those full suites belong to the
historical 164-input local candidate above; the freeze-5 source adds a test-only
alias-oracle correction, so these totals are not presented as a fresh full
suite on the 165-input head.

## Hosted CI by exact head

The preparation snapshot for exact head
`806a42f65d8cab29311ff63e5801f8e063cf2046` returned all 30 expected checks:
27 success, 3 in progress, and no failures or cancellations. A completed
Windows Python 3.13 Core job (check 117913015952) passed 348 tests with 28
platform/capability skips, including POSIX-only cases, unsupported Windows
Unicode normalization aliasing, and recovery-publication cases requiring the
reviewed Linux native adapter. The two remaining Windows Core jobs and the
Windows benchmark/package job were still in progress at that snapshot. This is
a timestamped preparation snapshot, not a final census; the terminal exact-head
results and remaining Windows summaries belong in the PR acceptance record.
No check was manually rerun or cancelled.

The preceding reviewed test-only head `b5fd949642ce2654159b54c6e092080cf818f792`
had 19 success, 3 failure, 6 cancelled and 2 in-progress checks at its latest
snapshot. The two macOS Core matrix runs and Qt macOS benchmark/package job each
ran 348 tests with 2 failures and 17 skips. The same two failures repeated:
`test_case_equivalent_alias_on_host_filesystem` and
`test_unicode_equivalent_alias_on_host_filesystem`, both failing the
registry-identity baseline assertion after the alias-refusal helper. The
cancelled Windows Core jobs ended in `KeyboardInterrupt` during the
mounted-share/source-scan probe and did not produce final unittest totals.
The 806a head contains the reviewed test-only alias-oracle correction; b5
failures remain historical outcomes for b5 and are not overwritten by that
change.

For earlier exact head `8eb869636ef196f6b177a4beca1310923d4ad013`, 25 checks
succeeded, 3 failed and 2 were cancelled. Each of the four Windows Core
push/PR Python 3.11/3.13 runs logged 336 tests, 2 errors and 26 skips. The
errors were `test_cleanup_reference_survives_invalidated_catalog` and
`test_replacement_is_observable_and_never_adopted`, both `PermissionError
[WinError 5]` at `replacement.replace(catalog)`. The Qt Windows Core step had
the same errors. Its Tauri native adapter and Python/Rust interoperability jobs
completed on Windows, Ubuntu and macOS. Windows logged three native probe
tests (including 24-byte, 8-byte-aligned `FILE_ID_INFO`, protocol vectors and
lease behavior) and ten catalog tests; Ubuntu and macOS logged two native
probe tests and nine catalog tests each. Interoperability passed on all three
hosts. The 128-bit golden vectors are test vectors, not proof of every Windows
identity edge case or byte-order case. These results apply to 8eb, not the
final outcome for 806.

## Preserved earlier attempts

Compatibility/bridge orchestration had two preserved unsuccessful starts
before the successful attempt 3: attempt 1 stopped at an exclusive-output
directory guard before the helper ran; attempt 2 reached the real registry
boundary and stopped on a read-only filesystem, with no fixture events and no
input/output changes. A separate proposed launch was rejected by automatic
approval review before execution and created no attempt-3 output directory.
After explicit approval for that exact generated-fixture command, attempt 3
ran once and passed. The rejected launch was not a test failure and is not
counted as an execution.

- The first focused fix attempt ran 43 tests and exited 1 with four failures
  and two errors while the fixed per-user registry was denied by the restricted
  sandbox. Its stderr SHA-256 is
  `d54490fa66a7fd3dd29bee3ea657d263afb7a98d17969c77418a6de0eccc5de8`; receipt
  SHA-256 is `b0fc648c46c02c9881975fe7d571db54cb97acf484b7ad956bd833467605268c`.
  This remains a failed attempt, not a passing result.
- The later focused fix attempt ran the same 43 tests and exited 0. Its stderr
  SHA-256 is
  `6cc12b0328243354629119c6401c9e2c2872bc79906ac4ce921a1d23c7ada869`; receipt
  SHA-256 is `c22fe0968ca98c59aa78f0283e31ab721a15759834281255de01248800d1eee6`.
- The first full Core run used the pre-fix runtime candidate
  `fdbeb370a94fa42632ad8d92a0a82e290dd44d2f629be294168c92278928638f` and
  exited 1 after 335 tests, with one failure and one error. The thumbnail
  cancellation path raised `KeyError` before child launch; the backup busy
  condition surfaced as a generic library-identity `ValueError` instead of a
  bounded busy refusal. Raw stderr SHA-256:
  `cb435c2e6bd45990f59e9e3100aa8058f819d3970154868986d663cb5eaa08b1`;
  receipt SHA-256:
  `5d340bad380be7b68528621276896affd92582e3399400e0c4de43955ecde272`.
  That result remains preserved and was not rewritten by the passing run.
- The obsolete frozen attempt had a package child direct exit of `-15`; its
  supervising helper exited `1`. These are separate exits and neither is a
  frozen pass. Package-log SHA-256:
  `d164e5d15df7ae70f0849acc54ad913cb146b22ee69f5bb210bcc54bd53c5675`.
  The refreshed build is recorded separately below.

## Frozen package smoke evidence

The refreshed frozen build receipt records all nine named smokes as passed,
including recovery publication. This is package-smoke evidence, not a native
desktop lifecycle result. Task49 independently verified the receipt, raw
logs, metrics, binary, source freeze and output preservation. The package ran against the same exact uncommitted runtime candidate
ID above, without claiming Git HEAD equivalence. Its receipt SHA-256 is
`749e3861ab1c5b5be77c6bce56d7bb366fe5dfe3810b689de05ebd2533db35c8`; the
package log SHA-256 is
`7c882053dabc95de7cba2d4743efd7c496c6c6534feb55acefb8a825d4baf60e`. The
package command exited 0 after 392.216 s. Its binary SHA-256 is
`c712019fd83ef6a4fb54d3c4333891facad600e7c79d02b929acad5c18f8aab4`
(51,297,792 bytes, mode 755); metrics SHA-256 is
`843ab63096f2719b64ce9788446b742dfc5682a74d5ff90ff70e2801f30c283a`. The
receipt reports the 164 repository/source inputs and 15 deployed outputs
unchanged, with no remaining private workers.

The nine labels were frozen admission, thumbnail, gallery worker, desktop
identity, external probe, cached preview, comparison, gallery filters, and
recovery worker publication. The older frozen attempt remains a separate
failure: its package child exited `-15` and its supervising helper exited `1`.

## Evidence boundaries and remaining gates

The focused and full Core tests provide bounded functional evidence for their
named generated-fixture cases. The offscreen Qt suite provides Qt service and
UI test evidence on this Linux host. A separate native Qt attempt-5 generated
fixture passed its named lifecycle on KDE Wayland through Qt xcb/XWayland: an
exposed owner refused a second CLI; close stayed pending while its owned idle
child lived; after child exit, the owner released, a CLI acquired, and the
production window reopened and closed. The exact host portal lookup warning
remains a private harness limitation; host portal registration is unqualified.
This is not native Wayland protocol evidence, Windows/macOS desktop evidence,
or native Tauri GUI evidence. The frozen Linux package passed its nine named
smokes but does not establish a native desktop lifecycle.

Hosted CI for the exact 806 source head had three checks in progress at the
recorded preparation snapshot. The terminal current-head checks, actual Windows
totals and named skips belong in the PR acceptance record. None of these bounded results
establish support for old/external writers, unsupported or network/removable
storage, full FR-LIB-003 acceptance, all SDD requirements, or release
readiness. Merge and deployment remain separate decisions.
