"""Scratch-only, operator-controlled mounted-share interruption probe.

Private session state and the catalog remain in an explicitly supplied new local
folder. Every share operation runs in a bounded child process. This tool never
mounts, unmounts, changes services, or executes operator-provided commands.
"""
from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import queue
import stat
import subprocess
import sys
import threading
import time
import uuid

from benchmarks.source_scan_soak import _fictional_pngs
from defiantmaple.catalog import connect, initialize
from defiantmaple import sources


SCHEMA = "defiantmaple.mounted-share-probe.v1"
PRIVATE_NAME = "session.private.json"
MARKER_NAME = ".defiantmaple-owned-fixture.json"
WORKER_LOCK = "worker.private.lock"
TRANSITIONS = {
    "interrupt": {"ready_observation": "observation_interrupted",
                  "ready_indexing": "indexing_interrupted"},
    "offline": {"observation_interrupted": "observation_offline",
                "indexing_interrupted": "indexing_offline"},
    "recover": {"observation_offline": "ready_indexing",
                "indexing_offline": "complete"},
}


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _save(state: dict) -> None:
    path = Path(state["local_state"]) / PRIVATE_NAME
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, indent=2)
        stream.write("\n")
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)


def _load(local_state: Path) -> dict:
    # Local state is trusted operator input, not a portable untrusted manifest.
    path = local_state.resolve() / PRIVATE_NAME
    if path.is_symlink():
        raise ValueError("Private state must not be a symlink")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA or state.get("local_state") != str(path.parent):
        raise ValueError("Unknown or moved private session")
    _validate_identity(state)
    return state


def _validate_identity(state: dict) -> None:
    session_id = str(uuid.UUID(state["session_id"]))
    scratch = Path(state["scratch_share"])
    root = Path(state["fixture_root"])
    if (root.parent != scratch or root.name != "defiantmaple-fictional-" + session_id
            or not scratch.is_absolute() or not root.is_absolute()
            or _inside(Path(state["local_state"]), scratch)):
        raise ValueError("Fixture ownership path does not match session")


def _marker(state: dict) -> dict:
    return {"schema": SCHEMA, "session_id": state["session_id"],
            "purpose": "generated-fictional-scratch-only"}


def _owned_root(state: dict) -> Path:
    _validate_identity(state)
    root = Path(state["fixture_root"])
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise ValueError("Owned fixture has disappeared or been substituted")
    marker = root / MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Owned fixture marker missing or unsafe")
    if json.loads(marker.read_text(encoding="utf-8")) != _marker(state):
        raise ValueError("Owned fixture marker does not match session")
    return root


def _safe_file(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 2:
        raise ValueError("Invalid generated fixture member")
    path = root / rel
    if (root.is_symlink() or root.resolve() != root
            or path.parent.is_symlink() or path.parent.resolve() != path.parent
            or path.is_symlink()):
        raise ValueError("Symlink or substituted path in generated fixture")
    return path


def _fingerprint(path: Path) -> dict:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Fixture member is not a regular file")
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns}


def _inventory(state: dict) -> None:
    root = _owned_root(state)
    expected_files = {MARKER_NAME, *state["manifest"]}
    expected_dirs = {str(Path(name).parent) for name in state["manifest"]}
    actual_files = set()
    actual_dirs = set()
    # Reject links, unknown files and subtrees. Never follow a directory link.
    for directory, children, files in os.walk(root, followlinks=False):
        for name in children:
            path = Path(directory) / name
            if path.is_symlink() or path.resolve() != path:
                raise ValueError("Symlink or redirected directory in generated fixture")
            actual_dirs.add(path.relative_to(root).as_posix())
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Symlink in generated fixture")
            actual_files.add(path.relative_to(root).as_posix())
    if actual_files != expected_files or actual_dirs != expected_dirs:
        raise ValueError("Fixture contains unexpected or missing members")
    for relative, expected in state["manifest"].items():
        if _fingerprint(_safe_file(root, relative)) != expected:
            raise ValueError("Generated fixture file changed")


def _create_batch(state: dict, batch: str) -> None:
    root = _owned_root(state)
    pngs = _fictional_pngs()
    directory = root / batch
    directory.mkdir()  # Exclusive: a partial or previous batch is never reused.
    for index in range(state["count"]):
        relative = f"{batch}/fictional-{index:06}.png"
        path = _safe_file(root, relative)
        with path.open("xb") as stream:
            stream.write(pngs[index % len(pngs)])
        state["manifest"][relative] = _fingerprint(path)
        # Keep ownership records useful if a later network write blocks/fails.
        _save(state)


def _snapshot(state: dict) -> dict:
    with connect(Path(state["database"])) as db:
        assets = sorted(row[0] for row in db.execute("SELECT asset_id FROM assets"))
        entries = {row["current_path"]: dict(row) for row in db.execute(
            "SELECT current_path,asset_id,disposition FROM source_entries")}
    return {"assets": assets, "entries": entries}


def _retained(before: dict, after: dict) -> bool:
    return (set(before["assets"]).issubset(after["assets"])
            and all(path in after["entries"]
                    and (not entry["asset_id"]
                         or after["entries"][path]["asset_id"] == entry["asset_id"])
                    and after["entries"][path]["disposition"] != "missing"
                    for path, entry in before["entries"].items()))


def _scan(state: dict, *, progress=None) -> dict:
    return sources.scan_sources(Path(state["database"]),
                                source_id=state["source_id"], quiet_seconds=0,
                                progress=progress)


def _aggregate_scan(result: dict) -> dict:
    return {"complete": result["complete"], "canceled": result["canceled"],
            "health": result["sources"][0]["health"],
            "totals": result["totals"]}


def _record(state: dict, action: str, phase: str, **fields) -> None:
    state["events"].append({"action": action, "phase": phase,
                            "utc": datetime.now(timezone.utc).isoformat(), **fields})
    _save(state)


def _perform(state: dict, action: str, gate=None) -> dict:
    """Child-side operation. gate is a fixed callback, never a shell hook."""
    if action == "prepare":
        scratch = Path(state["scratch_share"])
        if (not scratch.is_dir() or scratch.resolve() != scratch
                or _inside(Path(state["local_state"]), scratch)):
            raise ValueError("Scratch parent must be an existing canonical directory")
        root = Path(state["fixture_root"])
        root.mkdir()  # Unique child only; no scan of the supplied parent.
        (root / MARKER_NAME).write_text(json.dumps(_marker(state)), encoding="utf-8")
        _create_batch(state, "baseline")
        initialize(Path(state["database"]))
        state["source_id"] = sources.add_source(Path(state["database"]), root)["source_id"]
        first, second = _scan(state), _scan(state)
        snapshot = _snapshot(state)
        if (not first["complete"] or not second["complete"]
                or len(snapshot["assets"]) != state["count"]):
            raise AssertionError("Baseline failed")
        state["baseline"] = snapshot
        state["status"] = "ready_observation"
        _inventory(state)
        _record(state, action, "baseline", file_count=state["count"],
                asset_count=len(snapshot["assets"]), source_integrity=True)
        return state
    if action == "cleanup":
        _inventory(state)
        root = _owned_root(state)
        for relative in state["manifest"]:
            _safe_file(_owned_root(state), relative).unlink()
        for relative in sorted({str(Path(name).parent) for name in state["manifest"]},
                               reverse=True):
            directory = _owned_root(state) / relative
            if directory.is_symlink() or directory.resolve() != directory:
                raise ValueError("Fixture directory substituted during cleanup")
            directory.rmdir()
        root = _owned_root(state)
        (root / MARKER_NAME).unlink()
        if root.is_symlink() or root.resolve() != root:
            raise ValueError("Fixture root substituted during cleanup")
        root.rmdir()
        state["cleaned"] = True
        _save(state)
        return state
    current = state["status"]
    if current not in TRANSITIONS.get(action, {}):
        raise ValueError("Action is out of protocol order")
    phase = "observation" if current.startswith(("ready_observation", "observation")) else "indexing"
    before = _snapshot(state)
    if action == "interrupt":
        _inventory(state)
        if gate is None:
            raise ValueError("Interruption requires an operator gate")
        if phase == "indexing":
            _create_batch(state, "indexing")
            observed = _scan(state)
            if not observed["complete"] or observed["totals"]["pending"] != state["count"]:
                raise AssertionError("Indexing batch observation failed")
            before = _snapshot(state)
        state["before_trial"] = before
        _save(state)
        gated = False

        def enumeration_progress(progress):
            nonlocal gated
            if (phase == "observation" and not gated
                    and progress["phase"] == "enumerating"
                    and progress["enumerated"] == 64):
                gated = True
                gate(phase)

        real_index = sources.index_file
        index_calls = 0

        def indexing_gate(*args, **kwargs):
            nonlocal gated, index_calls
            if not gated and index_calls == 1:
                gated = True
                gate(phase)
            result = real_index(*args, **kwargs)
            index_calls += 1
            return result

        if phase == "indexing":
            sources.index_file = indexing_gate
        try:
            result = _scan(state, progress=enumeration_progress)
        finally:
            sources.index_file = real_index
        after = _snapshot(state)
        safe = _retained(before, after) and result["totals"]["missing"] == 0
        _record(state, action, phase, scan=_aggregate_scan(result), gate_reached=gated,
                records_retained=safe, uuid_set_retained=set(before["assets"]).issubset(after["assets"]))
        if not safe:
            raise AssertionError("Interrupted pass changed retained records")
        # Completion through client caching is evidence of an inconclusive trial.
        if not gated or result["complete"] or result["sources"][0]["health"] != "offline":
            state["status"] = "inconclusive"
            _save(state)
            return state
    elif action == "offline":
        # Do not inspect the root marker before scanning an unavailable source.
        result = _scan(state)
        after = _snapshot(state)
        safe = (_retained(before, after) and _retained(state["before_trial"], after)
                and result["totals"]["missing"] == 0)
        _record(state, action, phase, scan=_aggregate_scan(result), records_retained=safe,
                uuid_set_retained=set(before["assets"]).issubset(after["assets"]))
        if not safe:
            raise AssertionError("Offline probe changed retained records")
        if result["complete"] or result["sources"][0]["health"] != "offline":
            state["status"] = "inconclusive"
            _save(state)
            return state
    elif action == "recover":
        _inventory(state)
        first, second = _scan(state), _scan(state)
        after = _snapshot(state)
        expected_count = len(state["manifest"])
        safe = _retained(before, after) and _retained(state["before_trial"], after)
        full = (first["complete"] and second["complete"]
                and len(after["assets"]) == expected_count
                and len(after["entries"]) == expected_count + 1
                and all(entry["disposition"] ==
                        ("unsupported" if Path(path).name == MARKER_NAME else "indexed")
                        for path, entry in after["entries"].items()))
        _inventory(state)
        _record(state, action, phase, records_retained=safe,
                uuid_set_retained=set(before["assets"]).issubset(after["assets"]),
                complete=full, asset_count=len(after["assets"]), source_integrity=True)
        if not safe or not full:
            raise AssertionError("Healthy recovery did not retain and index the full fixture")
    state["status"] = TRANSITIONS[action][current]
    _save(state)
    return state


def _worker(local_state: str, action: str) -> int:
    def send(message):
        print(json.dumps(message), flush=True)

    try:
        state = _load(Path(local_state))

        def gate(phase):
            send({"kind": "gate", "phase": phase})
            if sys.stdin.readline().strip() != "continue":
                raise ValueError("Operator gate was not continued")

        state = _perform(state, action, gate=gate)
        send({"kind": "done", "status": state["status"]})
        return 0
    except Exception as exc:
        # Detailed exceptions may contain private paths; never emit them publicly.
        try:
            state = _load(Path(local_state))
            state["failure"] = {"action": action, "exception_type": type(exc).__name__,
                                "detail": str(exc)}
            state["status"] = "failed"
            _save(state)
        except Exception:
            pass
        send({"kind": "error", "exception_type": type(exc).__name__})
        return 2


def _confirm_disconnect(phase: str, timeout: float) -> bool:
    print(f"{phase} gate reached BETWEEN filesystem operations. Disconnect only the "
          "dedicated disposable mount now; press Enter after it is unavailable.", flush=True)
    answers = queue.Queue()

    def read():
        try:
            answers.put(input())
        except EOFError:
            answers.put(None)

    threading.Thread(target=read, daemon=True).start()
    try:
        return answers.get(timeout=timeout) == ""
    except queue.Empty:
        return False


def execute(local_state: Path, action: str, timeout: float = 60,
            confirm=_confirm_disconnect) -> dict:
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
        raise ValueError("timeout must be finite and between 0 and 3600 seconds")
    state = _load(local_state)
    if action != "prepare" and action != "cleanup" and state["status"] not in TRANSITIONS.get(action, {}):
        raise ValueError("Action is out of protocol order")
    if action == "prepare" and state["status"] != "new":
        raise ValueError("A prepared session cannot be reused")
    lock = Path(state["local_state"]) / WORKER_LOCK
    # Exclusive local lock also blocks cleanup after an unreaped kernel-I/O hang.
    with lock.open("x", encoding="utf-8") as stream:
        stream.write("Worker starting; do not remove until its exit is verified.\n")
    try:
        worker = subprocess.Popen(
            [sys.executable, "-m", "benchmarks.mounted_share_probe", "_worker",
             "--local-state", str(local_state), "--operation", action],
            cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except Exception:
        lock.unlink()
        raise
    lock.write_text(json.dumps({"pid": worker.pid, "action": action}), encoding="utf-8")
    messages = queue.Queue()

    def read_messages():
        for line in worker.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                messages.put({"kind": "error", "exception_type": "InvalidWorkerOutput"})

    threading.Thread(target=read_messages, daemon=True).start()
    deadline = time.monotonic() + timeout
    outcome = None
    try:
        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=min(0.1, max(0, deadline - time.monotonic())))
            except queue.Empty:
                if worker.poll() is not None:
                    # Reader may still be delivering the process's final line.
                    try:
                        message = messages.get(timeout=0.2)
                    except queue.Empty:
                        break
                else:
                    continue
            if message["kind"] == "gate":
                if not confirm(message["phase"], max(0, deadline - time.monotonic())):
                    break
                worker.stdin.write("continue\n")
                worker.stdin.flush()
            else:
                outcome = message
                break
    except (OSError, KeyboardInterrupt):
        pass
    finally:
        if outcome is None and worker.poll() is None:
            worker.terminate()
        try:
            worker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            worker.kill()
            try:
                worker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    # Popen does not join an unreaped child at interpreter exit. The lock must
    # remain if the OS cannot finish killing it; do not race its local catalog.
    state = _load(local_state)
    if worker.poll() is None:
        state["status"] = "blocked_worker"
        return state
    lock.unlink()
    worker.stdin.close()
    worker.stdout.close()
    if outcome is None:
        _record(state, action, "unknown", outcome="timeout_or_canceled")
        state["status"] = "inconclusive"
        _save(state)
    elif outcome["kind"] == "error":
        raise RuntimeError("Worker failed; inspect local private state")
    elif worker.returncode != 0:
        _record(state, action, "unknown", outcome="worker_exit_not_success")
        state["status"] = "inconclusive"
        _save(state)
    return state


def new_session(scratch_share: Path, local_state: Path, *, count: int = 256,
                environment_kind: str = "local_fixture", protocol: str = "unknown",
                mount_evidence: Path | None = None) -> dict:
    if type(count) is not int or count < 128 or count > 100_000:
        raise ValueError("count must be between 128 and 100000")
    if environment_kind not in ("local_fixture", "mounted_scratch"):
        raise ValueError("Unknown environment kind")
    if protocol not in ("unknown", "smb", "nfs", "other"):
        raise ValueError("Unknown protocol")
    if environment_kind == "local_fixture" and protocol != "unknown":
        raise ValueError("Local fixtures cannot attest a mounted protocol")
    if not scratch_share.is_absolute() or not local_state.is_absolute():
        raise ValueError("Scratch and local state paths must be absolute")
    # Local path resolution is an operator assertion of local storage. Share
    # canonicalization is deferred to the bounded prepare worker.
    local_state = local_state.parent.resolve() / local_state.name
    scratch = Path(os.path.abspath(scratch_share))
    repo = Path(__file__).resolve().parents[1]
    if _inside(local_state, scratch) or _inside(local_state, repo):
        raise ValueError("Local state must be outside scratch parent and repository")
    if local_state.exists() or local_state.is_symlink():
        raise ValueError("Local state must be a new directory")
    if environment_kind == "mounted_scratch" and protocol != "unknown" and mount_evidence is None:
        raise ValueError("A named mounted protocol requires local operator evidence")
    evidence = None
    if mount_evidence is not None:
        evidence_path = mount_evidence.resolve()
        if _inside(evidence_path, scratch):
            raise ValueError("Mount evidence must be a local file outside scratch storage")
        evidence = {"path": str(evidence_path),
                    "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest()}
    local_state.mkdir(mode=0o700)
    session_id = str(uuid.uuid4())
    state = {"schema": SCHEMA, "session_id": session_id, "status": "new",
             "scratch_share": str(scratch),
             "fixture_root": str(scratch / ("defiantmaple-fictional-" + session_id)),
             "local_state": str(local_state), "database": str(local_state / "catalog.sqlite3"),
             "count": count, "environment_kind": environment_kind, "protocol": protocol,
             "mount_evidence": evidence, "manifest": {}, "events": [],
             "platform": platform.system(), "python_version": platform.python_version(),
             "created_utc": datetime.now(timezone.utc).isoformat()}
    _save(state)
    return state


def public_report(state: dict) -> dict:
    events = state["events"]
    event_keys = {"action", "utc", "gate_reached", "records_retained", "uuid_set_retained",
                  "complete", "asset_count", "source_integrity"}
    total_keys = {"indexed", "updated", "renamed", "pending", "ignored_existing",
                  "unchanged", "unsupported", "missing", "overlap_skipped"}

    def public_event(event):
        result = {key: value for key, value in event.items() if key in event_keys}
        if "scan" in event:
            scan = event["scan"]
            result["scan"] = {key: scan[key] for key in ("complete", "canceled", "health")}
            result["scan"]["totals"] = {key: value for key, value in scan["totals"].items()
                                               if key in total_keys}
        return result

    trials = []
    for phase in ("observation", "indexing"):
        phase_events = [event for event in events if event["phase"] == phase]
        trials.append({"phase": phase, "events": [
            public_event(event) for event in phase_events]})
    worker_locked = (Path(state["local_state"]) / WORKER_LOCK).exists()
    complete = state["status"] == "complete" and not worker_locked
    return {"schema": SCHEMA, "platform": state["platform"],
            "python_version": state["python_version"], "created_utc": state["created_utc"],
            "fixture_kind": "generated-fictional-png", "environment_kind": state["environment_kind"],
            "protocol": state["protocol"],
            "protocol_evidence": "operator_attested" if state["environment_kind"] == "mounted_scratch" else "not_tested",
            "mount_evidence_sha256": (state["mount_evidence"]["sha256"] if state["mount_evidence"] else None),
            "protocol_independently_verified_by_harness": False,
            "status": "worker_active_or_unreaped" if worker_locked else state["status"],
            "complete": complete, "worker_lock_present": worker_locked,
            "fixture_files": len(state["manifest"]), "configured_count": state["count"],
            "baseline_assets": (len(state["baseline"]["assets"]) if "baseline" in state else None),
            "trials": trials, "cleaned": state.get("cleaned", False),
            "timed_out_actions": [event["action"] for event in events
                                  if event.get("outcome") == "timeout_or_canceled"],
            "note": "Progress gates occur between operations. Protocol is operator attestation; "
                    "client caching and blocked kernel I/O can make a trial inconclusive. "
                    "A timeout is not a scanner Offline result."}


def main(argv=None) -> int:
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare", help="Create a unique fictional child and baseline")
    prepare.add_argument("--scratch-share", type=Path, required=True)
    prepare.add_argument("--local-state", type=Path, required=True)
    prepare.add_argument("--count", type=int, default=256)
    prepare.add_argument("--environment-kind", choices=("local_fixture", "mounted_scratch"), required=True)
    prepare.add_argument("--protocol", choices=("unknown", "smb", "nfs", "other"), default="unknown")
    prepare.add_argument("--mount-evidence", type=Path)
    prepare.add_argument("--timeout", type=float, default=60)
    for action in ("interrupt", "offline", "recover", "cleanup", "report"):
        command = sub.add_parser(action)
        command.add_argument("--local-state", type=Path, required=True)
        if action != "report":
            command.add_argument("--timeout", type=float, default=60)
        else:
            command.add_argument("--metrics", type=Path)
    internal = sub.add_parser("_worker", help="Internal fixed worker; do not invoke manually")
    internal.add_argument("--local-state", required=True)
    internal.add_argument("--operation", choices=("prepare", "interrupt", "offline", "recover", "cleanup"), required=True)
    args = parser.parse_args(argv)
    if args.action == "_worker":
        return _worker(args.local_state, args.operation)
    try:
        if args.action == "prepare":
            new_session(args.scratch_share, args.local_state, count=args.count,
                        environment_kind=args.environment_kind, protocol=args.protocol,
                        mount_evidence=args.mount_evidence)
        state = (_load(args.local_state) if args.action == "report" else
                 execute(args.local_state, args.action, args.timeout))
        report = public_report(state)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.action == "report" and args.metrics is not None:
            target = args.metrics.parent.resolve() / args.metrics.name
            if _inside(target, Path(state["scratch_share"])) or _inside(target, Path(state["fixture_root"])):
                raise ValueError("Public report must be written outside source scratch storage")
            with target.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        print(rendered, end="")
        return 0 if report["status"] not in ("failed", "inconclusive", "blocked_worker", "worker_active_or_unreaped") else 2
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"Probe stopped: {type(exc).__name__}. Inspect local private state and the runbook.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
