# Task 20: Phase 1a gallery usability implementation

## User authorization and feedback

On 4 October 2026 the user requested the gallery-usability milestone, feedback-to-SDD v0.2 mapping, refreshed tracking, implementation/acceptance briefs, native desktop evidence, relevant green checks, independent review and a reviewable PR. Their stated priorities are undistorted thumbnails, responsive loading, full-image viewing and correct Fedora/KDE application identity. These are confirmed priorities, not invented observations of a particular test run. An optional request for further test details is pending; current authorized work continues.

Baseline main/PR14 merge: b0d1755fd344f7cb033c83d66413dff04997bfd4. Branch: codex/phase1a-gallery-usability. Design basis: docs/sdd-v0.2.md and docs/sdd-v0.2-review.md. Preserve historical acceptance and frozen benchmark archives.

## Outcomes and scope

1. Aspect-preserving default thumbnail presentation for portrait, landscape and square images, correct orientation, no stretched pixels. Any explicit crop mode must be accurately labeled. Preserve alpha and bounded cache/decoder behavior. FR-UX-001, FR-MEDIA-001/003/004.
2. Bounded lazy thumbnail work that prioritizes the visible gallery and stays responsive during cold/warm image loading, scrolling, resizing and selection. Handle stale requests, failures and closing without retargeting assets or hanging teardown. FR-UX-001/006, job/resource requirements in SDD §§18–19. Native measured interaction evidence is scoped to a named generated fixture and this host; proposed numerical NFRs are not automatically adopted.
3. Captured-asset full-image inspect with real source decoding outside the GUI hot path, fit/zoom/pan, predictable open/close/keyboard handling, truthful loading/error/unsupported/unavailable states. Preserve orientation and aspect ratio, selectable alpha background where practical; full resolution means original supported image pixels within explicit decoder/resource limits. FR-UX-002/007/010, FR-MEDIA-001/003. Do not substitute a small cached thumbnail while calling it full resolution.
4. Visible product name DefiantMaple, consistent application/window/icon identity, valid Linux .desktop entry and Fedora/KDE Wayland app-id/window grouping. Package assets and document launch/install procedure. Track platform identity as a derived requirement anchored to SDD §§15,20–22; do not fabricate an SDD identifier. Test native identity and packaging separately.

## Boundaries

No source media writes, automatic metadata edits, scanner/SQL transaction/PRAGMA/durability changes, inference/model downloads, real-share testing, watcher claims or new attribution experiment. Use fictional generated fixtures outside Git and sources; isolate catalogs/caches. Do not scan personal media or install persistent global desktop settings. Color-profile fidelity, animation/video playback, full accessibility, full 1a backup/restore/export and broader curation remain explicit partial/deferred targets unless actually implemented and accepted.

## Ownership and validation

Sol implementation owns app/helper modules, Qt regression tests, identity assets/package integration and Qt README. Luna owns acceptance brief, feedback record, requirement tracker and reproducible native acceptance script/evidence. Independent Sol reviews without editing implementation. Root owns orchestration/publication and this brief. Shared checkout; no agent commits, pushes, branch changes or PR creation.

Run meaningful tests for aspect/orientation, original-pixel preview, bounded/stale async work and close/error paths, identity and frozen resources. Reuse existing source/integrity tests. Produce native KDE evidence with isolated fixtures, named runtime/display/cache/memory limits and source/catalog digests before/after. Hosted/offscreen evidence must be labeled separately. Finish with green relevant CI, actual affected Windows test summaries, independent clearance and a draft/reviewable PR; merging remains separate.

## Completed diagnostic workflow boundary

Both older diagnostic workflows previously triggered on every pull request;
their conservative publication gates would launch fresh measurements for a GUI
code delta. Root and independent Sol reviewed narrowing their PR path filters
to their exact measured runtime lists (six scan files, eight exit files).
Workflow/docs edits alone do not trigger new measurements. The original gates,
measured source and archived evidence stay intact; Core and Qt checks remain
active for gallery work. YAML parse, measured-list equality and no overlap with
this milestone's changed files are checked before publication. Historical
workflow digests describe their original runs, not the current workflow file.
