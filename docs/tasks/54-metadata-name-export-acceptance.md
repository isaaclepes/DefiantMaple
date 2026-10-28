# Task 54 — bounded export acceptance

Use generated temporary catalogs/media and offscreen Qt only. Verify deterministic
bytes, schema and exact omission; Unicode/control-text escaping, malformed and
oversized input refusal; unchecked defaults; immutable captured selection;
cancel, error, existing-file/symlink/directory refusal and staging cleanup.
Verify GUI thread responsiveness while saving, held close during the worker,
and truthful saved/not-saved/cleanup-needed feedback. Compare original fixture
bytes, modes and mtimes. Run focused Core/Qt preview/export and scheduler
coexistence tests plus public-artifact privacy checks. Record environment, counts,
skips and source. Native/frozen/cross-platform and full portable export remain
unqualified. Stop at a validated local increment; no PR or merge/deployment.

## Local implementation validation

On the merged `a9c1ed13` baseline plus this local increment: **74 tests passed,
0 skipped**, in 1.920 s, using Python 3.14.7, PySide6 6.11.2, Pillow 12.3.0
and Qt offscreen on Linux. The focused run combined Core name export/preview,
Qt preview/export, scheduler timing/controller and scheduler-window coexistence.
Public-artifact privacy and diff whitespace checks passed. No hosted run,
new native/frozen runtime check or other platform execution was performed.

The first 21-test run caught a worker signal-lifetime failure on a repeated save.
Completion now delivers to the GUI before releasing/deleting the bridge; the
21-test rerun passed and the expanded 74-test run passed. Blocked-worker parent
removal and close-hold tests use explicit events and bounded readiness checks.
These observations are source/offscreen evidence, not release qualification.
