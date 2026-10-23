# Task 52 — independent scheduled metadata snapshot review

Status: exact revised Task50 design and Task51 acceptance contracts are cleared
in the review document before material runtime changes. Root's staged
implementation go remains separate. No implementation acceptance, retention
deletion or private native/frozen helper execution clearance is implied.
Owner: independent Sol. Baseline: merged PR24
`47effeeb5a5adf8b692023c49b67ee52a9025559`.

Review [the review contract](../scheduled-snapshots-review.md) against SDD v0.2
§16.3 FR-RECOVERY-003, §21.2 and the existing admission/recovery contracts.
The goal is opt-in, application-running, verified local metadata snapshots with
visible last-success and failure status and configurable retention/storage
policy. The goal is not complete merely because a timer invokes manual backup.
No OS service, export/relink, deployed output replacement or broad storage
qualification is included.

Before material runtime changes, independently review the exact frozen Task50
design and Task51 acceptance matrix. Trace actual entry points and existing
backup/admission/worker/publication lifetimes. Require explicit decisions for
physical identity and copies/moves/replacement; external durable configuration,
status and clocks/restarts; directory/index trust; verified-point selection;
retention authorization, race handling and fault ordering. Send concrete
blocking findings promptly. Record exact hashes and explicit clearance only
after findings are resolved. Root owns scope decisions and execution approval;
reviewer does not implement its own proposed runtime correction.

Preserve current writers and manual recovery behavior on Linux, macOS and
Windows, existing recovery publication qualification/refusal, schema7, UUIDs,
SQLite durability, scanner semantics, source/standalone/pending holds, original
media/cache and all15 deployed outputs. Unsupported scheduled snapshot storage
must refuse truthfully without disabling unrelated current functionality.
Never treat admission as a security boundary against old/external callers.

After implementation, review incremental code and meaningful tests, exact
private generated native/frozen helpers before execution, and resulting raw
receipts. Require actual failure/cancellation/restart and retention boundaries,
not only success-path timing. Independently validate freeze/preservation,
platform CI totals and named skips, public evidence/privacy, and all129
requirement IDs/status bounds before the final draft PR record. Do not mark
FR-RECOVERY-003 fully accepted from an untested platform/storage matrix.
No runtime/source edits, test execution, external settings, commit, push, merge
or deployment are authorized by this review task. Root owns publication.


B3 checkpoint: independent review accepted the two exact generated offscreen
QApplication/controller/native backend ordering cases, including genuine Qt
finished versus actual actor cleanup in both orders and fresh durable stopped
status. See the bounded checkpoint in `../scheduled-snapshots-review.md`. The
faulted child’s original BrokenPipe reporting failure remains explicit; no
containment intervention or protected-output change was accepted. This is not
window/settings/manual wiring, restart or frozen/visible application acceptance.
Continue exact review of W1 integration and the open timing/status, manual
reservation/cleanup, startup/close, platform and application acceptance gates.
No new execution or publication authorization is implied by this checkpoint.

W1 checkpoint: bounded timing (amended 29), manual hooks (41), prior application
wiring (46), and startup-fix (52) focused suites are cleared as recorded in the
review document with exact source/receipt hashes. The original startup
configuration/cache normalizer now runs off GUI with retained genuine-thread
lifetime, start-failure/manual recovery and close/stale-result coverage. The
52-test receipt includes that original constructor assertion and mocked
scheduling actors; it claims no actual recovery Process or W2 native wiring.
Prior failures and pre-fix evidence remain historical. W2 exact helper review
and separately authorized execution, restart/prune integration, W3/platform and
full requirement acceptance remain open. Review documentation closes here for
Root's explicit public allowlist checkpoint; no execution is authorized.
