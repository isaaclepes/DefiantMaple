"""Executable-boundary tests use real fixed OS-account admission namespace."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from defiantmaple.admission import admission_session
from defiantmaple.catalog import initialize
from defiantmaple.private_eval import PrivateSelectionStore


class AdmissionCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "catalog.sqlite3"
        initialize(self.catalog)

    def cli(self, *arguments, env=None):
        return subprocess.run([sys.executable, "-m", "defiantmaple", *map(str, arguments)],
                              capture_output=True, text=True, timeout=15, env=env)

    def test_current_cli_refuses_owner_with_varied_home(self):
        before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        env = dict(os.environ, HOME=str(self.root / "different-home"), XDG_STATE_HOME=str(self.root / "else"))
        with admission_session(self.catalog):
            result = self.cli("list", self.catalog, env=env)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("already in use", json.loads(result.stderr)["error"])
        self.assertEqual(hashlib.sha256(self.catalog.read_bytes()).hexdigest(), before)
        result = self.cli("list", self.catalog)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_cli_initializes_absent_parent_and_catalog(self):
        destination = self.root / "new-parent" / "new.sqlite3"
        result = self.cli("init", destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["created"])
        self.assertEqual(json.loads(result.stdout)["schema_version"], 7)
        result = self.cli("init", destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["created"])

    def test_private_selection_hardlink_refused_before_schema_mutation(self):
        alias = self.root / "evaluation.sqlite3"
        try:
            os.link(self.catalog, alias)
        except OSError as exc:
            self.skipTest(f"hardlinks unavailable: {exc}")
        before = hashlib.sha256(self.catalog.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "separate database"):
            PrivateSelectionStore(alias, self.catalog)
        self.assertEqual(hashlib.sha256(self.catalog.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
