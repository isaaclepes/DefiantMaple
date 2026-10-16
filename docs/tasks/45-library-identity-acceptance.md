# Task 45 — stable library identity acceptance

Status: authentic PR22 schema-6/v1 fixture prepared in a private attempt; independent receipt/fixture review pending. No acceptance claimed. Owner: Luna.
Implementation: [Task44](44-library-identity-implementation.md).
Independent review: [Task46](46-library-identity-review.md).

Prepare `docs/library-identity-acceptance.md` and a case matrix against the
reviewed design before execution. Use generated fixtures only; raw catalogs,
UUIDs, local paths, media and private logs stay outside public evidence.

Cover fresh identity, reopen/relocation stability, supported legacy migration,
verified original-state backup and rollback, invalid identity/schema refusal,
current and legacy package inspection, explicit legacy identity assignment,
identity-preserving restore, pending/source/standalone holds, no automatic
library switch or scan, stale Qt replies, cancellation and owned cleanup.
Distinguish legacy missing identity from a preserved modern identity. Record
old-client compatibility and unresolved multi-instance/platform boundaries.

Capture source hashes, commands, direct exits, failures, named platform skips,
environment and unchanged output/media/cache evidence. Reuse unchanged evidence
only within its measured scope. Relevant Core/Qt tests, an exact-source frozen
build and bounded native desktop evidence require separate reviewable claims.
Native execution needs the real desktop available and an independently reviewed
generated-fixture driver. Do not silently substitute offscreen evidence.

Audit all actually triggered current-head CI runs and actual Windows summaries,
not only workflow wrapper conclusions. Never cancel or rerun jobs without an
actual need. Preserve historical failures. Publish sanitized aggregate evidence
only after privacy review. Scheduling/retention/export and full SDD/release
acceptance remain outside this bounded milestone. Do not modify deployed
outputs, commit, publish or merge. Root owns integration and final gates.
