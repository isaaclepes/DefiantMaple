"""Bounded name-only derivative; no catalog access or portable-backup semantics."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

from defiantmaple.metadata import NAME_PREVIEW_FIELDS

MAX_DOCUMENT_BYTES = 131072
_FIELDS = tuple(key for key, _ in NAME_PREVIEW_FIELDS)


def encode_name_export(projection: dict) -> bytes:
    """Serialize only an explicit name projection, copying no other metadata."""
    if (type(projection) is not dict or any(type(k) is not str or k not in _FIELDS for k in projection)
            or any(type(v) is not list or any(type(s) is not str for s in v)
                   for v in projection.values())):
        raise ValueError("Choose only lists of names from the available fields")
    if sum(map(len, projection.values())) > 256:
        raise ValueError("Name export is limited to 256 assigned names")
    try:
        if sum(len(name.encode("utf-8")) for values in projection.values() for name in values) > 65536:
            raise ValueError("Name export exceeds the 64 KiB name-text limit")
    except UnicodeError as exc:
        raise ValueError("Name export contains invalid Unicode") from exc
    selected = [key for key in _FIELDS if key in projection]
    document = {"format": "defiantmaple-name-projection", "version": 1,
                "scope": "selected names only; not a portable catalog or backup",
                "included_fields": selected,
                "omitted_fields": [key for key in _FIELDS if key not in projection],
                "names": {key: list(projection[key]) for key in selected}}
    try:
        payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Name export contains invalid Unicode") from exc
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError("Name export exceeds the 128 KiB document limit")
    return payload


@dataclass(frozen=True)
class ExportResult:
    published: bool | None
    cleanup_pending: bool = False
    error: str = ""


def save_name_export(destination: str | Path, payload: bytes) -> ExportResult:
    """Publish complete bytes at a new name; never open or replace destination.

    A private same-directory staging file is closed before exclusive link
    publication. Filesystems without hard-link support refuse. No crash/power-loss
    or network filesystem durability guarantee is made. Choose a trusted local
    directory: hostile concurrent directory mutation is outside this contract.
    Staging cleanup failure is reported, including when publication succeeded.
    """
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_DOCUMENT_BYTES:
        raise ValueError("Invalid bounded export payload")
    path = Path(destination)
    if not path.name or path.name in (".", ".."):
        return ExportResult(False, error="Choose a new file name")
    staging = None
    fd = None
    published = False
    error = ""
    cleanup_pending = False
    staging_identity = None
    try:
        fd, staging = tempfile.mkstemp(prefix=".defiantmaple-export-", dir=path.parent)
        staging_stat = os.fstat(fd)
        staging_identity = (staging_stat.st_dev, staging_stat.st_ino)
        stream = os.fdopen(fd, "wb")
        fd = None  # stream now owns the descriptor
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # link() fails for every existing destination, including dangling symlinks.
        current = os.lstat(staging)
        if (current.st_dev, current.st_ino) != staging_identity:
            raise OSError("Staging identity changed")
        os.link(staging, path, follow_symlinks=False)
        published = True
    except OSError as exc:
        # Do not echo private paths or names into application feedback/logs.
        error = f"File operation failed ({type(exc).__name__}, errno {exc.errno})"
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if staging is not None:
            try:
                current = os.lstat(staging)
                if (current.st_dev, current.st_ino) != staging_identity:
                    cleanup_pending = True
                else:
                    os.unlink(staging)
            except OSError:
                cleanup_pending = True
    return ExportResult(published, cleanup_pending, error)
