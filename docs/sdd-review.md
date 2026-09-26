# SDD 0.1 review and implementation plan

Reviewed source: `Artist_Gallery_Asset_Management_SDD_v0.1.pdf`, dated
24 September 2026, all 12 pages. The document is a requirements/design source;
its examples are not commands or authorization to inspect personal media,
configure watched folders, execute tools, or organize files.

## Assessment

The strongest architectural choices are stable asset identity independent of
paths, filesystem interoperability, multiple provenance records per asset,
preview-before-mutation, and local inference as an assistive workflow. The phased
plan is appropriate, but the full scope is substantially larger than an MVP.

The principal gaps to resolve before the gallery MVP are:

1. **Identity and reconciliation.** Define how a rename, replacement, in-place
   edit, and byte-identical copy differ. Hash equality cannot establish identity.
   Keep duplicate grouping separate from asset merging, and preserve every origin.
2. **Source overlaps and stability.** Specify precedence for overlapping source
   roots, symlink traversal, debounce intervals, and files that pause mid-write.
   A stable interval is a heuristic, not proof that a producer has finished.
3. **Archive lifecycle.** Define immutable preview plans, archive fingerprints,
   validation immediately before commit, cancellation, staging cleanup, and
   recovery after each commit boundary. Prefix sniffing alone is not media validation.
4. **Metadata authority.** Decide conflict handling among embedded metadata,
   sidecars, and catalog edits. Preserve competing values and their source until
   a resolution policy exists; do not silently overwrite either copy.
5. **Acceptance criteria.** NFR-002 names 100k assets without latency, memory,
   thumbnail-cache, or reference-hardware budgets. Add measured targets before
   declaring performance compliance. Similarity needs a labeled evaluation set,
   license review, and CPU/GPU benchmarks before choosing a model.
6. **Vocabulary.** Workflow states in section 7 and artistic workflow labels in
   section 10 need separate fields; the query alias `workflow:inbox` needs a
   documented mapping. This slice uses section 7's six states only.

## Decisions for this initial slice

- Implement a dependency-free Python core spike to exercise SQLite and ZIP
  invariants. This is provisional and does not decide the final desktop stack.
- Use one database per library for isolation. Media may remain outside that
  directory. Cross-library search is deferred.
- Use UUID asset keys, separate non-unique SHA-256 hashes, and a one-to-many
  provenance table. Matching bytes at different paths do not merge automatically.
- Record only signature-based media hints; explicitly mark decoder validation as
  pending. Unsupported content is not guessed from its suffix.
- Offer read-only ZIP previews first. There is deliberately no extraction/commit
  API until journal and recovery work exists.
- Reject changes at already indexed paths pending reconciliation instead of
  silently assigning existing metadata to a replacement file.
- Schema version 2 initializes atomically and transactionally migrates the
  experimental version 1 catalog. Unknown/future versions are rejected. Upgrade
  backups, rollback migrations, WAL policy, and recovery remain future work.
- Generate thumbnails in a spawned decoder process. Cache entries are keyed by
  asset UUID, source SHA-256/byte count, output size, cache schema, and decoder
  version. Only validated cache files are published atomically.
- Persist independent filesystem sources and require one of the SDD's three
  existing-file policies at registration. The prototype scans on demand; it does
  not claim to be an ongoing watcher.
- Resolve overlaps by assigning a path to the most-specific enabled source. Skip
  symlinks, preserve assets through unavailable scans, and accept an external
  rename only after a unique identity/fingerprint match or a conservative unique
  byte-size candidate plus full-hash fallback.

## Implemented and tested now

| SDD area | Initial implementation | Remaining work |
| --- | --- | --- |
| 5, 6, 6.1 | SQLite catalog; UUID keys; indexed paths/hash/state; source identity | Tags, entities, collections, relationships, ambiguous reconciliation |
| 6.2 | Filesystem origin records; ZIP original member paths retained in preview | Persist archive jobs, archive identity, richer provenance |
| FR-IMP-001/002/003/006 | Central-directory enumeration, bounded signature probes, corrected proposed suffixes | Decoder validation, manifest context, editable UI preview |
| SEC-ARC-001/002/003/004/006 | Flag unsafe paths, links/special files, encrypted entries and size/ratio limits; no execution/network | Hardened extraction path rules and parser isolation |
| FR-IMP-012 | Nested archive warning; no expansion | Opt-in bounded nesting policy |
| 7, 11, NFR-002 | Pillow-backed PNG thumbnail cache; fingerprint/version keys; worker timeout; byte/dimension/pixel limits | Video posters, color management, OS worker memory sandbox, eviction policy, cold/warm cache budgets |
| FR-INBOX-001/003/004/005 | Persisted multiple sources; three existing-file policies; size/mtime quiet interval; deterministic overlaps; Offline/Permission Denied health | Include/exclude profiles, native watcher backends, network-share soak tests, watcher self-event suppression |
| 14 | Exact hash grouping without deletion | Perceptual hashes, embeddings, duplicate decisions |
| 21 | Adversarial archive and catalog integration tests; OS CI matrix | Watchers, crash recovery, migrations, large-library benchmarks |

This table describes partial coverage, not completed Must requirements.

## Limitations worth preserving in future work

- ZIP central-directory parsing occurs before the member-count check. The archive
  byte cap bounds its input, but this is not a sandbox or a strict process-memory
  budget. A production parser should preflight directory size/count and use a
  worker resource limit, timeout, cancellation, and fuzzing.
- Prefix reads need not verify the full member CRC. Preview cannot certify that a
  member will decode or that a future extraction is safe.
- The source scanner requires two matching observations across a quiet interval,
  but a producer can pause longer than that heuristic. Ongoing watch events are
  not implemented.
- Same-filesystem renames with unique identity/fingerprint matches preserve UUIDs.
  Ambiguous moves, cross-volume moves, inode reuse, and replacement policy still
  need a user-facing reconciliation flow.
- Local tests run on Linux. The configured Windows/macOS CI jobs must succeed
  before claiming cross-platform verification.
- Schema 2 remains an experimental foundation. No user library has been ingested.

## Phase 1 milestone sequence

1. **Completed:** compare UI/runtime candidates using a 100k-item virtual gallery
   fixture and record the stack ADR.
2. **Implemented in this slice:** add a decoder-backed thumbnail cache keyed by
   asset UUID plus fingerprint, with malformed-image and oversized-dimension
   isolation.
3. **Implemented in this slice:** prototype multiple sources with explicit existing-file policy,
   stable-file debounce, overlap handling, and Offline/Permission Denied states.
   Test external writes and renames on each OS before implementing ongoing watches.
4. **Next:** benchmark a small set of locally licensed embedding candidates on curated
   stylized character references; retain confidence and model/version metadata.
5. Deliver the first desktop vertical slice: library creation, source selection,
   Inbox grid, asset detail, basic search, review state, and duplicate view.

Later gates remain aligned with the SDD: Phase 2 adds journaled organization,
undo and sidecars; Phase 3 adds staged archive imports/adapters; Phase 4 adds
similarity and character curation; Phase 5 expands media/video; Phase 6 adds
permissioned extensibility. File mutations must not precede the journal/recovery
foundation simply because an early ZIP preview is available.
