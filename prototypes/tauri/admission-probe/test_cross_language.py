"""Actual-host oracle. Build probe, then pass its executable as argv[1].

Run from repository root: python prototypes/tauri/admission-probe/test_cross_language.py PROBE
No Windows behavior is simulated; this runs whichever native host invokes it.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from defiantmaple.admission import LibraryInUseError, admission_session

PROBE = str(Path(sys.argv.pop(1)).resolve()) if len(sys.argv) > 1 else None
if PROBE and Path(PROBE).name == "--built-native":
    PROBE = str(Path(__file__).resolve().parent / "target" / "debug" /
                ("defiantmaple-admission-probe.exe" if os.name == "nt" else "defiantmaple-admission-probe"))


class CrossLanguage(unittest.TestCase):
    @unittest.skipUnless(PROBE, "requires built native admission probe")
    def test_native_mutual_exclusion_aliases_and_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.sqlite3"
            alias = Path(directory) / "hardlink.sqlite3"
            catalog.write_bytes(b"generated admission fixture")
            os.link(catalog, alias)
            before = catalog.read_bytes()
            varied = dict(os.environ, HOME=directory, XDG_STATE_HOME=directory, XDG_DATA_HOME=directory)
            # Python owner refuses real Rust contender, including physical alias.
            with admission_session(catalog):
                for path in (catalog, alias):
                    result = subprocess.run([PROBE, str(path)], env=varied, input="\n", text=True,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("Close the other application", result.stderr)
                    self.assertEqual(catalog.read_bytes(), before)
            # Rust readiness is an emitted acknowledgment after acquired leases.
            owner = subprocess.Popen([PROBE, str(catalog)], env=varied, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                ready = []
                waiter = threading.Thread(target=lambda: ready.append(owner.stdout.readline()), daemon=True)
                waiter.start()
                waiter.join(10)
                self.assertFalse(waiter.is_alive(), "native probe did not acknowledge readiness")
                self.assertEqual(ready, ["ADMITTED\n"])
                for path in (catalog, alias):
                    with self.assertRaises(LibraryInUseError):
                        with admission_session(path):
                            self.fail("Python entered while native Rust owner was active")
                self.assertEqual(catalog.read_bytes(), before)
                owner.kill()
                owner.wait(timeout=10)
                with admission_session(alias) as session:
                    session.validate()
            finally:
                if owner.poll() is None:
                    owner.kill()
                owner.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
