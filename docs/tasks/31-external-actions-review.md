# Task 31: Independent external-actions review

Baseline: merged PR17/main `00432238d7c1e7918fb505364de382dcaa1e3425`.
Branch: `codex/phase1a-external-actions`. Task29 defines implementation scope;
Task30 defines independent acceptance. Independent Sol reviews read-only source
and evidence, records findings here and coordinates fixes through Root/owners.
No production/helper/acceptance edits, commits, switches, PR operations or
visible native probes.

Audit typed immutable ID/revision/path/fingerprint capture and revalidation;
selection/filter/configuration drift, ABA, zero retargeting and source-health
truthfulness. Paused explicit-scan state is not unavailable. Evaluate fresh
regular/readable source checks, content fingerprint, off-GUI blocking probes,
finite limits, worker cleanup, timeout cancellation and no late launch.

Review trusted local configuration/compatibility, structured literal argv,
OS local-file URLs, no shell/media-name interpolation, executable failure and
process ownership. Explain check-to-launch race and user-controlled external
application limits; no false save/reconciliation claims. Check catalog/schema/
metadata/journal/source preservation and unchanged scanner/recovery/workflows/
archives/deployed outputs. Keep comparison, cached-offline display, broad
accessibility and platform/release qualification separate.

Independently review complex native helper before freezing/running. Verify
exact app/focus/keyboard gates, generated-only isolated state, read-only handler,
adversarial literal argv/no marker effects, stale/unavailable refusal and
before/after source/catalog evidence. Audit raw-to-public derivatives/capture
bytes/privacy and all 129 requirement IDs. Failed attempts retain identities.
Mocked associations do not count as native default-application evidence.

Reproduce meaningful failure cases when needed; do not repeat broad passed
suites without changes or unresolved risk. Review published head/tree, green
relevant CI, actual Windows summaries, current feedback and final PR claims.
Record resolved findings and explicit final independent verdict. Finish with a
reviewable draft PR; merging and deployed binary replacement are separate.

## Design review before implementation

The proposed single-request isolated helper keeps database, filesystem hashing
and handoff work off the GUI thread. Its proposed 5-second deadline and 512 MiB
hash cap are operational refusal bounds, not adopted performance or supported-
media limits. A slow or larger valid original may be refused with a clear
reason. No numeric user-facing latency claim follows from these bounds.

The initial design raised three targeting and handoff questions, resolved in
Task 29 before implementation:

1. Standalone indexed assets can have a null source ID and no source-entry row.
   They remain eligible under immutable UUID/revision/path/fingerprint plus
   fresh-file checks; no source health is invented. Source-backed assets require
   the same asset ID, source ID and path on exactly one indexed entry. `paused`
   and `watching` are allowed; `scanning`, offline, permission-denied, error
   and nonindexed entries are conservatively refused.
2. Hashing can overlap a catalog update. The helper must requery the same
   captured asset and source relation after the fd/path hash immediately before
   handoff; an initial requery alone is insufficient, since source disposition
   and health do not necessarily increment asset revision. A short final
   `BEGIN IMMEDIATE` gate may keep that catalog snapshot stable through dispatch,
   but its lock lifetime must remain bounded by the operation deadline. The
   final path-to-external-handler interval remains a documented race.
3. A timeout before a one-time dispatch permit must leave no launch-capable
   helper. A timeout after permitted `Popen` or OS association begins can mean
   handoff occurred without acknowledgement. Report that outcome as uncertain,
   never auto-retry it, and do not terminate an acknowledged user-owned editor.

These decisions clear the design for implementation. Source, helper and test
review remain open; no production or native changes were made by this reviewer.

## Incremental service review (implementation evolving)

The first `external_actions.py` draft preserves a typed captured target, keeps
one spawned probe behind READY/permit, rechecks the catalog after hashing, and
uses literal `Popen` arguments or `QUrl.fromLocalFile`. Two concrete issues were
sent to the implementation owner for correction before source clearance:

* `Path.stat()` and `Path.open()` follow a symlink swapped into a cataloged
  regular path. A same-byte/hash symlink target could pass verification and
  hand a different path relation to the external application even though the
  scanner excludes symlinks. Refuse newly symlinked leaf/parent components,
  use a non-follow fd open where supported, and test generated symlink swaps.
* The helper marks `dispatched=True` before calling `_dispatch`. A known
  `Popen` failure or declined OS association therefore appears as an uncertain
  successful dispatch. Separate entry into the handoff boundary from an
  acknowledged handoff, while retaining conservative uncertainty on lost
  acknowledgement and no automatic retry.

The source is not frozen and these findings are not a final verdict.

The owner addressed both in the evolving service: source validation now checks
canonical leaf/parent paths before and after hashing and again under the final
catalog reservation, opens with non-follow/nonblocking flags where available,
and confirms the descriptor is regular; known dispatch rejection now returns a
refused result while an acknowledgement lost across the entered OS boundary
remains uncertain. Focused regressions and the Qt/helper integration still need
independent review before these fixes receive final clearance.

The evolving Qt integration captures the focused model row once, runs action
and settings I/O through bounded workers, and defers a captured request while
settings load. The default settings path is machine-local app data; the helper
canonicalizes it and refuses exact catalog collision or placement under a
registered artwork source before reading or replacing it. The settings dialog
does not itself perform filesystem/DB checks on the GUI thread. The side pane
is already dense and now has four more controls; verify default-window/native
reachability of both new and existing controls, adding scrolling if required.
Task 30 protocol wording should distinguish connection-local PRAGMA setup from
persistent catalog changes and the five-second permit deadline from cleanup
time or an uncertain entered OS handoff. These points were sent to the owners.

The side pane now uses `QScrollArea`, and six focused Qt tests pass according to
the implementation owner. They exercise actual QThread probe/cleanup, literal
stub dispatch, captured target across selection/filter/settings changes,
revision ABA refusal, keyboard settings entry/save, cancellation and close under
a held catalog lock, and mocked local-file association URLs. The frozen CLI
smoke invokes the same external QThread worker with `probe_only=True`; the
package step uses a generated catalog/source and verifies no permit plus
unchanged source/catalog digests. Final native reachability and frozen-build
evidence remain pending. The file action's `Open in Editor` label also covers
OS association, which may launch a viewer; the owner was asked to clarify this
user-visible distinction before final clearance.

## Native-helper prefreeze review

The first helper draft uses generated `/tmp` media/catalog/configuration,
retains raw attempt stages, requires a real exposed/active/focused Qt window,
checks keyboard target reachability in the scroll pane, and sends the fictional
original as a separate literal argument to a generated handler that records
argv only. It compares source byte/size/mtime manifests and catalog dumps
before/after, and does not install an OS association. The draft is not frozen.

Three execution blockers were sent to the owner before any native run:

* `QTimer` is used in the catalog-lock responsiveness stage without import,
  causing a late `NameError` after the first handoffs.
* Save traversal starts from a `QPlainTextEdit`; plain Tab normally inserts a
  tab there instead of moving focus. The helper needs an actual bounded
  keyboard path to Save, with focused-widget evidence.
* The settings capture's own privacy guard rejects a home-directory executable
  path, while the supplied venv's `sys.executable` is under the home directory.
  A checked system Python outside home can run the stdlib-only generated stub.

The raw host evidence also needs exact distro/session/screen facts and the
final/trial SQLite foreign-key check requested in Task 30. None of these
observations is native acceptance evidence; Root alone will execute a reviewed
frozen helper once corrected.

The evolving helper now imports `QTimer`, enables Tab focus traversal on the
argument text editors, and chooses a checked system Python outside the home
directory for the stdlib-only handler. It records exact distro and screen
facts and checks foreign keys in the disposable refusal trial and final catalog.
The independent static reread found no further blocking issue; the owner was
asked to record the generated XDG paths and to keep the acceptance wording
precise: focus is established programmatically, then actual QtTest key events
are exercised. Screen names remain private raw evidence and should be filtered
from public derivatives. Exact frozen helper hash and selfcheck are still
pending before Root's visible run.

Exact helper SHA `ed42a150a450b63d3734e362c46f3809c7a25641521fba4484e3647c29693a11`
matched the reviewed file after those corrections. Pre-native clearance was
briefly held for a separate Qt integration issue: `external_feedback` used a
default `QLabel` AutoText format while inserting untrusted media basenames and
error messages. HTML-like filenames can render as markup instead of literal
text. The owner was asked to force `Qt.TextFormat.PlainText`, add a focused
generated-filename regression, and refresh the source digest before native
execution. The helper itself need not change for that product fix.

The focused fix set both external-status and settings-error labels to
`Qt.TextFormat.PlainText` before dynamic text. A generated HTML-like basename
and error regression checks literal display, zero dispatch and unchanged
catalog/source facts; nine affected Qt tests passed per the implementation
owner. Exact pre-native slice reviewed: helper
`ed42a150a450b63d3734e362c46f3809c7a25641521fba4484e3647c29693a11`,
Qt module `743f7a75d8a7146db723a3566ae756b09e0fd93ebe82670081ce468a7178c38a`,
Qt test `f6c658910ce4e9bf4b6a964786304c328ffc8281fc936a0e283119575cc2c6a6`.
The independent reviewer cleared this exact slice for Root's first visible
native attempt after unlocked-session preflight; native outcome is pending.

## Native attempt 1 independent audit

Root's first visible attempt completed on the reviewed helper and source bytes.
The raw final and partial receipts are byte-identical (SHA-256
`53f24b5a89f1b2b25dcb313204ad851d0950ecb913cc3ddfb1eccbc7ac555c60`),
and all ten recorded source-file digests still match the checkout. The reviewer
read the surviving fictional `/tmp` fixture independently: both original PNG
SHA/size/mtime manifests and the full SQLite dump digest exactly match the
recorded before/after values; the catalog has one source, two assets and two
entries, `integrity_check=ok`, and no foreign-key violations. The generated
handler log has exactly three literal argv rows matching first file, containing
folder and reopened-file stages; no extra dispatch or shell-marker file exists.

The separate disposable trial refused scanning, offline, permission-denied and
error last-observed source states, revision ABA, absent tool and startup timeout
without a permit. The native locked-catalog stage timed out without permit or
additional handler request while a GUI timer recorded 257 ticks. All 38 raw
keyboard ledger entries show an active, exposed, visible window with focus
inside; the ledger includes bounded scroll-bar keys and Tab traversal to Save.
These are QtTest keys after programmatic focus establishment, not a human
assistive-technology assessment. Both app-only captures were viewed: they show
fictional `/tmp` paths and generated assets; the gallery uses placeholders in
this run and does not establish cached-thumbnail behavior. The settings
capture contains `/usr/bin/python3.14` and no home path.

The host receipt identifies Nobara Linux 44 KDE edition, Qt Wayland, PySide6/Qt
6.11.2 and an active/exposed focused window. It records generated XDG
environment destinations and preservation of `XDG_RUNTIME_DIR`; the three XDG
subdirectories were not created, so public wording should describe redirected
destinations rather than created directories. Both gallery closes report a
closed model connection and reaped helper. Configured read-only stub dispatch
is evidenced; native OS default associations, Windows/macOS, frozen dispatch,
real-share interruption and broad accessibility are not. Public derivative
privacy and hosted current-head CI remain pending, so this is provisional
source/native clearance rather than final milestone acceptance.

## Public derivative and prepublication clearance

The public attempt-history JSON SHA-256 is
`de37e823a0eb0c77aace3aee7433b47916c63fe76836bc16457b692fbe5d74e4`.
Its raw receipt, wrapper log, helper and ten source-file digests all correspond
to the reviewed native attempt. Both PNGs are byte-identical to the two viewed
app-only raw captures. The timeout-controls caption correctly identifies a
refusal, not a successful handoff. The JSON has no absolute path or UUID value
and passed explicit `_check_json`; the unchanged captures visibly contain only
disposable generated `/tmp` paths and generated asset IDs, as disclosed, with
no user artwork, home path or desktop chrome. The acceptance record and tracker
retain Partial status and separate native stub, mocked OS association, hosted
CI, frozen worker and broader release/accessibility limits. The SDD and tracker
each contain the same 129 unique requirement IDs: 104 FR, 15 NFR and 10 SEC.

The draft PR description accurately distinguishes 58 broad Qt tests before
the feedback-label fix from nine focused Qt tests afterward, and describes
source-native evidence and pending CI/frozen-package gates. `package.py` SHA-256
`77f5cec780102e5f90d74b76b4ebba3822344f7647ef23a6e1555cf6d467dc89`
is the approved narrow preservation exception: its diff adds a generated
real-worker READY/no-permit smoke and result metric while retaining prior
identity, thumbnail, gallery-worker and package behavior. Against Root's
baseline receipt, 83 other protected files retain exact bytes, and all 15
deployed output files retain SHA, size and mode. Source, native and public
privacy review clear this tree for draft publication. Final independent
milestone acceptance still depends on exact-head hosted CI, actual Windows
results, and frozen-package evidence.
