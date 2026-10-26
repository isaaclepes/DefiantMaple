Adds opt-in, app-running local metadata snapshots through the verified backup pipeline. On supported Linux storage, explicit Enable now creates private scheduler storage for fresh default profiles and existing user-owned `0755` app-data directories, preserving existing directory permissions.

## Current bounded status (2026-10-26)

PR 25 remains draft and unmerged at `c2149e51b4ef95e125da9793971b79cd603f596c` (tree `4ebcd668c5aea42ebcf5dbcbbce02ba41a930c03`). The published locator-profile bootstrap fix is exactly six reviewed files. The same-head hosted CI audit records 30/30 checks green. This is source CI evidence; it does not qualify a product binary or full recovery.

The author reported 79 focused passes for the source change; the source review recorded that report without rerunning suites. Windows summaries: Core 513 tests / 155 skipped on Python 3.11 and 3.13; Qt root 513 / 96 skipped and prototype 192 / 6 skipped. The ten locator cases have explicit platform skips on Windows. The new XDG profile provenance case is Linux-only and skipped on Windows. Ubuntu Qt summaries: root 513 / 86 skipped and prototype 192 / 1 skipped. Named skip reasons are in the inline evidence JSON.

A later-current independent qualification accepted the complete build tree, with 720 entries and a current binary of 51,879,424 bytes (SHA-256 `cb33cfc38019cfa8758f8c9f36bcc1e7e7c3fe7cfef1644d84eb00560e966bb9`). The earlier strict compile receipt remains failed closed because its postcheck found a symlink or special file. The rejected entries were exactly three intermediate Nuitka C-source links to pinned compiler files; the separate inventory verified all regular outputs and those links. Later qualification does not retroactively turn that receipt green. The older binary hash `cb9f1ce4f3f64730d9a8923e3bf3128db5aa2ef4babdaaa4d2e1842fdab4d387` remains unchanged.

The later V13 generated-fixture native case completed all seven checkpoints: unconfigured, enabled with initial verified package, first explicit snapshot, hidden settings window, second explicit snapshot, stopped, and reopened stopped. Counts were baseline, 1, 2, 2, 3, 3, 3; retention stayed disabled; stopped state persisted after reopen. The Qt event gate recorded the two start notices and completion notice as painted/exposed for at least five seconds. Native notice-only captures and 105 sampled focus IDs support presentation within the recorded limits; they do not establish user attention or universal compositor visibility. Three verified packages were each 237,971 bytes; hashes and ordinals are in the inline evidence JSON. New locator root mode was 0700; existing app-data parent remained 0755. Prior registry metadata was preserved and exactly three planned empty private locks were added. Fifteen protected outputs and source/catalog/cache guards remained unchanged.

Both launches ended naturally with exit status 0, no signals or forced cleanup, and no remaining owned group members. Each run recorded one adopted child reaped with status 0 before artifact exit. Its role is UNKNOWN from retained evidence; no executable identity was captured. This supports external process/session closure only and does not prove Qt worker-thread join or internal thread shutdown.

The earlier V11 native attempt remains a failed partial result: only the first three checkpoints were accepted before the owned window became unviewable during an Escape key-release path; forced cleanup followed. V13 is a separate later case and does not erase that history.

ENOSPC remains unqualified: actual G0, E1 and E2 runs are all zero. Hash-check counts below are payload manifest entries, not total published files. T1-T3 had 11 payload manifest entries within 13 committed files; T1’s retained run summary says verification passed, but its raw job log is unavailable, while T2 logged 10/11 OK and one failure and T3 logged 11/11 OK. T4-T8 each had 13/13 payload hash entries verified within 15 committed files; earlier references to “15 source checks” meant the total files published. T9 had 17/17 payload hash entries verified within 19 committed files; T10 had 18/18 entries within 20 published files. Each total includes the hash manifest and workflow. T1-T7 failed before package installation for the recorded source-verification, dependency allowlist, apt-plan, runner-permission, or bounded-query reasons. T8 passed source checks and package setup before the keyring inventory failure; the later K1 read-only inventory recorded the keyring facts and the two world-writable ancestors.

T9 (`40320808591`, attempt 1; exact head `1a7ff5afc5720157f8c57daa5cbd4d3f49bb3370`, tree `b2698e54c5455392210978b086327c0442c8958d`) used the independently reviewed V11 source. All 17 payload hash entries passed; the T9 commit contains 19 remote files total. Authenticated metadata for 18 packages, the apt plan and guard, and the APT install command status checks succeeded. The subsequent host inventory failed with `RuntimeError: ambiguous package ownership: /lib64/ld-linux-x86-64.so.2`. At T9, the ambiguous owner remained unknown; no owner was inferred. Its cleanup record says `removed` and matches the created file/directory identities and key hash. The uploaded evidence bundle does not include an APT installation transcript. Image download/authentication and QEMU boot were skipped; T9 produced no boot, ENOSPC, G0, E1 or E2 result.

A separate K2 read-only inventory later completed on exact push commit `4ae39425e37152aac2fc6de5b1b485b9eabee882` (tree `b67bac27c7782600cc46c5daa1c321a2beb82959`). Its runner was Ubuntu 24.04.5, image `ubuntu24`, version `20261023.334.3`; that image version is a K2 observation and is not attributed retroactively to T9. The requested `/lib64/ld-linux-x86-64.so.2` path was a symlink to `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2`. `dpkg-query -S` on the alias returned only two libc6 diversion records, with no direct owner; querying the canonical target returned `libc6:amd64`, version `2.39-0ubuntu8.9`. The canonical file was 236,616 bytes with SHA-256 `c20a2dc8917c755f02b94049356320fe1f62ac7d9f8994731f807d9df39302da`. The raw bounded query outputs and modes are recorded in the JSON below. K2 is a read-only inventory, not a T9 repair or a direct-boot run. Its host closure remains incomplete; QEMU binaries were absent from PATH and G0/E1/E2 remain zero.

V12 passed 49 focused tests and received independent source review CLEAR; it was used for T10. T10's source checks passed, but its hosted setup still failed on a separate libaio symlink during host inventory after APT package installation. The cgroup-v2 common-ancestor write-permission rule is established: non-root migration requires write access to both the destination `cgroup.procs` and the source/destination common ancestor's `cgroup.procs`. The V12 source assumes the runner has that permission without recording or verifying it. The parent's permission was not measured, so EACCES is not an observed result. Its narrow root-only helper attaches one paused, identity-verified child with bounded identity, limit and ordering checks. It does not chmod/chown cgroups or run QEMU as root.

T10 (`40326427395`, attempt 1; exact head `91008b17c255c19696ba2494188ab682d1a9fd37`, tree `75ca7153fd975b341b02d254bdc355084ae2796f`) used V12. All 18 payload hash entries passed within 20 committed files. APT update, 18 authenticated metadata records, apt plan/guard, and the install command status checks passed; the transaction installed 18 packages, with 98 not upgraded and no upgrades or removals. Final host inventory failed with `PackageOwnershipError` for `/lib/x86_64-linux-gnu/libaio.so.1t64`. The retained bounded `dpkg-query -S` returned 1 with no stdout and “no path found matching pattern”; it recorded resolved path `/usr/lib/x86_64-linux-gnu/libaio.so.1t64.0.2`, but no canonical-path query. Package ownership therefore remains UNKNOWN; no owner is guessed. The keyring cleanup receipt says `removed` and its file/directory identities and key hash match creation. The canonical image download/authentication and QEMU boot steps were skipped; no cgroup, root attach, watchdog, or guest receipt was produced. The failure receipt's `cgroup_removed=false` accompanies a skipped boot/cgroup stage and does not indicate an unremoved cgroup. T10 produced no ENOSPC, G0, E1 or E2 result.

V13 parser review is independently CLEAR for 51 focused tests, but activation was held before T11 by the cgroup-parent compatibility finding below. V14 has independently CLEAR source review with 55 focused tests; this is source-only qualification and does not qualify hosted runtime or topology. Its activation awaits a fresh all-22-file stage. Author staging is on hold pending this report and a new base. No T11 run has occurred.

## Cgroup compatibility finding and V14 status

Independent source analysis held V13 activation before T11. The observed controller process is in a populated non-root service cgroup; that cgroup cannot distribute the required domain `memory` controller to a child. This makes V13’s selected control parent incompatible with the measured hierarchy. This is a source-level finding; no runtime cgroup failure or EACCES was observed. The analysis is recorded in `work/enospc-direct-boot-cgroup-parent-source-analysis.md` (SHA-256 `04c908fde667306dcd5079e8f12e277894ad35fa7d6b567ae2d0327718fc3da2`).

V14 received independent CLEAR source review with 55 focused tests. This qualifies source only; hosted runtime and topology remain unobserved. V14 proposes the already-enabled `/sys/fs/cgroup` as a read-only control parent, separately records the service cgroup as source identity, creates only a nonce leaf, and uses the bounded root helper for one paused identity-verified child. It makes no global cgroup writes or permission changes, does not run QEMU as root, and does not move other processes. A fresh all-22-file activation stage remains outstanding. Author staging is on hold pending the report and a new base. No T11 run has occurred. ENOSPC G0/E1/E2 remain zero.

FR-RECOVERY-003 remains **Partial**. Full Phase 1 acceptance and release remain held. The V13 case does not establish restore/recovery correctness, retention deletion, arbitrary storage behavior, physical-NVMe durability, or ENOSPC behavior.

<details>
<summary>Sanitized current evidence (JSON)</summary>

```json
{
  "build": {
    "current_binary_bytes": 51879424,
    "current_binary_sha256": "cb33cfc38019cfa8758f8c9f36bcc1e7e7c3fe7cfef1644d84eb00560e966bb9",
    "later_qualification": "accepted complete tree; separate later result, not a repair of earlier receipt",
    "prior_binary_sha256": "cb9f1ce4f3f64730d9a8923e3bf3128db5aa2ef4babdaaa4d2e1842fdab4d387",
    "strict_compile": "failed closed: Build output contains a symlink or special file"
  },
  "ci": {
    "head": "c2149e51b4ef95e125da9793971b79cd603f596c",
    "named_skip_reasons": [
      "10 locator cases: Recovery publication has no reviewed native adapter on this platform",
      "Ubuntu locator cases: Recovery requires a verified durable local filesystem",
      "Windows XDG provenance: Linux locator profile provenance"
    ],
    "scope": "Hosted source CI only.",
    "ubuntu_qt": {
      "prototype": [
        192,
        1
      ],
      "root": [
        513,
        86
      ]
    },
    "windows": {
      "core_py311": [
        513,
        155
      ],
      "core_py313": [
        513,
        155
      ],
      "qt_prototype": [
        192,
        6
      ],
      "qt_root": [
        513,
        96
      ]
    }
  },
  "enospc": {
    "e1": 0,
    "e2": 0,
    "firstboot_plan": "T1-T7 failed before package installation for their recorded source, allowlist, apt-plan, runner-permission, or bounded-query failures. T8 passed 15 source checks, obtained authenticated metadata for 18 packages, passed apt_guard, and its install command returned success before the host inventory keyring check failed. K1 later recorded the exact keyring and ancestor metadata. T9 used the independently reviewed V11 source: all source checks, authenticated APT metadata (18 records), the apt plan and guard, and the install command status checks passed. T9 then failed during host inventory with ambiguous package ownership for `/lib64/ld-linux-x86-64.so.2`. The staged keyring cleanup reported `removed` with matching identities and hash. Neither T8 nor T9 reached image download or QEMU boot. T10 then passed 18/18 payload hash entries within 20 published files, completed package setup and installation (18 packages), and failed closed during host inventory on the libaio alias query. Its resolved canonical path was recorded but not queried; owner remains UNKNOWN. Keyring cleanup succeeded. No image download or cgroup/QEMU/guest step occurred. V13's explicit canonical-path fallback is under development and unactivated. V13 parser source review is CLEAR (51 focused tests), but activation was held before T11 by independent kernel/source-compatibility analysis: the observed controller process occupies a populated non-root service cgroup, which cannot distribute the required domain memory controller. This is a source-level incompatibility; no cgroup failure or runtime EACCES was observed. V14 independently passed 55 focused source tests and received CLEAR review (source-only); runtime/topology remains unobserved. It uses the already-enabled root cgroup as a read-only control parent and records the service cgroup separately as source identity. Activation awaits a fresh all-22-file stage. Author staging is on hold pending the report and a new base. No T11 run has occurred.",
    "firstboot_qualifies_g0_e1_e2": false,
    "g0": 0,
    "g0_e1_e2": 0,
    "inventory": "preliminary; no qemu-img or qemu-system-x86_64 in PATH; closure incomplete",
    "inventory_run": "40286952345",
    "k2_is_direct_boot": false,
    "k2_not_activated": false,
    "k2_status": "read-only initial inventory completed successfully; V12 source follow-up under development and not activated",
    "next": "T10 attempt 1 failed closed after successful package installation and cleanup when the libaio alias query returned no path; the resolved canonical path was not queried and owner remains UNKNOWN. V13 parser source review is CLEAR (51 focused tests), but V13 activation was held before T11 because its populated non-root service-cgroup parent cannot distribute the required domain memory controller. This is a source-level incompatibility established from the recorded hierarchy and kernel rule; no runtime cgroup failure or EACCES was observed. V14 source review is independently CLEAR with 55 focused tests, source-only; runtime/topology remains unobserved and activation awaits a fresh all-22-file stage. V14 proposes the existing root cgroup as a read-only control parent, with the service cgroup recorded separately as source identity; no global ancestor changes, root QEMU, or moving other processes. Author staging is on hold pending the report and a new base. No T11 run has occurred. G0, E1 and E2 remain zero.",
    "offline_boot_t1": {
      "artifact_sha256": "6f1bd6b6fb24968bc1c04374365c2ae623b4a5f88bd7e89aa97104517ba526d15",
      "attempt": 1,
      "commit": "1efd3e7150ba274ff507033c04531158eebe5f59",
      "count_basis": "11 lines in the retained payload manifest; run summary records exact checkout and payload hash verification passed, but no raw T1 job log is retained",
      "failure": "APT plan guard rejected libpcsclite1 outside reviewed allowlist",
      "image_download": false,
      "package_install": false,
      "payload_manifest_entry_count": 11,
      "payload_sha256_verification": "passed according to retained run summary; raw job log/hash output not retained",
      "published_remote_file_count": 13,
      "qemu_boot": false,
      "result": "failed closed before installation",
      "run_id": 40301273325
    },
    "offline_boot_t10": {
      "E1": 0,
      "E2": 0,
      "G0": 0,
      "apt_guard": "passed",
      "apt_install_status": "command and bounded-output status checks passed; install transcript not included in uploaded evidence",
      "apt_metadata_records": 18,
      "apt_metadata_sha256": "8494bbb14cd4868fae9373241f004656377794257276b9ff81739dcc6b1241ba",
      "apt_plan_log_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "apt_plan_sha256": "0f65a20f744493e8dcabcec6bed38031b2f6233da5f6ac181c511ae3050d4d09",
      "apt_transaction": {
        "estimated_new_bytes": 96927744,
        "newly_installed": 18,
        "not_upgraded": 98,
        "removed": 0,
        "upgraded": 0
      },
      "apt_update_status": "passed",
      "artifact_bytes": 20780,
      "artifact_entries": 11,
      "artifact_expanded_bytes": 19380,
      "artifact_manifest_files_validated": true,
      "artifact_sha256": "b13a85c5c9398552c274204866940ed296b7d8cd3f9d9aece8e31da4ed3f6a23",
      "attempt": 1,
      "canonical_path_queried": false,
      "cgroup_removed_receipt_value": false,
      "cgroup_setup_reached": false,
      "claim": "No image, VM/boot, ENOSPC, product import, G0, E1 or E2.",
      "commit": "91008b17c255c19696ba2494188ab682d1a9fd37",
      "commit_message": "Run reviewed offline boot measurement T10 46fbbfb76aa2d2d80ec19cf4",
      "event": "push",
      "failure": "PackageOwnershipError: ambiguous package ownership: /lib/x86_64-linux-gnu/libaio.so.1t64",
      "failure_phase": "host inventory library package-ownership mapping",
      "guest_boot": false,
      "image_authentication": false,
      "image_download": false,
      "interpretation": "The boot/cgroup step was skipped; no cgroup, QEMU, watchdog, attach, or guest receipt was created. cgroup_removed=false does not indicate a leftover cgroup.",
      "job_id": 121584187440,
      "keyring_cleanup": {
        "directory_identity_match": true,
        "file_identity_match": true,
        "hash_match": true,
        "sha256": "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
        "status": "removed"
      },
      "measurement_success": false,
      "owner": "UNKNOWN; no canonical-path query retained and no owner inferred",
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 18,
      "payload_manifest_entry_count": 18,
      "published_remote_file_count": 20,
      "qemu_launched": false,
      "receipt_success": false,
      "requested_path": "/lib/x86_64-linux-gnu/libaio.so.1t64",
      "requested_path_query": {
        "returncode": 1,
        "stderr": "dpkg-query: no path found matching pattern /lib/x86_64-linux-gnu/libaio.so.1t64\n",
        "stderr_bytes": 80,
        "stderr_truncated": false,
        "stdout": "",
        "stdout_bytes": 0,
        "stdout_truncated": false
      },
      "resolved_path": "/usr/lib/x86_64-linux-gnu/libaio.so.1t64.0.2",
      "root_attach": false,
      "run_id": 40326427395,
      "runner_image": "Ubuntu 24.04.5 LTS",
      "runner_image_version": "20261023.334.3",
      "setup_stage": "failed at final host inventory after package install status passed",
      "tree": "75ca7153fd975b341b02d254bdc355084ae2796f",
      "watchdog_started": false,
      "workflow": "ENOSPC precursor - one offline direct QEMU boot"
    },
    "offline_boot_t2": {
      "actual_git_blob_sha1": "c062446fa53e63fd8c19871e6d6cf1596c9664dd",
      "artifact": "none",
      "attempt": 1,
      "commit": "3803d4f28ba408ca538a3dadeee6dcca193c38ef",
      "count_basis": "job log shows 10 of 11 payload hash lines OK and one failed",
      "expected_sha256": "027dd3ef8e203b40d86aa87e57dd18765950583a4c97547e98f42ce4c7286668",
      "file": "evidence/direct-boot/test_policy.py",
      "image_download": false,
      "package_setup": false,
      "payload_hashes_failed": 1,
      "payload_hashes_passed": 10,
      "payload_manifest_entry_count": 11,
      "published_remote_file_count": 13,
      "qemu_boot": false,
      "result": "failed closed at packaged-source verification",
      "reviewed_git_blob_sha1": "7e686d7a79735755eae50d5bbfda80b6534d0496",
      "run_id": 40304386935,
      "tree": "5ffb714609c5b302f85f88e1f042f5d7ed357a37"
    },
    "offline_boot_t3": {
      "apt_plan_bytes": 3476,
      "apt_plan_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "apt_plan_space_summary_limitation": "No transaction space-summary line was present in the saved simulation output.",
      "apt_plan_space_summary_present": false,
      "artifact_bytes": 6608,
      "artifact_entries": 6,
      "artifact_expanded_bytes": 5866,
      "artifact_sha256": "129656affe0e6824a49c0fb67a6b94b644d9597acedf7c3288fd9ccd46fbd287",
      "attempt": 1,
      "commit": "f4a559bbeb3040a4b20eb3725914fc288cc3023a",
      "image_download": false,
      "not_upgraded": 98,
      "only_inst_outside_allowlist": [
        "libcacard0"
      ],
      "package_install": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 11,
      "payload_manifest_entry_count": 11,
      "published_remote_file_count": 13,
      "qemu_boot": false,
      "result": "source checks passed; failed closed at apt-plan allowlist",
      "run_id": 40305901780,
      "simulated_new_packages": 18,
      "tree": "f004570db47ca6ea0374c9295084a1a8e369f28a",
      "upgrades": 0
    },
    "offline_boot_t4": {
      "apt_guard_reached": false,
      "apt_metadata_json_artifact": false,
      "apt_metadata_json_created": false,
      "apt_plan_bytes": 3476,
      "apt_plan_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "artifact_bytes": 6792,
      "artifact_entries": 6,
      "artifact_expanded_bytes": 6050,
      "artifact_sha256": "857dd0a63dee8f35d551d84696dc9e4e834225fd1e2e19d5d10ff5455792f18f",
      "attempt": 1,
      "cgroup_removed_claim": false,
      "claim": "No image/VM boot or G0/E1/E2 evidence; no ENOSPC; no product import.",
      "commit": "dce157f204ba7054af47d4daa21e7bb8f8e7866c",
      "event": "push",
      "failure": "PermissionError [Errno 13] opening root-owned APT administrative lock; metadata collector ran without permission",
      "image_download": false,
      "package_install": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 13,
      "payload_manifest_entry_count": 13,
      "published_remote_file_count": 15,
      "qemu_boot": false,
      "receipt_success": false,
      "result": "failed closed during authenticated APT metadata collection",
      "run_id": 40308232928,
      "tree": "612bba83498f38aa789a629bad4673d659ca29da"
    },
    "offline_boot_t5": {
      "apt_guard_reached": false,
      "apt_metadata_json_artifact": false,
      "apt_metadata_json_created": false,
      "apt_plan_bytes": 3476,
      "apt_plan_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "artifact_bytes": 6792,
      "artifact_entries": 6,
      "artifact_expanded_bytes": 6050,
      "artifact_sha256": "1ea832332c4d5e4a03f56092fe47d6457e152fc9b70051c544387a568aac8cef",
      "attempt": 1,
      "cgroup_removed_claim": false,
      "claim": "No installation/image/VM boot, ENOSPC, product import, G0, E1 or E2 evidence.",
      "commit": "f83b55fe1454f5d5c05d1971742df276f56fc935",
      "event": "push",
      "failure": "RuntimeError: bounded apt-cache exact-version query failed",
      "image_download": false,
      "package_install": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 13,
      "payload_manifest_entry_count": 13,
      "published_remote_file_count": 15,
      "qemu_boot": false,
      "query_stderr_preserved": false,
      "receipt_success": false,
      "result": "failed closed during bounded authenticated apt-cache exact-version metadata query",
      "run_id": 40310058871,
      "tree": "44adbc8ca832d218cc2a65ceff81612ecdf5430b"
    },
    "offline_boot_t6": {
      "apt_guard_reached": false,
      "apt_metadata_failure_json_bytes": 20395,
      "apt_metadata_failure_json_sha256": "2866b2d875000702e590d527dd7fd2a2d0f9efab40f97bf7af953e313339919e",
      "apt_metadata_json_created": false,
      "apt_plan_bytes": 3476,
      "apt_plan_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "artifact_bytes": 27450,
      "artifact_entries": 7,
      "artifact_expanded_bytes": 26566,
      "artifact_sha256": "3d40bbbdfc397b56d0d66e022cec7bbb7cc0189fe98db2f405e9033c65629332",
      "attempt": 1,
      "cgroup_removed_claim": false,
      "claim": "No image/VM boot or G0/E1/E2 evidence; no ENOSPC or product import.",
      "commit": "3636443bfda89ece9beef133e2c36a6ab0dc1326",
      "event": "push",
      "failed_query_count": 18,
      "failure_reasons_each_query": [
        "nonzero-returncode",
        "stdout-empty"
      ],
      "image_download": false,
      "integrity_errors": [],
      "linux_signal_mapping": "Linux signal enum maps 25 to SIGXFSZ; the underlying file or operation is unknown.",
      "package_install": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 13,
      "payload_manifest_entry_count": 13,
      "published_remote_file_count": 15,
      "qemu_boot": false,
      "query_count": 18,
      "receipt_success": false,
      "result": "failed closed in bounded apt-cache batch; apt guard not reached",
      "returncode_each_query": -25,
      "run_id": 40311482230,
      "stderr_bytes_each_query": 0,
      "stdout_bytes_each_query": 0,
      "tree": "f1f0a46ce9152ea57ba6f32716dabec4450dadc0"
    },
    "offline_boot_t7": {
      "apt_guard_reached": false,
      "apt_metadata_failure_json_bytes": 61618,
      "apt_metadata_failure_json_sha256": "efea6248fc74bab17de5c03af1a3eb3d4bb5f3678194ed185478e4ae77749dcd",
      "apt_metadata_json_created": false,
      "apt_plan_bytes": 3476,
      "apt_plan_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "artifact_bytes": 68673,
      "artifact_entries": 7,
      "artifact_expanded_bytes": 67789,
      "artifact_sha256": "0e2ecf9e1980e92c7e736e8cbc51866b7c107955a3c5eb0e18866613162fcfef",
      "attempt": 1,
      "cgroup_removed_claim": false,
      "claim": "No image/VM boot, ENOSPC, product import, G0, E1 or E2 evidence.",
      "commit": "db61463167ed6ea4069e94072f85df855bea7fe3",
      "event": "push",
      "failed_query_count": 18,
      "failure_reason_each_query": [
        "stderr-nonempty"
      ],
      "image_download": false,
      "integrity_errors": [],
      "package_install": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 13,
      "payload_manifest_entry_count": 13,
      "published_remote_file_count": 15,
      "qemu_boot": false,
      "query_count": 18,
      "receipt_success": false,
      "result": "failed closed after apt-cache query diagnostics; apt guard not reached",
      "returncode_each_query": 0,
      "run_id": 40314175423,
      "source_environment": "APT_CONFIG=/dev/null",
      "stderr_each_query": "W: Unable to read /dev/null - RealFileExists (0: Success)",
      "stderr_each_query_bytes": 58,
      "stdout_bytes_total": 27637,
      "stdout_stanzas_nonempty": true,
      "t7_signal_result": "No; T7 queries returned 0. T6 signal mapping and unknown underlying file remain historical only.",
      "tree": "9f70f38b0fe975320b22bc373bb4c56c1e6cb7b4"
    },
    "offline_boot_t8": {
      "actual_keyring_bytes": 3607,
      "actual_keyring_nlink": 1,
      "actual_keyring_sha256": "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
      "actual_keyring_uid_mode": "uid=0,gid=0,mode=0o777",
      "apt_install_command": "returned success; following size checks and inventory command executed; installation transcript was not exported",
      "apt_metadata_json_bytes": 4063,
      "apt_metadata_json_created": true,
      "apt_metadata_json_sha256": "21f87217b491403d791493b36ae9408c80f68a7dcdf9e1c126b112b6041d9882",
      "apt_metadata_records": 18,
      "apt_plan_json_bytes": 6310,
      "apt_plan_json_created": true,
      "apt_plan_json_sha256": "4e968aa47fb7931043d36b06bfbc1887f1f61b4f261115c905a8ba4ad3ed4742",
      "apt_plan_log_bytes": 3476,
      "apt_plan_log_sha256": "85d994e92feb2298682b1b6ea494add82b9f8bbbe7d62d43019882587c96541f",
      "artifact_bytes": 17628,
      "artifact_entries": 8,
      "artifact_expanded_bytes": 16642,
      "artifact_sha256": "825657f078437cf33330df28a6ba4bb830f51580d72b1c0c1280578f8895c722",
      "attempt": 1,
      "cgroup_removed_claim": false,
      "claim": "No authenticated image download, QEMU boot, ENOSPC operation, product import, G0, E1, or E2.",
      "commit": "d65796485d304afa1d1aabddc981f85ff080dd43",
      "event": "push",
      "failure": "RuntimeError: Ubuntu archive keyring owner/mode",
      "failure_step": "host_controller.host_inventory after package installation",
      "image_download": false,
      "keyring_metadata_source": "separate successful read-only K1 inventory artifact; exact path /usr/share/keyrings/ubuntu-archive-keyring.gpg; lstat/stat/canonical-bytes agree; regular file",
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 13,
      "payload_manifest_entry_count": 13,
      "planned_new_packages": 18,
      "published_remote_file_count": 15,
      "qemu_boot": false,
      "receipt_success": false,
      "removed": 0,
      "result": "metadata collection and apt plan accepted; installation command succeeded; final host inventory failed keyring owner/mode check",
      "run_id": 40315202403,
      "tree": "dee439e70bfbd60fbdd8c0405a4bab782a864dae",
      "upgraded": 0
    },
    "offline_boot_t9": {
      "ambiguous_owner": "unknown; no owner inferred",
      "apt_install_status": "command and bounded-output status checks passed; installation transcript was not included in the uploaded bundle",
      "apt_metadata_records": 18,
      "apt_metadata_sha256": "0005e771d37c0dcf4fba7f543762c2b766c528f088f8f1485ff8604e1e5834be",
      "apt_plan_sha256": "bb7a3bd19d70a251e11779b5e4bff21945134bac9eece240ae77e6664826a667",
      "apt_plan_transaction": {
        "newly_installed": 18,
        "not_upgraded": 98,
        "removed": 0,
        "upgraded": 0
      },
      "apt_update_status": "passed; execution advanced to authenticated plan",
      "artifact_bytes": 19542,
      "artifact_entries": 10,
      "artifact_expanded_bytes": 18288,
      "artifact_sha256": "052571b16651c336757d90360baa3019fe0984aaa2c3ca4e89967761f0f98d7b",
      "attempt": 1,
      "cgroup_removed": false,
      "claim": "No image download, VM/boot, ENOSPC, product import, G0, E1 or E2.",
      "commit": "1a7ff5afc5720157f8c57daa5cbd4d3f49bb3370",
      "estimated_new_bytes": 96927744,
      "event": "push",
      "failure": "RuntimeError: ambiguous package ownership: /lib64/ld-linux-x86-64.so.2",
      "failure_phase": "host inventory library package-ownership mapping",
      "image_authentication": false,
      "image_download": false,
      "job_conclusion": "failure",
      "job_id": 121564955048,
      "keyring": {
        "accepted_signer": "F6ECB3762474EDA9D21B7022871920D1991BC93C!",
        "bytes": 3607,
        "cleanup_directory_identity_match": true,
        "cleanup_file_identity_match": true,
        "cleanup_hash_match": true,
        "cleanup_status": "removed",
        "sha256": "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
        "staged_directory_mode": "0755",
        "staged_file_mode": "0444"
      },
      "measurement_success": false,
      "payload_hash_entries_failed": 0,
      "payload_hash_entries_passed": 17,
      "payload_manifest_entry_count": 17,
      "published_remote_file_count": 19,
      "qemu_boot": false,
      "receipt_success": false,
      "run_id": 40320808591,
      "tree": "b2698e54c5455392210978b086327c0442c8958d",
      "workflow": "ENOSPC precursor - one offline direct QEMU boot"
    },
    "pid_role_probe": "separate minimal classification follow-up required; no UI process-role inference",
    "source_count_convention": {
      "T10": {
        "note": "20 total published files are 18 payload hash manifest entries plus the payload hash manifest and workflow; all 18 payload checks passed.",
        "payload_hash_manifest_entries": 18,
        "published_remote_file_count": 20
      },
      "T1_T3": {
        "note": "13 total files include the workflow and payload hash manifest; T1 manifest has 11 entries and its retained run summary says verification passed, while individual raw hash-check lines are unavailable; T2 log shows 10/11 OK and one failed; T3 log shows 11/11 OK.",
        "payload_hash_manifest_entries": 11,
        "published_remote_file_count": 13
      },
      "T4_T8": {
        "note": "15 total files are 13 payload entries plus the payload hash manifest and workflow",
        "payload_hash_manifest_entries": 13,
        "published_remote_file_count": 15
      },
      "T9": {
        "note": "19 total files are 17 payload entries plus the payload hash manifest and workflow",
        "payload_hash_manifest_entries": 17,
        "published_remote_file_count": 19
      }
    },
    "source_keyring_bootstrap_proposal": {
      "activation_review_sha256": "9e34bd814057a6188a27035fc5f9a4c5a085a026096da5c6c8428cb1fc95464c",
      "claim": "The keyring bootstrap worked in T9 and its cleanup receipt reports exact-object removal. T9 did not reach canonical image download or QEMU boot; no ENOSPC/G0/E1/E2 evidence.",
      "declared_dsc_sha256": "c71c8e5a1dd5e8ef682b7104645a88f0bc9eeb9380bf64288adcf78f40bcf68b",
      "declared_upstream_tar_bytes": 20236,
      "declared_upstream_tar_sha256": "aecd455ae15561371d6e454f121f079f0641d5e1b579a5563a2bc363fc74aa2e",
      "implementation_review_decision": "CLEAR for one future activation staging step; 37/37 focused tests passed; no runtime result implied",
      "implementation_review_sha256": "749a0b5a78d8a09d7ed4db0e6032628828b05317c28d40c986030852f0f9727e",
      "independent_review_sha256": "2eab08852ef77ad8c32098b0b112b510e7e1fca47d8b1ac6239fc365d09646f8",
      "keyring_permissions_design": "readable by the _apt sandbox without write permission; proposal describes private staging, identity checks, and exact cleanup",
      "limitation": "The source package descriptor developer signature was not independently anchored; proposal records this limitation.",
      "proposal_scope": "bounded source package and keyring pin for review; K1 metadata is an observation, not a trust anchor",
      "review_decision": "CLEAR for design and source pin only; no activation or package/image/VM operation is authorized by that review",
      "reviewed_accepted_primary_signer": "F6ECB3762474EDA9D21B7022871920D1991BC93C!",
      "source_manifest_description": "SHA-256 of the final five-entry source-hashes.txt manifest, independently checked by the source reviewer",
      "source_manifest_sha256": "41374b28c8a7617d3a9edf86299757dcf26c71e0a9291eed0c5743198ea95966",
      "source_pin_review_sha256": "2eab08852ef77ad8c32098b0b112b510e7e1fca47d8b1ac6239fc365d09646f8",
      "status": "official Ubuntu source pin/design and V11 implementation independently reviewed CLEAR; V11 used for T9, which stopped at host inventory before image or boot",
      "target_keyring_sha256": "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
      "upstream_package": "ubuntu-keyring",
      "upstream_version": "2023.11.28.1"
    },
    "source_keyring_metadata_experiment": {
      "artifact_bytes": 3307,
      "artifact_sha256": "97b53c79b6df547431e9dab3742d3c9251d2823151e38b13046e3a92ebb25583",
      "attempt": 1,
      "commit": "24f487191baaa9883c05209f0f5427c443a540d2",
      "inventory_closure_complete": false,
      "inventory_runnable": false,
      "job": "inventory",
      "job_conclusion": "success",
      "keyring": {
        "bytes": 3607,
        "gid": 0,
        "mode": "0o777",
        "nlink": 1,
        "path": "/usr/share/keyrings/ubuntu-archive-keyring.gpg",
        "sha256": "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
        "type": "regular",
        "uid": 0
      },
      "keyring_ancestors": [
        {
          "gid": 0,
          "mode": "0o777",
          "nlink": 2,
          "path": "/usr/share/keyrings",
          "size": 4096,
          "type": "directory",
          "uid": 0
        },
        {
          "gid": 0,
          "mode": "0o777",
          "nlink": 209,
          "path": "/usr/share",
          "size": 12288,
          "type": "directory",
          "uid": 0
        }
      ],
      "qemu_img": "not found in PATH",
      "qemu_system_x86_64": "not found in PATH",
      "run_id": 40316538232,
      "same_head_run_snapshot": "inventory workflow succeeded; collateral Core tests were still in progress; no direct-boot workflow run observed for this head",
      "scope": "read-only host observation only; no apt action, image action, VM, direct boot, G0, E1 or E2",
      "status": "completed read-only K1 inventory; at the exact K1 head, no direct-boot workflow run was observed",
      "tree": "82fb2910ad8a85880a33b3b999df452f5517963d"
    },
    "source_loader_metadata_diagnostic": {
      "attempt": 1,
      "canonical_target": {
        "architecture": "amd64",
        "bytes": 236616,
        "dpkg_query_returncode": 0,
        "dpkg_query_stdout": "libc6:amd64: /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2\n",
        "dpkg_query_stdout_bytes": 60,
        "dpkg_query_stdout_truncated": false,
        "mode": "0o755",
        "owner": "root:root",
        "package": "libc6:amd64",
        "path": "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
        "sha256": "c20a2dc8917c755f02b94049356320fe1f62ac7d9f8994731f807d9df39302da",
        "type": "regular",
        "version": "2.39-0ubuntu8.9"
      },
      "closure_complete": false,
      "commit": "4ae39425e37152aac2fc6de5b1b485b9eabee882",
      "g0_e1_e2": 0,
      "image_download": false,
      "kernel": "6.17.0-1022-azure",
      "package_install": false,
      "qemu_img": "not found in PATH",
      "qemu_system_x86_64": "not found in PATH",
      "requested_alias": {
        "direct_owner": null,
        "dpkg_query_returncode": 0,
        "dpkg_query_stdout": "diversion by libc6 from: /lib64/ld-linux-x86-64.so.2\ndiversion by libc6 to: /lib64/ld-linux-x86-64.so.2.usr-is-merged\n",
        "dpkg_query_stdout_bytes": 118,
        "dpkg_query_stdout_truncated": false,
        "lstat_bytes": 44,
        "lstat_mode": "0o777",
        "lstat_owner": "root:root",
        "lstat_type": "symlink",
        "path": "/lib64/ld-linux-x86-64.so.2",
        "target": "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
      },
      "run_id": 40322816845,
      "runnable": false,
      "runner_image": "Ubuntu 24.04.5 LTS",
      "runner_image_os": "ubuntu24",
      "runner_image_version": "20261023.334.3",
      "scope": "Read-only measurement of the requested loader alias and canonical target, including bounded dpkg-query -S output for both paths.",
      "scope_limit": "This later read-only measurement does not rewrite T9, which failed at alias-only ownership mapping. It does not establish that T9 had the same runner image version.",
      "status": "K2 completed successfully as an initial hosted inventory on its exact push commit; it did not modify the host or start direct boot.",
      "tree": "b67bac27c7782600cc46c5daa1c321a2beb82959",
      "vm_or_boot": false
    },
    "source_proposal_v10": {
      "observed_failure": "host inventory keyring owner/mode check; actual uid/mode not retained",
      "scope": "removed the explicit APT_CONFIG=/dev/null setting; query/authentication bounds remain active",
      "status": "used for T8 attempt; metadata, apt plan, guard and installation command succeeded before final inventory error"
    },
    "source_proposal_v12": {
      "cgroup_review_limit": "The kernel rule is established: non-root migration requires write access to both destination cgroup.procs and source/destination common ancestor cgroup.procs. Current source assumes common-ancestor permission without recording or verifying it. Parent cgroup.procs permission was not measured, so no EACCES result is claimed or observed.",
      "focused_tests_failed": 0,
      "focused_tests_passed": 49,
      "runtime_result": "T10 attempt 1 failed closed before image download and before cgroup/QEMU/guest setup; no runtime behavior was exercised.",
      "scope": "K2 loader-alias/canonical fallback plus the reviewed bounded direct-boot source and privileged attachment of one paused identity-verified child. T10 passed source checks but failed host inventory on a different symlink alias after package installation.",
      "separate_cgroup_review_brief_sha256": "7cda1a394a96800515b82f72563d9a23405b3e494fb3bae0671c028591ed5f15",
      "source_review": "not yet complete",
      "source_review_sha256": "c6f1824a1a60063235f4b3dd6d06b86a9c659ad7ec006b52b1406dd3412894b2",
      "status": "independently reviewed CLEAR; 49 focused source tests passed; used for T10; no source or test failure recorded"
    },
    "source_proposal_v13": {
      "activation": false,
      "activation_status": "activation held before T11 by source-level kernel-compatibility finding; no T11 run",
      "independent_review": "CLEAR for exact libaio no-match/canonical parser correction, 51 focused tests; does not clear cgroup-parent design",
      "kernel_compatibility_finding_sha256": "04c908fde667306dcd5079e8f12e277894ad35fa7d6b567ae2d0327718fc3da2",
      "runtime_run": null,
      "scope": "For the exact libaio symlink failure, retain the requested-path dpkg-query result. If it returns no path/no direct owner and a distinct resolved canonical path was measured, query that canonical path separately and retain both bounded outputs. Do not infer or guess an owner; accept only an unambiguous direct canonical-path owner.",
      "source_changes": null,
      "status": "under development; source review not complete; not activated; no T11 run"
    },
    "source_proposal_v14": {
      "activation_status": "awaiting fresh all-22-file activation stage; author staging on hold pending report and new base",
      "author_reported_focused_tests": 55,
      "cgroup_compatibility_analysis_sha256": "04c908fde667306dcd5079e8f12e277894ad35fa7d6b567ae2d0327718fc3da2",
      "corrective_scope": "use fixed /sys/fs/cgroup as control parent; read existing controller state only; separately record helper source-cgroup identity; create only one nonce leaf; root helper attaches one paused identity-verified child",
      "guardrails": [
        "no global cgroup writes",
        "no ancestor chmod/chown or permission changes",
        "no root QEMU",
        "no migration of other processes"
      ],
      "independent_focused_tests": 55,
      "independent_review_sha256": "1312319e88fb1949965b5807342381db95f6c1f3208c8ca3e3ebfe22d4c02222",
      "payload_manifest_sha256": "138f1c038667441ff08f1d2be179dd56d11f2189121d73599a3b7bb7666351b3",
      "qualification_limit": "Runtime and hosted topology remain unobserved; independent source clearance does not qualify a hosted run.",
      "source_manifest_sha256": "ef3e61676a7affc329bd1656bab9943cb38940e3b01260a714594a43f85229b6",
      "status": "independent source review CLEAR; source-only; disabled; no T11"
    },
    "source_proposal_v3": {
      "review_scope": "The T3 plan lacked its expected transaction space summary; this proposal was not the source used by T4 and should not be regenerated.",
      "scope": "exact libcacard0 allowlist entry plus bounded authenticated exact-version Installed-Size metadata cap",
      "status": "superseded; known incomplete after T3; do not generate or activate"
    },
    "source_proposal_v4": {
      "observed_failure": "PermissionError [Errno 13] reading the root-owned APT administrative lock",
      "scope": "T4 source revision with authenticated APT metadata collection",
      "status": "used for T4 attempt; failed closed before apt guard/install"
    },
    "source_proposal_v5": {
      "review_scope": "Historical proposal only; superseded before a hosted attempt.",
      "scope": "resolve authenticated APT metadata collection around the root-owned administrative lock while retaining bounded trust and validation",
      "status": "blocked; 0600-only approach; not activated or run"
    },
    "source_proposal_v6": {
      "observed_failure": "RuntimeError: bounded apt-cache exact-version query failed; query stderr was not retained; cause unknown",
      "scope": "T5 source revision with bounded authenticated exact-version apt-cache metadata query",
      "status": "used for T5 attempt; failed closed before apt guard/install"
    },
    "source_proposal_v7": {
      "review_scope": "Bounded diagnostics proposal lineage; T6 used v8 source.",
      "scope": "retain bounded apt-cache exact-version query failure diagnostics so the actual failure is inspectable; do not ignore stderr or guess a fix",
      "status": "diagnostics proposal lineage; not separately activated or run, superseded by v8"
    },
    "source_proposal_v8": {
      "observed_result": "18/18 returned -25, with stdout/stderr empty; Linux signal enum maps 25 to SIGXFSZ; underlying file/operation unknown",
      "scope": "bounded apt-cache query diagnostics preserving return codes and bounded output",
      "status": "used for T6 attempt; failed with bounded query SIGXFSZ results as recorded"
    },
    "source_proposal_v9": {
      "observed_result": "18 queries returned 0 with valid stdout; every query emitted the same 58-byte APT_CONFIG=/dev/null warning; stderr-nonempty guard rejected each",
      "scope": "bounded concurrent output diagnostics for authenticated apt-cache queries",
      "status": "used for T7 attempt; failed closed on nonempty apt-cache stderr",
      "underlying_t6_sigxfsz_file": "unknown; no T7 SIGXFSZ result"
    },
    "t1_t2_t3_t4_t5_t6_t7_stopped_before_package_install": true,
    "t1_through_t10_no_boot": true,
    "t1_through_t8_no_boot": true,
    "t1_through_t9_no_boot": true
  },
  "historical_v11": {
    "accepted_checkpoints": 3,
    "failure": "owned window became unviewable during Escape key-release path",
    "forced_cleanup": true,
    "status": "failed partial"
  },
  "native_v13": {
    "app_data_mode": "0755",
    "checkpoints": [
      "unconfigured",
      "enabled_initial_verified",
      "first_explicit_verified",
      "hidden",
      "second_explicit_verified",
      "stopped",
      "reopened_stopped"
    ],
    "interval_seconds": 86400,
    "locator_root_mode": "0700",
    "new_empty_private_locks": 3,
    "notice_evidence": {
      "limit": "supports presentation within recorded limits; does not establish user attention or universal compositor visibility",
      "native_notice_only_captures": true,
      "qt_event_gate_painted_exposed_seconds_minimum": 5,
      "sampled_focus_ids": 105
    },
    "notice_minimum_seconds": 5,
    "package_counts": [
      null,
      1,
      2,
      2,
      3,
      3,
      3
    ],
    "packages": [
      {
        "bytes": 237971,
        "sequence": 1,
        "sha256": "f17eb38edefbccd917ce96b58bc60dfa8fa4adf25942acc69c0c37de1ef316fa"
      },
      {
        "bytes": 237971,
        "sequence": 2,
        "sha256": "f2eae5850f3d411280d9bf0e7fce4e5cbc14be770d0c95731c485c98c08cd55d"
      },
      {
        "bytes": 237971,
        "sequence": 3,
        "sha256": "cd8fd654fbe1f29183cb32f55eff9a839cf4cb61e547e9bd02d21324c11b8bfb"
      }
    ],
    "process": {
      "adopted_child_per_launch": 1,
      "adopted_child_role": "UNKNOWN",
      "adopted_child_wait_status": 0,
      "forced": false,
      "groups_gone": true,
      "launches": 2,
      "natural_exit_status": 0,
      "qt_thread_join_proven": false,
      "signals": 0
    },
    "protected_outputs_unchanged": 15,
    "registry_after": 285,
    "registry_before": 282,
    "retention_enabled": false,
    "status": "accepted scoped generated-fixture UI and persistence case",
    "stopped_state_persisted_after_reopen": true
  },
  "pr": {
    "checks_success": 30,
    "checks_total": 30,
    "draft": true,
    "head": "c2149e51b4ef95e125da9793971b79cd603f596c",
    "merged": false,
    "number": 25,
    "state": "open",
    "tree": "4ebcd668c5aea42ebcf5dbcbbce02ba41a930c03"
  },
  "release": {
    "fr_recovery_003": "Partial",
    "not_established": [
      "restore/recovery correctness",
      "retention deletion",
      "arbitrary storage behavior",
      "physical-NVMe durability",
      "ENOSPC behavior"
    ],
    "phase1": "held",
    "release": "held"
  },
  "schema": "locator-bootstrap-public-evidence-v1",
  "source": {
    "author_reported_focused_passes": 79,
    "commit": "892f75e174de13290143acc127bbb33087e3ba6a",
    "review": "accepted",
    "reviewed_files": 6,
    "reviewed_code_file_sha256": [
      "2389e49248d1d258478749a40622a0393ebf7d2b859bb406e747b5cb13a922b0",
      "ea98ab49dabc375faa1c75089690e69254dd0e3add32451b8af278c250389e25",
      "4f920c958e3867301cc2d0c6cac98802c8733858b2099e287c263ac419d6a5b0",
      "803ced2b6f07a000ab1f64b861c1080bd4fe4cc259606b8d04ad7f04d234e513",
      "4de411f4751875db76bc499c1d0cc255beeaf5cc3f78c4e1e3283a235ce2ce34",
      "0bafe73ef27e820b3985a624ccdc7cd41e8989de706214a047eefd80777eefac"
    ],
    "tracked_files": 347,
    "tree": "4ebcd668c5aea42ebcf5dbcbbce02ba41a930c03"
  }
}
```

</details>

### Historical PR body (preserved verbatim)

The following is the prior body as fetched before preparing this candidate. It is retained as history. Current status above supersedes earlier progress statements; historical failures and unavailable evidence remain part of the record.

## Latest desktop diagnostic qualification (2026-10-26)

The desktop warning and completion notices are now implemented and independently reviewed in the acceptance harness. Thirteen focused headless checks passed. A native notice-only run displayed each notice for more than five seconds; all 105 sampled active-window IDs remained unchanged. Own-window captures confirmed that the text fits. These observations do not prove user attention, compositor visibility through every possible overlay, or focus behavior between samples.

A subsequent frozen-dialog diagnostic completed with the warning before launch and the completion notice after normal cleanup. Independent review verified 498 requested/received native events in exact order, no unsolicited events, 2,056 complete durable observations, exact full short/long test strings, and two Enable callbacks plus one Refresh callback. The fake-controller callback records matched the accepted interpreted diagnostic. All three exact compiled PySide method identities were qualified without relaxing input checks. The original application artifact was not rebuilt.

The following real packaged-app attempt reached Enable but suspended with `Recovery requires a user-owned private destination directory`. It was closed normally, without forced termination, and the stopped notice completed. Independent review confirmed no saved schedule or package, unchanged protected files, and only the three expected empty admission locks. Read-only analysis found that the generated application-data parent was mode 0755 while locator bootstrap requires a private parent. Default-profile creation has the same source-level risk and is under review; the failed fixture remains preserved. No permission repair or validator relaxation has been applied.

This supersedes earlier statements that the frozen diagnostic was still pending. It does **not** qualify real schedule persistence, snapshot creation, recovery, or identify a Nuitka/product defect. Earlier failed attempts remain preserved. During the preceding fake-controller diagnostic, the recorded protected output files and admission registry remained unchanged. Real packaged acceptance and actual ENOSPC evidence remain outstanding; FR-RECOVERY-003 remains Partial. The inventory workflow proposal is still unpublished and needs its initial branch trigger corrected before use. No merge or deployed-binary replacement is included.

---

## Summary

Adds opt-in, app-running local metadata snapshots for an admitted physical catalog, with persisted schedule configuration, truthful last-result/status display, and bounded managed retention. Scheduling runs only while the application is open; no background service is installed. Snapshot packages use the existing consistent-backup and verification path. The feature stays within local metadata recovery and the existing storage-adapter policy; it does not back up media or automatically restore/relink. Linux/native evidence is limited to generated fixtures and named cases, not arbitrary writable, network, synchronized, or removable storage, or complete retention-pruning qualification.

Current source is local `177b209658da4ec4a6b7bc000a231264f58c58ea` and published head `7af81043488ab15efc6df6ae9aa8af00fddae886`, both tree `ff026e1d840ee66354ec1d97f567d61be8db5aad`. The head and previously recorded 30/30 exact-head CI results are unchanged. PR 25 remains draft and unmerged.

## Bounded evidence

- Exact-head hosted CI remains 30/30 green, including Windows: 502 Core tests with 144 skips on each of Python 3.11 and 3.13; Windows Qt had 502 Core tests (85 skips), 192 prototype tests (6 skips), eight frozen smoke checks, and ten named SnapshotWindow cases passed. Source CI does not establish desktop or full recovery acceptance.
- Focused refresh/monotonic-authority regressions: 38 offscreen passes. Other accepted bounded evidence includes the delayed same-process consumer case, W2-A's four offscreen window/settings/manual-backup/reopen cases, and L7's seven Linux/offscreen source/location cases. These remain case-limited; L7 does not qualify retention pruning or negative scheduled-control cases.
- T1 v3 is accepted only for its closed accelerated/injected timer scope. T2 is accepted for its two fresh completed-status clock cases and durable supplement: the overdue case produced one backup and one sequence increment; the backward-clock case produced no backup or increment and retained about 900 seconds, with physical-catalog/CAS state preserved. T3 is accepted narrowly for real 900-second timer runtime and natural role cleanup. Its original aggregate **failed** the 64 MiB publication bound, and the original instant post-snapshot is **unavailable** and was not reconstructed. A later freeze comparison does not repair either result. No physical-NVMe durability claim is made.

## Desktop and input evidence

The compiled artifact was launched in desktop attempts, but scheduled-snapshot desktop acceptance remains **failed**. V5 stopped at a prelaunch namespace guard; v6 intentionally aborted its title harness before snapshot controls; v7 did not save the intended schedule and required forced exact-owned TERM cleanup. V8 again did not save the schedule: only the unconfigured checkpoint passed. Root correctly declined enabled-state validation after the captured UI showed no saved schedule. V8 then closed normally through its owned window path and exited without forced signals, but internal Qt/owner/worker release was not proven. No snapshot package was created, and no product or Nuitka defect is established. The literal Refreshed saved settings feedback, actual clicked receiver/slot entry, and full entered field value are unconfirmed/unknown.

The legacy input feasibility probe has a narrowly accepted plain-Qt attempt: all 180 sent key/button events matched the recorded actual Qt input, with two sample entries, two Enable responses, one Refresh response, one Close response, and natural close. This is **input feasibility only**, not frozen-product or snapshot acceptance. Legacy and translated coordinates matched in that window; the proposed coordinate cause was not reproduced and no coordinate-fix claim is supported. A preceding attempt failed its focus guard after 92 exact events; an earlier confounded attempt failed before any Root command or capture, with unrequested native key/text events of unknown origin and forced cleanup. No hardware/user/server attribution or historical cause for v7 is established. The user confirmed the unsolicited input stopped and the session was idle, clearing the prior input hold; product acceptance remains failed.

Three further authorized empty admission locks were added during v8; the audited production registry count is 276. Prior entries, catalog/source/runtime state, and all 15 protected deployed outputs remained unchanged. No deployed output was replaced.

## Remaining gates

FR-RECOVERY-003 remains **Partial**. The mandatory real ENOSPC case is uncovered. G0 v2 is static source review only; G0/E1/E2 actual acceptance counts remain zero. The new base-boot measurement proposal is source-only and disabled, host pins are null, and integration is unfinished; official image bytes were not downloaded and the inspection VM was not run. A fresh diagnostic preserving the original product settings class with pure callbacks and full-field/native Qt observers is pending source review. Its compile-only proposal has not been compiled or launched; independent review requires bounded observation persistence and a stricter cleanup-success predicate before compile GO. No further product desktop retry is qualified. No full-feature, merge, release, deployment, or physical-NVMe durability claim is made.
