"""One-session Windows transaction-exit experiment on fictional local files."""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

from benchmarks import source_scan_exit_probe as probe
from benchmarks import source_scan_profile_series as old
from benchmarks import source_scan_soak as soak
from defiantmaple.catalog import SCHEMA_VERSION

TRIAL_SCHEMA = "defiantmaple.source-scan-exit-trial.v1"
PAIR_SCHEMA = "defiantmaple.source-scan-exit-pair.v1"
SERIES_SCHEMA = "defiantmaple.source-scan-exit-series.v1"
ORDERS = (("baseline", "instrumented"), ("instrumented", "baseline"),
          ("instrumented", "baseline"), ("baseline", "instrumented"))
CODE_FILES = old.CODE_FILES + ("benchmarks/source_scan_exit_probe.py",
                               "benchmarks/source_scan_exit_series.py")
ROOT = Path(__file__).resolve().parents[1]
ISSUES = old.ISSUES | {"runtime_changed", "session_mismatch"}
NOTE = "Hosted Windows local generated fixture; cache and physical reference hardware uncontrolled."
_UNREAPED = []


class ValidationError(ValueError):
    def __init__(self, code="invalid_report"):
        self.code = code if code in ISSUES else "invalid_report"
        super().__init__(self.code)


def require(condition, code="invalid_report"):
    if not condition:
        raise ValidationError(code)


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def integer(value, low=0, high=10**18):
    require(type(value) is int and low <= value <= high)


def hexstr(value, length):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None)


def parameters(count, page_size, pairs, pair_index=None):
    require(type(count) is int and 64 <= count <= 2048, "invalid_arguments")
    require(type(page_size) is int and 1 <= page_size <= count, "invalid_arguments")
    require(pairs == 4 and type(pairs) is int, "invalid_arguments")
    if pair_index is not None:
        require(type(pair_index) is int and 1 <= pair_index <= 4, "invalid_arguments")


def _dirty(paths):
    return bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
        cwd=ROOT, stderr=subprocess.DEVNULL, timeout=10))


def actual_identity(revision=None, run_id="local", run_attempt=1,
                    job_id="local", session_token=None, head_sha="local"):
    base, _ = old.actual_identity(revision, run_id, run_attempt)
    actual_job = os.environ.get("GITHUB_JOB", "local")
    require(type(job_id) is str and job_id == actual_job and
            re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id) is not None, "identity_mismatch")
    require(session_token is not None, "session_mismatch")
    hexstr(session_token, 32)
    if run_id == "local":
        require(head_sha == "local", "identity_mismatch")
    else:
        hexstr(head_sha, 40)
    digests = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in CODE_FILES}
    code = {"revision": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL,
        timeout=10, text=True).strip(), "dirty": _dirty(CODE_FILES),
        "checkout_dirty": _dirty(()), "digests": digests}
    if run_id != "local":
        parents = subprocess.check_output(
            ["git", "show", "-s", "--format=%P", code["revision"]],
            cwd=ROOT, stderr=subprocess.DEVNULL, timeout=10, text=True).strip().split()
        require(len(parents) == 2 and parents[1] == head_sha, "identity_mismatch")
    return {**base, "job_id": job_id, "session_token": session_token,
            "head_sha": head_sha}, code


def runtime_metadata():
    return old.runtime_metadata()


def _validate_identity(value):
    keys(value, ("run_id", "run_attempt", "job_id", "session_token", "head_sha"))
    old._validate_identity({key: value[key] for key in ("run_id", "run_attempt")})
    require(type(value["job_id"]) is str and
            re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value["job_id"]) is not None)
    hexstr(value["session_token"], 32)
    if value["run_id"] == "local":
        require(value["head_sha"] == "local")
    else:
        hexstr(value["head_sha"], 40)


def _validate_code(value):
    keys(value, ("revision", "dirty", "checkout_dirty", "digests"))
    hexstr(value["revision"], 40)
    require(type(value["dirty"]) is bool and type(value["checkout_dirty"]) is bool)
    keys(value["digests"], CODE_FILES)
    for digest in value["digests"].values():
        hexstr(digest, 64)


def _code_key(value):
    return {key: item for key, item in value.items() if key != "checkout_dirty"}


def _validate_issues(value):
    require(type(value) is list)
    for item in value:
        keys(item, ("code", "error_type"))
        require(item["code"] in ISSUES and item["error_type"] in old.ERROR_TYPES | {None})


def _error_type(exc):
    if exc is None:
        return None
    if isinstance(exc, ValidationError):
        return "ValueError"
    return type(exc).__name__ if type(exc).__name__ in old.ERROR_TYPES else "UnexpectedError"


def issue(code, exc=None):
    return {"code": code, "error_type": _error_type(exc)}


def _metric(value):
    keys(value, ("count", "total_ns", "min_ns", "max_ns", "buckets"))
    integer(value["count"], 0, 1_000_000)
    integer(value["total_ns"])
    require(type(value["buckets"]) is list and
            len(value["buckets"]) == len(probe.BUCKET_UPPER_NS) + 1)
    for count in value["buckets"]:
        integer(count, 0, 1_000_000)
    require(sum(value["buckets"]) == value["count"])
    if value["count"] == 0:
        require(value["total_ns"] == 0 and value["min_ns"] is None and value["max_ns"] is None)
    else:
        integer(value["min_ns"])
        integer(value["max_ns"], value["min_ns"])
        require(value["count"] * value["min_ns"] <= value["total_ns"] <=
                value["count"] * value["max_ns"])
        boundaries = (0, *probe.BUCKET_UPPER_NS, 10**18 + 1)
        active = [index for index, count in enumerate(value["buckets"]) if count]
        require(boundaries[active[0]] <= value["min_ns"] < boundaries[active[0] + 1]
                and boundaries[active[-1]] <= value["max_ns"] < boundaries[active[-1] + 1])
        if value["count"] == 1:
            require(value["min_ns"] == value["max_ns"] == value["total_ns"])
        else:
            remaining = list(value["buckets"])
            remaining[active[0]] -= 1
            remaining[active[-1]] -= 1
            require(all(count >= 0 for count in remaining))
            lower = value["min_ns"] + value["max_ns"] + sum(
                count * boundaries[index] for index, count in enumerate(remaining))
            upper = value["min_ns"] + value["max_ns"] + sum(
                count * (boundaries[index + 1] - 1) for index, count in enumerate(remaining))
            require(lower <= value["total_ns"] <= upper)


def validate_trial(value):
    keys(value, ("schema", "status", "variant", "identity", "code", "runtime",
                 "configuration", "soak", "phases"))
    require(value["schema"] == TRIAL_SCHEMA and value["status"] == "complete")
    require(value["variant"] in ("baseline", "instrumented"))
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    old._validate_runtime(value["runtime"])
    keys(value["configuration"], ("count", "page_size"))
    count, page_size = (value["configuration"][key] for key in ("count", "page_size"))
    parameters(count, page_size, 4)
    if value["identity"]["run_id"] != "local":
        require((count, page_size, value["runtime"]["platform"]) == (2048, 256, "Windows"))
    old._validate_soak(value["soak"], count, page_size, value["runtime"])
    require(value["soak"]["fixture"]["recipe"] == soak.CANONICAL_FIXTURE_RECIPE)
    if value["variant"] == "baseline":
        keys(value["phases"], ())
        return
    keys(value["phases"], probe.PHASES)
    for name, phase in value["phases"].items():
        keys(phase, ("elapsed_ns", "strata"))
        integer(phase["elapsed_ns"])
        keys(phase["strata"], probe.STRATA)
        for metric in phase["strata"].values():
            _metric(metric)
        require(sum(item["total_ns"] for item in phase["strata"].values()) <=
                phase["elapsed_ns"])
    for phase, interval in (("observation", "observation"), ("indexing", "indexing")):
        require(value["phases"][phase]["elapsed_ns"] <= value["soak"]["timings_ns"][interval])
    require(value["phases"]["fresh_resume"]["elapsed_ns"] +
            value["phases"]["stable_followup"]["elapsed_ns"] <=
            value["soak"]["timings_ns"]["fresh_resume"])


def validate_pair(value):
    keys(value, ("schema", "status", "identity", "code", "runtime", "configuration",
                 "order", "samples", "wall_ns", "cleanup", "issues"))
    require(value["schema"] == PAIR_SCHEMA and value["status"] in ("complete", "incomplete"))
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    old._validate_runtime(value["runtime"])
    keys(value["configuration"], ("count", "page_size", "pairs", "pair_index"))
    config = value["configuration"]
    parameters(config["count"], config["page_size"], config["pairs"], config["pair_index"])
    require(value["order"] == list(ORDERS[config["pair_index"] - 1]))
    integer(value["wall_ns"])
    keys(value["cleanup"], ("workers_reaped", "owned_storage_removed", "storage_retained"))
    require(all(type(item) is bool for item in value["cleanup"].values()))
    require(not value["cleanup"]["owned_storage_removed"] or
            (value["cleanup"]["workers_reaped"] and not value["cleanup"]["storage_retained"]))
    _validate_issues(value["issues"])
    require(type(value["samples"]) is list and len(value["samples"]) <= 2)
    for position, sample in enumerate(value["samples"], 1):
        keys(sample, ("position", "trial"))
        integer(sample["position"], position, position)
        trial = sample["trial"]
        validate_trial(trial)
        require(trial["variant"] == value["order"][position - 1] and
                trial["identity"] == value["identity"] and
                _code_key(trial["code"]) == _code_key(value["code"]) and
                trial["runtime"] == value["runtime"] and
                trial["configuration"] == {key: config[key] for key in ("count", "page_size")})
        require(trial["soak"]["fixture"] == value["samples"][0]["trial"]["soak"]["fixture"])
        require(trial["soak"]["catalog_schema_version"] ==
                value["samples"][0]["trial"]["soak"]["catalog_schema_version"])
    if value["status"] == "complete":
        require(len(value["samples"]) == 2 and not value["issues"] and
                value["cleanup"] == {"workers_reaped": True, "owned_storage_removed": True,
                                     "storage_retained": False})
    else:
        require(bool(value["issues"]))


def _attribution(pairs):
    ratios, strata = [], []
    for pair in pairs:
        trials = {item["trial"]["variant"]: item["trial"] for item in pair["samples"]}
        baseline = trials["baseline"]["soak"]["timings_ns"]["indexing"]
        measured = trials["instrumented"]["soak"]["timings_ns"]["indexing"]
        ratio = measured / baseline if baseline else None
        phase = trials["instrumented"]["phases"]["indexing"]
        winner = [name for name, metric in phase["strata"].items()
                  if metric["total_ns"] * 2 > measured]
        ratios.append({"pair_index": pair["configuration"]["pair_index"], "ratio": ratio})
        strata.append(winner[0] if len(winner) == 1 else None)
    return {"indexing_ratios": ratios, "dominant_strata": strata,
            "verdict": "attributed" if all(item["ratio"] is not None and
                    .80 <= item["ratio"] <= 1.25 for item in ratios) and
                    strata[0] is not None and len(set(strata)) == 1 else "inconclusive"}


def validate_series(value):
    keys(value, ("schema", "status", "identity", "code", "runtime", "configuration",
                 "pairs", "issues", "note") + (("attribution",) if
                 value.get("status") == "complete" else ()))
    require(value["schema"] == SERIES_SCHEMA and value["status"] in ("complete", "incomplete")
            and value["note"] == NOTE)
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    old._validate_runtime(value["runtime"])
    keys(value["configuration"], ("count", "page_size", "pairs"))
    config = value["configuration"]
    parameters(config["count"], config["page_size"], config["pairs"])
    if value["identity"]["run_id"] != "local":
        require((config["count"], config["page_size"], value["runtime"]["platform"]) ==
                (2048, 256, "Windows"))
    require(type(value["pairs"]) is list and len(value["pairs"]) <= 4)
    for index, pair in enumerate(value["pairs"], 1):
        validate_pair(pair)
        require(pair["configuration"] == {**config, "pair_index": index} and
                pair["identity"] == value["identity"] and
                _code_key(pair["code"]) == _code_key(value["code"]) and
                pair["runtime"] == value["runtime"])
    require(len({sample["trial"]["soak"]["catalog_schema_version"]
                 for pair in value["pairs"] for sample in pair["samples"]}) <= 1)
    _validate_issues(value["issues"])
    if value["status"] == "complete":
        require(len(value["pairs"]) == 4 and not value["issues"] and
                all(pair["status"] == "complete" for pair in value["pairs"]))
        require(value["attribution"] == _attribution(value["pairs"]))
    else:
        require(bool(value["issues"]) and
                (not value["pairs"] or all(pair["status"] == "complete" for pair in value["pairs"][:-1])))


def validate_public_report(value):
    require(type(value) is dict)
    if set(value) == {"schema", "status", "samples", "issues"}:
        require(value["schema"] in (TRIAL_SCHEMA, PAIR_SCHEMA, SERIES_SCHEMA) and
                value["status"] == "incomplete" and value["samples"] == [])
        _validate_issues(value["issues"])
        require(bool(value["issues"]))
        return
    {TRIAL_SCHEMA: validate_trial, PAIR_SCHEMA: validate_pair,
     SERIES_SCHEMA: validate_series}[value["schema"]](value)


def _child_root():
    raw = os.environ.get("DEFIANTMAPLE_EXIT_TRIAL_ROOT")
    token = os.environ.get("DEFIANTMAPLE_EXIT_TRIAL_TOKEN")
    require(raw is not None and token is not None, "storage_ownership")
    hexstr(token, 64)
    root = Path(raw)
    require(not root.is_symlink() and root.is_dir() and
            (root / ".owned-exit-trial").read_text(encoding="ascii") == token,
            "storage_ownership")
    tempfile.tempdir = str(root)


def run_trial(count, page_size, variant, *, revision=None, run_id="local",
              run_attempt=1, job_id="local", head_sha="local", session_token):
    parameters(count, page_size, 4)
    require(variant in ("baseline", "instrumented"), "invalid_arguments")
    identity, code = actual_identity(revision, run_id, run_attempt, job_id, session_token, head_sha)
    runtime = runtime_metadata()
    measured = probe.run_trial(count, page_size, variant)
    later_identity, later_code = actual_identity(revision, run_id, run_attempt, job_id, session_token, head_sha)
    require(identity == later_identity and _code_key(code) == _code_key(later_code), "code_changed")
    require(runtime == runtime_metadata(), "runtime_changed")
    result = {"schema": TRIAL_SCHEMA, "status": "complete", "variant": variant,
              "identity": identity, "code": code, "runtime": runtime,
              "configuration": {"count": count, "page_size": page_size}, **measured}
    validate_trial(result)
    require(result["soak"]["catalog_schema_version"] == SCHEMA_VERSION, "incomparable")
    require(result["soak"]["fixture"] == soak.fixture_descriptor(
        count, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE))
    return result


def _reap(process, grace=5):
    for action in ("terminate", "kill"):
        try:
            getattr(process, action)()
        except BaseException:
            pass
        try:
            process.communicate(timeout=grace)
            if process.poll() is not None:
                return True
        except BaseException:
            pass
    try:
        return process.poll() is not None
    except BaseException:
        return False


def _run_child(command, environment, timeout):
    process = subprocess.Popen(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException as exc:
        reaped = _reap(process)
        if not reaped:
            _UNREAPED.append(process)
        return None, issue("child_timeout" if isinstance(exc, subprocess.TimeoutExpired)
                           else "child_failed", exc), reaped
    if process.poll() is None:
        _UNREAPED.append(process)
        return None, issue("child_not_reaped"), False
    if process.returncode:
        return None, issue("child_failed"), True
    try:
        require(len(stdout) <= 2**22)
        value = old.parse_report(stdout)
        validate_trial(value)
        return value, None, True
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return None, issue("invalid_report", exc), True


def run_pair(count=2048, page_size=256, pairs=4, pair_index=1, *, trial_timeout=1440,
             pair_timeout=3000, revision=None, run_id="local", run_attempt=1,
             job_id="local", head_sha="local", session_token):
    parameters(count, page_size, pairs, pair_index)
    for duration, maximum in ((trial_timeout, 1440), (pair_timeout, 3000)):
        require(type(duration) in (int, float) and math.isfinite(duration) and
                0 < duration <= maximum, "invalid_arguments")
    identity, code = actual_identity(revision, run_id, run_attempt, job_id, session_token, head_sha)
    runtime = runtime_metadata()
    if run_id != "local":
        require((count, page_size, runtime["platform"]) == (2048, 256, "Windows"),
                "invalid_arguments")
    started = time.perf_counter_ns()
    report = {"schema": PAIR_SCHEMA, "status": "incomplete", "identity": identity,
              "code": code, "runtime": runtime,
              "configuration": {"count": count, "page_size": page_size,
                                "pairs": pairs, "pair_index": pair_index},
              "order": list(ORDERS[pair_index - 1]), "samples": [], "wall_ns": 0,
              "cleanup": {"workers_reaped": True, "owned_storage_removed": False,
                          "storage_retained": True}, "issues": []}
    token = secrets.token_hex(32)
    owned = Path(tempfile.mkdtemp(prefix="defiantmaple-exit-pair-")).resolve()
    marker = owned / ".owned-exit-pair"
    owner_identity = (owned.stat().st_dev, owned.stat().st_ino)
    try:
        marker.write_text(token, encoding="ascii")
        for position, variant in enumerate(report["order"], 1):
            remaining = pair_timeout - (time.perf_counter_ns() - started) / 1e9
            if remaining <= 0:
                report["issues"].append(issue("pair_deadline"))
                break
            child_root = owned / f"trial-{position}"
            child_root.mkdir()
            (child_root / ".owned-exit-trial").write_text(token, encoding="ascii")
            environment = dict(os.environ, TMPDIR=str(child_root), TEMP=str(child_root),
                               TMP=str(child_root), DEFIANTMAPLE_EXIT_TRIAL_ROOT=str(child_root),
                               DEFIANTMAPLE_EXIT_TRIAL_TOKEN=token)
            command = [sys.executable, "-W", "error::ResourceWarning", "-m",
                       "benchmarks.source_scan_exit_series", "trial", "--count", str(count),
                       "--page-size", str(page_size), "--variant", variant,
                       "--revision", code["revision"], "--run-id", run_id,
                       "--run-attempt", str(run_attempt), "--job-id", job_id,
                       "--head-sha", head_sha,
                       "--session-token", session_token]
            trial, failure, reaped = _run_child(command, environment,
                                                min(trial_timeout, remaining))
            report["cleanup"]["workers_reaped"] &= reaped
            if failure is not None:
                report["issues"].append(failure)
                break
            require(trial["identity"] == identity and
                    _code_key(trial["code"]) == _code_key(code) and
                    trial["runtime"] == runtime and trial["variant"] == variant and
                    trial["configuration"] == {"count": count, "page_size": page_size},
                    "identity_mismatch")
            require(trial["soak"]["catalog_schema_version"] == SCHEMA_VERSION, "incomparable")
            report["samples"].append({"position": position, "trial": trial})
        later_identity, later_code = actual_identity(revision, run_id, run_attempt,
                                                    job_id, session_token, head_sha)
        require(identity == later_identity and _code_key(code) == _code_key(later_code),
                "code_changed")
        require(runtime == runtime_metadata(), "runtime_changed")
        if (time.perf_counter_ns() - started) / 1e9 > pair_timeout:
            report["issues"].append(issue("pair_deadline"))
    except BaseException as exc:
        report["issues"].append(issue(exc.code if isinstance(exc, ValidationError)
                                      else "child_failed", exc))
    finally:
        if report["cleanup"]["workers_reaped"]:
            try:
                require(not owned.is_symlink() and owned.is_dir() and
                        (owned.stat().st_dev, owned.stat().st_ino) == owner_identity and
                        marker.read_text(encoding="ascii") == token, "storage_ownership")
                shutil.rmtree(owned)
                report["cleanup"].update(owned_storage_removed=True, storage_retained=False)
            except (OSError, ValidationError) as exc:
                report["issues"].append(issue("cleanup_failed", exc))
    report["wall_ns"] = time.perf_counter_ns() - started
    if report["wall_ns"] / 1e9 > pair_timeout:
        report["issues"].append(issue("pair_deadline"))
    if len(report["samples"]) == 2 and not report["issues"]:
        report["status"] = "complete"
    validate_pair(report)
    return report


def run_series(count=2048, page_size=256, pairs=4, *, trial_timeout=1440,
               pair_timeout=3000, revision=None, run_id="local",
               run_attempt=1, job_id="local", head_sha="local", session_token=None):
    parameters(count, page_size, pairs)
    session_token = session_token or secrets.token_hex(16)
    identity, code = actual_identity(revision, run_id, run_attempt, job_id, session_token, head_sha)
    runtime = runtime_metadata()
    if run_id != "local":
        require((count, page_size, runtime["platform"]) == (2048, 256, "Windows"),
                "invalid_arguments")
    report = {"schema": SERIES_SCHEMA, "status": "incomplete", "identity": identity,
              "code": code, "runtime": runtime,
              "configuration": {"count": count, "page_size": page_size, "pairs": pairs},
              "pairs": [], "issues": [], "note": NOTE}
    for index in range(1, pairs + 1):
        try:
            pair = run_pair(count, page_size, pairs, index, trial_timeout=trial_timeout,
                            pair_timeout=pair_timeout, revision=revision,
                            run_id=run_id, run_attempt=run_attempt, job_id=job_id,
                            head_sha=head_sha,
                            session_token=session_token)
            require(all(sample["trial"]["soak"]["catalog_schema_version"] == SCHEMA_VERSION
                        for sample in pair["samples"]), "incomparable")
            report["pairs"].append(pair)
            if pair["status"] != "complete":
                report["issues"].append(issue(pair["issues"][0]["code"]))
                break
        except BaseException as exc:
            report["issues"].append(issue(exc.code if isinstance(exc, ValidationError)
                                          else "child_failed", exc))
            break
    try:
        later_identity, later_code = actual_identity(revision, run_id, run_attempt,
                                                    job_id, session_token, head_sha)
        require(identity == later_identity and _code_key(code) == _code_key(later_code),
                "code_changed")
        require(runtime == runtime_metadata(), "runtime_changed")
    except BaseException as exc:
        report["issues"].append(issue(exc.code if isinstance(exc, ValidationError)
                                      else "runtime_changed", exc))
    if len(report["pairs"]) == 4 and not report["issues"]:
        report["status"] = "complete"
        report["attribution"] = _attribution(report["pairs"])
    validate_series(report)
    return report


def write_report(path, report):
    validate_public_report(report)
    target = Path(path)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix="exit-metrics-", suffix=".tmp",
                                            dir=target.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _Parser(ArgumentParser):
    def error(self, message):
        raise ValidationError("invalid_arguments")


def _parser():
    parser = _Parser(prog="source_scan_exit_series", description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True, parser_class=_Parser)
    for mode in ("trial", "pair", "series"):
        command = modes.add_parser(mode)
        command.add_argument("--count", type=int, default=2048)
        command.add_argument("--page-size", type=int, default=256)
        command.add_argument("--revision")
        command.add_argument("--run-id", default="local")
        command.add_argument("--run-attempt", type=int, default=1)
        command.add_argument("--job-id", default="local")
        command.add_argument("--head-sha", default="local")
        command.add_argument("--session-token")
        command.add_argument("--metrics", type=Path)
        if mode == "trial":
            command.add_argument("--variant", required=True,
                                 choices=("baseline", "instrumented"))
        else:
            command.add_argument("--pairs", type=int, default=4)
            command.add_argument("--trial-timeout", type=float, default=1440)
            command.add_argument("--pair-timeout", type=float, default=3000)
        if mode == "pair":
            command.add_argument("--pair-index", type=int, required=True)
    return parser


def main(argv=None):
    args = None
    report = None
    schema = SERIES_SCHEMA
    try:
        args = _parser().parse_args(argv)
        schema = {"trial": TRIAL_SCHEMA, "pair": PAIR_SCHEMA,
                  "series": SERIES_SCHEMA}[args.mode]
        identity = {key: getattr(args, key) for key in
                    ("revision", "run_id", "run_attempt", "job_id", "head_sha")}
        if args.mode == "trial":
            _child_root()
            report = run_trial(args.count, args.page_size, args.variant,
                               session_token=args.session_token, **identity)
        elif args.mode == "pair":
            report = run_pair(args.count, args.page_size, args.pairs, args.pair_index,
                              trial_timeout=args.trial_timeout, pair_timeout=args.pair_timeout,
                              session_token=args.session_token or secrets.token_hex(16), **identity)
        else:
            report = run_series(args.count, args.page_size, args.pairs,
                                trial_timeout=args.trial_timeout,
                                pair_timeout=args.pair_timeout,
                                session_token=args.session_token, **identity)
        validate_public_report(report)
        if args.metrics is not None:
            write_report(args.metrics, report)
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code == 0:
            return 0
        report = {"schema": schema, "status": "incomplete", "samples": [],
                  "issues": [issue(exc.code if isinstance(exc, ValidationError)
                                   else "invalid_report", exc)]}
        if args is not None and args.metrics is not None:
            try:
                write_report(args.metrics, report)
            except (OSError, ValueError):
                report["issues"].append(issue("output_failed"))
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
