"""The CI-facing frozen-smoke failure clue must never print fixture paths."""
from pathlib import Path, PureWindowsPath
import unittest

from prototypes.qt.package import _recovery_smoke_ci_diagnostic


class RecoveryPackageDiagnosticTests(unittest.TestCase):
    def test_terminal_error_is_bounded_and_redacts_generated_and_other_paths(self):
        fixture_parent = Path("/Users/runner/work/DefiantMaple/DefiantMaple")
        fixture = fixture_parent / "defiantmaple-recovery-smoke-private"
        stderr = (b'Traceback (most recent call last):\n'
                  b'  File "/Users/runner/My Private Folder/worker.py", line 3\n'
                  b'RuntimeError: cannot open ' + str(fixture / "generated.sqlite3").encode()
                  + b' or C:\\Users\\runner\\secret.sqlite3 ' + b'x' * 900 + b'\n')
        summary = _recovery_smoke_ci_diagnostic(1, b"generated child output", stderr,
                                                 fixture, fixture_parent)
        self.assertIn("direct_exit=1", summary)
        self.assertIn("stdout_sha256=", summary)
        self.assertIn("stderr_sha256=", summary)
        self.assertIn("<path>", summary)
        self.assertNotIn("/Users/", summary)
        self.assertNotIn("C:\\Users", summary)
        self.assertNotIn("secret.sqlite3", summary)
        self.assertLess(len(summary), 900)

    def test_uncertain_terminal_line_is_omitted(self):
        summary = _recovery_smoke_ci_diagnostic(
            -6, b"", b"RuntimeError: odd\tcontrol\n", Path("/tmp/generated"), Path("/tmp"))
        self.assertIn("direct_exit=-6", summary)
        self.assertIn("stderr_terminal=None", summary)

    def test_quoted_absolute_path_with_spaces_is_redacted(self):
        summary = _recovery_smoke_ci_diagnostic(
            1, b"", b'RuntimeError: missing "/Users/other/Private Folder/file.txt"\n',
            Path("/tmp/generated"), Path("/tmp"))
        self.assertIn("RuntimeError: missing", summary)
        self.assertIn("<path>", summary)
        self.assertNotIn("Private Folder", summary)

    def test_windows_fixture_root_descendant_keeps_path_free_clue(self):
        fixture_parent = PureWindowsPath("C:/Users/runner/work/DefiantMaple")
        fixture = fixture_parent / "defiantmaple-recovery-smoke-private"
        stderr = ("RuntimeError: generated target " + str(fixture / "generated.sqlite3")
                  + " was refused\n").encode()
        summary = _recovery_smoke_ci_diagnostic(1, b"", stderr, fixture, fixture_parent)
        self.assertIn("RuntimeError: generated target", summary)
        self.assertIn("<path>", summary)
        self.assertNotIn("generated.sqlite3", summary)
        self.assertNotIn("C:\\Users", summary)
        self.assertNotIn("stderr_terminal=None", summary)


if __name__ == "__main__":
    unittest.main()
