"""Signature hints only: these results do not establish decodability."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaType:
    mime: str
    extension: str
    method: str = "magic_bytes"


def sniff(data: bytes) -> MediaType | None:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
        (b"\xff\xd8\xff", "image/jpeg", "jpg"),
        (b"GIF87a", "image/gif", "gif"),
        (b"GIF89a", "image/gif", "gif"),
    )
    for signature, mime, extension in signatures:
        if data.startswith(signature):
            return MediaType(mime, extension)
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return MediaType("image/webp", "webp")
    # ISO-BMFF is broader than MP4 (e.g. HEIC/AVIF); accept explicit brands only.
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (
        b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ",
    ):
        return MediaType("video/mp4", "mp4")
    return None
