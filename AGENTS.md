# DefiantMaple contributor guidance

## Start here

- Read [the bounded state and evidence index](docs/current-state.md) before
  selecting work. Recheck Git HEAD and local changes; dated evidence is not live status.
- [SDD v0.2](docs/sdd-v0.2.md) is the forward design specification;
  [ADR 0001](docs/adr-0001-desktop-stack.md) records the Qt/PySide6 decision.
  Requirements describe targets, not completed acceptance or authorization.
- Use [the Qt guide](prototypes/qt/README.md) for gallery behavior and launch
  instructions. Older task briefs and result ledgers remain audit history.

## Commands (repository root)

Use an isolated Python environment and generated fixtures, not real libraries.

```sh
python -m pip install -r requirements.txt -r prototypes/qt/requirements.txt
python -m unittest discover -s tests -v
python -m scripts.check_public_artifacts
QT_QPA_PLATFORM=offscreen python -m unittest discover -s prototypes/qt/tests -v
(umask 077; python -m unittest discover -s tests -p 'test_admission*.py' -v)
```

The environment prefixes and umask command above use POSIX shell syntax. CI
workflow files define the desktop OS/Python matrix. Report passes, failures,
skips, and checks not run with the exact tested source and environment.

## Boundaries

- Preserve stable asset UUIDs, provenance, revision checks, admission refusal,
  preview-before-mutation, and verified backup/restore guarantees. Originals
  remain ordinary files; similarity alone never authorizes destructive cleanup.
- Keep blocking work off the Qt GUI thread. Preserve generation/selection guards,
  truthful unknown outcomes, and explicit readiness assertions in asynchronous tests.
- Work in an isolated branch/worktree. Do not edit or steer another active task's
  checkout, fixtures, runtime, or evidence. Reconcile completed checkpoints first.
- Tests, green CI, compilation, offscreen checks, and native frozen-runtime
  acceptance are distinct evidence. Preserve exact-source/input manifests and
  independent acceptance gates; changed inputs require a fresh applicability review.
- Keep private media, catalogs, local paths, credentials, and raw local receipts
  out of tracked documents. Review new documents as well as running the privacy check.
- Deployment, binary replacement, production-data/credential changes, publication,
  and dependency/environment changes require their own authorized scope.
- Follow [the diagnostic experiment policy](docs/diagnostic-experiment-policy.md).
  Completed measurement cohorts are historical; ordinary edits do not authorize
  fresh diagnostic runs or opt-in CI labels.
