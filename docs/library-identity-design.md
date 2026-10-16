# Stable library identity and compatible metadata recovery

Status: proposed design; independent Task46 review must clear this document
before runtime or schema implementation. Task44 owns implementation; Task45
owns acceptance. Base: PR22 merge d53d7d0675800ec8bd71536c1be0c6890ee4bd01.

## Contract and boundaries

A library has one immutable UUID independent of catalog location and source
paths. Reopening, relocating, backing up, and replacement restoring a modern
catalog preserve it. A copied/restored catalog is the same logical library;
this milestone does not make copies independently mergeable libraries or
coordinate their writers. No scanner, relink, scheduling, retention, portable
export/import, source-file writing, cache rebuilding, or deployment is added.
FR-LIB-002 and FR-RECOVERY-001/002/004/005 remain bounded Partial claims.

## Schema 7 and identity ownership

Schema 7 adds only `library_identity(singleton INTEGER NOT NULL PRIMARY KEY
CHECK(singleton=1), library_id TEXT NOT NULL UNIQUE)` plus authenticated
BEFORE UPDATE and BEFORE DELETE triggers that abort identity changes, and a
BEFORE INSERT trigger that aborts whenever a row already exists. The latter
explicitly blocks INSERT OR REPLACE from deleting/replacing the singleton
regardless of SQLite recursive-trigger settings. The
catalog owner inserts exactly one row with singleton=1 and canonical lowercase
RFC 4122 UUID version 4 text from `uuid.uuid4()`. SQL enforces singleton and
text shape and typeof(library_id)=text; Python validates exact canonical spelling, RFC variant/version,
and exactly one row. Missing, duplicate, malformed, unsupported-version or
altered identity declarations fail closed; they are never repaired on open.
The strict schema validator authenticates column/constraint/index signatures
and trigger bodies just as it does existing supported schemas. The identity
getter validates identity instead of generating it. APIs expose library_id
where useful to recovery reports; it is not a credential or access boundary.

`PRAGMA application_id` retains precisely its current meaning: zero for active,
DMRP for restore pending, all other values refused. Neither migration nor
identity reads clear it. Existing source review tokens and standalone-asset
browse-only behavior remain unchanged.

## Creation, migration, and rollback

Fresh initialization creates schema 7 and one UUID within its existing
transaction. Supported schemas 1–6 first authenticate their original schema
and state and receive the existing SQLite-consistent, verified original-state
backup, before any catalog change. Their existing migrations run in order,
then a 6→7 step creates the identity table/triggers and inserts one UUID.
Final schema, integrity, and identity validation precede commit. Any exception
rolls back schema/data/identity changes and preserves the verified original
backup. Existing historical backup files are never overwritten or removed.
A retried rolled-back migration may generate another UUID; no uncommitted
UUID was a successfully established identity. Successful reopen never changes
it. User rows, IDs, journal mode, synchronous policy and restore holds survive.

Initialization remains an explicit startup operation before app workers open.
Its BEGIN IMMEDIATE transaction serializes SQLite writers during migration;
it does not add a broker, advisory lock, cross-instance runtime agreement, or
safe simultaneous use of older application connections. Supported use requires
other application instances closed for upgrade. An older already-open process
may retain cached state: no new claim of safe mixed-version concurrent use.

## Package compatibility matrix

Keep the container header/magic and bounded framing unchanged. Emit package
version 2 for schema 7 with exactly the existing manifest fields plus
`library_id`, which must match the authenticated snapshot singleton. Continue
to accept exactly the deployed package version 1/schema 6 manifest with its
original exact key set. Reject mixed pairs, extra keys, mismatched UUIDs,
unsupported versions, malformed manifests, and failed digest/schema/integrity
checks. Validation selects schema from this explicit matrix rather than the
current SCHEMA_VERSION constant alone.

| Input | Inspection by new build | Restore by new build | Old schema-6 build |
| --- | --- | --- | --- |
| Live schemas 1–5 | Existing initialization upgrade path only | Not package inputs | Existing supported behavior |
| Live schema 6 | Verified upgrade to 7 on explicit initialization | Not package input | Continues existing use before upgrade |
| Live schema 7 | Strict schema/UUID validation; preserve UUID | Not package input | Refuses unsupported schema; cannot downgrade |
| Package v1/schema 6 | Read-only; identity absent, never generated | Verify original, migrate isolated stage to 7, assign fresh UUID and retain holds | Existing inspect/restore behavior |
| Package v2/schema 7 | Verify manifest/snapshot UUID equality | Preserve UUID exactly; retain holds | Refuses unsupported package version/schema |
| Other pair/version | Refuse unchanged | Refuse before publication | No new compatibility promise |

Inspection returns explicit schema and identity status (`legacy_absent` or
`stored`) and nullable library_id. It never mutates the selected package or
assigns a persistent identity. Backup accepts only initialized schema 7 and
emits v2; it never implicitly upgrades the live source. Older packages remain
byte-for-byte unchanged and may be restored repeatedly.

## Legacy restore semantics and verification

Each successful restore of a v1/schema-6 package assigns a fresh UUID in the
isolated unpublished destination. Repeated restores therefore have different
UUIDs. No historical library identity existed to preserve; the UI explains
this before restore and reports `assigned_legacy` afterward. No path-derived,
package-digest-derived, or externally remembered identity is invented.

The verified immutable legacy package serves as the original recovery point
for this isolated stage upgrade; do not call general initialize on the stage
and create an extra untracked migration-backup file. Use the same bounded
6→7 schema step inside the restore transaction, then set the existing pending
marker and per-source holds before committing and validating publication.
Legacy package snapshots are authenticated as schema 6 before mutation.
Modern restore does not migrate and must preserve the exact stored UUID.

Compare every preexisting user table/row before and after restore, excluding
only existing permitted source hold fields. For legacy upgrade, exclude only
the newly introduced library_identity table from this comparison and separately
verify its one valid UUID. For modern restore include the identity table in
that comparison. Verify asset/source/standalone counts and schema independently.
Never exclude another table merely because it is absent or unexpected: schema
authentication rejects unknown/missing tables first.

## Worker, publication, and Qt behavior

Retain the existing no-follow/private-local-storage adapter, process/resource
bounds, cancellation, stage ownership, close/sidecar checks, fsync and
no-replace publication. No final output is published before successful schema,
identity, hold and fingerprint verification. Cancellation/failure removes only
owned unpublished stages; uncertain publication preserves a possibly published
final and directs inspection. No identity registry or other side file exists.

Qt reports stored identity for modern inspected packages and preserved identity
on restore. For legacy packages it plainly reports absent identity and fresh
assignment on each restore, including the restore confirmation. Keep captured
file identity (device/inode), window epoch and stale-reply guards; library UUID
does not replace those freshness checks. No successful restore switches the
active catalog or starts scanning. UI identity text uses plain text rendering.

## Required acceptance and review

Generated fixtures cover creation, reopen and relocation stability; supported
legacy upgrades and pre-upgrade backup contents; failed migration rollback;
empty/duplicate/invalid UUID rows and altered declarations; unknown schemas;
modern package equality and deliberately mismatched manifest identity; unchanged
legacy package inspection; two legacy restores with distinct assigned IDs;
legacy pending catalogs and modern pending round trips; exact user-data
fingerprints; source and standalone holds; stale Qt results; cancellation,
owned cleanup, uncertain publication, and old-client refusal. Freeze source
before full Core/Qt suites and separate frozen/native/actual Windows evidence.
Existing Linux/local PCIe NVMe recovery storage limits remain explicit.
