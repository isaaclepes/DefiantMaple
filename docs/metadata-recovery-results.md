# Metadata recovery evidence checkpoint

Status: **bounded recovery milestone evidence reviewed; full SDD acceptance and release remain held**. The reviewed generated Linux run cleared 14 bounded native case assertions, and exact current-head CI at 317 passed 30/30 checks. These results qualify the bounded milestone; they do not establish full SDD snapshot/restore acceptance or authorize merge, deployment, or release. Docs-only publication CI remains pending.

The reviewed Qt integration passed the focused recovery/comparison/usability suite (**43/43**, zero skips) and the official Qt discovery suite (**178/178**, zero skips). The official command was run with the project virtual environment, Python 3.14.7, `QT_QPA_PLATFORM=offscreen`, and `PYTHONFAULTHANDLER=1`. It completed in 37.353 seconds with direct exit 0. The private raw log basename is `qt-discovery-20261015T1018Z.log`, SHA-256 `4d7c8961bdadc05e283150c1058c4a086077cb3ad858a863b16384628f48896a`. The 57-file pre/post source manifests matched exactly; their digest is `7065665b12bd636571ac3cea69f10eb29f6926bd4873496ca7b6859096eff8f6`. No failure, error, skip, warning, or callback traceback appeared.

An earlier source-revision discovery run remains in the private evidence store as a failed historical checkpoint: **176/177 passed**, one source-selection readiness timeout, exit 1. The later run followed a reviewed source correction and included a delayed-reply selection ABA regression case. The earlier failure is retained and not represented as a current passing result.

The frozen Core regression receipt records focused **89/89** and full **293/293**, zero skips. The amended portability/concurrency oracle has its own focused **22/22** run, zero skips. Task 43 independently cleared the reviewed Core and Qt implementation for the next stage. A source-mode packaging smoke exercised actual spawned Core backup, inspection, and isolated restore workers on its generated fixture and reported `publication_passed`; its private raw-log SHA-256 is `77f2eaee57a0ab5516ef788357c1c37199f2e9101df9cb162ea1be3e4504cb35`. It is not an executable build result and does not prove absence of source reads.

The reviewed frozen local build at published head `0667199f` exited 0. Its unsigned offscreen artifact was 51,199,488 bytes, SHA-256 `eb66e05e21045734426a04fcac1b7279dbc0fc1c5525fc88f02ab32d555a377b`. The receipt reports all seven preserved smokes plus the new spawned recovery-worker smoke passing; all 281 shadow inventory files and runtime sources matched the frozen inventory, and all 15 deployed-output records remained unchanged. The artifact was **not deployed**. This is local build/smoke evidence, not native desktop acceptance or hosted platform CI; it predates the f74 RLIMIT guard and the 317 Qt correction.

## Exact-head hosted CI

The historical read-only audit covered all four workflow runs and all 30 checks for exact head `0667199f759ce8c0ce304472e1efca661234f148`: Core push, Core PR, Qt PR, and Tauri PR. **29 checks succeeded and one failed.** Core push, Core PR, and Tauri PR runs completed successfully. The Qt PR run failed only in the macOS packaging job's frozen recovery-worker smoke; no workflow was rerun.

All four Windows Core jobs (push and PR, Python 3.11 and 3.13) ran **296 tests each**: **279 passed, 17 skipped**. Twelve recovery publication tests skipped because publication requires the reviewed Linux PCIe NVMe adapter: `test_backup_inspect_restore_preserves_rows_and_guards_linked_original`, `test_backup_refuses_unknown_application_id_before_publication`, `test_cache_and_source_containment_refuse_before_publication`, `test_closed_package_reinspection_prevents_corrupt_stage_publication`, `test_concurrent_writer_snapshot_is_consistent_or_bounded_refusal`, `test_digest_and_existing_destination_refuse_without_overwrite`, `test_new_restore_target_refuses_preexisting_sidecar`, `test_post_link_failure_is_explicitly_uncertain_and_keeps_final`, `test_precanceled_backup_has_bounded_exit_and_no_final`, `test_resolved_source_alias_cannot_hide_output_containment`, `test_restore_sidecar_refusal_with_valid_package`, and `test_symlink_and_truncated_package_refuse`. The other five skips were `test_escaped_network_mount_is_not_misclassified_as_local` (synthetic mountinfo uses POSIX path spelling), `test_reviewed_root_requires_read_and_search_access` (POSIX effective-ID and `O_DIRECTORY` semantics), `test_nonregular_manifest_fifo_refuses_without_open_block` (FIFO creation is POSIX-only), `test_supported_address_space_failure_refuses_instead_of_silent_waiver` (POSIX resource controls unavailable on Windows), and `test_local_loss_recovery_checks_both_phases_and_stable_uuids` (host denied generated root rename while a scan handle was open; portable injected-loss protocol is tested separately).

The Windows Qt job passed its Core suite (296 run: 279 passed, 17 skipped) and Qt suite (178 run: 172 passed, 6 skipped); catalog generation and unsigned artifact packaging also completed successfully. The six Qt-suite skips were `test_first_stage_malformed_and_partial_frame_deadline_create_no_scratch` (POSIX byte-stream injection), `test_file_replacement_refuses_captured_review_before_core_dispatch`, `test_atomic_file_replacement_refuses_old_connection_rows`, and `test_replacement_before_legacy_and_write_never_dispatches_core_handler` (Windows denied atomic replacement of generated open SQLite files with `WinError 5`), `test_dialog_worker_restore_preserves_active_catalog_and_reports_standalone_limit` (reviewed Linux adapter required), and `test_qt_per_source_enable_clears_only_selected_reviewed_hold` (POSIX effective-ID and `O_DIRECTORY` semantics required). The macOS Qt job's Core suite passed (296 run: 284 passed, 12 skipped) and its Qt suite passed (178 run: 177 passed, 1 skipped); the only Qt skip required the reviewed Linux adapter. Its packaging command created the app, then `frozen_recovery_smoke` raised `ValueError: Frozen recovery worker smoke failed` at `package.py:314` (called from `main` at line 584), exiting 1. This was a hosted packaging failure at historical head `0667199f`; later f74 and 317 Qt workflows succeeded.

The historical private read-only run/check snapshot SHA-256 is `bb12a1152c5b5dff6ca0125658a19ed35929a43ce367efca11216abcbcf9ba97`; the job snapshot SHA-256 is `55ecf3183e2773bab2f227d81f5c459eadbeec3b36c51815e538f477985b2306`. Full raw job logs remain private. Their SHA-256 digests are recorded in the sanitized evidence JSON and private audit receipt; the macOS failure log digest is `ed4d2edba3e9d7cefda8680030ea674121e6969e3dcaa749159f8c6ab8a45eed`. These hosted test/build results are not native acceptance or recovery acceptance.

The later read-only audit covered all four workflow runs and all 30 checks at exact head `8b26e3eb8e3e7e06b596fc4d48d1c38da9b596e0`, tree `a173ea1c09c26cbbd3e9112d0e575f26c1df3fe9`. **28 checks succeeded and two failed**, both in the Qt PR workflow: the Windows Qt job and the macOS frozen recovery smoke. Core push, Core PR, Tauri PR, and Ubuntu Qt package jobs succeeded. Each of the four Windows Core jobs ran 296 tests with 279 passing and 17 skipped. Windows Qt ran Core 296 (279 pass, 17 skipped), then Qt 181 (174 pass, one failure, six skipped). The failed test was `test_terminal_error_is_bounded_and_redacts_generated_and_other_paths`: its assertion expected a redacted `<path>` marker, while the diagnostic ended with `stderr_terminal=None`. The six skips covered POSIX partial-frame injection; three Windows-denied atomic replacements of open SQLite files; native recovery publication requiring the reviewed Linux PCIe NVMe adapter; and POSIX effective-ID/`O_DIRECTORY` enable semantics.

The macOS Qt job ran Core 296 (284 pass, 12 skipped) and Qt 181 (180 pass, one Linux-adapter skip). Its frozen recovery worker smoke exited 1 after app creation. The child reported `ValueError: Spawned recovery inspection refused unexpectedly: ValueError: current limit exceeds maximum limit` (child stdout SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; stderr SHA-256 `0169d70f57342dc3df98cff4da818a725ab6d652f127a4c0dbdb5a96398941a9`). This macOS failure was specific to head 8b26e3eb; later f74 and 317 Qt workflow runs succeeded. The private all-runs/checks/jobs snapshot SHA-256 is `d9d5df81dcb92546d8024ef12fc639ec2c45fe8552599d0229447d746a1261d0`. Raw logs remain private: macOS Qt `a465039abd40500c65f2cb435deb022bb7a50262b634c6cda9c654056cb82f25`, Windows Qt `437ef8b3b53138f7a7f31872708a91aeb271d1b8441a2bc2137c7e0a00e88196`, Windows Core Python 3.11 `c0f855759b4afc79494503ff93eed1fed14927f7fc99a0fd78f27ffdc97f534e`, and Python 3.13 `f5af152cca8737651c8d84c1b19cdb343c31f8c3140b6f3f175f4cf5092d7b03`. This hosted cohort is not overall recovery acceptance.

The exact Qt close-ownership correction at head 317 passed its focused
regression **8/8**, zero skips, direct exit 0; Task 43 independently cleared
those exact Qt files for follow-up hosted CI. The delayed worker used synthetic
exact Core replies, so this focused run does not establish a real post-publication
race or an OS-blocked worker. The earlier native run and frozen local build
remain tied to their measured heads and were not repeated for this Qt-only fix.

At current published head `317ee0b1175ec89bb5e31c4785bc01c9c70c1d22`, the
read-only GitHub API audit found exactly four triggered workflow runs and 30
check-runs; every run and every check-run completed successfully. Core push
[38822980927](https://github.com/isaaclepes/DefiantMaple/actions/runs/38822980927)
and Core PR
[38822987036](https://github.com/isaaclepes/DefiantMaple/actions/runs/38822987036)
each had 12 successful jobs. Qt PR
[38822987039](https://github.com/isaaclepes/DefiantMaple/actions/runs/38822987039)
and Tauri PR
[38822987121](https://github.com/isaaclepes/DefiantMaple/actions/runs/38822987121)
each had three successful jobs. The PR remains draft/open, clean and mergeable,
with no submitted reviews or comments. No workflow was canceled or rerun.

All four Windows Core test jobs (push and PR, Python 3.11 and 3.13) ran
**298 tests each: 281 passed, 17 skipped, zero failed**. Each Windows test job
also completed the public-artifact privacy check. The 17 skips comprise the
12 recovery-publication cases listed above, which require the reviewed Linux
PCIe NVMe adapter, plus `test_nonregular_manifest_fifo_refuses_without_open_block`
(POSIX FIFO creation),
`test_supported_address_space_failure_refuses_instead_of_silent_waiver`
(POSIX resource controls),
`test_local_loss_recovery_checks_both_phases_and_stable_uuids` (the host
denied generated-root rename with an open scan handle; portable injected-loss
protocol tested separately),
`test_escaped_network_mount_is_not_misclassified_as_local` (synthetic
mountinfo uses POSIX path spelling), and
`test_reviewed_root_requires_read_and_search_access` (POSIX effective-ID and
`O_DIRECTORY` semantics). All four Windows Core jobs skipped the same named
cases. Windows source-scan soak and scan-profile jobs succeeded in both runs.

The Windows Qt job passed Core **298/281/17** and ran Qt **183/177/6**
(run/passed/skipped), with zero failures. Its six Qt skips were
`test_first_stage_malformed_and_partial_frame_deadline_create_no_scratch`
(POSIX byte-stream injection),
`test_file_replacement_refuses_captured_review_before_core_dispatch`,
`test_atomic_file_replacement_refuses_old_connection_rows`, and
`test_replacement_before_legacy_and_write_never_dispatches_core_handler`
(Windows `WinError 5` denied replacement of generated open SQLite files),
`test_dialog_worker_restore_preserves_active_catalog_and_reports_standalone_limit`
(reviewed Linux adapter required), and
`test_qt_per_source_enable_clears_only_selected_reviewed_hold` (POSIX
effective-ID and `O_DIRECTORY` semantics). Catalog generation, unsigned artifact
packaging, and upload succeeded. Qt and Tauri package jobs succeeded on Linux,
Windows, and macOS.

The five Windows raw logs are retained privately: push Python 3.11 SHA-256
`e81e90b80dd390e18cd5e816d073645e8e794b6a3aed714df13127d93c90035a`, push
Python 3.13 `1652c2181e9e72fdd8fd4092f6a4fc9c41770c4bd478698a7ee771925393b444`,
PR Python 3.11 `05f1cabb43ee0ac131cf8c346bf607d57e75fbbd12738e3109aaf2c1272c3c27`,
PR Python 3.13 `d4440f8a71da085f7d1af186fcd923f6356325df3a11dff9c20f0d6c03fdf504`,
and Qt PR Windows `641abaf0583856bf2b6dbae787c5b902587b6fcafed749f794252670e2ab3d43`.
This resolves the exact-head hosted CI and Windows-summary audit. It remains
regression/platform evidence, not Task 42 recovery acceptance.

The first visible native attempt ran at exact head `0667199f759ce8c0ce304472e1efca661234f148` in the unlocked Wayland session, using driver SHA-256 `1daf7f0a8da3404601e6c544f3f019c8dba478563925b1a5d23368d15af95fa4` and fixture-manifest SHA-256 `e60a939a784661b233a0f77cc1859bc56eb5bba464f319af58fcbe6007e0cd6a`. It stopped before N01: the driver called synchronous `row_for_asset` on the asynchronous gallery and raised `RuntimeError: Use request_rank for an async gallery`; direct exit was 1 and the receipt recorded `cleanup_uncertain`. **Zero native cases were observed.** The process returned, but its final live-window close returned false. Root's post-failure inventory check found all 12 initial generated-fixture files unchanged by hash and physical metadata; this is a mutation check, not proof of no reads. The private raw-log SHA-256 is `304389812da6fcf01a18981b0f323db65501bce674d0d0566a8d8ca6b8b2771d`; the private receipt SHA-256 is `a2e1e523433d06abcd52d54d89a0539154f04c51d2a7e45fb9bfbe1e5c3b5122`; the preservation-record SHA-256 is `0aec99cedba5467643b4ab78a54b30c7a23bd19ef19137e220f8f893ab08a9ed`.

Native attempt 2 ran on reviewed head `8b26e3eb8e3e7e06b596fc4d48d1c38da9b596e0`, tree `a173ea1c09c26cbbd3e9112d0e575f26c1df3fe9`, with driver SHA-256 `f0d8f9b8be13af9525ec900a57f4b6b271c146c4c02c03257c6e9bf558a0d93c` and generated-fixture manifest SHA-256 `b3115c7c05edea13e3658d730f7bccf729440745c00c4dba911ee751a6734f88`. It observed N01, N02, N03, N04, N08, N05, N06, N07, N09, N10, and N11 pass in that order. N12 then stopped the run: after source activation changed the gallery view, the production rank guard refused the stale captured rank with `Gallery view changed; reload count and first page`. This is an expected fail-closed refusal and exposed a driver sequencing gap; it does not count as a pass for N12 or overall native acceptance. Direct exit was 1. Cleanup evidence reports all windows closed, workers no longer owned, and gateways complete. The private raw-log SHA-256 is `adb510b49113339bb4fd9ee19d0c94a446b685af67e48e4fc26f52cf719437d2`; the private receipt SHA-256 is `6279543bbd07470967a5f37ccb3ceceda2f4a46f8c9cb0876fcab12316eb3a3a`. The receipt records that no child-wide source-read instrumentation was available; physical checks and these observations do not prove absence of reads. That bounded rank-refresh correction was reviewed and used in native attempt 3 below.

After the bounded rank-refresh correction, native attempt 3 ran on the same reviewed head in the visible unlocked Wayland session. The receipt records **all 14 cases passed**, and an independent reviewer cleared the bounded case assertions. The run used driver SHA-256 `ce7dadcb16321316fc3eeac7e1b247668763193cce1131f80a7e9201bc9a5826` and fixture-manifest SHA-256 `cb16cb15c4babaeaff96cc591a114519634c6cfed08fbbda89cb3dc885e2eec2`; direct exit was 0. Observations covered visible recovery controls; backup and inspection with no library switch; isolated restore with the four declared metadata deltas and durable per-source holds; pending-state browsing with a known cache; changed-root-map refusal; explicit per-source enable; standalone browse-only behavior; invalid-package and collision refusal; output-containment refusals; inspect-worker result delivery after a view change; actual Core inspect cancellation plus a separate injected delayed-QThread ownership test; and generated source/cache/live/package integrity checks. Cleanup closed all windows, left no owned recovery worker, and completed gateways. Root's final preservation record found no mismatch in the 15 deployed-output baseline records.

This is a **bounded reviewed native run**, not overall recovery acceptance. It predates the f74 RLIMIT guard; the frozen binary and native UI flow were not rebuilt or re-executed at f74. The driver supplied paths directly; native file-chooser selection was not exercised. No child-wide source-file-access trace was available, so file integrity checks do not prove absence of reads. N13's delayed QThread was an injected lifecycle case (not an OS-blocked worker); actual Core cancellation was observed separately. The private receipt SHA-256 is `a0b80d187283853123795046d485c07b517a91e31abe0cf309447e38b1022819`; the root execution-record SHA-256 is `5518f92bd151b3a909f9a6b0671f9db7061d318786ef38dbfba6168c13a1b31e`; the final preservation-record SHA-256 is `58f87196cea74f8248c03b29200735f96b01627159718a0f9ef0b9360b277e90`. The private raw log is empty (SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).

![Sanitized native recovery controls, with paths and catalog data excluded](evidence/metadata-recovery/native-controls-linux.png)

| Evidence area | Observed result | Current limit |
|---|---|---|
| Core tests and code review | Historical frozen Core receipt: 89 focused and 293 full tests passed; exact reviewed design/Core checkpoint | These runs predate the later Linux-only RLIMIT runtime amendment; they are regression/review evidence, not Task 42 acceptance |
| Core portability and Linux release guard | Earlier test-only oracle: 22 tests passed; current f74 guard-focused run: 24/24 passed with direct exit 0 | The focused 24-test run covers the later Linux-only RLIMIT guard; the full 293-test receipt predates that runtime change. macOS unsupported-adapter refusal still requires hosted verification |
| Qt focused regression | 43 focused Qt tests passed; Task 43 clearance for the reviewed integration | Offscreen regression only |
| Qt full discovery | 178 tests passed, zero skips, exit 0; source manifests identical | Offscreen regression only; no native UI or no-read proof |
| Generated source-mode package smoke | Actual Core worker backup, inspect, restore, and refusal checks passed on the qualified generated fixture | Not a packaged executable, native UI, or source no-read proof |
| Frozen local build and smoke | Earlier head 0667199f: exit 0; 51,199,488-byte unsigned artifact; seven preserved smokes and spawned recovery-worker smoke passed; 281 shadow files/runtime matched and 15 deployed outputs unchanged | Not deployed; binary predates f74's RLIMIT guard and was not rebuilt at f74; not native UI or hosted CI |
| Native visible-desktop cases N01–N14 | **All 14 case assertions passed in attempt 3 and were independently cleared for the bounded Wayland run** | Attempts 1 and 2 remain recorded failures. Attempt 3 cleanup completed and the 15-output baseline is unchanged. Native chooser paths were not exercised; no child-wide source-read trace was available; N13 separates actual Core cancellation from an injected delayed QThread lifecycle test. This does not establish absence of reads or overall recovery acceptance. |
| Exact-head hosted Windows/macOS/Linux CI | Historical head 0667199f: 29/30; head 8b26e3eb: **28/30**; published 317ee0b: **30/30 successful checks**, with four successful workflows and actual Windows test/skip summaries recorded above | Five Windows raw logs are retained privately; all Windows jobs and named skips are recorded above. Hosted CI is platform regression evidence, not recovery acceptance. |
| Source-read privacy audit and independent final review | Task 43 static source-access call-path audit cleared; final review pending | No child-wide runtime source-read trace was available; physical before/after hashes establish integrity only, not absence of reads |
| Requirement transitions and release | **Pending** | Existing tracker statuses remain authoritative |

The current tracker marks FR-RECOVERY-001, 002, 004, and 005 **Partial** for bounded Core evidence; FR-RECOVERY-003, 006, and 007 remain **Not Started**. This checkpoint does not recommend any tracker change. The reviewed Linux Wayland run independently cleared all 14 bounded native case assertions, with the file-chooser and child-read instrumentation limits recorded above. The current hosted CI gate is satisfied; child-wide source-read tracing, final staged-set review, and the remaining recovery acceptance gates remain open.

See [Task 42](tasks/42-metadata-recovery-acceptance.md) for exact historical/current run details and the remaining acceptance gates, and [the acceptance protocol](metadata-recovery-acceptance.md) for required evidence and limits.
