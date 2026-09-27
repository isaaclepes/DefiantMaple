"""Create disposable fictional artwork for the hands-on gallery smoke test."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import shutil
import struct
import zlib

from PIL import Image, ImageDraw


def _portrait(index: int) -> Image.Image:
    colors = ("#ab4a55", "#447cb0", "#7c609d", "#548c69", "#b18847", "#4d8190")
    image = Image.new("RGBA", (320, 320), (235, 238, 245, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 30, 290, 290), fill="#e0e6ef")
    draw.ellipse((78, 70, 242, 245), fill=colors[index % len(colors)])
    draw.ellipse((102, 92, 218, 235), fill="#e9ba91")
    draw.ellipse((127, 155, 139, 166), fill="#293546")
    draw.ellipse((181, 155, 193, 166), fill="#293546")
    draw.arc((145, 177, 178, 200), 5, 170, fill="#774044", width=4)
    draw.rectangle((103, 242, 217, 308), fill=colors[(index + 2) % len(colors)])
    return image


def _oversized_png_header() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (struct.pack(">I", len(data)) + payload
                + struct.pack(">I", zlib.crc32(payload)))

    ihdr = struct.pack(">IIBBBBB", 50_000, 50_000, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
            + chunk(b"IEND", b""))


def generate(root: Path) -> dict:
    root = Path(root).expanduser().resolve(strict=False)
    repository = Path(__file__).resolve().parents[1]
    if root == repository or repository in root.parents:
        raise ValueError("Disposable image fixtures must be outside Git")
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fixture destination must be empty")
    root.mkdir(parents=True, exist_ok=True)
    (_portrait(0)).save(root / "fictional-amber.png")
    shutil.copyfile(root / "fictional-amber.png", root / "fictional-amber-copy.png")
    _portrait(1).convert("RGB").save(root / "fictional-blue.jpg", quality=90)
    _portrait(2).convert("P").save(root / "fictional-violet.gif")
    _portrait(3).save(root / "fictional-green.webp", lossless=True)
    _portrait(4).save(root / "fictional-transparent.png")
    oriented = _portrait(5).convert("RGB").crop((0, 0, 260, 320))
    exif = Image.Exif()
    exif[274] = 6
    oriented.save(root / "fictional-exif.jpg", exif=exif)
    (root / "fictional-malformed.png").write_bytes(b"\x89PNG\r\n\x1a\ncorrupt")
    (root / "fictional-oversized.png").write_bytes(_oversized_png_header())
    (root / "unsupported.txt").write_text("This is not an image.\n", encoding="utf-8")
    return {"root": str(root), "images": 9, "unsupported": 1,
            "note": "Generated fictional images only; delete this disposable folder when done."}


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
