"""Deterministic, original cartoon portraits for a small retrieval smoke test.

These labels describe the drawings generated below; they are not claims about
real character identity or model recognition accuracy on an artist's library.
"""
from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageOps
from PIL import __version__ as pillow_version


CHARACTERS = (
    ("amber-bob", "bob", "#bb672e", "#38638b", "#e9b680"),
    ("cobalt-spikes", "spikes", "#2762a6", "#b4514d", "#dfaa78"),
    ("violet-twins", "twins", "#744c9b", "#e3a747", "#f0bd93"),
    ("jade-long", "long", "#247c67", "#814f83", "#d99b70"),
    ("ruby-curls", "curls", "#a53e52", "#458376", "#b87958"),
    ("silver-cap", "cap", "#909caa", "#a06a42", "#e8b390"),
)


def _portrait(style: str, hair: str, coat: str, skin: str, variant: int) -> Image.Image:
    scale = 2
    background = ("#ede5d3", "#d9e9ed", "#e9dce9", "#f0ece7")[variant]
    image = Image.new("RGB", (256 * scale, 256 * scale), background)
    draw = ImageDraw.Draw(image)
    def box(coords):
        return tuple(int(v * scale) for v in coords)
    shift = (0, 7, -6, 0)[variant]
    draw.ellipse(box((20 + shift, 190, 236 + shift, 330)), fill=coat)
    draw.rectangle(box((106 + shift, 155, 150 + shift, 209)), fill=skin)
    if style == "long":
        draw.ellipse(box((61 + shift, 36, 195 + shift, 232)), fill=hair)
    elif style == "twins":
        for x in (42, 168):
            draw.ellipse(box((x + shift, 87, x + 48 + shift, 174)), fill=hair)
    elif style == "curls":
        for x, y in ((70, 78), (91, 49), (121, 42), (151, 53), (173, 81)):
            draw.ellipse(box((x - 25 + shift, y - 20, x + 25 + shift, y + 29)), fill=hair)
    elif style == "spikes":
        draw.polygon([tuple(int(v * scale) for v in p) for p in
                      ((62 + shift, 114), (54 + shift, 33), (83 + shift, 63),
                       (102 + shift, 18), (125 + shift, 52), (154 + shift, 20),
                       (173 + shift, 63), (200 + shift, 39), (190 + shift, 119))],
                     fill=hair)
    else:
        draw.ellipse(box((66 + shift, 46, 190 + shift, 154)), fill=hair)
    draw.ellipse(box((78 + shift, 75, 178 + shift, 191)), fill=skin)
    if style == "bob":
        draw.rectangle(box((65 + shift, 96, 84 + shift, 174)), fill=hair)
        draw.rectangle(box((174 + shift, 96, 193 + shift, 174)), fill=hair)
        draw.pieslice(box((68 + shift, 46, 188 + shift, 122)), 180, 360, fill=hair)
    elif style == "cap":
        draw.ellipse(box((61 + shift, 39, 195 + shift, 102)), fill=hair)
        draw.rounded_rectangle(box((49 + shift, 85, 205 + shift, 103)), radius=8 * scale,
                               fill="#374a5a")
    else:
        draw.pieslice(box((69 + shift, 47, 187 + shift, 111)), 180, 360, fill=hair)
    for x in (105, 148):
        draw.ellipse(box((x - 5 + shift, 120, x + 5 + shift, 130)), fill="#253044")
    draw.arc(box((111 + shift, 139, 145 + shift, 160)), 10, 170, fill="#833f4b", width=3 * scale)
    if style == "twins":
        for x in (70, 184):
            draw.ellipse(box((x - 8 + shift, 108, x + 8 + shift, 125)), fill="#efd577")
    if style == "cap":
        draw.rectangle(box((109 + shift, 198, 147 + shift, 214)), fill="#dae6ec")
    if variant == 2:
        image = image.crop(box((24, 13, 232, 221))).resize((256, 256), Image.Resampling.LANCZOS)
    else:
        image = image.resize((256, 256), Image.Resampling.LANCZOS)
        if variant == 1:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif variant == 3:
            image = ImageOps.grayscale(image).convert("RGB").rotate(
                7, resample=Image.Resampling.BICUBIC, fillcolor="#eeeeee"
            )
    return image


def generate(root: Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    items = []
    for label, style, hair, coat, skin in CHARACTERS:
        for variant in range(4):
            path = root / f"{label}-{variant}.png"
            _portrait(style, hair, coat, skin, variant).save(path, format="PNG")
            items.append({"file": path.name, "label": label,
                          "role": "gallery" if variant == 0 else "query",
                          "sha256": sha256(path.read_bytes()).hexdigest()})
    manifest = {"schema": "defiantmaple.embedding-fixture.v2", "seed": "deterministic",
                "generator": "benchmarks.embedding_fixture", "pillow_version": pillow_version,
                "items": items}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
