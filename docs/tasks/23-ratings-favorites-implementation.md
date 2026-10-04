# Task 23: Explicit ratings and favorites

## Baseline and authorization

The user authorized merging PR #15 and continuing the next documented goal on
4 October 2026. PR #15 is merged at
`60ebf881e6bb85316042100e3ed8beb119acf400`; this increment uses
`codex/phase1a-ratings-favorites`. SDD v0.2 and its ordered backlog prioritize
daily catalog curation. Documents supply requirements, not additional execution
authority. No new user test observations have been supplied for this increment.

## Required outcome

Support explicit single-asset ratings (unrated or 1–5 stars) and an independent
favorite flag, persistent across reopening and scans. Provide typed rating and
favorite gallery filters that compose with existing filters. An editor must
retain its captured asset identity when gallery selection changes. Show the
target, current values, and truthful failure/conflict messages; keyboard focus
and controls must be usable. Editing changes only catalog data.

Provide catalog undo for these edits with durable preconditions. Refuse unsafe
undo after intervening catalog-observed asset-content/path or metadata revisions, including ABA
changes that return values to their previous state. Undo must work after catalog
reopening. A no-op must not create a misleading edit; invalid values and stale
writes must fail atomically. Do not claim generic bulk undo or imported metadata
synchronization. Conservative single-edit undo does not rebase older journal
entries into a general undo stack or provide redo. Filesystem changes not yet
observed by an explicit scan do not produce catalog revisions; catalog undo
only restores ratings/favorites and never reverses source file changes. Keep
FR-TXN-007 partial and disclose that distinction.

FR-META-002/003, FR-UX-003/005 and scoped FR-TXN-007 guide this increment.
Title/description, rights, stage, bulk editing, shortcuts/multiselection,
additional search facets and filesystem undo remain separate requirements.

## Design and preservation

Sol owns catalog migration/API, reader/Qt integration, meaningful regression
tests and product README changes. Report the proposed schema, revision and undo
strategy to Root before substantial implementation. Use the existing versioned
schema and verified-backup migration machinery; do not hide new tables outside
schema validation. Preserve asset UUIDs, source records, tags/entities,
collections and their ordering, scanner behavior, transaction/PRAGMA durability,
recovery, previews and frozen benchmark archives. Coordinate schema-reader
compatibility (including Tauri) rather than leaving silent version mismatches.

Test generated old-schema upgrades and migration failure rollback, invalid API
and SQL values, persistence/reopen, source integrity, rescans, captured-ID
editing, filters, undo/reopen, competing writers and ABA refusal. Explicitly
describe field authority: these are user catalog overrides; recognition/import
must not silently populate or replace them.

## Ownership and completion

Luna owns Task 24, tracker and native acceptance protocol/evidence. Independent
Sol owns Task 25 and reviews without editing implementation. Root owns this
brief, orchestration, workflow integration and publication. Agents share this
checkout: no commits, pushes, branch switches, PR creation or edits to another
agent's files. Coordinate new file ownership explicitly.

Root must ensure completed diagnostic cohorts are opt-in to a concrete future
experiment decision before publishing a catalog change. Do not modify measured
benchmark source to evade hashing or rerun a cohort by default. Relevant Core,
Qt and Tauri checks remain active. Finish with native generated-fixture evidence,
privacy checks, actual Windows summaries, independent review and a draft PR;
merging that PR remains a separate user decision.

## Historical report compatibility

The v5 catalog exposes a pre-existing coupling: archived schema-v4 benchmark
reports were validated against the live catalog version. Sol owns a reviewed
compatibility fix in the two series readers, distinguishing explicit supported
archive versions from the exact schema required for new generated trials and
aggregates. Mixed-version pairs/cohorts must still fail. Existing report bytes,
recorded source hashes, protected-byte publication gates, scanner, workload,
durability and profiling/attribution runtime remain unchanged. These reader
changes have new current hashes; they do not retroactively change the archived
measured-code identities or authorize another experiment. Run affected reader,
gate and public-artifact checks; do not rerun a completed cohort to fix a reader.
