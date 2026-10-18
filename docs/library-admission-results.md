# Library admission results (incomplete review draft)

**Status: incomplete; exact-candidate local suites passed, acceptance remains held.**
This is a sanitized evidence ledger for review, not release or full SDD
acceptance. The reviewed design is the exact SHA-256
`53a214f89d5f36c416c94acfbe9b766663d92b6ed465f28bdeac1220a86ace22`.
Implementation scope remains cooperative admission for current participating
Qt, CLI, and Rust/Tauri entry points plus explicit Core admitted sessions.
Unwrapped Core calls, old clients, arbitrary SQLite writers, and unsupported
storage are outside that guarantee.

## Exact local candidate and preservation

The run used the reviewed, uncommitted runtime overlay on base commit
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

## Run record

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
source and output comparisons were clean.

## Preserved earlier attempts

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
UI test evidence on this Linux host; it does not demonstrate a mapped/exposed
native desktop window or compositor lifecycle. The frozen package receipt
covers only its named packaged smokes and does not establish native GUI
behavior.

Actual three-host Rust admission-probe and Tauri package CI evidence remains
held. Native Qt desktop evidence remains held pending independent review of
the exact helper source before execution. No native Tauri GUI qualification is
claimed. The local results do not establish Windows or macOS adapter execution,
hosted CI status, network/removable storage support, behavior of old or
external writers, full FR-LIB-003 acceptance, or release readiness. Task49 must
review the evidence and privacy boundaries before any results are treated as
final.
