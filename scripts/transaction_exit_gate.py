"""Fail-closed decision for a docs-only transaction-exit evidence PR update.

Only a synchronize event extending the measured PR head with docs changes can
reuse one complete, closed Windows series. Every uncertain case measures again.
"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from benchmarks import source_scan_exit_series as series
from scripts.scan_characterization_gate import PROTECTED_FILES as OLD_PROTECTED

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PREFIX = "docs/transaction-exit-benchmark-results/"
PROTECTED_FILES = tuple(dict.fromkeys((*OLD_PROTECTED, *series.CODE_FILES,
    "benchmarks/source_scan_exit_probe.py", "benchmarks/source_scan_exit_series.py",
    "tests/test_scan_exit_probe.py", "tests/test_transaction_exit_gate.py",
    "scripts/transaction_exit_gate.py",
    ".github/workflows/transaction-exit-attribution.yml",
    "scripts/check_public_artifacts.py")))
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _git(repo, *args):
    result = subprocess.check_output(["git", *args], cwd=repo,
                                     stderr=subprocess.DEVNULL, timeout=15)
    if len(result) > 4 * 2**20:
        raise ValueError("Unbounded Git result")
    return result


def _parents(repo, commit):
    text = _git(repo, "show", "-s", "--format=%P", commit).decode("ascii").strip()
    return text.split() if text else []


def decision(event, report, merge_sha, *, repo=ROOT, environment=None):
    """Return a public boolean/reason; never echo event or report content."""
    try:
        environment = environment or {}
        if (environment.get("GITHUB_EVENT_NAME") != "pull_request" or
                environment.get("GITHUB_RUN_ATTEMPT") != "1"):
            return True, "measurement_event"
        if not isinstance(event, dict) or event.get("action") != "synchronize":
            return True, "not_synchronize"
        before, after = event.get("before"), event.get("after")
        pr = event.get("pull_request")
        if not isinstance(pr, dict):
            return True, "missing_pr"
        base = pr.get("base", {}).get("sha")
        head = pr.get("head", {}).get("sha")
        if not all(isinstance(item, str) and _SHA.fullmatch(item)
                   for item in (before, after, base, head, merge_sha)):
            return True, "invalid_identity"
        if head != after or before == after:
            return True, "invalid_identity"
        if _git(repo, "rev-parse", "HEAD").decode("ascii").strip() != merge_sha:
            return True, "invalid_checkout"
        if subprocess.run(["git", "merge-base", "--is-ancestor", before, after],
                          cwd=repo, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=15).returncode != 0:
            return True, "not_descendant"
        if _parents(repo, merge_sha) != [base, after]:
            return True, "merge_proof_failed"
        changed = [item.decode("utf-8") for item in _git(
            repo, "diff", "--name-only", "--no-renames", "-z", before, after,
            "--").split(b"\0") if item]
        if not changed or any(not path.startswith("docs/") for path in changed):
            return True, "changed_inputs"
        if not isinstance(report, dict):
            return True, "missing_evidence"
        series.validate_public_report(report)
        if (report["schema"] != series.SERIES_SCHEMA or report["status"] != "complete" or
                report["identity"]["run_id"] == "local" or
                report["identity"]["job_id"] != "windows-series" or
                report["runtime"]["platform"] != "Windows" or
                report["runtime"]["host_kind"] != "github-hosted" or
                report["configuration"] != {"count": 2048, "page_size": 256, "pairs": 4}):
            return True, "evidence_mismatch"
        measured_head = report["identity"]["head_sha"]
        measured_merge = report["code"]["revision"]
        if measured_merge == merge_sha:
            return True, "evidence_revision"
        # Older synthetic PR merge objects may no longer be fetched when a
        # newer synchronize event runs. Check their parents when available;
        # the source-head and protected-byte proof below does not depend on
        # that object's continued reachability. Independent review still
        # attests the archived run/log/artifact origin.
        available = subprocess.run(["git", "cat-file", "-e", measured_merge],
                                   cwd=repo, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15).returncode == 0
        if available and _parents(repo, measured_merge) != [base, measured_head]:
            return True, "evidence_revision"
        if subprocess.run(["git", "merge-base", "--is-ancestor", measured_head, before],
                          cwd=repo, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=15).returncode != 0:
            return True, "evidence_revision"
        since_measurement = [item.decode("utf-8") for item in _git(
            repo, "diff", "--name-only", "--no-renames", "-z", measured_head,
            before, "--").split(b"\0") if item]
        if any(not path.startswith("docs/") for path in since_measurement):
            return True, "changed_inputs"
        if report["code"]["dirty"]:
            return True, "dirty_measurement"
        for path in PROTECTED_FILES:
            current = _git(repo, "show", f"{merge_sha}:{path}")
            if (current != _git(repo, "show", f"{before}:{path}") or
                    current != _git(repo, "show", f"{measured_head}:{path}") or
                    current != (repo / path).read_bytes()):
                return True, "changed_inputs"
        for path, digest in report["code"]["digests"].items():
            if hashlib.sha256(_git(repo, "show", f"{merge_sha}:{path}")).hexdigest() != digest:
                return True, "changed_inputs"
        return False, "verified_docs_only_evidence"
    except (OSError, subprocess.SubprocessError, ValueError, TypeError,
            KeyError, UnicodeError, OverflowError):
        return True, "proof_unavailable"


def _load_evidence(repo, path):
    if (not isinstance(path, str) or not path.startswith(EVIDENCE_PREFIX)
            or ".." in Path(path).parts or not path.endswith(".json")):
        return None
    try:
        data = _git(repo, "show", f"HEAD:{path}")
        if len(data) > 4 * 2**20:
            return None
        return series.old.parse_report(data.decode("utf-8"))
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return None


def _only_evidence_path(repo):
    try:
        paths = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--",
                     EVIDENCE_PREFIX).decode("utf-8").splitlines()
        evidence = [path for path in paths if path.startswith(EVIDENCE_PREFIX)
                    and path.endswith(".json")]
        return evidence[0] if len(evidence) == 1 else None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--event-json", type=Path, default=Path(
        os.environ.get("GITHUB_EVENT_PATH", "")))
    parser.add_argument("--merge-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--evidence")
    parser.add_argument("--github-output", type=Path, default=(
        Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None))
    args = parser.parse_args(argv)
    try:
        data = args.event_json.read_bytes()
        event = series.old.parse_report(data.decode("utf-8")) if len(data) <= 2**20 else None
    except (OSError, UnicodeError, ValueError):
        event = None
    report = _load_evidence(ROOT, args.evidence or _only_evidence_path(ROOT))
    measure, reason = decision(event, report, args.merge_sha, repo=ROOT,
                               environment=dict(os.environ))
    output = {"measure": measure, "reason": reason}
    if args.github_output is not None:
        with args.github_output.open("a", encoding="ascii") as stream:
            stream.write(f"measure={'true' if measure else 'false'}\nreason={reason}\n")
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
