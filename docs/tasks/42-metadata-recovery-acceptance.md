# Task 42 — verified metadata recovery acceptance

In progress; acceptance held. Owner: Luna. Root owns release/stage transitions; Task 41 owns the recovery design and Core implementation, and Task 43 provides independent review.

Read [Task 41](41-metadata-recovery-implementation.md) after it is authored, [the acceptance protocol](../metadata-recovery-acceptance.md), SDD v0.2 §§5.3, 10.4, 16.3, 21.2, and 22.3, and the 129-row requirements tracker. This task prepares acceptance for one narrow metadata-only verified backup and isolated restore. It does not implement recovery and makes no acceptance claim.

## Checkpoint

The 13 October 2026 gallery-filter checkpoint is preserved: PR21 merged as `a42b213ec600db5cab2a55281533dd21ac53a584`, tree `d7f3f411237edc490d5351efb791a7c2403c5fb4`. Task 39 and its private wrapper evidence record the exact-head 30-check audit and deployed-output disposition. Audit of the merged-main Core run is a separate record and must not be conflated with those results. Recovery has frozen Core regression evidence, focused Qt regression evidence, Task 43 clearance for the exact Qt integration revision, and a reviewed full Qt discovery checkpoint of 178/178. The earlier 177-test timeout remains a retained historical failure and is superseded for current Qt regression by the later reviewed-source run; it is not erased. No native or hosted-platform acceptance result is established, and no recovery acceptance result is claimed.

Task 43 cleared the reviewed design SHA-256 `0fa4b6a536021e681bc4fe51670552eb468a5076b208f5406c560bc590bf345e` and Task 41 SHA-256 `d9a9b2bb0a7536d49b4adee48dc9ea604926a7aaa05b08b235465f5c588bede1` for the current Core implementation. Its reviewed implementation/test hashes and limitations are recorded in [Task 43](43-metadata-recovery-review.md). The private receipt `core-final-receipt.json` has SHA-256 `d3ca7132254c15bad93dfbf6b194fbdf2c85a7439eee110faec8aa8b58777847`: focused Core tests passed 89/89 and full Core discovery passed 293/293, both with zero skips; direct exits were 0. Python was 3.14.7 on Linux 7.2.10-200.nobara.fc44.x86_64 with `QT_QPA_PLATFORM=offscreen`. Before/after source SHA-256 manifests and stat comparisons matched; `git diff --check` exited 0. This proves Core regression and review clearance, not Task 42 snapshot/restore acceptance. Qt integration and the full Qt regression are also cleared at the current checkpoint; native, hosted-platform, privacy, and release gates remain held.

On 15 October, the explicitly authorized portability follow-up changed only
`tests/test_recovery.py` test code. Its final SHA-256 is
`c17c05b59f15c4e80f7c403952a3bc8c2cdb33a15901fd53677b1ece9fb942eb`.
The concurrency case now accepts only the exact bounded starvation refusal or
SQLite `database is locked` refusal, and checks no package/staging residue,
worker reaping, bounded exit, and generated-media byte/stat immutability on
refusal or success; the successful snapshot consistency assertions remain.
The observed earlier run returned `OperationalError: database is locked` while
the test oracle admitted only starvation, so an unchanged green rerun was not
used to dismiss it. The updated focused 22-test run passed in 4.312 seconds,
exit 0, with no skips. Its private raw log, direct exit file, and matching
pre/post source hashes are under
private wrapper evidence store; the raw-log basename is `recovery-portability-20261015.log`. The
raw-log SHA-256 is
`2f01d86cfa1e1e2678da651a3a29add41a73a186e6fdd0965a806938b30a7bf6`. This is
test-only portability/concurrency-oracle evidence, not acceptance of online
snapshot behavior. Task 43 cleared this exact test amendment. No CI, native,
hosted-platform, or publication run was made by this portability check.

The official Qt discovery command was run once on 15 October with
`QT_QPA_PLATFORM=offscreen` and `PYTHONFAULTHANDLER=1`. It ran 177 tests in
42.814 seconds: 176 passed, one failed, zero skipped; direct exit was 1. The
only failure was
`GalleryWorkflowTests.test_launcher_creates_library_and_source_dialog_sets_policy`,
which timed out after 5 seconds waiting for source addition and policy
publication. At timeout the test reported generation 3, count 0, an actionable
token, no pending mutation, and a still-running gateway. The traceback was a
bounded readiness assertion in `prototypes/qt/tests/test_gallery_workflow.py`
through `gallery_wait.py`; no other test traceback was present. The private
raw log is `qt-discovery-20261015-20261015T100734Z.log`
(SHA-256 `cd26dafe847b3379b797501da881d417a89b2b4957042d328725a101e33bd76d`);
its direct-exit file records `1`. The 57-file pre/post Python-source
manifests are identical (manifest SHA-256
`c40a11ed3de3570afdb5e0ffea946c6d8b98eedd505f8ea6c1d3ccf417194d2d`). This is
a completed failed regression run, not an acceptance result. It remains
preserved as a historical failed checkpoint; it was not dismissed by an
unchanged rerun.

After the reviewed source/package correction, the official Qt discovery command
was run once more with the same interpreter and environment. It ran 178 tests
in 37.353 seconds: 178 passed, zero failed, zero skipped; direct exit was 0.
The actual command process was polled to completion through its exec session.
The private log is
`qt-discovery-20261015T1018Z.log`
(SHA-256 `4d7c8961bdadc05e283150c1058c4a086077cb3ad858a863b16384628f48896a`);
its direct-exit file records `0`. Pre/post manifests of the same 57 Python
inputs are identical (manifest SHA-256
`7065665b12bd636571ac3cea69f10eb29f6926bd4873496ca7b6859096eff8f6`). No
failure, error, skip, warning, or callback traceback was present. The focused
Qt regression gate is green at this reviewed checkpoint. This remains
regression evidence only: it does not establish native desktop acceptance,
source no-read proof, hosted-platform acceptance, or release readiness.

On the published head `0667199f759ce8c0ce304472e1efca661234f148`, the frozen
local build command exited 0. Its unsigned offscreen artifact is 51,199,488
bytes with SHA-256
`eb66e05e21045734426a04fcac1b7279dbc0fc1c5525fc88f02ab32d555a377b`. The
private build receipt basename is `root-build-receipt.json` (SHA-256
`94d4fa9ac5bbed4b10a2842460b6627a2645cdff8e27b67ff26e31ba802529d4`); its
private raw-log digest is
`81aaff788f2ba6a1fcb6d02b4be63a1727ef37681629cc73c1c5f5980402ce68`. Seven
preserved smokes and the new spawned recovery-worker smoke passed. All 281
shadow inventory files and runtime source inputs matched; all 15 deployed
outputs remained unchanged. The artifact was not deployed. Independent review
cleared this exact build receipt. This is local build/smoke evidence only.

The read-only exact-head hosted audit completed for all four workflow runs and
all 30 checks on `0667199f759ce8c0ce304472e1efca661234f148`: Core push, Core
PR, Qt PR, and Tauri PR. **29 checks succeeded and one failed.** Core push,
Core PR, and Tauri PR were green; the Qt PR workflow failed in its macOS
packaging smoke. No workflow was rerun.

All four Windows Core jobs (push and PR, Python 3.11 and 3.13) ran 296
tests each: 279 passed and 17 skipped. Twelve recovery-publication tests named in the
public results record require the reviewed Linux PCIe NVMe adapter. The other
five named skips cover POSIX mountinfo spelling, effective-ID/`O_DIRECTORY`
permissions, FIFO creation, POSIX resource controls, and a host-denied
generated-root rename while a scan handle was open. The Windows Qt job ran the same Core suite (296: 279 passed, 17 skipped) and its Qt suite (178: 172 passed, 6 skipped); its six named Qt
limits cover POSIX byte-stream injection, three Windows-denied atomic
replacements of open SQLite files, native Linux-adapter backup/restore, and
POSIX per-source enable semantics. Catalog generation and unsigned artifact
packaging succeeded in that Windows job.

The macOS Qt Core suite ran 296 tests (284 passed, 12 skipped) and its Qt suite ran
178 tests (177 passed, one Linux-adapter skip). The subsequent packaging command created
the app, then `frozen_recovery_smoke` raised
`ValueError: Frozen recovery worker smoke failed` at `package.py:314`, called
from `main` at line 584; the job exited 1. This failure is unresolved and keeps
the Qt workflow red. Tauri's PR run succeeded. These are hosted CI results,
not recovery acceptance or native desktop evidence.

The combined private run/check snapshot has SHA-256
`bb12a1152c5b5dff6ca0125658a19ed35929a43ce367efca11216abcbcf9ba97`; the
private job snapshot has SHA-256
`55ecf3183e2773bab2f227d81f5c459eadbeec3b36c51815e538f477985b2306`. Full
job logs remain private. Their digests are in the sanitized results JSON and
private CI receipt; the macOS failure log digest is
`ed4d2edba3e9d7cefda8680030ea674121e6969e3dcaa749159f8c6ab8a45eed`.

The first visible native attempt ran on exact head
`0667199f759ce8c0ce304472e1efca661234f148` in the unlocked Wayland session.
Its reviewed driver SHA-256 was
`1daf7f0a8da3404601e6c544f3f019c8dba478563925b1a5d23368d15af95fa4`; the
fixture-manifest SHA-256 was
`e60a939a784661b233a0f77cc1859bc56eb5bba464f319af58fcbe6007e0cd6a`. The
driver failed before N01 because it called synchronous `row_for_asset` on the
asynchronous gallery and raised `RuntimeError: Use request_rank for an async
gallery`; direct exit was 1 and no native cases were observed. The private
receipt status is `cleanup_uncertain`: the process returned, but the final
live-window close returned false. Root's post-failure check found all 12
generated-fixture files unchanged by hash and physical metadata. This is a
mutation check only and does not prove absence of reads. Private evidence
digests: raw log `304389812da6fcf01a18981b0f323db65501bce674d0d0566a8d8ca6b8b2771d`,
receipt `a2e1e523433d06abcd52d54d89a0539154f04c51d2a7e45fb9bfbe1e5c3b5122`,
and preservation record
`0aec99cedba5467643b4ab78a54b30c7a23bd19ef19137e220f8f893ab08a9ed`. A
corrected asynchronous driver and a fresh attempt remain pending independent
review; N01–N14 remain pending with zero cases accepted.

## Preservation audit and change boundary

The protected baseline is the private wrapper artifact
`metadata-recovery-baseline-2026-10-13.json` (SHA-256 `e0e791263f14963e4bbc27b1c5e9db247a157aa6d3927b7f8b6bf9e2a6657528`), captured from PR21 merge
`a42b213ec600db5cab2a55281533dd21ac53a584` / tree
`d7f3f411237edc490d5351efb791a7c2403c5fb4`. It records the 270 tracked
paths and the 15 deployed outputs. Before and after recovery work, compare
every baseline path for SHA-256, byte length, mode, and nanosecond mtime;
compare deployed output bytes, mode, and time separately. The baseline and
prior gallery-filter evidence are read-only inputs.

The frozen Core implementation consists of the reviewed paths recorded in
Task 43 and the private Core receipt. Root has explicitly released the Qt
integration scope for this recovery slice: `prototypes/qt/app.py`, new
`prototypes/qt/recovery_qt.py`, `prototypes/qt/preview.py`,
`prototypes/qt/comparison.py`, `prototypes/qt/gallery_filters.py`,
`prototypes/qt/gallery_operations.py`, `prototypes/qt/cached_preview.py`,
`prototypes/qt/README.md`, and recovery-specific Qt tests as needed. Keep the
frozen design and eight reviewed Core runtime files byte-for-byte frozen.
The only authorized Core-baseline change is the reviewed test-only
portability/concurrency-oracle revision to `tests/test_recovery.py`; it does
not unfreeze Core runtime. Any additional product path must be justified and
included in the Qt-inclusive frozen input inventory. Do not
edit workflows, generated outputs, gallery-filter evidence, the baseline, or
unrelated requirements and orchestration records as part of Task 42. Root
owns Task 00 and tracker transitions.

The baseline audit found all 270 tracked paths present and 10 changed: six
approved Core files, the two Qt guard files `prototypes/qt/comparison.py` and
`prototypes/qt/preview.py` now covered by Root's explicit Qt release, and the
tracker and Task 00 orchestration files owned by Root. All 15 deployed outputs match the baseline
SHA-256, byte length, mode, and nanosecond mtime exactly. The preservation
comparison must continue to report all changed paths and the expected
recovery-path set. For each changed baseline path, record whether it is within
this allowlist and its purpose. Confirm no baseline file was removed or
replaced unexpectedly, no deployed output changed, and no gallery-filter
acceptance receipt was rewritten. Untracked private fixture data and raw logs
belong only in the private wrapper evidence directory; they must not be staged
as public acceptance artifacts. Sanitized evidence may contain fixture IDs and
aggregate results, never real catalog paths, user metadata, or raw logs.

## Acceptance matrix and current disposition

The frozen design SHA-256 is
`0fa4b6a536021e681bc4fe51670552eb468a5076b208f5406c560bc590bf345e` and the
reviewed Task 41 SHA-256 is
`d9a9b2bb0a7536d49b4adee48dc9ea604926a7aaa05b08b235465f5c588bede1`.
Task 43 records the prior amendment hashes and formal clearance of this exact
design/Core revision. The reviewed Core source and test hashes are enumerated
there; the final Core receipt is retained privately at
`core-final-receipt.json`. Any material source or
design change requires updated hashes and renewed review before Qt handoff or
acceptance relies on that clearance.

| Gate | Required evidence | Current disposition |
|---|---|---|
| Design and Core review | Task 41/design hashes; independent review of the durable per-restored-root `health_detail` hold, exact deterministic encoding, persistence after marker clear, health/source-enable APIs, captured cache-root input, and Linux physical backing eligibility | **Cleared for Qt integration only.** Task 43 reviewed the frozen design and Core code at the exact hashes referenced above. This does not clear any acceptance gate. |
| Frozen acceptance inputs | Exact Qt-inclusive source tree/commit, full file inventory and hashes, generated fixture definitions, direct commands, environment, and private evidence location | **Partially established.** Reviewed Qt source/package inputs, the 178-test regression checkpoint, and the local unsigned build/smoke receipt are recorded; reviewed native-helper inputs and native evidence remain pending. |
| Core snapshot and restore acceptance | Coherent online snapshot under writer activity; schema/integrity/foreign-key/orphan checks; digest; exact metadata comparison; exact marker/source-column deltas including durable `health_detail` hold | **Not started.** Core regression tests and review do not exercise or satisfy this acceptance gate. |
| Refusal and failure matrix | Malformed/unsupported package, path and placement refusal, collision, cancellation, worker failure, post-link failures, cleanup failure, uncertain publication, and no-overwrite checks | **Not started.** |
| Guard and activation | Pending and unknown markers; source-backed and standalone original-path refusal; cache-only reads; pre-resolve/stat index refusal; changed root-map refusal; linked-only activation; standalone refusal; per-source explicit enable clearing only its reviewed hold without scan; ordinary enabled-paused behavior | **Not started.** |
| Qt and native | Responsive UI, truthful notices, worker close/reap, stale-result containment, no media I/O, Linux native run | **Qt regression passed** at the reviewed 178-test checkpoint. Native attempt 1 failed before N01 on an async-gallery API mismatch (exit 1, zero cases); cleanup was uncertain. A 12-file inventory found no detected mutation, which does not prove no reads. Corrected driver/review and a fresh native attempt remain pending. |
| Hosted platforms and packaging | Exact-head Windows/macOS/Linux results, named skips; frozen build/smokes; preserve seven gallery-filter smokes | **Windows Core and Qt test suites passed with named platform skips; 29/30 exact-head checks succeeded.** Qt macOS packaging smoke failed after the app was created; that failure remains open. The local 51,199,488-byte unsigned build and smokes passed but were not deployed. No hosted result establishes acceptance. |
| Preservation and privacy | Baseline/output comparison, changed-path allowlist review, raw-to-sanitized review | **Not started.** |
| Independent final review | Frozen implementation/tests, acceptance receipts, native evidence, privacy, final diff | **Not started.** |

The private Core receipt is retained as a regression/review record, not a
Task 42 acceptance result. Its focused 89-test and full 293-test runs passed
with zero skips; Task 43 independently cleared the exact reviewed Core for Qt
integration. Do not describe those runs as recovery snapshot/restore
acceptance, and do not repeat CI or run broad/native acceptance until the
Qt-inclusive inputs are frozen and the relevant review gate is satisfied.

## Goals and boundaries

Prepare a reviewable, generated-fixture acceptance record for a consistent schema-6 metadata snapshot, versioned manifest, verification and inspection, and restore into a new, nonexistent local catalog location. Check preservation of stable asset IDs and revisions, taxonomy/aliases/assignments, provenance, ordered collections, source entries, and curation histories. The only intended snapshot-to-restore differences are the pending marker (`PRAGMA application_id`) and source fields `enabled=0`, `health='paused'`, and `health_detail` equal to `defiantmaple:restored-root-review:v1:` plus lowercase SHA-256 hex of `UTF8(source_id) || 0x00 || UTF8(root_path)`, computed from stored strings without normalization. Verify the hold persists after global marker clearing and only explicit captured per-source review removes it; test normal source-enable and health-update paths as bypass attempts. The backup itself remains unchanged. No source media is probed, scanned, moved, or rewritten; the restored catalog is not auto-opened and does not replace the current library.

The protocol covers bounded evidence related to FR-LIB-005, FR-RECOVERY-001/002/004/005 and NFR-005/014/015. It does not complete any full SDD requirement. Preserve the tracker's existing IDs and statuses: FR-LIB-005 Partial; FR-RECOVERY-001, 002, 004, and 005 Partial for bounded Core evidence; FR-RECOVERY-003, 006, and 007 Not Started; NFR-005 Implemented; NFR-014/015 Partial. Do not claim Partial completion for recovery rows before reviewed implementation evidence. Scheduled snapshots, portable export/import, selective redaction, general multi-instance writer coordination, cache/index rebuild, stable library ID, and full recovery qualification remain separate work. Schema 6 has no stable `library_id`; do not synthesize one in the manifest.

## Entry conditions

- Task 41 design is complete, independently reviewed, and frozen, including live-catalog placement eligibility, output containment, concurrent-writer semantics, platform publication durability, bounded package/cancellation behavior, failure cleanup, and a proven source-activation guard. A material change to the activation contract, including a durable per-root hold or added source-enable APIs, requires updated design/Task 41 hashes and renewed independent review before acceptance. Pausing `health` alone does not guard external actions, and `sources.enabled=0` cannot guard assets with `source_id` NULL. Prove a current-build-only, fail-closed guard from the pending marker for source-backed and standalone assets while preserving ordinary enabled-paused behavior. Acceptance must retain source-backed cached-only catalog browsing while refusing original thumbnail, inspector, comparison, and external-open actions until review; standalone assets remain catalog-browsable only until later per-asset review. Verify the marker survives restore copying. Older binaries that ignore `application_id` are outside the protection claim.
- Implementation and all acceptance inputs are frozen and hash-recorded. Use generated fictional schema-6 catalogs and disposable local paths only. Do not run tests before implementation is complete and frozen.
- The 13 October baseline and all deployed outputs are protected and compared for byte, mode, and time changes. Raw path-bearing logs remain in the private wrapper; sanitize generated evidence before publication.

## Planned gates and record

1. Core coherent snapshot under controlled concurrent writes, schema/version declarations, integrity/foreign-key/orphan-provenance validation, exact manifest digest, and exact metadata restoration comparison. Compare every source row and every column against the snapshot; permit only design-enumerated deltas, including any `health_detail` hold sentinel, with the exact sentinel value specified. Prove the per-root hold survives pending-marker clearing and blocks normal enable APIs until captured explicit review succeeds.
2. Refusal/failure matrix covering corrupt/truncated/unsupported packages, invalid schema and relationships, missing/denied paths, collisions, cancellation, and injected backup/publication/restore failures. Include faults immediately after create-if-absent link creation (final readback/identity, staging unlink, and directory sync where supported). Prove the published final remains complete on late failure, is reported as uncertain when required, is never deleted or overwritten, and cannot damage a prior verified point. Record cleanup failures explicitly.
3. Qt/native explicit backup, inspect, and restore flow with responsive event loop, truthful pending/refusal/unknown results, omission and root-review text, correct path ownership, no media/source I/O, real worker shutdown, invalid package and inaccessible-target cases, and metadata browsing after restore with guarded sources. Compare snapshot and restored catalog with exactly the pending marker and source-column values above; verify the hold is displayed as readable review state rather than its token, marker preservation, and per-source hold persistence after marker clear. Include `source_id` NULL assets, retain source-backed cached-only browsing, block original thumbnail/inspector/comparison/external-open until review, disable/refuse scan without probing a source, refuse whole-catalog activation and report standalone count, and verify ordinary enabled-paused sources behave as before. Test changed captured-root-mapping refusal, successful atomic marker clear with all sources still disabled and held, ordinary source-enable/health-update bypass refusal, then explicit per-source enable clearing only that source's hold after captured mapping and root-access review without a scan. Test pending `index_file` refusal before resolve/stat, unknown marker refusal at raw gallery/cache openers, captured cache-root placement enforcement, and state that older builds ignoring the marker are outside the guard guarantee.
4. Focused Core/Qt suites, one coordinated full Core/Qt discovery, generated Linux native acceptance, package smoke only if the packaged runtime changes, exact-head hosted Windows/macOS/Linux summaries and named skips, artifact/privacy review, and protected source/output preservation. Verify Linux local-storage eligibility against actual backing-device/mount evidence (including sysfs where the adapter relies on it), and prove cache-root exclusion using captured cache context; unknown or unavailable backing/context must refuse. Preserve the existing seven gallery-filter smokes.
5. Independent code, test, native evidence, and privacy reviews. A draft PR follows successful review; merge and deployed-output replacement remain separate decisions.

For every gate, record reviewer, exact commit/tree, input hashes, command, environment, exit code, summary, skips, evidence digest, and disposition. Leave gates pending until evidence is present. A failure is recorded with scope and is repeated only if a fix or a specific justified failure warrants it. Do not infer recovery acceptance from gallery-filter CI or merged-main Core results.

## Ownership and completion

This task owns this acceptance record and `docs/metadata-recovery-acceptance.md`. Root owns Task 00 and the requirements tracker; Sol owns Task 41 design; the independent reviewer owns Task 43. Do not edit those owned files here. Completion requires all applicable gates, independent reviews, sanitized evidence, and a truthful traceability proposal; it does not authorize a merge or deployed-binary replacement.
