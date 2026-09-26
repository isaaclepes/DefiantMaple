import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from defiantmaple.__main__ import main
from defiantmaple.catalog import index_file, initialize
from defiantmaple.thumbnail import ThumbnailError, ThumbnailLimits, thumbnail_for


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "catalog.sqlite3"
        self.cache = self.root / "cache"
        initialize(self.database)

    def image(self, name="source.png", size=(80, 40)):
        path = self.root / name
        Image.new("RGB", size, (31, 79, 127)).save(path, format="PNG")
        return path

    def test_cache_is_keyed_by_asset_fingerprint_and_repairs_corruption(self):
        source = self.image()
        original = source.read_bytes()
        asset_id = index_file(self.database, source)

        first = thumbnail_for(self.database, asset_id, self.cache, max_edge=32)
        self.assertFalse(first["cache_hit"])
        self.assertEqual((first["width"], first["height"]), (32, 16))
        output = Path(first["path"])
        self.assertIn(asset_id, output.parts)
        self.assertIn(first["source_sha256"], str(output))
        self.assertEqual(source.read_bytes(), original)

        second = thumbnail_for(self.database, asset_id, self.cache, max_edge=32)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["output_sha256"], first["output_sha256"])

        output.write_bytes(b"corrupt cache entry")
        repaired = thumbnail_for(self.database, asset_id, self.cache, max_edge=32)
        self.assertFalse(repaired["cache_hit"])
        self.assertEqual(repaired["output_sha256"], first["output_sha256"])
        with Image.open(output) as thumbnail:
            self.assertEqual(thumbnail.size, (32, 16))

    def test_malformed_image_failure_is_contained_and_leaves_no_output(self):
        malformed = self.root / "malformed.png"
        malformed.write_bytes(b"\x89PNG\r\n\x1a\nnot a decodable image")
        asset_id = index_file(self.database, malformed)

        with self.assertRaisesRegex(ThumbnailError, "decode_error"):
            thumbnail_for(self.database, asset_id, self.cache)
        self.assertEqual(list(self.cache.rglob("*.png")), [])
        self.assertEqual(malformed.read_bytes(), b"\x89PNG\r\n\x1a\nnot a decodable image")

    def test_oversized_dimensions_and_changed_sources_are_rejected(self):
        oversized = self.image("oversized.png", (64, 64))
        oversized_id = index_file(self.database, oversized)
        limits = ThumbnailLimits(max_dimension=32, max_pixels=4_096)
        with self.assertRaisesRegex(ThumbnailError, "oversized_image"):
            thumbnail_for(self.database, oversized_id, self.cache, limits=limits)

        changed = self.image("changed.png")
        changed_id = index_file(self.database, changed)
        changed.write_bytes(changed.read_bytes() + b"changed")
        with self.assertRaisesRegex(ThumbnailError, "catalog fingerprint"):
            thumbnail_for(self.database, changed_id, self.cache)
        self.assertEqual(list(self.cache.rglob("*.png")), [])

    def test_cli_generates_thumbnail_and_rejects_non_images(self):
        source = self.image()
        asset_id = index_file(self.database, source)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([
                "thumbnail", str(self.database), asset_id, str(self.cache),
                "--max-edge", "48",
            ]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual((result["width"], result["height"]), (48, 24))
        self.assertTrue(Path(result["path"]).is_file())

        video = self.root / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 32)
        video_id = index_file(self.database, video)
        with self.assertRaisesRegex(ThumbnailError, "unsupported_media"):
            thumbnail_for(self.database, video_id, self.cache)

    def test_limits_validate_values(self):
        with self.assertRaises(ValueError):
            ThumbnailLimits(max_pixels=0)
        with self.assertRaises(ValueError):
            thumbnail_for(self.database, "not-a-uuid", self.cache)


if __name__ == "__main__":
    unittest.main()
