"""The manual fixture must exercise real scan and thumbnail failure paths."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from benchmarks.gallery_fixture import generate
from defiantmaple.catalog import connect, initialize
from defiantmaple.sources import add_source, scan_sources
from defiantmaple.thumbnail import ThumbnailError, thumbnail_for


class GalleryFixtureTests(unittest.TestCase):
    def test_generated_formats_duplicates_and_decoder_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            art = root / "fictional-art"
            metadata = generate(art)
            self.assertEqual(metadata["images"], 9)
            self.assertEqual(len(list(art.iterdir())), 10)
            self.assertEqual((art / "fictional-amber.png").read_bytes(),
                             (art / "fictional-amber-copy.png").read_bytes())
            database = root / "library.sqlite3"
            cache = root / "thumbnails"
            initialize(database)
            source = add_source(database, art)
            for instant in (1_000_000_000, 2_000_000_000):
                result = scan_sources(database, source_id=source["source_id"],
                                      quiet_seconds=0, now_ns=instant)
            self.assertEqual(result["totals"]["indexed"], 9)
            self.assertEqual(result["totals"]["unsupported"], 1)
            with connect(database) as db:
                assets = {Path(row["current_path"]).name: row["asset_id"]
                          for row in db.execute("SELECT asset_id,current_path FROM assets")}
            for name in ("fictional-amber.png", "fictional-blue.jpg",
                         "fictional-violet.gif", "fictional-green.webp"):
                thumb = thumbnail_for(database, assets[name], cache, max_edge=128)
                self.assertTrue(Path(thumb["path"]).exists())
                self.assertTrue(thumbnail_for(database, assets[name], cache,
                                              max_edge=128)["cache_hit"])
            with Image.open(thumbnail_for(
                database, assets["fictional-transparent.png"], cache,
                max_edge=128)["path"]) as transparent:
                self.assertEqual(transparent.mode, "RGBA")
                self.assertEqual(transparent.getpixel((0, 0))[3], 0)
            with Image.open(thumbnail_for(
                database, assets["fictional-exif.jpg"], cache,
                max_edge=128)["path"]) as oriented:
                self.assertGreater(oriented.width, oriented.height)
            with self.assertRaisesRegex(ThumbnailError, "decode_error"):
                thumbnail_for(database, assets["fictional-malformed.png"], cache)
            with self.assertRaisesRegex(ThumbnailError, "oversized_image"):
                thumbnail_for(database, assets["fictional-oversized.png"], cache)


if __name__ == "__main__":
    unittest.main()
