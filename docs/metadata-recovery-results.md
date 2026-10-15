# Metadata recovery evidence checkpoint

Status: **acceptance held**. This record reports regression and review evidence only. It does not claim that metadata recovery has been accepted or released.

The reviewed Qt integration passed the focused recovery/comparison/usability suite (**43/43**, zero skips) and the official Qt discovery suite (**178/178**, zero skips). The official command was run with the project virtual environment, Python 3.14.7, `QT_QPA_PLATFORM=offscreen`, and `PYTHONFAULTHANDLER=1`. It completed in 37.353 seconds with direct exit 0. The private raw log basename is `qt-discovery-20261015T1018Z.log`, SHA-256 `4d7c8961bdadc05e283150c1058c4a086077cb3ad858a863b16384628f48896a`. The 57-file pre/post source manifests matched exactly; their digest is `7065665b12bd636571ac3cea69f10eb29f6926bd4873496ca7b6859096eff8f6`. No failure, error, skip, warning, or callback traceback appeared.

An earlier source-revision discovery run remains in the private evidence store as a failed historical checkpoint: **176/177 passed**, one source-selection readiness timeout, exit 1. The later run followed a reviewed source correction and included a delayed-reply selection ABA regression case. The earlier failure is retained and not represented as a current passing result.

The frozen Core regression receipt records focused **89/89** and full **293/293**, zero skips. The amended portability/concurrency oracle has its own focused **22/22** run, zero skips. Task 43 independently cleared the reviewed Core and Qt implementation for the next stage. A source-mode packaging smoke exercised actual spawned Core backup, inspection, and isolated restore workers on its generated fixture and reported `publication_passed`; its private raw-log SHA-256 is `77f2eaee57a0ab5516ef788357c1c37199f2e9101df9cb162ea1be3e4504cb35`. It is not an executable build result and does not prove absence of source reads.

| Evidence area | Observed result | Current limit |
|---|---|---|
| Core tests and code review | 89 focused and 293 full Core tests passed; exact reviewed Core/design clearance | Not the Task 42 snapshot/restore acceptance matrix |
| Core portability oracle | 22 focused tests passed; exact named skips retained for unsupported native publication capabilities | No fresh 293-test run after the test-only portability amendment; Core runtime was unchanged |
| Qt focused regression | 43 focused Qt tests passed; Task 43 clearance for the reviewed integration | Offscreen regression only |
| Qt full discovery | 178 tests passed, zero skips, exit 0; source manifests identical | Offscreen regression only; no native UI or no-read proof |
| Generated source-mode package smoke | Actual Core worker backup, inspect, restore, and refusal checks passed on the qualified generated fixture | Not a packaged executable, native UI, or source no-read proof |
| Native visible-desktop cases N01–N14 | **Pending** | No native case has been executed or accepted |
| Frozen executable/build smoke | **Pending** | No current binary/package acceptance result |
| Exact-head hosted Windows/macOS/Linux CI | **Pending** | No CI result is asserted here |
| Source-read privacy audit and independent final review | **Pending** | Physical before/after hashes establish integrity only, not absence of reads |
| Requirement transitions and release | **Pending** | Existing tracker statuses remain authoritative |

The current tracker marks FR-RECOVERY-001, 002, 004, and 005 **Partial** for bounded Core evidence; FR-RECOVERY-003, 006, and 007 remain **Not Started**. This checkpoint does not recommend any tracker change. Native cases will be reported only after the reviewed helper is run in the unlocked visible Wayland session, each observation is captured, and privacy review is complete.

See [Task 42](tasks/42-metadata-recovery-acceptance.md) for exact historical/current run details and the remaining acceptance gates, and [the acceptance protocol](metadata-recovery-acceptance.md) for required evidence and limits.
