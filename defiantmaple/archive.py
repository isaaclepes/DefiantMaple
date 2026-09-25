"""Bounded, read-only generic ZIP preview. Never extracts or runs members."""
from dataclasses import asdict, dataclass
from pathlib import Path
import stat
import zipfile
import zlib

from .media import sniff


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 64 * 1024 * 1024
    members: int = 10_000
    total_bytes: int = 2 * 1024**3
    member_bytes: int = 256 * 1024**2
    ratio: int = 200
    prefix_bytes: int = 4096

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("Archive limits must be positive integers")


def unsafe_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return (
        not normalized or normalized.startswith("/")
        or any(ord(c) < 32 for c in normalized)
        or any(part in (".", "..") or ":" in part for part in normalized.split("/"))
    )


def inspect_archive(path: Path, limits: Limits = Limits()) -> dict:
    path = Path(path)
    # The file-size cap also bounds central-directory allocation by zipfile;
    # the member-count limit is checked after the central directory is parsed.
    with path.open("rb") as stream:
        stream.seek(0, 2)
        archive_size = stream.tell()
        if archive_size > limits.archive_bytes:
            raise ValueError("Archive exceeds archive_bytes limit")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > limits.members:
                raise ValueError("Archive exceeds members limit")
            total = sum(info.file_size for info in infos)
            if total > limits.total_bytes:
                raise ValueError("Archive exceeds total_bytes limit")
            items = []
            for index, info in enumerate(infos):
                warnings = []
                original = info.orig_filename
                mode = info.external_attr >> 16
                if unsafe_path(original):
                    warnings.append("unsafe_path")
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    warnings.append("link_or_special_file")
                if info.flag_bits & 1:
                    warnings.append("encrypted_member")
                if info.file_size > limits.member_bytes:
                    warnings.append("member_size_limit")
                if info.file_size / max(info.compress_size, 1) > limits.ratio:
                    warnings.append("compression_ratio_limit")
                detected = None
                nested = original.lower().endswith(".zip")
                if not warnings and not info.is_dir():
                    try:
                        with archive.open(info) as member:
                            prefix = member.read(limits.prefix_bytes)
                        detected = sniff(prefix)
                        nested |= prefix.startswith((b"PK\x03\x04", b"PK\x05\x06"))
                    except (OSError, ValueError, RuntimeError, NotImplementedError,
                            zipfile.BadZipFile, EOFError, zlib.error) as exc:
                        warnings.append("probe_failed:" + type(exc).__name__)
                if nested:
                    warnings.append("nested_archive_not_expanded")
                if detected:
                    warnings.append("decoder_validation_pending")
                # Generated ASCII names do not reuse untrusted archive paths.
                proposed = f"asset_{index + 1:05d}.{detected.extension}" if detected else None
                items.append({
                    "member_index": index, "original_member_path": original,
                    "declared_extension": Path(original).suffix.lstrip("."),
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                    "detected": asdict(detected) if detected else None,
                    "proposed_name": proposed, "warnings": warnings,
                    "candidate": detected is not None and not nested,
                })
            return {
                "archive_name": path.name, "adapter": "generic_signature_v1",
                "archive_bytes": archive_size, "member_count": len(infos),
                "total_compressed_bytes": sum(info.compress_size for info in infos),
                "total_uncompressed_bytes": total,
                "preview_only": True, "items": items,
            }
