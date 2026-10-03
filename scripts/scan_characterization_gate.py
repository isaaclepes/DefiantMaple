"""Conservative PR publication gate; never turn old evidence into new samples.

Archive execution provenance is independently reviewed before publication. This
gate checks unchanged inputs and a closed, comparable archive, not its origin.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess

from benchmarks import source_scan_profile_series as series, source_scan_soak as soak

EVIDENCE_PREFIX = "benchmarks/source-scan-results/"
PROTECTED_FILES = (*series.CODE_FILES, ".gitattributes", "requirements.txt",
                   ".github/workflows/scan-characterization.yml",
                   "scripts/scan_characterization_gate.py", "tests/test_scan_characterization_gate.py",
                   "tests/test_scan_profile.py", "tests/test_scan_profile_series.py")
MAX_METADATA_BYTES = 2**20
MAX_REPORT_BYTES = 2**22
MAX_PATHS = 2048
MAX_ARCHIVES = 24


@dataclass(frozen=True)
class Decision:
    measure: bool
    reason: str
    evidence: dict | None = None


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _git(root, *arguments, limit=MAX_METADATA_BYTES):
    result = subprocess.run(["git", *arguments], cwd=root, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, check=True, timeout=10)
    if len(result.stdout) > limit:
        raise ValueError("Bounded Git output exceeded")
    return result.stdout


def _paths(raw):
    if not raw or not raw.endswith(b"\0"):
        raise ValueError("Missing complete path list")
    names = raw[:-1].decode("utf-8").split("\0")
    if len(names) > MAX_PATHS or any(not name or name.startswith("/") or
                                  ".." in Path(name).parts for name in names):
        raise ValueError("Invalid bounded path list")
    return names


def _public_file(root, name, maximum):
    path = root / name
    if any((root / Path(*Path(name).parts[:index])).is_symlink()
           for index in range(1, len(Path(name).parts) + 1)):
        raise ValueError("Symbolic input refused")
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Invalid bounded input")
    return path.read_bytes()


def _blob(root, revision, name, maximum):
    reference = f"{revision}:{name}"
    size = int(_git(root, "cat-file", "-s", reference).strip())
    if size > maximum:
        raise ValueError("Bounded Git blob exceeded")
    return _git(root, "show", reference, limit=maximum)


def _accepted_archive(root, digests):
    raw = _git(root, "ls-files", "-z", "--", EVIDENCE_PREFIX)
    if not raw:
        return None
    candidates = [name for name in _paths(raw) if name.endswith(".json")]
    if len(candidates) > MAX_ARCHIVES:
        return None
    accepted = None
    for name in candidates:
        try:
            data = _public_file(root, name, MAX_REPORT_BYTES)
            if data != _blob(root, "HEAD", name, MAX_REPORT_BYTES):
                return None
            report = series.parse_report(data.decode("utf-8"))
            series.validate_public_report(report)
            if (report["schema"] != series.SERIES_SCHEMA or report["status"] != "complete" or
                    report["identity"]["run_id"] == "local" or report["code"]["dirty"] or
                    report["code"]["digests"] != digests or
                    report["configuration"] != {"count": 2048, "page_size": 256, "pairs": 4,
                                                 "platforms": list(series.PLATFORMS)}):
                continue
            expected = soak.fixture_descriptor(2048, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
            if any(pair["runtime"]["host_kind"] != "github-hosted" or pair["code"]["dirty"] or
                   any(sample["trial"]["soak"]["fixture"] != expected for sample in pair["samples"])
                   for pair in report["pairs"]):
                continue
            if accepted is None:
                accepted = {"revision": report["code"]["revision"], **report["identity"],
                            "sha256": hashlib.sha256(data).hexdigest()}
        except (OSError, ValueError, TypeError, KeyError, OverflowError,
                subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    return accepted


def decide(root: Path, event: dict, environment: dict) -> Decision:
    """Only a proven attempt-one docs/evidence synchronization can skip."""
    if (environment.get("GITHUB_EVENT_NAME") != "pull_request" or
            environment.get("GITHUB_RUN_ATTEMPT") != "1" or type(event) is not dict or
            event.get("action") != "synchronize"):
        return Decision(True, "measurement_event")
    try:
        before, after, current = event.get("before"), event.get("after"), environment.get("GITHUB_SHA")
        head, base = event["pull_request"]["head"]["sha"], event["pull_request"]["base"]["sha"]
        if not all(_sha(value) for value in (before, after, current, head, base)) or after != head or before == after:
            return Decision(True, "invalid_event")
        if _git(root, "rev-parse", "HEAD").decode().strip() != current:
            return Decision(True, "invalid_checkout")
        if _git(root, "show", "-s", "--format=%P", current).decode().strip().split() != [base, after]:
            return Decision(True, "invalid_checkout")
        _git(root, "merge-base", "--is-ancestor", before, after)
        changed = _paths(_git(root, "diff", "--name-only", "--no-renames", "-z", before, after, "--"))
        if any(not (name.startswith("docs/") or name.startswith(EVIDENCE_PREFIX)) for name in changed):
            return Decision(True, "changed_inputs")
        digests = {}
        for name in PROTECTED_FILES:
            actual = _public_file(root, name, MAX_METADATA_BYTES)
            if actual != _blob(root, before, name, MAX_METADATA_BYTES) or actual != _blob(root, current, name, MAX_METADATA_BYTES):
                return Decision(True, "changed_inputs")
            if name in series.CODE_FILES:
                digests[name] = hashlib.sha256(actual).hexdigest()
        archive = _accepted_archive(root, digests)
        return Decision(False, "accepted_archive", archive) if archive else Decision(True, "no_accepted_archive")
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return Decision(True, "proof_unavailable")


def main():
    environment = dict(os.environ)
    try:
        event_path = Path(environment["GITHUB_EVENT_PATH"])
        if event_path.is_symlink() or event_path.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError("Invalid bounded event")
        event = series.parse_report(event_path.read_text(encoding="utf-8"))
        decision = decide(series.ROOT, event, environment)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        decision = Decision(True, "proof_unavailable")
    try:
        with Path(environment["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
            stream.write(f"measure={str(decision.measure).lower()}\nreason={decision.reason}\n")
    except (OSError, ValueError, TypeError, KeyError):
        print("Characterization gate output failed.")
        return 1
    summary = "Dedicated characterization will measure: " + decision.reason + ".\n"
    if decision.evidence:
        evidence = decision.evidence
        summary = ("Measurement inputs are unchanged; dedicated pair and aggregate jobs are skipped.\n\n"
                   f"Earlier accepted evidence: run {evidence['run_id']}, attempt {evidence['run_attempt']}, "
                   f"measured revision {evidence['revision']}, archive SHA-256 {evidence['sha256']}.\n\n"
                   "Original evidence identity is preserved. This gate produces no new performance samples.\n")
    if environment.get("GITHUB_STEP_SUMMARY"):
        try:
            with Path(environment["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
                stream.write(summary)
        except OSError:
            print("Characterization gate summary failed.")
            return 1
    print(summary.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
