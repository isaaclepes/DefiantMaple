"""Bounded thumbnail generation in a spawned decoder process."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import multiprocessing
import os
import re
import stat
import tempfile
import uuid
import warnings

from PIL import (
    Image,
    ImageFile,
    ImageOps,
    UnidentifiedImageError,
    __version__ as PILLOW_VERSION,
)

from .catalog import connect


CACHE_SCHEMA = 1
SHA256 = re.compile(r"[0-9a-f]{64}")


class ThumbnailError(ValueError):
    """A thumbnail could not be safely produced."""


class _OversizedImageError(ValueError):
    pass


@dataclass(frozen=True)
class ThumbnailLimits:
    max_source_bytes: int = 512 * 1024 * 1024
    max_dimension: int = 32_768
    max_pixels: int = 80_000_000
    timeout_seconds: float = 20.0

    def __post_init__(self):
        values = (self.max_source_bytes, self.max_dimension, self.max_pixels)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Thumbnail size limits must be positive integers")
        if not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= 0:
            raise ValueError("Thumbnail timeout_seconds must be positive")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_identity(value) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _decode_worker(payload: dict, sender) -> None:
    """Decode one image in a child process and report only structured data."""
    try:
        limits = ThumbnailLimits(**payload["limits"])
        Image.MAX_IMAGE_PIXELS = limits.max_pixels
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        source = Path(payload["source"])
        output = Path(payload["output"])

        with source.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("thumbnail source is not a regular file")
            if before.st_size != payload["source_bytes"]:
                raise ValueError("thumbnail source size differs from the catalog fingerprint")
            if before.st_size > limits.max_source_bytes:
                raise _OversizedImageError("thumbnail source exceeds max_source_bytes")

            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            if digest.hexdigest() != payload["source_sha256"]:
                raise ValueError("thumbnail source content differs from the catalog fingerprint")
            stream.seek(0)

            with Image.open(stream) as decoded:
                width, height = decoded.size
                if (
                    width <= 0
                    or height <= 0
                    or width > limits.max_dimension
                    or height > limits.max_dimension
                    or width * height > limits.max_pixels
                ):
                    raise _OversizedImageError(
                        f"image dimensions {width}x{height} exceed thumbnail limits"
                    )
                source_format = decoded.format
                decoded.seek(0)
                oriented = ImageOps.exif_transpose(decoded)
                try:
                    transparent = oriented.mode in ("RGBA", "LA") or (
                        oriented.mode == "P" and "transparency" in oriented.info
                    )
                    rendered = oriented.convert("RGBA" if transparent else "RGB")
                    try:
                        rendered.thumbnail(
                            (payload["max_edge"], payload["max_edge"]),
                            Image.Resampling.LANCZOS,
                        )
                        rendered.save(output, format="PNG", optimize=False, compress_level=6)
                        output_width, output_height = rendered.size
                    finally:
                        rendered.close()
                finally:
                    oriented.close()

            after = os.fstat(stream.fileno())
            if _stat_identity(before) != _stat_identity(after):
                raise ValueError("thumbnail source changed during decoding")

        with output.open("rb+") as generated:
            os.fsync(generated.fileno())
        sender.send({
            "ok": True,
            "source_format": source_format,
            "width": output_width,
            "height": output_height,
            "output_bytes": output.stat().st_size,
            "output_sha256": _file_sha256(output),
        })
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            _OversizedImageError) as exc:
        sender.send({"ok": False, "category": "oversized_image", "error": str(exc)})
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        sender.send({"ok": False, "category": "decode_error", "error": str(exc)})
    except Exception as exc:  # The parent still contains unexpected decoder failures.
        sender.send({
            "ok": False,
            "category": "decoder_worker_error",
            "error": f"{type(exc).__name__}: {exc}",
        })
    finally:
        sender.close()


def _stop_process(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(2)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(2)


def _run_decoder(payload: dict, timeout: float) -> dict:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_decode_worker, args=(payload, sender))
    try:
        process.start()
        sender.close()
        if not receiver.poll(timeout):
            _stop_process(process)
            raise ThumbnailError(f"decoder_timeout: exceeded {timeout:g} seconds")
        try:
            result = receiver.recv()
        except EOFError as exc:
            process.join(2)
            raise ThumbnailError(
                f"decoder_worker_exit: process exited with code {process.exitcode}"
            ) from exc
        process.join(2)
        if process.is_alive():
            _stop_process(process)
            raise ThumbnailError("decoder_worker_exit: process did not stop after reporting")
        if not result.get("ok"):
            raise ThumbnailError(f"{result['category']}: {result['error']}")
        if process.exitcode != 0:
            raise ThumbnailError(
                f"decoder_worker_exit: process exited with code {process.exitcode}"
            )
        return result
    finally:
        sender.close()
        receiver.close()
        if process.is_alive():
            _stop_process(process)


def _write_json_atomic(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".thumbnail-manifest-", suffix=".json"
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _cached_result(image_path: Path, manifest_path: Path, expected: dict) -> dict | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if manifest.get(key) != value:
                return None
        if image_path.stat().st_size != manifest["output_bytes"]:
            return None
        if _file_sha256(image_path) != manifest["output_sha256"]:
            return None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return {**manifest, "cache_hit": True, "path": str(image_path)}


def thumbnail_for(
    database: Path,
    asset_id: str,
    cache_root: Path,
    max_edge: int = 256,
    limits: ThumbnailLimits = ThumbnailLimits(),
) -> dict:
    """Return a validated PNG cache entry for one cataloged image asset."""
    if type(max_edge) is not int or not 32 <= max_edge <= 2_048:
        raise ValueError("max_edge must be an integer from 32 through 2048")
    try:
        canonical_id = str(uuid.UUID(asset_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("asset_id must be a UUID") from exc

    with connect(database) as catalog:
        row = catalog.execute(
            "SELECT asset_id,current_path,media_type,sha256,byte_size "
            "FROM assets WHERE asset_id=?",
            (canonical_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Unknown asset_id: {canonical_id}")
    asset = dict(row)
    if not asset["media_type"].startswith("image/"):
        raise ThumbnailError("unsupported_media: thumbnails require an image asset")
    if not SHA256.fullmatch(asset["sha256"]):
        raise ThumbnailError("invalid_catalog_fingerprint: sha256 is malformed")
    if asset["byte_size"] > limits.max_source_bytes:
        raise ThumbnailError("oversized_image: source exceeds max_source_bytes")

    # Hyphens keep the cache path valid on Windows while retaining an inspectable key.
    source_fingerprint = f"sha256-{asset['sha256']}-bytes-{asset['byte_size']}"
    cache_root = Path(cache_root).resolve()
    asset_root = cache_root / canonical_id[:2] / canonical_id / source_fingerprint
    asset_root.mkdir(parents=True, exist_ok=True)
    basename = f"thumbnail-v{CACHE_SCHEMA}-{max_edge}"
    image_path = asset_root / f"{basename}.png"
    manifest_path = asset_root / f"{basename}.json"
    expected = {
        "cache_schema": CACHE_SCHEMA,
        "asset_id": canonical_id,
        "source_fingerprint": source_fingerprint,
        "source_sha256": asset["sha256"],
        "source_bytes": asset["byte_size"],
        "media_type": asset["media_type"],
        "max_edge": max_edge,
        "decoder": "Pillow",
        "decoder_version": PILLOW_VERSION,
    }
    cached = _cached_result(image_path, manifest_path, expected)
    if cached is not None:
        return cached
    image_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)

    descriptor, temporary = tempfile.mkstemp(
        dir=asset_root, prefix=".thumbnail-worker-", suffix=".png"
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        result = _run_decoder({
            "source": asset["current_path"],
            "output": str(temporary_path),
            "source_sha256": asset["sha256"],
            "source_bytes": asset["byte_size"],
            "max_edge": max_edge,
            "limits": asdict(limits),
        }, limits.timeout_seconds)
        if result["width"] <= 0 or result["height"] <= 0:
            raise ThumbnailError("decoder_worker_error: generated invalid dimensions")
        os.replace(temporary_path, image_path)
        manifest = {**expected, **result}
        manifest.pop("ok", None)
        _write_json_atomic(manifest_path, manifest)
        return {**manifest, "cache_hit": False, "path": str(image_path)}
    finally:
        temporary_path.unlink(missing_ok=True)
