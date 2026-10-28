"""Name-only JSON derivative tests, using generated temporary files only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defiantmaple.metadata_name_export import encode_name_export, save_name_export


class NameExportTests(unittest.TestCase):
    def test_deterministic_document_explicit_omission_and_empty_default(self):
        self.assertEqual(encode_name_export({"Artist": ["人"], "tags": ["line\n\"quote\"\u0000"]}),
                         encode_name_export({"tags": ["line\n\"quote\"\u0000"], "Artist": ["人"]}))
        doc = json.loads(encode_name_export({"tags": ["line\n\"quote\"\u0000"]}))
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["names"], {"tags": ["line\n\"quote\"\u0000"]})
        self.assertEqual(doc["included_fields"], ["tags"])
        self.assertIn("Location", doc["omitted_fields"])
        self.assertNotIn("asset_id", doc)
        self.assertEqual(json.loads(encode_name_export({}))["names"], {})

    def test_unknown_types_counts_and_text_bounds_refuse(self):
        for value in ({"asset_id": ["hidden"]}, {"tags": "wrong"}, {"tags": [3]}, [],
                      {"tags": ["x"] * 257}, {"tags": ["é" * 32769]}, {"tags": ["\ud800"]},
                      {"tags": ["\x00" * 40000]}):
            with self.subTest(value_type=type(value)):
                with self.assertRaises(ValueError):
                    encode_name_export(value)

    def test_new_complete_file_only_and_mode(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "names.json"
            payload = encode_name_export({"Location": ["Fictional place"]})
            self.assertTrue(save_name_export(path, payload).published)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(list(Path(root).iterdir()), [path])
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            self.assertFalse(save_name_export(path, encode_name_export({})).published)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode), before)

    def test_existing_directory_and_dangling_symlink_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "directory"
            directory.mkdir()
            self.assertFalse(save_name_export(directory, b"{}").published)
            link = Path(root) / "link.json"
            try:
                link.symlink_to(Path(root) / "missing")
            except OSError:
                self.skipTest("Host does not permit generated symlinks")
            self.assertFalse(save_name_export(link, b"{}").published)
            self.assertTrue(link.is_symlink())
            self.assertFalse(link.exists())

    def test_failure_before_publication_cleans_only_staging(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "names.json"
            with patch("defiantmaple.metadata_name_export.os.fsync", side_effect=OSError(28, "private path")):
                result = save_name_export(path, b"{}")
            self.assertFalse(result.published)
            self.assertFalse(result.cleanup_pending)
            self.assertNotIn("private path", result.error)
            self.assertEqual(list(Path(root).iterdir()), [])
            with patch("defiantmaple.metadata_name_export.os.link", side_effect=OSError(95, "unsupported")):
                result = save_name_export(path, b"{}")
            self.assertFalse(result.published)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_cleanup_failure_preserves_success_and_destination(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "names.json"
            with patch("defiantmaple.metadata_name_export.os.unlink", side_effect=PermissionError(13, "private")):
                result = save_name_export(path, b"{}")
            self.assertTrue(result.published)
            self.assertTrue(result.cleanup_pending)
            self.assertEqual(path.read_bytes(), b"{}")
            self.assertEqual(len(list(Path(root).iterdir())), 2)

    def test_replaced_staging_is_not_unlinked(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "names.json"
            actual_link = os.link
            def replace_after_link(staging, destination, **kwargs):
                actual_link(staging, destination, **kwargs)
                os.unlink(staging)
                Path(staging).write_bytes(b"replacement")
            with patch("defiantmaple.metadata_name_export.os.link", side_effect=replace_after_link):
                result = save_name_export(path, b"{}")
            self.assertTrue(result.published)
            self.assertTrue(result.cleanup_pending)
            self.assertEqual(path.read_bytes(), b"{}")
            self.assertIn(b"replacement", [p.read_bytes() for p in Path(root).iterdir()])

    def test_descriptor_closed_if_stream_ownership_fails(self):
        with tempfile.TemporaryDirectory() as root:
            actual_close = os.close
            with patch("defiantmaple.metadata_name_export.os.fdopen", side_effect=OSError(5, "generated")), patch(
                    "defiantmaple.metadata_name_export.os.close", wraps=actual_close) as close:
                result = save_name_export(Path(root) / "names.json", b"{}")
            self.assertFalse(result.published)
            close.assert_called_once()
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_changed_staging_identity_refuses_publication(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "names.json"
            actual_stat = os.lstat
            def changed_stat(staging):
                value = actual_stat(staging)
                from types import SimpleNamespace
                return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + 1)
            with patch("defiantmaple.metadata_name_export.os.lstat", side_effect=changed_stat):
                result = save_name_export(path, b"{}")
            self.assertFalse(result.published)
            self.assertTrue(result.cleanup_pending)
            self.assertFalse(path.exists())
