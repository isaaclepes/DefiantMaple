"""Persisted watched-source prototype with explicit, one-shot scan semantics."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import os
from pathlib import Path
import stat
import time
import uuid

from .catalog import connect, index_file, record_external_rename


EXISTING_FILE_POLICIES = ("inbox", "reviewed", "ignore_until_modified")


@dataclass(frozen=True)
class _Candidate:
    path: Path
    byte_size: int
    modified_ns: int
    device: str
    inode: str

    @classmethod
    def from_entry(cls, entry: os.DirEntry) -> "_Candidate":
        value = entry.stat(follow_symlinks=False)
        if not stat.S_ISREG(value.st_mode):
            raise ValueError("candidate is not a regular file")
        return cls(
            Path(entry.path).resolve(strict=False),
            value.st_size,
            value.st_mtime_ns,
            str(value.st_dev),
            str(value.st_ino),
        )

    @property
    def fingerprint(self) -> tuple[int, int]:
        return self.byte_size, self.modified_ns

    @property
    def file_identity(self) -> tuple[str, str] | None:
        if self.device == "0" and self.inode == "0":
            return None
        return self.device, self.inode


def _source_dict(row) -> dict:
    result = dict(row)
    result["recursive"] = bool(result["recursive"])
    result["enabled"] = bool(result["enabled"])
    result["initial_scan_completed"] = bool(result["initial_scan_completed"])
    return result


def add_source(
    database: Path,
    root: Path,
    *,
    name: str | None = None,
    existing_file_policy: str = "inbox",
    recursive: bool = True,
) -> dict:
    """Register a source without requiring it to be online at registration time."""
    if existing_file_policy not in EXISTING_FILE_POLICIES:
        raise ValueError(
            "existing_file_policy must be inbox, reviewed, or ignore_until_modified"
        )
    root = Path(root).expanduser().resolve(strict=False)
    source_name = (name or root.name or str(root)).strip()
    if not source_name:
        raise ValueError("source name must not be empty")
    source_id = str(uuid.uuid4())
    with connect(database) as db:
        db.execute(
            "INSERT INTO sources(source_id,name,root_path,recursive,existing_file_policy) "
            "VALUES(?,?,?,?,?)",
            (source_id, source_name, str(root), int(bool(recursive)), existing_file_policy),
        )
        row = db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
    return _source_dict(row)


def list_sources(database: Path) -> list[dict]:
    with connect(database) as db:
        return [
            _source_dict(row)
            for row in db.execute("SELECT * FROM sources ORDER BY created_at,source_id")
        ]


def set_source_enabled(database: Path, source_id: str, enabled: bool) -> dict:
    with connect(database) as db:
        changed = db.execute(
            "UPDATE sources SET enabled=?,health='paused',health_detail=NULL "
            "WHERE source_id=?",
            (int(bool(enabled)), source_id),
        ).rowcount
        if changed != 1:
            raise ValueError(f"Unknown source: {source_id}")
        row = db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
    return _source_dict(row)


def _set_health(database: Path, source_id: str, health: str, detail: str | None) -> None:
    with connect(database) as db:
        db.execute(
            "UPDATE sources SET health=?,health_detail=? WHERE source_id=?",
            (health, detail, source_id),
        )


def _iter_candidates(root: Path, recursive: bool) -> list[_Candidate]:
    value = root.stat()
    if not stat.S_ISDIR(value.st_mode):
        raise NotADirectoryError(str(root))
    pending = [root]
    candidates: list[_Candidate] = []
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            candidates.append(_Candidate.from_entry(entry))
                        elif recursive and entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            if directory == root:
                raise
    return sorted(candidates, key=lambda item: str(item.path))


def _contains(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _owner_for(path: Path, sources: list[dict]) -> str | None:
    matches = [
        (len(Path(source["root_path"]).parts), source["source_id"])
        for source in sources
        if source["enabled"] and _contains(Path(source["root_path"]), path)
    ]
    return max(matches)[1] if matches else None


def _entry_fingerprint(entry: dict) -> tuple[int, int]:
    return entry["byte_size"], entry["modified_ns"]


def _entry_identity(entry: dict) -> tuple[str, str] | None:
    value = entry["device"], entry["inode"]
    return None if value == ("0", "0") else value


def _upsert_observation(
    database: Path,
    source_id: str,
    candidate: _Candidate,
    now_ns: int,
    *,
    preexisting: bool,
    disposition: str,
    asset_id: str | None = None,
    last_error: str | None = None,
) -> None:
    with connect(database) as db:
        db.execute(
            "INSERT INTO source_entries(current_path,source_id,byte_size,modified_ns,"
            "device,inode,stable_since_ns,observed_at_ns,preexisting,disposition,asset_id,last_error) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(current_path) DO UPDATE SET source_id=excluded.source_id,"
            "byte_size=excluded.byte_size,modified_ns=excluded.modified_ns,"
            "device=excluded.device,inode=excluded.inode,"
            "stable_since_ns=excluded.stable_since_ns,observed_at_ns=excluded.observed_at_ns,"
            "preexisting=excluded.preexisting,disposition=excluded.disposition,"
            "asset_id=excluded.asset_id,last_error=excluded.last_error",
            (str(candidate.path), source_id, candidate.byte_size, candidate.modified_ns,
             candidate.device, candidate.inode, now_ns, now_ns, int(preexisting),
             disposition, asset_id, last_error),
        )


def _move_observation(
    database: Path,
    old_path: str,
    source_id: str,
    candidate: _Candidate,
    now_ns: int,
) -> None:
    with connect(database) as db:
        db.execute(
            "UPDATE source_entries SET current_path=?,source_id=?,byte_size=?,modified_ns=?,"
            "device=?,inode=?,observed_at_ns=?,disposition=CASE WHEN disposition='missing' "
            "THEN 'indexed' ELSE disposition END,last_error=NULL WHERE current_path=?",
            (str(candidate.path), source_id, candidate.byte_size, candidate.modified_ns,
             candidate.device, candidate.inode, now_ns, old_path),
        )
        db.execute(
            "UPDATE assets SET source_id=? WHERE asset_id=(SELECT asset_id FROM source_entries "
            "WHERE current_path=?)",
            (source_id, str(candidate.path)),
        )


def _scan_one(database: Path, source: dict, quiet_ns: int, now_ns: int) -> dict:
    source_id = source["source_id"]
    summary = {
        "source_id": source_id,
        "name": source["name"],
        "root_path": source["root_path"],
        "health": "scanning",
        "indexed": 0,
        "updated": 0,
        "renamed": 0,
        "pending": 0,
        "ignored_existing": 0,
        "unchanged": 0,
        "unsupported": 0,
        "missing": 0,
        "overlap_skipped": 0,
        "errors": [],
    }
    _set_health(database, source_id, "scanning", None)
    try:
        candidates = _iter_candidates(Path(source["root_path"]), source["recursive"])
    except (FileNotFoundError, NotADirectoryError) as exc:
        detail = f"{type(exc).__name__}: {exc}"
        _set_health(database, source_id, "offline", detail)
        summary.update(health="offline", health_detail=detail)
        return summary
    except PermissionError as exc:
        detail = f"PermissionError: {exc}"
        _set_health(database, source_id, "permission_denied", detail)
        summary.update(health="permission_denied", health_detail=detail)
        return summary
    except OSError as exc:
        detail = f"{type(exc).__name__}: {exc}"
        _set_health(database, source_id, "error", detail)
        summary.update(health="error", health_detail=detail)
        return summary

    all_sources = list_sources(database)
    owned = [candidate for candidate in candidates if _owner_for(candidate.path, all_sources) == source_id]
    summary["overlap_skipped"] = len(candidates) - len(owned)
    all_candidate_paths = {str(candidate.path) for candidate in candidates}

    with connect(database) as db:
        entries = [dict(row) for row in db.execute("SELECT * FROM source_entries")]
    entries_by_path = {entry["current_path"]: entry for entry in entries}
    candidate_identity_counts = Counter(
        candidate.file_identity for candidate in owned if candidate.file_identity is not None
    )
    entry_identity_counts = Counter(
        _entry_identity(entry) for entry in entries if _entry_identity(entry) is not None
    )

    permission_failure: str | None = None
    for candidate in owned:
        path_text = str(candidate.path)
        entry = entries_by_path.get(path_text)

        if entry is None and candidate.file_identity is not None:
            matches = [
                previous for previous in entries
                if _entry_identity(previous) == candidate.file_identity
                and _entry_fingerprint(previous) == candidate.fingerprint
                and previous["current_path"] not in all_candidate_paths
                and not Path(previous["current_path"]).exists()
            ]
            if (
                len(matches) == 1
                and candidate_identity_counts[candidate.file_identity] == 1
                and entry_identity_counts[candidate.file_identity] == 1
            ):
                previous = matches[0]
                try:
                    if previous["asset_id"]:
                        record_external_rename(
                            database, previous["asset_id"],
                            Path(previous["current_path"]), candidate.path, source_id,
                            byte_size=candidate.byte_size,
                            modified_ns=candidate.modified_ns,
                            device=candidate.device,
                            inode=candidate.inode,
                            observed_at_ns=now_ns,
                        )
                    else:
                        _move_observation(
                            database, previous["current_path"], source_id,
                            candidate, now_ns,
                        )
                except ValueError as exc:
                    summary["errors"].append({"path": path_text, "error": str(exc)})
                else:
                    summary["renamed"] += 1
                    entries_by_path[path_text] = {
                        **previous, "current_path": path_text, "source_id": source_id
                    }
                    continue

        if entry is None:
            preexisting = not source["initial_scan_completed"]
            if preexisting and source["existing_file_policy"] == "ignore_until_modified":
                disposition = "ignored_existing"
                summary["ignored_existing"] += 1
            else:
                disposition = "pending"
                summary["pending"] += 1
            _upsert_observation(
                database, source_id, candidate, now_ns,
                preexisting=preexisting, disposition=disposition,
            )
            continue

        if entry["source_id"] != source_id:
            with connect(database) as db:
                db.execute(
                    "UPDATE source_entries SET source_id=? WHERE current_path=?",
                    (source_id, path_text),
                )
                if entry["asset_id"]:
                    db.execute(
                        "UPDATE assets SET source_id=? WHERE asset_id=?",
                        (source_id, entry["asset_id"]),
                    )
            entry["source_id"] = source_id

        if _entry_fingerprint(entry) != candidate.fingerprint:
            _upsert_observation(
                database, source_id, candidate, now_ns, preexisting=False,
                disposition="pending", asset_id=entry["asset_id"],
            )
            summary["pending"] += 1
            continue

        if entry["disposition"] == "ignored_existing":
            with connect(database) as db:
                db.execute(
                    "UPDATE source_entries SET observed_at_ns=? WHERE current_path=?",
                    (now_ns, path_text),
                )
            summary["ignored_existing"] += 1
            continue
        if entry["disposition"] == "unsupported":
            summary["unsupported"] += 1
            continue
        if entry["disposition"] in ("indexed", "missing"):
            with connect(database) as db:
                db.execute(
                    "UPDATE source_entries SET observed_at_ns=?,disposition='indexed',"
                    "last_error=NULL WHERE current_path=?",
                    (now_ns, path_text),
                )
            summary["unchanged"] += 1
            continue
        if now_ns - entry["stable_since_ns"] < quiet_ns:
            summary["pending"] += 1
            continue

        workflow_state = (
            "needs_review" if entry["asset_id"]
            else "reviewed" if entry["preexisting"]
            and source["existing_file_policy"] == "reviewed"
            else "new"
        )
        try:
            asset_id = index_file(
                database, candidate.path, source_id=source_id,
                workflow_state=workflow_state, reconcile=bool(entry["asset_id"]),
            )
        except PermissionError as exc:
            permission_failure = f"PermissionError: {exc}"
            _upsert_observation(
                database, source_id, candidate, now_ns, preexisting=bool(entry["preexisting"]),
                disposition="error", asset_id=entry["asset_id"],
                last_error=permission_failure,
            )
            summary["errors"].append({"path": path_text, "error": permission_failure})
            break
        except FileNotFoundError:
            with connect(database) as db:
                db.execute("DELETE FROM source_entries WHERE current_path=?", (path_text,))
            summary["missing"] += 1
            continue
        except OSError as exc:
            message = f"{type(exc).__name__}: {exc}"
            _upsert_observation(
                database, source_id, candidate, now_ns,
                preexisting=bool(entry["preexisting"]), disposition="error",
                asset_id=entry["asset_id"], last_error=message,
            )
            summary["errors"].append({"path": path_text, "error": message})
            continue
        except ValueError as exc:
            message = str(exc)
            disposition = (
                "unsupported" if not entry["asset_id"]
                and message == "Unsupported or unrecognized media signature"
                else "error"
            )
            _upsert_observation(
                database, source_id, candidate, now_ns, preexisting=bool(entry["preexisting"]),
                disposition=disposition, asset_id=entry["asset_id"], last_error=message,
            )
            if disposition == "unsupported":
                summary["unsupported"] += 1
            else:
                if entry["asset_id"]:
                    with connect(database) as db:
                        db.execute(
                            "UPDATE assets SET workflow_state='error' WHERE asset_id=?",
                            (entry["asset_id"],),
                        )
                summary["errors"].append({"path": path_text, "error": message})
            continue
        _upsert_observation(
            database, source_id, candidate, now_ns, preexisting=bool(entry["preexisting"]),
            disposition="indexed", asset_id=asset_id,
        )
        if entry["asset_id"]:
            summary["updated"] += 1
        else:
            summary["indexed"] += 1

    with connect(database) as db:
        for entry in db.execute(
            "SELECT current_path,asset_id FROM source_entries "
            "WHERE source_id=? AND disposition<>'missing'",
            (source_id,),
        ).fetchall():
            if entry["current_path"] not in all_candidate_paths:
                if entry["asset_id"]:
                    db.execute(
                        "UPDATE source_entries SET disposition='missing',observed_at_ns=? "
                        "WHERE current_path=?",
                        (now_ns, entry["current_path"]),
                    )
                else:
                    db.execute(
                        "DELETE FROM source_entries WHERE current_path=?",
                        (entry["current_path"],),
                    )
                summary["missing"] += 1

    if permission_failure:
        _set_health(database, source_id, "permission_denied", permission_failure)
        summary.update(health="permission_denied", health_detail=permission_failure)
        return summary

    with connect(database) as db:
        db.execute(
            "UPDATE sources SET health='paused',health_detail=NULL,initial_scan_completed=1,"
            "last_scan_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_id=?",
            (source_id,),
        )
    summary["health"] = "paused"
    return summary


def scan_sources(
    database: Path,
    *,
    source_id: str | None = None,
    quiet_seconds: float = 2.0,
    now_ns: int | None = None,
) -> dict:
    """Observe configured sources once; callers schedule later passes or watchers."""
    if (
        not isinstance(quiet_seconds, (int, float))
        or not math.isfinite(quiet_seconds)
        or quiet_seconds < 0
    ):
        raise ValueError("quiet_seconds must be a finite nonnegative number")
    if now_ns is None:
        now_ns = time.time_ns()
    if type(now_ns) is not int or now_ns < 0:
        raise ValueError("now_ns must be a nonnegative integer")
    sources = list_sources(database)
    if source_id is not None:
        sources = [source for source in sources if source["source_id"] == source_id]
        if not sources:
            raise ValueError(f"Unknown source: {source_id}")
    enabled = [source for source in sources if source["enabled"]]
    results = [
        _scan_one(database, source, int(quiet_seconds * 1_000_000_000), now_ns)
        for source in enabled
    ]
    numeric = (
        "indexed", "updated", "renamed", "pending", "ignored_existing",
        "unchanged", "unsupported", "missing", "overlap_skipped",
    )
    totals = {key: sum(result[key] for result in results) for key in numeric}
    totals["errors"] = sum(len(result["errors"]) for result in results)
    return {"sources": results, "totals": totals}
