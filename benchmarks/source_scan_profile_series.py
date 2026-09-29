"""Balanced fictional scan trials and strict aggregate-only hosted evidence.

No source/catalog input is accepted. Children receive newly owned temporary
storage; incomplete work never produces a complete-series timing summary.
"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

from PIL import __version__ as pillow_version, features

from benchmarks import source_scan_profile as profile, source_scan_soak as soak
from defiantmaple.catalog import SCHEMA_VERSION

TRIAL_SCHEMA = "defiantmaple.source-scan-profile-trial.v1"
PAIR_SCHEMA = "defiantmaple.source-scan-profile-pair.v1"
SERIES_SCHEMA = "defiantmaple.source-scan-profile-series.v1"
PLATFORMS = ("Linux", "Darwin", "Windows")
ORDERS = (("baseline", "instrumented"), ("instrumented", "baseline"),
          ("instrumented", "baseline"), ("baseline", "instrumented"))
INTERVALS = ("observation", "indexing", "fresh_resume")
CODE_FILES = ("benchmarks/source_scan_profile.py", "benchmarks/source_scan_soak.py",
              "benchmarks/source_scan_profile_series.py", "defiantmaple/catalog.py",
              "defiantmaple/sources.py", "defiantmaple/media.py")
ROOT = Path(__file__).resolve().parents[1]
NOTE = "Balanced generated local-file trials; hosted jobs sample a runner pool; no hardware budget."
ISSUES = {"invalid_arguments", "identity_mismatch", "code_changed", "invalid_report",
          "child_failed", "child_timeout", "child_not_reaped", "pair_deadline",
          "cleanup_failed", "storage_ownership", "missing_pair", "duplicate_pair",
          "unexpected_pair", "incomparable", "output_failed", "interrupted"}
ERROR_TYPES = {"OSError", "PermissionError", "TimeoutExpired", "ValueError", "RuntimeError",
               "AssertionError", "JSONDecodeError", "KeyboardInterrupt", "UnexpectedError"}
TOTALS = {"indexed", "updated", "renamed", "pending", "ignored_existing", "unchanged",
          "unsupported", "missing", "overlap_skipped", "errors"}
MIN_PNG_BYTES = 57  # Signature and required chunk framing, before image data.
MAX_PNG_BYTES = 8192  # Conservative encoded-size guard for this fixed 32x32 recipe.
_UNREAPED = []  # Keep unreaped handles/storage alive; never delete their owned trees.


class ValidationError(ValueError):
    def __init__(self, code="invalid_report"):
        self.code = code if code in ISSUES else "invalid_report"
        super().__init__(self.code)


def _require(condition, code="invalid_report"):
    if not condition:
        raise ValidationError(code)


def _keys(value, expected):
    _require(type(value) is dict and set(value) == set(expected))


def _integer(value, low=0, high=10**15):
    _require(type(value) is int and low <= value <= high)


def _number(value):
    _require(type(value) in (int, float) and 0 <= value <= 10**15 and math.isfinite(value))


def _hex(value, length):
    _require(type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None)


def _safe_error(exc):
    if isinstance(exc, ValidationError):
        return "ValueError"
    name = type(exc).__name__
    return name if name in ERROR_TYPES else "UnexpectedError"


def _issue(code, exc=None):
    return {"code": code, "error_type": _safe_error(exc) if exc is not None else None}


def _validate_issues(value):
    _require(type(value) is list)
    for item in value:
        _keys(item, ("code", "error_type"))
        _require(item["code"] in ISSUES and item["error_type"] in ERROR_TYPES | {None})


def _parameters(count, page_size, pairs, pair_index=None):
    _require(type(count) is int and 64 <= count <= 2048, "invalid_arguments")
    _require(type(page_size) is int and 1 <= page_size <= count, "invalid_arguments")
    _require(type(pairs) is int and pairs in (2, 4), "invalid_arguments")
    if pair_index is not None:
        _require(type(pair_index) is int and 1 <= pair_index <= pairs, "invalid_arguments")


def actual_identity(revision=None, run_id="local", run_attempt=1):
    actual_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL,
        timeout=10, text=True).strip()
    _hex(actual_revision, 40)
    _require(revision is None or revision == actual_revision, "identity_mismatch")
    actual_run = os.environ.get("GITHUB_RUN_ID", "local")
    actual_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    _require(re.fullmatch(r"[1-9][0-9]*|local", actual_run) is not None, "identity_mismatch")
    _require(re.fullmatch(r"[1-9][0-9]*", actual_attempt) is not None, "identity_mismatch")
    _require(run_id == actual_run and type(run_attempt) is int
             and run_attempt == int(actual_attempt), "identity_mismatch")
    digests = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CODE_FILES}
    def dirty(paths):
        result = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
            cwd=ROOT, stderr=subprocess.DEVNULL, timeout=10)
        return bool(result)
    code = {"revision": actual_revision, "dirty": dirty(CODE_FILES),
            "checkout_dirty": dirty(()), "digests": digests}
    return {"run_id": actual_run, "run_attempt": int(actual_attempt)}, code


def _code_key(code):
    return {key: value for key, value in code.items() if key != "checkout_dirty"}


def runtime_metadata():
    runner = os.environ.get("RUNNER_ENVIRONMENT")
    host_kind = {"github-hosted": "github-hosted", "self-hosted": "self-hosted"}.get(runner, "unverified")
    result = {"platform": platform.system(), "machine": platform.machine(),
              "os_release": re.match(r"[0-9]+(?:\.[0-9]+){0,3}", platform.release()).group(0)
                  if re.match(r"[0-9]+(?:\.[0-9]+){0,3}", platform.release()) else None,
              "python_implementation": platform.python_implementation(),
              "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version,
              "pillow_version": pillow_version, "png_zlib_version": features.version_codec("zlib"),
              "cpu_logical_count": os.cpu_count(), "host_kind": host_kind,
              "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
              "cpu_model": None, "ram_total_bytes": None, "filesystem": None, "storage": None,
              "power_policy": None, "antivirus": None}
    _validate_runtime(result)
    return result


def _validate_code(value):
    _keys(value, ("revision", "dirty", "checkout_dirty", "digests"))
    _hex(value["revision"], 40)
    _require(type(value["dirty"]) is bool and type(value["checkout_dirty"]) is bool)
    _keys(value["digests"], CODE_FILES)
    for digest in value["digests"].values():
        _hex(digest, 64)


def _validate_identity(value):
    _keys(value, ("run_id", "run_attempt"))
    _require(type(value["run_id"]) is str and re.fullmatch(r"[1-9][0-9]*|local", value["run_id"]) is not None)
    _integer(value["run_attempt"], 1, 10**6)


def _validate_runtime(value):
    _keys(value, ("platform", "machine", "os_release", "python_implementation", "python_version",
                  "sqlite_version", "pillow_version", "png_zlib_version", "cpu_logical_count", "host_kind",
                  "runner_image", "runner_image_version", "cpu_model", "ram_total_bytes", "filesystem",
                  "storage", "power_policy", "antivirus"))
    _require(value["platform"] in PLATFORMS)
    _require(value["machine"] in ("x86_64", "AMD64", "arm64", "aarch64", "x86", "i386", "i686"))
    _require(value["python_implementation"] in ("CPython", "PyPy"))
    for key in ("python_version", "sqlite_version", "pillow_version"):
        _require(type(value[key]) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", value[key]) is not None)
    _require(type(value["png_zlib_version"]) is str and
             re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:\.zlib-ng)?", value["png_zlib_version"]) is not None)
    for key in ("os_release", "runner_image_version"):
        _require(value[key] is None or (type(value[key]) is str and
                 re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", value[key]) is not None))
    _require(value["runner_image"] is None or (type(value["runner_image"]) is str and
             re.fullmatch(r"ubuntu[0-9]{2}|win[0-9]{2}|win25-vs2026|macos-?[0-9]{2}(?:-arm64)?", value["runner_image"]) is not None))
    if value["cpu_logical_count"] is not None:
        _integer(value["cpu_logical_count"], 1, 10**5)
    _require(value["host_kind"] in ("github-hosted", "self-hosted", "unverified"))
    _require(all(value[key] is None for key in ("cpu_model", "ram_total_bytes", "filesystem", "storage",
                                              "power_policy", "antivirus")))


def _validate_fixture(value, count):
    # An archive describes the producer's encoder, not the reader's encoder.
    # Authenticate fixed recipe shape and cycle/prefix byte arithmetic without
    # recompressing PNGs under a potentially different Pillow/zlib runtime.
    _require(type(value) is dict)
    recipe = value.get("recipe")
    _require(recipe in (soak.FIXTURE_RECIPE, soak.CANONICAL_FIXTURE_RECIPE))
    fixed = {"recipe": recipe, "width": 32, "height": 32, "mode": "RGBA",
             "encoded_contents": 8, "directory_group_size": 256,
             "initial_files": count, "resume_added_files": 1}
    _keys(value, (*fixed, "initial_bytes", "resume_added_bytes"))
    for key, expected in fixed.items():
        if type(expected) is int:
            _integer(value[key])
        _require(value[key] == expected)
    _integer(value["initial_bytes"], count * MIN_PNG_BYTES, count * MAX_PNG_BYTES)
    _integer(value["resume_added_bytes"], MIN_PNG_BYTES, MAX_PNG_BYTES)
    if recipe == soak.CANONICAL_FIXTURE_RECIPE:
        # Immutable public corpus; no runtime PNG encoding or mutable producer
        # state is needed to read its archived descriptor.
        _require(value["initial_bytes"] == sum(soak.CANONICAL_PNG_SIZES[index % 8]
                                               for index in range(count))
                 and value["resume_added_bytes"] == soak.CANONICAL_PNG_SIZES[0])
        return
    cycles, prefix = divmod(count, 8)
    remaining = value["initial_bytes"] - (cycles + bool(prefix)) * value["resume_added_bytes"]
    # The first payload is known from the resume addition. Other prefix payloads
    # appear cycles+1 times and the rest cycles times. Check an integer solution
    # within encoded-size guards; nonmultiples of eight remain supported.
    longer = max(prefix - 1, 0)
    shorter = 7 - longer
    low = max(longer * MIN_PNG_BYTES, (remaining - cycles * shorter * MAX_PNG_BYTES + cycles) // (cycles + 1))
    high = min(longer * MAX_PNG_BYTES, (remaining - cycles * shorter * MIN_PNG_BYTES) // (cycles + 1))
    _require(low + (remaining - low) % cycles <= high)


def _validate_soak(value, count, page_size, runtime):
    _keys(value, ("schema", "platform", "python_version", "fixture_kind", "file_count", "page_size",
                  "observation_pages", "index_pages", "observation_seconds", "index_seconds",
                  "fresh_resume_seconds", "timings_ns", "catalog_schema_version", "fixture", "memory_scope",
                  "cache_scope", "python_peak_allocated_bytes", "assets_after_recovery", "interruption_resumed",
                  "offline_retained_assets", "source_files_unchanged", "source_bytes_unchanged", "stable_identity_retained", "note"))
    _require(value["schema"] == "defiantmaple.source-scan-soak.v1")
    _require(value["platform"] == runtime["platform"] and value["python_version"] == runtime["python_version"])
    _require(value["fixture_kind"] == "generated-fictional-png" and value["file_count"] == count
             and value["page_size"] == page_size and value["catalog_schema_version"] == SCHEMA_VERSION)
    for key in ("file_count", "page_size", "catalog_schema_version"):
        _integer(value[key], 1)
    _validate_fixture(value["fixture"], count)
    _require(value["memory_scope"] == soak.MEMORY_SCOPE and value["cache_scope"] == soak.CACHE_SCOPE)
    _require(value["note"] == "Local generated fixture; no real network share or native watcher tested.")
    _require(all(value[key] is True for key in ("interruption_resumed", "offline_retained_assets",
                 "source_files_unchanged", "source_bytes_unchanged", "stable_identity_retained")))
    _integer(value["python_peak_allocated_bytes"])
    _integer(value["assets_after_recovery"], count + 1, count + 1)
    for key in ("observation_pages", "index_pages"):
        _integer(value[key], math.ceil(count / page_size), math.ceil(count / page_size))
    _keys(value["timings_ns"], INTERVALS)
    for interval, old_key in zip(INTERVALS, ("observation_seconds", "index_seconds", "fresh_resume_seconds")):
        duration = value["timings_ns"][interval]
        _integer(duration)
        _number(value[old_key])
        _require(value[old_key] == round(duration / 1e9, 3))


def _validate_phases(value, count, page_size, variant, fixture):
    if variant == "baseline":
        _keys(value, ())
        return
    _keys(value, profile.PHASES)
    for name, phase in value.items():
        _keys(phase, ("elapsed_ns", "elapsed_seconds", "operations", "counts") +
                    (("pages", "totals") if name != "offline" else ()))
        _integer(phase["elapsed_ns"])
        _number(phase["elapsed_seconds"])
        _require(phase["elapsed_seconds"] == phase["elapsed_ns"] / 1e9)
        _keys(phase["operations"], profile.OPERATIONS)
        for operation in phase["operations"].values():
            _keys(operation, ("calls", "failures", "inclusive_ns", "exclusive_ns", "inclusive_seconds", "exclusive_seconds"))
            for key in ("calls", "failures", "inclusive_ns", "exclusive_ns"):
                _integer(operation[key])
            _require(operation["failures"] == 0 and operation["exclusive_ns"] <= operation["inclusive_ns"])
            _require(operation["calls"] != 0 or operation["inclusive_ns"] == 0)
            for kind in ("inclusive", "exclusive"):
                _number(operation[kind + "_seconds"])
                _require(operation[kind + "_seconds"] == operation[kind + "_ns"] / 1e9)
        operations = phase["operations"]
        _require(operations["scan_pass"]["calls"] == 1 and
                 operations["scan_pass"]["inclusive_ns"] == phase["elapsed_ns"])
        _require(sum(item["exclusive_ns"] for item in operations.values()) == phase["elapsed_ns"])
        _require(operations["enumeration"]["calls"] == int(name != "offline"))
        for operation in ("sqlite_connection_open", "sqlite_connection_close", "sqlite_transaction_enter",
                          "sqlite_transaction_exit", "catalog_connection_teardown"):
            _require(operations[operation]["calls"] == operations["catalog_connection_setup"]["calls"])
        _require(type(phase["counts"]) is dict and set(phase["counts"]) <=
                 {"sha256_bytes", "transaction_exits_with_transaction", "exceptional_transaction_exits"})
        for number in phase["counts"].values():
            _integer(number)
        _require(phase["counts"].get("exceptional_transaction_exits", 0) == 0)
        if name != "offline":
            _integer(phase["pages"], 1, count + 1)
            _keys(phase["totals"], TOTALS)
            for total in phase["totals"].values():
                _integer(total, 0, count + 1)
            _require(phase["totals"]["errors"] == 0)
    expected_totals = {
        "observation": {"pending": count}, "indexing": {"indexed": count},
        "fresh_resume": {"pending": 1, "unchanged": count},
        "stable_followup": {"indexed": 1, "unchanged": count},
        "online_recovery": {"unchanged": count + 1},
    }
    for name, known in expected_totals.items():
        _require(value[name]["totals"] == {key: known.get(key, 0) for key in TOTALS})
        files = count if name in ("observation", "indexing") else count + 1
        _require(value[name]["pages"] == math.ceil(files / page_size))
    canceled = value["cancellation"]
    _require(all(total == 0 for key, total in canceled["totals"].items() if key != "unchanged"))
    _require(count // 3 <= canceled["totals"]["unchanged"] <= count)
    _require(canceled["pages"] <= math.ceil(count / page_size))
    # Every preceding page completed; cancellation can leave only the final
    # page partially (or not yet) processed. Counts must fit that page prefix.
    _require((canceled["pages"] - 1) * page_size <= canceled["totals"]["unchanged"]
             <= canceled["pages"] * page_size)
    _require(value["indexing"]["operations"]["index_file"]["calls"] == count)
    _require(value["indexing"]["counts"]["sha256_bytes"] == fixture["initial_bytes"])
    _require(value["stable_followup"]["counts"]["sha256_bytes"] == fixture["resume_added_bytes"])
    _require(value["observation"]["operations"]["index_file"]["calls"] == 0)
    _require(value["stable_followup"]["operations"]["index_file"]["calls"] == 1)


def validate_trial(value):
    _keys(value, ("schema", "status", "variant", "identity", "code", "runtime", "configuration", "soak", "phases"))
    _require(value["schema"] == TRIAL_SCHEMA and value["status"] == "complete")
    _require(value["variant"] in ("baseline", "instrumented"))
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    _validate_runtime(value["runtime"])
    _keys(value["configuration"], ("count", "page_size"))
    count, page_size = (value["configuration"][key] for key in ("count", "page_size"))
    _parameters(count, page_size, 2)
    if value["identity"]["run_id"] != "local":
        _require((count, page_size) == (2048, 256))
    _validate_soak(value["soak"], count, page_size, value["runtime"])
    _validate_phases(value["phases"], count, page_size, value["variant"], value["soak"]["fixture"])
    if value["variant"] == "instrumented":
        for interval in ("observation", "indexing"):
            _require(value["phases"][interval]["elapsed_ns"] <= value["soak"]["timings_ns"][interval])
        _require(value["phases"]["fresh_resume"]["elapsed_ns"] +
                 value["phases"]["stable_followup"]["elapsed_ns"] <= value["soak"]["timings_ns"]["fresh_resume"])


def validate_pair(value):
    _keys(value, ("schema", "status", "identity", "code", "runtime", "configuration", "order", "samples",
                  "wall_ns", "cleanup", "issues"))
    _require(value["schema"] == PAIR_SCHEMA and value["status"] in ("complete", "incomplete"))
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    _validate_runtime(value["runtime"])
    _keys(value["configuration"], ("count", "page_size", "pairs", "pair_index"))
    config = value["configuration"]
    _parameters(config["count"], config["page_size"], config["pairs"], config["pair_index"])
    if value["identity"]["run_id"] != "local":
        _require((config["count"], config["page_size"], config["pairs"]) == (2048, 256, 4))
    _require(value["order"] == list(ORDERS[config["pair_index"] - 1]))
    _integer(value["wall_ns"])
    _keys(value["cleanup"], ("workers_reaped", "owned_storage_removed", "storage_retained"))
    _require(all(type(item) is bool for item in value["cleanup"].values()))
    _require(not value["cleanup"]["owned_storage_removed"] or
             (value["cleanup"]["workers_reaped"] and not value["cleanup"]["storage_retained"]))
    _validate_issues(value["issues"])
    _require(type(value["samples"]) is list and len(value["samples"]) <= 2)
    for position, sample in enumerate(value["samples"], 1):
        _keys(sample, ("position", "trial"))
        _integer(sample["position"], position, position)
        validate_trial(sample["trial"])
        trial = sample["trial"]
        _require(trial["variant"] == value["order"][position - 1] and trial["identity"] == value["identity"])
        _require(_code_key(trial["code"]) == _code_key(value["code"]) and trial["runtime"] == value["runtime"])
        _require(trial["configuration"] == {key: config[key] for key in ("count", "page_size")})
        _require(trial["soak"]["fixture"] == value["samples"][0]["trial"]["soak"]["fixture"])
    if value["status"] == "complete":
        _require(len(value["samples"]) == 2 and not value["issues"] and
                 value["cleanup"] == {"workers_reaped": True, "owned_storage_removed": True, "storage_retained": False})
    else:
        _require(bool(value["issues"]))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def parse_report(data):
    def invalid_constant(value):
        raise ValidationError()
    return json.loads(data, object_pairs_hook=_unique_object, parse_constant=invalid_constant)


def _child_root():
    # No source argument: this is a parent-created temp base, not a scan target.
    raw = os.environ.get("DEFIANTMAPLE_SCAN_TRIAL_ROOT")
    token = os.environ.get("DEFIANTMAPLE_SCAN_TRIAL_TOKEN")
    _require(raw is not None and token is not None, "storage_ownership")
    _hex(token, 64)
    root = Path(raw)
    _require(not root.is_symlink() and root.is_dir(), "storage_ownership")
    _require((root / ".owned-scan-trial").read_text(encoding="ascii") == token, "storage_ownership")
    tempfile.tempdir = str(root)


def run_trial(count, page_size, variant, revision=None, run_id="local", run_attempt=1):
    _parameters(count, page_size, 2)
    _require(variant in ("baseline", "instrumented"), "invalid_arguments")
    identity, code = actual_identity(revision, run_id, run_attempt)
    runtime = runtime_metadata()
    measured = profile.run_trial(count, page_size, variant,
                                 fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
    after_identity, after_code = actual_identity(revision, run_id, run_attempt)
    _require(identity == after_identity and _code_key(code) == _code_key(after_code), "code_changed")
    _require(runtime_metadata() == runtime, "identity_mismatch")
    report = {"schema": TRIAL_SCHEMA, "status": "complete", "variant": variant,
              "identity": identity, "code": code, "runtime": runtime,
              "configuration": {"count": count, "page_size": page_size}, **measured}
    validate_trial(report)
    # Archive validators accept legacy recipes; current production must use the
    # pinned corpus and cannot adopt a valid historical encoder's descriptor.
    _require(report["soak"]["fixture"] == soak.fixture_descriptor(
        count, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE))
    return report


def _reap(process, grace=5):
    # poll()/communicate() prove exit; a signal request alone does not.
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
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8")
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException as exc:
        reaped = _reap(process)
        if not reaped:
            _UNREAPED.append(process)
        code = "child_timeout" if isinstance(exc, subprocess.TimeoutExpired) else "child_failed"
        return None, _issue(code, exc), reaped
    try:
        reaped = process.poll() is not None
    except BaseException:
        reaped = False
    if not reaped:
        _UNREAPED.append(process)
        return None, _issue("child_not_reaped"), False
    if process.returncode != 0:
        return None, _issue("child_failed"), True
    try:
        _require(len(stdout) <= 2**22)
        report = parse_report(stdout)
        validate_trial(report)
        return report, None, True
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return None, _issue("invalid_report", exc), True


def run_pair(count=2048, page_size=256, pairs=4, pair_index=1, *, trial_timeout=720,
             pair_timeout=1800, revision=None, run_id="local", run_attempt=1):
    _parameters(count, page_size, pairs, pair_index)
    for duration, maximum in ((trial_timeout, 1800), (pair_timeout, 3600)):
        _require(type(duration) in (int, float) and 0 < duration <= maximum
                 and math.isfinite(duration), "invalid_arguments")
    identity, code = actual_identity(revision, run_id, run_attempt)
    runtime = runtime_metadata()
    if run_id != "local":
        _require((count, page_size, pairs) == (2048, 256, 4), "invalid_arguments")
    expected_fixture = soak.fixture_descriptor(count, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
    started = time.perf_counter_ns()
    report = {"schema": PAIR_SCHEMA, "status": "incomplete", "identity": identity, "code": code,
              "runtime": runtime, "configuration": {"count": count, "page_size": page_size,
              "pairs": pairs, "pair_index": pair_index}, "order": list(ORDERS[pair_index - 1]),
              "samples": [], "wall_ns": 0, "cleanup": {"workers_reaped": True,
              "owned_storage_removed": False, "storage_retained": True}, "issues": []}
    token = secrets.token_hex(32)
    owned = Path(tempfile.mkdtemp(prefix="defiantmaple-profile-pair-")).resolve()
    owner_identity = None
    marker = owned / ".owned-scan-pair"
    try:
        owner_identity = (owned.stat().st_dev, owned.stat().st_ino)
        marker.write_text(token, encoding="ascii")
        for position, variant in enumerate(report["order"], 1):
            remaining = pair_timeout - (time.perf_counter_ns() - started) / 1e9
            if remaining <= 0:
                report["issues"].append(_issue("pair_deadline"))
                break
            child_root = owned / f"trial-{position}"
            child_root.mkdir()
            (child_root / ".owned-scan-trial").write_text(token, encoding="ascii")
            environment = dict(os.environ, TMPDIR=str(child_root), TEMP=str(child_root), TMP=str(child_root),
                               DEFIANTMAPLE_SCAN_TRIAL_ROOT=str(child_root), DEFIANTMAPLE_SCAN_TRIAL_TOKEN=token)
            command = [sys.executable, "-W", "error::ResourceWarning", "-m", __name__ if __name__ != "__main__"
                       else "benchmarks.source_scan_profile_series", "trial", "--count", str(count),
                       "--page-size", str(page_size), "--variant", variant, "--revision", code["revision"],
                       "--run-id", run_id, "--run-attempt", str(run_attempt)]
            trial, issue, reaped = _run_child(command, environment, min(trial_timeout, remaining))
            report["cleanup"]["workers_reaped"] &= reaped
            if not reaped:
                report["issues"].append(_issue("child_not_reaped"))
                break
            if issue is not None:
                report["issues"].append(issue)
                break
            _require(trial["identity"] == identity and _code_key(trial["code"]) == _code_key(code)
                     and trial["runtime"] == runtime and trial["variant"] == variant
                     and trial["configuration"] == {"count": count, "page_size": page_size}, "identity_mismatch")
            _require(trial["soak"]["fixture"] == expected_fixture, "incomparable")
            _require(not report["samples"] or trial["soak"]["fixture"] ==
                     report["samples"][0]["trial"]["soak"]["fixture"], "incomparable")
            report["samples"].append({"position": position, "trial": trial})
        final_identity, final_code = actual_identity(code["revision"], run_id, run_attempt)
        _require(final_identity == identity and _code_key(final_code) == _code_key(code), "code_changed")
        if (time.perf_counter_ns() - started) / 1e9 > pair_timeout:
            report["issues"].append(_issue("pair_deadline"))
    except BaseException as exc:
        report["issues"].append(_issue(exc.code if isinstance(exc, ValidationError) else "child_failed", exc))
    finally:
        if report["cleanup"]["workers_reaped"]:
            try:
                _require(not owned.is_symlink() and owned.is_dir() and
                         (owned.stat().st_dev, owned.stat().st_ino) == owner_identity and
                         marker.read_text(encoding="ascii") == token, "storage_ownership")
                shutil.rmtree(owned)
                report["cleanup"].update(owned_storage_removed=True, storage_retained=False)
            except (OSError, ValidationError) as exc:
                report["issues"].append(_issue("cleanup_failed", exc))
    report["wall_ns"] = time.perf_counter_ns() - started
    if len(report["samples"]) == 2 and not report["issues"]:
        report["status"] = "complete"
    validate_pair(report)
    return report


def _stats(values):
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def _summaries(reports, platforms):
    result = {}
    for system in platforms:
        pairs = sorted((item for item in reports if item["runtime"]["platform"] == system),
                       key=lambda item: item["configuration"]["pair_index"])
        intervals = {}
        for interval in INTERVALS:
            variants = {variant: [] for variant in ("baseline", "instrumented")}
            ratios = []
            groups = {"baseline-first": [], "instrumented-first": []}
            for pair in pairs:
                durations = {sample["trial"]["variant"]: sample["trial"]["soak"]["timings_ns"][interval]
                             for sample in pair["samples"]}
                for variant in variants:
                    variants[variant].append(durations[variant])
                ratio = durations["instrumented"] / durations["baseline"] if durations["baseline"] else None
                label = pair["order"][0] + "-first"
                groups[label].append(ratio)
                ratios.append({"pair_index": pair["configuration"]["pair_index"], "order": pair["order"], "ratio": ratio})
            intervals[interval] = {"variant_ns": {key: _stats(value) for key, value in variants.items()},
                                   "paired_ratios": ratios,
                                   "order_groups": {key: {"pairs": len(value), "ratios": _stats(
                                       [number for number in value if number is not None])} for key, value in groups.items()}}
        measured = [next(sample["trial"]["phases"] for sample in pair["samples"]
                         if sample["trial"]["variant"] == "instrumented") for pair in pairs]
        components = {phase: {operation: {kind: _stats([trial[phase]["operations"][operation][kind]
                      for trial in measured]) for kind in ("calls", "inclusive_ns", "exclusive_ns")}
                      for operation in profile.OPERATIONS} for phase in profile.PHASES}
        result[system] = {"intervals": intervals, "instrumented_components": components}
    return result


def _cohort_key(pair):
    return (pair["runtime"], pair["samples"][0]["trial"]["soak"]["fixture"],
            pair["samples"][0]["trial"]["soak"]["catalog_schema_version"])


def _check_grid(reports, count, page_size, pairs, platforms, identity, code):
    expected = {(system, index) for system in platforms for index in range(1, pairs + 1)}
    seen, cohorts, issues = set(), {}, []
    for pair in reports:
        key = (pair["runtime"]["platform"], pair["configuration"]["pair_index"])
        if key not in expected:
            issues.append(_issue("unexpected_pair"))
        if key in seen:
            issues.append(_issue("duplicate_pair"))
        seen.add(key)
        if (pair["identity"] != identity or _code_key(pair["code"]) != _code_key(code)
                or any(pair["configuration"][name] != value for name, value in
                       (("count", count), ("page_size", page_size), ("pairs", pairs)))):
            issues.append(_issue("identity_mismatch"))
        if pair["status"] != "complete":
            issues.append(_issue("incomparable"))
        else:
            cohort = _cohort_key(pair)
            if key[0] in cohorts and cohorts[key[0]] != cohort:
                issues.append(_issue("incomparable"))
            cohorts[key[0]] = cohort
    if seen != expected:
        issues.append(_issue("missing_pair"))
    # Encoded fixture and common Python/Pillow versions also match across OSes;
    # OS/SQLite/codec versions are retained platform-specific measurements.
    complete = [pair for pair in reports if pair["status"] == "complete"]
    if complete:
        first = complete[0]
        for pair in complete[1:]:
            if (pair["samples"][0]["trial"]["soak"]["fixture"] != first["samples"][0]["trial"]["soak"]["fixture"]
                    or any(pair["runtime"][key] != first["runtime"][key]
                           for key in ("python_implementation", "python_version", "pillow_version"))):
                issues.append(_issue("incomparable"))
    return issues


def aggregate(reports, *, count=2048, page_size=256, pairs=4, platforms=PLATFORMS,
              revision=None, run_id="local", run_attempt=1):
    _parameters(count, page_size, pairs)
    _require(type(reports) in (list, tuple) and len(reports) <= 24, "invalid_arguments")
    _require(type(platforms) in (tuple, list) and len(platforms) == len(set(platforms))
             and bool(platforms) and set(platforms) <= set(PLATFORMS), "invalid_arguments")
    identity, code = actual_identity(revision, run_id, run_attempt)
    if run_id != "local":
        _require((count, page_size, pairs) == (2048, 256, 4) and set(platforms) == set(PLATFORMS), "invalid_arguments")
    expected_fixture = soak.fixture_descriptor(count, fixture_recipe=soak.CANONICAL_FIXTURE_RECIPE)
    result = {"schema": SERIES_SCHEMA, "status": "incomplete", "identity": identity, "code": code,
              "configuration": {"count": count, "page_size": page_size, "pairs": pairs,
                                "platforms": list(platforms)}, "pairs": [], "issues": [], "note": NOTE}
    for report in reports:
        try:
            validate_pair(report)
            # Discard untrusted identity records instead of echoing their metadata.
            _require(report["identity"] == identity and _code_key(report["code"]) == _code_key(code), "identity_mismatch")
            _require(report["runtime"]["platform"] in platforms, "unexpected_pair")
            _require(all(sample["trial"]["soak"]["fixture"] == expected_fixture
                         for sample in report["samples"]), "incomparable")
            result["pairs"].append(report)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            result["issues"].append(_issue(exc.code if isinstance(exc, ValidationError) else "invalid_report", exc))
    result["pairs"].sort(key=lambda item: (list(platforms).index(item["runtime"]["platform"]),
                                         item["configuration"]["pair_index"]))
    result["issues"] += _check_grid(result["pairs"], count, page_size, pairs, platforms, identity, code)
    if not result["issues"]:
        result["status"] = "complete"
        result["summaries"] = _summaries(result["pairs"], platforms)
    validate_series(result)
    return result


def validate_series(value):
    _require(type(value) is dict)
    _keys(value, ("schema", "status", "identity", "code", "configuration", "pairs", "issues", "note") +
                 (("summaries",) if value.get("status") == "complete" else ()))
    _require(value["schema"] == SERIES_SCHEMA and value["status"] in ("complete", "incomplete") and value["note"] == NOTE)
    _validate_identity(value["identity"])
    _validate_code(value["code"])
    _keys(value["configuration"], ("count", "page_size", "pairs", "platforms"))
    config = value["configuration"]
    _parameters(config["count"], config["page_size"], config["pairs"])
    systems = config["platforms"]
    _require(type(systems) is list and bool(systems) and len(systems) == len(set(systems)) and set(systems) <= set(PLATFORMS))
    if value["identity"]["run_id"] != "local":
        _require((config["count"], config["page_size"], config["pairs"]) == (2048, 256, 4)
                 and set(systems) == set(PLATFORMS))
    _require(type(value["pairs"]) is list and len(value["pairs"]) <= 24)
    for pair in value["pairs"]:
        validate_pair(pair)
    _validate_issues(value["issues"])
    problems = _check_grid(value["pairs"], config["count"], config["page_size"], config["pairs"],
                           systems, value["identity"], value["code"])
    if value["status"] == "complete":
        _require(not problems and not value["issues"])
        _require(value["summaries"] == _summaries(value["pairs"], systems))
    else:
        _require(bool(value["issues"]))


def validate_public_report(value):
    """Closed schemas for the shared privacy checker; never trust free text."""
    _require(type(value) is dict)
    if set(value) == {"schema", "status", "issues", "samples"}:
        _require(value["schema"] in (TRIAL_SCHEMA, PAIR_SCHEMA, SERIES_SCHEMA)
                 and value["status"] == "incomplete" and value["samples"] == [])
        _validate_issues(value["issues"])
        _require(bool(value["issues"]))
        return
    validators = {TRIAL_SCHEMA: validate_trial, PAIR_SCHEMA: validate_pair, SERIES_SCHEMA: validate_series}
    _require(value.get("schema") in validators)
    validators[value["schema"]](value)


def write_report(path, report):
    validate_public_report(report)
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix="scan-metrics-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _Parser(ArgumentParser):
    def error(self, message):
        raise ValidationError("invalid_arguments")


def _parser():
    parser = _Parser(prog="source_scan_profile_series", description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True, parser_class=_Parser)
    for mode in ("pair", "trial", "aggregate"):
        command = modes.add_parser(mode)
        command.add_argument("--count", type=int, default=2048)
        command.add_argument("--page-size", type=int, default=256)
        command.add_argument("--revision")
        command.add_argument("--run-id", default="local")
        command.add_argument("--run-attempt", type=int, default=1)
        command.add_argument("--metrics", type=Path)
        if mode == "trial":
            command.add_argument("--variant", required=True, choices=("baseline", "instrumented"))
        else:
            command.add_argument("--pairs", type=int, default=4)
        if mode == "pair":
            command.add_argument("--pair-index", type=int, required=True)
            command.add_argument("--trial-timeout", type=float, default=720)
            command.add_argument("--pair-timeout", type=float, default=1800)
        if mode == "aggregate":
            command.add_argument("--input-dir", type=Path, required=True)
            command.add_argument("--platforms", nargs="+", choices=PLATFORMS, default=list(PLATFORMS))
    return parser


def main(argv=None):
    args = None
    report = None
    validated = False
    schema = SERIES_SCHEMA
    try:
        args = _parser().parse_args(argv)
        schema = {"pair": PAIR_SCHEMA, "trial": TRIAL_SCHEMA, "aggregate": SERIES_SCHEMA}[args.mode]
        provenance = {key: getattr(args, key) for key in ("revision", "run_id", "run_attempt")}
        if args.mode == "trial":
            _child_root()
            report = run_trial(args.count, args.page_size, args.variant, **provenance)
        elif args.mode == "pair":
            report = run_pair(args.count, args.page_size, args.pairs, args.pair_index,
                              trial_timeout=args.trial_timeout, pair_timeout=args.pair_timeout, **provenance)
        else:
            paths = sorted(args.input_dir.rglob("*.json"))
            _require(args.input_dir.is_dir() and len(paths) <= 24)
            reports, failures = [], []
            for path in paths:
                try:
                    _require(not path.is_symlink() and path.stat().st_size <= 2**22)
                    reports.append(parse_report(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    failures.append(_issue("invalid_report", exc))
            report = aggregate(reports, count=args.count, page_size=args.page_size, pairs=args.pairs,
                               platforms=args.platforms, **provenance)
            if failures:
                report["issues"] += failures
                report["status"] = "incomplete"
                report.pop("summaries", None)
        validate_public_report(report)
        validated = True
        if args.metrics is not None:
            write_report(args.metrics, report)
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code == 0:
            return 0
        problem = _issue(exc.code if isinstance(exc, ValidationError) else
                         ("output_failed" if validated else "invalid_report"), exc)
        if validated and schema in (PAIR_SCHEMA, SERIES_SCHEMA):
            # A failed report write must not erase already validated aggregates.
            report["status"] = "incomplete"
            report["issues"].append(problem)
            report.pop("summaries", None)
        else:
            report = {"schema": schema, "status": "incomplete", "samples": [], "issues": [problem]}
        if args is not None and args.metrics is not None:
            try:
                write_report(args.metrics, report)
            except (OSError, ValueError):
                report["issues"].append(_issue("output_failed"))
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
