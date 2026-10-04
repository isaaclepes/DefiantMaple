# Artist Gallery and Asset Management Platform

## Software Design Document v0.2 - Project DefiantMaple

| Document control | Value |
| --- | --- |
| Version | 0.2 |
| Date | 3 October 2026 |
| Status | Revised design specification; implementation and release acceptance are tracked separately |
| Replaces | SDD v0.1, dated 24 September 2026, as the forward-looking design specification |
| Product | DefiantMaple: a local-first desktop gallery and asset manager for artists |
| Delivery format | Markdown |
| Evidence baseline | Repository snapshot `1d4dc92c5a9aa4bd043daaf191581ef19937e611`; this revision does not certify subsequent CI or runtime results |

This document defines target product behavior and engineering acceptance. New and clarified requirements describe the intended product, not capabilities already delivered. Implementation status and release acceptance are recorded separately; the original PDF remains historical source material.

Examples are fictional design illustrations. Requirements for scanning, installation, external tools, and file mutation describe application behavior within the user's configured permissions; they do not authorize operations on user data merely by appearing in this specification.

### Changes from v0.1

- Incorporates the accepted Qt/PySide6 desktop direction, per-library catalogs, and conservative duplicate identity policy.
- Separates a useful explicit-scan gallery milestone from continuous watching and advanced source automation.
- Defines content revisions, replacement ambiguity, source relinking, offline browsing, and metadata conflict handling.
- Adds library backup, verified restore, portable export, and rebuild requirements.
- Separates review state, creative lifecycle, availability, and machine suggestions.
- Brings correct image display, external-editor integration, accessibility, ratings, favorites, and bulk catalog curation into the gallery plan.
- Specifies mutation boundaries, deletion meanings, interrupted-job outcomes, and recovery tests.
- Adds proposed numerical interaction budgets, resource governance, benchmark stop rules, and release qualification gates.
- Strengthens vector provenance, unknown-character handling, and recognition evaluation; similarity never establishes character identity or automatically changes asset metadata.
- Retains the original archive, naming, pipeline, similarity, video, and plugin scope with explicit delivery phases.

### Reading and requirement conventions

**Must** means required for the named delivery phase. It does not mean every later-phase feature belongs in the initial release. **Should** identifies a preferred behavior whose deferral needs a recorded reason. **May** identifies an optional capability. Tables assign phases; requirements that protect existing data apply whenever the corresponding operation is exposed.

The original `FR-INBOX-001..007`, `FR-IMP-001..012`, `SEC-ARC-001..006`, and `NFR-001..008` identifiers are retained. Clarifications and phase assignments supersede their v0.1 wording without implying implementation completion. New requirement families cover previously implicit contracts.

Proposed numerical targets are design candidates, not measurements or approved hardware commitments. A release cannot claim those targets until its named reference profile and acceptance results are recorded.

### Contents

1. [Executive summary](#1-executive-summary)
2. [Goals and non-goals](#2-goals-and-non-goals)
3. [Design principles](#3-design-principles)
4. [Primary user workflows](#4-primary-user-workflows)
5. [Architecture and recorded decisions](#5-architecture-and-recorded-decisions)
6. [Data model, identity, and provenance](#6-data-model-identity-and-provenance)
7. [Inbox and sources](#7-inbox-and-sources)
8. [Archive and data-export import](#8-archive-and-data-export-import)
9. [Archive and parser security](#9-archive-and-parser-security)
10. [Metadata, taxonomy, sidecars, and portability](#10-metadata-taxonomy-sidecars-and-portability)
11. [Gallery, search, collections, and accessibility](#11-gallery-search-collections-and-accessibility)
12. [Naming, rules, and automation](#12-naming-rules-and-automation)
13. [Local retrieval and character suggestions](#13-local-retrieval-and-character-suggestions)
14. [Duplicates and relationships](#14-duplicates-and-relationships)
15. [Media display, processing, and video](#15-media-display-processing-and-video)
16. [Transactions, undo, backup, and recovery](#16-transactions-undo-backup-and-recovery)
17. [External tools and extensibility](#17-external-tools-and-extensibility)
18. [Non-functional requirements](#18-non-functional-requirements)
19. [Performance and resource governance](#19-performance-and-resource-governance)
20. [Filesystem and platform compatibility](#20-filesystem-and-platform-compatibility)
21. [Verification and acceptance](#21-verification-and-acceptance)
22. [Phased delivery and current coverage](#22-phased-delivery-and-current-coverage)
23. [Risks and tradeoffs](#23-risks-and-tradeoffs)
24. [Decisions still requiring evidence or product selection](#24-decisions-still-requiring-evidence-or-product-selection)
25. [Assumptions and change control](#25-assumptions-and-change-control)

Appendices provide query/configuration examples, provenance examples, a v0.1 requirement crosswalk, and references.

## 1. Executive summary

DefiantMaple combines an image-first gallery with catalog metadata, review workflows, independently configured sources, duplicate grouping, safe organization, intelligent archive import, and optional local similarity search. It serves artists who work across ordinary folders, creative applications, generated outputs, reference libraries, removable storage, and network media.

The filesystem remains usable outside the application. Originals remain ordinary files. A local catalog supplies identities, metadata, provenance, relationships, workflow state, and searchable indexes. Portable export and optional sidecars preserve user-authored information if the operational database must be restored or rebuilt.

The first usable gallery supports explicit scans and catalog-only curation. Continuous watching is a separately accepted increment. Organization, extraction, and processing that write files follow a journal and recovery foundation. ML is optional and advisory: users can curate without a model or network connection.

The product is successful when an artist can find and review work quickly, understand where it came from, recover catalog information, and trust that background analysis will not silently reorganize, relabel, or remove media.

## 2. Goals and non-goals

### 2.1 Goals

- Browse, inspect, compare, and curate large libraries of supported images, then expand to animation, video, and specialist formats.
- Organize information through tags, structured entities, projects, ratings, favorites, review states, and manual or saved-query collections.
- Keep multiple source roots independent while presenting a unified Inbox.
- Support external editors and file managers without losing identities or provenance.
- Recover useful media and context from poorly named platform archives through safe previews, generic heuristics, and replaceable adapters.
- Preview rename, move, copy, conversion, sidecar, and processing plans before committing them.
- Preserve origins, revisions, transformations, and publication relationships.
- Offer local retrieval and character candidates with explicit uncertainty, versioned vectors, and confirmation.
- Export and restore irreplaceable metadata while rebuilding derived indexes and caches.
- Expose bounded jobs, progress, errors, cancellation, and recovery.
- Operate without a required account, telemetry, cloud service, or remote inference.

### 2.2 Non-goals for initial releases

- Cloud DAM collaboration, concurrent multi-user editing, and enterprise access controls.
- Professional image editing, nonlinear video editing, or replacement of Krita, Photoshop, GIMP, or Blender.
- Generative model training or mandatory generation/inference inside the application.
- Perfect identification of stylized characters or presentation of similarity as identity.
- Transparent live synchronization of a writable SQLite catalog between computers.
- Support claims for every image, video, project-file format, filesystem, or Linux distribution.
- A general plugin SDK or unattended filesystem mutation before their later-phase safety gates.

## 3. Design principles

| Principle | Required consequence |
| --- | --- |
| Local-first | Gallery, metadata, sources, and installed-model inference function offline. Downloads and external services are explicit optional actions. |
| Originals remain under user control | Analysis reads originals; processing normally creates a separate derivative. Source-writing commands require the applicable preview, authorization, and journal. |
| Stable identity | Paths and hashes are attributes, not sole identity. Uncertain reconciliation is surfaced rather than guessed. |
| Preview before mutation | Plans expose selected assets, destination effects, collisions, metadata effects, and reversibility before commit. |
| Recoverable operations | Durable state records what was planned and what completed. Crash recovery never invents a successful outcome. |
| Portable information | User-authored metadata, identities, collections, and relationships have a versioned export/restore path. |
| Filesystem interoperability | External edits, renames, disconnected storage, and changed mount points are normal conditions. |
| Explicit uncertainty | Recognition, readiness heuristics, inferred types, and ambiguous identity matches retain their evidence and uncertainty. |
| Bounded resource use | Jobs have concurrency, time, memory, and storage policies; visible work takes priority. |
| Progressive disclosure | Everyday browsing and curation remain simple; archive adapters, rules, and plugins live in appropriate advanced workflows. |
| Evidence before claims | Generated fixtures, hosted CI, real media, real shares, and reference-desktop results remain distinct evidence classes. |

## 4. Primary user workflows

### 4.1 Create, open, and recover a library

The user creates a local library or opens an existing one. Opening does not silently create a missing catalog or wait for a full scan. Unsupported schemas produce a clear refusal. A supported migration verifies a consistent backup before changing catalog state. The gallery opens from cached information; recovery work is separately visible.

The user can back up metadata, export a portable library manifest, restore to a new local catalog, and relink media roots without moving originals.

### 4.2 Source triage and Inbox

The user adds local or network media roots with an explicit existing-file policy. Initial scans are explicit. Later watching produces event hints and periodic reconciliation. Each source retains its identity, configuration, health, and provenance.

Readable files that pass readiness checks enter the configured review workflow. Files still changing remain pending. A disconnected source becomes unavailable; its assets, labels, and collections remain in the library.

### 4.3 Rapid catalog curation

The user reviews thumbnails and details, opens full-resolution previews, assigns tags/entities, rates or favorites items, changes review state, and adds assets to ordered collections. Bulk operations identify the selected asset IDs and can be undone. These actions do not rename, move, or delete media.

### 4.4 External creative work

The user opens a supported asset in a configured editor or reveals it in a file manager. Returning to DefiantMaple refreshes changed content through reconciliation. Atomic-save patterns and replacement ambiguity are handled conservatively. The application does not lock originals merely because a preview is open.

### 4.5 Safe organization

The user chooses assets and a naming/folder profile, reviews an immutable plan, resolves conflicts, then authorizes execution. The job validates preconditions again, commits through the journal, and reports completion, partial completion, or recovery needs. Undo first checks whether reversal remains safe.

### 4.6 Archive recovery

The user selects an archive. The importer inspects bounded metadata and selected content, detects adapters and manifests, proposes recovered types/names, and shows duplicates and warnings. Selected members are staged, fully validated as required, then committed through the transaction service. Original archive/member provenance remains intact.

### 4.7 Reference retrieval and relationships

The user searches metadata or requests Find Similar within a compatible embedding space. Character candidates can be confirmed, rejected, or left unknown. Originals, edits, upscales, crops, frames, alternates, and published derivatives remain linked by explicit relationships.

## 5. Architecture and recorded decisions

### 5.1 Service boundaries

```text
Qt/PySide6 desktop UI
  |
Application command and query services
  +-- Library / Asset / Revision services
  +-- Source / Inbox / Reconciliation services
  +-- Metadata / Tag / Entity / Collection services
  +-- Import / Rule / Pipeline services
  +-- Job / Transaction / Undo / Recovery services
  +-- Backup / Restore / Export services
  |
Bounded media and analysis workers
  +-- Thumbnail / Preview / Metadata extraction
  +-- Hash / Perceptual duplicate analysis
  +-- Optional Embedding / Recognition
  +-- Optional FFmpeg / Specialist-format adapters
  |
Local persistence
  +-- Per-library SQLite catalog and durable journals
  +-- Versioned vector store/index
  +-- Derived thumbnail / analysis caches
  +-- Verified backups / export packages
  +-- Optional sidecars
  |
Ordinary media files, archives, configured external tools
```

UI widgets submit typed commands and bounded queries. They do not bypass validation to mutate source files or start arbitrary processes. Domain code remains independent of the UI toolkit. Media decode, hashing, archive parsing, and inference stay outside the GUI thread.

A worker process contains failures but is not automatically an OS sandbox. The product must describe which resource and access limits it actually enforces on each platform.

### 5.2 Recorded decisions

| Decision | Status and boundary |
| --- | --- |
| Desktop client | Qt/PySide6 and Qt Widgets, accepted for Phase 1 through ADR 0001. Exact dependency versions follow the tested release manifest rather than a permanent SDD pin. |
| Alternative client | Tauri remains a comparison prototype and first fallback if documented packaging, licensing, accessibility, or native-display gates invalidate the Qt choice. |
| Domain implementation | Existing Python catalog/media interfaces remain the foundation. UI-independent services preserve future replacement options. |
| Catalog topology | One operational catalog per library. Cross-library search is deferred. |
| Catalog placement | Supported live catalogs reside on local storage. Media and verified closed backup/export packages may reside elsewhere, subject to their access policy. |
| Exact duplicates | Matching bytes at different ordinary paths remain distinct assets by default. Grouping does not merge metadata or discard origin history. |
| Recognition | Optional local retrieval and review assistance; no automatic metadata mutation or identity certification from scores. |
| Mutations | Central transaction service with preview, precondition validation, durable journal, and recovery before source-writing features. |
| Vector persistence | A versioned adjacent store is acceptable. A SQLite vector extension requires cross-platform packaging and compatibility evidence before adoption. |

The selected stack does not establish accessibility, signed distribution, clean-machine installation, memory budgets, or color correctness. Those remain release gates.

### 5.3 Local library and concurrency contract

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-LIB-001 | 1a | Create and open libraries explicitly. Refuse missing existing catalogs, unsupported versions, and invalid supported schemas without silently replacing them. |
| FR-LIB-002 | 1a | Store catalog identity separately from source-root paths. Catalogs and caches shall not be placed inside scanned media roots by default. |
| FR-LIB-003 | 1a | Coordinate application writers and migration/restore operations. A second application instance must either share the documented broker or enter an explicit read-only/refused state; it must not independently run conflicting jobs. |
| FR-LIB-004 | 1a | Distinguish live catalog storage from NAS/removable media roots. Do not advertise writable catalogs on SMB/NFS or active file-sync folders as supported without a separate storage design and acceptance. |
| FR-LIB-005 | 1a | Provide verified metadata backup and restore; see §16. |
| FR-LIB-006 | 1a | Provide versioned portable catalog export and import into an isolated destination; retain stable IDs and require explicit conflict resolution. |
| FR-LIB-007 | 1a | Rebuild derived caches/indexes without discarding user-authored catalog information. A filesystem-only rescan must explain which information cannot be reconstructed. |

SQLite WAL is not a network-filesystem solution. If WAL is used locally, its locking, checkpoint, runtime-version, backup, and durability contract must be independently tested. This document does not direct a change to current journal or synchronous settings.

## 6. Data model, identity, and provenance

### 6.1 Logical records

These are domain concepts; they do not prescribe an immediate migration or claim all tables already exist.

| Record | Purpose |
| --- | --- |
| Library | Stable library ID, catalog schema, export schema, source configuration, and release compatibility. |
| Asset / MediaAsset | Stable asset ID, current path/location, media type, review state, creative stage, availability, and current content fingerprint. |
| AssetRevision | Observed content change, prior/new fingerprints, observation time, identity decision, and analysis invalidation. Historical originals are retained only if an explicit revision-storage policy exists. |
| AssetProvenance | One-to-many origin and transformation records, including source, archive/member, import job, adapter, and evidence. |
| Source | Stable source ID, current root mapping, mode, health, existing-file policy, profile, and reconciliation state. |
| Tag | Canonical name, aliases, hierarchy, and optional groups/rules. |
| Entity / Character | Typed structured identity; character records add reference sets, aliases, ownership notes, and recognition configuration. |
| Annotation | Region or media time range with versioned coordinate space, tags/entities, assignment source, and confirmation state. |
| Collection | Stable ID, manual ordered membership or versioned saved query. |
| AssetRelationship | Typed connection such as derived_from, crop_of, version_of, or published_as. |
| FieldValue / Conflict | Value, authority/source, revision, imported candidate, tombstone, and unresolved-conflict state. |
| Analysis / Vector | Input fingerprint, compatible embedding-space identity, result, runtime provenance, and stale/valid status. |
| Job / Transaction / Undo | Planned work, completed effects, durable checkpoints, errors, recovery, and reversal preconditions. |
| ImportJob | Archive identity, preview plan, item decisions, validation, results, and report. |

New assets receive UUIDs. Supported legacy IDs remain intact during migration; normalization is not a reason to rewrite established identities. APIs and UI selections use IDs, not mutable row positions.

### 6.2 Identity and revision behavior

| Event | Target behavior |
| --- | --- |
| Unchanged file rescanned | Retain ID, metadata, and provenance; avoid unnecessary analysis. |
| New path with identical bytes | Create a distinct asset by default and expose exact-duplicate grouping. |
| Unique verified external rename | Retain ID and add path-change provenance. Use conservative filesystem identity/fingerprint or full-hash evidence. |
| Application-authorized move | Retain ID through the transaction record, including a cross-volume copy-verify-delete implementation. |
| Ordinary edit of a known asset | Retain ID when continuity is established; record the content revision, invalidate derived results, and mark Needs Review. |
| New content or ambiguous replacement at an old path | Preserve prior information and flag an unresolved identity/revision decision. Do not silently certify old labels or provenance for unrelated new content. |
| Ambiguous move, copy, or inode reuse | Do not auto-merge. Present candidates for explicit reconciliation; retain prior records. |
| Source unavailable | Preserve catalog records and cached information; record unavailable health. |
| Healthy complete scan confirms a missing file | Mark missing, without deleting the asset, metadata, or collection membership. |
| Source root relinked | Validate the proposed mapping and show ambiguities before applying it; never rewrite paths from a prefix alone. |

An editor's atomic save can change filesystem identity while remaining an edit. An unrelated replacement can occupy the same pathname. Neither pathname, inode, quiet interval, nor hash alone resolves every case.

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-ID-001 | 1a | Preserve stable IDs through supported edits/verified moves and retain ambiguous prior records. |
| FR-ID-002 | 1a | Keep exact duplicate grouping separate from asset merging. Explicit merges, if later offered, must preserve every origin and resolve metadata conflicts. |
| FR-ID-003 | 1a | Record content changes and invalidate thumbnails, perceptual signatures, vectors, and automatic suggestions bound to the old content. |
| FR-ID-004 | 1b | Offer reconciliation actions: retain as revision, create separate asset, or relink a prior asset. Show the effects on metadata, collections, and relationships. |
| FR-ID-005 | 1a | Provide source relinking with preflight and cancellation. Unverified matches remain unresolved rather than overwriting associations. |
| FR-ID-006 | 1a | Keep review, creative lifecycle, availability, and analysis status independent. |

The current scanner already preserves IDs in its documented supported cases and records changed fingerprints. The full replacement/revision and user-facing reconciliation model above remains target behavior; it is not a claim that the present schema implements it.

### 6.3 Provenance

Preserve original source/archive/member names, archive content identity, import-job identity, adapter/version, original and reconstructed names, and observation/import timestamps. Record whether type/name/context came from a manifest, a signature, a decoder, a heuristic, or a user decision.

Imported timestamps retain their original timezone/uncertainty when known; filesystem modification time is not automatically artwork creation time. Raw adapter values remain distinguishable from normalized user-facing fields.

Transformation history links inputs, parameters, tool/version, and outputs. A derived asset does not overwrite the parent's history. Additional provenance for an explicitly reused asset is append-only unless the user edits an erroneous record through an audited action.

## 7. Inbox and sources

### 7.1 States

| Dimension | Values and meaning |
| --- | --- |
| Review state | New, Needs Review, Reviewed, Organized, Ignored, Error. Organized is a review declaration, not proof that a filesystem move occurred. |
| Creative stage | Reference, WIP, Review, Final, Published, Archived, Rejected; optional and independent of review state. |
| Source health | Scanning, Paused, Offline, Permission Denied, Error; Watching only when a functioning watcher is active. |
| Asset availability | Available, Missing after a healthy complete pass, Unavailable due to source health, or Unresolved identity. |
| Analysis state | Pending, Running, Valid, Stale, Unsupported, or Failed. |

The Inbox is a virtual view of New, Needs Review, and Error items, with filters to isolate errors. It is not a physical folder. The query alias `workflow:inbox` maps to that review-state set; `stage:wip` refers to creative lifecycle.

### 7.2 Original source requirements, clarified

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-INBOX-001 | 1a registration; 1b watching | Support multiple independent sources with enable/pause/rescan controls and no small arbitrary product cap. Source lists and scans remain bounded; practical scale is stated in acceptance. Do not label explicit scans as continuous watching. |
| FR-INBOX-002 | 1b basic filters; 2 advanced profiles | Support recursion, include/exclude patterns, and media filters. Phase 2 adds initial metadata, project defaults, and processing bindings; Phase 4 may add explicit recognition settings. Defaults must not invoke unapproved media mutation or automatic recognition assignment. |
| FR-INBOX-003 | 1a | Require Inbox, Already Reviewed, or Ignore Until Modified policy when adding a source. Preserve an ignored baseline through temporary disappearance. |
| FR-INBOX-004 | 1a readiness; 1b event debounce | Require matching size/timestamp observations and readable, fingerprint-verified content. Treat quietness as a readiness heuristic, not proof that a producer has finished. Changes during analysis invalidate/requeue the result safely. |
| FR-INBOX-005 | 1a; Watching in 1b | Show truthful source health. An unavailable or incomplete scan never establishes asset deletion or missing-file reconciliation. |
| FR-INBOX-006 | 1a | Support all six review states independently of location and creative stage. |
| FR-INBOX-007 | 2 before file mutations with watchers | Correlate application file events to transaction IDs. Suppression prevents duplicate discovery without hiding unrelated external changes; periodic reconciliation repairs missed events. |

### 7.3 Scanning and watcher contract

The most-specific enabled source owns an overlapping path. Ties must be rejected or resolved by a persisted deterministic rule. Disabled sources do not own new discovery. Changing overlap ownership requires a preview of affected records.

Default scans do not traverse symbolic links. Hard links and future link traversal need an explicit capability and cycle/escape policy; shared filesystem identity must not accidentally merge separate paths.

A canceled or failed pass keeps completed safe observations but does not reconcile missing files. A fresh pass uses fresh enumeration; stale in-memory cursors cannot be applied to a different inventory. Large scans must have a bounded inventory strategy or explicitly documented limits.

Native notifications are hints. Events may be duplicated, reordered, or lost. Watchers must handle overflow and interrupted roots through a healthy reconciliation pass. Pause, restart, and application exit have explicit job/checkpoint behavior.

Real generated-file SMB/NFS disconnect/reconnect evidence is required before claiming support for continuously watched network sources. Synthetic loss tests are useful but insufficient for that claim. Local watcher acceptance can be scoped independently rather than blocked by every possible remote environment.

### 7.4 Fictional profile illustration

```yaml
name: Generated Art
source_root: D:/ExampleArt/output
mode: explicit_scan
recursive: true
existing_file_policy: inbox
exclude:
  - "*.partial"
  - "*.tmp"
on_discovery:
  read_generation_metadata: true
  hash: true
  thumbnail: true
  recognition_suggestions: false
  automatic_metadata_assignment: false
  processing_pipeline: null
  filesystem_mutation: false
```

Recognition and processing bindings require their later-phase configuration and permissions; this example enables neither.

## 8. Archive and data-export import

Platform export filenames and extensions are hints. Import must remain useful without a known adapter and must preserve source context when names are reconstructed.

### 8.1 Import lifecycle

```text
Selected archive
  -> Bounded inspection / archive fingerprint
  -> Adapter detection + generic fallback
  -> Candidate enumeration / bounded manifest parsing
  -> Signature hints + isolated decode/probe where supported
  -> Context / relationships / proposed names
  -> Exact duplicate and destination conflict analysis
  -> Editable user preview
  -> Immutable accepted plan
  -> Revalidate archive, destinations, and limits
  -> Stage selected members and validate full content
  -> Journaled item commits
  -> Catalog / provenance finalization
  -> Report or recovery queue
```

Inspection must not imply that a prefix read verified a member CRC or guaranteed successful decoding. Archive identity binds the accepted plan to the exact input; replacement or modification invalidates the plan.

### 8.2 Original import requirements, clarified

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-IMP-001 | 3; inspection spike in 0 | Inspect bounded archive metadata and selected prefixes before extraction. Show counts, sizes, nesting, manifests, candidates, and warnings. |
| FR-IMP-002 | 3 | Distinguish signature hints from verified decoder/probe results; misleading extensions are not authoritative. |
| FR-IMP-003 | 3 | Propose a supported detected extension while retaining original names and detection evidence. Unsupported content is reported rather than guessed. |
| FR-IMP-004 | 3 | Define versioned platform-adapter inputs/outputs. Adapters correlate manifests, object IDs, contextual records, and relationships without performing their own file commits. |
| FR-IMP-005 | 3 | Offer generic enumeration, bounded probing, optional metadata extraction, and user-controlled naming when no adapter matches. |
| FR-IMP-006 | 3 | Reconstruct candidate names from reliable metadata with deterministic fallbacks; preserve original member paths exactly. |
| FR-IMP-007 | 3 | Parse supported JSON/JSONL/CSV/HTML manifests within size/depth/record limits. Preserve unrecognized context in the report or an explicitly retained package. |
| FR-IMP-008 | 3 | Show original path, inferred/verified type, proposed destination, metadata candidates, duplicates, warnings, and item overrides before accepting a plan. |
| FR-IMP-009 | 3 exact; 4 perceptual/embedding assistance | Allow Skip, Keep Both, or explicit association with an existing asset. Similarity alone never proves a duplicate. Any reuse preserves origin history and resolves metadata conflicts. |
| FR-IMP-010 | 3 | Save import profiles with adapter versions, limits, naming rules, and approval policy. A profile does not bypass revalidation. |
| FR-IMP-011 | 3 | Produce a report covering imported, skipped, duplicate-associated, renamed, type-corrected, failed, suspicious, and recovery-required items. |
| FR-IMP-012 | 3 | Detect nested archives without automatic expansion. Opt-in nesting shares one enforced job-wide depth/byte/member budget. |

Canceled and failed jobs retain explicit committed-item and uncommitted-item states. A multi-file import across filesystem and database boundaries must not claim universal atomicity. The recovery contract in §16 governs rollback and reconciliation.

## 9. Archive and parser security

### 9.1 Original security requirements, clarified

| ID | Phase | Requirement |
| --- | --- | --- |
| SEC-ARC-001 | 0 inspection; 3 extraction | Reject escapes, absolute/drive/UNC paths, unsafe traversal, NUL/control characters, target-volume collisions, and unsupported alternate-stream forms. Validate destinations again at commit and prevent link/reparse-point races using platform-appropriate handles or a constrained staging design. |
| SEC-ARC-002 | 0/3 | Enforce archive, directory, member-count, expanded-byte, per-member, ratio, nesting, time, memory, and staging-space limits. Limits apply to actual output as well as declared sizes. |
| SEC-ARC-003 | 0/3 | Reject archive links/special files or retain them as inert metadata by default. Advanced link behavior requires explicit permission and containment guarantees. |
| SEC-ARC-004 | 0/3 | Never execute imported members, render active manifest scripts, evaluate data as code, or load unsafe serialized objects automatically. Opaque files need explicit selection. |
| SEC-ARC-005 | 3 after Phase 2 safety gate | Stage and validate content; journal each commit boundary. Every completed or interrupted item must have a deterministic resume, rollback, or reconcile outcome. |
| SEC-ARC-006 | All | Keep media, prompts, metadata, hashes, vectors, and imported context local unless the user explicitly enables a service with a stated data scope. |

### 9.2 All media and manifest parsers

| ID | Phase | Requirement |
| --- | --- | --- |
| SEC-PARSE-001 | 1a onward | Treat media, sidecars, manifests, plugin outputs, and model files as untrusted inputs. Use bounded parsing, version checks, and safe data formats. |
| SEC-PARSE-002 | 1a onward | Isolate decode/probe failures, enforce cancellation/timeouts, and apply real process memory/CPU controls where available. Publish enforcement gaps rather than describing a subprocess as a sandbox. |
| SEC-PARSE-003 | 1a onward | Escape displayed filenames/metadata and avoid path or prompt disclosure in public diagnostics. Local detailed reports remain private. |
| SEC-PARSE-004 | 3 | Bound central-directory parsing before relying on a post-parse member-count check; add fuzz and adversarial fixtures. |

Default archive limits must be configurable and recorded in the preview/report. Current prototype limits are evidence of a conservative inspection spike, not a permanent product-size promise.

## 10. Metadata, taxonomy, sidecars, and portability

### 10.1 User-facing information

Support tags and aliases, structured entities, title/description, rating, favorite, source URL, medium/software, project/client, creative stage, attribution/rights notes, and generation metadata. Generation fields include model/checkpoint, prompt, negative prompt, seed, and parameters with extractor provenance.

Core entity categories remain Character, Artist, Project, Location, Client, and Franchise. Rich character reference fields arrive in Phase 4. Plugin-defined types arrive only through a later versioned extension contract.

### 10.2 Metadata authority

The catalog is the operational authority for explicit in-application edits. Embedded metadata, manifests, and sidecars are imported candidates with source/version information. They do not silently overwrite newer user edits.

| Situation | Default resolution |
| --- | --- |
| First import, no user value | Import a supported value with its origin recorded. |
| Same external value observed again | Keep it without generating a duplicate conflict. |
| External change, no intervening user edit, known synchronization base | Accept as a new sourced revision if the field policy permits. |
| User and external source both changed since the base | Preserve both and show a conflict; do not choose by timestamp alone. |
| No trustworthy synchronization base | Show a candidate/conflict rather than claim a safe three-way merge. |
| User removed an imported label/value | Preserve the removal as a tombstone or explicit override so rescanning does not silently re-add it. |
| Extraction or inference proposes a value | Keep proposal separate until the applicable explicit user action. |
| A field cannot be written safely to the media format | Keep it in the catalog/sidecar; never rewrite the original as a fallback. |

Field ownership, import policies, and synchronization versions must be inspectable. A user can choose a value, retain multiple values where the field supports them, or keep the conflict unresolved.

### 10.3 Requirements

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-META-001 | 1a | Persist tags, aliases, acyclic hierarchy, six entity categories, and explicit assignments with stable IDs. |
| FR-META-002 | 1a | Provide title/description, ratings, favorites, rights/attribution notes, and independent creative stage with explicit editing and filtering. |
| FR-META-003 | 1a basic; 2 synchronization | Preserve field source and user overrides. Imported candidates and conflicts shall be visible; synchronization must use a recorded base/version. |
| FR-META-004 | 1a | Support bulk catalog edits over captured asset IDs with an effects preview, atomic logical outcome, and catalog undo. Do not retarget a changed selection mid-dialog. |
| FR-META-005 | 2 | Offer versioned JSON sidecars containing stable identity and rich selected metadata. Sidecars are opt-in and written through the transaction service. |
| FR-META-006 | 2 | Read/write safe supported embedded fields through explicit policy; retain unsupported fields and originals. Optional XMP/YAML adapters must declare fidelity and conflict behavior. |
| FR-META-007 | 2 | Add tag groups, implication/exclusion rules, and taxonomy merge/delete with explicit assignment previews. Implication must not silently rewrite stored labels when a hierarchy is edited. |
| FR-META-008 | 1a export; 2 sharing presets | Allow selected-field export/redaction of locations, clients, generation prompts, and other sensitive information. Redaction applies to an export/derivative, not the original. |

### 10.4 Sidecars and export

The initial sidecar mode is per-asset JSON with a documented schema and association by stable ID plus content fingerprint. Adjacent sidecars are written only where the user enables them and has write access. Managed sidecar storage is available for read-only media sources. Per-folder manifests and XMP adapters are later options, not simultaneous initial requirements.

A rename/move plan includes its sidecar association. Sidecar files and application caches are excluded from media discovery by default. Unknown fields from a newer compatible export/sidecar are preserved when safe; unsupported major versions are refused without partial import.

Portable export contains library/asset IDs, metadata, taxonomy, collections/order, relationships, provenance, source mappings, profiles/rules, schema versions, and relevant model/configuration identities. It clearly distinguishes metadata-only export from a media-inclusive package. Credentials and machine-specific executable paths are excluded; restored active rules and sources remain paused until reviewed.

## 11. Gallery, search, collections, and accessibility

### 11.1 Gallery and curation requirements

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-UX-001 | 1a | Provide virtualized grid/detail views, adjustable thumbnail size, aspect-preserving/cropped modes, and lazy loading. |
| FR-UX-002 | 1a | Provide full-resolution inspect, zoom, pan, fit-to-window, fullscreen, transparency background choice, and explicit unsupported/error display. |
| FR-UX-003 | 1a | Support predictable keyboard review, configurable shortcuts, multi-selection, ratings/favorites, and visible selection/focus. |
| FR-UX-004 | 1a | Provide manual ordered collections with stable membership through offline/missing media, explicit deletion of the collection only, and bounded paging. |
| FR-UX-005 | 1a basic; 2 advanced | Basic search shall include text/path, tags, entities, review state, source, media type, rating, and favorite. Phase 2 adds the full versioned query language and saved-query collections. |
| FR-UX-006 | 1a | Sort by supported basic fields with deterministic tie-breaking. Filtering or refresh shall not silently retarget commands to a different asset. |
| FR-UX-007 | 1a | Show cached previews and metadata while originals are unavailable; label cache freshness and disable operations requiring unavailable content. |
| FR-UX-008 | 1a | Offer side-by-side comparison and Open in Editor / Show in Folder through the configured command service. |
| FR-UX-009 | 1b/2 | Add tag/entity/project browsers, folder tree, filmstrip/list/timeline views, and saved workspace state as scoped increments. Masonry is optional. |
| FR-UX-010 | 1a | Provide keyboard-only navigation, accessible names/roles/states, logical focus order, scalable text, high-DPI behavior, and non-color-only status cues. |

Accessible behavior must be tested with the custom virtual gallery, not inferred from the toolkit's support. Selection, sorting, background progress, dialogs, and errors require meaningful assistive-technology announcements.

### 11.2 Query contract

The full grammar defines quoted strings, field types, comparisons, parentheses, and precedence: NOT, then AND, then OR. Invalid fields/types/expressions produce a helpful parse error rather than silently broadening the query. Search values never become executable SQL.

Use `review:` and `stage:` to distinguish review and creative lifecycle. Preserve `workflow:inbox` as a documented compatibility alias. Saved searches store the query grammar version, display name, and parameters; they store no frozen asset list unless explicitly converted to a manual collection.

Similarity queries bind a model/weights/preprocessing/metric identity. Results from incompatible spaces cannot be compared as if they shared a scale.

## 12. Naming, rules, and automation

Templates support metadata variables, defaults, conditional sections, date formatting, sequence scopes, slug/case transforms, bounded regular-expression operations, collision policies, and destination-volume normalization.

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-RULE-001 | 2 | Produce deterministic filename/folder proposals with original and resulting names shown. Missing variables and ambiguous multi-entity values require defaults or a user choice. |
| FR-RULE-002 | 2 | Preview collisions against the complete batch and existing destination contents using destination-volume semantics. |
| FR-RULE-003 | 2 | Trigger rules on explicit invocation, discovery, import, supported metadata change, or schedule only under a documented enabled policy. |
| FR-RULE-004 | 2 | Support conditions over source, type, dimensions, supported metadata, tags/entities, and duplicate state. Analysis scores retain their evidence/type and cannot stand in for confirmed labels. |
| FR-RULE-005 | 2 | Separate catalog actions, derivative-processing actions, and source-writing actions. Source mutations require preview/approval unless a separately reviewed explicit policy permits a bounded action. |
| FR-RULE-006 | 2 | Version rule definitions, prevent reentrant loops, record applied versions and effects, and offer dry-run for every rule. |

New rules and restored rules default to disabled/dry-run. Processing or filesystem actions are never implied by registering a source. Automatic recognition assignment is outside this baseline.

Examples of triggers/actions in v0.1 remain planned scope, including pipelines, sidecar creation, and configured external tools. Arbitrary code execution is not a template feature.

## 13. Local retrieval and character suggestions

### 13.1 Scope and behavior

Embeddings support Find Similar, alternate-generation discovery, and candidate character retrieval. Whole-image composition, style, background, outfit, and identity can all influence a result; the UI must not label an uncalibrated ranking score as a probability of identity.

```text
Asset revision or selected region
  -> Explicitly enabled local model
  -> Versioned vector with input fingerprint
  -> Compatible reference/search index
  -> Ranked candidates or Unknown/Uncertain
  -> User confirms, rejects, or leaves unresolved
  -> Explicit reference-set curation
```

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-REC-001 | 0 benchmark; 4 product | Inference is optional, local, CPU-usable, and bounded. GPU acceleration is optional and has a CPU fallback or a clear unavailable state. |
| FR-REC-002 | 4 | Show candidate evidence, model/space identity, raw score meaning, and confirmation state: Suggested, Confirmed, Rejected, or Manually Assigned. |
| FR-REC-003 | 4 | Include Unknown/Uncertain and lookalike/absent-character behavior; never force a nearest candidate into an identity label. |
| FR-REC-004 | 4 | Store per-vector model name, immutable revision, weights digest/license reference, method, preprocessing identity, input hash/revision/region, dimension, encoding, normalization, and distance metric. |
| FR-REC-005 | All inference | Writing vectors or suggestions must not automatically change tags, entities, review state, filenames, paths, or other asset metadata. User confirmation is an explicit catalog command. |
| FR-REC-006 | 4 | Support manual character regions first; automatic regions need their own evaluated detector contract. Region coordinates bind orientation and input revision. |
| FR-REC-007 | 4 | Separate approved references, confirmed appearances, and rejected examples. A confirmation does not silently add a reference or train a model. |
| FR-REC-008 | 4 | Invalidate results on content/preprocessing changes; isolate incompatible model generations and support explicit background re-embedding. |

The v0.1 optional high-confidence auto-tag concept is deferred outside this baseline. It requires a future explicit policy revision, quality/calibration evidence, and user authorization; score thresholds alone are insufficient.

### 13.2 Character records

Character records include names/aliases, ownership and attribution notes, description, canonical tag mapping, approved reference assets/regions, confirmed appearances, rejected examples, and versioned recognition profiles. Multiple characters may occur in one asset.

Canonical tags may be represented as a derived view of an explicit entity assignment. Materializing those tags is a user-configured catalog operation, not a consequence of a model suggestion.

### 13.3 Model decision and quality gate

The checked-in benchmark recommends pinned DINOv2-small only as the next retrieval-prototype baseline: 384 dimensions and about 88.25 MB of measured weights. It is not an approved character classifier or installer dependency. Its generated six-identity fixture does not establish real-reference quality.

A product recommendation requires a licensed/artist-authorized human-labeled evaluation with style shifts, lookalikes, unknown identities, multiple characters, and held-out queries. Report Recall@1/5, ranking metrics, false matches/unknown behavior, per-style results, CPU latency, full-process memory, installed footprint, and compatible cross-platform behavior. Tune thresholds on a separate development set.

Download size, runtime installation size, vector-store size, Python/native memory, and optional GPU memory are distinct measurements. Model code, weights, and runtime dependency licenses are independently reviewed.

## 14. Duplicates and relationships

Exact SHA-256 grouping, perceptual near-duplicates, and embedding-related results are separate categories. A visually similar item is not necessarily a duplicate, derivative, or the same character.

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-DUP-001 | 1a | Group exact hashes without merging or deleting assets; display distinct locations and provenance. |
| FR-DUP-002 | 4 | Offer versioned perceptual hashes and embedding-assisted families with their method/evidence visible. |
| FR-DUP-003 | 3/4 | Preview Keep Both, Skip Import, Associate Origin, Link Relationship, or Replace decisions with metadata and source effects. Replace requires the mutation contract. |
| FR-DUP-004 | All duplicate flows | Never delete or overwrite solely from similarity. Explicit choices preserve history and obey journal/recovery rules. |
| FR-REL-001 | 2 basic; 5 expanded | Record typed relationships: derived_from, upscale_of, crop_of, edit_of, frame_of, alternate_of, version_of, published_as. Retain stable references through moves or unavailability. |
| FR-REL-002 | 2/5 | Show direction, source, and provenance of relationships; reject invalid self-links and prohibited derivation cycles while allowing legitimate peer associations. |

Metadata conflict resolution is required before an explicit asset merge. Archive-origin association with an existing asset appends a provenance record; it does not imply that every same-byte file should share one asset ID.

## 15. Media display, processing, and video

### 15.1 Initial format contract

| Format class | Initial gallery target | Later expansion |
| --- | --- | --- |
| PNG, JPEG, static WebP | Validated decoding, orientation where applicable, color-aware previews, alpha handling, dimensions, and metadata/error display | Processing and richer metadata adapters |
| GIF, APNG, animated WebP | Explicit animation badge and a documented poster/first-frame policy only when the tested decoder supports it | Playback, frame inspection/export, animation metadata |
| TIFF, high-bit-depth/HDR images | Support only the specifically tested modes; otherwise explicit unsupported status with external-open option | Tested conversion/tone mapping and precision-preserving workflows |
| MP4, WebM and other video | Catalog/opaque metadata status or supported probe only; no playback promise | FFmpeg probing, posters, scrub/hover previews, frame/time annotations |
| PSD, KRA, SVG, RAW, Blender and other project files | Explicit unsupported/opaque handling or a narrowly tested inert thumbnail provider | Versioned specialist providers with safety and fidelity limits |

This table is a target support policy, not a statement that the present PNG-focused implementation decodes every listed format. The release manifest enumerates exact accepted modes, tested decoders, limits, and fallback behavior.

### 15.2 Display fidelity

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-MEDIA-001 | 1a | Respect orientation consistently across thumbnail, full preview, region selection, and comparison. Retain the source unchanged. |
| FR-MEDIA-002 | 1a | Apply documented color-profile handling for supported formats. State assumptions for untagged content and show invalid/unsupported-profile status rather than silently promising faithful color. |
| FR-MEDIA-003 | 1a | Show alpha against selectable checker/light/dark backgrounds and maintain correct aspect ratio and high-DPI scaling. |
| FR-MEDIA-004 | 1a | Key derived previews by asset ID, content fingerprint, size, cache schema, decoder/color-transform version, and output policy. Publish verified cache files atomically. |
| FR-MEDIA-005 | 2 processing; 5 expansion | Prefer new derivative outputs for resize/crop/rotate/flip/convert/compress/alpha/contact-sheet operations. Record inputs, parameters, tools, and output hashes. |
| FR-MEDIA-006 | 5 | Add frame/sprite-sheet tools and FFmpeg metadata, posters, scrub previews, trimming/transcoding, and scene/frame extraction through bounded jobs. |
| FR-MEDIA-007 | 2 export; 5 expansion | Provide reusable export/processing presets, including privacy-aware metadata choices and destination constraints. |

Display transforms are not destructive edits. Tone-mapped HDR or converted high-bit-depth previews must be labeled as previews, not archival conversions. Video recognition, if introduced, binds sampled frames/time ranges to versioned analysis and remains advisory.

## 16. Transactions, undo, backup, and recovery

### 16.1 Distinct recovery mechanisms

| Mechanism | Protects | Does not imply |
| --- | --- | --- |
| Catalog transaction | Logical metadata consistency | Atomic multi-file filesystem changes |
| Mutation journal | Known planned/committed effects and recoverable boundaries | Guaranteed rollback after arbitrary external edits or storage loss |
| Catalog undo | Reversal of explicit user edits with preconditions | Reversal of every imported observation |
| Verified backup | A consistent recoverable catalog snapshot | Backup of original media unless selected |
| Portable export/sidecars | Rebuild of supported user information | Recovery of fields that were never exported |
| Cache/vector rebuild | Derived data | Restoration of manually authored metadata |

### 16.2 Mutation state machine

```text
Draft plan -> Preview accepted -> Preconditions revalidated
  -> Journaled pending item -> Staged/verified output
  -> Filesystem effect committed -> Catalog finalized -> Complete

Any interruption -> Recovery required
  -> Validated resume, rollback, or explicit reconciliation
```

Plans bind asset IDs, input fingerprints, destination-volume semantics, intended metadata effects, rule/tool versions, and collision decisions. Journal writes precede source changes and record enough evidence to inspect an interrupted boundary.

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-TXN-001 | 2 before any source-writing API | Plan, preview, validate, journal, and execute source mutations through one application command boundary. |
| FR-TXN-002 | 2 | Recheck source/destination preconditions immediately before commit. A changed file, collision, lost permission, or changed source root invalidates the affected plan. |
| FR-TXN-003 | 2 | Define durable item boundaries and idempotent recovery. Repeat execution cannot blindly duplicate or delete an already committed output. |
| FR-TXN-004 | 2 | Implement cross-volume moves as staged copy, full verification, destination publication, then authorized source removal. Preserve the source until destination correctness is established. |
| FR-TXN-005 | 2 | Cancellation stops further commits and reports completed/uncommitted items. Cleanup failure is visible and recoverable; never erase the journal to imply success. |
| FR-TXN-006 | 2 | On startup, inspect unfinished jobs before launching conflicting mutations. Allow safe cached browsing while affected assets/actions are guarded. |
| FR-TXN-007 | 1a catalog; 2 filesystem | Validate undo against resulting content/path/metadata revisions. Refuse unsafe reversal or offer explicit reconciliation when external changes intervened. |
| FR-TXN-008 | 2 | Distinguish Remove from Library, Ignore, Move to Trash, and Permanent Delete. Permanent deletion requires an explicit destructive choice and must disclose its irreversibility. |
| FR-TXN-009 | 2 | Keep audit/journal/quarantine storage separate from disposable caches. Retention/cleanup must never silently delete the only recoverable original. |

Filesystem operations and catalog commits are not one universal ACID transaction. The implementation must specify observable outcomes at every boundary. Rollback can fail or become unsafe; recovery must retain evidence and offer reconciliation.

### 16.3 Backup and restore

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-RECOVERY-001 | 1a | Make SQLite-consistent backups before supported migrations and on explicit backup. Verify schema/version, integrity, IDs, and required relationships before claiming success. |
| FR-RECOVERY-002 | 1a | Provide backup selection and restore into an isolated new location. Verify before activation; leave the source catalog and backup intact on failure. |
| FR-RECOVERY-003 | 1a | Offer scheduled local metadata snapshots with visible last-success status, configurable retention/storage policy, and no silent deletion of the last verified recovery point. |
| FR-RECOVERY-004 | 1a | Explain whether a backup is metadata-only or media-inclusive. An export/backup manifest records schemas, content digests, and omitted or unresolved data. |
| FR-RECOVERY-005 | 1a | Restore stable asset/library IDs, metadata, taxonomy, collection order, relationships, provenance, and safe configuration. Pause restored sources/rules until paths and permissions are reviewed. |
| FR-RECOVERY-006 | 1a export; 2 sidecars | Demonstrate reconstruction from a portable export, and later from supported sidecars, with a report of conflicts, unresolved media, and unsupported fields. |
| FR-RECOVERY-007 | 2 | Test disk-full, interrupted writes, backup destination loss, catalog corruption, and failure at every mutation commit boundary. |

A live database must not be backed up by casual copying of only its main file. Use SQLite's supported snapshot/backup mechanism or another explicitly verified offline procedure. Migration backups are not a substitute for a user-facing restore workflow.

Restoring as a replacement preserves library identity. Importing into a different existing library is a distinct merge workflow: detect UUID conflicts, show intended mappings, and preserve origin history. Restored credentials or executable/tool bindings require fresh configuration.

## 17. External tools and extensibility

### 17.1 External editor integration

Open in Editor and Show in Folder are early gallery features, independent of a plugin SDK. The user selects a trusted installed application or OS association. Arguments are passed as structured values; media names must not be interpolated into a shell command.

Track the asset/path snapshot used to open an editor, then reconcile observed changes. Do not infer successful saving merely because a process exited. The user controls the external application's behavior.

### 17.2 Later extension interfaces

| Interface | Scope |
| --- | --- |
| ImportAdapter | Bounded archive/manifest interpretation and normalized candidates; no private commit authority |
| MetadataProvider | Versioned field extraction with source/fidelity information |
| Recognizer | Compatible vector/candidate results with explicit uncertainty |
| Processor | Declared inputs, bounded execution, staged derivative outputs |
| ThumbnailProvider | Isolated supported-format previews with cache identity |
| Exporter | Selected metadata/media packaging and redaction |
| External command | User-configured applications or structured CLI arguments |
| UI/workspace extension | Scoped panels and commands through the application boundary |

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-EXT-001 | 1a | Provide configured external-open actions safely and handle unavailable files/tools without shell injection. |
| FR-EXT-002 | 6 | Version extension APIs and declare compatible host/dependency versions. Unknown/incompatible plugins remain disabled. |
| FR-EXT-003 | 6 | Declare permissions for selected roots, catalog read/write, process launch, and network/data egress. Deny undeclared capabilities by default where the boundary can enforce them. |
| FR-EXT-004 | 6 | Offer install review, disable/remove controls, auditable updates, and explicit trust status. Ordinary Python imports are not an enforceable sandbox. |
| FR-EXT-005 | 6 | Bind plugin output to validated schemas and resource limits. File effects still use the central transaction service. |

No adapter/model/plugin silently updates itself or transmits user data. A future scripting layer must not bypass command authorization and journaling.

## 18. Non-functional requirements

### 18.1 Original requirements, clarified

| ID | Phase | Requirement and acceptance boundary |
| --- | --- | --- |
| NFR-001 | Each released phase | Maintain one primary codebase for Windows, Linux, and macOS. Publish exact supported OS/architecture/display combinations; hosted CI alone is not desktop release qualification. |
| NFR-002 | 1a onward | Keep interactive operations responsive with at least 100,000 cataloged assets on a named reference profile, using the §19 budgets and real preview I/O. |
| NFR-003 | 1a onward | Run hashing, decode, archive/video probing, and inference as cancellable bounded jobs. Specify concurrency, acknowledgment, stop, and cleanup behavior. |
| NFR-004 | 1a | Open from cached catalog state without requiring full rescan. Show stale/offline state and perform eligible reconciliation separately. |
| NFR-005 | 1a onward | Version schemas; authenticate supported structures; verify original-state backup before migration; roll back logical changes on failure and refuse unsupported versions. |
| NFR-006 | All | Require no network, account, telemetry, or remote inference for installed core functionality. Optional downloads/services are explicit and documented. |
| NFR-007 | 1a onward | Isolate malformed items and failed workers so they cannot terminate the gallery or falsely mark a job complete. Enforce declared parser/resource limits. |
| NFR-008 | Before destructive features | Require explicit confirmation or a separately enabled bounded policy for destructive effects; retain an audit record and disclose reversibility. |

### 18.2 Added quality and release requirements

| ID | Phase | Requirement |
| --- | --- | --- |
| NFR-009 | 1a onward | Test accessibility, scaling, focus, keyboard behavior, and meaningful errors on each claimed desktop platform. |
| NFR-010 | 1a onward | Publish cache/job resource limits and observed full-process-tree memory; distinguish Python tracing, RSS, GPU memory, and disk usage. |
| NFR-011 | Each distributed release | Test clean installation, offline first use, supported upgrade, rollback/recovery, and uninstall that preserves user libraries/media. |
| NFR-012 | Each distributed release | Maintain dependency/license notices and a tested runtime manifest. Review Qt distribution terms, model weights, optional FFmpeg/codecs, and transitive native packages. |
| NFR-013 | Each distributed release | Verify signed/checksummed artifacts and applicable signing/notarization; update actions are consented and preserve the previous recoverable installation/catalog. |
| NFR-014 | All public evidence | Publish only fictional/licensed/authorized fixtures and sanitized reports. Private paths, prompts, asset labels, and per-image vectors are not public diagnostics. |
| NFR-015 | 1a onward | Make recovery, unsupported conditions, stale results, and partial completion actionable; avoid silent fallback that changes semantics. |

## 19. Performance and resource governance

### 19.1 Proposed reference profile

The initial candidate acceptance profile is an eight-logical-core CPU, 16 GiB RAM, local SSD, 1920×1080 desktop at 100% and 200% scaling, and a declared OS/display backend. This is a proposal for release validation, not a claim about the developer machine or a definition of every supported workstation.

Record CPU model, RAM, storage/filesystem, free space, OS/build, display/scaling, power policy, decoder/runtime/model versions, worker limits, cache preparation, and dataset manifest. Use authorized representative media alongside reproducible fictional stress fixtures.

### 19.2 Candidate interaction budgets

These values are unmeasured product targets. They become binding only when adopted with the named profile and workload before acceptance measurement.

| Metric | Candidate target | Measurement scope |
| --- | --- | --- |
| Cached startup to usable gallery | p95 ≤3 s | At least 100k records; no mandatory full scan; record cold/warm process/cache conditions separately |
| Basic filter/search to first visible page | p95 ≤200 ms | Supported indexed fields, 100k records, declared query distribution |
| Keyboard selection/review feedback | p95 ≤100 ms | User-visible feedback with concurrent background work |
| Scrolling | p95 presented-frame interval ≤33.3 ms; stalls >250 ms reported | Actual compositor presentation with decoded cached thumbnails, not placeholder cells or synchronous harness steps |
| Visible warm-cache preview | p95 ≤250 ms | Selected viewport and declared thumbnail size/storage |
| Visible uncached supported thumbnail | p95 ≤1 s for the qualified normal-image corpus | Includes queueing and decode; oversized/unsupported items reported separately |
| Cancel acknowledgment | ≤250 ms | Immediate UI acknowledgment |
| Cooperative job stop or isolated-worker termination | ≤2 s, with bounded cleanup separately reported | Chunked hashing and supervised decode/inference; slow network calls have explicit timeout behavior |
| Gallery process-tree RSS without optional ML | Peak ≤1 GiB | Defined active-window/100k workload; measure all child processes |
| Optional ML addition | Additional peak RSS ≤1.5 GiB for the initial qualified model | Include runtime/model/preprocessor; no claim from weights size alone |

Indexing throughput and cold/warm total-time budgets remain pending a representative size/format/storage corpus. Report assets/s and bytes/s separately, including errors, cache state, and analysis enabled/disabled. There is no honest universal 10k-file elapsed target independent of file sizes and enabled work.

CPU model usability additionally requires a predeclared batch-one latency/throughput and total-memory budget on the selected CPU profile. GPU support must be measured independently where advertised.

### 19.3 Resource scheduling

| ID | Phase | Requirement |
| --- | --- | --- |
| FR-JOB-001 | 1a | Prioritize visible previews and explicit user work above speculative background scans/analysis. Prevent starvation through a documented scheduling policy. |
| FR-JOB-002 | 1a | Provide queue, progress, pause/cancel, item errors, and truthful completed/incomplete counts. |
| FR-JOB-003 | 1a onward | Configure worker/thread limits and record them in diagnostics. Start conservatively; do not saturate an artist workstation by default. |
| FR-JOB-004 | 1a onward | Enforce per-stage time/memory/output bounds, with platform enforcement gaps and safe fallback disclosed. |
| FR-JOB-005 | 1a | Bound the derived cache by a user-visible disk budget; a proposed 5 GiB default is configurable. Eviction applies only to verified disposable data, not originals/journals/backups. |
| FR-JOB-006 | 1b durable scans; 2 mutations | Persist appropriate checkpoints and distinguish canceled, paused, resumable, failed, and recovery-required jobs. A new enumeration does not reuse an unsafe old cursor. |

Keep expensive media work outside long-lived database write transactions. Batching or journaling changes require correctness, recovery, and durability evidence; a timing observation never authorizes weakened durability.

### 19.4 Benchmark governance

Declare a benchmark's question, fixture, variants, code hashes, pairing/order, environment identity, caps, acceptance screen, and stop conditions before running it. Reuse complete frozen evidence when its provenance and inputs remain valid.

Retain every attempt's identity and failure. Do not combine incomplete jobs into a supposedly complete aggregate or rerun only failed jobs to assemble a fresh balanced cohort. Do not retry an inconclusive diagnostic merely to obtain a preferred verdict.

Each diagnostic ends with a supported result or an explicit inconclusive finding and the smallest justified next experiment. Further experiments require a concrete unresolved product/engineering decision. CI budgets must distinguish ordinary regression tests from expensive characterization.

A 100k-row virtual-grid benchmark is not 100k-media indexing. Synthetic source loss is not real SMB/NFS acceptance. Hosted pools are not a defined physical reference desktop. Python `tracemalloc` is not whole-process memory.

## 20. Filesystem and platform compatibility

### 20.1 Filesystem behavior

- Use destination-volume case/normalization semantics for collisions; do not rely on a language default.
- Test Windows reserved names, trailing dots/spaces, long paths, alternate streams, drive/UNC forms, and reparse points.
- Test Unicode normalization and case-only renames on the actual target filesystem.
- Detect cross-device operations and loss of access; do not assume atomic rename across volumes.
- Treat file identities as scoped, potentially reused observations rather than permanent cross-volume keys.
- Keep temporary/source-unavailable conditions distinct from missing records.
- Test root replacement, changed mount points, removable-drive relinking, and intermittent network reads.
- Define read-only-source behavior. Catalog curation remains possible; writing sidecars/media needs destination permission and the transaction service.

### 20.2 Platform qualification matrix

| Target family | Candidate qualification | Release status |
| --- | --- | --- |
| Windows desktop | Named Windows desktop version, x64, native display, supported paths/editor integration | Version commitment and signed clean-machine evidence required; Windows Server CI is supplementary |
| macOS | Named supported macOS version, Apple Silicon; Intel only if separately qualified | Architecture, signing/notarization, decoder/model dependencies, and native UI evidence required |
| Linux | Named x86-64 distribution baseline; X11 and Wayland claims accepted separately | Packaging, native display, file-manager/editor integration, and dependency evidence required |
| Other architectures/distributions | Optional extension | No support claim from another platform's CI |

Python 3.11+ is the current catalog baseline, not a promise that every optional model/native dependency supports every Python release. A distributed application pins a compatible tested dependency set.

### 20.3 Dependency maintenance

Track actual bundled SQLite and decoder/runtime versions, not just the Python or package version. Dependency security/correctness fixes are reviewed and regression-tested.

SQLite's upstream documentation identifies a WAL concurrency defect fixed in 3.51.3 and selected backports. If WAL is used, qualify a fixed runtime such as 3.51.3+ or an applicable fixed branch, and test the chosen concurrency/checkpoint policy. This is a release qualification requirement, not a finding that the current scanner encountered that defect.

Exact Qt/model/FFmpeg distribution obligations depend on the shipped components and chosen licensing path. Record that review in the release manifest; the SDD is not a legal opinion.

## 21. Verification and acceptance

### 21.1 Requirement traceability

Each requirement is linked in the implementation tracker to a delivery phase, owner, design/API, test or manual acceptance procedure, evidence artifact, and status: Not Started, Partial, Implemented, or Accepted. Accepted means the scoped release gate passed; a test file's existence alone is insufficient.

Deferrals retain the requirement ID, reason, affected release, and replacement milestone. A phase may be split without declaring its remaining Must requirements complete.

### 21.2 Required acceptance scenarios

| Area | Required evidence |
| --- | --- |
| Library and migration | Fresh/open/refusal paths; supported upgrades; consistent pre-upgrade backup; full rollback on failure; restored IDs/metadata; unsupported schemas left unchanged |
| Identity | Unchanged rescan, same-byte separate paths, verified rename, atomic editor save, ambiguous replacement/move, inode reuse, and explicit relink without metadata misassignment |
| Sources | Existing-file policies, overlaps, exclusions, external writes, cancellation, fresh restart, incomplete-pass preservation, and native event overflow where watching is claimed |
| Network sources | Generated scratch-only SMB/NFS loss during enumeration and reads, reconnect, stable IDs and source bytes; each claimed OS/backend qualified |
| Metadata | Overrides/tombstones, conflicts, stale synchronization base, bulk captured-ID edits, undo after intervening changes, aliases/hierarchy integrity |
| Collections/search | Reopen/order preservation, unavailable assets, duplicate membership, stale moves, typed filters, invalid queries, deterministic selection |
| Media | Oriented/tagged/untagged/alpha fixtures, supported bit depths, malformed/truncated/oversized files, thumbnail corruption, high-DPI, and unsupported-mode behavior |
| Accessibility | Keyboard-only tasks, focus order, dialogs, virtual-grid screen-reader semantics, status/error announcements, scaling and contrast |
| Jobs | Foreground interaction under load, queue priorities, cancellation/timeout, worker crash, resource bounds, cleanup failure, and resumability rules |
| Backup/restore | Restore into a new location; digests/schema/integrity; metadata-only omission report; roots unresolved but metadata usable; failure leaves originals/backup intact |
| Transactions | Fault injection before/after every durable boundary, external destination changes, disk-full, cross-volume move, reexecution, safe refusal of undo, and journal retention |
| Archives | Frozen generic/platform fixtures, zip-slip/link/special entries, malformed directory, actual expansion limits, nesting, CRC/decode failure, changed archive after preview, and manifest output escaping |
| Recognition | Reproducible authorized data, unknown/lookalike/style-shift cases, compatible vector spaces, stale input rejection, corrupt vectors, model upgrades, and zero automatic metadata mutation |
| Release | Clean-machine install/offline launch, signed/checksummed artifacts, update/rollback, uninstall preservation, license notices, and platform/backend manifest |

### 21.3 Performance acceptance

Separate 100k catalog browsing from cold media indexing at 10k/100k/500k scales. The 500k corpus is an extended scalability experiment, not an automatic prerequisite for every small Phase 1 increment.

Use repeated predeclared workloads, cold/warm preparation where enforceable, concurrent jobs, actual thumbnail I/O, full-process-tree memory, and native-display measurements. Record sample counts, percentiles, variability, exclusions, and unmeasured conditions.

When reference hardware or a budget is unset, report measurements without claiming NFR compliance. An inconclusive result preserves raw evidence and ends with a bounded next decision/experiment.

### 21.4 Data and safety boundaries

Use generated fictional fixtures for automated acceptance. Real artwork/reference evaluation requires explicit authorization and rights appropriate to that use. Public reports exclude private originals, paths, prompts, client names, asset-level vectors, and identifying labels.

Real-share tests use an isolated generated-file scratch area and a scoped disconnect method. They never require modifying existing mounts/services or scanning private collections merely because this specification mentions NAS support.

## 22. Phased delivery and current coverage

### 22.1 Delivery roadmap

| Phase | Product scope | Exit gate |
| --- | --- | --- |
| 0 - Technical foundations | UI/runtime comparison, catalog/migration spike, thumbnail/parser isolation, source behavior investigation, archive preview, embedding benchmark | Recorded stack decision and evidence limits; risky file commits remain unavailable |
| 1a - Explicit-scan gallery | Libraries, explicit multiple-source scans, Inbox/review, correct supported-image previews, inspector, tags/entities, ratings/favorites, manual collections, basic search, exact duplicates, external-open, accessible curation, verified backup/restore/export | Scoped user tasks work on qualified platforms; privacy/integrity tests pass; recovery and proposed performance gates are measured or explicitly unresolved before release claims |
| 1b - Reliable watching and reconciliation | Local native watchers, basic source filters, bounded durable scanning, relinking/replacement UI, periodic reconciliation; network watching only for qualified shares | Native event and interruption evidence, truthful health, no uncertain deletion; real-share evidence for remote support claims |
| 2 - Safe organization | Mutation journal/recovery, naming/folder templates, move/copy/trash, filesystem undo, sidecars/synchronization, saved queries, advanced source profiles, basic derivative pipelines/relationships | Fault injection at every commit boundary; safe undo/refusal; metadata conflict and source-byte preservation |
| 3 - Archive import | Generic and selected known-platform adapters, reconstructed types/names/context, preview, staged commit, limits, reports/provenance | Phase 2 journal proven first; adversarial parser/path/expansion and interrupted-import acceptance |
| 4 - Intelligent curation | Perceptual families, versioned Find Similar, character references/suggestions, confirmation, manual multi-character regions | Authorized real-reference evaluation, unknown/lookalike behavior, compatible vector/index lifecycle, qualified CPU packaging |
| 5 - Media expansion | Video/animation playback and sampling, sprite/frame tools, specialist previews, richer relationships, FFmpeg-backed processing | Format fidelity, isolation, CPU/GPU/resource behavior, and platform-specific distribution evidence |
| 6 - Ecosystem | Plugin SDK, scoped external processors/adapters, advanced scripting/automation, workspace extensions | Enforceable declared capabilities or honest trust limits, versioned interfaces, update/disable/remove and egress controls |

Basic color/orientation/alpha display, backup, external editing, and accessibility are deliberately earlier than the v0.1 media/plugin phases. Source-writing work remains behind the Phase 2 safety gate. Early prototypes of later features do not grant that phase's release status.

### 22.2 Implementation snapshot

The read-only baseline for this revision is commit `1d4dc92c5a9aa4bd043daaf191581ef19937e611`. This table summarizes checked-in evidence, not a fresh full code/CI audit.

| Capability | Baseline evidence and remaining boundary |
| --- | --- |
| Desktop direction | Qt/PySide6 chosen; catalog-row/offscreen measurements do not establish native preview, accessibility, or distribution acceptance |
| Catalog | Stable assets/provenance, supported backed-up migrations to schema v4; general restore/recovery/export remains unfinished |
| Sources | Persistent independent roots, explicit scans, quiet-interval checks, conservative supported renames, cancellation and synthetic recovery; continuous watching and real-share acceptance unfinished |
| Gallery | Qt grid/details, cached PNG previews, review/filtering, exact duplicate view; broader display/format/search/accessibility/curation targets remain partial |
| Metadata/collections | Tags, aliases, hierarchy, six typed entities, explicit assignments, ordered manual collections; richer fields, synchronization, bulk editing, and saved queries unfinished |
| Archive | Bounded read-only ZIP inspection; no production extraction/commit interface |
| Embeddings | Two pinned candidates benchmarked on a tiny generated fixture; DINOv2-small is a provisional retrieval baseline, not recognition acceptance |
| Scan characterization | Two separate accepted hosted 12-pair cohorts; no claim for large varied media, reference hardware, cold caches, or real network shares |
| Exit-only diagnostic | First complete Windows four-pair cohort is inconclusive because one I/B ratio breached its predeclared bound; a later gate-repair cohort was not reviewed for this SDD revision |
| Mutations/plugins/video | Later-phase design, not delivered capabilities |

The new requirements in v0.2 must be added to the implementation tracker before a release is declared. Existing scoped acceptance is preserved as historical evidence rather than retroactively labeled complete under expanded requirements.

### 22.3 Recommended sequencing

Finish a bounded in-progress evidence task under its original declared contract when project work is separately resumed. Then prioritize everyday curation, backup/restore, identity/relinking, and truthful source behavior.

Further performance experiments should answer an explicit product budget or unresolved correctness/engineering decision. A stream of increasingly detailed microbenchmarks is not a substitute for the gallery acceptance tasks. Metadata-only product work can proceed independently of unavailable real-share environments.

## 23. Risks and tradeoffs

| Risk | Required mitigation or decision |
| --- | --- |
| Rich metadata cannot be reconstructed from files alone | Verified backups, full portable export, explicit omission reports, and restore drills |
| Same path/bytes mistaken for same identity | Conservative reconciliation, separate duplicate groups, revision evidence, and explicit ambiguity UI |
| Source unavailability mistaken for deletion | No missing reconciliation after failed/incomplete scans; retain records and cache |
| Watcher events unreliable | Treat notifications as hints; overflow handling and periodic healthy reconciliation |
| Partial filesystem/catalog commit | Durable item journal and tested resume/rollback/reconcile boundaries |
| Metadata conflicts or removed labels reappear | Per-field authority, synchronization base, source records, and user override/tombstones |
| Recognition false positives or reference contamination | Unknown state, held-out negatives, explicit confirmation/reference approval, no automatic assignment |
| Model upgrade mixes incompatible vectors | Full space identity, input versioning, isolated generations, and invalidation |
| Decoder/archive abuse | Bounded input/output/time/memory, isolation, containment checks, and fuzzing |
| Cached color/thumbnail misleading | Versioned display transforms, freshness/error labels, and format-fidelity acceptance |
| SQLite placement/runtime assumption unsafe | Local live-catalog policy, writer coordination, fixed/tested runtimes, consistent backups |
| CI samples become product claims | Named reference profile, native display, authorized corpus, and separate evidence classes |
| Feature breadth overwhelms UI/schedule | Phase-scoped Must requirements, progressive disclosure, and bounded acceptance milestones |
| Package/update or plugin trust expands authority | Tested manifests, license review, consented updates, declared access/egress, disable/remove controls |

## 24. Decisions still requiring evidence or product selection

Resolved directions in §5 are no longer open questions. The following remain visible release/design choices rather than blockers for unrelated safe catalog work.

| Decision | Default direction | Required resolution |
| --- | --- | --- |
| Exact supported OS versions and architectures | Windows/macOS/Linux primary families; qualified configurations only | Record release matrix and clean/native acceptance |
| Reference hardware and interaction budgets | Candidate profile and values in §19 | Adopt before pass/fail measurement; record any justified revision |
| Representative media/indexing corpus | Authorized mix of actual workflow formats/sizes plus deterministic stress fixtures | Publish manifest, analysis options, storage/cache policy, and throughput targets |
| Media format depth | Image-first; explicitly unsupported modes | Select exact initial format/mode coverage and fidelity tests |
| Replacement/revision UI | Conservative retention with explicit resolution | Specify user choices and source-profile policy without silently transferring identity |
| Backup retention and media-inclusive mode | Verified metadata snapshots; originals excluded unless chosen | Choose visible defaults, storage budget, cleanup and restore procedures |
| Sidecar convention | Per-asset versioned JSON, opt-in; managed storage for read-only media | Finalize association, schema, conflict handling, and transaction integration |
| Product embedding model/runtime | Provisional DINOv2-small retrieval baseline only | Real-reference quality, footprint/licenses, and cross-platform CPU packaging |
| GPU support | Optional | Provider-specific parity/space-versioning and installed footprint evidence |
| Archive adapters | Generic importer plus individually maintained selected adapters | Select formats, authorized frozen fixtures, supported versions, and update trust policy |
| Automatic organization | Disabled/dry-run default | Separate bounded opt-in policy and safety evidence before enablement |
| Plugin execution model | Later-phase capability boundary | Specify enforceable isolation versus explicit full-trust behavior |

## 25. Assumptions and change control

1. The filesystem is authoritative for currently observed media bytes/placement; the catalog is authoritative for operational identities and explicit application metadata. Conflicts require reconciliation, not blind overwrite.
2. Artists use external tools. Files may change while the application is running, and a quiet interval cannot prove producer completion.
3. Source availability and asset existence are different observations. Offline storage does not imply removal.
4. Export formats evolve. Generic import, versioned adapters, and retained context are necessary.
5. Recognition is an aid. Scores are evidence for ranking and review, not character ground truth.
6. Derived previews/vectors are rebuildable; user-authored taxonomy, decisions, and relationships require backup/export.
7. The current catalog schema is an implementation detail. Domain additions require compatible migrations and verified backups, not ad hoc schema edits.
8. Published benchmarks remain attached to their code, environment, and attempt identities. A later document cannot transform a failed screen into acceptance.

Changes to identity, metadata authority, file mutation, durability, or external data access require an ADR or equivalent reviewed design note, updated acceptance, and a compatibility/migration assessment. Editing this SDD does not automatically enable those capabilities or modify user data.

## Appendix A. Queries, templates, and profile examples

The following are fictional target-language illustrations. The current basic search does not implement all of them.

```text
character:Fuyumi AND rating:>=4 AND NOT tag:meme
source:"Generated Art" AND workflow:inbox
review:needs_review AND stage:wip
media:video AND duration:>30s AND character:Lunara
archive.platform:chatgpt AND imported:2026-09
favorite:true AND (project:Portfolio OR tag:reference)
similar:"asset:00000000-0000-4000-8000-000000000001"
```

A similarity request additionally selects a compatible model/space and interprets its score as ranking. A numerical threshold is valid only for its declared model and calibrated use, not a universal identity probability.

```text
Filename: {character}_{project}_{date:yyyy-MM-dd}_{sequence:03}.{ext}
Folder:   {artist}/{character}/{year}/{project}/
Fallback: {source_platform}_{import_date}_{sequence:05}_{hash:8}.{ext}
```

Templates must specify how missing or multiple characters/projects resolve. A shortened hash helps naming but is not the catalog identity or a sufficient collision proof.

## Appendix B. Provenance and vector illustrations

### B.1 Import provenance

```json
{
  "schema": "defiantmaple.import-provenance.example.v1",
  "asset_id": "00000000-0000-4000-8000-000000000001",
  "source_kind": "archive_export",
  "platform": "example_platform",
  "archive_name": "example_export_2026-09-24.zip",
  "archive_sha256": "example-full-digest",
  "archive_member_path": "media/example-object-id.dat",
  "original_member_name": "example-object-id.dat",
  "declared_extension": "dat",
  "detected_media_type": "image/png",
  "detected_extension": "png",
  "detection_evidence": ["signature", "successful_decoder_probe"],
  "reconstructed_name": "Fuyumi_Reference_2026-09-24_001.png",
  "adapter": "example_export",
  "adapter_version": "1",
  "adapter_score": 0.93,
  "adapter_score_kind": "heuristic_not_probability",
  "content_sha256": "example-full-content-digest",
  "import_job_id": "00000000-0000-4000-8000-000000000002"
}
```

This is an illustrative record, not the runtime schema. Production digest fields contain validated full digests. Original private member paths stay in local provenance, not public benchmark reports.

### B.2 Per-vector identity

```json
{
  "schema": "defiantmaple.vector-provenance.example.v1",
  "asset_id": "00000000-0000-4000-8000-000000000001",
  "asset_revision": "example-revision",
  "input_sha256": "example-full-content-digest",
  "region": null,
  "orientation_policy": "declared-decoder-orientation-v1",
  "model_name": "facebook/dinov2-small",
  "model_revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056",
  "weights_sha256": "example-full-weights-digest",
  "weights_license": "Apache-2.0",
  "embedding_method": "cls_token",
  "preprocessing_fingerprint": "example-versioned-fingerprint",
  "dimensions": 384,
  "encoding": "float32_le",
  "normalization": "l2",
  "distance_metric": "cosine",
  "runtime_manifest": "example-tested-runtime",
  "status": "valid",
  "metadata_mutation": false
}
```

The model identifiers illustrate the existing benchmark baseline; they do not authorize downloads, infer licensing for other weights, or approve a product classifier. The vector payload is omitted.

## Appendix C. v0.1 requirement and scope crosswalk

| v0.1 group | v0.2 treatment |
| --- | --- |
| FR-INBOX-001..007 | All seven retained in §7; explicit scans, watching, filters, advanced profiles, and transaction self-events receive separate delivery boundaries |
| FR-IMP-001..012 | All twelve retained in §8; exact duplicates precede perceptual assistance; immutable preview and actual validation are explicit |
| SEC-ARC-001..006 | All six retained in §9; actual output limits, parser isolation, path races, item recovery, and privacy are clarified |
| NFR-001..008 | All eight retained in §18 with evidence scopes; NFR-009..015 add accessibility, resources, release, privacy, and actionable failure |
| Asset identity/provenance | §§6 and 14 retain stable IDs and multiple origins; same-byte distinct assets are the default, and merging is explicit |
| Metadata/taxonomy/sidecars | §10 retains original fields, groups/rules, entity types, generation context, embedded fields, and export; authority/conflicts/tombstones are added |
| Gallery/search/collections | §11 retains original view/query/curation scope; daily viewing, accessibility, bulk editing, offline behavior, and external-open are made explicit |
| Naming/rules/pipelines | §12 preserves triggers/templates/actions while defining defaults, approval, and loop prevention |
| Recognition | §13 retains optional retrieval, character references, regions, and GPU possibilities; automatic tagging is deferred outside this baseline |
| Duplicates/relationships | §14 preserves exact/perceptual/embedding families and all relationship categories with explicit association/delete safeguards |
| Media/video | §15 preserves processing, animation/sprite, FFmpeg, frame/time annotation, and export presets; essential viewing fidelity moves earlier |
| Transactions/recovery | §16 retains journal/undo/reconciliation and adds deletion distinctions, verified restore, portability, and concrete failure boundaries |
| Extensibility | §17 retains original extension interfaces; simple external editing moves earlier while the SDK remains Phase 6 |
| Performance/testing | §§19 and 21 preserve large-library and adversarial testing; reference budgets, native display, full memory, and finite experiment governance are added |
| Phase plan | §22 retains Phases 0–6 and splits Phase 1 into explicit-scan gallery and reliable watching; no completed requirement is inferred from that split |

## Appendix D. Evidence and references

### D.1 Design and implementation evidence

The following repository documents provide implementation-specific detail. Links are pinned to the read-only snapshot used for this revision; they do not imply that every target requirement is implemented.

- [SDD v0.1 review](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/sdd-review.md)
- [Phase 1 requirements audit](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/phase1-requirements-audit.md)
- [ADR 0001: desktop stack](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/adr-0001-desktop-stack.md)
- [Metadata and migration contract](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/metadata-design.md)
- [Manual collection contract](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/collections-design.md)
- [Source scanning contract](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/source-scanning-prototype.md)
- [Embedding benchmark and limits](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/embedding-model-benchmark.md)
- [First complete Windows exit diagnostic](https://github.com/isaaclepes/DefiantMaple/blob/1d4dc92c5a9aa4bd043daaf191581ef19937e611/docs/transaction-exit-benchmark-history/2026-10-03/first-complete/README.md)

Original source: *Artist Gallery and Asset Management Platform - Software Design Document v0.1*, 24 September 2026, 12 pages. The reviewed PDF's SHA-256 is `2065217447836f372aef91fada0a19b7eee0a1422f355a44eff114ccf93650ce`. This Markdown revision preserves its substantive product scope while clarifying decisions and adding requirements.

### D.2 Primary technical references

- [SQLite WAL: locking, network-filesystem limitations, and fixed-runtime guidance](https://www.sqlite.org/wal.html). Supports §§5, 20; it is not a recommendation to change journaling settings without a separate design.
- [SQLite Online Backup API](https://www.sqlite.org/backup.html). Supports consistent snapshot/backup requirements in §16.
- [Qt accessibility guidance](https://doc.qt.io/qt-6/accessible.html). Supports application-level keyboard, scaling, contrast, and assistive-tool acceptance in §11.
- [Licenses used in Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html). Supports the shipped-component license inventory in §18; distribution compliance requires the actual release manifest and chosen licensing path.

These technical references were checked on 3 October 2026. Future release qualification must recheck applicable runtime and licensing information.
