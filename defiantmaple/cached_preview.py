"""Read-only, bounded derived-preview inspection; never opens original media."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import hashlib
import json
import math
import multiprocessing
import os
import re
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
import warnings

from PIL import Image, ImageFile, __version__ as PILLOW_VERSION
from .catalog import SCHEMA_VERSION

CACHE_SCHEMA = 1
OUTPUT_POLICY = "legacy-exif-oriented-rgb-rgba-first-frame-png-no-icc-transform"
SOURCE_POLICY = (512 * 1024 * 1024, 32768, 80000000)
EDGES = frozenset(range(96, 225)) | {32, 64, 128, 256, 512, 1024, 2048}
SHA256 = re.compile(r"[0-9a-f]{64}")
_ORPHANS = {}
_OWNERSHIP_LOCK = threading.Lock()


class CacheRefusal(ValueError):
    pass


@dataclass(frozen=True)
class CachedTarget:
    asset_id: str
    sha256: str
    byte_size: int
    media_type: str
    revision: int
    path: str
    source_id: str | None

    def __post_init__(self):
        if str(uuid.UUID(self.asset_id)) != self.asset_id:
            raise ValueError("Cache target ID must be a canonical UUID")
        if not isinstance(self.sha256, str) or not SHA256.fullmatch(self.sha256):
            raise ValueError("Cache target fingerprint is invalid")
        if type(self.byte_size) is not int or self.byte_size < 0:
            raise ValueError("Cache target byte size is invalid")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("Cache target revision is invalid")
        if not isinstance(self.media_type, str) or not self.media_type.startswith("image/"):
            raise ValueError("Cache target requires indexed image content")
        if not isinstance(self.path, str) or not Path(self.path).is_absolute():
            raise ValueError("Cache target path must be absolute")
        if self.source_id is not None and str(uuid.UUID(self.source_id)) != self.source_id:
            raise ValueError("Cache target source ID is invalid")


def capture_target(row: dict) -> CachedTarget:
    """Lexical capture only: no original or cache filesystem access."""
    return CachedTarget(row["asset_id"], row["sha256"], row["byte_size"],
                        row["media_type"], row.get("revision", 0),
                        row["current_path"], row.get("source_id"))


@dataclass(frozen=True)
class CacheReadLimits:
    manifest_bytes: int = 16384
    png_bytes: int = 20 * 1024 * 1024
    max_edge: int = 2048
    max_pixels: int = 4194304
    raw_bytes: int = 16 * 1024 * 1024
    directory_entries: int = 512
    timeout_seconds: float = 5.0
    address_space_bytes: int = 512 * 1024 * 1024

    def __post_init__(self):
        for name in ("manifest_bytes", "png_bytes", "max_edge", "max_pixels",
                     "raw_bytes", "directory_entries", "address_space_bytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError("Cache limits must be positive integers")
        if (type(self.timeout_seconds) not in (int, float) or
                not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 5):
            raise ValueError("Cache deadline must be finite, positive and no greater than five seconds")
        # Configurations may tighten limits, never silently expand the contract.
        for name, ceiling in (("manifest_bytes", 16384), ("png_bytes", 20 * 1024 * 1024),
                              ("max_edge", 2048), ("max_pixels", 4194304),
                              ("raw_bytes", 16 * 1024 * 1024), ("directory_entries", 512),
                              ("address_space_bytes", 512 * 1024 * 1024)):
            if getattr(self, name) > ceiling:
                raise ValueError(f"{name} exceeds the supported cache-read ceiling")


@dataclass(frozen=True)
class CachedResult:
    status: str
    message: str
    target: CachedTarget
    width: int = 0
    height: int = 0
    requested_edge: int = 0
    cache_edge: int = 0
    pixels: bytes = b""
    entries_examined: int = 0
    catalog_drift: bool = False
    cleanup_complete: bool = True
    address_space_enforced: bool = False
    address_space_note: str = ""


def generation_refusal(row: dict | None) -> str | None:
    """Last-observed catalog eligibility, never a fresh source probe."""
    if row is None:
        return "No indexed asset selected"
    if row.get("source_id") is None:
        return "Standalone asset has inconsistent source linkage" if row.get("linked_entry_count", 0) else None
    if row.get("source_health") not in ("paused", "watching"):
        return "Original unavailable or unresolved in the last source observation"
    if (row.get("entry_disposition") != "indexed" or row.get("source_relation_count", 0) != 1
            or row.get("entry_path") != row.get("current_path")
            or row.get("entry_source_id") != row.get("source_id")):
        return "Original source relation is unavailable or unresolved"
    return None


def availability_text(row: dict) -> str:
    if row.get("source_id") is None:
        return "availability unchecked; last indexed content"
    health = row.get("source_health") or "unresolved"
    disposition = row.get("entry_disposition") or "unresolved"
    return f"last source observation: {health.replace('_', ' ')} / {disposition.replace('_', ' ')}"


def fresh_generation_refusal(database: Path, target: CachedTarget, admitted_row: dict) -> str | None:
    """Off-GUI requery before original generation; cache-only admission never upgrades."""
    reason = generation_refusal(admitted_row)
    if reason:
        return reason
    db = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=.25)
    db.row_factory = sqlite3.Row
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            return "Unsupported catalog version"
        row = db.execute("SELECT assets.*,sources.health AS source_health,"
                         "source_entries.current_path AS entry_path,source_entries.source_id AS entry_source_id,"
                         "source_entries.disposition AS entry_disposition,"
                         "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id) AS linked_entry_count,"
                         "(SELECT COUNT(*) FROM source_entries e WHERE e.asset_id=assets.asset_id "
                         "AND e.source_id=assets.source_id AND e.current_path=assets.current_path "
                         "AND e.disposition='indexed') AS source_relation_count "
                         "FROM assets LEFT JOIN sources ON sources.source_id=assets.source_id "
                         "LEFT JOIN source_entries ON source_entries.asset_id=assets.asset_id "
                         "WHERE assets.asset_id=? LIMIT 1", (target.asset_id,)).fetchone()
    finally:
        db.close()
    if row is None:
        return "Captured asset is no longer indexed"
    current = capture_target(dict(row))
    if (current.asset_id, current.sha256, current.byte_size, current.path, current.source_id, current.media_type) != (
            target.asset_id, target.sha256, target.byte_size, target.path, target.source_id, target.media_type):
        return "Captured asset content or source location changed"
    return generation_refusal(dict(row))


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns)


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import msvcrt
    _KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _KERNEL.CreateFileW.restype = wintypes.HANDLE
    _KERNEL.CloseHandle.argtypes = (wintypes.HANDLE,)
    _KERNEL.CloseHandle.restype = wintypes.BOOL

    class _FileInfo(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                    ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    _KERNEL.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.POINTER(_FileInfo))
    _KERNEL.GetFileInformationByHandle.restype = wintypes.BOOL

    def _windows_handle(path, directory):
        # Holding each directory without FILE_SHARE_DELETE pins its pathname.
        handle = _KERNEL.CreateFileW(str(path), 0x80 if directory else 0x80000000,
                                     3 if directory else 1, None, 3,
                                     0x00200000 | (0x02000000 if directory else 0), None)
        if handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "Cache handle could not be opened")
        info = _FileInfo()
        if not _KERNEL.GetFileInformationByHandle(handle, ctypes.byref(info)):
            _KERNEL.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "Cache handle identity unavailable")
        if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory:
            _KERNEL.CloseHandle(handle)
            raise CacheRefusal("Cache links/reparse points or unsafe types are refused")
        return handle


class _DirectoryTree:
    """Pinned no-follow hierarchy; no symlink/UNC fallback to ordinary open."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.handles = []
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise CacheRefusal("Cache storage requires an absolute contained path")
        try:
            if os.name == "nt":
                if self.path.drive.startswith("\\\\"):
                    raise CacheRefusal("Cache-only reads require local cache storage")
                current = Path(self.path.anchor)
                self.handles.append(_windows_handle(current, True))
                for part in self.path.parts[1:]:
                    current /= part
                    self.handles.append(_windows_handle(current, True))
            elif (os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")
                  and hasattr(os, "O_DIRECTORY")):
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
                self.handles.append(os.open(self.path.anchor, flags))
                for part in self.path.parts[1:]:
                    self.handles.append(os.open(part, flags, dir_fd=self.handles[-1]))
            else:
                raise CacheRefusal("Safe cache containment is unsupported on this platform")
        except BaseException:
            self.close()
            raise

    def close(self):
        for handle in reversed(self.handles):
            if os.name == "nt":
                _KERNEL.CloseHandle(handle)
            else:
                os.close(handle)
        self.handles.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def entries(self):
        return os.scandir(self.path if os.name == "nt" else self.handles[-1])

    def read(self, name: str, ceiling: int, *, digest_only=False):
        if Path(name).name != name or name in (".", ".."):
            raise CacheRefusal("Unsafe cache leaf")
        if os.name == "nt":
            path = self.path / name
            before = path.lstat()
            if _unsafe(before) or not stat.S_ISREG(before.st_mode):
                raise CacheRefusal("Cache input is not a nonlinked regular file")
            handle = _windows_handle(path, False)
            try:
                descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                _KERNEL.CloseHandle(handle)
                raise
            after_stat = path.lstat
        else:
            descriptor_dir = self.handles[-1]
            before = os.stat(name, dir_fd=descriptor_dir, follow_symlinks=False)
            if _unsafe(before) or not stat.S_ISREG(before.st_mode):
                raise CacheRefusal("Cache input is not a nonlinked regular file")
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                                 dir_fd=descriptor_dir)
            after_stat = lambda: os.stat(name, dir_fd=descriptor_dir, follow_symlinks=False)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > ceiling:
                raise CacheRefusal("Cache input exceeds its regular-file byte bound")
            if _identity(before) != _identity(opened):
                raise CacheRefusal("Cache input changed while opening")
            if digest_only:
                digest = hashlib.sha256()
                length = 0
                while chunk := stream.read(min(1024 * 1024, ceiling - length + 1)):
                    length += len(chunk)
                    if length > ceiling:
                        raise CacheRefusal("Cache input exceeds its byte bound")
                    digest.update(chunk)
                value = (digest.hexdigest(), length)
            else:
                value = stream.read(ceiling + 1)
                length = len(value)
            if length > ceiling or length != opened.st_size:
                raise CacheRefusal("Cache input size changed or exceeds its byte bound")
            if _identity(opened) != _identity(os.fstat(stream.fileno())) or _identity(opened) != _identity(after_stat()):
                raise CacheRefusal("Cache input changed while reading")
        return value


def read_bounded_cache_file(path: Path, ceiling: int) -> bytes:
    """Also used for the narrow legacy cache JSON/checksum read exception."""
    path = Path(path)
    with _DirectoryTree(path.parent) as directory:
        return directory.read(path.name, ceiling)


def hash_bounded_cache_file(path: Path, ceiling: int) -> tuple[str, int]:
    """Pinned/no-follow checksum in at most 1 MiB chunks, never source hashing."""
    path = Path(path)
    with _DirectoryTree(path.parent) as directory:
        return directory.read(path.name, ceiling, digest_only=True)


def stat_regular_cache_file(path: Path):
    """No-follow fallback observation for malformed regular cache leases."""
    path = Path(path)
    with _DirectoryTree(path.parent) as directory:
        observed = (path.lstat() if os.name == "nt" else
                    os.stat(path.name, dir_fd=directory.handles[-1], follow_symlinks=False))
        if _unsafe(observed) or not stat.S_ISREG(observed.st_mode):
            raise CacheRefusal("Cache lease is not a nonlinked regular file")
        return observed


def _json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CacheRefusal("Duplicate cache manifest key")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(CacheRefusal("Nonfinite cache value")))
    if not isinstance(value, dict) or any(type(v) not in (str, int, float, bool, type(None)) for v in value.values()):
        raise CacheRefusal("Cache manifest requires bounded scalar fields")
    return value


def _basename(edge):
    return f"thumbnail-v1-e{edge}-b{SOURCE_POLICY[0]}-d{SOURCE_POLICY[1]}-p{SOURCE_POLICY[2]}"


def _asset_snapshot(database, target, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("Cache lookup deadline expired")
    # Read-only admission with a short SQLite wait. Only the local catalog path
    # is resolved; target.path and source roots are never filesystem operands.
    db = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True,
                         timeout=min(0.25, max(.001, deadline - time.monotonic())))
    db.row_factory = sqlite3.Row
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise CacheRefusal("Unsupported catalog version for cached viewing")
        row = db.execute("SELECT * FROM assets WHERE asset_id=?", (target.asset_id,)).fetchone()
    finally:
        db.close()
    if row is None:
        raise CacheRefusal("Captured asset is no longer indexed")
    row = dict(row)
    if (row["sha256"], row["byte_size"], row["media_type"]) != (target.sha256, target.byte_size, target.media_type):
        raise CacheRefusal("Indexed content changed; reopen the cached preview")
    return (row["revision"] != target.revision or row["current_path"] != target.path
            or row["source_id"] != target.source_id)


def _address_space_limit(ceiling):
    try:
        import resource
    except ImportError:
        return False, "Address-space enforcement unavailable on this platform"
    if not hasattr(resource, "RLIMIT_AS"):
        return False, "Address-space enforcement unavailable on this platform"
    try:
        hard = resource.getrlimit(resource.RLIMIT_AS)[1]
        value = min(ceiling, hard) if hard != resource.RLIM_INFINITY else ceiling
        resource.setrlimit(resource.RLIMIT_AS, (value, hard))
        return True, f"RLIMIT_AS {value} bytes (address space, not RSS)"
    except (OSError, ValueError) as exc:
        raise CacheRefusal(f"Required address-space ceiling could not be applied: {type(exc).__name__}") from exc


def _cache_helper(database, target, root, requested, limits, deadline, stopped, output, sender):
    enforcement = (False, "Helper did not establish address-space enforcement")
    count = 0
    try:
        enforcement = _address_space_limit(limits.address_space_bytes)
        def check():
            if stopped.is_set():
                raise InterruptedError("Cached preview canceled")
            if time.monotonic() >= deadline:
                raise TimeoutError("Cached preview deadline expired")
        check()
        drift = _asset_snapshot(database, target, deadline)
        fingerprint = f"sha256-{target.sha256}-bytes-{target.byte_size}"
        directory_path = Path(root) / target.asset_id[:2] / target.asset_id / fingerprint
        edges = EDGES | {requested}
        names = {_basename(edge) + suffix: edge for edge in edges for suffix in (".json", ".png")}
        present = set()
        try:
            directory = _DirectoryTree(directory_path)
        except FileNotFoundError:
            sender.send({"status": "no_cache", "message": "No cached preview for the indexed content",
                         "enforcement": enforcement, "entries_examined": 0})
            return
        with directory:
            with directory.entries() as entries:
                for entry in entries:
                    check()
                    count += 1
                    if count > limits.directory_entries:
                        raise CacheRefusal("Cache directory entry limit exceeded")
                    if entry.name in names:
                        present.add(names[entry.name])
            check()
            if not present:
                sender.send({"status": "no_cache", "message": "No compatible cached size for the indexed content",
                             "enforcement": enforcement, "entries_examined": count})
                return
            edge = (requested if requested in present else
                    min((v for v in present if v > requested), default=0) or max(present))
            base = _basename(edge)
            manifest = _json_object(directory.read(base + ".json", limits.manifest_bytes))
            expected = {"cache_schema": CACHE_SCHEMA, "asset_id": target.asset_id,
                        "source_fingerprint": fingerprint, "source_sha256": target.sha256,
                        "source_bytes": target.byte_size, "media_type": target.media_type,
                        "max_edge": edge, "decoder": "Pillow", "decoder_version": PILLOW_VERSION,
                        "max_source_bytes": SOURCE_POLICY[0], "max_dimension": SOURCE_POLICY[1],
                        "max_pixels": SOURCE_POLICY[2]}
            allowed = set(expected) | {"source_format", "width", "height", "output_bytes", "output_sha256", "output_policy"}
            if set(manifest) - allowed or ("output_policy" in manifest and manifest["output_policy"] != OUTPUT_POLICY):
                raise CacheRefusal("Preferred cached entry has an unknown output policy or manifest field")
            # Legacy v1 inferred this policy from its fixed generator; it did
            # not publish an independently authenticated output-policy field.
            if any(type(manifest.get(k)) is not type(v) or manifest.get(k) != v for k, v in expected.items()):
                raise CacheRefusal("Preferred cached entry has incompatible identity or display policy")
            for key in ("output_bytes", "width", "height"):
                if type(manifest.get(key)) is not int or manifest[key] <= 0:
                    raise CacheRefusal("Invalid cached dimensions or byte declaration")
            width, height = manifest["width"], manifest["height"]
            if (max(width, height) > min(edge, limits.max_edge) or width * height > limits.max_pixels
                    or width * height * 4 > limits.raw_bytes or manifest["output_bytes"] > limits.png_bytes):
                raise CacheRefusal("Cached preview exceeds image/output bounds")
            raw = directory.read(base + ".png", limits.png_bytes)
            if (len(raw) != manifest["output_bytes"] or not isinstance(manifest.get("output_sha256"), str)
                    or not SHA256.fullmatch(manifest["output_sha256"])
                    or hashlib.sha256(raw).hexdigest() != manifest["output_sha256"]):
                raise CacheRefusal("Cached preview digest or byte size disagrees with its manifest")
            check()
            Image.MAX_IMAGE_PIXELS = limits.max_pixels
            ImageFile.LOAD_TRUNCATED_IMAGES = False
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=["PNG"]) as image:
                if image.format != "PNG" or image.mode not in ("RGB", "RGBA") or image.size != (width, height) or getattr(image, "n_frames", 1) != 1:
                    raise CacheRefusal("Cached preview format or dimensions disagree with its manifest")
                image.load()
                with image.convert("RGBA") as rgba:
                    pixels = rgba.tobytes()
            check()
            # No cache file is touched by this normalized private output.
            with open(output, "wb") as stream:
                stream.write(pixels)
            drift |= _asset_snapshot(database, target, deadline)
            check()
            sender.send({"status": "ready", "message": "Cached preview of last indexed content",
                         "width": width, "height": height, "cache_edge": edge,
                         "catalog_drift": drift, "entries_examined": count, "enforcement": enforcement})
    except InterruptedError as exc:
        sender.send({"status": "cancelled", "message": str(exc), "enforcement": enforcement, "entries_examined": count})
    except TimeoutError as exc:
        sender.send({"status": "timeout", "message": str(exc), "enforcement": enforcement, "entries_examined": count})
    except Exception as exc:
        sender.send({"status": "refused", "message": f"Cached preview refused: {type(exc).__name__}: {exc}",
                     "enforcement": enforcement, "entries_examined": count})
    finally:
        sender.close()


def read_cached_preview(database: Path, target: CachedTarget, cache_root: Path, requested_edge=256,
                        limits: CacheReadLimits = CacheReadLimits(), cancel_event=None) -> CachedResult:
    """One owned child; deadline and separate bounded cleanup are observable."""
    if type(target) is not CachedTarget or type(limits) is not CacheReadLimits:
        raise ValueError("Cached reads require typed immutable target and limits")
    if type(requested_edge) is not int or not 32 <= requested_edge <= 2048:
        raise ValueError("Requested cache edge must be from 32 through 2048")
    with _OWNERSHIP_LOCK:
        for pid, (process, temporary) in list(_ORPHANS.items()):
            if not process.is_alive():
                process.join(0)
                temporary.cleanup()
                del _ORPHANS[pid]
        if _ORPHANS:
            return CachedResult("cleanup_failed", "Prior cache worker remains owned; replacement refused", target, cleanup_complete=False)
    if cancel_event is not None and cancel_event.is_set():
        return CachedResult("cancelled", "Cached preview canceled", target)
    started = time.monotonic()
    context = multiprocessing.get_context("spawn")
    stopped = context.Event()
    receiver, sender = context.Pipe(duplex=False)
    temporary = tempfile.TemporaryDirectory(prefix="defiantmaple-cache-read-")
    # Only supervisor-owned local scratch is canonicalized; never target.path.
    output = Path(temporary.name).resolve(strict=True) / "normalized.rgba"
    process = context.Process(target=_cache_helper, args=(Path(database), target, Path(cache_root),
                              requested_edge, limits, started + limits.timeout_seconds,
                              stopped, str(output), sender))
    result = {"status": "refused", "message": "Cache worker could not start"}
    try:
        process.start()
        sender.close()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                stopped.set()
                result = {"status": "cancelled", "message": "Cached preview canceled"}
                break
            if time.monotonic() >= started + limits.timeout_seconds:
                stopped.set()
                result = {"status": "timeout", "message": "Cached preview timed out"}
                break
            if receiver.poll(.05):
                try:
                    result = receiver.recv()
                except EOFError:
                    result = {"status": "refused", "message": "Cache worker exited without a result"}
                break
            if not process.is_alive():
                result = {"status": "refused", "message": "Cache worker exited without a result"}
                break
        process.join(.1)
        if result.get("status") == "ready":
            width, height = result["width"], result["height"]
            pixels = read_bounded_cache_file(output, limits.raw_bytes)
            if len(pixels) != width * height * 4:
                raise CacheRefusal("Normalized cache image has inconsistent byte size")
            if time.monotonic() >= started + limits.timeout_seconds:
                result = {"status": "timeout", "message": "Cached preview deadline expired during delivery"}
    except Exception as exc:
        result = {"status": "refused", "message": f"Cache worker failed: {type(exc).__name__}: {exc}"}
    finally:
        if process.pid is not None:
            if process.is_alive():
                stopped.set()
                process.terminate()
                process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
        receiver.close()
        sender.close()
        clean = process.pid is None or not process.is_alive()
        if clean:
            temporary.cleanup()
        else:
            with _OWNERSHIP_LOCK:
                _ORPHANS[process.pid] = (process, temporary)
    enforced, note = result.get("enforcement", (False, "Worker enforcement not reported"))
    return CachedResult(result["status"] if clean else "cleanup_failed", result["message"], target,
                        width=result.get("width", 0), height=result.get("height", 0),
                        requested_edge=requested_edge, cache_edge=result.get("cache_edge", 0),
                        pixels=pixels if result["status"] == "ready" and clean else b"",
                        entries_examined=result.get("entries_examined", 0), catalog_drift=result.get("catalog_drift", False),
                        cleanup_complete=clean, address_space_enforced=enforced, address_space_note=note)
