import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

from defiantmaple.__main__ import main
from defiantmaple.catalog import index_file, initialize
from defiantmaple.thumbnail import (ThumbnailCancelled, ThumbnailError,
                                   ThumbnailLimits, _cache_lock, _run_decoder,
                                   thumbnail_for)


def _sleeping_decoder(_payload, sender):
    time.sleep(10)
    sender.close()


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

    def test_cancel_waiting_for_cache_lock(self):
        lock = self.root / "busy.lock"
        lock.write_text(json.dumps({"expires_at": time.time() + 60, "token": "other"}))
        canceled = threading.Event()
        timer = threading.Timer(.1, canceled.set)
        timer.start()
        began = time.monotonic()
        try:
            with self.assertRaises(ThumbnailCancelled):
                with _cache_lock(lock, 6, canceled):
                    self.fail("canceled lock was acquired")
        finally:
            timer.join()
        self.assertLess(time.monotonic() - began, 1)
        self.assertTrue(lock.exists())  # Other owner's lease is left alone.

    def test_cancel_terminates_decoder_child(self):
        canceled = threading.Event()
        timer = threading.Timer(.2, canceled.set)
        began = time.monotonic()
        with patch("defiantmaple.thumbnail._decode_worker", _sleeping_decoder):
            timer.start()
            try:
                with self.assertRaises(ThumbnailCancelled):
                    _run_decoder({}, 6, canceled)
            finally:
                timer.join()
        self.assertLess(time.monotonic() - began, 2)

    def test_cancel_full_thumbnail_cleans_cache_and_preserves_source(self):
        source = self.image("cancel-source.png", (96, 48))
        original = source.read_bytes()
        asset_id = index_file(self.database, source)
        canceled = threading.Event()
        before_children = {child.pid for child in multiprocessing.active_children()}
        with patch("defiantmaple.thumbnail._decode_worker", _sleeping_decoder):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(thumbnail_for, self.database, asset_id,
                                      self.cache, 128, ThumbnailLimits(timeout_seconds=6),
                                      canceled)
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not ({child.pid for child in
                        multiprocessing.active_children()} - before_children):
                    time.sleep(.01)
                self.assertTrue({child.pid for child in multiprocessing.active_children()}
                                - before_children, "decoder child did not start")
                canceled.set()
                with self.assertRaises(ThumbnailCancelled):
                    pending.result(timeout=3)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.cache.rglob("*.png")), [])
        self.assertEqual(list(self.cache.rglob("*.json")), [])
        self.assertEqual(list(self.cache.rglob("*.lock")), [])
        self.assertEqual(list(self.cache.rglob(".thumbnail-worker-*")), [])
        self.assertEqual({child.pid for child in multiprocessing.active_children()},
                         before_children)

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

    def test_cache_does_not_bypass_a_stricter_limit_policy(self):
        source = self.image("policy.png", (64, 64))
        asset_id = index_file(self.database, source)
        permissive = ThumbnailLimits(max_dimension=128, max_pixels=16_384)
        generated = thumbnail_for(
            self.database, asset_id, self.cache, max_edge=32, limits=permissive
        )
        self.assertFalse(generated["cache_hit"])

        strict = ThumbnailLimits(max_dimension=32, max_pixels=16_384)
        with self.assertRaisesRegex(ThumbnailError, "oversized_image"):
            thumbnail_for(
                self.database, asset_id, self.cache, max_edge=32, limits=strict
            )

    def test_concurrent_callers_publish_one_complete_entry(self):
        source = self.image("concurrent.png", (128, 64))
        asset_id = index_file(self.database, source)

        def generate():
            return thumbnail_for(self.database, asset_id, self.cache, max_edge=64)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: generate(), range(2)))
        self.assertEqual(sorted(result["cache_hit"] for result in results), [False, True])
        self.assertEqual(results[0]["path"], results[1]["path"])
        self.assertTrue(Path(results[0]["path"]).is_file())
        self.assertTrue(Path(results[0]["path"]).with_suffix(".json").is_file())

    def test_png_color_key_transparency_is_preserved(self):
        source = self.root / "transparent.png"
        image = Image.new("RGB", (32, 32), (255, 0, 0))
        for y in range(32):
            image.putpixel((31, y), (0, 255, 0))
        image.save(source, format="PNG", transparency=(255, 0, 0))
        image.close()
        asset_id = index_file(self.database, source)

        result = thumbnail_for(self.database, asset_id, self.cache, max_edge=32)
        with Image.open(result["path"]) as thumbnail:
            self.assertEqual(thumbnail.mode, "RGBA")
            self.assertEqual(thumbnail.getpixel((0, 0))[3], 0)
            self.assertEqual(thumbnail.getpixel((31, 0))[3], 255)

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
