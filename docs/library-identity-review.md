# Independent library identity review

Task46 owner: independent Sol. Date: 16 October 2026.

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
