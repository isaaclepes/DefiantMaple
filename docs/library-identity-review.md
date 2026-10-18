# Independent library identity review

Task46 owner: independent Sol. Initial review: 16 October 2026.

Current gate: **BOUNDED COMPLETE at runtime head
`a9e2be9fe5239e3fb3e1d743d3050e441813f553`.** The mapped LI01–21 evidence,
all30 hosted checks/four workflow runs, actual Windows logs, preservation and
public privacy are cleared within their stated scopes. Final documentation
publication and any checks triggered by its resulting head remain pending.
PR23 must remain draft and unmerged; deployment is outside this clearance.
Historical sections below retain their original gate state.

## Design gate

**CLEARED for bounded implementation.** Reviewed Task44, Task45, Task46,
SDD v0.2 sections 5.3, 16.3, 22.3 and 25, existing catalog migration and
metadata recovery design/code, and `library-identity-design.md` SHA-256
`86db125e79638f0e7e34acd22f93c6e08ccbe188b26ede21db3c5b223a4bbc5c`.
Review base HEAD: `d53d7d0675800ec8bd71536c1be0c6890ee4bd01`.
This clearance preceded runtime/schema implementation and establishes no
implementation, platform, native, frozen-build or release acceptance.

The reviewed design adequately separates stable UUID from application_id and
file freshness identity; authenticates one protected canonical UUID; backs up
verified original catalogs before migration; rolls back failed changes; and
preserves prior backups. It explicitly dispatches deployed v1/schema6 versus
v2/schema7 packages, preserves modern identity, and honestly assigns a new
identity independently for each legacy restore. The immutable legacy package
is a recovery point for its unpublished restored stage. Inspection assigns
no persistent identity. Pending state, source holds and standalone limits
remain required.

Implementation review must specifically verify INSERT OR REPLACE cannot
replace the singleton when recursive triggers are disabled; missing identity
in schema7 refuses rather than regenerates; all schema7 catalog/package
admissions validate identity; and legacy restore excludes only the newly
introduced identity table while modern restore includes it in row fingerprints.
Exact expected source hold changes require independent assertions alongside
the fingerprint that omits those fields.

BEGIN IMMEDIATE provides SQLite writer serialization during migration, not
application broker coordination. Other application instances must be closed
for upgrade. Old-client refusal means the measured prior schema6 runtime's
version checks, not protection against arbitrary raw SQLite clients or every
historical client. Current copies retain one logical library UUID; independent
merge/import and conflicting copy coordination remain outside this milestone.

## Remaining gates

The private Task45 execution plan and fixture specification were reviewed and
cleared for use after implementation freeze and Root assignment. They require
genuine unchanged PR22 schema6/v1 production, distinct historical fixtures,
old/new subprocess import provenance, immutable originals with disposable
migration copies, and production-qualified private local fixture storage.
This is preparation clearance, not execution or acceptance evidence.

Initial Core review identified an admission gap: adding identity validation to
`catalog.connect` alone leaves raw gallery/cache/original-reader connections
with state/version-only checks. Shared bounded current-catalog admission and
adversarial direct-reader tests resolved this gap before stage clearance.
The shared admission preserves valid pending metadata/cache access and keeps
schema6 migration/package verification separate. The Core/admission stage is
cleared to proceed to recovery UI integration; final acceptance remains held.

Reviewed Core catalog SHA-256
`d0b74ef0b12036af7d71d9314e751f67cf42add42f1d758a21a823644c34b5e8`
and recovery SHA-256
`1d939417ff3396b99f59fb4ee420e71c54a6b77fdf774e92332ebec643423c29`.
Independently matched all source hashes and six raw-log hashes in the private
Core attempt-one receipt. Its direct exits are zero: identity 13, migration 21,
recovery 24, curation 10, bulk curation 10, gallery query 11 tests. This is
reviewed focused evidence, not an independent rerun or acceptance matrix.
Handcrafted legacy unit packages do not substitute for Task45's genuine
unchanged PR22 producer. Narrow Qt admission bridges still require their
regression evidence with the full recovery UI changes.

Qt integration subsequently cleared for full-suite freeze at recovery UI hash
`072d314cffdab517caefd64ee0738f6b55c5833ec232d47b4bd1335c974726bc`
and new identity UI test hash
`1d67c2fa67324ecc5ccaf1783308ebb48700c683f40b3f2b5ba4b20ef0c19fb3`.
Identity reports use the existing plain-text report widget; legacy absence,
fresh assignment and modern preservation are explicit. Restore confirmation
defaults to No and proceeds only on Yes. Logical UUID does not replace
device/inode or callback/epoch freshness. Focused adversarial tests cover
raw Qt readers, a same-UUID replacement file and stale callback rejection.

Completed private attempt-one receipts independently matched current source
and raw-log hashes: seven Core suites total 110 and six offscreen Qt suites
total 76, all direct exits zero and source unchanged. The additional Core
suite covers cached preview (21); Qt suites cover new identity (5), recovery
(8), catalog gateway (17), query gateway (4), comparison (28), cached preview
(14). These focused results permit proceeding to full-suite freeze; they are
not full discovery, native desktop, frozen package, genuine legacy producer,
actual hosted CI or release acceptance.

The final diagnostic compatibility adjustment is cleared at benchmark hash
`d2dcdad579fb00de42acac53795497a2168f201ca835fd5172e7b2c1ae177962`
and test hash
`3300ed8b4fa57c60d32ba06f6d868044161e12ffad400bf3a8e6c2c5fd5ad2d1`.
It only adds schema7 to the closed archived-reader allowlist, preserves 4/5/6
and exact-current producer checks, and tests unknown8 and noninteger refusal.
The private focused receipt/source/log hashes match seven passing tests and
direct exit zero. This does not authorize benchmark measurements. The unchanged
frozen recovery smoke enumerates every user table and compares every nonsource
table exactly, so schema7 identity is included automatically. Runtime is now
cleared for full Core/Qt freeze under Root assignment.

Implementation/adversarial tests, source freeze, package provenance, native
desktop evidence, actual current-head CI/Windows summaries, privacy review,
and preservation of baseline outputs are pending. No broad broker, platform,
SDD or release acceptance is claimed.

## Resumed evidence review

Independently re-read the retained full Core receipt and raw log after explicit
resume. Raw SHA-256
`421abbb7af81c8eb788cc95c5110535dcfe668e4a7f53afeab8277c43f914301`
matches 311 tests in 88.635 seconds, OK, direct exit 0. All 154 frozen
runtime/test/build-input hashes still match the current checkout. This retained
full Core evidence is cleared without a redundant rerun. Interrupted Qt
remains unclassified as pass/fail pending the separate resumed attempt.

The authentic PR22 archive hash and git archive commit independently match
the recorded merge baseline; all 285 extracted file hashes match archive
members. Final fixture helper review identified a remaining working-directory
mismatch: helper `parents[3]` selects the work parent while the wrapper selects
the checkout wrapper parent. Preparation execution remains blocked until both
select the actual DefiantMaple checkout and revised hashes receive clearance.
The archive prefix correction is present. Private production storage admission,
import origins, no-overwrite artifacts, direct exits and preservation remain
required; preparation clearance will not constitute fixture acceptance.

The final preparation helper and wrapper are now cleared at SHA-256
`b539091c8a3d5ea95dca8792866a99795ee7711b99327f71577f62943aa146ef`
and `104d2a0c47055f0880a7b29e024220c963c86e8ec6fff01c22b30d0670782a89`.
Both use the exact checkout path. Pre/post preservation checks use the correct
wrapper output root and compare all 15 SHA-256/size/mode/mtime records. All 15
currently match independently. The mode-0700 run, frozen old-source import
provenance, unchanged production storage admission before fixture creation,
read-only legacy originals, no-overwrite logs/receipts and direct child exit
recording satisfy bounded preparation requirements. Root still assigns execution.
No fixture/matrix or native acceptance is inferred from this static clearance.

Fresh full Qt receipt and raw log independently matched SHA-256
`c5de17760f990e284f5afd74dad40a32ce601d098e9e50bb9c32268f06dc2b16`,
188 tests in 42.581 seconds, OK, direct exit 0. Its pre/post manifests are
identical across 154 paths and match the current checkout. The Qt backend is
offscreen; no warning filter override was recorded. Full Core and full Qt
evidence clear the regression freeze gate for an isolated build proposal.
Frozen build/smokes, native desktop, actual hosted CI/Windows, acceptance and
final public privacy/preservation review remain pending.

The isolated build helper is cleared at SHA-256
`b04ed84f56741d601769ef0e5494b1c14bfff5be3de6a75625e469909f1a90cc`.
All 293 candidate shadow-file hashes independently match its manifest; 154
runtime inputs and 15 deployed outputs are gated before/after. The existing
private task TMPDIR confines package cache deletion, shadow cwd confines
artifact cleanup, and the unchanged package driver retains all eight smokes.
The 100000-row placeholder catalog supports only the existing package run.
This is build preparation clearance, not successful build or native evidence.

Actual legacy fixture preparation attempt one failed before backup/publication
with CurationConflict at the first curation call: hardcoded expected revision
zero was stale after metadata edits. Its direct exit one, raw log and partial
fixture are retained. This is a fixture-helper assumption failure, not product
failure evidence. A separate attempt must capture current revision before the
first edit and use the returned revision before the second; re-review required.

Separate fixture attempt two is cleared at helper SHA-256
`79887a87eba2d7bedd5f613cd77241e91525e8533e8e9074f46ae34e8be0dc60`
and unchanged wrapper
`104d2a0c47055f0880a7b29e024220c963c86e8ec6fff01c22b30d0670782a89`.
It reads actual current curation state before each edit and verifies returned
revision, resulting values and exact history order against unchanged PR22 API
semantics. Its fresh mode-0700 workspace contains the same authentic archive
and all 285 extracted file hashes independently match. Prior failed attempt
raw SHA-256 `8df755c182770f66ccd5f44ddef8e78b2b914056cc52f01dbfe0f643e25bc3e1`
and direct exit one remain retained; no prior package exists. Root assigns
retry execution. No product code or failure classification was changed.

## Initial implementation draft gate

The initial staged implementation draft is cleared for publication to obtain
actual current-head hosted CI. Reviewed index tree
`5d2f86bf23967282344a4e0fd53910ec7ad59120` contains exactly 25 public
paths. All 154 staged runtime/test/build hashes independently match the
reviewed Core311/Qt188 freeze. The staged changes retain authenticated identity,
legacy compatibility, freshness/source holds and the documented concurrency
limits. Public artifact checking and cached whitespace checking pass; staged
content contains no private fixture paths, assigned UUIDs or raw receipt data.
Synthetic fixed UUIDs occur only in adversarial tests. This review addendum
changes documentation only and requires Root to restage the review records.

Task00 explicitly allows this initial draft while frozen/native/legacy and
final evidence gates remain pending. The draft must identify those incomplete
gates; it establishes no Goal completion, merge, deployment or release claim.
A final evidence/publication review remains required after actual current-head
CI/Windows logs and local acceptance are available.

Authentic PR22 preparation attempt two is independently verified: direct exit
zero, empty raw-log SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`,
schema6 catalog, genuine v1/schema6 package, integrity OK/FK zero, immutable
fixture inventory hashes/modes, unchanged source/cache and all 15 output
records. It is cleared as a legacy compatibility input with a material limit:
both source scans indexed zero assets and left entries pending; the single
asset is standalone. It cannot establish linked-asset relationship, missing
asset or rich linked-history coverage. Separate authentic linked fixtures
are required before those acceptance claims. Preparation is not acceptance.

The separate linked fixture preparation helper is cleared at SHA-256
`3300b0ddb93b02e98ff4d501503084a416e1744dabe0793a4524c521d809ac7f`
with unchanged wrapper `104d2a0c47055f0880a7b29e024220c963c86e8ec6fff01c22b30d0670782a89`.
Its fresh mode-0700 run retains the authentic archive and all 285 extracted
hashes match independently. Controlled timestamps affect only owned generated
media; documented scan time arguments exercise the unchanged first-observation
and two-second quiet contract. Bounded named readiness requires exact three
linked path/source assignments and indexed entries before adding one standalone
asset; strict table population and curation history checks follow. Root assigns
execution. This preparation does not establish missing-asset, distinct source
health or multiple provenance-origin coverage, or successful acceptance.

Completed genuine linked preparation is cleared as an immutable acceptance
input after independent receipt and read-only database review. Direct exit
zero and empty-log SHA-256 match. All 285 old-source hashes and all frozen
fixture hashes/read-only modes match. Schema6 integrity is OK with zero FK
violations; the genuine package is v1/schema6. There are four assets (three
linked across two source IDs, one standalone), three indexed entries whose
asset/path/source relationships match exactly, two collections/four members,
two curation edits and the recorded tag/entity assignments and four provenance
rows. Scans indexed two plus one with zero pending/errors. Source/cache and
all 15 output pre/post records match. This qualifies these actual generated
rows only; missing-asset and richer origin/history cases remain unestablished.
No new-version compatibility or native acceptance has yet executed.

Completed isolated build evidence is independently cleared: binary SHA-256
`2581a9db32be148a03a60e523f886423b85aa78d1a7325bc6397072ece5fa1eb`,
51207680 bytes; package raw SHA-256
`3900e079602ed25dc01de0b0fc52e2e483d19140c60c3cc751613af0eaf58797`;
metrics SHA-256 `b460e1a31c54e4f697f4b5b8368ea78eadf49975854f70e82a223e9afcd08e1e`.
All three command exits are zero and raw hashes match. All eight frozen
smokes pass; qualified recovery publication reports exact all-table preservation,
which includes schema7 identity through the unchanged full-table comparison.
All 154 live/shadow pre/post runtime hashes match the current PR runtime, and
15 output records equal baseline. The 293-file archive predates later public
documentation updates; only runtime equality to the PR is claimed. These
offscreen build/smokes provide no native desktop evidence or deployment.

Initial Core compatibility driver review found fixture-only blockers before
execution: reap timeout exceeds the API maximum, immutable package inspection
needs a verified disposable copy in a writable private parent, and the frozen
restore API requires explicit live_catalog. Revised helper review is pending.

Revised Core compatibility driver preparation is cleared at SHA-256
`ebcdb1267eafb1bf132153dcab06026bcb072f0e25c375d1a8103f6fa267c058`,
wrapper `29517f0e0982f24f1505f3ca71e61dde7b04873f046da0c93272c54139acce28`,
and plan `ab7cea21643b8275b2b485731b73d946aff678e25d631c15ad3f7e802b4dbffb`.
It corrects the reviewed API assumptions, separates old subprocess origins,
uses verified disposable package copies under a private parent, independently
compares every table and exact source hold fields, preserves primary exceptions
and cleanup evidence, and records old-command timeouts without a false exit.
This is static preparation clearance; Root assigns execution.

The initial native proposal remains blocked before execution: timer callbacks
need explicit exception/deadline propagation and bounded modal termination,
exact real No/Yes confirmation counts, and pre/post original-input inventories.
No native result is inferred from static source review.

Completed genuine-producer Core acceptance attempt two is cleared within its
declared scope. Direct exit zero, empty raw hash and receipt SHA-256
`0c18d3d88fa226f837ece6f768b1af308f8b73c544a5c0c5c73208439974177e`
match. All ten old-command raw hashes/direct exits match; actual logs identify
frozen PR22 import origins and the expected typed refusals. Independent read-only
checks of both families confirm original rows survive migration, repeated legacy
restores assign distinct UUIDs, and modern restore preserves all tables/identity
with exact expected source holds. Runtime154 and output15 records match; the
100000-row trace contains only identity declaration/singleton queries, with no
asset/provenance reads. Cleanup reports no remaining workers/errors. The earlier
operator preflight refusal remains retained and is not a product failure. This
does not imply every LI case or richer fixture family was independently rerun.

Final native preparation is cleared at driver SHA-256
`70b9dbbaa72e55b51ace6d89b361a3714086d70418f8190f6945589f8719b05a`
and wrapper `7553708f643ecf1f6421778b9c9a1703ea7a27b237bc40eb3e9d2d00a645258b`.
Private XDG roots precede Qt imports; initial named detail/background readiness
precedes recovery snapshots. Callback errors/deadlines are captured, real modal
No/Yes/default-No checks occur outside callbacks, and owned watchdog/process
group bounds retain failure evidence. Original/Core input inventories are
protected. Root assigns execution after a fresh desktop check. Source Qt,
injected chooser paths and UI-only scan guards remain explicit limits; ordinary
initial gallery reads are separate from recovery-specific probes.

## User-requested pause after native completion

Completed native source Qt evidence is cleared within its declared scope.
Receipt SHA-256
`4cc205b8dcfb6f3c6b0adce7f4cb8484450d8bf3a50f1afd3f636bb5aa1542bf`
and command receipt `b10d4f18aedfb08ce84191373ebd46a144db6e196852427bcfc3aaa27be02efc`
match direct exit zero, no timeout and empty raw log. The reviewed helper's
unlocked Wayland and exposed active-window checks completed. Four actual
visible confirmations recorded No/Yes for legacy and modern, all default No,
with no callback errors. Reports explicitly disclose absent/assigned legacy
identity and exact modern preservation; independent actual target-row/hold
comparison passes. Active library/selection and UI scan absence were checked
after named initial readiness; original/Core inventories, runtime154 and
output15 records remain unchanged. Workers and windows reached clean terminal
cleanup. This is source Qt with injected chooser paths, separate from frozen
binary smokes, and establishes no child-wide original-media no-read claim.

User requested pausing at this completed evidence boundary. No new testing,
product edits or publication follow this checkpoint. Actual hosted Tauri
failures on three operating systems report unsupported schema7; that gap is
unfixed and final CI/Windows/public-evidence review remains pending. Existing
external jobs are left running. Final acceptance/Goal completion, merge and
deployment remain held until explicit resume and remaining reviewed evidence.

## Resume after native checkpoint

Retained Core/Qt raw hashes and native receipt were revalidated on resume; all
154 frozen paths still matched before any Tauri fix. Actual Windows, macOS and
Ubuntu Tauri failure logs independently terminate with unsupported catalog
schema7. This is an application admission failure after build, not cache noise.

The affected-input boundary for a Rust-main-only correction is one of the 154
frozen paths: `prototypes/tauri/src-tauri/src/main.rs`. A revised manifest must
record that supersession and retain the other 153 hashes. Unchanged Core/Qt
and native source inputs can reuse their reviewed evidence; Qt frozen smokes
retain their original build/runtime scope. Do not claim all154/current-head
equality after changing Rust. Tauri Rust tests and affected hosted compile,
package and benchmark results require fresh current-head evidence. Schema7
admission must authenticate bounded stable identity while preserving historical
prototype schemas2–6 and unknown/future refusal. Implementation review pending.

Actual initial-head Windows Core logs also expose a test-fixture portability
error before identity admission: POSIX `/generated.png` is not an absolute
Windows target path. PR/push Python3.11 and PR Qt's prerequisite Core step
report 311 tests, one error and 21 named skips; no Windows Qt-suite outcome
is inferred from its earlier Core-step failure. The cancelled PR Python3.13
log contains the same failed test summary, while the cancelled push Python3.13
log has no completed suite total. Workflow cancellation and recorded test
results remain distinct. A platform-native generated absolute path is the
bounded proposed test-only correction; fresh Windows evidence remains needed.

Tauri review additionally requires SQL normalization to preserve quoted literals
and escapes, matching Core's declaration-authentication intent. The initial
normalizer removed literal whitespace/case and therefore failed exact altered
constraint authentication. Revision and adversarial test review are pending.


## Bounded hosted-failure correction review

Independent exact-file review clears the two affected inputs for a follow-up
commit. Rust schema7 admission authenticates the Core table and three immutable
trigger declarations, reads at most two identity rows, and requires the
canonical RFC4122 version4 singleton UUID. Historical schemas2–6 remain
admitted and unknown schema8 remains refused. The SQL key now preserves
single-quoted literal whitespace/case and doubled quote escapes; the added
adversarial regression distinguishes altered `'te xt'` from `'text'`, and
requires all three entry points to refuse without changing catalog bytes.
Rust compilation/tests are not claimed locally: cargo/rustc are unavailable;
affected hosted Rust compile, test, package and benchmark evidence is required.

The Windows correction uses a resolved fixture-root generated path in the
existing refusal test. Its retained focused receipt independently matches the
current source hashes and raw log SHA-256
`709a1bf19d778fccd665f2f1da5620e0eab270de7dcdd47ac22bb4947a4e9cb1`:
13 tests, OK, direct exit zero. This is local focused evidence; actual Windows
Core and Qt outcomes remain pending.

Independent comparison with the authoritative 154-path freeze finds precisely
two supersessions: `prototypes/tauri/src-tauri/src/main.rs` changes from
`1f4c08629d91d11ab7c3e31fed940937ac41f0631f898c37bae859364f939f31` to
`cf50e3cd2a5a33c95df26e81eb91b8e6a496e48ca9ab595159b6893cc75a9c10`,
and `tests/test_library_identity.py` changes from
`9636448311a9530d8005d7d7f14b8731ff3389a52f104a3325344f86f8089cb9` to
`a1e154471e47da6930fbc8f961ece24afdd80918d8f39ee7c8af4025f0c87655`.
The other 152 hashes match exactly. This supersedes the earlier provisional
one-path/153-unchanged boundary. Retained full Core311/Qt188, native and frozen
package evidence keeps its original tested/built scope; unchanged Python Core
and Qt execution inputs do not require indiscriminate reruns. No all154/current
head equality or rebuilt-package claim follows. Final current-head CI/Windows,
privacy, LI01–21 evidence mapping and draft-PR review remain required before
Goal completion. Merge and deployment remain outside this clearance.


## Completion case-map audit

Generated SQL fixtures and fault injection are valid bounded functional proof;
there is no separate human-acceptance requirement for adversarial SQL failures.
A blanket Partial/synthetic-only label obscures the reviewed oracles. LI01/02
creation, canonical identity, reopen/relocation/copy and immutable mutation
checks; LI04–06 backup ordering/rollback and fail-closed malformed admission;
LI08 package binding/mismatch; LI14 active-catalog/no-scan guards; LI15 stale
file/epoch replies; and LI16 fault/cancel/cleanup tests provide bounded passes
within their actual executed scope. Offscreen Qt remains offscreen proof.

LI03 is not missing schema5 migration evidence. The full Core suite includes
`tests/test_bulk_curation.py::BulkCurationTests.test_real_v5_migration_preserves_single_journal_and_failed_v6_upgrade_original_backup`
(the method name is the stable evidence pointer): populated SCHEMA_V5 creation,
injected five-to-six failure, original and failed-backup snapshot equality,
successful retry from5 to current7, original-state backup equality, retained
rating/journal, empty new batch history and functional undo. Generated
empty/populated schema1–4 backup/restore tests and generated/genuine schema6
evidence complete the supported-version coverage. No duplicate schema5 test or
broad rerun is required merely because the public map omitted this method.

LI07 proves the migration reserves its writer before backup, a rival
BEGIN IMMEDIATE refuses, and committed WAL rows survive. It does not explicitly
exercise initialization while a rival already holds its writer; that direction
is a narrow possible oracle addition, not general mixed-process acceptance.
The documented close-other-instances limitation remains intact.

LI09/10 combine genuine legacy inspection/package immutability and generated
format/digest/truncation/version-pair rejection. Frozen old-client execution is
separate LI17 evidence, already cleared, and is not an unexecuted prerequisite
for LI10. LI11/12 genuine restore preservation and distinct legacy assignment,
LI13 pending/source/standalone guarded behavior, LI17 actual old Core consumer,
LI18 outputs/media/cache preservation, LI20 frozen build/native, and LI21 large
bounded getter trace are cleared within their recorded limits. None requires a
new universal platform or child-wide OS no-read claim. LI19 current-head hosted
and actual Windows audit remains the clear execution gate. Final publication
privacy and exact current-head diff review remain required.


The explicit LI07 pre-held-writer scenario is now independently cleared. The
private helper was reviewed before its single execution at SHA-256
`9d7e79c8c73358a5389cf7e419dbbf08bd5e69e0656a4300b021ecd46bebe015`.
A real writer held BEGIN IMMEDIATE with an uncommitted generated schema6 row
edit. The separate unchanged initializer used its default SQLite timeout and
refused with OperationalError/SQLITE_BUSY after 5.078 seconds (expected child
exit2); the holder retained its transaction/edit. Original committed bytes,
full dump/settings, absent identity and absent migration backup were checked
before releasing the writer. After rollback/release, initialization reached7,
retained the verified original6 backup and every original table row, preserved
journal/synchronous settings and exposed a stable canonical UUID on reopen.
Independent read-only database comparison confirms original6 backup/current7
versions, all original rows and the singleton canonical v4 UUID.

Outer execution exit0/no timeout, raw SHA-256
`a366299da8f11c5ab62ae05f9589816d1b4c9236038602c1e9ac553a2932adb6`,
result receipt SHA-256
`1926c534d1fec28a63b4364969173b106c11495b411c07a6338dd72de72478d1`,
and command receipt SHA-256
`62deae988b7c7a5bb33868461a848a69295a33550f46887869cb446ae8e248ac`
match independently. All154 current input hashes match pre/post and checkout.
This closes the explicit local contention oracle noted above; it does not
qualify general mixed-version or already-open-client safety. No public source,
test, full suite, native run or build was changed/repeated for this experiment.


## Final runtime-head and publication-candidate clearance

All30 exact-a9e2be9 checks and four actual workflows are terminal success.
The four Windows Core raw logs independently match public digests and311
runs/21 named skips each. Actual Windows Qt raw SHA-256
`8cab992f3f918d35d3c3ac590d9391ee1719c727b3015ff0d6cc3107068898d5`
independently matches Core311/21skips, Qt188/6skips, unsigned build565.736s,
artifact12120155585/33828094bytes and successful upload. Public Qt skip reasons
summarize the actual platform causes while omitting generated private paths.
Windows recovery worker is refusal-only, not qualified publication. Hosted
Tauri Rust tests/build are recorded separately from local Python13 evidence.

The final bounded LI01–21 map has accurate migration and Qt test pointers,
includes the reviewed pre-held-writer experiment and genuine legacy/current
Core/native evidence, and keeps unqualified platform/SDD/release claims outside
scope. All15 deployed output SHA-256/size/mode/mtime records match unchanged.
Public results, protocol, Task00/44/45/46, tracker and this review contain no
raw fixture UUIDs, local paths, credentials or raw logs. Exactly two of154
runtime inputs supersede the initial freeze;152 remain identical. The final
public evidence candidate is cleared for allowlisted documentation staging.
This clearance does not authorize merge/deployment or assert CI for a later
documentation commit; audit any newly triggered checks at that resulting head.
